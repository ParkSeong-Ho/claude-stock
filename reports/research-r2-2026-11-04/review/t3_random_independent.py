"""
검토 시험 3 — 무작위 대조(I13)를 거래 하나씩 도는 단순한 코드로 따로 계산해 sim_team.Contribution 과 맞춰 본다.

점검 12 는 '제자리 = 실제'(같은 함수끼리 비교)와 '끝까지 보유하지 않은 미국 거래 하나'만 손으로 맞춘다.
여기서는 (1) 실제 진입, (2) 무작위 진입 50번 모두에 대해, 국내 매도세·끝까지 보유·정지 종목·신규 상장 종목을
포함해 거래별 기여를 따로 계산한다. 또 무작위 진입 범위가 'A7 60봉 + 국면 안 신호'와 맞는지 따로 계산한다.
출력은 차이·개수뿐이다.

실행(저장소 루트): /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/review/t3_random_independent.py
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


def naive_one(md, tr, entry, i1):
    """거래 하나: 진입 자기 봉 entry, 보유 봉 수 L 은 실제 거래에서. 단순 계산."""
    st = md.by_code[tr["code"]]
    jend = int(st.last_own_at_cal[i1])
    L = (tr["exit_own"] if tr["exit_own"] is not None else jend + 1) - tr["entry_own"]
    x = entry + L
    N = tr["notional"]
    f, s = md.fee, md.slip
    buy_cost = (1 + s) * (1 + f) - 1
    idx_sell_cost = 1 - (1 - s) * (1 - f)
    idx_buy_cost = (1 + s) * (1 + f) - 1
    p_in = st.open[entry]
    i_in = md.idx_open[st.cal_of_own[entry]]
    if x <= jend:                       # 국면 안에서 청산(청산 시가)
        p_out = st.open[x]
        i_out = md.idx_open[st.cal_of_own[x]]
        tax = md.tax(md.dstr[st.cal_of_own[x]])
        g_s, g_i = p_out / p_in, i_out / i_in
        sell_cost = 1 - (1 - s) * (1 - f - tax)
        cost = N * (buy_cost + idx_sell_cost) + N * g_s * (sell_cost + idx_buy_cost)
    else:                               # 끝까지 보유(마지막 종가)
        g_s = st.close[jend] / p_in
        g_i = md.idx_close[i1] / i_in
        tax = md.tax(md.dstr[i1])
        sell_cost = 1 - (1 - s) * (1 - f - tax)
        cost = N * (buy_cost + idx_sell_cost) + N * g_s * sell_cost - N * g_i * idx_sell_cost
    return N * (g_s - g_i) - cost


def naive_range(md, tr, i0, i1):
    """들어갈 수 있는 진입 자기 봉 [lo, hi]: 신호 봉(진입-1)의 달력이 i0 이상·i1 미만이고 신호 봉+1 >= 60,
    보유 L 봉이 국면 끝(마지막 자기 봉+1)을 넘지 않음."""
    st = md.by_code[tr["code"]]
    jend = int(st.last_own_at_cal[i1])
    L = (tr["exit_own"] if tr["exit_own"] is not None else jend + 1) - tr["entry_own"]
    ok = []
    for e in range(1, len(st.open)):
        sig = e - 1
        if st.cal_of_own[sig] < i0 or st.cal_of_own[sig] >= i1 or sig + 1 < S.MIN_BARS:
            continue
        if e + L > jend + 1:
            continue
        ok.append(e)
    return (min(ok), max(ok)) if ok else (None, None)


for key, per in (("kr", "2018 조정"), ("kr", "2022 하락"), ("us", "2020 급락·회복")):
    md = S.get_market(key)
    r = S.run(S.Config(market=key, period=per, arm="A1", with_refs=False))
    c = S.Contribution(md, r)
    i0, i1 = r["i0"], r["i1"]
    act = c.actual()
    nv = np.array([naive_one(md, tr, tr["entry_own"], i1) for tr in r["trades"]])
    ent = c.draws(50, 123)
    rnd = c.per_trade(ent)
    nrnd = np.array([[naive_one(md, tr, int(ent[d, k]), i1) for k, tr in enumerate(r["trades"])] for d in range(50)])
    rng_bad = 0
    for k, tr in enumerate(r["trades"]):
        lo, hi = naive_range(md, tr, i0, i1)
        if (lo, hi) != (int(c.lo[k]), int(c.hi[k])):
            rng_bad += 1
    held = sum(1 for tr in r["trades"] if tr["exit_own"] is None)
    late = sorted({tr["code"] for tr in r["trades"] if md.by_code[tr["code"]].cal_of_own[0] > i0 - S.MIN_BARS})
    scale = max(1.0, float(np.max(np.abs(nv))))
    print(f"{key} {per}: 거래 {len(nv)}건(끝까지 보유 {held}건, 국면 중 60봉 채운 종목 {late}), "
          f"실제 최대 차이 {np.max(np.abs(nv - act)) / scale:.1e}(상대), "
          f"무작위 50번 최대 차이 {np.max(np.abs(nrnd - rnd)) / scale:.1e}(상대), 진입 범위 불일치 {rng_bad}건")
