Add-Type -AssemblyName System.Speech

$voices = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voiceName = "Microsoft Zira Desktop"
try {
    $voices.SelectVoice($voiceName)
} catch {
    Write-Host "Voice $voiceName not found, using default voice."
}

$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

$prompts = @{
    "match"             = "Welcome. Attendance recorded successfully."
    "already_checked"   = "Attendance already recorded."
    "unknown"           = "Unknown person. Please register your face first."
    "enroll_start"      = "Enrollment started."
    "enroll_sample"     = "Sample captured."
    "enroll_complete"   = "Enrollment completed successfully."
    "enroll_failed"     = "Enrollment failed. Please try again."
    "rec_error"         = "Recognition failed. Please try again."
    "no_face"           = "Please stand in front of the camera."
    "too_far"           = "Please move closer."
    "too_near"          = "Please move back."
    "not_centered"      = "Please look at the camera."
    "multiple"          = "Please stand alone."
    "low_light"         = "Please improve the lighting."
    "blurry"            = "Please keep your face steady."
}

$tempDir = Join-Path $PSScriptRoot "temp_audio"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
}

$headerPath = Join-Path $PSScriptRoot "..\include\audio_assets.h"
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("#pragma once")
[void]$sb.AppendLine("// Auto-generated I2S 16kHz 16-bit Mono Audio Assets for VisionAttend-AI")
[void]$sb.AppendLine("#include <Arduino.h>")
[void]$sb.AppendLine("#include <pgmspace.h>")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("constexpr uint32_t AUDIO_SAMPLE_RATE = 16000;")
[void]$sb.AppendLine("constexpr uint8_t AUDIO_BITS_PER_SAMPLE = 16;")
[void]$sb.AppendLine("constexpr uint8_t AUDIO_CHANNELS = 1; // Mono (duplicated to stereo for MAX98357A)")
[void]$sb.AppendLine("")

$enumList = @()

foreach ($key in $prompts.Keys) {
    $text = $prompts[$key]
    $wavPath = Join-Path $tempDir "$key.wav"
    
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try { $synth.SelectVoice($voiceName) } catch {}
    $synth.SetOutputToWaveFile($wavPath, $format)
    $synth.Speak($text)
    $synth.Dispose()
    
    $bytes = [System.IO.File]::ReadAllBytes($wavPath)
    # Skip standard 44-byte WAV header to get pure PCM 16-bit samples
    $pcmBytes = $bytes[44..($bytes.Length - 1)]
    $varName = "AUDIO_DATA_" + $key.ToUpper()
    $sizeName = "AUDIO_SIZE_" + $key.ToUpper()
    
    [void]$sb.AppendLine("constexpr uint32_t $sizeName = $($pcmBytes.Length);")
    [void]$sb.AppendLine("const uint8_t $varName[] PROGMEM = {")
    
    # Format bytes in lines of 16
    for ($i = 0; $i -lt $pcmBytes.Length; $i += 16) {
        $end = [Math]::Min($i + 15, $pcmBytes.Length - 1)
        $chunk = $pcmBytes[$i..$end] | ForEach-Object { "0x{0:X2}" -f $_ }
        $line = "    " + ($chunk -join ", ") + ","
        [void]$sb.AppendLine($line)
    }
    [void]$sb.AppendLine("};")
    [void]$sb.AppendLine("")
    
    $enumList += $key
}

# Add helper lookup struct
[void]$sb.AppendLine("enum AudioEvent {")
[void]$sb.AppendLine("    AUDIO_EVENT_NONE = 0,")
foreach ($k in $prompts.Keys) {
    [void]$sb.AppendLine("    AUDIO_EVENT_" + $k.ToUpper() + ",")
}
[void]$sb.AppendLine("};")
[void]$sb.AppendLine("")

[void]$sb.AppendLine("struct AudioAsset {")
[void]$sb.AppendLine("    const uint8_t *data;")
[void]$sb.AppendLine("    uint32_t size;")
[void]$sb.AppendLine("    const char *textDescription;")
[void]$sb.AppendLine("};")
[void]$sb.AppendLine("")

[void]$sb.AppendLine("inline AudioAsset getAudioAsset(AudioEvent event) {")
[void]$sb.AppendLine("    switch (event) {")
foreach ($k in $prompts.Keys) {
    $upper = $k.ToUpper()
    $desc = $prompts[$k]
    [void]$sb.AppendLine("        case AUDIO_EVENT_${upper}: return { AUDIO_DATA_${upper}, AUDIO_SIZE_${upper}, ""$desc"" };")
}
[void]$sb.AppendLine("        default: return { nullptr, 0, """" };")
[void]$sb.AppendLine("    }")
[void]$sb.AppendLine("}")

[System.IO.File]::WriteAllText($headerPath, $sb.ToString(), [System.Text.Encoding]::UTF8)
Write-Host "Successfully generated audio assets in $headerPath"

# Clean up temp wav files
Remove-Item -Recurse -Force $tempDir
