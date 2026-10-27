"""Google-managed BigQuery MCP server configuration for Challenge 5.

Connects ADK agents to Google's managed BigQuery MCP endpoint
(`https://bigquery.googleapis.com/mcp`) using Application Default Credentials.
Only read-only inspection and query tools are exposed to evidence-gathering
analysts so they can inspect schemas and run parameterized SQL against
`a4i_health` without modifying tables.
"""

from __future__ import annotations

import os
import google.auth
import google.auth.transport.requests
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
DATASET_ID = os.environ.get("A4I_DATASET", "a4i_health")
BIGQUERY_MCP_URL = "https://bigquery.googleapis.com/mcp"


def get_bigquery_mcp_headers() -> dict[str, str]:
    """Acquire fresh ADC bearer token and project header for Google's BigQuery MCP."""
    creds, detected_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/bigquery"]
    )
    if not creds.valid or creds.expired or not creds.token:
        creds.refresh(google.auth.transport.requests.Request())
    project = PROJECT_ID or detected_project or "qwiklabs-gcp-04-f5825262a0a0"
    return {
        "Authorization": f"Bearer {creds.token}",
        "x-goog-user-project": project,
    }


def create_bigquery_mcp_toolset(
    tool_filter: list[str] | None = None,
    readonly: bool = True,
) -> McpToolset:
    """Create an McpToolset connected to the Google-managed BigQuery MCP server."""
    if tool_filter is None and readonly:
        tool_filter = [
            "execute_sql_readonly",
            "get_table_info",
            "get_dataset_info",
            "list_table_ids",
        ]
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=BIGQUERY_MCP_URL,
            headers=get_bigquery_mcp_headers(),
        ),
        tool_filter=tool_filter,
    )
