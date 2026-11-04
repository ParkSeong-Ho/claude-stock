"""
가짜 지갑 (Paper Trading Wallet) - 학습 모드의 심장
------------------------------------------------------
진짜 돈은 절대 쓰지 않습니다. 컴퓨터 안의 가상 돈으로만 사고팔기를 흉내 냅니다.
세 트레이너(스프린터/마라토너/파이오니어)가 각자 이 지갑을 하나씩 가집니다.

초보자용 설명:
- deposit(): 지갑에 가짜 돈을 넣는다
- buy():     가짜 돈으로 주식을 산다 (수수료도 흉내)
- sell():    가진 주식을 판다 (tax_rate 를 주면 그 건만 그 매도세율로 — H1 지수 다리 0, 국내 날짜별 세율)
- skip():    "사려다 안 산" 일도 이유와 함께 기록한다 (예: 상한 안에서 1주도 못 삼)
- value():   지금 이 지갑이 총 얼마짜리인지 계산한다
- shares_within_cap(): 상한(예산×비율) 안에서 비용까지 내고 살 수 있는 최대 주식 수
- 모든 거래는 자동으로 기록된다 (나중에 세금/복기용)

v1 결정(docs/v1-design.md):
- D4: 미국 종목 전용, 지갑 통화는 달러(USD). 거래 기록에도 통화를 남긴다.
- D5: 상한을 넘겨서 1주를 사는 일은 없다. 1주도 못 사면 0주 → 호출부가 skip()으로 사유 기록.
- D8: 미국 기준 비용. 수수료 0.1%(양방향), 매도세 0, 슬리피지 0.05%.

kr-broker 결정(docs/kr-broker-design.md):
- 지갑은 시장별로 따로. 국내 지갑은 currency="KRW" + 국내 비용(수수료 0.015%, 매도세 0.20%, 슬리피지 0.05%).
  국내 값은 markets.MARKETS["kr"] 에 있고, main.make_wallet() 이 그 값으로 지갑을 만든다.
- 아래 기본값은 그대로 미국(달러) — 인자 없이 만든 지갑은 예전과 똑같다. 한 지갑 안에서 통화를 바꾸지 않는다.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

# 미국 기준 기본 비용 (D8). 지갑과 shares_within_cap 이 같은 숫자를 쓰도록 한 곳에 모아 둠.
DEFAULT_FEE_RATE = 0.001       # 매매 수수료율 0.1% (살 때·팔 때 각각)
DEFAULT_SELL_TAX_RATE = 0.0    # 미국은 매도 거래세 없음 (양도세는 연간 정산이라 건별 시뮬 제외)
DEFAULT_SLIPPAGE = 0.0005      # 체결 미끄러짐 가정 0.05% (시장가 근사)


def shares_within_cap(budget: float, cap: float, price: float,
                      fee_rate: float = DEFAULT_FEE_RATE,
                      slippage: float = DEFAULT_SLIPPAGE) -> int:
    """예산(budget) × 상한비율(cap) 안에서, 슬리피지·수수료까지 다 내고 살 수 있는 최대 주식 수.

    초보자용 설명:
    - 1주에 실제로 드는 돈 = 가격 × (1+슬리피지) × (1+수수료율)
    - 한도 = budget × cap
    - 한도 ÷ 1주 비용 을 내림한 값이 답. 1주도 안 되면 0 (억지로 1주 사지 않음, D5).
    - 계산 오차로 한도를 아주 조금이라도 넘는 일이 없도록 마지막에 다시 확인한다.
    """
    try:
        budget, cap, price = float(budget), float(cap), float(price)
    except (TypeError, ValueError):
        return 0
    limit = budget * cap
    unit = price * (1 + slippage) * (1 + fee_rate)     # 1주당 실제 비용
    # 값이 이상하면(NaN, 0 이하, 무한대) 사지 않는다
    if not (math.isfinite(limit) and math.isfinite(unit)) or limit <= 0 or unit <= 0:
        return 0
    # 나눗셈 오차(예: 2.9999999 → 2) 때문에 '딱 맞는 가격'에서 1주 덜 사는 일을 막으려고 아주 작은 여유를 더함
    n = int(math.floor(limit / unit + 1e-9))
    # 그 여유 때문에 한도를 넘으면 하나씩 줄인다 (절대 상한 초과 금지)
    while n > 0 and n * unit > limit:
        n -= 1
    return max(n, 0)


@dataclass
class Holding:
    """한 종목을 얼마에 몇 주 샀는지 기록."""
    shares: float        # 보유 수량. 주식은 정수 값(21 처럼), H1 대기 자산(지수 SPY·KS200)은 소수 단위(74.2187… 처럼)
    avg_price: float     # 평균 매입 단가


@dataclass
class PaperWallet:
    name: str                                       # 트레이너 이름 (예: "스프린터")
    cash: float = 0.0                               # 지금 남은 현금
    currency: str = "USD"                           # 지갑 통화: 미국 "USD"(기본, D4) / 국내 "KRW" (환전 없음)
    fee_rate: float = DEFAULT_FEE_RATE              # 매매 수수료율 (0.1%, 양방향, D8)
    sell_tax_rate: float = DEFAULT_SELL_TAX_RATE    # 매도세 (미국 0, D8 / 국내 0.20%, K-D8)
    slippage: float = DEFAULT_SLIPPAGE              # 체결 미끄러짐 가정 (0.05%)
    holdings: dict = field(default_factory=dict)    # {종목코드: Holding}
    log: list = field(default_factory=list)         # 모든 거래 기록
    # 참고: 예전 상태 파일(state/*.json)을 복원할 때 currency 를 안 넘겨도 기본값 "USD"가 들어가서 깨지지 않는다.

    # --- 돈 넣기 ---
    def deposit(self, amount: float, date: str | None = None):
        """지갑에 가짜 돈을 넣는다."""
        self.cash += amount
        self._record("입금", None, 0, amount, date)

    # --- 사기 ---
    def buy(self, code: str, price: float, shares: int, date: str | None = None) -> bool:
        """price 가격에 shares 주 만큼 산다. 돈이 부족하거나 주식 수가 0 이하면 사지 않고 False.
        date = 거래일 'YYYY-MM-DD' (없으면 지금 시각으로 기록 — 예전 호출부 호환)."""
        if shares <= 0:
            return False  # 0주 매수는 거래가 아님 (D5: 못 사면 skip()으로 사유를 남길 것)
        exec_price = price * (1 + self.slippage)   # 살 땐 조금 더 비싸게 체결(현실)
        cost = exec_price * shares
        fee = cost * self.fee_rate
        total = cost + fee
        if total > self.cash:
            return False  # 현금 부족 -> 매수 실패 (규칙: 예산 안에서만)
        self.cash -= total
        if code in self.holdings:
            h = self.holdings[code]
            # 평균 단가 다시 계산 (기존 것 + 새로 산 것)
            new_shares = h.shares + shares
            h.avg_price = (h.avg_price * h.shares + exec_price * shares) / new_shares
            h.shares = new_shares
        else:
            self.holdings[code] = Holding(shares=shares, avg_price=exec_price)
        self._record("매수", code, shares, total, date)
        return True

    # --- 팔기 ---
    def sell(self, code: str, price: float, shares: int, date: str | None = None,
             tax_rate: float | None = None) -> bool:
        """가진 주식을 판다. 가진 것보다 많이 팔 수는 없다. date 는 buy() 와 같음.
        tax_rate: 이 매도 한 건에만 쓸 매도세율. None(기본)이면 지갑의 sell_tax_rate — 지금까지와 똑같다.
          H1 장부만 넘긴다: 대기 자산(지수) 매도는 0.0, 국내 주식은 체결일의 세율(설계 §3.4).
          지갑의 sell_tax_rate 자체는 바꾸지 않는다."""
        if shares <= 0 or code not in self.holdings or self.holdings[code].shares < shares:
            return False
        exec_price = price * (1 - self.slippage)   # 팔 땐 조금 더 싸게 체결(현실)
        proceeds = exec_price * shares
        fee = proceeds * self.fee_rate
        tax = proceeds * (self.sell_tax_rate if tax_rate is None else tax_rate)   # 매도세 (미국 기본 0)
        net = proceeds - fee - tax
        self.cash += net
        self.holdings[code].shares -= shares
        if self.holdings[code].shares == 0:
            del self.holdings[code]
        self._record("매도", code, shares, net, date)
        return True

    # --- 안 한 거래도 기록 ---
    def skip(self, code: str, reason: str, date: str | None = None) -> None:
        """사려다 못 산(보류한) 일을 이유와 함께 기록한다. 돈·보유는 바뀌지 않는다.
        예: wallet.skip("NVDA", "상한 $2,000 안에서 1주도 못 삼 (1주 $2,500)", "2026-11-03")"""
        self._record("보류", code, 0, 0.0, date, reason=reason)

    # --- 지금 총 얼마짜리인가 ---
    def value(self, prices: dict) -> float:
        """현금 + (보유 주식을 지금 시세로 판다면 받을 돈). prices = {종목코드: 현재가}"""
        stock_value = sum(
            h.shares * prices.get(code, h.avg_price)
            for code, h in self.holdings.items()
        )
        return self.cash + stock_value

    def _record(self, kind, code, shares, amount, date=None, reason=None):
        # 거래일(date)을 받으면 그 날짜로, 없으면 실행 시각으로 기록 (기준선 N3: 전부 실행 시각으로 찍히던 문제)
        when = date if date else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "시각": when, "종류": kind, "종목": code, "수량": shares,
            "금액": round(amount, 2), "통화": self.currency,
        }
        if reason is not None:
            entry["사유"] = reason   # 사유는 보류일 때만
        self.log.append(entry)


if __name__ == "__main__":
    # 자체 점검: 수수료·슬리피지가 실제로 비용으로 빠지는지 (미국 기준, 달러)
    w = PaperWallet(name="테스트")
    w.deposit(10_000)
    # 같은 가격에 사고팔면 비용만큼 손실이어야 (본전이면 버그)
    assert w.buy("X", 100, 50, date="2026-11-02")
    assert w.sell("X", 100, 50, date="2026-11-03")
    round_trip_cost = 10_000 - w.cash
    notional = 100 * 50   # 거래금액 $5,000
    pct = round_trip_cost / notional * 100
    # 예상 왕복 비용 ≈ 매수(슬리피지 0.05%+수수료 0.1%) + 매도(슬리피지 0.05%+수수료 0.1%) ≈ 0.30%
    assert 0.28 < pct < 0.32, f"왕복 비용 이상: {pct:.2f}%"
    assert not w.holdings, "전량 매도 후 보유 남음"
    assert w.log[1]["시각"] == "2026-11-02" and w.log[1]["통화"] == "USD"
    # 잔고보다 많이 못 삼
    assert w.buy("Y", 100, 10**9) is False
    # 상한 안에서 1주도 못 사면 0 (억지로 1주 사지 않음)
    assert shares_within_cap(10_000, 0.2, 2_500) == 0
    print(f"[PASS] 왕복 비용 ${round_trip_cost:,.2f}({pct:.2f}%) — 비용 반영 확인")
