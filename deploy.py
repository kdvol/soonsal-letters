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
  6. Git add, commit, push
"""

import sys
import os
import re
import shutil
import subprocess
from pathlib import Path

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
        # Date exists → append non-briefing items to existing today-grid
        for item in sorted(items, key=lambda x: ORDER[x["type"]]):
            if item["type"] == "briefing":
                continue
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
        # Append to existing date section (6-space indent)
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
# Main
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
        print(f"📄 {filename} → {deploy_path}")

        items.append(
            {
                "type": ctype,
                "directory": directory,
                "yyyy": yyyy,
                "mmdd": mmdd,
                "date_formatted": date_fmt,
                "keywords": keywords,
                "deploy_path": deploy_path,
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

    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push", "origin", "main"], check=True)
    print(f"\n✨ Done! {msg}")


if __name__ == "__main__":
    main()
