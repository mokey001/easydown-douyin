import asyncio
import json
from pathlib import Path

import pytest
from engine import Engine, BridgeError, extract_urls, validate_settings, DEFAULTS

URL = "https://www.douyin.com/video/7390000000000000001"


def test_share_text_normalization_and_duplicates():
    text = f"复制打开抖音！{URL}?foo=secret。再次分享 {URL} https://www.douyin.com/user/self?modal_id=7390000000000000001"
    assert extract_urls(text) == [URL]


@pytest.mark.parametrize("url", ["https://www.douyin.com.evil.org/video/1", "https://evil.org", "file:///C:/test", "https://www.douyin.com@evil.org/video/1", "https://www.douyin.com:9000/video/1"])
def test_reject_non_douyin_input(url):
    with pytest.raises(ValueError):
        extract_urls(url)


def test_settings_validate_atomically(tmp_path):
    current = {**DEFAULTS, "output_dir": str(tmp_path)}
    with pytest.raises(ValueError):
        validate_settings(current, {"start_date": "2026-09-20", "end_date": "2026-09-01"})
    assert current["start_date"] == ""
    with pytest.raises(ValueError):
        validate_settings(current, {"filename_template": "../{id}"})


async def test_persistent_queue_and_deduplication(tmp_path):
    engine = Engine(tmp_path / "data", tmp_path / "media", lambda _: None)
    first = await engine.command({"action": "enqueue", "text": URL})
    second = await engine.command({"action": "enqueue", "text": URL})
    assert len(first["added"]) == 1 and second["duplicate"] == 1
    engine.db.close()  # Simulate process loss while a task is queued.
    restored = Engine(tmp_path / "data", tmp_path / "media", lambda _: None)
    assert restored.tasks[first["added"][0]]["state"] == "paused"
    await restored.shutdown()


async def wait_for(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.01)


async def test_pause_cancels_running_work_then_resume_completes(tmp_path):
    started = asyncio.Event()
    cancelled = asyncio.Event()
    gate = asyncio.Event()
    async def execute(engine, job):
        started.set()
        try:
            await gate.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"state": "completed", "success": 1, "total": 1}
    engine = Engine(tmp_path, tmp_path / "out", lambda _: None, execute)
    worker = asyncio.create_task(engine.worker())
    response = await engine.command({"action": "enqueue", "text": URL})
    task_id = response["added"][0]
    await asyncio.wait_for(started.wait(), 3)
    await engine.command({"action": "pause", "task_id": task_id})
    assert cancelled.is_set() and engine.tasks[task_id]["state"] == "paused"
    gate.set()
    await engine.command({"action": "resume", "task_id": task_id})
    await wait_for(lambda: engine.tasks[task_id]["state"] == "completed")
    await engine.shutdown()
    await worker


async def test_bridge_failure_is_actionable_and_does_not_block_next_task(tmp_path):
    calls = []
    async def execute(engine, job):
        calls.append(job["id"])
        if len(calls) == 1:
            raise BridgeError("请打开登录窗口", "NOT_LOGGED_IN")
        return {"state": "completed", "total": 1, "success": 1}
    engine = Engine(tmp_path, tmp_path / "out", lambda _: None, execute)
    await engine.command({"action":"enqueue", "text": URL + " " + URL.replace("0001", "0002")})
    worker = asyncio.create_task(engine.worker())
    await wait_for(lambda: len(calls) == 2)
    await wait_for(lambda: any(t["state"] == "completed" for t in engine.tasks.values()))
    assert next(iter(engine.tasks.values()))["state"] == "waiting_login"
    await engine.shutdown()
    await worker


async def test_bridge_round_trip_and_cleanup(tmp_path):
    events = []
    engine = Engine(tmp_path, tmp_path / "out", events.append)
    task = asyncio.create_task(engine.bridge("/aweme/v1/web/aweme/detail/"))
    await wait_for(lambda: bool(events))
    rid = events[-1]["request_id"]
    await engine.command({"action":"bridge_response","request_id":rid,"payload":{"http_status":200,"body":{"status_code":0}}})
    result = await task
    assert result["http_status"] == 200 and not engine.bridge_pending
    await engine.shutdown()


async def test_diagnostics_excludes_urls_paths_and_identity(tmp_path):
    engine = Engine(tmp_path, tmp_path / "private", lambda _: None)
    await engine.command({"action":"enqueue","text":URL})
    text = json.dumps(await engine.command({"action":"diagnostics"}))
    assert "7390000000000000001" not in text and "private" not in text
    await engine.shutdown()


async def test_real_core_downloads_gallery_bytes_and_skips_existing(tmp_path):
    from aiohttp import web
    from adapter import execute
    # Local integration fixture exercises the actual upstream downloader, database and file writer.
    content = b"\xff\xd8\xff\xe0" + b"test-image-payload" * 6000 + b"\xff\xd9"
    server = web.Application()
    async def media(request):
        return web.Response(body=content, content_type="image/jpeg")
    server.router.add_get('/image.jpg', media)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        events = []
        engine = Engine(tmp_path / "data", tmp_path / "out", events.append)
        async def bridge(path, params=None, method="GET", data=None):
            return {"http_status":200,"body":{"status_code":0,"aweme_detail":{
                "aweme_id":"7390000000000000001", "aweme_type":68, "desc":"集成测试图集", "create_time":1720000000,
                "author":{"nickname":"测试作者","sec_uid":"test-user","uid":"123"},
                "images":[{"url_list":[f"http://127.0.0.1:{port}/image.jpg"]}]
            }}}
        engine.bridge = bridge
        reply = await engine.command({"action":"enqueue","text":URL.replace('/video/','/note/')})
        job = engine.tasks[reply["added"][0]]
        result = await execute(engine, job)
        assert result["state"] == "completed" and result["success"] == 1
        images = list((tmp_path / "out").rglob('*.jpg'))
        assert len(images) == 1 and images[0].read_bytes() == content
        result = await execute(engine, job)
        assert result["skipped"] == 1 and result["failed"] == 0
        assert any(e.get("task", {}).get("bytes_read", 0) > 0 for e in events)
        await engine.shutdown()
    finally:
        await runner.cleanup()
