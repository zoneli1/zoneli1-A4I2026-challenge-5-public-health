"""Test Scenario 8: Explanation Agent Styles."""

import asyncio
import os

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
os.environ["GOOGLE_CLOUD_PROJECT"] = "qwiklabs-gcp-04-f5825262a0a0"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["A4I_DATASET"] = "a4i_health"
os.environ["A4I_MODEL"] = "gemini-3.6-flash"

from google.adk.runners import InMemoryRunner
from google.genai import types
from agent.agent import build_root_agent


async def test_explanation_styles():
    root = build_root_agent()
    runner = InMemoryRunner(agent=root, app_name="explanation_test_app")
    
    prompts = [
        ("Clinical Note", "Write a clinical note on why we picked tract 13121007603."),
        ("Unpicked Explanation", "Explain to residents of the neighborhood we didn’t pick why we didn’t pick them."),
    ]
    
    for label, prompt in prompts:
        session = await runner.session_service.create_session(
            app_name="explanation_test_app",
            user_id="judge_evaluator_s8",
        )
        print(f"\n==================== {label} ====================")
        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        texts = []
        async for event in runner.run_async(
            user_id="judge_evaluator_s8",
            session_id=session.id,
            new_message=msg,
        ):
            if getattr(event, "content", None) and getattr(event.content, "parts", None):
                for p in event.content.parts:
                    if getattr(p, "text", None):
                        texts.append(p.text)
        full_text = "\n".join(texts).strip()
        print(full_text[:600] + ("..." if len(full_text) > 600 else ""))


if __name__ == "__main__":
    asyncio.run(test_explanation_styles())
