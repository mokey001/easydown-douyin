"""Original adapter over the unmodified MIT core; page signing stays in WebView."""
import time
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

from engine import BridgeError
from config import ConfigLoader
from config.default_config import DEFAULT_CONFIG
from core import DouyinAPIClient, DownloaderFactory, URLParser
from storage import FileManager, Database
from control import RateLimiter, RetryHandler, QueueManager


class MemoryCookies:
    def get_cookies(self):
        return {}
    def get_cookie_string(self):
        return ""
    def set_cookies(self, cookies):
        pass


class PageBridge:
    def __init__(self, engine):
        self.engine = engine

    async def fetch(self, path, params, method="GET", data=None):
        answer = await self.engine.bridge(path, params, method, data)
        status = answer.get("http_status", 0)
        body = answer.get("body")
        if status in (401, 403, 429):
            raise BridgeError("抖音要求登录或验证。请打开登录窗口，完成验证后点击重试", "VERIFICATION_REQUIRED")
        if status == 200 and not isinstance(body, dict):
            raise BridgeError("抖音返回了验证页面，请在登录窗口完成验证", "VERIFICATION_REQUIRED")
        if isinstance(body, dict) and (body.get("verify_ticket") or body.get("status_code") in {8, 9, 1024}):
            raise BridgeError("登录状态失效或需要验证，请打开登录窗口处理", "NOT_LOGGED_IN")
        return SimpleNamespace(http_status=status, body=body, text="" if body else answer.get("text", ""))


class DesktopAPI(DouyinAPIClient):
    def __init__(self, engine, reporter, proxy):
        super().__init__({}, proxy=proxy, page_bridge=PageBridge(engine))
        self.reporter = reporter

    async def _ensure_ms_token(self):
        return ""  # The page SDK owns browser identity. Never mint a conflicting identity in Python.

    async def _request_json(self, path, params, *, method="GET", data=None, request_headers=None, suppress_error=False):
        return await self._request_json_gated(path, params, method=method, data=data, suppress_error=suppress_error)

    async def get_video_detail(self, aweme_id, **kwargs):
        detail = await super().get_video_detail(aweme_id, **kwargs)
        if detail:
            self.reporter.engine.update(self.reporter.job, title=(detail.get("desc") or "抖音作品")[:200],
                                       kind="gallery" if detail.get("images") else "video")
        return detail


class Reporter:
    def __init__(self, engine, job):
        self.engine, self.job = engine, job
        self.last_emit = 0
        self.samples = {}

    def update_step(self, step, detail=""):
        self.engine.update(self.job, detail=detail or step, persist=False)

    def set_item_total(self, total, detail=""):
        self.engine.update(self.job, total=total, detail=detail or "正在下载作品")

    def advance_item(self, status, detail="", reason=""):
        key = "success" if status in {"success", "ok", "succeeded"} else "skipped" if status in {"skip", "skipped"} else "failed"
        self.job[key] += 1
        done = sum(self.job[k] for k in ["success", "skipped", "failed"])
        self.engine.update(self.job, progress=min(99, int(100 * done / max(1, self.job["total"]))),
                           detail=reason or f"已处理 {done} / {self.job['total']} 个作品", speed=0)

    def on_item_progress(self, *, aweme_id, bytes_read, bytes_total):
        now = time.monotonic()
        old_time, old_bytes = self.samples.get(aweme_id, (now, bytes_read))
        if now - self.last_emit < 0.25 and bytes_read != bytes_total and self.job["bytes_read"] > 0:
            return
        speed = max(0, (bytes_read - old_bytes) / max(0.01, now - old_time))
        self.samples[aweme_id] = (now, bytes_read)
        self.last_emit = now
        done = self.job["success"] + self.job["failed"] + self.job["skipped"]
        fraction = bytes_read / bytes_total if bytes_total else 0
        progress = min(99, int(100 * (done + fraction) / max(1, self.job["total"])))
        self.engine.update(self.job, persist=False, state="downloading", bytes_read=bytes_read,
                           bytes_total=bytes_total, speed=speed, progress=progress, detail="正在保存媒体文件")

    def on_output_dir(self, *, path):
        self.engine.update(self.job, output_dir=path)

    def on_author(self, nickname=None, sec_uid=None):
        if nickname:
            changes = {"author": nickname}
            if self.job["kind"] == "user":
                changes["title"] = f"{nickname} 的作品"
            self.engine.update(self.job, **changes)


class ReportingFileManager(FileManager):
    """Gallery/cover paths in the core do not all supply a byte callback."""
    def __init__(self, path, reporter):
        super().__init__(path)
        self.reporter = reporter

    async def download_file(self, url, save_path, *args, **kwargs):
        if kwargs.get("on_progress") is None:
            kwargs["on_progress"] = lambda read, total: self.reporter.on_item_progress(
                aweme_id=str(save_path), bytes_read=read, bytes_total=total)
        return await super().download_file(url, save_path, *args, **kwargs)

    @staticmethod
    async def _stream_to_tmp(chunk_iter, tmp_path, expected_size, on_progress):
        written = await FileManager._stream_to_tmp(chunk_iter, tmp_path, expected_size, on_progress)
        # The upstream intentionally suppresses events for transfers shorter than 2s.
        # Desktop also needs their final byte count for the task row.
        if on_progress:
            on_progress(written, expected_size or written)
        return written


async def execute(engine, job):
    opts = job["options"]
    config = ConfigLoader()
    config.config = deepcopy(DEFAULT_CONFIG)
    config.config.update(path=opts["output_dir"], video_quality=opts["quality"], thread=opts["concurrency"],
                         filename_template=opts["filename_template"], cover=opts["save_cover"],
                         json=opts["save_metadata"], start_time=opts["start_date"], end_time=opts["end_date"],
                         mode=["post"], browser_fallback={"enabled": False}, proxy=opts["proxy"], retry_times=2)
    config.config["number"]["post"] = opts["max_items"]
    config.config["number"]["mix"] = opts["max_items"]
    config.config["number"]["allmix"] = opts["max_items"]
    reporter = Reporter(engine, job)
    database = Database(str(engine.data_dir / "archive.sqlite"))
    try:
        await database.initialize()
        async with DesktopAPI(engine, reporter, opts["proxy"]) as api:
            url = job["url"]
            if "v.douyin.com" in url or "/share/" in url:
                url = await api.resolve_short_url(url)
                if not url:
                    raise ValueError("短链接解析失败，请在浏览器打开后复制完整作品地址")
            parsed = URLParser.parse(url)
            if not parsed or parsed["type"] not in {"video", "gallery", "user", "collection"}:
                raise ValueError("此版本支持视频、图集、主页作品和合集链接")
            engine.update(job, kind=parsed["type"], detail="正在读取作品信息")
            downloader = DownloaderFactory.create(parsed["type"], config, api, ReportingFileManager(opts["output_dir"], reporter),
                MemoryCookies(), database, RateLimiter(max_per_second=1.5), RetryHandler(max_retries=2),
                QueueManager(max_workers=opts["concurrency"]), reporter, job_id=job["id"])
            result = await downloader.download(parsed)
            counts = {k: getattr(result, k) for k in ["total", "success", "failed", "skipped"]}
            if result.incomplete_reason:
                return {**counts, "state": "failed", "detail": "部分作品已保存，列表未完整获取。请完成登录验证后重试"}
            if result.failed:
                return {**counts, "state": "failed", "detail": job["detail"] if job["failed"] else "部分资源下载失败，可重试"}
            if result.total == 0:
                return {**counts, "state": "failed", "detail": "没有获取到符合条件的作品，请检查筛选日期及主页是否公开"}
            return {**counts, "state": "completed", "progress": 100,
                    "detail": f"已保存 {result.success} 个作品" + (f" · 跳过 {result.skipped} 个已有作品" if result.skipped else "")}
    finally:
        await database.close()
