#pragma once

// ============================================================================
// VisionAttend-AI Stage 5.5: Network & Edge Client Configuration
// ============================================================================

// Wi-Fi Access Point Credentials
// NOTE: Set these to your local 2.4 GHz Wi-Fi network credentials.
#ifndef WIFI_SSID
#define WIFI_SSID "Asad"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "rifat7232"
#endif

// Local FastAPI Backend Configuration
// When running locally, use your computer's LAN IPv4 address (e.g., 192.168.1.101).
// Run backend with: uvicorn app.main:app --host 0.0.0.0 --port 8000
#ifndef BACKEND_HOST
#define BACKEND_HOST "192.168.1.101"
#endif

#ifndef BACKEND_PORT
#define BACKEND_PORT 8000
#endif

#ifndef BACKEND_PATH
#define BACKEND_PATH "/api/v1/face/recognize"
#endif

// Device Authentication & Identification
// Place the cryptographically generated device key below:
#ifndef ESP32_S3_DEVICE_KEY
#define ESP32_S3_DEVICE_KEY "va_edge_SlyuBwB8H3LDFDsw4wHeb_mx5lqjzhJNyl-Or7FotJc"
#endif

#ifndef DEVICE_API_KEY
#define DEVICE_API_KEY ESP32_S3_DEVICE_KEY
#endif

#ifndef DEVICE_ID
#define DEVICE_ID "esp32-cam-01"
#endif

// Edge Pipeline Parameters
#define HTTP_REQUEST_TIMEOUT_MS  8000   // 8 second timeout for inference POST
#define RECOGNITION_COOLDOWN_MS  4000   // 4 second cooldown between uploads for same person
#define MIN_FACE_CROP_DIM        44     // Minimum width & height (pixels) to trigger upload
#define JPEG_CROP_QUALITY        80     // Standard JPEG compression quality for face crops
