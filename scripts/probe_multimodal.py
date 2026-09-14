import asyncio
import base64
import io
import os
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    RunContextWrapper,
    Runner,
    ToolExecutionConfig,
    ToolOutputImage,
    TResponseInputItem,
    function_tool,
    set_tracing_disabled,
)
from agents.run import CallModelData, ModelInputData
from dotenv import load_dotenv
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from PIL import Image, ImageDraw

PROBE_ASSET_ID = "probe_image"


@dataclass(slots=True)
class ProbeContext:
    tool_executions: int = 0
    http_requests: int = 0


def create_probe_model(
    context: ProbeContext,
) -> tuple[AsyncOpenAI, OpenAIChatCompletionsModel]:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

    values: dict[str, str] = {}

    for name in (
        "SKYNET_BASE_URL",
        "SKYNET_API_KEY",
        "ARCHITECTURE_AUTHOR_MODEL",
    ):
        value = os.environ.get(name)

        if value is None or not value.strip():
            raise ValueError(f"Missing required environment variable: {name}")

        values[name] = value.strip()

    async def count_http_request(_request: object) -> None:
        context.http_requests += 1

    set_tracing_disabled(True)

    client = AsyncOpenAI(
        base_url=values["SKYNET_BASE_URL"],
        api_key=values["SKYNET_API_KEY"],
        timeout=600.0,
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(
            follow_redirects=False,
            event_hooks={"request": [count_http_request]},
        ),
    )

    model = OpenAIChatCompletionsModel(
        model=values["ARCHITECTURE_AUTHOR_MODEL"],
        openai_client=client,
    )

    return client, model


def build_probe_image() -> bytes:
    with Image.new("RGB", (320, 160), color="white") as image:
        drawing = ImageDraw.Draw(image)

        drawing.ellipse(
            (30, 30, 130, 130),
            fill="red",
        )
        drawing.rectangle(
            (190, 30, 290, 130),
            fill="blue",
        )

        with io.BytesIO() as buffer:
            image.save(buffer, format="PNG")
            return buffer.getvalue()


@function_tool(failure_error_function=None)
async def get_probe_asset(
    ctx: RunContextWrapper[ProbeContext],
    asset_id: str,
) -> ToolOutputImage:
    """Return the synthetic image declared in the probe catalog.

    This tool may be used only once per run.

    Args:
        asset_id: Exact identifier of the requested asset: probe_image.
    """
    if ctx.context.tool_executions >= 1:
        raise RuntimeError("A second asset request is not allowed.")

    if asset_id != PROBE_ASSET_ID:
        raise ValueError(f"Unknown probe asset identifier: {asset_id}")

    ctx.context.tool_executions += 1

    image_bytes = build_probe_image()
    encoded_image = base64.b64encode(image_bytes).decode("ascii")

    return ToolOutputImage(
        image_url=f"data:image/png;base64,{encoded_image}",
    )


def prepare_probe_input(
    data: CallModelData[ProbeContext],
) -> ModelInputData:
    items: list[TResponseInputItem] = []

    for item in data.model_data.input:
        if item.get("type") != "function_call_output":
            items.append(item)
            continue

        output = item["output"]

        if (
            not isinstance(output, list)
            or len(output) != 1
            or output[0].get("type") != "input_image"
        ):
            raise RuntimeError("Expected one image in the probe tool output.")

        items.append(
            {
                **item,
                "output": (
                    f"Asset {PROBE_ASSET_ID} was retrieved. "
                    "Its image is attached in the following user message."
                ),
            }
        )

        items.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Requested asset: {PROBE_ASSET_ID}.",
                    },
                    output[0],
                ],
            }
        )

    return ModelInputData(
        input=items,
        instructions=data.model_data.instructions,
    )


async def main() -> int:
    context = ProbeContext()
    client, model = create_probe_model(context)
    context_code = "PROBE-CONTEXT-731"

    try:
        print(f"Model: {model.model}")
        print(f"Agents SDK: {version('openai-agents')}")
        print(f"OpenAI client: {version('openai')}")
        print("Protocol: Chat Completions; tool result plus user image")

        agent = Agent[ProbeContext](
            name="Multimodal protocol probe",
            model=model,
            instructions=(
                "You are testing a visual tool interaction. "
                "Retrieve the requested image using get_probe_asset exactly once. "
                "Do not guess its contents before receiving it. "
                "After receiving the image, give a short final answer in English "
                "describing the shape and color on the left and on the right. "
                "Include the exact context code from the initial user message. "
                "Do not request another tool."
            ),
            tools=[get_probe_asset],
            model_settings=ModelSettings(
                tool_choice="auto",
                parallel_tool_calls=False,
            ),
        )

        result = await Runner.run(
            agent,
            input=(
                f"Context code: {context_code}\n"
                f"Visual catalog: {PROBE_ASSET_ID}, available PNG image.\n"
                f"Inspect {PROBE_ASSET_ID} and describe its contents."
            ),
            context=context,
            max_turns=2,
            run_config=RunConfig(
                tracing_disabled=True,
                call_model_input_filter=prepare_probe_input,
                tool_execution=ToolExecutionConfig(
                    max_function_tool_concurrency=1,
                ),
            ),
        )

        print(f"Model responses: {len(result.raw_responses)}")
        print(f"Final answer:\n{result.final_output}")

        if (
            context.http_requests != 2
            or len(result.raw_responses) != 2
            or context.tool_executions != 1
        ):
            print(
                "Protocol check failed: expected two HTTP requests, "
                "two model responses and one tool execution."
            )
            return 1

        if (
            not isinstance(result.final_output, str)
            or context_code not in result.final_output
        ):
            print("Context check failed: the final answer omitted the context code.")
            return 1

        print("Protocol checks passed. Verify the visual description manually.")
        return 0

    except Exception as error:
        print(f"Probe failed: {type(error).__name__}")

        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            print(f"HTTP status: {status_code}")

        return 1

    finally:
        await client.close()
        print(f"HTTP request attempts: {context.http_requests}")
        print(f"Tool executions: {context.tool_executions}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
