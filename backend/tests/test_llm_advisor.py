"""Fix 1: LLM prompt scaling and empty-message guard. Groq is replaced by a fake."""
from types import SimpleNamespace

import groq
import httpx
import pytest

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


# ---------- Fix 8: advice, model cascade and specific Groq errors ----------

_REQ = httpx.Request("POST", "https://api.groq.invalid")


def _status_error(cls, code):
    return cls("err", response=httpx.Response(code, request=_REQ), body=None)


class ScriptedGroq:
    """Raises or answers per call, in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.models = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.models.append(kwargs["model"])
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if kwargs.get("stream"):
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=outcome))])])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))])


@pytest.fixture(autouse=True)
def clear_advice_cache():
    llm_advisor._advice_cache.clear()


def test_advice_without_key_is_fallback():
    assert llm_advisor.generate_strategic_advice({"grit_score": 50}) == llm_advisor.FALLBACK_ADVICE


def test_advice_parsed_to_three_bullets_and_cached(monkeypatch):
    fake = ScriptedGroq("- one\n- two\n\n- three\n- four")
    monkeypatch.setattr(llm_advisor, "client", fake)
    metrics = {"grit_score": 42.0, "runway_decay_estimate": 9.1}
    assert llm_advisor.generate_strategic_advice(metrics) == ["one", "two", "three"]
    assert llm_advisor.generate_strategic_advice(metrics) == ["one", "two", "three"]
    assert len(fake.models) == 1          # second call served from cache


def test_advice_api_error_falls_back(monkeypatch):
    monkeypatch.setattr(llm_advisor, "client", ScriptedGroq(groq.APIConnectionError(request=_REQ)))
    assert llm_advisor.generate_strategic_advice({"grit_score": 1}) == llm_advisor.FALLBACK_ADVICE


def test_chat_rate_limit_moves_to_next_model(monkeypatch):
    fake = ScriptedGroq(_status_error(groq.RateLimitError, 429), "answer")
    monkeypatch.setattr(llm_advisor, "client", fake)
    assert "".join(llm_advisor.chat_with_advisor(HELLO, METRICS)) == "answer"
    assert fake.models == llm_advisor.MODEL_CASCADE


def test_chat_all_models_at_capacity(monkeypatch):
    fake = ScriptedGroq(_status_error(groq.RateLimitError, 429), _status_error(groq.NotFoundError, 404))
    monkeypatch.setattr(llm_advisor, "client", fake)
    out = "".join(llm_advisor.chat_with_advisor(HELLO, METRICS))
    assert "at capacity" in out and "NotFoundError" in out


def test_chat_other_api_error_stops_with_clear_message(monkeypatch):
    fake = ScriptedGroq(_status_error(groq.AuthenticationError, 401), "never")
    monkeypatch.setattr(llm_advisor, "client", fake)
    out = "".join(llm_advisor.chat_with_advisor(HELLO, METRICS))
    assert "AuthenticationError" in out and fake.models == [llm_advisor.MODEL_CASCADE[0]]


def test_chat_history_roles_mapped_for_groq(monkeypatch):
    fake = FakeGroq()
    monkeypatch.setattr(llm_advisor, "client", fake)
    history = [{"role": "model", "content": "hi"}, {"role": "user", "content": "q"}]
    list(llm_advisor.chat_with_advisor(history, METRICS))
    assert [m["role"] for m in fake.calls[0]["messages"]] == ["system", "assistant", "user"]
