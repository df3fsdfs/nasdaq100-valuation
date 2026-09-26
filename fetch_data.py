
import json
import os
import statistics
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf


# =========================================================
# CONFIG
# =========================================================

BQ_API_KEY = os.environ.get("BUSINESSQUANT_API_KEY")

BQ_ESTIMATES_URL = "https://data.businessquant.com/estimates"
BQ_HISTORIC_URL = "https://data.businessquant.com/historic"

TOP_N = 40
REQUEST_TIMEOUT = 30

# Historical P/E는 이미 받은 ticker를 다시 호출하지 않는다.
HISTORY_CACHE_FILE = "history_cache.json"

# 최초 구축 시 한 번에 너무 많은 Historical API를 호출하지 않는다.
MAX_NEW_HISTORY_REQUESTS = 5

KST = timezone(timedelta(hours=9))


# =========================================================
# NASDAQ-100
# =========================================================

NASDAQ_100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT",
    "AMD", "AMGN", "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO",
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
# HELPERS
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


def parse_year(period):
    if period is None:
        return None

    text = str(period).strip()

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

    if start <= 0 or end <= 0:
        return None

    if years <= 0:
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


def percentile(values, percentile_value):
    values = sorted(
        x for x in values
        if x is not None
    )

    if not values:
        return None

    if len(values) == 1:
        return values[0]

    position = (
        percentile_value / 100
    ) * (len(values) - 1)

    lower = int(position)
    upper = min(
        lower + 1,
        len(values) - 1
    )

    fraction = position - lower

    return (
        values[lower]
        + (
            values[upper]
            - values[lower]
        ) * fraction
    )


def safe_discount(current, historical):
    if current is None or historical is None:
        return None

    if current <= 0 or historical <= 0:
        return None

    return (
        current / historical - 1
    ) * 100


# =========================================================
# YAHOO
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

        return {
            "ticker": ticker,
            "company": (
                info.get("longName")
                or info.get("shortName")
                or ticker
            ),
            "industry": (
                info.get("industry")
                or info.get("industryKey")
                or "Unknown"
            ),
            "sector": (
                info.get("sector")
                or "Unknown"
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
# =========================================================

def get_businessquant_eps(ticker):

    if not BQ_API_KEY:
        raise RuntimeError(
            "BUSINESSQUANT_API_KEY is not configured."
        )

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
            f"BQ_HTTP_{response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        payload = response.json()
    except Exception:
        raise RuntimeError(
            "BQ_INVALID_JSON"
        )

    metadata = payload.get(
        "metadata"
    ) or {}

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

        if str(
            section.get("dimension") or ""
        ).lower() != "annual":
            continue

        estimates = section.get(
            "estimates"
        )

        if not isinstance(
            estimates,
            list
        ):
            continue

        for row in estimates:

            if not isinstance(
                row,
                dict
            ):
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
                    row.get(
                        "value_reported"
                    )
                )

            elif data_type == "estimate":

                eps = to_number(
                    row.get(
                        "value_estimate"
                    )
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

    # 동일 연도/동일 타입 중복 제거
    unique = {}

    for row in rows:
        key = (
            row["year"],
            row["data_type"]
        )

        unique[key] = row

    rows = list(
        unique.values()
    )

    rows.sort(
        key=lambda x: (
            x["year"],
            x["data_type"]
        )
    )

    return rows


# =========================================================
# BUSINESS QUANT — HISTORICAL P/E
# =========================================================

def get_businessquant_historical_pe(ticker):

    if not BQ_API_KEY:
        raise RuntimeError(
            "BUSINESSQUANT_API_KEY is not configured."
        )

    response = requests.get(
        BQ_HISTORIC_URL,
        params={
            "slug":
                "price-to-earnings-daily",
            "ticker": ticker,
            "period": "max",
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
            f"BQ_HISTORY_HTTP_"
            f"{response.status_code}"
        )

    payload = response.json()

    metadata = payload.get(
        "metadata"
    ) or {}

    returned_ticker = (
        metadata.get("ticker")
        or metadata.get("symbol")
    )

    if returned_ticker:

        returned_ticker = str(
            returned_ticker
        ).upper()

        if returned_ticker != ticker.upper():
            raise RuntimeError(
                "BQ_HISTORY_TICKER_MISMATCH: "
                f"{ticker} != "
                f"{returned_ticker}"
            )

    raw_data = payload.get(
        "data"
    )

    # API가 list 형태인 경우
    if isinstance(raw_data, list):
        rows = raw_data

    # 일부 historical API 응답에서
    # series/data가 중첩될 가능성까지 처리
    elif isinstance(
        payload.get("series"),
        list
    ):
        rows = payload["series"]

    else:
        rows = []

    parsed = []

    for row in rows:

        if not isinstance(
            row,
            dict
        ):
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

        # Historical P/E에서
        # 음수/0은 valuation 비교에서 제외
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

        if isinstance(data, dict):
            return data

    except Exception as e:

        print(
            "[History Cache] "
            f"read error: {e}"
        )

    return {}


def save_history_cache(cache):

    temp_file = (
        HISTORY_CACHE_FILE
        + ".tmp"
    )

    with open(
        temp_file,
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
        temp_file,
        HISTORY_CACHE_FILE
    )


# =========================================================
# HISTORICAL STATISTICS
# =========================================================

def build_historical_stats(
    history_rows
):

    if not history_rows:
        return {
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

    today = now_kst().date()

    values_all = [
        row["value"]
        for row in history_rows
    ]

    def values_since(days):

        cutoff = (
            today
            - timedelta(days=days)
        )

        result = []

        for row in history_rows:

            date_text = (
                row["date"][:10]
            )

            try:

                date = datetime.strptime(
                    date_text,
                    "%Y-%m-%d"
                ).date()

            except Exception:
                continue

            if date >= cutoff:
                result.append(
                    row["value"]
                )

        return result

    values_3y = values_since(
        365 * 3
    )

    values_5y = values_since(
        365 * 5
    )

    values_10y = values_since(
        365 * 10
    )

    return {
        "count":
            len(values_all),

        "median":
            median(values_all),

        "p25":
            percentile(
                values_all,
                25
            ),

        "p75":
            percentile(
                values_all,
                75
            ),

        "min":
            min(values_all),

        "max":
            max(values_all),

        "median_3y":
            median(values_3y),

        "median_5y":
            median(values_5y),

        "median_10y":
            median(values_10y),
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

    previous_years = [
        year
        for year in reported
        if year < current_year
    ]

    previous_actual_year = (
        max(previous_years)
        if previous_years
        else None
    )

    previous_actual_eps = (
        reported[
            previous_actual_year
        ]
        if previous_actual_year
        else None
    )

    return {
        "previous_actual_year":
            previous_actual_year,

        "previous_actual_eps":
            previous_actual_eps,

        "current_eps":
            estimates.get(
                current_year
            ),

        "y1_eps":
            estimates.get(
                current_year + 1
            ),

        "y2_eps":
            estimates.get(
                current_year + 2
            ),

        "y3_eps":
            estimates.get(
                current_year + 3
            ),

        "y4_eps":
            estimates.get(
                current_year + 4
            ),

        "eps_years": [
            {
                "year": year,
                "offset": offset,
                "eps": estimates.get(year),
            }
            for offset, year in enumerate(
                range(
                    current_year,
                    current_year + 5
                )
            )
        ],

        "reported_years":
            sorted(
                reported.keys()
            ),

        "estimate_years":
            sorted(
                estimates.keys()
            ),
    }


# =========================================================
# STOCK BUILD
# =========================================================

def build_stock(
    yahoo,
    eps_rows,
    history_rows,
    market_cap_rank,
    current_year
):

    eps = build_eps_structure(
        eps_rows,
        current_year
    )

    price = yahoo["price"]

    current_eps = eps["current_eps"]
    y1_eps = eps["y1_eps"]
    y2_eps = eps["y2_eps"]
    y3_eps = eps["y3_eps"]
    y4_eps = eps["y4_eps"]

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

    future_growth = [
        growth["y1"],
        growth["y2"],
        growth["y3"],
        growth["y4"],
    ]

    future_growth = [
        x for x in future_growth
        if x is not None
    ]

    if len(future_growth) < 2:

        growth_trend = "N/A"

    else:

        change = (
            future_growth[-1]
            - future_growth[0]
        )

        if change > 2:
            growth_trend = "accelerating"

        elif change < -2:
            growth_trend = "decelerating"

        else:
            growth_trend = "stable"

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

    historical = (
        build_historical_stats(
            history_rows
        )
        if history_rows
        else build_historical_stats([])
    )

    return {

        "ticker":
            yahoo["ticker"],

        "company":
            yahoo["company"],

        "sector":
            yahoo["sector"],

        "industry":
            yahoo["industry"],

        "market_cap":
            yahoo["market_cap"],

        "market_cap_rank":
            market_cap_rank,

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

    selected = candidates[
        :TOP_N
    ]

    for index, item in enumerate(
        selected,
        start=1
    ):
        item["market_cap_rank"] = index

    return selected


# =========================================================
# DATA INTEGRITY CHECKS
# =========================================================

def validate_stock(stock):

    required = [
        "ticker",
        "company",
        "market_cap",
        "price",
    ]

    for field in required:

        if stock.get(field) is None:
            raise RuntimeError(
                f"MISSING_REQUIRED_FIELD: "
                f"{stock['ticker']}:{field}"
            )


def validate_collection(stocks):

    if not stocks:
        raise RuntimeError(
            "NO_STOCK_DATA"
        )

    tickers = [
        x["ticker"]
        for x in stocks
    ]

    if len(tickers) != len(
        set(tickers)
    ):
        raise RuntimeError(
            "DUPLICATE_TICKER_IN_OUTPUT"
        )

    # -----------------------------------------------------
    # Detect suspiciously identical EPS trajectories.
    # One or two can legitimately match.
    # 3+ identical full trajectories are suspicious.
    # -----------------------------------------------------

    trajectories = {}

    for stock in stocks:

        key = (
            stock.get("current_eps"),
            stock.get("y1_eps"),
            stock.get("y2_eps"),
            stock.get("y3_eps"),
            stock.get("y4_eps"),
        )

        if all(
            value is None
            for value in key
        ):
            continue

        trajectories.setdefault(
            key,
            []
        ).append(
            stock["ticker"]
        )

    suspicious = []

    for key, group in trajectories.items():

        if len(group) >= 3:
            suspicious.append(
                group
            )

    if suspicious:
        raise RuntimeError(
            "SUSPICIOUS_SHARED_EPS_TRAJECTORY: "
            + str(suspicious)
        )

    # -----------------------------------------------------
    # Ensure EPS values are not identical to a known
    # hardcoded demo trajectory.
    # -----------------------------------------------------

    known_bad = (
        9.21,
        10.06,
        10.39,
        12.83,
        13.10,
    )

    for stock in stocks:

        trajectory = (
            stock.get("current_eps"),
            stock.get("y1_eps"),
            stock.get("y2_eps"),
            stock.get("y3_eps"),
            stock.get("y4_eps"),
        )

        if trajectory == known_bad:
            raise RuntimeError(
                "KNOWN_BAD_DEMO_EPS_DETECTED: "
                + stock["ticker"]
            )


# =========================================================
# MAIN
# =========================================================

def main():

    current_year = now_kst().year

    print(
        f"Current KST year: "
        f"{current_year}"
    )

    if not BQ_API_KEY:
        raise RuntimeError(
            "BUSINESSQUANT_API_KEY missing"
        )

    # -----------------------------------------------------
    # 1. Yahoo → top 40
    # -----------------------------------------------------

    selected = select_top_40()

    if len(selected) < TOP_N:
        print(
            f"WARNING: only "
            f"{len(selected)} "
            f"Yahoo-valid stocks"
        )

    print(
        "Selected tickers:",
        [
            x["ticker"]
            for x in selected
        ]
    )

    # -----------------------------------------------------
    # 2. Load historical cache
    # -----------------------------------------------------

    history_cache = (
        load_history_cache()
    )

    # -----------------------------------------------------
    # 3. EPS
    #
    # One BQ estimate request per stock.
    # No retry.
    # -----------------------------------------------------

    stocks = []

    for index, yahoo in enumerate(
        selected,
        start=1
    ):

        ticker = yahoo["ticker"]

        print(
            f"[EPS {index}/{len(selected)}] "
            f"{ticker}"
        )

        try:

            eps_rows = (
                get_businessquant_eps(
                    ticker
                )
            )

        except RuntimeError as e:

            print(
                f"[EPS ERROR] "
                f"{ticker}: {e}"
            )

            eps_rows = []

        # -------------------------------------------------
        # 4. Historical P/E cache
        # -------------------------------------------------

        history_rows = (
            history_cache.get(
                ticker
            )
        )

        stocks.append({
            "yahoo": yahoo,
            "eps_rows": eps_rows,
            "history_rows":
                history_rows,
        })

    # -----------------------------------------------------
    # 5. Fill missing historical cache
    #
    # Only MAX_NEW_HISTORY_REQUESTS.
    # Never re-request cached ticker.
    # -----------------------------------------------------

    new_history_requests = 0

    for item in stocks:

        ticker = (
            item["yahoo"]["ticker"]
        )

        if item["history_rows"]:
            continue

        if new_history_requests >= (
            MAX_NEW_HISTORY_REQUESTS
        ):
            break

        print(
            "[HISTORY] fetching:",
            ticker
        )

        try:

            history_rows = (
                get_businessquant_historical_pe(
                    ticker
                )
            )

            history_cache[
                ticker
            ] = history_rows

            item["history_rows"] = (
                history_rows
            )

            new_history_requests += 1

        except RuntimeError as e:

            print(
                f"[HISTORY ERROR] "
                f"{ticker}: {e}"
            )

            # 실패를 빈 리스트로 캐시하지 않는다.
            # 다음 실행에서 다시 시도할 수 있게 한다.

    save_history_cache(
        history_cache
    )

    # -----------------------------------------------------
    # 6. Build final stocks
    # -----------------------------------------------------

    final_stocks = []

    for item in stocks:

        yahoo = item["yahoo"]

        eps_rows = item[
            "eps_rows"
        ]

        history_rows = item[
            "history_rows"
        ]

        stock = build_stock(
            yahoo,
            eps_rows,
            history_rows,
            yahoo["market_cap_rank"],
            current_year
        )

        validate_stock(
            stock
        )

        final_stocks.append(
            stock
        )

    # -----------------------------------------------------
    # 7. Integrity validation
    # -----------------------------------------------------

    validate_collection(
        final_stocks
    )

    # -----------------------------------------------------
    # 8. Historical discount
    # -----------------------------------------------------

    for stock in final_stocks:

        historical = stock[
            "historical_fper"
        ]

        current_fper = stock[
            "current_fper"
        ]

        historical[
            "discount_3y"
        ] = safe_discount(
            current_fper,
            historical[
                "median_3y"
            ]
        )

        historical[
            "discount_5y"
        ] = safe_discount(
            current_fper,
            historical[
                "median_5y"
            ]
        )

        historical[
            "discount_10y"
        ] = safe_discount(
            current_fper,
            historical[
                "median_10y"
            ]
        )

    # -----------------------------------------------------
    # 9. Industry aggregation
    # -----------------------------------------------------

    industry_groups = {}

    for stock in final_stocks:

        industry = (
            stock.get("industry")
            or "Unknown"
        )

        industry_groups.setdefault(
            industry,
            []
        ).append(stock)

    industries = []

    for industry, group in (
        industry_groups.items()
    ):

        current_fpers = [
            x["current_fper"]
            for x in group
            if x["current_fper"]
            is not None
        ]

        cagr_values = [
            x["cagr_4y"]
            for x in group
            if x["cagr_4y"]
            is not None
        ]

        hist_values = [
            x[
                "historical_fper"
            ][
                "median_5y"
            ]
            for x in group
            if x[
                "historical_fper"
            ][
                "median_5y"
            ] is not None
        ]

        current_median = median(
            current_fpers
        )

        historical_median = median(
            hist_values
        )

        industries.append({

            "industry":
                industry,

            "stock_count":
                len(group),

            "current_fper_median":
                current_median,

            "historical_5y_fper_median":
                historical_median,

            "historical_5y_discount":
                safe_discount(
                    current_median,
                    historical_median
                ),

            "eps_cagr_4y_median":
                median(
                    cagr_values
                ),
        })

    industries.sort(
        key=lambda x:
            (
                x[
                    "historical_5y_discount"
                ]
                if x[
                    "historical_5y_discount"
                ] is not None
                else 999999
            )
    )

    # -----------------------------------------------------
    # 10. Final output
    # -----------------------------------------------------

    output = {

        "status":
            "LIVE",

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

        "historical_cache_count":
            len(history_cache),

        "historical_new_requests":
            new_history_requests,

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
        },
    }

    # -----------------------------------------------------
    # Atomic write
    # -----------------------------------------------------

    temp_file = (
        "data.json.tmp"
    )

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
        "data.json written successfully."
    )

    print(
        "Stocks:",
        len(final_stocks)
    )

    print(
        "Historical cache:",
        len(history_cache)
    )


if __name__ == "__main__":
    main()
