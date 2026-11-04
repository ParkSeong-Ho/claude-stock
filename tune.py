"""
파라미터 튜닝 - 여러 값을 과거 데이터로 쓸어보고 성적을 '기록'한다.
------------------------------------------------------------------
과최적화를 막으려고 기간을 둘로 나눈다:
  - 훈련(train, 앞 60%): 여기서 좋은 값을 고른다
  - 검증(test, 뒤 40%): 그 값이 '안 본 기간'에서도 좋은지 확인한다
훈련만 좋고 검증이 나쁘면 = 과거에 끼워맞춘 것(overfit). 검증까지 좋아야 채택.

루프마다 나온 성적표를 버리지 않고 results/tune_*.csv 에 전부 남긴다.
표는 검증(out-of-sample) 순손익 높은 순으로 정렬한다.

⚠️ 검증까지 좋아도 미래 보장은 아니다. 고른 값은 live.py 로 포워드 검증할 것.

실행: python tune.py   (main.py 와 같은 라이브러리 필요)
"""

import csv
import inspect
import itertools
import math

import main
from sprinter_brain import SprinterBrain
from pioneer_brain import PioneerBrain
from risk_guard import CircuitBreaker

TRAIN_RATIO = 0.6   # 앞 60%로 값 고르고, 뒤 40%로 재확인

# ===== 쓸어볼 값들 (여기 숫자만 바꾸면 됨) =====
GRIDS = {
    "스프린터": {   # 진입 문턱을 높여 매매 횟수를 줄이고 수수료를 이기는지 탐색
        "class": SprinterBrain,
        "params": {
            "take_profit":    [0.03, 0.05],
            "stop_loss":      [0.015, 0.02],
            "cross_lookback": [1, 3],           # 1=신선한 크로스만(매매 줄임)
            "rsi_floor":      [0, 45, 50, 55],  # 진입 문턱: 약한 기세 매수 차단
        },
    },
    "파이오니어": {  # 5종목·train/test로 35/1.5 완화가 견고한지 재확인
        "class": PioneerBrain,
        "params": {
            "volume_surge": [1.3, 1.5, 1.8],
            "rsi_oversold": [30, 35, 40],
            "take_profit":  [0.10],
            "stop_loss":    [0.05],
        },
    },
}
# ==============================================


def _combos(params):
    keys = list(params)
    for vals in itertools.product(*(params[k] for k in keys)):
        yield dict(zip(keys, vals))


def _defaults(cls):
    return {k: v.default for k, v in inspect.signature(cls.__init__).parameters.items()
            if v.default is not inspect.Parameter.empty}


# ===== 실패 처리 도우미 =====
# 조합 하나, 종목 하나가 실패(예외)하거나 NaN을 내도 전체를 멈추지 않는다.
# 실패는 '계산 불가(사유)'로 기록하고 다음으로 넘어간 뒤, 끝에 몇 개가 왜 실패했는지 요약한다.
METRIC_KEYS = ("훈련_순손익", "훈련_MDD%", "검증_순손익", "검증_MDD%",
               "검증_매수", "검증_승률%", "검증_정지", "계산_종목수", "제외_종목", "기본값")


def is_nan(x):
    """None 이거나 숫자 NaN 이면 True. (문자열 등은 False)"""
    if x is None:
        return True
    try:
        return math.isnan(float(x))
    except (TypeError, ValueError):
        return False


def reason_of(e):
    """예외를 사람이 읽을 한 줄 사유로. 예: 'ValueError: 데이터 없음'"""
    msg = str(e).strip().splitlines()[0] if str(e).strip() else ""
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def unavailable(reason):
    """CSV·화면에 찍을 '계산 불가(사유)' 문자열."""
    return f"계산 불가({reason})"


def record(failures, stage, target, reason):
    """실패 한 건을 목록에 남긴다. failures 가 None 이면 버린다."""
    if failures is not None:
        failures.append({"단계": stage, "대상": target, "사유": reason})


def fmt_money(v):
    """숫자면 천 단위 쉼표, 아니면(계산 불가 등) 그대로."""
    return f"{v:,}" if isinstance(v, (int, float)) and not is_nan(v) else str(v)


def print_failure_summary(failures, title="실패 요약"):
    """끝에 실패 요약: 몇 개, 어떤 것, 왜."""
    print("\n" + "-" * 68)
    if not failures:
        print(f" {title}: 실패 0건 — 모든 단위가 정상 계산됐어요.")
        print("-" * 68)
        return
    print(f" {title}: 실패 {len(failures)}건 (해당 단위는 '계산 불가'로 기록하고 계속했어요)")
    # 같은 사유끼리 묶어서 보여준다
    groups = {}
    for f in failures:
        groups.setdefault(f["사유"], []).append(f"{f['단계']}/{f['대상']}")
    for reason, items in groups.items():
        shown = ", ".join(items[:5]) + (f" 외 {len(items) - 5}개" if len(items) > 5 else "")
        print(f"  - {len(items)}건  사유: {reason}")
        print(f"      대상: {shown}")
    print("-" * 68)


def _check_result(r, label):
    """run_one_trainer 결과에 NaN 이 있으면 사유 문자열, 정상이면 None."""
    for key, kor in (("profit", "순손익"), ("mdd", "MDD")):
        if is_nan(r.get(key)):
            return f"{label} {kor} NaN"
    return None


def load_split(name, failures=None):
    """종목목록 전체를 한 번씩 받아 훈련/검증으로 쪼갠다. 받기 실패한 종목은 기록하고 뺀다."""
    stocks = {}
    for 종목명, code in main.CONFIG["종목목록"].items():
        try:
            df = main.load_prices(code, main.CONFIG["시작일"])
            if df is None or len(df) == 0:
                raise ValueError("데이터 0행")
        except Exception as e:  # 한 종목이 실패해도 나머지로 계속
            record(failures, f"{name} 데이터", 종목명, reason_of(e))
            continue
        split = int(len(df) * TRAIN_RATIO)
        stocks[종목명] = (code, df.iloc[:split], df.iloc[split:])
    return stocks


def tune_one(name, failures=None, params=None):
    """이 트레이너의 모든 값 조합을 종목 전체에 돌려, 훈련·검증 성적을 각각 집계.
    failures: 실패 기록을 모을 리스트(선택). 실패한 (조합, 종목)은 그 조합 합계에서 빼고
              '제외_종목' 칸과 failures 에 사유를 남긴다. 모든 종목이 실패한 조합은 숫자 칸이 '계산 불가(사유)'.
    params:   탐색 격자를 바꿔 끼울 때(테스트용). 없으면 GRIDS 그대로."""
    spec = GRIDS[name]
    cls = spec["class"]
    grid = params if params is not None else spec["params"]
    cash = int(main.CONFIG["총_가상자금"] * main.CONFIG["배분비율"][name])
    cap = main.CONFIG["종목상한"][name]
    cb = main.CONFIG["서킷브레이커"]
    breaker = CircuitBreaker(cb["누적한도"], cb["일일한도"])
    defaults = _defaults(cls)

    # 데이터는 종목당 한 번만 로드하고 훈련/검증으로 쪼갠다
    stocks = load_split(name, failures)

    rows = []
    for combo in _combos(grid):
        tr_profit = te_profit = 0.0
        tr_mdd = te_mdd = 0.0
        te_buys = te_closed = te_wins = te_stopped = 0
        ok = 0
        skipped = []   # 이 조합에서 계산 못 한 종목과 사유
        combo_s = ",".join(f"{k}={v}" for k, v in combo.items())
        for 종목명, (code, train_df, test_df) in stocks.items():
            try:
                rt = main.run_one_trainer(name, cls(**combo), train_df, cash, cap, code, breaker)
                rv = main.run_one_trainer(name, cls(**combo), test_df, cash, cap, code, breaker)
                bad = _check_result(rt, "훈련") or _check_result(rv, "검증")
            except Exception as e:  # 이 (조합, 종목)만 포기하고 계속
                bad = reason_of(e)
            if bad:
                skipped.append(f"{종목명}:{bad}")
                record(failures, f"{name} [{combo_s}]", 종목명, bad)
                continue
            ok += 1
            tr_profit += rt["profit"]; tr_mdd = min(tr_mdd, rt["mdd"])
            te_profit += rv["profit"]; te_mdd = min(te_mdd, rv["mdd"])
            te_buys += rv["buys"]; te_closed += rv["closed"]; te_wins += rv["wins"]
            te_stopped += 1 if rv["stopped"] else 0
        row = {**combo}
        if ok:
            row.update({
                "훈련_순손익": round(tr_profit), "훈련_MDD%": round(tr_mdd * 100, 1),
                "검증_순손익": round(te_profit), "검증_MDD%": round(te_mdd * 100, 1),
                "검증_매수": te_buys,
                "검증_승률%": round(te_wins / te_closed * 100, 1) if te_closed else "",
                "검증_정지": te_stopped,
            })
        else:
            why = unavailable("계산된 종목 0개" if not stocks else "모든 종목 실패")
            row.update({k: why for k in ("훈련_순손익", "훈련_MDD%", "검증_순손익", "검증_MDD%",
                                         "검증_매수", "검증_승률%", "검증_정지")})
        row["계산_종목수"] = f"{ok}/{len(main.CONFIG['종목목록'])}"
        row["제외_종목"] = unavailable("; ".join(skipped)) if skipped else ""
        row["기본값"] = "예" if all(combo.get(k) == defaults.get(k) for k in combo) else ""
        rows.append(row)
    # 정렬: 계산된 조합 먼저 → 계산 종목 수 많은 순(같은 종목 묶음끼리 비교)
    #       → 검증(안 본 기간) 순손익 높은 순 → 같으면 덜 물린 순. 계산 불가 조합은 맨 아래.
    def _key(x):
        if isinstance(x["검증_순손익"], str):
            return (0, 0, 0.0, 0.0)
        return (1, int(x["계산_종목수"].split("/")[0]), x["검증_순손익"], x["검증_MDD%"])
    rows.sort(key=_key, reverse=True)
    return rows


def _save(name, rows):
    main.RESULTS_DIR.mkdir(exist_ok=True)
    f = main.RESULTS_DIR / f"tune_{name}.csv"
    with open(f, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return f


def main_run(failures=None):
    """튜닝 전체 실행. 트레이너 하나가 통째로 실패해도 다음 트레이너로 넘어가고, 끝에 실패 요약.
    실패 목록을 돌려준다(테스트·다른 스크립트용)."""
    failures = [] if failures is None else failures
    print("=" * 68)
    print(" 파라미터 튜닝 — 훈련(앞60%)으로 고르고 검증(뒤40%)으로 재확인")
    print(f" 종목: {', '.join(main.CONFIG['종목목록'])}  기간: {main.CONFIG['시작일']}~")
    print("=" * 68)
    for name in GRIDS:
        print(f"\n▼ [{name}] 조합 쓸어보는 중...")
        try:
            rows = tune_one(name, failures)
            if not rows:
                raise ValueError("조합이 하나도 없음")
            f = _save(name, rows)
        except Exception as e:  # 이 트레이너만 포기하고 다음으로
            record(failures, name, "전체", reason_of(e))
            print(f"  {unavailable(reason_of(e))} — 다음 트레이너로 넘어갑니다.")
            continue
        cols = [k for k in rows[0] if k != "기본값"]
        n_bad = sum(isinstance(r["검증_순손익"], str) for r in rows)
        print(f"  {len(rows)}개 조합을 {f.name} 에 기록"
              + (f" (그중 {n_bad}개는 계산 불가)" if n_bad else "") + ". 검증 성적 상위 5개:")
        print("   " + "  ".join(cols))
        for row in rows[:5]:
            mark = " ★기본값" if row["기본값"] else ""
            print("   " + "  ".join(str(row[c]) for c in cols) + mark)
        base = next((r for r in rows if r["기본값"]), None)
        if base and base not in rows[:5]:
            print(f"   (지금 기본값은 {len(rows)}개 중 {rows.index(base)+1}등: "
                  f"검증 순손익 {fmt_money(base['검증_순손익'])})")
    print_failure_summary(failures, "튜닝 실패 요약")
    print("\n" + "=" * 68)
    print("※ 훈련만 좋고 검증 나쁘면 과최적화. 검증까지 좋은 값만 채택하세요.")
    print("※ 검증까지 좋아도 미래 보장은 아니에요. 고른 값은 live.py 로 포워드 검증.")
    print("※ '계산 불가' 종목이 있으면 그 조합 합계는 남은 종목만의 합이에요(계산_종목수 칸 확인).")
    print("=" * 68)
    return failures


if __name__ == "__main__":
    main_run()
