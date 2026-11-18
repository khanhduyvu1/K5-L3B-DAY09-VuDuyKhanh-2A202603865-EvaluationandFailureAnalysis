# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY: verdict của judge lưu sẵn trong CSV, không gọi model). Lớp dương = `FAIL` (việc của judge là tìm lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **dùng**, chỉ cho giọng văn, không chặn release một mình |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** κ và R (exit 1) | **loại** |

Ma trận nhầm lẫn (FAIL = dương):

| | tp | fp | fn | tn | Tỉ lệ FAIL judge thấy | Sau Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

## ≥5 case audit thủ công

### tone_ok (cả 10 bất đồng)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric thêm: **xưng hô phải là "LogiX" / "anh/chị"; "em", "bạn", "nha", "nhé" ⇒ FAIL**, kèm 2 ví dụ âm. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…rồi nha." | PASS | FAIL | Người | Cùng lỗi xưng hô ("bạn ơi"). Judge nhầm "thân thiện" với "đúng mực". Gộp vào quy tắc #1. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ bắt từ lịch sự ở đầu câu ("Dạ, vui lòng"). Rubric thêm: **câu mệnh lệnh / chặn khách liên hệ ⇒ FAIL dù mở đầu lịch sự**; chấm cả câu, không chấm từ khóa. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt "thiếu xin lỗi". Rubric ghi rõ: **ngắn, đủ ý, có kính ngữ = PASS; không bắt buộc xin lỗi** (xin lỗi thừa là lỗi của tiêu chí helpful, xem dưới). |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | Style guide CS LogiX cho phép "refund". Rubric thêm danh sách từ tiếng Anh được phép (refund, ship, voucher). |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Giọng văn không sai; lỗi là **hứa ngoài kết quả hệ thống**. Không đưa vào rubric tone: chuyển sang grader code (reply không được nhắc số tiền / cam kết không có trong ledger — `ReplyMatchesLedger`). Ghi nhận: nhãn người trộn hai tiêu chí. |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric thêm: **emoji trong phản hồi khiếu nại ⇒ FAIL**. Có thể bắt bằng regex trước khi gọi judge (rẻ hơn). |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn… ạ." | FAIL | PASS | **Judge** | Ghi chú người chấm: nhãn người sai (đọc nhầm ticket). **Sửa nhãn thành FAIL.** Sau khi sửa: tp 25, fp 3, P = 0.893, R = 0.806, κ = 0.784. Không sửa trong CSV công khai (replay giữ nguyên để so được); ghi ở đây và vào tập held-out mới. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (ranh giới) | Lặp "Dạ" là lỗi gõ, không phải giọng văn sai. Rubric: **lỗi gõ nhẹ không đổi nghĩa ⇒ PASS**. Case ranh giới, để 2 người chấm lại. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ… xin loi…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric thêm: **tiếng Việt không dấu ⇒ FAIL**. |

Mẫu hình: 6/10 lỗi của judge là **bỏ sót** (FN: suồng sã, mệnh lệnh, emoji, mất dấu), 3/10 là **bắt nhầm** (FP: thiếu xin lỗi, từ tiếng Anh, lỗi gõ), 1/10 là nhãn người sai. Judge dễ dãi với câu có từ lịch sự và quá khắt khe với câu ngắn.

### helpful (3 mẫu hình, 21/21 bất đồng đều là judge bỏ sót)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | **18/21** case bỏ sót là "sai tiền". Judge chỉ đọc reply, **không thấy ledger** ⇒ về cấu trúc không thể bắt lỗi này. Không sửa được bằng rubric: tách ra grader code `ReplyMatchesLedger` (FM-08). |
| 12 | HL-016 / HL-043 / HL-090 … (xin lỗi dài, lặp 2 lần, kèm số tiền sai) | PASS | FAIL | Người | **Thiên lệch độ dài:** cả 13 reply dài >120 ký tự đều bị người chấm FAIL, judge PASS cả 13. Rubric thêm: **xin lỗi lặp lại / nội dung đệm không thêm thông tin ⇒ FAIL**; nhưng vẫn không cứu được vì lỗi chính là sai tiền. |
| 13 | HL-047 / HL-091 / HL-097 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Sai xưng hô + không nói kết quả cụ thể. Đây là việc của tiêu chí tone (quy tắc #1), không phải helpful. |

## Kết luận
- **tone_ok: dùng được.** κ 0.757, P 0.857, R 0.80 qua FLOORS. Dùng để theo dõi giọng văn, không làm metric chặn release một mình. Tỉ lệ lỗi judge quan sát 0.28 được hiệu chỉnh Rogan-Gladen thành 0.30 (sens 0.80, spec 66/70 = 0.943), khớp tỉ lệ người chấm (30/100).
- **helpful: loại, không được làm gate.** Precision 1.0 dễ gây ảo tưởng (judge nói FAIL thì đúng là FAIL), nhưng recall 0.30 nghĩa là **bỏ sót 70% reply hỏng**, κ 0.375 < 0.6. Ma trận: fn = 21, trong đó 18 là "sai tiền". Judge không thấy ledger nên không bao giờ phát hiện được lỗi tiền. Một gate dựa trên nó sẽ cho merge đúng loại lỗi đắt nhất. Quy tắc: **tiền luôn chấm bằng code**.
  - Nếu bỏ 18 dòng "sai tiền" (giao cho `ReplyMatchesLedger`), phần còn lại (n=82) cho P 1.0, R 0.75, κ 0.837. Như vậy, **tách tiêu chí** thành "helpful về hình thức" (judge) + "đúng số tiền" (code) mới có thể dùng được, sau khi calibrate lại trên nhãn mới.
  - Rogan-Gladen cho helpful (0.09 → 0.30) chỉ đúng vì tính trên chính tập dùng để đo sens/spec; với judge không qua FLOORS, con số hiệu chỉnh không đáng tin ngoài tập này.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (n = 100 mỗi tiêu chí, CI của κ còn rộng). Cần nhãn người mới (held-out, ≥2 người chấm, đo κ giữa người với người) trước khi tin judge trên dữ liệu thật. Case H-081 cho thấy chính nhãn người cũng có lỗi.
