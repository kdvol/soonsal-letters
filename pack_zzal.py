#!/usr/bin/env python3
"""
순살짤 자동 패킹 스크립트 (pack_zzal.py)

Usage:
  python3 pack_zzal.py 순살짤_20260321.html

입력: 모든 메시지가 하나의 chat-card에 들어있는 순살짤 HTML
출력: 메시지를 카드별로 자동 분배한 최종 캐러셀 HTML (같은 파일에 덮어쓰기)

원리:
  1. Playwright로 HTML을 렌더링
  2. 각 .msg 요소의 실제 높이를 측정
  3. 가용 높이(카드 675px - 헤더 - 푸터)를 기준으로 greedy bin packing
  4. 카드별로 분배된 최종 HTML 생성
  5. 마지막 페이지는 zzal_master_template.html에서 복사 (절대 새로 만들지 않음)

의존성: playwright, Pillow
"""

import sys
import re
import random
from pathlib import Path
from playwright.sync_api import sync_playwright

# ═══════════════════════════════════════
# Configuration
# ═══════════════════════════════════════

CARD_HEIGHT = 675        # 카드 전체 높이
HEADER_HEIGHT = 48       # chat-header
INPUT_BAR_HEIGHT = 52    # chat-input-bar
BODY_PADDING = 28        # chat-body padding (12+16)
DATE_DIVIDER_HEIGHT = 40 # 날짜 구분선

# 가용 높이 = 카드 - 헤더 - 푸터 - 패딩
AVAIL = CARD_HEIGHT - HEADER_HEIGHT - INPUT_BAR_HEIGHT - BODY_PADDING
AVAIL_WITH_DATE = AVAIL - DATE_DIVIDER_HEIGHT

SAFETY_MARGIN = 15  # 잘림 방지 여유
FILL_TARGET = 85    # percent — 이 미만이면 리액션 자동 삽입
EST_REACTION_HEIGHT = 55  # 짧은 리액션 1개 ~55px

# ═══════════════════════════════════════
# Reaction Auto-Fill Pool
# ═══════════════════════════════════════

REACTIONS = {
    "avatar-andrew": [
        "ㄹㅇ?", "아 미쳤다 진짜", "와 소름", "헐", "이건 좀 무섭네",
        "아 진짜 ㅋㅋㅋ", "그건 좀 심하다", "ㅠㅠ", "에이 설마",
        "그래서 어쩌라고 ㅋ", "나도 그거 봤어", "아 맞아 그거",
        "아 몰라 걍 존버할래", "ㅋㅋㅋ 핵공감", "장난 아니네",
    ],
    "avatar-sean": [
        "????", "ㅋㅋㅋㅋ", "아 ㅋㅋ 뭐야 이게", "대박", "진짜?",
        "이게 되냐", "ㅋㅋ 웃기네", "아 이건 좀", "미쳤다 ㅋ",
        "와 그건 몰랐네", "ㄹㅇㅋㅋ", "에바 아님?", "ㅇㅇ 인정",
        "아 그러면 나도 해야되나", "ㅎㄷㄷ",
    ],
}

REACTION_NAMES = {
    "avatar-andrew": ("앤", "앤드류 (운용역)"),
    "avatar-sean": ("션", "션 (스타트업)"),
}

REACTION_CHARS = list(REACTIONS.keys())


def make_reaction_html(char_class):
    avatar_letter, name = REACTION_NAMES[char_class]
    text = random.choice(REACTIONS[char_class])
    return (
        f'<div class="msg">\n'
        f'  <div class="avatar {char_class}">{avatar_letter}</div>\n'
        f'  <div class="msg-content">\n'
        f'    <span class="msg-name">{name}</span>\n'
        f'    <div class="msg-row">\n'
        f'      <div class="bubble">{text}</div>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'</div>'
    )

# 마스터 템플릿 경로 (프로젝트에 따라 조정)
TEMPLATE_PATHS = [
    Path.home() / "kdvol.github.io" / "zzal_master_template.html",
    Path(__file__).parent / "zzal_master_template.html",
    Path("zzal_master_template.html"),
]


def find_template():
    """마스터 템플릿 찾기."""
    for p in TEMPLATE_PATHS:
        if p.exists():
            return p
    print("⚠️  zzal_master_template.html not found, trying project knowledge...")
    # Fallback: same directory as input file
    return None


def extract_closing_card(template_path):
    """마스터 템플릿에서 클로징 카드를 그대로 추출."""
    with open(template_path) as f:
        t = f.read()
    idx = t.index('<div class="card closing-card">')
    comment_start = t.rfind('<!-- ====', 0, idx)
    return t[comment_start:]


def extract_head_and_cover(html):
    """HTML에서 <head>~CSS 부분과 커버 카드를 추출."""
    first_comment = html.index('<!-- ====')
    head = html[:first_comment]
    
    # Cover card: from first <!-- ==== to second <!-- ====
    second_comment = html.index('<!-- ====', first_comment + 10)
    cover = html[first_comment:second_comment]
    
    return head, cover


def measure_and_extract_messages(html_path):
    """Playwright로 각 .msg의 실제 렌더링 높이 측정 + outerHTML 추출.
    
    Returns list of dicts: {index, height, text, html}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 560, "height": 8000},
            device_scale_factor=1,  # 측정용이라 1x
        )
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1500)

        # 모든 .msg의 높이 + gap(6px) + outerHTML 한번에 추출
        messages = page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('.msg');
                const gap = 6;
                return Array.from(msgs).map((el, i) => ({
                    index: i,
                    height: el.getBoundingClientRect().height + gap,
                    text: (el.querySelector('.bubble, .bubble-img') || {}).textContent
                          ? el.querySelector('.bubble, .bubble-img').textContent.trim().substring(0, 40)
                          : '[img]',
                    html: el.outerHTML
                }));
            }
        """)

        page.close()
        browser.close()

    return messages


def greedy_pack(heights, first_card_has_date=True):
    """Greedy bin packing: 각 카드에 가용 높이만큼 채우기."""
    cards = []
    current = []
    current_h = 0
    
    for msg in heights:
        avail = AVAIL_WITH_DATE - SAFETY_MARGIN if len(cards) == 0 and first_card_has_date else AVAIL - SAFETY_MARGIN
        
        if current_h + msg["height"] > avail and current:
            cards.append(current)
            current = [msg]
            current_h = msg["height"]
        else:
            current.append(msg)
            current_h += msg["height"]
    
    if current:
        cards.append(current)
    
    return cards


def build_chat_card(page_num, total_pages, msg_htmls, has_date=False, date_text=""):
    """채팅 카드 HTML 생성."""
    date_html = ""
    if has_date and date_text:
        date_html = f'\n  <div class="date-divider">\n    <span>{date_text}</span>\n  </div>\n'
    
    padding = ' style="padding-top:16px;"' if not has_date else ''
    msgs = '\n'.join(f'    {m}' for m in msg_htmls)
    
    return f"""<!-- ================================================================
     {page_num}p
     ================================================================ -->
<div class="card chat-card">
  <div class="chat-header">
    <div class="chat-header-left">
      <span class="chat-header-back">‹</span>
      <span class="chat-room-name">순살 단톡방</span>
      <span class="chat-room-count">4</span>
    </div>
    <span class="chat-page-num">{page_num}/{total_pages}</span>
  </div>
{date_html}
  <div class="chat-body"{padding}>

{msgs}

  </div>

  <div class="chat-input-bar">
    <div class="chat-input-fake">메시지 입력</div>
    <div class="chat-send-btn">▶</div>
  </div>
</div>

"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 pack_zzal.py <순살짤_YYYYMMDD.html>")
        print("\n입력 파일은 모든 메시지가 하나의 chat-card에 들어있어야 합니다.")
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        html = f.read()

    # 1. 마스터 템플릿 찾기
    template_path = find_template()
    if not template_path:
        print("❌ zzal_master_template.html not found")
        sys.exit(1)
    print(f"📋 Template: {template_path}")

    # 2. HEAD + CSS, 커버 카드 추출
    head, cover = extract_head_and_cover(html)
    
    # CSS에 overflow:hidden 보장
    if 'overflow: hidden' not in head:
        head = head.replace(
            'flex-direction: column;\n    gap: 6px;\n  }',
            'flex-direction: column;\n    gap: 6px;\n    overflow: hidden;\n  }'
        )

    # 날짜 구분선 텍스트 추출
    date_match = re.search(r'<div class="date-divider">\s*<span>(.*?)</span>', html)
    date_text = date_match.group(1) if date_match else ""

    # 3. Playwright로 메시지 높이 측정 + outerHTML 추출 (한번에)
    print("📏 Measuring + extracting messages...")
    messages = measure_and_extract_messages(input_path)
    print(f"   Found {len(messages)} messages")
    
    for msg in messages:
        print(f"   [{msg['index']:2d}] {msg['height']:5.1f}px  {msg['text']}")

    # 4. Greedy 패킹
    cards = greedy_pack(messages, first_card_has_date=True)
    
    # 4-1. Auto-fill: fill rate < FILL_TARGET인 카드에 리액션 자동 삽입
    #       원본 messages는 수정하지 않음 — 카드 조립 시점에 HTML 추가
    #       경계: 마지막 순살(avatar-soonsal) 메시지가 포함된 카드부터는 삽입 금지
    #       (열린 질문은 항상 순살이 마지막에 치므로)
    
    # 마지막 순살 메시지가 어느 카드에 있는지 찾기
    last_soonsal_card = -1
    for i, card in enumerate(cards):
        for msg in card:
            if "avatar-soonsal" in msg["html"]:
                last_soonsal_card = i
    
    # Auto-fill 경계 결정:
    # - 마지막 순살이 마지막 카드에 있으면 → 마지막 카드만 금지
    # - 마지막 순살이 마지막 카드가 아니면 → 그 이후 카드들 금지
    last_card_idx = len(cards) - 1
    if last_soonsal_card == last_card_idx:
        # 순살 열린 질문이 마지막 카드 → 마지막 카드만 금지
        autofill_blocked_from = last_card_idx
    else:
        # 순살 이후에 다른 대화가 이어짐 → 순살 이후 카드들만 금지
        autofill_blocked_from = last_soonsal_card + 1
    
    autofill_map = {}

    for i, card in enumerate(cards):
        if i >= autofill_blocked_from:
            continue
        
        total_h = sum(m["height"] for m in card)
        avail = AVAIL_WITH_DATE - SAFETY_MARGIN if i == 0 else AVAIL - SAFETY_MARGIN
        pct = total_h / avail * 100
        gap_px = avail - total_h
        
        if pct < FILL_TARGET and gap_px > EST_REACTION_HEIGHT:
            n_reactions = int(gap_px // EST_REACTION_HEIGHT)
            n_reactions = min(n_reactions, 3)
            if n_reactions > 0:
                last_char = None
                last_html = card[-1]["html"]
                for c in REACTION_CHARS:
                    if c in last_html:
                        last_char = c
                        break
                
                reactions = []
                used_texts = set()
                for _ in range(n_reactions):
                    candidates = [c for c in REACTION_CHARS if c != last_char]
                    char = random.choice(candidates) if candidates else random.choice(REACTION_CHARS)
                    
                    attempts = 0
                    reaction_html = make_reaction_html(char)
                    while any(t in reaction_html for t in used_texts) and attempts < 10:
                        reaction_html = make_reaction_html(char)
                        attempts += 1
                    
                    bubble_match = re.search(r'<div class="bubble">(.*?)</div>', reaction_html)
                    if bubble_match:
                        used_texts.add(bubble_match.group(1))
                    
                    reactions.append(reaction_html)
                    last_char = char
                
                autofill_map[i] = reactions
                print(f"   🔧 Card {i+1}: {pct:.0f}% → 리액션 {n_reactions}개 자동 삽입")
    
    total_pages = len(cards) + 2  # +1 cover +1 closing
    print(f"\n📦 Packed into {len(cards)} chat cards ({total_pages} total pages)")
    
    for i, card in enumerate(cards):
        total_h = sum(m["height"] for m in card)
        if i in autofill_map:
            total_h += len(autofill_map[i]) * EST_REACTION_HEIGHT
        avail = AVAIL_WITH_DATE - SAFETY_MARGIN if i == 0 else AVAIL - SAFETY_MARGIN
        pct = total_h / avail * 100
        status = "✅" if pct >= FILL_TARGET else f"⚠️ {pct:.0f}%"
        extra = f" (+{len(autofill_map[i])} auto)" if i in autofill_map else ""
        fill_blocked = " 🔒" if i >= autofill_blocked_from else ""
        print(f"   Card {i+1}: {len(card)}{extra} msgs, {total_h:.0f}px / {avail}px ({pct:.0f}%) {status}{fill_blocked}")

    # 5. 최종 HTML 조립 (autofill 반영)
    chat_html = ""
    for ci, card_msgs in enumerate(cards):
        page_num = ci + 2
        card_msg_htmls = [m["html"] for m in card_msgs]
        if ci in autofill_map:
            card_msg_htmls.extend(autofill_map[ci])
        chat_html += build_chat_card(page_num, total_pages, card_msg_htmls, has_date=(ci == 0), date_text=date_text)

    # 6. 클로징 카드 (마스터 템플릿에서 그대로 복사)
    closing = extract_closing_card(template_path)
    closing = re.sub(r'\d+p — 클로징', f'{total_pages}p — 클로징', closing)

    # 7. 조립
    full = head + cover + chat_html + closing
    
    # 8. 저장
    with open(input_path, 'w') as f:
        f.write(full)

    # 9. 검증
    assert '<div class="card closing-card">' in full
    assert '</html>' in full
    total_cards = full.count('<div class="card ')
    print(f"\n✅ {input_path.name}: {total_cards} cards written")


if __name__ == "__main__":
    main()
