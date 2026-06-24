@echo off
chcp 65001 > nul
echo ===== Slack Error Dashboard - Windows Setup =====
echo.

:: 스크립트 위치를 기준으로 프로젝트 경로 설정
set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python 이 설치되어 있지 않습니다.
    echo https://www.python.org 에서 설치 후 다시 실행하세요.
    pause & exit /b 1
)

:: 가상환경 생성
echo [1/4] 가상환경 생성 중...
python -m venv venv
call venv\Scripts\activate.bat

:: 패키지 설치
echo [2/4] 패키지 설치 중...
pip install -r requirements.txt --quiet

:: .env 파일 생성
echo [3/4] 환경 설정 파일 확인 중...
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo.
    echo  [주의] .env 파일이 생성됐습니다.
    echo  .env 파일을 열어 SLACK_BOT_TOKEN 을 실제 토큰으로 변경하세요.
    echo.
    pause
)

:: 로그 디렉토리 생성
if not exist "logs" mkdir logs

:: 작업 스케줄러 등록
echo [4/4] Windows 작업 스케줄러 등록 중...

:: 대시보드 서버 - 로그인 시 자동 시작
schtasks /create /tn "SlackErrorDashboard" ^
  /tr "\"%PROJECT_DIR%\windows\start_dashboard.bat\"" ^
  /sc onlogon /rl highest /f > nul
echo  - 대시보드 서버: 로그인 시 자동 시작 등록 완료

:: 수집기 - 매일 오전 11시
schtasks /create /tn "SlackErrorCollector" ^
  /tr "\"%PROJECT_DIR%\windows\run_collector.bat\"" ^
  /sc daily /st 11:00 /rl highest /f > nul
echo  - 수집기: 매일 오전 11:00 실행 등록 완료

echo.
echo ===== 설정 완료 =====
echo 지금 바로 대시보드를 시작하려면 windows\start_dashboard.bat 를 실행하세요.
echo.
pause
