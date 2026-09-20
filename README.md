# 拾影 Shiying Desktop 0.1.1

Windows 抖音下载工具，Tauri 2 + React + Python sidecar。源码和构建脚本随本地交付提供，不依赖第三方解析服务。

## 0.1.1 修复

- 修复 Windows 上点击「连接抖音」后，登录窗口空白、主窗口失去响应的问题：窗口改为异步创建，避免 WebView2 初始化死锁。
- 打开窗口期间显示「正在打开…」，并拦截重复点击。
- 安装包与便携版保留原来的应用标识和数据位置，不清除账号数据与下载记录。下载引擎本次未改动，版本仍为 0.1.0。

## 使用

1. 运行 Windows 安装包，或解压便携版后运行 `shiying.exe`。便携版内的 `shiying-engine.exe` 必须与主程序放在一起。
2. 点击「连接抖音」，在独立的抖音窗口完成登录或验证。关闭这个窗口会隐藏它，以便继续提供页面请求。
3. 粘贴作品、图集、主页、合集链接，或者整段分享文案。可一次添加最多 50 个链接。
4. 点击「添加下载」。主页/合集默认最多获取 50 个作品，可在偏好设置中调整数量、日期、画质和保存位置。

没有登录时也可以尝试公开内容，但平台可能要求验证。遇到「需要验证」时，打开抖音窗口处理，再点击该任务的重试按钮。

## 已实现

- 视频、图集、主页已发布作品、合集的下载核心适配。
- 短链接解析、多链接去重、持久化任务队列、历史记录和搜索。
- 真实文件字节进度、当前文件速度/预计剩余时间、作品计数。
- 暂停、继续、取消、重试；退出后未完成任务保留为暂停状态。
- 最高画质/1080P/720P/节省空间，数量和发布日期筛选。
- 输出目录、文件名模板、封面和作品 JSON、媒体下载代理。
- 独立 WebView 登录、页面内请求桥、清除登录、脱敏诊断导出。

## 当前边界

- 这是 Windows 测试版本。使用自有抖音账号的在线验收仍需在使用者的网络环境下完成；本地测试不代表平台所有账号和作品都可下载。
- 暂停会取消在途传输；继续时跳过已完成作品，未完成文件会重新下载，当前不宣称字节级断点续传。
- 同时处理一个链接任务，任务中的媒体文件支持 1–4 路并发。
- 登录窗口显示「页面已连接」仅表示页面加载完成，不表示账号已经登录。
- 主程序关闭会结束下载，不提供托盘后台驻留。
- 0.1 不包含直播、喜欢/收藏、音频提取、FFmpeg 转码和自动更新。没有捆绑 FFmpeg 或 yt-dlp。
- 抖音签名和风控随平台变化，页面桥仍可能需要后续适配；HTTP 403/429 会提示验证，不会无限重试。
- 当前提供 Windows x64 构建；macOS/Linux 构建与页面桥差异尚未验收。

## 数据位置

- 默认文件目录：系统「下载」目录中的 `拾影`。
- 任务、归档、设置：Tauri 的 `app_data_dir`，Windows 通常为 `%APPDATA%/app.shiying.desktop/`。
- 登录数据：同一数据目录下的 `douyin-profile`，由 WebView2 管理。
- 账号 Cookie 不经前端转存，不写入普通配置。诊断导出不包含 Cookie、作品 URL、标题、作者或本地路径。

## 本地开发

环境：Node.js 22+、Rust 1.96.1、Visual Studio C++ Build Tools、Python 3.11+、uv、WebView2 Runtime。

```powershell
npm ci
uv sync --project sidecar --frozen
./scripts/build-sidecar.ps1
npm run desktop
```

完整打包：

```powershell
./scripts/build.ps1
```

安装包位于 `src-tauri/target/release/bundle/nsis/`。

验证：

```powershell
npm run test:engine
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
```

测试覆盖真实核心的 HTTP 文件传输与校验、归档去重、队列恢复、暂停取消、页面桥响应及敏感字段排除。HTTP 集成测试使用本地可控媒体服务，不会登录抖音。

## 代码结构

```text
src/                  React 中文 UI 和类型化 IPC
src-tauri/src/        窗口、sidecar 管理、页面桥、系统对话框
src-tauri/capabilities/ 主窗口与远程抖音窗口的独立权限
sidecar/engine.py     SQLite 队列、状态机、NDJSON 协议
sidecar/adapter.py    上游核心适配与进度报告
sidecar/vendor/      固定版本的 MIT 下载核心（未修改）
sidecar/tests/       本地集成测试与协议测试
scripts/             Windows 可重复构建脚本
```

上游：https://github.com/jiji262/douyin-downloader

固定 commit：`f7ec48f9cfe1fc80b0093440c62c0c60425c31b2`。完整 MIT 许可保留在 `sidecar/vendor/LICENSE-jiji.txt`。本项目的页面桥为独立实现，没有使用上游未公开的桌面代码。

# easydown-douyin
