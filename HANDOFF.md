# Windows 이전 핸드오프 노트

**작성일**: 2026-06-24  
**작업**: Mac 로컬 서버 → Windows PC 이전 및 내부망 접속 설정

---

## 발생 이슈 및 해결

### 1. `tzdata` 패키지 누락 (`requirements.txt`)

**증상**: `collector.py` 실행 시 `ZoneInfoNotFoundError: 'No time zone found with key Asia/Seoul'`  
**원인**: Windows에는 macOS/Linux와 달리 시스템 시간대 DB가 없어 `zoneinfo`가 `tzdata` pip 패키지를 필요로 함  
**해결**: `requirements.txt`에 `tzdata>=2024.1` 추가 후 `venv\Scripts\pip.exe install tzdata`로 venv에 설치

> **주의**: 반드시 `venv\Scripts\pip.exe`로 설치해야 venv 내부에 설치됨. 시스템 pip 사용 시 효과 없음

---

### 2. `windows\setup.bat` — `logs\` 폴더 미생성

**증상**: `run_collector.bat` 첫 실행 시 로그 파일을 쓰지 못하고 조용히 실패  
**원인**: `logs\collector.log`로 리다이렉션하지만 `logs\` 폴더가 자동 생성되지 않음  
**해결**: `setup.bat`에 `if not exist "logs" mkdir logs` 추가

---

### 3. `windows\run_collector.bat` — 잘못된 경로 처리 및 시스템 Python 사용

**증상**: bat 파일 실행해도 로그가 기록되지 않거나 여전히 tzdata 오류 발생  
**원인 1**: `%~dp0..` 경로(`windows\..`)가 `>>` 리다이렉션에서 올바르게 해석되지 않음  
**원인 2**: `call venv\Scripts\activate.bat` 방식이 Task Scheduler 환경에서 시스템 Python으로 실행됨  
**원인 3**: 한글 로그가 CP949로 출력되어 파일에서 깨짐  
**해결**:
- `cd /d "%~dp0.."` 후 상대경로 `logs\collector.log` 사용
- `venv\Scripts\python.exe`를 직접 호출 (활성화 방식 제거)
- `-X utf8` 플래그로 UTF-8 출력 강제

```bat
@echo off
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 collector.py >> "logs\collector.log" 2>&1
```

---

### 4. `windows\start_dashboard.bat` — 동일 경로 문제

**증상**: Task Scheduler에서 대시보드 서버가 시스템 Python으로 실행될 위험  
**해결**: `run_collector.bat`과 동일하게 venv Python 직접 호출 방식으로 변경

```bat
@echo off
cd /d "%~dp0.."
start /B venv\Scripts\pythonw.exe -m flask --app app run --host=0.0.0.0 --port=8765
```

---

### 5. 내부망 접속 설정

**방법**: Windows 방화벽 인바운드 규칙 추가 (관리자 권한 PowerShell)

```powershell
New-NetFirewallRule -DisplayName "Error Dashboard" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow
```

**접속 URL**: `http://192.168.10.141:8765`  
Flask가 `0.0.0.0`으로 바인딩되어 있어 코드 수정 불필요

---

## 현재 구성 요약

| 항목 | 내용 |
|------|------|
| 대시보드 URL | `http://localhost:8765` (로컬) / `http://192.168.10.141:8765` (내부망) |
| 수집기 자동 실행 | 매일 오전 11:00 (Windows Task Scheduler: `SlackErrorCollector`) |
| 서버 자동 실행 | 로그인 시 (Windows Task Scheduler: `SlackErrorDashboard`) |
| 로그 위치 | `logs\collector.log` |
| 수동 수집 | `venv\Scripts\python.exe -X utf8 collector.py` |

---

## 신규 PC 세팅 시 체크리스트

1. Python 3.10 이상 설치
2. `.env.example` → `.env` 복사 후 `SLACK_BOT_TOKEN` 입력
3. **관리자 권한**으로 `windows\setup.bat` 실행
4. `venv\Scripts\pip.exe install tzdata` (Windows 전용 필수)
5. 방화벽 규칙 추가 (내부망 공유 필요 시)
6. `windows\start_dashboard.bat` 실행 후 `http://localhost:8765` 확인
