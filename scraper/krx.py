"""
Scraper for KOSPI / KOSDAQ stock listings and daily price data.

Data source: KRX (Korea Exchange) open API endpoints and Naver Finance.
"""

import logging
import time
from datetime import date, datetime, timedelta
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ---- KRX / Naver endpoints ----
KRX_LISTING_URL = "http://kind.krx.co.kr/corpgeneral/corpList.do"
NAVER_SISE_URL = "https://finance.naver.com/item/sise_day.naver"
NAVER_MAIN_URL = "https://finance.naver.com/item/main.naver"


def fetch_stock_listing(market: str = "kospiMkt") -> pd.DataFrame:
    """Fetch the full stock listing from KRX for a given market.

    Args:
        market: 'kospiMkt' for KOSPI, 'kosdaqMkt' for KOSDAQ.

    Returns:
        DataFrame with columns: code, name, sector.
    """
    params = {
        "method": "download",
        "orderMode": "1",
        "orderStat": "D",
        "searchType": "13",
        "marketType": market,
    }

    for attempt in range(3):
        try:
            resp = requests.get(
                KRX_LISTING_URL,
                params=params,
                headers=HEADERS,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            logger.warning("Listing fetch attempt %d failed: %s", attempt + 1, exc)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    df = pd.read_html(StringIO(resp.text), header=0)[0]
    df = df[["종목코드", "회사명", "업종"]].copy()
    df.columns = ["code", "name", "sector"]
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def fetch_all_listings() -> pd.DataFrame:
    """Fetch combined KOSPI + KOSDAQ listings."""
    frames = []
    for mkt_code, mkt_label in [("kospiMkt", "KOSPI"), ("kosdaqMkt", "KOSDAQ")]:
        try:
            df = fetch_stock_listing(mkt_code)
            df["market"] = mkt_label
            frames.append(df)
            logger.info("Fetched %d %s stocks", len(df), mkt_label)
        except Exception:
            logger.exception("Failed to fetch %s listings", mkt_label)
    if not frames:
        return pd.DataFrame(columns=["code", "name", "sector", "market"])
    return pd.concat(frames, ignore_index=True)


def fetch_daily_prices(code: str, pages: int = 3) -> pd.DataFrame:
    """Scrape recent daily price data from Naver Finance.

    Args:
        code: 6-digit stock code.
        pages: Number of pages to scrape (each page ≈ 10 trading days).

    Returns:
        DataFrame with columns: trade_date, open, high, low, close, volume.
    """
    rows = []
    for page in range(1, pages + 1):
        params = {"code": code, "page": page}
        try:
            resp = requests.get(
                NAVER_SISE_URL,
                params=params,
                headers=HEADERS,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Price fetch failed for %s page %d: %s", code, page, exc)
            break

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", class_="type2")
        if table is None:
            break

        for tr in table.find_all("tr", {"onmouseover": True}):
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue
            raw_date = tds[0].get_text(strip=True)
            try:
                trade_date = datetime.strptime(raw_date, "%Y.%m.%d").date()
            except ValueError:
                continue

            def parse_int(td):
                txt = td.get_text(strip=True).replace(",", "")
                return int(txt) if txt.lstrip("-").isdigit() else 0

            rows.append(
                {
                    "trade_date": trade_date,
                    "close": parse_int(tds[1]),
                    "open": parse_int(tds[3]),
                    "high": parse_int(tds[4]),
                    "low": parse_int(tds[5]),
                    "volume": parse_int(tds[6]),
                }
            )

        time.sleep(config.REQUEST_DELAY)

    if not rows:
        return pd.DataFrame(
            columns=["trade_date", "open", "high", "low", "close", "volume"]
        )

    df = pd.DataFrame(rows)
    df.sort_values("trade_date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def fetch_fundamental(code: str) -> dict:
    """Scrape fundamental data (PER, PBR, EPS, BPS, dividend yield) from Naver Finance.

    Returns a dict with keys: per, pbr, eps, bps, dividend_yield, market_cap.
    """
    url = NAVER_MAIN_URL
    params = {"code": code}
    result = {
        "per": None,
        "pbr": None,
        "eps": None,
        "bps": None,
        "dividend_yield": None,
        "market_cap": None,
    }

    try:
        resp = requests.get(
            url, params=params, headers=HEADERS, timeout=config.REQUEST_TIMEOUT
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Fundamental fetch failed for %s: %s", code, exc)
        return result

    soup = BeautifulSoup(resp.text, "lxml")

    # Parse the aside table that contains PER, EPS, PBR, BPS
    table = soup.find("table", {"summary": lambda s: s and "투자정보" in s if s else False})
    if table is None:
        # fallback: look for the corp_group1 area
        table = soup.find("div", class_="corp_group1")

    if table:
        text = table.get_text(" ", strip=True)

        import re

        for key, pattern in [
            ("per", r"PER\s+([\d,.]+)"),
            ("eps", r"EPS\s+([\d,.]+)"),
            ("pbr", r"PBR\s+([\d,.]+)"),
            ("bps", r"BPS\s+([\d,.]+)"),
        ]:
            m = re.search(pattern, text)
            if m:
                try:
                    result[key] = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass

    # Dividend yield from the page
    div_tag = soup.find("em", id="_dvr")
    if div_tag:
        try:
            result["dividend_yield"] = float(div_tag.get_text(strip=True).replace(",", ""))
        except ValueError:
            pass

    # Market cap
    cap_tag = soup.find("em", id="_market_sum")
    if cap_tag:
        try:
            cap_text = cap_tag.get_text(strip=True).replace(",", "").replace("\n", "")
            result["market_cap"] = int(cap_text) * 100_000_000  # displayed in 억원
        except (ValueError, TypeError):
            pass

    return result
