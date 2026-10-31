#pragma once

// ============================================================================
// VisionAttend-AI Stage 5.5: Network & Edge Client Configuration
// ============================================================================

// Wi-Fi Access Point Credentials
// NOTE: Set these to your local 2.4 GHz Wi-Fi network credentials.
#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
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
// Must match DEVICE_API_KEY in backend/.env
#ifndef DEVICE_API_KEY
#define DEVICE_API_KEY "esp32_device_secret_key_change_in_production"
#endif

#ifndef DEVICE_ID
#define DEVICE_ID "ESP32-S3-CAM"
#endif

// Edge Pipeline Parameters
#define HTTP_REQUEST_TIMEOUT_MS  8000   // 8 second timeout for inference POST
#define RECOGNITION_COOLDOWN_MS  4000   // 4 second cooldown between uploads for same person
#define MIN_FACE_CROP_DIM        44     // Minimum width & height (pixels) to trigger upload
#define JPEG_CROP_QUALITY        80     // Standard JPEG compression quality for face crops
