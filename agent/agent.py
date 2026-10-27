"""ADK Multi-Agent Orchestration for Challenge 5: Preventative Mobile Care & Health Equity Broker.

Architecture:
                    ┌──────────────────────────────┐
                    │            START             │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
            ┌─────►│     1. PLANNING AGENT         │
            │      │  Generates or revises plan    │
            │      └──────────────┬────────────────┘
            │                     │
            │                     │ writes: session.state["proposed_plan"]
            │                     ▼
            │      ┌───────────────────────────────┐
            │      │      2. AUDITOR AGENT         │
            │      │  Cross-examines for equity,   │
            │      │  nominal clinics & resolution │
            │      └──────────────┬────────────────┘
            │                     │
            │                     │ writes: session.state["audit_verdict"]
            │                     │         session.state["audit_feedback"]
            │                     ▼
            │      ┌───────────────────────────────┐
            │      │      Conditional Router       │
            │      │    verdict == REVISION?       │
            │      └──────┬─────────────────┬──────┘
            │             │                 │
            │  REVISION   │                 │ APPROVED
            │ (max 2 loops)                 │
            └─────────────┘                 ▼
                           ┌───────────────────────────────┐
                           │    3. COMMUNICATOR AGENT      │
                           │  Translates to community      │
                           │  flyers & "Why Not Us?" notes │
                           └──────────────┬────────────────┘
                                          │
                                          ▼
                                        [ END ]

Conversational entry point:
- `root_agent` (`mobile_care_equity_broker`):
  - Welcomes users warmly upon greetings without dumping unsolicited plans.
  - Answers ad-hoc domain and health data questions directly using BigQuery tools.
  - Transfers to `mobile_clinic_siting_pipeline` when asked to plan or deploy mobile clinics.
"""

from __future__ import annotations

import json
import os
import re
from typing import AsyncGenerator

# Ensure Vertex AI on global endpoint is active for gemini-3.6-flash
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("A4I_DATASET", "a4i_health")

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from .mcp_config import create_bigquery_mcp_toolset
from .mcp_config import create_bigquery_mcp_toolset
from .prompts import (
    AUDITOR_PROMPT,
    BROKER_COORDINATOR_PROMPT,
    COMMUNICATOR_PROMPT,
    PLANNING_AGENT_SYSTEM_PROMPT,
)
from .tools import (
    analyze_burden_and_barriers,
    analyze_regional_context_and_surveillance,
    analyze_regional_context_and_surveillance,
    analyze_spatial_access_and_shortages,
    audit_candidate_plan,
    audit_cross_border_access,
    audit_facility_reality,
    audit_tract_demographics,
    find_overlooked_high_burden_tracts,
    get_candidate_siting_tracts,
    get_field_reports,
    get_holistic_tract_rankings,
    get_tract_deep_dive,
    log_clinic_field_report,
    rank_candidate_tracts,
    record_audit_verdict,
    save_proposed_plan,
)

DEFAULT_MODEL = os.getenv("A4I_MODEL", "gemini-3.6-flash")


def _extract_verdict_from_state(state: dict) -> str:
    """Determines whether the Auditor verdict is REVISION_REQUIRED or APPROVED."""
    feedback = state.get("audit_feedback")
    if isinstance(feedback, str) and feedback.strip():
        # Check for JSON verdict field in audit_feedback first
        match = re.search(
            r'"verdict"\s*:\s*"(REVISION_REQUIRED|APPROVED|REJECT|APPROVE)"',
            feedback,
            re.IGNORECASE,
        )
        if match:
            raw = match.group(1).upper()
            return "REVISION_REQUIRED" if "REVISION" in raw or "REJECT" in raw else "APPROVED"
        if "REVISION_REQUIRED" in feedback.upper():
            return "REVISION_REQUIRED"
        if '"APPROVED"' in feedback.upper() or "VERDICT: APPROVED" in feedback.upper():
            return "APPROVED"

    raw_verdict = str(state.get("audit_verdict", "")).upper().strip()
    if "REVISION" in raw_verdict or "REJECT" in raw_verdict:
        return "REVISION_REQUIRED"
    if "APPROV" in raw_verdict:
        return "APPROVED"
    return "APPROVED"


class ConditionalRouterAgent(BaseAgent):
    """Conditional Router inside the Planning-Audit LoopAgent.

    Inspects `session.state["audit_verdict"]` and `session.state["audit_feedback"]`:
    - If `verdict == "REVISION_REQUIRED"`, keeps `escalate=False` so `LoopAgent`
      loops back to `planner_agent` (up to `max_iterations=2`).
    - If `verdict == "APPROVED"`, emits `EventActions(escalate=True)` to exit
      `LoopAgent` and transition to `communicator_agent`.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        iteration = int(state.get("audit_loop_iteration", 0)) + 1
        verdict = _extract_verdict_from_state(state)
        proposed_plan = state.get("proposed_plan", "")
        audit_feedback = state.get("audit_feedback", "")

        state_delta: dict[str, object] = {
            "audit_loop_iteration": iteration,
            "audit_verdict": verdict,
            "candidate_plan": proposed_plan,
            "equity_audit": audit_feedback,
        }

        if verdict == "REVISION_REQUIRED":
            state_delta["rejected_first_plan"] = proposed_plan
            state_delta["pass1_audit_feedback"] = audit_feedback
            escalate = False
            router_msg = (
                f"[Conditional Router — Loop {iteration}/2] Verdict is REVISION_REQUIRED. "
                "Routing back to `planner_agent` to revise the siting plan using `audit_feedback`."
            )
        else:
            state_delta["approved_plan"] = proposed_plan
            escalate = True
            router_msg = (
                f"[Conditional Router — Loop {iteration}/2] Verdict is APPROVED. "
                "Exiting audit loop and routing approved plan to `communicator_agent`."
            )

        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=router_msg)],
            ),
            actions=EventActions(escalate=escalate, state_delta=state_delta),
        )


def build_planner_agent(
    model: str = DEFAULT_MODEL, include_mcp: bool = False
) -> LlmAgent:
    """1. Planning Agent: Generates or revises the 4-stop plan and writes to session.state['proposed_plan']."""
    tools: list = [
        get_holistic_tract_rankings,
        get_candidate_siting_tracts,
        get_tract_deep_dive,
        save_proposed_plan,
        analyze_burden_and_barriers,
        analyze_spatial_access_and_shortages,
        analyze_regional_context_and_surveillance,
        rank_candidate_tracts,
    ]
    if include_mcp:
        tools.append(create_bigquery_mcp_toolset(readonly=True))

    return LlmAgent(
        name="planner_agent",
        description=(
            "Generates or revises a 4-stop Saturday mobile care deployment plan using "
            "`v_planner_holistic_ranking` and writes to `session.state['proposed_plan']`."
        ),
        instruction=PLANNING_AGENT_SYSTEM_PROMPT,
        model=model,
        tools=tools,
        output_key="proposed_plan",
    )


def build_auditor_agent(
    model: str = DEFAULT_MODEL, include_mcp: bool = False
) -> LlmAgent:
    """2. Auditor Agent: Cross-examines `proposed_plan` for equity, nominal clinics, and resolution limits."""
    tools: list = [
        audit_tract_demographics,
        audit_facility_reality,
        audit_cross_border_access,
        find_overlooked_high_burden_tracts,
        record_audit_verdict,
        audit_candidate_plan,
    ]
    if include_mcp:
        tools.append(create_bigquery_mcp_toolset(readonly=True))

    return LlmAgent(
        name="auditor_agent",
        description=(
            "Cross-examines `session.state['proposed_plan']` for demographic equity, "
            "nominal clinics (school-based, mobile, part-time <30h/wk), cross-border FQHCs, "
            "and spatial/temporal resolution limits; writes `audit_verdict` and `audit_feedback`."
        ),
        instruction=AUDITOR_PROMPT,
        model=model,
        tools=tools,
        output_key="audit_feedback",
    )


def build_conditional_router() -> ConditionalRouterAgent:
    """Builds the Conditional Router agent that evaluates `verdict == REVISION_REQUIRED` vs `APPROVED`."""
    return ConditionalRouterAgent(
        name="conditional_router",
        description=(
            "Inspects `session.state['audit_verdict']` and `session.state['audit_feedback']`. "
            "Loops back to `planner_agent` on REVISION_REQUIRED (max 2 loops) or escalates to "
            "`communicator_agent` on APPROVED."
        ),
    )


def build_communicator_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """3. Communicator Agent: Translates approved plan into community flyers & 'Why Not Us?' notes."""
    return LlmAgent(
        name="communicator_agent",
        description="Generates the 4-part Clinic Plan (Where and when, What to bring, Why here and not there, What this plan cannot see) and bilingual outreach copy.",
        instruction=COMMUNICATOR_PROMPT,
        model=model,
        tools=[get_field_reports, log_clinic_field_report],
        output_key="community_materials",
    )


def build_siting_pipeline(
    model: str = DEFAULT_MODEL, include_mcp: bool = False, include_mcp: bool = False
) -> SequentialAgent:
    """Builds the 3-stage SequentialAgent (`planning_audit_loop` -> `communicator_agent`)."""
    planner = build_planner_agent(model=model, include_mcp=include_mcp, include_mcp=include_mcp)
    auditor = build_auditor_agent(model=model, include_mcp=include_mcp)
    router = build_conditional_router()
    communicator = build_communicator_agent(model=model)

    planning_audit_loop = LoopAgent(
        name="planning_audit_loop",
        description=(
            "Iterative Planning -> Auditing -> Conditional Routing loop (max 2 iterations)."
        ),
        sub_agents=[planner, auditor, router],
        max_iterations=2,
    )

    return SequentialAgent(
        name="mobile_clinic_siting_pipeline",
        description=(
            "Executes the complete Mobile Clinic Siting workflow: "
            "1. Planning Agent -> 2. Auditor Agent -> Conditional Router (max 2 loops) -> "
            "3. Communicator Agent."
        ),
        sub_agents=[planning_audit_loop, communicator],
    )


def build_root_agent(
    model: str = DEFAULT_MODEL, include_mcp: bool = False
) -> LlmAgent:
    """Builds the conversational broker root agent with the siting pipeline and domain tools."""
    siting_pipeline = build_siting_pipeline(model=model, include_mcp=include_mcp)
    tools: list = [
        get_holistic_tract_rankings,
        get_tract_deep_dive,
        analyze_burden_and_barriers,
        analyze_spatial_access_and_shortages,
        analyze_regional_context_and_surveillance,
        get_field_reports,
        log_clinic_field_report,
    ]
    if include_mcp:
        tools.append(create_bigquery_mcp_toolset(readonly=True))

    return LlmAgent(
        name="mobile_care_equity_broker",
        description="Interactive Public Health Equity & Preventative Mobile Care Broker for Fulton County, GA (13121).",
        instruction=BROKER_COORDINATOR_PROMPT,
        model=model,
        tools=tools,
        sub_agents=[siting_pipeline],
    )


# Exported root agent for ADK discovery
root_agent = build_root_agent()

__all__ = [
    "ConditionalRouterAgent",
    "root_agent",
    "build_root_agent",
    "build_siting_pipeline",
    "build_planner_agent",
    "build_auditor_agent",
    "build_conditional_router",
    "build_communicator_agent",
]
