param(
    [switch]$Open,
    [ValidateRange(1, 65535)]
    [int]$CorePort = 8765
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$uiDirectory = Join-Path $repositoryRoot "apps\desktop-ui"
$coreDirectory = Join-Path $repositoryRoot "services\core"
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$runtimeDirectory = Join-Path $repositoryRoot "temp\runtime"
$logDirectory = Join-Path $runtimeDirectory "logs"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The local Python environment is missing. Run scripts\setup.ps1 first."
}

if (Get-NetTCPConnection -LocalPort $CorePort -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $CorePort is already in use. Stop the existing service or choose another port with -CorePort."
}

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $venvPython
$startInfo.WorkingDirectory = $coreDirectory
$startInfo.Arguments = "-m uvicorn xinyu_core.app:create_app --factory --host 127.0.0.1 --port $CorePort"
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.EnvironmentVariables["XINYU_DATA_DIR"] = $runtimeDirectory

$coreProcess = [System.Diagnostics.Process]::Start($startInfo)
$stdoutTask = $coreProcess.StandardOutput.ReadToEndAsync()
$stderrTask = $coreProcess.StandardError.ReadToEndAsync()
$coreUrl = "http://127.0.0.1:$CorePort"
$previousCoreUrl = $env:VITE_XINYU_CORE_URL

try {
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 150
        $listener = Get-NetTCPConnection -LocalPort $CorePort -State Listen -ErrorAction SilentlyContinue
    } while ($null -eq $listener -and [DateTime]::UtcNow -lt $deadline)

    if ($null -eq $listener) {
        throw "The core service did not start within 15 seconds."
    }

    Write-Host "Core API: $coreUrl"
    Write-Host "Desktop UI: http://127.0.0.1:4173"
    Write-Host "Press Ctrl+C to stop the development stack."
    $env:VITE_XINYU_CORE_URL = $coreUrl
    $viteArguments = @(
        "--prefix",
        $uiDirectory,
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1"
    )
    if ($Open) {
        $viteArguments += "--open"
    }
    & npm.cmd $viteArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Desktop UI development server exited with code $LASTEXITCODE."
    }
}
finally {
    $env:VITE_XINYU_CORE_URL = $previousCoreUrl

    if ($null -ne $coreProcess -and -not $coreProcess.HasExited) {
        $coreProcess.Kill()
        $coreProcess.WaitForExit()
    }

    $stdoutTask.GetAwaiter().GetResult() | Set-Content -LiteralPath (Join-Path $logDirectory "core.stdout.log") -Encoding utf8
    $stderrTask.GetAwaiter().GetResult() | Set-Content -LiteralPath (Join-Path $logDirectory "core.stderr.log") -Encoding utf8
}
