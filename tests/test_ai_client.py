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
