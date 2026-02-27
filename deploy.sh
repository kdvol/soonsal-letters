#!/bin/bash
set -e

REPO_DIR="$HOME/Desktop/soonsal-letters"
SOURCE_DIR="$HOME/Downloads"

TODAY=$(date +%Y%m%d)
YEAR=$(date +%Y)
MMDD=$(date +%m%d)
FOLDER="$REPO_DIR/$YEAR/$MMDD"

echo ""
echo "📰 순살브리핑 배포 — $YEAR.${MMDD:0:2}.${MMDD:2:2}"
echo ""

cd "$REPO_DIR"
mkdir -p "$FOLDER"

for pair in \
  "순살브리핑_${TODAY}:index.html:순살브리핑" \
  "순살크립토_${TODAY}:crypto.html:순살크립토" \
  "순살크립토카드뉴스_${TODAY}:cards.html:카드뉴스" \
  "순살카드뉴스_${TODAY}:cards.html:카드뉴스" \
  "SoonsalCrypto_${TODAY}_Publish:publish.html:X Article"
do
  PATTERN=$(echo "$pair" | cut -d: -f1)
  DEST=$(echo "$pair" | cut -d: -f2)
  LABEL=$(echo "$pair" | cut -d: -f3)
  FOUND=$(find "$SOURCE_DIR" -maxdepth 1 -name "${PATTERN}*" -type f 2>/dev/null | head -1)
  if [ -n "$FOUND" ]; then
    cp "$FOUND" "$FOLDER/$DEST"
    echo "  ✅ $LABEL → $DEST"
  fi
done

DISPLAY="${YEAR}.${MMDD:0:2}.${MMDD:2:2}"

if ! grep -q "/$YEAR/$MMDD/" index.html 2>/dev/null; then
  ENTRY="<div class=\"issue\"><span class=\"date\">$DISPLAY</span><div class=\"links\"><a href=\"/$YEAR/$MMDD/\">순살브리핑</a> <a href=\"/$YEAR/$MMDD/crypto.html\">순살크립토</a> <a href=\"/$YEAR/$MMDD/cards.html\">📱 카드뉴스</a> <a href=\"/$YEAR/$MMDD/publish.html\">English</a></div></div>"
  sed -i '' "s|<!-- 최신이 위로.*-->|&\\
    $ENTRY|" index.html
  echo "  📋 index.html 업데이트"
fi

echo ""
git add .
git commit -m "$DISPLAY 순살브리핑"
git push

echo ""
echo "✅ 배포 완료!"
echo "  📖 https://letters.soonsal.com/$YEAR/$MMDD/"
echo "  🪙 https://letters.soonsal.com/$YEAR/$MMDD/crypto.html"
echo "  📱 https://letters.soonsal.com/$YEAR/$MMDD/cards.html"
echo "  🌐 https://letters.soonsal.com/$YEAR/$MMDD/publish.html"
echo ""
