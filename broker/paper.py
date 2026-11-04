"""
broker/paper.py - 종이 브로커 (오프라인 기본값)
------------------------------------------------------------------
진짜 증권사에 연결하지 않고, 주문을 파일(JSON Lines, 한 줄에 주문 하나)에 적어 두기만 한다.
주문은 지정가에 "즉시 전부 체결"된 것으로 본다. 그래서 fills() 는 적어 둔 주문을 그대로 돌려준다.

초보자용 설명:
- 키·인터넷 없이 order_runner 흐름(주문 → 체결 조회 → 장부와 비교)을 끝까지 돌려 보는 연습용.
- 같은 client_id(주문 이름표) 주문이 파일에 이미 있으면 거부한다(K-D4: 같은 주문 두 번 금지).
- 실패해도 예외를 던지지 않고 OrderResult(ok=False, ...) 로 알린다. 재시도는 하지 않는다.
- 이 브로커는 현금을 모른다 → buyable_shares() 는 None("모름").
- 이 브로커가 기억하는 보유 수량은 "이 파일에 적힌 주문"만으로 계산한다.
  파일을 쓰기 전부터 장부에 있던 종목은 모르므로, 팔 때 보유 수량을 따지지 않는다.

파일 한 줄의 모양 (예):
{"client_id": "kr-sprinter-005930-buy-2026-11-03", "broker_order_id": "PAPER-000001",
 "market": "kr", "code": "005930", "side": "buy", "shares": 3, "limit_price": 55000.0,
 "trainer": "sprinter", "signal_date": "2026-11-03", "fill_date": "2026-11-04", "placed_at": "..."}
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from broker.base import Fill, Order, OrderResult, BrokerError, fail, validate_order

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "state" / "broker" / "paper_broker.jsonl"   # state/ 는 gitignore 됨

# 체결 날짜는 그 시장의 현지 날짜로 적는다 (markets.py 와 같은 값. 여기서는 import 하지 않고 따로 둠)
_MARKET_TZ = {"us": "America/New_York", "kr": "Asia/Seoul"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaperBroker:
    """주문을 파일에 적고, 지정가에 즉시 체결된 것으로 보는 가짜 브로커."""

    name = "paper"

    def __init__(self, path: str | os.PathLike | None = None,
                 clock: Callable[[], datetime] = _utc_now):
        # path: 주문을 적을 파일. 상대경로면 프로젝트 폴더 기준.
        # clock: 지금 시각을 돌려주는 함수 (테스트에서 날짜를 고정하려고 바꿔 끼운다)
        p = Path(path) if path is not None else DEFAULT_PATH
        self.path = p if p.is_absolute() else ROOT / p
        self.clock = clock

    # ---------- 파일 읽기 ----------
    def _records(self) -> list[dict]:
        """파일에 적힌 주문 줄들. 파일이 없으면 빈 목록. 깨진 줄은 건너뛴다."""
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue   # 중간에 끊긴 줄 등. 나머지는 계속 읽는다
                if isinstance(rec, dict):
                    out.append(rec)
        return out

    def _local_date(self, market: str) -> str:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(ZoneInfo(_MARKET_TZ.get(market, "UTC"))).date().isoformat()

    # ---------- Broker 기능 ----------
    def place(self, order: Order) -> OrderResult:
        """주문을 파일에 한 줄 적는다. 예외를 던지지 않는다. 재시도하지 않는다."""
        try:
            cid = order.client_id
        except Exception as e:  # 주문서가 아예 이상한 경우
            return fail("", "rejected", f"주문서를 읽을 수 없음: {e}")
        try:
            problem = validate_order(order)
            if problem:
                return fail(cid, "rejected", problem)

            records = self._records()
            if any(r.get("client_id") == cid for r in records):
                return fail(cid, "rejected", f"같은 주문이 이미 있음(중복 거부): {cid}")

            broker_order_id = f"PAPER-{len(records) + 1:06d}"
            rec = asdict(order)
            rec["limit_price"] = float(order.limit_price)
            rec.update(
                client_id=cid,
                broker_order_id=broker_order_id,
                fill_date=self._local_date(order.market),
                placed_at=self.clock().isoformat(),
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return OrderResult(client_id=cid, ok=True, broker_order_id=broker_order_id,
                               error_kind=None,
                               message=f"종이 주문 접수·즉시 체결: {order.side} {order.code} "
                                       f"{order.shares}주 @ {float(order.limit_price):g}")
        except Exception as e:  # 파일 쓰기 실패 등. 절대 예외를 밖으로 내보내지 않는다
            return fail(cid, "unknown", f"종이 주문 기록 실패: {type(e).__name__}: {e}")

    def fills(self, market: str, date: str) -> list[Fill]:
        """그날 체결 내역 = 그날 적힌 주문 전부 (지정가에 전량 체결로 봄)."""
        try:
            records = self._records()
        except OSError as e:
            raise BrokerError("unknown", f"종이 주문 파일을 읽을 수 없음: {e}") from e
        return [
            Fill(broker_order_id=r["broker_order_id"], market=r["market"], code=r["code"],
                 side=r["side"], shares=int(r["shares"]), price=float(r["limit_price"]),
                 date=r["fill_date"])
            for r in records
            if r.get("market") == market and r.get("fill_date") == date
        ]

    def holdings(self, market: str) -> dict[str, int]:
        """이 파일에 적힌 주문만으로 계산한 보유 수량 (0주가 된 종목은 뺀다)."""
        try:
            records = self._records()
        except OSError as e:
            raise BrokerError("unknown", f"종이 주문 파일을 읽을 수 없음: {e}") from e
        held: dict[str, int] = {}
        for r in records:
            if r.get("market") != market:
                continue
            n = int(r["shares"]) if r.get("side") == "buy" else -int(r["shares"])
            held[r["code"]] = held.get(r["code"], 0) + n
        return {code: n for code, n in held.items() if n != 0}

    def buyable_shares(self, market: str, code: str, price: float) -> int | None:
        """종이 브로커는 현금을 모른다 → None. (수량은 장부의 shares_within_cap 으로 정한다)"""
        return None
