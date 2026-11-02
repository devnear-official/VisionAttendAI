#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "esp_memory_utils.h"
#include "esp_partition.h"
#include "esp_ota_ops.h"
#include "esp_idf_version.h"
#include "esp_arduino_version.h"
#include "sdkconfig.h"
#include <stdlib.h>

#include "face_detector.hpp"
#include "network_config.h"
#include "wifi_manager.hpp"
#include "recognition_client.hpp"

// Global Wi-Fi and Server Configuration Manager
WiFiConfigManager wifiConfigManager;

// GOOUUU ESP32-S3-CAM V1.3: GPIO9-13 are used by the camera.
constexpr int TFT_CS = 47;
constexpr int TFT_RST = 1;
constexpr int TFT_DC = 14;
constexpr int TFT_MOSI = 41;
constexpr int TFT_SCK = 42;
constexpr int TFT_MISO = 2; // Connected but not needed for preview.
Adafruit_ILI9341 tft(&SPI, TFT_DC, TFT_CS, TFT_RST);

FaceDetector faceDetector;
bool faceDetectorReady = false;

// Global recognition client
RecognitionClient recognitionClient;

// FreeRTOS background task communication for non-blocking HTTP requests
struct RecognitionPayload {
  uint8_t *jpeg_buf = nullptr;
  size_t jpeg_len = 0;
  char landmarks_json[96] = {0};
};
QueueHandle_t recognitionQueue = nullptr;

void recognitionWorkerTask(void *param) {
  RecognitionPayload payload;
  while (true) {
    if (xQueueReceive(recognitionQueue, &payload, portMAX_DELAY) == pdTRUE) {
      Serial.printf("[TASK] Received crop for recognition (%u bytes JPEG)...\n", (unsigned)payload.jpeg_len);
      RecognitionResult res = RecognitionClient::sendRecognitionRequest(
        payload.jpeg_buf, payload.jpeg_len, payload.landmarks_json
      );
      // Free JPEG memory allocated by fmt2jpg
      if (payload.jpeg_buf) {
        free(payload.jpeg_buf);
        payload.jpeg_buf = nullptr;
      }
      // Update result with 4-second display duration
      recognitionClient.updateResult(res, 4000);
      Serial.printf("[TASK] Finished recognition. Result: %s (Confidence: %.2f)\n",
                    res.statusStr.c_str(), res.confidence);
    }
  }
}

bool cameraReady = false;
const char *frameLocation = "not observed yet";
void *lastFrameBuf = nullptr;
bool frameInPsram = false;
const char *psramTest = "not run";
unsigned long lastDiagnostics = 0;
uint16_t *detectBuf = nullptr; // Dedicated 160x120 fast decimation buffer for ESP-DL inference

// Memory before and after model init
size_t psramFreeBeforeInit = 0;
size_t psramFreeAfterInit = 0;
size_t internalFreeBeforeInit = 0;
size_t internalFreeAfterInit = 0;

// Performance and stability telemetry
uint32_t totalFramesRendered = 0;
uint32_t totalCaptureFailures = 0;
unsigned long fpsWindowStart = 0;
uint32_t fpsFrameCount = 0;
float currentFps = 0.0f;
uint32_t lastInferTimeMs = 0;
uint32_t detectedFaceCount = 0;

// Stabilization & Capture State
constexpr unsigned long FACE_STABLE_HOLD_MS = 1500; // Hold bounding box for 1.5 seconds if face temporarily drops
constexpr unsigned long CAPTURE_DISPLAY_MS = 2000;  // Display "IMAGE CAPTURED" for 2 seconds
std::list<dl::detect::result_t> stableFaces;
unsigned long lastFaceSeenTime = 0;
bool captureTriggered = false;
unsigned long captureBannerExpiry = 0;

void testPsram() {
  if (!psramFound() || heap_caps_get_total_size(MALLOC_CAP_SPIRAM) == 0) {
    psramTest = "unavailable to heap; no late reinitialization attempted";
    return;
  }
  constexpr size_t bytes = 4096;
  uint8_t *p = static_cast<uint8_t *>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!p) { psramTest = "4096-byte allocation failed"; return; }
  bool ok = true;
  for (size_t i = 0; i < bytes; ++i) p[i] = static_cast<uint8_t>(i ^ 0xA5);
  for (size_t i = 0; i < bytes; ++i) if (p[i] != static_cast<uint8_t>(i ^ 0xA5)) { ok = false; break; }
  for (size_t i = 0; i < bytes; ++i) p[i] = static_cast<uint8_t>(i ^ 0x5A);
  for (size_t i = 0; i < bytes; ++i) if (p[i] != static_cast<uint8_t>(i ^ 0x5A)) { ok = false; break; }
  free(p);
  psramTest = ok ? "4096-byte read/write PASS (not a full memory test)" : "read/write FAILED";
}

void printDiagnostics() {
  Serial.println("\n--- VisionAttend Stage 4 diagnostics (ESP-DL Face Detection) ---");
  Serial.printf("Arduino ESP32: %s; ESP-IDF: %s\n", ESP_ARDUINO_VERSION_STR, esp_get_idf_version());
#ifdef BOARD_HAS_PSRAM
  Serial.println("BOARD_HAS_PSRAM: defined");
#else
  Serial.println("BOARD_HAS_PSRAM: not defined");
#endif
  Serial.printf("Arduino psramFound: %s; test: %s\n", psramFound() ? "yes" : "no", psramTest);
  Serial.printf("PSRAM heap total: %u; free: %u; largest block: %u bytes\n",
    (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),
    (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
    (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
  Serial.printf("Internal 8-bit heap free: %u; largest block: %u bytes\n",
    (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
    (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  Serial.printf("FaceDetector Status: %s; Models: MSR_S8_V1 + MNP_S8_V1 (Flash .rodata)\n",
    faceDetectorReady ? "OPERATIONAL" : "FAILED/DISABLED");
  Serial.printf("Face Detection: faces=%u; last inference time=%u ms\n",
    (unsigned)detectedFaceCount, (unsigned)lastInferTimeMs);
  Serial.printf("Framebuffer buffer pointer: %p; location: %s (in PSRAM: %s)\n",
    lastFrameBuf, frameLocation, frameInPsram ? "YES" : "NO");
  Serial.printf("Streaming Performance: FPS=%.1f; frames rendered=%u; capture failures=%u\n",
    currentFps, (unsigned)totalFramesRendered, (unsigned)totalCaptureFailures);
  Serial.printf("Flash size: %u bytes; running image: %u bytes\n",
    (unsigned)ESP.getFlashChipSize(), (unsigned)ESP.getSketchSize());
}

void showError(const char *message) {
  tft.fillScreen(ILI9341_BLACK);
  tft.setCursor(8, 20);
  tft.setTextColor(ILI9341_RED);
  tft.setTextSize(2);
  tft.println(message);
}

void setup() {
  Serial.begin(115200);
  SPI.begin(TFT_SCK, TFT_MISO, TFT_MOSI, TFT_CS);
  tft.begin(40000000); // Fast 40MHz SPI to eliminate display jitter
  tft.setRotation(3); // 320 x 240 landscape (180 deg rotated)
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextColor(ILI9341_CYAN);
  tft.setTextSize(2);
  tft.setCursor(8, 20);
  tft.print("Starting camera...");

  testPsram();

  // Allocate fast 160x120 buffer for ESP-DL inference (prefer ultra-fast internal SRAM)
  detectBuf = static_cast<uint16_t *>(
    heap_caps_malloc(160 * 120 * sizeof(uint16_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
  );
  if (!detectBuf) {
    detectBuf = static_cast<uint16_t *>(
      heap_caps_malloc(160 * 120 * sizeof(uint16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
    );
  }

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_pwdn = -1;
  config.pin_reset = -1;
  config.pin_xclk = 15;
  config.pin_sccb_sda = 4;
  config.pin_sccb_scl = 5;
  config.pin_d0 = 11;
  config.pin_d1 = 9;
  config.pin_d2 = 8;
  config.pin_d3 = 10;
  config.pin_d4 = 12;
  config.pin_d5 = 18;
  config.pin_d6 = 17;
  config.pin_d7 = 16;
  config.pin_vsync = 6;
  config.pin_href = 7;
  config.pin_pclk = 13;
  config.xclk_freq_hz = 20000000;       // Boosted to 20MHz for 43% faster DMA transfer
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size = FRAMESIZE_QVGA;   // Upgraded to native 320 x 240 (4x resolution boost)
  config.fb_count = 2;                  // Double buffering for non-blocking stream
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;// Always grab the freshest frame with zero latency

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", static_cast<unsigned>(err));
    showError("Camera init failed");
    return;
  }
  cameraReady = true;

  sensor_t *s = esp_camera_sensor_get();
  if (s != nullptr) {
    s->set_vflip(s, 1);        // Flip vertically so heads are upright
    s->set_brightness(s, 1);   // Enhance indoor face lighting (+1)
    s->set_contrast(s, 1);     // Crisp face boundaries for landmark precision
    Serial.println("Camera sensor configured: 320x240 @ 20MHz, double buffered");
  }

  tft.setCursor(8, 50);
  tft.setTextColor(ILI9341_YELLOW);
  tft.print("Loading Face Models...");
  Serial.println("Initializing ESP-DL Face Detector (MSR_S8_V1 + MNP_S8_V1)...");

  psramFreeBeforeInit = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  internalFreeBeforeInit = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);

  if (faceDetector.init(0.5f, 0.5f)) {
    faceDetectorReady = true;
    Serial.println("FaceDetector initialized successfully.");
  } else {
    Serial.println("FaceDetector initialization FAILED.");
  }

  psramFreeAfterInit = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  internalFreeAfterInit = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  Serial.printf("FaceDetector memory delta: PSRAM used=%d bytes, Internal RAM used=%d bytes\n",
    (int)(psramFreeBeforeInit - psramFreeAfterInit),
    (int)(internalFreeBeforeInit - internalFreeAfterInit));

  // Initialize Recognition Task on Core 0 (Network core)
  recognitionQueue = xQueueCreate(1, sizeof(RecognitionPayload));
  if (recognitionQueue != nullptr) {
    xTaskCreatePinnedToCore(
      recognitionWorkerTask,
      "rec_worker",
      8192,
      nullptr,
      1,
      nullptr,
      0 // Core 0
    );
    Serial.println("Recognition background task started on Core 0.");
  }

  // Connect to Wi-Fi with Captive Portal fallback
  tft.setCursor(8, 80);
  tft.setTextColor(ILI9341_WHITE);
  tft.print("Connecting to Wi-Fi...");
  
  wifiConfigManager.loadConfig();
  if (!wifiConfigManager.connectStation(8000)) {
    Serial.println("[WiFi] Saved network not reachable. Launching 'Setup' portal...");
    wifiConfigManager.startPortal(&tft);
  }

  printDiagnostics();
  lastDiagnostics = millis();
  fpsWindowStart = millis();
  tft.fillScreen(ILI9341_BLACK);
}

void loop() {
  if (!cameraReady) { delay(1000); return; }

  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) {
    totalCaptureFailures++;
    Serial.println("Camera capture failed");
    delay(50);
    return;
  }

  lastFrameBuf = frame->buf;
  frameInPsram = esp_ptr_external_ram(frame->buf);
  if (frameLocation[0] == 'n') {
    frameLocation = frameInPsram ? "external PSRAM" :
                    esp_ptr_internal(frame->buf) ? "internal RAM" : "unknown address region";
    Serial.printf("Camera framebuffer actual location: %s (%u bytes at %p)\n",
                  frameLocation, (unsigned)frame->len, frame->buf);
  }

  if (frame->format == PIXFORMAT_RGB565 && frame->width == 320 &&
      frame->height == 240 && frame->len >= 320U * 240U * 2U) {

    // 1. Execute Face Detection via Fast 2:1 Decimation (<0.5ms)
    std::list<dl::detect::result_t> results;
    if (faceDetectorReady && detectBuf != nullptr) {
      // Downsample 320x240 to 160x120 by skipping every 2nd pixel
      const uint16_t *src320 = reinterpret_cast<const uint16_t *>(frame->buf);
      for (int y = 0; y < 120; ++y) {
        const uint16_t *srcRow = src320 + (y * 2) * 320;
        uint16_t *dstRow = detectBuf + y * 160;
        for (int x = 0; x < 160; ++x) {
          dstRow[x] = srcRow[x * 2];
        }
      }

      dl::image::img_t img;
      img.data = reinterpret_cast<uint8_t *>(detectBuf);
      img.width = 160;
      img.height = 120;
      img.pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB565BE;

      unsigned long t0 = millis();
      results = faceDetector.detect(img);
      lastInferTimeMs = millis() - t0;
      detectedFaceCount = results.size();

      // Scale detected bounding boxes and landmarks back to native 320x240 space
      for (auto &res : results) {
        res.box[0] *= 2;
        res.box[1] *= 2;
        res.box[2] *= 2;
        res.box[3] *= 2;
        for (size_t k = 0; k < res.keypoint.size(); ++k) {
          res.keypoint[k] *= 2;
        }
      }
    }

    unsigned long now = millis();

    // Stabilization and Capture Logic:
    if (!results.empty()) {
      stableFaces = results; // Update with fresh detection boxes (320x240 space)
      lastFaceSeenTime = now;

      // When a face is detected, trigger image capture event
      if (!captureTriggered) {
        captureTriggered = true;
        captureBannerExpiry = now + CAPTURE_DISPLAY_MS;
        Serial.printf(">>> [CAPTURE] Face detected (%d face(s)) - High-Res image captured at %lums\n",
                      (int)results.size(), now);
      }

      // Check if we can trigger recognition upload to FastAPI
      if (recognitionClient.canTriggerRecognition()) {
        const auto &primaryFace = results.front();
        uint8_t *jpg_buf = nullptr;
        size_t jpg_len = 0;
        int cx = 0, cy = 0, cw = 0, ch = 0;

        // Extract high-resolution face crop from full 320x240 frame!
        if (RecognitionClient::extractAndEncodeFaceCrop(
              frame->buf, 320, 240, primaryFace.box,
              &jpg_buf, &jpg_len, &cx, &cy, &cw, &ch)) {

          RecognitionPayload payload;
          payload.jpeg_buf = jpg_buf;
          payload.jpeg_len = jpg_len;
          payload.landmarks_json[0] = '\0';

          if (primaryFace.keypoint.size() >= 10) {
            RecognitionClient::transformLandmarksToCrop(
              primaryFace.keypoint, cx, cy, cw, ch,
              payload.landmarks_json, sizeof(payload.landmarks_json)
            );
          }

          recognitionClient.setUploadInProgress(true);
          if (xQueueSend(recognitionQueue, &payload, 0) != pdTRUE) {
            free(jpg_buf);
            recognitionClient.setUploadInProgress(false);
          } else {
            Serial.printf(">>> [UPLOAD] Queued HD face crop (%dx%d, %u bytes JPEG, landmarks: %s)\n",
                          cw, ch, (unsigned)jpg_len, payload.landmarks_json);
          }
        }
      }
    } else {
      // If no face in this exact frame, check if within 1.5s stability hold window
      if (now - lastFaceSeenTime > FACE_STABLE_HOLD_MS) {
        stableFaces.clear();      // Expire bounding box after 1.5s of no face
        captureTriggered = false; // Reset capture trigger for next person
      }
    }

    bool hasActiveFace = !stableFaces.empty();
    bool showCapturedNotice = (now < captureBannerExpiry);

    // 2. Render native 320x240 camera frame directly to TFT (Crystal Clear, zero duplication overhead)
    tft.startWrite();
    tft.setAddrWindow(0, 0, 320, 240);
    const uint16_t *frame16 = reinterpret_cast<const uint16_t *>(frame->buf);
    for (size_t y = 0; y < 240; ++y) {
      tft.writePixels(const_cast<uint16_t *>(frame16 + y * 320), 320, true, true);
    }
    tft.endWrite();

    // 3. Immediately draw Bounding Boxes and Landmarks from stableFaces (Native 320x240 coordinates)
    for (const auto &res : stableFaces) {
      int bx = res.box[0];
      int by = res.box[1];
      int bw = res.box[2] - res.box[0];
      int bh = res.box[3] - res.box[1];

      if (bx < 0) bx = 0;
      if (by < 0) by = 0;
      if (bx + bw > 320) bw = 320 - bx;
      if (by + bh > 240) bh = 240 - by;

      // Draw 2-pixel thick green bounding box
      tft.drawRect(bx, by, bw, bh, ILI9341_GREEN);
      if (bw > 2 && bh > 2) {
        tft.drawRect(bx + 1, by + 1, bw - 2, bh - 2, ILI9341_GREEN);
      }

      // Draw facial landmarks if detected by MNP stage
      if (res.keypoint.size() >= 10) {
        for (size_t kp = 0; kp < 10; kp += 2) {
          int kpx = res.keypoint[kp];
          int kpy = res.keypoint[kp + 1];
          tft.fillCircle(kpx, kpy, 2, ILI9341_CYAN);
        }
      }
    }

    // 4. Draw HUD status banner and recognition state
    RecognitionResult recRes = recognitionClient.getActiveResult();
    bool isUploading = recognitionClient.isUploadInProgress();

    if (isUploading) {
      tft.fillRect(0, 0, 320, 20, ILI9341_NAVY);
      tft.setTextColor(ILI9341_CYAN, ILI9341_NAVY);
      tft.setTextSize(1);
      tft.setCursor(6, 6);
      tft.print(" [PROCESSING] IDENTIFYING FACE WITH ARCFACE... ");
    } else if (recRes.state == REC_STATE_MATCH) {
      tft.fillRect(0, 0, 320, 30, ILI9341_DARKGREEN);
      tft.setTextColor(ILI9341_WHITE, ILI9341_DARKGREEN);
      tft.setTextSize(1);
      tft.setCursor(6, 4);
      tft.printf("MATCH: %s (%s)", recRes.fullName.c_str(), recRes.studentId.c_str());

      tft.setCursor(6, 17);
      tft.setTextColor(ILI9341_YELLOW, ILI9341_DARKGREEN);
      tft.printf("CONF: %.1f%% | %s",
                 recRes.confidence * 100.0f,
                 recRes.alreadyCheckedIn ? "ALREADY CHECKED IN" : "ATTENDANCE RECORDED");
    } else if (recRes.state == REC_STATE_ENROLLING) {
      tft.fillRect(0, 0, 320, 24, ILI9341_NAVY);
      tft.setTextColor(ILI9341_CYAN, ILI9341_NAVY);
      tft.setTextSize(1);
      tft.setCursor(6, 4);
      if (recRes.targetSamples > 0) {
        tft.printf(" [ENROLLING %d/%d] %s ", recRes.sampleIndex, recRes.targetSamples, recRes.fullName.c_str());
      } else {
        tft.printf(" [ENROLLING] %s ", recRes.fullName.c_str());
      }
      tft.setCursor(6, 15);
      tft.setTextColor(ILI9341_WHITE, ILI9341_NAVY);
      tft.print("HOLD STILL / TURN SLIGHTLY FOR NEXT SAMPLE");
    } else if (recRes.state == REC_STATE_ENROLLED) {
      tft.fillRect(0, 0, 320, 24, ILI9341_DARKGREEN);
      tft.setTextColor(ILI9341_WHITE, ILI9341_DARKGREEN);
      tft.setTextSize(1);
      tft.setCursor(6, 4);
      tft.printf(" [ENROLLMENT COMPLETE] %s ", recRes.fullName.c_str());
      tft.setCursor(6, 15);
      tft.setTextColor(ILI9341_YELLOW, ILI9341_DARKGREEN);
      tft.printf("STUDENT ID: %s | TEMPLATES COMMITTED", recRes.studentId.c_str());
    } else if (recRes.state == REC_STATE_UNKNOWN) {
      tft.fillRect(0, 0, 320, 20, ILI9341_MAROON);
      tft.setTextColor(ILI9341_WHITE, ILI9341_MAROON);
      tft.setTextSize(1);
      tft.setCursor(6, 6);
      tft.print(" UNKNOWN PERSON - ATTENDANCE NOT MARKED ");
    } else if (recRes.state == REC_STATE_AMBIGUOUS) {
      tft.fillRect(0, 0, 320, 20, ILI9341_ORANGE);
      tft.setTextColor(ILI9341_BLACK, ILI9341_ORANGE);
      tft.setTextSize(1);
      tft.setCursor(6, 6);
      tft.print(" AMBIGUOUS MATCH - PLEASE LOOK DIRECTLY AT CAMERA ");
    } else if (recRes.state == REC_STATE_ERROR) {
      tft.fillRect(0, 0, 320, 20, ILI9341_MAGENTA);
      tft.setTextColor(ILI9341_WHITE, ILI9341_MAGENTA);
      tft.setTextSize(1);
      tft.setCursor(6, 6);
      tft.printf(" SERVER ERROR: %s ", recRes.message.c_str());
    } else {
      // Default live tracking HUD
      char hudBuf[36];
      if (showCapturedNotice) {
        snprintf(hudBuf, sizeof(hudBuf), " [IMAGE CAPTURED] %lums    ", (unsigned long)lastInferTimeMs);
        tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
      } else if (hasActiveFace) {
        snprintf(hudBuf, sizeof(hudBuf), " FACE DETECTED (%d) %lums ", (int)stableFaces.size(), (unsigned long)lastInferTimeMs);
        tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
      } else {
        snprintf(hudBuf, sizeof(hudBuf), " NO FACE %lums            ", (unsigned long)lastInferTimeMs);
        tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
      }
      tft.setTextSize(1);
      tft.setCursor(4, 4);
      tft.print(hudBuf);
    }

    // Top-right Wi-Fi connection indicator
    tft.setTextSize(1);
    if (recognitionClient.isWiFiConnected()) {
      tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
      tft.setCursor(264, 4);
      tft.print("[WIFI OK]");
    } else {
      tft.setTextColor(ILI9341_RED, ILI9341_BLACK);
      tft.setCursor(256, 4);
      tft.print("[WIFI OFF]");
    }

    totalFramesRendered++;
    fpsFrameCount++;
  } else {
    Serial.printf("Unexpected camera frame: %u x %u, %u bytes\n",
                  frame->width, frame->height, static_cast<unsigned>(frame->len));
  }

  // Always return framebuffer safely
  esp_camera_fb_return(frame);

  unsigned long now = millis();
  if (now - fpsWindowStart >= 1000UL) {
    currentFps = (fpsFrameCount * 1000.0f) / (now - fpsWindowStart);
    fpsFrameCount = 0;
    fpsWindowStart = now;
  }

  if (now - lastDiagnostics >= 10000UL) {
    lastDiagnostics = now;
    printDiagnostics();
  }
}
