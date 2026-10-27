"""ADK Multi-Agent Orchestration for Challenge 5: Preventative Mobile Care & Health Equity Broker.

Architecture (answering the 4 Challenge Judge Questions):
1. `evidence_gathering_panel` (`ParallelAgent`):
   - `burden_analyst`: Analyzes `burden_tracts` (11-digit Census Tract grain, PLACES MRP models vs.
     measured ACS SVI, inverted `pct_checkup`, two uninsured columns) + attaches the Google-managed
     BigQuery MCP server (`https://bigquery.googleapis.com/mcp`). Writes `session.state['burden_evidence']`.
   - `access_analyst`: Analyzes `tract_access`, `care_sites`, `care_sites_state`, `shortage_areas`
     (0 live polygons in Fulton due to 99 `Proposed For Withdrawal`), and `shortage_facilities`
     (6 point designations), plus part-time/school/mobile facility capacity distortions.
     Writes `session.state['access_evidence']`.
   - `context_surveillance_analyst`: Analyzes `exposure_tracts` (12 km EPA Downscaler grid wearing
     a tract ID; `p90/p10 = 1.051x`; 2021 only; 327 vs 326 rows) and `disease_weekly` (4-county HSA
     grain). Writes `session.state['regional_context']`.

2. `plan_audit_revise_loop` (`LoopAgent`, `max_iterations=2`):
   - `siting_planner`: Proposes 4 Saturday mobile clinic stops. Blinded to race/ethnicity (SVI Theme 3).
     In Pass 1 (`pass1_naive_access`), ranks by raw distance and uninsured rate, clustering all 4 stops
     in North Fulton (`13121011431`, `13121011421`, `13121011430`, `13121011432` within 0.46–1.58 km).
     In Pass 2 (`pass2_audited_composite`), incorporates Auditor rejection feedback to select 4
     diversified, high-need corridors (`13121007603`, `13121010214`, `13121007400`, `13121002300`).
     Writes `session.state['candidate_plan_summary']`.
   - `equity_and_rigor_auditor`: Adversarial methodological & equity auditor with exclusive access to
     `a4i_health.audit_tract_diagnostics` (CDC SVI Theme 3 `RPL_THEME3`, Census ACS racial/ethnic/poverty
     demographics, and CDC PLACES 95% confidence intervals). Rejects Pass 1 for spatial cannibalization,
     overlapping 95% CIs, and facility capacity illusions; approves Pass 2 (`escalate=True`) and produces
     the post-hoc "Who This Plan Lands On" equity report. Writes `session.state['audit_report_summary']`.

3. `communication_panel` (`ParallelAgent`):
   - `clinical_accountability_writer`: Strictly hedged, methodological writer producing Parts 1, 2, and 3
     for the County Health Director & Federal Grant Auditors. Writes `session.state['accountability_brief']`.
   - `community_outreach_writer`: Warm, 6th-grade reading level, bilingual (English & Spanish) CHW writer
     producing Part 4 flyers & WhatsApp/SMS scripts with zero statistical jargon.
     Writes `session.state['community_outreach']`.

4. `clinic_plan_synthesizer` (`LlmAgent`):
   - Combines `{accountability_brief}` and `{community_outreach}` into the final 4-Part Clinic Plan and
     exposes `log_clinic_field_report` / `get_field_reports` for the Nurse Practitioner field feedback loop.
"""

from __future__ import annotations

import os

# Ensure Vertex AI on global endpoint is active for gemini-3.6-flash
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("A4I_DATASET", "a4i_health")

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent

from .mcp_config import create_bigquery_mcp_toolset
from .prompts import (
    ACCESS_ANALYST_PROMPT,
    BURDEN_ANALYST_PROMPT,
    CLINICAL_ACCOUNTABILITY_WRITER_PROMPT,
    CLINIC_PLAN_SYNTHESIZER_PROMPT,
    COMMUNITY_OUTREACH_WRITER_PROMPT,
    CONTEXT_SURVEILLANCE_PROMPT,
    EQUITY_AND_RIGOR_AUDITOR_PROMPT,
    SITING_PLANNER_PROMPT,
)
from .tools import (
    analyze_burden_and_barriers,
    analyze_regional_context_and_surveillance,
    analyze_spatial_access_and_shortages,
    audit_candidate_plan,
    get_field_reports,
    log_clinic_field_report,
    rank_candidate_tracts,
)

MODEL_NAME = os.environ.get("A4I_MODEL", "gemini-3.6-flash")


def build_root_agent(
    model_name: str = MODEL_NAME,
    include_mcp: bool = True,
) -> SequentialAgent:
    """Constructs a fresh multi-agent pipeline hierarchy for the Mobile Care Equity Broker."""
    burden_tools = [analyze_burden_and_barriers]
    if include_mcp:
        burden_tools.append(create_bigquery_mcp_toolset(readonly=True))

    burden_analyst = LlmAgent(
        name="burden_analyst",
        model=model_name,
        description=(
            "Analyzes Census-tract chronic disease burden (CDC PLACES MRP models) and "
            "structural transit/language barriers (CDC SVI ACS measurements) for Fulton County."
        ),
        instruction=BURDEN_ANALYST_PROMPT,
        tools=burden_tools,
        output_key="burden_evidence",
    )

    access_analyst = LlmAgent(
        name="access_analyst",
        model=model_name,
        description=(
            "Evaluates spatial distance to care, part-time/school/mobile facility capacity distortions, "
            "cross-county FQHCs, and the federal HPSA polygon vacuum."
        ),
        instruction=ACCESS_ANALYST_PROMPT,
        tools=[analyze_spatial_access_and_shortages],
        output_key="access_evidence",
    )

    context_surveillance_analyst = LlmAgent(
        name="context_surveillance_analyst",
        model=model_name,
        description=(
            "Evaluates 12 km EPA Downscaler PM2.5 exposure (`exposure_tracts`) and 4-county HSA "
            "weekly respiratory disease surveillance (`disease_weekly`), enforcing spatial grain limits."
        ),
        instruction=CONTEXT_SURVEILLANCE_PROMPT,
        tools=[analyze_regional_context_and_surveillance],
        output_key="regional_context",
    )

    evidence_gathering_panel = ParallelAgent(
        name="evidence_gathering_panel",
        description=(
            "Parallel evidence panel that simultaneously queries tract health burden, spatial facility "
            "access, and regional environmental/epidemiological context into distinct session.state keys."
        ),
        sub_agents=[
            burden_analyst,
            access_analyst,
            context_surveillance_analyst,
        ],
    )

    siting_planner = LlmAgent(
        name="siting_planner",
        model=model_name,
        description=(
            "Operational mobile clinic siting planner (blinded to racial/ethnic SVI Theme 3 data). "
            "Proposes Pass 1 naive access stops and revises to Pass 2 composite stops when rejected."
        ),
        instruction=SITING_PLANNER_PROMPT,
        tools=[rank_candidate_tracts, get_field_reports],
        output_key="candidate_plan_summary",
    )

    equity_and_rigor_auditor = LlmAgent(
        name="equity_and_rigor_auditor",
        model=model_name,
        description=(
            "Adversarial methodological and health equity auditor with access to CDC PLACES 95% CIs "
            "and CDC SVI Theme 3 demographics (`audit_tract_diagnostics`). Rejects clustered/naive plans "
            "and produces the post-hoc 'Who This Plan Lands On' audit."
        ),
        instruction=EQUITY_AND_RIGOR_AUDITOR_PROMPT,
        tools=[audit_candidate_plan],
        output_key="audit_report_summary",
    )

    plan_audit_revise_loop = LoopAgent(
        name="plan_audit_revise_loop",
        description=(
            "Iterative Plan -> Audit -> Revise loop (max 2 iterations) where the Auditor rejects "
            "the Planner's naive Pass 1 proposal and verifies the diversified Pass 2 proposal."
        ),
        max_iterations=2,
        sub_agents=[siting_planner, equity_and_rigor_auditor],
    )

    clinical_accountability_writer = LlmAgent(
        name="clinical_accountability_writer",
        model=model_name,
        description=(
            "Writes the strictly hedged technical brief (Parts 1, 2, and 3) citing 95% confidence "
            "intervals, spatial grain disclosures, Pass 1->Pass 2 self-correction, and SVI Theme 3 equity."
        ),
        instruction=CLINICAL_ACCOUNTABILITY_WRITER_PROMPT,
        output_key="accountability_brief",
    )

    community_outreach_writer = LlmAgent(
        name="community_outreach_writer",
        model=model_name,
        description=(
            "Writes warm, plain-language (6th-grade reading level) bilingual English and Spanish "
            "community flyers and WhatsApp/SMS outreach scripts (Part 4) with zero statistical jargon."
        ),
        instruction=COMMUNITY_OUTREACH_WRITER_PROMPT,
        output_key="community_outreach",
    )

    communication_panel = ParallelAgent(
        name="communication_panel",
        description=(
            "Parallel communication panel running two intentionally conflicting personas: "
            "the hedged Clinical Accountability Writer and the 6th-grade Bilingual Community Outreach Writer."
        ),
        sub_agents=[
            clinical_accountability_writer,
            community_outreach_writer,
        ],
    )

    clinic_plan_synthesizer = LlmAgent(
        name="clinic_plan_synthesizer",
        model=model_name,
        description=(
            "Synthesizes Parts 1-3 (`accountability_brief`) and Part 4 (`community_outreach`) into "
            "the complete 4-Part Fulton County Mobile Clinic Plan and supports field report logging."
        ),
        instruction=CLINIC_PLAN_SYNTHESIZER_PROMPT,
        tools=[log_clinic_field_report, get_field_reports],
        output_key="final_clinic_plan",
    )

    return SequentialAgent(
        name="mobile_care_equity_broker",
        description=(
            "Dynamic Public Health Equity & Preventative Mobile Care Broker for Fulton County, GA (13121)."
        ),
        sub_agents=[
            evidence_gathering_panel,
            plan_audit_revise_loop,
            communication_panel,
            clinic_plan_synthesizer,
        ],
    )


root_agent = build_root_agent(include_mcp=True)
