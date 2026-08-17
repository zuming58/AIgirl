param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Driving,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [int]$SourceMaxDim = 1920,

    [double]$DrivingMultiplier = 1.0
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $repoRoot -Parent
$livePortraitRoot = Join-Path $repoRoot "third_party\LivePortrait"
$runtimeRoot = Join-Path $workspaceRoot "runtime-envs\liveportrait"
$python = Join-Path $runtimeRoot "Scripts\python.exe"
$torchLib = Join-Path $runtimeRoot "Lib\site-packages\torch\lib"
$ffmpegLink = "C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links"

foreach ($requiredPath in @($Source, $Driving, $python, $livePortraitRoot, $torchLib)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path does not exist: $requiredPath"
    }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$env:PATH = "$torchLib;$ffmpegLink;$env:PATH"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Push-Location $livePortraitRoot
try {
    & $python inference.py `
        --source $Source `
        --driving $Driving `
        --output-dir $OutputDir `
        --flag-normalize-lip `
        --source-max-dim $SourceMaxDim `
        --driving-multiplier $DrivingMultiplier

    if ($LASTEXITCODE -ne 0) {
        throw "LivePortrait inference failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
