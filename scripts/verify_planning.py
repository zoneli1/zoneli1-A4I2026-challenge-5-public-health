"""Test Scenario 2 & 5: Planning Pipeline with State Inspection."""

import asyncio
import os
import json

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
os.environ["GOOGLE_CLOUD_PROJECT"] = "qwiklabs-gcp-04-f5825262a0a0"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["A4I_DATASET"] = "a4i_health"
os.environ["A4I_MODEL"] = "gemini-3.6-flash"

from google.adk.runners import InMemoryRunner
from google.genai import types
from agent.agent import build_root_agent


async def test_full_plan():
    root = build_root_agent()
    runner = InMemoryRunner(agent=root, app_name="plan_test_app")
    session = await runner.session_service.create_session(
        app_name="plan_test_app",
        user_id="judge_evaluator",
    )

    prompt = "Plan the four Saturdays for next month. Give me four locations, ranked, with a reason for each."
    print(f"Running full plan evaluation: '{prompt}'...")

    msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    events_log = []

    async for event in runner.run_async(
        user_id="judge_evaluator",
        session_id=session.id,
        new_message=msg,
    ):
        author = getattr(event, "author", "unknown")
        text = ""
        tool_calls = []
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for p in event.content.parts:
                if getattr(p, "text", None):
                    text += p.text
                if getattr(p, "function_call", None):
                    tool_calls.append(p.function_call.name)
        if text or tool_calls:
            print(f"[Event] author={author} tools={tool_calls} text_len={len(text)}")
            events_log.append((author, tool_calls, text))

    # Check updated session state
    updated_session = await runner.session_service.get_session(
        app_name="plan_test_app",
        user_id="judge_evaluator",
        session_id=session.id,
    )
    state = dict(updated_session.state) if updated_session else {}
    print("\n================ SESSION STATE KEYS ================")
    print("State keys found:", list(state.keys()))
    for k in state:
        val_str = str(state[k])
        print(f"  {k}: {val_str[:120]}... (len {len(val_str)})")

    print("\n================ FINAL TEXT OUTPUT ================")
    final_text = [t for a, tc, t in events_log if t]
    if final_text:
        print(final_text[-1])


if __name__ == "__main__":
    asyncio.run(test_full_plan())
