param(
    [Parameter(Mandatory = $true)]
    [string]$SourceMaster,

    [Parameter(Mandatory = $true)]
    [string]$BlinkVideo,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [int]$Width = 2352,
    [int]$Height = 3520,
    [double]$Duration = 4.933,
    [int]$Fps = 30
)

$ErrorActionPreference = "Stop"

foreach ($path in @($SourceMaster, $BlinkVideo)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required avatar input does not exist: $path"
    }
}

$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    throw "ffmpeg is required but was not found on PATH."
}

$outputDirectory = Split-Path -Parent $Output
if ($outputDirectory) {
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}

# These coordinates are locked to the R13 identity master. The LivePortrait
# result is visible only in a softly feathered eye band during the two blink
# windows. Every other pixel comes from the approved high-resolution master.
$eyeX = 576
$eyeY = 1000
$eyeWidth = 1200
$eyeHeight = 600
$filter = @"
[0:v]format=yuv420p[base];
[1:v]scale=${Width}:${Height}:flags=lanczos,crop=${eyeWidth}:${eyeHeight}:${eyeX}:${eyeY},format=rgba[eyeband];
color=c=black:s=${eyeWidth}x${eyeHeight}:r=${Fps}:d=${Duration},format=gray,drawbox=x=120:y=130:w=960:h=300:color=white:t=fill,gblur=sigma=70[mask];
[eyeband][mask]alphamerge[eyes];
[base][eyes]overlay=${eyeX}:${eyeY}:enable='between(t,1.35,1.95)+between(t,3.28,3.98)'[blink];
[blink]scale=2364:3538:flags=lanczos,crop=${Width}:${Height}:x=6:y='9+2*sin(2*PI*t/${Duration})'[outv]
"@ -replace "`r?`n", ""

& $ffmpeg `
    -y `
    -loop 1 `
    -framerate $Fps `
    -t $Duration `
    -i $SourceMaster `
    -i $BlinkVideo `
    -filter_complex $filter `
    -map "[outv]" `
    -t $Duration `
    -r $Fps `
    -c:v libx264 `
    -preset slow `
    -crf 10 `
    -pix_fmt yuv420p `
    -movflags +faststart `
    $Output

if ($LASTEXITCODE -ne 0) {
    throw "Hybrid idle render failed with exit code $LASTEXITCODE."
}

Write-Host "Created hybrid idle proof: $Output"
