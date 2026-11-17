# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | ĐẠT (0.757 ≥ 0.6, 0.857 ≥ 0.8, 0.800 ≥ 0.7) | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | KHÔNG ĐẠT (κ=0.375 < 0.6, R=0.300 < 0.7) | loại |

## ≥5 case audit thủ công (judge_tone)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người đúng | Reply: *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* — Xưng hô suồng sã ("anh - em", "nha"), không chuẩn mực CSKH B2C của LogiX. Cần sửa rubric: cấm xưng hô thân mật quá mức. |
| 2 | H-017 | PASS | FAIL | Người đúng | Reply: *"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."* — Dùng "bạn ơi", "nha" thiếu trang trọng. Rubric judge cần định nghĩa rõ danh sách khẩu ngữ không được dùng. |
| 3 | H-029 | PASS | FAIL | Người đúng | Reply: *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* — Giọng điệu cộc lốc, thiếu tôn trọng khách hàng ("không cần nhắn thêm"). Rubric cần cấm hành vi xua đuổi/ngắt lời khách. |
| 4 | H-042 | FAIL | PASS | Người đúng | Reply: *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* — Câu trả lời lịch sự, rõ ràng, có thời gian ước tính. Judge bị false positive do quá cứng nhắc. Cần nới rubric cho phép giải thích thời gian xử lý. |
| 5 | H-051 | FAIL | PASS | Người đúng | Reply: *"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."* — Dùng từ "refund" thay vì "hoàn tiền", judge phạt nặng dù ý tứ chuẩn xác lịch sự. Rubric cần cho phép các thuật ngữ quen thuộc trong ngữ cảnh TMĐT. |

## Kết luận
- **Tiêu chí bị loại:** `helpful` bị loại vì recall quá thấp (R = 0.300) và hệ số thỏa thuận Cohen's Kappa chỉ đạt κ = 0.375 (dưới ngưỡng 0.6). Ma trận nhầm lẫn của `helpful`: `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}`. Judge bỏ lọt tới 21 lỗi (FN = 21 trên tổng số 30 ca lỗi mà con người gắn nhãn). Dùng judge này làm gate sẽ khiến hàng loạt câu trả lời vô bổ hoặc không giải quyết được vấn đề lọt qua cổng kiểm thử.
- **Tiêu chí được chấp nhận:** `tone_ok` đạt chuẩn với κ = 0.757, P = 0.857, R = 0.800, ma trận nhầm lẫn `{'tp': 24, 'fp': 4, 'fn': 6, 'tn': 66}`. Tỉ lệ lỗi quan sát 28% sau khi hiệu chỉnh Rogan-Gladen cho ra tỉ lệ lỗi thực tế xấp xỉ 30%.
- **Rủi ro còn lại:** Judge chỉ được kiểm trên dữ liệu replay đã công khai (100 mẫu); cần bổ sung nhãn người trên tập held-out mới để kiểm chứng tính bền vững trước distribution drift.
