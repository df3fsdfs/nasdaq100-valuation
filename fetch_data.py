import json
import time
from datetime import datetime, timezone

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
        "as_of": datetime.now(timezone.utc).isoformat()
    }

    # 기본 정보
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
        result["info_error"] = str(e)[:200]


    # Yahoo Analyst Earnings Estimate
    #
    # Yahoo가 기본적으로 제공하는 연간 컨센서스:
    # 0y = Current Year
    # +1y = Next Year
    #
    # yfinance 공식 문서에서도 이 구조를 사용함.
    try:
        estimates = stock.get_earnings_estimate()

        if estimates is not None and not estimates.empty:

            if "0y" in estimates.index:
                result["current_eps"] = num(
                    estimates.loc["0y"].get("avg")
                )

            if "+1y" in estimates.index:
                result["y1_eps"] = num(
                    estimates.loc["+1y"].get("avg")
                )

    except Exception as e:
        result["estimate_error"] = str(e)[:200]


    # earningsTrend에는 Yahoo가 제공하는 추가 전망값이 있을 경우
    # 최대한 활용한다.
    #
    # 다만 Yahoo 데이터가 +2Y~+4Y를 항상 제공하는 것은 아니므로
    # 없는 값은 절대로 임의 계산하지 않는다.
    try:
        trend = stock.get_earnings_trend()

        if trend is not None and not trend.empty:

            for period in ["0y", "+1y", "+2y", "+3y", "+4y"]:

                if period not in trend.index:
                    continue

                row = trend.loc[period]

                eps = None

                # Yahoo 데이터 컬럼명에 따라 대응
                for column in [
                    "epsEstimateAvg",
                    "epsEstimate",
                    "avg"
                ]:
                    if column in row.index:
                        eps = num(row.get(column))
                        if eps is not None:
                            break

                if period == "0y":
                    result["current_eps"] = (
                        eps if eps is not None
                        else result["current_eps"]
                    )

                elif period == "+1y":
                    result["y1_eps"] = (
                        eps if eps is not None
                        else result["y1_eps"]
                    )

                elif period == "+2y":
                    result["y2_eps"] = eps

                elif period == "+3y":
                    result["y3_eps"] = eps

                elif period == "+4y":
                    result["y4_eps"] = eps

    except Exception as e:
        result["trend_error"] = str(e)[:200]


    # 현재가 유지 시 미래 FPER
    price = result["price"]

    if price is not None:

        for key in ["current_eps", "y1_eps", "y2_eps", "y3_eps", "y4_eps"]:

            eps = result[key]

            if eps is not None and eps > 0:
                result[key.replace("_eps", "_fper")] = price / eps
            else:
                result[key.replace("_eps", "_fper")] = None


    # EPS 성장률
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


    # 현재 EPS → +4Y EPS CAGR
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

    for i, ticker in enumerate(TICKERS, 1):

        print(f"[{i}/{len(TICKERS)}] {ticker}")

        try:

            row = get_stock(ticker)
            rows.append(row)

        except Exception as e:

            rows.append({
                "ticker": ticker,
                "company": ticker,
                "source": "Yahoo Finance",
                "error": str(e)[:200],
                "as_of": datetime.now(timezone.utc).isoformat()
            })

        # Yahoo 요청 간격
        time.sleep(0.5)


    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),

        "source": "Yahoo Finance",

        "count": len(rows),

        "notes": [
            "Missing estimates are kept as null.",
            "No EPS values are extrapolated.",
            "Future FPER means current price divided by future EPS estimate.",
            "GOOG and GOOGL are both included."
        ],

        "stocks": rows
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
