"""run2 진단: screener가 후보 0개인 이유 확인. 저장소 코드는 그대로 import만 한다.
(a) 40종목 중 마지막 봉 Close가 NaN인 종목 수, (b) NaN 봉을 뺐을 때(=어제 확정 봉 기준) 나오는 후보."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import main, screener
syms = screener.universe(40)
nan_last = 0; alt = {t: [] for t in screener.BRAINS}
for code in syms:
    try: df = main.load_prices(code, screener.START)
    except Exception as e: print(code, "load fail", e); continue
    if df["Close"].isna().iloc[-1]: nan_last += 1
    d0 = df.dropna(subset=["Close"])
    for t, cls in screener.BRAINS.items():
        b = cls(); d = b.add_indicators(d0); a, r = b.decide(d, None)
        if a == "매수": alt[t].append((code, round(float(d["Close"].iloc[-1]), 2), r[:30]))
print(f"마지막 봉 Close=NaN: {nan_last}/{len(syms)}종목 (마지막 날짜 예: {df.index[-1].date()})")
for t, c in alt.items(): print(f"NaN 봉 제외 시 {t} 후보 {len(c)}: {c}")
