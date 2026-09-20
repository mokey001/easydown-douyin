# easydown-douyin · 拾影

Windows 抖音下载桌面工具。粘贴分享链接，管理视频、图集和批量任务，把自己有权保存的内容留在本地。

Douyin downloader for Windows, with a desktop GUI, persistent download queue, and local login session.

**[下载 Windows x64 安装包](https://github.com/mokey001/easydown-douyin/releases/download/v0.1.1/Shiying_0.1.1_x64-setup.exe)** · [免安装版](https://github.com/mokey001/easydown-douyin/releases/download/v0.1.1/Shiying-0.1.1-Windows-x64-portable.zip) · [完整源码包](https://github.com/mokey001/easydown-douyin/releases/download/v0.1.1/Shiying-0.1.1-source.zip) · [发布说明](https://github.com/mokey001/easydown-douyin/releases/tag/v0.1.1)

> v0.1.1 为预览版，安装包约 18.5 MB，尚未配置代码签名。完整源码已公开，包含构建脚本、锁定依赖、测试与第三方许可；项目采用 [MIT 许可](LICENSE)。

[功能与验证](#功能与验证) · [使用流程](#使用流程) · [本地开发](#本地开发) · [常见问题](#常见问题) · [反馈需求](https://github.com/mokey001/easydown-douyin/issues)

## 拾影解决什么问题

保存多个抖音作品时，链接、下载进度和文件位置很容易混在一起。拾影把这些操作放进一个中文桌面窗口：

- 粘贴整段分享文案或多条链接，自动识别、去重，一次最多添加 50 个链接。
- 在队列中查看进度、速度和失败原因，暂停、继续或重试任务。
- 按画质、发布日期和作品数量筛选，设置保存目录和文件名。
- 在独立抖音窗口完成登录或验证，无需手动复制 Cookie。

当前目标平台是 Windows x64。安装包内置 Python 下载引擎，使用者无需另外配置 Python 环境。

## 功能与验证

区分「已接入功能」和「已经验证的范围」，方便判断是否适合你的需求。

| 功能 | 当前验证情况 |
| --- | --- |
| 单视频下载 | 一条真实抖音作品已完成在线下载验收，文件为 1080 × 1920、194.5 秒，包含视频与音频；前 5 秒解码检查通过 |
| 图集、主页已发布作品、合集 | 已接入下载核心；图集传输、主页数量限制经过本地集成测试，线上场景尚未全面验收 |
| 队列与历史记录 | 任务持久化、暂停、继续、取消、重试、搜索；重启后未完成任务保留为暂停状态 |
| 文件保存选项 | 画质偏好、日期范围、数量上限、文件名模板，可选保存封面和作品 JSON |
| 登录窗口 | 0.1.1 已修复 Windows 白屏问题，实机确认抖音页面正常显示、主窗口继续响应 |

2026-09-20 的本地验收结果：15 项自动化测试全部通过；打包后的下载引擎通过启动、页面请求桥、文件写入、进度、SQLite 和退出检查。前端与 Windows 安装包构建完成。

这些结果不代表所有作品、账号和网络都可下载，也不能保证平台规则变化后仍然适用。

## 使用流程

1. 从 [v0.1.1 发布页](https://github.com/mokey001/easydown-douyin/releases/tag/v0.1.1) 下载 `Shiying_0.1.1_x64-setup.exe`，关闭旧版拾影后安装。
2. 打开拾影，点击「连接抖音」。平台要求登录或验证码时，由你本人完成。
3. 粘贴分享链接或整段分享文案，点击「添加下载」。
4. 在队列中查看任务，完成后点击「打开所在文件夹」。默认保存在系统「下载」目录中的 `拾影` 文件夹。

画质、保存位置、主页或合集的作品数量和日期范围，都可以在「偏好设置」中调整。

免安装版解压后运行 `shiying.exe`，请保留同目录下的 `shiying-engine.exe`。免安装仅指不需要安装程序；登录数据和任务记录仍使用本机应用数据目录，不随 ZIP 一起移动。

安装包未签名，请根据系统安全提示审慎判断来源。SHA-256 校验值如下；它用于核对下载文件是否一致，不代替安全审查。

```text
70193aa1529357d91ab5ef9464016c221789d1e04cdd5370184c9b00f4b3604b
```

免安装版和完整源码包的校验值见发布页附件 `SHA256SUMS-v0.1.1-full.txt`。

## 本地开发

Windows 开发环境：Node.js 22+、Rust 1.96.1（见 `rust-toolchain.toml`）、Visual Studio C++ Build Tools、Python 3.11+、uv 和 WebView2 Runtime。依赖安装和首次编译需要联网。

```powershell
git clone https://github.com/mokey001/easydown-douyin.git
cd easydown-douyin
npm ci
uv sync --project sidecar --frozen
./scripts/build-sidecar.ps1
npm run desktop
```

构建安装包：

```powershell
./scripts/build.ps1
```

安装包位于 `src-tauri/target/release/bundle/nsis/`。构建脚本会先下载锁定的 Rust 依赖，再收集第三方许可。

验证：

```powershell
npm run test:engine
npm run build
cargo check --manifest-path src-tauri/Cargo.toml --locked
```

`src/` 是中文界面，`src-tauri/src/` 管理窗口和页面请求桥，`sidecar/` 包含下载引擎与本地测试。协议与边界见 [架构说明](docs/architecture.md)。代码库不包含用户登录状态、下载文件、运行时数据库或打包依赖缓存。

## 常见问题

### 现在能下载或编译吗？

可以。安装包和免安装版见上方链接；开发者可克隆本仓库的 `main` 分支，或下载 `Shiying-0.1.1-source.zip`。

注意：`v0.1.1` 标签在首次仅发布安装包时已经创建，为保留原发布历史，没有移动这个标签。因此该发布页底部自动生成的 `Source code (zip/tar.gz)` 仍是当时的说明文件快照。完整应用源码请使用具名附件 `Shiying-0.1.1-source.zip` 或 `main` 分支。

### 一定要登录吗？

部分公开内容可以尝试直接下载，但平台可能要求登录或验证。「页面已连接」只表示抖音页面加载完成，不表示账号已经登录。工具不会代你完成验证码，也不提供绕过访问权限的功能。

### 账号和文件放在哪里？

登录状态由本机 WebView2 管理；任务、历史和设置保存在本机。应用不接入第三方解析服务，不将下载完成的文件上传到项目服务器。抖音网页和媒体下载本身仍需要联网。

### 暂停后会从断点继续吗？

继续时会跳过已完成作品，未完成文件可能重新下载；当前不是字节级断点续传。关闭主程序会结束下载，不提供托盘后台驻留。

### 支持哪些平台和功能？

当前仅验收 Windows x64。macOS、Linux、直播录制、喜欢或收藏列表、音频提取、转码和自动更新都不在本版范围。安装包尚未配置代码签名。

## 反馈与关注

欢迎通过 [Issues](https://github.com/mokey001/easydown-douyin/issues) 描述你的使用场景，例如「希望备份自己的主页作品，并按月份整理」。请不要提交 Cookie、密码、手机号或未打码的账号截图。

如果拾影帮你省下了整理链接和文件的时间，可以点一个 Star，或把项目分享给有同样需求的人。反馈时请注明版本、Windows 版本、链接类型和操作步骤，不必提供账号数据。

## 技术与致谢

桌面部分使用 Tauri 2、React 和 TypeScript，下载引擎使用 Python。下载核心基于 MIT 许可的 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)，固定版本为 [`f7ec48f9`](https://github.com/jiji262/douyin-downloader/commit/f7ec48f9cfe1fc80b0093440c62c0c60425c31b2)。保留了 [上游许可](sidecar/vendor/LICENSE-jiji.txt) 和 [第三方声明](THIRD_PARTY_NOTICES.txt)。

拾影的桌面界面与页面请求桥为独立实现，没有使用上游未公开的桌面代码。此项目与抖音官方无关联。

请只保存你拥有权利或已获许可的内容，尊重创作者，并遵守适用的平台规则。

## English overview

Shiying is a Windows desktop app for saving Douyin content you own or have permission to download. It includes a download queue, history, quality preferences, and a local WebView login window. The desktop uses Tauri and React, with a Python engine based on the MIT-licensed project credited above.

**Source and Windows preview available:** download the unsigned installer or portable ZIP from the [v0.1.1 release](https://github.com/mokey001/easydown-douyin/releases/tag/v0.1.1). Full source, build scripts and tests are available on `main` under the MIT license, and in the named `Shiying-0.1.1-source.zip` asset. The original v0.1.1 tag remains unchanged, so its automatic source archives contain the earlier documentation snapshot. A local v0.1.1 build passed 15 automated tests and one real-world video download check. Availability across accounts and content is not guaranteed. Feedback on intended use cases is welcome in Issues.
