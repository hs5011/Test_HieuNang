"""Quản lý tác vụ nền (crawler, chạy test) dưới dạng tiến trình con.

Chạy tách tiến trình giúp giao diện Streamlit không bị treo và tránh xung đột
event-loop của Playwright trên Windows. Mỗi job có:
  jobs/<name>.json  : trạng thái (pid, status, started, finished, message)
  jobs/<name>.log   : log stdout/stderr
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

from .config import ROOT_DIR
from .storage import sub_dir


def _paths(project_id: str, name: str) -> tuple[Path, Path]:
    d = sub_dir(project_id, "jobs")
    return d / f"{name}.json", d / f"{name}.log"


def write_status(project_id: str, name: str, **fields) -> None:
    f, _ = _paths(project_id, name)
    data = read_status(project_id, name) or {}
    data.update(fields)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(project_id: str, name: str) -> Optional[dict]:
    f, _ = _paths(project_id, name)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def start_job(project_id: str, name: str, module: str, args: list[str], env: Optional[dict] = None) -> dict:
    """Khởi chạy `python -m <module> <args>` ở chế độ nền."""
    if is_running(project_id, name):
        raise RuntimeError(f"Tác vụ '{name}' đang chạy")
    f, log = _paths(project_id, name)
    full_env = os.environ.copy()
    full_env["PYTHONIOENCODING"] = "utf-8"
    full_env["PYTHONUTF8"] = "1"
    if env:
        full_env.update(env)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    logf = open(log, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-u", "-m", module, *args], cwd=str(ROOT_DIR), env=full_env,
                            stdout=logf, stderr=subprocess.STDOUT, creationflags=flags)
    status = {"pid": proc.pid, "status": "running", "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "finished": "", "message": "", "module": module, "args": args}
    f.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def is_running(project_id: str, name: str) -> bool:
    st = read_status(project_id, name)
    if not st or st.get("status") != "running":
        return False
    pid = st.get("pid")
    try:
        p = psutil.Process(pid)
        alive = p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, TypeError):
        alive = False
    if not alive:
        # tiến trình đã kết thúc mà không cập nhật trạng thái => coi là lỗi
        write_status(project_id, name, status="failed", finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     message=st.get("message") or "Tiến trình kết thúc bất thường (xem log)")
    return alive


def stop_job(project_id: str, name: str) -> None:
    st = read_status(project_id, name)
    if not st:
        return
    kill_tree(st.get("pid"))
    # tiến trình bị dừng đột ngột không kịp dọn file tạm chứa tài khoản/mật khẩu -> dọn tại đây
    from .accounts import cleanup_secret_files
    cleanup_secret_files(sub_dir(project_id, "runs"))
    write_status(project_id, name, status="stopped", finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 message="Người dùng đã dừng")


def kill_tree(pid: Optional[int]) -> None:
    if not pid:
        return
    try:
        parent = psutil.Process(pid)
        for c in parent.children(recursive=True):
            try:
                c.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def read_log(project_id: str, name: str, tail: int = 200) -> str:
    _, log = _paths(project_id, name)
    if not log.exists():
        return ""
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(lines[-tail:])
