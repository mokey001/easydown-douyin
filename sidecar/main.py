import argparse
import asyncio
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
from engine import Engine


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    protocol = sys.stdout
    sys.stdout = sys.stderr
    def emit(message):
        protocol.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        protocol.flush()
    engine = Engine(args.data_dir, args.output_dir, emit)
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    def read_input():
        for line in sys.stdin:
            loop.call_soon_threadsafe(queue.put_nowait, line)
        loop.call_soon_threadsafe(queue.put_nowait, None)
    threading.Thread(target=read_input, daemon=True).start()
    worker = asyncio.create_task(engine.worker())
    emit({"type": "ready", **engine.snapshot()})
    try:
        while (line := await queue.get()) is not None:
            request = {}
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("请求格式无效")
                if request.get("action") == "shutdown":
                    break
                result = await engine.command(request)
                if request.get("action") != "bridge_response":
                    emit({"type": "response", "request_id": request.get("request_id"), "ok": True, "data": result})
            except Exception as exc:
                emit({"type": "response", "request_id": request.get("request_id") if isinstance(request, dict) else None,
                      "ok": False, "error": str(exc) if isinstance(exc, ValueError) else "操作失败，请重试"})
    finally:
        await engine.shutdown()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
