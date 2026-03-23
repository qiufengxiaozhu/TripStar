"""启动脚本"""

import os
import sys

# Windows 下强制 UTF-8，必须在所有其他 import 之前设置，
# 这样 uvicorn --reload spawn 的子进程也能继承这些环境变量。
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()

    print(f"[启动] 工作目录: {os.getcwd()}", flush=True)
    print(f"[启动] Python: {sys.executable}", flush=True)
    print(f"[启动] stdout编码: {sys.stdout.encoding}", flush=True)
    print(f"[启动] PYTHONUTF8={os.environ.get('PYTHONUTF8')}", flush=True)
    print(f"[启动] 服务地址: http://{settings.host}:{settings.port}", flush=True)

    uvicorn.run(
        "app.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )

