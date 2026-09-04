from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RawChatCompletion:
    status_code: int
    headers: dict[str, str]
    body: bytes


class OpenAICompatibleClient:
    def __init__(self, sdk_client: Any) -> None:
        self.sdk_client = sdk_client

    def create_raw_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, object]],
        temperature: float,
        extra_body: dict[str, object],
    ) -> RawChatCompletion:
        response = self.sdk_client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
            temperature=temperature,
            extra_body=extra_body,
            stream=False,
        )

        return RawChatCompletion(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
        )
