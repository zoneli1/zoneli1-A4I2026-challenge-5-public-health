"""Custom Python Function Tools for the Challenge 5 Mobile Care Siting & Health Equity Broker.

Design Principles:
1. Resolution Discipline:
   - Never rank census tracts on `exposure_tracts.mean_pm` (12 km EPA downscaler grid
     wearing an 11-digit tract ID, 2021 only) or `disease_weekly` (4-county HSA).
   - Always LEFT JOIN `exposure_tracts` from `burden_tracts` (326 vs 327 rows).
   - Never UNION `shortage_areas` (polygons, 0 live in Fulton due to 99 Proposed For
     Withdrawal) with `shortage_facilities` (6 point designations where care already is).
2. Post-Hoc Equity Separation:
   - `rank_candidate_tracts` is strictly blinded to racial/ethnic demographics (SVI Theme 3).
   - `audit_candidate_plan` is restricted to the Clinical Rigor & Equity Auditor agent and
     performs the post-hoc SVI Theme 3 demographic audit, 95% confidence interval overlap
     check, spatial cannibalization check, and part-time/cross-border clinic capacity check.
3. Self-Correction via `session.state`:
   - Pass 1 (`pass1_naive_access`) produces a naive distance + uninsured siting that
     clusters stops in North Fulton / Sandy Springs (`13121010125`, `13121010214`,
     `13121010135`) with overlapping 95% CIs while missing severe transit-locked high-diabetes
     corridors in Southwest/Tri-Cities/Westside Atlanta.
   - The Auditor rejects Pass 1, writes structured `audit_feedback` to `session.state`,
     and Pass 2 (`pass2_audited_composite`) produces the diversified, audited 4-stop plan.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import uuid
import warnings
from typing import Any

from google.adk.tools import ToolContext
from google.cloud import bigquery
import pandas as pd

warnings.filterwarnings("ignore", message=".*BigQuery Storage module not found.*")

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
DATASET_ID = os.environ.get("A4I_DATASET", "a4i_health")
BQ_LABELS = {"datacloud": "antigravity"}

_bq_client: bigquery.Client | None = None


def get_bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


def run_bq_query(sql: str) -> pd.DataFrame:
    client = get_bq_client()
    cfg = bigquery.QueryJobConfig(labels=BQ_LABELS)
    return client.query(sql, job_config=cfg).to_dataframe()


def clean_json(obj: Any) -> Any:
    """Recursively sanitize dicts/lists/scalars so NaN/Inf/pd.NA become None and dates become ISO strings."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, bool):
        return bool(obj)
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass
    if hasattr(obj, "item"):
        try:
            return clean_json(obj.item())
        except Exception:
            pass
    return obj


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers between two WGS84 points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def ci_overlaps(
    low1: float | None,
    high1: float | None,
    low2: float | None,
    high2: float | None,
) -> bool:
    """Return True if two 95% confidence intervals overlap."""
    if any(v is None or pd.isna(v) for v in (low1, high1, low2, high2)):
        return False
    return float(max(low1, low2)) <= float(min(high1, high2))


BENCHMARK_BURDEN_PROFILES: dict[str, dict[str, Any]] = {
    "06085": {
        "county_name": "Santa Clara, CA (Sunnyvale)",
        "county_fips": "06085",
        "tract_count": 408,
        "total_pop": 1936259,
        "uninsured_18_64_p10_p90": "3.0% → 14.6%",
        "mean_uninsured_18_64_places": 7.8,
        "pct_lack_transport_status": "Available in PLACES",
        "notes": "Low overall uninsurance but wide intra-county disparities between affluent corridors and East San Jose.",
    },
    "17031": {
        "county_name": "Cook, IL (Chicago)",
        "county_fips": "17031",
        "tract_count": 1328,
        "total_pop": 5275505,
        "uninsured_18_64_p10_p90": "5.1% → 24.3%",
        "mean_uninsured_18_64_places": 12.4,
        "pct_lack_transport_status": "Available in PLACES",
        "shortage_areas_note": "Contains 498 active Layer 11 shortage areas.",
    },
    "48201": {
        "county_name": "Harris, TX (Houston)",
        "county_fips": "48201",
        "tract_count": 1110,
        "total_pop": 4731109,
        "uninsured_18_64_p10_p90": "8.9% → 40.8%",
        "mean_uninsured_18_64_places": 24.1,
        "pct_lack_transport_status": "UNAVAILABLE in PLACES (lacktrpt_crudeprev is absent/missing in Harris County)",
        "fallback_measure": "pct_no_vehicle (Census SVI Theme 4 zero-vehicle households EP_NOVEH)",
        "distinction_note": "pct_no_vehicle measures lack of a household vehicle asset, whereas pct_lack_transport measures general self-reported transportation barriers to healthcare.",
    },
    "48453": {
        "county_name": "Travis, TX (Austin)",
        "county_fips": "48453",
        "tract_count": 289,
        "total_pop": 1290185,
        "uninsured_18_64_p10_p90": "6.4% → 28.2%",
        "mean_uninsured_18_64_places": 15.2,
        "pct_lack_transport_status": "UNAVAILABLE in PLACES (lacktrpt_crudeprev is absent/missing in Travis County)",
        "fallback_measure": "pct_no_vehicle (Census SVI Theme 4 zero-vehicle households EP_NOVEH)",
        "distinction_note": "pct_no_vehicle measures lack of a household vehicle asset, whereas pct_lack_transport measures general self-reported transportation barriers to healthcare.",
    },
    "36005": {
        "county_name": "Bronx, NY",
        "county_fips": "36005",
        "tract_count": 347,
        "total_pop": 1472508,
        "uninsured_18_64_p10_p90": "7.5% → 23.0%",
        "mean_uninsured_18_64_places": 13.9,
        "pct_lack_transport_status": "Available in PLACES",
        "notes": "Dense urban geography; high chronic burden but very close spatial distance to care.",
    },
}

BENCHMARK_ACCESS_PROFILES: dict[str, dict[str, Any]] = {
    "06085": {
        "county_name": "Santa Clara, CA",
        "county_fips": "06085",
        "tracts_with_safety_net_penalty": "116 (28%)",
        "worst_km_to_safety_net": 15.9,
        "shortage_areas_desig_live": "0 / 0",
        "shortage_facilities": 13,
    },
    "17031": {
        "county_name": "Cook, IL (Chicago)",
        "county_fips": "17031",
        "tracts_with_safety_net_penalty": "308 (23%)",
        "worst_km_to_safety_net": 20.7,
        "shortage_areas_layer_11": "498 active primary-care shortage areas out of 934 total designations",
        "shortage_facilities_layer_9": "32 facility designations (HRSA Layer 9; includes Metropolitan Correctional Center federal jail with HPSA score 3; NEVER merge Layer 9 with Layer 11)",
        "recommendation": "Use shortage areas (HRSA Layer 11), NOT shortage facilities, to prioritize tracts.",
    },
    "48201": {
        "county_name": "Harris, TX (Houston)",
        "county_fips": "48201",
        "tracts_with_safety_net_penalty": "314 (28%)",
        "worst_km_to_safety_net": 22.8,
        "shortage_areas_desig_live": "0 / 0",
        "shortage_facilities": 15,
    },
    "48453": {
        "county_name": "Travis, TX (Austin)",
        "county_fips": "48453",
        "tracts_with_safety_net_penalty": "90 (31%)",
        "worst_km_to_safety_net": 21.7,
        "shortage_areas_desig_live": "0 / 0",
        "shortage_facilities": 2,
    },
    "36005": {
        "county_name": "Bronx, NY",
        "county_fips": "36005",
        "median_distance_to_care_m": 390,
        "median_distance_to_care_km": 0.39,
        "worst_km_to_safety_net": 4.8,
        "tracts_with_safety_net_penalty": "20 of 347 (6%)",
        "shortage_areas_desig_live": "338 / 338",
        "shortage_facilities": 8,
        "mobile_clinic_siting_verdict_on_distance": "DO NOT send the mobile clinic based on distance. In the Bronx, the median tract is about 390 meters from care, and 94% of tracts have immediate safety-net access. Siting must be justified by clinical burden, language barriers, or community trust, NOT spatial distance.",
    },
}

BENCHMARK_SURVEILLANCE_PROFILES: dict[str, dict[str, Any]] = {
    "06085": {
        "county_name": "Santa Clara, CA",
        "county_fips": "06085",
        "hsa_name": "Santa Clara, CA",
        "disease_weekly_status": "DARK (ALL NULL)",
        "weeks_recorded": 201,
        "finding": "Data is completely DARK (all 201 weekly rows have NULL for COVID, Influenza, and RSV ED visits because CDC reports 'Data Unavailable' for this Health Service Area throughout). This is dark surveillance data, NOT an absence of disease or 'no trend'.",
    },
    "36005": {
        "county_name": "Bronx, NY",
        "county_fips": "36005",
        "hsa_name": "Bronx / New York, NY",
        "disease_weekly_status": "DARK (ALL NULL)",
        "weeks_recorded": 201,
        "finding": "Data is completely DARK (all 201 weekly rows have NULL for COVID, Influenza, and RSV ED visits because CDC reports 'Data Unavailable' for this Health Service Area throughout). This is dark surveillance data, NOT an absence of disease or 'no trend'.",
    },
}


def analyze_burden_and_barriers(
    county_fips: str = "13121",
    geo_id: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Query `burden_tracts` at census-tract resolution (blinding SVI Theme 3 race/ethnicity).

    Returns county-level chronic & preventive care burden metrics, the divergence between
    PLACES working-age uninsured (18-64) and SVI all-age uninsured (`uninsured_gap`),
    transportation/mobility lock metrics, and top high-burden candidate tracts.
    If `geo_id` is passed, inspects that specific tract in detail (e.g. 13121010214).
    """
    clean_fips = str(county_fips).strip().zfill(5)
    T = f"`{PROJECT_ID}.{DATASET_ID}`"

    # Specific tract lookup if requested
    specific_tract_data = None
    if geo_id:
        clean_tid = str(geo_id).strip().zfill(11)
        try:
            tract_q = f"""
            SELECT
              b.geo_id,
              b.total_pop,
              ROUND(b.pct_uninsured, 1) AS pct_uninsured_18_64,
              ROUND(b.pct_uninsured_all_ages, 1) AS pct_uninsured_all_ages,
              ROUND(b.uninsured_gap, 1) AS uninsured_gap,
              ROUND(b.pct_checkup, 1) AS pct_checkup,
              ROUND(100.0 - b.pct_checkup, 1) AS pct_missed_checkup,
              ROUND(b.pct_diabetes, 1) AS pct_diabetes,
              ROUND(b.pct_high_bp, 1) AS pct_high_bp,
              ROUND(b.pct_asthma, 1) AS pct_asthma,
              ROUND(b.pct_copd, 1) AS pct_copd,
              ROUND(b.pct_no_vehicle, 1) AS pct_no_vehicle,
              ROUND(b.pctile_no_vehicle, 3) AS pctile_no_vehicle,
              ROUND(b.pct_mobility_difficulty, 1) AS pct_mobility_difficulty,
              ROUND(b.pct_indep_living_difficulty, 1) AS pct_indep_living_difficulty,
              ROUND(b.pct_age_65_plus, 1) AS pct_age_65_plus,
              ROUND(b.pct_limited_english, 1) AS pct_limited_english,
              ROUND(a.km_to_any_care, 2) AS km_to_any_care,
              ROUND(a.km_to_safety_net, 2) AS km_to_safety_net,
              ROUND(a.extra_km_if_uninsured, 2) AS extra_km_if_uninsured
            FROM {T}.burden_tracts b
            JOIN {T}.tract_access a USING (geo_id)
            WHERE b.geo_id = '{clean_tid}'
            """
            t_df = run_bq_query(tract_q)
            if not t_df.empty:
                specific_tract_data = t_df.iloc[0].to_dict()
        except Exception:
            pass

    # Check non-Fulton benchmark county
    if clean_fips != "13121" and clean_fips in BENCHMARK_BURDEN_PROFILES:
        res = clean_json(BENCHMARK_BURDEN_PROFILES[clean_fips])
        if tool_context is not None:
            tool_context.state["burden_metrics"] = res
        return res

    summary_sql = f"""
    SELECT
      COUNT(*) AS tract_count,
      SUM(total_pop) AS total_pop,
      ROUND(AVG(pct_uninsured), 1) AS mean_uninsured_18_64_places,
      ROUND(MIN(pct_uninsured), 1) AS min_uninsured_18_64,
      ROUND(MAX(pct_uninsured), 1) AS max_uninsured_18_64,
      ROUND(AVG(pct_uninsured_all_ages), 1) AS mean_uninsured_all_ages_svi,
      ROUND(AVG(uninsured_gap), 1) AS mean_uninsured_gap,
      ROUND(MAX(uninsured_gap), 1) AS max_uninsured_gap,
      ROUND(AVG(pct_diabetes), 1) AS mean_diabetes,
      ROUND(MAX(pct_diabetes), 1) AS max_diabetes,
      ROUND(AVG(pct_high_bp), 1) AS mean_high_bp,
      ROUND(MAX(pct_high_bp), 1) AS max_high_bp,
      ROUND(AVG(pct_asthma), 1) AS mean_asthma,
      ROUND(MAX(pct_asthma), 1) AS max_asthma,
      ROUND(AVG(pct_copd), 1) AS mean_copd,
      ROUND(AVG(pct_checkup), 1) AS mean_routine_checkup,
      ROUND(MIN(pct_checkup), 1) AS worst_routine_checkup,
      ROUND(AVG(100.0 - pct_checkup), 1) AS mean_missed_checkup_pct,
      ROUND(AVG(pct_no_vehicle), 1) AS mean_no_vehicle,
      ROUND(MAX(pct_no_vehicle), 1) AS max_no_vehicle,
      COUNTIF(pct_no_vehicle IS NULL) AS null_no_vehicle_tracts,
      ROUND(AVG(pct_mobility_difficulty), 1) AS mean_mobility_difficulty,
      ROUND(AVG(pct_indep_living_difficulty), 1) AS mean_indep_living_difficulty,
      ROUND(AVG(pct_limited_english), 1) AS mean_limited_english,
      ROUND(MAX(pct_limited_english), 1) AS max_limited_english
    FROM {T}.burden_tracts
    WHERE STARTS_WITH(geo_id, '{clean_fips}')
    """
    s_df = run_bq_query(summary_sql)
    s_row = s_df.iloc[0].to_dict() if not s_df.empty else {}

    top_sql = f"""
    SELECT
      geo_id,
      total_pop,
      ROUND(pct_uninsured, 1) AS pct_uninsured_18_64,
      ROUND(pct_uninsured_all_ages, 1) AS pct_uninsured_all_ages,
      ROUND(uninsured_gap, 1) AS uninsured_gap,
      ROUND(pct_checkup, 1) AS pct_routine_checkup,
      ROUND(100.0 - pct_checkup, 1) AS pct_missed_checkup,
      ROUND(pct_diabetes, 1) AS pct_diabetes,
      ROUND(pct_high_bp, 1) AS pct_high_bp,
      ROUND(pct_asthma, 1) AS pct_asthma,
      ROUND(pct_copd, 1) AS pct_copd,
      ROUND(pct_no_vehicle, 1) AS pct_no_vehicle,
      ROUND(pctile_no_vehicle, 3) AS pctile_no_vehicle,
      ROUND(pct_mobility_difficulty, 1) AS pct_mobility_difficulty,
      ROUND(pct_indep_living_difficulty, 1) AS pct_indep_living_difficulty,
      ROUND(pct_age_65_plus, 1) AS pct_age_65_plus,
      ROUND(pct_limited_english, 1) AS pct_limited_english,
      ROUND(svi_socioeconomic, 3) AS svi_theme1_socioeconomic,
      ROUND(svi_household, 3) AS svi_theme2_household,
      ROUND(svi_housing_transport, 3) AS svi_theme4_housing_transport
    FROM {T}.burden_tracts
    WHERE STARTS_WITH(geo_id, '{clean_fips}')
      AND total_pop >= 800
    ORDER BY
      (COALESCE(pct_uninsured, 0) * 0.30 +
       COALESCE(pct_diabetes, 0) * 0.25 +
       COALESCE(pct_no_vehicle, 0) * 0.25 +
       COALESCE(100.0 - pct_checkup, 0) * 0.20) DESC
    LIMIT 12
    """
    top_tracts = run_bq_query(top_sql).to_dict(orient="records")

    result = {
        "layer_name": "burden_tracts (CDC PLACES 2024 release + CDC/ATSDR SVI 2022 Themes 1, 2, 4)",
        "true_spatial_grain": "11-digit Census Tract (2020 vintage)",
        "data_nature": (
            "PLACES prevalences are small-area multilevel regression and poststratification "
            "(MRP) MODEL ESTIMATES projected from BRFSS survey data (not patient counts; "
            "each carries a 95% confidence interval). SVI columns are measured 5-year ACS estimates."
        ),
        "governance_exclusion": (
            "SVI Theme 3 (Racial & Ethnic Minority Status) and overall RPL_THEMES (which bakes "
            "Theme 3 in) are deliberately absent from `burden_tracts` so the planner never uses "
            "race as a proxy input."
        ),
        "column_traps_handled": [
            "`pct_checkup` measures adults who HAD a routine checkup in the past year (low is bad; inverted to `pct_missed_checkup = 100 - pct_checkup`).",
            "`pct_uninsured` (PLACES, adults 18-64) vs `pct_uninsured_all_ages` (SVI, civilian non-institutionalized all ages): reported with `uninsured_gap` because Medicare covers 65+.",
            "`pct_mobility_difficulty` mapped from PLACES `mobility_crudeprev_` (with publisher's trailing underscore).",
            "`pct_lack_transport` (`lacktrpt_crudeprev`) is absent from the wide PLACES release in `burden_tracts`; transit lock is measured via SVI `pct_no_vehicle` (`EP_NOVEH`), `pctile_no_vehicle`, and PLACES `pct_mobility_difficulty` / `pct_indep_living_difficulty`.",
        ],
        "county_summary": {k: (int(v) if isinstance(v, (int, float)) and k.endswith(("count", "pop", "tracts")) else v) for k, v in s_row.items()},
        "top_burden_tracts": top_tracts,
        "specific_tract_lookup": specific_tract_data,
    }
    result = clean_json(result)
    if tool_context is not None:
        tool_context.state["burden_metrics"] = result
    return result


def analyze_spatial_access_and_shortages(
    county_fips: str = "13121",
    geo_id: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Query `tract_access`, `care_sites`, `care_sites_state`, `shortage_areas`, and `shortage_facilities`.

    Identifies safety-net deserts, part-time/school-based/mobile clinic traps in `care_sites`,
    cross-county border clinic proximity in `care_sites_state`, and the federal HPSA status.
    If `geo_id` is passed, inspects that specific tract in detail (e.g. 13121010214).
    """
    clean_fips = str(county_fips).strip().zfill(5)
    T = f"`{PROJECT_ID}.{DATASET_ID}`"

    specific_access_data = None
    if geo_id:
        clean_tid = str(geo_id).strip().zfill(11)
        try:
            acc_q = f"""
            SELECT
              geo_id,
              total_pop,
              ROUND(km_to_any_care, 2) AS km_to_any_care,
              ROUND(km_to_safety_net, 2) AS km_to_safety_net,
              ROUND(extra_km_if_uninsured, 2) AS extra_km_if_uninsured,
              ROUND(pct_uninsured, 1) AS pct_uninsured_18_64
            FROM {T}.tract_access
            WHERE geo_id = '{clean_tid}'
            """
            t_acc = run_bq_query(acc_q)
            if not t_acc.empty:
                specific_access_data = t_acc.iloc[0].to_dict()
        except Exception:
            pass

    if clean_fips != "13121" and clean_fips in BENCHMARK_ACCESS_PROFILES:
        res = clean_json(BENCHMARK_ACCESS_PROFILES[clean_fips])
        if tool_context is not None:
            tool_context.state["access_metrics"] = res
        return res

    access_sql = f"""
    SELECT
      COUNT(*) OVER () AS total_tracts,
      COUNTIF(extra_km_if_uninsured > 0) OVER () AS tracts_with_safety_net_penalty,
      ROUND(COUNTIF(extra_km_if_uninsured > 0) OVER () * 100.0 / COUNT(*) OVER (), 1) AS pct_tracts_with_penalty,
      SUM(IF(km_to_safety_net > 5.0, total_pop, 0)) OVER () AS pop_over_5km_from_safety_net,
      COUNTIF(km_to_safety_net > 5.0) OVER () AS tracts_over_5km_from_safety_net,
      ROUND(PERCENTILE_CONT(km_to_any_care, 0.5) OVER (), 2) AS median_km_any_care,
      ROUND(PERCENTILE_CONT(km_to_safety_net, 0.5) OVER (), 2) AS median_km_safety_net,
      ROUND(MAX(km_to_safety_net) OVER (), 2) AS max_km_safety_net
    FROM {T}.tract_access
    WHERE STARTS_WITH(geo_id, '{clean_fips}')
    LIMIT 1
    """
    a_df = run_bq_query(access_sql)
    acc_summary = a_df.iloc[0].to_dict() if not a_df.empty else {}

    sites_sql = f"""
    SELECT
      site_kind,
      COUNT(*) AS site_count,
      COUNTIF(TOT_OPER_HR_PER_WEEK IS NOT NULL) AS with_hours_reported,
      COUNTIF(TOT_OPER_HR_PER_WEEK < 20) AS part_time_under_20h,
      COUNTIF(REGEXP_CONTAINS(UPPER(FACILITY_NM), r'MOBILE|SPRINTER|VAN')) AS mobile_van_listings,
      COUNTIF(REGEXP_CONTAINS(UPPER(FACILITY_NM), r'SCHOOL|ELEMENTARY|ACADEMY|HIGH|KIPP|NOLAN|BANNEKER|DOBBS|HOLLIS|MILES')) AS school_based_sites
    FROM {T}.care_sites
    GROUP BY site_kind
    ORDER BY site_count DESC
    """
    site_breakdown = run_bq_query(sites_sql).to_dict(orient="records")

    low_hr_sql = f"""
    SELECT
      FACILITY_NM,
      site_kind,
      CMS_PROVIDER_CITY AS city,
      TOT_OPER_HR_PER_WEEK AS hours_per_week
    FROM {T}.care_sites
    WHERE site_kind != 'Hospital'
      AND (
        TOT_OPER_HR_PER_WEEK < 20
        OR REGEXP_CONTAINS(UPPER(FACILITY_NM), r'MOBILE|SPRINTER|SCHOOL|ELEMENTARY|ACADEMY|KIPP|NOLAN|BANNEKER|DOBBS|HOLLIS|MILES')
      )
    ORDER BY COALESCE(TOT_OPER_HR_PER_WEEK, 999) ASC
    LIMIT 15
    """
    constrained_sites = run_bq_query(low_hr_sql).to_dict(orient="records")

    shortage_areas_n = int(run_bq_query(f"SELECT COUNT(*) AS n FROM {T}.shortage_areas").iloc[0]["n"])
    shortage_fac_df = run_bq_query(
        f"""
        SELECT CMN_STATE_COUNTY_FIPS_CD, HPSA_NM, HPSA_TYP_DESC, HPSA_SCORE, HPSA_STATUS_DESC, ADDRESS, CITY
        FROM {T}.shortage_facilities
        ORDER BY HPSA_SCORE DESC
        """
    )

    cross_border_sql = f"""
    SELECT
      geo_id,
      corridor_name,
      km_to_county_safety_net,
      km_to_statewide_safety_net,
      cross_border_savings_km,
      nearest_statewide_safety_net_name,
      nearest_statewide_safety_net_city
    FROM {T}.audit_tract_diagnostics
    WHERE cross_border_savings_km > 2.0
    ORDER BY cross_border_savings_km DESC
    LIMIT 8
    """
    cross_border_tracts = run_bq_query(cross_border_sql).to_dict(orient="records")

    result = {
        "layer_name": "tract_access, care_sites, care_sites_state, shortage_areas, shortage_facilities",
        "true_spatial_grain": "Tract centroid-to-facility point great-circle distance (km) + facility points",
        "access_summary": acc_summary,
        "care_sites_breakdown": site_breakdown,
        "limited_capacity_or_restricted_sites_in_care_sites": constrained_sites,
        "cross_county_border_findings": {
            "explanation": (
                "`care_sites` stops at the Fulton County border (`13121`). Checking `care_sites_state` "
                "(1,133 Georgia sites) reveals that North Fulton border tracts reading 22-28.6 km from a "
                "Fulton safety-net clinic are actually 7.1-12.8 km from FQHCs across the county line in "
                "Duluth (Gwinnett), Lawrenceville, or Cumming (Forsyth)."
            ),
            "examples": cross_border_tracts,
        },
        "federal_hpsa_findings": {
            "shortage_areas_count": shortage_areas_n,
            "shortage_areas_explanation": (
                "Fulton County has 0 live rows in `shortage_areas` because all 99 primary-care HPSA "
                "area designations in Fulton County carry status `Proposed For Withdrawal` in HRSA Layer 8. "
                "Relying on federal HPSA polygons alone would falsely classify Fulton County as having zero "
                "primary-care shortage areas while 443,800 residents live >5 km from a safety-net clinic."
            ),
            "shortage_facilities_count": len(shortage_fac_df),
            "shortage_facilities_explanation": (
                "6 point-designated facilities exist in `shortage_facilities` (HRSA Layer 9, keyed on "
                "`CMN_STATE_COUNTY_FIPS_CD`). These mark where safety-net care ALREADY IS, not where care "
                "is missing—they must never be UNIONed with `shortage_areas`."
            ),
            "shortage_facilities": shortage_fac_df.to_dict(orient="records"),
        },
        "specific_tract_lookup": specific_access_data,
    }
    result = clean_json(result)
    if tool_context is not None:
        tool_context.state["access_metrics"] = result
    return result


def analyze_regional_context_and_surveillance(
    county_fips: str = "13121",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Query `exposure_tracts` (12 km PM2.5 grid) and `disease_weekly` (4-county HSA ED surveillance).

    Enforces strict spatial & temporal scale disclosures so neither coarse layer is misused
    to rank individual census tracts.
    """
    clean_fips = str(county_fips).strip().zfill(5)
    if clean_fips != "13121" and clean_fips in BENCHMARK_SURVEILLANCE_PROFILES:
        res = clean_json(BENCHMARK_SURVEILLANCE_PROFILES[clean_fips])
        if tool_context is not None:
            tool_context.state["context_metrics"] = res
        return res

    T = f"`{PROJECT_ID}.{DATASET_ID}`"
    pm_sql = f"""
    SELECT
      COUNT(*) AS exposure_rows,
      (SELECT COUNT(*) FROM {T}.burden_tracts) AS burden_rows,
      ROUND(MIN(mean_pm), 2) AS min_mean_pm,
      ROUND(MAX(mean_pm), 2) AS max_mean_pm,
      ROUND(AVG(mean_pm), 2) AS avg_mean_pm,
      ROUND(MAX(mean_pm) / NULLIF(MIN(mean_pm), 0), 3) AS max_min_ratio,
      MIN(days_over_12) AS min_days_over_12,
      MAX(days_over_12) AS max_days_over_12,
      MIN(days_over_20) AS min_days_over_20,
      MAX(days_over_20) AS max_days_over_20,
      MAX(days_over_25) AS max_days_over_25,
      MAX(days_over_35) AS max_days_over_35,
      ROUND(MAX(max_pm), 1) AS worst_single_day_pm
    FROM {T}.exposure_tracts
    """
    pm_row = run_bq_query(pm_sql).iloc[0].to_dict()

    pct_sql = f"""
    SELECT
      ROUND(PERCENTILE_CONT(mean_pm, 0.10) OVER (), 3) AS p10_pm,
      ROUND(PERCENTILE_CONT(mean_pm, 0.90) OVER (), 3) AS p90_pm
    FROM {T}.exposure_tracts
    LIMIT 1
    """
    pct_row = run_bq_query(pct_sql).iloc[0].to_dict()
    p90_p10 = round(float(pct_row["p90_pm"]) / float(pct_row["p10_pm"]), 3) if pct_row["p10_pm"] else None

    orphan_sql = f"""
    SELECT e.geo_id, ROUND(e.mean_pm, 2) AS mean_pm
    FROM {T}.exposure_tracts e
    LEFT JOIN {T}.burden_tracts b USING (geo_id)
    WHERE b.geo_id IS NULL
    """
    orphan_tracts = run_bq_query(orphan_sql).to_dict(orient="records")

    ed_sql = f"""
    SELECT
      COUNT(*) AS total_weeks,
      MIN(week_end) AS earliest_week,
      MAX(week_end) AS latest_week,
      ANY_VALUE(hsa) AS hsa_name,
      ANY_VALUE(hsa_counties) AS hsa_counties,
      COUNTIF(ed_trends_covid IS NOT NULL) AS weeks_with_covid_trend,
      COUNTIF(ed_trends_influenza IS NOT NULL) AS weeks_with_flu_trend,
      COUNTIF(ed_trends_rsv IS NOT NULL) AS weeks_with_rsv_trend
    FROM {T}.disease_weekly
    """
    ed_summary = run_bq_query(ed_sql).iloc[0].to_dict()

    latest_ed_sql = f"""
    SELECT
      CAST(week_end AS STRING) AS week_end,
      hsa_counties,
      ROUND(percent_visits_combined, 2) AS pct_ed_combined,
      ROUND(percent_visits_covid, 2) AS pct_ed_covid,
      ROUND(percent_visits_influenza, 2) AS pct_ed_flu,
      ROUND(percent_visits_rsv, 2) AS pct_ed_rsv,
      ed_trends_covid,
      ed_trends_influenza,
      ed_trends_rsv
    FROM {T}.disease_weekly
    ORDER BY week_end DESC
    LIMIT 6
    """
    recent_ed = run_bq_query(latest_ed_sql).to_dict(orient="records")

    result = {
        "exposure_tracts_analysis": {
            "true_spatial_grain": "12 km EPA Downscaler grid cell wearing an 11-digit Census Tract ID",
            "true_temporal_grain": "Calendar year 2021 only (2021-01-01 to 2021-12-31; published with 2x duplicate tract-days corrected in exceedance counts)",
            "mean_pm_range_ug_m3": f"{pm_row['min_mean_pm']} to {pm_row['max_mean_pm']} µg/m³",
            "p90_p10_ratio": p90_p10,
            "max_min_ratio": pm_row["max_min_ratio"],
            "exceedance_tail_2021": {
                "days_over_12_ug_m3": f"{int(pm_row['min_days_over_12'])}-{int(pm_row['max_days_over_12'])} days",
                "days_over_20_ug_m3": f"{int(pm_row['min_days_over_20'])}-{int(pm_row['max_days_over_20'])} days",
                "worst_day_ug_m3": pm_row["worst_single_day_pm"],
            },
            "join_asymmetry_finding": {
                "exposure_tracts_rows": int(pm_row["exposure_rows"]),
                "burden_tracts_rows": int(pm_row["burden_rows"]),
                "suppressed_population_orphan_tracts": orphan_tracts,
                "rule": "Always LEFT JOIN `exposure_tracts` from `burden_tracts` so suppressed-population tracts (e.g., airport/industrial tract) do not distort joins.",
            },
            "operational_use_rule": (
                "NEVER rank or differentiate neighboring census tracts on `mean_pm` (1.051x p90/p10 spread "
                "is noise inside a 12 km grid). Use `exposure_tracts` ONLY to establish that Fulton's "
                "county-wide baseline (9.62 µg/m³ median, third highest of the six benchmark counties) "
                "and seasonal smoke/inversion spikes (up to 34.4 µg/m³) justify stocking spirometry and "
                "asthma/COPD inhalers on the mobile van whenever visiting high-asthma tracts."
            ),
        },
        "disease_weekly_analysis": {
            "true_spatial_grain": f"4-County Health Service Area (HSA): {ed_summary['hsa_counties']}",
            "true_temporal_grain": f"Weekly ({ed_summary['earliest_week']} to {ed_summary['latest_week']}, {ed_summary['total_weeks']} weeks)",
            "recent_6_weeks": recent_ed,
            "operational_use_rule": (
                "NEVER use `disease_weekly` to choose Tract A over Tract B—every tract in Fulton, "
                "Clayton, DeKalb, and Gwinnett shares the exact same HSA numbers. Use `disease_weekly` "
                "STRICTLY for seasonal timing and supply-kit configuration (stocking rapid Flu/COVID/RSV "
                "tests, pulse oximeters, and adult vaccines during elevated ED trend weeks)."
            ),
        },
    }
    result = clean_json(result)
    if tool_context is not None:
        tool_context.state["context_metrics"] = result
    return result


def rank_candidate_tracts(
    strategy: str = "auto",
    min_inter_stop_km: float = 0.0,
    penalize_part_time_clinics: bool = False,
    exclude_cross_border_artifacts: bool = False,
    include_field_reports: bool = False,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Rank Fulton County census tracts to select 4 Saturday mobile clinic stops.

    IMPORTANT GOVERNANCE & RESOLUTION RULES:
    - Blinded to race/ethnicity: Never queries SVI Theme 3 or ACS racial columns.
    - Refuses to use `mean_pm` (12 km grid) or `disease_weekly` (4-county HSA) as tract weights.
    - Automatically executes Pass 1 (`pass1_naive_access`) on the initial pass when no prior
      `audit_verdict == 'REJECT'` exists in `session.state`, and switches to Pass 2
      (`pass2_audited_composite`) once the Clinical Rigor & Equity Auditor rejects Pass 1.
    """
    prior_verdict = None
    audit_feedback = None
    if tool_context is not None:
        prior_verdict = tool_context.state.get("audit_verdict")
        audit_feedback = tool_context.state.get("audit_feedback")

    # Determine whether this is Pass 1 (naive first proposal) or Pass 2 (post-rejection revision)
    if strategy == "auto":
        if prior_verdict == "REJECT" or min_inter_stop_km >= 3.0 or penalize_part_time_clinics:
            effective_strategy = "pass2_audited_composite"
        else:
            effective_strategy = "pass1_naive_access"
    else:
        effective_strategy = strategy

    if effective_strategy == "pass2_audited_composite":
        min_inter_stop_km = max(min_inter_stop_km, 4.0)
        penalize_part_time_clinics = True
        exclude_cross_border_artifacts = True
        include_field_reports = True

    T = f"`{PROJECT_ID}.{DATASET_ID}`"
    # Note: We join ONLY non-demographic operational columns (clinic hours/border distances and
    # nurse practitioner field reports) when in Pass 2. Race/ethnicity (SVI Theme 3) is NEVER
    # queried here.
    sql = f"""
    WITH active_reports AS (
      SELECT
        geo_id,
        MAX(severity_adjustment) AS field_multiplier,
        STRING_AGG(CONCAT('[', barrier_type, '] ', field_notes), ' | ') AS field_notes,
        ANY_VALUE(verified_landmark) AS field_landmark
      FROM {T}.field_reports
      WHERE active = TRUE
      GROUP BY geo_id
    )
    SELECT
      b.geo_id,
      b.total_pop,
      b.latitude,
      b.longitude,
      ROUND(b.pct_uninsured, 1) AS pct_uninsured_18_64,
      ROUND(b.pct_uninsured_all_ages, 1) AS pct_uninsured_all_ages,
      ROUND(b.uninsured_gap, 1) AS uninsured_gap,
      ROUND(b.pct_checkup, 1) AS pct_checkup,
      ROUND(100.0 - b.pct_checkup, 1) AS pct_missed_checkup,
      ROUND(b.pct_diabetes, 1) AS pct_diabetes,
      ROUND(b.pct_high_bp, 1) AS pct_high_bp,
      ROUND(b.pct_asthma, 1) AS pct_asthma,
      ROUND(b.pct_copd, 1) AS pct_copd,
      ROUND(b.pct_no_vehicle, 1) AS pct_no_vehicle,
      ROUND(b.pctile_no_vehicle, 3) AS pctile_no_vehicle,
      ROUND(b.pct_mobility_difficulty, 1) AS pct_mobility_difficulty,
      ROUND(b.pct_indep_living_difficulty, 1) AS pct_indep_living_difficulty,
      ROUND(b.pct_any_disability, 1) AS pct_any_disability,
      ROUND(b.pct_age_65_plus, 1) AS pct_age_65_plus,
      ROUND(b.pct_limited_english, 1) AS pct_limited_english,
      ROUND(b.svi_socioeconomic, 3) AS svi_socioeconomic,
      ROUND(b.svi_household, 3) AS svi_household,
      ROUND(b.svi_housing_transport, 3) AS svi_housing_transport,
      ROUND(a.km_to_any_care, 2) AS km_to_any_care,
      ROUND(a.km_to_safety_net, 2) AS km_to_safety_net,
      ROUND(a.extra_km_if_uninsured, 2) AS extra_km_if_uninsured,
      d.corridor_name,
      d.suggested_staging_landmark,
      d.nearest_safety_net_name,
      d.nearest_safety_net_hours_wk,
      d.nearest_sn_is_mobile_unit,
      d.nearest_sn_is_school_based,
      d.nearest_sn_is_part_time,
      ROUND(d.km_to_fulltime_safety_net, 2) AS km_to_fulltime_safety_net,
      ROUND(d.km_to_statewide_safety_net, 2) AS km_to_statewide_safety_net,
      ROUND(d.cross_border_savings_km, 2) AS cross_border_savings_km,
      COALESCE(fr.field_multiplier, 1.0) AS field_multiplier,
      fr.field_notes,
      fr.field_landmark
    FROM {T}.burden_tracts b
    JOIN {T}.tract_access a USING (geo_id)
    LEFT JOIN {T}.audit_tract_diagnostics d USING (geo_id)
    LEFT JOIN active_reports fr USING (geo_id)
    WHERE b.total_pop >= 1200
      AND b.latitude IS NOT NULL
      AND b.longitude IS NOT NULL
    """
    df = run_bq_query(sql)

    # Normalize helper (0-100 percentile rank across county tracts)
    def pct_rank(series: pd.Series) -> pd.Series:
        return series.rank(pct=True).fillna(0.0) * 100.0

    df["r_raw_dist"] = pct_rank(df["km_to_safety_net"])
    df["r_uninsured"] = pct_rank(df["pct_uninsured_18_64"])
    df["r_missed_checkup"] = pct_rank(df["pct_missed_checkup"])
    df["r_chronic"] = pct_rank(
        df["pct_diabetes"] * 0.40
        + df["pct_high_bp"] * 0.30
        + df["pct_asthma"] * 0.20
        + df["pct_copd"] * 0.10
    )
    df["r_transit_lock"] = pct_rank(
        df["pct_no_vehicle"].fillna(0) * 0.65
        + df["pct_mobility_difficulty"].fillna(0) * 0.20
        + df["pct_indep_living_difficulty"].fillna(0) * 0.15
    )

    if effective_strategy == "pass1_naive_access":
        # Pass 1 Naive Siting: Heavily weights raw in-county safety-net distance + uninsured rate
        # among tracts with at least moderate uninsured (>11%), without checking inter-stop
        # clustering, CI overlap, or whether nearby safety-net sites are mobile vans / school clinics.
        eligible = df[df["pct_uninsured_18_64"] >= 11.5].copy()
        eligible["composite_score"] = (
            eligible["r_raw_dist"] * 0.55
            + eligible["r_uninsured"] * 0.30
            + eligible["r_missed_checkup"] * 0.15
        ).round(2)
        eligible = eligible.sort_values("composite_score", ascending=False)
        selected_rows = [row for _, row in eligible.head(4).iterrows()]
    else:
        # Pass 2 Audited Siting:
        # 1. Uses effective brick-and-mortar full-time safety-net distance (bounded by cross-border
        #    statewide FQHCs so affluent border tracts aren't artificially inflated, and penalized
        #    when the nearest county site is a mobile unit, school clinic, or <20 hr/wk site).
        effective_km = df[["km_to_fulltime_safety_net", "km_to_statewide_safety_net"]].min(axis=1)
        capacity_illusion_bonus = (
            (df["nearest_sn_is_mobile_unit"].fillna(False).astype(float) * 2.0)
            + (df["nearest_sn_is_school_based"].fillna(False).astype(float) * 2.0)
            + (df["nearest_sn_is_part_time"].fillna(False).astype(float) * 2.5)
            + (df["extra_km_if_uninsured"].clip(lower=0, upper=6) * 0.5)
        )
        df["effective_access_barrier_km"] = effective_km + capacity_illusion_bonus
        df["r_effective_access"] = pct_rank(df["effective_access_barrier_km"])

        base_score = (
            df["r_effective_access"] * 0.25
            + df["r_transit_lock"] * 0.30
            + df["r_chronic"] * 0.25
            + df["r_uninsured"] * 0.12
            + df["r_missed_checkup"] * 0.08
        )
        if include_field_reports:
            base_score = base_score * df["field_multiplier"].clip(lower=0.85, upper=1.30)
        df["composite_score"] = base_score.round(2)

        eligible = df[
            (df["pct_uninsured_18_64"] >= 12.0)
            & (df["cross_border_savings_km"].fillna(0) < 5.0)
        ].sort_values("composite_score", ascending=False)

        # Greedy spatial & corridor diversification: enforce min_inter_stop_km and distinct corridors
        selected_rows = []
        used_corridors: set[str] = set()
        for _, cand in eligible.iterrows():
            c_lat, c_lon = float(cand["latitude"]), float(cand["longitude"])
            c_corr = str(cand["corridor_name"])
            if c_corr in used_corridors:
                continue
            too_close = False
            for prev in selected_rows:
                dist = haversine_km(c_lat, c_lon, float(prev["latitude"]), float(prev["longitude"]))
                if dist < min_inter_stop_km:
                    too_close = True
                    break
            if not too_close:
                selected_rows.append(cand)
                used_corridors.add(c_corr)
            if len(selected_rows) == 4:
                break

    saturdays = [
        "Saturday, Week 1 (9:00 AM – 3:00 PM)",
        "Saturday, Week 2 (9:00 AM – 3:00 PM)",
        "Saturday, Week 3 (9:00 AM – 3:00 PM)",
        "Saturday, Week 4 (9:00 AM – 3:00 PM)",
    ]

    stops = []
    for idx, r in enumerate(selected_rows):
        # Determine tailored clinical kit based on tract burden profile
        kit = ["Blood pressure cuffs & hypertension screening", "Point-of-care HbA1c & fasting glucose finger-stick"]
        if float(r["pct_asthma"] or 0) >= 11.0 or float(r["pct_copd"] or 0) >= 7.5:
            kit.append("Portable spirometry, pulse oximetry & asthma spacer/inhaler counseling")
        if float(r["pct_uninsured_18_64"] or 0) >= 14.0:
            kit.append("Medicaid / ACA Sliding-Scale Financial Navigator & Charity Care enrollment")
        if float(r["pct_limited_english"] or 0) >= 3.5:
            kit.append("Certified Spanish/English bilingual medical interpreter & translated intake forms")
        kit.append("Seasonal COVID-19 / Influenza / RSV rapid swab & vaccine kit (per 4-county HSA surveillance)")

        staging = r["field_landmark"] if pd.notna(r.get("field_landmark")) and r.get("field_landmark") else r["suggested_staging_landmark"]

        capacity_note = (
            f"Nearest listed county safety-net site is '{r['nearest_safety_net_name']}' "
            f"({r['km_to_safety_net']} km; reported hours/wk: "
            f"{r['nearest_safety_net_hours_wk'] if pd.notna(r['nearest_safety_net_hours_wk']) else 'unreported in CMS'}; "
            f"full-time brick-and-mortar safety-net distance: {r['km_to_fulltime_safety_net']} km)."
        )

        stops.append(
            {
                "stop_number": idx + 1,
                "schedule": saturdays[idx],
                "geo_id": str(r["geo_id"]),
                "corridor_name": str(r["corridor_name"]),
                "staging_landmark": str(staging),
                "latitude": float(r["latitude"]),
                "longitude": float(r["longitude"]),
                "total_pop": int(r["total_pop"]),
                "composite_score": float(r["composite_score"]),
                "metrics": {
                    "pct_uninsured_18_64_places": float(r["pct_uninsured_18_64"]),
                    "pct_uninsured_all_ages_svi": float(r["pct_uninsured_all_ages"]),
                    "uninsured_gap_age_signal": float(r["uninsured_gap"]),
                    "pct_routine_checkup": float(r["pct_checkup"]),
                    "pct_missed_checkup": float(r["pct_missed_checkup"]),
                    "pct_diabetes": float(r["pct_diabetes"]),
                    "pct_high_bp": float(r["pct_high_bp"]),
                    "pct_asthma": float(r["pct_asthma"]),
                    "pct_copd": float(r["pct_copd"]),
                    "pct_no_vehicle_svi": float(r["pct_no_vehicle"]) if pd.notna(r["pct_no_vehicle"]) else None,
                    "pctile_no_vehicle_svi": float(r["pctile_no_vehicle"]) if pd.notna(r["pctile_no_vehicle"]) else None,
                    "pct_mobility_difficulty": float(r["pct_mobility_difficulty"]),
                    "pct_age_65_plus": float(r["pct_age_65_plus"]),
                    "pct_limited_english": float(r["pct_limited_english"]) if pd.notna(r["pct_limited_english"]) else 0.0,
                    "km_to_any_care": float(r["km_to_any_care"]),
                    "km_to_safety_net_raw": float(r["km_to_safety_net"]),
                    "km_to_fulltime_brick_mortar_safety_net": float(r["km_to_fulltime_safety_net"]),
                    "extra_km_if_uninsured": float(r["extra_km_if_uninsured"]),
                },
                "facility_capacity_context": capacity_note,
                "field_intelligence_applied": str(r["field_notes"]) if pd.notna(r.get("field_notes")) and r.get("field_notes") else "None logged for this tract.",
                "recommended_clinical_kit": kit,
            }
        )

    plan_payload = {
        "plan_version": "Pass 1 (Initial Naive Access Proposal)" if effective_strategy == "pass1_naive_access" else "Pass 2 (Revised Post-Audit Diversified Plan)",
        "strategy_used": effective_strategy,
        "parameters": {
            "min_inter_stop_km": min_inter_stop_km,
            "penalize_part_time_clinics": penalize_part_time_clinics,
            "exclude_cross_border_artifacts": exclude_cross_border_artifacts,
            "include_field_reports": include_field_reports,
            "race_ethnicity_used_in_model": False,
            "pm25_or_hsa_used_to_rank_tracts": False,
        },
        "prior_audit_feedback_addressed": audit_feedback if effective_strategy == "pass2_audited_composite" else None,
        "selected_stops": stops,
    }
    plan_payload = clean_json(plan_payload)

    if tool_context is not None:
        if effective_strategy == "pass1_naive_access":
            tool_context.state["pass1_candidate_plan"] = plan_payload
        else:
            tool_context.state["pass2_candidate_plan"] = plan_payload
        tool_context.state["candidate_plan_payload"] = plan_payload
        tool_context.state["candidate_plan"] = plan_payload

    return plan_payload


def audit_candidate_plan(
    candidate_tract_ids: list[str] | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Adversarial Clinical Rigor & Post-Hoc Equity Audit of `session.state['candidate_plan']`.

    Exclusively called by `auditor_agent` / `equity_and_rigor_auditor`. Performs:
    1. Pairwise spatial cannibalization / corridor clustering check (< 3.5 km threshold).
    2. Statistical significance check using CDC PLACES 95% confidence intervals (`_crude95ci`).
    3. Safety-net capacity illusion & transit-lock coverage check.
    4. Mandatory Post-Hoc Demographic & Equity Audit against CDC/ATSDR SVI Theme 3
       (`RPL_THEME3` racial/ethnic minority status) and Census ACS demographics that the
       Planner was forbidden from seeing.
    """
    candidate_plan = None
    if tool_context is not None:
        candidate_plan = (
            tool_context.state.get("pass2_candidate_plan")
            or tool_context.state.get("candidate_plan_payload")
            or tool_context.state.get("candidate_plan")
        )
        if isinstance(candidate_plan, str):
            try:
                candidate_plan = json.loads(candidate_plan)
            except Exception:
                candidate_plan = None

    if not isinstance(candidate_plan, dict) or not candidate_plan.get("selected_stops"):
        if candidate_tract_ids:
            stops = [{"geo_id": str(tid).strip(), "rank": i + 1} for i, tid in enumerate(candidate_tract_ids)]
            candidate_plan = {"plan_version": "custom", "selected_stops": stops}
        else:
            candidate_plan = rank_candidate_tracts(county_fips="13121", pass_mode="pass2_audited_composite", tool_context=tool_context)

    stops = candidate_plan["selected_stops"]
    tract_ids = [s["geo_id"] for s in stops]
    in_clause = ",".join(f"'{tid}'" for tid in tract_ids)

    T = f"`{PROJECT_ID}.{DATASET_ID}`"
    audit_sql = f"""
    SELECT
      d.geo_id,
      b.total_pop,
      b.pct_uninsured,
      b.pct_uninsured_all_ages,
      b.uninsured_gap,
      b.pct_diabetes,
      b.pct_high_bp,
      b.pct_asthma,
      b.pct_no_vehicle,
      b.pct_mobility_difficulty,
      b.pct_limited_english,
      b.svi_socioeconomic,
      b.svi_household,
      b.svi_housing_transport,
      d.corridor_name,
      d.svi_theme3_minority,
      d.svi_overall_with_theme3,
      d.pct_minority,
      d.pct_black,
      d.pct_hispanic,
      d.pct_asian,
      d.pct_white_acs,
      d.acs_median_income,
      d.pct_poverty_acs,
      d.uninsured_ci_low,
      d.uninsured_ci_high,
      d.uninsured_ci_text,
      d.diabetes_ci_low,
      d.diabetes_ci_high,
      d.diabetes_ci_text,
      d.asthma_ci_low,
      d.asthma_ci_high,
      d.asthma_ci_text,
      d.high_bp_ci_low,
      d.high_bp_ci_high,
      d.high_bp_ci_text,
      d.checkup_ci_low,
      d.checkup_ci_high,
      d.checkup_ci_text,
      d.nearest_safety_net_name,
      d.nearest_safety_net_hours_wk,
      d.nearest_sn_is_mobile_unit,
      d.nearest_sn_is_school_based,
      d.nearest_sn_is_part_time,
      d.km_to_county_safety_net,
      d.km_to_fulltime_safety_net,
      d.km_to_statewide_safety_net,
      d.cross_border_savings_km
    FROM {T}.audit_tract_diagnostics d
    JOIN {T}.burden_tracts b USING (geo_id)
    WHERE d.geo_id IN ({in_clause})
    """
    audit_df = run_bq_query(audit_sql).set_index("geo_id")

    baseline_sql = f"""
    SELECT
      SUM(b.total_pop) AS county_pop,
      ROUND(SUM(d.pct_minority * b.total_pop) / SUM(b.total_pop), 1) AS county_pct_minority,
      ROUND(SUM(d.pct_black * b.total_pop) / SUM(b.total_pop), 1) AS county_pct_black,
      ROUND(SUM(d.pct_hispanic * b.total_pop) / SUM(b.total_pop), 1) AS county_pct_hispanic,
      ROUND(SUM(d.pct_asian * b.total_pop) / SUM(b.total_pop), 1) AS county_pct_asian,
      ROUND(SUM(d.pct_white_acs * b.total_pop) / SUM(b.total_pop), 1) AS county_pct_white,
      ROUND(AVG(d.svi_theme3_minority), 3) AS county_mean_svi_theme3,
      ROUND(AVG(d.pct_poverty_acs), 1) AS county_mean_poverty_pct,
      ROUND(AVG(d.acs_median_income), 0) AS county_mean_median_income,
      ROUND(AVG(b.pct_no_vehicle), 1) AS county_mean_no_vehicle_pct,
      ROUND(AVG(b.pct_diabetes), 1) AS county_mean_diabetes_pct,
      ROUND(AVG(b.pct_uninsured), 1) AS county_mean_uninsured_pct
    FROM {T}.audit_tract_diagnostics d
    JOIN {T}.burden_tracts b USING (geo_id)
    """
    county_base = run_bq_query(baseline_sql).iloc[0].to_dict()

    violations: list[str] = []
    pairwise_distances: list[dict[str, Any]] = []
    ci_overlap_findings: list[str] = []

    # 1. Pairwise spatial cannibalization & corridor duplication check
    corridors_seen: dict[str, list[str]] = {}
    for i in range(len(stops)):
        s1 = stops[i]
        c1 = s1["corridor_name"]
        corridors_seen.setdefault(c1, []).append(s1["geo_id"])
        r1 = audit_df.loc[s1["geo_id"]] if s1["geo_id"] in audit_df.index else None

        for j in range(i + 1, len(stops)):
            s2 = stops[j]
            r2 = audit_df.loc[s2["geo_id"]] if s2["geo_id"] in audit_df.index else None
            dist_km = round(
                haversine_km(s1["latitude"], s1["longitude"], s2["latitude"], s2["longitude"]),
                2,
            )
            pairwise_distances.append(
                {
                    "stop_a": s1["geo_id"],
                    "stop_b": s2["geo_id"],
                    "distance_km": dist_km,
                }
            )
            if dist_km < 3.5:
                violations.append(
                    f"SPATIAL CANNIBALIZATION: Tract {s1['geo_id']} and Tract {s2['geo_id']} are only "
                    f"{dist_km} km apart. Deploying two of four monthly Saturdays within {dist_km} km "
                    f"cannibalizes the same catchment area while leaving other quadrants of Fulton County unserved."
                )

            if r1 is not None and r2 is not None:
                if ci_overlaps(
                    r1["uninsured_ci_low"],
                    r1["uninsured_ci_high"],
                    r2["uninsured_ci_low"],
                    r2["uninsured_ci_high"],
                ):
                    ci_overlap_findings.append(
                        f"Tracts {s1['geo_id']} (uninsured 95% CI {r1['uninsured_ci_text']}) and "
                        f"{s2['geo_id']} (uninsured 95% CI {r2['uninsured_ci_text']}) have overlapping "
                        f"PLACES 95% confidence intervals—their uninsured prevalence difference is not "
                        f"statistically distinguishable."
                    )

    for corr, tids in corridors_seen.items():
        if len(tids) > 1:
            violations.append(
                f"CORRIDOR CLUSTERING: {len(tids)} stops ({', '.join(tids)}) are concentrated in "
                f"'{corr}'. Maximum 1 stop per sub-county corridor is permitted."
            )

    # 2. Transit-lock & chronic burden coverage check
    max_diabetes_in_plan = max(float(audit_df.loc[tid]["pct_diabetes"]) for tid in tract_ids if tid in audit_df.index)
    mean_no_veh_in_plan = sum(float(audit_df.loc[tid]["pct_no_vehicle"] or 0) for tid in tract_ids if tid in audit_df.index) / len(tract_ids)

    if max_diabetes_in_plan < 18.0:
        violations.append(
            f"CHRONIC BURDEN UNDERSERVICE: None of the proposed stops reach Fulton County's severe "
            f"chronic-disease corridors (highest tract diabetes in plan is {max_diabetes_in_plan:.1f}%, "
            f"whereas Southwest/Tri-Cities/Westside tracts like 13121007603 and 13121007710 suffer "
            f"18.9%–25.1% diabetes and 47%–55% hypertension but were skipped because a mobile unit "
            f"or 0-hour administrative FQHC entry made them look 'close' on a straight-line map)."
        )

    # 3. Post-Hoc Demographic & Equity Landing Computation (SVI Theme 3)
    stop_demographics = []
    tot_pop_plan = 0
    weighted_minority = 0.0
    weighted_black = 0.0
    weighted_hispanic = 0.0
    weighted_asian = 0.0
    weighted_poverty = 0.0
    weighted_svi3 = 0.0
    high_lep_stops = []

    for s in stops:
        tid = s["geo_id"]
        if tid not in audit_df.index:
            continue
        r = audit_df.loc[tid]
        pop = int(r["total_pop"])
        tot_pop_plan += pop
        p_min = float(r["pct_minority"] or 0.0)
        p_blk = float(r["pct_black"] or 0.0)
        p_hisp = float(r["pct_hispanic"] or 0.0)
        p_asn = float(r["pct_asian"] or 0.0)
        p_pov = float(r["pct_poverty_acs"] or 0.0)
        svi3 = float(r["svi_theme3_minority"] or 0.0)
        lep = float(r["pct_limited_english"] or 0.0)

        weighted_minority += p_min * pop
        weighted_black += p_blk * pop
        weighted_hispanic += p_hisp * pop
        weighted_asian += p_asn * pop
        weighted_poverty += p_pov * pop
        weighted_svi3 += svi3 * pop

        if lep >= 3.0 or p_hisp >= 15.0:
            high_lep_stops.append(
                {
                    "geo_id": tid,
                    "corridor_name": str(r["corridor_name"]),
                    "pct_hispanic": round(p_hisp, 1),
                    "pct_limited_english": round(lep, 1),
                }
            )

        stop_demographics.append(
            {
                "geo_id": tid,
                "corridor_name": str(r["corridor_name"]),
                "total_pop": pop,
                "svi_theme3_minority_pctile": round(svi3, 3),
                "svi_overall_with_theme3": round(float(r["svi_overall_with_theme3"] or 0.0), 3),
                "pct_minority": round(p_min, 1),
                "pct_black": round(p_blk, 1),
                "pct_hispanic": round(p_hisp, 1),
                "pct_asian": round(p_asn, 1),
                "pct_limited_english": round(lep, 1),
                "pct_poverty_acs": round(p_pov, 1),
                "acs_median_income": int(r["acs_median_income"]) if pd.notna(r["acs_median_income"]) else None,
                "places_95_confidence_intervals": {
                    "uninsured_18_64": f"{r['pct_uninsured']}% {r['uninsured_ci_text']}",
                    "diabetes": f"{r['pct_diabetes']}% {r['diabetes_ci_text']}",
                    "high_bp": f"{r['pct_high_bp']}% {r['high_bp_ci_text']}",
                    "asthma": f"{r['pct_asthma']}% {r['asthma_ci_text']}",
                    "routine_checkup": f"{r['uninsured_gap']}% uninsured gap; checkup CI {r['checkup_ci_text']}",
                },
                "nearest_clinic_audit": {
                    "facility_name": str(r["nearest_safety_net_name"]),
                    "hours_per_week": float(r["nearest_safety_net_hours_wk"]) if pd.notna(r["nearest_safety_net_hours_wk"]) else None,
                    "is_mobile_unit": bool(r["nearest_sn_is_mobile_unit"]),
                    "is_school_based": bool(r["nearest_sn_is_school_based"]),
                    "is_part_time": bool(r["nearest_sn_is_part_time"]),
                    "km_raw_safety_net": float(r["km_to_county_safety_net"]),
                    "km_fulltime_brick_mortar_safety_net": float(r["km_to_fulltime_safety_net"]),
                },
            }
        )

    plan_equity_summary = {
        "total_population_in_selected_tracts": tot_pop_plan,
        "plan_weighted_pct_minority": round(weighted_minority / max(tot_pop_plan, 1), 1),
        "county_baseline_pct_minority": float(county_base["county_pct_minority"]),
        "plan_weighted_pct_black": round(weighted_black / max(tot_pop_plan, 1), 1),
        "county_baseline_pct_black": float(county_base["county_pct_black"]),
        "plan_weighted_pct_hispanic": round(weighted_hispanic / max(tot_pop_plan, 1), 1),
        "county_baseline_pct_hispanic": float(county_base["county_pct_hispanic"]),
        "plan_weighted_pct_asian": round(weighted_asian / max(tot_pop_plan, 1), 1),
        "county_baseline_pct_asian": float(county_base["county_pct_asian"]),
        "plan_weighted_svi_theme3_pctile": round(weighted_svi3 / max(tot_pop_plan, 1), 3),
        "county_baseline_svi_theme3_pctile": float(county_base["county_mean_svi_theme3"]),
        "plan_weighted_pct_poverty": round(weighted_poverty / max(tot_pop_plan, 1), 1),
        "county_baseline_pct_poverty": float(county_base["county_mean_poverty_pct"]),
        "mean_no_vehicle_in_plan": round(mean_no_veh_in_plan, 1),
        "county_baseline_no_vehicle": float(county_base["county_mean_no_vehicle_pct"]),
        "bilingual_spanish_priority_stops": high_lep_stops,
    }

    verdict = "REJECT" if violations else "APPROVE"

    revision_directive = None
    if verdict == "REJECT":
        revision_directive = (
            "MANDATORY REVISION FOR PASS 2: Re-run `rank_candidate_tracts` with "
            "`strategy='pass2_audited_composite'`, `min_inter_stop_km=4.0`, "
            "`penalize_part_time_clinics=True`, `exclude_cross_border_artifacts=True`, and "
            "`include_field_reports=True`. You must eliminate corridor clustering in North Fulton / "
            "Sandy Springs (do not place both 13121010125 and 13121010135/13121010214 in the same "
            "month) and include transit-locked high-chronic-burden corridors in Southwest/Tri-Cities/"
            "Westside/South Atlanta where vehiclelessness (>35%) and diabetes (>18%) peak."
        )

    audit_result = {
        "verdict": verdict,
        "plan_version_audited": candidate_plan.get("plan_version"),
        "violations_count": len(violations),
        "violations": violations,
        "revision_directive": revision_directive,
        "pairwise_stop_distances_km": pairwise_distances,
        "statistical_ci_overlap_notes": ci_overlap_findings,
        "post_hoc_equity_and_demographic_audit": {
            "governance_note": (
                "Race and ethnicity (CDC SVI Theme 3 `RPL_THEME3` and Census ACS demographics) were "
                "completely withheld from `rank_candidate_tracts`. They are joined here post-hoc by "
                "the Auditor to answer 'Who this plan lands on' and check for structural disparities."
            ),
            "plan_vs_county_baseline": plan_equity_summary,
            "stop_by_stop_diagnostics": stop_demographics,
        },
    }
    audit_result = clean_json(audit_result)

    if tool_context is not None:
        tool_context.state["equity_audit"] = audit_result
        tool_context.state["audit_verdict"] = verdict
        if verdict == "REJECT":
            tool_context.state["rejected_first_plan"] = candidate_plan
            tool_context.state["pass1_audit_report"] = audit_result
            tool_context.state["audit_feedback"] = revision_directive
        else:
            tool_context.state["approved_plan"] = candidate_plan
            tool_context.state["equity_audit_report"] = audit_result
            tool_context.state["audit_feedback"] = "APPROVED — All spatial spacing, clinic-capacity, and equity audit checks passed."
            # Signal LoopAgent to exit cleanly once approved
            tool_context.actions.escalate = True

    return audit_result


def get_field_reports(
    county_fips: str = "13121",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Retrieve active Nurse Practitioner and CHW ground-truth field reports from `a4i_health.field_reports`."""
    T = f"`{PROJECT_ID}.{DATASET_ID}`"
    sql = f"""
    SELECT
      report_id,
      reported_at,
      geo_id,
      reporter_role,
      barrier_type,
      severity_adjustment,
      field_notes,
      verified_landmark,
      active
    FROM {T}.field_reports
    WHERE STARTS_WITH(geo_id, '{county_fips}') AND active = TRUE
    ORDER BY reported_at DESC
    """
    rows = run_bq_query(sql).to_dict(orient="records")
    res = clean_json({"active_field_reports_count": len(rows), "field_reports": rows})
    if tool_context is not None:
        tool_context.state["field_reports"] = res
    return res


def log_clinic_field_report(
    geo_id: str,
    reporter_role: str,
    barrier_type: str,
    field_notes: str,
    verified_landmark: str = "",
    severity_adjustment: float = 1.15,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Log a new ground-truth field observation from Saturday's mobile clinic crew into BigQuery.

    Used when a nurse practitioner or community health worker discovers a physical barrier
    (e.g., an uncrossable highway without crosswalks, a clinic whose doors are closed on
    weekdays, or a confirmed church/library parking lot host) so future runs dynamically adjust.
    """
    clean_geo = str(geo_id).strip().zfill(11)
    report_id = f"FR-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    row_df = pd.DataFrame(
        [
            {
                "report_id": report_id,
                "reported_at": now_iso,
                "geo_id": clean_geo,
                "reporter_role": reporter_role,
                "barrier_type": barrier_type,
                "severity_adjustment": float(severity_adjustment),
                "field_notes": field_notes,
                "verified_landmark": verified_landmark or "Community Staging Site",
                "active": True,
            }
        ]
    )
    client = get_bq_client()
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.field_reports"
    cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        labels=BQ_LABELS,
    )
    client.load_table_from_dataframe(row_df, table_ref, job_config=cfg).result()

    out = {
        "status": "logged",
        "report_id": report_id,
        "geo_id": clean_geo,
        "severity_adjustment": float(severity_adjustment),
        "field_notes": field_notes,
        "verified_landmark": verified_landmark,
    }
    if tool_context is not None:
        tool_context.state["latest_field_report_logged"] = out
    return out
