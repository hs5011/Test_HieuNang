"""Tiện ích chung cho sinh script: phân tích thời lượng, hồ sơ tải theo loại kịch bản."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import TestConfig

# Tên hiển thị thống nhất cho mọi màn hình / biểu đồ / báo cáo (mã nội bộ smoke, load… giữ nguyên trong dữ liệu)
SCENARIO_NAMES = {
    "smoke": "Smoke Test",
    "load": "Load Test",
    "stress": "Stress Test",
    "spike": "Spike Test",
    "soak": "Soak Test",
}
SCENARIO_ORDER = list(SCENARIO_NAMES)
SCENARIO_TYPES = {
    "smoke": "Smoke Test – chạy ít tải, kiểm tra hệ thống & kịch bản hoạt động ổn trước khi test lớn",
    "load": "Load Test – chạy đúng tải dự kiến (ramp-up → giữ tải → ramp-down)",
    "stress": "Stress Test – chạy vượt tải, tăng dần theo bậc tới 150% tải mục tiêu để tìm giới hạn",
    "spike": "Spike Test – tải tăng đột ngột lên mức mục tiêu rồi giảm",
    "soak": "Soak Test – chạy tải liên tục trong thời gian dài",
}


def scenario_name(key: str) -> str:
    """'smoke' -> 'Smoke Test' (giữ nguyên nếu không nhận ra)."""
    return SCENARIO_NAMES.get(key, key)


def scenario_rank(key: str) -> int:
    return SCENARIO_ORDER.index(key) if key in SCENARIO_ORDER else 9


def parse_duration(s: str | int | float) -> int:
    """'1h30m', '5m', '45s', '90' -> số giây."""
    if isinstance(s, (int, float)):
        return int(s)
    s = (s or "").strip().lower()
    if s.isdigit():
        return int(s)
    total = 0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)", s):     # "ms" xét trước "m": 500ms ≠ 500 phút
        total += float(num) * {"ms": 0.001, "h": 3600, "m": 60, "s": 1}[unit]
    return int(total)


def fmt_duration(sec: int) -> str:
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return "".join(f"{v}{u}" for v, u in ((h, "h"), (m, "m"), (s, "s")) if v) or "0s"


@dataclass
class Stage:
    duration_s: int
    target: int


def stages_for(cfg: TestConfig, vus: int | None = None) -> list[Stage]:
    vus = max(1, int(vus or cfg.vus))
    up, hold, down = parse_duration(cfg.ramp_up), parse_duration(cfg.duration), parse_duration(cfg.ramp_down)
    t = cfg.scenario_type
    if t == "smoke":
        # tăng nhanh lên đủ VUs rồi giữ cố định (tránh k6 ramp tuyến tính suốt cả phiên)
        return [Stage(5, vus), Stage(max(hold, 30), vus)]
    if t == "stress":
        step = max(hold // 5, 30)
        return [Stage(up, int(vus * 0.5)), Stage(step, int(vus * 0.5)), Stage(up, vus), Stage(step, vus),
                Stage(up, int(vus * 1.25)), Stage(step, int(vus * 1.25)), Stage(up, int(vus * 1.5)),
                Stage(step, int(vus * 1.5)), Stage(down, 0)]
    if t == "spike":
        return [Stage(10, max(1, vus // 10)), Stage(max(up // 4, 10), vus), Stage(max(hold, 30), vus),
                Stage(10, max(1, vus // 10)), Stage(30, max(1, vus // 10)), Stage(max(down, 10), 0)]
    # load / soak
    return [Stage(up, vus), Stage(hold, vus), Stage(down, 0)]


def total_seconds(cfg: TestConfig) -> int:
    return sum(s.duration_s for s in stages_for(cfg))


def split_vus(total: int, n: int) -> list[int]:
    base, rem = divmod(max(total, n), n)
    return [base + (1 if i < rem else 0) for i in range(n)]
