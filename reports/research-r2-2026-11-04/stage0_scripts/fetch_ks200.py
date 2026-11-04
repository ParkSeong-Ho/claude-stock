"""KOSPI 200 가격지수(KS200)를 받아 data_kr 형식으로 저장한다. 배당·분배금이 빠진 가격지수라
배당 미포함 주식 가격과 기준이 같다(069500 네이버 시세는 분배금이 반영돼 있어 대신 쓴다)."""
import sys, json, datetime as dt
import FinanceDataReader as fdr
out = sys.argv[1]
df = fdr.DataReader("KS200", "2014-08-01", "2026-11-04")[["Open", "High", "Low", "Close", "Volume"]]
df = df[df["Close"].notna()]
df = df[df.index <= "2026-11-03"]          # 다른 국내 파일과 같은 마지막 날
df.index.name = None
df.to_csv(f"{out}/KS200.csv.gz", float_format="%.6f")
print(json.dumps({"code": "KS200", "source": "FinanceDataReader KS200 (KOSPI 200 price index)",
                  "fetched_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
                  "first": str(df.index[0].date()), "last": str(df.index[-1].date()), "rows": len(df),
                  "open_le_0": int((df["Open"] <= 0).sum())}, ensure_ascii=False))
