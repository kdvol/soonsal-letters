#!/usr/bin/env python3
"""
순살 Letters deploy script
Usage: python3 deploy.py <file1> [file2] ...

Example:
  python3 deploy.py ~/Downloads/순살브리핑_20260302.html ~/Downloads/순살크립토_20260302.html

Automatically:
  1. Detects content type from filename
  2. Copies to correct repo directory with proper naming
  3. Extracts keywords from story titles
  4. Updates main index.html (Hero, today sections)
  5. Updates archive indexes (newsletters, cardnews, english)
  6. Generates 1080×1080 PNG for cardnews (card, crypto-card)
  7. Git add, commit, push
  8. Uploads PNGs to Cloudflare R2 (cardnews only)
  9. Posts Instagram carousel (cardnews only)

Requirements for Instagram publishing (optional — gracefully skips if missing):
  - ~/instagram_pipeline/upload_r2.py (R2 upload module)
  - ~/instagram_pipeline/post_instagram.py (Instagram Graph API module)
"""

import sys
import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════
# Dashboard webhook
# ═══════════════════════════════════════════

DASHBOARD_URL = "https://soonsal-ops.kd-d0a.workers.dev/status"

def notify_dashboard(pipeline, step, status="done", count=None, version=None):
    """대시보드 상태 자동 업데이트."""
    try:
        import urllib.request, json
        data = json.dumps({
            "date": datetime.now().strftime("%Y%m%d"),
            "pipeline": pipeline,
            "step": step,
            "status": status,
            "count": count,
            "version": version,
        }).encode()
        req = urllib.request.Request(DASHBOARD_URL, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # 대시보드 실패해도 배포에 영향 없음

# ctype → dashboard 알림 목록 (여러 단계를 한번에 보고)
# 각 항목: (pipeline, step)
DASHBOARD_MAP = {
    "briefing":    [("briefing", "newsletter"), ("briefing", "publish_site")],
    "crypto":      [("crypto",   "newsletter"), ("crypto",   "publish_site")],
    "card":        [("briefing", "cardnews"),   ("briefing", "publish_site")],
    "crypto-card": [("crypto",   "cardnews"),   ("crypto",   "publish_site")],
    "english":     [("english",  "article"),    ("english",  "publish_site")],
}

# ═══════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════

REPO = Path.home() / "kdvol.github.io"

# Type detection (order matters: longer prefix first)
TYPES = [
    ("순살크립토카드뉴스", "crypto-card", "cardnews",    "-crypto"),
    ("순살카드뉴스",       "card",        "cardnews",    ""),
    ("순살크립토",         "crypto",      "newsletters", "-crypto"),
    ("순살브리핑",         "briefing",    "newsletters", ""),
    ("SoonsalCrypto",     "english",     "english",     ""),
]

# Tags for main index.html
MAIN_TAGS = {
    "briefing":    '<span class="tag" style="background:#F07040; color:#fff;">브리핑</span>',
    "crypto":      '<span class="tag tag-crypto">Crypto</span>',
    "card":        '<span class="tag tag-card">Card</span>',
    "crypto-card": '<span class="tag tag-card">Card</span>',
    "english":     '<span class="tag tag-en">EN</span>',
}

# Tags for archive indexes
ARCHIVE_TAGS = {
    "briefing":    '<span class="tag tag-briefing">브리핑</span>',
    "crypto":      '<span class="tag tag-crypto">Crypto</span>',
    "card":        '<span class="tag tag-card">Card</span>',
    "crypto-card": '<span class="tag tag-card tag-crypto">Card · Crypto</span>',
    "english":     '<span class="tag tag-en">EN</span>',
}

# Content type labels
LABELS = {
    "briefing":    "순살브리핑",
    "crypto":      "순살크립토",
    "card":        "순살카드뉴스",
    "crypto-card": "순살크립토카드뉴스",
    "english":     "",
}

# Display order within today-grid
ORDER = {"briefing": 0, "crypto": 1, "card": 2, "crypto-card": 3, "english": 4}


# ═══════════════════════════════════════════
# Cloudflare Web Analytics
# ═══════════════════════════════════════════

CF_ANALYTICS_TOKEN = "d6a07341c2bf438d8ef7f9209a0e9a81"
CF_ANALYTICS_SNIPPET = (
    '<!-- Cloudflare Web Analytics -->'
    '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
    f'data-cf-beacon=\'{{"token": "{CF_ANALYTICS_TOKEN}"}}\'></script>'
    '<!-- End Cloudflare Web Analytics -->'
)


def inject_analytics_beacon(filepath):
    """Inject Cloudflare Web Analytics beacon into HTML file if not already present."""
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    if "cloudflareinsights" in html:
        return  # Already has beacon

    if "</body>" in html:
        html = html.replace("</body>", f"{CF_ANALYTICS_SNIPPET}\n</body>")
    elif "</html>" in html:
        html = html.replace("</html>", f"{CF_ANALYTICS_SNIPPET}\n</html>")
    else:
        return  # No closing tag to inject before

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)


# ═══════════════════════════════════════════
# Back Link Fix
# ═══════════════════════════════════════════

BACK_LINK_NEW = (
    '<a href="https://soonsal.com" '
    "style=\"display:inline-flex;align-items:center;gap:6px;"
    "font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;"
    "font-size:14px;font-weight:700;color:#E55A00;"
    "text-decoration:none;padding:6px 0;\" "
    "onmouseover=\"this.style.color='#CC4E00'\" "
    "onmouseout=\"this.style.color='#E55A00'\">"
    "← 순살 홈</a>"
)


def fix_back_link(filepath):
    """Replace back-to-letters link with ← 순살 홈 (orange style)."""
    import re as _re

    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    if "<!-- BACK TO LETTERS -->" not in html:
        return

    # Match the entire <a>...</a> inside the back-to-letters div
    new_html = _re.sub(
        r'(<div[^>]*id="back-to-letters"[^>]*>\s*)<a[^>]*>.*?</a>',
        r'\1' + BACK_LINK_NEW,
        html,
        count=1,
        flags=_re.DOTALL,
    )

    if new_html != html:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_html)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def detect_type(filename):
    """Detect content type from filename pattern."""
    for prefix, ctype, directory, suffix in TYPES:
        if prefix in filename:
            return ctype, directory, suffix
    return None, None, None


def extract_date(filename):
    """Extract date components from filename.
    '순살브리핑_20260302.html' → ('2026', '0302', '2026.03.02')
    """
    m = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        return yyyy, mm + dd, f"{yyyy}.{mm}.{dd}"
    return None, None, None


def extract_keywords(html, ctype):
    """Extract display title from HTML content for index entry.

    Priority:
      1. <title> tag — strip " — 순살X YYYY.MM.DD" suffix (v16)
      2. <meta name="soonsal-keywords"> fallback (SEO keywords)
      3. <h2 class="story-title"> extraction (briefing, crypto)
    """
    # ── Priority 1: <title> tag (v16 — meme title for index) ──
    m = re.search(r"<title>(.*?)</title>", html)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        # "밈 제목 — 순살브리핑 2026.03.04" → "밈 제목"
        # rsplit: 마지막 " — " 기준으로만 분리 (제목 안의 — 는 보존)
        parts = t.rsplit(" — ", 1)
        if len(parts) == 2 and ("순살" in parts[1] or "Soonsal" in parts[1]):
            return parts[0].strip()
        # 카드뉴스 등 " — " 없는 경우 전체 반환
        return t

    # ── Priority 2: soonsal-keywords fallback (SEO) ──
    m = re.search(r'<meta\s+name="soonsal-keywords"\s+content="([^"]+)"', html)
    if m:
        return m.group(1).strip()

    # ── Priority 3: story-title extraction (briefing / crypto) ──
    titles = re.findall(r'<h2 class="story-title">(.*?)</h2>', html)
    if titles:
        kws = []
        for t in titles:
            clean = re.sub(r"<[^>]+>", "", t).strip()
            for sep in [" — ", "—"]:
                if sep in clean:
                    clean = clean.split(sep)[0].strip()
                    break
            else:
                clean = clean[:40].strip()
            kws.append(clean)
        return ", ".join(kws)

    return "Untitled"


def build_link(href, tag, label, keywords):
    """Build an <a> tag for the index."""
    text = f"{label} · {keywords}" if label else keywords
    return f'<a href="{href}" style="display:flex; align-items:center; gap:10px;">{tag}{text}</a>'


def get_hero_info(content):
    """Get current Hero date from main index."""
    m = re.search(r"Latest &mdash; (\d{4})\.(\d{2})\.(\d{2})", content)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        return yyyy, mm + dd, f"{yyyy}.{mm}.{dd}"
    return None, None, None


def get_first_today_date(content):
    """Get date of the first (non-padded) today section."""
    m = re.search(
        r'<div class="today">\n  <div class="today-title">'
        r"(\d{4}\.\d{2}\.\d{2}) 전체 콘텐츠</div>",
        content,
    )
    return m.group(1) if m else None


# ═══════════════════════════════════════════
# Main index update
# ═══════════════════════════════════════════

def update_main_index(items, date_fmt, has_briefing, yyyy, mmdd):
    """Update the main index.html."""
    path = REPO / "index.html"
    with open(path, "r") as f:
        c = f.read()

    date_exists = f"{date_fmt} 전체 콘텐츠" in c
    old_yyyy, old_mmdd, old_date_fmt = get_hero_info(c)

    # ── Step 1: Briefing → update Hero + add old briefing link ──
    if has_briefing and old_yyyy and old_mmdd:
        # Update Hero label & iframe
        c = c.replace(
            f"Latest &mdash; {old_date_fmt}",
            f"Latest &mdash; {date_fmt}",
        )
        c = c.replace(
            f'/newsletters/{old_yyyy}/{old_mmdd}.html" title="순살브리핑 최신호"',
            f'/newsletters/{yyyy}/{mmdd}.html" title="순살브리핑 최신호"',
        )

        # Add old briefing link to old Hero date's today section
        old_brief_path = REPO / "newsletters" / old_yyyy / f"{old_mmdd}.html"
        if old_brief_path.exists():
            with open(old_brief_path) as f:
                old_html = f.read()
            old_kw = extract_keywords(old_html, "briefing")
            old_brief_link = build_link(
                f"/newsletters/{old_yyyy}/{old_mmdd}.html",
                MAIN_TAGS["briefing"],
                "순살브리핑",
                old_kw,
            )
            # Remove existing briefing link for this date if present (dedup)
            old_brief_href = f"/newsletters/{old_yyyy}/{old_mmdd}.html"
            lines = c.split('\n')
            c = '\n'.join(line for line in lines if not (line.strip().startswith(f'<a href="{old_brief_href}"') and '브리핑' in line))
            # Insert at beginning of old date's today-grid
            grid_marker = (
                f"{old_date_fmt} 전체 콘텐츠</div>\n"
                f'  <div class="today-grid" style="grid-template-columns:1fr; gap:10px;">\n'
            )
            pos = c.find(grid_marker)
            if pos >= 0:
                insert_at = pos + len(grid_marker)
                c = c[:insert_at] + f"    {old_brief_link}\n" + c[insert_at:]

    # ── Step 2: Create or append to today section ──
    if not date_exists:
        # Build new today block (non-briefing items only)
        non_brief = sorted(
            [i for i in items if i["type"] != "briefing"],
            key=lambda x: ORDER[x["type"]],
        )

        new_today = None
        if non_brief:
            links = "\n".join(
                f"    {build_link('/' + i['deploy_path'], MAIN_TAGS[i['type']], LABELS[i['type']], i['keywords'])}"
                for i in non_brief
            )
            new_today = (
                f'<div class="today">\n'
                f'  <div class="today-title">{date_fmt} 전체 콘텐츠</div>\n'
                f'  <div class="today-grid" style="grid-template-columns:1fr; gap:10px;">\n'
                f"{links}\n"
                f"  </div>\n"
                f"</div>"
            )

        # Demote current first today → padding-top:0
        current_date = get_first_today_date(c)
        if current_date:
            old_hdr = (
                f'<div class="today">\n'
                f'  <div class="today-title">{current_date} 전체 콘텐츠</div>'
            )
            new_hdr = (
                f'<div class="today" style="padding-top:0;">\n'
                f'  <div class="today-title">{current_date} 전체 콘텐츠</div>'
            )
            c = c.replace(old_hdr, new_hdr)

            # Insert new today before demoted section
            if new_today:
                c = c.replace(new_hdr, f"{new_today}\n\n{new_hdr}")
    else:
        # Date exists → clean existing links of same type, then insert fresh
        for item in sorted(items, key=lambda x: ORDER[x["type"]]):
            if item["type"] == "briefing":
                continue
            # Remove existing link for same deploy_path (dedup)
            old_link_pattern = f'    <a href="/{item["deploy_path"]}"'
            lines = c.split('\n')
            c = '\n'.join(line for line in lines if not line.strip().startswith(f'<a href="/{item["deploy_path"]}"'))
            # Build fresh link
            link = build_link(
                "/" + item["deploy_path"],
                MAIN_TAGS[item["type"]],
                LABELS[item["type"]],
                item["keywords"],
            )
            pos = c.find(f"{date_fmt} 전체 콘텐츠")
            if pos >= 0:
                grid_end = c.find("  </div>\n</div>", pos)
                if grid_end >= 0:
                    c = c[:grid_end] + f"    {link}\n" + c[grid_end:]

    with open(path, "w") as f:
        f.write(c)
    print("  ✅ index.html")


# ═══════════════════════════════════════════
# Archive index update
# ═══════════════════════════════════════════

def update_archive_index(item):
    """Update the relevant archive index (newsletters, cardnews, or english)."""
    archive_path = REPO / item["directory"] / "index.html"
    if not archive_path.exists():
        print(f"  ⚠️  {item['directory']}/index.html not found, skipping")
        return

    with open(archive_path, "r") as f:
        c = f.read()

    # Archive uses date without "전체 콘텐츠"
    date_str = item["date_formatted"]
    date_exists = f'<div class="today-title">{date_str}</div>' in c

    link = build_link(
        "/" + item["deploy_path"],
        ARCHIVE_TAGS[item["type"]],
        LABELS[item["type"]],
        item["keywords"],
    )

    if date_exists:
        # Clean existing link for same deploy_path, then insert fresh (dedup)
        lines = c.split('\n')
        c = '\n'.join(line for line in lines if not line.strip().startswith(f'<a href="/{item["deploy_path"]}"'))
        pos = c.find(f'<div class="today-title">{date_str}</div>')
        if pos >= 0:
            grid_end = c.find("    </div>\n  </div>", pos)
            if grid_end >= 0:
                c = c[:grid_end] + f"      {link}\n" + c[grid_end:]
    else:
        # New date section → insert before first <div class="today">
        first_today = c.find('  <div class="today">')
        if first_today >= 0:
            new_section = (
                f'  <div class="today">\n'
                f'    <div class="today-title">{date_str}</div>\n'
                f'    <div class="today-grid" style="grid-template-columns:1fr; gap:10px;">\n'
                f"      {link}\n"
                f"    </div>\n"
                f"  </div>\n\n"
            )
            c = c[:first_today] + new_section + c[first_today:]

    with open(archive_path, "w") as f:
        f.write(c)
    print(f"  ✅ {item['directory']}/index.html")


# ═══════════════════════════════════════════
# Cardnews PNG generation
# ═══════════════════════════════════════════

CARDNEWS_TYPES = {"card", "crypto-card"}

GOOGLE_FONT_LINK = '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">'


def generate_cardnews_png(filepath, ctype):
    """Generate 1080×1080 PNG cards from cardnews HTML.
    
    Captures at device_scale_factor=4 (2160×2160) then Lanczos downscale
    to 1080×1080 for sharp text rendering with proper font weights.
    
    Returns: list of Path objects for generated PNGs, or empty list on failure.
    """
    if ctype not in CARDNEWS_TYPES:
        return []

    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError:
        print("  ⚠️  PNG 생성 스킵 (playwright 또는 Pillow 미설치)")
        print("     pip install playwright Pillow && python3 -m playwright install chromium")
        return []

    filepath = Path(filepath).resolve()
    stem = filepath.stem
    out_dir = filepath.parent / f"{stem}_png"

    # 이미 PNG 폴더 있으면 재생성 스킵
    existing = sorted(out_dir.glob("card_*.png")) if out_dir.exists() else []
    if existing:
        print(f"  ♻️  기존 PNG 재활용 ({len(existing)}장) → {out_dir}")
        return existing

    out_dir.mkdir(exist_ok=True)

    # Read HTML and inject Google Fonts for proper bold rendering
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    if "fonts.googleapis.com" not in html:
        html = html.replace("</head>", f"{GOOGLE_FONT_LINK}\n</head>")

    tmp_html = filepath.parent / f"_tmp_{filepath.name}"
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html)

    png_paths = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 540, "height": 4000},
                device_scale_factor=4,
            )
            page.goto(f"file://{tmp_html}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)  # Wait for font loading

            cards = page.query_selector_all(".card")
            print(f"  📸 {len(cards)} cards → PNG")

            for i, card in enumerate(cards):
                tmp_png = out_dir / f"tmp_{i+1:02d}.png"
                final_png = out_dir / f"card_{i+1:02d}.png"

                card.screenshot(path=str(tmp_png))
                img = Image.open(tmp_png)
                img_resized = img.resize((1080, 1080), Image.LANCZOS)
                img_resized.save(str(final_png), "PNG", optimize=True)
                tmp_png.unlink()

                png_paths.append(final_png)
                print(f"     ✅ card_{i+1:02d}.png ({final_png.stat().st_size:,} bytes)")

            browser.close()
    finally:
        tmp_html.unlink(missing_ok=True)

    print(f"  📁 PNGs → {out_dir}")
    return png_paths


# ═══════════════════════════════════════════
# Instagram Publishing (R2 + Instagram API)
# ═══════════════════════════════════════════

INSTAGRAM_PIPELINE = Path.home() / "instagram_pipeline"

# R2 config
R2_PUBLIC_URL = "https://pub-cb0321b52a854a95af8d6bb1688b2ecd.r2.dev"

# Instagram captions
IG_CAPTIONS = {
    "card": (
        "순살브리핑 카드뉴스 {date_fmt}\n\n"
        "{summary}\n\n"
        "#순살브리핑 #금융 #경제 #투자 #주식 #시장분석 "
        "#글로벌경제 #매크로 #금융뉴스 #경제공부"
    ),
    "crypto-card": (
        "순살크립토 카드뉴스 {date_fmt}\n\n"
        "{summary}\n\n"
        "#순살크립토 #비트코인 #크립토 #블록체인 #Web3 "
        "#금융 #투자 #BTC #ETF #암호화폐"
    ),
}


def parse_cardnews_content(html: str) -> list[dict]:
    """카드뉴스 HTML에서 각 카드의 제목 + 핵심 본문 추출."""
    import re as _re
    results = []
    card_blocks = _re.findall(
        r'<div[^>]*class="[^"]*\bcard\b[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bcard\b|</body|$)',
        html, _re.DOTALL
    )
    for block in card_blocks:
        title_m = _re.search(r'<(?:h[1-4])[^>]*>(.*?)</(?:h[1-4])>', block, _re.DOTALL)
        title = _re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
        paras = _re.findall(r'<p[^>]*>(.*?)</p>', block, _re.DOTALL)
        body = " ".join(
            _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", "", p)).strip()
            for p in paras if p.strip()
        )[:150]
        if title or body:
            results.append({"title": title[:60], "body": body})
    return results[:10]


def generate_ig_caption_ai(html: str, ctype: str, date_fmt: str) -> str:
    """Claude Haiku API로 Instagram 캡션 2~3문장 생성.
    ANTHROPIC_API_KEY 없으면 빈 문자열 반환.
    """
    import urllib.request, json as _json
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    cards = parse_cardnews_content(html)
    if not cards:
        return ""
    brand = "순살크립토" if ctype == "crypto-card" else "순살브리핑"
    card_text = "\n".join(
        f"- {c['title']}: {c['body']}" if c["body"] else f"- {c['title']}"
        for c in cards
    )
    prompt = (
        f"{brand} 카드뉴스 ({date_fmt}) 구성:\n{card_text}\n\n"
        "위 내용을 Instagram 본문으로 2~3문장 요약해줘.\n"
        "조건: 총 100자 이내, 독자가 클릭하고 싶게 임팩트 있게, "
        "광고 말투 금지, 뉴스레터 독자에게 말하듯 자연스럽게, "
        "해시태그 없이 본문만, 이모지 1~2개 허용"
    )
    payload = _json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
            return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"  ⚠️  Claude API 캡션 생성 실패: {e}")
        return ""


def build_ig_summary(keywords: str, ctype: str, html: str = "", date_fmt: str = "") -> str:
    """Instagram 본문 요약 생성.

    우선순위:
    1. HTML 내 <meta name="soonsal-ig-caption"> 태그 (카드뉴스 제작 시 미리 작성)
    2. Claude Haiku API 생성 (ANTHROPIC_API_KEY 있을 때)
    3. keywords fallback
    """
    import re as _re

    # 1순위: 미리 작성된 ig-caption 메타 태그
    if html:
        m = _re.search(r'<meta[^>]+name="soonsal-ig-caption"[^>]+content="([^"]+)"', html)
        if not m:
            m = _re.search(r'<meta[^>]+content="([^"]+)"[^>]+name="soonsal-ig-caption"', html)
        if m:
            caption = m.group(1).strip()
            print(f"  📋 ig-caption 메타 태그 사용")
            return caption

    # 2순위: Claude Haiku API
    if html and date_fmt:
        ai_text = generate_ig_caption_ai(html, ctype, date_fmt)
        if ai_text:
            print(f"  ✨ AI 캡션 생성 완료")
            return ai_text

    # 3순위: keywords fallback
    if not keywords or keywords == "Untitled":
        return ""
    items = [k.strip() for k in _re.split(r"[,\n]+", keywords) if k.strip()]
    emoji = "📊" if ctype == "crypto-card" else "📌"
    return "\n".join(f"{emoji} {item}" for item in items[:3])


def derive_r2_prefix(ctype, yyyy, mmdd):
    """Derive R2 storage path from content type."""
    suffix = "-crypto" if ctype == "crypto-card" else ""
    return f"cardnews/{yyyy}/{mmdd}{suffix}"


def upload_to_r2(png_paths, r2_prefix):
    """Upload PNGs to Cloudflare R2 via ~/instagram_pipeline/ modules.
    
    Returns: list of public URLs, or empty list on failure.
    """
    try:
        sys.path.insert(0, str(INSTAGRAM_PIPELINE))
        from upload_r2 import upload_pngs_to_r2
    except (ImportError, ModuleNotFoundError):
        print("  ⚠️  R2 업로드 스킵 (~/instagram_pipeline/upload_r2.py 미발견)")
        # Fallback: construct URLs assuming upload will happen manually
        return [f"{R2_PUBLIC_URL}/{r2_prefix}/{p.name}" for p in png_paths]

    print(f"\n☁️  R2 업로드 ({len(png_paths)}장)")
    print(f"  경로: {r2_prefix}/")

    try:
        image_urls = upload_pngs_to_r2(
            [str(p) for p in png_paths],
            r2_prefix=r2_prefix,
        )
        print(f"  ✅ R2 업로드 완료")
        return image_urls
    except Exception as e:
        print(f"  ❌ R2 업로드 실패: {e}")
        # fallback: upload_r2.py와 동일한 파일명 규칙 적용 (card_01.png → 01.png)
        import re
        public_url = os.environ.get("R2_PUBLIC_URL", "https://pub-cb0321b52a854a95af8d6bb1688b2ecd.r2.dev").rstrip("/")
        urls = []
        for p in png_paths:
            m = re.search(r"_(\d{2})\.png$", p.name)
            fname = f"{m.group(1)}.png" if m else p.name
            urls.append(f"{public_url}/{r2_prefix}/{fname}")
        return urls


def post_to_instagram(image_urls, ctype, date_fmt, keywords="", html=""):
    """Post carousel to Instagram via ~/instagram_pipeline/ modules.
    
    Returns: carousel ID string, or None on failure.
    """
    try:
        sys.path.insert(0, str(INSTAGRAM_PIPELINE))
        from post_instagram import post_carousel
    except (ImportError, ModuleNotFoundError):
        print("  ⚠️  Instagram 게시 스킵 (~/instagram_pipeline/post_instagram.py 미발견)")
        return None

    summary = build_ig_summary(keywords, ctype, html=html, date_fmt=date_fmt)
    caption = IG_CAPTIONS.get(ctype, "").format(date_fmt=date_fmt, summary=summary)
    print(f"\n📱 Instagram 캐러셀 게시")
    print(f"  캡션: {caption[:80]}...")

    try:
        carousel_id = post_carousel(image_urls, caption)
        print(f"  ✅ 게시 완료 — ID: {carousel_id}")
        return carousel_id
    except Exception as e:
        print(f"  ❌ Instagram 게시 실패: {e}")
        print(f"  💡 수동 재시도: cd ~/instagram_pipeline && python3 cardnews_publish.py <파일>")
        return None


def publish_cardnews_to_instagram(png_paths, ctype, yyyy, mmdd, date_fmt, keywords="", html=""):
    """Full pipeline: R2 upload → Instagram carousel post.
    
    Gracefully skips if modules are not available.
    Returns True on success, False otherwise.
    """
    if not png_paths:
        return False

    r2_prefix = derive_r2_prefix(ctype, yyyy, mmdd)
    image_urls = upload_to_r2(png_paths, r2_prefix)

    if image_urls:
        carousel_id = post_to_instagram(image_urls, ctype, date_fmt, keywords=keywords, html=html)
        if carousel_id:
            # Dashboard: instagram step done
            pipeline = "crypto" if ctype == "crypto-card" else "briefing"
            notify_dashboard(pipeline, "instagram", "done", count=1)
            print(f"  📡 Dashboard: {pipeline}.instagram → done")
            return True
    return False
# ═══════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 deploy.py <file1> [file2] ...")
        print("Example: python3 deploy.py ~/Downloads/순살브리핑_20260302.html ~/Downloads/순살크립토_20260302.html")
        sys.exit(1)

    os.chdir(REPO)
    print("📦 git pull...")
    subprocess.run(["git", "pull", "origin", "main"], check=True)

    # ── Parse and copy files ──
    items = []
    for filepath in sys.argv[1:]:
        filepath = Path(filepath).expanduser().resolve()
        filename = filepath.name

        ctype, directory, suffix = detect_type(filename)
        yyyy, mmdd, date_fmt = extract_date(filename)

        if not ctype or not yyyy:
            print(f"⚠️  Cannot parse, skipping: {filename}")
            continue

        with open(filepath, "r") as f:
            html = f.read()

        keywords = extract_keywords(html, ctype)
        deploy_path = f"{directory}/{yyyy}/{mmdd}{suffix}.html"

        # Copy file to repo
        dest = REPO / deploy_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filepath, dest)

        # Inject Cloudflare Web Analytics beacon
        inject_analytics_beacon(dest)

        # Fix back-to-home link (← 순살 홈, orange)
        fix_back_link(dest)

        print(f"📄 {filename} → {deploy_path}")

        # Generate PNG for cardnews
        png_paths = []
        if ctype in CARDNEWS_TYPES:
            png_paths = generate_cardnews_png(filepath, ctype)

        items.append(
            {
                "type": ctype,
                "directory": directory,
                "yyyy": yyyy,
                "mmdd": mmdd,
                "date_formatted": date_fmt,
                "keywords": keywords,
                "deploy_path": deploy_path,
                "png_paths": png_paths,
                "html": html if ctype in CARDNEWS_TYPES else "",
            }
        )

    if not items:
        print("❌ No valid files to deploy")
        sys.exit(1)

    # ── Update indexes by date ──
    dates = sorted(set(i["date_formatted"] for i in items))
    for date_fmt in dates:
        date_items = [i for i in items if i["date_formatted"] == date_fmt]
        yyyy = date_items[0]["yyyy"]
        mmdd = date_items[0]["mmdd"]
        has_briefing = any(i["type"] == "briefing" for i in date_items)

        print(f"\n🔧 Updating indexes for {date_fmt}...")
        update_main_index(date_items, date_fmt, has_briefing, yyyy, mmdd)

        for item in date_items:
            update_archive_index(item)

    # ── Git commit & push ──
    print("\n🚀 Committing...")
    subprocess.run(["git", "add", "-A"], check=True)

    names = [LABELS.get(i["type"]) or i["keywords"][:30] for i in items]
    mmdd = items[0]["mmdd"]
    msg = f"Add {' & '.join(names)} {mmdd}"

    result = subprocess.run(["git", "commit", "-m", msg])
    if result.returncode == 0:
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"\n✨ Site deployed! {msg}")
    else:
        print(f"\n⚠️  변경사항 없음 (already committed) — Instagram 발행은 계속 진행")

    # ── Instagram publish for cardnews ──
    # 브리핑(card) 먼저, 크립토(crypto-card) 나중에 정렬
    cardnews_items = [i for i in items if i["type"] in CARDNEWS_TYPES and i.get("png_paths")]
    cardnews_items.sort(key=lambda x: 0 if x["type"] == "card" else 1)

    if cardnews_items:
        print(f"\n{'='*60}")
        print(f"📱 Instagram 발행 ({len(cardnews_items)}건)")
        print(f"{'='*60}")

        # 첫 번째는 즉시 게시
        first = cardnews_items[0]
        print(f"\n  → {LABELS[first['type']]} {first['date_formatted']} (즉시)")
        publish_cardnews_to_instagram(
            first["png_paths"],
            first["type"],
            first["yyyy"],
            first["mmdd"],
            first["date_formatted"],
            keywords=first.get("keywords", ""),
            html=first.get("html", ""),
        )

        # 나머지는 1시간 간격으로 백그라운드 게시
        remaining = cardnews_items[1:]
        if remaining:
            import threading, time as _time

            def _delayed_publish(jobs):
                for i, item in enumerate(jobs):
                    delay_min = 60 * (i + 1)
                    print(f"\n  ⏰ [{LABELS[item['type']]}] {delay_min}분 후 자동 게시 대기 중...")
                    _time.sleep(3600)
                    print(f"\n  → {LABELS[item['type']]} {item['date_formatted']} (예약 게시)")
                    publish_cardnews_to_instagram(
                        item["png_paths"],
                        item["type"],
                        item["yyyy"],
                        item["mmdd"],
                        item["date_formatted"],
                        keywords=item.get("keywords", ""),
                        html=item.get("html", ""),
                    )

            t = threading.Thread(target=_delayed_publish, args=(remaining,), daemon=False)
            t.start()
            labels = [LABELS[i["type"]] for i in remaining]
            print(f"\n  ✅ {', '.join(labels)} → 60분 후 백그라운드 자동 게시")
            print(f"  💡 터미널을 닫지 마세요 (또는 nohup 사용 권장)")

    # ── Dashboard webhook ──
    notified = set()
    for item in items:
        steps = DASHBOARD_MAP.get(item["type"], [])
        for pipeline, step in steps:
            key = (pipeline, step)
            if key not in notified:
                notify_dashboard(pipeline, step, "done", count=1)
                notified.add(key)
                print(f"  📡 Dashboard: {pipeline}.{step} → done")


if __name__ == "__main__":
    main()
