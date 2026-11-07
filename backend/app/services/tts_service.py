"""High-performance Text-to-Speech (TTS) service for VisionAttend-AI edge speaker."""

import io
import subprocess
import wave
import numpy as np
from app.utils.logger import logger


class TTSService:
    """Synthesizes text strings into 16kHz 16-bit mono PCM audio for ESP32 I2S MAX98357A."""

    _tts_cache: dict[str, bytes] = {}

    @classmethod
    def synthesize_cached_pcm(cls, text: str) -> bytes:
        clean = text.strip()
        if clean in cls._tts_cache:
            logger.info(f"Serving cached TTS audio for: '{clean}' ({len(cls._tts_cache[clean])} bytes)")
            return cls._tts_cache[clean]
        pcm = cls.synthesize_pcm(clean)
        if pcm:
            cls._tts_cache[clean] = pcm
        return pcm

    @staticmethod
    def synthesize_pcm(text: str) -> bytes:
        if not text or not text.strip():
            return b""

        clean_text = text.replace('"', ' ').replace("'", " ").replace('`', ' ').strip()
        logger.info(f"Synthesizing TTS audio for edge speaker: '{clean_text}'")

        ps_script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$ms = New-Object System.IO.MemoryStream
$s.SetOutputToWaveStream($ms)
$s.Speak('{clean_text}')
$b = $ms.ToArray()
$ms.Dispose()
$s.Dispose()
[System.Console]::OpenStandardOutput().Write($b, 0, $b.Length)
"""
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )

        if proc.returncode != 0 or not proc.stdout:
            err = proc.stderr.decode("utf-8", errors="ignore")
            logger.error(f"TTS synthesis subprocess failed: {err}")
            raise RuntimeError(f"TTS synthesis failed: {err}")

        wav_bytes = proc.stdout
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        # Convert to numpy int16 array
        samples = np.frombuffer(frames, dtype=np.int16)

        # Convert multi-channel to mono
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

        # Resample to 16000 Hz if necessary
        if framerate != 16000:
            target_length = int(len(samples) * 16000 / framerate)
            samples = np.interp(
                np.linspace(0, len(samples) - 1, target_length),
                np.arange(len(samples)),
                samples,
            ).astype(np.int16)

        # Slight normalization & silence trimming
        raw_pcm = samples.tobytes()
        logger.info(f"Synthesized {len(raw_pcm)} bytes of 16kHz 16-bit mono PCM successfully.")
        return raw_pcm
