"""ADK Multi-Agent Orchestration for Challenge 5: Preventative Mobile Care & Health Equity Broker.

Conversational, user-responsive architecture:
1. `root_agent` (`mobile_care_equity_broker`):
   - Welcomes users warmly upon greetings (e.g. "hello") without dumping unsolicited plans.
   - Answers domain and health data questions directly using BigQuery inspection tools.
   - When asked to plan or deploy a mobile clinic tour, transfers to the 3-stage pipeline:
2. `planner_agent`: Queries BigQuery (Burden, Access, Shortages) -> Writes to session.state["candidate_plan"] -> transfers to auditor_agent.
3. `auditor_agent`: Evaluates equity criteria (uninsured share, vehicle access, CDC SVI) -> Writes to session.state["equity_audit"] -> transfers to communicator_agent.
4. `communicator_agent`: Generates clear, plain-language outreach copy & 4-week calendar from session.state.
"""

from __future__ import annotations

import os

# Ensure Vertex AI on global endpoint is active for gemini-3.6-flash
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("A4I_DATASET", "a4i_health")

from google.adk.agents import LlmAgent

from .prompts import (
    AUDITOR_PROMPT,
    BROKER_COORDINATOR_PROMPT,
    COMMUNICATOR_PROMPT,
    PLANNER_PROMPT,
)
from .tools import (
    analyze_burden_and_barriers,
    analyze_spatial_access_and_shortages,
    audit_candidate_plan,
    get_field_reports,
    log_clinic_field_report,
    rank_candidate_tracts,
)

DEFAULT_MODEL = os.getenv("A4I_MODEL", "gemini-3.6-flash")


def build_planner_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """Planner Agent: Queries BigQuery data and writes candidate plan to session.state['candidate_plan']."""
    return LlmAgent(
        name="planner_agent",
        description="Queries BigQuery data (Burden, Access, Shortages) and proposes a 4-stop Saturday mobile care deployment.",
        instruction=PLANNER_PROMPT,
        model=model,
        tools=[
            rank_candidate_tracts,
            analyze_burden_and_barriers,
            analyze_spatial_access_and_shortages,
        ],
        output_key="candidate_plan",
    )


def build_auditor_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """Auditor Agent: Evaluates equity criteria and writes audit results to session.state['equity_audit']."""
    return LlmAgent(
        name="auditor_agent",
        description="Evaluates candidate plan against health equity criteria (uninsured share, vehicle access, CDC SVI demographics).",
        instruction=AUDITOR_PROMPT,
        model=model,
        tools=[audit_candidate_plan],
        output_key="equity_audit",
    )


def build_communicator_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """Communicator Agent: Reads final state and generates plain-language outreach copy & 4-week calendar."""
    return LlmAgent(
        name="communicator_agent",
        description="Generates clear, plain-language outreach copy and the complete 4-week mobile clinic calendar.",
        instruction=COMMUNICATOR_PROMPT,
        model=model,
        tools=[get_field_reports, log_clinic_field_report],
    )


def build_root_agent(model: str = DEFAULT_MODEL) -> LlmAgent:
    """Builds the conversational broker root agent with the 3 sub-agents."""
    planner = build_planner_agent(model=model)
    auditor = build_auditor_agent(model=model)
    communicator = build_communicator_agent(model=model)

    return LlmAgent(
        name="mobile_care_equity_broker",
        description="Interactive Public Health Equity & Preventative Mobile Care Broker for Fulton County, GA (13121).",
        instruction=BROKER_COORDINATOR_PROMPT,
        model=model,
        tools=[
            analyze_burden_and_barriers,
            analyze_spatial_access_and_shortages,
            get_field_reports,
        ],
        sub_agents=[planner, auditor, communicator],
    )


# Exported root agent for ADK discovery
root_agent = build_root_agent()

__all__ = [
    "root_agent",
    "build_root_agent",
    "build_planner_agent",
    "build_auditor_agent",
    "build_communicator_agent",
]
