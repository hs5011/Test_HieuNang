"""Lưu/đọc dự án trong thư mục workspace/projects/<id>/."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from unidecode import unidecode

from .config import PROJECTS_DIR
from .models import Project, _now

KEYRING_SERVICE = "PerfTool"


def slugify(text: str) -> str:
    s = unidecode(text or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "project"


def project_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def sub_dir(project_id: str, name: str) -> Path:
    """Các thư mục con chuẩn: input, crawl, scripts, runs, charts, reports."""
    d = project_dir(project_id) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_projects() -> list[Project]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(PROJECTS_DIR.glob("*/project.json")):
        try:
            out.append(load_project(f.parent.name))
        except Exception:  # noqa: BLE001 - bỏ qua dự án hỏng
            continue
    return sorted(out, key=lambda p: p.updated_at, reverse=True)


def create_project(name: str) -> Project:
    pid = f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(name)[:30]}"
    p = Project(id=pid)
    p.info.name = name
    save_project(p)
    return p


def load_project(project_id: str) -> Project:
    f = PROJECTS_DIR / project_id / "project.json"
    with open(f, encoding="utf-8") as fh:
        return Project.model_validate(json.load(fh))


def save_project(p: Project) -> None:
    p.updated_at = _now()
    f = project_dir(p.id) / "project.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(p.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(f)


def delete_project(project_id: str) -> None:
    shutil.rmtree(PROJECTS_DIR / project_id, ignore_errors=True)


# ------------------------------------------------ mật khẩu (Windows Credential Manager)
def save_password(project_id: str, username: str, password: str) -> bool:
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, f"{project_id}:{username}", password)
        return True
    except Exception:  # noqa: BLE001
        return False


def load_password(project_id: str, username: str) -> str:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, f"{project_id}:{username}") or ""
    except Exception:  # noqa: BLE001
        return ""


def delete_password(project_id: str, username: str) -> None:
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, f"{project_id}:{username}")
    except Exception:  # noqa: BLE001 - không có mục nào để xoá
        pass
