#!/usr/bin/env python3
"""
순살짤 자동 패킹 스크립트 (pack_zzal.py) v2

Usage:
  python3 pack_zzal.py 순살짤_20260322.html

v2 변경점:
  - cover-chat-card 지원: 커버 카드 안의 .msg도 인식 (커버+첫채팅 통합)
  - 인라인 클로징: 별도 closing-card 페이지 없음 → 마지막 채팅 카드 하단에 삽입
  - 총 페이지 = cover-chat-card 1p + 채팅 Np = 10장 이내 하드캡
  - auto-fill 유지 (FILL_TARGET=85)

원리:
  1. Playwright로 HTML을 렌더링
  2. 각 .msg 요소의 실제 높이를 측정 (커버 내 메시지 제외)
  3. 커버 카드 내 메시지는 그대로 유지 (1p에 포함)
  4. 나머지 메시지를 가용 높이 기준으로 greedy bin packing
  5. 마지막 채팅 카드에 인라인 클로징 삽입 (~170px)
  6. 10장 하드캡 적용

의존성: playwright
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

SAFETY_MARGIN = 15       # 잘림 방지 여유
FILL_TARGET = 85         # percent — 이 미만이면 리액션 자동 삽입
EST_REACTION_HEIGHT = 55 # 짧은 리액션 1개 ~55px

INLINE_CLOSING_HEIGHT = 170  # 인라인 클로징 예상 높이 (로고+이름+핸들+CTA+면책)
HARD_CAP = 10            # 최대 10장 (커버 포함)

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


# 마스터 템플릿 경로
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
    return None


def extract_inline_closing(template_path):
    """마스터 템플릿에서 인라인 클로징 HTML을 생성.
    
    logo base64를 템플릿의 .cover-chat-card나 <img> 태그에서 추출하여
    .inline-closing 블록을 반환.
    """
    with open(template_path) as f:
        t = f.read()
    
    # 로고 base64 추출: soonsal_b64_icon.txt를 프로젝트에서 직접 읽기 (light bg용)
    icon_paths = [
        Path.home() / "kdvol.github.io" / "soonsal_b64_icon.txt",
        Path(__file__).parent / "soonsal_b64_icon.txt",
    ]
    logo_b64 = ""
    for p in icon_paths:
        if p.exists():
            logo_b64 = p.read_text().strip()
            break
    
    if not logo_b64:
        # 템플릿에서 cover-brand img의 base64 추출 (fallback)
        m = re.search(r'cover-brand.*?src="(data:image/png;base64,[^"]+)"', t, re.DOTALL)
        if m:
            logo_b64 = m.group(1)
        else:
            logo_b64 = "data:image/png;base64,"
    else:
        logo_b64 = f"data:image/png;base64,{logo_b64}"

    return f'''    <div class="inline-closing">
      <img class="inline-closing-logo" src="{logo_b64}" alt="순살">
      <div class="inline-closing-name">순살짤</div>
      <div class="inline-closing-handle">@soonsal.zzal</div>
      <div class="inline-closing-cta">팔로우하면 매일 단톡방 엿볼 수 있음</div>
      <div class="inline-closing-disclaimer">창작 콘텐츠이며 매수·매도 추천이 아닙니다<br>모든 투자 판단과 책임은 본인에게 있습니다</div>
    </div>'''


def extract_head_and_cover(html):
    """HTML에서 <head>~CSS 부분과 커버 카드를 추출.
    
    v2: cover-chat-card 또는 cover-card 모두 지원.
    """
    first_comment = html.index('<!-- ====')
    head = html[:first_comment]
    
    # Cover card: from first <!-- ==== to second <!-- ====
    second_comment = html.index('<!-- ====', first_comment + 10)
    cover = html[first_comment:second_comment]
    
    return head, cover


def measure_and_extract_messages(html_path):
    """Playwright로 각 .msg의 실제 렌더링 높이 측정 + outerHTML 추출.
    
    커버 카드(.cover-chat-card) 내부의 .msg는 별도 표시하여 패킹에서 제외.
    
    Returns list of dicts: {index, height, text, html, in_cover}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 560, "height": 8000},
            device_scale_factor=1,
        )
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1500)

        messages = page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('.msg');
                const gap = 6;
                return Array.from(msgs).map((el, i) => {
                    const inCover = el.closest('.cover-chat-card') !== null;
                    return {
                        index: i,
                        height: el.getBoundingClientRect().height + gap,
                        text: (el.querySelector('.bubble, .bubble-img') || {}).textContent
                              ? el.querySelector('.bubble, .bubble-img').textContent.trim().substring(0, 40)
                              : '[img]',
                        html: el.outerHTML,
                        in_cover: inCover
                    };
                });
            }
        """)

        page.close()
        browser.close()

    return messages


def greedy_pack(messages, first_card_has_date=True, reserve_closing=True):
    """Greedy bin packing.
    
    reserve_closing=True: 마지막 카드에 인라인 클로징 공간 예약.
    """
    cards = []
    current = []
    current_h = 0
    
    for msg in messages:
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
    
    # 인라인 클로징 공간 확인: 마지막 카드에 INLINE_CLOSING_HEIGHT가 남아있는지
    if reserve_closing and cards:
        last_card = cards[-1]
        last_h = sum(m["height"] for m in last_card)
        avail_last = AVAIL - SAFETY_MARGIN
        if last_h + INLINE_CLOSING_HEIGHT > avail_last:
            # 마지막 카드에 공간 없음 — 새 카드 추가
            # 마지막 메시지를 새 카드로 이동하여 공간 확보
            overflow = []
            while last_card and last_h + INLINE_CLOSING_HEIGHT > avail_last:
                moved = last_card.pop()
                overflow.insert(0, moved)
                last_h -= moved["height"]
            if not last_card:
                # 메시지 1개가 너무 큰 경우 — 그냥 새 카드에 넣기
                cards[-1] = overflow
                cards.append([])  # 빈 카드 (클로징만)
            else:
                cards[-1] = last_card
                cards.append(overflow)
    
    return cards


def build_chat_card(page_num, total_pages, msg_htmls, has_date=False, date_text="", closing_html=""):
    """채팅 카드 HTML 생성."""
    date_html = ""
    if has_date and date_text:
        date_html = f'\n  <div class="date-divider">\n    <span>{date_text}</span>\n  </div>\n'
    
    padding = ' style="padding-top:16px;"' if not has_date else ''
    msgs = '\n'.join(f'    {m}' for m in msg_htmls)
    
    closing_block = ""
    if closing_html:
        closing_block = f'\n{closing_html}\n'
    
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
{closing_block}
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
        print("\n입력 파일은 cover-chat-card + chat-card 구조여야 합니다.")
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
    
    # CSS에 overflow:hidden 보장 (chat-body)
    if 'overflow: hidden' not in head:
        head = head.replace(
            'flex-direction: column;\n    gap: 6px;\n  }',
            'flex-direction: column;\n    gap: 6px;\n    overflow: hidden;\n  }'
        )
    
    # 인라인 클로징 CSS가 없으면 추가
    if '.inline-closing' not in head:
        closing_css = """
  /* 인라인 클로징 */
  .inline-closing {
    margin-top: auto;
    padding: 16px 0 8px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    text-align: center;
  }
  .inline-closing-logo { width: 36px; height: 36px; object-fit: contain; }
  .inline-closing-name { font-size: 16px; font-weight: 900; color: rgba(0,0,0,0.5); }
  .inline-closing-handle { font-size: 13px; color: rgba(0,0,0,0.35); margin-top: -4px; }
  .inline-closing-cta { font-size: 13px; color: #E55A00; font-weight: 700; }
  .inline-closing-disclaimer { font-size: 10px; color: rgba(0,0,0,0.3); line-height: 1.5; }
"""
        head = head.replace('</style>', closing_css + '</style>')

    # 날짜 구분선 텍스트 추출
    date_match = re.search(r'<div class="date-divider">\s*<span>(.*?)</span>', html)
    date_text = date_match.group(1) if date_match else ""

    # 3. Playwright로 메시지 높이 측정 + outerHTML 추출
    print("📏 Measuring + extracting messages...")
    all_messages = measure_and_extract_messages(input_path)
    
    cover_msgs = [m for m in all_messages if m["in_cover"]]
    chat_msgs = [m for m in all_messages if not m["in_cover"]]
    
    print(f"   Cover messages: {len(cover_msgs)}")
    print(f"   Chat messages: {len(chat_msgs)}")
    
    for msg in all_messages:
        loc = "📌" if msg["in_cover"] else "  "
        print(f"   {loc} [{msg['index']:2d}] {msg['height']:5.1f}px  {msg['text']}")

    # 4. Greedy 패킹 (커버 내 메시지 제외, 채팅 메시지만)
    has_date_in_chat = not any('date-divider' in m.get("html", "") for m in cover_msgs)
    # 커버에 date-divider가 있으면 첫 채팅카드에는 없음
    first_chat_has_date = 'date-divider' not in cover and has_date_in_chat
    
    cards = greedy_pack(chat_msgs, first_card_has_date=first_chat_has_date, reserve_closing=True)
    
    # 4-1. Auto-fill: fill rate < FILL_TARGET인 카드에 리액션 자동 삽입
    # 마지막 순살 메시지가 있는 카드부터 삽입 금지
    last_soonsal_card = -1
    for i, card in enumerate(cards):
        for msg in card:
            if "avatar-soonsal" in msg["html"]:
                last_soonsal_card = i
    
    last_card_idx = len(cards) - 1
    if last_soonsal_card == last_card_idx:
        autofill_blocked_from = last_card_idx
    elif last_soonsal_card >= 0:
        autofill_blocked_from = last_soonsal_card + 1
    else:
        autofill_blocked_from = len(cards)
    
    autofill_map = {}

    for i, card in enumerate(cards):
        if i >= autofill_blocked_from:
            continue
        
        total_h = sum(m["height"] for m in card)
        avail = AVAIL_WITH_DATE - SAFETY_MARGIN if i == 0 and first_chat_has_date else AVAIL - SAFETY_MARGIN
        
        # 마지막 카드는 인라인 클로징 공간 빼기
        if i == last_card_idx:
            avail -= INLINE_CLOSING_HEIGHT
        
        pct = total_h / avail * 100 if avail > 0 else 100
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
    
    # 총 페이지 = 커버 1p + 채팅 카드 Np (인라인 클로징은 마지막 카드에 포함)
    total_pages = 1 + len(cards)  # cover + chat cards
    
    # 하드캡 체크
    if total_pages > HARD_CAP:
        print(f"⚠️  {total_pages} pages > {HARD_CAP} hard cap! Truncating chat cards.")
        cards = cards[:HARD_CAP - 1]  # 커버 1 + (HARD_CAP-1) 채팅 카드
        total_pages = HARD_CAP
    
    print(f"\n📦 Packed into {len(cards)} chat cards ({total_pages} total pages, inline closing)")
    
    for i, card in enumerate(cards):
        total_h = sum(m["height"] for m in card)
        if i in autofill_map:
            total_h += len(autofill_map[i]) * EST_REACTION_HEIGHT
        if i == len(cards) - 1:
            total_h += INLINE_CLOSING_HEIGHT
        avail = AVAIL_WITH_DATE - SAFETY_MARGIN if i == 0 and first_chat_has_date else AVAIL - SAFETY_MARGIN
        pct = total_h / avail * 100
        status = "✅" if pct >= FILL_TARGET else f"⚠️ {pct:.0f}%"
        extra = f" (+{len(autofill_map[i])} auto)" if i in autofill_map else ""
        fill_blocked = " 🔒" if i >= autofill_blocked_from else ""
        closing_tag = " 🏷️closing" if i == len(cards) - 1 else ""
        print(f"   Card {i+1}: {len(card)}{extra} msgs, {total_h:.0f}px / {avail}px ({pct:.0f}%) {status}{fill_blocked}{closing_tag}")

    # 5. 인라인 클로징 HTML 생성
    closing_html = extract_inline_closing(template_path)

    # 6. 커버 카드의 페이지 번호 업데이트
    cover = re.sub(r'(\d+/\d+|N/N)', f'1/{total_pages}', cover)

    # 7. 최종 HTML 조립
    chat_html = ""
    for ci, card_msgs in enumerate(cards):
        page_num = ci + 2  # 커버가 1p
        card_msg_htmls = [m["html"] for m in card_msgs]
        if ci in autofill_map:
            card_msg_htmls.extend(autofill_map[ci])
        
        is_last = (ci == len(cards) - 1)
        chat_html += build_chat_card(
            page_num, total_pages, card_msg_htmls,
            has_date=(ci == 0 and first_chat_has_date),
            date_text=date_text,
            closing_html=closing_html if is_last else ""
        )

    # 8. 조립 (커버 + 채팅 카드 — 클로징은 마지막 카드에 인라인)
    full = head + cover + chat_html + "\n</body>\n</html>\n"
    
    # 9. 저장
    with open(input_path, 'w') as f:
        f.write(full)

    # 10. 검증
    assert 'inline-closing' in full, "인라인 클로징이 없음!"
    assert '</html>' in full
    total_cards = full.count('<div class="card ')
    print(f"\n✅ {input_path.name}: {total_cards} cards written ({total_pages} pages)")
    
    # 별도 closing-card가 남아있으면 경고
    if 'closing-card' in full:
        print("⚠️  WARNING: 별도 closing-card가 남아있습니다! 제거하세요.")


if __name__ == "__main__":
    main()
