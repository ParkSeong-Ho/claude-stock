"""
broker - 증권사 연결 꾸러미 (docs/kr-broker-design.md §3)
------------------------------------------------------------------
초보자용 설명:
- make_broker("paper") : 파일에만 적는 종이 브로커 (키·인터넷 필요 없음, 기본값)
- make_broker("fake")  : 테스트용 가짜 브로커 (대본대로 응답)
- make_broker("kis")   : 한국투자증권 모의투자 (broker/kis.py, 키는 .env 에서)

    from broker import make_broker, Order
    b = make_broker("paper")
    r = b.place(Order("kr", "005930", "buy", 3, 55000, "sprinter", "2026-11-03"))
    if not r.ok:
        print(r.error_kind, r.message)
"""

from __future__ import annotations

from broker.base import (ERROR_KINDS, Broker, BrokerError, Fill, Order, OrderResult,
                         validate_order)
from broker.fake import FakeBroker
from broker.paper import PaperBroker

__all__ = [
    "ERROR_KINDS", "Broker", "BrokerError", "Fill", "Order", "OrderResult",
    "validate_order", "FakeBroker", "PaperBroker", "make_broker", "BROKER_NAMES",
]

BROKER_NAMES = ("paper", "fake", "kis")


def make_broker(name: str, **kwargs) -> Broker:
    """이름으로 브로커를 만든다. kwargs 는 그 브로커의 생성자에 그대로 넘긴다.

    - "paper": PaperBroker(path=None, clock=...)
    - "fake" : FakeBroker(script=None, ...)
    - "kis"  : broker.kis.KisBroker(env=None, http=None, ...)  ← 필요할 때만 늦게 불러온다
               (kis 를 안 쓰는 사람은 requests·키가 없어도 paper/fake 를 쓸 수 있게)
    """
    key = str(name).strip().lower()
    if key == "paper":
        return PaperBroker(**kwargs)
    if key == "fake":
        return FakeBroker(**kwargs)
    if key == "kis":
        try:
            from broker.kis import KisBroker
        except ModuleNotFoundError as e:
            if e.name in ("broker.kis",):
                raise ImportError(
                    "KIS 브로커(broker/kis.py)가 아직 없습니다. "
                    "K2 작업(kr-k2-kis 브랜치)이 합쳐진 뒤에 --broker kis 를 쓸 수 있어요. "
                    "지금은 --broker paper 로 연습하세요."
                ) from e
            raise ImportError(
                f"KIS 브로커에 필요한 패키지 '{e.name}' 가 설치되어 있지 않습니다. "
                f"~/.venv-cs/bin/pip install {e.name} 로 설치하세요."
            ) from e
        return KisBroker(**kwargs)
    raise ValueError(f"모르는 브로커 이름: {name!r} (쓸 수 있는 것: {', '.join(BROKER_NAMES)})")
