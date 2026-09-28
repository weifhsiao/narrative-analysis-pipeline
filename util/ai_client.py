import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from google import genai
from google.genai import types, errors


@dataclass
class Attachment:
    data: bytes
    mime_type: str = "text/plain"
    filename: str | None = None  # 只為可讀性/debug 用


@dataclass
class TokenUsage:
    """provider 中立的 AI 用量。各家 usage 的語意不同(輸出含不含思考、輸入含不含快取),
    由各 AIClient 子類別換算成這套,pipeline / DB 不碰 provider 原始參數名。

    input_tokens   :輸入總量(含快取)
    output_tokens  :輸出總量(含思考),對齊計費口徑
    thinking_tokens:output 中思考占多少;None = provider 沒回報(≠ 0)
    model          :API 實際回報的模型版本,不是設定值
    """

    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None


@dataclass
class GenerateResult:
    text: str
    usage: TokenUsage


class AIBlockedError(Exception):
    """The model accepted the request (HTTP 200) but returned no usable text,
    e.g. the input or output was blocked by a safety/content filter, or the
    generation stopped early (MAX_TOKENS). This is provider-neutral on purpose:
    the message carries the raw reason as a plain string, and callers only need
    to catch this type -- they never touch any provider-specific error class.
    Blocked requests are usually still billed for input, so usage rides along.
    """

    def __init__(self, message: str, usage: TokenUsage | None = None):
        super().__init__(message)
        self.usage = usage


class AIClient(ABC):

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: str,
        attachments: list[Attachment] | None = None,
    ) -> GenerateResult:
        pass


class GeminiClient(AIClient):

    def __init__(self):
        super().__init__()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.client = genai.Client(api_key=gemini_api_key)

    def generate(
        self,
        prompt: str,
        system_instruction: str,
        attachments: list[Attachment] | None = None,
    ) -> GenerateResult:
        # 未來可以把think level放進.env，目前覺得預設就夠用
        config = (
            types.GenerateContentConfig(system_instruction=system_instruction)
            if system_instruction
            else None
        )

        if attachments:
            # 夾檔模式:檔案 part 放前面、指令文字放後面(長文件在前、query 在後)
            parts = [
                types.Part.from_bytes(data=a.data, mime_type=a.mime_type)
                for a in attachments
            ]
            parts.append(types.Part.from_text(text=prompt))
            contents = parts
        else:
            contents = prompt

        try:
            response = self.client.models.generate_content(
                model=self.model,
                config=config,
                contents=contents,
            )
        except errors.APIError as e:
            # 情境A：4xx/5xx。code(HTTP狀態碼)/status/message 記進 log 後照原樣往上拋,
            # 讓 pipeline 端維持既有的 ERROR 記錄。
            print(
                f"[gemini][APIError] code={e.code} status={e.status} message={e.message}"
            )
            raise

        # Always log a one-line diagnostic, even on success, so finish_reason /
        # token usage is visible in the console for every call.
        diagnostics = _format_response_diagnostics(response)
        print(f"[gemini] {diagnostics}")

        # HTTP 200 but no text (safety block / MAX_TOKENS / etc). response.text
        # is None here; if we returned it, the downstream write_response(None)
        # would raise a misleading TypeError that hides the real reason. Instead
        # we raise a neutral AIBlockedError carrying the full diagnostic string,
        # so the caller records the true reason (e.g. block_reason).
        usage = _to_token_usage(response, self.model)
        if not response.text:
            print(f"[gemini][EMPTY] {diagnostics}")
            raise AIBlockedError(diagnostics, usage)

        return GenerateResult(text=response.text, usage=usage)


def _to_token_usage(response, fallback_model: str) -> TokenUsage:
    """Gemini usage_metadata → 中立語意。

    Gemini:prompt_token_count 已含快取;candidates_token_count 不含思考、
    thoughts_token_count 另列(沒思考時為 None)。所以 output = candidates + thoughts。
    有回報 usage 時思考缺值視為 0;整包 usage 都沒有才是 None。
    """
    model = response.model_version or fallback_model
    usage = response.usage_metadata
    if usage is None:
        return TokenUsage(model=model)

    candidates = usage.candidates_token_count
    thoughts = usage.thoughts_token_count
    if candidates is None and thoughts is None:
        output, thinking = None, None
    else:
        output, thinking = (candidates or 0) + (thoughts or 0), thoughts or 0

    return TokenUsage(
        model=model,
        input_tokens=usage.prompt_token_count,
        output_tokens=output,
        thinking_tokens=thinking,
    )


def _format_response_diagnostics(response) -> str:
    """Build a single-line, human-readable diagnostic string from a Gemini
    response. Pure function: it only reads fields and formats a string -- no
    printing, no DB, no side effects.

    This is the single source of truth for "what a response's diagnostic looks
    like". Every consumer (the success log, the empty-response warning, and the
    AIBlockedError message that ends up in the DB) uses this one string, so they
    can never drift apart. It is also where provider-specific enums are
    flattened to plain strings (see get_reason below), which keeps Google's
    types from leaking out to the rest of the app.
    """

    def flatten(value):
        # BlockedReason.PROHIBITED_CONTENT -> "PROHIBITED_CONTENT".
        # For plain values (None, str) this just returns the value unchanged.
        return getattr(value, "name", value)

    candidate = (response.candidates or [None])[0]
    finish_reason = flatten(getattr(candidate, "finish_reason", None))
    finish_message = getattr(candidate, "finish_message", None)
    safety_ratings = getattr(candidate, "safety_ratings", None)

    feedback = response.prompt_feedback
    block_reason = flatten(getattr(feedback, "block_reason", None))
    block_reason_message = getattr(feedback, "block_reason_message", None)

    usage = response.usage_metadata
    tokens = (
        f"{getattr(usage, 'prompt_token_count', None)}/"
        f"{getattr(usage, 'candidates_token_count', None)}/"
        f"{getattr(usage, 'thoughts_token_count', None)}/"
        f"{getattr(usage, 'total_token_count', None)}"
    )

    return (
        f"model_version={response.model_version} "
        f"response_id={response.response_id} "
        f"finish_reason={finish_reason} finish_message={finish_message} "
        f"block_reason={block_reason} block_reason_message={block_reason_message} "
        f"safety_ratings={safety_ratings} "
        f"tokens(prompt/candidates/thoughts/total)={tokens} "
        f"has_text={bool(response.text)}"
    )


def get_client() -> AIClient:
    provider = os.getenv("AI_PROVIDER", "gemini")

    if provider == "gemini":
        return GeminiClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")
