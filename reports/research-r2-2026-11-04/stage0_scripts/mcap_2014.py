"""2014-12-31 종가 기준 시가총액 직접 계산 (후보 약 48개).
시가총액 = 주식 수(SEC XBRL) × 2014-12-31 실제 종가(야후 분할조정 종가 × 그 뒤 분할비율 곱 → 분할 전 원래 가격)
- 주식 수 방법 'dei': 10-K/10-Q 표지의 EntityCommonStockSharesOutstanding 중 기준일이 2014-12-31 에 가장 가까운 값
- 방법 'wavg': (다중 클래스라 표지값이 API 에 없음) us-gaap WeightedAverageNumberOfSharesOutstandingBasic
  2014-10-01~2014-12-31 3개월 값, 없으면 4×연간−3×9개월로 4분기 평균 추정
- Visa 는 둘 다 없음 → (미확인)
실행: python -I mcap_2014.py <data_us_pit>
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

d = Path(sys.argv[1])
sec = d / "sec"
UA = {"User-Agent": "research-r2 data-check admin@example.com"}
REF = date(2014, 12, 31)
snap = set(json.loads((d / "sp500_members_2015-01-02.json").read_text())["tickers"])

# (2014 S&P 티커, 가격용 야후 티커, 2014 당시 CIK, 방법)
C = [("AAPL", "AAPL", 320193, "dei"), ("XOM", "XOM", 34088, "dei"), ("MSFT", "MSFT", 789019, "dei"),
     ("JNJ", "JNJ", 200406, "dei"), ("GOOGL", "GOOGL", 1288776, "wavg"), ("WFC", "WFC", 72971, "dei"),
     ("GE", "GE", 40545, "dei"), ("CVX", "CVX", 93410, "dei"), ("PG", "PG", 80424, "dei"),
     ("BRK.B", "BRK-A", 1067983, "wavg"), ("JPM", "JPM", 19617, "dei"), ("VZ", "VZ", 732712, "dei"),
     ("PFE", "PFE", 78003, "dei"), ("KO", "KO", 21344, "dei"), ("T", "T", 732717, "dei"),
     ("IBM", "IBM", 51143, "dei"), ("MRK", "MRK", 310158, "dei"), ("BAC", "BAC", 70858, "dei"),
     ("INTC", "INTC", 50863, "dei"), ("SLB", "SLB", 87347, "dei"), ("CSCO", "CSCO", 858877, "dei"),
     ("FB", "META", 1326801, "wavg"), ("C", "C", 831001, "dei"), ("DIS", "DIS", 1001039, "dei"),
     ("ORCL", "ORCL", 1341439, "dei"), ("QCOM", "QCOM", 804328, "dei"), ("PM", "PM", 1413329, "dei"),
     ("PEP", "PEP", 77476, "dei"), ("AMZN", "AMZN", 1018724, "dei"), ("WMT", "WMT", 104169, "dei"),
     ("V", "V", 1403161, "none"), ("HD", "HD", 354950, "dei"), ("UTX", "RTX", 101829, "dei"),
     ("COP", "COP", 1163165, "dei"), ("MMM", "MMM", 66740, "dei"), ("GILD", "GILD", 882095, "dei"),
     ("AXP", "AXP", 4962, "dei"), ("MCD", "MCD", 63908, "dei"), ("BA", "BA", 12927, "dei"),
     ("AMGN", "AMGN", 318154, "dei"), ("UNP", "UNP", 100885, "dei"), ("ABBV", "ABBV", 1551152, "dei"),
     ("CVS", "CVS", 64803, "dei"), ("MO", "MO", 764180, "dei"), ("MA", "MA", 1141391, "wavg"),
     ("BMY", "BMY", 14272, "dei"), ("CMCSA", "CMCSA", 1166691, "wavg"), ("UNH", "UNH", 731766, "dei")]


def get_json(url, path):
    if path.exists():
        return json.loads(path.read_text())
    r = requests.get(url, headers=UA, timeout=60)
    time.sleep(0.25)
    if r.status_code != 200:
        return None
    path.write_text(r.text)
    return r.json()


def shares_dei(cik):
    j = get_json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/dei/EntityCommonStockSharesOutstanding.json",
                 sec / "concept" / f"dei_shares_{cik:010d}.json")
    if not j:
        return None
    best = None
    for xs in j["units"].values():
        for x in xs:
            e = date.fromisoformat(x["end"])
            gap = abs((e - REF).days)
            if gap <= 100 and (best is None or gap < best[0]):
                best = (gap, x["val"], x["end"], x["form"])
    return best


def shares_wavg(cik):
    j = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", sec / "facts" / f"CIK{cik:010d}.json")
    xs = j["facts"]["us-gaap"]["WeightedAverageNumberOfSharesOutstandingBasic"]["units"]["shares"]
    q4 = [x for x in xs if x.get("start") == "2014-10-01" and x["end"] == "2014-12-31"]
    if q4:
        return (0, q4[0]["val"], "2014Q4 3개월 평균", q4[0]["form"])
    fy = [x for x in xs if x.get("start") == "2014-01-01" and x["end"] == "2014-12-31"]
    m9 = [x for x in xs if x.get("start") == "2014-01-01" and x["end"] == "2014-09-30"]
    if fy and m9:
        return (0, 4 * fy[0]["val"] - 3 * m9[0]["val"], "4×연간−3×9개월 추정", fy[0]["form"])
    return None


def raw_close(t):
    tk = yf.Ticker(t)
    h = tk.history(start="2014-12-24", end="2015-01-06", auto_adjust=False, actions=False)
    h.index = h.index.tz_localize(None).normalize()
    c = float(h.loc["2014-12-31", "Close"])
    sp = tk.splits
    sp.index = sp.index.tz_localize(None)
    after = sp[sp.index > "2014-12-31"]
    f = float(after.prod()) if len(after) else 1.0
    return c * f, c, f, ";".join(f"{i.date()}:{v:g}" for i, v in after.items())


rows = []
for t14, ty, cik, how in C:
    s = None
    if how == "dei":
        s = shares_dei(cik)
    elif how == "wavg":
        s = shares_wavg(cik)
    try:
        px, padj, fac, spl = raw_close(ty)
    except Exception as e:
        px = padj = fac = None
        spl = f"price error {e}"
    mc = s[1] * px if (s and px) else None
    rows.append({"ticker_2014": t14, "in_snapshot": t14 in snap, "yahoo": ty, "cik": cik, "method": how,
                 "shares": s[1] if s else None, "shares_asof": s[2] if s else None, "shares_form": s[3] if s else None,
                 "close_raw_20141231": px, "close_yahoo_splitadj": padj, "split_factor_after": fac, "splits_after": spl,
                 "mcap_bn": round(mc / 1e9, 1) if mc else None})
    print(t14, ty, how, s, px, spl, rows[-1]["mcap_bn"])
    time.sleep(0.3)

df = pd.DataFrame(rows).sort_values("mcap_bn", ascending=False, na_position="last")
df.insert(0, "rank", range(1, len(df) + 1))
df.to_csv(d / "mcap_2014-12-31_computed.csv", index=False)
print(df[["rank", "ticker_2014", "in_snapshot", "method", "shares", "shares_asof", "close_raw_20141231", "mcap_bn"]].to_string())
