import json
import os
import statistics
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf


# =========================================================
# CONFIG
# =========================================================

TOP_N = 40
REQUEST_TIMEOUT = 30

BQ_API_KEY = os.environ.get("BUSINESSQUANT_API_KEY")

BQ_ESTIMATES_URL = "https://data.businessquant.com/estimates"
BQ_HISTORIC_URL = "https://data.businessquant.com/historic"

HISTORY_CACHE_FILE = "history_cache.json"

KST = timezone(timedelta(hours=9))


# =========================================================
# NASDAQ-100 UNIVERSE
# =========================================================

NASDAQ_100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT",
    "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO",
    "AXON", "AZN", "BIIB", "BKNG", "CDNS", "CDW", "CEG", "CHTR",
    "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX", "CTAS",
    "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST",
    "FTNT", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN", "INTC",
    "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "MAR",
    "MCHP", "MDLZ", "MELI", "META", "MNST", "MPWR", "MRVL", "MSFT",
    "MSTR", "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY",
    "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM",
    "REGN", "ROP", "ROST", "SBUX", "SHOP", "SNPS", "TEAM", "TMUS",
    "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY",
    "WDC", "WMT", "XEL", "ZS"
]


# =========================================================
# INVESTMENT-ORIENTED INDUSTRY GROUP
# =========================================================

INDUSTRY_GROUP_MAP = {

    # Semiconductors
    "Semiconductors": "반도체",

    # Semiconductor equipment
    "Semiconductor Equipment & Materials": "반도체 장비",

    # Software
    "Software - Infrastructure": "소프트웨어",
    "Software - Application": "소프트웨어",
    "Information Technology Services": "소프트웨어",

    # Internet / Platform
    "Internet Content & Information": "인터넷·플랫폼",
    "Internet Retail": "전자상거래",
    "Travel Services": "인터넷·플랫폼",

    # Hardware / networking
    "Computer Hardware": "하드웨어·IT",
    "Communication Equipment": "하드웨어·IT",
    "Consumer Electronics": "하드웨어·IT",

    # Media
    "Entertainment": "미디어·엔터테인먼트",
    "Broadcasting": "미디어·엔터테인먼트",

    # Biotech / healthcare
    "Biotechnology": "바이오",
    "Diagnostics & Research": "헬스케어",
    "Medical Devices": "헬스케어",
    "Drug Manufacturers - General": "제약",
    "Drug Manufacturers - Specialty & Generic": "제약",

    # Financial
    "Credit Services": "금융",
    "Financial Data & Stock Exchanges": "금융",

    # Retail / consumer
    "Discount Stores": "유통·소비재",
    "Specialty Retail": "유통·소비재",
    "Restaurants": "유통·소비재",
    "Beverages - Non-Alcoholic": "유통·소비재",
    "Packaged Foods": "유통·소비재",

    # Auto / transportation
    "Auto Manufacturers": "자동차·모빌리티",
    "Auto Parts": "자동차·모빌리티",
    "Airlines": "운송",
    "Railroads": "운송",
    "Integrated Freight & Logistics": "운송",

    # Industrial
    "Aerospace & Defense": "산업재",
    "Specialty Industrial Machinery": "산업재",
    "Industrial Distribution": "산업재",
    "Conglomerates": "산업재",

    # Energy
    "Oil & Gas Integrated": "에너지",
    "Oil & Gas E&P": "에너지",
    "Oil & Gas Midstream": "에너지",

    # Telecom
    "Telecom Services": "통신",

    # Utilities
    "Utilities - Regulated Electric": "유틸리티",
    "Utilities - Diversified": "유틸리티",

    # Consumer defensive
    "Household & Personal Products": "필수소비재",
    "Tobacco": "필수소비재",
}


# Ticker-specific overrides.
# Yahoo 분류가 애매하거나 투자 관점에서 묶는 것이 더 적절한 경우 사용.
TICKER_INDUSTRY_OVERRIDE = {
    "NVDA": "반도체",
    "AMD": "반도체",
    "AVGO": "반도체",
    "MU": "반도체",
    "QCOM": "반도체",
    "TXN": "반도체",
    "MRVL": "반도체",
    "MCHP": "반도체",
    "NXPI": "반도체",
    "ON": "반도체",

    "ASML": "반도체 장비",
    "AMAT": "반도체 장비",
    "LRCX": "반도체 장비",
    "KLAC": "반도체 장비",

    "MSFT": "소프트웨어",
    "ADBE": "소프트웨어",
    "PLTR": "소프트웨어",
    "PANW": "소프트웨어",
    "CRWD": "소프트웨어",
    "DDOG": "소프트웨어",
    "SNPS": "소프트웨어",
    "CDNS": "소프트웨어",
    "ADSK": "소프트웨어",
    "INTU": "소프트웨어",
    "WDAY": "소프트웨어",
    "TEAM": "소프트웨어",
    "ZS": "소프트웨어",

    "GOOG": "인터넷·플랫폼",
    "GOOGL": "인터넷·플랫폼",
    "META": "인터넷·플랫폼",
    "NFLX": "미디어·엔터테인먼트",

    "AMZN": "전자상거래",
    "MELI": "전자상거래",
    "PDD": "전자상거래",
    "DASH": "전자상거래",

    "AAPL": "하드웨어·IT",
    "CSCO": "하드웨어·IT",

    "TSLA": "자동차·모빌리티",

    "MSTR": "디지털자산·핀테크",
}


# =========================================================
# TIME / NUMBER HELPERS
# =========================================================

def now_kst():
    return datetime.now(KST)


def to_number(value):
    if value is None or isinstance(value, bool):
        return None

    try:
        value = float(value)

        if value != value:
            return None

        if value in (float("inf"), float("-inf")):
            return None

        return value

    except (TypeError, ValueError):
        return None


def parse_year(value):
    if value is None:
        return None

    text = str(value).strip()

    if len(text) == 4 and text.isdigit():
        return int(text)

    return None


def safe_growth(current, previous):
    if current is None or previous is None:
        return None

    if current <= 0 or previous <= 0:
        return None

    return (current / previous - 1) * 100


def safe_cagr(start, end, years):
    if start is None or end is None:
        return None

    if start <= 0 or end <= 0 or years <= 0:
        return None

    return ((end / start) ** (1 / years) - 1) * 100


def safe_fper(price, eps):
    if price is None or eps is None:
        return None

    if price <= 0 or eps <= 0:
        return None

    return price / eps


def median(values):
    values = [
        x for x in values
        if x is not None
    ]

    if not values:
        return None

    return statistics.median(values)


def percentile(values, p):
    values = sorted(
        x for x in values
        if x is not None
    )

    if not values:
        return None

    if len(values) == 1:
        return values[0]

    position = (p / 100) * (len(values) - 1)

    lower = int(position)
    upper = min(lower + 1, len(values) - 1)

    fraction = position - lower

    return (
        values[lower]
        + (values[upper] - values[lower]) * fraction
    )


def safe_discount(current, historical):
    if current is None or historical is None:
        return None

    if current <= 0 or historical <= 0:
        return None

    return (current / historical - 1) * 100


# =========================================================
# INDUSTRY
# =========================================================

def classify_industry(ticker, yahoo_industry):
    if ticker in TICKER_INDUSTRY_OVERRIDE:
        return TICKER_INDUSTRY_OVERRIDE[ticker]

    if yahoo_industry in INDUSTRY_GROUP_MAP:
        return INDUSTRY_GROUP_MAP[yahoo_industry]

    return yahoo_industry or "기타"


# =========================================================
# YAHOO DATA
# =========================================================

def get_yahoo_data(ticker):

    try:
        obj = yf.Ticker(ticker)
        info = obj.info

        market_cap = to_number(
            info.get("marketCap")
        )

        price = to_number(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
        )

        if price is None:
            try:
                price = to_number(
                    obj.fast_info.get("lastPrice")
                )
            except Exception:
                pass

        if market_cap is None or price is None:
            print(
                f"[Yahoo] {ticker}: "
                "missing market cap or price"
            )
            return None

        yahoo_industry = (
            info.get("industry")
            or info.get("industryKey")
            or "Unknown"
        )

        return {
            "ticker": ticker,
            "company": (
                info.get("longName")
                or info.get("shortName")
                or ticker
            ),
            "sector": (
                info.get("sector")
                or "Unknown"
            ),
            "industry_raw": yahoo_industry,
            "industry_group": classify_industry(
                ticker,
                yahoo_industry
            ),
            "market_cap": market_cap,
            "price": price,
            "forward_pe": to_number(
                info.get("forwardPE")
            ),
        }

    except Exception as e:

        print(
            f"[Yahoo] {ticker}: {e}"
        )

        return None


# =========================================================
# BUSINESS QUANT — EPS
# EXACTLY ONE REQUEST PER STOCK
# =========================================================

def get_businessquant_eps(ticker):

    response = requests.get(
        BQ_ESTIMATES_URL,
        params={
            "ticker": ticker,
            "mode": "eps",
            "api_key": BQ_API_KEY,
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "BQ_RATE_LIMIT"
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"BQ_HTTP_{response.status_code}"
        )

    try:
        payload = response.json()
    except Exception:
        raise RuntimeError(
            "BQ_INVALID_JSON"
        )

    metadata = payload.get("metadata") or {}

    returned_ticker = (
        metadata.get("ticker")
        or metadata.get("symbol")
    )

    if returned_ticker:

        returned_ticker = str(
            returned_ticker
        ).strip().upper()

        if returned_ticker != ticker.upper():

            raise RuntimeError(
                "BQ_TICKER_MISMATCH: "
                f"requested={ticker}, "
                f"returned={returned_ticker}"
            )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError(
            "BQ_INVALID_DATA"
        )

    rows = []

    for section in data:

        if not isinstance(section, dict):
            continue

        dimension = str(
            section.get("dimension") or ""
        ).lower()

        if dimension != "annual":
            continue

        estimates = section.get("estimates")

        if not isinstance(estimates, list):
            continue

        for row in estimates:

            if not isinstance(row, dict):
                continue

            year = parse_year(
                row.get("period")
            )

            if year is None:
                continue

            data_type = str(
                row.get("data_type") or ""
            ).lower()

            if data_type == "reported":

                eps = to_number(
                    row.get("value_reported")
                )

            elif data_type == "estimate":

                eps = to_number(
                    row.get("value_estimate")
                )

            else:
                continue

            if eps is None:
                continue

            rows.append({
                "year": year,
                "data_type": data_type,
                "eps": eps,
            })

    if not rows:
        raise RuntimeError(
            "BQ_NO_ANNUAL_EPS"
        )

    # 같은 year/type 중복이 있으면 마지막 값 사용
    unique = {}

    for row in rows:

        unique[
            (
                row["year"],
                row["data_type"]
            )
        ] = row

    rows = list(unique.values())

    rows.sort(
        key=lambda x: (
            x["year"],
            x["data_type"]
        )
    )

    return rows


# =========================================================
# HISTORICAL P/E
#
# 중요:
# 여기서는 실제 historical P/E 데이터만 사용한다.
# 현재 EPS × 과거 가격 방식으로 재구성하지 않는다.
# =========================================================

def get_businessquant_historical_pe(ticker):

    response = requests.get(
        BQ_HISTORIC_URL,
        params={
            "slug": "price-to-earnings-daily",
            "ticker": ticker,
            "period": "max",
            "api_key": BQ_API_KEY,
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "BQ_HISTORY_RATE_LIMIT"
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"BQ_HISTORY_HTTP_{response.status_code}"
        )

    try:
        payload = response.json()
    except Exception:
        raise RuntimeError(
            "BQ_HISTORY_INVALID_JSON"
        )

    metadata = payload.get("metadata") or {}

    returned_ticker = (
        metadata.get("ticker")
        or metadata.get("symbol")
    )

    if returned_ticker:

        returned_ticker = str(
            returned_ticker
        ).strip().upper()

        if returned_ticker != ticker.upper():
            raise RuntimeError(
                "BQ_HISTORY_TICKER_MISMATCH"
            )

    raw_data = payload.get("data")

    if isinstance(raw_data, list):
        rows = raw_data

    elif isinstance(
        payload.get("series"),
        list
    ):
        rows = payload["series"]

    else:
        rows = []

    parsed = []

    for row in rows:

        if not isinstance(row, dict):
            continue

        date = (
            row.get("date")
            or row.get("period")
            or row.get("timestamp")
        )

        value = (
            row.get("value")
            if "value" in row
            else row.get("pe")
        )

        value = to_number(value)

        if not date or value is None:
            continue

        # 음수/0 P/E 제외
        if value <= 0:
            continue

        parsed.append({
            "date": str(date),
            "value": value,
        })

    if not parsed:
        raise RuntimeError(
            "BQ_NO_HISTORICAL_PE"
        )

    return parsed


# =========================================================
# HISTORY CACHE
# =========================================================

def load_history_cache():

    if not os.path.exists(
        HISTORY_CACHE_FILE
    ):
        return {}

    try:

        with open(
            HISTORY_CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception:
        return {}


def save_history_cache(cache):

    temp = HISTORY_CACHE_FILE + ".tmp"

    with open(
        temp,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp,
        HISTORY_CACHE_FILE
    )


# =========================================================
# HISTORICAL STATISTICS
# =========================================================

def build_historical_stats(history_rows):

    empty = {
        "count": 0,
        "median": None,
        "p25": None,
        "p75": None,
        "min": None,
        "max": None,
        "median_3y": None,
        "median_5y": None,
        "median_10y": None,
    }

    if not history_rows:
        return empty

    today = now_kst().date()

    all_values = [
        row["value"]
        for row in history_rows
        if row.get("value") is not None
    ]

    def values_since(days):

        cutoff = (
            today - timedelta(days=days)
        )

        values = []

        for row in history_rows:

            try:
                date = datetime.strptime(
                    str(row["date"])[:10],
                    "%Y-%m-%d"
                ).date()
            except Exception:
                continue

            if date >= cutoff:
                values.append(
                    row["value"]
                )

        return values

    values_3y = values_since(365 * 3)
    values_5y = values_since(365 * 5)
    values_10y = values_since(365 * 10)

    if not all_values:
        return empty

    return {
        "count": len(all_values),

        "median": median(
            all_values
        ),

        "p25": percentile(
            all_values,
            25
        ),

        "p75": percentile(
            all_values,
            75
        ),

        "min": min(all_values),
        "max": max(all_values),

        "median_3y": median(
            values_3y
        ),

        "median_5y": median(
            values_5y
        ),

        "median_10y": median(
            values_10y
        ),
    }


# =========================================================
# EPS STRUCTURE
# =========================================================

def build_eps_structure(
    rows,
    current_year
):

    reported = {}
    estimates = {}

    for row in rows:

        year = row["year"]
        eps = row["eps"]

        if row["data_type"] == "reported":
            reported[year] = eps

        elif row["data_type"] == "estimate":
            estimates[year] = eps

    previous_actual_years = [
        year
        for year in reported
        if year < current_year
    ]

    previous_actual_year = (
        max(previous_actual_years)
        if previous_actual_years
        else None
    )

    previous_actual_eps = (
        reported.get(
            previous_actual_year
        )
        if previous_actual_year
        else None
    )

    forecast = {}

    for offset in range(5):

        year = current_year + offset

        forecast[
            year
        ] = estimates.get(year)

    return {
        "previous_actual_year":
            previous_actual_year,

        "previous_actual_eps":
            previous_actual_eps,

        "eps_years":
            forecast,

        "reported_years":
            sorted(reported.keys()),

        "estimate_years":
            sorted(estimates.keys()),
    }


# =========================================================
# STOCK
# =========================================================

def build_stock(
    yahoo,
    eps_rows,
    history_rows,
    rank,
    current_year
):

    eps = build_eps_structure(
        eps_rows,
        current_year
    )

    forecast = eps["eps_years"]

    current_eps = forecast.get(
        current_year
    )

    y1_eps = forecast.get(
        current_year + 1
    )

    y2_eps = forecast.get(
        current_year + 2
    )

    y3_eps = forecast.get(
        current_year + 3
    )

    y4_eps = forecast.get(
        current_year + 4
    )

    growth = {
        "current":
            safe_growth(
                current_eps,
                eps["previous_actual_eps"]
            ),

        "y1":
            safe_growth(
                y1_eps,
                current_eps
            ),

        "y2":
            safe_growth(
                y2_eps,
                y1_eps
            ),

        "y3":
            safe_growth(
                y3_eps,
                y2_eps
            ),

        "y4":
            safe_growth(
                y4_eps,
                y3_eps
            ),
    }

    cagr_4y = safe_cagr(
        current_eps,
        y4_eps,
        4
    )

    growth_values = [
        growth["y1"],
        growth["y2"],
        growth["y3"],
        growth["y4"],
    ]

    growth_values = [
        x for x in growth_values
        if x is not None
    ]

    if len(growth_values) < 2:

        growth_trend = "N/A"

    else:

        change = (
            growth_values[-1]
            - growth_values[0]
        )

        if change > 2:
            growth_trend = "accelerating"

        elif change < -2:
            growth_trend = "decelerating"

        else:
            growth_trend = "stable"

    price = yahoo["price"]

    current_fper = safe_fper(
        price,
        current_eps
    )

    future_fper = {
        "current":
            safe_fper(
                price,
                current_eps
            ),

        "y1":
            safe_fper(
                price,
                y1_eps
            ),

        "y2":
            safe_fper(
                price,
                y2_eps
            ),

        "y3":
            safe_fper(
                price,
                y3_eps
            ),

        "y4":
            safe_fper(
                price,
                y4_eps
            ),
    }

    historical = build_historical_stats(
        history_rows
    )

    historical[
        "discount_3y"
    ] = safe_discount(
        current_fper,
        historical["median_3y"]
    )

    historical[
        "discount_5y"
    ] = safe_discount(
        current_fper,
        historical["median_5y"]
    )

    historical[
        "discount_10y"
    ] = safe_discount(
        current_fper,
        historical["median_10y"]
    )

    return {

        "ticker":
            yahoo["ticker"],

        "company":
            yahoo["company"],

        "sector":
            yahoo["sector"],

        "industry":
            yahoo["industry_group"],

        "industry_raw":
            yahoo["industry_raw"],

        "market_cap":
            yahoo["market_cap"],

        "market_cap_rank":
            rank,

        "price":
            price,

        "forward_pe":
            yahoo["forward_pe"],

        "current_year":
            current_year,

        "previous_actual_year":
            eps["previous_actual_year"],

        "previous_actual_eps":
            eps["previous_actual_eps"],

        "current_eps":
            current_eps,

        "y1_eps":
            y1_eps,

        "y2_eps":
            y2_eps,

        "y3_eps":
            y3_eps,

        "y4_eps":
            y4_eps,

        "eps_years":
            eps["eps_years"],

        "reported_years":
            eps["reported_years"],

        "estimate_years":
            eps["estimate_years"],

        "eps_growth":
            growth,

        "current_growth":
            growth["current"],

        "cagr_4y":
            cagr_4y,

        "growth_trend":
            growth_trend,

        "current_fper":
            current_fper,

        "future_fper":
            future_fper,

        "historical_fper":
            historical,

        "historical_data_available":
            bool(history_rows),

        "sources": [
            "Yahoo Finance"
        ] + (
            ["Business Quant"]
            if eps_rows
            else []
        ),
    }


# =========================================================
# TOP 40
# =========================================================

def select_top_40():

    candidates = []

    for ticker in NASDAQ_100:

        data = get_yahoo_data(
            ticker
        )

        if data is not None:
            candidates.append(data)

    candidates.sort(
        key=lambda x:
            x["market_cap"],
        reverse=True
    )

    selected = candidates[:TOP_N]

    for rank, item in enumerate(
        selected,
        start=1
    ):
        item["market_cap_rank"] = rank

    return selected


# =========================================================
# VALIDATION
# =========================================================

def validate_stock(stock):

    for field in [
        "ticker",
        "company",
        "market_cap",
        "price",
    ]:

        if stock.get(field) is None:
            raise RuntimeError(
                f"MISSING_FIELD:"
                f"{stock.get('ticker')}:"
                f"{field}"
            )


def validate_collection(stocks):

    if not stocks:
        raise RuntimeError(
            "NO_STOCK_DATA"
        )

    tickers = [
        stock["ticker"]
        for stock in stocks
    ]

    if len(tickers) != len(set(tickers)):
        raise RuntimeError(
            "DUPLICATE_TICKER"
        )

    trajectories = {}

    for stock in stocks:

        trajectory = (
            stock.get("current_eps"),
            stock.get("y1_eps"),
            stock.get("y2_eps"),
            stock.get("y3_eps"),
            stock.get("y4_eps"),
        )

        # 전부 N/A인 경우는 허용
        if all(
            value is None
            for value in trajectory
        ):
            continue

        trajectories.setdefault(
            trajectory,
            []
        ).append(
            stock["ticker"]
        )

    suspicious = [
        group
        for group in trajectories.values()
        if len(group) >= 3
    ]

    if suspicious:
        raise RuntimeError(
            "SUSPICIOUS_SHARED_EPS_TRAJECTORY:"
            + str(suspicious)
        )


# =========================================================
# INDUSTRY AGGREGATION
# =========================================================

def build_industries(stocks):

    groups = {}

    for stock in stocks:

        group_name = (
            stock.get("industry")
            or "기타"
        )

        groups.setdefault(
            group_name,
            []
        ).append(stock)

    result = []

    for industry, group in groups.items():

        current_values = [
            stock["current_fper"]
            for stock in group
            if stock["current_fper"]
            is not None
        ]

        hist_3y = [
            stock["historical_fper"]["median_3y"]
            for stock in group
            if stock["historical_fper"]["median_3y"]
            is not None
        ]

        hist_5y = [
            stock["historical_fper"]["median_5y"]
            for stock in group
            if stock["historical_fper"]["median_5y"]
            is not None
        ]

        hist_10y = [
            stock["historical_fper"]["median_10y"]
            for stock in group
            if stock["historical_fper"]["median_10y"]
            is not None
        ]

        cagr_values = [
            stock["cagr_4y"]
            for stock in group
            if stock["cagr_4y"]
            is not None
        ]

        current_fper = median(
            current_values
        )

        historical_3y = median(
            hist_3y
        )

        historical_5y = median(
            hist_5y
        )

        historical_10y = median(
            hist_10y
        )

        result.append({

            "industry":
                industry,

            "stock_count":
                len(group),

            "tickers": [
                stock["ticker"]
                for stock in group
            ],

            "current_fper_median":
                current_fper,

            "historical_3y_fper_median":
                historical_3y,

            "historical_5y_fper_median":
                historical_5y,

            "historical_10y_fper_median":
                historical_10y,

            "historical_3y_discount":
                safe_discount(
                    current_fper,
                    historical_3y
                ),

            "historical_5y_discount":
                safe_discount(
                    current_fper,
                    historical_5y
                ),

            "historical_10y_discount":
                safe_discount(
                    current_fper,
                    historical_10y
                ),

            "eps_cagr_4y_median":
                median(
                    cagr_values
                ),
        })

    result.sort(
        key=lambda x:
            (
                x["historical_5y_discount"]
                if x["historical_5y_discount"]
                is not None
                else 999999
            )
    )

    return result


# =========================================================
# WAITING DATA
# =========================================================

def build_waiting_output(
    selected,
    current_year
):

    stocks = []

    for rank, yahoo in enumerate(
        selected,
        start=1
    ):

        stocks.append({

            "ticker":
                yahoo["ticker"],

            "company":
                yahoo["company"],

            "sector":
                yahoo["sector"],

            "industry":
                yahoo["industry_group"],

            "industry_raw":
                yahoo["industry_raw"],

            "market_cap":
                yahoo["market_cap"],

            "market_cap_rank":
                rank,

            "price":
                yahoo["price"],

            "forward_pe":
                yahoo["forward_pe"],

            "current_year":
                current_year,

            "previous_actual_year":
                None,

            "previous_actual_eps":
                None,

            "current_eps":
                None,

            "y1_eps":
                None,

            "y2_eps":
                None,

            "y3_eps":
                None,

            "y4_eps":
                None,

            "eps_years": {
                str(current_year + i): None
                for i in range(5)
            },

            "reported_years":
                [],

            "estimate_years":
                [],

            "eps_growth": {
                "current": None,
                "y1": None,
                "y2": None,
                "y3": None,
                "y4": None,
            },

            "current_growth":
                None,

            "cagr_4y":
                None,

            "growth_trend":
                "N/A",

            "current_fper":
                None,

            "future_fper": {
                "current": None,
                "y1": None,
                "y2": None,
                "y3": None,
                "y4": None,
            },

            "historical_fper": {
                "count": 0,
                "median": None,
                "p25": None,
                "p75": None,
                "min": None,
                "max": None,
                "median_3y": None,
                "median_5y": None,
                "median_10y": None,
                "discount_3y": None,
                "discount_5y": None,
                "discount_10y": None,
            },

            "historical_data_available":
                False,

            "sources": [
                "Yahoo Finance"
            ],
        })

    return {
        "status": "WAITING",
        "generated_at_kst":
            now_kst().isoformat(),
        "generated_date_kst":
            now_kst().strftime("%Y-%m-%d"),
        "current_year":
            current_year,
        "top_n":
            TOP_N,
        "stock_count":
            len(stocks),
        "historical_cache_count":
            0,
        "historical_new_requests":
            0,
        "stocks":
            stocks,
        "industries":
            build_industries(stocks),
        "sources": {
            "market":
                "Yahoo Finance",
            "eps":
                "Business Quant Analyst Estimates",
            "historical_fper":
                "Business Quant Historical Metrics",
        },
        "methodology": {
            "current_fper":
                "current price / current-year EPS estimate",
            "future_fper":
                "current price / future EPS estimate",
            "historical_discount":
                "current FPER / historical median FPER - 1",
            "industry_valuation":
                "median of available stocks",
            "missing_data":
                "N/A",
            "future_eps":
                "never extrapolated",
            "historical_negative_pe":
                "excluded",
        },
    }


# =========================================================
# MAIN
# =========================================================

def main():

    current_year = now_kst().year

    print(
        f"Current KST year: {current_year}"
    )

    # -----------------------------------------------------
    # 1. Yahoo → Top 40
    # -----------------------------------------------------

    selected = select_top_40()

    if not selected:
        raise RuntimeError(
            "YAHOO_NO_VALID_STOCKS"
        )

    print(
        "Selected:",
        [
            x["ticker"]
            for x in selected
        ]
    )

    # -----------------------------------------------------
    # 2. API KEY가 없으면 WAITING
    #    절대 기존 data.json을 그대로 재사용하지 않는다.
    # -----------------------------------------------------

    # 캐시는 API 키 유무와 관계없이 항상 존재하도록 보장한다.
    history_cache = load_history_cache()
    save_history_cache(history_cache)

    if not BQ_API_KEY:

        print(
            "BUSINESSQUANT_API_KEY missing."
        )

        output = build_waiting_output(
            selected,
            current_year
        )

        write_output(
            output
        )

        return

    # -----------------------------------------------------
    # 3. EPS
    #
    # 정확히 종목당 1회.
    # 429 발생 시 재시도하지 않는다.
    # -----------------------------------------------------

    final_stocks = []

    for rank, yahoo in enumerate(
        selected,
        start=1
    ):

        ticker = yahoo["ticker"]

        print(
            f"[EPS {rank}/{len(selected)}] "
            f"{ticker}"
        )

        try:

            eps_rows = (
                get_businessquant_eps(
                    ticker
                )
            )

        except Exception as e:

            print(
                f"[EPS ERROR] "
                f"{ticker}: {e}"
            )

            eps_rows = []

        # -------------------------------------------------
        # Historical P/E
        # 캐시에 없으면 Business Quant에서 1회 조회 후 저장.
        # 이미 캐시가 있으면 추가 요청하지 않는다.
        # -------------------------------------------------

        history_rows = history_cache.get(ticker) or []

        if not history_rows:
            try:
                history_rows = get_businessquant_historical_pe(ticker)
                history_cache[ticker] = history_rows
                print(f"[HISTORY OK] {ticker}: {len(history_rows)} rows")
            except Exception as e:
                print(f"[HISTORY ERROR] {ticker}: {e}")
                history_rows = []

        stock = build_stock(
            yahoo,
            eps_rows,
            history_rows,
            rank,
            current_year
        )

        validate_stock(
            stock
        )

        final_stocks.append(
            stock
        )

    # 실행 중 새 캐시가 생겼거나 기존 캐시가 변경된 경우 저장한다.
    save_history_cache(history_cache)

    # -----------------------------------------------------
    # 4. 데이터 integrity
    # -----------------------------------------------------

    validate_collection(
        final_stocks
    )

    # -----------------------------------------------------
    # 5. 산업
    # -----------------------------------------------------

    industries = build_industries(
        final_stocks
    )

    # -----------------------------------------------------
    # 6. 상태 결정
    # -----------------------------------------------------

    eps_success_count = sum(
        1
        for stock in final_stocks
        if stock.get(
            "current_eps"
        ) is not None
    )

    if eps_success_count == len(
        final_stocks
    ):
        status = "LIVE"

    elif eps_success_count > 0:
        status = "PARTIAL"

    else:
        status = "WAITING"

    history_count = sum(
        1
        for stock in final_stocks
        if stock[
            "historical_data_available"
        ]
    )

    # -----------------------------------------------------
    # 7. Output
    # -----------------------------------------------------

    output = {

        "status":
            status,

        "generated_at_kst":
            now_kst().isoformat(),

        "generated_date_kst":
            now_kst().strftime(
                "%Y-%m-%d"
            ),

        "current_year":
            current_year,

        "top_n":
            TOP_N,

        "stock_count":
            len(final_stocks),

        "eps_success_count":
            eps_success_count,

        "historical_available_count":
            history_count,

        "stocks":
            final_stocks,

        "industries":
            industries,

        "sources": {

            "market":
                "Yahoo Finance",

            "eps":
                "Business Quant Analyst Estimates",

            "historical_fper":
                "Business Quant Historical Metrics",
        },

        "methodology": {

            "current_fper":
                "current price / current-year EPS estimate",

            "future_fper":
                "current price / future EPS estimate",

            "historical_discount":
                "current FPER / historical median FPER - 1",

            "industry_valuation":
                "median of available stocks",

            "missing_data":
                "N/A",

            "future_eps":
                "never extrapolated",

            "historical_negative_pe":
                "excluded from historical valuation statistics",

            "eps_api_calls":
                "one Business Quant EPS request per stock",

            "historical_pe":
                "actual historical P/E series only",
        },
    }

    write_output(
        output
    )


# =========================================================
# SAFE OUTPUT
# =========================================================

def write_output(output):

    temp_file = "data.json.tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp_file,
        "data.json"
    )

    print(
        "data.json written."
    )

    print(
        "Status:",
        output["status"]
    )

    print(
        "Stocks:",
        output["stock_count"]
    )


if __name__ == "__main__":
    main()
