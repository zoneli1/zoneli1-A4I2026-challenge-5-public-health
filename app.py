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
import math
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("A4I_DATASET", "a4i_health")
os.environ.setdefault("A4I_MODEL", "gemini-3.6-flash")

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from pydantic import BaseModel

from agent.agent import root_agent
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str = "web_user"


session_service = InMemorySessionService()
broker_runner = Runner(
    agent=root_agent, session_service=session_service, app_name="broker_app"
)


def _json_safe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _json_safe(val) for k, val in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_json_safe(val) for val in v]
    if hasattr(v, "item"):
        val = v.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    return str(v)


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
@app.head("/", response_class=HTMLResponse)
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


@app.post("/api/chat")
async def handle_chat(req: ChatRequest) -> JSONResponse:
    """Conversational endpoint executing Google ADK multi-agent orchestrator."""
    try:
        session_id = req.session_id
        if not session_id:
            sess = await session_service.create_session(app_name="broker_app", user_id=req.user_id)
            session_id = sess.id
        else:
            try:
                sess = await session_service.get_session(app_name="broker_app", user_id=req.user_id, session_id=session_id)
            except Exception:
                sess = await session_service.create_session(app_name="broker_app", user_id=req.user_id, session_id=session_id)

        user_msg = Content(role="user", parts=[Part.from_text(text=req.message)])
        text_chunks: list[str] = []
        author = "mobile_care_equity_broker"

        async for event in broker_runner.run_async(user_id=req.user_id, session_id=session_id, new_message=user_msg):
            if hasattr(event, "author") and event.author:
                author = event.author
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        text_chunks.append(part.text)

        reply = "\n\n".join(text_chunks) if text_chunks else "I processed your request, but no text response was produced."
        updated_sess = await session_service.get_session(app_name="broker_app", user_id=req.user_id, session_id=session_id)
        current_state = getattr(updated_sess, "state", {})

        return JSONResponse(
            content={
                "reply": reply,
                "session_id": session_id,
                "author": author,
                "state": _json_safe(current_state),
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "reply": f"Sorry, an error occurred in the agent runtime: {exc}"},
        )


@app.get("/api/download-flyer")
async def download_flyer(lang: str = "bilingual", format: str = "txt") -> Response:
    """Download plain-text or markdown community outreach flyer."""
    en_flyer = (
        "===========================================================\n"
        "   FREE HEALTH CHECKUPS THIS SATURDAY!\n"
        "   FULTON COUNTY PREVENTATIVE MOBILE CARE CLINIC\n"
        "===========================================================\n\n"
        "NO HEALTH INSURANCE? NO PROBLEM!\n"
        "Everyone in our neighborhood is welcome. All care is 100% FREE.\n\n"
        "WHAT WE OFFER FOR YOU & YOUR FAMILY:\n"
        "  * Free Blood Pressure Checks\n"
        "  * Free Diabetes Finger-Stick A1c Screenings\n"
        "  * Free Asthma & Breathing Screenings (with inhaler prescriptions)\n"
        "  * Free Flu, COVID-19 & Adult Routine Vaccines\n"
        "  * Friendly nutrition guidance & direct connections to permanent clinics\n\n"
        "WHAT TO BRING:\n"
        "  * NOTHING! No ID or driver's license required.\n"
        "  * No proof of address or income needed.\n"
        "  * No health insurance required.\n"
        "  * Walk-ins welcome -- no appointment necessary!\n"
        "  * Spanish and English interpreters on site.\n\n"
        "UPCOMING 4-WEEK SATURDAY SCHEDULE (9:00 AM - 3:00 PM):\n"
        "  * Week 1: Center Hill / NW Atlanta -- Center Hill Park (Tract 13121008400)\n"
        "  * Week 2: Bankhead / Grove Park -- West Lake Transit Hub (Tract 13121008602)\n"
        "  * Week 3: South Atlanta / Carver -- Carver Community Center (Tract 13121006500)\n"
        "  * Week 4: College Park / Tri-Cities -- Old National Transit Plaza (Tract 13121010701)\n\n"
        "Need a ride? MARTA bus lines drop off within 200m of all clinic sites.\n"
        "Questions? Call Fulton County Health & Human Services at (404) 612-4000\n"
    )

    es_flyer = (
        "===========================================================\n"
        "   ¡CHEQUEOS DE SALUD GRATUITOS ESTE SÁBADO!\n"
        "   CLÍNICA MÓVIL DE ATENCIÓN PREVENTIVA DEL CONDADO DE FULTON\n"
        "===========================================================\n\n"
        "¿NO TIENE SEGURO MÉDICO? ¡NO SE PREOCUPE!\n"
        "Toda nuestra comunidad es bienvenida. Toda la atención es 100% GRATUITA.\n\n"
        "SERVICIOS PARA USTED Y SU FAMILIA:\n"
        "  * Chequeos gratuitos de presión arterial\n"
        "  * Pruebas rápidas de glucosa y diabetes (A1c con punción en el dedo)\n"
        "  * Revisiones de asma y salud pulmonar\n"
        "  * Vacunas gratuitas contra la gripe (Flu), COVID-19 y vacunas de rutina\n"
        "  * Orientación nutricional y citas directas con clínicas comunitarias permanentes\n\n"
        "¿QUÉ NECESITA TRAER?:\n"
        "  * ¡NADA! No se requiere identificación ni licencia de conducir.\n"
        "  * No se necesita comprobante de domicilio ni de ingresos.\n"
        "  * No se requiere seguro médico.\n"
        "  * Atención por orden de llegada, ¡no necesita cita previa!\n"
        "  * Intérpretes amables de español e inglés disponibles en el lugar.\n\n"
        "CALENDARIO DE 4 SÁBADOS (9:00 AM - 3:00 PM):\n"
        "  * Semana 1: Center Hill / Noroeste de Atlanta -- Parque Center Hill (Tract 13121008400)\n"
        "  * Semana 2: Bankhead / Grove Park -- Centro de Tránsito West Lake (Tract 13121008602)\n"
        "  * Semana 3: Sur de Atlanta / Carver -- Centro Comunitario Carver (Tract 13121006500)\n"
        "  * Semana 4: College Park / Tri-Cities -- Plaza Old National (Tract 13121010701)\n\n"
        "¿Cómo llegar? Las líneas de autobús de MARTA paran a menos de 200 metros.\n"
        "¿Preguntas? Llame a Salud y Servicios Humanos de Fulton: (404) 612-4000\n"
    )

    if lang == "en":
        body = en_flyer
        filename = f"fulton_mobile_care_flyer_en.{format}"
    elif lang == "es":
        body = es_flyer
        filename = f"fulton_mobile_care_flyer_es.{format}"
    else:
        body = f"{en_flyer}\n\n-----------------------------------------------------------\n\n{es_flyer}"
        filename = f"fulton_mobile_care_bilingual_flyer.{format}"

    media_type = "text/markdown" if format == "md" else "text/plain"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

