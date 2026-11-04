"""2014-12-31 시가총액 상위 20 (S&P500 회원) 시세 받기 시험.
- 먼저 2014년 당시 티커 그대로 fdr.DataReader(t, 2015-01-02, 2026-11-03) 시도 → 실패/빈값 기록
- 실패하면 지금 티커로 다시 시도 (이름이 바뀐 경우)
- 성공분은 data_us_pit/prices/<지금티커>.csv.gz 로 이전 연구와 같은 형식(Open,High,Low,Close,Volume, %.6f)으로 저장
- |하루 변화| > 20% 인 날도 출력 (미반영 기업행위 의심 확인용)
실행: python -I fetch_us_pit.py <data_us_pit>
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr

d = Path(sys.argv[1])
out = d / "prices"
out.mkdir(exist_ok=True)
START, END = "2015-01-02", "2026-11-03"
END_Q = "2026-11-04"  # FDR yahoo 는 end 당일 0시까지만 줌 → 하루 뒤로 요청하고 END 까지 자름
# (순위, 2014 티커, 지금 티커)
TOP20 = [(1, "AAPL", "AAPL"), (2, "XOM", "XOM"), (3, "MSFT", "MSFT"), (4, "BRK.B", "BRK-B"), (5, "GOOGL", "GOOGL"),
         (6, "JNJ", "JNJ"), (7, "WFC", "WFC"), (8, "WMT", "WMT"), (9, "GE", "GE"), (10, "PG", "PG"),
         (11, "JPM", "JPM"), (12, "FB", "META"), (13, "CVX", "CVX"), (14, "ORCL", "ORCL"), (15, "VZ", "VZ"),
         (16, "PFE", "PFE"), (17, "BAC", "BAC"), (18, "KO", "KO"), (19, "T", "T"), (20, "INTC", "INTC")]
EXTRA = [(21, "C", "C"), (22, "V", "V"), (23, "MRK", "MRK"), (24, "DIS", "DIS"), (25, "IBM", "IBM"), (0, "GOOG", "GOOG")]


def try_fetch(sym):
    for attempt in range(2):
        try:
            df = fdr.DataReader(sym, START, END_Q)
            if df is None or len(df) == 0:
                return None, "빈 데이터"
            df = df.loc[:END]
            return df, None
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(1.5)
    return None, err


info = {"받은_시각_UTC": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M"), "출처": f"FinanceDataReader {fdr.__version__} (yahoo)",
        "시작일": START, "종료일": END, "종목": {}}
for rank, t14, tnow in TOP20 + EXTRA:
    rec = {"순위_2014말": rank, "티커_2014": t14, "지금_티커": tnow}
    df, err = try_fetch(t14)
    rec["2014티커로_받기"] = "성공" if df is not None else f"실패({err})"
    used = t14
    if df is not None and str(df.index[0].date()) > "2015-01-31":
        # 옛 티커가 '다른 증권'으로 재사용된 경우 (예: FB) → 경고 기록 후 지금 티커로
        rec["2014티커로_받기"] = (f"위험: 다른 증권 반환({len(df)}행, {df.index[0].date()}~, "
                               f"첫 종가 {df['Close'].iloc[0]:.2f})")
        df = None
    if df is None and tnow != t14:
        df, err = try_fetch(tnow)
        rec["지금티커로_받기"] = "성공" if df is not None else f"실패({err})"
        used = tnow
    if df is None:
        info["종목"][t14] = rec
        print(rank, t14, tnow, rec)
        continue
    n_raw = len(df)
    n_nan = int(df["Close"].isna().sum())
    df = df[df["Close"].notna()]
    o = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    o.index.name = None
    o.to_csv(out / f"{tnow}.csv.gz", float_format="%.6f")
    r = df["Close"].pct_change()
    big = [(str(i.date()), round(float(v), 3)) for i, v in r[r.abs() > 0.20].items()]
    rec.update({"받은_심볼": used, "행수": len(o), "Close_NaN_행": n_nan, "처음": str(o.index[0].date()),
                "마지막": str(o.index[-1].date()), "하루20%초과": big})
    info["종목"][t14] = rec
    print(rank, t14, tnow, rec["2014티커로_받기"], rec.get("지금티커로_받기", ""), used, len(o), n_nan,
          o.index[0].date(), o.index[-1].date(), big)
    time.sleep(0.3)
(d / "prices" / "universe.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
