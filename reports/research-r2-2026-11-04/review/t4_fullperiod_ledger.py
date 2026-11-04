"""
검토 시험 4 — 전체 2015-26 국면 장부 점검 (check_team.py 는 실데이터를 2018 한 국면만 돌린다).

check_team.accounting(현금 ≥ -0.01, 지수 단위 ≥ 0, 평가 = 현금+주식+지수, 원장, 체결 비용식, t+1 시가, Volume=0 체결 없음)을
전체 국면의 주요 설정에 적용하고, 추가로 다음을 본다.
  - 지수 다리 체결가 = 그날 지수 시가 (점검 4 에 없음)
  - 지수 대기(A1) 지갑의 매 종가 현금 < 1 (남는 돈 $1 미만, H1)
  - 같은 날 같은 종목 주문 중복(로그) 개수
  - B1 구간 경계 날짜가 daily 에 있는지
출력은 개수·장부 문제뿐이다(수익률은 찍지 않는다). 시간: 약 5~8분.

실행(저장소 루트): /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/review/t4_fullperiod_ledger.py
"""
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
R2 = HERE.parent
ROOT = R2.parents[1]
for p in (str(ROOT), str(R2)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np          # noqa: E402
import sim_team as S        # noqa: E402
import check_team as C      # noqa: E402

PER = "전체 2015-26"
PLAN = {
    "us": [dict(arm="A0"), dict(arm="A1"), dict(arm="A1T"), dict(arm="A2"), dict(arm="A0", cb="current"),
           dict(arm="A0", cb="staged"), dict(arm="A1", cb="current"), dict(arm="A1", cb="staged"),
           dict(arm="A1", realloc=True)],
    "kr": [dict(arm="A0"), dict(arm="A1"), dict(arm="A1", cb="staged"), dict(arm="A1", realloc=True)],
    "us_pit": [dict(arm="A1")],
}
B1_EDGES = ["2019-12-31", "2020-12-31", "2021-12-31", "2022-12-30", "2026-11-03"]

for key, arms in PLAN.items():
    md = S.get_market(key)
    for a in arms:
        t = time.time()
        r = S.run(S.Config(market=key, period=PER, **a))
        bad = C.accounting(r, md, key)
        # 지수 다리 체결가 = 그날 지수 시가
        pos = {d: k for k, d in enumerate(md.dstr)}
        idx_bad = sum(1 for f in r["fills"] if f["kind"] == "index" and f["price"] != md.idx_open[pos[f["date"]]])
        # A1 계열: 지수 대기 날 종가 현금 < 1 (이자 붙기 전 기준은 아님; 이자 0 이므로 같음)
        cash_hi = 0
        d = r["daily"]
        for nm, sv in r["sleeves"].items():
            if f"mode_{nm}" in d:
                m = d[f"mode_{nm}"].to_numpy() == "index"
                cash_hi += int(np.sum(d[f"cash_{nm}"].to_numpy()[m] >= 1.0))
        dup = Counter((o["sleeve"], o["code"], o["signal_date"], o["action"]) for o in r["orders"])
        n_dup = sum(v - 1 for v in dup.values() if v > 1)
        ev = Counter(e["kind"] for e in r["events"] if e["kind"] != "H4" or e["changed"])
        b1 = all(x in d.index for x in B1_EDGES) if key == "us" else None
        m = r["metrics"]
        print(f"{key:6s} {S.label(r['config']):14s} 매수 {m['buys']:5d} 매도 {m['sells']:5d} 지수다리 {m['index_legs']:5d} "
              f"보류 {m['skips']:5d} {dict(m['skip_kinds'])} 최소현금 {m['min_cash']:.4f} "
              f"NaN {int(np.isnan(r['equity']).sum())} 장부문제 {len(bad)} 지수시가아님 {idx_bad} "
              f"지수대기인데현금>=1 {cash_hi} 주문중복 {n_dup} 사건 {dict(ev)} B1날짜 {b1} ({time.time() - t:.0f}s)",
              flush=True)
        if bad:
            print("      ", bad[:3])
