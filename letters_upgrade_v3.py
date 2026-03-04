#!/usr/bin/env python3
"""
letters_upgrade_v3.py — letters.soonsal.com 업그레이드

사용법: 레포 루트(kdvol.github.io/)에서 실행
  python3 letters_upgrade_v3.py              # 전체 실행
  python3 letters_upgrade_v3.py --dry-run    # 미리보기만

작업 내용:
  1. 모든 index.html Nav에 구독하기 버튼 추가 (루트 + 각 섹션)
     → 인라인 스타일만 사용 (기존 CSS 절대 미수정)
  2. 개별 콘텐츠 HTML에 뒤로가기 버튼 삽입
  3. CNAME 확인

v3 변경점:
  - CSS 추가/수정 완전 제거 → 인라인 스타일로만 구현
  - 기존 .nav a 스타일과의 충돌 원천 차단
"""

import os
import re
import sys

DRY_RUN = '--dry-run' in sys.argv

# ─── 순살 브랜드 컬러 ───
SOONSAL_ORANGE = '#E55A00'
SOONSAL_ORANGE_HOVER = '#CC4E00'

SUBSCRIBE_URL = 'https://page.stibee.com/subscriptions/51845'

# ─── 구독하기 버튼 HTML (인라인 스타일만, CSS 추가 없음) ───
# .nav a 스타일 오버라이드를 위해 모든 속성에 !important
SUBSCRIBE_LINK = (
    f'<a href="{SUBSCRIBE_URL}" target="_blank" '
    f'style="'
    f'background:{SOONSAL_ORANGE} !important;'
    f'color:#fff !important;'
    f'padding:6px 16px !important;'
    f'border-radius:4px !important;'
    f'font-size:13px !important;'
    f'font-weight:700 !important;'
    f'text-decoration:none !important;'
    f'margin-left:8px !important;'
    f'border-bottom:none !important;'
    f'display:inline-block !important;'
    f'line-height:1.4 !important;'
    f'" '
    f'onmouseover="this.style.background=\'{SOONSAL_ORANGE_HOVER}\'" '
    f'onmouseout="this.style.background=\'{SOONSAL_ORANGE}\'"'
    f'>구독하기</a>'
)

# ─── 뒤로가기 버튼 HTML ───
BACK_BUTTON = '''<!-- BACK TO LETTERS -->
<div style="max-width:680px;margin:0 auto;padding:10px 16px 0;">
  <a href="https://letters.soonsal.com" style="display:inline-flex;align-items:center;gap:6px;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:13px;font-weight:600;color:#888;text-decoration:none;padding:6px 0;" onmouseover="this.style.color='#111'" onmouseout="this.style.color='#888'">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
    letters.soonsal.com
  </a>
</div>
<!-- /BACK TO LETTERS -->
'''


def add_subscribe_button(filepath):
    """단일 index.html에 구독하기 버튼 추가 (인라인 스타일만)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
    except Exception as e:
        print(f"  ❌ 읽기 실패: {filepath} — {e}")
        return False

    # 이미 구독 버튼이 있으면 스킵
    if 'subscriptions/51845' in html:
        print(f"  ⏭️  이미 있음: {filepath}")
        return False

    # 패턴: English</a></div>  →  English</a>{구독버튼}</div>
    target = '<a href="/english/">English</a></div>'
    if target in html:
        html = html.replace(
            target,
            f'<a href="/english/">English</a>{SUBSCRIBE_LINK}</div>'
        )
    else:
        # </div>가 다른 줄에 있을 수도 있으므로
        target2 = '<a href="/english/">English</a>'
        if target2 in html:
            html = html.replace(
                target2,
                f'{target2}{SUBSCRIBE_LINK}'
            )
        else:
            print(f"  ⚠️  Nav 패턴 못 찾음: {filepath}")
            return False

    if DRY_RUN:
        print(f"  📄 [DRY] 구독하기 추가 예정: {filepath}")
        return True

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✅ 구독하기 추가: {filepath}")
    return True


def upgrade_all_indexes():
    """모든 index.html에 구독하기 버튼 추가"""
    print("📌 [1/3] 구독하기 버튼 추가 (모든 index.html)")
    print("       ※ 인라인 스타일만 사용 — 기존 CSS 변경 없음")

    targets = [
        'index.html',
        'newsletters/index.html',
        'cardnews/index.html',
        'english/index.html',
    ]

    for path in targets:
        if os.path.exists(path):
            add_subscribe_button(path)
        else:
            print(f"  ⚠️  파일 없음: {path}")


def add_back_buttons():
    """개별 콘텐츠 HTML에 뒤로가기 버튼 삽입"""
    print("\n📌 [2/3] 개별 콘텐츠 — 뒤로가기 버튼")

    processed = 0
    skipped = 0
    errors = 0

    for directory in ['newsletters', 'cardnews', 'english']:
        if not os.path.isdir(directory):
            continue

        for root, dirs, files in os.walk(directory):
            for filename in sorted(files):
                if not filename.endswith('.html') or filename == 'index.html':
                    continue

                filepath = os.path.join(root, filename)

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception as e:
                    print(f"  ❌ 읽기 실패: {filepath} — {e}")
                    errors += 1
                    continue

                if 'BACK TO LETTERS' in content:
                    skipped += 1
                    continue

                match = re.search(r'(<body[^>]*>)', content, re.IGNORECASE)
                if not match:
                    skipped += 1
                    continue

                pos = match.end()
                new_content = content[:pos] + '\n' + BACK_BUTTON + content[pos:]

                if DRY_RUN:
                    print(f"  📄 [DRY] 대상: {filepath}")
                else:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"  ✅ 삽입: {filepath}")

                processed += 1

    print(f"\n  처리: {processed} | 스킵: {skipped} | 에러: {errors}")


def check_cname():
    """CNAME 확인"""
    print("\n📌 [3/3] CNAME 확인")

    if os.path.exists('CNAME'):
        with open('CNAME', 'r') as f:
            current = f.read().strip()
        print(f"  현재: {current}")
        if current == 'letters.soonsal.com':
            print("  ✅ OK")
        else:
            print("  ⚠️  변경 필요: echo 'letters.soonsal.com' > CNAME")
    else:
        print("  ⚠️  CNAME 없음")


def main():
    if DRY_RUN:
        print("🔍 드라이런 모드\n")

    print("🔧 letters.soonsal.com 업그레이드 v3")
    print("   (인라인 스타일만 사용 — 기존 CSS 절대 미수정)")
    print("=" * 50)

    upgrade_all_indexes()
    add_back_buttons()
    check_cname()

    print("\n" + "=" * 50)
    if DRY_RUN:
        print("🔍 드라이런 완료. 실제 적용: python3 letters_upgrade_v3.py")
    else:
        print("🎉 완료!")
        print("\n  git add .")
        print('  git commit -m "Add subscribe button + back navigation (v3)"')
        print("  git push")


if __name__ == '__main__':
    main()
