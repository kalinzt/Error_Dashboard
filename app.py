"""
app.py — Flask 웹 서버
내부 LAN에서만 접근 가능한 오류 보고 대시보드를 제공합니다.
포트: 8765
"""
import os
from datetime import date
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
import db

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__, template_folder="templates", static_folder="static")
db.init_db()


# ── 대시보드 HTML ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("templates", "dashboard.html")


# ── REST API ──────────────────────────────────────────────────────────────────

@app.route("/api/overview")
def api_overview():
    """오늘/주간/월간 요약 통계"""
    return jsonify(db.overview())


@app.route("/api/trend")
def api_trend():
    """
    기간별 오류 추이
    ?period=daily|monthly|quarterly|semi_annual|annual[&since=YYYY-MM-DD&until=YYYY-MM-DD]
    """
    period   = request.args.get("period", "monthly")
    category = request.args.get("category", "")
    since    = request.args.get("since", "")
    until    = request.args.get("until", "")
    valid    = {"weekly", "daily", "monthly", "quarterly", "semi_annual", "annual"}
    if period not in valid:
        return jsonify({"error": "invalid period"}), 400
    return jsonify(db.trend(period, category, start=since, end=until))


def _resolve_since_until(period: str, since: str, until: str):
    """since/until이 명시되지 않은 경우 period로 since를 계산.
    annual처럼 period_since가 None을 반환하면 하한 없음(전체 기간)."""
    s = since or db.period_since(period)  # annual → None = 하한 없음
    u = until or None
    return s, u


@app.route("/api/categories")
def api_categories():
    """오류 유형 분포 — period 또는 since/until 기준"""
    period = request.args.get("period", "monthly")
    since  = request.args.get("since", "")
    until  = request.args.get("until", "")
    s, u   = _resolve_since_until(period, since, until)
    return jsonify(db.categories(s, u))


@app.route("/api/devices")
def api_devices():
    """디바이스 분포 (상위 10개) — period + category 기준"""
    period   = request.args.get("period", "monthly")
    category = request.args.get("category", "")
    since    = request.args.get("since", "")
    until    = request.args.get("until", "")
    s, u     = _resolve_since_until(period, since, until)
    return jsonify(db.devices(s, u, category))


@app.route("/api/versions")
def api_versions():
    """앱 버전 분포 — period + category 기준"""
    period   = request.args.get("period", "monthly")
    category = request.args.get("category", "")
    since    = request.args.get("since", "")
    until    = request.args.get("until", "")
    s, u     = _resolve_since_until(period, since, until)
    return jsonify(db.app_versions(s, u, category))


@app.route("/api/filter-options")
def api_filter_options():
    """디바이스·앱 버전 드롭다운 선택지 — period + category 기준"""
    period   = request.args.get("period", "")
    category = request.args.get("category", "")
    since    = request.args.get("since", "")
    until    = request.args.get("until", "")
    s        = since or (db.period_since(period) if period else None)
    u        = until or None
    return jsonify(db.filter_options(s, u, category))


@app.route("/api/errors")
def api_errors():
    """페이지네이션된 오류 목록 — period 또는 since/until + category + device + version 기준"""
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    period   = request.args.get("period", "")
    category = request.args.get("category", "")
    device   = request.args.get("device", "")
    version  = request.args.get("version", "")
    since    = request.args.get("since", "")
    until    = request.args.get("until", "")
    s        = since or (db.period_since(period) if period else None)
    u        = until or None
    return jsonify(db.recent_errors(page, per_page, s, u, category, device, version))


@app.route("/api/years")
def api_years():
    """데이터가 존재하는 연도 목록"""
    return jsonify(db.available_years())


@app.route("/api/count-range")
def api_count_range():
    """지정 날짜 범위 내 레코드 수"""
    start    = request.args.get("start", "")
    end      = request.args.get("end", "")
    category = request.args.get("category", "")
    if not start or not end:
        return jsonify({"count": 0})
    return jsonify({"count": db.count_in_range(start, end, category)})


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


# ── 실행 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", 8765))
    # debug=False 는 운영 환경에서 필수
    app.run(host=host, port=port, debug=False)
