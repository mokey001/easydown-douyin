# Architecture and protocol

The local UI talks only to the Rust host. Rust owns a persistent Python process and relays newline-delimited JSON. Python exclusively owns the task database. One queue worker limits API fanout; each job has a media concurrency limit.

Commands: `snapshot`, `enqueue`, `settings`, `pause`, `cancel`, `resume`, `retry`, `diagnostics`. Every command has a UUID `request_id`; replies have `type=response`, `ok`, and `data` or a safe `error`. Events are `ready`, `task`, `settings`, `bridge_request`, and `bridge_cancel`.

## Page request bridge

Only HTTPS `www.douyin.com` can submit `bridge_response`, and only from the `douyin` WebView. A request is tied to a one-time UUID nonce kept by Rust. Expired, oversized, wrong-window, or unmatched replies are rejected. All other app commands also enforce the `main` window label in Rust.

Python requests only GET endpoints under `/aweme/v1/web/`. Rust validates this scope before evaluation. A serializable request is inserted into a fixed script using JSON encoding. The script calls the page's current `fetch` with browser credentials. The page SDK is responsible for platform signatures. Python's generated msToken/a_bogus values are deliberately not reused in page requests.

Remote page capabilities contain only `bridge_response`; they do not expose shell, filesystem, local app state, or event subscription permissions. All host events are emitted directly to `main`, never broadcast to the remote page.

## Recovery

At startup any queued/downloading/resolving task becomes paused, preventing surprise downloads after a crash. State-changing commands commit immediately. High-frequency progress is memory-only; task settlement persists counts. Shutdown asks the engine to cancel and save, then kills it after a bounded grace interval.

Retries preserve the original task settings and output location. Completed files are deduplicated by the upstream archive/filesystem checks. Partial files are cleaned by the core, so resume can re-download the unfinished file.

## Distribution

Windows uses a PyInstaller onefile console sidecar, spawned without a visible console by Tauri's process plugin. Python and dependencies are embedded. Tauri's NSIS installer packages the two executables. Build inputs are locked by Cargo.lock, package-lock.json, uv.lock, and the vendored upstream commit. Windows code signing and an updater endpoint are not configured in the first build.
