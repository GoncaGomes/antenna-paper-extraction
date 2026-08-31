from types import SimpleNamespace

from antenna_paper_extraction.model_client import (
    OpenAICompatibleClient,
    RawChatCompletion,
)


def test_create_raw_chat_completion_preserves_bytes_without_parsing() -> None:
    raw_body = b'{"id":"response-test","choices":[]}'

    class FakeRawResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = raw_body

        def parse(self):
            raise AssertionError("The SDK parser must not be called")

    calls: list[dict[str, object]] = []

    def create(**kwargs: object) -> FakeRawResponse:
        calls.append(kwargs)
        return FakeRawResponse()

    fake_sdk_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                with_raw_response=SimpleNamespace(
                    create=create,
                )
            )
        )
    )

    client = OpenAICompatibleClient(
        sdk_client=fake_sdk_client,
    )

    result = client.create_raw_chat_completion(
        model="nuextract3",
        messages=[
            {
                "role": "user",
                "content": "test input",
            }
        ],
        temperature=0.0,
        extra_body={
            "chat_template_kwargs": {
                "mode": "markdown",
                "enable_thinking": False,
            }
        },
    )

    assert result == RawChatCompletion(
        status_code=200,
        headers={"content-type": "application/json"},
        body=raw_body,
    )
    assert len(calls) == 1
    assert calls[0]["stream"] is False
