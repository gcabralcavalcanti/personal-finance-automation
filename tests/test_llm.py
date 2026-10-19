"""The API wrapper and the classifier's checks, with a fake client (no network)."""

import json
from types import SimpleNamespace

import pytest

from finance_automation import llm as llm_mod
from finance_automation.classifier import answer_schema, batch_prompt, classify_descriptions, make_check
from finance_automation.llm import LLM, BudgetExceeded, NoRecording

from .conftest import fake_llm

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["x"], "properties": {"x": {"type": "number"}}}
ITEMS = [
    {"description": "CAFETERIA GRAO NOBRE", "history": "COMPRA NO DEBITO", "direction": "out"},
    {"description": "PEDRO H LIMA", "history": "PIX ENVIADO", "direction": "out"},
]


def item(i, cat="Other", conf=0.9, kw="PEDRO"):
    return {"index": i, "category": cat, "confidence": conf, "reason": "r", "suggested_keyword": kw}


def test_valid_answer_is_recorded_and_reused(tmp_path):
    m = fake_llm(tmp_path, ['{"x": 1}'])
    assert m.ask("t", "sys", "p", SCHEMA) == {"x": 1}
    assert m.ask("t", "sys", "p", SCHEMA) == {"x": 1}  # same request: no second call
    assert len(m._client.messages.calls) == 1 and m.cache_hits == 1
    kw = m._client.messages.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["thinking"] == {"type": "disabled"}
    assert kw["output_config"]["effort"] == "low"
    assert kw["output_config"]["format"]["schema"] == SCHEMA


def test_schema_failure_retries_with_feedback(tmp_path):
    m = fake_llm(tmp_path, ['{"x": "one"}', '{"x": 1}'])
    assert m.ask("t", "sys", "p", SCHEMA) == {"x": 1}
    assert "rejected by the checker" in m._client.messages.calls[1]["messages"][0]["content"]


def test_semantic_failure_raises_after_retry_and_is_not_recorded(tmp_path):
    m = fake_llm(tmp_path, ['{"x": 1}', '{"x": 1}'])
    with pytest.raises(ValueError):
        m.ask("t", "sys", "p", SCHEMA, check=lambda a: ["x must be 2"] if a["x"] != 2 else [])
    assert not list((tmp_path / "rec").glob("*.json"))


def test_call_cap_raises(tmp_path):
    m = fake_llm(tmp_path, ['{"x": 1}', '{"x": 2}'], max_calls=1)
    m.ask("a", "sys", "p1", SCHEMA)
    with pytest.raises(BudgetExceeded):
        m.ask("b", "sys", "p2", SCHEMA)


def test_demo_mode_replays_or_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_mod, "_load_key", lambda: None)
    fake_llm(tmp_path, ['{"x": 3}']).ask("t", "sys", "p", SCHEMA)
    demo = LLM(mode="auto", recordings=tmp_path / "rec", log_dir=tmp_path / "logs")
    assert demo.mode == "demo"
    assert demo.ask("t", "sys", "p", SCHEMA) == {"x": 3}
    assert demo.calls == 0
    with pytest.raises(NoRecording):
        demo.ask("t", "sys", "another prompt", SCHEMA)


def test_log_is_json_lines_with_tokens_and_cost(tmp_path):
    m = fake_llm(tmp_path, ['{"x": 1}'])
    m.ask("t", "sys", "p", SCHEMA)
    line = json.loads(m.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert line["input_tokens"] == 100 and line["source"] == "api"
    assert m.cost_usd() == pytest.approx((100 * 0.10 + 10 * 0.50) / 1e6)
    assert m.summary()["api_calls"] == 1


def test_classifier_check_catches_missing_index_bad_keyword_and_confidence():
    check = make_check(ITEMS)
    assert check({"items": [item(0, kw="GRAO NOBRE"), item(1, kw="PEDRO H")]}) == []
    probs = check({"items": [item(0, kw="STARBUCKS")]})
    assert any("missing indexes" in p for p in probs) and any("substring" in p for p in probs)
    assert any("between 0 and 1" in p for p in check({"items": [item(0, conf=1.5, kw="GRAO"), item(1)]}))
    assert any("more than once" in p for p in check({"items": [item(0, kw="GRAO"), item(0, kw="GRAO"), item(1)]}))


def test_schema_enforces_the_category_enum():
    s = answer_schema()
    assert "Groceries" in s["properties"]["items"]["items"]["properties"]["category"]["enum"]
    assert batch_prompt(ITEMS).splitlines()[1] == "0 | out | COMPRA NO DEBITO | CAFETERIA GRAO NOBRE"


def test_bad_keyword_triggers_schema_retry_then_succeeds(tmp_path):
    bad = json.dumps({"items": [item(0, kw="XYZ"), item(1, kw="PEDRO")]})
    good = json.dumps({"items": [item(0, "Restaurants & Delivery", kw="grão nobre"), item(1, kw="PEDRO")]})
    m = fake_llm(tmp_path, [bad, good])
    answers, stop = classify_descriptions(m, ITEMS)
    assert stop is None and m.calls == 2
    assert answers["CAFETERIA GRAO NOBRE"]["suggested_keyword"] == "GRAO NOBRE"  # normalized


def test_batches_and_cap_stop_cleanly(tmp_path):
    items = [{"description": f"LOJA {i:02d}", "history": "COMPRA NO DEBITO", "direction": "out"} for i in range(45)]
    m = fake_llm(tmp_path, table={}, max_calls=2)
    answers, stop = classify_descriptions(m, items, batch_size=20)
    assert m.calls == 2 and len(answers) == 40 and "cap" in stop
    assert m._client.messages.calls[0]["max_tokens"] >= 20 * 35  # sized for the batch


def test_truncated_answer_is_retried_with_a_larger_budget(tmp_path):
    m = fake_llm(tmp_path, ['{"x": 1}'])
    msgs = m._client.messages
    real_create = msgs.create

    def create(**kw):
        if not msgs.calls:  # first call: pretend the output was cut
            msgs.calls.append(kw)
            return SimpleNamespace(
                stop_reason="max_tokens", content=[], usage=SimpleNamespace(input_tokens=100, output_tokens=600)
            )
        return real_create(**kw)

    msgs.create = create
    assert m.ask("t", "sys", "p", SCHEMA, max_tokens=600) == {"x": 1}
    assert [c["max_tokens"] for c in msgs.calls] == [600, 900]
