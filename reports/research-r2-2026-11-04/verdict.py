"""
R2 단계 2 판정식 (사전 등록 §7 + 보완 B1·B8·B9) — 결과를 보기 전에 코드로 정해 둔다
====================================================================================
입력: sim_team.run() 결과 dict 들을 {(설정 이름, 국면 이름): 결과} 로 모은 것.
      설정 이름 = sim_team.label(cfg): "A0", "A1", "A1T", "A2", "IDX", "A0+CB:current", "A0+CB:staged",
                  "A1+CB:current", "A1+CB:staged", "A1+H4"
      국면 이름 = sim_team.REGIMES 의 키 ("전체 2015-26" 등)
출력: 기준마다 {"pass": bool, "numbers": {쓴 숫자}, "rule": "사전 등록 문구"} 와 가설별 채택 여부·해석 문장.

판정에 쓰는 결과 칸(이것만 읽는다 — check_team.py 의 손으로 만든 dict 시험이 이 칸만 채운다):
  r["metrics"]["return"], r["metrics"]["mdd"](음수), r["daily"]["value"](날짜 문자열 → 종가 평가액),
  r["refs"]["index_bh_frac"]["return"/"mdd"], r["refs"]["index_bh"]["return"/"mdd"], r.get("random")

정해 둔 것 (B8 + 이 파일의 선택 V1~V4)
  - B8①  MDD 는 크기(절댓값)로 비교한다. "MDD 가 작다" = 덜 빠졌다.
  - B8②  B1 구간 수익률 = 구간 마지막 종가 평가액 ÷ 구간 첫 거래일 전날 종가 평가액 − 1 (매도 비용 빼지 않음, 두 실행 같은 식)
  - B9   "시장에 안 짐"의 지수 B&H 는 소수 단위(index_bh_frac). 정수 단위(index_bh) 값도 같이 적는다.
  - V1   H1 기준 3 의 "SPY B&H MDD" 도 소수 단위 B&H 로 잰다(A1 과 같은 기준, B9 와 같은 이유). 정수 단위로 했을 때
         판정이 달라지면 "민감"으로 표시한다.
  - V2   국내(7.5-1) "미국과 방향이 같다" = 그 가설의 핵심 차이가 국내에서도 0보다 크다.
         H1: 전체 A1 − A0 (사전 등록 예시 그대로)   H2: 2022 국면 A1-T − A1 (기준 1, H2 를 하는 이유)
         H3: A0·A1 둘 다 (가)−(다) MDD 크기 > 0 그리고 (다) − (나) 수익률 > 0   H4: 전체 H4 − H1
         (사전 등록은 H1 예시만 준다 — 나머지는 이 파일에서 정한 것, 결과 보기 전 커밋)
  - V3   us_pit(7.5-2)은 H1 기준 1~3 과 "시장에 안 짐"을 같은 식으로 계산해 보고하고, 방향(전체 A1 > A0)을 따로 적는다.
  - V4   H1 기준 4(트레이너 기여 백분위)는 판정에 쓰지 않는다. "50% 근처" 문턱은 사전 등록에 숫자가 없어 정하지 않고
         백분위만 그대로 낸다(문장은 사람이 쓴다).
"""
from __future__ import annotations

FULL = "전체 2015-26"
UP_REGIMES = ("2015-17 상승", "2020 급락·회복", "2023-26 상승")      # H1 기준 2
H2_DOWN = "2022 하락"                                                 # H2 기준 1
H2_WHIPSAW = "2020 급락·회복"                                         # H2 보고만
B1_WINDOWS = (("2020", "2020-01-02", "2020-12-31"),                   # B1: 전체 실행 안의 같은 달력 구간
              ("2022", "2022-01-03", "2022-12-30"),
              ("2023-26", "2023-01-03", "2026-11-03"))
H3_BASES = ("A0", "A1")


# ---------------------------------------------------------------- 작은 도구
def _run(runs: dict, label: str, period: str) -> dict:
    try:
        return runs[(label, period)]
    except KeyError:
        raise KeyError(f"판정에 필요한 실행이 없음: ({label}, {period})") from None


def ret(r: dict) -> float:
    return float(r["metrics"]["return"])


def mdd_size(r: dict) -> float:
    """B8①: MDD 크기(양수). metrics.max_drawdown 은 음수(예 -0.20)를 준다."""
    return abs(float(r["metrics"]["mdd"]))


def bh(r: dict, kind: str = "frac") -> dict:
    """지수 B&H 참고선. kind="frac" 소수 단위(B9 판정용), "int" 정수 단위(R0 방식, 같이 적는 값)."""
    return r["refs"]["index_bh_frac" if kind == "frac" else "index_bh"]


def window_return(r: dict, start: str, end: str) -> float:
    """B8②: 구간 마지막 종가 평가액 ÷ 구간 첫 거래일 전날 종가 평가액 − 1 (r["daily"]["value"], 매도 비용 없음)."""
    v = r["daily"]["value"]
    dates = list(v.index)
    inside = [d for d in dates if start <= d <= end]
    before = [d for d in dates if d < start]
    if not inside or not before:
        raise ValueError(f"구간 {start}~{end} 를 이 실행의 일별 기록으로 잴 수 없음")
    return float(v[inside[-1]]) / float(v[before[-1]]) - 1


def _crit(ok: bool, rule: str, **numbers) -> dict:
    return {"pass": bool(ok), "rule": rule, "numbers": numbers}


# ---------------------------------------------------------------- H1
def h1(runs: dict) -> dict:
    a0, a1, a2 = (_run(runs, k, FULL) for k in ("A0", "A1", "A2"))
    c1 = _crit(ret(a1) > ret(a0) and ret(a1) >= ret(a2),
               "전체 2015-26 수익률: A1 > A0 그리고 A1 ≥ A2",
               A1=ret(a1), A0=ret(a0), A2=ret(a2))
    wins = {p: ret(_run(runs, "A1", p)) > ret(_run(runs, "A0", p)) for p in UP_REGIMES}
    c2 = _crit(sum(wins.values()) >= 2, "상승 국면 3개(2015-17, 2020, 2023-26) 중 2개 이상에서 A1 > A0",
               **{f"A1>A0 {p}": w for p, w in wins.items()},
               **{f"A1 {p}": ret(_run(runs, "A1", p)) for p in UP_REGIMES},
               **{f"A0 {p}": ret(_run(runs, "A0", p)) for p in UP_REGIMES})
    gap_frac = mdd_size(a1) - abs(bh(a1, "frac")["mdd"])
    gap_int = mdd_size(a1) - abs(bh(a1, "int")["mdd"])
    c3 = _crit(gap_frac <= 0.05, "전체 MDD: A1 의 MDD 가 SPY B&H MDD 보다 5%p 넘게 나쁘지 않다 (크기 비교, V1 소수 단위 B&H)",
               A1_mdd_size=mdd_size(a1), bh_frac_mdd_size=abs(bh(a1, "frac")["mdd"]),
               bh_int_mdd_size=abs(bh(a1, "int")["mdd"]), gap_frac=gap_frac, gap_int=gap_int,
               sensitive=(gap_frac <= 0.05) != (gap_int <= 0.05))
    not_lost = _crit(ret(a1) >= bh(a1, "frac")["return"],
                     "시장에 안 짐(별도 보고): 전체 A1 수익률 ≥ SPY B&H 수익률 (B9 소수 단위)",
                     A1=ret(a1), bh_frac=bh(a1, "frac")["return"], bh_int=bh(a1, "int")["return"],
                     pass_if_int=ret(a1) >= bh(a1, "int")["return"])
    item4 = a1.get("random")
    item4_report = None
    if item4:
        item4_report = {g: {"pct_below": v["pct_below"], "pct_le": v["pct_le"], "actual": v["actual"],
                            "random_mean": v["random_mean"], "trades": v["trades"]}
                        for g, v in item4.items() if isinstance(v, dict)}
    adopt = c1["pass"] and c2["pass"] and c3["pass"]
    if not c1["pass"]:
        note = ("기준 1 실패: 쉬는 돈을 지수에 둬도 A0보다 못하거나 A2보다 못하다 → 문제는 cash drag 가 아니라 "
                "트레이너 매매 자체가 지수보다 못한 것. 세 트레이너 규칙을 바꾸지 않는 한 구조 유지로는 시장을 못 따라간다.")
    elif not c2["pass"] and c3["pass"]:
        note = "기준 2만 실패: 효과가 한 국면에 몰렸다 → 채택 보류."
    elif adopt:
        note = "기준 1~3 모두 통과 → 채택 후보(7.5 확인 단계 필요)."
    else:
        note = "기준을 모두 충족하지 못함 → 채택하지 않음."
    return {"hypothesis": "H1", "criteria": {"1": c1, "2": c2, "3": c3}, "adopt": adopt, "not_lost": not_lost,
            "item4_report_only": item4_report, "note": note}


# ---------------------------------------------------------------- H2
def h2(runs: dict) -> dict:
    t22, a22 = _run(runs, "A1T", H2_DOWN), _run(runs, "A1", H2_DOWN)
    c1 = _crit(ret(t22) - ret(a22) >= 0.05, "2022 하락 국면 손실: A1-T 가 A1 보다 5%p 이상 덜 잃는다",
               A1T=ret(t22), A1=ret(a22), diff=ret(t22) - ret(a22))
    tf, af, a2f = (_run(runs, k, FULL) for k in ("A1T", "A1", "A2"))
    c2 = _crit(ret(tf) >= ret(a2f) and ret(tf) >= 0.9 * ret(af),
               "전체 2015-26 수익률: A1-T ≥ A2 그리고 A1-T ≥ A1 × 0.9 (글자 그대로; A1 이 음수면 더 엄격해짐)",
               A1T=ret(tf), A2=ret(a2f), A1=ret(af), A1_x09=0.9 * ret(af), A1_negative=ret(af) < 0)
    c3 = _crit(mdd_size(tf) < mdd_size(af), "전체 MDD: A1-T < A1 (크기 비교)",
               A1T_mdd_size=mdd_size(tf), A1_mdd_size=mdd_size(af))
    w20 = ret(_run(runs, "A1T", H2_WHIPSAW)) - ret(_run(runs, "A1", H2_WHIPSAW))
    adopt = c1["pass"] and c2["pass"] and c3["pass"]
    if c1["pass"] and not c2["pass"]:
        note = "기준 1은 되는데 2가 안 됨: 보험료가 너무 비싸다 → H1 만 채택 후보로 둔다."
    elif not c1["pass"]:
        note = "기준 1 실패: 필터가 늦어서 쓸모없음 → 폐기."
    elif adopt:
        note = "기준 1~3 모두 통과 → H1 보다 우선하는 채택 후보(7.5 확인 단계 필요)."
    else:
        note = "기준 3 실패 → 채택하지 않음."
    return {"hypothesis": "H2", "criteria": {"1": c1, "2": c2, "3": c3}, "adopt": adopt,
            "report_2020_whipsaw": {"A1T_minus_A1": w20, "note": "판정에는 안 씀"}, "note": note}


# ---------------------------------------------------------------- H3
def h3(runs: dict) -> dict:
    per_base, ok_mdd, ok_ret = {}, True, True
    for b in H3_BASES:
        ga, na, da = (_run(runs, k, FULL) for k in (b, f"{b}+CB:current", f"{b}+CB:staged"))
        red = mdd_size(ga) - mdd_size(da)
        m = red >= 0.03
        rr = ret(da) > ret(na)
        ok_mdd &= m
        ok_ret &= rr
        per_base[b] = _crit(m and rr, "(다)의 전체 MDD가 (가)보다 3%p 이상 작고(크기), 전체 수익률이 (나)보다 높다",
                            mdd_size_none=mdd_size(ga), mdd_size_staged=mdd_size(da), mdd_reduction=red,
                            ret_current=ret(na), ret_staged=ret(da), mdd_ok=m, ret_ok=rr)
    adopt = ok_mdd and ok_ret
    if not ok_mdd:
        note = "MDD 를 못 줄임 → 폐기."
    elif not ok_ret:
        note = "수익이 (나)보다 낮음 → 지금 서킷 유지."
    else:
        note = "A0·A1 둘 다 통과."
    note += " (D6 은 원래 저장소 공동작업자와 합의할 사항 → 결과는 제안 자료로만)"
    return {"hypothesis": "H3", "criteria": per_base, "adopt": adopt, "note": note}


# ---------------------------------------------------------------- H4
def h4(runs: dict) -> dict:
    hf, af = _run(runs, "A1+H4", FULL), _run(runs, "A1", FULL)
    c1 = _crit(ret(hf) > ret(af), "전체 2015-26 수익률이 H1 보다 높다", H4=ret(hf), H1=ret(af))
    wins, nums = 0, {}
    for name, s, e in B1_WINDOWS:
        wh, wa = window_return(hf, s, e), window_return(af, s, e)
        nums[f"H4 {name}"], nums[f"H1 {name}"] = wh, wa
        nums[f"H4>H1 {name}"] = wh > wa
        wins += wh > wa
    c2 = _crit(wins >= 2, "B1: 전체 실행 안의 2020·2022·2023-26 구간 수익률 중 2개 이상에서 H4 > H1 (종가 평가액, B8②)",
               **nums)
    adopt = c1["pass"] and c2["pass"]
    note = ("통과 → 채택 후보(7.5 확인 단계 필요)." if adopt else
            "실패(예상): 60/30/10 고정을 유지하고 '성과 기반 재배분은 우리 데이터에서 득이 없다'를 기록한다.")
    return {"hypothesis": "H4", "criteria": {"1": c1, "2_B1": c2}, "adopt": adopt, "note": note}


def us_verdicts(runs: dict) -> dict:
    return {"H1": h1(runs), "H2": h2(runs), "H3": h3(runs), "H4": h4(runs)}


def holdout_plan(us: dict) -> dict:
    """7.5: 미국에서 통과(채택 후보)한 것만 국내로. 생존편향 확인(us_pit H1)은 H1 통과 여부와 상관없이 항상(B10)."""
    passed = [h for h in ("H1", "H2", "H3", "H4") if us[h]["adopt"]]
    return {"kr": passed, "us_pit_h1": True}


# ---------------------------------------------------------------- 7.5 확인 단계
def kr_direction(hyp: str, kr_runs: dict) -> dict:
    """7.5-1 (V2): 국내에서도 미국과 같은 방향인가."""
    if hyp == "H1":
        d = ret(_run(kr_runs, "A1", FULL)) - ret(_run(kr_runs, "A0", FULL))
        return _crit(d > 0, "국내 전체 A1 > A0", diff=d)
    if hyp == "H2":
        d = ret(_run(kr_runs, "A1T", H2_DOWN)) - ret(_run(kr_runs, "A1", H2_DOWN))
        return _crit(d > 0, "국내 2022 A1-T 가 A1 보다 덜 잃음", diff=d)
    if hyp == "H3":
        nums, ok = {}, True
        for b in H3_BASES:
            red = mdd_size(_run(kr_runs, b, FULL)) - mdd_size(_run(kr_runs, f"{b}+CB:staged", FULL))
            rr = ret(_run(kr_runs, f"{b}+CB:staged", FULL)) - ret(_run(kr_runs, f"{b}+CB:current", FULL))
            nums[f"{b} mdd_reduction"], nums[f"{b} staged_minus_current"] = red, rr
            ok &= red > 0 and rr > 0
        return _crit(ok, "국내 A0·A1 모두 (다)가 (가)보다 덜 빠지고 (나)보다 수익률 높음", **nums)
    if hyp == "H4":
        d = ret(_run(kr_runs, "A1+H4", FULL)) - ret(_run(kr_runs, "A1", FULL))
        return _crit(d > 0, "국내 전체 H4 > H1", diff=d)
    raise ValueError(hyp)


def pit_h1(pit_runs: dict) -> dict:
    """7.5-2 (V3): 2014말 시총 상위 20 종목군으로 H1 다시."""
    v = h1(pit_runs)
    d = ret(_run(pit_runs, "A1", FULL)) - ret(_run(pit_runs, "A0", FULL))
    v["direction"] = _crit(d > 0, "us_pit 전체 A1 > A0", diff=d)
    return v


def to_markdown(us: dict, kr: dict | None = None, pit: dict | None = None, title: str = "R2 판정") -> str:
    """판정 결과를 사람이 읽을 표로 (숫자는 소수 4자리)."""
    def fmt(x):
        return f"{x:.4f}" if isinstance(x, float) else str(x)
    lines = [f"# {title}", ""]
    for h, v in us.items():
        lines += [f"## {h} — 채택 후보: {'예' if v['adopt'] else '아니오'}", "", v["note"], ""]
        lines += ["| 기준 | 통과 | 규칙 | 쓴 숫자 |", "|---|---|---|---|"]
        for k, c in v["criteria"].items():
            nums = "; ".join(f"{a}={fmt(b)}" for a, b in c["numbers"].items())
            lines.append(f"| {k} | {'PASS' if c['pass'] else 'FAIL'} | {c['rule']} | {nums} |")
        for extra in ("not_lost",):
            if extra in v:
                c = v[extra]
                nums = "; ".join(f"{a}={fmt(b)}" for a, b in c["numbers"].items())
                lines.append(f"| {extra} | {'PASS' if c['pass'] else 'FAIL'} | {c['rule']} | {nums} |")
        lines.append("")
    if kr:
        lines += ["## 7.5-1 국내 방향 확인", "", "| 가설 | 같은 방향 | 규칙 | 숫자 |", "|---|---|---|---|"]
        for h, c in kr.items():
            nums = "; ".join(f"{a}={fmt(b)}" for a, b in c["numbers"].items())
            lines.append(f"| {h} | {'PASS' if c['pass'] else 'FAIL'} | {c['rule']} | {nums} |")
        lines.append("")
    if pit:
        lines += ["## 7.5-2 생존편향 확인 (us_pit, H1)", "", pit["note"], ""]
        for k, c in list(pit["criteria"].items()) + [("not_lost", pit["not_lost"]), ("direction", pit["direction"])]:
            nums = "; ".join(f"{a}={fmt(b)}" for a, b in c["numbers"].items())
            lines.append(f"- {k}: {'PASS' if c['pass'] else 'FAIL'} — {c['rule']} — {nums}")
        lines.append("")
    return "\n".join(lines) + "\n"
