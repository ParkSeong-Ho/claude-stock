"""order_runner (K3) 테스트 — 네트워크·증권사 키 없음.

확인하는 것:
- 두 번 실행해도 주문은 1번 (state/broker/<시장>-orders.jsonl 로 중복 방지)
- '보내는 중'만 남은 주문(결과 불명)은 다시 내지 않음
- 0주 보류: 상한 안에서 1주도 못 사거나 증권사 매수가능 0주면 주문 안 하고 사유 기록
- 매수 수량 = min(상한 수량, 증권사 매수가능), 매도 수량 = 장부 보유 수량
- 호가 맞춤: 종가 × (1 ± 0.5%) → 매수 올림 / 매도 내림
- 오류 규칙: rejected·network·예외는 그 주문만 실패하고 계속 / mock_expired·auth 는 남은 주문 중단
- reconcile 보고서: 일치·부분체결·미체결·주문 오류·장부 미반영·기록에 없는 체결
- 시장별 상태 파일 경로 (us: state/, kr: state/kr/)

broker/(K1)·markets.py(K4) 가 아직 없으면 §3 시그니처대로 최소 가짜를 이 파일 안에서 끼운다.
있으면 진짜를 쓴다(합친 뒤에도 같은 테스트가 돈다).
"""
import json
import math
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest


# ---------------- 다른 세션 모듈이 없을 때만 쓰는 최소 가짜 ----------------

def _install_fake_broker():
    m = types.ModuleType("broker")

    @dataclass
    class Order:
        market: str
        code: str
        side: str
        shares: int
        limit_price: float
        trainer: str
        signal_date: str

        @property
        def client_id(self):
            return f"{self.market}-{self.trainer}-{self.code}-{self.side}-{self.signal_date}"

    @dataclass
    class OrderResult:
        client_id: str
        ok: bool
        broker_order_id: object
        error_kind: object
        message: str

    @dataclass
    class Fill:
        broker_order_id: str
        market: str
        code: str
        side: str
        shares: int
        price: float
        date: str

    class BrokerError(Exception):
        def __init__(self, kind="unknown", message=""):
            super().__init__(message)
            self.kind = kind

    def make_broker(name):
        raise RuntimeError("테스트용 가짜 broker: make_broker 는 monkeypatch 로 바꿔 끼우세요")

    m.Order, m.OrderResult, m.Fill, m.BrokerError, m.make_broker = Order, OrderResult, Fill, BrokerError, make_broker
    sys.modules["broker"] = m


def _install_fake_markets():
    m = types.ModuleType("markets")

    @dataclass(frozen=True)
    class Market:
        key: str
        currency: str
        fee_rate: float
        sell_tax_rate: float
        slippage: float
        benchmark: str
        tz: str
        close_cutoff: str
        total_cash: float

    MARKETS = {
        "us": Market("us", "USD", 0.001, 0.0, 0.0005, "SPY", "America/New_York", "16:15", 10_000),
        "kr": Market("kr", "KRW", 0.00015, 0.0020, 0.0005, "KS200", "Asia/Seoul", "16:00", 10_000_000),
    }

    def _kr_tick(p):
        for limit, tick in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50),
                            (200_000, 100), (500_000, 500)):
            if p < limit:
                return tick
        return 1_000

    def round_to_tick(market_key, price, side):
        tick = 0.01 if market_key == "us" else _kr_tick(price)
        q = price / tick
        q = math.ceil(q - 1e-9) if side == "buy" else math.floor(q + 1e-9)
        return round(q * tick, 2) if market_key == "us" else float(q * tick)

    def money(market_key, v, sign=True):
        s = "+" if (sign and v >= 0) else ("-" if v < 0 else "")
        return f"{s}${abs(v):,.2f}" if market_key == "us" else f"{s}{abs(v):,.0f}원"

    m.Market, m.MARKETS = Market, MARKETS
    m.get_market = lambda key: MARKETS[key]
    m.round_to_tick, m.money = round_to_tick, money
    m.KR_UNIVERSE = {"삼성전자": "005930"}
    sys.modules["markets"] = m


try:
    from broker import Order, OrderResult, Fill  # noqa: F401
except ImportError:
    _install_fake_broker()
try:
    from markets import round_to_tick, get_market  # noqa: F401
except ImportError:
    _install_fake_markets()

import broker          # noqa: E402
import markets         # noqa: E402
import order_runner as R   # noqa: E402

KST_MORNING = datetime(2026, 11, 5, 9, 5)     # 목요일 09:05 (시간대 없음 → 시장 현지 시각)
SIG = "2026-11-04"


class KindError(Exception):
    """kind 가 붙은 오류 (BrokerError 처럼 행동)."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


class ScriptBroker:
    """FakeBroker 상당: 주문마다 미리 정한 응답을 순서대로 돌려준다.
    script 항목: "ok" | 오류 kind 문자열 | Exception 객체(던짐). 다 쓰면 "ok"."""

    name = "script"

    def __init__(self, script=(), buyable=None, fills=None):
        self.script = list(script)
        self.buyable = buyable or {}
        self.fills_by_date = fills or {}
        self.placed = []
        self.fill_calls = 0
        self.fill_errors = []

    def place(self, order):
        self.placed.append(order)
        step = self.script.pop(0) if self.script else "ok"
        if isinstance(step, Exception):
            raise step
        if step == "ok":
            return broker.OrderResult(client_id=order.client_id, ok=True,
                                      broker_order_id=f"B{len(self.placed)}", error_kind=None, message="접수")
        return broker.OrderResult(client_id=order.client_id, ok=False, broker_order_id=None,
                                  error_kind=step, message=f"가짜 {step}")

    def fills(self, market, date):
        self.fill_calls += 1
        if self.fill_errors:
            raise self.fill_errors.pop(0)
        return list(self.fills_by_date.get(date, []))

    def holdings(self, market):
        return {}

    def buyable_shares(self, market, code, price):
        return self.buyable.get(code)


# ---------------- 준비물 ----------------

def team_state(cash, pending=(), positions=None, log=None, fee=0.001, slip=0.0005, tax=0.0):
    """team.py 가 저장하는 모양 그대로의 상태 dict."""
    positions = positions or {}
    return {
        "wallet": {"name": "t", "cash": cash, "currency": "USD", "fee_rate": fee, "sell_tax_rate": tax,
                   "slippage": slip,
                   "holdings": {c: {"shares": p["shares"], "avg_price": p["buy_price"]} for c, p in positions.items()},
                   "log": log or []},
        "positions": positions, "pending": list(pending), "prev_value": cash, "stopped": False,
        "last_date": SIG, "start_cash": cash, "start_date": "2026-10-01", "schema": "v1-usd-1",
    }


def buy(code, sd=SIG):
    return {"code": code, "action": "매수", "signal_date": sd, "reason": "가짜 매수"}


def sell(code, sd=SIG):
    return {"code": code, "action": "매도", "signal_date": sd, "reason": "가짜 매도"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """state/·reports/ 를 임시 폴더로. 상태 파일 쓰는 함수를 돌려준다."""
    monkeypatch.setattr(R, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(R, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(R, "SLEEP", lambda s: None)

    def write(market, trainer, st):
        p = R.state_path(market, trainer)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        return p
    write.root = tmp_path
    return write


def closes(table):
    """close_fn 가짜: {종목: 종가}."""
    return lambda market, code, sd: table.get(code)


def journal(market):
    p = R.journal_path(market)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def quiet(*a, **k):
    pass


# ---------------- 호가 맞춤 · 수량 (build_orders, 순수 함수) ----------------

def test_지정가_호가_맞춤_국내_매수올림_매도내림():
    states = {"마라토너": team_state(10_000_000, [buy("005930"), sell("000660")],
                                     positions={"000660": {"shares": 3, "buy_price": 150_000,
                                                           "days_held": 2, "buy_date": "2026-11-01"}})}
    last = {"005930": 61_234, "000660": 183_456}
    orders = {o.code: o for o in R.build_orders("kr", states, last, {"마라토너": 0.30})}
    # 61,234 × 1.005 = 61,540.17 → 100원 단위 올림 = 61,600
    assert orders["005930"].limit_price == 61_600
    # 183,456 × 0.995 = 182,538.72 → 100원 단위 내림 = 182,500
    assert orders["000660"].limit_price == 182_500
    for o in orders.values():
        assert o.limit_price == markets.round_to_tick("kr", o.limit_price, o.side)  # 이미 호가에 맞음


def test_지정가_호가_맞춤_미국_센트():
    states = {"스프린터": team_state(3_000, [buy("AAPL")])}
    o, = R.build_orders("us", states, {"AAPL": 100.003}, {"스프린터": 0.20})
    assert o.limit_price == pytest.approx(100.51)        # 100.508... → 올림
    assert o.side == "buy" and o.market == "us" and o.signal_date == SIG
    assert o.client_id == f"us-스프린터-AAPL-buy-{SIG}"


def test_매수_수량은_상한과_매수가능_중_작은_값():
    st = {"마라토너": team_state(6_000, [buy("AAPL"), buy("MSFT")])}
    last = {"AAPL": 100.0, "MSFT": 100.0}
    cap = {"마라토너": 0.30}
    # 상한 $1,800, 지정가 $100.50 → shares_within_cap = 17주
    n_cap = R.shares_within_cap(6_000, 0.30, 100.50, 0.001, 0.0005)
    assert n_cap == 17
    orders = {o.code: o for o in R.build_orders("us", st, last, cap, buyable={"AAPL": 5, "MSFT": None})}
    assert orders["AAPL"].shares == 5           # 증권사가 5주만 가능 → 5
    assert orders["MSFT"].shares == n_cap       # 모름(None) → 상한 기준
    # 함수로 넘겨도 같고, 조회가 터져도 상한 기준으로
    def boom(code, px):
        raise KindError("network")
    o, = R.build_orders("us", {"마라토너": team_state(6_000, [buy("AAPL")])}, last, cap, buyable=boom)
    assert o.shares == n_cap


def test_매도_수량은_장부_보유_수량():
    st = {"파이오니어": team_state(1_000, [sell("NVDA")],
                                   positions={"NVDA": {"shares": 7, "buy_price": 120.0, "days_held": 3,
                                                       "buy_date": "2026-10-30"}})}
    o, = R.build_orders("us", st, {"NVDA": 130.0}, {"파이오니어": 0.15}, buyable={"NVDA": 0})
    assert (o.side, o.shares) == ("sell", 7)     # 매도엔 매수가능수량이 상관없음
    assert o.limit_price == pytest.approx(129.35)   # 130 × 0.995 = 129.35


def test_0주면_주문_안_하고_사유_기록():
    skips = []
    st = {"파이오니어": team_state(1_000, [buy("NVDA"), buy("AAPL"), sell("TSLA"), buy("MSFT")])}
    last = {"NVDA": 2_500.0, "AAPL": 50.0, "TSLA": 200.0}       # MSFT 종가 없음
    orders = R.build_orders("us", st, last, {"파이오니어": 0.15}, buyable={"AAPL": 0}, skips=skips)
    assert orders == []
    why = {s["code"]: s["reason"] for s in skips}
    assert "1주도 못 삼" in why["NVDA"]          # 상한 $150 < 1주
    assert "매수가능수량 0주" in why["AAPL"]
    assert "보유 수량이 없음" in why["TSLA"]
    assert "종가" in why["MSFT"]
    assert skips[0]["client_id"] == f"us-파이오니어-NVDA-buy-{SIG}"


# ---------------- place: 중복 방지 · 경로 · 오류 규칙 ----------------

def test_두번_실행해도_주문은_1번(home):
    home("kr", "마라토너", team_state(10_000_000, [buy("005930"), sell("000660")],
                                    positions={"000660": {"shares": 4, "buy_price": 150_000,
                                                          "days_held": 1, "buy_date": "2026-11-03"}}))
    b = ScriptBroker()
    cf = closes({"005930": 60_000, "000660": 180_000})
    r1 = R.place("kr", b, now=KST_MORNING, close_fn=cf, log=quiet)
    r2 = R.place("kr", b, now=KST_MORNING, close_fn=cf, log=quiet)
    r3 = R.place("kr", b, now=datetime(2026, 11, 6, 9, 5), close_fn=cf, log=quiet)   # 다음 날에도
    assert len(r1) == 2 and r2 == [] and r3 == []
    assert len(b.placed) == 2
    sent = [r for r in journal("kr") if r["status"] == "sending"]
    assert sorted(r["client_id"] for r in sent) == sorted(
        [f"kr-마라토너-005930-buy-{SIG}", f"kr-마라토너-000660-sell-{SIG}"])
    # 장부는 손대지 않는다 (K-D3)
    assert json.loads(R.state_path("kr", "마라토너").read_text(encoding="utf-8"))["pending"][0]["code"] == "005930"


def test_시장별_상태_파일_경로(home):
    assert R.state_path("us", "스프린터") == R.STATE_DIR / "team_스프린터.json"
    assert R.state_path("kr", "스프린터") == R.STATE_DIR / "kr" / "team_스프린터.json"
    home("us", "스프린터", team_state(3_000, [buy("AAPL")]))
    b = ScriptBroker()
    assert R.place("kr", b, now=KST_MORNING, close_fn=closes({"AAPL": 100}), log=quiet) == []   # kr 은 비어 있음
    assert len(R.place("us", b, now=datetime(2026, 11, 5, 9, 35), close_fn=closes({"AAPL": 100}), log=quiet)) == 1
    assert R.journal_path("us").exists() and not R.journal_path("kr").exists()


def test_결과_불명_주문은_다시_내지_않음(home):
    home("us", "스프린터", team_state(3_000, [buy("AAPL")]))
    cid = f"us-스프린터-AAPL-buy-{SIG}"
    R.append_journal("us", {"status": "sending", "client_id": cid, "date": "2026-11-05", "order": {}})
    b = ScriptBroker()
    msgs = []
    R.place("us", b, now=datetime(2026, 11, 5, 9, 35), close_fn=closes({"AAPL": 100}), log=msgs.append)
    assert b.placed == []
    assert any("결과를 모름" in m for m in msgs)


def test_0주_보류는_기록하고_주문_안_함(home):
    home("us", "파이오니어", team_state(1_000, [buy("NVDA")]))
    b = ScriptBroker()
    cf = closes({"NVDA": 2_500})
    R.place("us", b, now=datetime(2026, 11, 5, 9, 35), close_fn=cf, log=quiet)
    R.place("us", b, now=datetime(2026, 11, 5, 9, 36), close_fn=cf, log=quiet)
    assert b.placed == []
    sk = [r for r in journal("us") if r["status"] == "skipped"]
    assert len(sk) == 1 and "1주도 못 삼" in sk[0]["reason"]     # 같은 날 같은 사유는 한 줄만


def test_rejected_network_예외는_그_주문만_실패하고_계속(home):
    home("us", "마라토너", team_state(10_000, [buy("AAPL"), buy("MSFT"), buy("NVDA"), buy("AMZN")]))
    b = ScriptBroker(script=["rejected", "network", RuntimeError("터짐"), "ok"])
    cf = closes({"AAPL": 100, "MSFT": 100, "NVDA": 100, "AMZN": 100})
    res = R.place("us", b, now=datetime(2026, 11, 5, 9, 35), close_fn=cf, log=quiet)
    assert [r.ok for r in res] == [False, False, False, True]
    assert [r.error_kind for r in res] == ["rejected", "network", "unknown", None]
    # 같은 날 다시 돌려도 아무것도 다시 안 낸다 (주문 재시도 금지)
    R.place("us", b, now=datetime(2026, 11, 5, 10, 0), close_fn=cf, log=quiet)
    assert len(b.placed) == 4
    # 다음 거래일: '확실히 거절'(rejected)만 다시 낼 수 있다. network·예외는 들어갔을 수도 있어 영원히 안 냄
    R.place("us", b, now=datetime(2026, 11, 6, 9, 35), close_fn=cf, log=quiet)
    assert [o.code for o in b.placed[4:]] == ["AAPL"]


@pytest.mark.parametrize("kind, word", [("mock_expired", "모의투자 기간"), ("auth", "인증")])
def test_mock_expired_auth_는_크게_알리고_남은_주문_중단(home, kind, word):
    home("us", "마라토너", team_state(10_000, [buy("AAPL"), buy("MSFT"), buy("NVDA")]))
    b = ScriptBroker(script=["ok", kind])
    cf = closes({"AAPL": 100, "MSFT": 100, "NVDA": 100})
    msgs = []
    res = R.place("us", b, now=datetime(2026, 11, 5, 9, 35), close_fn=cf, log=msgs.append)
    assert [o.code for o in b.placed] == ["AAPL", "MSFT"]        # NVDA 는 안 냄
    assert res[-1].error_kind == kind
    text = "\n".join(msgs)
    assert word in text and "!!!!" in text and "남은 주문 1건" in text
    sent = {r["client_id"] for r in journal("us") if r["status"] == "sending"}
    assert f"us-마라토너-NVDA-buy-{SIG}" not in sent              # 기록 안 함 → 고친 뒤 다시 낼 수 있음
    # 고친 뒤 같은 날 다시 돌리면: 멈췄던 NVDA 만 나가고, 실패한 MSFT·성공한 AAPL 은 다시 안 나감
    R.place("us", b, now=datetime(2026, 11, 5, 9, 50), close_fn=cf, log=quiet)
    assert [o.code for o in b.placed] == ["AAPL", "MSFT", "NVDA"]


def test_주말에는_주문_안_냄(home):
    home("kr", "마라토너", team_state(10_000_000, [buy("005930")]))
    b = ScriptBroker()
    assert R.place("kr", b, now=datetime(2026, 11, 7, 9, 5), close_fn=closes({"005930": 60_000}), log=quiet) == []
    assert b.placed == []


# ---------------- reconcile 보고서 ----------------

def test_reconcile_보고서_내용(home):
    day = "2026-11-05"
    codes = ["005930", "035420", "051910", "207940", "000270"]
    # ① 아침: 스프린터 장부에 매수 대기 5건 → place
    st = team_state(10_000_000, [buy(c) for c in codes], fee=0.00015, tax=0.002)
    home("kr", "스프린터", st)
    b = ScriptBroker(script=["ok", "ok", "ok", "rejected", "ok"],
                     buyable={"005930": 10, "035420": 5, "051910": 4, "207940": 1, "000270": 2})
    cf = closes({"005930": 60_000, "035420": 200_000, "051910": 300_000, "207940": 900_000, "000270": 100_000})
    R.place("kr", b, now=datetime(2026, 11, 5, 9, 5), close_fn=cf, log=quiet)
    ids = {o.code: f"B{i + 1}" for i, o in enumerate(b.placed)}

    # ② 저녁: team.py 가 005930 만 장부에 시가 60,100원으로 체결했다고 치자 (나머지는 아직 미반영)
    amount = round(60_100 * 10 * 1.0005 * 1.00015, 2)
    st["wallet"]["log"] = [{"시각": day, "종류": "매수", "종목": "005930", "수량": 10, "금액": amount, "통화": "KRW"}]
    st["positions"] = {"005930": {"shares": 10, "buy_price": 60_100.0, "days_held": 0, "buy_date": day}}
    home("kr", "스프린터", st)

    F = broker.Fill
    b.fills_by_date[day] = [
        F(ids["005930"], "kr", "005930", "buy", 6, 60_200.0, day),          # 6 + 4 = 10주 전량 → 일치
        F(ids["005930"], "kr", "005930", "buy", 4, 60_200.0, day),
        F(ids["035420"], "kr", "035420", "buy", 2, 200_500.0, day),         # 5주 중 2주 → 부분체결
        # 051910 은 체결 없음 → 미체결 / 207940 은 rejected
        F(ids["000270"], "kr", "000270", "buy", 2, 100_000.0, day),         # 체결됐는데 장부엔 아직 없음
        F("X999", "kr", "005380", "sell", 1, 250_000.0, day),               # 우리가 안 낸 주문
    ]
    b.fill_errors = [KindError("network")]                                  # 조회는 한 번 실패 후 재시도
    path = R.reconcile("kr", b, day, log=quiet)
    assert path.endswith("kr-2026-11-05.md")
    assert b.fill_calls == 2
    text = open(path, encoding="utf-8").read()
    row = next(x for x in text.splitlines() if x.startswith("| 스프린터 | 005930 |"))
    assert "10주 @ 60,200원" in row and "10주 @ 60,100원" in row and "+0.17%" in row and "| 일치 |" in row
    assert "부분체결" in text and "미체결" in text
    assert "주문 오류(rejected)" in text and "가짜 rejected" in text
    assert "체결 (장부 미반영)" in text and "team.py 실행 뒤 reconcile" in text
    assert "005380" in text and "X999" in text and "손으로 낸 주문" in text
    assert "주문 5건" in text
    # 두 번 돌려도 같은 파일을 다시 쓸 뿐
    assert R.reconcile("kr", b, day, log=quiet) == path


def test_reconcile_체결조회_실패도_보고서에_남김(home):
    b = ScriptBroker()
    b.fill_errors = [KindError("mock_expired")]
    msgs = []
    path = R.reconcile("us", b, "2026-11-05", log=msgs.append)
    text = open(path, encoding="utf-8").read()
    assert "체결 조회 실패: mock_expired" in text
    assert any("모의투자 기간" in m for m in msgs)


# ---------------- 명령줄 ----------------

def test_cli_place_reconcile(home, monkeypatch, capsys):
    home("us", "스프린터", team_state(3_000, [buy("AAPL")]))
    b = ScriptBroker(script=["mock_expired"])
    monkeypatch.setattr(broker, "make_broker", lambda name: b)
    monkeypatch.setattr(R, "signal_close", lambda market, code, sd: 100.0)
    monkeypatch.setattr(R, "_now", lambda mk, now=None: datetime(2026, 11, 5, 9, 35, tzinfo=ZoneInfo("America/New_York")))
    assert R.cli(["place", "--market", "us", "--broker", "paper"]) == 2      # 중단 → 종료코드 2
    assert R.cli(["reconcile", "--market", "us", "--broker", "paper", "--date", "2026-11-05"]) == 0
    assert (R.REPORTS_DIR / "broker" / "us-2026-11-05.md").exists()
    with pytest.raises(SystemExit):
        R.cli(["reconcile", "--market", "us", "--date", "11/05"])
    with pytest.raises(SystemExit):
        R.cli(["place", "--market", "jp"])


def test_signal_close_는_신호일_행의_종가(monkeypatch):
    idx = pd.to_datetime(["2026-11-03", "2026-11-04", "2026-11-05"])
    df = pd.DataFrame({"Open": [1.0, 2.0, 3.0], "Close": [10.0, 20.0, 30.0]}, index=idx)
    monkeypatch.setattr(R.main, "load_prices", lambda code, start: df)
    assert R.signal_close("us", "AAPL", "2026-11-04") == 20.0
    assert R.signal_close("us", "AAPL", "2026-11-01") is None          # 그날 봉 없음
    def fail(code, start):
        raise SystemExit("라이브러리 없음")
    monkeypatch.setattr(R.main, "load_prices", fail)
    assert R.signal_close("us", "AAPL", "2026-11-04") is None          # 못 받으면 None → 보류
