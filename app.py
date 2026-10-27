"""FastAPI Web Application & Interactive Map Broker for Challenge 5.

Provides:
- Interactive Geospatial Map of Fulton County (`13121`) 326 census tracts, `care_sites`
  (highlighting part-time <20h/wk, school-based, and mobile units), cross-border FQHCs,
  Pass 1 Rejected stops (Red), and Pass 2 Approved stops (Emerald).
- Full 4-Part Mobile Clinic Plan viewer:
  - Part 1: 4 Ranked Saturday Stops + Pass 1 -> Pass 2 Self-Correction Diff
  - Part 2: "What We Could Not Tell You" (4 spatial scales, modeled vs measured, 0-row HPSA vacuum)
  - Part 3: "Who This Plan Lands On" (Post-hoc CDC SVI Theme 3 & ACS demographic equity audit)
  - Part 4: Bilingual English & Spanish Community Outreach Flyers & WhatsApp/SMS Scripts
- Live ADK Multi-Agent Trace & `session.state` Inspector + Nurse Practitioner Field Feedback Loop.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("A4I_DATASET", "a4i_health")
os.environ.setdefault("A4I_MODEL", "gemini-3.6-flash")

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from agent.tools import (
    DATASET_ID,
    PROJECT_ID,
    analyze_burden_and_barriers,
    analyze_regional_context_and_surveillance,
    analyze_spatial_access_and_shortages,
    audit_candidate_plan,
    get_field_reports,
    log_clinic_field_report,
    rank_candidate_tracts,
    run_bq_query,
)
from tests.test_agent_e2e import CACHE_PATH, run_full_broker_pipeline

app = FastAPI(
    title="A4I Challenge 5 — Dynamic Public Health Equity & Mobile Care Broker",
    version="1.0.0",
)


class DummyActions:
    def __init__(self) -> None:
        self.escalate = False


class DummyContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.actions = DummyActions()


class FieldReportRequest(BaseModel):
    geo_id: str
    reporter_role: str = "Mobile Clinic Nurse Practitioner"
    barrier_type: str = "Physical Transit / Facility Access Barrier"
    field_notes: str
    verified_landmark: str = ""
    severity_adjustment: float = 1.15


class RunAgentRequest(BaseModel):
    prompt: str | None = None


def _json_safe(obj: Any) -> Any:
    return json.loads(
        json.dumps(
            obj,
            default=lambda o: o.isoformat()
            if isinstance(o, (datetime.date, datetime.datetime))
            else str(o),
        )
    )


_DASHBOARD_CACHE: dict[str, Any] | None = None


def build_dashboard_payload(force_refresh: bool = False) -> dict[str, Any]:
    global _DASHBOARD_CACHE
    if _DASHBOARD_CACHE is not None and not force_refresh:
        # Attach latest cached_broker_run.json if updated
        if CACHE_PATH.exists():
            try:
                _DASHBOARD_CACHE["cached_agent_run"] = json.loads(CACHE_PATH.read_text())
            except Exception:
                pass
        return _DASHBOARD_CACHE

    T = f"`{PROJECT_ID}.{DATASET_ID}`"

    # 1. Fetch all 326 Fulton County tracts with coordinates, burden, access, and post-hoc diagnostics
    tracts_sql = f"""
    SELECT
      b.geo_id,
      b.total_pop,
      ROUND(b.pct_uninsured, 1) AS pct_uninsured,
      ROUND(b.pct_uninsured_all_ages, 1) AS pct_uninsured_all_ages,
      ROUND(b.uninsured_gap, 1) AS uninsured_gap,
      ROUND(b.pct_diabetes, 1) AS pct_diabetes,
      ROUND(b.pct_high_bp, 1) AS pct_high_bp,
      ROUND(b.pct_asthma, 1) AS pct_asthma,
      ROUND(b.pct_copd, 1) AS pct_copd,
      ROUND(100.0 - b.pct_checkup, 1) AS pct_missed_checkup,
      ROUND(b.pct_no_vehicle, 1) AS pct_no_vehicle,
      ROUND(b.pct_mobility_difficulty, 1) AS pct_mobility_difficulty,
      ROUND(b.pct_limited_english, 1) AS pct_limited_english,
      ROUND(a.km_to_any_care, 2) AS km_to_any_care,
      ROUND(a.km_to_safety_net, 2) AS km_to_safety_net,
      ROUND(a.extra_km_if_uninsured, 2) AS extra_km_if_uninsured,
      d.latitude,
      d.longitude,
      d.corridor_name,
      ROUND(d.km_to_fulltime_safety_net, 2) AS km_to_fulltime_safety_net,
      ROUND(d.km_to_statewide_safety_net, 2) AS km_to_statewide_safety_net,
      ROUND(d.cross_border_savings_km, 2) AS cross_border_savings_km,
      d.nearest_safety_net_name,
      d.nearest_safety_net_hours_wk,
      d.nearest_sn_is_mobile_unit,
      d.nearest_sn_is_school_based,
      d.nearest_sn_is_part_time,
      ROUND(d.svi_theme3_minority, 3) AS svi_theme3_minority,
      ROUND(d.pct_minority, 1) AS pct_minority,
      ROUND(d.pct_black, 1) AS pct_black,
      ROUND(d.pct_hispanic, 1) AS pct_hispanic,
      ROUND(d.pct_poverty_acs, 1) AS pct_poverty_acs,
      d.acs_median_income,
      d.uninsured_ci_text,
      d.diabetes_ci_text
    FROM {T}.burden_tracts b
    JOIN {T}.tract_access a USING (geo_id)
    JOIN {T}.audit_tract_diagnostics d USING (geo_id)
    ORDER BY b.geo_id
    """
    tracts = run_bq_query(tracts_sql).to_dict(orient="records")

    # 2. Fetch care_sites in Fulton County
    sites_sql = f"""
    SELECT
      FACILITY_NM AS name,
      site_kind,
      CMS_PROVIDER_CITY AS city,
      TOT_OPER_HR_PER_WEEK AS hours_per_week,
      latitude,
      longitude,
      REGEXP_CONTAINS(UPPER(FACILITY_NM), r'MOBILE|SPRINTER|VAN') AS is_mobile,
      REGEXP_CONTAINS(UPPER(FACILITY_NM), r'SCHOOL|ELEMENTARY|ACADEMY|HIGH|KIPP|NOLAN|BANNEKER|DOBBS|HOLLIS|MILES') AS is_school,
      (TOT_OPER_HR_PER_WEEK IS NOT NULL AND TOT_OPER_HR_PER_WEEK < 20) AS is_part_time
    FROM {T}.care_sites
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """
    care_sites = run_bq_query(sites_sql).to_dict(orient="records")

    # 3. Execute Pass 1 -> Audit Reject -> Pass 2 -> Audit Approve state machine
    ctx = DummyContext()
    burden_summary = analyze_burden_and_barriers("13121", ctx)
    access_summary = analyze_spatial_access_and_shortages("13121", ctx)
    regional_context = analyze_regional_context_and_surveillance("13121", ctx)
    pass1_plan = rank_candidate_tracts("auto", tool_context=ctx)
    pass1_audit = audit_candidate_plan(tool_context=ctx)
    pass2_plan = rank_candidate_tracts("auto", tool_context=ctx)
    pass2_audit = audit_candidate_plan(tool_context=ctx)
    field_reports = get_field_reports("13121", ctx)

    cached_run = None
    if CACHE_PATH.exists():
        try:
            cached_run = json.loads(CACHE_PATH.read_text())
        except Exception:
            cached_run = None

    payload = _json_safe(
        {
            "county_fips": "13121",
            "county_name": "Fulton County, Georgia",
            "tracts": tracts,
            "care_sites": care_sites,
            "burden_summary": burden_summary,
            "access_summary": access_summary,
            "regional_context": regional_context,
            "pass1_plan": pass1_plan,
            "pass1_audit": pass1_audit,
            "pass2_plan": pass2_plan,
            "pass2_audit": pass2_audit,
            "field_reports": field_reports,
            "cached_agent_run": cached_run,
        }
    )
    _DASHBOARD_CACHE = payload
    return payload


FRONTEND_HTML_PATH = Path(__file__).resolve().parent / "frontend" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def serve_index() -> HTMLResponse:
    return HTMLResponse(content=FRONTEND_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "project": PROJECT_ID,
        "dataset": DATASET_ID,
        "model": os.environ.get("A4I_MODEL", "gemini-3.6-flash"),
        "location": os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        "bigquery_mcp_endpoint": "https://bigquery.googleapis.com/mcp",
    }


@app.get("/api/dashboard-data")
async def get_dashboard_data(refresh: bool = False) -> JSONResponse:
    data = build_dashboard_payload(force_refresh=refresh)
    return JSONResponse(content=data)


@app.post("/api/field-report")
async def submit_field_report(req: FieldReportRequest) -> JSONResponse:
    logged = log_clinic_field_report(
        geo_id=req.geo_id,
        reporter_role=req.reporter_role,
        barrier_type=req.barrier_type,
        field_notes=req.field_notes,
        verified_landmark=req.verified_landmark,
        severity_adjustment=req.severity_adjustment,
    )
    updated_dashboard = build_dashboard_payload(force_refresh=True)
    return JSONResponse(
        content=_json_safe(
            {
                "logged_report": logged,
                "updated_pass2_plan": updated_dashboard["pass2_plan"],
                "updated_pass2_audit": updated_dashboard["pass2_audit"],
                "field_reports": updated_dashboard["field_reports"],
            }
        )
    )


@app.post("/api/run-agent")
async def trigger_agent_pipeline(req: RunAgentRequest) -> JSONResponse:
    try:
        run_payload = await run_full_broker_pipeline(prompt=req.prompt)
        build_dashboard_payload(force_refresh=True)
        return JSONResponse(content=_json_safe(run_payload))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
