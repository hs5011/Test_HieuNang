# Kinh nghiệm review PerfTool

Skill `perftool-review` đọc file này ở Bước 0 và cập nhật ở Bước 5. Mới nhất ở cuối mỗi mục.

## Phương pháp

- [2026-10-01] Pytest pass 100 % (414 test) nhưng vẫn có 4 lỗi mức Cao. **Vì sao:** test không chạy
  luồng thật (crawl demo, k6/JMeter thật) và không import `samples/` – luôn kiểm thử động, không tin số test.
- [2026-10-01] Server bẫy (GET có tác dụng phụ, `/api/_stats` đếm request ghi) là cách hiệu quả nhất để
  tìm lỗ hổng của guard chặn ghi. **Vì sao:** đọc mã không thấy được, chạy thật phát hiện ngay 5 request lọt.
- [2026-10-01] Kiểm tra với Python thấp nhất README cam kết (3.10). **Vì sao:** `demo_server.py` dùng
  f-string chỉ hợp lệ từ 3.12, máy dev chạy bản mới nên không ai thấy.
- [2026-10-01] Luôn thử các "đường tắt" của UI: ô để trống (NaN), bỏ trống mật khẩu khi tự đăng nhập,
  mã trùng, tài khoản kiểu `user01/user01`. **Vì sao:** 3 lỗi Cao/TB đến từ các đầu vào này.
- [2026-10-01] Với công cụ đo hiệu năng, hỏi "báo cáo có thể xanh khi hệ thống đang lỗi không?"
  (mất phiên, 200 trang lỗi, không correlation). **Vì sao:** đây là rủi ro lớn nhất, không lộ ra qua crash.

## Vùng hay có lỗi

- [2026-10-01] `crawler/web_crawler.py` (bắt login, thay placeholder), `crawler/guard.py`,
  `ui/steps/s05_confirm.py`, `runner/` (mã thoát, PID), `results/` (cache, parser JTL).

## Góp ý của người dùng

- [2026-10-02] Báo cáo viết bằng tiếng Việt; người dùng tự quyết định khi nào commit/push báo cáo.
