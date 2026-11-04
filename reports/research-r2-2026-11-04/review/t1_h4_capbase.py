"""
검토 시험 1 — H4 종목상한 기준 금액(I5)이 재배분과 상관없이 H4를 H1과 다르게 만든다.

무엇을 보나
  - sim_team 은 H4 몫이 처음 바뀌는 날 s.cap_budget = 새 몫 × (그날 팀 평가액) 으로 바꾼다 (sim_team.py:648).
  - H1(A1)은 끝까지 시작 예산(start_cash)을 쓴다.
  - 그래서 몫이 사실상 그대로여도(차이 1e-9) 팀이 커졌으면 H4 의 종목당 주식 수가 H1 보다 커진다.
  - 여기서는 h4_weights 를 '기본몫 + 1e-9' 로 바꿔(=재배분 효과 0) 돌리고, H1 과 체결이 갈리는지만 센다.
출력은 개수·비율뿐이다(어느 쪽 수익률이 높은지는 찍지 않는다).

실행(저장소 루트): /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/review/t1_h4_capbase.py
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
import sim_team as S        # noqa: E402

PER = "2015-17 상승"

a1 = S.run(S.Config(market="us", period=PER, arm="A1", with_refs=False))
h4 = S.run(S.Config(market="us", period=PER, arm="A1", realloc=True, with_refs=False))
# 비율 자체는 그날 팀 평가액(=수익률)을 드러내므로 찍지 않고, 시작 예산과 다른지만 본다.
print("[실제 H4] 끝 상한 기준이 시작 예산과 다른 트레이너:",
      [nm for nm, sv in h4["sleeves"].items() if abs(sv["cap_budget_end"] - sv["start_cash"]) > 1e-6])

# 재배분 효과를 0 으로: 몫을 기본몫에서 1e-9 만 흔든다 (changed=True 가 되도록)
orig = S.h4_weights


def nearly_base(excess_lists, base):
    w, ts = orig(excess_lists, base)
    if ts is None:
        return w, ts
    b = np.asarray(base, float) / np.sum(base)
    b = b * (1 + np.array([1e-9, 0, 0]))
    return list(b / b.sum()), ts


S.h4_weights = nearly_base
try:
    z = S.run(S.Config(market="us", period=PER, arm="A1", realloc=True, with_refs=False))
finally:
    S.h4_weights = orig

chg = [e for e in z["events"] if e["kind"] == "H4" and e["changed"]]
first = chg[0]["date"] if chg else None
moved = max((abs(v) / e["V"] for e in chg for v in e["moved"].values()), default=0.0)
print(f"[재배분 효과 0 인 H4] 몫 바뀜 처리 {len(chg)}번, 처음 {first}, "
      f"몫 차이 최대 {max(abs(e['w_new'][k] - e['w_old'][k]) for e in chg for k in e['w_new']):.1e}, "
      f"그런데 옮긴 금액 최대 = 팀 합계의 {moved:.2%} (현재 평가액을 60/30/10 으로 다시 맞춤)")
print("   끝 상한 기준이 시작 예산과 다른 트레이너:",
      [nm for nm, sv in z["sleeves"].items() if abs(sv["cap_budget_end"] - sv["start_cash"]) > 1e-6])


def key(f):
    return (f["sleeve"], f["date"], f["code"], f["side"], f["qty"])


fa = [key(f) for f in a1["fills"] if f["kind"] == "stock" and f["date"] >= first]
fz = [key(f) for f in z["fills"] if f["kind"] == "stock" and f["date"] >= first]
sa, sz = set(fa), set(fz)
print(f"첫 처리일 이후 주식 체결: H1 {len(fa)}건, '효과 0 H4' {len(fz)}건, 서로 다른 체결 {len(sa ^ sz)}건")
ta = {(t["sleeve"], t["entry_date"], t["code"]): t["shares"] for t in a1["trades"] if t["entry_date"] >= first}
tz = {(t["sleeve"], t["entry_date"], t["code"]): t["shares"] for t in z["trades"] if t["entry_date"] >= first}
both = set(ta) & set(tz)
bigger = sum(1 for k in both if tz[k] > ta[k])
print(f"같은 날 같은 종목 매수 {len(both)}건 중 H4 쪽 주식 수가 더 많은 것 {bigger}건")
skip_a = sum(1 for s in a1["skips"] if s["date"] >= first)
skip_z = sum(1 for s in z["skips"] if s["date"] >= first)
print(f"첫 처리일 이후 보류: H1 {skip_a}건, '효과 0 H4' {skip_z}건")
verdict = "재현됨(H4≠H1, 재배분 효과 0인데도)" if (sa ^ sz) else "재현 안 됨"
print("결론:", verdict)
