"""Fix 1: LLM prompt scaling and empty-message guard. Groq is replaced by a fake."""
from types import SimpleNamespace

import llm_advisor


class FakeGroq:
    """Minimal stand-in for groq.Groq: records calls, streams one chunk."""

    def __init__(self, reply="ok"):
        self.calls = []
        self.reply = reply
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        delta = SimpleNamespace(content=self.reply)
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])


METRICS = {"grit_score": 40.0, "runway_decay_estimate": 38.2, "baseline": {"runway_months": 2.5}}
HELLO = [{"role": "user", "content": "hi"}]


def system_prompt(fake):
    return fake.calls[0]["messages"][0]["content"]


def test_estimate_not_scaled_again(monkeypatch):
    # runway_decay_estimate is already 0-100: 38.2 must appear as 38.2%, not 3820%
    fake = FakeGroq()
    monkeypatch.setattr(llm_advisor, "client", fake)
    out = "".join(llm_advisor.chat_with_advisor(HELLO, METRICS))
    assert out == "ok"
    assert "Runway-Decay Estimate (heuristic, not a fitted survival model): 38.2%" in system_prompt(fake)
    assert "3820" not in system_prompt(fake)


def test_finite_runway_in_prompt(monkeypatch):
    fake = FakeGroq()
    monkeypatch.setattr(llm_advisor, "client", fake)
    list(llm_advisor.chat_with_advisor(HELLO, METRICS))
    assert "Cash Runway: 2.5 months" in system_prompt(fake)


def test_no_burn_runway_is_readable_in_prompt(monkeypatch):
    # runway None must not leak into the prompt as "None months"
    fake = FakeGroq()
    monkeypatch.setattr(llm_advisor, "client", fake)
    metrics = {**METRICS, "baseline": {"runway_months": None}}
    list(llm_advisor.chat_with_advisor(HELLO, metrics))
    assert "None" not in system_prompt(fake)
    assert "No cash burn" in system_prompt(fake)


def test_empty_messages_does_not_raise_or_call_llm(monkeypatch):
    # Previously messages[-1] raised IndexError
    fake = FakeGroq()
    monkeypatch.setattr(llm_advisor, "client", fake)
    out = list(llm_advisor.chat_with_advisor([], METRICS))
    assert len(out) == 1 and "No message received" in out[0]
    assert fake.calls == []


def test_empty_messages_without_api_key():
    # conftest sets client = None; the empty-message guard still runs first
    out = list(llm_advisor.chat_with_advisor([], METRICS))
    assert "No message received" in out[0]
