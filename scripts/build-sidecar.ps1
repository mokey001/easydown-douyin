$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    uv sync --project sidecar --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    uv run --project sidecar pyinstaller --noconfirm --clean --onefile --console --name shiying-engine --paths sidecar --paths sidecar/vendor --collect-submodules core --collect-submodules storage --collect-submodules auth --collect-submodules control --collect-submodules utils --collect-submodules config --exclude-module tkinter --exclude-module imageio_ffmpeg --exclude-module playwright --exclude-module whisper --distpath .build/engine --workpath .build/pyinstaller --specpath .build sidecar/main.py
    if ($LASTEXITCODE -ne 0) { throw 'Sidecar build failed' }
    New-Item -ItemType Directory -Force -Path src-tauri/binaries | Out-Null
    Copy-Item -LiteralPath .build/engine/shiying-engine.exe -Destination src-tauri/binaries/shiying-engine-x86_64-pc-windows-msvc.exe
} finally { Pop-Location }
