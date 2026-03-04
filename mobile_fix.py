#!/usr/bin/env python3
"""
mobile_fix.py — 모바일 최적화 보완

1. viewport 메타태그 누락된 HTML에 추가
2. 카드뉴스 모바일 CSS 보강 (540px 고정 → 반응형)
"""

import os
import re
import sys

DRY_RUN = '--dry-run' in sys.argv

VIEWPORT_TAG = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'

# 카드뉴스용 모바일 CSS 보강 (기존 MOBILE RESPONSIVE 블록의 .card 룰을 교체)
CARD_CSS_OLD = """    /* 카드뉴스 대응 */
    .card {
      width: 100% !important;
      max-width: 100% !important;
      border-radius: 0 !important;
    }"""

CARD_CSS_NEW = """    /* 카드뉴스 대응 */
    .card {
      width: 100% !important;
      max-width: 100% !important;
      height: auto !important;
      min-height: 0 !important;
      aspect-ratio: 1 / 1;
      border-radius: 0 !important;
      padding: 20px 16px 16px !important;
    }
    .card .top-zone {
      font-size: 22px !important;
    }
    .card .mid-zone {
      font-size: 13px !important;
    }
    .card .bot-zone {
      font-size: 11px !important;
    }"""


def fix_viewport(filepath):
    """viewport 메타태그 누락 시 추가"""
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    if 'viewport' in html:
        return False

    # <meta charset="UTF-8"> 다음 줄에 삽입
    if '<meta charset="UTF-8">' in html:
        html = html.replace(
            '<meta charset="UTF-8">',
            '<meta charset="UTF-8">\n' + VIEWPORT_TAG
        )
    elif '<head>' in html:
        html = html.replace('<head>', '<head>\n' + VIEWPORT_TAG)
    else:
        return False

    if DRY_RUN:
        print(f"  📄 [DRY] viewport 추가: {filepath}")
        return True

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✅ viewport 추가: {filepath}")
    return True


def fix_card_css(filepath):
    """카드뉴스 모바일 CSS 보강"""
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    if CARD_CSS_OLD not in html:
        return False

    html = html.replace(CARD_CSS_OLD, CARD_CSS_NEW)

    if DRY_RUN:
        print(f"  📄 [DRY] 카드CSS 보강: {filepath}")
        return True

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✅ 카드CSS 보강: {filepath}")
    return True


def main():
    if DRY_RUN:
        print("🔍 드라이런 모드\n")

    print("📱 모바일 최적화 보완")
    print("=" * 50)

    vp_count = 0
    card_count = 0

    print("\n📌 [1/2] viewport 메타태그 확인")
    for directory in ['newsletters', 'cardnews', 'english']:
        if not os.path.isdir(directory):
            continue
        for root, dirs, files in os.walk(directory):
            for filename in sorted(files):
                if not filename.endswith('.html') or filename == 'index.html':
                    continue
                filepath = os.path.join(root, filename)
                if fix_viewport(filepath):
                    vp_count += 1

    print(f"\n  viewport 추가: {vp_count}개")

    print("\n📌 [2/2] 카드뉴스 모바일 CSS 보강")
    for directory in ['cardnews']:
        if not os.path.isdir(directory):
            continue
        for root, dirs, files in os.walk(directory):
            for filename in sorted(files):
                if not filename.endswith('.html') or filename == 'index.html':
                    continue
                filepath = os.path.join(root, filename)
                if fix_card_css(filepath):
                    card_count += 1

    print(f"\n  카드CSS 보강: {card_count}개")

    print("\n" + "=" * 50)
    if DRY_RUN:
        print("🔍 드라이런 완료. 실제 적용: python3 mobile_fix.py")
    else:
        print("🎉 완료!")
        print("\n  git add .")
        print('  git commit -m "Fix mobile: add viewport + card responsive"')
        print("  git push")


if __name__ == '__main__':
    main()
