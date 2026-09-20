import struct
from aiohttp import web
import pytest
from engine import Engine
from adapter import execute


@pytest.mark.parametrize("kind", ["video", "user"])
async def test_video_quality_selection_and_profile_limit(tmp_path, kind):
    requests = []
    payload = struct.pack(">I4s", 24, b"ftyp") + b"isom\x00\x00\x02\x00isomiso2" + struct.pack(">I4s", 100008, b"mdat") + b"\0" * 100000
    async def media(request):
        requests.append(request.path)
        return web.Response(body=payload, content_type="video/mp4")
    app = web.Application()
    app.router.add_get('/{file}', media)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    author = {"nickname":"测试作者", "uid":"123", "sec_uid":"MS4wTestAuthor"}
    def video(index):
        return {"aweme_id":str(7390000000000000001+index), "aweme_type":0,"desc":f"video {index}",
                "create_time":1720000000, "author":author, "video":{"duration":1000,
                "play_addr":{"url_list":[f"http://127.0.0.1:{port}/default.mp4"]},
                "bit_rate":[{"bit_rate":1000000,"play_addr":{"width":720,"height":1280,"url_list":[f"http://127.0.0.1:{port}/720.mp4"]}},
                            {"bit_rate":3000000,"play_addr":{"width":1080,"height":1920,"url_list":[f"http://127.0.0.1:{port}/1080.mp4"]}}]}}
    engine = Engine(tmp_path / "data", tmp_path / "out", lambda _: None)
    try:
        async def bridge(path, params=None, method="GET", data=None):
            if "profile" in path:
                body = {"status_code":0,"user":author}
            elif "/post/" in path:
                body = {"status_code":0,"aweme_list":[video(0),video(1),video(2)],"has_more":0,"max_cursor":1}
            else:
                body = {"status_code":0,"aweme_detail":video(0)}
            return {"http_status":200,"body":body}
        engine.bridge = bridge
        await engine.command({"action":"settings","settings":{"quality":"720p","max_items":2}})
        url = "https://www.douyin.com/user/MS4wTestAuthor" if kind == "user" else "https://www.douyin.com/video/7390000000000000001"
        response = await engine.command({"action":"enqueue","text":url})
        job = engine.tasks[response["added"][0]]
        result = await execute(engine, job)
        expected = 2 if kind == "user" else 1
        assert result["state"] == "completed" and result["success"] == expected, result
        files = list((tmp_path / "out").rglob('*.mp4'))
        assert len(files) == expected and all(file.read_bytes() == payload for file in files)
        assert requests and all(path == '/720.mp4' for path in requests), requests
    finally:
        await engine.shutdown()
        await runner.cleanup()
