"""069500 naver Close 와 yahoo Close 의 비율이 언제 계단식으로 바뀌는지 (분배금 반영 여부) + 005930 불일치일 (출력만)."""
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

d = Path(sys.argv[1])


def yget(t):
    y = yf.download(t, start="2014-08-01", end="2026-11-04", auto_adjust=False, progress=False)
    y.columns = [c[0] if isinstance(c, tuple) else c for c in y.columns]
    return y


df = pd.read_csv(d / "069500.csv.gz", index_col=0, parse_dates=True)
y = yget("069500.KS")
j = pd.DataFrame({"naver": df["Close"], "yclose": y["Close"], "yadj": y["Adj Close"]}).dropna()
j["ratio"] = (j["naver"] / j["yclose"]).round(4)
chg = j[j["ratio"].diff().abs() > 0.002]
print("069500 ratio steps (naver/yahooClose), first 40:")
print(chg.head(40).to_string())
print("... total steps", len(chg))
print(j.tail(3).to_string())
# 분배락 전후 naver 가 실제 종가와 같은지 — 최근 구간
print("\nratio==1 since:", j[j["ratio"] == 1.0].index.min())

s = pd.read_csv(d / "005930.csv.gz", index_col=0, parse_dates=True)
y5 = yget("005930.KS")
k = pd.DataFrame({"naver": s["Close"], "yclose": y5["Close"], "vol_n": s["Volume"], "vol_y": y5["Volume"]}).dropna()
mm = k[(k["naver"] - k["yclose"]).abs() > 0.5]
print("\n005930 mismatches", len(mm))
print(mm.head(10).to_string())
print(mm.tail(10).to_string())
