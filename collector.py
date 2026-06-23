"""
collector.py — Slack 오류 채널 수집기
launchd에 의해 매일 오전 11시에 실행됩니다.
전날 00:00~23:59 KST 메시지를 읽어 파싱 후 SQLite에 저장합니다.
"""
import os
import re
import sys
import datetime
import logging
import requests
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import db

load_dotenv(Path(__file__).parent / ".env")

SLACK_TOKEN       = os.environ["SLACK_BOT_TOKEN"]
SOURCE_CHANNEL    = os.environ.get("SOURCE_CHANNEL_ID", "C01HAVBQAQL")
TIMEZONE          = ZoneInfo("Asia/Seoul")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── 오류 유형 분류 ─────────────────────────────────────────────────────────
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("컨텐츠", ["답지", "해설", "정답", "교재", "스마트", "기출문제", "컨텐츠", "페이지", "추가", "콘텐츠", "자료", "파일", "문서", "pdf", "ppt", "영상", "동영상", "사진", "업로드"]),
    ("펜/필기",    ["선굵기", "펜", "필기", "그림", "드래그", "획", "글씨", "이어지", "터치펜", "스타일러스"]),
    ("오디오/마이크", ["마이크", "음소거", "오디오", "소리", "목소리","안들린","안 들린", "안들리", "안 들리", "안 들립", "안들립", "안들려","안 들려", "안 들림", "음성", "볼륨", "무음"]),
    ("화면/UI",   ["화면", "버튼", "표시", "안보", "안 보", "렌더", "레이아웃", "팝업", "모달"]),
    ("연결/끊김",  ["무한", "통신", "네트워크", "인터넷", "로딩", "서버", "와이파이", "연결", "과외방", "수업방", "안 들어", "안들어", "못들어","못 들어", "들어가", "들어와", "끊기", "끊김", "끊긴", "끊어", "재연결", "튕기", "튕김", "튕김.", "튕겨", "튕깁", "틩깁","나감", "연결", "접속", "종료"]),
    ("앱/업데이트", ["업데이트", "설치가", "재설치", "실행", "충돌", "crash", "설탭 앱", "오류코드"]),
    ("앱/기능", ["설정", "마치기", "앱", "기능", "비밀번호", "일정", "마치기", "일정", "알림", "푸시", "로그아웃", "로그인", "회원가입", "계정", "아이디"]),
]

def categorize(text: str) -> str:
    lower = text.lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in lower for kw in keywords):
            return category
    return "기타"


# ── Slack 메시지 파싱 ────────────────────────────────────────────────────────
def _extract(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else default

def parse_message(text: str, slack_ts: str) -> dict | None:
    """
    Slack 메시지 원문에서 구조화된 데이터를 추출합니다.
    파싱 불가 메시지는 None 반환.
    """
    # 필수 필드가 없으면 스킵
    if "error_detail" not in text.lower() and "ISSUE_TIME" not in text:
        return None

    user_raw   = _extract(r"send_user_No\s*:\s*(\d+)\s*/\s*(STUDENT|TEACHER)", text)
    user_no    = _extract(r"send_user_No\s*:\s*(\d+)", text)
    user_type  = "STUDENT" if "STUDENT" in text.upper() else \
                 ("TEACHER" if "TEACHER" in text.upper() else "")

    error_detail = _extract(r"error_detail\s*:\s*(.+?)(?:\n|$)", text)
    issue_time_s = _extract(r"ISSUE_TIME:\s*(.+?)(?:\n|$)", text)
    device_info  = _extract(r"DEVICE_INFO:\s*(.+?)(?:\n|$)", text)
    os_version   = _extract(r"OS_VERSION:\s*(.+?)(?:\n|$)", text)
    device_id    = _extract(r"DEVICE_IDENTIFIER:\s*(.+?)(?:\n|$)", text)
    app_version  = _extract(r"APP_VERSION:\s*(.+?)(?:\n|$)", text)

    # 날짜 파싱
    ts_dt = datetime.datetime.fromtimestamp(float(slack_ts), tz=TIMEZONE)
    try:
        issue_dt = datetime.datetime.strptime(issue_time_s, "%Y-%m-%d %H:%M:%S")
        issue_dt_aware = issue_dt.replace(tzinfo=TIMEZONE)
        if issue_dt_aware > ts_dt:
            # ISSUE_TIME이 Slack 인입 시각보다 미래 → 잘못된 값으로 판단해 Slack ts로 보정
            log.warning(
                "ISSUE_TIME(%s)이 Slack 인입 시각(%s)보다 미래 → Slack ts로 보정 (slack_ts=%s)",
                issue_dt, ts_dt.strftime("%Y-%m-%d %H:%M:%S"), slack_ts,
            )
            issue_date = ts_dt.date().isoformat()
            issue_time = ts_dt.isoformat()
        else:
            issue_date = issue_dt.date().isoformat()
            issue_time = issue_dt.isoformat()
    except ValueError:
        # ISSUE_TIME 없으면 slack_ts에서 추출
        issue_date = ts_dt.date().isoformat()
        issue_time = ts_dt.isoformat()

    return {
        "issue_date":       issue_date,
        "issue_time":       issue_time,
        "send_user_no":     user_no,
        "user_type":        user_type,
        "error_detail":     error_detail,
        "error_category":   categorize(error_detail),
        "device_info":      device_info,
        "os_version":       os_version,
        "device_identifier": device_id,
        "app_version":      app_version,
        "slack_ts":         slack_ts,
        "raw_message":      text,
    }


# ── Slack API ────────────────────────────────────────────────────────────────
def fetch_messages(channel: str, oldest: float, latest: float) -> list[dict]:
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    all_msgs, cursor = [], None

    while True:
        params = dict(channel=channel, oldest=str(oldest),
                      latest=str(latest), limit=200, inclusive=True)
        if cursor:
            params["cursor"] = cursor

        resp = requests.get("https://slack.com/api/conversations.history",
                            headers=headers, params=params, timeout=30)
        data = resp.json()

        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error')}")

        all_msgs.extend(data.get("messages", []))
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    all_msgs.sort(key=lambda m: float(m.get("ts", 0)))
    return all_msgs


# ── 메인 ────────────────────────────────────────────────────────────────────
def main(target_date: datetime.date | None = None, return_counts: bool = False):
    db.init_db()

    if target_date is None:
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    tz = TIMEZONE
    start = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=tz)
    end   = datetime.datetime.combine(target_date, datetime.time.max, tzinfo=tz)

    log.info("수집 시작: %s (%s ~ %s KST)", target_date, start.time(), end.time())

    messages = fetch_messages(SOURCE_CHANNEL, start.timestamp(), end.timestamp())
    log.info("슬랙 메시지 %d건 조회", len(messages))

    saved, updated, skipped = 0, 0, 0
    for msg in messages:
        parsed = parse_message(msg.get("text", ""), msg.get("ts", "0"))
        if parsed is None:
            skipped += 1
            continue
        if db.save_error(parsed):
            saved += 1
        elif msg.get("edited"):
            # Slack에서 메시지가 편집된 경우 기존 레코드를 최신 내용으로 갱신
            if db.update_error(parsed):
                updated += 1
            else:
                skipped += 1
        else:
            skipped += 1  # 중복 (미편집)

    log.info("저장 완료: %d건 신규, %d건 업데이트, %d건 스킵", saved, updated, skipped)

    if return_counts:
        return saved, updated, skipped


if __name__ == "__main__":
    """
    사용법:
      python3 collector.py                          # 어제 하루
      python3 collector.py 2026-06-22               # 특정 하루
      python3 collector.py 2026-06-01 2026-06-22    # 기간 (시작일 ~ 종료일 포함)
    """
    args = sys.argv[1:]

    if len(args) == 0:
        # 인자 없음 → 어제
        main()

    elif len(args) == 1:
        # 날짜 1개 → 해당 하루
        main(datetime.date.fromisoformat(args[0]))

    elif len(args) == 2:
        # 날짜 2개 → 기간 수집
        start_date = datetime.date.fromisoformat(args[0])
        end_date   = datetime.date.fromisoformat(args[1])

        if start_date > end_date:
            print("오류: 시작일이 종료일보다 늦을 수 없습니다.")
            sys.exit(1)

        total_days = (end_date - start_date).days + 1
        log.info("기간 수집 시작: %s ~ %s (%d일)", start_date, end_date, total_days)

        total_saved, total_updated, total_skipped = 0, 0, 0
        current = start_date
        while current <= end_date:
            log.info("── %s 수집 중 (%d/%d일)", current,
                     (current - start_date).days + 1, total_days)
            saved, updated, skipped = main(current, return_counts=True)
            total_saved   += saved
            total_updated += updated
            total_skipped += skipped
            current += datetime.timedelta(days=1)

        log.info("기간 수집 완료: 총 %d건 신규, %d건 업데이트, %d건 스킵", total_saved, total_updated, total_skipped)

    else:
        print("사용법: python3 collector.py [시작일] [종료일]")
        print("  예시: python3 collector.py 2026-06-01 2026-06-22")
        sys.exit(1)
