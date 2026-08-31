"""Probe which Gemini model IDs actually resolve on this project's Vertex endpoint."""
import os

os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "1"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "my-agent-learning-project-01")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from google import genai  # noqa: E402

client = genai.Client(
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
)

candidates = [
    "gemini-3-flash",
    "gemini-3.0-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-flash-latest",
]

for m in candidates:
    try:
        r = client.models.generate_content(model=m, contents="Reply with exactly: LLM_OK")
        text = (getattr(r, "text", "") or "")[:40].replace("\n", " ")
        print(f"OK   {m} -> {text}")
    except Exception as e:
        first = str(e).split("\n")[0][:140]
        print(f"FAIL {m} -> {first}")
