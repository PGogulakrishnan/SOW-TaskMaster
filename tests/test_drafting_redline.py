"""Regression test: customer redline must extend the warranty to the TARGET months."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force mock/deterministic fill so we test OUR code, not the LLM.
os.environ["USE_REAL_LLM"] = "false"

from models import SOWCase
from agents.drafting_agent import generate_draft
from agents.intake_agent import process_intake


SAMPLE = """
Project: Test Migration
Customer: TestCorp
Budget: 30000 GBP
Timeline: 12 weeks
Scope: migrate stuff.
"""

case = SOWCase(case_id="SOW-TEST1")
case = process_intake(case, SAMPLE)
case.customer_redlines.append("Please extend the warranty period from 12 months to 24 months.")
case = generate_draft(case)

assert "Warranty Period:        24 months" in case.draft_sow_text, "draft must contain 24-month warranty"
assert case.draft_version == 1

# The logged reasoning must reflect the target period (24), not the starting 12.
last = case.timeline[-1]
assert last.agent_name == "DraftingAgent"
assert "Warranty set to 24 months" in last.reasoning, f"reasoning wrong: {last.reasoning}"

print("PASS: redline warranty extension applied correctly (24 months)")