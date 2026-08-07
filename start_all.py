"""
一键启动脚本 —— crypto_causal_agent 全栈
  1. 检查/启动数据库容器（docker compose up -d）
  2. 启动后端 API（8699，pythonw 独立进程，不占用终端）
  3. 启动前端（8700，pnpm dev）
  4. --agent 可选：自动启动 Agent 决策循环

用法：
  python start_all.py            # 只启动服务
  python start_all.py --agent    # 启动服务 + 自动运行 Agent 循环
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
VENV_PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
BACKEND = ROOT / "dashboard" / "server.py"
FRONTEND = ROOT / "dashboard" / "frontend"

# Windows 分离进程标志
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def ensure_docker() -> bool:
    """确保 3 个数据库容器在运行"""
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=20).stdout
        missing = [n for n in ("timescaledb", "neo4j", "redis") if n not in out]
        if missing:
            print(f"[docker] 容器未就绪，执行 docker compose up -d ...")
            r = subprocess.run(["docker", "compose", "up", "-d"],
                               cwd=ROOT, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                print(f"[docker] 启动失败: {r.stderr[:300]}")
                return False
            print("[docker] 容器已启动")
        else:
            print("[docker] 容器已就绪")
        # 等待健康
        for _ in range(30):
            out = subprocess.run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
                                 capture_output=True, text=True, timeout=20).stdout
            if "healthy" in out or "Up" in out:
                return True
            time.sleep(2)
        return True
    except Exception as e:
        print(f"[docker] 检查失败: {e}")
        return True  # 不阻塞（可能 docker 不在 PATH）


def start_backend() -> bool:
    """启动后端（pythonw 独立进程）"""
    if _http_ok("http://localhost:8699/api/health"):
        print("[backend] 已在运行 (http://localhost:8699)")
        return True
    print("[backend] 启动 ...")
    exe = VENV_PYTHONW if VENV_PYTHONW.exists() else VENV_PY
    env = dict(os.environ)
    env["TMP"] = env["TEMP"] = "C:\\tmp"
    try:
        subprocess.Popen([str(exe), str(BACKEND)],
                         cwd=ROOT / "dashboard", env=env,
                         creationflags=DETACHED,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[backend] 启动失败: {e}")
        return False
    for _ in range(30):
        if _http_ok("http://localhost:8699/api/health"):
            print("[backend] 已就绪 (http://localhost:8699)")
            return True
        time.sleep(1)
    print("[backend] 等待超时（检查端口 8699）")
    return False


def start_frontend() -> bool:
    """启动前端（pnpm dev）"""
    if _http_ok("http://localhost:8700/"):
        print("[frontend] 已在运行 (http://localhost:8700)")
        return True
    print("[frontend] 启动 vite ...")
    try:
        subprocess.Popen(["pnpm", "dev"], cwd=FRONTEND,
                         creationflags=DETACHED,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[frontend] 启动失败: {e}")
        return False
    for _ in range(60):
        if _http_ok("http://localhost:8700/"):
            print("[frontend] 已就绪 (http://localhost:8700)")
            return True
        time.sleep(1)
    print("[frontend] 等待超时（检查端口 8700）")
    return False


def start_agent() -> bool:
    """通过 API 启动 Agent 决策循环"""
    if not _http_ok("http://localhost:8699/api/health"):
        return False
    import json
    req = urllib.request.Request(
        "http://localhost:8699/api/agent/start", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read())
        if body.get("status") == "running":
            print("[agent] Agent 决策循环已启动（每 120s 一周期）")
            return True
    except Exception as e:
        print(f"[agent] 启动失败: {e}")
    return False


def main():
    ap = argparse.ArgumentParser(description="crypto_causal_agent 一键启动")
    ap.add_argument("--agent", action="store_true", help="启动后自动运行 Agent 决策循环")
    ap.add_argument("--no-docker", action="store_true", help="跳过数据库容器检查")
    args = ap.parse_args()

    print("=" * 50)
    print("  crypto_causal_agent — 一键启动")
    print("=" * 50)

    if not args.no_docker:
        ensure_docker()

    ok = start_backend()
    ok = start_frontend() and ok

    if args.agent:
        time.sleep(2)
        start_agent()

    print("=" * 50)
    print("  后端 API:   http://localhost:8699")
    print("  前端工作台: http://localhost:8700")
    print("  WebSocket:  ws://localhost:8699/ws")
    if not ok:
        print("  提示: 部分服务启动异常，请检查上方日志")
    print("=" * 50)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
