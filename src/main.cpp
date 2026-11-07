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
#include "speaker_driver.hpp"
#include "camera_guidance.hpp"
#include "feedback_manager.hpp"

// Global Wi-Fi and Server Configuration Manager
WiFiConfigManager wifiConfigManager;

// Global I2S Speaker & Audio Manager (MAX98357A on GPIO 38, 39, 40)
SpeakerDriver speakerDriver;
FeedbackManager feedbackManager;

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
static uint8_t *downsampleBuf = nullptr;

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
  unsigned long lastTelemetryCheck = 0;

  while (true) {
    // Wait up to 1500ms for incoming face crops to verify
    if (xQueueReceive(recognitionQueue, &payload, pdMS_TO_TICKS(1500)) == pdTRUE) {
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

      // Dynamic Personalized Student Name Voice Announcement:
      // If backend synthesized personalized speech (e.g. "Welcome Rahim Ahmed. Attendance recorded successfully"),
      // stream and speak it directly over I2S!
      if (res.hasSpeechAudio && res.state == REC_STATE_MATCH && speakerDriver.isEnabled()) {
        const char *targetHost = wifiConfigManager.getBackendHost().c_str();
        uint16_t targetPort = wifiConfigManager.getBackendPort();
        WiFiClient audioClient;
        audioClient.setTimeout(3500);
        if (audioClient.connect(targetHost, targetPort)) {
          String audioPath = "/api/v1/devices/" + String(DEVICE_ID) + "/audio";
          audioClient.printf("GET %s HTTP/1.1\r\n", audioPath.c_str());
          audioClient.printf("Host: %s:%d\r\n", targetHost, targetPort);
          audioClient.printf("X-Device-Api-Key: %s\r\n", DEVICE_API_KEY);
          audioClient.print("Connection: close\r\n\r\n");

          unsigned long aTimeout = millis() + 3500;
          while (!audioClient.available() && millis() < aTimeout) delay(10);
          if (audioClient.available()) {
            String aStatus = audioClient.readStringUntil('\n');
            size_t contentLength = 0;
            while (audioClient.available()) {
              String hl = audioClient.readStringUntil('\n');
              if (hl.startsWith("Content-Length:") || hl.startsWith("content-length:")) {
                contentLength = hl.substring(15).toInt();
              }
              if (hl == "\r" || hl.length() == 0) break;
            }
            if (contentLength > 0) {
              speakerDriver.playRawStream(audioClient, contentLength);
            }
          }
          audioClient.stop();
        }
      } else {
        feedbackManager.handleRecognitionResult(res);
      }

      Serial.printf("[TASK] Finished recognition. Result: %s (Confidence: %.2f)\n",
                    res.statusStr.c_str(), res.confidence);
    } else {
      // Idle cycle: Periodically check backend telemetry, speaker on/off state, and pending audio (every 2.5s)
      unsigned long now = millis();
      if (now - lastTelemetryCheck >= 2500) {
        lastTelemetryCheck = now;
        RecognitionClient::checkDeviceTelemetryAndAudio();
      }
    }
  }
}

bool cameraReady = false;
const char *frameLocation = "not observed yet";
void *lastFrameBuf = nullptr;
bool frameInPsram = false;
const char *psramTest = "not run";
unsigned long lastDiagnostics = 0;

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
constexpr int HUD_HEIGHT = 20;                      // Dedicated top status bar height (flicker-free)
static GFXcanvas16 hudCanvas(320, HUD_HEIGHT);     // Off-screen canvas for 100% flicker-free HUD blitting
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
  config.xclk_freq_hz = 14000000;
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size = FRAMESIZE_QVGA; // 320 x 240 Native High-Definition
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", static_cast<unsigned>(err));
    showError("Camera init failed");
    return;
  }
  cameraReady = true;

  sensor_t *s = esp_camera_sensor_get();
  if (s != nullptr) {
    s->set_vflip(s, 1); // Flip vertically so heads are upright
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    Serial.println("Camera sensor initialized at 320x240 High Resolution");
  }

  // Allocate 160x120 downsample buffer in PSRAM for real-time face detection
  downsampleBuf = (uint8_t*)ps_malloc(160 * 120 * 2);
  if (!downsampleBuf) {
    downsampleBuf = (uint8_t*)malloc(160 * 120 * 2);
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

  // Initialize I2S Audio Driver (MAX98357A on GPIO 38, 39, 40)
  tft.setCursor(8, 110);
  tft.setTextColor(ILI9341_GREEN);
  tft.print("Starting I2S Audio...");
  speakerDriver.init();

  printDiagnostics();
  lastDiagnostics = millis();
  fpsWindowStart = millis();
  tft.fillScreen(ILI9341_BLACK);
}

// -----------------------------------------------------------------------------
// Full-Screen Recognition Result Cards (Large bold text, high-contrast, beautiful)
// -----------------------------------------------------------------------------
void drawCenteredText(const String &text, int y, uint8_t size, uint16_t color, uint16_t bg = ILI9341_BLACK) {
  tft.setTextSize(size);
  tft.setTextColor(color, bg);
  int textWidth = text.length() * 6 * size;
  int x = (320 - textWidth) / 2;
  if (x < 4) x = 4;
  tft.setCursor(x, y);
  tft.print(text);
}

void drawFullScreenMatch(const RecognitionResult &res) {
  tft.fillScreen(ILI9341_BLACK);

  // Top Header Banner
  uint16_t bannerColor = res.alreadyCheckedIn ? ILI9341_BLUE : ILI9341_DARKGREEN;
  tft.fillRect(0, 0, 320, 48, bannerColor);
  tft.drawRect(0, 0, 320, 48, ILI9341_GREEN);

  String headerStr = res.alreadyCheckedIn ? "ALREADY CHECKED IN" : "ATTENDANCE RECORDED";
  drawCenteredText(headerStr, 16, 2, ILI9341_WHITE, bannerColor);

  // Student Full Name (Big, bold)
  uint8_t nameSize = (res.fullName.length() > 17) ? 2 : 3;
  drawCenteredText(res.fullName, 68, nameSize, ILI9341_WHITE, ILI9341_BLACK);

  // Student ID
  String idStr = "ID: " + res.studentId;
  drawCenteredText(idStr, 108, 2, ILI9341_YELLOW, ILI9341_BLACK);

  // Department if available
  if (res.department.length() > 0) {
    drawCenteredText("Dept: " + res.department, 136, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
  }

  // Match Confidence Box
  tft.drawRoundRect(20, 155, 280, 42, 8, ILI9341_DARKGREEN);
  tft.fillRoundRect(22, 157, 276, 38, 6, (uint16_t)0x01E0);
  char confBuf[40];
  snprintf(confBuf, sizeof(confBuf), "Match Confidence: %.1f%%", res.confidence * 100.0f);
  drawCenteredText(confBuf, 168, 2, ILI9341_GREEN, (uint16_t)0x01E0);

  // Bottom Notice
  drawCenteredText("Verified by Face Recognition", 215, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
}

void drawFullScreenUnknown(const RecognitionResult &res) {
  tft.fillScreen(ILI9341_BLACK);

  tft.fillRect(0, 0, 320, 48, ILI9341_MAROON);
  tft.drawRect(0, 0, 320, 48, ILI9341_RED);
  drawCenteredText("ACCESS DENIED", 16, 2, ILI9341_WHITE, ILI9341_MAROON);

  drawCenteredText("UNKNOWN PERSON", 75, 3, ILI9341_RED, ILI9341_BLACK);
  drawCenteredText("Face not in database", 120, 2, ILI9341_YELLOW, ILI9341_BLACK);

  tft.drawRoundRect(20, 155, 280, 42, 8, ILI9341_MAROON);
  drawCenteredText("Attendance NOT marked", 168, 2, ILI9341_RED, ILI9341_BLACK);

  drawCenteredText("Please contact admin to register", 215, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
}

void drawFullScreenAmbiguous(const RecognitionResult &res) {
  tft.fillScreen(ILI9341_BLACK);

  tft.fillRect(0, 0, 320, 48, ILI9341_ORANGE);
  drawCenteredText("LOW CONFIDENCE", 16, 2, ILI9341_BLACK, ILI9341_ORANGE);

  drawCenteredText("PLEASE TRY AGAIN", 75, 2, ILI9341_WHITE, ILI9341_BLACK);
  drawCenteredText("Look directly at camera", 115, 2, ILI9341_YELLOW, ILI9341_BLACK);

  drawCenteredText("Hold still and avoid harsh shadows", 170, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
}

void drawFullScreenError(const RecognitionResult &res) {
  tft.fillScreen(ILI9341_BLACK);

  tft.fillRect(0, 0, 320, 48, ILI9341_MAGENTA);
  drawCenteredText("SERVER NOTICE", 16, 2, ILI9341_WHITE, ILI9341_MAGENTA);

  drawCenteredText("CONNECTION ISSUE", 75, 2, ILI9341_RED, ILI9341_BLACK);
  drawCenteredText(res.message, 115, 2, ILI9341_YELLOW, ILI9341_BLACK);

  drawCenteredText("Please check Wi-Fi & Backend Server", 170, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
}

void drawFullScreenEnrolling(const RecognitionResult &res) {
  tft.fillScreen(ILI9341_BLACK);

  tft.fillRect(0, 0, 320, 48, ILI9341_NAVY);
  tft.drawRect(0, 0, 320, 48, ILI9341_CYAN);
  drawCenteredText("ENROLLING FACE", 16, 2, ILI9341_CYAN, ILI9341_NAVY);

  char sampleBuf[32];
  if (res.targetSamples > 0) {
    snprintf(sampleBuf, sizeof(sampleBuf), "Sample %d of %d", res.sampleIndex, res.targetSamples);
  } else {
    snprintf(sampleBuf, sizeof(sampleBuf), "Capturing Sample...");
  }
  drawCenteredText(sampleBuf, 70, 2, ILI9341_YELLOW, ILI9341_BLACK);
  drawCenteredText(res.fullName, 105, 2, ILI9341_WHITE, ILI9341_BLACK);

  drawCenteredText("Hold still / Turn head slightly", 165, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
}

void drawFullScreenEnrolled(const RecognitionResult &res) {
  tft.fillScreen(ILI9341_BLACK);

  tft.fillRect(0, 0, 320, 48, ILI9341_DARKGREEN);
  tft.drawRect(0, 0, 320, 48, ILI9341_GREEN);
  drawCenteredText("ENROLLMENT COMPLETE", 16, 2, ILI9341_WHITE, ILI9341_DARKGREEN);

  drawCenteredText(res.fullName, 75, 3, ILI9341_WHITE, ILI9341_BLACK);
  drawCenteredText("ID: " + res.studentId, 120, 2, ILI9341_YELLOW, ILI9341_BLACK);

  tft.drawRoundRect(20, 155, 280, 42, 8, ILI9341_DARKGREEN);
  drawCenteredText("Templates Committed", 168, 2, ILI9341_GREEN, ILI9341_BLACK);

  drawCenteredText("Student ready for recognition", 215, 1, ILI9341_LIGHTGREY, ILI9341_BLACK);
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

    // 1. Downsample 320x240 to 160x120 for real-time ESP-DL inference (takes <0.15ms)
    if (downsampleBuf) {
      for (int y = 0; y < 120; ++y) {
        const uint16_t *srcRow = reinterpret_cast<const uint16_t*>(frame->buf + (y * 2) * 320 * 2);
        uint16_t *dstRow = reinterpret_cast<uint16_t*>(downsampleBuf + y * 160 * 2);
        for (int x = 0; x < 160; ++x) {
          dstRow[x] = srcRow[x * 2];
        }
      }
    }

    // 2. Execute Face Detection in memory FIRST (Display is NOT touched during inference)
    std::list<dl::detect::result_t> results;
    if (faceDetectorReady && downsampleBuf) {
      dl::image::img_t img;
      img.data = downsampleBuf;
      img.width = 160;
      img.height = 120;
      img.pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB565BE;

      unsigned long t0 = millis();
      results = faceDetector.detect(img);
      lastInferTimeMs = millis() - t0;
      detectedFaceCount = results.size();
    }

    unsigned long now = millis();

    // Stabilization and Capture Logic:
    if (!results.empty()) {
      stableFaces = results; // Update with fresh detection boxes
      lastFaceSeenTime = now;

      // When a face is detected, trigger image capture event
      if (!captureTriggered) {
        captureTriggered = true;
        captureBannerExpiry = now + CAPTURE_DISPLAY_MS;
        Serial.printf(">>> [CAPTURE] Face detected (%d face(s)) - Image captured at %lums\n",
                      (int)results.size(), now);
      }

      // Check if we can trigger recognition upload to FastAPI
      if (recognitionClient.canTriggerRecognition()) {
        const auto &primaryFace = results.front();
        uint8_t *jpg_buf = nullptr;
        size_t jpg_len = 0;
        int cx = 0, cy = 0, cw = 0, ch = 0;

        // Scale bounding box x2 to crop directly from full-resolution 320x240 frame buffer
        std::vector<int> box320 = {
          primaryFace.box[0] * 2,
          primaryFace.box[1] * 2,
          primaryFace.box[2] * 2,
          primaryFace.box[3] * 2
        };

        if (RecognitionClient::extractAndEncodeFaceCrop(
              frame->buf, 320, 240, box320,
              &jpg_buf, &jpg_len, &cx, &cy, &cw, &ch)) {

          RecognitionPayload payload;
          payload.jpeg_buf = jpg_buf;
          payload.jpeg_len = jpg_len;
          payload.landmarks_json[0] = '\0';

          if (primaryFace.keypoint.size() >= 10) {
            std::vector<int> kp320;
            for (size_t k = 0; k < primaryFace.keypoint.size(); ++k) {
              kp320.push_back(primaryFace.keypoint[k] * 2);
            }
            RecognitionClient::transformLandmarksToCrop(
              kp320, cx, cy, cw, ch,
              payload.landmarks_json, sizeof(payload.landmarks_json)
            );
          }

          recognitionClient.setUploadInProgress(true);
          if (xQueueSend(recognitionQueue, &payload, 0) != pdTRUE) {
            free(jpg_buf);
            recognitionClient.setUploadInProgress(false);
          } else {
            Serial.printf(">>> [UPLOAD] Queued HIGH-RES face crop (%dx%d, %u bytes JPEG, landmarks: %s)\n",
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

    // 4. Check for Full-Screen Recognition Result (Match / Unknown / Error / Enrolling)
    RecognitionResult recRes = recognitionClient.getActiveResult();
    bool isUploading = recognitionClient.isUploadInProgress();

    bool hasFullScreenResult = (recRes.state == REC_STATE_MATCH ||
                                recRes.state == REC_STATE_UNKNOWN ||
                                recRes.state == REC_STATE_AMBIGUOUS ||
                                recRes.state == REC_STATE_ERROR ||
                                recRes.state == REC_STATE_ENROLLING ||
                                recRes.state == REC_STATE_ENROLLED);

    // Camera Guidance Evaluation & Audio Feedback Dispatcher
    GuidanceResult guidance = CameraGuidance::evaluate(
      downsampleBuf ? downsampleBuf : frame->buf, 160, 120, results
    );
    feedbackManager.handleCameraGuidance(guidance, isUploading, hasFullScreenResult);

    static RecognitionState lastDisplayedState = REC_STATE_IDLE;
    static unsigned long lastDisplayedTimestamp = 0;

    if (hasFullScreenResult) {
      // If we haven't drawn this specific result yet, draw the full-screen card ONCE!
      if (lastDisplayedState != recRes.state || lastDisplayedTimestamp != recRes.resultTimestamp) {
        lastDisplayedState = recRes.state;
        lastDisplayedTimestamp = recRes.resultTimestamp;

        switch (recRes.state) {
          case REC_STATE_MATCH:      drawFullScreenMatch(recRes); break;
          case REC_STATE_UNKNOWN:    drawFullScreenUnknown(recRes); break;
          case REC_STATE_AMBIGUOUS:  drawFullScreenAmbiguous(recRes); break;
          case REC_STATE_ERROR:      drawFullScreenError(recRes); break;
          case REC_STATE_ENROLLING:  drawFullScreenEnrolling(recRes); break;
          case REC_STATE_ENROLLED:   drawFullScreenEnrolled(recRes); break;
          default: break;
        }
      }
      // While full-screen card is displayed, skip rendering camera pixels to LCD (frozen & clear)
    } else {
      // If we just exited a full-screen result card, reset state so camera preview resumes cleanly
      if (lastDisplayedState != REC_STATE_IDLE) {
        lastDisplayedState = REC_STATE_IDLE;
        stableFaces.clear();
        captureTriggered = false;
      }

      // 2. Render crisp 320x240 camera frame below HUD - 100% flicker-free & native 1:1 pixel mapping
      tft.startWrite();
      tft.setAddrWindow(0, HUD_HEIGHT, 320, 240 - HUD_HEIGHT);
      for (size_t y = HUD_HEIGHT; y < 240; ++y) {
        const uint16_t *srcRow = reinterpret_cast<const uint16_t*>(frame->buf + y * 320 * 2);
        tft.writePixels(const_cast<uint16_t*>(srcRow), 320, true, true);
      }
      tft.endWrite();

      // 3. Immediately draw Bounding Boxes and Landmarks from stableFaces (1-2s persistent)
      for (const auto &res : stableFaces) {
        // Map 160x120 model coords to 320x240 display coords (x2 scaling)
        int bx = res.box[0] * 2;
        int by = res.box[1] * 2;
        int bw = (res.box[2] - res.box[0]) * 2;
        int bh = (res.box[3] - res.box[1]) * 2;

        if (bx < 0) bx = 0;
        if (by < HUD_HEIGHT) {
          int diff = HUD_HEIGHT - by;
          by = HUD_HEIGHT;
          bh -= diff;
        }
        if (bx + bw > 320) bw = 320 - bx;
        if (by + bh > 240) bh = 240 - by;

        if (bw > 0 && bh > 0) {
          // Draw 2-pixel thick green bounding box
          tft.drawRect(bx, by, bw, bh, ILI9341_GREEN);
          if (bw > 2 && bh > 2) {
            tft.drawRect(bx + 1, by + 1, bw - 2, bh - 2, ILI9341_GREEN);
          }
        }

        // Draw facial landmarks if detected by MNP stage
        if (res.keypoint.size() >= 10) {
          for (size_t kp = 0; kp < 10; kp += 2) {
            int kpx = res.keypoint[kp] * 2;
            int kpy = res.keypoint[kp + 1] * 2;
            if (kpy >= HUD_HEIGHT && kpy < 240 && kpx >= 0 && kpx < 320) {
              tft.fillCircle(kpx, kpy, 2, ILI9341_CYAN);
            }
          }
        }
      }

      // 4. Draw HUD status banner into off-screen hudCanvas (100% flicker-free)
      hudCanvas.fillScreen(ILI9341_BLACK);
      hudCanvas.setTextSize(1);
      hudCanvas.setCursor(4, 6);

      if (isUploading) {
        hudCanvas.setTextColor(ILI9341_CYAN);
        hudCanvas.print(" [PROCESSING] IDENTIFYING WITH ARCFACE... ");
      } else if (guidance.status != GUIDANCE_OK && guidance.status != GUIDANCE_NONE) {
        hudCanvas.setTextColor(guidance.status == GUIDANCE_NO_FACE ? ILI9341_YELLOW : ILI9341_ORANGE);
        hudCanvas.printf(" %s", guidance.shortNotice);
      } else if (showCapturedNotice) {
        hudCanvas.setTextColor(ILI9341_CYAN);
        hudCanvas.printf(" [IMAGE CAPTURED] %lums", (unsigned long)lastInferTimeMs);
      } else if (hasActiveFace) {
        hudCanvas.setTextColor(ILI9341_GREEN);
        hudCanvas.printf(" FACE READY (%d) %lums", (int)stableFaces.size(), (unsigned long)lastInferTimeMs);
      } else {
        hudCanvas.setTextColor(ILI9341_YELLOW);
        hudCanvas.printf(" NO FACE %lums", (unsigned long)lastInferTimeMs);
      }

      // Top-right Wi-Fi connection indicator
      if (recognitionClient.isWiFiConnected()) {
        hudCanvas.setTextColor(ILI9341_GREEN);
        hudCanvas.setCursor(256, 6);
        hudCanvas.print("[WIFI OK]");
      } else {
        hudCanvas.setTextColor(ILI9341_RED);
        hudCanvas.setCursor(250, 6);
        hudCanvas.print("[WIFI OFF]");
      }

      // Blit the entire 320x20 HUD canvas to TFT in a single burst!
      tft.drawRGBBitmap(0, 0, hudCanvas.getBuffer(), 320, HUD_HEIGHT);
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
