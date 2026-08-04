param(
    [int]$Count = 100000,
    [int]$Queries = 100,
    [int]$Seed = 20260804,
    [string]$DatabasePath = ""
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The local Python environment is missing. Run scripts\setup.ps1 first."
}
if ($Count -lt 1 -or $Queries -lt 1) {
    throw "Count and Queries must be positive."
}
if ([string]::IsNullOrWhiteSpace($DatabasePath)) {
    $runId = [guid]::NewGuid().ToString("N")
    $DatabasePath = Join-Path $repositoryRoot "temp\memory-benchmark-$runId.db"
}
$resolvedDatabase = [System.IO.Path]::GetFullPath($DatabasePath)
if (Test-Path -LiteralPath $resolvedDatabase) {
    throw "Benchmark database already exists; choose a new path."
}
$parent = Split-Path -Parent $resolvedDatabase
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent | Out-Null
}

& $python -m xinyu_core.memory_benchmark `
    --database $resolvedDatabase `
    --count $Count `
    --queries $Queries `
    --seed $Seed
if ($LASTEXITCODE -ne 0) {
    throw "Memory benchmark failed with exit code $LASTEXITCODE."
}
Write-Host "Synthetic benchmark database retained for manual cleanup: $resolvedDatabase"
