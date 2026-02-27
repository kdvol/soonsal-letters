#!/bin/bash
set -e

# ── 설정 (내 환경에 맞게 수정) ──────────
REPO_DIR="$HOME/Desktop/soonsal-letters"
SOURCE_DIR="$HOME/Downloads"
# ────────────────────────────────────────

TODAY=$(date +%Y%m%d)
YEAR=$(date +%Y)
MMDD=$(date +%m%d)
FOLDER="$REPO_DIR/$YEAR/$MMDD"

echo "📰 순살브리핑 배포 시작 — $TODAY"
echo ""

# 1. 폴더 생성
mkdir -p "$FOLDER"

# 2. 파일 찾기 & 복사
copy_file() {
  local pattern="$1"
  local dest="$2"
  local label="$3"
  local found=$(find "$SOURCE_DIR" -maxdepth 1 -name "$pattern" -type f -newer "$SOURCE_DIR" 2>/dev/null | head -1)
  if [ -n "$found" ]; then
    cp "$found" "$dest"
    echo "  ✅ $label"
  else
    echo "  ⚠️  $label — 파일 없음, 건너뜀"
  fi
}

echo "📁 파일 복사 중..."
copy_file "순살브리핑_${TODAY}*"               "$FOLDER/index.html"    "순살브리핑 → index.html"
copy_file "순살크립토_${TODAY}*"               "$FOLDER/crypto.html"   "순살크립토 → crypto.html"
copy_file "순살크립토카드뉴스_${TODAY}*"        "$FOLDER/cards.html"    "카드뉴스 → cards.html"
copy_file "순살카드뉴스_${TODAY}*"              "$FOLDER/cards.html"    "카드뉴스 → cards.html"
copy_file "SoonsalCrypto_${TODAY}_Publish*"    "$FOLDER/publish.html"  "X Article → publish.html"

# 3. index.html에 새 이슈 자동 추가
DISPLAY_DATE="${YEAR}.${MMDD:0:2}.${MMDD:2:2}"
NEW_ENTRY="    <div class=\"issue\">\\
      <span class=\"date\">$DISPLAY_DATE</span>\\
      <div class=\"links\">\\
        <a href=\"/$YEAR/$MMDD/\">순살브리핑</a>\\
        <a href=\"/$YEAR/$MMDD/crypto.html\">순살크립토</a>\\
        <a href=\"/$YEAR/$MMDD/cards.html\">📱 카드뉴스</a>\\
        <a href=\"/$YEAR/$MMDD/publish.html\">English</a>\\
      </div>\\
    </div>"

cd "$REPO_DIR"
if ! grep -q "/$YEAR/$MMDD/" index.html 2>/dev/null; then
  # macOS sed 호환
  sed -i '' "/<!-- 최신이 위로/a\\
$NEW_ENTRY
" index.html
  echo ""
  echo "📋 index.html 업데이트 완료"
else
  echo ""
  echo "📋 index.html에 오늘 날짜 이미 존재 — 건너뜀"
fi

# 4. Git push
echo ""
echo "🚀 GitHub에 배포 중..."
git add .
git commit -m "$DISPLAY_DATE 순살브리핑"
git push

echo ""
echo "════════════════════════════════════════"
echo "✅ 배포 완료!"
echo ""
echo "  📖 https://letters.soonsal.com/$YEAR/$MMDD/"
echo "  🪙 https://letters.soonsal.com/$YEAR/$MMDD/crypto.html"
echo "  📱 https://letters.soonsal.com/$YEAR/$MMDD/cards.html"
echo "  🌐 https://letters.soonsal.com/$YEAR/$MMDD/publish.html"
echo "════════════════════════════════════════"
