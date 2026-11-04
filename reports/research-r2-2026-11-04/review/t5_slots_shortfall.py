"""
검토 시험 5 — check_team.py 가 직접 시험하지 않는 두 동작 (합성 데이터, 오프라인, 몇 초).

(가) 빈자리 배분: 같은 날 후보 6개, 보유 1개 + MAX_POSITIONS 5 → universe 순서 앞 4개만 주문, 나머지는 over_slots.
     다음 날 매수 대기 4개가 체결돼 5자리가 차면 새 주문 없음. 주식 수 = shares_within_cap(시작 예산, 상한, 시가).
(나) A1 '모자란 만큼만 지수 팔기'(H1 문구): 매수 날 지수 매도 단위 = (필요 − 현금) / (1단위 순매도액),
     체결 뒤 현금 < $1. 현금+지수로도 모자라면 지수를 팔지 않고 '현금부족' 보류(I2).
(다) 서킷이 걸린 날 주문 로그 중복(같은 종목·같은 신호일 매도 주문 두 번) 개수.

실행(저장소 루트): /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/review/t5_slots_shortfall.py
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
R2 = HERE.parent
ROOT = R2.parents[1]
for p in (str(ROOT), str(R2)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np          # noqa: E402
import pandas as pd         # noqa: E402
import sim_team as S        # noqa: E402
import check_team as C      # noqa: E402
from paper_wallet import shares_within_cap   # noqa: E402

ok_all = True


def report(name, ok, detail=""):
    global ok_all
    ok_all &= bool(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


cal = pd.bdate_range("2021-01-04", periods=160)
n = len(cal)
k = np.arange(n)
codes = [f"S{i}" for i in range(7)]
stocks = {}
for i, c in enumerate(codes):
    sig = np.zeros(n)
    if i == 0:
        sig[61] = 1
    else:
        sig[70:75] = 1                     # S1..S6 가 70~74 종가에 매수 신호
    stocks[c] = {"close": np.full(n, 20.0 + i), "sig": sig}
md = C.synth_market("us", cal, np.full(n, 100.0), stocks)
per = (cal[60].date().isoformat(), cal[-1].date().isoformat())
r = S.run(C.one_trainer(market="us", period=per, arm="A0", caps={"마라토너": 0.1}, interest=False, total=100_000), md)
o70 = [o["code"] for o in r["orders"] if o["action"] == "매수" and o["signal_cal"] == 70]
later = [o["code"] for o in r["orders"] if o["action"] == "매수" and 70 < o["signal_cal"] <= 74]
report("(가) 보유 1 + 후보 6 → universe 순서 앞 4개(S1~S4)만 주문", o70 == ["S1", "S2", "S3", "S4"], str(o70))
report("(가) 다음 날부터 5자리가 차서 새 매수 주문 없음", later == [], str(later))
report("(가) over_slots = 2 (자리가 다 찬 71~74일은 후보를 보지 않으므로 세지 않음)", r["sleeves"]["마라토너"]["over_slots"] == 2,
       str(r["sleeves"]["마라토너"]["over_slots"]))
okq = all(t["shares"] == shares_within_cap(100_000, 0.1, t["entry_price"], md.fee, md.slip) for t in r["trades"])
report("(가) 주식 수 = shares_within_cap(시작 예산 100,000, 10%, 시가)", okq)

# (나) A1 모자란 만큼만
stocks2 = {"X": {"close": np.full(n, 50.0), "sig": np.where(k == 61, 1.0, 0.0)},
           "Y": {"close": np.full(n, 40.0), "sig": np.where(k == 64, 1.0, 0.0)}}
md2 = C.synth_market("us", cal, np.full(n, 100.0), stocks2, idx_open=np.full(n, 101.0))
r2 = S.run(C.one_trainer(market="us", period=per, arm="A1", caps={"마라토너": 0.6}, interest=False, total=100_000), md2)
d62 = [f for f in r2["fills"] if f["date"] == md2.dstr[62]]
idx_sell = [f for f in d62 if f["kind"] == "index" and f["side"] == "매도"]
buy = [f for f in d62 if f["kind"] == "stock"]
cash_before = r2["daily"]["cash_마라토너"].iloc[62 - 60 - 1]
net_unit = 101.0 * (1 - md2.slip) * (1 - md2.fee)
want_u = (-buy[0]["cash"] - cash_before) / net_unit if buy else None
report("(나) 매수 날 지수 매도 단위 = (필요 − 현금)/1단위 순매도액 (오차 1e-6 이내)",
       buy and idx_sell and abs(idx_sell[0]["qty"] - want_u) <= 1e-6 * want_u,
       f"{idx_sell[0]['qty'] if idx_sell else None} vs {want_u}")
report("(나) 체결 뒤 종가 현금 < $1", r2["daily"]["cash_마라토너"].iloc[62 - 60] < 1.0)
d65 = [f for f in r2["fills"] if f["date"] == md2.dstr[65]]
sk = [s for s in r2["skips"] if s["date"] == md2.dstr[65]]
report("(나) 현금+지수로 모자란 두 번째 매수(60% 상한, 남은 40%) → 지수 안 팔고 '현금부족' 보류",
       not any(f["kind"] == "index" and f["side"] == "매도" for f in d65) and [s["kind"] for s in sk] == ["현금부족"],
       f"보류 {[s['kind'] for s in sk]}, 그날 체결 {[(f['kind'], f['side']) for f in d65]}")

# (다) 서킷 날 주문 로그 중복
x = np.where(k < 80, 100.0, 100.0 * 0.97 ** np.clip(k - 79, 0, 30))
stocks3 = {"X": {"close": x, "sig": np.where(k == 61, 1.0, np.where(k == 83, -1.0, 0.0))}}
md3 = C.synth_market("us", cal, np.full(n, 100.0), stocks3)
r3 = S.run(C.one_trainer(market="us", period=per, arm="A0", cb="current", caps={"마라토너": 1.0}, interest=False,
                         total=100_000), md3)
dup = Counter((o["code"], o["signal_date"], o["action"]) for o in r3["orders"])
n_dup = sum(v - 1 for v in dup.values() if v > 1)
print(f"(다) 서킷 사건 {[(e['date'], e['kind']) for e in r3['events']]}, 같은 날 같은 종목 매도 주문 로그 중복 {n_dup}건 "
      f"(체결은 1건: {sum(1 for f in r3['fills'] if f['kind'] == 'stock' and f['side'] == '매도')})")
print("전체:", "PASS" if ok_all else "FAIL 있음")
