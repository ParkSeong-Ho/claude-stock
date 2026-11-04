"""
broker/fake.py - 테스트용 가짜 브로커
------------------------------------------------------------------
미리 정해 둔 응답·오류를 순서대로 돌려준다. 네트워크도 파일도 쓰지 않는다.

초보자용 설명:
- script 는 place() 가 불릴 때마다 앞에서부터 하나씩 꺼내 쓰는 "대본"이다.
  대본 한 칸에 넣을 수 있는 것:
    "ok" 또는 None          → 성공 (주문번호는 FAKE-000001 처럼 자동)
    "network", "rejected"… → 그 종류(error_kind)의 실패
    BrokerError(...)        → 그 오류의 kind·메시지로 실패 (예외를 던지지는 않음)
    OrderResult(...)        → 그대로 돌려줌 (client_id 가 비어 있으면 주문의 것으로 채움)
    dict                    → OrderResult 칸 이름으로 일부만 지정 {"ok": False, "error_kind": "auth"}
  대본을 다 쓰면 그 뒤로는 성공으로 본다.
- placed 에는 place() 로 받은 주문이 순서대로 쌓인다 → "몇 번 냈나(재시도 안 했나)" 확인용.
- 조회(fills/holdings/buyable_shares)는 query_errors 에 넣은 오류를 앞에서부터 하나씩 던진 뒤
  정상값을 돌려준다 → "조회 재시도" 테스트용.
- fill_on_place=True 면 성공한 주문을 지정가 전량 체결로 fills 에 더한다 (날짜는 fill_date).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from broker.base import ERROR_KINDS, BrokerError, Fill, Order, OrderResult, fail


class FakeBroker:
    """미리 정한 응답·오류를 순서대로 돌려주는 테스트용 브로커."""

    name = "fake"

    def __init__(self, script: Iterable | None = None, *,
                 fills: Iterable[Fill] | None = None,
                 holdings: dict[str, dict[str, int]] | None = None,
                 buyable: dict | int | None = None,
                 query_errors: Iterable[BrokerError] | None = None,
                 fill_on_place: bool = False,
                 fill_date: str | None = None):
        # holdings: {"kr": {"005930": 3}, "us": {...}}
        # buyable:  정수 하나(모든 종목 같은 값) 또는 {(market, code): 수량} 또는 {code: 수량}
        self.script = list(script or [])
        self._fills = list(fills or [])
        self._holdings = {m: dict(h) for m, h in (holdings or {}).items()}
        self._buyable = buyable
        self.query_errors = list(query_errors or [])
        self.fill_on_place = fill_on_place
        self.fill_date = fill_date
        self.placed: list[Order] = []      # place() 로 받은 주문들 (순서대로)
        self.results: list[OrderResult] = []
        self.query_calls: list[tuple] = []  # 조회 호출 기록 (이름, 인자...)
        self._next_id = 1

    # ---------- 주문 ----------
    def place(self, order: Order) -> OrderResult:
        """대본에서 다음 응답을 꺼내 돌려준다. 예외를 던지지 않는다."""
        self.placed.append(order)
        try:
            cid = order.client_id
        except Exception:
            cid = ""
        step = self.script.pop(0) if self.script else "ok"
        try:
            result = self._result_from(step, cid)
        except Exception as e:  # 대본이 이상해도 예외는 밖으로 내보내지 않는다
            result = fail(cid, "unknown", f"가짜 브로커 대본 오류: {e}")
        if result.ok and self.fill_on_place:
            self._fills.append(Fill(
                broker_order_id=result.broker_order_id or "",
                market=order.market, code=order.code, side=order.side,
                shares=int(order.shares), price=float(order.limit_price),
                date=self.fill_date or order.signal_date,
            ))
        self.results.append(result)
        return result

    def _new_id(self) -> str:
        oid = f"FAKE-{self._next_id:06d}"
        self._next_id += 1
        return oid

    def _result_from(self, step, cid: str) -> OrderResult:
        if step is None or step == "ok":
            return OrderResult(cid, True, self._new_id(), None, "가짜 주문 접수")
        if isinstance(step, str):
            kind = step if step in ERROR_KINDS else "unknown"
            return fail(cid, kind, f"가짜 오류: {step}")
        if isinstance(step, BrokerError):
            return fail(cid, step.kind, step.message or step.kind)
        if isinstance(step, OrderResult):
            return step if step.client_id else replace(step, client_id=cid)
        if isinstance(step, dict):
            ok = bool(step.get("ok", False))
            return OrderResult(
                client_id=step.get("client_id", cid),
                ok=ok,
                broker_order_id=step.get("broker_order_id", self._new_id() if ok else None),
                error_kind=step.get("error_kind", None if ok else "unknown"),
                message=step.get("message", ""),
            )
        raise TypeError(f"모르는 대본 칸: {step!r}")

    # ---------- 조회 ----------
    def _maybe_raise(self, *call):
        self.query_calls.append(call)
        if self.query_errors:
            raise self.query_errors.pop(0)

    def fills(self, market: str, date: str) -> list[Fill]:
        self._maybe_raise("fills", market, date)
        return [f for f in self._fills if f.market == market and f.date == date]

    def holdings(self, market: str) -> dict[str, int]:
        self._maybe_raise("holdings", market)
        return dict(self._holdings.get(market, {}))

    def buyable_shares(self, market: str, code: str, price: float) -> int | None:
        self._maybe_raise("buyable_shares", market, code, price)
        b = self._buyable
        if b is None or isinstance(b, int):
            return b
        if (market, code) in b:
            return b[(market, code)]
        return b.get(code)
