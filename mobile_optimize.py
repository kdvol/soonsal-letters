#!/usr/bin/env python3
"""
mobile_optimize.py — letters.soonsal.com 모바일 최적화

사용법: 레포 루트(kdvol.github.io/)에서 실행
  python3 mobile_optimize.py --dry-run    # 미리보기
  python3 mobile_optimize.py              # 실행

작업 내용:
  newsletters/, cardnews/, english/ 내 개별 콘텐츠 HTML에
  모바일 반응형 미디어쿼리를 </style> 앞에 삽입

  - 기존 CSS는 그대로 유지 (데스크톱 동일)
  - @media (max-width: 680px) 블록만 추가
"""

import os
import re
import sys

DRY_RUN = '--dry-run' in sys.argv

# ─── 모바일 반응형 CSS ───
MOBILE_CSS = """
  /* === MOBILE RESPONSIVE === */
  @media (max-width: 680px) {
    .wrapper {
      max-width: 100% !important;
      margin: 0 !important;
      border-radius: 0 !important;
      box-shadow: none !important;
    }
    .header {
      padding: 20px 16px 16px !important;
    }
    .header .brand {
      font-size: 19px !important;
    }
    .market-table {
      padding: 16px 14px !important;
    }
    .market-table table {
      font-size: 12px !important;
    }
    .content {
      padding: 20px 16px !important;
    }
    .story {
      margin-bottom: 28px !important;
      padding-bottom: 24px !important;
    }
    .story-title {
      font-size: 17px !important;
    }
    .story-body p {
      font-size: 14px !important;
    }
    .headline-section {
      padding: 20px 16px !important;
    }
    .word-section {
      padding: 20px 16px 24px !important;
    }
    .quote-section {
      padding: 24px 16px 20px !important;
    }
    .footer {
      padding: 24px 16px !important;
    }
    .footer-inner {
      max-width: 100% !important;
    }
    /* 카드뉴스 대응 */
    .card {
      width: 100% !important;
      max-width: 100% !important;
      border-radius: 0 !important;
    }
  }
"""

MARKER = '/* === MOBILE RESPONSIVE === */'


def inject_mobile_css(filepath):
    """단일 HTML 파일에 모바일 CSS 주입"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
    except Exception as e:
        print(f"  ❌ 읽기 실패: {filepath} — {e}")
        return 'error'

    # 이미 주입됨
    if MARKER in html:
        return 'skip'

    # </style> 앞에 삽입
    if '</style>' not in html:
        print(f"  ⚠️  </style> 없음: {filepath}")
        return 'error'

    html = html.replace('</style>', MOBILE_CSS + '\n</style>', 1)

    if DRY_RUN:
        print(f"  📄 [DRY] 대상: {filepath}")
        return 'dry'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✅ 주입: {filepath}")
    return 'ok'


def main():
    if DRY_RUN:
        print("🔍 드라이런 모드\n")

    print("📱 letters.soonsal.com 모바일 최적화")
    print("   (기존 CSS 유지 + @media 미디어쿼리 추가)")
    print("=" * 50)

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
                result = inject_mobile_css(filepath)

                if result in ('ok', 'dry'):
                    processed += 1
                elif result == 'skip':
                    skipped += 1
                else:
                    errors += 1

    print(f"\n  처리: {processed} | 스킵(이미적용): {skipped} | 에러: {errors}")

    print("\n" + "=" * 50)
    if DRY_RUN:
        print("🔍 드라이런 완료. 실제 적용: python3 mobile_optimize.py")
    else:
        print("🎉 완료!")
        print("\n  git add .")
        print('  git commit -m "Add mobile responsive CSS"')
        print("  git push")


if __name__ == '__main__':
    main()
