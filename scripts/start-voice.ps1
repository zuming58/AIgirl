param(
    [string]$LlmBaseUrl = "http://127.0.0.1:8080/v1",
    [string]$LlmModel = "local-companion",
    [string]$SttModel = "large-v3-turbo",
    [string]$TtsModel = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    [string]$Speaker = "Aiden",
    [ValidateSet("quality_local", "quality_cloud_llm")]
    [string]$Profile = "quality_local",
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$voiceExecutable = Join-Path $repositoryRoot ".venv-voice\Scripts\speech-to-speech.exe"

if ([string]::IsNullOrWhiteSpace($LlmModel)) {
    throw "LlmModel is required. Configure the selected OpenAI-compatible model ID."
}

try {
    $llmUri = [System.Uri]$LlmBaseUrl
} catch {
    throw "LlmBaseUrl must be an absolute http:// or https:// URL."
}

if ($llmUri.Scheme -notin @("http", "https")) {
    throw "LlmBaseUrl must use http:// or https://."
}

if ([string]::IsNullOrWhiteSpace($SttModel) -or [string]::IsNullOrWhiteSpace($TtsModel)) {
    throw "SttModel and TtsModel are required."
}

if ($Profile -eq "quality_local" -and $TtsModel -match "(?i)1\.7b") {
    throw "The 1.7B TTS tier exceeds the quality_local 16GB budget. Use the 0.6B model or explicitly select quality_cloud_llm after benchmarking."
}

if (-not (Test-Path -LiteralPath $voiceExecutable)) {
    throw "The isolated voice runtime is missing. Review docs\VOICE_RUNTIME.md and run scripts\setup-voice.ps1."
}

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}

Write-Host "Starting speech-to-speech ($Profile) at ws://127.0.0.1:$Port/v1/realtime"
Write-Host "The first approved run may download the selected STT and TTS model weights."

& $voiceExecutable `
    --mode realtime `
    --ws_host 127.0.0.1 `
    --ws_port $Port `
    --stt faster-whisper `
    --stt_model_name $SttModel `
    --language zh `
    --llm_backend chat-completions `
    --model_name $LlmModel `
    --responses_api_base_url $LlmBaseUrl `
    --responses_api_api_key "" `
    --responses_api_stream `
    --tts qwen3 `
    --qwen3_tts_model_name $TtsModel `
    --qwen3_tts_speaker $Speaker `
    --qwen3_tts_language auto `
    --enable_live_transcription
