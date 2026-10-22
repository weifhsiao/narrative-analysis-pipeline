"""Gemini usage_metadata → provider 中立的 TokenUsage。"""
from types import SimpleNamespace

from util.ai_client import TokenUsage, _to_token_usage


def _response(usage, model_version="gemini-x-001"):
    return SimpleNamespace(model_version=model_version, usage_metadata=usage)


def _usage(prompt=None, candidates=None, thoughts=None):
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
    )


def test_output_includes_thinking():
    usage = _to_token_usage(_response(_usage(100, 30, 10)), "cfg-model")

    assert usage == TokenUsage("gemini-x-001", input_tokens=100, output_tokens=40, thinking_tokens=10)


def test_no_thoughts_reported_means_zero_thinking():
    usage = _to_token_usage(_response(_usage(100, 30, None)), "cfg-model")

    assert (usage.output_tokens, usage.thinking_tokens) == (30, 0)


def test_missing_usage_is_all_none_but_keeps_model():
    usage = _to_token_usage(_response(None), "cfg-model")

    assert usage == TokenUsage(model="gemini-x-001")


def test_model_falls_back_to_configured_when_not_reported():
    usage = _to_token_usage(_response(_usage(1, 1), model_version=None), "cfg-model")

    assert usage.model == "cfg-model"


# ---- thinking_level:呼叫端指定才帶 ThinkingConfig,不指定維持模型預設 ----
import pytest  # noqa: E402

import util.ai_client as ai_client  # noqa: E402


class _FakeModels:
    def __init__(self):
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            text="ok", model_version="m", response_id="r", candidates=[], prompt_feedback=None,
            usage_metadata=_usage(1, 1, 0),
        )


@pytest.fixture
def gemini(monkeypatch):
    models = _FakeModels()
    monkeypatch.setattr(ai_client.genai, "Client", lambda api_key: SimpleNamespace(models=models))
    return ai_client.GeminiClient(), models


def test_model_override_else_configured(monkeypatch):
    monkeypatch.setattr(ai_client.genai, "Client", lambda api_key: SimpleNamespace(models=_FakeModels()))
    monkeypatch.setenv("GEMINI_MODEL", "pipeline-model")
    assert ai_client.GeminiClient().model == "pipeline-model"
    assert ai_client.get_client("feature-model").model == "feature-model"


def test_thinking_level_sets_thinking_config(gemini):
    client, models = gemini
    client.generate("p", "sys", thinking_level="low")
    cfg = models.kwargs["config"]
    assert cfg.system_instruction == "sys"
    assert cfg.thinking_config.thinking_level.value == "LOW"


def test_no_thinking_level_keeps_model_default(gemini):
    client, models = gemini
    client.generate("p", "sys")
    assert models.kwargs["config"].thinking_config is None
    client.generate("p", "")
    assert models.kwargs["config"] is None


def test_unknown_thinking_level_rejected(gemini):
    client, _ = gemini
    with pytest.raises(ValueError, match="thinking_level"):
        client.generate("p", "sys", thinking_level="turbo")
