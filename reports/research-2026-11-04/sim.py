"""
연구용 공통 시뮬레이터 (research-2026-11-04)
---------------------------------------------
저장소 코드(.py)는 한 줄도 고치지 않고 import 만 한다.
  - 판단: marathoner_brain / sprinter_brain / pioneer_brain 의 decide() 를 그대로 호출
  - 돈:   paper_wallet.PaperWallet(수수료 0.1%, 슬리피지 0.05%, 매도세 0), shares_within_cap
  - 비교: metrics.max_drawdown

체결 규칙 (설계 D3·D5·D8):
  - 봉 t 의 종가까지 보고 decide → 봉 t+1 의 시가(Open)로 체결. 미래 데이터는 보지 않는다.
  - 살 주식 수 = shares_within_cap(지갑 현금, 상한, 시가). 0주면 사지 않고 wallet.skip() 으로 '보류' 기록.
  - 마지막 날 들고 있으면 그날 종가에 판다고 보고 매도 비용(슬리피지+수수료)을 뺀 '청산 가치'로 평가.
  - 서킷 브레이커는 쓰지 않는다(브레인 규칙 자체를 보려는 연구, REPORT.md 참고).

속도를 위한 처리(결과는 같음):
  - 지표(이동평균·RSI·거래량평균)는 전체 기간에 한 번만 계산한다. 셋 다 '과거만 보는' 지표라
    봉 t 의 값은 t 이후 데이터와 무관하다(main.py 도 전체 df 에 한 번 계산한다).
  - decide() 에는 최근 80개 봉만 잘라서 넘긴다. decide 는 마지막 몇 줄과 len(df)>=60 만 보므로
    결과가 같다. 단, 데이터 시작(2015-01) 직후 60봉 미만 구간은 원래처럼 길이가 짧게 넘어간다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                  # 저장소 루트
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from marathoner_brain import MarathonerBrain   # noqa: E402
from sprinter_brain import SprinterBrain       # noqa: E402
from pioneer_brain import PioneerBrain         # noqa: E402
from paper_wallet import PaperWallet, shares_within_cap   # noqa: E402
import metrics                                  # noqa: E402

FEE = 0.001
SLIP = 0.0005
WINDOW = 80          # decide 에 넘기는 최근 봉 수 (>= 60)
WARMUP = 60          # 모든 트레이너가 판단 가능해지는 최소 봉 수 (마라토너 60일선)

BRAINS = {"마라토너": MarathonerBrain, "스프린터": SprinterBrain, "파이오니어": PioneerBrain}

DATA = HERE / "data"


def load(code: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{code}.csv.gz", index_col=0, parse_dates=True)
    return df[df["Close"].notna()]


def universe() -> list[str]:
    import json
    info = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))
    return [c for c in info["종목"] if c != "SPY"]


def names() -> dict:
    import json
    info = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))
    return {c: v["이름"] for c, v in info["종목"].items()}


class Prepared:
    """종목 하나 × 트레이너 하나 의 지표 계산 결과와 넘파이 배열."""

    def __init__(self, df: pd.DataFrame, brain_cls):
        self.ind = brain_cls().add_indicators(df)    # 지표 칸 계산은 파라미터와 무관
        self.open = df["Open"].to_numpy(float)
        self.close = df["Close"].to_numpy(float)
        self.dates = df.index
        self.flat_cache: dict = {}    # (params, i) -> 보유 없을 때의 판단 (같은 봉이면 항상 같음)


def idx_range(dates: pd.DatetimeIndex, start: str, end: str, warmup: int = WARMUP):
    """[start, end] 안의 첫·마지막 봉 위치. 시작은 최소 warmup 번째 봉 이후."""
    i0 = int(dates.searchsorted(pd.Timestamp(start)))
    i1 = int(dates.searchsorted(pd.Timestamp(end), side="right")) - 1
    return max(i0, warmup), i1


def simulate(prep: Prepared, brain, i0: int, i1: int, budget: float, cap: float = 1.0,
             code: str = "X", params_key=None, keep_log: bool = False) -> dict:
    """봉 i0..i1 동안 가상매매. 봉 i0 종가부터 판단 시작, 첫 체결은 빨라야 i0+1 시가.
    budget: 이 슬롯의 시작 현금. cap: 살 때 현금의 몇 %까지 쓸지(연구 기본 1.0 = 슬롯 전부)."""
    wallet = PaperWallet(name=type(brain).__name__, fee_rate=FEE, slippage=SLIP)
    wallet.deposit(budget, date=str(prep.dates[i0].date()))
    ind, op, cl, dates = prep.ind, prep.open, prep.close, prep.dates
    position = None
    pending = None
    trades = []          # (진입 봉, 청산 봉 또는 None=끝까지 보유)
    buys = sells = skips = wins = 0
    held_days = 0
    equity = []
    for i in range(i0, i1 + 1):
        d = str(dates[i].date())
        if position is not None:
            position["days_held"] += 1
        # 1) 어제 종가에 낸 주문을 오늘 시가에 체결
        if pending == "매수" and position is None:
            n = shares_within_cap(wallet.cash, cap, op[i], FEE, SLIP)
            if n <= 0:
                wallet.skip(code, f"상한 ${wallet.cash * cap:,.0f} 안에서 1주도 못 삼 (1주 ${op[i]:,.2f})", d)
                skips += 1
            elif wallet.buy(code, op[i], n, d):
                position = {"buy_price": float(op[i]), "days_held": 0, "shares": n, "entry": i}
                buys += 1
            else:
                wallet.skip(code, "현금 부족", d)
                skips += 1
        elif pending == "매도" and position is not None:
            if wallet.sell(code, op[i], position["shares"], d):
                sells += 1
                wins += 1 if op[i] > position["buy_price"] else 0
                trades.append((position["entry"], i))
                position = None
        pending = None
        # 2) 오늘 종가까지 보고 판단 (마지막 봉의 신호는 체결할 다음 날이 없으니 버림)
        if position is None and params_key is not None and (params_key, i) in prep.flat_cache:
            action = prep.flat_cache[(params_key, i)]
        else:
            window = ind.iloc[max(0, i - WINDOW + 1): i + 1]
            action, _ = brain.decide(window, position)
            if position is None and params_key is not None:
                prep.flat_cache[(params_key, i)] = action
        if i < i1:
            if action == "매수" and position is None:
                pending = "매수"
            elif action == "매도" and position is not None:
                pending = "매도"
        if position is not None:
            held_days += 1
        equity.append(wallet.value({code: cl[i]}))
    # 3) 끝: 들고 있으면 종가 청산 가치로 평가
    final = wallet.cash
    if position is not None:
        final += position["shares"] * cl[i1] * (1 - SLIP) * (1 - FEE)
        trades.append((position["entry"], None))
    equity[-1] = final
    n_days = i1 - i0 + 1
    out = {
        "start": str(dates[i0].date()), "end": str(dates[i1].date()),
        "profit": final - budget, "return": final / budget - 1,
        "mdd": metrics.max_drawdown(equity) or 0.0,
        "buys": buys, "sells": sells, "skips": skips, "wins": wins,
        "exposure": held_days / n_days, "trades": trades, "equity": equity,
    }
    if keep_log:
        out["log"] = wallet.log
    return out


def buy_hold(prep_or_df, i0: int, i1: int, budget: float) -> dict:
    """같은 돈으로 봉 i0 시가에 사서 i1 종가까지 보유(metrics.buy_and_hold) + 일별 평가곡선."""
    if isinstance(prep_or_df, Prepared):
        op, cl, dates = prep_or_df.open, prep_or_df.close, prep_or_df.dates
    else:
        op, cl, dates = (prep_or_df["Open"].to_numpy(float), prep_or_df["Close"].to_numpy(float),
                         prep_or_df.index)
    frame = pd.DataFrame({"Open": op[i0:i1 + 1], "Close": cl[i0:i1 + 1]}, index=dates[i0:i1 + 1])
    bh = metrics.buy_and_hold(frame, budget, FEE, SLIP)
    unit = op[i0] * (1 + SLIP) * (1 + FEE)
    shares = bh["shares"]
    left = budget - shares * unit
    equity = list(left + shares * cl[i0:i1 + 1])
    equity[-1] = budget + bh["profit"]
    bh["equity"] = equity
    bh["mdd"] = metrics.max_drawdown(equity) or 0.0
    return bh


# ---------- 무작위 타이밍 비교 (같은 거래 횟수·보유 기간, 시점만 무작위) ----------
def trade_lengths(trades, i0: int, i1: int):
    """체결 봉 기준 보유 길이. 진입은 시가 e, 청산은 시가 x (끝까지 보유면 i1 종가)."""
    L = i1 - i0   # 진입 가능한 봉: i0+1 .. i1
    out = []
    for e, x in trades:
        out.append((x if x is not None else i1 + 1) - e)
    return L, out


def trade_return(op, cl, i_entry: int, i_exit: int | None, i1: int) -> float:
    """한 번 사고판 배수(비용 포함, 소수 주 허용)."""
    buy = op[i_entry] * (1 + SLIP) * (1 + FEE)
    sell = (cl[i1] if i_exit is None or i_exit > i1 else op[i_exit]) * (1 - SLIP) * (1 - FEE)
    return sell / buy


def actual_factor(prep: Prepared, trades, i1: int) -> float:
    f = 1.0
    for e, x in trades:
        f *= trade_return(prep.open, prep.close, e, x, i1)
    return f


def random_factors(prep: Prepared, trades, i0: int, i1: int, n: int, rng) -> np.ndarray:
    """실제와 같은 개수·같은 길이의 거래를 기간 안 무작위 위치에 겹치지 않게 놓았을 때의 배수 n개."""
    L, lens = trade_lengths(trades, i0, i1)
    k = len(lens)
    if k == 0:
        return np.ones(n)
    lens = np.array(lens)
    G = L - lens.sum()
    if G < 0:
        G = 0
    op, cl = prep.open, prep.close
    # 진입 시가 배열, 청산 가격 배열(봉 i 시가, 마지막 다음은 i1 종가)
    buy_px = op * (1 + SLIP) * (1 + FEE)
    exit_px = np.append(op[: i1 + 1], cl[i1]) * (1 - SLIP) * (1 - FEE)
    out = np.empty(n)
    for j in range(n):
        order = rng.permutation(k)
        cuts = np.sort(rng.integers(0, G + 1, size=k))
        gaps = np.diff(np.concatenate(([0], cuts)))
        ls = lens[order]
        starts = i0 + 1 + np.cumsum(gaps) + np.concatenate(([0], np.cumsum(ls)[:-1]))
        ends = np.minimum(starts + ls, i1 + 1)
        out[j] = np.prod(exit_px[ends] / buy_px[starts])
    return out
