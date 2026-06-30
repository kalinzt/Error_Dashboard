"""
db.py — SQLite 데이터베이스 레이어
모든 오류 보고를 저장하고 기간별 집계를 제공합니다.
"""
import sqlite3
from pathlib import Path
from datetime import date, timedelta

DB_PATH = Path(__file__).parent / "data.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """테이블 및 인덱스 초기화 (최초 1회 실행)"""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS error_reports (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            issue_date          DATE      NOT NULL,
            issue_time          TIMESTAMP,
            send_user_no        TEXT,
            user_type           TEXT,                  -- STUDENT | TEACHER
            error_detail        TEXT,
            error_category      TEXT,                  -- 펜/필기 | 오디오 | 화면/UI | 연결 | 앱 | 기타
            device_info         TEXT,
            os_version          TEXT,
            device_identifier   TEXT,
            app_version         TEXT,
            slack_ts            TEXT UNIQUE,           -- 중복 방지
            raw_message         TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_issue_date      ON error_reports(issue_date);
        CREATE INDEX IF NOT EXISTS idx_user_type       ON error_reports(user_type);
        CREATE INDEX IF NOT EXISTS idx_error_category  ON error_reports(error_category);
        CREATE INDEX IF NOT EXISTS idx_app_version     ON error_reports(app_version);
        CREATE INDEX IF NOT EXISTS idx_device          ON error_reports(device_identifier);
        """)


def save_error(data: dict) -> bool:
    """오류 1건 저장. 중복(slack_ts 기준)이면 무시하고 False 반환."""
    with get_conn() as conn:
        cur = conn.execute("""
        INSERT OR IGNORE INTO error_reports
            (issue_date, issue_time, send_user_no, user_type, error_detail,
             error_category, device_info, os_version, device_identifier,
             app_version, slack_ts, raw_message)
        VALUES
            (:issue_date, :issue_time, :send_user_no, :user_type, :error_detail,
             :error_category, :device_info, :os_version, :device_identifier,
             :app_version, :slack_ts, :raw_message)
        """, data)
    return cur.rowcount == 1


def update_error(data: dict) -> bool:
    """편집된 메시지의 파싱 결과로 기존 레코드를 갱신. slack_ts 기준으로 찾아 업데이트."""
    with get_conn() as conn:
        cur = conn.execute("""
        UPDATE error_reports SET
            issue_date        = :issue_date,
            issue_time        = :issue_time,
            send_user_no      = :send_user_no,
            user_type         = :user_type,
            error_detail      = :error_detail,
            error_category    = :error_category,
            device_info       = :device_info,
            os_version        = :os_version,
            device_identifier = :device_identifier,
            app_version       = :app_version,
            raw_message       = :raw_message
        WHERE slack_ts = :slack_ts
        """, data)
    return cur.rowcount == 1


# ── 집계 쿼리 ─────────────────────────────────────────────────────────────────

def overview() -> dict:
    """오늘 / 이번 주 / 이번 달 통계 + 가장 많은 오류 유형"""
    today = date.today().isoformat()
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    month_start = date.today().replace(day=1).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last_week_start = (date.today() - timedelta(days=date.today().weekday() + 7)).isoformat()
    last_month_start = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()

    with get_conn() as conn:
        def count(start, end=None):
            if end:
                return conn.execute(
                    "SELECT COUNT(*) FROM error_reports WHERE issue_date BETWEEN ? AND ?",
                    (start, end)
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM error_reports WHERE issue_date = ?", (start,)
            ).fetchone()[0]

        today_cnt      = count(today)
        yesterday_cnt  = count(yesterday)
        week_cnt       = conn.execute(
            "SELECT COUNT(*) FROM error_reports WHERE issue_date >= ?", (week_start,)
        ).fetchone()[0]
        last_week_cnt  = conn.execute(
            "SELECT COUNT(*) FROM error_reports WHERE issue_date >= ? AND issue_date < ?",
            (last_week_start, week_start)
        ).fetchone()[0]
        month_cnt      = conn.execute(
            "SELECT COUNT(*) FROM error_reports WHERE issue_date >= ?", (month_start,)
        ).fetchone()[0]
        last_month_cnt = conn.execute(
            "SELECT COUNT(*) FROM error_reports WHERE issue_date >= ? AND issue_date < ?",
            (last_month_start, month_start)
        ).fetchone()[0]

        top_cats = conn.execute("""
            SELECT error_category, COUNT(*) as cnt
            FROM error_reports
            WHERE issue_date >= ?
            GROUP BY error_category ORDER BY cnt DESC LIMIT 3
        """, (month_start,)).fetchall()

    def pct_change(curr, prev):
        if prev == 0:
            return None
        return round((curr - prev) / prev * 100, 1)

    return {
        "today":      {"count": today_cnt,  "change": pct_change(today_cnt, yesterday_cnt)},
        "week":       {"count": week_cnt,   "change": pct_change(week_cnt, last_week_cnt)},
        "month":      {"count": month_cnt,  "change": pct_change(month_cnt, last_month_cnt)},
        "top_categories": [{"name": r["error_category"], "count": r["cnt"]} for r in top_cats],
    }


def trend(period: str, category: str = "", start: str = "", end: str = "", breakdown: str = "user_type") -> dict:
    """
    기간별 오류 발생 추이.
    period: 그룹핑 단위 (weekly|daily=일별, monthly=월별, quarterly=분기별,
                          semi_annual=반기별, annual=연도별)
    start:  명시적 시작일 (ISO 문자열) — period 기반 시작일을 대체
    end:    명시적 종료일 (ISO 문자열) — 상한 제한 (분기/반기 선택 시 사용)
    """
    LABEL_EXPR = {
        'weekly':      "issue_date",
        'daily':       "issue_date",
        'monthly':     "strftime('%Y-%m', issue_date)",
        'quarterly':   ("strftime('%Y', issue_date) || '-Q' ||"
                        " ((CAST(strftime('%m', issue_date) AS INTEGER)-1)/3+1)"),
        'semi_annual': ("strftime('%Y', issue_date) || '-H' ||"
                        " (CASE WHEN CAST(strftime('%m', issue_date) AS INTEGER) <= 6"
                        "  THEN '1' ELSE '2' END)"),
        'annual':      "strftime('%Y', issue_date)",
    }
    SINCE_EXPR = {
        'weekly':      "date('now','-7 days')",
        'daily':       "date('now','-30 days')",
        'monthly':     "date('now','-12 months')",
        'quarterly':   "date('now','-2 years')",
        'semi_annual': "date('now','-3 years')",
    }
    label_expr = LABEL_EXPR.get(period, "issue_date")

    with get_conn() as conn:
        if start:
            since_date = start
        elif period in SINCE_EXPR:
            since_date = conn.execute(f"SELECT {SINCE_EXPR[period]}").fetchone()[0]
        else:
            since_date = None

        conds, params = [], []
        if since_date:
            conds.append("issue_date >= ?")
            params.append(since_date)
        if end:
            conds.append("issue_date <= ?")
            params.append(end)
        if category:
            conds.append("error_category = ?")
            params.append(category)

        where = ("WHERE " + " AND ".join(conds)) if conds else ""

        if breakdown == "category":
            rows = conn.execute(f"""
                SELECT {label_expr} as label,
                       COALESCE(error_category, '기타') as cat,
                       COUNT(*) as cnt
                FROM error_reports {where}
                GROUP BY label, cat ORDER BY label, cat
            """, tuple(params)).fetchall()
            label_cat: dict = {}
            for r in rows:
                label_cat.setdefault(r["label"], {})[r["cat"]] = r["cnt"]
            all_labels = sorted(label_cat.keys())
            all_cats = sorted(
                {c for d in label_cat.values() for c in d},
                key=lambda c: -sum(d.get(c, 0) for d in label_cat.values()),
            )
            return {
                "labels":     all_labels,
                "breakdown":  "category",
                "categories": [
                    {"name": cat, "data": [label_cat[l].get(cat, 0) for l in all_labels]}
                    for cat in all_cats
                ],
                "total": sum(r["cnt"] for r in rows),
            }

        rows = conn.execute(f"""
            SELECT {label_expr} as label,
                   COUNT(*) as total,
                   SUM(user_type='STUDENT') as student,
                   SUM(user_type='TEACHER') as teacher
            FROM error_reports {where}
            GROUP BY label ORDER BY label
        """, tuple(params)).fetchall()

    return {
        "labels":    [r["label"]   for r in rows],
        "breakdown": "user_type",
        "student":   [r["student"] for r in rows],
        "teacher":   [r["teacher"] for r in rows],
        "total":     sum(r["total"] for r in rows),
    }


def period_since(period: str) -> str | None:
    """기간 키 → 시작일 ISO 문자열. annual 또는 미지정은 None(전체)."""
    EXPR = {
        'weekly':      "date('now','-7 days')",
        'daily':       "date('now','-30 days')",
        'monthly':     "date('now','-12 months')",
        'quarterly':   "date('now','-2 years')",
        'semi_annual': "date('now','-3 years')",
    }
    expr = EXPR.get(period)
    if not expr:
        return None
    with get_conn() as conn:
        return conn.execute(f"SELECT {expr}").fetchone()[0]


def categories(start_date: str | None = None, until: str | None = None) -> list[dict]:
    """오류 유형 분포. start_date=None이면 전체 기간."""
    conds, params = [], []
    if start_date:
        conds.append("issue_date >= ?"); params.append(start_date)
    if until:
        conds.append("issue_date <= ?"); params.append(until)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT error_category as name, COUNT(*) as count
            FROM error_reports {where}
            GROUP BY error_category ORDER BY count DESC
        """, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def devices(start_date: str | None = None, until: str | None = None,
            category: str = "") -> list[dict]:
    """디바이스 분포 (상위 10개). start_date=None이면 전체 기간."""
    conds, params = [], []
    if start_date:
        conds.append("issue_date >= ?"); params.append(start_date)
    if until:
        conds.append("issue_date <= ?"); params.append(until)
    if category:
        conds.append("error_category = ?"); params.append(category)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT {_DEVICE_NAME_EXPR} as name, COUNT(*) as count
            FROM error_reports {where}
            GROUP BY name ORDER BY count DESC LIMIT 10
        """, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def app_versions(start_date: str | None = None, until: str | None = None,
                 category: str = "") -> list[dict]:
    """앱 버전 분포. start_date=None이면 전체 기간."""
    conds, params = [], []
    if start_date:
        conds.append("issue_date >= ?"); params.append(start_date)
    if until:
        conds.append("issue_date <= ?"); params.append(until)
    if category:
        conds.append("error_category = ?"); params.append(category)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT COALESCE(NULLIF(app_version,''), '알 수 없음') as name,
                   COUNT(*) as count
            FROM error_reports {where}
            GROUP BY app_version ORDER BY count DESC LIMIT 10
        """, tuple(params)).fetchall()
    return [dict(r) for r in rows]


_DEVICE_NAME_EXPR = """
    CASE
      WHEN device_identifier LIKE 'SM-%' AND device_info LIKE '%의 %'
      THEN SUBSTR(device_info, INSTR(device_info, '의 ') + 2)
      WHEN device_identifier LIKE 'SM-%' AND device_info LIKE '%''s %'
      THEN SUBSTR(device_info, INSTR(device_info, '''s ') + 3)
      WHEN device_identifier LIKE 'SM-%' AND device_info LIKE 'Galaxy %'
      THEN SUBSTR(device_info, 8)
      ELSE COALESCE(NULLIF(device_identifier,''), '알 수 없음')
    END"""


def filter_options(start_date: str | None = None, until: str | None = None,
                   category: str = "") -> dict:
    """디바이스/앱 버전 드롭다운 선택지 — 기간·카테고리 기준으로 집계. start_date=None이면 전체 기간."""
    conds, params = [], []
    if start_date:
        conds.append("issue_date >= ?"); params.append(start_date)
    if until:
        conds.append("issue_date <= ?"); params.append(until)
    if category:
        conds.append("error_category = ?"); params.append(category)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    p = tuple(params)
    with get_conn() as conn:
        dev_rows = conn.execute(f"""
            SELECT DISTINCT {_DEVICE_NAME_EXPR} AS name
            FROM error_reports {where} ORDER BY name
        """, p).fetchall()
        ver_rows = conn.execute(f"""
            SELECT DISTINCT COALESCE(NULLIF(app_version,''), '알 수 없음') AS name
            FROM error_reports {where} ORDER BY name
        """, p).fetchall()
    return {
        "devices":  [r["name"] for r in dev_rows],
        "versions": [r["name"] for r in ver_rows],
    }


def available_years() -> list[int]:
    """데이터가 존재하는 연도 목록 (오름차순)"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT CAST(strftime('%Y', issue_date) AS INTEGER) as year
            FROM error_reports ORDER BY year
        """).fetchall()
    return [r["year"] for r in rows]


def update_category(error_id: int, category: str) -> bool:
    """오류 분류를 수동으로 보정. id 기준으로 error_category 업데이트."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE error_reports SET error_category = ? WHERE id = ?",
            (category, error_id)
        )
    return cur.rowcount == 1


def count_in_range(start: str, end: str, category: str = "") -> int:
    """지정 날짜 범위 내 레코드 수"""
    conds = ["issue_date >= ?", "issue_date <= ?"]
    params: list = [start, end]
    if category:
        conds.append("error_category = ?"); params.append(category)
    where = "WHERE " + " AND ".join(conds)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM error_reports {where}", tuple(params)
        ).fetchone()[0]


def recent_errors(page: int = 1, per_page: int = 20,
                  since: str | None = None,
                  until: str | None = None,
                  category: str = "",
                  device: str = "",
                  version: str = "",
                  user_no: str = "",
                  date: str = "") -> dict:
    """
    페이지네이션된 오류 목록.
    반환: { items, total, page, per_page, total_pages }
    """
    page     = max(1, page)
    per_page = max(1, min(per_page, 200))
    offset   = (page - 1) * per_page

    conds, params = [], []
    if since:
        conds.append("issue_date >= ?")
        params.append(since)
    if until:
        conds.append("issue_date <= ?")
        params.append(until)
    if category:
        conds.append("error_category = ?")
        params.append(category)
    if device:
        conds.append(f"({_DEVICE_NAME_EXPR}) = ?")
        params.append(device)
    if version:
        conds.append("COALESCE(NULLIF(app_version,''), '알 수 없음') = ?")
        params.append(version)
    if user_no:
        conds.append("send_user_no LIKE ?")
        params.append(f"%{user_no}%")
    if date:
        conds.append("issue_date = ?")
        params.append(date)

    where    = ("WHERE " + " AND ".join(conds)) if conds else ""
    params_t = tuple(params)

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM error_reports {where}", params_t
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT id, issue_time, send_user_no, user_type, error_category,
                       error_detail, device_identifier, app_version, device_info
                FROM error_reports {where}
                ORDER BY issue_time DESC
                LIMIT ? OFFSET ?""",
            params_t + (per_page, offset)
        ).fetchall()

    return {
        "items":       [dict(r) for r in rows],
        "total":       total,
        "page":        page,
        "per_page":    per_page,
        "total_pages": max(1, -(-total // per_page)),
    }
