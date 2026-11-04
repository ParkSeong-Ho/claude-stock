"""fja05680/sp500 의 PIT 파일에서 2015-01-02 시점 S&P500 구성 종목을 뽑는다.
(sp500_by_date.ipynb 방식: 해당 날짜 이하의 마지막 행)
실행: python -I sp500_snapshot.py <sp500_repo_dir> <out_dir> [date]
"""
import json
import sys
from pathlib import Path

import pandas as pd

repo = Path(sys.argv[1])
out = Path(sys.argv[2])
date = sys.argv[3] if len(sys.argv) > 3 else "2015-01-02"
df = pd.read_csv(repo / "S&P 500 Historical Components & Changes (Updated).csv", parse_dates=["date"])
df = df.sort_values("date")
row = df[df["date"] <= date].iloc[-1]
tickers = sorted(row["tickers"].split(","))
print("snapshot row date:", row["date"].date(), "n =", len(tickers))
nxt = df[df["date"] > date].iloc[0]
print("next row date:", nxt["date"].date(), "n =", len(nxt["tickers"].split(",")))
print("first row:", df["date"].iloc[0].date(), " last row:", df["date"].iloc[-1].date())
(out / f"sp500_members_{date}.txt").write_text("\n".join(tickers) + "\n", encoding="utf-8")
(out / f"sp500_members_{date}.json").write_text(json.dumps(
    {"source": "github.com/fja05680/sp500 'S&P 500 Historical Components & Changes (Updated).csv'",
     "snapshot_row_date": str(row["date"].date()), "count": len(tickers), "tickers": tickers},
    indent=1), encoding="utf-8")
want = ["AAPL", "XOM", "MSFT", "BRK.B", "BRK-B", "GOOG", "GOOGL", "JNJ", "WFC", "GE", "WMT", "JPM", "PG", "CVX",
        "VZ", "FB", "META", "PFE", "ORCL", "KO", "T", "BAC", "IBM", "GILD", "MRK", "AMZN", "DIS", "C", "INTC", "CMCSA",
        "PEP", "V", "MA", "CSCO", "QCOM", "SLB", "HD", "UNH", "AGN", "ACT", "AMGN", "ABBV", "MO", "PM", "MDT", "BUD",
        "NVS", "CVS", "BA", "UTX", "MMM", "HPQ", "SPY", "COST", "NVDA", "LLY"]
print("in snapshot?", {w: (w in tickers) for w in want})
