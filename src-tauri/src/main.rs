#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
};
use tauri::{Emitter, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

struct Host {
    child: Mutex<Option<CommandChild>>,
    bridges: Mutex<HashMap<String, String>>,
    ready: AtomicBool,
}

fn data_dir(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    if let Some(path) = std::env::var_os("SHIYING_TEST_DATA_DIR") {
        let path = std::path::PathBuf::from(path);
        if !path.is_absolute() {
            return Err("Test data directory must be absolute".into());
        }
        return Ok(path);
    }
    app.path().app_data_dir().map_err(|e| e.to_string())
}

fn only_main(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "main" {
        return Err("该窗口无权执行此操作".into());
    }
    Ok(())
}

fn send(app: &tauri::AppHandle, value: &Value) -> Result<(), String> {
    let host = app.state::<Host>();
    let mut guard = host.child.lock().map_err(|_| "下载引擎锁定异常")?;
    let child = guard.as_mut().ok_or("下载引擎尚未启动，请稍候")?;
    let line = format!("{}\n", value);
    child
        .write(line.as_bytes())
        .map_err(|_| "下载引擎连接已断开，请重新启动应用".into())
}

#[tauri::command]
fn engine_command(
    window: WebviewWindow,
    app: tauri::AppHandle,
    message: Value,
) -> Result<(), String> {
    only_main(&window)?;
    let action = message.get("action").and_then(Value::as_str).unwrap_or("");
    if ![
        "snapshot",
        "enqueue",
        "settings",
        "pause",
        "cancel",
        "resume",
        "retry",
        "diagnostics",
    ]
    .contains(&action)
    {
        return Err("操作不允许".into());
    }
    if !app.state::<Host>().ready.load(Ordering::Relaxed) {
        return Err("下载引擎正在启动".into());
    }
    send(&app, &message)
}

#[tauri::command]
async fn open_login(window: WebviewWindow, app: tauri::AppHandle) -> Result<(), String> {
    // WebView2 creation must run outside the synchronous IPC/UI callback on Windows.
    // A synchronous command deadlocks initialization and leaves a blank native window.
    only_main(&window)?;
    if let Some(login) = app.get_webview_window("douyin") {
        login.show().map_err(|e| e.to_string())?;
        return login.set_focus().map_err(|e| e.to_string());
    }
    let profile = data_dir(&app)?.join("douyin-profile");
    let handle = app.clone();
    let login = WebviewWindowBuilder::new(
        &app,
        "douyin",
        WebviewUrl::External("https://www.douyin.com/".parse().unwrap()),
    )
    .title("拾影 · 登录抖音（完成后可关闭此窗口）")
    .inner_size(1100.0, 800.0)
    .data_directory(profile)
    .on_navigation(|url| {
        url.scheme() == "https"
            && url
                .host_str()
                .is_some_and(|host| host == "douyin.com" || host.ends_with(".douyin.com"))
    })
    .on_page_load(move |_, payload| {
        if payload.event() == tauri::webview::PageLoadEvent::Finished {
            let _ = handle.emit_to("main", "page-status", json!({"status":"connected"}));
        }
    })
    .build()
    .map_err(|e| format!("无法打开抖音窗口：{e}"))?;
    let hidden = login.clone();
    login.on_window_event(move |event| {
        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            let _ = hidden.hide();
        }
    });
    Ok(())
}

fn reject_bridge(app: &tauri::AppHandle, id: &str, code: &str, error: &str) {
    let _ = send(
        app,
        &json!({"action":"bridge_response","request_id":id,"payload":{"error":error,"code":code}}),
    );
}

fn dispatch_bridge(app: &tauri::AppHandle, mut message: Value) {
    let id = message["request_id"].as_str().unwrap_or("").to_owned();
    let path = message["path"].as_str().unwrap_or("");
    if !path.starts_with("/aweme/v1/web/")
        || path.contains("..")
        || path.contains('\\')
        || message["method"] != "GET"
    {
        reject_bridge(app, &id, "INVALID_ENDPOINT", "页面请求地址不允许");
        return;
    }
    let Some(page) = app.get_webview_window("douyin") else {
        reject_bridge(
            app,
            &id,
            "NOT_LOGGED_IN",
            "请先点击「连接抖音」打开页面，完成登录或验证后重试",
        );
        return;
    };
    let nonce = uuid::Uuid::new_v4().to_string();
    app.state::<Host>()
        .bridges
        .lock()
        .unwrap()
        .insert(id.clone(), nonce.clone());
    message["nonce"] = json!(nonce);
    let script = include_str!("page_bridge.js").replace("__BRIDGE_REQUEST__", &message.to_string());
    if page.eval(&script).is_err() {
        app.state::<Host>().bridges.lock().unwrap().remove(&id);
        reject_bridge(app, &id, "PAGE_ERROR", "抖音页面尚未就绪，请稍候重试");
    }
}

#[tauri::command]
fn bridge_response(
    window: WebviewWindow,
    app: tauri::AppHandle,
    id: String,
    nonce: String,
    payload: Value,
) -> Result<(), String> {
    if window.label() != "douyin"
        || window
            .url()
            .ok()
            .and_then(|u| u.host_str().map(str::to_owned))
            .as_deref()
            != Some("www.douyin.com")
    {
        return Err("Forbidden".into());
    }
    if payload.to_string().len() > 8 * 1024 * 1024 {
        return Err("Response too large".into());
    }
    let host = app.state::<Host>();
    let mut pending = host.bridges.lock().map_err(|_| "Bridge unavailable")?;
    if pending.get(&id) != Some(&nonce) {
        return Err("Expired response".into());
    }
    pending.remove(&id);
    drop(pending);
    send(
        &app,
        &json!({"action":"bridge_response","request_id":id,"payload":payload}),
    )
}

#[tauri::command]
async fn choose_folder(
    window: WebviewWindow,
    app: tauri::AppHandle,
) -> Result<Option<String>, String> {
    only_main(&window)?;
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .set_title("选择下载保存位置")
            .blocking_pick_folder()
            .map(|p| {
                p.into_path()
                    .map(|p| p.to_string_lossy().to_string())
                    .map_err(|e| e.to_string())
            })
            .transpose()
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn open_folder(window: WebviewWindow, path: String) -> Result<(), String> {
    only_main(&window)?;
    let folder = std::path::Path::new(&path);
    if !folder.is_absolute() || !folder.is_dir() {
        return Err("文件夹尚未创建，请先开始下载".into());
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer.exe")
            .arg(folder)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(folder)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(folder)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn clear_login(window: WebviewWindow, app: tauri::AppHandle) -> Result<(), String> {
    only_main(&window)?;
    if let Some(page) = app.get_webview_window("douyin") {
        page.clear_all_browsing_data().map_err(|e| e.to_string())?;
        page.navigate("https://www.douyin.com/".parse().unwrap())
            .map_err(|e| e.to_string())?;
    } else {
        return Err("请先打开抖音窗口，再清除登录数据".into());
    }
    let _ = app.emit_to("main", "page-status", json!({"status":"disconnected"}));
    Ok(())
}

#[tauri::command]
async fn export_diagnostics(
    window: WebviewWindow,
    app: tauri::AppHandle,
    data: Value,
) -> Result<Option<String>, String> {
    only_main(&window)?;
    // Caller supplies the engine's pre-redacted report; no browser profile or raw logs are exported.
    if data.to_string().len() > 1024 * 1024 {
        return Err("诊断信息过大".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let path = app
            .dialog()
            .file()
            .set_file_name("shiying-diagnostics.json")
            .blocking_save_file();
        if let Some(path) = path {
            let path = path.into_path().map_err(|e| e.to_string())?;
            std::fs::write(&path, serde_json::to_vec_pretty(&data).unwrap())
                .map_err(|e| e.to_string())?;
            Ok(Some(path.to_string_lossy().to_string()))
        } else {
            Ok(None)
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(Host { child: Mutex::new(None), bridges: Mutex::new(HashMap::new()), ready: AtomicBool::new(false) })
        .invoke_handler(tauri::generate_handler![engine_command, open_login, choose_folder, open_folder, clear_login, export_diagnostics, bridge_response])
        .setup(|app| {
            let data = data_dir(app.handle()).map_err(std::io::Error::other)?;
            std::fs::create_dir_all(&data)?;
            let output = if std::env::var_os("SHIYING_TEST_DATA_DIR").is_some() { data.join("downloads") } else { app.path().download_dir()?.join("拾影") };
            let (mut rx, child) = app.shell().sidecar("shiying-engine")?
                .args(["--data-dir", &data.to_string_lossy(), "--output-dir", &output.to_string_lossy()])
                .spawn()?;
            *app.state::<Host>().child.lock().unwrap() = Some(child);
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(bytes) => {
                            if let Ok(message) = serde_json::from_slice::<Value>(&bytes) {
                                match message["type"].as_str() {
                                    Some("ready") => {
                                        handle.state::<Host>().ready.store(true, Ordering::Relaxed);
                                        let _ = handle.emit_to("main", "engine-event", &message);
                                    }
                                    Some("bridge_request") => {
                                        let on_main = handle.clone();
                                        let _ = handle.run_on_main_thread(move || dispatch_bridge(&on_main, message));
                                    }
                                    Some("bridge_cancel") => {
                                        if let Some(id) = message["request_id"].as_str() { handle.state::<Host>().bridges.lock().unwrap().remove(id); }
                                    }
                                    _ => { let _ = handle.emit_to("main", "engine-event", &message); }
                                }
                            }
                        }
                        CommandEvent::Terminated(_) | CommandEvent::Error(_) => {
                            handle.state::<Host>().ready.store(false, Ordering::Relaxed);
                            let _ = handle.emit_to("main", "engine-event", json!({"type":"engine_error","error":"下载引擎已停止，请重新启动拾影"}));
                        }
                        _ => {} // Never persist unredacted upstream stderr.
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" && matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event { api.prevent_close(); }
                let _ = window.hide();
                let app = window.app_handle();
                let _ = send(app, &json!({"action":"shutdown"}));
                if let Some(page) = app.get_webview_window("douyin") { let _ = page.destroy(); }
                // Give the queue time to persist its paused state before killing a stuck sidecar.
                let handle = app.clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(1500));
                    if let Some(child) = handle.state::<Host>().child.lock().unwrap().take() { let _ = child.kill(); }
                    handle.exit(0);
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("无法启动拾影");
}
