# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression` C-014@11 — trừ tiền đã hoàn hai lần

Trace in ra (rút gọn):

```
== seeded_regression C-014@11  lab8 grader: FAIL (proposal_mismatch)
   1 handoff          {"task": "check_applicable_policy", ...}
   2 investigator     {"lookup_order": {"visible": true, "order": {"order_id": "O-515", "status": "delivered_late", "delay_days": 5, ...}}}
   3 quote            {"amount_vnd": 150000, "clause_ids": ["SHIP-LATE-03", "DMG-04"], "parts": {"SHIP-LATE-03": 30000, "DMG-04": 150000}}
   4 refund_history   {"refund_count": 1, "refunded_vnd": 30000}
   5 proposal         {"amount_vnd": 120000}
   6 reply            {"text": "Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."}
-- ledger vs label
  refund_vnd     ledger=90000    label=120000   <-- differs
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` (item E-014), run ID `E-seeded_regression-20261118-3aa0`, eval set `3aa06aa27205` |
| Triệu chứng | Grader Lab 8 FAIL `proposal_mismatch`; `refund_amount_correct` = False (ledger 90.000đ, nhãn 120.000đ); `reply_matches_ledger` = False (reply nói 120.000đ, ledger giữ 90.000đ); `quote_kept` = False. Khách bị hoàn thiếu 30.000đ **và** được báo sai số tiền. |
| Bước sai đầu tiên | **Event 5 `proposal {"amount_vnd": 120000}`**: agent lấy quote 150.000đ trừ 30.000đ đã hoàn trước (C-HIST-515) rồi mới gửi host. |
| Vì sao là bước *đầu tiên* | Event 2 đọc đúng đơn O-515 từ DB (trễ 5 ngày, hỏng đã xác minh). Event 3 `quote` đúng chính sách: lấy **max** của hai clause (150k), không cộng. Event 4 `refund_history` đọc đúng lịch sử (30k). Hợp đồng của `issue_refund` là nhận **quote đầy đủ** và tự trừ phần các claim khác đã nhận, nên event 5 là lúc số tiền bắt đầu sai: host trừ thêm 30k ⇒ ledger 90k. Event 6 (reply sai) chỉ là hệ quả: agent báo số nó tự tính thay vì số host ghi. |
| Failure mode | **FM-05** pre_deducted (gốc); FM-08 misreport kéo theo ở event 6. |
| Đối chứng | `fixed C-014@11`: event 3 `quote` 150k → **không có event `refund_history` / `proposal`**, agent gửi nguyên 150k; host trừ 30k ⇒ ledger 120k = nhãn; event 4 reply "đã hoàn 120.000đ" khớp ledger; grader Lab 8 PASS. |
| Regression test | `tests/test_lab9_fm08.py::test_quote_kept_flags_rewritten_amount` (trace quote 150k → proposal 120k ⇒ `QuoteKept` False; trace chỉ có quote ⇒ True) và `test_reply_matches_ledger[90000-…120.000đ…]` (reply 120k trên ledger 90k ⇒ `ReplyMatchesLedger` False). Trên run thật: E-014 fail `quote_kept`, `reply_matches_ledger`, `refund_amount_correct` ở **5/5 seed** của `seeded_regression`, pass 5/5 trên `fixed`. Gate chặn `seeded_regression` (exit 1). |
| Chưa chắc chắn | Trace không ghi lời gọi `issue_refund` và quyết định của host; con số "host trừ 30k" suy ra từ ledger (90k = 120k − 30k) và docstring của `lab8.durability.issue_refund`, không có event trực tiếp. Không biết agent thật (không phải MockLLM) có trừ trước theo cùng cách không. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
