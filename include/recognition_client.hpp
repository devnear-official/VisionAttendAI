#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "img_converters.h"
#include "dl_detect_base.hpp"
#include "network_config.h"
#include "wifi_manager.hpp"
#include "speaker_driver.hpp"

enum RecognitionState {
    REC_STATE_IDLE,          // Waiting for face
    REC_STATE_DETECTED,      // Face in frame, stabilizing
    REC_STATE_UPLOADING,     // Background HTTP upload in progress
    REC_STATE_MATCH,         // Student identity verified & attendance logged
    REC_STATE_UNKNOWN,       // Unknown person detected
    REC_STATE_AMBIGUOUS,     // Borderline confidence, please look again
    REC_STATE_ERROR,         // Network / HTTP / Server error
    REC_STATE_ENROLLING,     // Biometric enrollment in progress (sample N/M)
    REC_STATE_ENROLLED       // Biometric enrollment completed successfully
};

struct RecognitionResult {
    RecognitionState state = REC_STATE_IDLE;
    String statusStr = "";
    String studentId = "";
    String fullName = "";
    String department = "";
    float confidence = 0.0f;
    bool alreadyCheckedIn = false;
    bool attendanceRecorded = false;
    float inferenceTimeMs = 0.0f;
    String message = "";
    int sampleIndex = 0;
    int targetSamples = 0;
    bool hasSpeechAudio = false;
    unsigned long resultTimestamp = 0;
};

class RecognitionClient {
private:
    RecognitionResult m_lastResult;
    bool m_uploadInProgress = false;
    unsigned long m_lastUploadTime = 0;
    unsigned long m_displayExpiry = 0;
    char m_hudBuffer[64];

    // Synchronization primitives
    portMUX_TYPE m_mutex = portMUX_INITIALIZER_UNLOCKED;

public:
    RecognitionClient() {
        memset(m_hudBuffer, 0, sizeof(m_hudBuffer));
    }

    void initWiFi() {
        if (WiFi.status() == WL_CONNECTED) return;

        Serial.printf("[WiFi] Connecting to '%s'...\n", WIFI_SSID);
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

        unsigned long start = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - start < 10000UL) {
            delay(200);
            Serial.print(".");
        }

        if (WiFi.status() == WL_CONNECTED) {
            Serial.printf("\n[WiFi] Connected! IP: %s, RSSI: %d dBm\n",
                          WiFi.localIP().toString().c_str(), WiFi.RSSI());
        } else {
            Serial.println("\n[WiFi] Connection failed. Will retry in background.");
        }
    }

    bool isWiFiConnected() const {
        return WiFi.status() == WL_CONNECTED;
    }

    bool isUploadInProgress() const {
        return m_uploadInProgress;
    }

    bool canTriggerRecognition() {
        if (m_uploadInProgress) return false;
        if (!isWiFiConnected()) return false;
        if (millis() - m_lastUploadTime < RECOGNITION_COOLDOWN_MS) return false;
        return true;
    }

    void setUploadInProgress(bool inProgress) {
        portENTER_CRITICAL(&m_mutex);
        m_uploadInProgress = inProgress;
        if (inProgress) {
            m_lastUploadTime = millis();
        }
        portEXIT_CRITICAL(&m_mutex);
    }

    void updateResult(const RecognitionResult &res, unsigned long displayDurationMs = 3000) {
        portENTER_CRITICAL(&m_mutex);
        m_lastResult = res;
        m_displayExpiry = millis() + displayDurationMs;
        m_uploadInProgress = false;
        portEXIT_CRITICAL(&m_mutex);
    }

    RecognitionResult getActiveResult() {
        portENTER_CRITICAL(&m_mutex);
        RecognitionResult res = m_lastResult;
        bool expired = (millis() > m_displayExpiry);
        portEXIT_CRITICAL(&m_mutex);

        if (expired && res.state != REC_STATE_UPLOADING) {
            res.state = REC_STATE_IDLE;
        }
        return res;
    }

    // Transforms landmarks from full 160x120 coordinates to crop-relative coordinates
    static bool transformLandmarksToCrop(
        const std::vector<int> &keypoints,
        int crop_x, int crop_y, int crop_w, int crop_h,
        char *json_out, size_t json_max_len
    ) {
        if (keypoints.size() < 10) return false;

        // ESP-DL keypoint order: left_eye, right_eye, nose, left_mouth, right_mouth
        int pts[5][2];
        for (int i = 0; i < 5; ++i) {
            int rx = keypoints[2 * i] - crop_x;
            int ry = keypoints[2 * i + 1] - crop_y;

            // Clamp crop-relative coordinates safely inside crop bounds
            pts[i][0] = std::max(0, std::min(crop_w - 1, rx));
            pts[i][1] = std::max(0, std::min(crop_h - 1, ry));
        }

        snprintf(json_out, json_max_len,
            "[[%d,%d],[%d,%d],[%d,%d],[%d,%d],[%d,%d]]",
            pts[0][0], pts[0][1],
            pts[1][0], pts[1][1],
            pts[2][0], pts[2][1],
            pts[3][0], pts[3][1],
            pts[4][0], pts[4][1]
        );
        return true;
    }

    // Encodes sub-rectangle of 160x120 RGB565 frame to JPEG
    static bool extractAndEncodeFaceCrop(
        const uint8_t *frame_buf,
        int frame_w, int frame_h,
        const std::vector<int> &box,
        uint8_t **out_jpeg, size_t *out_jpeg_len,
        int *out_crop_x, int *out_crop_y, int *out_crop_w, int *out_crop_h
    ) {
        int bw = box[2] - box[0];
        int bh = box[3] - box[1];

        if (bw < MIN_FACE_CROP_DIM || bh < MIN_FACE_CROP_DIM) {
            Serial.printf("[CROP] Face too small (%dx%d < %d). Skipping upload.\n",
                          bw, bh, MIN_FACE_CROP_DIM);
            return false;
        }

        // 15% margin expansion for alignment context
        int margin_x = static_cast<int>(bw * 0.15f);
        int margin_y = static_cast<int>(bh * 0.15f);

        int cx1 = std::max(0, box[0] - margin_x);
        int cy1 = std::max(0, box[1] - margin_y);
        int cx2 = std::min(frame_w, box[2] + margin_x);
        int cy2 = std::min(frame_h, box[3] + margin_y);

        int cw = cx2 - cx1;
        int ch = cy2 - cy1;

        if (cw <= 0 || ch <= 0) return false;

        // Allocate crop buffer in PSRAM
        size_t crop_bytes = cw * ch * 2;
        uint8_t *crop_buf = static_cast<uint8_t *>(
            heap_caps_malloc(crop_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
        );
        if (!crop_buf) {
            crop_buf = static_cast<uint8_t *>(malloc(crop_bytes));
        }
        if (!crop_buf) {
            Serial.println("[CROP] Allocation failed for face crop buffer.");
            return false;
        }

        // Copy horizontal scanlines
        for (int r = 0; r < ch; ++r) {
            const uint8_t *src_row = frame_buf + ((cy1 + r) * frame_w + cx1) * 2;
            uint8_t *dst_row = crop_buf + (r * cw) * 2;
            memcpy(dst_row, src_row, cw * 2);
        }

        // Encode RGB565 crop to JPEG
        uint8_t *jpg_ptr = nullptr;
        size_t jpg_size = 0;
        bool ok = fmt2jpg(crop_buf, crop_bytes, cw, ch, PIXFORMAT_RGB565, JPEG_CROP_QUALITY, &jpg_ptr, &jpg_size);
        free(crop_buf);

        if (!ok || !jpg_ptr || jpg_size == 0) {
            Serial.println("[CROP] fmt2jpg encoding failed.");
            if (jpg_ptr) free(jpg_ptr);
            return false;
        }

        *out_jpeg = jpg_ptr;
        *out_jpeg_len = jpg_size;
        *out_crop_x = cx1;
        *out_crop_y = cy1;
        *out_crop_w = cw;
        *out_crop_h = ch;
        return true;
    }

    // Sends HTTP POST multipart/form-data request to FastAPI /api/v1/face/recognize
    static RecognitionResult sendRecognitionRequest(
        uint8_t *jpeg_data, size_t jpeg_len,
        const char *landmarks_json
    ) {
        RecognitionResult result;
        result.state = REC_STATE_ERROR;
        result.resultTimestamp = millis();

        if (WiFi.status() != WL_CONNECTED) {
            result.message = "Wi-Fi Disconnected";
            Serial.println("[HTTP] Cannot send: Wi-Fi is disconnected.");
            return result;
        }

        WiFiClient client;
        client.setTimeout(HTTP_REQUEST_TIMEOUT_MS / 1000);

        const char *targetHost = (wifiConfigManager.getBackendHost().length() > 0)
                               ? wifiConfigManager.getBackendHost().c_str()
                               : BACKEND_HOST;
        uint16_t targetPort = (wifiConfigManager.getBackendPort() > 0)
                            ? wifiConfigManager.getBackendPort()
                            : BACKEND_PORT;

        Serial.printf("[HTTP] Connecting to %s:%d...\n", targetHost, targetPort);
        if (!client.connect(targetHost, targetPort)) {
            result.message = "Connection Failed";
            Serial.println("[HTTP] Connection to backend failed.");
            return result;
        }

        const char *boundary = "---------------------------ESP32CamBoundary";

        // Construct multipart header parts
        String headPart = "";
        // 1. device_id field
        headPart += "--" + String(boundary) + "\r\n";
        headPart += "Content-Disposition: form-data; name=\"device_id\"\r\n\r\n";
        headPart += String(DEVICE_ID) + "\r\n";

        // 2. landmarks field
        if (landmarks_json && strlen(landmarks_json) > 0) {
            headPart += "--" + String(boundary) + "\r\n";
            headPart += "Content-Disposition: form-data; name=\"landmarks\"\r\n\r\n";
            headPart += String(landmarks_json) + "\r\n";
        }

        // 3. image file header
        headPart += "--" + String(boundary) + "\r\n";
        headPart += "Content-Disposition: form-data; name=\"image\"; filename=\"face_crop.jpg\"\r\n";
        headPart += "Content-Type: image/jpeg\r\n\r\n";

        String tailPart = "\r\n--" + String(boundary) + "--\r\n";

        size_t totalPayloadLength = headPart.length() + jpeg_len + tailPart.length();

        // Send HTTP Request Headers
        client.printf("POST %s HTTP/1.1\r\n", BACKEND_PATH);
        client.printf("Host: %s:%d\r\n", targetHost, targetPort);
        client.printf("X-Device-Api-Key: %s\r\n", DEVICE_API_KEY);
        client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", boundary);
        client.printf("Content-Length: %u\r\n", (unsigned)totalPayloadLength);
        client.print("Connection: close\r\n\r\n");

        // Send Multipart Payload
        client.print(headPart);
        client.write(jpeg_data, jpeg_len);
        client.print(tailPart);

        Serial.printf("[HTTP] Sent %u bytes (JPEG: %u bytes). Awaiting response...\n",
                      (unsigned)totalPayloadLength, (unsigned)jpeg_len);

        // Read HTTP Response Status
        unsigned long timeout = millis() + HTTP_REQUEST_TIMEOUT_MS;
        while (!client.available() && millis() < timeout) {
            delay(10);
        }

        if (!client.available()) {
            result.message = "HTTP Timeout";
            Serial.println("[HTTP] Request timed out.");
            client.stop();
            return result;
        }

        String statusLine = client.readStringUntil('\n');
        Serial.printf("[HTTP] Status: %s\n", statusLine.c_str());

        // Parse HTTP status code
        int statusCode = 0;
        if (statusLine.startsWith("HTTP/1.")) {
            statusCode = statusLine.substring(9, 12).toInt();
        }

        // Skip HTTP headers
        while (client.available()) {
            String line = client.readStringUntil('\n');
            if (line == "\r" || line.length() == 0) {
                break;
            }
        }

        // Read Response Body
        String responseBody = "";
        while (client.available()) {
            responseBody += client.readString();
        }
        client.stop();

        Serial.printf("[HTTP] Body (%d bytes): %s\n", responseBody.length(), responseBody.c_str());

        // Parse JSON with ArduinoJson
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, responseBody);
        if (err) {
            result.message = "Bad JSON";
            Serial.printf("[HTTP] JSON Deserialization failed: %s\n", err.c_str());
            return result;
        }

        if (statusCode == 200) {
            result.statusStr = doc["status"].as<const char*>() ? doc["status"].as<const char*>() : "UNKNOWN";
            result.confidence = doc["confidence"] | 0.0f;
            result.studentId = doc["student_id"].as<const char*>() ? doc["student_id"].as<const char*>() : "";
            result.fullName = doc["full_name"].as<const char*>() ? doc["full_name"].as<const char*>() : "";
            result.department = doc["department"].as<const char*>() ? doc["department"].as<const char*>() : "";
            result.alreadyCheckedIn = doc["already_checked_in"] | false;
            result.attendanceRecorded = doc["attendance_recorded"] | false;
            result.inferenceTimeMs = doc["inference_time_ms"] | 0.0f;
            result.message = doc["message"].as<const char*>() ? doc["message"].as<const char*>() : "";
            result.sampleIndex = doc["sample_index"] | 0;
            result.targetSamples = doc["target_samples"] | 0;
            result.hasSpeechAudio = doc["has_speech_audio"] | false;

            if (result.statusStr == "ENROLLED" || result.message.startsWith("ENROLLED")) {
                result.state = REC_STATE_ENROLLED;
            } else if (result.statusStr == "ENROLLING" || result.message.startsWith("ENROLLING")) {
                result.state = REC_STATE_ENROLLING;
                if (result.sampleIndex == 0 && result.message.startsWith("ENROLLING ")) {
                    // Parse "ENROLLING 1/3"
                    int slashIdx = result.message.indexOf('/');
                    if (slashIdx > 10) {
                        result.sampleIndex = result.message.substring(10, slashIdx).toInt();
                        result.targetSamples = result.message.substring(slashIdx + 1).toInt();
                    }
                }
            } else if (result.statusStr == "MATCH") {
                result.state = REC_STATE_MATCH;
            } else if (result.statusStr == "AMBIGUOUS") {
                result.state = REC_STATE_AMBIGUOUS;
            } else {
                result.state = REC_STATE_UNKNOWN;
            }
        } else {
            result.state = REC_STATE_ERROR;
            String fallbackMsg = "HTTP " + String(statusCode);
            const char *det = doc["detail"].as<const char*>();
            result.message = det ? det : fallbackMsg;
            Serial.printf("[HTTP] Error response (%d): %s\n", statusCode, result.message.c_str());
        }

        return result;
    }

    // Polls backend heartbeat, synchronizes speaker status, and streams pending TTS audio
    static void checkDeviceTelemetryAndAudio() {
        if (WiFi.status() != WL_CONNECTED) return;

        const char *targetHost = wifiConfigManager.getBackendHost().c_str();
        uint16_t targetPort = wifiConfigManager.getBackendPort();

        WiFiClient client;
        client.setTimeout(2500);
        if (!client.connect(targetHost, targetPort)) return;

        // 1. Send Heartbeat POST
        String path = "/api/v1/devices/heartbeat?device_code=" + String(DEVICE_ID);
        client.printf("POST %s HTTP/1.1\r\n", path.c_str());
        client.printf("Host: %s:%d\r\n", targetHost, targetPort);
        client.printf("X-Device-Api-Key: %s\r\n", DEVICE_API_KEY);
        client.print("Content-Length: 0\r\n");
        client.print("Connection: close\r\n\r\n");

        unsigned long timeout = millis() + 2500;
        while (!client.available() && millis() < timeout) delay(10);
        if (!client.available()) { client.stop(); return; }

        String statusLine = client.readStringUntil('\n');
        // Skip headers
        while (client.available()) {
            String l = client.readStringUntil('\n');
            if (l == "\r" || l.length() == 0) break;
        }

        String body = "";
        while (client.available()) body += client.readString();
        client.stop();

        JsonDocument doc;
        if (deserializeJson(doc, body) == DeserializationError::Ok) {
            bool speakerEnabled = doc["data"]["speaker_enabled"] | doc["speaker_enabled"] | true;
            speakerDriver.setEnabled(speakerEnabled);

            bool hasAudio = doc["data"]["has_pending_audio"] | doc["has_pending_audio"] | false;
            if (hasAudio && speakerEnabled) {
                // Fetch and stream the queued PCM audio from backend
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
            }
        }
    }
};

extern RecognitionClient recognitionClient;
