import os
from abc import ABC, abstractmethod
from google import genai
from google.genai import types


class AIClient(ABC):

    @abstractmethod
    def generate(self, prompt: str, system_instruction: str) -> str:
        pass


class GeminiClient(AIClient):

    def __init__(self):
        super().__init__()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.client = genai.Client(api_key=gemini_api_key)

    def generate(self, prompt: str, system_instruction: str) -> str:
        # 未來可以把think level放進.env，目前覺得預設就夠用
        config = (
            types.GenerateContentConfig(system_instruction=system_instruction)
            if system_instruction
            else None
        )

        response = self.client.models.generate_content(
            model=self.model,
            config=config,
            contents=prompt,
        )
        return response.text


def get_client() -> AIClient:
    provider = os.getenv("AI_PROVIDER", "gemini")

    if provider == "gemini":
        return GeminiClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")
