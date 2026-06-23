#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER=$(whoami)
PYTHON=$(which python3)
VENV_DIR="$SCRIPT_DIR/venv"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "========================================"
echo "  slack-dashboard 설치 스크립트"
echo "  사용자: $USER"
echo "  Python: $PYTHON"
echo "  디렉토리: $SCRIPT_DIR"
echo "========================================"

# 1. 가상환경 생성 및 패키지 설치
echo ""
echo "[1/5] 가상환경 생성 및 패키지 설치..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
echo "  ✅ 완료 (venv: $VENV_DIR)"

# 2. .env 파일 확인
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo ""
  echo "[2/5] .env 파일 생성..."
  cat > "$SCRIPT_DIR/.env" << 'ENV'
SLACK_BOT_TOKEN=xoxb-여기에-실제-토큰-입력
SOURCE_CHANNEL_ID=C01HAVBQAQL
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8765
ENV
  chmod 600 "$SCRIPT_DIR/.env"
  echo "  ⚠️  .env 파일에 실제 토큰을 입력해주세요: $SCRIPT_DIR/.env"
else
  echo "[2/5] .env 파일 확인 완료"
fi

# 3. DB 초기화
echo ""
echo "[3/5] 데이터베이스 초기화..."
cd "$SCRIPT_DIR" && "$VENV_DIR/bin/python3" -c "import db; db.init_db(); print('  ✅ data.db 초기화 완료')"

# 4. plist 파일 생성 (venv Python 경로로 자동 치환)
echo ""
echo "[4/5] launchd plist 설치..."
mkdir -p "$LAUNCH_AGENTS"
VENV_PYTHON="$VENV_DIR/bin/python3"

for PLIST_SRC in "$SCRIPT_DIR/launchd/"*.plist; do
  PLIST_NAME=$(basename "$PLIST_SRC")
  PLIST_DEST="$LAUNCH_AGENTS/$PLIST_NAME"

  sed \
    -e "s|/opt/homebrew/bin/python3|$VENV_PYTHON|g" \
    -e "s|/Users/사용자이름|$HOME|g" \
    "$PLIST_SRC" > "$PLIST_DEST"

  launchctl unload "$PLIST_DEST" 2>/dev/null || true
  launchctl load   "$PLIST_DEST"
  echo "  ✅ $PLIST_NAME 등록 완료"
done

# 5. 방화벽 안내
echo ""
echo "[5/5] 내부 네트워크 접근 설정 안내"
echo "  LAN(192.168.x.x)만 허용하려면:"
echo "  sudo sh -c 'echo \"pass in proto tcp from 192.168.0.0/16 to any port 8765\" >> /etc/pf.conf'"
echo "  sudo pfctl -f /etc/pf.conf -e"

echo ""
echo "========================================"
echo "  설치 완료! 🎉"
echo ""
echo "  대시보드: http://$(ipconfig getifaddr en0):8765"
echo "  로그:     ~/Library/Logs/slack-dashboard.log"
echo ""
echo "  수동 수집 테스트:"
echo "    cd $SCRIPT_DIR && $VENV_PYTHON collector.py"
echo "========================================"
