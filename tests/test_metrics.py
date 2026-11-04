"""metrics.py 테스트 — 네트워크 없이, 손으로 계산할 수 있는 합성 데이터만 쓴다."""
import math
import sys
from pathlib import Path

# 저장소 루트를 import 경로에 넣는다(S0의 conftest/pytest.ini가 없어도 단독 실행되게)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

import metrics as m

NAN = float("nan")


def _series(values, start="2026-01-02"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


# ── MDD ──
def test_mdd_손계산():
    # 고점 120 → 90 = -25%가 가장 깊다. (130 → 117 은 -10%)
    assert m.max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(-0.25)


def test_mdd_안떨어지면_0_빈값은_None():
    assert m.max_drawdown([100, 110, 120]) == 0.0
    assert m.max_drawdown([]) is None
    assert m.max_drawdown([NAN, NAN]) is None


def test_mdd_NaN_무시():
    assert m.max_drawdown([100, NAN, 80, 100]) == pytest.approx(-0.20)


# ── 총수익 ──
def test_total_return():
    assert m.total_return([100, 105, 110]) == pytest.approx(0.10)
    assert m.total_return([200, 150]) == pytest.approx(-0.25)


def test_total_return_NaN_무시_부족은_None():
    assert m.total_return([100, 120, NAN]) == pytest.approx(0.20)
    assert m.total_return([NAN, 100, 90]) == pytest.approx(-0.10)
    assert m.total_return([100]) is None
    assert m.total_return([]) is None


# ── Sharpe ──
def test_sharpe_부호():
    up = [100, 101, 103, 104, 106, 107]
    down = [100, 99, 97, 96, 94, 93]
    assert m.sharpe(up) > 0
    assert m.sharpe(down) < 0


def test_sharpe_손계산():
    # 수익률 +10%, -10%... 대신 단순한 값: [100, 110, 99] → +0.10, -0.10 → 평균 0 → 샤프 0
    assert m.sharpe([100, 110, 99]) == pytest.approx(0.0, abs=1e-12)
    # [100, 110, 121, 121*1.2]: 수익률 0.1, 0.1, 0.2 → 평균 0.1333, 표본표준편차 0.057735
    r = [0.1, 0.1, 0.2]
    mean = sum(r) / 3
    std = math.sqrt(sum((x - mean) ** 2 for x in r) / 2)
    assert m.sharpe([100, 110, 121, 145.2]) == pytest.approx(mean / std * math.sqrt(252))


def test_sharpe_None():
    assert m.sharpe([]) is None
    assert m.sharpe([100]) is None
    assert m.sharpe([100, 101]) is None            # 수익률 1개 → 표준편차 불가
    assert m.sharpe([100, 100, 100, 100]) is None  # 흔들림 0
    assert m.sharpe([100, NAN, NAN, 101]) is None  # NaN 버리면 2개뿐


# ── buy&hold ──
def test_buy_and_hold_비용_포함():
    # 1주 실제 매수비 = 100 × 1.0005 × 1.001 = 100.15005 → 예산 1000이면 9주
    # 산 돈 = 9 × 100.15005 = 901.35045
    # 판 돈 = 9 × 110 × 0.9995 × 0.999 = 988.515495
    bh = m.buy_and_hold(_series([100, 105, 110]), 1000)
    assert bh["shares"] == 9
    assert bh["profit"] == pytest.approx(988.515495 - 901.35045)
    assert bh["return"] == pytest.approx((988.515495 - 901.35045) / 1000)
    assert bh["start"] == "2026-01-02"
    assert bh["end"] == "2026-01-06"


def test_buy_and_hold_비용_0이면_단순계산():
    bh = m.buy_and_hold(_series([100, 110]), 1000, fee_rate=0, slippage=0)
    assert bh["shares"] == 10
    assert bh["profit"] == pytest.approx(100.0)
    assert bh["return"] == pytest.approx(0.10)


def test_buy_and_hold_마지막_NaN_행_무시():
    # 마지막 봉 Close가 NaN(미확정) → 그 전날 110으로 평가, end도 그 전날
    s = _series([100, 105, 110, NAN])
    bh = m.buy_and_hold(s, 1000, fee_rate=0, slippage=0)
    assert bh["profit"] == pytest.approx(100.0)
    assert bh["end"] == "2026-01-06"


def test_buy_and_hold_DataFrame은_첫날_Open에_산다():
    idx = pd.bdate_range("2026-01-02", periods=3)
    df = pd.DataFrame({"Open": [50.0, 101.0, 999.0],
                       "Close": [100.0, 102.0, NAN]}, index=idx)
    bh = m.buy_and_hold(df, 1000, fee_rate=0, slippage=0)
    # Open 50에 20주 → 마지막 유효 Close 102 → 손익 20 × 52 = 1040
    assert bh["shares"] == 20
    assert bh["profit"] == pytest.approx(1040.0)
    assert bh["end"] == "2026-01-05"
    # Open 열이 없으면 Close로
    bh2 = m.buy_and_hold(df[["Close"]], 1000, fee_rate=0, slippage=0)
    assert bh2["shares"] == 10


def test_buy_and_hold_못사면_0주_데이터없으면_None():
    bh = m.buy_and_hold(_series([500, 600]), 100)
    assert bh["shares"] == 0 and bh["profit"] == 0.0 and bh["return"] == 0.0
    assert m.buy_and_hold(_series([NAN, NAN]), 1000) is None
    assert m.buy_and_hold(_series([100, 110]), 0) is None


def test_buy_and_hold_예산_초과_안함():
    # 딱 맞아떨어지는 가격에서도 산 돈이 예산을 넘지 않아야 한다
    for price in [33.33, 99.99, 100.0, 250.5]:
        bh = m.buy_and_hold(_series([price, price]), 1000)
        assert bh["shares"] * price * 1.0005 * 1.001 <= 1000


# ── 벤치마크 ──
def test_benchmark_return_날짜_범위():
    spy = _series([100, 110, 120, 130, 140])  # 01-02, 05, 06, 07, 08
    assert m.benchmark_return(spy, "2026-01-05", "2026-01-07") == pytest.approx(130 / 110 - 1)
    # 양 끝 포함, 범위 밖 값은 안 씀
    assert m.benchmark_return(spy, "2026-01-01", "2026-01-31") == pytest.approx(0.40)
    # 시작일이 휴일이면 그 뒤 첫 거래일부터
    assert m.benchmark_return(spy, "2026-01-03", "2026-01-06") == pytest.approx(120 / 110 - 1)


def test_benchmark_return_NaN_무시_부족은_None():
    spy = _series([100, NAN, 120, NAN])
    assert m.benchmark_return(spy, "2026-01-02", "2026-01-07") == pytest.approx(0.20)
    assert m.benchmark_return(spy, "2026-01-06", "2026-01-07") is None  # 유효값 1개
    assert m.benchmark_return(spy, "2027-01-01", "2027-12-31") is None


# ── 비교 한 줄 ──
def test_compare_line_패():
    bh = {"profit": 1950.0}
    line = m.compare_line("마라토너", 412.0, bh, 0.38, 5000)
    assert line == "마라토너 +$412 | 그냥 들고 있었으면 +$1,950 | SPY +38% → 패"


def test_compare_line_승_반반():
    assert m.compare_line("스프린터", 900, {"profit": 500}, 0.10, 5000).endswith("→ 승")
    # 들고있기(500)는 이기고 SPY(+20% × 5000 = 1000)는 짐
    line = m.compare_line("스프린터", 900, {"profit": 500}, 0.20, 5000)
    assert "반반" in line and "들고있기 승" in line and "SPY 패" in line
    assert m.compare_line("x", -120, {"profit": -30}, -0.05, 1000).startswith("x -$120")


def test_compare_line_계산불가():
    line = m.compare_line("파이오니어", NAN, None, None, 1000)
    assert "nan" not in line.lower()
    assert "계산 불가" in line and "판정 불가" in line
    line2 = m.compare_line("파이오니어", 100, None, 0.05, 1000)
    assert line2.endswith("→ 승") and "그냥 들고 있었으면 계산 불가" in line2
