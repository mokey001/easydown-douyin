$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    & "$PSScriptRoot/build-sidecar.ps1"
    cargo fetch --manifest-path src-tauri/Cargo.toml --locked
    if ($LASTEXITCODE -ne 0) { throw 'Rust dependency fetch failed' }
    node scripts/collect-notices.mjs
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
    npm run desktop:build
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
} finally { Pop-Location }
