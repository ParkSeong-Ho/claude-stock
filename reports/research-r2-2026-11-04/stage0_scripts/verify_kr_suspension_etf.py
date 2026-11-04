import sys, glob, pandas as pd, FinanceDataReader as fdr, yfinance as yf
d = sys.argv[1]
# 1) suspension rows
tot = 0
for f in sorted(glob.glob(d + "/data_kr/*.csv.gz")):
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    z = int((df["Open"] <= 0).sum()); v0 = int((df["Volume"] <= 0).sum()); tot += z
    if z or v0: print(f.split("/")[-1], "Open<=0:", z, "Vol=0:", v0)
print("total Open<=0 rows", tot)
# 2) 069500 naver vs yahoo raw close
n = pd.read_csv(d + "/data_kr/069500.csv.gz", index_col=0, parse_dates=True)["Close"]
y = yf.download("069500.KS", start="2014-12-01", end="2026-11-04", auto_adjust=False, progress=False)
yc = y["Close"].squeeze(); ya = y["Adj Close"].squeeze()
for day in ["2015-01-02", "2018-01-02", "2022-01-03", "2026-11-03"]:
    t = pd.Timestamp(day)
    print(day, "naver", n.get(t), "yahoo_close", round(float(yc.get(t, float('nan'))),1), "yahoo_adj", round(float(ya.get(t, float('nan'))),1))
k = fdr.DataReader("KS200", "2014-12-01", "2026-11-04")["Close"]
print("KS200 index rows", len(k), k.index[0].date(), k.index[-1].date(), "ret 2015-01-02..2026-11-03",
      round(float(k.loc["2026-11-03"]/k.loc["2015-01-02"]-1),4))
print("069500 naver ret", round(float(n.loc["2026-11-03"]/n.loc["2015-01-02"]-1),4),
      "yahoo raw ret", round(float(yc.loc["2026-11-03"]/yc.loc["2015-01-02"]-1),4))
