"""
LLM Utilities
==============
Shared helpers for invoking ADK agents backed by the Gemini LLM.

These helpers are only used when `USE_REAL_LLM` is True. They run a single
`LlmAgent` through an `InMemoryRunner` and return the agent raw text reply,
plus a tolerant JSON parser for agents that return structured data.
"""

import json
import re

from google.adk.runners import InMemoryRunner
from google.genai import types

_APP_NAME = "sow-taskmaster"
_USER_ID = "demo-user"
_RUNNERS: dict[str, InMemoryRunner] = {}


def _get_runner(agent) -> InMemoryRunner:
    """Return a cached InMemoryRunner for the given agent."""
    runner = _RUNNERS.get(agent.name)
    if runner is None:
        runner = InMemoryRunner(agent=agent, app_name=_APP_NAME)
        _RUNNERS[agent.name] = runner
    return runner


def _extract_text(events) -> str:
    """Collect the last text the agent produced across all events."""
    text = ""
    for event in events:
        if getattr(event, "content", None) and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    text = part.text
    return text.strip()


def run_agent(agent, user_content: str) -> str:
    """
    Run an ADK agent synchronously with a single user message.

    Args:
        agent: The ADK LlmAgent to invoke.
        user_content: The user prompt text.

    Returns:
        The agent's final response text (stripped), or "" on failure.
    """
    runner = _get_runner(agent)
    session_service = runner.session_service
    session = session_service.create_session_sync(app_name=_APP_NAME, user_id=_USER_ID)

    events = list(
        runner.run(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=user_content)],
            ),
        )
    )
    return _extract_text(events)


def parse_json(text: str):
    """
    Tolerantly parse a JSON object out of an LLM reply.

    LLMs often wrap JSON in ``` fences or add prose around it. This tries a
    direct parse first, then extracts the first {...} block.

    Returns:
        A dict, or None if no valid JSON object was found.
    """
    if not text:
        return None

    # 1) direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) strip markdown fences
    fenced = re.sub(r"```(?:json)?", "", text).strip()
    try:
        obj = json.loads(fenced)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 3) first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            return None

    return None