"""
validate.py - 과최적화 점검 도구 ⚠️ 규칙/파라미터를 바꿀 때마다 돌릴 것
------------------------------------------------------------------
"지금 값이 과거 데이터에 끼워맞춘(overfit) 건 아닌가?"를 자동으로 점검한다. 두 가지:

 1) 국면 리포트: 지금 채택값이 여러 시장 국면(2018 조정/2020 폭락/2022 약세장/2023~)에서
    버티는지. 한 국면만 좋고 다른 국면에서 무너지면 위험.
 2) 교차-시대 감사: 서로 다른 시대(2018~2022 vs 2023~)에 각각 튜닝했을 때, 지금 채택값이
    양쪽에서 상위로 뽑히는지. 한 시대만 상위면 '그 시대 과최적화' → ⚠️ 경고.

실행: python validate.py   (main.py 와 같은 라이브러리 필요, 시간이 좀 걸림)

원칙: 과거 검증은 끝이 있다. 여기까지 통과해도 '과거'일 뿐 — 진짜 판정은 live.py 포워드 검증.
"""

import main
import tune
from sprinter_brain import SprinterBrain
from marathoner_brain import MarathonerBrain
from pioneer_brain import PioneerBrain
from risk_guard import CircuitBreaker

# 2018년부터 역사가 있는 분산된 종목 (국면 리포트용)
STOCKS = {   # v1 미국 전용(D4)
    "알파벳": "GOOGL", "JP모건": "JPM", "엑슨모빌": "XOM", "존슨앤존슨": "JNJ",
    "애플": "AAPL", "MS": "MSFT", "엔비디아": "NVDA", "테슬라": "TSLA",
    "메타": "META", "아마존": "AMZN",
}
AUDIT_STOCKS = {"애플": "AAPL", "MS": "MSFT", "엔비디아": "NVDA",
                "알파벳": "GOOGL", "아마존": "AMZN"}  # 튜닝 감사(느려서 5개, main.py 종목과 같음)

REGIMES = {
    "2018 조정":       ("2018-01-01", "2019-06-30"),
    "2020 코로나폭락":  ("2019-06-01", "2021-06-30"),
    "2022 약세장":      ("2021-06-01", "2023-06-30"),
    "2023~ 상승":       ("2023-01-01", "2026-12-31"),
    "전체(2018~)":      ("2018-01-01", "2026-12-31"),
}
ERAS = {"2018~2022": ("2018-01-01", "2022-12-31"),
        "2023~이후":  ("2023-01-01", "2026-12-31")}

BRAINS = {"마라토너": MarathonerBrain, "스프린터": SprinterBrain, "파이오니어": PioneerBrain}

_CACHE = {}
FAILURES = []   # 실패 기록: {"단계", "대상", "사유"}. 끝에 tune.print_failure_summary 로 요약.


def _full(code, loader=None):
    """종목별 2018~ 전체 시세를 한 번만 받아 캐시. 실패도 캐시해서 같은 종목을 매번 다시 받지 않는다.
    loader: 시세 받는 함수(기본은 지금의 main.load_prices)."""
    if code not in _CACHE:
        try:
            df = (loader or main.load_prices)(code, "2018-01-01")
            if df is None or len(df) == 0:
                raise ValueError("데이터 0행")
            _CACHE[code] = df
        except Exception as e:
            _CACHE[code] = e
    hit = _CACHE[code]
    if isinstance(hit, Exception):
        raise hit
    return hit


def regime_report(failures=None):
    """국면별 성적. (국면, 트레이너, 종목) 하나가 실패하거나 NaN 이어도 기록만 하고 계속."""
    failures = FAILURES if failures is None else failures
    print("\n" + "#" * 72 + "\n# 1) 국면 리포트 — 지금 채택값이 여러 시장에서 버티나\n" + "#" * 72)
    total = main.CONFIG["총_가상자금"]; ratios = main.CONFIG["배분비율"]; caps = main.CONFIG["종목상한"]
    cbc = main.CONFIG["서킷브레이커"]; breaker = CircuitBreaker(cbc["누적한도"], cbc["일일한도"])
    for regime, (s, e) in REGIMES.items():
        print(f"\n[{regime}]  {s} ~ {e}")
        print(f"  {'트레이너':<8}{'평균수익률':>10}{'최악MDD':>9}{'손실종목':>9}{'서킷발동':>9}")
        for tname, cls in BRAINS.items():
            cash = int(total * ratios[tname]); cap = caps[tname]
            rets, mdds, losers, stopped = [], [], 0, 0
            bad = []   # 이 칸에서 계산 못 한 종목
            need = 60 if cls is MarathonerBrain else 20
            for sname, code in STOCKS.items():
                try:
                    seg = _full(code).loc[s:e]
                    if len(seg) < need + 5:
                        continue   # 기간이 짧은 건 실패가 아니라 '해당 없음'
                    r = main.run_one_trainer(tname, cls(), seg, cash, cap, code, breaker)
                    why = tune._check_result(r, "")
                    if why:
                        raise ValueError(why.strip())
                except Exception as ex:   # 이 종목만 빼고 계속
                    why = tune.reason_of(ex)
                    tune.record(failures, f"국면 {regime}/{tname}", sname, why)
                    bad.append(sname)
                    continue
                ret = r["profit"] / cash * 100
                rets.append(ret); mdds.append(r["mdd"] * 100)
                losers += ret < 0; stopped += bool(r["stopped"])
            note = f"  (계산 불가 {len(bad)}종목: {', '.join(bad)})" if bad else ""
            if rets:
                print(f"  {tname:<8}{sum(rets)/len(rets):>+9.1f}%{min(mdds):>8.1f}%"
                      f"{losers:>6}/{len(rets)}{stopped:>6}/{len(rets)}{note}")
            elif bad:
                print(f"  {tname:<8}{tune.unavailable('모든 종목 실패')}{note}")


def _audit_era(name, era, failures):
    """한 (트레이너, 시대)의 감사 한 줄. 돌려주는 값: (era, 지금값 검증손익, 순위, 조합수) 또는 None."""
    rows = tune.tune_one(name, failures)
    ok_rows = [r for r in rows if not isinstance(r["검증_순손익"], str)]
    if not ok_rows:
        raise ValueError("계산된 조합 0개")
    top = ok_rows[0]
    key = [k for k in top if k not in tune.METRIC_KEYS]
    top_s = ", ".join(f"{k}={top[k]}" for k in key)
    print(f"  {era}: 최고=[{top_s}] 검증 {tune.fmt_money(top['검증_순손익'])}  ({top['계산_종목수']}종목)")
    base = next((r for r in rows if r["기본값"] == "예"), None)
    if base is None:
        return None
    if isinstance(base["검증_순손익"], str):
        print(f"          ★지금값 {base['검증_순손익']}")
        tune.record(failures, f"감사 {name}/{era}", "지금값", base["검증_순손익"])
        return None
    rank = rows.index(base) + 1
    print(f"          ★지금값 {rank}/{len(rows)}등, 검증 {tune.fmt_money(base['검증_순손익'])}")
    return (era, base["검증_순손익"], rank, len(rows))


def overfit_audit(failures=None):
    """시대별 튜닝 순위 감사. (트레이너, 시대) 하나가 실패해도 다음으로 넘어간다."""
    failures = FAILURES if failures is None else failures
    print("\n" + "#" * 72 + "\n# 2) 교차-시대 감사 — 지금 값이 '그 시대 과최적화'는 아닌가\n" + "#" * 72)
    orig_load = main.load_prices
    orig_list = main.CONFIG["종목목록"]
    main.CONFIG["종목목록"] = dict(AUDIT_STOCKS)
    cur = [None, None]
    main.load_prices = lambda code, start, *a, **k: _full(code, orig_load).loc[cur[0]:cur[1]]
    try:
        for name in tune.GRIDS:
            print(f"\n[{name}] 시대별 최고 조합 vs 지금 채택값(★) 순위")
            base_profits = []
            for era, (s, e) in ERAS.items():
                cur[0], cur[1] = s, e
                try:
                    got = _audit_era(name, era, failures)
                except Exception as ex:   # 이 시대만 계산 불가로 두고 계속
                    tune.record(failures, f"감사 {name}", era, tune.reason_of(ex))
                    print(f"  {era}: {tune.unavailable(tune.reason_of(ex))}")
                    continue
                if got:
                    base_profits.append(got)
            # 과최적화 경고: 어느 시대든 지금값이 손실이거나 하위권이면 의심
            warn = [era for era, p, rk, n in base_profits if p < 0 or rk > n * 0.5]
            if warn:
                print(f"  ⚠️ 과최적화 의심: {', '.join(warn)} 에서 지금값이 손실 또는 하위권. 재검토 필요.")
            if len(base_profits) < len(ERAS):
                # 계산 못 한 시대가 있으면 '모두 통과'라고 말할 수 없다
                print(f"  ❔ 판정 보류: {len(ERAS)}개 시대 중 {len(base_profits)}개만 계산됐어요.")
            elif not warn:
                print("  ✅ 모든 시대에서 지금값이 흑자+상위권 — 국면에 안 휘둘림.")
    finally:
        main.load_prices = orig_load
        main.CONFIG["종목목록"] = orig_list


def run_all(failures=None):
    """국면 리포트 → 교차-시대 감사 → 실패 요약. 실패 목록을 돌려준다."""
    failures = FAILURES if failures is None else failures
    for step in (regime_report, overfit_audit):
        try:
            step(failures)
        except Exception as ex:   # 단계 전체가 터져도 다음 단계는 돈다
            tune.record(failures, step.__name__, "전체", tune.reason_of(ex))
            print(f"\n{tune.unavailable(tune.reason_of(ex))} — 다음 단계로 넘어갑니다.")
    tune.print_failure_summary(failures, "검증 실패 요약")
    return failures


if __name__ == "__main__":
    print("데이터 받는 중(10종목, 2018~)...", flush=True)
    run_all()
    print("\n※ 과거 검증일 뿐 미래 보장 아님. 규칙 바꿀 때마다 이걸 돌리고, 최종은 live.py 포워드 검증.")
