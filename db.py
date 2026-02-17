# =========================================================
# db.py  —  SQLite 데이터베이스 헬퍼
# ---------------------------------------------------------
# quant.db 단일 파일로 모든 수집/스크리닝 데이터를 관리.
# collected_date 컬럼으로 날짜별 버전 관리 (기존 CSV 파일명 대체).
# =========================================================

import logging
import sqlite3

import pandas as pd

import config

log = logging.getLogger("DB")

# ─────────────────────────────────────────────
# 테이블 스키마
# ─────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS master (
    종목코드      TEXT NOT NULL,
    종목명        TEXT,
    시장구분      TEXT,
    종목구분      TEXT,
    collected_date TEXT NOT NULL,
    PRIMARY KEY (종목코드, collected_date)
);

CREATE TABLE IF NOT EXISTS daily (
    종목코드      TEXT NOT NULL,
    종목명        TEXT,
    종가          REAL,
    시가총액      REAL,
    상장주식수    REAL,
    EPS           REAL,
    BPS           REAL,
    주당배당금    REAL,
    기준일        TEXT,
    collected_date TEXT NOT NULL,
    PRIMARY KEY (종목코드, collected_date)
);

CREATE TABLE IF NOT EXISTS financial_statements (
    종목코드      TEXT NOT NULL,
    기준일        TEXT,
    계정          TEXT,
    주기          TEXT,
    값            REAL,
    추정치        INTEGER,
    collected_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS indicators (
    종목코드      TEXT NOT NULL,
    기준일        TEXT,
    지표구분      TEXT,
    계정          TEXT,
    값            REAL,
    collected_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shares (
    종목코드      TEXT NOT NULL,
    기준일        TEXT,
    발행주식수    INTEGER,
    자사주        INTEGER,
    유통주식수    INTEGER,
    collected_date TEXT NOT NULL,
    PRIMARY KEY (종목코드, collected_date)
);

CREATE TABLE IF NOT EXISTS price_history (
    종목코드      TEXT NOT NULL,
    날짜          TEXT NOT NULL,
    시가          REAL,
    고가          REAL,
    저가          REAL,
    종가          REAL,
    거래량        REAL,
    거래대금      REAL,
    collected_date TEXT NOT NULL,
    PRIMARY KEY (종목코드, 날짜, collected_date)
);

CREATE INDEX IF NOT EXISTS idx_fs_code_date
    ON financial_statements (종목코드, collected_date);
CREATE INDEX IF NOT EXISTS idx_ind_code_date
    ON indicators (종목코드, collected_date);
CREATE INDEX IF NOT EXISTS idx_ph_code_date
    ON price_history (종목코드, collected_date);

CREATE TABLE IF NOT EXISTS analysis_reports (
    종목코드      TEXT NOT NULL,
    종목명        TEXT,
    report_html   TEXT,
    scores_json   TEXT,
    model_used    TEXT,
    generated_date TEXT NOT NULL,
    PRIMARY KEY (종목코드)
);
"""


# ─────────────────────────────────────────────
# 연결
# ─────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
    log.info("DB 초기화 완료: %s", config.DB_PATH)


# ─────────────────────────────────────────────
# 쓰기
# ─────────────────────────────────────────────

def table_has_data(table: str, collected_date: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            f"SELECT COUNT(*) FROM [{table}] WHERE collected_date = ?",
            (collected_date,),
        )
        return cur.fetchone()[0] > 0


def save_df(df: pd.DataFrame, table: str, collected_date: str):
    if df.empty:
        return
    data = df.copy()
    data["collected_date"] = collected_date

    # Timestamp → "YYYY-MM-DD" 문자열 변환 (SQLite 호환)
    for col in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[col]):
            data[col] = data[col].dt.strftime("%Y-%m-%d")

    with get_conn() as conn:
        conn.execute(
            f"DELETE FROM [{table}] WHERE collected_date = ?",
            (collected_date,),
        )
        data.to_sql(table, conn, if_exists="append", index=False)

    log.info("저장: %s (%d건, date=%s)", table, len(data), collected_date)


def save_dashboard(df: pd.DataFrame):
    if df.empty:
        return
    with get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS dashboard_result")
        df.to_sql("dashboard_result", conn, index=False)
    log.info("저장: dashboard_result (%d건)", len(df))


# ─────────────────────────────────────────────
# 읽기
# ─────────────────────────────────────────────

def load_latest(table: str) -> pd.DataFrame:
    with get_conn() as conn:
        try:
            cur = conn.execute(
                f"SELECT MAX(collected_date) FROM [{table}]"
            )
        except sqlite3.OperationalError:
            return pd.DataFrame()

        row = cur.fetchone()
        if row is None or row[0] is None:
            return pd.DataFrame()

        latest = row[0]
        df = pd.read_sql(
            f"SELECT * FROM [{table}] WHERE collected_date = ?",
            conn,
            params=(latest,),
        )

    if "collected_date" in df.columns:
        df = df.drop(columns=["collected_date"])

    log.info("로드: %s (%d건, date=%s)", table, len(df), latest)
    return df


def load_dashboard() -> pd.DataFrame:
    with get_conn() as conn:
        try:
            df = pd.read_sql("SELECT * FROM dashboard_result", conn)
        except (sqlite3.OperationalError, pd.io.sql.DatabaseError):
            return pd.DataFrame()
    return df


# ─────────────────────────────────────────────
# 상태 조회 (webapp용)
# ─────────────────────────────────────────────

def save_report(code: str, name: str, html: str, scores_json: str,
                 model: str, date: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO analysis_reports
               (종목코드, 종목명, report_html, scores_json, model_used, generated_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, name, html, scores_json, model, date),
        )
    log.info("보고서 저장: %s %s", code, name)


def load_report(code: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM analysis_reports WHERE 종목코드 = ?",
            (code.zfill(6),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def list_reports() -> list[dict]:
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "SELECT 종목코드, 종목명, model_used, generated_date "
                "FROM analysis_reports ORDER BY generated_date DESC"
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except sqlite3.OperationalError:
            return []


def delete_report(code: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM analysis_reports WHERE 종목코드 = ?",
            (code.zfill(6),),
        )


def get_data_status() -> dict:
    tables = ["master", "daily", "financial_statements",
              "indicators", "shares", "price_history", "dashboard_result"]
    status = {}

    with get_conn() as conn:
        for t in tables:
            try:
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM [{t}]"
                )
                total = cur.fetchone()[0]
            except sqlite3.OperationalError:
                continue

            if total == 0:
                continue

            if t == "dashboard_result":
                status[t] = {"rows": total, "collected_date": "-"}
            else:
                cur2 = conn.execute(
                    f"SELECT MAX(collected_date) FROM [{t}]"
                )
                latest = cur2.fetchone()[0]
                status[t] = {"rows": total, "collected_date": latest}

    return status
