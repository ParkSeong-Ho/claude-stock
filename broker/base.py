"""
broker/base.py - 증권사 연결의 공통 약속 (주문·결과·체결·오류·브로커 모양)
------------------------------------------------------------------
docs/kr-broker-design.md §3 의 이름·시그니처를 그대로 따른다.
가짜 브로커(PaperBroker·FakeBroker)와 진짜 브로커(KisBroker)가 모두 이 모양을 지킨다.

초보자용 설명:
- Order       : "무엇을, 몇 주, 얼마에 사고/팔지" 적은 주문서 한 장
- OrderResult : 주문서를 냈더니 증권사가 뭐라고 했는지 (접수됨 / 거부됨 + 이유)
- Fill        : 실제로 체결된 내역 한 줄 (몇 주가 얼마에 사고팔렸는지)
- BrokerError : 증권사와 이야기하다 생긴 문제. kind 로 종류를 나눈다
- Broker      : 브로커라면 꼭 있어야 하는 기능 목록 (place / fills / holdings / buyable_shares)

안전 규칙 (K-D4):
- place() 는 예외를 던지지 않는다. 실패도 OrderResult(ok=False, error_kind=...) 로 돌려준다.
- place() 는 재시도하지 않는다. 같은 주문이 두 번 나가는 것을 막기 위해서다.
  (조회 기능 fills/holdings/buyable_shares 는 실패하면 BrokerError 를 던지고, 재시도해도 된다.)
- 같은 client_id 주문은 하루 한 번만. client_id 는 주문 내용으로 만들어지는 "주문 이름표"다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# BrokerError.kind 로 쓸 수 있는 값들 (이 밖의 값은 "unknown" 으로 바꾼다)
ERROR_KINDS = (
    "network",       # 인터넷·서버 연결 문제 (주문이 들어갔는지 모를 수 있음 → 재시도 금지)
    "auth",          # 앱 키·토큰 문제
    "rate_limit",    # 너무 자주 불렀음 (초당 호출 제한)
    "rejected",      # 증권사가 주문을 거절함 (잔고 부족, 잘못된 가격, 중복 주문 등)
    "mock_expired",  # 모의투자 기간 만료 (KIS 오류코드 40910000) → 크게 알려야 함
    "unknown",       # 위에 없는 문제
)

MARKET_KEYS = ("us", "kr")
SIDES = ("buy", "sell")


class BrokerError(Exception):
    """증권사 관련 오류. kind 로 종류를 나눈다 (ERROR_KINDS 중 하나).

    예) raise BrokerError("network", "서버 응답 없음")
    """

    def __init__(self, kind: str, message: str = ""):
        if kind not in ERROR_KINDS:
            # 모르는 종류가 들어와도 프로그램이 멈추지 않게 unknown 으로 바꾸고 원래 값은 메시지에 남긴다
            message = f"[{kind}] {message}".strip()
            kind = "unknown"
        super().__init__(message or kind)
        self.kind = kind
        self.message = message


@dataclass
class Order:
    """주문서 한 장. 지정가 주문만 쓴다 (K-D4)."""
    market: str          # "us" | "kr"
    code: str            # "AAPL" / "005930"
    side: str            # "buy" | "sell"
    shares: int          # 정수 주식 수 (소수점 주문 없음)
    limit_price: float   # 지정가 (이 가격보다 불리하게는 체결되지 않음)
    trainer: str         # 어느 트레이너의 주문인지 (sprinter / marathoner / pioneer ...)
    signal_date: str     # 신호가 나온 봉 날짜 'YYYY-MM-DD'

    @property
    def client_id(self) -> str:
        """주문 이름표. 같은 신호에서 나온 주문은 항상 같은 이름표 → 중복 주문을 알아챌 수 있다."""
        return f"{self.market}-{self.trainer}-{self.code}-{self.side}-{self.signal_date}"


@dataclass
class OrderResult:
    """주문을 낸 결과."""
    client_id: str
    ok: bool                       # True = 증권사가 주문을 받아 줌
    broker_order_id: str | None    # 증권사가 붙인 주문번호 (실패면 None)
    error_kind: str | None         # 실패 이유 종류 (ERROR_KINDS 중 하나, 성공이면 None)
    message: str                   # 사람이 읽을 설명


@dataclass
class Fill:
    """체결 내역 한 줄."""
    broker_order_id: str
    market: str
    code: str
    side: str
    shares: int
    price: float
    date: str            # 체결된 날짜 'YYYY-MM-DD' (그 시장 현지 날짜)


@runtime_checkable
class Broker(Protocol):
    """브로커라면 꼭 있어야 하는 기능 목록."""
    name: str

    def place(self, order: Order) -> OrderResult:
        """주문을 낸다. 예외를 던지지 않고 OrderResult(ok=False) 로 알린다. 재시도 금지."""
        ...

    def fills(self, market: str, date: str) -> list[Fill]:
        """그날(date) 체결 내역. 실패하면 BrokerError. 조회는 재시도해도 된다."""
        ...

    def holdings(self, market: str) -> dict[str, int]:
        """종목 → 보유 주식 수. 실패하면 BrokerError."""
        ...

    def buyable_shares(self, market: str, code: str, price: float) -> int | None:
        """그 가격에 살 수 있는 최대 주식 수. 모르면 None. 실패하면 BrokerError."""
        ...


def validate_order(order: Order) -> str | None:
    """주문서가 말이 되는지 검사한다. 문제가 있으면 이유(문장), 없으면 None.

    브로커들이 주문을 내기 전에 공통으로 쓰는 검사 (문제가 있으면 error_kind="rejected").
    """
    if order.market not in MARKET_KEYS:
        return f"모르는 시장: {order.market!r} (us 또는 kr)"
    if order.side not in SIDES:
        return f"모르는 주문 방향: {order.side!r} (buy 또는 sell)"
    if not str(order.code).strip():
        return "종목 코드가 비어 있음"
    if isinstance(order.shares, bool) or not isinstance(order.shares, int):
        return f"주식 수는 정수여야 함: {order.shares!r}"
    if order.shares <= 0:
        return f"주식 수는 1 이상이어야 함: {order.shares}"
    try:
        price = float(order.limit_price)
    except (TypeError, ValueError):
        return f"지정가가 숫자가 아님: {order.limit_price!r}"
    if not price > 0 or price == float("inf"):   # NaN 도 여기서 걸린다 (NaN > 0 은 False)
        return f"지정가는 0보다 큰 숫자여야 함: {order.limit_price!r}"
    if not str(order.trainer).strip():
        return "트레이너 이름이 비어 있음"
    if not _is_date(order.signal_date):
        return f"신호 날짜 형식이 'YYYY-MM-DD' 가 아님: {order.signal_date!r}"
    return None


def _is_date(s) -> bool:
    from datetime import date
    try:
        return isinstance(s, str) and len(s) == 10 and date.fromisoformat(s).isoformat() == s
    except ValueError:
        return False


def fail(client_id: str, kind: str, message: str) -> OrderResult:
    """실패 결과를 만드는 지름길. kind 가 이상하면 unknown 으로."""
    if kind not in ERROR_KINDS:
        kind = "unknown"
    return OrderResult(client_id=client_id, ok=False, broker_order_id=None,
                       error_kind=kind, message=message)
