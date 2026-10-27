#!/usr/bin/env python3
"""Build supplemental BigQuery tables for Challenge 5 Post-Hoc Equity & Rigor Audit.

Creates two tables in `a4i_health`:
1. `audit_tract_diagnostics`:
   - Strictly isolated from the Siting Planner agent; queried ONLY by the
     Clinical Rigor & Equity Auditor agent.
   - Contains CDC/ATSDR SVI 2022 Theme 3 (`RPL_THEME3` racial & ethnic minority
     status, `EP_MINRTY`, `EP_AFAM`, `EP_HISP`, `EP_ASIAN`) and `RPL_THEMES`
     (contaminated composite) plus Census ACS 2020 5-year tract demographics.
   - Contains CDC PLACES 95% confidence intervals (`_crude95ci` parsed into
     low/high bounds) to test whether rankings are statistically distinguishable.
   - Contains clinic operating-hour diagnostics (`TOT_OPER_HR_PER_WEEK`),
     distance to full-time (>=35 hr/wk) safety-net care, and cross-county-border
     safety-net distances from `care_sites_state`.
2. `field_reports`:
   - Stores ground-truth field observations logged by Saturday's nurse
     practitioner / Community Health Workers (CHWs) to dynamically adjust future
     siting recommendations.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from google.cloud import bigquery
import pandas as pd

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
DATASET_ID = os.environ.get("A4I_DATASET", "a4i_health")
COUNTY_FIPS = os.environ.get("A4I_COUNTY_FIPS", "13121")

SVI_URL = (
    "https://onemap.cdc.gov/onemapservices/rest/services/SVI/"
    "CDC_ATSDR_Social_Vulnerability_Index_2022_USA/MapServer/2/query"
)
PLACES_WIDE_URL = "https://data.cdc.gov/resource/yjkw-uj5s.json"

BQ_LABELS = {"datacloud": "antigravity"}


def get_json(url: str, params: dict[str, Any]) -> Any:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": "A4I-Challenge5-EquityAudit/1.0"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_svi_theme3(county_fips: str) -> pd.DataFrame:
    """Fetch SVI Theme 3 (Racial & Ethnic Minority Status) fields excluded from burden_tracts."""
    fields = [
        "FIPS",
        "RPL_THEME3",
        "RPL_THEMES",
        "EP_MINRTY",
        "EPL_MINRTY",
        "EP_AFAM",
        "EP_HISP",
        "EP_ASIAN",
        "EP_AIAN",
        "EP_NHPI",
        "EP_TWOMORE",
        "EP_POV150",
    ]
    meta = get_json(
        SVI_URL.replace("/query", ""),
        {"f": "json"},
    )
    avail = {f["name"] for f in meta.get("fields", [])}
    use_fields = [f for f in fields if f in avail]

    data = get_json(
        SVI_URL,
        {
            "where": f"FIPS LIKE '{county_fips}%'",
            "outFields": ",".join(use_fields),
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 2000,
        },
    )
    rows = [feat["attributes"] for feat in data.get("features", [])]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["geo_id"])

    df["geo_id"] = df["FIPS"].astype(str).str.strip().str.zfill(11)
    for col in use_fields:
        if col == "FIPS":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] == -999, col] = None

    rename_map = {
        "RPL_THEME3": "svi_theme3_minority",
        "RPL_THEMES": "svi_overall_with_theme3",
        "EP_MINRTY": "pct_minority_svi",
        "EPL_MINRTY": "pctile_minority_svi",
        "EP_AFAM": "pct_black_svi",
        "EP_HISP": "pct_hispanic_svi",
        "EP_ASIAN": "pct_asian_svi",
        "EP_POV150": "pct_below_150pct_poverty_svi",
    }
    keep = ["geo_id"] + [k for k in rename_map if k in df.columns]
    return df[keep].rename(columns=rename_map)


def parse_ci_pair(val: Any) -> tuple[float | None, float | None, str | None]:
    """Parse PLACES confidence interval string like '(11.8, 16.4)' into (low, high, text)."""
    if val is None or pd.isna(val):
        return None, None, None
    text = str(val).strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1]), text
    return None, None, text


def fetch_places_confidence_intervals(county_fips: str) -> pd.DataFrame:
    """Fetch 95% confidence intervals from CDC PLACES wide tract release."""
    ci_cols = [
        "tractfips",
        "access2_crude95ci",
        "diabetes_crude95ci",
        "casthma_crude95ci",
        "copd_crude95ci",
        "bphigh_crude95ci",
        "checkup_crude95ci",
        "lacktrpt_crude95ci",
    ]
    rows = get_json(
        PLACES_WIDE_URL,
        {
            "$select": ",".join(ci_cols),
            "$where": f"countyfips='{county_fips}'",
            "$limit": 5000,
        },
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["geo_id"])

    df["geo_id"] = df["tractfips"].astype(str).str.strip().str.zfill(11)
    out = pd.DataFrame({"geo_id": df["geo_id"]})

    mapping = {
        "access2_crude95ci": "uninsured",
        "diabetes_crude95ci": "diabetes",
        "casthma_crude95ci": "asthma",
        "copd_crude95ci": "copd",
        "bphigh_crude95ci": "high_bp",
        "checkup_crude95ci": "checkup",
        "lacktrpt_crude95ci": "lack_transport",
    }
    for src_col, prefix in mapping.items():
        if src_col in df.columns:
            parsed = df[src_col].apply(parse_ci_pair)
            out[f"{prefix}_ci_low"] = [p[0] for p in parsed]
            out[f"{prefix}_ci_high"] = [p[1] for p in parsed]
            out[f"{prefix}_ci_text"] = [p[2] for p in parsed]
        else:
            out[f"{prefix}_ci_low"] = None
            out[f"{prefix}_ci_high"] = None
            out[f"{prefix}_ci_text"] = None

    return out


def classify_fulton_corridor(lat: float | None, lon: float | None, geo_id: str) -> tuple[str, str]:
    """Assign human-readable Fulton County sub-corridor and landmark anchor."""
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return ("Unclassified Corridor", "Fulton County Community Center")

    # South Fulton / Fairburn / Palmetto / Chattahoochee Hills
    if lat < 33.62:
        if lon < -84.60:
            return (
                "Deep South Fulton (Palmetto / Chattahoochee Hills / Rico)",
                "Palmetto Library & South Fulton Pkwy Corridor",
            )
        return (
            "South Fulton (Fairburn / Union City / Old National Hwy)",
            "South Fulton Service Center / Old National Hwy Transit Hub",
        )
    # Tri-Cities & Southwest Atlanta
    if lat < 33.71:
        if lon < -84.51:
            return (
                "Southwest Atlanta (Campbellton Rd / Cascade / Sandtown)",
                "Campbellton Rd & Greenbriar Transit Hub",
            )
        if lon < -84.42:
            return (
                "Tri-Cities (East Point / College Park / Hapeville)",
                "East Point MARTA Station & Main St Civic Plaza",
            )
        return (
            "Southeast Atlanta (Lakewood / South River / Browns Mill)",
            "Lakewood Heights Town Center & Rosel Fann Rec Center",
        )
    # Central / Westside / Downtown
    if lat < 33.79:
        if lon < -84.45:
            return (
                "Westside Atlanta (Bankhead / Donald Lee Hollowell / Collier Heights)",
                "HE Holmes / Bankhead MARTA Plaza & Adamsville Rec Center",
            )
        if lon < -84.39:
            return (
                "Central-South Atlanta (West End / Mechanicsville / Pittsburgh / AUC)",
                "West End MARTA Mall & Dunbar Neighborhood Center",
            )
        return (
            "East Central Atlanta (Downtown / Sweet Auburn / Old Fourth Ward)",
            "Martin Luther King Jr. Recreation & Aquatic Center",
        )
    # Midtown / Buckhead
    if lat < 33.90:
        return (
            "Midtown & Buckhead (Peachtree / Lindbergh Corridor)",
            "Lindbergh Center MARTA Plaza",
        )
    # North Fulton (Sandy Springs / Roswell / Alpharetta / Johns Creek)
    if lat < 33.98:
        return (
            "Sandy Springs & Dunwoody Border Corridor",
            "North Springs Transit Hub & Roswell Rd Community Plaza",
        )
    return (
        "North Fulton (Roswell / Alpharetta / Johns Creek)",
        "Roswell Library & Holcomb Bridge Civic Plaza",
    )


def build_tables() -> None:
    client = bigquery.Client(project=PROJECT_ID)
    job_config_query = bigquery.QueryJobConfig(labels=BQ_LABELS)

    print("1/4 Querying tract spatial & cross-border clinic diagnostics from BigQuery...")
    sql = f"""
    WITH safety_net_county AS (
      SELECT
        FACILITY_NM,
        site_kind,
        COALESCE(TOT_OPER_HR_PER_WEEK, 40.0) AS hours_per_week,
        TOT_OPER_HR_PER_WEEK AS raw_hours_per_week,
        REGEXP_CONTAINS(UPPER(FACILITY_NM), r'MOBILE|SPRINTER|VAN') AS is_mobile_unit,
        REGEXP_CONTAINS(UPPER(FACILITY_NM), r'SCHOOL|ELEMENTARY|ACADEMY|HIGH|KIPP|NOLAN|BANNEKER|DOBBS|HOLLIS|MILES') AS is_school_based,
        (COALESCE(TOT_OPER_HR_PER_WEEK, 40.0) < 20.0) AS is_part_time,
        ST_GEOGPOINT(longitude, latitude) AS pt
      FROM `{PROJECT_ID}.{DATASET_ID}.care_sites`
      WHERE site_kind IN ('FQHC', 'FQHC Look-Alike', 'Rural Health Clinic', 'Health Center site')
        AND longitude IS NOT NULL AND latitude IS NOT NULL
    ),
    safety_net_state AS (
      SELECT
        FACILITY_NM,
        CMS_PROVIDER_CITY AS city,
        site_kind,
        COALESCE(TOT_OPER_HR_PER_WEEK, 40.0) AS hours_per_week,
        ST_GEOGPOINT(longitude, latitude) AS pt
      FROM `{PROJECT_ID}.{DATASET_ID}.care_sites_state`
      WHERE site_kind IN ('FQHC', 'FQHC Look-Alike', 'Rural Health Clinic', 'Health Center site')
        AND longitude IS NOT NULL AND latitude IS NOT NULL
    ),
    tract_pts AS (
      SELECT
        b.geo_id,
        b.total_pop,
        b.latitude,
        b.longitude,
        b.pct_limited_english,
        b.uninsured_gap,
        ST_GEOGPOINT(b.longitude, b.latitude) AS t_pt
      FROM `{PROJECT_ID}.{DATASET_ID}.burden_tracts` b
    ),
    nearest_county AS (
      SELECT
        t.geo_id,
        ARRAY_AGG(
          STRUCT(
            s.FACILITY_NM AS name,
            s.site_kind AS kind,
            s.raw_hours_per_week AS hours_wk,
            s.is_mobile_unit AS is_mobile,
            s.is_school_based AS is_school,
            s.is_part_time AS is_part_time,
            ROUND(ST_DISTANCE(t.t_pt, s.pt) / 1000.0, 2) AS km
          )
          ORDER BY ST_DISTANCE(t.t_pt, s.pt) ASC
          LIMIT 1
        )[OFFSET(0)] AS nearest_any_sn,
        ARRAY_AGG(
          IF(NOT s.is_mobile_unit AND NOT s.is_school_based AND NOT s.is_part_time,
             ROUND(ST_DISTANCE(t.t_pt, s.pt) / 1000.0, 2),
             NULL) IGNORE NULLS
          ORDER BY ST_DISTANCE(t.t_pt, s.pt) ASC
          LIMIT 1
        )[SAFE_OFFSET(0)] AS km_to_fulltime_sn
      FROM tract_pts t
      CROSS JOIN safety_net_county s
      GROUP BY t.geo_id
    ),
    nearest_state AS (
      SELECT
        t.geo_id,
        ARRAY_AGG(
          STRUCT(
            s.FACILITY_NM AS name,
            s.city AS city,
            s.hours_per_week AS hours_wk,
            ROUND(ST_DISTANCE(t.t_pt, s.pt) / 1000.0, 2) AS km
          )
          ORDER BY ST_DISTANCE(t.t_pt, s.pt) ASC
          LIMIT 1
        )[OFFSET(0)] AS nearest_state_sn
      FROM tract_pts t
      CROSS JOIN safety_net_state s
      GROUP BY t.geo_id
    ),
    acs AS (
      SELECT
        geo_id,
        median_income AS acs_median_income,
        ROUND(SAFE_DIVIDE(poverty, total_pop) * 100.0, 1) AS pct_poverty_acs,
        ROUND(SAFE_DIVIDE(black_pop, total_pop) * 100.0, 1) AS pct_black_acs,
        ROUND(SAFE_DIVIDE(hispanic_pop, total_pop) * 100.0, 1) AS pct_hispanic_acs,
        ROUND(SAFE_DIVIDE(white_pop, total_pop) * 100.0, 1) AS pct_white_acs,
        ROUND(SAFE_DIVIDE(asian_pop, total_pop) * 100.0, 1) AS pct_asian_acs,
        ROUND(SAFE_DIVIDE(total_pop - white_pop, total_pop) * 100.0, 1) AS pct_minority_acs
      FROM `bigquery-public-data.census_bureau_acs.censustract_2020_5yr`
      WHERE STARTS_WITH(geo_id, '{COUNTY_FIPS}')
    )
    SELECT
      t.geo_id,
      t.latitude,
      t.longitude,
      nc.nearest_any_sn.name AS nearest_safety_net_name,
      nc.nearest_any_sn.kind AS nearest_safety_net_kind,
      nc.nearest_any_sn.hours_wk AS nearest_safety_net_hours_wk,
      nc.nearest_any_sn.is_mobile AS nearest_sn_is_mobile_unit,
      nc.nearest_any_sn.is_school AS nearest_sn_is_school_based,
      nc.nearest_any_sn.is_part_time AS nearest_sn_is_part_time,
      nc.nearest_any_sn.km AS km_to_county_safety_net,
      nc.km_to_fulltime_sn AS km_to_fulltime_safety_net,
      ROUND(nc.km_to_fulltime_sn - nc.nearest_any_sn.km, 2) AS fulltime_hours_penalty_km,
      ns.nearest_state_sn.name AS nearest_statewide_safety_net_name,
      ns.nearest_state_sn.city AS nearest_statewide_safety_net_city,
      ns.nearest_state_sn.km AS km_to_statewide_safety_net,
      ROUND(nc.nearest_any_sn.km - ns.nearest_state_sn.km, 2) AS cross_border_savings_km,
      acs.acs_median_income,
      acs.pct_poverty_acs,
      acs.pct_black_acs,
      acs.pct_hispanic_acs,
      acs.pct_white_acs,
      acs.pct_asian_acs,
      acs.pct_minority_acs
    FROM tract_pts t
    LEFT JOIN nearest_county nc USING (geo_id)
    LEFT JOIN nearest_state ns USING (geo_id)
    LEFT JOIN acs USING (geo_id)
    """
    base_df = client.query(sql, job_config=job_config_query).to_dataframe()
    print(f"   Retrieved {len(base_df)} tracts with spatial & ACS diagnostics.")

    print("2/4 Fetching CDC/ATSDR SVI 2022 Theme 3 (Racial/Ethnic Minority Status)...")
    svi_df = fetch_svi_theme3(COUNTY_FIPS)
    print(f"   Retrieved {len(svi_df)} SVI Theme 3 rows.")

    print("3/4 Fetching CDC PLACES 95% Confidence Intervals (_crude95ci)...")
    ci_df = fetch_places_confidence_intervals(COUNTY_FIPS)
    print(f"   Retrieved {len(ci_df)} PLACES CI rows.")

    merged = base_df.merge(svi_df, on="geo_id", how="left").merge(ci_df, on="geo_id", how="left")

    corridors = [
        classify_fulton_corridor(r["latitude"], r["longitude"], r["geo_id"])
        for _, r in merged.iterrows()
    ]
    merged["corridor_name"] = [c[0] for c in corridors]
    merged["suggested_staging_landmark"] = [c[1] for c in corridors]

    # Fall back to ACS minority % if SVI Theme 3 is missing for any tract
    if "pct_minority_svi" in merged.columns:
        merged["pct_minority"] = merged["pct_minority_svi"].combine_first(merged["pct_minority_acs"])
        merged["pct_black"] = merged["pct_black_svi"].combine_first(merged["pct_black_acs"])
        merged["pct_hispanic"] = merged["pct_hispanic_svi"].combine_first(merged["pct_hispanic_acs"])
        merged["pct_asian"] = merged["pct_asian_svi"].combine_first(merged["pct_asian_acs"])
    else:
        merged["pct_minority"] = merged["pct_minority_acs"]
        merged["pct_black"] = merged["pct_black_acs"]
        merged["pct_hispanic"] = merged["pct_hispanic_acs"]
        merged["pct_asian"] = merged["pct_asian_acs"]

    audit_table_ref = f"{PROJECT_ID}.{DATASET_ID}.audit_tract_diagnostics"
    load_cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        labels=BQ_LABELS,
    )
    client.load_table_from_dataframe(merged, audit_table_ref, job_config=load_cfg).result()
    print(f"   Loaded {audit_table_ref}: {len(merged)} rows.")

    print("4/4 Creating and seeding `field_reports` table for Nurse Practitioner feedback loop...")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    seed_reports = pd.DataFrame(
        [
            {
                "report_id": "FR-2026-001",
                "reported_at": now_iso,
                "geo_id": "13121010125",
                "reporter_role": "Mobile Clinic Nurse Practitioner (Saturday Shift)",
                "barrier_type": "corridor_overlap_notice",
                "severity_adjustment": 0.0,
                "field_notes": (
                    "Strong turnout at Old National Hwy staging site, but residents noted "
                    "adjacent tract 13121010135 shares the exact same bus route (#89/#189). "
                    "Do not double-book both tracts in the same month."
                ),
                "verified_landmark": "South Fulton Service Center / Old National Hwy MARTA Park & Ride",
                "active": True,
            },
            {
                "report_id": "FR-2026-002",
                "reported_at": now_iso,
                "geo_id": "13121007603",
                "reporter_role": "CHW Outreach Coordinator (Southwest/Campbellton)",
                "barrier_type": "clinic_hours_mismatch",
                "severity_adjustment": 1.25,
                "field_notes": (
                    "Nearly half of households (49.4%) have no vehicle and 25.1% have diabetes. "
                    "Although a bricks-and-mortar clinic appears 3.17 km away on the map, "
                    "elderly residents without cars face a two-bus transfer on Campbellton Rd."
                ),
                "verified_landmark": "Campbellton Plaza & Greenbriar Transit Hub",
                "active": True,
            },
            {
                "report_id": "FR-2026-003",
                "reported_at": now_iso,
                "geo_id": "13121010214",
                "reporter_role": "Bilingual Community Health Worker",
                "barrier_type": "highway_pedestrian_barrier",
                "severity_adjustment": 1.15,
                "field_notes": (
                    "43.3% of households have no vehicle and safety-net care is 8.13 km away. "
                    "Van must park on the residential west side of the arterial road so seniors "
                    "do not have to cross 4 lanes of high-speed traffic."
                ),
                "verified_landmark": "Neighborhood Senior Center & West Fairburn Community Lot",
                "active": True,
            },
        ]
    )
    fr_table_ref = f"{PROJECT_ID}.{DATASET_ID}.field_reports"
    client.load_table_from_dataframe(seed_reports, fr_table_ref, job_config=load_cfg).result()
    print(f"   Loaded {fr_table_ref}: {len(seed_reports)} seed rows.")


if __name__ == "__main__":
    build_tables()
