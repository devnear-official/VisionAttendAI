import os
import subprocess
import wave
import struct

PROMPTS = {
    "match": "Welcome! Attendance recorded successfully.",
    "already_checked": "Attendance already recorded.",
    "unknown": "Unknown person. Please register your face first.",
    "enroll_start": "Enrollment started.",
    "enroll_sample": "Sample captured.",
    "enroll_complete": "Enrollment completed successfully.",
    "enroll_failed": "Enrollment failed. Please try again.",
    "rec_error": "Recognition failed. Please try again.",
    "no_face": "Please stand in front of the camera.",
    "too_far": "Please move closer.",
    "too_near": "Please move back.",
    "not_centered": "Please look at the camera.",
    "multiple": "Please stand alone.",
    "low_light": "Please improve the lighting.",
    "blurry": "Please keep your face steady.",
}

os.makedirs("scripts/temp_wav", exist_ok=True)

# 1. Synthesize using Windows SAPI at 16000Hz 16-bit Mono
ps_script = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoice('Microsoft Zira Desktop') } catch {}
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
"""

for key, text in PROMPTS.items():
    wav_path = f"scripts/temp_wav/{key}.wav".replace("/", "\\")
    ps_script += f"""
$s.SetOutputToWaveFile('{wav_path}', $fmt)
$s.Speak('{text}')
"""

ps_script += "$s.Dispose()\n"

with open("scripts/synth.ps1", "w", encoding="utf-8") as f:
    f.write(ps_script)

print("Synthesizing audio files via PowerShell...")
subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts/synth.ps1"], check=True)
os.remove("scripts/synth.ps1")

# 2. Trim silence & normalize
trimmed_audio = {}
total_pcm_bytes = 0

for key in PROMPTS.keys():
    wav_path = f"scripts/temp_wav/{key}.wav"
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    samples = struct.unpack(f"<{n_frames}h", raw_bytes)
    
    # Find start and end of speech (threshold: 300)
    thresh = 350
    start = 0
    while start < len(samples) and abs(samples[start]) < thresh:
        start += 1
    # keep a small 50ms padding (800 samples)
    start = max(0, start - 800)
    
    end = len(samples) - 1
    while end > start and abs(samples[end]) < thresh:
        end -= 1
    end = min(len(samples), end + 800)
    
    trimmed = list(samples[start:end])
    
    # Peak normalization to ~85% full scale (27500)
    peak = max([abs(s) for s in trimmed] or [1])
    gain = min(2.5, 27500.0 / peak)
    norm = [int(s * gain) for s in trimmed]
    norm = [max(-32768, min(32767, s)) for s in norm]
    
    pcm_bytes = struct.pack(f"<{len(norm)}h", *norm)
    trimmed_audio[key] = pcm_bytes
    total_pcm_bytes += len(pcm_bytes)
    print(f"[{key}] Original frames: {n_frames} -> Trimmed: {len(norm)} ({len(pcm_bytes)/1024:.1f} KB)")

print(f"\nTotal Trimmed Audio Size: {total_pcm_bytes/1024:.1f} KB")

# 3. Generate include/audio_assets.h
header_lines = []
header_lines.append("#pragma once")
header_lines.append("// Auto-generated I2S 16kHz 16-bit Mono Audio Assets for VisionAttend-AI")
header_lines.append("#include <Arduino.h>")
header_lines.append("#include <pgmspace.h>")
header_lines.append("")
header_lines.append("constexpr uint32_t AUDIO_SAMPLE_RATE = 16000;")
header_lines.append("constexpr uint8_t AUDIO_BITS_PER_SAMPLE = 16;")
header_lines.append("constexpr uint8_t AUDIO_CHANNELS = 1; // Mono (duplicated to stereo for MAX98357A)")
header_lines.append("")

for key, pcm in trimmed_audio.items():
    var_name = f"AUDIO_DATA_{key.upper()}"
    size_name = f"AUDIO_SIZE_{key.upper()}"
    header_lines.append(f"constexpr uint32_t {size_name} = {len(pcm)};")
    header_lines.append(f"const uint8_t {var_name}[] PROGMEM = {{")
    
    for i in range(0, len(pcm), 16):
        chunk = pcm[i:i+16]
        hex_str = ", ".join([f"0x{b:02X}" for b in chunk])
        header_lines.append(f"    {hex_str},")
    header_lines.append("};")
    header_lines.append("")

header_lines.append("enum AudioEvent {")
header_lines.append("    AUDIO_EVENT_NONE = 0,")
for key in PROMPTS.keys():
    header_lines.append(f"    AUDIO_EVENT_{key.upper()},")
header_lines.append("};")
header_lines.append("")

header_lines.append("struct AudioAsset {")
header_lines.append("    const uint8_t *data;")
header_lines.append("    uint32_t size;")
header_lines.append("    const char *textDescription;")
header_lines.append("};")
header_lines.append("")

header_lines.append("inline AudioAsset getAudioAsset(AudioEvent event) {")
header_lines.append("    switch (event) {")
for key, desc in PROMPTS.items():
    upper = key.upper()
    header_lines.append(f'        case AUDIO_EVENT_{upper}: return {{ AUDIO_DATA_{upper}, AUDIO_SIZE_{upper}, "{desc}" }};')
header_lines.append('        default: return { nullptr, 0, "" };')
header_lines.append("    }")
header_lines.append("}")

with open("include/audio_assets.h", "w", encoding="utf-8") as f:
    f.write("\n".join(header_lines) + "\n")

# Cleanup temp files
for key in PROMPTS.keys():
    try:
        os.remove(f"scripts/temp_wav/{key}.wav")
    except:
        pass
try:
    os.rmdir("scripts/temp_wav")
except:
    pass

print(f"Successfully generated include/audio_assets.h ({os.path.getsize('include/audio_assets.h')/1024/1024:.2f} MB)")
