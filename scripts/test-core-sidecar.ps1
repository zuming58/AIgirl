$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$sidecar = Join-Path $repositoryRoot "apps\desktop-ui\src-tauri\binaries\xinyu-core-x86_64-pc-windows-msvc.exe"
$tempRoot = Join-Path $repositoryRoot "temp"
$testData = Join-Path $tempRoot "sidecar-test-$([guid]::NewGuid().ToString('N'))"
$port = Get-Random -Minimum 18700 -Maximum 18800
$bootstrapProcess = $null
$listenerPid = $null

try {
    & (Join-Path $scriptDirectory "build-core-sidecar.ps1")
    if (-not (Test-Path -LiteralPath $sidecar -PathType Leaf)) {
        throw "Core sidecar was not created."
    }

    $env:XINYU_DATA_DIR = $testData
    $bootstrapProcess = Start-Process `
        -FilePath $sidecar `
        -ArgumentList "--host", "127.0.0.1", "--port", $port `
        -WindowStyle Hidden `
        -PassThru

    $deadline = (Get-Date).AddSeconds(30)
    $health = $null
    do {
        Start-Sleep -Milliseconds 300
        try {
            $health = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$port/health" `
                -TimeoutSec 2
        }
        catch {
            $health = $null
        }
    } until ($health -or (Get-Date) -gt $deadline)

    if (-not $health -or $health.status -ne "ok") {
        throw "Packaged Core sidecar did not become healthy."
    }

    $listener = Get-NetTCPConnection `
        -LocalPort $port `
        -State Listen `
        -ErrorAction Stop |
        Select-Object -First 1
    $listenerPid = $listener.OwningProcess
    Write-Host "Packaged Core sidecar health check passed on port $port."
}
finally {
    $processIds = @($listenerPid, $bootstrapProcess.Id) |
        Where-Object { $null -ne $_ } |
        Select-Object -Unique
    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -ne $process -and $process.Path -eq $sidecar) {
            Stop-Process -Id $processId -Force
        }
    }

    if (Test-Path -LiteralPath $testData) {
        Write-Host "Sidecar test data retained for manual cleanup: $testData"
    }
}
