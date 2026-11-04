"""성적표 지표 모음 (v1 설계 D7)

트레이너가 "이겼다"고 말하려면 두 가지와 비교해야 한다.
  1) buy&hold : 같은 돈으로 첫날 사서 끝까지 그냥 들고 있었으면?
  2) SPY      : 미국 시장 전체(S&P500 ETF)를 샀으면?

이 파일은 pandas와 표준 라이브러리만 쓰고, 저장소의 다른 모듈은 import하지 않는다(독립).
모든 함수는 NaN(빈 값) 행을 먼저 버리고 계산한다. 데이터가 모자라 계산할 수 없으면 None.
"""
import math

import pandas as pd


def _clean(values):
    """리스트/Series에서 숫자가 아닌 값·NaN·무한대를 버리고 float 리스트로 돌려준다."""
    if values is None:
        return []
    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    if isinstance(values, pd.Series):
        values = values.tolist()
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def max_drawdown(values):
    """최대 낙폭(MDD): 고점 대비 가장 깊이 떨어졌던 비율. 음수(예: -0.12 = -12%).
    한 번도 안 떨어졌으면 0.0, 값이 없으면 None."""
    vals = _clean(values)
    if not vals:
        return None
    peak = vals[0]
    mdd = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1)  # 지금이 고점 대비 몇 % 아래인가
    return mdd


def total_return(values):
    """총수익률: 마지막 평가금액 / 처음 평가금액 - 1. 값이 2개 미만이거나 처음이 0 이하면 None."""
    vals = _clean(values)
    if len(vals) < 2 or vals[0] <= 0:
        return None
    return vals[-1] / vals[0] - 1


def sharpe(values, periods_per_year=252):
    """샤프 비율(연환산): 하루 수익률의 평균 / 표준편차 × √(1년 거래일 수).
    '흔들림 대비 얼마나 벌었나'. 무위험 이자율은 0으로 본다.
    일별 수익률이 2개 미만이거나 전혀 흔들리지 않았으면(표준편차 0) None."""
    vals = _clean(values)
    if len(vals) < 3:
        return None
    rets = pd.Series(vals).pct_change().dropna()
    rets = rets[rets.map(math.isfinite)]
    if len(rets) < 2:
        return None
    std = rets.std()  # 표본 표준편차(ddof=1)
    if not math.isfinite(std) or std == 0:
        return None
    return float(rets.mean() / std * math.sqrt(periods_per_year))


def _date_str(idx):
    """인덱스 값을 'YYYY-MM-DD' 문자열로."""
    try:
        return pd.Timestamp(idx).date().isoformat()
    except (TypeError, ValueError):
        return str(idx)


def buy_and_hold(prices, budget, fee_rate=0.001, slippage=0.0005):
    """같은 투입액으로 '그냥 사서 들고 있었으면' 얼마였나.

    prices : 종가 Series, 또는 Open/Close 열이 있는 DataFrame.
             첫 날 Open(없으면 Close)에 사서, 마지막 Close로 평가한다.
             Close가 NaN인 행(아직 확정 안 된 봉 등)은 먼저 버린다.
    budget : 투입액(달러). 비용(슬리피지·수수료) 포함해 예산 안에서 살 수 있는 만큼만 산다(정수 주).
    평가할 때도 실제로 판다고 가정하고 매도 비용을 뺀다(왕복 비용 차감). 남는 현금은 그대로 둔다.

    돌려주는 값: {"start", "end", "shares", "profit", "return"}
      start/end = 'YYYY-MM-DD', profit = 달러 손익, return = profit / budget
    데이터가 없거나 예산이 0 이하면 None. 1주도 못 사면 shares=0, profit=0.0.
    """
    if prices is None or budget is None or not budget > 0:
        return None
    if isinstance(prices, pd.DataFrame):
        if "Close" not in prices.columns:
            return None
        df = prices[prices["Close"].notna()]
        df = df[df["Close"].map(lambda v: math.isfinite(float(v)))]
        if df.empty:
            return None
        open0 = df["Open"].iloc[0] if "Open" in df.columns else float("nan")
        buy_px = float(open0) if pd.notna(open0) and float(open0) > 0 else float(df["Close"].iloc[0])
        sell_px = float(df["Close"].iloc[-1])
        start, end = df.index[0], df.index[-1]
    else:
        s = pd.Series(prices).dropna()
        s = s[s.map(lambda v: math.isfinite(float(v)))]
        if s.empty:
            return None
        buy_px, sell_px = float(s.iloc[0]), float(s.iloc[-1])
        start, end = s.index[0], s.index[-1]
    if buy_px <= 0:
        return None

    cost_per_share = buy_px * (1 + slippage) * (1 + fee_rate)   # 1주 사는 데 드는 실제 돈
    shares = int(budget // cost_per_share)
    # 부동소수점 오차로 예산을 넘지 않게 한 번 더 확인
    while shares > 0 and shares * cost_per_share > budget:
        shares -= 1
    if shares > 0:
        spent = shares * cost_per_share
        received = shares * sell_px * (1 - slippage) * (1 - fee_rate)  # 팔 때 비용도 뺀다
        profit = received - spent
    else:
        profit = 0.0
    return {
        "start": _date_str(start),
        "end": _date_str(end),
        "shares": shares,
        "profit": float(profit),
        "return": float(profit / budget),
    }


def benchmark_return(bench_prices, start, end):
    """기준 지수(예: SPY)의 start~end(양 끝 포함) 수익률. 첫 유효 종가 → 마지막 유효 종가.
    구간 안에 유효한 값이 2개 미만이면 None."""
    if bench_prices is None:
        return None
    if isinstance(bench_prices, pd.DataFrame):
        if "Close" not in bench_prices.columns:
            return None
        bench_prices = bench_prices["Close"]
    s = pd.Series(bench_prices).dropna()
    if s.empty:
        return None
    s = s.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    vals = _clean(s)
    if len(vals) < 2 or vals[0] <= 0:
        return None
    return vals[-1] / vals[0] - 1


def _fmt_money(v):
    """+$1,234 / -$56 형식."""
    sign = "+" if v >= 0 else "-"
    return f"{sign}${abs(v):,.0f}"


def _fmt_pct(v):
    return f"{v * 100:+.0f}%"


def _ok(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def compare_line(name, profit, bh, spy_ret, budget):
    """초보자도 읽을 수 있는 비교 한 줄.
    예: '마라토너 +$412 | 그냥 들고 있었으면 +$1,950 | SPY +38% → 패'

    판정: 그냥 들고 있기(buy&hold)와 SPY(같은 돈 투입 시 손익) 둘 다 이기면 '승',
          둘 다 지면 '패', 하나만 이기면 '반반(…)'. 비교할 숫자가 없으면 그 부분은 '계산 불가'."""
    me = _fmt_money(profit) if _ok(profit) else "계산 불가"
    bh_profit = bh.get("profit") if isinstance(bh, dict) else None
    bh_txt = _fmt_money(bh_profit) if _ok(bh_profit) else "계산 불가"
    spy_txt = _fmt_pct(spy_ret) if _ok(spy_ret) else "계산 불가"
    line = f"{name} {me} | 그냥 들고 있었으면 {bh_txt} | SPY {spy_txt}"

    if not _ok(profit):
        return line + " → 판정 불가"
    results = []  # (이름, 이겼나)
    if _ok(bh_profit):
        results.append(("들고있기", profit > bh_profit))
    if _ok(spy_ret) and _ok(budget):
        results.append(("SPY", profit > spy_ret * budget))
    if not results:
        return line + " → 판정 불가"
    if all(w for _, w in results):
        verdict = "승"
    elif not any(w for _, w in results):
        verdict = "패"
    else:
        verdict = "반반(" + "·".join(f"{n} {'승' if w else '패'}" for n, w in results) + ")"
    return f"{line} → {verdict}"
