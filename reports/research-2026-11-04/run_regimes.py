"""
국면별 성적 (research-2026-11-04)
----------------------------------
세 트레이너의 '기본값' 규칙을 국면마다 따로 돌려 buy&hold·SPY 와 비교한다.

설정 A (연구 기본): 종목 20개 × 슬롯 $10,000. 살 때 슬롯 현금 전부(상한 100%)까지.
                    → '규칙이 좋은가'만 보려고 정수 주 문제를 없앤 설정.
설정 B (v1 그대로): 총 $10,000 를 60/30/10% 로 나누고 종목상한 30/20/15% (main.py 처럼 종목마다 지갑).
                    → 실제 v1 금액에서 '0주라 보류'가 얼마나 생기는지 확인용.

무작위 타이밍 비교: 트레이너가 실제로 한 거래와 '횟수·보유 기간'이 똑같은 거래를 기간 안 무작위
시점에 1,000번 놓아 본다. 실제 규칙이 무작위보다 나은 비율이 95% 이상이어야(p<0.05) '타이밍 실력'
의 약한 근거로 본다. (20종목 동시 판단이라 종목끼리 독립이 아니므로 이것도 느슨한 기준이다)

실행(저장소 루트 어디서든): ~/.venv-cs/bin/python reports/research-2026-11-04/run_regimes.py
"""
from __future__ import annotations

import csv
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import sim

REGIMES = {
    "2015-17 상승": ("2015-01-01", "2017-12-31"),
    "2018 조정": ("2018-01-01", "2018-12-31"),
    "2020 급락·회복": ("2020-01-01", "2020-12-31"),
    "2022 하락": ("2022-01-01", "2022-12-31"),
    "2023-26 상승": ("2023-01-01", "2026-12-31"),
    "전체 2015-26": ("2015-01-01", "2026-12-31"),
}
SLOT = 10_000
V1_TOTAL = 10_000
V1_RATIO = {"마라토너": 0.60, "스프린터": 0.30, "파이오니어": 0.10}
V1_CAP = {"마라토너": 0.30, "스프린터": 0.20, "파이오니어": 0.15}
N_RANDOM = 1000
OUT = sim.HERE / "results"


def run_stock(code):
    """한 종목: 국면 × 트레이너 × 설정(A,B) 결과 + 무작위 배수."""
    df = sim.load(code)
    rows, rand = [], {}
    rng = np.random.default_rng(sum(map(ord, code)))   # 종목마다 고정 시드(재현 가능)
    for tname, cls in sim.BRAINS.items():
        prep = sim.Prepared(df, cls)
        for rname, (s, e) in REGIMES.items():
            i0, i1 = sim.idx_range(prep.dates, s, e)
            bh = sim.buy_hold(prep, i0, i1, SLOT)
            for setting in ("A", "B"):
                if setting == "B" and rname.startswith("전체"):
                    continue
                if setting == "A":
                    budget, cap = SLOT, 1.0
                else:
                    budget, cap = V1_TOTAL * V1_RATIO[tname], V1_CAP[tname]
                r = sim.simulate(prep, cls(), i0, i1, budget, cap, code, params_key="default")
                slot_amt = budget * cap
                bh_b = bh if setting == "A" else sim.buy_hold(prep, i0, i1, slot_amt)
                row = {
                    "설정": setting, "국면": rname, "트레이너": tname, "종목": code,
                    "시작": r["start"], "끝": r["end"], "슬롯금액": round(slot_amt, 2),
                    "손익": round(r["profit"], 2), "수익률": r["profit"] / slot_amt,
                    "MDD": r["mdd"],   # B 는 지갑 전체(놀고 있는 현금 포함) 기준 MDD
                    "매수": r["buys"], "매도": r["sells"], "보류": r["skips"], "익절수": r["wins"],
                    "보유비율": r["exposure"],
                    "BH손익": round(bh_b["profit"], 2), "BH수익률": bh_b["profit"] / slot_amt,
                    "BH_MDD": bh_b["mdd"],
                    "equity": r["equity"], "bh_equity": bh_b["equity"],
                }
                rows.append(row)
                if setting == "A":
                    act = sim.actual_factor(prep, r["trades"], i1)
                    rnd = sim.random_factors(prep, r["trades"], i0, i1, N_RANDOM, rng)
                    rand[(rname, tname)] = (act, rnd)
    return code, rows, rand


def pct(x, nd=1):
    return "-" if x is None else f"{x * 100:+.{nd}f}%"


def main():
    OUT.mkdir(exist_ok=True)
    codes = sim.universe()
    spy = sim.load("SPY")
    with ProcessPoolExecutor(4) as ex:
        results = list(ex.map(run_stock, codes))
    all_rows = [r for _, rows, _ in results for r in rows]
    rand = {}
    for _, _, rd in results:
        for k, v in rd.items():
            rand.setdefault(k, []).append(v)

    # SPY: 같은 날짜 구간, 같은 돈
    def spy_for(start, end, budget):
        i0 = int(spy.index.searchsorted(np.datetime64(start)))
        i1 = int(spy.index.searchsorted(np.datetime64(end), side="right")) - 1
        return sim.buy_hold(spy, i0, i1, budget)

    # 종목별 CSV
    keys = [k for k in all_rows[0] if k not in ("equity", "bh_equity")]
    with open(OUT / "regimes_by_stock.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys + ["SPY수익률"])
        w.writeheader()
        for r in all_rows:
            sp = spy_for(r["시작"], r["끝"], r["슬롯금액"])
            out = {k: r[k] for k in keys}
            out["SPY수익률"] = sp["profit"] / r["슬롯금액"]
            for k in ("수익률", "MDD", "보유비율", "BH수익률", "BH_MDD", "SPY수익률"):
                out[k] = round(out[k], 5)
            w.writerow(out)

    # 포트폴리오(20종목 합산) 요약
    summary = []
    for setting in ("A", "B"):
        for rname in REGIMES:
            for tname in sim.BRAINS:
                g = [r for r in all_rows if r["설정"] == setting and r["국면"] == rname and r["트레이너"] == tname]
                if not g:
                    continue
                total = sum(r["슬롯금액"] for r in g)
                eq = np.sum([r["equity"] for r in g], axis=0)
                if setting == "B":   # B 는 지갑 전체 곡선이므로 슬롯 기준이 아님 → 손익만 합산
                    eq = None
                bh_eq = np.sum([r["bh_equity"] for r in g], axis=0)
                prof = sum(r["손익"] for r in g)
                bh_prof = sum(r["BH손익"] for r in g)
                sp = spy_for(g[0]["시작"], g[0]["끝"], total)
                row = {
                    "설정": setting, "국면": rname, "트레이너": tname,
                    "기간": f"{g[0]['시작']}~{g[0]['끝']}",
                    "수익률": prof / total,
                    "MDD": sim.metrics.max_drawdown(list(eq)) if eq is not None else None,
                    "매수": sum(r["매수"] for r in g), "보류": sum(r["보류"] for r in g),
                    "보유비율": float(np.mean([r["보유비율"] for r in g])),
                    "BH수익률": bh_prof / total, "BH_MDD": sim.metrics.max_drawdown(list(bh_eq)),
                    "SPY수익률": sp["profit"] / total, "SPY_MDD": sp["mdd"],
                    "BH이긴종목": sum(r["수익률"] > r["BH수익률"] for r in g),
                    "SPY이긴종목": sum(r["수익률"] > spy_for(r["시작"], r["끝"], r["슬롯금액"])["profit"] / r["슬롯금액"] for r in g),
                    "종목수": len(g),
                }
                row["BH대비"] = row["수익률"] - row["BH수익률"]
                row["SPY대비"] = row["수익률"] - row["SPY수익률"]
                if setting == "A":
                    act = np.mean([a for a, _ in rand[(rname, tname)]]) - 1
                    rnd = np.mean([r_ for _, r_ in rand[(rname, tname)]], axis=0) - 1
                    row["무작위_평균"] = float(rnd.mean())
                    row["무작위_p"] = float((rnd >= act).mean())
                    row["무작위보다_나음"] = float((rnd < act).mean())
                    # 종목마다 '실제가 무작위 1,000번 중 몇 %보다 나았나' → 20종목 중앙값 (NVDA 쏠림 방지)
                    row["종목별_무작위백분위_중앙값"] = float(np.median(
                        [(r_ < a).mean() for a, r_ in rand[(rname, tname)]]))
                row["수익률_중앙값"] = float(np.median([r["수익률"] for r in g]))
                row["BH수익률_중앙값"] = float(np.median([r["BH수익률"] for r in g]))
                summary.append(row)

    fields = list(summary[0].keys())
    with open(OUT / "regimes_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in summary:
            w.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})

    # 사람이 읽을 표(마크다운)
    lines = ["# 국면별 결과 (자동 생성: run_regimes.py)", "",
             "## 설정 A — 종목 20개 × $10,000 슬롯, 20종목 합산", "",
             "| 국면 | 트레이너 | 수익률 | MDD | 매수 | 보유비율 | B&H | B&H MDD | SPY | SPY MDD | B&H 대비 | SPY 대비 | B&H 이긴 종목 | SPY 이긴 종목 | 종목 중앙값(트레이너/B&H) | 무작위 평균 | 무작위보다 나은 비율 | 종목별 무작위 백분위(중앙값) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        if r["설정"] != "A":
            continue
        lines.append(f"| {r['국면']} | {r['트레이너']} | {pct(r['수익률'])} | {pct(r['MDD'])} | {r['매수']} | "
                     f"{r['보유비율'] * 100:.0f}% | {pct(r['BH수익률'])} | {pct(r['BH_MDD'])} | {pct(r['SPY수익률'])} | "
                     f"{pct(r['SPY_MDD'])} | {pct(r['BH대비'])} | {pct(r['SPY대비'])} | {r['BH이긴종목']}/{r['종목수']} | "
                     f"{r['SPY이긴종목']}/{r['종목수']} | {pct(r['수익률_중앙값'])} / {pct(r['BH수익률_중앙값'])} | "
                     f"{pct(r['무작위_평균'])} | {r['무작위보다_나음'] * 100:.0f}% | {r['종목별_무작위백분위_중앙값'] * 100:.0f}% |")
    lines += ["", "## 설정 B — v1 금액 그대로(총 $10,000, 60/30/10%, 종목상한 30/20/15%)", "",
              "수익률·B&H 는 '종목상한 금액'(마라토너 $1,800 / 스프린터 $600 / 파이오니어 $150) 기준.", "",
              "| 국면 | 트레이너 | 수익률 | 매수 | 보류(0주) | B&H(같은 상한액) | SPY | B&H 이긴 종목 |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        if r["설정"] != "B":
            continue
        lines.append(f"| {r['국면']} | {r['트레이너']} | {pct(r['수익률'])} | {r['매수']} | {r['보류']} | "
                     f"{pct(r['BH수익률'])} | {pct(r['SPY수익률'])} | {r['BH이긴종목']}/{r['종목수']} |")
    (OUT / "regimes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
