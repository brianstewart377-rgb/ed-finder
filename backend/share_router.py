"""
Share / OpenGraph router for ED Finder.

Exposes two endpoints used to make shared system links unfurl into
rich-media preview cards in Discord, Reddit, Twitter, Slack, etc.

  GET /s/{id64}              ── HTML page with OG meta tags. Bots stop
                                here and read the meta. Humans get a
                                tiny inline script that 302s them to
                                `/#s={id64}` on the SPA.
  GET /api/share/og/{id64}   ── PNG (1200x630) preview card rendered
                                with Pillow. Lazy: cached in Redis for
                                7 days under  `og:{id64}`.

The router is installed by `main.py` via `app.include_router(...)`.
Adding a router (rather than inlining in main.py) keeps the OG-image
code, which is large and dependency-heavy (Pillow), out of the hot
path and the 2k-line main module.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

import asyncpg
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

router = APIRouter(tags=["share"])

# Bot user-agents we serve OG-tagged HTML to instead of redirecting.
# Anyone NOT in this set gets bounced to the SPA (faster on real users).
BOT_UAS = (
    "discordbot", "twitterbot", "slackbot", "facebookexternalhit",
    "linkedinbot", "redditbot", "telegrambot", "whatsapp", "embedly",
    "googlebot", "bingbot", "applebot", "skypeuripreview", "pinterestbot",
    "iframely", "developers.google.com/+/web/snippet",
)

# Pillow doesn't ship a default font on most slim base images. We try a
# few system paths; if none exist, fall back to PIL's bitmap default
# (ugly but never crashes).
def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _wrap(text: str, max_chars: int) -> list[str]:
    """Naive word-wrap that's fine for one-line rationales (≤ 160 chars)."""
    if not text:
        return []
    words = text.split()
    lines, cur = [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if len(nxt) <= max_chars:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ─────────────────────────────────────────────────────────────────────────
# HTML stop-page for bots
# ─────────────────────────────────────────────────────────────────────────
@router.get("/s/{id64}")
async def share_stop_page(id64: int, request: Request):
    """
    Bots → static HTML with OG/Twitter meta tags pointing at the PNG
    endpoint below. Real users → 302 to the SPA's `#s={id64}` deep-link
    so the existing client-side router takes over.
    """
    ua = (request.headers.get("user-agent") or "").lower()
    is_bot = any(b in ua for b in BOT_UAS)

    base = str(request.base_url).rstrip("/")
    sys_url = f"{base}/#s={id64}"
    img_url = f"{base}/api/share/og/{id64}"

    # Fetch system name + score for human-readable title. If the lookup
    # fails (404 / db down), fall back to a generic title — we still want
    # the preview to render even if the system is unknown.
    name, score, rationale = None, None, None
    try:
        pool = request.app.state.pool  # type: ignore[attr-defined]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT s.name, r.score, r.rationale
                FROM systems s
                LEFT JOIN ratings r ON r.system_id64 = s.id64
                WHERE s.id64 = $1
            """, id64, timeout=5)
            if row:
                name, score, rationale = row["name"], row["score"], row["rationale"]
    except Exception as e:
        log.debug(f"share OG lookup failed for {id64}: {e}")

    title = f"{name or f'System #{id64}'} — ED Finder"
    if score is not None:
        title += f" · score {score}"
    desc = rationale or "Elite Dangerous system rating, exploration data, and economy potential."

    if not is_bot:
        # Real user → bounce to the SPA. Includes a <noscript> fallback
        # link in case JS is off (rare but not zero).
        return RedirectResponse(url=sys_url, status_code=302)

    # Bot → serve OG-tagged HTML.
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_html_escape(title)}</title>
  <meta name="description" content="{_html_escape(desc)}">

  <!-- OpenGraph — Facebook, Discord, Slack, LinkedIn, etc. -->
  <meta property="og:type" content="website">
  <meta property="og:title" content="{_html_escape(title)}">
  <meta property="og:description" content="{_html_escape(desc)}">
  <meta property="og:image" content="{img_url}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="{sys_url}">
  <meta property="og:site_name" content="ED Finder">

  <!-- Twitter Card — Twitter / X -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_html_escape(title)}">
  <meta name="twitter:description" content="{_html_escape(desc)}">
  <meta name="twitter:image" content="{img_url}">

  <link rel="canonical" href="{sys_url}">
</head>
<body>
  <h1>{_html_escape(title)}</h1>
  <p>{_html_escape(desc)}</p>
  <p><a href="{sys_url}">Open in ED Finder</a></p>
</body>
</html>"""
    return HTMLResponse(html)


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ─────────────────────────────────────────────────────────────────────────
# OG image renderer
# ─────────────────────────────────────────────────────────────────────────
@router.get("/api/share/og/{id64}")
async def og_image(id64: int, request: Request):
    """
    Render a 1200×630 PNG preview card for the given system. Cached in
    Redis for 7 days; falls through to live render if cache is missing.
    """
    redis = getattr(request.app.state, "redis", None)
    cache_key = f"og:{id64}"

    # 1. Cache hit — stream straight from Redis.
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(
                    content=cached,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=604800",
                             "X-Cache": "HIT"},
                )
        except Exception as e:
            log.debug(f"og redis read failed: {e}")

    # 2. Live fetch system data.
    name, score, conf, rationale, x, y, z = None, None, None, None, 0.0, 0.0, 0.0
    try:
        pool = request.app.state.pool  # type: ignore[attr-defined]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT s.name, s.x, s.y, s.z,
                       r.score, r.confidence, r.rationale
                FROM systems s
                LEFT JOIN ratings r ON r.system_id64 = s.id64
                WHERE s.id64 = $1
            """, id64, timeout=5)
            if row:
                name      = row["name"]
                score     = row["score"]
                conf      = row["confidence"]
                rationale = row["rationale"]
                x, y, z   = float(row["x"] or 0), float(row["y"] or 0), float(row["z"] or 0)
    except Exception as e:
        log.warning(f"og system lookup failed for {id64}: {e}")

    if not name:
        raise HTTPException(404, f"System {id64} not found")

    # 3. Render the image.
    png = _render_card(
        title=name,
        score=score,
        confidence=conf,
        rationale=rationale,
        coords=(x, y, z),
        id64=id64,
    )

    # 4. Cache for 7 days.
    if redis is not None:
        try:
            await redis.setex(cache_key, 7 * 24 * 3600, png)
        except Exception as e:
            log.debug(f"og redis write failed: {e}")

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800", "X-Cache": "MISS"},
    )


def _render_card(
    title: str,
    score: Optional[int],
    confidence: Optional[float],
    rationale: Optional[str],
    coords: tuple[float, float, float],
    id64: int,
) -> bytes:
    """
    Produce a 1200×630 PNG matching Twitter Card / OG dimensions.

    Layout (left-aligned, dark theme):
      ┌──────────────────────────────────────────────────────────────┐
      │  ED FINDER                                          ◆ 92%    │
      │                                                              │
      │  System Name                                                 │
      │  Coords  -1234.56 / 12.34 / 5678.90 LY                       │
      │                                                              │
      │  ▸ Strong agriculture via 2 ELW + 3 terraformable HMC       │
      │                                                              │
      │                                            ┌──── 87 ────┐   │
      │                                            │  /100      │   │
      │                                            └────────────┘   │
      └──────────────────────────────────────────────────────────────┘
    """
    W, H = 1200, 630
    BG, FG, DIM = (10, 8, 18), (255, 240, 220), (170, 160, 150)
    ORANGE = (255, 170, 60)
    GOLD   = (255, 215, 90)

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Soft warm radial glow on the right (nods to the BH visual on the site).
    # Pillow has no native gradient; we fake it with a few overlapping
    # alpha-blended ellipses, which is fast and good enough.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i, alpha in enumerate([24, 16, 8]):
        rr = 220 + i * 110
        od.ellipse([W - rr, H // 2 - rr, W + rr, H // 2 + rr],
                   fill=(255, 100, 30, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── Header strip (brand top-left + confidence top-right) ──────────
    f_brand = _font(28)
    draw.text((48, 36), "ED FINDER", font=f_brand, fill=ORANGE)
    if confidence is not None:
        pct = int(round(confidence * 100))
        f_conf = _font(26)
        txt = f"◆ {pct}%"
        # Right-align by measuring the text bbox.
        bbox = draw.textbbox((0, 0), txt, font=f_conf)
        tw = bbox[2] - bbox[0]
        col = GOLD if pct >= 90 else ORANGE if pct >= 70 else DIM
        draw.text((W - 48 - tw, 36), txt, font=f_conf, fill=col)

    # ── Title (system name) ───────────────────────────────────────────
    # Truncate long names so the layout never overflows.
    name = (title or f"System #{id64}").strip()
    if len(name) > 36:
        name = name[:33] + "…"
    f_title = _font(72)
    draw.text((48, 110), name, font=f_title, fill=FG)

    # ── Coords subtitle ────────────────────────────────────────────────
    f_sub = _font(22)
    coord_str = f"Coords  {coords[0]:.1f} / {coords[1]:.1f} / {coords[2]:.1f} LY"
    draw.text((48, 200), coord_str, font=f_sub, fill=DIM)

    # ── Rationale (wrapped) ────────────────────────────────────────────
    f_rat = _font(28)
    rat   = (rationale or "Elite Dangerous system — open in ED Finder for the full briefing.")
    lines = _wrap(rat, max_chars=58)[:3]   # cap at 3 wrapped lines
    y0 = 280
    for i, ln in enumerate(lines):
        prefix = "▸ " if i == 0 else "   "
        draw.text((48, y0 + i * 42), prefix + ln, font=f_rat, fill=FG)

    # ── Score badge (bottom-right) ─────────────────────────────────────
    if score is not None:
        bx, by, bw, bh = W - 280, H - 200, 232, 152
        # Badge background — orange-tinted card with a thin border.
        draw.rectangle([bx, by, bx + bw, by + bh],
                       fill=(35, 22, 10), outline=ORANGE, width=3)
        f_score = _font(96)
        s_txt = str(score)
        bbox = draw.textbbox((0, 0), s_txt, font=f_score)
        tw = bbox[2] - bbox[0]
        # Pick the colour from the same palette the frontend uses.
        if score >= 80:
            col = GOLD
        elif score >= 60:
            col = ORANGE
        elif score >= 40:
            col = (250, 204, 21)
        else:
            col = DIM
        draw.text((bx + (bw - tw) / 2 - 4, by + 16), s_txt, font=f_score, fill=col)
        f_sm = _font(22)
        draw.text((bx + bw / 2 - 32, by + bh - 36), "/100", font=f_sm, fill=DIM)

    # ── Footer URL ─────────────────────────────────────────────────────
    f_foot = _font(20)
    draw.text((48, H - 50), f"ed-finder.app  /  #s={id64}", font=f_foot, fill=DIM)

    # Encode to PNG bytes.
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
