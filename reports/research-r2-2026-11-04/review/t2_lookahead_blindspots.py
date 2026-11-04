"""
검토 시험 2 — check_team.py 의 '미리보기 없음'(점검 3)과 장부(점검 4)가 못 잡는 미리보기를 일부러 넣어 본다.

시나리오
  (가) 같은 봉 미리보기: A1 에서 '모자란 만큼 지수 팔기'(_raise_cash)를 그날 시가 대신 '그날 종가'로 체결.
       잘라낸 데이터에도 t 의 종가는 남아 있으므로 점검 3 은 같다고 본다.
       점검 4 는 주식 다리만 '체결가 = 시가'를 확인하고 지수 다리는 확인하지 않는다.
  (나) 기간 날짜 미리보기: 국내 월별 금리(날짜 = 그 달 1일)를 m-1월 대신 m월 값으로 사용.
       m월 1일자 행은 m월 중간에서 잘라도 남아 있으므로 점검 3 은 같다고 본다(점검 8 만 잡는다).
각 시나리오에서 (1) 점검 3 의 same_prefix, (2) 점검 4 의 accounting 이 문제를 찾는지, (3) 원래 코드와 결과가 실제로
달라졌는지(= 미리보기가 결과를 바꿨는지)를 찍는다. 수익률은 찍지 않는다.

실행(저장소 루트): /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/review/t2_lookahead_blindspots.py
"""
import sys
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
import check_team as C      # noqa: E402  (main() 은 부르지 않는다: same_prefix, accounting 만 씀)


def truncated_md(key, tdate):
    idx, frames, rates, rule, zv = S.load_frames(key, tdate)
    return S.MarketData(key, idx, frames, rates, rule, zero_volume=zv)


# ---------------------------------------------------------------- (가) 지수 다리 같은 봉 종가 체결
def raise_cash_at_close(self, s, need, t):
    short = need - s.wallet.cash
    if short <= 0:
        return
    held = s.units(self.md.idx_code)
    px = self.md.idx_close[t]                               # ← 미리보기: 시가 시점에 그날 종가 사용
    w = s.wallet
    net = px * (1 - w.slippage) * (1 - w.fee_rate)
    u = min(held, short / net * (1 + 1e-9))
    if u > 0:
        self._sell(s, self.md.idx_code, px, u, t, 0.0, "index")


key, per = "us", "2018 조정"
md = S.get_market(key)
base = S.run(S.Config(market=key, period=per, arm="A1", with_refs=False))
orig = S.TeamSim._raise_cash
S.TeamSim._raise_cash = raise_cash_at_close
try:
    full = S.run(S.Config(market=key, period=per, arm="A1", with_refs=False))
    i0, _ = S.period_range(md, per)
    tdate = md.dstr[i0 + 120]
    tr = S.run(S.Config(market=key, period=(S.REGIMES[per][0], tdate), arm="A1", with_refs=False),
               truncated_md(key, tdate))
    probs3 = C.same_prefix(full, tr, tdate)
    probs4 = C.accounting(full, md, "blind")
finally:
    S.TeamSim._raise_cash = orig
n_idx_close = sum(1 for f in full["fills"] if f["kind"] == "index" and f["side"] == "매도"
                  and f["price"] == md.idx_close[md.dstr.index(f["date"])]
                  and f["price"] != md.idx_open[md.dstr.index(f["date"])])
diff = sum(1 for a, b in zip(base["fills"], full["fills"]) if a != b) + abs(len(base["fills"]) - len(full["fills"]))
print("(가) 지수 다리를 그날 종가에 체결하는 미리보기")
print(f"    종가로 체결된 지수 매도 {n_idx_close}건, 원래 코드와 다른 체결 {diff}건")
print(f"    점검 3(잘라내기) 문제: {probs3 or '없음 → 못 잡음'}")
print(f"    점검 4(장부) 문제: {probs4[:2] or '없음 → 못 잡음'}")

# ---------------------------------------------------------------- (나) 국내 월별 금리 m월 값 사용
orig_rate = S.rate_for_days


def rate_same_month(cal, series, rule):
    if rule == "prev_month":
        first_of_this = cal.to_period("M").to_timestamp()      # ← 미리보기: m월 평균을 m월에 사용
        return S._asof(series, first_of_this.values)
    return orig_rate(cal, series, rule)


key, per = "kr", "2018 조정"
idx, frames, rates, rule, zv = S.load_frames(key)
md_ok = S.MarketData(key, idx, frames, rates, rule, zero_volume=zv)
base = S.run(S.Config(market=key, period=per, arm="A0", with_refs=False), md_ok)
S.rate_for_days = rate_same_month
try:
    md_bad = S.MarketData(key, idx, frames, rates, rule, zero_volume=zv)
    full = S.run(S.Config(market=key, period=per, arm="A0", with_refs=False), md_bad)
    tdate = "2018-06-15"
    tr = S.run(S.Config(market=key, period=(S.REGIMES[per][0], tdate), arm="A0", with_refs=False),
               truncated_md(key, tdate))
    probs3 = C.same_prefix(full, tr, tdate)
    probs4 = C.accounting(full, md_bad, "blind")
finally:
    S.rate_for_days = orig_rate
ndays = int(np.sum(md_ok.rate_pct != md_bad.rate_pct))
print("(나) 국내 월별 금리를 그 달 값으로 쓰는 미리보기")
print(f"    금리가 달라진 거래일 {ndays}일, 이자 합 달라짐: {not np.isclose(base['metrics']['interest'], full['metrics']['interest'])}")
print(f"    점검 3(잘라내기) 문제: {probs3 or '없음 → 못 잡음'}")
print(f"    점검 4(장부) 문제: {probs4[:2] or '없음 → 못 잡음'}")
print("결론: 두 미리보기 모두 점검 3·4 를 통과한다. (나)는 점검 8 의 합성 시험만 잡는다. (가)는 어떤 점검도 잡지 않는다.")
