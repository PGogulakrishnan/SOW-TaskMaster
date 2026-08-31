"""
SOW-TaskMaster Configuration
=============================
Central configuration for the SOW Signing Automation multi-agent system.
All thresholds, stage definitions, and mock settings live here.
"""

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env (project root).
# The ADK CLI loads .env automatically, but running `python main.py` does
# not, so we load it explicitly here.
load_dotenv(Path(__file__).resolve().parent / ".env")


# ─── SOW Lifecycle Stages ────────────────────────────────────────────────────

class SOWStage(str, Enum):
    """The 6 stages of the SOW signing lifecycle."""
    INTAKE = "INTAKE"
    DRAFTING = "DRAFTING"
    VALIDATION = "VALIDATION"
    APPROVAL = "APPROVAL"
    CUSTOMER_REVIEW = "CUSTOMER_REVIEW"
    SIGNING = "SIGNING"
    COMPLETE = "COMPLETE"


# Stage ordering for the state machine
STAGE_ORDER = [
    SOWStage.INTAKE,
    SOWStage.DRAFTING,
    SOWStage.VALIDATION,
    SOWStage.APPROVAL,
    SOWStage.CUSTOMER_REVIEW,
    SOWStage.SIGNING,
    SOWStage.COMPLETE,
]


# ─── Approval Thresholds ────────────────────────────────────────────────────

# Deals at or above this value require additional executive sign-off
APPROVAL_THRESHOLD_GBP = 50_000

# Standard approvers for deals under the threshold
STANDARD_APPROVERS = ["delivery_manager"]

# Additional approvers for high-value deals (at or above threshold)
EXECUTIVE_APPROVERS = ["delivery_manager", "vp_delivery"]


# ─── Validation Rules ───────────────────────────────────────────────────────

# Commercial: minimum acceptable margin percentage
MIN_MARGIN_PERCENT = 15.0

# Timeline: maximum allowed delivery weeks (feasibility cap)
MAX_DELIVERY_WEEKS = 26

# Timeline: minimum weeks needed per £10K of budget (capacity rule)
WEEKS_PER_10K_GBP = 1.0


# ─── Mock Integration Settings ───────────────────────────────────────────────

# Simulate network delay (seconds) — set to 0 for instant demo
MOCK_DELAY_SECONDS = 0.5

# Simulated customer response: "approve" or "redline"
# For demo: customer requests one redline then approves
CUSTOMER_FIRST_RESPONSE = "redline"
CUSTOMER_REDLINE_REQUEST = "Please extend the warranty period from 12 months to 24 months."
CUSTOMER_SECOND_RESPONSE = "approve"

# Simulated approver response: "approve" or "reject"
APPROVER_RESPONSE = "approve"


# ─── State Store ─────────────────────────────────────────────────────────────

DATA_DIR = "data/cases"


# ─── LLM Settings ───────────────────────────────────────────────────────────

# --- GCP Vertex AI / Gemini Enterprise backend (Option A) ---
# Mirrors the training config: GOOGLE_GENAI_USE_ENTERPRISE=1
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip()
USE_GCP_VERTEX = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("true", "1")
USE_GCP_ENTERPRISE = os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "").strip().lower() in ("true", "1")
USING_GCP_BACKEND = bool(GCP_PROJECT) and (USE_GCP_VERTEX or USE_GCP_ENTERPRISE)

# --- Gemini Developer API key (Option B) ---
# GOOGLE_API_KEY takes priority, then GEMINI_API_KEY (matches google-genai's
# own resolution order).
GEMINI_API_KEY = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()

# Treat placeholder values (e.g. "your_actual_gemini_api_key_here") as no key
if not GEMINI_API_KEY or GEMINI_API_KEY.lower().startswith("your_") or GEMINI_API_KEY.startswith("<"):
    GEMINI_API_KEY = ""

# Gemini model name — override via GEMINI_MODEL in the .env file
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Whether to use the real Gemini API.
#   USE_REAL_LLM=true/false  -> force on/off
#   USE_REAL_LLM=auto        -> on iff credentials are configured (GCP
#                               backend OR an API key is present)
_use_llm_env = os.getenv("USE_REAL_LLM", "auto").strip().lower()
if _use_llm_env == "true":
    USE_REAL_LLM = True
elif _use_llm_env == "false":
    USE_REAL_LLM = False
else:
    USE_REAL_LLM = bool(GEMINI_API_KEY) or USING_GCP_BACKEND
# ─── Signing / webhook mode ───────────────────────────────────────────────────
# "auto"    -> signature confirmed immediately inside the demo
# "webhook" -> case pauses at SIGNING and waits for the mock DocuSign callback
#               (POST /api/webhooks/esign/{case_id} on the dashboard app)
SIGNING_MODE = os.getenv("SIGNING_MODE", "auto").strip().lower()
if SIGNING_MODE not in ("auto", "webhook"):
    SIGNING_MODE = "auto"

# ─── Dashboard / web app ─────────────────────────────────────────────────────
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1").strip()
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

# ─── Console encoding safety (Windows legacy codepages) ──────────────────────
# Agent output contains emoji; print() raises UnicodeEncodeError on Windows
# consoles/pipes using cp1252. Replace unencodable characters instead of
# crashing. config.py is imported by every entry point, so this covers
# main.py, web_app.py, and the test runners.
import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass  # stream already detached or not reconfigurable