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

    # Execute Pass 1 -> Audit Reject -> Pass 2 -> Audit Approve state machine
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
        current_state = getattr(updated_sess, "state", {}) or {}

        # Extract structured 4-week plan & equity audit if generated during this session
        active_plan = (
            current_state.get("pass2_candidate_plan")
            or current_state.get("candidate_plan_payload")
        )
        active_audit = current_state.get("equity_audit")
        if isinstance(active_audit, str):
            active_audit = None

        # If the user asked to plan/schedule the 4 Saturdays and the agent responded,
        # ensure we attach the structured 4-week schedule & audit so the UI table always updates
        msg_lower = req.message.lower()
        is_schedule_query = any(
            kw in msg_lower
            for kw in ("plan", "schedule", "saturday", "4-week", "four week", "four location", "stops", "deploy")
        )
        if is_schedule_query and (not isinstance(active_plan, dict) or not active_plan.get("selected_stops")):
            dash = build_dashboard_payload(force_refresh=False)
            active_plan = dash.get("pass2_plan")
            active_audit = active_audit or dash.get("pass2_audit")

        return JSONResponse(
            content={
                "reply": reply,
                "session_id": session_id,
                "author": author,
                "state": _json_safe(current_state),
                "pass2_plan": _json_safe(active_plan) if active_plan else None,
                "pass2_audit": _json_safe(active_audit) if active_audit else None,
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

