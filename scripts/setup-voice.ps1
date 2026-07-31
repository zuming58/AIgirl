param(
    [switch]$ConfirmLargeInstall
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmLargeInstall) {
    throw "Voice dependencies include PyTorch and model runtimes. Review docs\VOICE_RUNTIME.md, then rerun with -ConfirmLargeInstall."
}

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$voiceSource = Join-Path $repositoryRoot "third_party\speech-to-speech"
$voiceEnvironment = Join-Path $repositoryRoot ".venv-voice"
$voicePython = Join-Path $voiceEnvironment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath (Join-Path $voiceSource "pyproject.toml"))) {
    throw "The speech-to-speech submodule is missing. Run scripts\setup.ps1 first."
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    throw "uv is required to create the isolated voice environment."
}

if (-not (Test-Path -LiteralPath $voicePython)) {
    & $uv.Source venv $voiceEnvironment --python 3.11
}

$voicePackage = "$voiceSource[faster-whisper]"
& $voicePython -m pip install --disable-pip-version-check --editable $voicePackage

Write-Host "Voice runtime dependencies are installed in .venv-voice."
Write-Host "No STT or TTS model weights were downloaded by this script."
Write-Host "Start the configured runtime with scripts\start-voice.ps1."
