#pragma once

#include <Arduino.h>
#include "speaker_driver.hpp"
#include "camera_guidance.hpp"
#include "recognition_client.hpp"

class FeedbackManager {
private:
    unsigned long m_lastGuidanceAudioTime = 0;
    unsigned long m_lastIdleAudioTime = 0;
    AudioEvent m_lastGuidanceEvent = AUDIO_EVENT_NONE;
    unsigned long m_lastProcessedResultTime = 0;
    RecognitionState m_lastProcessedState = REC_STATE_IDLE;

    // Cooldown timings (in milliseconds)
    static constexpr unsigned long GUIDANCE_COOLDOWN_MS = 6000;
    static constexpr unsigned long IDLE_COOLDOWN_MS     = 14000;

public:
    FeedbackManager() {}

    // Called on new recognition result arrival from backend
    void handleRecognitionResult(const RecognitionResult &res) {
        if (res.state == REC_STATE_IDLE || res.state == REC_STATE_UPLOADING) return;
        if (res.resultTimestamp == m_lastProcessedResultTime && res.state == m_lastProcessedState) {
            return; // Already announced for this exact result
        }

        m_lastProcessedResultTime = res.resultTimestamp;
        m_lastProcessedState = res.state;

        switch (res.state) {
            case REC_STATE_MATCH:
                if (res.alreadyCheckedIn) {
                    speakerDriver.queueAudio(AUDIO_EVENT_ALREADY_CHECKED, true);
                } else {
                    speakerDriver.queueAudio(AUDIO_EVENT_MATCH, true);
                }
                break;

            case REC_STATE_UNKNOWN:
                speakerDriver.queueAudio(AUDIO_EVENT_UNKNOWN, true);
                break;

            case REC_STATE_AMBIGUOUS:
                speakerDriver.queueAudio(AUDIO_EVENT_REC_ERROR, true);
                break;

            case REC_STATE_ERROR:
                speakerDriver.queueAudio(AUDIO_EVENT_REC_ERROR, true);
                break;

            case REC_STATE_ENROLLING:
                if (res.sampleIndex == 1) {
                    speakerDriver.queueAudio(AUDIO_EVENT_ENROLL_START, true);
                } else {
                    speakerDriver.queueAudio(AUDIO_EVENT_ENROLL_SAMPLE, true);
                }
                break;

            case REC_STATE_ENROLLED:
                speakerDriver.queueAudio(AUDIO_EVENT_ENROLL_COMPLETE, true);
                break;

            default:
                break;
        }
    }

    // Called periodically during live camera preview
    void handleCameraGuidance(const GuidanceResult &guidance, bool isUploading, bool isShowingResult) {
        // If an upload or full-screen card is currently active, suppress camera guidance audio
        if (isUploading || isShowingResult) return;
        if (guidance.audioEvent == AUDIO_EVENT_NONE) return;
        if (speakerDriver.isPlaying()) return; // Don't interrupt if audio is currently playing

        unsigned long now = millis();

        // 1. Idle No-Face guidance - completely silent when room is empty
        if (guidance.status == GUIDANCE_NO_FACE) {
            return;
        }

        // 2. Active Face Quality Guidance (Too Far, Too Near, Center, Multiple, Low Light, Blurry)
        if (now - m_lastGuidanceAudioTime >= GUIDANCE_COOLDOWN_MS || m_lastGuidanceEvent != guidance.audioEvent) {
            if (now - m_lastGuidanceAudioTime >= 4000) { // minimum 4s even if condition changed
                m_lastGuidanceAudioTime = now;
                m_lastGuidanceEvent = guidance.audioEvent;
                speakerDriver.queueAudio(guidance.audioEvent, false);
            }
        }
    }
};

extern FeedbackManager feedbackManager;
