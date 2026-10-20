"""Names of private individuals never reach the API."""

import json
from types import SimpleNamespace

from finance_automation.classifier import batch_prompt, classify_descriptions
from finance_automation.llm import LLM
from finance_automation.privacy import PERSON, is_person


def test_person_detection():
    assert is_person("PEDRO H LIMA", "PIX ENVIADO")
    assert is_person("CARLA M SOUZA", "PIX RECEBIDO")
    assert not is_person("JOSE ELETRICISTA REPAROS", "PIX ENVIADO")  # a trade word marks a business
    assert not is_person("ACME SERVICOS DIGITAIS LTDA", "PIX RECEBIDO")
    assert not is_person("CHAVEIRO SEGURO 24H", "PIX ENVIADO")
    assert not is_person("PEDRO H LIMA", "COMPRA NO DEBITO")  # only transfers are masked
    assert not is_person("NETFLIX", "PIX ENVIADO")


class Spy:
    """Fake client that records every prompt and answers <PERSON> for masked lines."""

    def __init__(self):
        self.prompts = []
        self.messages = self

    def create(self, **kw):
        prompt = kw["system"] + kw["messages"][0]["content"]
        self.prompts.append(prompt)
        lines = [ln for ln in kw["messages"][0]["content"].splitlines() if ln[:1].isdigit()]
        items = [
            {"index": i, "category": "Other", "confidence": 0.5, "reason": "person", "suggested_keyword": PERSON}
            if ln.endswith(PERSON)
            else {"index": i, "category": "Shopping", "confidence": 0.9, "reason": "shop", "suggested_keyword": "LOJA"}
            for i, ln in enumerate(lines)
        ]
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps({"items": items}))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=10),
        )


def test_names_are_masked_before_the_api(tmp_path):
    items = [
        {"description": "PEDRO H LIMA", "history": "PIX ENVIADO", "direction": "out"},
        {"description": "LOJA DO BAIRRO", "history": "COMPRA NO DEBITO", "direction": "out"},
    ]
    assert "PEDRO" not in batch_prompt(items)
    llm = LLM(mode="demo", recordings=tmp_path / "rec", log_dir=tmp_path / "logs")
    llm.mode, llm._client = "live", Spy()
    answers, stop = classify_descriptions(llm, items)
    assert stop is None and len(llm._client.prompts) == 1  # no retry: <PERSON> is an accepted keyword
    assert "PEDRO" not in llm._client.prompts[0] and "LIMA" not in llm._client.prompts[0]
    assert answers["PEDRO H LIMA"]["suggested_keyword"] == "PEDRO H LIMA"  # the local rule keeps the real text
    saved = " ".join(p.read_text(encoding="utf-8") for p in (tmp_path / "rec").glob("*.json"))
    assert "PEDRO" not in saved  # the recorded request does not hold the name either
