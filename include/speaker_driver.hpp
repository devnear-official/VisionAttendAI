#pragma once

#include <Arduino.h>
#include <ESP_I2S.h>
#include "audio_assets.h"

// MAX98357A I2S Pin Mapping (Confirmed by user)
constexpr int I2S_BCLK_PIN = 38;
constexpr int I2S_LRC_PIN  = 39;
constexpr int I2S_DIN_PIN  = 40;

class SpeakerDriver {
private:
    I2SClass m_i2s;
    QueueHandle_t m_audioQueue = nullptr;
    TaskHandle_t m_audioTaskHandle = nullptr;
    volatile bool m_isPlaying = false;
    volatile bool m_abortCurrent = false;
    bool m_enabled = true;
    uint8_t m_volume = 95; // 0 - 100%
    bool m_initialized = false;

    static void audioTask(void *param) {
        SpeakerDriver *self = static_cast<SpeakerDriver*>(param);
        self->runAudioLoop();
    }

    void runAudioLoop() {
        AudioEvent event;
        // Stereo buffer for MAX98357A (256 samples * 2 channels * 2 bytes = 1024 bytes)
        constexpr size_t CHUNK_SAMPLES = 256;
        int16_t stereoBuffer[CHUNK_SAMPLES * 2];

        while (true) {
            if (xQueueReceive(m_audioQueue, &event, portMAX_DELAY) == pdTRUE) {
                if (!m_enabled || event == AUDIO_EVENT_NONE) continue;

                AudioAsset asset = getAudioAsset(event);
                if (!asset.data || asset.size == 0) continue;

                m_isPlaying = true;
                m_abortCurrent = false;

                Serial.printf("[AUDIO] Playing: %s (%u bytes)\n", asset.textDescription, (unsigned)asset.size);

                const int16_t *pcm16 = reinterpret_cast<const int16_t*>(asset.data);
                size_t totalSamples = asset.size / sizeof(int16_t);
                size_t sampleOffset = 0;

                while (sampleOffset < totalSamples && !m_abortCurrent) {
                    size_t samplesToRead = std::min(CHUNK_SAMPLES, totalSamples - sampleOffset);
                    int32_t volFactor = m_volume;

                    for (size_t i = 0; i < samplesToRead; ++i) {
                        // Read from Flash (pgmspace)
                        int16_t mono = (int16_t)pgm_read_word(&pcm16[sampleOffset + i]);
                        // Apply volume scaling
                        int32_t scaled = (mono * volFactor) / 100;
                        int16_t outSample = (int16_t)std::max(-32768, std::min(32767, (int)scaled));

                        // Output to both Left and Right channels for MAX98357A
                        stereoBuffer[2 * i]     = outSample;
                        stereoBuffer[2 * i + 1] = outSample;
                    }

                    size_t bytesToWrite = samplesToRead * 2 * sizeof(int16_t);
                    m_i2s.write(reinterpret_cast<const uint8_t*>(stereoBuffer), bytesToWrite);
                    sampleOffset += samplesToRead;
                }

                // Small trailing delay for DMA buffer flush
                if (!m_abortCurrent) {
                    delay(40);
                }
                m_isPlaying = false;
                m_abortCurrent = false;
            }
        }
    }

public:
    SpeakerDriver() {}

    bool init() {
        if (m_initialized) return true;

        Serial.printf("[AUDIO] Initializing MAX98357A I2S on BCLK=%d, LRC=%d, DIN=%d...\n",
                      I2S_BCLK_PIN, I2S_LRC_PIN, I2S_DIN_PIN);

        m_i2s.setPins(I2S_BCLK_PIN, I2S_LRC_PIN, I2S_DIN_PIN);

        // Standard Philips I2S, 16kHz, 16-bit, Stereo
        if (!m_i2s.begin(I2S_MODE_STD, AUDIO_SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
            Serial.println("[AUDIO] ERROR: Failed to initialize I2S bus!");
            return false;
        }

        m_audioQueue = xQueueCreate(4, sizeof(AudioEvent));
        if (!m_audioQueue) {
            Serial.println("[AUDIO] ERROR: Failed to create audio queue!");
            return false;
        }

        // Pinned to Core 0 (Network & background core), leaving Core 1 100% free for camera & inference
        BaseType_t ret = xTaskCreatePinnedToCore(
            audioTask,
            "audio_worker",
            4096,
            this,
            1, // Low priority
            &m_audioTaskHandle,
            0  // Core 0
        );

        if (ret != pdPASS) {
            Serial.println("[AUDIO] ERROR: Failed to start audio worker task!");
            return false;
        }

        m_initialized = true;
        Serial.println("[AUDIO] MAX98357A I2S Speaker driver initialized successfully.");
        return true;
    }

    bool isPlaying() const { return m_isPlaying; }
    void setVolume(uint8_t vol) { m_volume = std::min((uint8_t)100, vol); }
    uint8_t getVolume() const { return m_volume; }
    void setEnabled(bool en) { m_enabled = en; }
    bool isEnabled() const { return m_enabled; }

    void abortPlayback() {
        if (m_isPlaying) {
            m_abortCurrent = true;
        }
    }

    // Direct streaming playback for dynamic text-to-speech audio received from backend
    void playRawStream(WiFiClient &client, size_t totalBytes) {
        if (!m_enabled || !m_initialized || totalBytes == 0) return;
        m_isPlaying = true;
        m_abortCurrent = false;

        constexpr size_t CHUNK_SAMPLES = 256;
        int16_t monoChunk[CHUNK_SAMPLES];
        int16_t stereoBuffer[CHUNK_SAMPLES * 2];

        size_t bytesRead = 0;
        int32_t volFactor = m_volume;

        Serial.printf("[AUDIO] Streaming dynamic audio from backend (%u bytes)...\n", (unsigned)totalBytes);

        while (bytesRead < totalBytes && client.connected() && !m_abortCurrent) {
            size_t toRead = std::min(sizeof(monoChunk), totalBytes - bytesRead);
            size_t r = client.readBytes(reinterpret_cast<uint8_t*>(monoChunk), toRead);
            if (r == 0) break;

            size_t sampleCount = r / sizeof(int16_t);
            for (size_t i = 0; i < sampleCount; ++i) {
                int32_t scaled = (monoChunk[i] * volFactor) / 100;
                int16_t outSample = (int16_t)std::max(-32768, std::min(32767, (int)scaled));
                stereoBuffer[2 * i]     = outSample;
                stereoBuffer[2 * i + 1] = outSample;
            }

            size_t bytesToWrite = sampleCount * 2 * sizeof(int16_t);
            m_i2s.write(reinterpret_cast<const uint8_t*>(stereoBuffer), bytesToWrite);
            bytesRead += r;
        }

        delay(40);
        m_isPlaying = false;
        m_abortCurrent = false;
        Serial.println("[AUDIO] Dynamic audio streaming finished.");
    }

    bool queueAudio(AudioEvent event, bool clearPrevious = false) {
        if (!m_initialized || !m_enabled || event == AUDIO_EVENT_NONE) return false;

        if (clearPrevious) {
            m_abortCurrent = true;
            xQueueReset(m_audioQueue);
        }

        return (xQueueSend(m_audioQueue, &event, 0) == pdTRUE);
    }
};

extern SpeakerDriver speakerDriver;
