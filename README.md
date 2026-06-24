# Slack 오류 보고 대시보드

Slack 채널에 수집된 앱 오류 보고를 시각화하는 내부 대시보드입니다.  
Flask + SQLite 기반으로 동작하며, 수집기가 매일 오전 11시에 Slack API에서 데이터를 가져옵니다.

---

## 구성 파일

```
slack-dashboard/
├── app.py              # Flask 웹 서버 (포트 8765)
├── collector.py        # Slack 메시지 수집기
├── db.py               # SQLite 데이터 레이어
├── requirements.txt    # Python 패키지 목록
├── .env.example        # 환경변수 템플릿
├── templates/
│   └── dashboard.html  # 대시보드 UI
├── launchd/            # macOS 자동 실행 설정
└── windows/            # Windows 자동 실행 설정
```

---

## 설치 및 실행

### macOS

**1. 레포 클론**
```bash
git clone git@github.com:kalinzt/Error_Dashboard.git
cd Error_Dashboard
```

**2. 환경변수 설정**
```bash
cp .env.example .env
```
`.env` 파일을 열어 `SLACK_BOT_TOKEN`을 실제 토큰으로 교체합니다.

**3. 자동 설치 (가상환경 + launchd 등록)**
```bash
chmod +x setup.sh
./setup.sh
```

설치 완료 후 대시보드 서버와 수집기가 launchd에 자동 등록됩니다.
- 대시보드: 로그인 시 자동 시작, 종료 시 자동 재시작
- 수집기: 매일 오전 11:00 자동 실행

**4. 접속**
```
http://localhost:8765
```

---

### Windows

**1. 사전 준비**
- [Python 3.10+](https://www.python.org/downloads/) 설치 (설치 시 "Add Python to PATH" 체크)
- Git 설치 후 클론
```cmd
git clone git@github.com:kalinzt/Error_Dashboard.git
cd Error_Dashboard
```

**2. 환경변수 설정**
`.env.example`을 복사해 `.env`로 저장 후 `SLACK_BOT_TOKEN`을 실제 토큰으로 교체합니다.

**3. 자동 설치 (관리자 권한으로 실행)**
```
windows\setup.bat  ← 우클릭 → 관리자 권한으로 실행
```

설치 완료 후 Windows 작업 스케줄러에 자동 등록됩니다.
- 대시보드: 로그인 시 자동 시작
- 수집기: 매일 오전 11:00 자동 실행

**4. 대시보드 즉시 시작**
```
windows\start_dashboard.bat
```

**5. 접속**
```
http://localhost:8765
```

---

## 수동 실행

### macOS
```bash
# 가상환경 활성화
source venv/bin/activate

# 대시보드 서버 시작
python app.py

# 특정 날짜 수동 수집
python collector.py 2026-06-23

# 기간 수집
python collector.py 2026-06-01 2026-06-23
```

### Windows
```cmd
venv\Scripts\activate

python app.py
python collector.py 2026-06-23
python collector.py 2026-06-01 2026-06-23
```

---

## 환경변수 설명 (`.env`)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SLACK_BOT_TOKEN` | Slack Bot OAuth Token (`xoxb-...`) | 필수 입력 |
| `SOURCE_CHANNEL_ID` | 수집할 Slack 채널 ID | `C01HAVBQAQL` |
| `DASHBOARD_HOST` | 서버 바인딩 주소 | `0.0.0.0` |
| `DASHBOARD_PORT` | 서버 포트 | `8765` |

---

## 로그 위치

| OS | 경로 |
|----|------|
| macOS | `~/Library/Logs/slack-dashboard.log` |
| macOS | `~/Library/Logs/slack-collector.log` |
| Windows | `logs\collector.log` (프로젝트 폴더 내) |

---

## 주의사항

- `data.db` (수집 데이터), `.env` (토큰)은 `.gitignore`에 포함되어 있어 GitHub에 업로드되지 않습니다.
- 다른 PC로 이전 시 기존 `data.db`를 복사하거나, `collector.py`로 재수집합니다.
