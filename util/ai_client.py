import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from google import genai
from google.genai import types


@dataclass
class Attachment:
    data: bytes
    mime_type: str = "text/plain"
    filename: str | None = None  # 只為可讀性/debug 用


class AIClient(ABC):

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: str,
        attachments: list[Attachment] | None = None,
    ) -> str:
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
    ) -> str:
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

        response = self.client.models.generate_content(
            model=self.model,
            config=config,
            contents=contents,
        )
        return response.text


def get_client() -> AIClient:
    provider = os.getenv("AI_PROVIDER", "gemini")

    if provider == "gemini":
        return GeminiClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")
