"""
test_kis.py - broker/kis.py (KIS 클라이언트) 테스트
------------------------------------------------------------------
네트워크·증권사 키 없이 돈다. http 자리에 가짜 객체를 끼워 넣고,
시계(clock)·잠자기(sleep)도 가짜로 바꿔 시간을 마음대로 움직인다.

여기 나오는 키·계좌번호는 전부 지어낸 값이다.
"""

import json
import sys
import types
from dataclasses import dataclass
from typing import Optional

import pytest

# ── broker/base.py 가 아직 없을 때(K1 작업 중) 쓰는 최소 가짜 ──────────
try:
    import broker.base  # noqa: F401
except ImportError:
    _base = types.ModuleType("broker.base")

    class BrokerError(Exception):
        def __init__(self, kind, message=""):
            super().__init__(message)
            self.kind = kind

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
        broker_order_id: Optional[str]
        error_kind: Optional[str]
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

    for _n, _v in dict(BrokerError=BrokerError, Order=Order, OrderResult=OrderResult, Fill=Fill).items():
        setattr(_base, _n, _v)
    sys.modules["broker.base"] = _base

from broker.base import BrokerError, Order  # noqa: E402
from broker import kis  # noqa: E402
from broker.kis import KisBroker, KisConfigError, classify_error, mask_account  # noqa: E402

FAKE_ENV = {
    "KIS_APP_KEY": "FAKEAPPKEY0000000000",
    "KIS_APP_SECRET": "FAKESECRET9999999999",
    "KIS_ACCOUNT": "12345678-01",
}


# ── 가짜 HTTP ──────────────────────────────────────────────
class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeHttp:
    """경로별로 응답 목록을 차례로 돌려준다. 예외 객체를 넣으면 그걸 던진다."""

    def __init__(self, routes=None):
        self.routes = {k: list(v) for k, v in (routes or {}).items()}
        self.calls = []   # (method, path, headers, body_or_params)

    def _answer(self, method, url, headers, payload):
        path = url.split(":29443", 1)[-1].split(":9443", 1)[-1]
        self.calls.append((method, path, dict(headers or {}), payload))
        queue = self.routes.get(path)
        if not queue:
            raise AssertionError(f"예상 못 한 호출: {method} {path}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, headers=None, data=None, timeout=None):
        return self._answer("POST", url, headers, json.loads(data) if data else {})

    def get(self, url, headers=None, params=None, timeout=None):
        return self._answer("GET", url, headers, dict(params or {}))

    def count(self, path):
        return sum(1 for c in self.calls if c[1] == path)


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s

    slept: list


def token_resp(tok="tok-A", expires_in=86400):
    return Resp(200, {"access_token": tok, "token_type": "Bearer", "expires_in": expires_in,
                      "access_token_token_expired": "2026-11-05 09:00:00"})


def ok_order(odno="0000123456"):
    return Resp(200, {"rt_cd": "0", "msg_cd": "APBK0013", "msg1": "주문 전송 완료 되었습니다.",
                      "output": {"KRX_FWDG_ORD_ORGNO": "00950", "ODNO": odno, "ORD_TMD": "090101"}})


def make(tmp_path, routes, env=None, clock=None):
    clock = clock or Clock()
    clock.slept = []
    http = FakeHttp(routes)
    b = KisBroker(env=dict(env or FAKE_ENV), http=http,
                  token_path=str(tmp_path / "state" / "kis_token.json"), clock=clock)
    b._sleep = clock.sleep
    return b, http, clock


def kr_order(**kw):
    d = dict(market="kr", code="005930", side="buy", shares=3, limit_price=70100.0,
             trainer="sprinter", signal_date="2026-11-03")
    d.update(kw)
    return Order(**d)


def us_order(**kw):
    d = dict(market="us", code="AAPL", side="buy", shares=2, limit_price=201.234,
             trainer="marathoner", signal_date="2026-11-03")
    d.update(kw)
    return Order(**d)


# ═════════════════════════════════════════════════════════
# 계좌 가리기
# ═════════════════════════════════════════════════════════
def test_mask_account():
    assert mask_account("12345678-01") == "1234****-01"
    assert mask_account("1234567801") == "1234****-01"
    assert mask_account("") == "****"
    assert "5678" not in mask_account("12345678-01")


def test_account_never_in_logs_or_messages(tmp_path, caplog):
    caplog.set_level("DEBUG", logger="broker.kis")
    rej = Resp(200, {"rt_cd": "1", "msg_cd": "APBK0952",
                     "msg1": "계좌 12345678 주문가능금액을 초과 했습니다"})
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_ORDER: [ok_order(), rej]})
    r1 = b.place(kr_order())
    r2 = b.place(kr_order(code="000660"))
    text = caplog.text + r1.message + r2.message + repr(b.account_masked)
    assert "12345678" not in text
    assert FAKE_ENV["KIS_APP_KEY"] not in text and FAKE_ENV["KIS_APP_SECRET"] not in text
    assert "1234****" in r2.message
    assert b.account_masked == "1234****-01"


# ═════════════════════════════════════════════════════════
# 오류 분류
# ═════════════════════════════════════════════════════════
@pytest.mark.parametrize("status, body, kind", [
    (0, {}, "network"),
    (502, {}, "network"),
    (500, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."}, "rate_limit"),
    (429, {}, "rate_limit"),
    (500, {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}, "auth"),
    (401, {}, "auth"),
    (200, {"rt_cd": "1", "msg_cd": "40910000", "msg1": "모의투자 기간이 만료되었습니다"}, "mock_expired"),
    (500, {"rt_cd": "1", "msg_cd": "", "msg1": "[40910000] 모의투자 종료"}, "mock_expired"),
    (200, {"rt_cd": "1", "msg_cd": "APBK0952", "msg1": "주문가능금액을 초과 했습니다"}, "rejected"),
    (400, {"rt_cd": "1", "msg_cd": "OPSQ0002"}, "rejected"),
    (302, {}, "unknown"),
])
def test_classify_error(status, body, kind):
    assert classify_error(status, body) == kind


def test_classify_error_tolerates_bad_body():
    assert classify_error(0, None) == "network"


# ═════════════════════════════════════════════════════════
# 설정: 키 누락·실전 차단
# ═════════════════════════════════════════════════════════
def test_missing_keys_raise_without_echoing_values(tmp_path):
    env = dict(FAKE_ENV)
    del env["KIS_APP_SECRET"]
    with pytest.raises(KisConfigError) as e:
        KisBroker(env=env, http=FakeHttp(), token_path=str(tmp_path / "t.json"))
    assert "KIS_APP_SECRET" in str(e.value)
    assert FAKE_ENV["KIS_APP_KEY"] not in str(e.value)


def test_bad_account_format(tmp_path):
    with pytest.raises(KisConfigError):
        KisBroker(env={**FAKE_ENV, "KIS_ACCOUNT": "1234-5"}, http=FakeHttp(),
                  token_path=str(tmp_path / "t.json"))


def test_default_is_mock_server(tmp_path):
    b, _, _ = make(tmp_path, {})
    assert b.mode == "mock"
    assert b.base_url == kis.MOCK_URL == "https://openapivts.koreainvestment.com:29443"
    assert all(v.startswith(("V", "HHDFS")) for v in b.tr.values())


@pytest.mark.parametrize("extra", [
    {"KIS_MODE": "real"},
    {"KIS_MODE": "real", "KIS_I_UNDERSTAND_REAL": "no"},
    {"KIS_MODE": "REAL", "KIS_I_UNDERSTAND_REAL": ""},
    {"KIS_I_UNDERSTAND_REAL": "yes", "KIS_MODE": "prod"},
])
def test_real_server_blocked_without_both_flags(tmp_path, extra):
    with pytest.raises(KisConfigError):
        KisBroker(env={**FAKE_ENV, **extra}, http=FakeHttp(), token_path=str(tmp_path / "t.json"))


def test_flag_alone_stays_mock(tmp_path):
    b, _, _ = make(tmp_path, {}, env={**FAKE_ENV, "KIS_I_UNDERSTAND_REAL": "yes"})
    assert b.base_url == kis.MOCK_URL


def test_real_only_with_both_flags_no_network(tmp_path):
    # 서버에는 아무것도 보내지 않고 주소·tr_id 선택만 본다
    b, http, _ = make(tmp_path, {}, env={**FAKE_ENV, "KIS_MODE": "real", "KIS_I_UNDERSTAND_REAL": "yes"})
    assert b.base_url == kis.REAL_URL
    assert b.tr["kr_buy"] == "TTTC0012U"
    assert http.calls == []


def test_env_file_then_os_environ(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("# 주석\nKIS_APP_KEY='from-file'\nKIS_ACCOUNT=\nexport KIS_MODE=mock\n", encoding="utf-8")
    monkeypatch.setenv("KIS_APP_KEY", "from-environ")
    monkeypatch.setenv("KIS_ACCOUNT", "87654321-01")
    monkeypatch.delenv("KIS_APP_SECRET", raising=False)
    s = kis.read_settings(envf)
    assert s["KIS_APP_KEY"] == "from-file"        # .env 가 우선
    assert s["KIS_ACCOUNT"] == "87654321-01"      # .env 에 비어 있으면 환경변수
    assert s["KIS_MODE"] == "mock"
    assert "KIS_APP_SECRET" not in s


# ═════════════════════════════════════════════════════════
# 토큰 캐시·재발급 제한
# ═════════════════════════════════════════════════════════
def test_token_cached_in_file_and_reused_across_instances(tmp_path):
    routes = {kis.PATH_TOKEN: [token_resp("tok-A")], kis.PATH_KR_ORDER: [ok_order()]}
    b1, http1, clock = make(tmp_path, routes)
    assert b1.place(kr_order()).ok
    assert http1.count(kis.PATH_TOKEN) == 1

    saved = json.loads((tmp_path / "state" / "kis_token.json").read_text())
    assert saved["token"] == "tok-A"
    assert FAKE_ENV["KIS_APP_KEY"] not in json.dumps(saved)
    assert FAKE_ENV["KIS_APP_SECRET"] not in json.dumps(saved)

    # 새 프로세스(새 인스턴스)가 몇 시간 뒤에 와도 파일 토큰을 그대로 씀
    clock.t += 3 * 3600
    b2, http2, _ = make(tmp_path, routes, clock=clock)
    assert b2.place(kr_order(code="000660")).ok
    assert http2.count(kis.PATH_TOKEN) == 0
    assert http2.calls[0][2]["authorization"] == "Bearer tok-A"


def test_token_renewed_after_24h(tmp_path):
    routes = {kis.PATH_TOKEN: [token_resp("tok-A"), token_resp("tok-B")], kis.PATH_KR_ORDER: [ok_order()]}
    b, http, clock = make(tmp_path, routes)
    b.place(kr_order())
    clock.t += 24 * 3600 + 1
    b.place(kr_order(code="000660"))
    assert http.count(kis.PATH_TOKEN) == 2
    assert http.calls[-1][2]["authorization"] == "Bearer tok-B"


def test_token_reissue_at_most_once_per_minute(tmp_path):
    # 토큰 발급이 실패해도 시도 시각이 남아 1분 안에는 다시 요청하지 않는다
    routes = {kis.PATH_TOKEN: [Resp(403, {"error_code": "EGW00103", "error_description": "유효하지 않은 AppKey"}),
                               token_resp("tok-B")],
              kis.PATH_KR_ORDER: [ok_order()]}
    b, http, clock = make(tmp_path, routes)
    r1 = b.place(kr_order())
    assert not r1.ok and r1.error_kind == "auth"

    clock.t += 30
    r2 = b.place(kr_order())
    assert not r2.ok and r2.error_kind == "rate_limit"
    assert http.count(kis.PATH_TOKEN) == 1          # 30초 뒤에는 서버에 묻지도 않음

    # 다른 인스턴스(다른 프로세스)도 같은 파일을 보고 막힌다
    b2, http2, _ = make(tmp_path, routes, clock=clock)
    assert b2.place(kr_order()).error_kind == "rate_limit"
    assert http2.count(kis.PATH_TOKEN) == 0

    clock.t += 31
    r3 = b.place(kr_order())
    assert r3.ok
    assert http.count(kis.PATH_TOKEN) == 2


def test_token_of_other_key_is_ignored(tmp_path):
    routes = {kis.PATH_TOKEN: [token_resp("tok-A"), token_resp("tok-B")], kis.PATH_KR_ORDER: [ok_order()]}
    b1, _, clock = make(tmp_path, routes)
    b1.place(kr_order())
    clock.t += 120
    b2, http2, _ = make(tmp_path, routes, env={**FAKE_ENV, "KIS_APP_KEY": "OTHERKEY"}, clock=clock)
    b2.place(kr_order())
    assert http2.count(kis.PATH_TOKEN) == 1


# ═════════════════════════════════════════════════════════
# 호출 속도 제한
# ═════════════════════════════════════════════════════════
def test_rate_limit_two_calls_per_second(tmp_path):
    routes = {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_ORDER: [ok_order()]}
    b, http, clock = make(tmp_path, routes)
    times = []
    orig = http._answer

    def stamp(*a, **k):
        times.append(clock.t)
        return orig(*a, **k)
    http._answer = stamp
    for code in ("005930", "000660", "035420", "005380"):
        b.place(kr_order(code=code))
    gaps = [b_ - a_ for a_, b_ in zip(times, times[1:])]
    assert len(times) == 5            # 토큰 1 + 주문 4
    assert all(g >= kis.MIN_INTERVAL - 1e-9 for g in gaps)


# ═════════════════════════════════════════════════════════
# 주문 바디 필드
# ═════════════════════════════════════════════════════════
def test_kr_buy_order_body_and_headers(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_ORDER: [ok_order("0000777")]})
    r = b.place(kr_order())
    assert r.ok and r.broker_order_id == "0000777" and r.error_kind is None
    assert r.client_id == "kr-sprinter-005930-buy-2026-11-03"

    method, path, headers, body = http.calls[-1]
    assert (method, path) == ("POST", "/uapi/domestic-stock/v1/trading/order-cash")
    assert headers["tr_id"] == "VTTC0012U"
    assert headers["custtype"] == "P"
    assert headers["authorization"] == "Bearer tok-A"
    assert headers["appkey"] == FAKE_ENV["KIS_APP_KEY"]
    assert body == {"CANO": "12345678", "ACNT_PRDT_CD": "01", "PDNO": "005930",
                    "ORD_DVSN": "00", "ORD_QTY": "3", "ORD_UNPR": "70100",
                    "EXCG_ID_DVSN_CD": "KRX", "SLL_TYPE": "", "CNDT_PRIC": ""}
    assert all(isinstance(v, str) for v in body.values())   # KIS 는 문자열만 받음


def test_kr_sell_order_tr_id(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_ORDER: [ok_order()]})
    b.place(kr_order(side="sell"))
    _, _, headers, body = http.calls[-1]
    assert headers["tr_id"] == "VTTC0011U"
    assert body["SLL_TYPE"] == "01"


def test_us_order_body(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_US_ORDER: [ok_order("US1")]})
    r = b.place(us_order())
    assert r.ok and r.broker_order_id == "US1"
    method, path, headers, body = http.calls[-1]
    assert path == "/uapi/overseas-stock/v1/trading/order"
    assert headers["tr_id"] == "VTTT1002U"
    assert body == {"CANO": "12345678", "ACNT_PRDT_CD": "01", "OVRS_EXCG_CD": "NASD",
                    "PDNO": "AAPL", "ORD_QTY": "2", "OVRS_ORD_UNPR": "201.23",
                    "CTAC_TLNO": "", "MGCO_APTM_ODNO": "", "SLL_TYPE": "",
                    "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}


def test_us_sell_order_and_spy_exchange(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_US_ORDER: [ok_order()]})
    b.place(us_order(code="SPY", side="sell"))
    _, _, headers, body = http.calls[-1]
    assert headers["tr_id"] == "VTTT1001U"
    assert body["SLL_TYPE"] == "00"
    assert body["OVRS_EXCG_CD"] == "AMEX"


def test_us_exchange_table_covers_v1_universe():
    for code in ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "SPY"):
        assert kis.US_EXCHANGE[code] in ("NASD", "NYSE", "AMEX")


def test_us_unknown_symbol_looked_up(tmp_path):
    empty = Resp(200, {"rt_cd": "0", "output": {"rsym": "", "last": ""}})
    found = Resp(200, {"rt_cd": "0", "output": {"rsym": "DNYSKO", "last": "190.5"}})
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()],
                                 kis.PATH_US_PRICE: [empty, found],
                                 kis.PATH_US_ORDER: [ok_order()]})
    assert b.place(us_order(code="KO")).ok
    price_calls = [c for c in http.calls if c[1] == kis.PATH_US_PRICE]
    assert [c[3]["EXCD"] for c in price_calls] == ["NAS", "NYS"]
    assert http.calls[-1][3]["OVRS_EXCG_CD"] == "NYSE"
    # 한 번 찾으면 기억
    b.place(us_order(code="KO", signal_date="2026-11-04"))
    assert http.count(kis.PATH_US_PRICE) == 2


def test_bad_orders_never_sent(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()]})
    for o in (kr_order(shares=0), kr_order(limit_price=0), kr_order(side="hold"), kr_order(market="jp")):
        r = b.place(o)
        assert not r.ok and r.error_kind == "rejected"
    assert http.calls == []


# ═════════════════════════════════════════════════════════
# 주문은 재시도 안 함 / 예외 안 던짐
# ═════════════════════════════════════════════════════════
@pytest.mark.parametrize("answer, kind", [
    (ConnectionError("boom"), "network"),
    (TimeoutError("slow"), "network"),
    (Resp(500, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."}), "rate_limit"),
    (Resp(500, {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}), "auth"),
    (Resp(200, {"rt_cd": "1", "msg_cd": "40910000", "msg1": "모의투자 기간 만료"}), "mock_expired"),
    (Resp(200, {"rt_cd": "1", "msg_cd": "APBK0952", "msg1": "주문가능금액을 초과 했습니다"}), "rejected"),
    (Resp(502, {}), "network"),
])
def test_order_not_retried(tmp_path, answer, kind):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_ORDER: [answer]})
    r = b.place(kr_order())
    assert r.ok is False
    assert r.error_kind == kind
    assert r.broker_order_id is None
    assert http.count(kis.PATH_KR_ORDER) == 1     # 딱 한 번만 보냄


def test_order_network_error_says_check_fills(tmp_path):
    b, _, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_ORDER: [ConnectionError("x")]})
    r = b.place(kr_order())
    assert "체결 조회" in r.message


def test_mock_expired_is_loud(tmp_path, caplog):
    caplog.set_level("ERROR", logger="broker.kis")
    b, _, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()],
                              kis.PATH_KR_ORDER: [Resp(200, {"rt_cd": "1", "msg_cd": "40910000", "msg1": "만료"})]})
    b.place(kr_order())
    assert "모의투자 기간" in caplog.text


def test_token_network_failure_returns_result(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [ConnectionError("dns")]})
    r = b.place(kr_order())
    assert not r.ok and r.error_kind == "network"
    assert http.count(kis.PATH_KR_ORDER) == 0


# ═════════════════════════════════════════════════════════
# 조회는 최대 3번 재시도
# ═════════════════════════════════════════════════════════
def _kr_ccld_row(odno, code, side, qty, avg):
    return {"ord_dt": "20261104", "odno": odno, "pdno": code, "sll_buy_dvsn_cd": side,
            "ord_qty": str(qty), "tot_ccld_qty": str(qty), "avg_prvs": str(avg)}


def test_query_retries_then_succeeds(tmp_path):
    good = Resp(200, {"rt_cd": "0", "output1": [_kr_ccld_row("1", "005930", "02", 3, "70000")], "output2": {}})
    b, http, clock = make(tmp_path, {kis.PATH_TOKEN: [token_resp()],
                                     kis.PATH_KR_CCLD: [ConnectionError("x"),
                                                        Resp(500, {"rt_cd": "1", "msg_cd": "EGW00201"}),
                                                        good]})
    fills = b.fills("kr", "2026-11-04")
    assert http.count(kis.PATH_KR_CCLD) == 3
    assert len(fills) == 1


def test_query_gives_up_after_3_retries(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_BALANCE: [ConnectionError("x")]})
    with pytest.raises(BrokerError) as e:
        b.holdings("kr")
    assert e.value.kind == "network"
    assert http.count(kis.PATH_KR_BALANCE) == 1 + kis.QUERY_RETRIES == 4


def test_query_rejected_not_retried(tmp_path):
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()],
                                 kis.PATH_KR_BALANCE: [Resp(200, {"rt_cd": "1", "msg_cd": "OPSQ0001", "msg1": "x"})]})
    with pytest.raises(BrokerError) as e:
        b.holdings("kr")
    assert e.value.kind == "rejected"
    assert http.count(kis.PATH_KR_BALANCE) == 1


def test_query_mock_expired_raises(tmp_path):
    b, _, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()],
                              kis.PATH_KR_PSBL: [Resp(200, {"rt_cd": "1", "msg_cd": "40910000"})]})
    with pytest.raises(BrokerError) as e:
        b.buyable_shares("kr", "005930", 70000)
    assert e.value.kind == "mock_expired"


# ═════════════════════════════════════════════════════════
# 체결·잔고·매수가능 파싱
# ═════════════════════════════════════════════════════════
def test_kr_fills_parsing_and_paging(tmp_path):
    p1 = Resp(200, {"rt_cd": "0", "ctx_area_fk100": "FK", "ctx_area_nk100": "NK",
                    "output1": [_kr_ccld_row("11", "005930", "02", 3, "70050"),
                                {**_kr_ccld_row("12", "000660", "02", 0, "0")}]},   # 미체결은 뺌
              headers={"tr_cont": "M"})
    p2 = Resp(200, {"rt_cd": "0", "output1": [_kr_ccld_row("13", "035420", "01", 5, "180000")]},
              headers={"tr_cont": "D"})
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_CCLD: [p1, p2]})
    fills = b.fills("kr", "2026-11-04")
    assert [(f.broker_order_id, f.code, f.side, f.shares, f.price) for f in fills] == [
        ("11", "005930", "buy", 3, 70050.0), ("13", "035420", "sell", 5, 180000.0)]
    assert all(f.market == "kr" and f.date == "2026-11-04" for f in fills)
    c1, c2 = [c for c in http.calls if c[1] == kis.PATH_KR_CCLD]
    assert c1[2]["tr_id"] == "VTTC0081R"
    assert c1[3]["INQR_STRT_DT"] == c1[3]["INQR_END_DT"] == "20261104"
    assert c2[2]["tr_cont"] == "N" and c2[3]["CTX_AREA_NK100"] == "NK"


def test_us_fills_parsing(tmp_path):
    body = {"rt_cd": "0", "output": [
        {"odno": "77", "pdno": "aapl", "sll_buy_dvsn_cd": "02", "ft_ccld_qty": "2", "ft_ccld_unpr3": "201.10"},
        {"odno": "78", "pdno": "MSFT", "sll_buy_dvsn_cd": "01", "ft_ccld_qty": "0", "ft_ccld_unpr3": "0"},
    ]}
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_US_CCNL: [Resp(200, body)]})
    fills = b.fills("us", "2026-11-03")
    assert len(fills) == 1 and fills[0].code == "AAPL" and fills[0].price == 201.10 and fills[0].side == "buy"
    assert http.calls[-1][2]["tr_id"] == "VTTS3035R"


def test_holdings_kr_and_us(tmp_path):
    kr = Resp(200, {"rt_cd": "0", "output1": [{"pdno": "005930", "hldg_qty": "7"},
                                              {"pdno": "000660", "hldg_qty": "0"}], "output2": [{}]})
    nasd = Resp(200, {"rt_cd": "0", "output1": [{"ovrs_pdno": "AAPL", "ovrs_cblc_qty": "4"}]})
    none = Resp(200, {"rt_cd": "0", "output1": []})
    amex = Resp(200, {"rt_cd": "0", "output1": [{"ovrs_pdno": "SPY", "ovrs_cblc_qty": "1"}]})
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_BALANCE: [kr],
                                 kis.PATH_US_BALANCE: [nasd, none, amex]})
    assert b.holdings("kr") == {"005930": 7}
    assert b.holdings("us") == {"AAPL": 4, "SPY": 1}
    us_calls = [c for c in http.calls if c[1] == kis.PATH_US_BALANCE]
    assert [c[3]["OVRS_EXCG_CD"] for c in us_calls] == ["NASD", "NYSE", "AMEX"]
    assert us_calls[0][2]["tr_id"] == "VTTS3012R"


def test_buyable_shares(tmp_path):
    kr = Resp(200, {"rt_cd": "0", "output": {"nrcvb_buy_qty": "12", "max_buy_qty": "30"}})
    us = Resp(200, {"rt_cd": "0", "output": {"ord_psbl_qty": "5", "max_ord_psbl_qty": "9"}})
    b, http, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()], kis.PATH_KR_PSBL: [kr], kis.PATH_US_PSAMOUNT: [us]})
    assert b.buyable_shares("kr", "005930", 70100.4) == 12
    assert b.buyable_shares("us", "AAPL", 201.0) == 5
    kr_call = [c for c in http.calls if c[1] == kis.PATH_KR_PSBL][0]
    assert kr_call[2]["tr_id"] == "VTTC8908R" and kr_call[3]["ORD_UNPR"] == "70100"
    us_call = [c for c in http.calls if c[1] == kis.PATH_US_PSAMOUNT][0]
    assert us_call[2]["tr_id"] == "VTTS3007R" and us_call[3]["OVRS_EXCG_CD"] == "NASD"


def test_buyable_shares_unknown_returns_none(tmp_path):
    b, _, _ = make(tmp_path, {kis.PATH_TOKEN: [token_resp()],
                              kis.PATH_KR_PSBL: [Resp(200, {"rt_cd": "1", "msg_cd": "X", "msg1": "x"})],
                              kis.PATH_US_PSAMOUNT: [Resp(200, {"rt_cd": "0", "output": {}})]})
    assert b.buyable_shares("kr", "005930", 70000) is None
    assert b.buyable_shares("us", "AAPL", 200) is None
    assert b.buyable_shares("jp", "7203", 100) is None


def test_auth_error_on_query_drops_token_and_reissues(tmp_path):
    expired = Resp(500, {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."})
    good = Resp(200, {"rt_cd": "0", "output1": []})
    b, http, clock = make(tmp_path, {kis.PATH_TOKEN: [token_resp("tok-A"), token_resp("tok-B")],
                                     kis.PATH_KR_BALANCE: [expired, good]})
    clock.t += 0
    # 첫 토큰 발급 직후라 1분 제한에 걸림 → 재발급은 다음 실행에서
    with pytest.raises(BrokerError) as e:
        b.holdings("kr")
    assert e.value.kind == "rate_limit"
    clock.t += 61
    assert b.holdings("kr") == {}
    assert http.calls[-1][2]["authorization"] == "Bearer tok-B"
