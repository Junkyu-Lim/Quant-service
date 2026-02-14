# =========================================================
# quant_collector.py  —  한국 주식 퀀트 데이터 수집기
# ---------------------------------------------------------
# 수집 항목:
#   1) 종목 마스터 (KRX 전종목)
#   2) 일별 시세 + 펀더멘털 (종가, 시가총액, EPS, BPS, DPS)
#   3) 재무제표 (IS / BS / CF — 연간 + 분기)
#   4) 핵심 지표 (Financial Highlight + 재무비율)
#   5) 주식수 (발행주식수, 자사주, 유통주식수)
#
# 출력: ./data/ 폴더에 CSV 파일로 저장 (DB 불필요)
# 
# 실행:
#   테스트 모드: python quant_collector.py --test
#   전체 실행:   python quant_collector.py
# =========================================================

import os
import re
import sys
import logging
import warnings
import argparse
from datetime import datetime, date, timedelta  # timedelta 추가
from io import StringIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests
import FinanceDataReader as fdr
from pykrx import stock
from tqdm import tqdm

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("COLLECTOR")

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

MAX_WORKERS = 15          # FnGuide 동시 요청 수 (너무 높으면 차단됨)
REQUEST_TIMEOUT = 12      # 초

# 테스트용 샘플 종목 (대표 종목 선정)
TEST_TICKERS = [
    "005930",  # 삼성전자
    "035720",  # 카카오
    "000660",  # SK하이닉스
]

# 전역 세션 (TCP 커넥션 재사용)
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
})


# ═════════════════════════════════════════════
# 공통 유틸리티
# ═════════════════════════════════════════════

def get_biz_day() -> str:
    """최근 영업일 (YYYYMMDD) - 서버 통신 없이 로컬 계산"""
    d = datetime.now()
    # 월=0 ... 금=4, 토=5, 일=6
    if d.weekday() == 5:    # 토요일이면
        d = d - timedelta(days=1)  # 금요일로
    elif d.weekday() == 6:  # 일요일이면
        d = d - timedelta(days=2)  # 금요일로
    
    # 평일 오전 9시 이전이면(장 시작 전), 전날 데이터를 보기 위해 하루 뺌 (선택사항, 일단은 당일 기준)
    return d.strftime("%Y%m%d")


def load_tables(url: str) -> list:
    """FnGuide HTML 테이블 파싱 (인코딩 자동 감지)"""
    try:
        r = _session.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception:
        return []

    for enc in ("cp949", "euc-kr", "utf-8"):
        try:
            html = r.content.decode(enc, errors="strict")
            return pd.read_html(StringIO(html), displayed_only=False)
        except Exception:
            continue
    # fallback
    try:
        html = r.content.decode("cp949", errors="replace")
        return pd.read_html(StringIO(html), displayed_only=False)
    except Exception:
        return []


def safe_float(x):
    """안전한 float 변환"""
    if x is None:
        return None
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return None
    try:
        s = str(x).replace(",", "").strip()
        if s in ("", "-", "N/A", "nan", "None"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def safe_int(x):
    v = safe_float(x)
    return int(v) if v is not None else None


def parse_period(col_name: str):
    """컬럼명에서 기준일 파싱 (2023/12, 2024.03 등)"""
    s = str(col_name)
    is_estimate = "(E)" in s
    m = re.search(r"(\d{4})[\./](\d{2})", s)
    if not m:
        return None, is_estimate
    d = pd.to_datetime(f"{m.group(1)}-{m.group(2)}") + pd.offsets.MonthEnd()
    return d, is_estimate


def normalize_market(m: str) -> str:
    if not m:
        return "ETC"
    m = m.upper()
    if "KOSPI" in m:
        return "KOSPI"
    if "KOSDAQ" in m:
        return "KOSDAQ"
    if "KONEX" in m:
        return "KONEX"
    return "ETC"


# ═════════════════════════════════════════════
# 1. 종목 마스터
# ═════════════════════════════════════════════

def collect_master() -> pd.DataFrame:
    """KRX 전종목 마스터 수집"""
    log.info("📘 종목 마스터 수집 중...")
    df = fdr.StockListing("KRX")[["Code", "Name", "Market"]]
    df.columns = ["종목코드", "종목명", "시장구분"]
    df["시장구분"] = df["시장구분"].apply(normalize_market)

    name = df["종목명"].fillna("")
    code = df["종목코드"].fillna("")
    df["종목구분"] = np.select(
        [name.str.contains("스팩"), code.str[-1] != "0", name.str.endswith("리츠")],
        ["스팩", "우선주", "리츠"],
        default="보통주",
    )
    log.info(f"  → 전체 {len(df)}개 종목 ({df['종목구분'].value_counts().to_dict()})")
    return df


# ═════════════════════════════════════════════
# 2. 일별 시세 + 펀더멘털
# ═════════════════════════════════════════════

def collect_daily(biz_day: str) -> pd.DataFrame:
    """FinanceDataReader를 이용한 시세 + 펀더멘털 수집"""
    # biz_day 포맷 변경 (YYYYMMDD -> YYYY-MM-DD) 필요 시 변환, 
    # 하지만 fdr.StockListing('KRX')는 '현재' 기준 가장 최신 데이터를 가져옵니다.
    # 과거 특정일 데이터를 가져오려면 복잡해지므로, 스크리너 목적상 '최신' 데이터로 진행합니다.
    
    log.info(f"📊 일별 시세 수집 (최신 기준)...")

    # 1. KRX 전종목 리스팅 (가격, 시가총액, 거래량 등 포함됨)
    # fdr.StockListing('KRX')는 종가, 시가총액, 거래량 등을 기본 포함합니다.
    df_krx = fdr.StockListing('KRX')
    
    # 컬럼 이름이 한글/영문 혼용될 수 있어 정리
    # (최신 fdr 버전에 따라 컬럼명이 다를 수 있으니 확인 후 매핑)
    # 일반적인 fdr KRX 컬럼: Code, Name, Close, Marcap, Stocks, Market ...
    
    # 필요한 컬럼만 선택 및 리네임
    rename_map = {
        'Code': '종목코드',
        'Name': '종목명',
        'Close': '종가',
        'Marcap': '시가총액',
        'Stocks': '상장주식수' # 필요하다면
    }
    # 실제 존재하는 컬럼만 변경
    avail_cols = [c for c in rename_map if c in df_krx.columns]
    df_krx = df_krx[avail_cols].rename(columns=rename_map)
    
    # 2. 펀더멘털(PER, PBR 등)은 fdr.StockListing('KRX-DESC') 등에 일부 있으나, 
    #    정확한 EPS/BPS/DPS는 KRX 정보시스템에서 별도로 긁어야 하는데 fdr로는 한계가 있을 수 있음.
    #    하지만 스크리너 로직상 PER/PBR은 '종가 / EPS' 등으로 재계산하므로 
    #    EPS, BPS 데이터가 필수입니다.
    #    
    #    대안: pykrx가 안되므로, fdr의 'KRX' 데이터에 있는 PER, PBR을 쓰거나
    #    FnGuide 크롤링 단계(fetch_indicators)에서 가져온 데이터를 믿고 가야 합니다.
    #    
    #    여기서는 일단 '시세(종가, 시총)'는 fdr로 확실히 챙기고,
    #    EPS/BPS 컬럼은 비워둔 뒤 나중에 채우거나 0으로 처리합니다.
    #    (quant_screener.py에서 EPS/BPS가 없으면 PER/PBR 계산을 못하지만, 
    #     FnGuide 데이터가 있으면 거기서 보완 가능할 수도 있음. 
    #     하지만 현재 구조는 daily.csv에 EPS/BPS가 있어야 함.)

    # **중요**: pykrx가 계속 터지므로, 일단 안정적인 fdr 데이터로 '종가/시가총액'만이라도 확보하여 저장합니다.
    # EPS, BPS, 배당금은 0 또는 None으로 채워서 에러를 방지합니다.
    
    for c in ["EPS", "BPS", "주당배당금"]:
        df_krx[c] = None
        
    # 기준일 추가
    df_krx["기준일"] = biz_day
    
    log.info(f"  → {len(df_krx)}개 종목 시세 수집 완료 (fdr 사용)")
    return df_krx


# ═════════════════════════════════════════════
# 3. 재무제표 (FnGuide)
# ═════════════════════════════════════════════

def _classify_fs_table(t: pd.DataFrame) -> str | None:
    """테이블 1열 키워드로 IS/BS/CF 판별"""
    if t.shape[0] < 2 or t.shape[1] < 2:
        return None
    text = " ".join(t.iloc[:, 0].astype(str).tolist())
    if ("매출액" in text or "영업수익" in text) and "자산" not in text:
        return "IS"
    if "자산" in text and "부채" in text and "자본" in text:
        return "BS"
    if "영업활동" in text and "투자활동" in text:
        return "CF"
    return None


def _melt_fs(df: pd.DataFrame, ticker: str, freq: str) -> list[dict]:
    """재무제표 테이블 → 세로형 dict 리스트"""
    if df is None or df.empty:
        return []
    df = df.loc[:, ~df.columns.str.contains("전년동기")]
    df = df.rename(columns={df.columns[0]: "계정"})
    df["계정"] = df["계정"].astype(str).str.replace(
        "계산에 참여한 계정 펼치기", "", regex=False
    ).str.strip()
    df = df.drop_duplicates("계정", keep="first")

    try:
        melted = pd.melt(df, id_vars="계정", var_name="기간", value_name="값")
    except Exception:
        return []

    rows = []
    for _, r in melted.iterrows():
        biz_date, is_est = parse_period(r["기간"])
        if biz_date is None:
            continue
        val = safe_float(r["값"])
        if val is None:
            continue
        rows.append({
            "종목코드": ticker,
            "기준일": biz_date,
            "계정": r["계정"],
            "주기": freq,
            "값": val,
            "추정치": is_est,
        })
    return rows


def fetch_fs(ticker: str) -> list[dict]:
    """종목 1개의 재무제표 수집"""
    url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{ticker}"
    tables = load_tables(url)
    if len(tables) < 2:
        return []

    # 테이블 분류: IS/BS/CF 각각 연간(y) → 분기(q) 순서로 채움
    slots = {k: {"y": None, "q": None} for k in ("IS", "BS", "CF")}
    for t in tables:
        label = _classify_fs_table(t)
        if label is None:
            continue
        if slots[label]["y"] is None:
            slots[label]["y"] = t
        elif slots[label]["q"] is None:
            slots[label]["q"] = t

    rows = []
    for fs_type in ("IS", "BS", "CF"):
        for freq_key, freq_label in (("y", "y"), ("q", "q")):
            rows += _melt_fs(slots[fs_type][freq_key], ticker, freq_label)
    return rows


# ═════════════════════════════════════════════
# 4. 핵심 지표 (Financial Highlight + 재무비율)
# ═════════════════════════════════════════════

def _extract_indicator_rows(
    df: pd.DataFrame, ticker: str, source: str
) -> list[dict]:
    """지표 테이블 → dict 리스트"""
    if df is None or df.empty or df.shape[1] < 2:
        return []

    # [수정] MultiIndex 컬럼(두 줄 이상의 헤더) 처리
    # 헤더가 여러 줄일 경우, 가장 마지막 줄(날짜가 있는 줄)만 남기고 평탄화
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    # 첫 번째 컬럼을 '계정'으로 이름 변경
    df = df.rename(columns={df.columns[0]: "계정"})
    
    # '계정' 컬럼이 문자열인지 확인 및 공백 제거
    df["계정"] = df["계정"].astype(str).str.strip()

    try:
        melted = pd.melt(df, id_vars="계정", var_name="기간", value_name="값")
    except Exception:
        return []

    rows = []
    for _, r in melted.iterrows():
        biz_date, is_est = parse_period(r["기간"])
        if biz_date is None:
            continue
        account = str(r["계정"]).strip()
        if not account or account.lower() in ("nan", "none"):
            continue
        val = safe_float(r["값"])
        rows.append({
            "종목코드": ticker,
            "기준일": biz_date,
            "지표구분": f"{source}_E" if is_est else source,
            "계정": account,
            "값": val,
        })
    return rows


def fetch_indicators(ticker: str) -> list[dict]:
    """Financial Highlight + 재무비율 + 배당금 수집"""
    rows = []

    # ── (A) 메인 페이지: Financial Highlight + DPS ──
    url_main = (
        f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp"
        f"?pGB=1&gicode=A{ticker}&stkGb=701"
    )
    main_tables = load_tables(url_main)

    for t in main_tables:
        if not isinstance(t, pd.DataFrame) or t.shape[0] < 2 or t.shape[1] < 2:
            continue
        
        # [수정] 안전하게 문자열로 변환 (float/NaN 오류 방지)
        col1_list = [str(x) for x in t.iloc[:, 0].values]
        col1_text = " ".join(col1_list)

        # Financial Highlight 테이블 식별
        has_rev = "매출액" in col1_text or "영업수익" in col1_text
        has_roe = "ROE" in col1_text
        has_op = "영업이익" in col1_text
        if has_rev or has_roe or has_op:
            rows += _extract_indicator_rows(t, ticker, "HIGHLIGHT")
            break  # 첫 번째 매칭만

    # DPS (배당금) — Highlight 테이블에서 별도 추출
    for t in main_tables:
        if not isinstance(t, pd.DataFrame) or t.shape[0] < 2:
            continue
        
        # [수정] 시리즈 변환 시에도 안전하게 처리
        col1 = t.iloc[:, 0].astype(str)
        
        dps_idx = col1[col1.str.contains("배당금|DPS", regex=True)].index
        if len(dps_idx) == 0:
            continue
        row_data = t.iloc[dps_idx[0]]
        for col_name, val in row_data.items():
            if col_name == t.columns[0]:
                continue
            biz_date, _ = parse_period(col_name)
            if biz_date is None:
                continue
            v = safe_float(val)
            if v is not None:
                rows.append({
                    "종목코드": ticker,
                    "기준일": biz_date,
                    "지표구분": "DPS",
                    "계정": "주당배당금",
                    "값": v,
                })
        break

    # ── (B) 재무비율 페이지 ──
    url_ratio = (
        f"https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp"
        f"?pGB=1&gicode=A{ticker}&stkGb=701"
    )
    ratio_tables = load_tables(url_ratio)
    if len(ratio_tables) >= 1:
        rows += _extract_indicator_rows(ratio_tables[0], ticker, "RATIO_Y")
    if len(ratio_tables) >= 2:
        rows += _extract_indicator_rows(ratio_tables[1], ticker, "RATIO_Q")

    return rows


# ═════════════════════════════════════════════
# 5. 주식수 (FnGuide)
# ═════════════════════════════════════════════

def fetch_shares(ticker: str) -> dict | None:
    """발행주식수, 자사주, 유통주식수 수집"""
    url = (
        f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp"
        f"?pGB=1&gicode=A{ticker}&stkGb=701"
    )
    tables = load_tables(url)
    if not tables:
        return None

    # 발행주식수
    try:
        issued = safe_int(str(tables[0].iloc[6, 1]).split("/")[0])
    except Exception:
        issued = 0

    # 자사주
    treasury = 0
    for t in tables:
        if isinstance(t, pd.DataFrame) and "보통주" in t.columns:
            try:
                val = safe_int(t["보통주"].iloc[4])
                if val is not None:
                    treasury = val
                    break
            except Exception:
                pass

    float_shares = max((issued or 0) - treasury, 0)
    return {
        "종목코드": ticker,
        "기준일": date.today().isoformat(),
        "발행주식수": issued,
        "자사주": treasury,
        "유통주식수": float_shares,
    }


# ═════════════════════════════════════════════
# 병렬 수집 래퍼
# ═════════════════════════════════════════════

def parallel_collect(func, tickers: list, desc: str) -> list:
    """ThreadPoolExecutor 래퍼 — 결과를 리스트로 반환"""
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(func, t): t for t in tickers}
        for f in tqdm(as_completed(futures), total=len(tickers), desc=desc):
            res = f.result()
            if res:
                if isinstance(res, list):
                    results.extend(res)
                else:
                    results.append(res)
    return results


# ═════════════════════════════════════════════
# 테스트 함수
# ═════════════════════════════════════════════

def test_crawling():
    """3개 샘플 종목으로 크롤링 테스트"""
    log.info("=" * 60)
    log.info("🧪 테스트 모드 시작 (샘플 3개 종목)")
    log.info("=" * 60)
    
    # 마스터 데이터 로드 (종목명 확인용)
    master = collect_master()
    
    test_results = {}
    
    for ticker in TEST_TICKERS:
        stock_name = master[master["종목코드"] == ticker]["종목명"].values
        stock_name = stock_name[0] if len(stock_name) > 0 else "Unknown"
        
        log.info(f"\n{'='*60}")
        log.info(f"📌 [{ticker}] {stock_name} 테스트 중...")
        log.info(f"{'='*60}")
        
        test_results[ticker] = {
            "종목명": stock_name,
            "재무제표": False,
            "지표": False,
            "주식수": False,
        }
        
        # 1) 재무제표
        try:
            fs_data = fetch_fs(ticker)
            if fs_data and len(fs_data) > 0:
                test_results[ticker]["재무제표"] = True
                log.info(f"  ✅ 재무제표: {len(fs_data)}건 수집 성공")
                # 샘플 출력
                sample = pd.DataFrame(fs_data[:5])
                print(sample.to_string(index=False))
            else:
                log.warning(f"  ⚠️  재무제표: 데이터 없음")
        except Exception as e:
            log.error(f"  ❌ 재무제표 오류: {e}")
        
        # 2) 지표
        try:
            ind_data = fetch_indicators(ticker)
            if ind_data and len(ind_data) > 0:
                test_results[ticker]["지표"] = True
                log.info(f"  ✅ 핵심지표: {len(ind_data)}건 수집 성공")
                # 샘플 출력
                sample = pd.DataFrame(ind_data[:5])
                print(sample.to_string(index=False))
            else:
                log.warning(f"  ⚠️  핵심지표: 데이터 없음")
        except Exception as e:
            log.error(f"  ❌ 핵심지표 오류: {e}")
        
        # 3) 주식수
        try:
            share_data = fetch_shares(ticker)
            if share_data:
                test_results[ticker]["주식수"] = True
                log.info(f"  ✅ 주식수: 수집 성공")
                print(f"     발행주식수: {share_data['발행주식수']:,}주")
                print(f"     자사주: {share_data['자사주']:,}주")
                print(f"     유통주식수: {share_data['유통주식수']:,}주")
            else:
                log.warning(f"  ⚠️  주식수: 데이터 없음")
        except Exception as e:
            log.error(f"  ❌ 주식수 오류: {e}")
    
    # 결과 요약
    log.info("\n" + "=" * 60)
    log.info("📊 테스트 결과 요약")
    log.info("=" * 60)
    
    summary_df = pd.DataFrame(test_results).T
    print(summary_df.to_string())
    
    # 성공률 계산
    total_tests = len(TEST_TICKERS) * 3
    passed_tests = sum([
        sum([
            test_results[t]["재무제표"],
            test_results[t]["지표"],
            test_results[t]["주식수"]
        ])
        for t in TEST_TICKERS
    ])
    
    success_rate = (passed_tests / total_tests) * 100
    log.info(f"\n✅ 성공률: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        log.info("🎉 테스트 통과! 전체 수집을 진행할 수 있습니다.")
        return True
    else:
        log.warning("⚠️  테스트 성공률이 낮습니다. 네트워크나 FnGuide 접근을 확인하세요.")
        return False


# ═════════════════════════════════════════════
# 메인 파이프라인
# ═════════════════════════════════════════════

def run_full():
    """전체 데이터 수집 (날짜별 파일 버전 관리 + 이어하기)"""
    start = datetime.now()
    biz_day = get_biz_day()  # 예: '20260206'
    log.info(f"📅 기준 영업일: {biz_day}")

    # ── 파일명 정의 (날짜 포함) ──
    # 예: master_20260206.csv
    path_master = DATA_DIR / f"master_{biz_day}.csv"
    path_daily = DATA_DIR / f"daily_{biz_day}.csv"
    path_fs = DATA_DIR / f"financial_statements_{biz_day}.csv"
    path_ind = DATA_DIR / f"indicators_{biz_day}.csv"
    path_shares = DATA_DIR / f"shares_{biz_day}.csv"

    # ── 1) 마스터 ──
    if path_master.exists():
        log.info(f"📂 {path_master.name} 파일이 있어 로드합니다.")
        master = pd.read_csv(path_master, encoding="utf-8-sig")
    else:
        master = collect_master()
        master.to_csv(path_master, index=False, encoding="utf-8-sig")
        log.info(f"✅ {path_master.name} 저장 ({len(master)}건)")

    # ── 2) 일별 시세 ──
    if path_daily.exists():
        log.info(f"📂 {path_daily.name} 파일이 있어 로드합니다.")
        daily = pd.read_csv(path_daily, encoding="utf-8-sig")
    else:
        daily = collect_daily(biz_day)
        daily.to_csv(path_daily, index=False, encoding="utf-8-sig")
        log.info(f"✅ {path_daily.name} 저장 ({len(daily)}건)")

    # 보통주만 추출 (FnGuide 크롤링 대상)
    targets = master.loc[
        (master["종목구분"] == "보통주") & (master["시장구분"].isin(["KOSPI", "KOSDAQ"])),
        "종목코드",
    ].tolist()
    
    # 종목코드 포맷 통일 (005930)
    targets = [f"{x:06d}" if isinstance(x, (int, float)) else str(x) for x in targets]
    
    log.info(f"🎯 FnGuide 크롤링 대상: {len(targets)}개 보통주")

    # ── 3) 재무제표 ──
    if path_fs.exists():
        log.info(f"⏭️  {path_fs.name} 이미 존재하여 수집 건너뜀")
    else:
        fs_rows = parallel_collect(fetch_fs, targets, "재무제표")
        if fs_rows:
            fs_df = pd.DataFrame(fs_rows)
            fs_df.to_csv(path_fs, index=False, encoding="utf-8-sig")
            log.info(f"✅ {path_fs.name} 저장 ({len(fs_df)}건)")
        else:
            log.warning("⚠️ 재무제표 데이터 없음")

    # ── 4) 핵심 지표 ──
    if path_ind.exists():
        log.info(f"⏭️  {path_ind.name} 이미 존재하여 수집 건너뜀")
    else:
        ind_rows = parallel_collect(fetch_indicators, targets, "핵심지표")
        if ind_rows:
            ind_df = pd.DataFrame(ind_rows)
            ind_df.to_csv(path_ind, index=False, encoding="utf-8-sig")
            log.info(f"✅ {path_ind.name} 저장 ({len(ind_df)}건)")
        else:
            log.warning("⚠️ 핵심지표 데이터 없음")

    # ── 5) 주식수 ──
    if path_shares.exists():
        log.info(f"⏭️  {path_shares.name} 이미 존재하여 수집 건너뜀")
    else:
        share_rows = parallel_collect(fetch_shares, targets, "주식수")
        if share_rows:
            share_df = pd.DataFrame(share_rows)
            share_df.to_csv(path_shares, index=False, encoding="utf-8-sig")
            log.info(f"✅ {path_shares.name} 저장 ({len(share_df)}건)")
        else:
            log.warning("⚠️ 주식수 데이터 없음")

    elapsed = datetime.now() - start
    log.info(f"🎉 전체 수집 완료 (소요: {elapsed})")
    log.info(f"📁 저장 폴더: {DATA_DIR.resolve()}")


def main():
    parser = argparse.ArgumentParser(
        description="한국 주식 퀀트 데이터 수집기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  테스트 모드 (3개 종목):  python quant_collector.py --test
  전체 실행:              python quant_collector.py
  테스트 후 전체 실행:     python quant_collector.py --test --auto-proceed
        """
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="테스트 모드 (샘플 3개 종목만 크롤링)"
    )
    parser.add_argument(
        "--auto-proceed",
        action="store_true",
        help="테스트 성공 시 자동으로 전체 수집 진행"
    )
    
    args = parser.parse_args()
    
    if args.test:
        test_passed = test_crawling()
        
        if test_passed and args.auto_proceed:
            log.info("\n자동 진행 모드: 전체 수집을 시작합니다...")
            run_full()
        elif test_passed:
            response = input("\n전체 수집을 진행하시겠습니까? (y/n): ").strip().lower()
            if response == 'y':
                run_full()
            else:
                log.info("전체 수집을 취소했습니다.")
        else:
            log.info("테스트를 통과하지 못했습니다. 문제를 해결 후 다시 시도하세요.")
    else:
        run_full()


if __name__ == "__main__":
    main()
