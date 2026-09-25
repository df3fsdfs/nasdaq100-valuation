import json
import os
import re
import time
from datetime import datetime, timezone

import requests
import yfinance as yf


# ============================================================
# 설정
# ============================================================

BQ_API_KEY = os.environ.get("BUSINESSQUANT_API_KEY")

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

TOP_N = 40

BQ_URL = "https://data.businessquant.com/estimates"


# ============================================================
# 숫자 처리
# ============================================================

def num(value):
    try:
        if value is None:
            return None

        value = float(value)

        if value != value:
            return None

        return value

    except Exception:
        return None


# ============================================================
# Business Quant EPS
# ============================================================

def get_businessquant_eps(ticker):

    if not BQ_API_KEY:
        print("BUSINESSQUANT_API_KEY가 없습니다.")
        return {}

    try:

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

        response.raise_for_status()

        payload = response.json()

        annual_eps = {}

        # ----------------------------------------------------
        # 공식 응답 구조:
        #
        # data
        #   └─ dimension: annual
        #        └─ estimates
        #             ├─ period
        #             ├─ data_type
        #             └─ value_estimate
        #
        # 구조가 조금 달라져도 대응할 수 있도록
        # 재귀적으로 annual estimates를 탐색한다.
        # ----------------------------------------------------

        data = payload.get("data", [])

        def scan(obj, annual_context=False):

            if isinstance(obj, dict):

                current_annual_context = annual_context

                if obj.get("dimension") == "annual":
                    current_annual_context = True

                period = obj.get("period")
                data_type = obj.get("data_type")
                value_estimate = obj.get("value_estimate")

                if (
                    current_annual_context
                    and isinstance(period, str)
                    and re.fullmatch(r"\d{4}", period)
                    and data_type == "estimate"
                ):
                    value = num(value_estimate)

                    if value is not None:
                        annual_eps[int(period)] = value

                for value in obj.values():
                    scan(value, current_annual_context)

            elif isinstance(obj, list):

                for item in obj:
                    scan(item, annual_context)

        scan(data)

        print(
            f"{ticker} Business Quant annual EPS: "
            f"{dict(sorted(annual_eps.items()))}"
        )

        return dict(sorted(annual_eps.items()))

    except requests.HTTPError as e:

        print(
            f"{ticker} Business Quant HTTP error: "
            f"{e}"
        )

        try:
            print(
                "Response:",
                response.text[:500]
            )
        except Exception:
            pass

        return {}

    except Exception as e:

        print(
            f"{ticker} Business Quant error: "
            f"{type(e).__name__}: {e}"
        )

        return {}


# ============================================================
# Yahoo Finance
# ============================================================

def get_yahoo_data(ticker):

    result = {
        "company": None,
        "industry": None,
        "market_cap": None,
        "price": None,
        "forward_pe": None,
        "trailing_eps": None,
        "yahoo_current_eps": None,
        "yahoo_next_eps": None,
        "error": None,
    }

    try:

        stock = yf.Ticker(ticker)

        info = stock.info

        result["company"] = (
            info.get("longName")
            or info.get("shortName")
        )

        result["industry"] = info.get("industry")

        result["market_cap"] = num(
            info.get("marketCap")
        )

        result["price"] = num(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
        )

        result["forward_pe"] = num(
            info.get("forwardPE")
        )

        result["trailing_eps"] = num(
            info.get("trailingEps")
        )

        # ----------------------------------------------------
        # Yahoo earnings estimate fallback
        # ----------------------------------------------------

        try:

            estimate = stock.get_earnings_estimate()

            if estimate is not None:

                if "0y" in estimate.index:

                    result["yahoo_current_eps"] = num(
                        estimate.loc["0y", "avg"]
                    )

                if "+1y" in estimate.index:

                    result["yahoo_next_eps"] = num(
                        estimate.loc["+1y", "avg"]
                    )

        except Exception as e:

            print(
                f"{ticker} Yahoo earnings estimate error: {e}"
            )

    except Exception as e:

        result["error"] = str(e)

        print(
            f"{ticker} Yahoo error: "
            f"{type(e).__name__}: {e}"
        )

    return result


# ============================================================
# EPS 성장률
# ============================================================

def calculate_growth(eps_years):

    growth = {}

    years = sorted(eps_years.keys())

    for i in range(1, len(years)):

        previous_year = years[i - 1]
        current_year = years[i]

        previous = eps_years[previous_year]
        current = eps_years[current_year]

        if (
            previous is not None
            and current is not None
            and previous != 0
        ):

            growth[current_year] = (
                (current / previous) - 1
            ) * 100

        else:

            growth[current_year] = None

    return growth


# ============================================================
# CAGR
# ============================================================

def calculate_cagr(start_eps, end_eps, years):

    if (
        start_eps is None
        or end_eps is None
        or years <= 0
        or start_eps <= 0
        or end_eps <= 0
    ):
        return None

    try:

        return (
            (end_eps / start_eps)
            ** (1 / years)
            - 1
        ) * 100

    except Exception:

        return None


# ============================================================
# 성장 추세
# ============================================================

def calculate_growth_trend(growth):

    values = [
        value
        for _, value in sorted(growth.items())
        if value is not None
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
# 종목 데이터
# ============================================================

def get_stock(ticker):

    print("")
    print("=" * 60)
    print(f"Processing {ticker}")
    print("=" * 60)

    yahoo = get_yahoo_data(ticker)

    # --------------------------------------------------------
    # Business Quant
    # --------------------------------------------------------

    bq_eps = get_businessquant_eps(ticker)

    # API 제한을 고려해 종목당 한 번만 호출
    time.sleep(0.5)

    current_year = datetime.now(timezone.utc).year

    # --------------------------------------------------------
    # 미래 EPS
    # --------------------------------------------------------

    future_eps = {
        year: value
        for year, value in bq_eps.items()
        if year >= current_year
    }

    future_years = sorted(future_eps.keys())

    # 현재연도부터 최대 5개 연도
    selected_years = future_years[:5]

    eps_years = {}

    for year in selected_years:
        eps_years[year] = future_eps[year]

    # --------------------------------------------------------
    # Yahoo fallback
    #
    # Business Quant에서 현재연도 / 다음연도가 없는 경우
    # Yahoo 추정치를 사용한다.
    # --------------------------------------------------------

    if current_year not in eps_years:

        if yahoo["yahoo_current_eps"] is not None:

            eps_years[current_year] = (
                yahoo["yahoo_current_eps"]
            )

    if current_year + 1 not in eps_years:

        if yahoo["yahoo_next_eps"] is not None:

            eps_years[current_year + 1] = (
                yahoo["yahoo_next_eps"]
            )

    eps_years = dict(
        sorted(eps_years.items())
    )

    # --------------------------------------------------------
    # 현재 EPS
    # --------------------------------------------------------

    current_eps = eps_years.get(current_year)

    y1_eps = eps_years.get(current_year + 1)
    y2_eps = eps_years.get(current_year + 2)
    y3_eps = eps_years.get(current_year + 3)
    y4_eps = eps_years.get(current_year + 4)

    # --------------------------------------------------------
    # EPS 성장률
    # --------------------------------------------------------

    growth = calculate_growth(eps_years)

    current_growth = growth.get(
        current_year + 1
    )

    # --------------------------------------------------------
    # 4년 CAGR
    # --------------------------------------------------------

    cagr_4y = calculate_cagr(
        current_eps,
        y4_eps,
        4
    )

    # --------------------------------------------------------
    # 현재가 유지 시 미래 FPER
    # --------------------------------------------------------

    price = yahoo["price"]

    future_fper = {}

    for year, eps in eps_years.items():

        if (
            price is not None
            and eps is not None
            and eps > 0
        ):

            future_fper[str(year)] = (
                price / eps
            )

        else:

            future_fper[str(year)] = None

    # --------------------------------------------------------
    # 성장 추세
    # --------------------------------------------------------

    growth_trend = calculate_growth_trend(
        growth
    )

    # --------------------------------------------------------
    # 최종 결과
    # --------------------------------------------------------

    return {

        "ticker": ticker,

        "company": yahoo["company"],

        "industry": yahoo["industry"],

        "market_cap": yahoo["market_cap"],

        "price": price,

        "forward_pe": yahoo["forward_pe"],

        "trailing_eps": yahoo["trailing_eps"],

        "current_eps": current_eps,

        "y1_eps": y1_eps,

        "y2_eps": y2_eps,

        "y3_eps": y3_eps,

        "y4_eps": y4_eps,

        "eps_years": {
            str(year): value
            for year, value in eps_years.items()
        },

        "eps_growth": {
            str(year): value
            for year, value in growth.items()
        },

        "current_growth": current_growth,

        "cagr_4y": cagr_4y,

        "growth_trend": growth_trend,

        "future_fper": future_fper,

        "sources": [
            "Yahoo Finance",
            "Business Quant"
        ],

        "error": yahoo["error"],

    }


# ============================================================
# NASDAQ-100 → 시총 상위 40개 선정
# ============================================================

def get_top_40():

    print("")
    print("=" * 60)
    print("NASDAQ-100 시가총액 조회")
    print("=" * 60)

    market_caps = []

    for ticker in NASDAQ_100_TICKERS:

        try:

            stock = yf.Ticker(ticker)

            info = stock.info

            market_cap = num(
                info.get("marketCap")
            )

            company = (
                info.get("longName")
                or info.get("shortName")
            )

            if market_cap is not None:

                market_caps.append(
                    {
                        "ticker": ticker,
                        "company": company,
                        "market_cap": market_cap,
                    }
                )

                print(
                    f"{ticker}: "
                    f"{market_cap:,.0f}"
                )

            else:

                print(
                    f"{ticker}: market cap 없음"
                )

        except Exception as e:

            print(
                f"{ticker}: "
                f"market cap error - {e}"
            )

        time.sleep(0.2)

    # --------------------------------------------------------
    # 시총 내림차순
    # --------------------------------------------------------

    market_caps.sort(
        key=lambda x: x["market_cap"],
        reverse=True
    )

    top_40 = market_caps[:TOP_N]

    print("")
    print("=" * 60)
    print("NASDAQ-40 선정 결과")
    print("=" * 60)

    for rank, item in enumerate(
        top_40,
        start=1
    ):

        print(
            f"{rank:2d}. "
            f"{item['ticker']:6s} "
            f"{item['market_cap']:,.0f}"
        )

    return top_40


# ============================================================
# 메인
# ============================================================

def main():

    if not BQ_API_KEY:

        raise RuntimeError(
            "BUSINESSQUANT_API_KEY 환경변수가 없습니다."
        )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    # --------------------------------------------------------
    # 1. NASDAQ-100 중 시총 상위 40개 자동 선정
    # --------------------------------------------------------

    top_40 = get_top_40()

    stocks = []

    # --------------------------------------------------------
    # 2. 상위 40개만 Business Quant EPS 조회
    # --------------------------------------------------------

    for rank, item in enumerate(
        top_40,
        start=1
    ):

        ticker = item["ticker"]

        data = get_stock(ticker)

        data["market_cap_rank"] = rank

        stocks.append(data)

        print("")
        print(
            f"[{rank}/{len(top_40)}] "
            f"{ticker} 완료"
        )

    # --------------------------------------------------------
    # 3. 다시 시총 순으로 정렬
    # --------------------------------------------------------

    stocks.sort(
        key=lambda x: (
            x["market_cap"] is None,
            -(x["market_cap"] or 0)
        )
    )

    # --------------------------------------------------------
    # 4. 순위 재부여
    # --------------------------------------------------------

    for rank, stock in enumerate(
        stocks,
        start=1
    ):

        stock["market_cap_rank"] = rank

    # --------------------------------------------------------
    # 5. data.json 저장
    # --------------------------------------------------------

    output = {

        "site_name": "NASDAQ-40",

        "description": (
            "NASDAQ-100 구성종목 중 "
            "시가총액 상위 40개 종목의 "
            "EPS 성장 및 Forward Valuation"
        ),

        "generated_at": generated_at,

        "universe": "NASDAQ-100",

        "universe_size": len(
            NASDAQ_100_TICKERS
        ),

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

            "시가총액 순위는 Yahoo Finance marketCap 기준",

            "Business Quant EPS는 consensus mean estimate",

            "미래 EPS가 제공되지 않는 경우 "
            "임의로 추정하지 않고 null 처리",

            "현재가 유지 시 미래 FPER = "
            "현재 주가 / 해당 연도 EPS",

            "4Y CAGR은 현재연도 EPS와 "
            "+4Y EPS가 모두 존재할 때만 계산",

            "GOOG와 GOOGL은 현재 NASDAQ-100 "
            "구성 티커 목록에서 각각 별도 종목으로 처리"

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
    print("=" * 60)
    print("완료")
    print("=" * 60)
    print(
        f"NASDAQ-40 종목 수: {len(stocks)}"
    )
    print(
        "data.json 저장 완료"
    )


if __name__ == "__main__":
    main()
