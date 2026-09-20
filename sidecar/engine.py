"""Persistent queue and NDJSON protocol. Stdout is reserved for protocol messages."""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import sys
import time
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs

ACTIVE = {"queued", "resolving", "downloading"}
DEFAULTS = {"output_dir": "", "quality": "highest", "max_items": 50,
            "concurrency": 3, "start_date": "", "end_date": "",
            "filename_template": "{date}_{title}_{id}", "save_cover": False,
            "save_metadata": False, "proxy": ""}


class BridgeError(Exception):
    def __init__(self, message, code="PAGE_ERROR"):
        super().__init__(message)
        self.page_bridge_code = code


def extract_urls(text):
    if not isinstance(text, str) or len(text) > 50000:
        raise ValueError("链接内容过长，请每次添加不超过 50 个链接")
    urls = []
    for raw in re.findall(r"https?://[^\s<>\"'，。；！）】]+", text):
        raw = raw.rstrip(".,;!)]}、")
        p = urlsplit(raw)
        if p.hostname not in {"www.douyin.com", "douyin.com", "v.douyin.com", "iesdouyin.com", "www.iesdouyin.com"} or p.username or p.password or p.port not in (None, 80, 443):
            continue
        path, query, host = p.path, p.query, p.hostname
        modal_id = parse_qs(query).get("modal_id", [""])[0]
        if modal_id.isdigit():
            path, query, host = f"/video/{modal_id}", "", "www.douyin.com"
        elif re.fullmatch(r"/(?:video|note|gallery|slides|user|collection|mix)/[\w-]+/?", path):
            query = ""
        elif host != "v.douyin.com" and not path.startswith("/share/"):
            continue
        if host == "douyin.com":
            host = "www.douyin.com"
        normalized = urlunsplit(("https", host, path, query, ""))
        if normalized not in urls:
            urls.append(normalized)
    if not urls:
        raise ValueError("没有识别到抖音链接。请粘贴作品、图集、主页或合集的分享链接")
    if len(urls) > 50:
        raise ValueError("每次最多添加 50 个链接")
    return urls


def validate_settings(current, changes):
    if not isinstance(changes, dict) or set(changes) - set(DEFAULTS):
        raise ValueError("设置字段无效")
    value = {**current, **changes}
    if value["quality"] not in {"highest", "1080p", "720p", "lowest"}:
        raise ValueError("画质选项无效")
    for key, low, high in [("concurrency", 1, 4), ("max_items", 1, 10000)]:
        if isinstance(value[key], bool) or not isinstance(value[key], int) or not low <= value[key] <= high:
            raise ValueError(f"{key} 超出允许范围")
    for key in ["start_date", "end_date"]:
        if value[key]:
            date.fromisoformat(value[key])
    if value["start_date"] and value["end_date"] and value["start_date"] > value["end_date"]:
        raise ValueError("开始日期不能晚于结束日期")
    if not isinstance(value["output_dir"], str) or not Path(value["output_dir"]).is_absolute():
        raise ValueError("请选择有效的绝对保存路径")
    template = value["filename_template"]
    if not isinstance(template, str) or not template.strip() or len(template) > 120 or re.search(r'[<>:"/\\|?*]', template):
        raise ValueError("文件名模板无效，请移除路径分隔符或特殊字符")
    if set(re.findall(r"\{([^{}]+)\}", template)) - {"date", "title", "id", "author"}:
        raise ValueError("文件名支持 {date}、{title}、{id}、{author}")
    if value["proxy"]:
        p = urlsplit(value["proxy"])
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            raise ValueError("代理仅支持不含账号密码的 http(s)://主机:端口")
    return value


class Engine:
    def __init__(self, data_dir, output_dir, emit, executor=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.data_dir / "tasks.sqlite")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.emit = emit
        self.settings = {**DEFAULTS, "output_dir": str(output_dir)}
        saved = self.db.execute("SELECT payload FROM settings WHERE id=1").fetchone()
        if saved:
            self.settings.update(json.loads(saved[0]))
        self.tasks = {row[0]: json.loads(row[1]) for row in self.db.execute("SELECT id,payload FROM tasks")}
        for job in self.tasks.values():
            if job["state"] in ACTIVE:
                job.update(state="paused", detail="上次退出时任务未结束，点击继续恢复", speed=0)
                self.save(job)
        self.executor = executor
        self.running = None
        self.running_id = None
        self.bridge_pending = {}
        self.wakeup = asyncio.Event()
        self.closed = False

    def snapshot(self):
        return {"tasks": sorted(self.tasks.values(), key=lambda j: j["created_at"], reverse=True),
                "settings": self.settings, "version": "0.1.0", "engine": "ready"}

    def save(self, job):
        self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?)", (job["id"], json.dumps(job, ensure_ascii=False)))
        self.db.commit()

    def update(self, job, persist=True, **changes):
        job.update(changes)
        if persist:
            self.save(job)
        self.emit({"type": "task", "task": dict(job)})

    async def bridge(self, path, params=None, method="GET", data=None):
        rid = str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        self.bridge_pending[rid] = fut
        self.emit({"type": "bridge_request", "request_id": rid, "path": path,
                   "params": params or {}, "method": method, "data": data})
        try:
            response = await asyncio.wait_for(fut, timeout=50)
            if response.get("error"):
                raise BridgeError(response["error"], response.get("code", "PAGE_ERROR"))
            return response
        except asyncio.TimeoutError:
            raise BridgeError("抖音页面响应超时，请打开登录窗口完成验证后重试", "TIMEOUT")
        finally:
            self.bridge_pending.pop(rid, None)
            self.emit({"type": "bridge_cancel", "request_id": rid})

    async def command(self, message):
        action = message.get("action")
        if action == "bridge_response":
            future = self.bridge_pending.get(message.get("request_id"))
            if future and not future.done():
                future.set_result(message.get("payload", {}))
            return None
        if action == "snapshot":
            return self.snapshot()
        if action == "settings":
            settings = validate_settings(self.settings, message.get("settings", {}))
            Path(settings["output_dir"]).mkdir(parents=True, exist_ok=True)
            self.settings = settings
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (1,?)", (json.dumps(settings),))
            self.db.commit()
            self.emit({"type": "settings", "settings": settings})
            return settings
        if action == "enqueue":
            urls = extract_urls(message.get("text", ""))
            added = []
            duplicate = 0
            for url in urls:
                if any(j["url"] == url and j["state"] in ACTIVE | {"paused", "waiting_login"} for j in self.tasks.values()):
                    duplicate += 1
                    continue
                job = {"id": str(uuid.uuid4()), "url": url, "state": "queued", "title": "等待解析作品",
                       "author": "", "kind": "user" if "/user/" in url else "link", "detail": "等待下载",
                       "created_at": time.time(), "total": 0, "success": 0, "failed": 0, "skipped": 0,
                       "bytes_read": 0, "bytes_total": 0, "speed": 0, "progress": 0,
                       "output_dir": self.settings["output_dir"], "options": dict(self.settings)}
                self.tasks[job["id"]] = job
                self.update(job)
                added.append(job["id"])
            self.wakeup.set()
            return {"added": added, "duplicate": duplicate}
        if action in {"pause", "cancel", "resume", "retry"}:
            job = self.tasks.get(message.get("task_id"))
            if not job:
                raise ValueError("任务不存在")
            if action in {"pause", "cancel"}:
                if job["state"] not in ACTIVE | {"waiting_login", "paused"}:
                    raise ValueError("该任务已结束")
                state = "paused" if action == "pause" else "cancelled"
                self.update(job, state=state, detail="已暂停，可继续未完成的作品" if state == "paused" else "已取消", speed=0)
                if self.running_id == job["id"] and self.running:
                    self.running.cancel()
                    await asyncio.gather(self.running, return_exceptions=True)
            else:
                if job["state"] in ACTIVE:
                    return {"ok": True}
                self.update(job, state="queued", detail="已重新加入队列", progress=0, bytes_read=0,
                            bytes_total=0, speed=0, total=0, success=0, failed=0, skipped=0)
            self.wakeup.set()
            return {"ok": True}
        if action == "diagnostics":
            return {"version": "0.1.0", "upstream": "f7ec48f9cfe1fc80b0093440c62c0c60425c31b2",
                    "tasks": [{k: j[k] for k in ["state", "kind", "total", "success", "failed", "skipped"]} for j in self.tasks.values()],
                    "settings": {k: self.settings[k] for k in ["quality", "max_items", "concurrency"]}}
        raise ValueError("未知操作")

    async def run_job(self, job):
        self.update(job, state="resolving", detail="正在连接抖音页面")
        try:
            if self.executor is None:
                from adapter import execute
                result = await execute(self, job)
            else:
                result = await self.executor(self, job)
            self.update(job, **result, speed=0)
        except asyncio.CancelledError:
            if job["state"] in ACTIVE:
                self.update(job, state="paused", detail="已暂停", speed=0)
            raise
        except Exception as exc:
            is_bridge = isinstance(exc, BridgeError) or getattr(exc, "page_bridge_code", None) or "LoginRequired" in type(exc).__name__
            detail = str(exc) if is_bridge or isinstance(exc, ValueError) else "下载未完成，请检查网络或重新打开抖音页面后重试"
            # Do not forward raw HTTP errors, cookies, signed URLs, or local paths into diagnostic logs.
            self.update(job, state="waiting_login" if is_bridge else "failed", detail=detail[:240], speed=0)

    async def worker(self):
        while not self.closed:
            job = next((j for j in self.tasks.values() if j["state"] == "queued"), None)
            if job is None:
                self.wakeup.clear()
                await self.wakeup.wait()
                continue
            self.running_id = job["id"]
            self.running = asyncio.create_task(self.run_job(job))
            await asyncio.gather(self.running, return_exceptions=True)
            self.running = None
            self.running_id = None

    async def shutdown(self):
        self.closed = True
        if self.running:
            self.running.cancel()
            await asyncio.gather(self.running, return_exceptions=True)
        for job in self.tasks.values():
            if job["state"] == "queued":
                self.update(job, state="paused", detail="已随应用关闭暂停", speed=0)
        self.wakeup.set()
        self.db.close()
