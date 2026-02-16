# =========================================================
# quant_screener.py  (v6)
# ---------------------------------------------------------
# [업데이트 내용]
# v5 → v6 변경:
#   4. GARP 스크리닝 추가: PEG<1.5 + 매출성장 10%↑ + ROE 12%↑
#   5. 캐시카우 스크리닝 추가: 영업CF 우량 + 저부채 + 이익률 높음
#   6. 턴어라운드 스크리닝 추가: 적자→흑자 전환 or 이익률 급개선
#   7. analyze_one_stock에 턴어라운드/캐시카우 감지 필드 추가
#   8. calc_valuation에 PSR, FCF수익률, PEG 등 파생지표 추가
#
# 출력 파일 (6개):
#   1) quant_all_stocks.xlsx   — 전체 종목
#   2) quant_screened.xlsx     — 우량주/저평가 스크리닝
#   3) quant_momentum.xlsx     — 폭발적 성장+마진개선
#   4) quant_GARP.xlsx         — 성장+합리적 가격 (피터 린치)
#   5) quant_cashcow.xlsx      — 현금흐름 우량 (버핏)
#   6) quant_turnaround.xlsx   — 실적 반등 종목
# =========================================================

import sys
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc="", **kwargs):
        items = list(iterable)
        total = len(items)
        for i, item in enumerate(items):
            if i % max(1, total // 10) == 0:
                print(f"  {desc}: {i}/{total} ({i*100//total}%)")
            yield item
        print(f"  {desc}: {total}/{total} (100%)")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("SCREENER")

DATA_DIR = Path("./data")


# ─────────────────────────────────────────────
# 계정 매핑 (exact match용)
# ─────────────────────────────────────────────
EXACT_ACCOUNTS = {
    "매출액": ["매출액", "영업수익", "이자수익", "보험료수익", "순영업수익"],
    "영업이익": ["영업이익"],
    "순이익": ["지배주주순이익", "당기순이익"],
    "자본": ["자본", "자본총계", "지배주주지분", "지배기업주주지분"],
    "부채": ["부채", "부채총계"],
    "배당금": ["주당배당금"],
    # 캐시카우/턴어라운드용 추가 계정
    "영업CF": ["영업활동현금흐름", "영업활동으로인한현금흐름"],
    "투자CF": ["투자활동현금흐름", "투자활동으로인한현금흐름"],
    "CAPEX": ["유형자산의취득", "유형자산취득"],
}

EXCLUDE_KEYWORDS = [
    "증가율", "(-1Y)", "(평균)", "률(", "비율", "배율", "(-1A", "(-1Q", "/ 수정평균"
]


# ═════════════════════════════════════════════
# 유틸리티
# ═════════════════════════════════════════════

def normalize_code(x):
    try:
        if pd.isna(x) or str(x).strip() == "":
            return np.nan
        s = str(x).strip()
        if '.' in s:
            s = s.split('.')[0]
        return s.zfill(6)
    except:
        return np.nan


def load_table(prefix: str) -> pd.DataFrame:
    import db as _db
    df = _db.load_latest(prefix)

    if df.empty:
        return df

    df.columns = df.columns.str.strip()

    if "종목코드" in df.columns:
        df["종목코드"] = df["종목코드"].apply(normalize_code)
        df = df.dropna(subset=["종목코드"])

    # 기준일 정규화: "2023-12-31 00:00:00" → "2023-12-31"
    if "기준일" in df.columns:
        df["기준일"] = df["기준일"].astype(str).str[:10]

    for col in ["값", "종가", "시가총액", "상장주식수"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# 하위 호환용 별칭
load_csv = load_table


def _should_exclude(account_name: str) -> bool:
    for kw in EXCLUDE_KEYWORDS:
        if kw in account_name:
            return True
    return False


def find_account_value(df, target_key, date_filter=None):
    if df.empty or "계정" not in df.columns:
        return {}

    targets = EXACT_ACCOUNTS.get(target_key, [target_key])
    work = df.copy()
    if date_filter is not None:
        work = work[work["기준일"].isin(date_filter)]

    mask = work["계정"].isin(targets)
    matched = work[mask]

    if matched.empty:
        def _startswith_any(name):
            name_str = str(name)
            for t in targets:
                if name_str.startswith(t) and not _should_exclude(name_str):
                    return True
            return False
        mask2 = work["계정"].apply(_startswith_any)
        matched = work[mask2]

    if matched.empty:
        return {}

    matched = matched.drop_duplicates(["종목코드", "기준일"], keep="first")

    result = {}
    for _, r in matched.iterrows():
        try:
            dt = str(r["기준일"])
            v = float(r["값"]) if pd.notna(r["값"]) else None
            if v is not None:
                result[dt] = v
        except:
            pass
    return result


# ═════════════════════════════════════════════
# 데이터 전처리 & 단위 감지
# ═════════════════════════════════════════════

def preprocess_indicators(ind_df):
    if ind_df.empty:
        return ind_df
    ind_df = ind_df.drop_duplicates(["종목코드", "기준일", "계정", "지표구분"], keep="first")
    return ind_df


def detect_unit_multiplier(ind_df):
    sam = ind_df[ind_df["종목코드"] == "005930"]
    if sam.empty:
        return 100_000_000

    sam_y = sam[sam["지표구분"] == "RATIO_Y"]
    rev_dict = find_account_value(sam_y, "매출액")

    if not rev_dict:
        return 100_000_000

    annual_revs = {d: v for d, v in rev_dict.items() if d.endswith("12-31")}
    if not annual_revs:
        annual_revs = rev_dict
    latest_rev = max(annual_revs.values())

    if latest_rev > 1e14: return 1
    elif latest_rev > 1e8: return 1_000_000
    elif latest_rev > 1e5: return 100_000_000
    else: return 100_000_000


# ═════════════════════════════════════════════
# 성장/추세 분석 유틸
# ═════════════════════════════════════════════

def calc_cagr(series_dict, min_years=2):
    if len(series_dict) < min_years:
        return np.nan
    dates = sorted(series_dict.keys())
    v0, v1 = series_dict[dates[0]], series_dict[dates[-1]]
    if v0 <= 0 or v1 <= 0:
        return np.nan
    try:
        d0, d1 = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
        years = (d1 - d0).days / 365.25
        if years < 0.5: return np.nan
        return ((v1 / v0) ** (1 / years) - 1) * 100
    except:
        return np.nan


def count_consecutive_growth(series_dict):
    if len(series_dict) < 2:
        return 0
    vals = [series_dict[d] for d in sorted(series_dict.keys())]
    count = 0
    for i in range(len(vals) - 1, 0, -1):
        if vals[i] > vals[i - 1] and vals[i - 1] > 0:
            count += 1
        else:
            break
    return count


# ═════════════════════════════════════════════
# 종목별 펀더멘털 분석 (v6: 턴어라운드/캐시카우 필드 추가)
# ═════════════════════════════════════════════

def analyze_one_stock(ticker, ind_grp, fs_grp):
    result = {"종목코드": ticker}
    has_ind = not ind_grp.empty and "지표구분" in ind_grp.columns
    has_fs = not fs_grp.empty

    # ── TTM (Trailing 12 Months) ──
    ttm_rev, ttm_op, ttm_ni = np.nan, np.nan, np.nan
    ttm_source = "없음"

    if has_ind:
        y_data = ind_grp[ind_grp["지표구분"] == "RATIO_Y"]
        q_data = ind_grp[ind_grp["지표구분"] == "RATIO_Q"]

        y_dates = sorted(y_data["기준일"].unique())
        annual_dates = [d for d in y_dates if str(d).endswith("12-31")]
        q_dates = sorted(q_data["기준일"].unique())
        last4q = q_dates[-4:] if len(q_dates) >= 4 else []

        for label, key, setter in [("매출", "매출액", "ttm_rev"), ("영업이익", "영업이익", "ttm_op"), ("순이익", "순이익", "ttm_ni")]:
            val = np.nan
            if last4q:
                d = find_account_value(q_data[q_data["기준일"].isin(last4q)], key)
                if len(d) >= 4: val = sum(d.values())
            if pd.isna(val) and annual_dates:
                d = find_account_value(y_data, key, annual_dates)
                if d: val = d[max(d.keys())]

            if setter == "ttm_rev": ttm_rev = val
            elif setter == "ttm_op": ttm_op = val
            else: ttm_ni = val

        if pd.notna(ttm_rev): ttm_source = "있음"

    result.update({"TTM_매출": ttm_rev, "TTM_영업이익": ttm_op, "TTM_순이익": ttm_ni, "TTM_소스": ttm_source})

    # ── 자본/부채 ──
    curr_equity, curr_debt = np.nan, np.nan
    if has_fs:
        last_dt = sorted(fs_grp["기준일"].unique())[-1]
        bs_last = fs_grp[fs_grp["기준일"] == last_dt]
        e = find_account_value(bs_last, "자본")
        d = find_account_value(bs_last, "부채")
        if e: curr_equity = list(e.values())[0]
        if d: curr_debt = list(d.values())[0]

    if pd.isna(curr_equity) and has_ind:
        y_data = ind_grp[ind_grp["지표구분"] == "RATIO_Y"]
        e = find_account_value(y_data, "자본")
        d = find_account_value(y_data, "부채")
        if e: curr_equity = e[max(e.keys())]
        if d: curr_debt = d[max(d.keys())]

    result.update({"자본": curr_equity, "부채": curr_debt})

    # ── 성장성 (CAGR) ──
    rev_series, op_series, ni_series = {}, {}, {}
    if has_ind:
        y_data = ind_grp[ind_grp["지표구분"] == "RATIO_Y"]
        annual_dates = [d for d in sorted(y_data["기준일"].unique()) if str(d).endswith("12-31")]
        if len(annual_dates) >= 2:
            rev_series = find_account_value(y_data, "매출액", annual_dates)
            op_series = find_account_value(y_data, "영업이익", annual_dates)
            ni_series = find_account_value(y_data, "순이익", annual_dates)

    result["매출_CAGR"] = calc_cagr(rev_series)
    result["영업이익_CAGR"] = calc_cagr(op_series)
    result["순이익_CAGR"] = calc_cagr(ni_series)
    result["매출_연속성장"] = count_consecutive_growth(rev_series)
    result["영업이익_연속성장"] = count_consecutive_growth(op_series)
    result["순이익_연속성장"] = count_consecutive_growth(ni_series)
    result["데이터_연수"] = len(rev_series)

    # ── 이익률 개선 여부 ──
    if len(rev_series) >= 2 and len(op_series) >= 2:
        latest = sorted(rev_series.keys())[-1]
        prev = sorted(rev_series.keys())[-2]
        opm_l = (op_series.get(latest, 0) / rev_series[latest] * 100) if rev_series[latest] > 0 else np.nan
        opm_p = (op_series.get(prev, 0) / rev_series[prev] * 100) if rev_series[prev] > 0 else np.nan
        result["영업이익률_최근"] = opm_l
        result["영업이익률_전년"] = opm_p
        result["이익률_개선"] = 1 if pd.notna(opm_l) and pd.notna(opm_p) and opm_l > opm_p else 0

        # [v6] 이익률 급개선 감지 (영업이익률 +5%p 이상)
        if pd.notna(opm_l) and pd.notna(opm_p):
            delta = opm_l - opm_p
            result["이익률_변동폭"] = delta
            result["이익률_급개선"] = 1 if delta >= 5 else 0
        else:
            result["이익률_변동폭"] = np.nan
            result["이익률_급개선"] = 0
    else:
        result.update({
            "영업이익률_최근": np.nan, "영업이익률_전년": np.nan,
            "이익률_개선": 0, "이익률_변동폭": np.nan, "이익률_급개선": 0,
        })

    # ── [v6] 턴어라운드 감지: 전년 순이익 < 0 → 올해 > 0 ──
    if len(ni_series) >= 2:
        ni_vals = [ni_series[d] for d in sorted(ni_series.keys())]
        result["순이익_전년음수"] = 1 if ni_vals[-2] < 0 else 0
        result["순이익_당기양수"] = 1 if ni_vals[-1] > 0 else 0
        result["흑자전환"] = 1 if ni_vals[-2] < 0 and ni_vals[-1] > 0 else 0
    else:
        result["순이익_전년음수"] = 0
        result["순이익_당기양수"] = 0
        result["흑자전환"] = 0

    # ── [v7] 영업CF / CAPEX / FCF 시계열 + TTM ──
    ocf_series, capex_series = {}, {}

    # 1) indicators(RATIO_Y)에서 연도별 시계열 추출
    if has_ind:
        y_data = ind_grp[ind_grp["지표구분"] == "RATIO_Y"]
        ad = annual_dates if 'annual_dates' in dir() else None
        ocf_series = find_account_value(y_data, "영업CF", ad)
        capex_series = find_account_value(y_data, "CAPEX", ad)

    # 2) indicators에 없으면 financial_statements(CF)에서 fallback
    if not ocf_series and has_fs:
        fs_y = fs_grp[(fs_grp["주기"] == "y")]
        ocf_series = find_account_value(fs_y, "영업CF")
    if not capex_series and has_fs:
        fs_y = fs_grp[(fs_grp["주기"] == "y")]
        capex_series = find_account_value(fs_y, "CAPEX")

    # CAPEX는 FnGuide에서 음수로 기재되므로 절대값 처리
    capex_series = {d: abs(v) for d, v in capex_series.items()}

    # 3) FCF 시계열 (영업CF - CAPEX, 동일 연도만)
    fcf_series = {}
    common_dates = set(ocf_series.keys()) & set(capex_series.keys())
    for d in common_dates:
        fcf_series[d] = ocf_series[d] - capex_series[d]

    # TTM 값 (최신 연도)
    ttm_ocf = ocf_series[max(ocf_series.keys())] if ocf_series else np.nan
    ttm_capex = capex_series[max(capex_series.keys())] if capex_series else np.nan
    ttm_fcf = fcf_series[max(fcf_series.keys())] if fcf_series else np.nan

    result["TTM_영업CF"] = ttm_ocf
    result["TTM_CAPEX"] = ttm_capex
    result["TTM_FCF"] = ttm_fcf
    result["영업CF_CAGR"] = calc_cagr(ocf_series)
    result["FCF_CAGR"] = calc_cagr(fcf_series)
    result["영업CF_연속성장"] = count_consecutive_growth(ocf_series)

    # ── 배당 ──
    dps_series = {}
    if has_ind:
        dps_data = ind_grp[ind_grp["지표구분"] == "DPS"]
        annual_dps = [d for d in sorted(dps_data["기준일"].unique()) if str(d).endswith("12-31")]
        if annual_dps:
            dps_series = find_account_value(dps_data, "배당금", annual_dps)

    result["DPS_최근"] = list(dps_series.values())[-1] if dps_series else np.nan
    result["DPS_CAGR"] = calc_cagr(dps_series)
    result["배당_연속증가"] = count_consecutive_growth(dps_series)

    return result


def analyze_all(fs_df, ind_df):
    results = []
    tickers = list(set(
        list(fs_df["종목코드"].unique() if not fs_df.empty else []) +
        list(ind_df["종목코드"].unique() if not ind_df.empty else [])
    ))
    for ticker in tqdm(tickers, desc="펀더멘털 분석", ncols=100):
        ind_grp = ind_df[ind_df["종목코드"] == ticker] if not ind_df.empty else pd.DataFrame()
        fs_grp = fs_df[fs_df["종목코드"] == ticker] if not fs_df.empty else pd.DataFrame()
        results.append(analyze_one_stock(ticker, ind_grp, fs_grp))
    return pd.DataFrame(results)


# ═════════════════════════════════════════════
# 밸류에이션 & 스코어링 (v6: 파생지표 추가)
# ═════════════════════════════════════════════

def calc_valuation(daily, anal_df, multiplier, shares_df):
    merge_cols = ["종목코드", "종목명", "종가", "시가총액", "상장주식수"]
    valid_merge = [c for c in merge_cols if c in daily.columns]
    df = daily[valid_merge].drop_duplicates("종목코드").merge(anal_df, on="종목코드", how="inner")

    if not shares_df.empty and "상장주식수" in df.columns:
        shares_map = shares_df.drop_duplicates("종목코드").set_index("종목코드")["발행주식수"]
        mask_no = df["상장주식수"].isna() | (df["상장주식수"] == 0)
        df.loc[mask_no, "상장주식수"] = df.loc[mask_no, "종목코드"].map(shares_map)

    M = multiplier

    # ── 기본 지표 ──
    df["PER"] = np.where((df["TTM_순이익"] > 0) & (df["시가총액"] > 0), df["시가총액"] / (df["TTM_순이익"] * M), np.nan)
    df["PBR"] = np.where((df["자본"] > 0) & (df["시가총액"] > 0), df["시가총액"] / (df["자본"] * M), np.nan)
    df["ROE(%)"] = np.where((df["자본"] > 0) & pd.notna(df["TTM_순이익"]), (df["TTM_순이익"] / df["자본"]) * 100, np.nan)
    df["부채비율(%)"] = np.where((df["자본"] > 0), (df["부채"] / df["자본"]) * 100, np.nan)
    df["영업이익률(%)"] = df["영업이익률_최근"]

    shares_safe = df["상장주식수"].replace(0, np.nan)
    df["BPS"] = (df["자본"] * M) / shares_safe
    df["EPS"] = (df["TTM_순이익"] * M) / shares_safe
    df["배당수익률(%)"] = np.where((df["종가"] > 0) & (df["DPS_최근"] > 0), (df["DPS_최근"] / df["종가"]) * 100, 0)

    # ── [v6] 추가 파생 지표 ──
    # PSR (Price-to-Sales)
    df["PSR"] = np.where(
        (df["TTM_매출"] > 0) & (df["시가총액"] > 0),
        df["시가총액"] / (df["TTM_매출"] * M), np.nan
    )

    # PEG (PER / 순이익CAGR) — GARP용
    df["PEG"] = np.where(
        pd.notna(df["PER"]) & (df["PER"] > 0) &
        pd.notna(df["순이익_CAGR"]) & (df["순이익_CAGR"] > 0),
        df["PER"] / df["순이익_CAGR"], np.nan
    )

    # 이익수익률 (Earnings Yield = EPS / 종가)
    df["이익수익률(%)"] = np.where(
        (df["종가"] > 0) & pd.notna(df["EPS"]) & (df["EPS"] > 0),
        (df["EPS"] / df["종가"]) * 100, np.nan
    )

    # FCF 수익률 (진짜 FCF = 영업CF - CAPEX)
    df["FCF수익률(%)"] = np.where(
        pd.notna(df["TTM_FCF"]) & (df["시가총액"] > 0),
        (df["TTM_FCF"] * M / df["시가총액"]) * 100, np.nan
    )

    # 현금전환율 (영업CF / 순이익 × 100, 100% 이상이면 이익이 현금으로 뒷받침됨)
    df["현금전환율(%)"] = np.where(
        pd.notna(df["TTM_영업CF"]) & pd.notna(df["TTM_순이익"]) & (df["TTM_순이익"] > 0),
        (df["TTM_영업CF"] / df["TTM_순이익"]) * 100, np.nan
    )

    # CAPEX 비율 (CAPEX / 영업CF × 100, 낮을수록 경자산 비즈니스)
    df["CAPEX비율(%)"] = np.where(
        pd.notna(df["TTM_CAPEX"]) & pd.notna(df["TTM_영업CF"]) & (df["TTM_영업CF"] > 0),
        (df["TTM_CAPEX"] / df["TTM_영업CF"]) * 100, np.nan
    )

    # 영업CF > 순이익 (이익 품질 플래그)
    df["이익품질_양호"] = np.where(
        pd.notna(df["TTM_영업CF"]) & pd.notna(df["TTM_순이익"]) & (df["TTM_순이익"] > 0),
        np.where(df["TTM_영업CF"] > df["TTM_순이익"], 1, 0), 0
    )

    # S-RIM
    Ke = 8.0
    df["적정주가_SRIM"] = np.where(
        (df["ROE(%)"] > Ke) & (df["BPS"] > 0),
        df["BPS"] + df["BPS"] * (df["ROE(%)"] - Ke) / Ke,
        np.where((df["BPS"] > 0), df["BPS"] * 0.9, np.nan)
    )
    df["괴리율(%)"] = ((df["적정주가_SRIM"] - df["종가"]) / df["종가"]) * 100

    # 검증 플래그
    df["PER_이상"] = np.where((df["PER"] < 0.5) | (df["PER"] > 500), "⚠️", "")

    # ── 스코어링 (NaN은 순위에서 제외 → NaN 유지, 스크리닝 단계에서 필터) ──
    df["S_PER"] = (1 - df["PER"].rank(pct=True, na_option='keep')) * 100
    df["S_PBR"] = (1 - df["PBR"].rank(pct=True, na_option='keep')) * 100
    df["S_ROE"] = df["ROE(%)"].rank(pct=True, na_option='keep') * 100

    df["S_매출CAGR"] = df["매출_CAGR"].rank(pct=True, na_option='keep') * 100
    df["S_영업이익CAGR"] = df["영업이익_CAGR"].rank(pct=True, na_option='keep') * 100
    df["S_순이익CAGR"] = df["순이익_CAGR"].rank(pct=True, na_option='keep') * 100

    # 연속성장: 각 항목 0~5년을 0~100으로 정규화 후 평균
    df["S_연속성장"] = (
        df["매출_연속성장"].fillna(0).clip(0, 5) / 5 * 100 +
        df["영업이익_연속성장"].fillna(0).clip(0, 5) / 5 * 100 +
        df["순이익_연속성장"].fillna(0).clip(0, 5) / 5 * 100
    ) / 3

    # 이익률 변동폭 연속값 사용 (이진 플래그 대신 실제 개선폭 반영)
    df["S_이익률개선"] = df["이익률_변동폭"].rank(pct=True, na_option='keep') * 100
    df["S_배당수익률"] = df["배당수익률(%)"].rank(pct=True, na_option='keep') * 100
    df["S_배당연속증가"] = df["배당_연속증가"].fillna(0).clip(0, 5) / 5 * 100
    df["S_괴리율"] = df["괴리율(%)"].rank(pct=True, na_option='keep') * 100

    df["종합점수"] = (
        df["S_PER"].fillna(0) * 1.0 +
        df["S_PBR"].fillna(0) * 0.5 +
        df["S_ROE"].fillna(0) * 2.5 +
        df["S_매출CAGR"].fillna(0) * 2.0 +
        df["S_영업이익CAGR"].fillna(0) * 2.0 +
        df["S_순이익CAGR"].fillna(0) * 0.5 +
        df["S_연속성장"].fillna(0) * 1.0 +
        df["S_이익률개선"].fillna(0) * 1.0 +
        df["S_배당수익률"].fillna(0) * 0.5 +
        df["S_배당연속증가"].fillna(0) * 0.5 +
        df["S_괴리율"].fillna(0) * 1.0
    )

    return df


# ═════════════════════════════════════════════
# 스크리닝 (기존 2 + 신규 3 = 총 5개 필터)
# ═════════════════════════════════════════════

def apply_screen(df):
    """① 기본 우량주/저평가 스크리닝"""
    mask = (
        pd.notna(df["TTM_순이익"]) & (df["TTM_순이익"] > 0) &
        (df["ROE(%)"] >= 5) &
        (df["PER"].between(1, 50)) &
        (df["PBR"].between(0.1, 10)) &
        (df["매출_연속성장"] >= 2) &
        (df["순이익_연속성장"] >= 1) &
        (df["시가총액"] >= 50_000_000_000) &
        (df["PER_이상"] == "")
    )
    return df[mask].sort_values("종합점수", ascending=False)


def apply_momentum_screen(df):
    """② 모멘텀/성장주 스크리닝"""
    mask = (
        pd.notna(df["매출_CAGR"]) &
        pd.notna(df["영업이익_CAGR"]) &
        ((df["매출_CAGR"] >= 15) | (df["영업이익_CAGR"] >= 15)) &
        (df["이익률_개선"] == 1) &
        (df["ROE(%)"] >= 5) &
        (df["TTM_순이익"] > 0) &
        (df["시가총액"] >= 50_000_000_000)
    )
    mom_df = df[mask].copy()
    if not mom_df.empty:
        mom_df["모멘텀_점수"] = (
            mom_df["매출_CAGR"].rank(pct=True) * 2.0 +
            mom_df["영업이익_CAGR"].rank(pct=True) * 2.5 +
            mom_df["ROE(%)"].rank(pct=True) * 1.5 +
            mom_df["영업이익률_최근"].rank(pct=True) * 1.0 +
            mom_df["이익률_개선"].rank(pct=True) * 1.0
        )
    if "모멘텀_점수" in mom_df.columns:
        return mom_df.sort_values("모멘텀_점수", ascending=False)
    return mom_df


def apply_garp_screen(df):
    """
    ③ GARP (Growth At Reasonable Price) — 피터 린치 스타일
    조건:
      - PEG < 1.5 (성장 대비 합리적 가격)
      - 매출 CAGR ≥ 10% (성장 확인)
      - ROE ≥ 12% (수익성 담보)
      - PER 5~30 (적자·극단 제외)
      - 시총 500억+ (소형주 제외)
    """
    mask = (
        pd.notna(df["PEG"]) & (df["PEG"] > 0) & (df["PEG"] < 1.5) &
        pd.notna(df["매출_CAGR"]) & (df["매출_CAGR"] >= 10) &
        pd.notna(df["ROE(%)"]) & (df["ROE(%)"] >= 12) &
        pd.notna(df["PER"]) & df["PER"].between(5, 30) &
        (df["시가총액"] >= 50_000_000_000) &
        (df["TTM_순이익"] > 0) &
        (df["PER_이상"] == "")
    )
    g = df[mask].copy()
    if not g.empty:
        g["GARP_점수"] = (
            (1 - g["PEG"].rank(pct=True)) * 3.0 +           # 낮은 PEG 선호
            g["매출_CAGR"].rank(pct=True) * 2.0 +            # 높은 매출 성장
            g["영업이익_CAGR"].rank(pct=True) * 1.5 +        # 높은 이익 성장
            g["ROE(%)"].rank(pct=True) * 2.0 +               # 높은 ROE
            (1 - g["PER"].rank(pct=True)) * 1.0 +            # 낮은 PER
            g["이익률_개선"].fillna(0) * 0.5 +               # 이익률 개선 보너스
            g["S_괴리율"] / 100 * 1.0                        # S-RIM 저평가 보너스
        )
    if "GARP_점수" in g.columns:
        return g.sort_values("GARP_점수", ascending=False)
    return g


def apply_cashcow_screen(df):
    """
    ④ 캐시카우 (고수익 우량주) — 버핏 스타일
    조건 (안정적 지표 기반):
      - ROE ≥ 10% (높은 자본 수익성)
      - 영업이익률 ≥ 10% (높은 마진)
      - 부채비율 < 100% (또는 무차입)
      - 매출 연속성장 ≥ 1년
      - 시총 500억+
      - 흑자
      - 이익품질 양호 (영업CF > 순이익)
    """
    mask = (
        pd.notna(df["ROE(%)"]) & (df["ROE(%)"] >= 10) &
        pd.notna(df["영업이익률(%)"]) & (df["영업이익률(%)"] >= 10) &
        (
            (pd.notna(df["부채비율(%)"]) & (df["부채비율(%)"] < 100)) |
            df["부채비율(%)"].isna()
        ) &
        (df["매출_연속성장"] >= 1) &
        (df["시가총액"] >= 50_000_000_000) &
        (df["TTM_순이익"] > 0) &
        (df["이익품질_양호"] == 1)
    )
    c = df[mask].copy()
    if not c.empty:
        c["캐시카우_점수"] = (
            c["ROE(%)"].rank(pct=True) * 2.0 +                               # ROE
            c["영업이익률(%)"].rank(pct=True) * 2.0 +                         # 영업이익률
            (1 - c["부채비율(%)"].fillna(0).rank(pct=True)) * 1.5 +          # 저부채 선호
            c["FCF수익률(%)"].fillna(0).rank(pct=True) * 2.5 +               # FCF 수익률 (핵심)
            c["매출_연속성장"].fillna(0).rank(pct=True) * 1.0 +              # 안정 성장
            (1 - c["PER"].clip(1, 100).rank(pct=True)) * 1.0 +              # 저PER
            c["배당수익률(%)"].rank(pct=True) * 0.5 +                         # 배당 보너스
            c["S_괴리율"].fillna(0) / 100 * 0.5                              # S-RIM 저평가
        )
    if "캐시카우_점수" in c.columns:
        return c.sort_values("캐시카우_점수", ascending=False)
    return c


def apply_turnaround_screen(df):
    """
    ⑤ 턴어라운드 (실적 반등) — 역발상 투자
    조건 (OR):
      A) 적자→흑자 전환 (흑자전환 == 1)
      B) 영업이익률 +5%p 이상 급개선 (이익률_급개선 == 1)
    공통:
      - 현재 순이익 > 0 (현재 흑자)
      - 시총 300억+ (소형주 포함 — 턴어라운드는 초기 발굴)
    """
    mask = (
        (
            (df["흑자전환"] == 1) |
            (df["이익률_급개선"] == 1)
        ) &
        (df["TTM_순이익"] > 0) &
        (df["시가총액"] >= 30_000_000_000)
    )
    t = df[mask].copy()
    if not t.empty:
        t["턴어라운드_점수"] = (
            t["이익률_변동폭"].fillna(0).rank(pct=True) * 2.5 +       # 이익률 개선폭
            t["매출_CAGR"].rank(pct=True) * 1.5 +                     # 매출 성장
            t["ROE(%)"].rank(pct=True) * 1.5 +                        # ROE
            t["흑자전환"].fillna(0) * 1.5 +                           # 흑전 보너스
            (1 - t["PER"].clip(0, 100).rank(pct=True)) * 1.0 +       # 저PER
            t["이익률_급개선"].fillna(0) * 1.0 +                      # 급개선 보너스
            t["S_괴리율"] / 100 * 1.0                                 # S-RIM 저평가
        )
    if "턴어라운드_점수" in t.columns:
        return t.sort_values("턴어라운드_점수", ascending=False)
    return t


# ═════════════════════════════════════════════
# 엑셀 저장
# ═════════════════════════════════════════════

def save_to_excel(df, filepath, sheet_name="Result"):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    col_groups = {
        "기본정보": ["종목코드", "종목명", "종가", "시가총액", "상장주식수"],
        "주요지표": ["PER", "PBR", "PSR", "PEG", "ROE(%)", "EPS", "BPS",
                    "부채비율(%)", "영업이익률(%)", "이익수익률(%)", "FCF수익률(%)",
                    "배당수익률(%)", "이익품질_양호"],
        "점수": ["종합점수", "모멘텀_점수", "GARP_점수", "캐시카우_점수", "턴어라운드_점수"],
        "성장추세": ["매출_CAGR", "영업이익_CAGR", "순이익_CAGR",
                    "매출_연속성장", "영업이익_연속성장", "순이익_연속성장",
                    "이익률_개선", "이익률_급개선", "이익률_변동폭",
                    "흑자전환", "영업이익률_최근", "영업이익률_전년"],
        "밸류에이션": ["적정주가_SRIM", "괴리율(%)"],
        "TTM_원본": ["TTM_매출", "TTM_영업이익", "TTM_순이익", "TTM_영업CF", "자본", "부채"],
    }

    ordered_cols = []
    for g in col_groups.values():
        for c in g:
            if c in df.columns:
                ordered_cols.append(c)
    for c in df.columns:
        if c not in ordered_cols and not c.startswith("S_"):
            ordered_cols.append(c)

    export_df = df[ordered_cols].copy()

    fills = {
        "기본정보": PatternFill("solid", fgColor="D6E4F0"),
        "주요지표": PatternFill("solid", fgColor="E2EFDA"),
        "점수": PatternFill("solid", fgColor="C6EFCE"),
        "성장추세": PatternFill("solid", fgColor="FFF2CC"),
        "밸류에이션": PatternFill("solid", fgColor="DAEEF3"),
        "TTM_원본": PatternFill("solid", fgColor="F2DCDB"),
    }

    header_font = Font(name="맑은 고딕", bold=True, size=10)
    data_font = Font(name="맑은 고딕", size=9)
    thin_border = Border(bottom=Side(style='thin', color='CCCCCC'))

    for col_idx, col_name in enumerate(ordered_cols, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        for grp, cols in col_groups.items():
            if col_name in cols:
                cell.fill = fills[grp]
                break

    for row_idx, (_, row_data) in enumerate(export_df.iterrows(), 2):
        for col_idx, col_name in enumerate(ordered_cols, 1):
            val = row_data[col_name]
            if pd.isna(val): val = None
            elif isinstance(val, (np.floating, float)): val = round(float(val), 2)
            elif isinstance(val, (np.integer,)): val = int(val)

            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = data_font
            cell.border = thin_border

            if col_name in ["시가총액", "종가", "EPS", "BPS", "적정주가_SRIM"]:
                cell.number_format = '#,##0'
            elif "%" in col_name or "CAGR" in col_name:
                cell.number_format = '#,##0.00'
            elif "점수" in col_name:
                cell.number_format = '#,##0.0'

    for col_idx, col_name in enumerate(ordered_cols, 1):
        width = 12
        if col_name == "종목명": width = 18
        elif "점수" in col_name: width = 14
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "C2"
    wb.save(filepath)
    log.info(f"💾 저장: {filepath}")


# ═════════════════════════════════════════════
# 메인 실행
# ═════════════════════════════════════════════

def run():
    master = load_table("master")
    daily = load_table("daily")
    fs = load_table("financial_statements")
    ind = load_table("indicators")
    shares = load_table("shares")

    if daily.empty:
        log.error("❌ daily 없음")
        return

    ind = preprocess_indicators(ind)
    multiplier = detect_unit_multiplier(ind)
    anal_df = analyze_all(fs, ind)

    full_df = calc_valuation(daily, anal_df, multiplier, shares)

    # ── 6개 결과물 저장 ──
    # 1. 전체
    save_to_excel(full_df.sort_values("종합점수", ascending=False),
                  DATA_DIR / "quant_all_stocks.xlsx", "전체종목")

    # 2. 우량주
    screened = apply_screen(full_df)
    save_to_excel(screened, DATA_DIR / "quant_screened.xlsx", "우량주")

    # 3. 모멘텀
    momentum_df = apply_momentum_screen(full_df)
    save_to_excel(momentum_df, DATA_DIR / "quant_momentum.xlsx", "모멘텀")

    # 4. GARP (성장+합리적 가격)
    garp_df = apply_garp_screen(full_df)
    save_to_excel(garp_df, DATA_DIR / "quant_GARP.xlsx", "GARP")

    # 5. 캐시카우 (현금흐름 우량)
    cashcow_df = apply_cashcow_screen(full_df)
    save_to_excel(cashcow_df, DATA_DIR / "quant_cashcow.xlsx", "캐시카우")

    # 6. 턴어라운드 (실적 반등)
    turnaround_df = apply_turnaround_screen(full_df)
    save_to_excel(turnaround_df, DATA_DIR / "quant_turnaround.xlsx", "턴어라운드")

    # ── 요약 출력 ──
    print("\n" + "=" * 80)
    print(f"📏 단위 보정: {multiplier:,.0f}")
    print(f"📊 분석 종목:             {len(full_df):,}개")
    print(f"✅ 우량주 스크리닝:        {len(screened):,}개")
    print(f"🚀 모멘텀 (고성장):        {len(momentum_df):,}개")
    print(f"📈 GARP (성장+가치):       {len(garp_df):,}개")
    print(f"💵 캐시카우 (현금흐름):    {len(cashcow_df):,}개")
    print(f"🔄 턴어라운드 (반등):      {len(turnaround_df):,}개")
    print("=" * 80)

    # TOP 10 출력
    if len(momentum_df) > 0:
        print("\n🚀 모멘텀 TOP 10:")
        cols = ["종목명", "매출_CAGR", "영업이익_CAGR", "영업이익률_최근", "ROE(%)", "모멘텀_점수"]
        valid = [c for c in cols if c in momentum_df.columns]
        print(momentum_df[valid].head(10).to_string(index=False, float_format="%.1f"))

    if len(garp_df) > 0:
        print("\n📈 GARP TOP 10:")
        cols = ["종목명", "PEG", "매출_CAGR", "ROE(%)", "PER", "GARP_점수"]
        valid = [c for c in cols if c in garp_df.columns]
        print(garp_df[valid].head(10).to_string(index=False, float_format="%.1f"))

    if len(cashcow_df) > 0:
        print("\n💵 캐시카우 TOP 10:")
        cols = ["종목명", "FCF수익률(%)", "영업이익률(%)", "부채비율(%)", "ROE(%)", "캐시카우_점수"]
        valid = [c for c in cols if c in cashcow_df.columns]
        print(cashcow_df[valid].head(10).to_string(index=False, float_format="%.1f"))

    if len(turnaround_df) > 0:
        print("\n🔄 턴어라운드 TOP 10:")
        cols = ["종목명", "흑자전환", "이익률_급개선", "이익률_변동폭", "영업이익률_최근", "ROE(%)", "턴어라운드_점수"]
        valid = [c for c in cols if c in turnaround_df.columns]
        print(turnaround_df[valid].head(10).to_string(index=False, float_format="%.1f"))


if __name__ == "__main__":
    run()