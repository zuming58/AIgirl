$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$uiDirectory = Join-Path $repositoryRoot "apps\desktop-ui"

Write-Host "Updating Git submodules..."
git -C $repositoryRoot submodule update --init --recursive

Write-Host "Installing desktop UI dependencies..."
npm --prefix $uiDirectory ci

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start the demo with:"
Write-Host "  cd `"$uiDirectory`""
Write-Host "  npm run dev"
