"""
Build a one-page A4-landscape architecture PDF from the README Mermaid diagrams.

- Reads the ```mermaid blocks from README.md (expected: 2).
- Renders each to PNG via mermaid.ink (no local Chromium needed).
- Composes a single branded page with fig captions and saves it as
  docs/SOW-TaskMaster-Architecture.pdf.

Requirements: pip install pillow   (network needed for mermaid.ink)

Run:  python scripts/build_architecture_pdf.py
"""

import base64
import io
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, "README.md")
DOCS = os.path.join(REPO, "docs")
OUT = os.path.join(DOCS, "SOW-TaskMaster-Architecture.pdf")

MMD_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.S)

# Strip emoji/variation-selectors for the headless renderer so labels are
# clean text instead of tofu boxes (keep the emoji in the README itself).
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # misc symbols & pictographs incl. emoji
    "\u2600-\u27BF"          # misc symbols / dingbats
    "\uFE0F"                 # variation selector-16
    "\u200D"                 # zero-width joiner
    "]+"
)


def strip_emoji(text: str) -> str:
    return EMOJI_RE.sub("", text)


def fetch(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_png(src: str, timeout: int = 90) -> bytes:
    """Render a Mermaid diagram to PNG via mermaid.ink (white background)."""
    plain = base64.b64encode(src.encode("utf-8")).decode("ascii")
    url = f"https://mermaid.ink/img/{plain}?bgColor=FFFFFF"
    try:
        return fetch(url, timeout)
    except Exception:
        # url-safe fallback
        safe = base64.urlsafe_b64encode(src.encode("utf-8")).decode("ascii")
        return fetch(f"https://mermaid.ink/img/{safe}?bgColor=FFFFFF", timeout)


def font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def center_text(draw: ImageDraw, y: int, text: str, fnt, fill, width: int):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) / 2, y), text, font=fnt, fill=fill)


def main() -> int:
    md = open(README, encoding="utf-8").read()
    blocks = [m.group(1).strip() for m in MMD_RE.finditer(md)]
    if len(blocks) < 2:
        print(f"ERROR: expected 2 mermaid diagrams in README, found {len(blocks)}")
        return 1

    print(f"Rendering {len(blocks)} diagrams via mermaid.ink ...")
    pngs = [fetch_png(strip_emoji(b)) for b in blocks]
    imgs = [Image.open(io.BytesIO(p)).convert("RGB") for p in pngs]
    for i, img in enumerate(imgs, 1):
        print(f"  diagram {i}: PNG {len(pngs[i-1])} bytes, {img.size[0]}x{img.size[1]}")

    # ── A4 landscape @ 150 dpi ──────────────────────────────────────────────
    W, H = 1754, 1240  # 11.69in x 8.27in
    margin = 52
    title_h = 92
    sub_h = 46
    cap_h = 30
    foot_h = 40
    gap = 28
    avail_w = W - 2 * margin
    avail_h = H - margin - title_h - sub_h - foot_h - 2 * cap_h - gap * 3

    scale = min(
        avail_w / max(i.width for i in imgs),
        avail_h / sum(i.height for i in imgs),
    )
    scaled = [i.resize((int(i.width * scale), int(i.height * scale))) for i in imgs]
    print(f"  fit scale {scale:.3f} -> sizes {[i.size for i in scaled]}")

    # ── fonts ───────────────────────────────────────────────────────────────
    f_title = font(r"C:\Windows\Fonts\arialbd.ttf", 46)
    f_sub = font(r"C:\Windows\Fonts\arial.ttf", 24)
    f_cap = font(r"C:\Windows\Fonts\ariali.ttf", 19)
    f_foot = font(r"C:\Windows\Fonts\arial.ttf", 17)

    NAVY, INK, GREY, ACCENT, BORDER = "#0f172a", "#1e293b", "#64748b", "#38bdf8", "#cbd5e1"

    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)

    # ── header ──────────────────────────────────────────────────────────────
    center_text(draw, 40, "SOW-TaskMaster — Multi-Agent SOW Signing Automation",
                f_title, NAVY, W)
    center_text(draw, 100, "Task Master hackathon  ·  Google ADK + Gemini  ·  one-page architecture",
                f_sub, GREY, W)
    draw.rectangle([margin, 158, W - margin, 158 + 4], fill=ACCENT)  # accent rule

    # ── diagrams + captions ─────────────────────────────────────────────────
    CAPTIONS = [
        "Fig 1 — Agent graph: orchestrator, supporting agents, mock integration layer, HITL",
        "Fig 2 — Lifecycle: the resumable six-stage state machine",
    ]
    y = 200
    for img, cap in zip(scaled, CAPTIONS):
        x = (W - img.width) // 2
        draw.rectangle([x - 2, y - 2, x + img.width + 2, y + img.height + 2],
                       outline=BORDER, width=2)
        canvas.paste(img, (x, y))
        y += img.height + 10
        center_text(draw, y, cap, f_cap, INK, W)
        y += cap_h - 6 + gap

    # ── footer ──────────────────────────────────────────────────────────────
    draw.line([margin, H - foot_h - 14, W - margin, H - foot_h - 14], fill=BORDER, width=1)
    center_text(draw, H - foot_h - 4,
                "Generated from README.md Mermaid diagrams · docs/SOW-TaskMaster-Architecture.pdf",
                f_foot, GREY, W)

    os.makedirs(DOCS, exist_ok=True)
    canvas.save(OUT, "PDF", resolution=150)
    preview = os.path.join(DOCS, "SOW-TaskMaster-Architecture-preview.png")
    canvas.save(preview, "PNG")
    print(f"saved: {OUT}")
    print(f"preview: {preview}")

    # ── verify (bytes-level; Pillow's PDF reader needs Ghostscript) ──────────
    raw = open(OUT, "rb").read()
    head = raw[:5]
    pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
    print(f"verify: header={head!r}, {len(raw)} bytes, page count={pages}")
    return 0 if (head == b"%PDF-" and pages == 1) else 2


if __name__ == "__main__":
    sys.exit(main())