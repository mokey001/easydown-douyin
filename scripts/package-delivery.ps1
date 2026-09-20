$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '../../outputs'))
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '../..'))
if (-not $outputRoot.StartsWith($workspaceRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Output path outside workspace' }
$releaseDir = Join-Path $projectRoot 'src-tauri/target/release'
$version = (Get-Content -LiteralPath (Join-Path $projectRoot 'package.json') -Raw | ConvertFrom-Json).version
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid release version' }
$installer = Join-Path $releaseDir "bundle/nsis/Shiying_${version}_x64-setup.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw 'Build the installer first' }
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$portable = Join-Path $outputRoot "Shiying-${version}-Windows-x64"
New-Item -ItemType Directory -Force -Path $portable | Out-Null
Copy-Item -LiteralPath (Join-Path $releaseDir 'shiying.exe'), (Join-Path $releaseDir 'shiying-engine.exe') -Destination $portable
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md'), (Join-Path $projectRoot 'LICENSE'), (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.txt') -Destination $portable
Copy-Item -LiteralPath $installer -Destination $outputRoot
Compress-Archive -LiteralPath $portable -DestinationPath (Join-Path $outputRoot "Shiying-${version}-Windows-x64-portable.zip") -Force
$sourceStage = Join-Path $projectRoot ('.build/source-' + [Guid]::NewGuid().ToString('N'))
$sourceDir = Join-Path $sourceStage 'shiying-desktop'
New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null
Push-Location $projectRoot
try {
    $sourceFiles = & rg --files --hidden -g '!.git/**' -g '!node_modules/**' -g '!.build/**' -g '!dist/**' -g '!src-tauri/target/**' -g '!src-tauri/binaries/**' -g '!src-tauri/gen/**' -g '!sidecar/.venv/**' -g '!**/__pycache__/**' -g '!**/.pytest_cache/**' -g '!*.tsbuildinfo' -g '!**/AGENTS.md'
    if ($LASTEXITCODE -ne 0) { throw 'Source file enumeration failed' }
    foreach ($sourceFile in $sourceFiles) {
        $destination = Join-Path $sourceDir $sourceFile
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $projectRoot $sourceFile) -Destination $destination
    }
    Compress-Archive -LiteralPath $sourceDir -DestinationPath (Join-Path $outputRoot "Shiying-${version}-source.zip") -Force
} finally { Pop-Location }
Get-ChildItem -LiteralPath $outputRoot -File | Select-Object Name,Length
