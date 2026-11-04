"""data_kr/*.csv.gz 의 수정주가 여부 점검 (출력만).
- 005930 2018-04-25 ~ 2018-05-10 구간 출력 (50:1 액면분할, 2018-05-04 재상장)
- 모든 코드: 하루 종가대비 |변화| > 35% 목록
- Open<=0 / 거래량 0 행 목록 (거래정지일 표기 방식 확인)
실행: python -I check_kr_adjust.py <data_kr>
"""
import json
import sys
from pathlib import Path

import pandas as pd

d = Path(sys.argv[1])
info = json.loads((d / "universe.json").read_text(encoding="utf-8"))

s = pd.read_csv(d / "005930.csv.gz", index_col=0, parse_dates=True)
print("=== 005930 around split ===")
print(s.loc["2018-04-25":"2018-05-10"].to_string())
print("\n=== 005930 first rows ===")
print(s.head(3).to_string())

print("\n=== jumps > 35% ===")
for code in info["종목"]:
    df = pd.read_csv(d / f"{code}.csv.gz", index_col=0, parse_dates=True)
    c = df["Close"]
    r = c / c.shift(1) - 1
    big = r[r.abs() > 0.35]
    for dt, v in big.items():
        i = df.index.get_loc(dt)
        print(code, info["종목"][code]["이름"], dt.date(), "prev", c.iloc[i - 1], "close", c.iloc[i], f"{v:+.1%}")
    # 참고: 30% 초과 35% 이하
    mid = r[(r.abs() > 0.30) & (r.abs() <= 0.35)]
    for dt, v in mid.items():
        i = df.index.get_loc(dt)
        print("  (30~35%)", code, dt.date(), c.iloc[i - 1], c.iloc[i], f"{v:+.1%}")

print("\n=== Open<=0 or Volume==0 rows (summary) ===")
for code in info["종목"]:
    df = pd.read_csv(d / f"{code}.csv.gz", index_col=0, parse_dates=True)
    bad = df[(df["Open"] <= 0) | (df["Volume"] == 0)]
    if len(bad):
        z = bad[bad["Open"] <= 0]
        print(code, info["종목"][code]["이름"], "rows", len(bad), "Open<=0:", len(z),
              "dates", bad.index.min().date(), "~", bad.index.max().date())
        print(bad.head(2).to_string(header=False))
