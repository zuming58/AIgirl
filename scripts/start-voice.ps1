param(
    [string]$LlmBaseUrl = "http://127.0.0.1:8080/v1",
    [string]$LlmModel = "local-companion",
    [string]$SttModel = "large-v3-turbo",
    [string]$Speaker = "Aiden",
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$voiceExecutable = Join-Path $repositoryRoot ".venv-voice\Scripts\speech-to-speech.exe"

if (-not (Test-Path -LiteralPath $voiceExecutable)) {
    throw "The isolated voice runtime is missing. Review docs\VOICE_RUNTIME.md and run scripts\setup-voice.ps1."
}

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}

Write-Host "Starting speech-to-speech at ws://127.0.0.1:$Port/v1/realtime"
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
    --qwen3_tts_model_name "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" `
    --qwen3_tts_speaker $Speaker `
    --qwen3_tts_language auto `
    --enable_live_transcription
