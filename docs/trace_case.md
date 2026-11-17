# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (run_id: `case-seeded_regression-C-002-11`) |
| Triệu chứng | Grader `TrialPass` (lab8) fail với lý do `status resolved != denied`. Reply báo "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." trong khi ledger ghi 20.000đ nhưng nhãn yêu cầu 0đ (denied). |
| Bước sai đầu tiên | Event #3: `model_override` payload: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event #1 `handoff` phân chia task đúng. Event #2 `investigator` tra cứu DB thành công, trả về đúng `order: {"order_id": "O-202", "status": "delivered", "delay_days": 2}`. Event #3 là bước đầu tiên làm biến dạng sự thật khách quan khi lấy 5 ngày từ ticket đè lên 2 ngày của DB, khiến event #4 tính ra khoản bồi thường 20.000đ thay vì 0đ. |
| Failure mode | `FM-03` (`ticket_trust` — tin ticket hơn DB) |
| Đối chứng | Cùng claim@seed trên `fixed C-002@11`: không hề có event `model_override`. Ngay sau Event #2, Event #3 là `quote` trả về `amount_vnd: 0`, kết luận `denied` và ledger hoàn 0đ (pass hoàn toàn). |
| Regression test | `src/tests/test_lab9_graders.py` (grader `DbFactKept`) và `test_public_single_run_cases` (trong `src/tests/test_public_matrix.py`). Đã xác nhận fail trên `seeded_regression` và pass trên `fixed`. |
| Chưa chắc chắn | Trace chỉ ghi nhận payload can thiệp `{"delay_days": 5}`, không lưu rationale/prompt reasoning nội bộ giải thích vì sao model lại ưu tiên chuỗi văn bản không xác thực trong ticket hơn DB facts. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
