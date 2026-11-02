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

// GOOUUU ESP32-S3-CAM V1.3: GPIO9-13 are used by the camera.
constexpr int TFT_CS = 47;
constexpr int TFT_RST = 1;
constexpr int TFT_DC = 14;
constexpr int TFT_MOSI = 41;
constexpr int TFT_SCK = 42;
constexpr int TFT_MISO = 2; // Connected but not needed for preview.
Adafruit_ILI9341 tft(&SPI, TFT_DC, TFT_CS, TFT_RST);
bool cameraReady = false;
// These diagnostics do not change the camera, SPI or display settings.
const char *frameLocation = "not observed yet";
const char *psramTest = "not run";
unsigned long lastDiagnostics = 0;

void testPsram() {
  // Arduino/ESP-IDF initializes PSRAM during boot when the build enables it.
  // Do not force a late initialization with an unknown bus mode.
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
  Serial.println("\n--- VisionAttend Stage 1 diagnostics ---");
  Serial.printf("Arduino ESP32: %s; ESP-IDF: %s\n", ESP_ARDUINO_VERSION_STR, esp_get_idf_version());
#ifdef BOARD_HAS_PSRAM
  Serial.println("BOARD_HAS_PSRAM: defined");
#else
  Serial.println("BOARD_HAS_PSRAM: not defined");
#endif
#if defined(CONFIG_SPIRAM) && CONFIG_SPIRAM
  Serial.println("SDK CONFIG_SPIRAM: enabled");
#elif defined(CONFIG_SPIRAM_SUPPORT) && CONFIG_SPIRAM_SUPPORT
  Serial.println("SDK CONFIG_SPIRAM_SUPPORT: enabled");
#else
  Serial.println("SDK PSRAM configuration: disabled or not exposed");
#endif
#if defined(CONFIG_SPIRAM_MODE_OCT) && CONFIG_SPIRAM_MODE_OCT
  Serial.println("SDK PSRAM mode setting: octal (not proof PSRAM is enabled)");
#elif defined(CONFIG_SPIRAM_MODE_QUAD) && CONFIG_SPIRAM_MODE_QUAD
  Serial.println("SDK PSRAM mode setting: quad (not proof PSRAM is enabled)");
#else
  Serial.println("SDK PSRAM mode: not exposed/unknown");
#endif
  Serial.printf("Arduino psramFound: %s; test: %s\n", psramFound() ? "yes" : "no", psramTest);
  Serial.printf("ESP.getPsramSize: %u; ESP.getFreePsram: %u bytes\n",
    (unsigned)ESP.getPsramSize(), (unsigned)ESP.getFreePsram());
  Serial.printf("PSRAM heap total: %u; free: %u; largest block: %u bytes\n",
    (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),
    (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
    (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
  Serial.printf("Internal 8-bit heap free: %u bytes\n",
    (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  Serial.printf("Camera framebuffer requested DRAM; actual buffer: %s\n", frameLocation);
  Serial.printf("Flash size reported by build/flash API: %u bytes; running image: %u bytes\n",
    (unsigned)ESP.getFlashChipSize(), (unsigned)ESP.getSketchSize());
  const esp_partition_t *running = esp_ota_get_running_partition();
  if (running) {
    size_t image = ESP.getSketchSize();
    Serial.printf("Running app %s: offset 0x%08x, size %u, approximate unused %u bytes\n",
      running->label, (unsigned)running->address, (unsigned)running->size,
      (unsigned)(image <= running->size ? running->size - image : 0));
  } else Serial.println("Running app partition: unknown");
  Serial.println("Partition table (label, type, subtype, offset, size):");
  esp_partition_iterator_t it = esp_partition_find(ESP_PARTITION_TYPE_ANY, ESP_PARTITION_SUBTYPE_ANY, nullptr);
  while (it) {
    const esp_partition_t *part = esp_partition_get(it);
    Serial.printf("  %s, 0x%02x, 0x%02x, 0x%08x, %u\n", part->label,
      (unsigned)part->type, (unsigned)part->subtype, (unsigned)part->address, (unsigned)part->size);
    it = esp_partition_next(it);
  }
  Serial.println("Model/dependency fit: not verified; exact binary and peak RAM required.");
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
  tft.setRotation(1); // 320 x 240 landscape
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextColor(ILI9341_CYAN);
  tft.setTextSize(2);
  tft.setCursor(8, 20);
  tft.print("Starting camera...");

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_pwdn = -1;
  config.pin_reset = -1;
  config.pin_xclk = 15;
  config.pin_sscb_sda = 4;
  config.pin_sscb_scl = 5;
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
  config.fb_location = CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", static_cast<unsigned>(err));
    showError("Camera init failed");
    return;
  }
  cameraReady = true;
  testPsram();
  printDiagnostics();
  lastDiagnostics = millis();
  tft.fillScreen(ILI9341_BLACK);
}

void loop() {
  if (!cameraReady) { delay(1000); return; }
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) {
    Serial.println("Camera capture failed");
    delay(100);
    return;
  }
  if (frameLocation[0] == 'n') {
    frameLocation = esp_ptr_external_ram(frame->buf) ? "external PSRAM" :
                    esp_ptr_internal(frame->buf) ? "internal RAM" : "unknown address region";
    Serial.printf("Camera framebuffer actual location: %s (%u bytes)\n", frameLocation, (unsigned)frame->len);
  }
  if (frame->format == PIXFORMAT_RGB565 && frame->width == 160 &&
      frame->height == 120 && frame->len >= 160U * 120U * 2U) {
    // Camera RGB565 arrives MSB first. Double every pixel and row.
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
  } else {
    Serial.printf("Unexpected camera frame: %u x %u, %u bytes\n",
                  frame->width, frame->height, static_cast<unsigned>(frame->len));
  }
  esp_camera_fb_return(frame);
  if (millis() - lastDiagnostics >= 15000UL) {
    lastDiagnostics = millis();
    printDiagnostics();
  }
}