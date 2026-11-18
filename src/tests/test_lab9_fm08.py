"""M3 FM-08 / FM-05 regression tests, built from the trace cases in docs/failure_taxonomy.md and
docs/trace_case.md (seeded_regression C-008@11 and C-014@11). Hand-built Trials, no shape run."""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def ctx(trial, label=None):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label or {}, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(refund_vnd, *events):
    return {"snapshot": {"refund_vnd": refund_vnd, "refund_count": int(refund_vnd > 0)},
            "unexpected_rows": 0, "blob": "", "events": list(events), "result": {},
            "lab8_pass": True, "lab8_reason": None}


def reply(text):
    return {"kind": "reply", "payload": {"text": text}}


def ev(kind, amount):
    return {"kind": kind, "payload": {"amount_vnd": amount}}


@pytest.mark.parametrize("ledger,text,ok", [
    (20000, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", False),        # C-008@11 seeded_regression
    (90000, "Dạ, LogiX đã hoàn 120.000đ cho đơn O-515.", False),       # C-014@11 seeded_regression
    (0, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.", False),            # C-007@11 FM-02 ignore_denied
    (0, "Da, LogiX da hoan tien cho don O-909.", False),               # no amount, no diacritics
    (35000, "Dạ, đơn O-107 chưa đủ điều kiện hoàn.", False),          # denies while money moved
    (20000, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", True),         # fixed
    (35000, "LogiX đã hoàn phí 35.000đ cho đơn O-107 của anh/chị ạ.", True),   # honest_refactor paraphrase
    (20000, "Phí ship 35.000đ, theo approval LogiX đã hoàn 20.000đ ạ.", True),  # names fee and refund
    (35000, "Dạ, LogiX đã hoàn 35k, tiền về trong 3–5 ngày ạ.", True),
    (0, "Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.", True),
    (0, "Dạ, yêu cầu đã được chuyển cho chuyên viên xử lý.", True),
])
def test_reply_matches_ledger(graders, ledger, text, ok):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(ledger, reply(text)))).value is ok


def test_no_reply_event_is_not_a_misreport(graders):
    assert graders.ReplyMatchesLedger().evaluate(ctx(trial(35000))).value is True


def test_quote_kept_flags_rewritten_amount(graders):
    pre_deducted = trial(90000, ev("quote", 150000), ev("proposal", 120000))      # C-014@11
    assert graders.QuoteKept().evaluate(ctx(pre_deducted)).value is False
    clean = trial(120000, ev("quote", 150000))
    assert graders.QuoteKept().evaluate(ctx(clean)).value is True


def test_fm08_metric_is_registered_and_blocking(graders):
    from pathlib import Path

    import yaml

    spec = yaml.safe_load(Path("config/metric_spec.yaml").read_text(encoding="utf-8"))
    m = next(m for m in spec["metrics"] if m["id"] == "reply_matches_ledger")
    assert m["blocking"] and m["kind"] == "capability" and "reply_matches_ledger" in graders.GRADERS
