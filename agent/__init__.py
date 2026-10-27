"""Challenge 5 ADK Agent package."""

import os

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f5825262a0a0")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("A4I_DATASET", "a4i_health")

from . import agent
from .agent import build_root_agent, root_agent

__all__ = ["agent", "root_agent", "build_root_agent"]
