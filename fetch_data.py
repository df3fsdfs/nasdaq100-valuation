import json
import os
import time
from datetime import datetime, timezone

import requests
import yfinance as yf


# ============================================================
# 설정
# ============================================================

BQ_API_KEY = os.environ.get("BUSINESSQUANT_API_KEY")

BQ_URL = "https://data.businessquant.com/estimates"

TOP_N = 40

CURRENT_YEAR = datetime.now(timezone.utc).year


# ============================================================
# NASDAQ-100 구성종목
# ============================================================

NASDAQ_100_TICKERS = [
    "AAPL", "AMD", "AMAT", "AMGN", "AMZN", "ARM", "ASML", "AVGO",
    "AXON", "BKNG", "BKR", "CCEP", "CDNS", "CDW", "CEG", "CHTR",
    "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CTSH", "DASH", "DDOG",
    "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT", "GEHC", "GILD",
    "GOOG", "GOOGL", "HON", "IDXX", "INTC", "INTU", "ISRG", "KDP",
    "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP", "MDLZ",
    "MELI", "META", "MNST", "MRNA", "MRVL", "MSFT", "MU", "NFLX",
    "NVDA", "NDAQ", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX",
    "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM", "REGN", "ROST",
    "SBUX", "SHOP", "SNPS", "TMUS", "TSLA", "TTWO", "TXN", "VRSK",
    "VRTX", "WBA", "WBD", "WDAY", "WDC", "WMT", "XEL", "ZS"
]


# ============================================================
# 숫자 변환
# ============================================================

def to_number(value):

    if value is None:
        return None

    try:

        value = float(value)

        if value != value:
            return None

        return value

    except (TypeError, ValueError):

        return None


# ============================================================
# Yahoo Finance 데이터
# ============================================================

def get_yahoo_data(ticker):

    result = {
        "company": None,
        "industry": None,
        "market_cap": None,
        "price": None,
        "forward_pe": None,
        "error": None,
    }

    try:

        stock = yf.Ticker(ticker)

        info = stock.info

        result["company"] = (
            info.get("longName")
            or info.get("shortName")
            or ticker
        )

        result["industry"] = info.get("industry")

        result["market_cap"] = to_number(
            info.get("marketCap")
        )

        result["price"] = to_number(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
        )

        result["forward_pe"] = to_number(
            info.get("forwardPE")
        )

    except Exception as e:

        result["error"] = str(e)

        print(
            f"{ticker}: Yahoo error - {e}"
        )

    return result


# ============================================================
# Business Quant EPS
#
# 공식 구조:
#
# data
#   ├─ dimension: annual
#   │    └─ estimates
#   │         ├─ period
#   │         ├─ data_type
#   │         └─ value_estimate
#   │
#   └─ dimension: quarter
#
# ============================================================

def get_businessquant_eps(ticker):

    if not BQ_API_KEY:

        raise RuntimeError(
            "BUSINESSQUANT_API_KEY가 없습니다."
        )

    params = {
        "ticker": ticker,
        "mode": "eps",
        "api_key": BQ_API_KEY,
    }

    response = requests.get(
        BQ_URL,
        params=params,
        timeout=30,
    )

    # --------------------------------------------------------
    # 429 = 일일 한도 초과
    # --------------------------------------------------------

    if response.status_code == 429:

        raise RuntimeError(
            "BQ_RATE_LIMIT"
        )

    response.raise_for_status()

    payload = response.json()

    annual = {}

    data = payload.get("data", [])

    if not isinstance(data, list):

        return {
            "reported": {},
            "estimate": {}
        }

    # --------------------------------------------------------
    # 공식 구조를 정확히 탐색
    # --------------------------------------------------------

    for section in data:

        if not isinstance(section, dict):
            continue

        if section.get("dimension") != "annual":
            continue

        estimates = section.get(
            "estimates",
            []
        )

        if not isinstance(estimates, list):
            continue

        for row in estimates:

            if not isinstance(row, dict):
                continue

            period = row.get("period")
            data_type = row.get("data_type")
            value = to_number(
                row.get("value_estimate")
            )

            if value is None:
                continue

            try:
                year = int(period)
            except (TypeError, ValueError):
                continue

            annual[year] = {
                "type": data_type,
                "value": value
            }

    reported = {}
    estimates = {}

    for year, row in annual.items():

        if row["type"] == "reported":

            reported[year] = row["value"]

        elif row["type"] == "estimate":

            estimates[year] = row["value"]

    print(
        f"{ticker} BQ reported: "
        f"{dict(sorted(reported.items()))}"
    )

    print(
        f"{ticker} BQ estimates: "
        f"{dict(sorted(estimates.items()))}"
    )

    return {
        "reported": reported,
        "estimate": estimates
    }


# ============================================================
# 성장률
# ============================================================

def growth_rate(previous, current):

    if (
        previous is None
        or current is None
        or previous == 0
    ):
        return None

    return (
        (current / previous) - 1
    ) * 100


# ============================================================
# CAGR
# ============================================================

def cagr(start, end, years):

    if (
        start is None
        or end is None
        or years <= 0
        or start <= 0
        or end <= 0
    ):
        return None

    return (
        (end / start)
        ** (1 / years)
        - 1
    ) * 100


# ============================================================
# 성장 추세
# ============================================================

def growth_trend(growth_values):

    values = [
        x for x in growth_values
        if x is not None
    ]

    if len(values) < 2:
        return None

    first = values[0]
    last = values[-1]

    if last > first + 5:
        return "accelerating"

    if last < first - 5:
        return "decelerating"

    return "stable"


# ============================================================
# 종목 하나 생성
# ============================================================

def build_stock(
    rank,
    ticker,
    yahoo,
    bq
):

    reported = bq["reported"]
    estimates = bq["estimate"]

    # --------------------------------------------------------
    # 이전 실제 EPS
    #
    # 현재년도 이전의 가장 최근 reported
    # --------------------------------------------------------

    previous_years = [
        year
        for year in reported
        if year < CURRENT_YEAR
    ]

    previous_year = (
        max(previous_years)
        if previous_years
        else None
    )

    previous_eps = (
        reported.get(previous_year)
        if previous_year is not None
        else None
    )

    # --------------------------------------------------------
    # 현재년도 + 미래 EPS
    # --------------------------------------------------------

    current_eps = estimates.get(
        CURRENT_YEAR
    )

    y1_eps = estimates.get(
        CURRENT_YEAR + 1
    )

    y2_eps = estimates.get(
        CURRENT_YEAR + 2
    )

    y3_eps = estimates.get(
        CURRENT_YEAR + 3
    )

    y4_eps = estimates.get(
        CURRENT_YEAR + 4
    )

    # --------------------------------------------------------
    # 성장률
    # --------------------------------------------------------

    current_growth = growth_rate(
        previous_eps,
        current_eps
    )

    y1_growth = growth_rate(
        current_eps,
        y1_eps
    )

    y2_growth = growth_rate(
        y1_eps,
        y2_eps
    )

    y3_growth = growth_rate(
        y2_eps,
        y3_eps
    )

    y4_growth = growth_rate(
        y3_eps,
        y4_eps
    )

    # --------------------------------------------------------
    # 4Y CAGR
    #
    # 현재년도 → +4Y
    # --------------------------------------------------------

    cagr_4y = cagr(
        current_eps,
        y4_eps,
        4
    )

    # --------------------------------------------------------
    # 성장 추세
    # --------------------------------------------------------

    trend = growth_trend([
        current_growth,
        y1_growth,
        y2_growth,
        y3_growth,
        y4_growth
    ])

    # --------------------------------------------------------
    # 현재 FPER
    #
    # 현재 주가 / 현재년도 EPS
    # --------------------------------------------------------

    price = yahoo["price"]

    if (
        price is not None
        and current_eps is not None
        and current_eps > 0
    ):

        current_fper = (
            price / current_eps
        )

    else:

        current_fper = None

    # --------------------------------------------------------
    # 현재가 유지 시 미래 FPER
    # --------------------------------------------------------

    future_eps = {
        str(CURRENT_YEAR): current_eps,
        str(CURRENT_YEAR + 1): y1_eps,
        str(CURRENT_YEAR + 2): y2_eps,
        str(CURRENT_YEAR + 3): y3_eps,
        str(CURRENT_YEAR + 4): y4_eps,
    }

    future_fper = {}

    for year, eps in future_eps.items():

        if (
            price is not None
            and eps is not None
            and eps > 0
        ):

            future_fper[year] = (
                price / eps
            )

        else:

            future_fper[year] = None

    # --------------------------------------------------------
    # EPS trajectory
    # --------------------------------------------------------

    eps_years = {}

    if previous_year is not None:
        eps_years[str(previous_year)] = previous_eps

    eps_years[str(CURRENT_YEAR)] = current_eps
    eps_years[str(CURRENT_YEAR + 1)] = y1_eps
    eps_years[str(CURRENT_YEAR + 2)] = y2_eps
    eps_years[str(CURRENT_YEAR + 3)] = y3_eps
    eps_years[str(CURRENT_YEAR + 4)] = y4_eps

    # --------------------------------------------------------
    # 성장률 trajectory
    # --------------------------------------------------------

    eps_growth = {
        str(CURRENT_YEAR): current_growth,
        str(CURRENT_YEAR + 1): y1_growth,
        str(CURRENT_YEAR + 2): y2_growth,
        str(CURRENT_YEAR + 3): y3_growth,
        str(CURRENT_YEAR + 4): y4_growth,
    }

    return {

        "rank": rank,

        "ticker": ticker,

        "company": yahoo["company"],

        "industry": yahoo["industry"],

        "market_cap": yahoo["market_cap"],

        "price": price,

        "forward_pe_yahoo": yahoo["forward_pe"],

        "previous_year": previous_year,

        "previous_eps": previous_eps,

        "current_year": CURRENT_YEAR,

        "current_eps": current_eps,

        "y1_eps": y1_eps,

        "y2_eps": y2_eps,

        "y3_eps": y3_eps,

        "y4_eps": y4_eps,

        "eps_years": eps_years,

        "eps_growth": eps_growth,

        "current_growth": current_growth,

        "y1_growth": y1_growth,

        "y2_growth": y2_growth,

        "y3_growth": y3_growth,

        "y4_growth": y4_growth,

        "cagr_4y": cagr_4y,

        "growth_trend": trend,

        "current_fper": current_fper,

        "future_fper": future_fper,

        "error": yahoo["error"],

    }


# ============================================================
# NASDAQ-100 → 시총 상위 40개
# ============================================================

def select_top_40():

    print("")
    print("=" * 70)
    print("NASDAQ-100 시가총액 조회")
    print("=" * 70)

    candidates = []

    for ticker in NASDAQ_100_TICKERS:

        yahoo = get_yahoo_data(ticker)

        market_cap = yahoo["market_cap"]

        if market_cap is not None:

            candidates.append({
                "ticker": ticker,
                "company": yahoo["company"],
                "market_cap": market_cap
            })

            print(
                f"{ticker:6s} "
                f"{market_cap:,.0f}"
            )

        else:

            print(
                f"{ticker:6s} "
                f"market cap 없음"
            )

        time.sleep(0.15)

    candidates.sort(
        key=lambda x: x["market_cap"],
        reverse=True
    )

    selected = candidates[:TOP_N]

    print("")
    print("=" * 70)
    print("NASDAQ-40")
    print("=" * 70)

    for rank, item in enumerate(
        selected,
        start=1
    ):

        print(
            f"{rank:2d}. "
            f"{item['ticker']:6s} "
            f"{item['company']} "
            f"{item['market_cap']:,.0f}"
        )

    return selected


# ============================================================
# MAIN
# ============================================================

def main():

    if not BQ_API_KEY:

        raise RuntimeError(
            "BUSINESSQUANT_API_KEY가 없습니다."
        )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    selected = select_top_40()

    stocks = []

    # BQ 429가 발생하면 더 이상 요청하지 않는다.
    rate_limited = False

    for rank, item in enumerate(
        selected,
        start=1
    ):

        ticker = item["ticker"]

        print("")
        print("=" * 70)
        print(
            f"[{rank}/{len(selected)}] {ticker}"
        )
        print("=" * 70)

        yahoo = get_yahoo_data(ticker)

        try:

            bq = get_businessquant_eps(
                ticker
            )

        except RuntimeError as e:

            if str(e) == "BQ_RATE_LIMIT":

                print("")
                print(
                    "Business Quant 일일 "
                    "API 한도에 도달했습니다."
                )
                print(
                    "이후 종목은 요청하지 않습니다."
                )

                rate_limited = True

                break

            raise

        stock = build_stock(
            rank,
            ticker,
            yahoo,
            bq
        )

        stocks.append(stock)

        print(
            f"{ticker} 완료"
        )

        # API 요청 사이 간격
        time.sleep(0.5)

    # --------------------------------------------------------
    # BQ 429로 중간 종료된 경우
    #
    # 기존 data.json을 덮어써서
    # 일부 종목만 있는 화면을 만들지 않는다.
    # --------------------------------------------------------

    if rate_limited:

        print("")
        print(
            "BQ rate limit 때문에 "
            "이번 실행에서는 data.json을 "
            "갱신하지 않습니다."
        )

        return

    # --------------------------------------------------------
    # 시총 순서
    # --------------------------------------------------------

    stocks.sort(
        key=lambda x: (
            x["market_cap"] is None,
            -(x["market_cap"] or 0)
        )
    )

    for rank, stock in enumerate(
        stocks,
        start=1
    ):

        stock["rank"] = rank

    # --------------------------------------------------------
    # data.json
    # --------------------------------------------------------

    output = {

        "site_name": "NASDAQ-40",

        "generated_at": generated_at,

        "generated_date_kst": datetime.now(
            timezone.utc
        ).astimezone().strftime(
            "%Y-%m-%d"
        ),

        "current_year": CURRENT_YEAR,

        "universe": "NASDAQ-100",

        "selected_size": len(stocks),

        "selection": (
            "NASDAQ-100 구성종목 중 "
            "시가총액 상위 40개"
        ),

        "sources": [
            "Yahoo Finance",
            "Business Quant"
        ],

        "notes": [

            "현재 FPER = 현재 주가 / 현재년도 EPS",

            "현재년도 EPS 성장률 = "
            "현재년도 EPS / 가장 최근 실제 EPS - 1",

            "미래 FPER = 현재 주가 / 해당 미래 EPS",

            "4Y CAGR = 현재년도 EPS에서 +4Y EPS까지의 CAGR",

            "미래 EPS가 없으면 임의 추정하지 않고 null 처리"

        ],

        "stocks": stocks

    }

    with open(
        "data.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print("=" * 70)
    print("NASDAQ-40 데이터 갱신 완료")
    print("=" * 70)
    print(
        f"종목 수: {len(stocks)}"
    )
    print(
        "data.json 저장 완료"
    )


if __name__ == "__main__":

    main()
