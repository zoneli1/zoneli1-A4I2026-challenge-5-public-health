"""End-to-end ADK multi-agent pipeline test (`InMemoryRunner`) for Challenge 5.

Executes the full `mobile_care_equity_broker` SequentialAgent:
1. `evidence_gathering_panel` (ParallelAgent: `burden_analyst`, `access_analyst`, `context_surveillance_analyst`)
2. `plan_audit_revise_loop` (LoopAgent: `siting_planner` Pass 1 -> `equity_and_rigor_auditor` REJECT ->
   `siting_planner` Pass 2 -> `equity_and_rigor_auditor` APPROVE)
3. `communication_panel` (ParallelAgent: `clinical_accountability_writer`, `community_outreach_writer`)
4. `clinic_plan_synthesizer` (LlmAgent)

Also saves the full execution trace and `session.state` snapshot to `agent/cached_broker_run.json`
for instant inspection in the web dashboard.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from typing import Any

from google.adk.runners import InMemoryRunner
from google.genai import types

from agent.agent import build_root_agent

CACHE_PATH = Path(__file__).resolve().parent.parent / "agent" / "cached_broker_run.json"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)


async def run_full_broker_pipeline(prompt: str | None = None) -> dict[str, Any]:
    if not prompt:
        prompt = (
            "Generate the complete 4-Part Saturday Preventative Mobile Care Siting Plan "
            "for Fulton County, Georgia (FIPS 13121) for next month's 4 Saturdays. "
            "Ensure you audit and reject any clustered or naive first-pass proposal, "
            "disclose all spatial/temporal resolution limits and federal HPSA gaps, "
            "run the post-hoc SVI Theme 3 demographic landing audit, and produce "
            "bilingual English and Spanish community outreach flyers."
        )

    # Use include_mcp=False during automated batch runner or True when testing MCP
    root = build_root_agent(include_mcp=True)
    runner = InMemoryRunner(agent=root, app_name="a4i_challenge5_broker")
    session = await runner.session_service.create_session(
        app_name="a4i_challenge5_broker",
        user_id="fulton_health_director",
    )

    msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    agent_events: list[dict[str, Any]] = []

    async for event in runner.run_async(
        user_id="fulton_health_director",
        session_id=session.id,
        new_message=msg,
    ):
        author = getattr(event, "author", "unknown")
        text_parts: list[str] = []
        tool_calls: list[str] = []
        tool_responses: list[str] = []

        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for p in event.content.parts:
                if getattr(p, "text", None):
                    text_parts.append(p.text)
                if getattr(p, "function_call", None):
                    tool_calls.append(p.function_call.name)
                if getattr(p, "function_response", None):
                    tool_responses.append(p.function_response.name)

        if text_parts or tool_calls or tool_responses:
            agent_events.append(
                {
                    "author": author,
                    "tool_calls": tool_calls,
                    "tool_responses": tool_responses,
                    "text": "\n".join(text_parts).strip(),
                }
            )
            print(
                f"[Event] author={author} tools={tool_calls} resp={tool_responses} text_len={sum(len(t) for t in text_parts)}"
            )

    updated_session = await runner.session_service.get_session(
        app_name="a4i_challenge5_broker",
        user_id="fulton_health_director",
        session_id=session.id,
    )
    state = dict(updated_session.state) if updated_session else {}

    # Assertions verifying the 4 Judge Questions
    assert "burden_evidence" in state, "Missing burden_evidence in session.state"
    assert "access_evidence" in state, "Missing access_evidence in session.state"
    assert "regional_context" in state, "Missing regional_context in session.state"
    assert "rejected_first_plan" in state, "Pass 1 plan was not recorded as rejected in session.state"
    assert "approved_plan" in state, "Pass 2 plan was not approved in session.state"
    assert state.get("audit_verdict") == "APPROVE", f"Expected final verdict APPROVE, got {state.get('audit_verdict')}"
    assert "accountability_brief" in state, "Missing accountability_brief in session.state"
    assert "community_outreach" in state, "Missing community_outreach in session.state"
    assert "final_clinic_plan" in state, "Missing final_clinic_plan in session.state"

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "prompt": prompt,
        "agent_events": agent_events,
        "session_state": state,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, default=_json_default))
    print(f"Saved full multi-agent run trace to {CACHE_PATH}")
    return payload


if __name__ == "__main__":
    asyncio.run(run_full_broker_pipeline())
