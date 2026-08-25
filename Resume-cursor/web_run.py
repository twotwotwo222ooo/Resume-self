from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8001
FALLBACK_PORTS = (8002, 8003, 8004, 8005)


def _port_in_use(host: str, port: int) -> bool:
    probe = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe, port)) == 0


def _pick_port(host: str, preferred: int) -> int:
    if not _port_in_use(host, preferred):
        return preferred
    for port in FALLBACK_PORTS:
        if not _port_in_use(host, port):
            print(
                f"端口 {preferred} 已被旧服务占用（可能没有删除接口）。"
                f"改用 {port} 启动。",
                file=sys.stderr,
            )
            return port
    raise SystemExit(
        f"端口 {preferred} 及备用端口 {', '.join(map(str, FALLBACK_PORTS))} 均被占用。"
        "请关闭任务管理器中的 python / uvicorn 进程后重试。"
    )


def main() -> None:
    os.chdir(ROOT)
    host = os.getenv("HOST", "0.0.0.0")
    preferred = int(os.getenv("PORT", str(DEFAULT_PORT)))
    port = _pick_port(host, preferred)
    reload = os.getenv("RELOAD", "0").strip() not in {"0", "false", "False"}
    print(f"启动服务：http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
