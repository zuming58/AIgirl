$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$uiDirectory = Join-Path $repositoryRoot "apps\desktop-ui"
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$testRunId = [guid]::NewGuid().ToString("N")
$pytestTemp = Join-Path $repositoryRoot "temp\pytest-$testRunId"
$pytestCache = Join-Path $repositoryRoot "temp\pytest-cache-$testRunId"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The local Python environment is missing. Run scripts\setup.ps1 first."
}

Write-Host "Running core service tests..."
& $venvPython -m pytest `
    (Join-Path $repositoryRoot "services\core") `
    --basetemp=$pytestTemp `
    -o cache_dir=$pytestCache `
    --cov=xinyu_core `
    --cov-report=term

Write-Host "Building and checking the packaged Core sidecar..."
& (Join-Path $scriptDirectory "test-core-sidecar.ps1")

Write-Host "Building the desktop UI..."
npm.cmd --prefix $uiDirectory run build

Write-Host "Running desktop UI service tests..."
npm.cmd --prefix $uiDirectory run test:unit

Write-Host "Running Sites packaging tests..."
npm.cmd --prefix $uiDirectory run test:sites

Write-Host "Checking patch whitespace..."
git -C $repositoryRoot diff --check

Write-Host "Validating PowerShell scripts..."
$scriptFiles = Get-ChildItem -LiteralPath $scriptDirectory -Filter *.ps1
$allParseErrors = @()
foreach ($scriptFile in $scriptFiles) {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $scriptFile.FullName,
        [ref]$tokens,
        [ref]$parseErrors
    ) | Out-Null
    foreach ($parseError in $parseErrors) {
        $allParseErrors += "$($scriptFile.Name): $($parseError.Message)"
    }
}
if ($allParseErrors.Count -gt 0) {
    $allParseErrors
    throw "PowerShell syntax validation failed."
}

Write-Host "All automated checks passed."
