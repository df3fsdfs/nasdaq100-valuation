import json
import os
import re
import time
from datetime import datetime, timezone

import requests
import yfinance as yf


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
    Business Quant Analyst Estimates API
    연간 EPS 컨센서스 조회
    """

    if not BQ_API_KEY:
        return {}

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

        data = payload.get("data", [])

        if not isinstance(data, list):
            return {}

        annual = {}

        for section in data:

            if section.get("dimension") != "annual":
                continue

            estimates = section.get("estimates", [])

            if not isinstance(estimates, list):
                continue

            for row in estimates:

                period = str(
                    row.get("period", "")
                ).strip()

                if not re.fullmatch(
                    r"\d{4}",
                    period
                ):
                    continue

                if row.get("data_type") != "estimate":
                    continue

                value = num(
                    row.get("value_estimate")
                )

                if value is None:
                    continue

                year = int(period)

                annual[year] = value

        return annual

    except Exception as e:

        print(
            f"Business Quant error: "
            f"{ticker} - {str(e)[:200]}"
        )

        return {}


def get_stock(ticker):

    stock = yf.Ticker(ticker)

    result = {
        "ticker": ticker,
        "company": ticker,
        "industry": None,

        "price": None,
        "fper": None,

        "trailing_eps": None,

        "current_eps": None,
        "y1_eps": None,
        "y2_eps": None,
        "y3_eps": None,
        "y4_eps": None,

        "current_fper": None,
        "y1_fper": None,
        "y2_fper": None,
        "y3_fper": None,
        "y4_fper": None,

        "growth": [],

        "eps_cagr_4y": None,

        "source": "Yahoo Finance + Business Quant",

        "as_of": datetime.now(timezone.utc).isoformat()
    }


    # ==========================================
    # Yahoo Finance
    # ==========================================

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

    except Exception as e:

        result["info_error"] = str(e)[:200]


    # ==========================================
    # Business Quant
    # ==========================================

    annual_eps = get_businessquant_eps(ticker)

    if annual_eps:

        current_year = datetime.now(timezone.utc).year

        future_years = sorted(
            year
            for year in annual_eps
            if year >= current_year
        )

        if future_years:

            base_year = future_years[0]

            year_map = {
                "current_eps": base_year,
                "y1_eps": base_year + 1,
                "y2_eps": base_year + 2,
                "y3_eps": base_year + 3,
                "y4_eps": base_year + 4
            }

            for key, year in year_map.items():

                result[key] = annual_eps.get(year)

            result["eps_years"] = {
                key: year
                for key, year in year_map.items()
                if result[key] is not None
            }

            result["eps_source"] = "Business Quant"


    # ==========================================
    # Yahoo 현재/+1Y 보완
    # ==========================================

    try:

        estimates = stock.get_earnings_estimate()

        if estimates is not None and not estimates.empty:

            if result["current_eps"] is None:

                if "0y" in estimates.index:

                    result["current_eps"] = num(
                        estimates.loc["0y"].get("avg")
                    )

            if result["y1_eps"] is None:

                if "+1y" in estimates.index:

                    result["y1_eps"] = num(
                        estimates.loc["+1y"].get("avg")
                    )

    except Exception as e:

        result["estimate_error"] = str(e)[:200]


    # ==========================================
    # 현재가 유지 시 미래 FPER
    # ==========================================

    price = result["price"]

    eps_keys = [
        "current_eps",
        "y1_eps",
        "y2_eps",
        "y3_eps",
        "y4_eps"
    ]

    for key in eps_keys:

        eps = result[key]

        if (
            price is not None
            and eps is not None
            and eps > 0
        ):

            fper_key = key.replace(
                "_eps",
                "_fper"
            )

            result[fper_key] = price / eps


    # ==========================================
    # EPS 성장률
    # trailing
    # → current
    # → +1Y
    # → +2Y
    # → +3Y
    # → +4Y
    # ==========================================

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


    # ==========================================
    # 현재 EPS → +4Y EPS CAGR
    # ==========================================

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


    return result


def main():

    rows = []

    print("NASDAQ-100 data collection started")

    print(
        "Business Quant API:",
        "CONNECTED" if BQ_API_KEY else "MISSING"
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
                "source": "Yahoo Finance + Business Quant",
                "error": str(e)[:200],
                "as_of": datetime.now(
                    timezone.utc
                ).isoformat()
            })

        time.sleep(0.5)


    data = {

        "generated_at":
            datetime.now(timezone.utc).isoformat(),

        "source":
            "Yahoo Finance + Business Quant",

        "count":
            len(rows),

        "notes": [

            "Missing estimates are kept as null.",

            "No EPS values are extrapolated.",

            "Future FPER means current price divided by future EPS estimate.",

            "Business Quant provides annual EPS consensus estimates.",

            "Yahoo Finance provides price, forward PE and trailing EPS.",

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
