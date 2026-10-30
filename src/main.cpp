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
  tft.begin();
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
  config.frame_size = FRAMESIZE_QQVGA; // 160 x 120; doubled for display.
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

  if (frame->format == PIXFORMAT_RGB565 && frame->width == 160 &&
      frame->height == 120 && frame->len >= 160U * 120U * 2U) {

    // 1. Render camera frame to TFT (160x120 doubled to 320x240 landscape)
    static uint16_t row[320];
    uint8_t *out = reinterpret_cast<uint8_t *>(row);
    tft.startWrite();
    tft.setAddrWindow(0, 0, 320, 240);
    for (size_t y = 0; y < 120; ++y) {
      const uint8_t *src = frame->buf + y * 160 * 2;
      for (size_t x = 0; x < 160; ++x) {
        out[4*x] = out[4*x+2] = src[2*x];
        out[4*x+1] = out[4*x+3] = src[2*x+1];
      }
      tft.writePixels(row, 320, true, true);
      tft.writePixels(row, 320, true, true);
    }
    tft.endWrite();

    // 2. Execute Face Detection
    std::list<dl::detect::result_t> results;
    if (faceDetectorReady) {
      dl::image::img_t img;
      img.data = frame->buf;
      img.width = 160;
      img.height = 120;
      img.pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB565BE;

      unsigned long t0 = millis();
      results = faceDetector.detect(img);
      lastInferTimeMs = millis() - t0;
      detectedFaceCount = results.size();
    }

    // 3. Draw Bounding Boxes and Status Overlay on TFT
    if (!results.empty()) {
      for (const auto &res : results) {
        // Map 160x120 model coords to 320x240 display coords (x2 scaling)
        int bx = res.box[0] * 2;
        int by = res.box[1] * 2;
        int bw = (res.box[2] - res.box[0]) * 2;
        int bh = (res.box[3] - res.box[1]) * 2;

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
            int kpx = res.keypoint[kp] * 2;
            int kpy = res.keypoint[kp + 1] * 2;
            tft.fillCircle(kpx, kpy, 2, ILI9341_CYAN);
          }
        }
      }

      // Status header overlay
      tft.fillRect(0, 0, 180, 16, ILI9341_BLACK);
      tft.setCursor(4, 4);
      tft.setTextColor(ILI9341_GREEN);
      tft.setTextSize(1);
      tft.printf("FACE DETECTED (%d) %ums", (int)results.size(), (unsigned)lastInferTimeMs);
    } else {
      tft.fillRect(0, 0, 140, 16, ILI9341_BLACK);
      tft.setCursor(4, 4);
      tft.setTextColor(ILI9341_YELLOW);
      tft.setTextSize(1);
      tft.printf("NO FACE %ums", (unsigned)lastInferTimeMs);
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
