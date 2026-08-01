$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$uiDirectory = Join-Path $repositoryRoot "apps\desktop-ui"
$coreDirectory = Join-Path $repositoryRoot "services\core"
$venvDirectory = Join-Path $repositoryRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$uv = Get-Command uv -ErrorAction SilentlyContinue

Write-Host "Updating Git submodules..."
git -C $repositoryRoot submodule update --init --recursive
if ($LASTEXITCODE -ne 0) {
    throw "Git submodule update failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($null -eq $uv) {
        throw "Python 3.11 environment is missing. Install uv from https://docs.astral.sh/uv/ and run this script again."
    }

    Write-Host "Creating the Python 3.11 virtual environment..."
    & $uv.Source venv $venvDirectory --python 3.11
    if ($LASTEXITCODE -ne 0) {
        throw "Python environment creation failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Installing the local core service and test dependencies..."
$corePackage = "$coreDirectory[dev]"
if ($null -ne $uv) {
    & $uv.Source pip install --python $venvPython --editable $corePackage
}
else {
    & $venvPython -m pip install --disable-pip-version-check --editable $corePackage
}
if ($LASTEXITCODE -ne 0) {
    throw "Core dependency installation failed with exit code $LASTEXITCODE."
}

Write-Host "Installing desktop UI dependencies..."
npm.cmd --prefix $uiDirectory ci
if ($LASTEXITCODE -ne 0) {
    throw "Desktop UI dependency installation failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start the local application with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$scriptDirectory\dev.ps1`" -Open"
Write-Host "Run the complete local verification with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$scriptDirectory\test.ps1`""
