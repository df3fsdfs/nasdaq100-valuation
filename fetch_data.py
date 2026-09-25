import json
import os
import re
import time
from datetime import datetime, timezone

import requests
import yfinance as yf


# NASDAQ-100 구성종목
# GOOG / GOOGL은 Alphabet의 두 상장종목이라 둘 다 포함
TICKERS = """
AAPL AMD AMAT AMGN AMZN ARM ASML AVGO AXON BKNG BKR CCEP CDNS CDW CEG CHTR
CMCSA COST CPRT CRWD CSCO CTSH DASH DDOG DXCM EA EXC FANG FAST FTNT GEHC GILD
GOOG GOOGL HON IDXX INTC INTU ISRG KDP KHC KLAC LIN LRCX LULU MAR MCHP MDLZ
MELI META MNST MRNA MRVL MSFT MU NFLX NVDA NDAQ NXPI ODFL ON ORLY PANW PAYX
PCAR PDD PEP PLTR PYPL QCOM REGN ROST SBUX SHOP SNPS TMUS TSLA TTWO TXN
VRSK VRTX WBA WBD WDAY WDC WMT XEL ZS
""".split()


BQ_API_KEY = os.environ.get("BUSINESSQUANT_API_KEY")


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


def get_businessquant_eps(ticker):
    """
    Business Quant Analyst Estimates API에서
    연간 EPS 컨센서스를 가져온다.

    현재 연도부터 최대 +4년까지 사용한다.
    없는 값은 절대로 임의 계산하지 않는다.
    """

    result = {
        "current_eps": None,
        "y1_eps": None,
        "y2_eps": None,
        "y3_eps": None,
        "y4_eps": None,
        "eps_source": "Business Quant"
    }

    if not BQ_API_KEY:
        result["eps_error"] = "BUSINESSQUANT_API_KEY is missing"
        return result

    url = "https://data.businessquant.com/estimates"

    params = {
        "ticker": ticker,
        "mode": "eps",
        "api_key": BQ_API_KEY
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        rows = payload.get("data", [])

        if not isinstance(rows, list):
            result["eps_error"] = "Unexpected API data format"
            return result

        current_year = datetime.now(timezone.utc).year

        estimates = {}

        for row in rows:

            period = str(row.get("period", "")).strip()
            data_type = str(row.get("data_type", "")).lower()

            # 연간 데이터만 사용
            if not re.fullmatch(r"\d{4}", period):
                continue

            # 컨센서스 전망치만 사용
            if data_type != "estimate":
                continue

            year = int(period)

            value = num(row.get("value_estimate"))

            if value is None:
                continue

            estimates[year] = value

        # 현재 연도부터 +4년
        targets = [
            current_year,
            current_year + 1,
            current_year + 2,
            current_year + 3,
            current_year + 4
        ]

        keys = [
            "current_eps",
            "y1_eps",
            "y2_eps",
            "y3_eps",
            "y4_eps"
        ]

        # 가장 가까운 전망연도를 사용
        # 현재 연도 전망이 없고 이미 지나간 경우,
        # 다음 전망연도를 현재 EPS로 간주하지 않는다.
        for key, year in zip(keys, targets):
            result[key] = estimates.get(year)

        result["eps_years"] = {
            "current": targets[0],
            "y1": targets[1],
            "y2": targets[2],
            "y3": targets[3],
            "y4": targets[4]
        }

    except Exception as e:
        result["eps_error"] = str(e)[:300]

    return result


def get_stock(ticker):

    stock = yf.Ticker(ticker)

    result = {
        "ticker": ticker,
        "company": ticker,
        "industry": None,

        "price": None,
        "fper": None,

        "trailing_eps": None,
        "forward_eps": None,

        "current_eps": None,
        "y1_eps": None,
        "y2_eps": None,
        "y3_eps": None,
        "y4_eps": None,

        "source": "Yahoo Finance",
        "eps_source": "Business Quant",

        "as_of": datetime.now(timezone.utc).isoformat()
    }


    # ---------------------------------
    # Yahoo Finance
    # ---------------------------------

    try:

        info = stock.info or {}

        result["company"] = (
            info.get("longName")
            or info.get("shortName")
            or ticker
        )

        result["industry"] = (
            info.get("industry")
            or info.get("industryKey")
        )

        result["price"] = num(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
        )

        result["fper"] = num(
            info.get("forwardPE")
        )

        result["trailing_eps"] = num(
            info.get("trailingEps")
        )

        result["forward_eps"] = num(
            info.get("forwardEps")
        )

    except Exception as e:

        result["info_error"] = str(e)[:300]


    # ---------------------------------
    # Business Quant EPS estimates
    # ---------------------------------

    bq = get_businessquant_eps(ticker)

    for key in [
        "current_eps",
        "y1_eps",
        "y2_eps",
        "y3_eps",
        "y4_eps"
    ]:

        result[key] = bq.get(key)

    if "eps_years" in bq:
        result["eps_years"] = bq["eps_years"]

    if "eps_error" in bq:
        result["eps_error"] = bq["eps_error"]


    # ---------------------------------
    # 현재가 유지 시 미래 FPER
    # ---------------------------------

    price = result["price"]

    if price is not None:

        for key in [
            "current_eps",
            "y1_eps",
            "y2_eps",
            "y3_eps",
            "y4_eps"
        ]:

            eps = result[key]

            if eps is not None and eps > 0:

                result[key.replace(
                    "_eps",
                    "_fper"
                )] = price / eps

            else:

                result[key.replace(
                    "_eps",
                    "_fper"
                )] = None


    # ---------------------------------
    # EPS 성장률
    # ---------------------------------

    eps_list = [
        result["trailing_eps"],
        result["current_eps"],
        result["y1_eps"],
        result["y2_eps"],
        result["y3_eps"],
        result["y4_eps"]
    ]

    growth = []

    for i in range(1, len(eps_list)):

        previous = eps_list[i - 1]
        current = eps_list[i]

        if (
            previous is not None
            and current is not None
            and previous != 0
        ):

            growth.append(
                (current / previous) - 1
            )

        else:

            growth.append(None)

    result["growth"] = growth


    # ---------------------------------
    # 현재 EPS → +4Y EPS CAGR
    # ---------------------------------

    start = result["current_eps"]
    end = result["y4_eps"]

    if (
        start is not None
        and end is not None
        and start > 0
        and end > 0
    ):

        result["eps_cagr_4y"] = (
            (end / start) ** (1 / 4)
        ) - 1

    else:

        result["eps_cagr_4y"] = None


    return result


def main():

    rows = []

    print("NASDAQ-100 data collection started")

    print(
        f"Business Quant API key: "
        f"{'FOUND' if BQ_API_KEY else 'MISSING'}"
    )

    print()


    for i, ticker in enumerate(TICKERS, 1):

        print(
            f"[{i}/{len(TICKERS)}] {ticker}"
        )

        try:

            row = get_stock(ticker)

            rows.append(row)

        except Exception as e:

            rows.append({
                "ticker": ticker,
                "company": ticker,
                "source": "Yahoo Finance",
                "eps_source": "Business Quant",
                "error": str(e)[:300],
                "as_of": datetime.now(
                    timezone.utc
                ).isoformat()
            })

        # API 요청 간격
        time.sleep(0.5)


    data = {

        "generated_at":
            datetime.now(timezone.utc).isoformat(),

        "source":
            "Yahoo Finance + Business Quant",

        "count":
            len(rows),

        "notes": [

            "Yahoo Finance provides price, Forward PE and trailing EPS.",

            "Business Quant provides annual EPS consensus estimates.",

            "Missing estimates are kept as null.",

            "No EPS values are extrapolated.",

            "Future FPER means current price divided by future EPS estimate.",

            "GOOG and GOOGL are both included."

        ],

        "stocks":
            rows
    }


    with open(
        "data.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


    print()
    print("================================")
    print("Finished")
    print(f"Stocks: {len(rows)}")
    print("Output: data.json")
    print("================================")


if __name__ == "__main__":
    main()
