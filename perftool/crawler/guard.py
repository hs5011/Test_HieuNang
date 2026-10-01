"""Bộ chặn ghi dữ liệu: huỷ request ghi (Lưu/Xoá/Duyệt…) trước khi tới máy chủ khi crawler bấm thử
hoặc khi người dùng ghi thao tác thủ công. Request bị chặn vẫn được ghi nhận (blocked=True) để sinh kịch bản test.

Quy tắc chi tiết: xem `crawler.write_guard` trong config/settings.yaml.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional
from urllib.parse import parse_qsl, unquote, urlparse

from .. import config

LEVELS = {"keyword": "Chặn request ghi theo từ khoá (khuyến nghị)",
          "strict": "Chặn mọi request không phải GET (trừ API truy vấn)",
          "off": "Không chặn (thao tác của tôi sẽ ghi dữ liệu thật)"}

# đoạn đường dẫn là mã bản ghi (số, GUID, chuỗi hex dài) -> bỏ qua khi tìm "đoạn cuối có nghĩa"
_ID_SEG = re.compile(r"^(\d+|[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}|[0-9a-f]{16,})$", re.I)


def _ascii(s: str) -> str:
    """Giải mã %xx, bỏ dấu tiếng Việt (cập-nhật -> cap-nhat), chữ thường."""
    s = unicodedata.normalize("NFD", unquote(s or "")).replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def _tokens(s: str) -> list[str]:
    """Tách từ: theo ký tự không phải chữ/số và theo chữ hoa (CheckAndApprove -> check, and, approve)."""
    s = unicodedata.normalize("NFD", unquote(s or "")).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return [t for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t]


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _ascii(s))


def has_keyword(text: str, words: list[str]) -> bool:
    """So khớp từ khoá trong đoạn văn bản URL (đã bỏ dấu, không phân biệt hoa thường):
      - "xoa*" (có dấu * cuối): một TỪ bắt đầu bằng xoa (xoaBanGhi, xoabanghi);
      - "=read" hoặc từ khoá ≤ 3 ký tự (gui, huy, ky…): phải là NGUYÊN một từ (tránh guid, huyen, thread);
      - từ khoá dài hơn: chứa ở bất kỳ đâu (deleteItem, cap-nhat -> capnhat).
    """
    comp, toks = _compact(text), _tokens(text)
    for w in words:
        w = str(w).strip()
        k = _compact(w)
        if not k:
            continue
        if w.endswith("*"):
            if any(t.startswith(k) for t in toks):
                return True
        elif w.startswith("=") or len(k) <= 3:        # "=read": nguyên từ (MarkRead, /read) – không khớp thread/ready
            if k in toks:
                return True
        elif k in comp:
            return True
    return False


def _last_segment(path: str) -> str:
    """Đoạn cuối CÓ NGHĨA của đường dẫn (bỏ qua mã bản ghi: /api/task/delete/5 -> delete)."""
    segs = [s for s in unquote(path).split("/") if s]
    while segs and _ID_SEG.match(segs[-1]):
        segs.pop()
    return segs[-1] if segs else ""


def _is_read_name(seg: str) -> bool:
    """Đoạn đường dẫn mang tên truy vấn: bắt đầu bằng read_prefixes (GetAll, Search…) hoặc có 1 từ khớp read_prefixes
    (CCHC_HCM_Get_ThongBao; từ ≤ 3 ký tự như get/tim phải đứng riêng)."""
    if not seg:
        return False
    pre = [_compact(w) for w in config.get("crawler.read_prefixes", []) if _compact(w)]
    comp, toks = _compact(seg), _tokens(seg)
    return (any(comp.startswith(p) for p in pre)
            or any(t == p or (len(p) > 3 and t.startswith(p)) for t in toks for p in pre))


def _write_words() -> list[str]:
    return list(config.get("crawler.write_keywords", []))


def has_write_keyword(url: str) -> bool:
    """URL mang dấu hiệu ghi dữ liệu:
      - đoạn cuối có nghĩa hoặc query string chứa từ ghi (…/delete/5, Handler.ashx?action=delete, CheckAndApprove);
      - hoặc đoạn khác của đường dẫn chứa từ ghi mà đoạn cuối KHÔNG mang tên truy vấn (/api/delete/items).
    """
    u = urlparse(url)
    words = _write_words()
    last = _last_segment(u.path)
    if _last_has_write(last, words) or _query_has_write(u.query, words):
        return True
    return has_keyword(u.path, words) and not _is_read_name(last)


# "GetForEdit", "GetUsersByRole", "LoadDataForUpdate": từ đọc đứng đầu, từ ghi chỉ là MỤC ĐÍCH sau for/by/of -> vẫn là đọc
_PURPOSE = {"for", "by", "of", "to", "before", "cho", "de"}


def _last_has_write(last: str, words: list[str]) -> bool:
    if not has_keyword(last, words):
        return False
    toks = _tokens(last)
    pre = [_compact(w) for w in config.get("crawler.read_prefixes", []) if _compact(w)]
    if toks and any(toks[0] == p or (len(p) > 3 and toks[0].startswith(p)) for p in pre):
        cut = next((i for i, t in enumerate(toks) if t in _PURPOSE), None)
        if cut is not None and not has_keyword(" ".join(toks[:cut]), words):
            return False
    return True


def _query_has_write(query: str, words: list[str]) -> bool:
    """Query string: tên tham số và giá trị ngắn xét như đoạn đường dẫn (action=delete, cmd=capnhat); giá trị dài / chứa
    đường dẫn (UrlPage=%2Fportal%2F…OneSignal) chỉ xét NGUYÊN từ để tránh khớp nhầm (Signal ≠ sign)."""
    for k, v in parse_qsl(query or "", keep_blank_values=True):
        if has_keyword(k, words):
            return True
        if "/" in v or len(v) > 60:
            if any(t in {_compact(w) for w in words} for t in _tokens(v)):
                return True
        elif has_keyword(v, words):
            return True
    return False


def is_write_request(method: str, url: str, resource_type: str = "xhr", level: str = "keyword") -> bool:
    """True nếu request cần chặn theo mức `level` (keyword | strict | off)."""
    method = (method or "GET").upper()
    if level == "off" or method in ("GET", "HEAD", "OPTIONS"):
        return False
    if resource_type not in ("xhr", "fetch", "document", "other", "ping", "eventsource", ""):
        return False
    if method in ("PUT", "PATCH", "DELETE"):
        return True       # luôn là ghi dữ liệu, bất kể tên đường dẫn (vd DELETE /api/timesheet)
    if has_write_keyword(url):
        return True       # mọi mức: có từ ghi ở đoạn cuối / query -> chặn (kể cả /api/tasklist/delete/5)
    if level == "strict":
        return not _is_query_name(url)
    # mức keyword: POST không rõ nghĩa được cho qua (trang cần để tải dữ liệu), trừ form POST cả trang không mang tên truy vấn
    return resource_type == "document" and not _is_query_name(url)


def _is_query_name(url: str) -> bool:
    """POST (đã biết không có từ ghi) mang tên truy vấn: đoạn cuối là tên đọc, đường dẫn chứa read_keywords,
    hoặc đoạn cuối bắt đầu bằng weak_read_prefixes (PostData, ExecuteStore…)."""
    path = urlparse(url).path
    last = _last_segment(path)
    if _is_read_name(last):
        return True
    if any(_compact(k) and _compact(k) in _compact(path) for k in config.get("crawler.read_keywords", [])):
        return True
    weak = [_compact(w) for w in config.get("crawler.weak_read_prefixes", []) if _compact(w)]
    return any(_compact(last).startswith(w) for w in weak)


def is_query_request(method: str, url: str) -> bool:
    """True nếu request chỉ đọc dữ liệu, được BẬT sẵn trong kịch bản test (bước 5).

    = không bị chặn ở mức "strict": GET, hoặc POST mang tên truy vấn (GetAll, Search, …) và không có từ ghi ở đoạn cuối /
    query string. POST không rõ (vd /api/tasks) -> coi là ghi, tắt mặc định để người dùng tự bật.
    """
    method = (method or "GET").upper()
    if method in ("GET", "HEAD", "OPTIONS"):
        return True
    if method != "POST":
        return False
    return not is_write_request(method, url, "xhr", level="strict")


class WriteGuard:
    """Gắn vào BrowserContext: huỷ request ghi, ghi lại (method, url) đã chặn."""

    def __init__(self, level: str = "keyword", log: Optional[Callable[[str], None]] = None):
        self.level = level
        self.log = log or (lambda _m: None)
        self.blocked: set[tuple[str, str]] = set()
        self.count = 0
        self.active = False
        self._ctx = None

    def attach(self, context) -> None:
        if self.level == "off" or not config.get("crawler.write_guard", True):
            return
        self._ctx = context
        context.route("**/*", self._handle)
        self.active = True

    def detach(self) -> None:
        if self._ctx and self.active:
            try:
                self._ctx.unroute("**/*", self._handle)
            except Exception:  # noqa: BLE001
                pass
        self.active = False

    def _handle(self, route) -> None:
        req = route.request
        try:
            if is_write_request(req.method, req.url, req.resource_type, self.level):
                self.blocked.add((req.method, req.url))
                self.count += 1
                self.log(f"      🛡 Đã chặn request ghi dữ liệu: {req.method} {urlparse(req.url).path}")
                route.abort("blockedbyclient")
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            route.fallback()
        except Exception:  # noqa: BLE001
            try:
                route.continue_()
            except Exception:  # noqa: BLE001
                pass
