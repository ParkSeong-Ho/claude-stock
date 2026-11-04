"""
R2 단계 2 실행 스크립트 — 사전 등록 §7 전부 + 7.5 확인 단계 (A1~A9, B1~B9 반영)
================================================================================
⚠️ 이 스크립트는 단계 1에서 **실행하지 않았다**(--dry-run 만 시험). 검토가 끝난 뒤 사용자가 돌린다.

순서 (사전 등록 그대로)
  1. 미국(R0 20종목) 전체 표: A0, A1, A1T, A2, G11, IDX, A0·A1 × 서킷 2종(H3), A1+H4 × 6국면.
     A1 은 무작위 시점 대조 1,000번(H1-4). §7.0 의 "$10,000 결과는 참고로만" → A0·A1·A1T·A2 를 $10,000 로도 돌린다.
  2. verdict.us_verdicts() 로 H1~H4 판정 (판정식은 verdict.py, 결과 보기 전에 커밋한 것).
  3. 7.5-1: 미국에서 통과(채택 후보)한 가설만 국내(KR_UNIVERSE, ₩1억)에서 같은 규칙으로 → verdict.kr_direction().
  4. 7.5-2: H1 이 채택 후보이면 us_pit(2014말 시총 상위 20)로 H1 을 다시 → verdict.pit_h1().
  돌린 것은 전부 표와 로그에 남긴다(통과 못 한 가설의 확인 단계는 돌리지 않는다 — 7.6 시험 횟수).
  매 실행마다 check_team.accounting(장부·체결가·비용·이자 규칙) 점검을 돌려 문제가 있으면 멈춘다.

출력 (--out, 기본 reports/research-r2-2026-11-04/results/)
  summary.csv        실행마다 한 줄: 수익률·MDD·비율·매매·보류·비용·이자·참고선(지수 B&H 정수/소수, 동일비중, G11)
  tables.md          시장·국면별 표
  random.csv         A1 무작위 대조 백분위(트레이너별)
  trades.csv.gz      모든 거래   events.csv  서킷·재배분 사건   a6.csv  국내 A6 보고
  daily_full/*.csv.gz 전체 국면 실행의 일별 기록(B1 구간 재계산용)
  verdicts.json, VERDICTS.md   판정   run_log.txt  실행 기록

실행(저장소 루트):
  /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/run_r2.py                 # 단계 2 (아직 안 돌림)
  /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/run_r2.py --dry-run --out <임시 폴더>
      → 2018 한 국면만, 확인 단계도 강제로 돌려 코드 길만 시험한다. 판정 숫자는 의미가 없고 화면에 찍지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import sim_team as S        # noqa: E402
import verdict as V         # noqa: E402
import check_team as C      # noqa: E402  (accounting 만 쓴다; main() 은 부르지 않음)

US_ARMS = [dict(arm="A0"), dict(arm="A1"), dict(arm="A1T"), dict(arm="A2"), dict(arm="G11"), dict(arm="IDX"),
           dict(arm="A0", cb="current"), dict(arm="A0", cb="staged"), dict(arm="A1", cb="current"),
           dict(arm="A1", cb="staged"), dict(arm="A1", realloc=True)]
REF_10K = [dict(arm="A0"), dict(arm="A1"), dict(arm="A1T"), dict(arm="A2")]
HOLDOUT_ARMS = {
    "H1": [dict(arm="A0"), dict(arm="A1"), dict(arm="A2"), dict(arm="IDX")],
    "H2": [dict(arm="A1"), dict(arm="A1T"), dict(arm="A2"), dict(arm="IDX")],
    "H3": [dict(arm="A0"), dict(arm="A0", cb="current"), dict(arm="A0", cb="staged"),
           dict(arm="A1"), dict(arm="A1", cb="current"), dict(arm="A1", cb="staged")],
    "H4": [dict(arm="A1"), dict(arm="A1", realloc=True)],
}
N_RANDOM = 1000


class Log:
    def __init__(self, path: Path):
        self.f = open(path, "w", encoding="utf-8")

    def __call__(self, msg: str):
        print(msg, flush=True)
        self.f.write(msg + "\n")
        self.f.flush()


def run_matrix(market, arms, periods, log, total=None, n_random=N_RANDOM, done=None):
    """설정 × 국면을 돌린다. 키 = (설정 이름, 국면). 장부 점검에 문제가 있으면 멈춘다."""
    out = {} if done is None else done
    md = S.get_market(market)
    for a in arms:
        for p in periods:
            cfg = S.Config(market=market, period=p, total=total,
                           n_random=n_random if (a == dict(arm="A1") and total is None) else 0, **a)
            key = (S.label(cfg), p)
            if key in out:
                continue
            t = time.time()
            r = S.run(cfg)
            bad = C.accounting(r, md, market)
            if bad:
                raise SystemExit(f"장부 점검 실패 {market} {key}: {bad[:3]}")
            out[key] = r
            log(f"  실행 {market:6s} {('$10k ' if total else '')}{key[0]:14s} {p:12s} {r['start']}~{r['end']} "
                f"({time.time() - t:.1f}s, 장부 OK)")
    return out


def summary_row(market, total_tag, key, r):
    m, refs = r["metrics"], r.get("refs", {})
    ev = {}
    for e in r["events"]:
        if e["kind"] != "H4" or e.get("changed"):
            ev[e["kind"]] = ev.get(e["kind"], 0) + 1
    row = {"market": market, "total": total_tag, "config": key[0], "period": key[1], "start": r["start"],
           "end": r["end"], "return": m["return"], "mdd": m["mdd"], "mdd_size": abs(m["mdd"]),
           "stock_frac_mean": m["stock_frac_mean"], "index_frac_mean": m["index_frac_mean"],
           "cash_frac_mean": m["cash_frac_mean"], "days_with_stock": m["days_with_stock"],
           "buys": m["buys"], "sells": m["sells"], "index_legs": m["index_legs"], "skips": m["skips"],
           "skip_zero_shares": m["skip_kinds"].get("0주", 0), "skip_cash_short": m["skip_kinds"].get("현금부족", 0),
           "over_slots": m["over_slots"], "cost_stock": m["cost_stock"], "tax_stock": m["tax_stock"],
           "cost_index": m["cost_index"], "costs_total": m["costs_total"], "interest": m["interest"],
           "events": json.dumps(ev, ensure_ascii=False)}
    for name, k in (("idx_bh_int", "index_bh"), ("idx_bh_frac", "index_bh_frac"), ("ew_bh", "ew_bh"), ("g11", "g11")):
        if k in refs:
            row[f"{name}_return"] = refs[k]["return"]
            row[f"{name}_mdd"] = refs[k]["mdd"]
    for k in ("vs_index_bh", "vs_index_bh_frac", "vs_ew_bh"):
        row[k] = m.get(k)
    return row


def write_outputs(out: Path, groups: dict, verdicts: dict, kr_dir: dict, pit_v, dry: bool, log):
    """groups = {(market, total_tag): {(config, period): result}}"""
    out.mkdir(parents=True, exist_ok=True)
    (out / "daily_full").mkdir(exist_ok=True)
    rows, rnd, trades, events, a6 = [], [], [], [], []
    for (market, tag), runs in groups.items():
        md = S.get_market(market)
        for key, r in runs.items():
            rows.append(summary_row(market, tag, key, r))
            run_id = f"{market}|{tag}|{key[0]}|{key[1]}"
            if r.get("random"):
                for g, v in r["random"].items():
                    if isinstance(v, dict):
                        rnd.append({"run": run_id, "group": g, **v})
            for t in r["trades"]:
                trades.append({"run": run_id, **{k: t[k] for k in ("sleeve", "code", "signal_date", "entry_date", "shares",
                                                                  "entry_price", "cap_budget", "cap", "cap_mult",
                                                                  "exit_signal_date", "exit_date", "exit_price",
                                                                  "exit_reason", "signal_reason") if k in t}})
            for e in r["events"]:
                events.append({"run": run_id, "date": e["date"], "kind": e["kind"], "sleeve": e.get("sleeve", ""),
                               "detail": json.dumps({k: v for k, v in e.items() if k not in ("date", "kind", "sleeve")},
                                                    ensure_ascii=False, default=str)})
            if key[1] == V.FULL or dry:                    # 전체 국면(B1 구간 재계산용); dry-run 은 그 국면
                cols = ["value", "stock_frac", "index_frac", "cash_frac", "interest", "costs", "n_buys", "n_sells",
                        "n_skips"] + [c for c in r["daily"].columns if c.startswith("v_")]
                fn = out / "daily_full" / f"{market}_{tag}_{key[0].replace(':', '-').replace('+', '_')}_{key[1]}.csv.gz"
                with gzip.open(fn, "wt", encoding="utf-8") as f:
                    r["daily"][cols].to_csv(f)
            if market == "kr" and key[0] in ("A0", "A1"):
                for code, v in S.a6_split_volume_buys(md, r).items():
                    a6.append({"run": run_id, "code": code, **v})

    def wcsv(name, recs):
        if not recs:
            return
        keys = list(dict.fromkeys(k for rec in recs for k in rec))
        opener = gzip.open if name.endswith(".gz") else open
        with opener(out / name, "wt", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for rec in recs:
                w.writerow(rec)
    wcsv("summary.csv", rows)
    wcsv("random.csv", rnd)
    wcsv("trades.csv.gz", trades)
    wcsv("events.csv", events)
    wcsv("a6.csv", a6)
    # 사람이 읽을 표
    lines = ["# R2 단계 2 결과표 (자동 생성: run_r2.py)" + (" — DRY-RUN, 숫자 의미 없음" if dry else ""), ""]

    def pct(x):
        return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x * 100:+.1f}%"
    for (market, tag) in groups:
        sub = [r for r in rows if r["market"] == market and r["total"] == tag]
        for per in dict.fromkeys(r["period"] for r in sub):
            lines += [f"## {market} {tag} — {per}", "",
                      "| 설정 | 수익률 | MDD | 주식 | 지수 | 현금 | 매수 | 보류(0주/현금) | 비용 | 이자 | 지수B&H(소수) | 지수B&H(정수) | 동일비중 | G11 |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for r in [x for x in sub if x["period"] == per]:
                lines.append(f"| {r['config']} | {pct(r['return'])} | {pct(r['mdd'])} | {r['stock_frac_mean'] * 100:.0f}% | "
                             f"{r['index_frac_mean'] * 100:.0f}% | {r['cash_frac_mean'] * 100:.0f}% | {r['buys']} | "
                             f"{r['skip_zero_shares']}/{r['skip_cash_short']} | {r['costs_total']:,.0f} | {r['interest']:,.0f} | "
                             f"{pct(r.get('idx_bh_frac_return'))} | {pct(r.get('idx_bh_int_return'))} | "
                             f"{pct(r.get('ew_bh_return'))} | {pct(r.get('g11_return'))} |")
            lines.append("")
    (out / "tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 판정
    blob = {"dry_run": dry, "us": verdicts, "kr_direction": kr_dir, "us_pit_h1": pit_v}
    (out / "verdicts.json").write_text(json.dumps(blob, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    title = "R2 판정" + (" — DRY-RUN(2018 한 국면을 모든 국면 이름에 붙인 것, 의미 없음)" if dry else "")
    if verdicts:
        (out / "VERDICTS.md").write_text(V.to_markdown(verdicts, kr_dir, pit_v, title), encoding="utf-8")
    log(f"출력: {out} — summary {len(rows)}줄, 거래 {len(trades)}건, 사건 {len(events)}건, 무작위 {len(rnd)}줄")


def alias_periods(runs: dict, src: str) -> dict:
    """dry-run 전용: 한 국면 결과를 모든 국면 이름에 붙여 판정 코드 길만 시험한다."""
    out = dict(runs)
    for (lab, p), r in runs.items():
        if p == src:
            for q in S.REGIMES:
                out.setdefault((lab, q), r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="2018 한 국면만, 확인 단계도 강제 — 코드 길 시험용")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    dry = a.dry_run
    out = Path(a.out) if a.out else (Path(tempfile.mkdtemp(prefix="r2_dryrun_")) if dry else HERE / "results")
    if not dry and out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} 가 비어 있지 않음 — 덮어쓰지 않는다")
    out.mkdir(parents=True, exist_ok=True)
    log = Log(out / "run_log.txt")
    periods = ["2018 조정"] if dry else list(S.REGIMES)
    t0 = time.time()
    log(f"R2 단계 2 {'DRY-RUN ' if dry else ''}시작 — 국면 {periods}")
    groups = {}
    log("1) 미국 전체 표")
    groups[("us", "100k")] = run_matrix("us", US_ARMS, periods, log)
    log("   $10,000 참고 (§7.0, 판정에 안 씀)")
    groups[("us", "10k")] = run_matrix("us", REF_10K, periods, log, total=10_000)
    us_runs = groups[("us", "100k")]
    vin = alias_periods(us_runs, periods[0]) if dry else us_runs
    log("2) 미국 판정 (verdict.py)")
    verdicts, kr_dir, pit_v = {}, {}, None
    try:
        verdicts = V.us_verdicts(vin)
    except ValueError as e:          # dry-run: B1 구간이 2018 데이터 밖이라 잴 수 없음
        if not dry:
            raise
        log(f"   dry-run: 판정 일부 건너뜀 ({type(e).__name__})")
        verdicts = {h: f(vin) for h, f in (("H1", V.h1), ("H2", V.h2), ("H3", V.h3))}
    plan = V.holdout_plan(verdicts) if (verdicts and "H4" in verdicts) else {"kr": [], "us_pit_h1": False}
    if dry:
        plan = {"kr": ["H1", "H2", "H3", "H4"], "us_pit_h1": True}        # 코드 길만 시험
        log("   dry-run: 확인 단계를 강제로 모두 돌림 (판정 값은 찍지 않음)")
    else:
        log(f"   미국 판정: " + ", ".join(f"{h} {'채택 후보' if v['adopt'] else '아님'}" for h, v in verdicts.items()))
    log(f"3) 7.5-1 국내: {plan['kr'] or '없음(미국 통과 가설 없음)'}")
    if plan["kr"]:
        arms = []
        for h in plan["kr"]:
            for x in HOLDOUT_ARMS[h]:
                if x not in arms:
                    arms.append(x)
        kr_runs = run_matrix("kr", arms, periods, log)
        groups[("kr", "100m")] = kr_runs
        kin = alias_periods(kr_runs, periods[0]) if dry else kr_runs
        for h in plan["kr"]:
            kr_dir[h] = V.kr_direction(h, kin)
        if not dry:
            log("   국내 방향: " + ", ".join(f"{h} {'같음' if c['pass'] else '다름'}" for h, c in kr_dir.items()))
    log(f"4) 7.5-2 us_pit H1: {'돌림' if plan['us_pit_h1'] else '안 돌림(H1 미통과)'}")
    if plan["us_pit_h1"]:
        pit_runs = run_matrix("us_pit", HOLDOUT_ARMS["H1"], periods, log)
        groups[("us_pit", "100k")] = pit_runs
        pin = alias_periods(pit_runs, periods[0]) if dry else pit_runs
        pit_v = V.pit_h1(pin)
    write_outputs(out, groups, verdicts, kr_dir, pit_v, dry, log)
    log(f"끝 ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
