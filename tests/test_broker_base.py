"""
test_broker_base.py - broker/ 뼈대(K1) 테스트. 네트워크·키 없이, 파일은 tmp_path 에만.
"""

import json
import sys
from datetime import datetime, timezone

import pytest

from broker import (ERROR_KINDS, Broker, BrokerError, FakeBroker, Fill, Order, OrderResult,
                    PaperBroker, make_broker, validate_order)


def kr_order(**kw):
    base = dict(market="kr", code="005930", side="buy", shares=3, limit_price=55000.0,
                trainer="sprinter", signal_date="2026-11-03")
    base.update(kw)
    return Order(**base)


def fixed_clock(iso="2026-11-04T00:30:00+00:00"):
    # 2026-11-04 00:30 UTC = 한국 09:30 (11-04), 미국 동부 11-03 19:30
    return lambda: datetime.fromisoformat(iso)


# ---------------- base ----------------

def test_client_id_형식():
    o = kr_order()
    assert o.client_id == "kr-sprinter-005930-buy-2026-11-03"
    assert Order("us", "AAPL", "sell", 1, 190.5, "pioneer", "2026-11-02").client_id \
        == "us-pioneer-AAPL-sell-2026-11-02"


def test_brokererror_kind():
    e = BrokerError("network", "연결 끊김")
    assert e.kind == "network" and "연결 끊김" in str(e)
    assert isinstance(e, Exception)
    weird = BrokerError("이상한값", "x")
    assert weird.kind == "unknown" and "이상한값" in str(weird)
    assert set(ERROR_KINDS) == {"network", "auth", "rate_limit", "rejected", "mock_expired", "unknown"}


@pytest.mark.parametrize("kw", [
    dict(market="jp"), dict(side="hold"), dict(shares=0), dict(shares=-1), dict(shares=1.5),
    dict(shares=True), dict(limit_price=0), dict(limit_price=float("nan")),
    dict(limit_price=float("inf")), dict(limit_price="abc"), dict(code=""),
    dict(trainer=""), dict(signal_date="2026/11/03"), dict(signal_date="2026-13-01"),
])
def test_validate_order_나쁜_주문(kw):
    assert validate_order(kr_order(**kw)) is not None


def test_validate_order_좋은_주문():
    assert validate_order(kr_order()) is None
    assert validate_order(kr_order(limit_price=55000)) is None   # 정수 가격도 OK


def test_protocol_구현():
    assert isinstance(PaperBroker("x.jsonl"), Broker)
    assert isinstance(FakeBroker(), Broker)


# ---------------- PaperBroker ----------------

def test_paper_주문_기록과_즉시체결(tmp_path):
    path = tmp_path / "sub" / "paper.jsonl"
    b = PaperBroker(path, clock=fixed_clock())
    r = b.place(kr_order())
    assert r.ok and r.error_kind is None
    assert r.client_id == "kr-sprinter-005930-buy-2026-11-03"
    assert r.broker_order_id == "PAPER-000001"

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["client_id"] == r.client_id and rec["shares"] == 3 and rec["fill_date"] == "2026-11-04"

    fills = b.fills("kr", "2026-11-04")
    assert fills == [Fill("PAPER-000001", "kr", "005930", "buy", 3, 55000.0, "2026-11-04")]
    assert b.fills("kr", "2026-11-03") == []
    assert b.fills("us", "2026-11-04") == []


def test_paper_체결날짜는_시장_현지날짜(tmp_path):
    b = PaperBroker(tmp_path / "p.jsonl", clock=fixed_clock())
    b.place(Order("us", "AAPL", "buy", 2, 190.0, "sprinter", "2026-11-02"))
    assert [f.code for f in b.fills("us", "2026-11-03")] == ["AAPL"]   # 뉴욕은 아직 11-03


def test_paper_같은_client_id_두번이면_거부(tmp_path):
    path = tmp_path / "p.jsonl"
    b = PaperBroker(path, clock=fixed_clock())
    assert b.place(kr_order()).ok
    r2 = b.place(kr_order(shares=5))           # 수량만 달라도 같은 신호 → 같은 이름표
    assert not r2.ok and r2.error_kind == "rejected" and r2.broker_order_id is None
    # 새로 만든 브로커(프로그램 재실행)도 파일을 보고 거부한다
    r3 = PaperBroker(path, clock=fixed_clock()).place(kr_order())
    assert not r3.ok and r3.error_kind == "rejected"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    # 다른 주문은 들어간다
    r4 = b.place(kr_order(side="sell"))
    assert r4.ok and r4.broker_order_id == "PAPER-000002"


def test_paper_나쁜_주문은_rejected_파일에_안씀(tmp_path):
    path = tmp_path / "p.jsonl"
    r = PaperBroker(path).place(kr_order(shares=0))
    assert not r.ok and r.error_kind == "rejected" and r.message
    assert not path.exists()


def test_paper_place_는_예외를_던지지_않음(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    b = PaperBroker(blocker / "p.jsonl")       # 부모가 파일이라 폴더를 못 만듦
    r = b.place(kr_order())
    assert not r.ok and r.error_kind == "unknown"


def test_paper_holdings_와_깨진줄(tmp_path):
    path = tmp_path / "p.jsonl"
    b = PaperBroker(path, clock=fixed_clock())
    b.place(kr_order(shares=5))
    b.place(kr_order(code="000660", shares=2))
    b.place(kr_order(side="sell", shares=5, signal_date="2026-11-04"))
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"client_id": "끊긴 줄\n')
    b.place(Order("us", "AAPL", "buy", 1, 190.0, "sprinter", "2026-11-02"))
    assert b.holdings("kr") == {"000660": 2}   # 005930 은 다 팔아서 빠짐
    assert b.holdings("us") == {"AAPL": 1}
    assert b.buyable_shares("kr", "005930", 55000) is None


def test_paper_상대경로는_프로젝트_폴더_기준():
    from broker.paper import ROOT
    assert PaperBroker("state/broker/x.jsonl").path == ROOT / "state" / "broker" / "x.jsonl"


# ---------------- FakeBroker ----------------

def test_fake_대본_순서대로():
    b = FakeBroker(["ok", "network", BrokerError("mock_expired", "모의기간 만료"),
                    {"ok": False, "error_kind": "rate_limit", "message": "천천히"},
                    OrderResult("", True, "X-1", None, "수동")])
    rs = [b.place(kr_order(code=str(i))) for i in range(6)]
    assert [r.ok for r in rs] == [True, False, False, False, True, True]   # 대본 소진 뒤엔 성공
    assert [r.error_kind for r in rs] == [None, "network", "mock_expired", "rate_limit", None, None]
    assert rs[2].message == "모의기간 만료"
    assert rs[4].broker_order_id == "X-1" and rs[4].client_id == kr_order(code="4").client_id
    assert rs[0].broker_order_id != rs[5].broker_order_id
    assert len(b.placed) == 6 and all(isinstance(r.client_id, str) and r.client_id for r in rs)


def test_fake_place_는_한번만_예외없음():
    b = FakeBroker([object()])                 # 이상한 대본 칸
    r = b.place(kr_order())
    assert not r.ok and r.error_kind == "unknown"
    assert len(b.placed) == 1


def test_fake_조회_오류뒤_정상():
    f = Fill("F1", "kr", "005930", "buy", 3, 55000.0, "2026-11-04")
    b = FakeBroker(fills=[f], holdings={"kr": {"005930": 3}}, buyable={("kr", "005930"): 7},
                   query_errors=[BrokerError("network")])
    with pytest.raises(BrokerError) as ei:
        b.fills("kr", "2026-11-04")
    assert ei.value.kind == "network"
    assert b.fills("kr", "2026-11-04") == [f]  # 다시 부르면 정상 (조회는 재시도 가능)
    assert b.holdings("kr") == {"005930": 3} and b.holdings("us") == {}
    assert b.buyable_shares("kr", "005930", 55000) == 7
    assert b.buyable_shares("kr", "000660", 1) is None
    assert FakeBroker(buyable=4).buyable_shares("us", "AAPL", 1) == 4
    assert len(b.query_calls) == 6


def test_fake_fill_on_place():
    b = FakeBroker(["ok", "rejected"], fill_on_place=True, fill_date="2026-11-04")
    b.place(kr_order())
    b.place(kr_order(code="000660"))
    fills = b.fills("kr", "2026-11-04")
    assert len(fills) == 1 and fills[0].code == "005930" and fills[0].price == 55000.0


# ---------------- make_broker ----------------

def test_make_broker_paper_fake(tmp_path):
    p = make_broker("paper", path=tmp_path / "p.jsonl")
    assert isinstance(p, PaperBroker) and p.name == "paper"
    f = make_broker(" FAKE ", script=["auth"])
    assert isinstance(f, FakeBroker) and f.place(kr_order()).error_kind == "auth"


def test_make_broker_모르는_이름():
    with pytest.raises(ValueError, match="paper"):
        make_broker("toss")


def test_make_broker_kis_없으면_친절한_오류(monkeypatch):
    # broker/kis.py 가 없는 상황을 흉내 (이미 있어도 import 를 막는다)
    monkeypatch.setitem(sys.modules, "broker.kis", None)
    with pytest.raises(ImportError, match="broker/kis.py"):
        make_broker("kis")


def test_make_broker_kis_늦은_import(monkeypatch):
    import types
    fake_mod = types.ModuleType("broker.kis")

    class KisBroker:
        name = "kis"

        def __init__(self, **kw):
            self.kw = kw
    fake_mod.KisBroker = KisBroker
    monkeypatch.setitem(sys.modules, "broker.kis", fake_mod)
    b = make_broker("kis", env={"KIS_MODE": "mock"})
    assert isinstance(b, KisBroker) and b.kw == {"env": {"KIS_MODE": "mock"}}
