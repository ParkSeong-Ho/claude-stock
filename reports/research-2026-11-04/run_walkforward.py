"""
Walk-forward 검증 (research-2026-11-04)
----------------------------------------
"과거 2년에 제일 좋았던 설정을 다음 1년에 쓰면 어떻게 되나?"를 10번 반복한다.

  훈련 2015-16 → 시험 2017,  훈련 2016-17 → 시험 2018,  …,  훈련 2024-25 → 시험 2026(11월 초까지)

- 후보 설정: tune.py 의 GRIDS 를 그대로 import (스프린터 32개, 파이오니어 9개).
  마라토너는 tune.py 에 격자가 없어서 기본값 하나만 쓴다(=고르기 없음, 해마다 기본값 성적).
- '1등' = 훈련 2년 동안 20종목 × $10,000 슬롯 합산 수익률이 가장 높은 설정 (tune.py 처럼 손익 합 기준).
- 훈련·시험 구간은 각각 현금에서 새로 시작한다(앞 구간 보유를 넘겨받지 않음).
- 비교: 같은 해 기본값 / 20종목 buy&hold(해마다 같은 돈으로 새로 삼) / SPY.
- 과최적화 점검: 훈련 성적 순위와 시험 성적 순위의 상관(스피어만). 0 근처나 음수면
  '과거에 좋았던 설정이 미래에도 좋다'는 근거가 없다는 뜻.

실행: ~/.venv-cs/bin/python reports/research-2026-11-04/run_walkforward.py   (4코어 약 2~4분)
"""
from __future__ import annotations

import csv
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import sim
import tune     # 저장소 tune.py (import 만, 수정 없음)

SLOT = 10_000
TEST_YEARS = list(range(2017, 2027))
OUT = sim.HERE / "results"


def grids():
    g = {"마라토너": [{}]}
    for name, spec in tune.GRIDS.items():
        g[name] = list(tune._combos(spec["params"]))
    return g


def key(combo):
    return tuple(sorted(combo.items()))


def windows():
    out = []
    for y in TEST_YEARS:
        out.append((y, ("train", f"{y - 2}-01-01", f"{y - 1}-12-31"), ("test", f"{y}-01-01", f"{y}-12-31")))
    return out


def run_stock(code):
    df = sim.load(code)
    res = {}
    for tname, combos in grids().items():
        cls = sim.BRAINS[tname]
        prep = sim.Prepared(df, cls)
        for y, *wins in windows():
            for kind, s, e in wins:
                i0, i1 = sim.idx_range(prep.dates, s, e)
                if kind == "test":
                    bh = sim.buy_hold(prep, i0, i1, SLOT)
                    res[("BH", y)] = (bh["profit"], bh["equity"], 0)
                for c in combos:
                    r = sim.simulate(prep, cls(**c), i0, i1, SLOT, 1.0, code, params_key=key(c))
                    res[(tname, key(c), y, kind)] = (r["profit"], r["equity"] if kind == "test" else None, r["buys"])
    return code, res


def spearman(a, b):
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def pct(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:+.1f}%"


def main():
    OUT.mkdir(exist_ok=True)
    codes = sim.universe()
    with ProcessPoolExecutor(4) as ex:
        per_stock = dict(ex.map(run_stock, codes))
    spy = sim.load("SPY")
    total = SLOT * len(codes)
    G = grids()
    defaults = {t: key(tune._defaults(sim.BRAINS[t])) if t != "마라토너" else key({}) for t in G}
    # 기본값 key 는 격자 칸 이름으로만 비교 (격자에 없는 인자는 기본값 그대로)
    for t in ("스프린터", "파이오니어"):
        dd = tune._defaults(sim.BRAINS[t])
        defaults[t] = next(key(c) for c in G[t] if all(dd[k] == v for k, v in c.items()))

    def port(tname, ck, y, kind):
        prof = sum(per_stock[c][(tname, ck, y, kind)][0] for c in codes)
        buys = sum(per_stock[c][(tname, ck, y, kind)][2] for c in codes)
        return prof / total, buys

    def port_mdd(tname, ck, y):
        eq = np.sum([per_stock[c][(tname, ck, y, "test")][1] for c in codes], axis=0)
        return sim.metrics.max_drawdown(list(eq))

    rows = []
    for y in TEST_YEARS:
        bh_ret = sum(per_stock[c][("BH", y)][0] for c in codes) / total
        bh_mdd = sim.metrics.max_drawdown(list(np.sum([per_stock[c][("BH", y)][1] for c in codes], axis=0)))
        i0, i1 = sim.idx_range(spy.index, f"{y}-01-01", f"{y}-12-31")
        sp = sim.buy_hold(spy, i0, i1, total)
        for tname, combos in G.items():
            ks = [key(c) for c in combos]
            tr = {k: port(tname, k, y, "train")[0] for k in ks}
            te = {k: port(tname, k, y, "test") for k in ks}
            best = max(ks, key=lambda k: tr[k])
            test_sorted = sorted(ks, key=lambda k: te[k][0], reverse=True)
            rows.append({
                "시험연도": y, "트레이너": tname, "후보수": len(ks),
                "고른설정": ",".join(f"{k}={v}" for k, v in best) or "기본값",
                "고른설정_훈련": tr[best], "고른설정_시험": te[best][0], "고른설정_시험MDD": port_mdd(tname, best, y),
                "고른설정_시험매수": te[best][1],
                "고른설정_시험순위": test_sorted.index(best) + 1,
                "기본값_시험": te[defaults[tname]][0],
                "시험_1등": te[test_sorted[0]][0],
                "훈련시험_순위상관": spearman([tr[k] for k in ks], [te[k][0] for k in ks]) if len(ks) > 1 else float("nan"),
                "BH_시험": bh_ret, "BH_MDD": bh_mdd, "SPY_시험": sp["profit"] / total, "SPY_MDD": sp["mdd"],
                "기간": f"{sp['start']}~{sp['end']}",
            })
    with open(OUT / "walkforward.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})

    # 사람이 읽을 표
    lines = ["# Walk-forward 결과 (자동 생성: run_walkforward.py)", "",
             "20종목 × $10,000 슬롯 합산. 해마다 현금에서 새로 시작.", ""]
    chain = {}
    for tname in G:
        lines += [f"## {tname}", "",
                  "| 시험연도 | 고른 설정(앞 2년 1등) | 훈련 수익률 | 시험 수익률 | 시험 MDD | 시험 순위 | 기본값 시험 | B&H | SPY | B&H 대비 | SPY 대비 | 훈련↔시험 순위상관 |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        gr = [r for r in rows if r["트레이너"] == tname]
        for r in gr:
            lines.append(f"| {r['시험연도']} | {r['고른설정']} | {pct(r['고른설정_훈련'])} | {pct(r['고른설정_시험'])} | "
                         f"{pct(r['고른설정_시험MDD'])} | {r['고른설정_시험순위']}/{r['후보수']} | {pct(r['기본값_시험'])} | "
                         f"{pct(r['BH_시험'])} | {pct(r['SPY_시험'])} | {pct(r['고른설정_시험'] - r['BH_시험'])} | "
                         f"{pct(r['고른설정_시험'] - r['SPY_시험'])} | "
                         + ("-" if np.isnan(r['훈련시험_순위상관']) else f"{r['훈련시험_순위상관']:+.2f}") + " |")
        wf = float(np.prod([1 + r["고른설정_시험"] for r in gr]) - 1)
        de = float(np.prod([1 + r["기본값_시험"] for r in gr]) - 1)
        bh = float(np.prod([1 + r["BH_시험"] for r in gr]) - 1)
        sp = float(np.prod([1 + r["SPY_시험"] for r in gr]) - 1)
        beat_bh = sum(r["고른설정_시험"] > r["BH_시험"] for r in gr)
        beat_spy = sum(r["고른설정_시험"] > r["SPY_시험"] for r in gr)
        beat_def = sum(r["고른설정_시험"] > r["기본값_시험"] for r in gr)
        rho = [r["훈련시험_순위상관"] for r in gr if not np.isnan(r["훈련시험_순위상관"])]
        chain[tname] = (wf, de, bh, sp)
        lines += ["", f"- 10년(2017~2026.11) 이어 붙인 누적: walk-forward {pct(wf)} / 기본값 {pct(de)} / "
                      f"B&H(해마다 새로 삼) {pct(bh)} / SPY {pct(sp)}",
                  f"- 시험 해 중 B&H 이긴 해 {beat_bh}/10, SPY 이긴 해 {beat_spy}/10"
                  + (f", 기본값보다 나은 해 {beat_def}/10, 훈련↔시험 순위상관 평균 {np.mean(rho):+.2f}" if rho else ""), ""]
    (OUT / "walkforward.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
