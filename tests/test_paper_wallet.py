"""paper_wallet 경계값 테스트 (네트워크 없음).

확인하는 것:
- 상한(예산×비율)에 '딱 맞는' 가격이면 그만큼 산다
- 상한보다 비싼 1주는 사지 않는다 (0주, D5)
- 비용(슬리피지·수수료) 때문에 1주 줄어드는 경우
- 왕복 비용이 D8 숫자대로 나온다
- 매수 보류가 사유와 함께 log 에 남는다
"""
import os
import sys

import pytest

# 저장소 루트를 import 경로에 추가 (conftest 가 없어도 단독 실행되도록)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_wallet import Holding, PaperWallet, shares_within_cap  # noqa: E402

FEE, SLIP = 0.001, 0.0005
UNIT = (1 + SLIP) * (1 + FEE)   # 가격 1당 실제 비용 배수


def _cost(price, n):
    """n주를 살 때 실제로 빠지는 돈 (지갑 buy 와 같은 공식)."""
    return price * (1 + SLIP) * n * (1 + FEE)


# ---------- shares_within_cap ----------

def test_기본값_D8():
    w = PaperWallet(name="t")
    assert w.currency == "USD"
    assert w.fee_rate == 0.001
    assert w.sell_tax_rate == 0.0
    assert w.slippage == 0.0005


def test_상한에_딱_맞는_가격이면_그만큼_산다():
    budget, cap = 10_000, 0.2          # 한도 $2,000
    price = 2_000 / (4 * UNIT)          # 4주 비용이 정확히 $2,000
    assert shares_within_cap(budget, cap, price) == 4
    assert _cost(price, 4) <= budget * cap + 1e-9


def test_1주_비용이_상한과_정확히_같으면_1주():
    price = 2_000 / UNIT
    assert shares_within_cap(10_000, 0.2, price) == 1


def test_상한보다_비싼_1주는_안_산다():
    # 예전 max(1, …) 는 여기서 1주를 사서 상한을 넘겼다
    assert shares_within_cap(10_000, 0.2, 2_500) == 0
    assert shares_within_cap(10_000, 0.2, 2_000.01) == 0


def test_가격은_상한_이하지만_비용_포함하면_1주도_못_산다():
    # 가격 자체는 $2,000 이하라도 슬리피지+수수료를 더하면 넘는다
    price = 1_999.0
    assert price < 2_000
    assert shares_within_cap(10_000, 0.2, price) == 0


def test_비용_때문에_1주_줄어드는_경우():
    budget, cap = 10_000, 0.2
    price = 400.0                       # 비용 무시하면 2000/400 = 5주
    assert int(budget * cap / price) == 5
    n = shares_within_cap(budget, cap, price)
    assert n == 4                       # 5주는 비용 포함 $2,003 > $2,000
    assert _cost(price, 4) <= 2_000 < _cost(price, 5)


@pytest.mark.parametrize("price", [0.37, 1.0, 13.3, 99.99, 187.41, 333.33, 1_999.99, 5_000])
@pytest.mark.parametrize("budget,cap", [(10_000, 0.2), (10_000, 0.1), (3_333.33, 0.3), (50, 1.0)])
def test_절대_상한_초과_금지이고_한_주_더는_넘는다(budget, cap, price):
    n = shares_within_cap(budget, cap, price)
    limit = budget * cap
    assert n >= 0
    assert _cost(price, n) <= limit            # 상한 이하
    assert _cost(price, n + 1) > limit         # 최대값 (한 주 더 사면 넘음)


@pytest.mark.parametrize("price", [0, -5, float("nan"), float("inf"), None, "abc"])
def test_이상한_가격이면_0(price):
    assert shares_within_cap(10_000, 0.2, price) == 0


def test_예산이나_상한이_0이면_0():
    assert shares_within_cap(0, 0.2, 10) == 0
    assert shares_within_cap(10_000, 0, 10) == 0
    assert shares_within_cap(float("nan"), 0.2, 10) == 0


def test_shares_within_cap_으로_산_만큼은_지갑이_실제로_살_수_있다():
    w = PaperWallet(name="t")
    w.deposit(2_000)
    price = 400.0
    n = shares_within_cap(2_000, 1.0, price, w.fee_rate, w.slippage)
    assert n == 4
    assert w.buy("X", price, n)
    assert w.cash >= 0
    assert not w.buy("Y", price, 1)    # 남은 돈으론 1주도 못 삼


# ---------- 지갑 매매 ----------

def test_왕복_비용_범위():
    w = PaperWallet(name="t")
    w.deposit(10_000)
    assert w.buy("X", 100, 50)
    assert w.sell("X", 100, 50)
    pct = (10_000 - w.cash) / 5_000 * 100
    # 매수 슬리피지0.05+수수료0.1 + 매도 슬리피지0.05+수수료0.1 ≈ 0.30%
    assert 0.29 < pct < 0.31
    assert not w.holdings


def test_매도세_설정시_추가로_빠진다():
    a = PaperWallet(name="a"); a.deposit(10_000)
    b = PaperWallet(name="b", sell_tax_rate=0.0018); b.deposit(10_000)
    for w in (a, b):
        w.buy("X", 100, 10); w.sell("X", 100, 10)
    assert b.cash < a.cash


def test_현금_부족이면_안_산다():
    w = PaperWallet(name="t"); w.deposit(100)
    assert w.buy("X", 100, 1) is False      # 비용 포함하면 $100 초과
    assert w.cash == 100 and not w.holdings


def test_0주_매수와_매도는_거래가_아니다():
    w = PaperWallet(name="t"); w.deposit(1_000)
    assert w.buy("X", 10, 0) is False
    assert w.sell("X", 10, 0) is False
    assert len(w.log) == 1                  # 입금만


def test_가진것보다_많이_못_판다():
    w = PaperWallet(name="t"); w.deposit(1_000)
    assert w.buy("X", 10, 5)
    assert w.sell("X", 10, 6) is False
    assert w.sell("Z", 10, 1) is False


# ---------- 기록(log) ----------

def test_거래일과_통화가_log에_찍힌다():
    w = PaperWallet(name="t"); w.deposit(1_000, date="2026-11-01")
    w.buy("X", 10, 5, date="2026-11-02")
    w.sell("X", 11, 5, date="2026-11-03")
    assert [e["시각"] for e in w.log] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert all(e["통화"] == "USD" for e in w.log)
    assert all(set(e) == {"시각", "종류", "종목", "수량", "금액", "통화"} for e in w.log)


def test_date_없이_불러도_동작한다_하위호환():
    w = PaperWallet(name="t"); w.deposit(1_000)
    assert w.buy("X", 10, 5)                # 예전 호출부(main/live/team) 방식
    assert w.sell("X", 10, 5)
    for e in w.log:
        assert len(e["시각"]) == len("2026-11-04 12:00:00")


def test_보류는_사유와_함께_log에_남고_돈은_그대로():
    w = PaperWallet(name="t"); w.deposit(10_000)
    w.skip("NVDA", "상한 $2,000 안에서 1주도 못 삼", date="2026-11-03")
    e = w.log[-1]
    assert e["종류"] == "보류"
    assert e["종목"] == "NVDA"
    assert e["수량"] == 0 and e["금액"] == 0
    assert e["통화"] == "USD"
    assert e["사유"] == "상한 $2,000 안에서 1주도 못 삼"
    assert e["시각"] == "2026-11-03"
    assert w.cash == 10_000 and not w.holdings


def test_보류_date_없으면_실행시각():
    w = PaperWallet(name="t")
    w.skip("X", "이유")
    assert len(w.log[-1]["시각"]) == len("2026-11-04 12:00:00")


# ---------- 상태 파일 복원 호환 ----------

def test_예전_상태_dict_로_복원해도_깨지지_않는다():
    # team._wallet_from_dict 처럼 currency 를 모르는 복원 코드를 흉내
    old = {"name": "스프린터", "cash": 500.0, "fee_rate": 0.00015,
           "holdings": {"X": {"shares": 3, "avg_price": 10.0}},
           "log": [{"시각": "2026-11-01 09:00:00", "종류": "매수", "종목": "X", "수량": 3, "금액": 30.0}]}
    w = PaperWallet(name=old["name"], cash=old["cash"], fee_rate=old["fee_rate"],
                    sell_tax_rate=old.get("sell_tax_rate", 0.0018), slippage=old.get("slippage", 0.0005))
    w.holdings = {k: Holding(**v) for k, v in old["holdings"].items()}
    w.log = old["log"]
    assert w.currency == "USD"
    assert w.sell("X", 10, 3, date="2026-11-02")
    assert w.log[-1]["통화"] == "USD"
