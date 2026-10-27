"""Unit & integration tests for Challenge 5 custom tools, BigQuery MCP toolset, and Pass 1 -> Pass 2 audit loop."""

from __future__ import annotations

import asyncio

from agent.mcp_config import create_bigquery_mcp_toolset
from agent.tools import (
    analyze_burden_and_barriers,
    analyze_regional_context_and_surveillance,
    analyze_spatial_access_and_shortages,
    audit_candidate_plan,
    get_field_reports,
    rank_candidate_tracts,
)


class DummyActions:
    def __init__(self) -> None:
        self.escalate = False


class DummyContext:
    def __init__(self) -> None:
        self.state: dict = {}
        self.actions = DummyActions()


def test_bigquery_mcp_toolset() -> None:
    async def _check() -> list[str]:
        mcp = create_bigquery_mcp_toolset(readonly=True)
        tools = await mcp.get_tools()
        names = sorted([t.name for t in tools])
        await mcp.close()
        return names

    tool_names = asyncio.run(_check())
    assert "execute_sql_readonly" in tool_names
    assert "get_table_info" in tool_names
    assert "list_table_ids" in tool_names
    print("MCP toolset verified:", tool_names)


def test_evidence_tools_and_audit_loop() -> None:
    ctx = DummyContext()

    burden = analyze_burden_and_barriers("13121", ctx)
    assert burden["county_summary"]["tract_count"] == 326
    assert len(burden["column_traps_handled"]) >= 4

    access = analyze_spatial_access_and_shortages("13121", ctx)
    assert access["access_summary"]["total_tracts"] == 326
    assert access["federal_hpsa_findings"]["shortage_areas_count"] == 0
    assert access["federal_hpsa_findings"]["shortage_facilities_count"] == 6
    assert (
        access["synthetic_shortage_tracts_findings"]["summary"]["synthetic_shortage_areas_count"]
        == 93
    )
    assert (
        access["synthetic_shortage_tracts_findings"]["summary"]["max_synthetic_shortage_score"]
        == 83.1
    )
    assert len(access["limited_capacity_or_restricted_sites_in_care_sites"]) > 0

    context = analyze_regional_context_and_surveillance("13121", ctx)
    assert context["exposure_tracts_analysis"]["join_asymmetry_finding"]["exposure_tracts_rows"] == 327
    assert context["exposure_tracts_analysis"]["join_asymmetry_finding"]["burden_tracts_rows"] == 326
    assert context["exposure_tracts_analysis"]["p90_p10_ratio"] < 1.10
    assert "weeks" in context["disease_weekly_analysis"]["true_temporal_grain"]

    # Pass 1: Naive distance + uninsured ranking
    p1 = rank_candidate_tracts(strategy="auto", tool_context=ctx)
    assert p1["strategy_used"] == "pass1_naive_access"
    p1_ids = [s["geo_id"] for s in p1["selected_stops"]]
    assert p1_ids == ["13121011431", "13121011421", "13121011430", "13121011432"]

    # Audit Pass 1 -> Must REJECT (including synthetic_shortage_tracts cross-border check)
    a1 = audit_candidate_plan(tool_context=ctx)
    assert a1["verdict"] == "REJECT"
    assert a1["violations_count"] >= 3
    assert any(v["type"] == "CROSS_BORDER_EDGE_ARTIFACT" for v in a1["violations"])
    assert ctx.actions.escalate is False
    assert ctx.state["audit_verdict"] == "REJECT"

    # Pass 2: Automatically switches to pass2_audited_composite after REJECT
    p2 = rank_candidate_tracts(strategy="auto", tool_context=ctx)
    assert p2["strategy_used"] == "pass2_audited_composite"
    p2_ids = [s["geo_id"] for s in p2["selected_stops"]]
    assert p2_ids == ["13121007603", "13121010214", "13121007400", "13121002300"]
    assert set(p1_ids).isdisjoint(set(p2_ids))
    assert len(p2["runner_up_tracts_not_selected"]) >= 4
    # Verify synthetic_shortage_tracts metrics are present on Pass 2 stops
    stop2_metrics = next(s for s in p2["selected_stops"] if s["geo_id"] == "13121010214")["metrics"]
    assert stop2_metrics["synthetic_shortage_score"] == 83.1
    assert stop2_metrics["is_synthetic_shortage_area"] is True

    # Audit Pass 2 -> Must APPROVE and escalate
    a2 = audit_candidate_plan(tool_context=ctx)
    assert a2["verdict"] == "APPROVE"
    assert a2["violations"] == []
    assert ctx.actions.escalate is True
    assert (
        a2["post_hoc_equity_and_demographic_audit"]["plan_vs_county_baseline"][
            "plan_selected_synthetic_shortage_areas_count"
        ]
        == 3
    )
    assert (
        a2["post_hoc_equity_and_demographic_audit"]["plan_vs_county_baseline"][
            "plan_weighted_pct_minority"
        ]
        > 80.0
    )

    reports = get_field_reports("13121", ctx)
    assert reports["active_field_reports_count"] >= 3
    print("All tool & Pass 1 -> Pass 2 self-correction assertions passed!")


if __name__ == "__main__":
    test_bigquery_mcp_toolset()
    test_evidence_tools_and_audit_loop()
