param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$coreSource = Join-Path $repositoryRoot "services\core\src"
$entryPoint = Join-Path $coreSource "xinyu_core\cli.py"
$migrationDirectory = Join-Path $coreSource "xinyu_core\migrations"
$buildRoot = Join-Path $repositoryRoot "temp\sidecar-build"
$workPath = Join-Path $buildRoot "work"
$distPath = Join-Path $buildRoot "dist"
$specPath = Join-Path $buildRoot "spec"
$binaryDirectory = Join-Path $repositoryRoot "apps\desktop-ui\src-tauri\binaries"
$builtExecutable = Join-Path $distPath "xinyu-core.exe"
$targetExecutable = Join-Path $binaryDirectory "xinyu-core-$TargetTriple.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python environment not found. Run scripts/setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) {
    throw "Core entry point not found: $entryPoint"
}

New-Item -ItemType Directory -Force -Path $workPath, $distPath, $specPath, $binaryDirectory | Out-Null

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name "xinyu-core" `
    --paths $coreSource `
    --hidden-import "xinyu_core.app" `
    --collect-submodules "xinyu_core" `
    --collect-all "sqlite_vec" `
    --collect-all "uvicorn" `
    --add-data "$migrationDirectory;xinyu_core/migrations" `
    --workpath $workPath `
    --distpath $distPath `
    --specpath $specPath `
    $entryPoint

if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $builtExecutable -PathType Leaf)) {
    throw "Core sidecar build failed."
}

Copy-Item -LiteralPath $builtExecutable -Destination $targetExecutable -Force
Write-Host "Core sidecar ready: $targetExecutable"
