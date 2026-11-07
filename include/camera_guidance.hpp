#pragma once

#include <Arduino.h>
#include <list>
#include "dl_detect_base.hpp"
#include "speaker_driver.hpp"

enum GuidanceStatus {
    GUIDANCE_NONE = 0,
    GUIDANCE_NO_FACE,
    GUIDANCE_TOO_FAR,
    GUIDANCE_TOO_NEAR,
    GUIDANCE_NOT_CENTERED,
    GUIDANCE_MULTIPLE_FACES,
    GUIDANCE_LOW_LIGHT,
    GUIDANCE_BLURRY,
    GUIDANCE_OK
};

struct GuidanceResult {
    GuidanceStatus status = GUIDANCE_NONE;
    const char *shortNotice = "";
    AudioEvent audioEvent = AUDIO_EVENT_NONE;
    float brightness = 0.0f;
    float blurVariance = 0.0f;
};

class CameraGuidance {
private:
    // Fast inline luminance extraction from RGB565 Big-Endian
    static inline uint8_t getLuma(const uint8_t *frameBuf, int x, int y, int stride = 160) {
        size_t idx = (y * stride + x) * 2;
        uint8_t b0 = frameBuf[idx];
        uint8_t b1 = frameBuf[idx + 1];
        uint16_t pix = (b0 << 8) | b1;
        uint8_t r = (pix >> 11) & 0x1F;
        uint8_t g = (pix >> 5) & 0x3F;
        uint8_t b = pix & 0x1F;
        // Fast integer approximation of Y = 0.299R + 0.587G + 0.114B
        return static_cast<uint8_t>((r * 77 + (g >> 1) * 150 + b * 29) >> 8);
    }

public:
    static GuidanceResult evaluate(
        const uint8_t *frameBuf,
        int frameW, int frameH,
        const std::list<dl::detect::result_t> &faces
    ) {
        GuidanceResult res;

        // 1. No Face Detected - completely silent! Only speak when someone is detected in frame.
        if (faces.empty()) {
            res.status = GUIDANCE_NO_FACE;
            res.shortNotice = "NO FACE";
            res.audioEvent = AUDIO_EVENT_NONE;
            return res;
        }

        // 2. Multiple Faces Detected
        if (faces.size() > 1) {
            res.status = GUIDANCE_MULTIPLE_FACES;
            res.shortNotice = "MULTIPLE: Stand alone";
            res.audioEvent = AUDIO_EVENT_MULTIPLE;
            return res;
        }

        // 3. Single Face Analysis
        const auto &face = faces.front();
        int bx1 = std::max(0, face.box[0]);
        int by1 = std::max(0, face.box[1]);
        int bx2 = std::min(frameW - 1, face.box[2]);
        int by2 = std::min(frameH - 1, face.box[3]);

        int bw = bx2 - bx1;
        int bh = by2 - by1;
        int cx = (bx1 + bx2) / 2;
        int cy = (by1 + by2) / 2;

        // 3a. Distance Check - Too Far
        if (bw < 30 || bh < 30) {
            res.status = GUIDANCE_TOO_FAR;
            res.shortNotice = "TOO FAR: Move closer";
            res.audioEvent = AUDIO_EVENT_TOO_FAR;
            return res;
        }

        // 3b. Distance Check - Too Near
        if (bw > 105 || bh > 95) {
            res.status = GUIDANCE_TOO_NEAR;
            res.shortNotice = "TOO NEAR: Move back";
            res.audioEvent = AUDIO_EVENT_TOO_NEAR;
            return res;
        }

        // 3c. Centering Check (Frame center is 80, 60)
        if (cx < 45 || cx > 115 || cy < 30 || cy > 90) {
            res.status = GUIDANCE_NOT_CENTERED;
            res.shortNotice = "CENTER: Look at camera";
            res.audioEvent = AUDIO_EVENT_NOT_CENTERED;
            return res;
        }

        // 3d. Light & Blur Analysis on Face Crop (Step by 2 pixels for max efficiency <0.3ms)
        if (frameBuf != nullptr && bw >= 30 && bh >= 30) {
            int step = 2;
            int margin = 3;
            int xStart = bx1 + margin;
            int xEnd   = bx2 - margin;
            int yStart = by1 + margin;
            int yEnd   = by2 - margin;

            float sumLuma = 0.0f;
            int lumaCount = 0;

            float sumLap = 0.0f;
            float sumLapSq = 0.0f;
            int lapCount = 0;

            for (int y = yStart; y <= yEnd; y += step) {
                for (int x = xStart; x <= xEnd; x += step) {
                    uint8_t c = getLuma(frameBuf, x, y, frameW);
                    sumLuma += c;
                    lumaCount++;

                    // Discrete Laplacian with step 2: L = Left + Right + Top + Bottom - 4*Center
                    if (x > bx1 + 2 && x < bx2 - 2 && y > by1 + 2 && y < by2 - 2) {
                        uint8_t l = getLuma(frameBuf, x - 2, y, frameW);
                        uint8_t r = getLuma(frameBuf, x + 2, y, frameW);
                        uint8_t t = getLuma(frameBuf, x, y - 2, frameW);
                        uint8_t b = getLuma(frameBuf, x, y + 2, frameW);

                        int lapVal = (int)l + (int)r + (int)t + (int)b - 4 * (int)c;
                        sumLap += lapVal;
                        sumLapSq += (lapVal * lapVal);
                        lapCount++;
                    }
                }
            }

            if (lumaCount > 0) {
                res.brightness = sumLuma / lumaCount;
            }

            if (lapCount > 0) {
                float meanLap = sumLap / lapCount;
                res.blurVariance = (sumLapSq / lapCount) - (meanLap * meanLap);
            }

            // Low Light Check (Conservative threshold: 42 / 255)
            if (res.brightness < 42.0f) {
                res.status = GUIDANCE_LOW_LIGHT;
                res.shortNotice = "LOW LIGHT: Need lighting";
                res.audioEvent = AUDIO_EVENT_LOW_LIGHT;
                return res;
            }

            // Blur Check (Conservative Laplacian variance threshold: 48.0)
            if (res.blurVariance < 48.0f) {
                res.status = GUIDANCE_BLURRY;
                res.shortNotice = "BLURRY: Keep face steady";
                res.audioEvent = AUDIO_EVENT_BLURRY;
                return res;
            }
        }

        // 3e. Position & Quality Acceptable!
        res.status = GUIDANCE_OK;
        res.shortNotice = "READY: Hold still";
        res.audioEvent = AUDIO_EVENT_NONE;
        return res;
    }
};
