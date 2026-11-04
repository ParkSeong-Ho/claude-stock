"""
broker/kis.py - 한국투자증권(KIS) Open API 클라이언트 (모의투자 기본)
------------------------------------------------------------------
설계 문서 docs/kr-broker-design.md §3 의 `KisBroker` 를 구현한다.
Broker 프로토콜(broker/base.py)의 네 가지 일을 한다.

    place(order)                      지정가 주문 1건 (재시도 안 함, 예외 대신 OrderResult)
    fills(market, date)               그날 체결 내역 (조회라서 재시도 가능)
    holdings(market)                  보유 주식 수
    buyable_shares(market, code, px)  매수 가능 수량 (모르면 None)

초보자용 요약
- 키(앱 키·시크릿·계좌번호)는 프로젝트 폴더의 `.env` 에서 읽는다. 없으면 환경변수.
  키는 저장소·로그 어디에도 남기지 않는다. 로그의 계좌번호는 `1234****-01` 처럼 가린다.
- 기본은 **모의투자 서버**. 실전 서버는 `KIS_MODE=real` 과 `KIS_I_UNDERSTAND_REAL=yes`
  두 개가 모두 있을 때만 쓴다(하나라도 없으면 만들 때 바로 멈춘다).
- 접속 토큰은 24시간 유효하고, 새로 받는 건 1분에 1번만 허용된다 → `state/kis_token.json` 에 저장해 재사용.
- 모의 서버는 호출 한도가 낮다 → 모든 호출 사이를 0.5초 이상 띄운다(초당 2회 이하).
- 주문은 **절대 재시도하지 않는다**(같은 주문이 두 번 나가는 사고 방지). 조회만 최대 3번 재시도.

스펙 출처: 한국투자증권 공식 저장소 koreainvestment/open-trading-api 를 **읽고** 확인한 값이다
(라이선스 표기가 없어 코드는 복사하지 않고 새로 썼다). 표와 출처 파일 경로는 docs/kis-setup.md.
확인 못 한 값은 주석에 (미확인) 이라고 적었다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

from broker.base import BrokerError, Fill, Order, OrderResult

log = logging.getLogger("broker.kis")

ROOT = Path(__file__).resolve().parent.parent   # 프로젝트 폴더 (.env 가 있는 곳)

# ── 서버 주소 ─────────────────────────────────────────────
MOCK_URL = "https://openapivts.koreainvestment.com:29443"   # 모의투자 (kis_devlp.yaml 의 vps)
REAL_URL = "https://openapi.koreainvestment.com:9443"       # 실전 (kis_devlp.yaml 의 prod) — 이중 확인 없이는 안 씀

# ── API 경로 ──────────────────────────────────────────────
PATH_TOKEN = "/oauth2/tokenP"
PATH_KR_ORDER = "/uapi/domestic-stock/v1/trading/order-cash"
PATH_KR_CCLD = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
PATH_KR_BALANCE = "/uapi/domestic-stock/v1/trading/inquire-balance"
PATH_KR_PSBL = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
PATH_US_ORDER = "/uapi/overseas-stock/v1/trading/order"
PATH_US_CCNL = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
PATH_US_BALANCE = "/uapi/overseas-stock/v1/trading/inquire-balance"
PATH_US_PSAMOUNT = "/uapi/overseas-stock/v1/trading/inquire-psamount"
PATH_US_PRICE = "/uapi/overseas-price/v1/quotations/price"

# ── 거래 ID(tr_id) ── 모의(mock) / 실전(real) ───────────────
TR_IDS = {
    "mock": {
        "kr_buy": "VTTC0012U",       # 국내 현금 매수
        "kr_sell": "VTTC0011U",      # 국내 현금 매도
        "kr_ccld": "VTTC0081R",      # 국내 일별 주문체결 (3개월 이내)
        "kr_balance": "VTTC8434R",   # 국내 잔고
        "kr_psbl": "VTTC8908R",      # 국내 매수가능
        "us_buy": "VTTT1002U",       # 미국 매수
        "us_sell": "VTTT1001U",      # 미국 매도 (문서·주석 기준. 공식 예제 코드는 'V'+TTTT1006U → VTTT1006U 로
                                     #  만들어 서로 다름 → 문서값 사용, 첫 모의 주문에서 확인 필요)
        "us_ccnl": "VTTS3035R",      # 미국 주문체결내역
        "us_balance": "VTTS3012R",   # 미국 잔고
        "us_psamount": "VTTS3007R",  # 미국 매수가능금액(수량)
        "us_price": "HHDFS00000300", # 미국 현재가 (모의·실전 공통) — 거래소 코드 조회용
    },
    "real": {
        "kr_buy": "TTTC0012U",
        "kr_sell": "TTTC0011U",
        "kr_ccld": "TTTC0081R",
        "kr_balance": "TTTC8434R",
        "kr_psbl": "TTTC8908R",
        "us_buy": "TTTT1002U",
        "us_sell": "TTTT1006U",
        "us_ccnl": "TTTS3035R",
        "us_balance": "TTTS3012R",
        "us_psamount": "TTTS3007R",
        "us_price": "HHDFS00000300",
    },
}

# ── 미국 거래소 코드 ──────────────────────────────────────
# 주문·잔고에 쓰는 코드(NASD/NYSE/AMEX) ↔ 시세 조회에 쓰는 코드(NAS/NYS/AMS)
US_EXCHANGE = {
    "AAPL": "NASD",
    "MSFT": "NASD",
    "NVDA": "NASD",
    "GOOGL": "NASD",
    "AMZN": "NASD",
    "SPY": "AMEX",   # NYSE Arca 상장. KIS 는 Arca 종목을 AMEX 로 분류하는 것으로 알려짐 (미확인)
}
US_ORDER_TO_QUOTE = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}

# ── 오류 코드 ──────────────────────────────────────────────
MOCK_EXPIRED_CODE = "40910000"          # 모의투자 기간 만료 (설계 K-D4. 공식 저장소에서는 못 찾음 → (미확인))
RATE_LIMIT_CODES = {
    "EGW00201",   # 초당 거래건수 초과 (공식 README 에서 확인)
    "EGW00133",   # 토큰 발급 1분 제한 (미확인)
}
AUTH_CODES = {
    "EGW00123",   # 기간이 만료된 token (공식 legacy 예제에서 확인)
    "EGW00121",   # 유효하지 않은 token (미확인)
    "EGW00102",   # 앱 키 오류 (미확인)
    "EGW00103",   # 앱 키 오류 (미확인)
    "EGW00105",   # 앱 시크릿 오류 (미확인)
}

# ── 동작 설정 ──────────────────────────────────────────────
MIN_INTERVAL = 0.5        # 호출 사이 최소 간격(초) → 초당 2회 이하
TOKEN_LIFETIME = 86400    # 토큰 유효 24시간
TOKEN_MARGIN = 300        # 만료 5분 전부터는 새 토큰
TOKEN_REISSUE_GAP = 60    # 토큰 재발급은 60초에 1번 이하
QUERY_RETRIES = 3         # 조회: 처음 1번 + 재시도 최대 3번
MAX_PAGES = 10            # 연속조회 최대 쪽수
HTTP_TIMEOUT = 10         # 초


class KisConfigError(ValueError):
    """.env 설정이 빠졌거나 잘못됨(키 누락, 실전 확인 플래그 없음 등). 값 자체는 메시지에 넣지 않는다."""


# ═════════════════════════════════════════════════════════
# 작은 도우미 (테스트에서 직접 부름)
# ═════════════════════════════════════════════════════════
def mask_account(acct: str) -> str:
    """계좌번호를 로그용으로 가린다. '12345678-01' → '1234****-01'."""
    digits = re.sub(r"\D", "", str(acct or ""))
    if len(digits) >= 10:
        return f"{digits[:4]}****-{digits[8:10]}"
    if len(digits) >= 8:
        return f"{digits[:4]}****"
    return "****"


def classify_error(status: int, body: dict) -> str:
    """HTTP 상태코드와 응답 본문을 BrokerError.kind 값 하나로 바꾼다.

    network      연결 실패·시간 초과·서버 5xx (status 0 은 '응답 자체가 없음')
    auth         토큰·앱 키 문제 (401/403, EGW00123 등)
    rate_limit   호출 한도 초과 (429, EGW00201)
    rejected     증권사가 주문/조회를 거절 (잔고 부족, 가격 오류 등 rt_cd != '0')
    mock_expired 모의투자 기간 만료 (메시지 코드 40910000) → 사용자가 모의투자를 다시 신청해야 함
    unknown      그 밖
    """
    body = body if isinstance(body, dict) else {}
    code = str(body.get("msg_cd") or body.get("error_code") or "").strip()
    text = " ".join(str(body.get(k) or "") for k in ("msg1", "error_description", "message"))

    if code == MOCK_EXPIRED_CODE or MOCK_EXPIRED_CODE in text:
        return "mock_expired"
    if code in RATE_LIMIT_CODES or status == 429 or "초당" in text:
        return "rate_limit"
    if code in AUTH_CODES or status in (401, 403) or "token" in text.lower() or "토큰" in text:
        return "auth"
    if not status:
        return "network"
    if status >= 500:
        return "network"
    if status == 200:
        rt_cd = str(body.get("rt_cd", "")).strip()
        return "rejected" if rt_cd not in ("", "0") else "unknown"
    if 400 <= status < 500:
        return "rejected"
    return "unknown"


def _make_error(kind: str, message: str) -> BrokerError:
    """BrokerError 를 만든다. base.py 의 생성자 모양을 몰라도 되도록 kind 를 직접 붙인다."""
    try:
        err = BrokerError(kind, message)
    except TypeError:
        err = BrokerError(message)
    try:
        err.kind = kind
    except Exception:  # pragma: no cover - frozen 등
        pass
    return err


def _kind_of(err: BaseException) -> str:
    return getattr(err, "kind", None) or "unknown"


def load_env_file(path: Path) -> dict:
    """아주 단순한 .env 읽기: KEY=VALUE, # 주석, 앞뒤 따옴표 제거. 없으면 빈 dict."""
    out = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        out[key.strip()] = val
    return out


ENV_KEYS = ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT", "KIS_MODE", "KIS_I_UNDERSTAND_REAL")


def read_settings(env_path: Path | None = None) -> dict:
    """.env(프로젝트 폴더) → os.environ 순서로 KIS_* 값을 모은다. .env 값이 우선."""
    file_vals = load_env_file(env_path or ROOT / ".env")
    out = {}
    for k in ENV_KEYS:
        v = file_vals.get(k)
        if not v:
            v = os.environ.get(k, "")
        if v:
            out[k] = v
    return out


def _yyyymmdd(date: str) -> str:
    return str(date).replace("-", "")[:8]


def _to_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _to_float(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


# ═════════════════════════════════════════════════════════
# KisBroker
# ═════════════════════════════════════════════════════════
class KisBroker:
    """한국투자증권 Open API 로 Broker 프로토콜을 구현한다 (기본 모의투자)."""

    name = "kis"

    def __init__(self, env: dict | None = None, http=None,
                 token_path="state/kis_token.json", clock=time.time):
        cfg = dict(env) if env is not None else read_settings()

        self._app_key = str(cfg.get("KIS_APP_KEY") or "").strip()
        self._app_secret = str(cfg.get("KIS_APP_SECRET") or "").strip()
        acct = str(cfg.get("KIS_ACCOUNT") or "").strip()
        missing = [k for k, v in (("KIS_APP_KEY", self._app_key),
                                  ("KIS_APP_SECRET", self._app_secret),
                                  ("KIS_ACCOUNT", acct)) if not v]
        if missing:
            raise KisConfigError(
                f"KIS 설정이 없습니다: {', '.join(missing)}. 프로젝트 폴더 .env 에 적어 주세요 "
                "(docs/kis-setup.md 참고)."
            )
        m = re.fullmatch(r"(\d{8})-?(\d{2})", acct)
        if not m:
            raise KisConfigError("KIS_ACCOUNT 형식은 '8자리-2자리' 입니다 (예: 12345678-01).")
        self._cano, self._prdt = m.group(1), m.group(2)
        self.account_masked = mask_account(acct)

        # 실전 서버는 이중 확인이 있을 때만
        mode = str(cfg.get("KIS_MODE") or "mock").strip().lower()
        if mode not in ("mock", "real"):
            raise KisConfigError("KIS_MODE 는 mock 또는 real 만 됩니다 (기본 mock).")
        if mode == "real" and str(cfg.get("KIS_I_UNDERSTAND_REAL") or "").strip().lower() != "yes":
            raise KisConfigError(
                "실전 서버는 막혀 있습니다. 정말 실전 계좌로 주문하려면 KIS_MODE=real 과 "
                "KIS_I_UNDERSTAND_REAL=yes 를 둘 다 적어야 합니다. 이 프로젝트 범위는 모의투자입니다."
            )
        self.mode = mode
        self.base_url = REAL_URL if mode == "real" else MOCK_URL
        self.tr = TR_IDS[mode]

        if http is None:
            import requests  # 늦게 import: 테스트는 requests 없이도 돈다
            http = requests.Session()
        self._http = http

        tp = Path(token_path)
        self._token_path = tp if tp.is_absolute() else ROOT / tp
        self._clock = clock
        self._sleep = time.sleep     # 테스트에서 바꿔 끼움
        self._last_call = None       # 마지막 HTTP 호출 시각 (속도 제한용)
        self._token = None           # {"token", "issued_at", "expires_at"}
        self._key_id = hashlib.sha256(self._app_key.encode()).hexdigest()[:12]   # 키 자체가 아님
        self._us_exchange = dict(US_EXCHANGE)

        if mode == "real":
            log.warning("KIS 실전 서버 사용 중 (계좌 %s)", self.account_masked)

    # ── 로그·메시지 가리기 ───────────────────────────────
    def _scrub(self, text) -> str:
        s = str(text)
        for secret in (self._app_key, self._app_secret):
            if secret:
                s = s.replace(secret, "***")
        if self._cano:
            s = s.replace(self._cano, mask_account(self._cano + self._prdt).split("-")[0])
        tok = (self._token or {}).get("token")
        if tok:
            s = s.replace(tok, "***")
        return s

    # ── 속도 제한 ─────────────────────────────────────────
    def _throttle(self):
        now = self._clock()
        if self._last_call is not None:
            wait = MIN_INTERVAL - (now - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    # ── HTTP 한 번 (재시도 없음) ─────────────────────────
    def _send(self, method: str, path: str, headers: dict, body=None, params=None):
        """(status, body_dict, resp_headers) 를 돌려준다. 연결 실패는 BrokerError(network)."""
        self._throttle()
        url = self.base_url + path
        try:
            if method == "POST":
                resp = self._http.post(url, headers=headers, data=json.dumps(body or {}),
                                       timeout=HTTP_TIMEOUT)
            else:
                resp = self._http.get(url, headers=headers, params=params or {},
                                      timeout=HTTP_TIMEOUT)
        except Exception as e:  # 연결 실패·시간 초과 등
            raise _make_error("network", f"KIS 연결 실패: {type(e).__name__}: {self._scrub(e)}")
        status = int(getattr(resp, "status_code", 0) or 0)
        try:
            data = resp.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        rh = getattr(resp, "headers", None) or {}
        return status, data, rh

    # ── 토큰 ─────────────────────────────────────────────
    def _read_token_file(self) -> dict:
        try:
            data = json.loads(self._token_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if data.get("mode") != self.mode or data.get("key_id") != self._key_id:
            return {}   # 다른 키·다른 서버의 토큰이면 무시
        return data

    def _write_token_file(self, data: dict):
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._token_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:  # pragma: no cover
            pass
        tmp.replace(self._token_path)

    def _token_ok(self, t: dict | None) -> bool:
        return bool(t and t.get("token") and self._clock() < float(t.get("expires_at", 0)) - TOKEN_MARGIN)

    def _get_token(self) -> str:
        if self._token_ok(self._token):
            return self._token["token"]
        saved = self._read_token_file()
        if self._token_ok(saved):
            self._token = saved
            return saved["token"]

        # 새로 받아야 함 — 1분에 1번만
        now = self._clock()
        last = float(saved.get("last_issue_at", 0) or 0)
        if last and now - last < TOKEN_REISSUE_GAP:
            raise _make_error(
                "rate_limit",
                f"KIS 토큰 재발급은 1분에 1번만 됩니다. {int(TOKEN_REISSUE_GAP - (now - last)) + 1}초 뒤 다시 실행하세요.",
            )
        # 시도 시각을 먼저 기록(실패해도 1분 제한은 지킨다)
        self._write_token_file({"mode": self.mode, "key_id": self._key_id, "last_issue_at": now})

        status, data, _ = self._send(
            "POST", PATH_TOKEN,
            headers={"content-type": "application/json; charset=utf-8"},
            body={"grant_type": "client_credentials",
                  "appkey": self._app_key, "appsecret": self._app_secret},
        )
        token = data.get("access_token")
        if status != 200 or not token:
            kind = classify_error(status, data)
            if kind in ("unknown", "rejected"):
                kind = "auth"
            raise _make_error(kind, f"KIS 토큰 발급 실패 (HTTP {status}, {self._scrub(data.get('error_description') or data.get('msg1') or '')})")
        life = _to_int(data.get("expires_in")) or TOKEN_LIFETIME
        life = min(life, TOKEN_LIFETIME)
        info = {"mode": self.mode, "key_id": self._key_id, "token": token,
                "issued_at": now, "expires_at": now + life, "last_issue_at": now}
        self._write_token_file(info)
        self._token = info
        log.info("KIS 토큰 새로 받음 (%s 서버, 계좌 %s)", self.mode, self.account_masked)
        return token

    def _drop_token(self):
        """토큰이 서버에서 거절되면 기억에서 지운다(파일의 last_issue_at 은 남겨 1분 제한 유지)."""
        self._token = None
        saved = self._read_token_file()
        if saved.get("token"):
            saved.pop("token", None)
            saved["expires_at"] = 0
            self._write_token_file(saved)

    def _headers(self, tr_id: str, tr_cont: str = "") -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
            "custtype": "P",       # 개인
            "tr_cont": tr_cont,
        }

    # ── 조회 한 번 + 재시도 ──────────────────────────────
    def _query(self, path: str, tr_id: str, params: dict, tr_cont: str = ""):
        """GET 조회. network/rate_limit/auth 는 재시도(최대 QUERY_RETRIES 번). (body, resp_headers) 반환."""
        last_err = None
        for attempt in range(QUERY_RETRIES + 1):
            if attempt:
                self._sleep(1.0 * attempt)
            headers = self._headers(tr_id, tr_cont)   # 토큰 문제(1분 제한 등)는 그대로 위로
            try:
                status, data, rh = self._send("GET", path, headers, params=params)
            except BrokerError as e:   # 연결 실패 → 다시
                last_err = e
                continue
            if status == 200 and str(data.get("rt_cd", "0")) == "0":
                return data, rh
            kind = classify_error(status, data)
            msg = f"KIS 조회 실패 [{tr_id}] HTTP {status} {data.get('msg_cd', '')} {self._scrub(data.get('msg1', ''))}".strip()
            last_err = _make_error(kind, msg)
            log.warning("%s (시도 %d)", msg, attempt + 1)
            if kind == "auth":
                self._drop_token()
                continue
            if kind in ("network", "rate_limit"):
                continue
            raise last_err   # rejected / mock_expired / unknown 은 다시 해도 같다
        raise last_err

    def _query_pages(self, path, tr_id, params, fk_key, nk_key, out_key="output1"):
        """연속조회(tr_cont M/F)를 따라가며 out_key 행을 모은다."""
        rows, tr_cont, params = [], "", dict(params)
        for _ in range(MAX_PAGES):
            data, rh = self._query(path, tr_id, params, tr_cont)
            part = data.get(out_key) or []
            if isinstance(part, dict):
                part = [part]
            rows.extend(part)
            nxt = str((rh.get("tr_cont") if hasattr(rh, "get") else "") or "").strip()
            if nxt not in ("M", "F"):
                break
            params[fk_key] = data.get(fk_key.lower(), "")
            params[nk_key] = data.get(nk_key.lower(), "")
            tr_cont = "N"
        return rows

    # ── 미국 거래소 코드 ─────────────────────────────────
    def us_exchange(self, code: str) -> str:
        """미국 종목의 주문용 거래소 코드(NASD/NYSE/AMEX). 표에 없으면 현재가 조회로 찾는다."""
        code = code.upper()
        if code in self._us_exchange:
            return self._us_exchange[code]
        for excg, qcode in US_ORDER_TO_QUOTE.items():
            try:
                data, _ = self._query(PATH_US_PRICE, self.tr["us_price"],
                                      {"AUTH": "", "EXCD": qcode, "SYMB": code})
            except BrokerError as e:
                if _kind_of(e) == "mock_expired":
                    raise
                continue
            out = data.get("output") or {}
            if _to_float(out.get("last")) > 0:
                self._us_exchange[code] = excg
                log.info("미국 거래소 코드 조회: %s → %s", code, excg)
                return excg
        raise _make_error("rejected", f"{code} 의 미국 거래소(NASD/NYSE/AMEX)를 찾지 못했습니다.")

    # ── 주문 (재시도 금지) ───────────────────────────────
    def _order_request(self, order: Order):
        side = order.side
        if order.market == "kr":
            tr_id = self.tr["kr_buy" if side == "buy" else "kr_sell"]
            path = PATH_KR_ORDER
            body = {
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._prdt,
                "PDNO": order.code,
                "ORD_DVSN": "00",                      # 00 = 지정가
                "ORD_QTY": str(int(order.shares)),
                "ORD_UNPR": str(int(round(order.limit_price))),   # 원 단위 정수 (호가단위는 호출자가 맞춤)
                "EXCG_ID_DVSN_CD": "KRX",              # 모의에서 필수인지 (미확인)
                "SLL_TYPE": "01" if side == "sell" else "",   # 01 = 일반매도
                "CNDT_PRIC": "",
            }
        else:
            tr_id = self.tr["us_buy" if side == "buy" else "us_sell"]
            path = PATH_US_ORDER
            body = {
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._prdt,
                "OVRS_EXCG_CD": self.us_exchange(order.code),
                "PDNO": order.code.upper(),
                "ORD_QTY": str(int(order.shares)),
                "OVRS_ORD_UNPR": f"{float(order.limit_price):.2f}",
                "CTAC_TLNO": "",
                "MGCO_APTM_ODNO": "",
                "SLL_TYPE": "00" if side == "sell" else "",
                "ORD_SVR_DVSN_CD": "0",
                "ORD_DVSN": "00",                      # 모의는 00(지정가)만 가능
            }
        return path, tr_id, body

    def place(self, order: Order) -> OrderResult:
        """지정가 주문 1건. 예외를 던지지 않고 OrderResult 로 돌려준다. **재시도하지 않는다.**"""
        cid = order.client_id

        def fail(kind, msg):
            msg = self._scrub(msg)
            if kind == "mock_expired":
                log.error("!!! KIS 모의투자 기간이 끝났습니다. KIS 홈페이지에서 모의투자를 다시 신청하세요. (%s)", cid)
            else:
                log.warning("주문 실패 %s [%s] %s", cid, kind, msg)
            return OrderResult(client_id=cid, ok=False, broker_order_id=None,
                               error_kind=kind, message=msg)

        # 보내기 전 검사 (증권사에 가지도 않음)
        if order.market not in ("kr", "us"):
            return fail("rejected", f"모르는 시장: {order.market}")
        if order.side not in ("buy", "sell"):
            return fail("rejected", f"모르는 매매 방향: {order.side}")
        if int(order.shares) <= 0 or int(order.shares) != order.shares:
            return fail("rejected", f"주문 수량은 1 이상 정수여야 합니다: {order.shares}")
        if not (float(order.limit_price) > 0):
            return fail("rejected", f"지정가는 0보다 커야 합니다: {order.limit_price}")

        try:
            path, tr_id, body = self._order_request(order)
            headers = self._headers(tr_id)
        except BrokerError as e:      # 토큰·거래소 조회 실패 — 주문은 아직 안 나감
            return fail(_kind_of(e), str(e))
        except Exception as e:  # pragma: no cover - 방어
            return fail("unknown", f"{type(e).__name__}: {e}")

        try:
            status, data, _ = self._send("POST", path, headers, body=body)
        except BrokerError as e:
            # 연결이 끊기면 증권사가 받았는지 모른다 → 재시도하지 말고 체결 조회로 확인
            return fail(_kind_of(e), f"{e} — 주문이 들어갔는지 알 수 없습니다. 재시도하지 말고 체결 조회로 확인하세요.")

        if status == 200 and str(data.get("rt_cd", "")) == "0":
            out = data.get("output") or {}
            odno = str(out.get("ODNO") or out.get("odno") or "") or None
            log.info("주문 접수 %s → 주문번호 %s (계좌 %s)", cid, odno, self.account_masked)
            return OrderResult(client_id=cid, ok=True, broker_order_id=odno, error_kind=None,
                               message=self._scrub(data.get("msg1", "")).strip() or "주문 접수")
        kind = classify_error(status, data)
        if kind == "auth":
            self._drop_token()
        return fail(kind, f"HTTP {status} {data.get('msg_cd', '')} {data.get('msg1', '')}".strip())

    # ── 체결 ─────────────────────────────────────────────
    def fills(self, market: str, date: str) -> list[Fill]:
        d = _yyyymmdd(date)
        out: list[Fill] = []
        if market == "kr":
            rows = self._query_pages(PATH_KR_CCLD, self.tr["kr_ccld"], {
                "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
                "INQR_STRT_DT": d, "INQR_END_DT": d,
                "SLL_BUY_DVSN_CD": "00",   # 전체
                "INQR_DVSN": "00",         # 역순
                "PDNO": "",
                "CCLD_DVSN": "01",         # 체결만
                "ORD_GNO_BRNO": "", "ODNO": "",
                "INQR_DVSN_3": "00", "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
                "EXCG_ID_DVSN_CD": "KRX",
            }, "CTX_AREA_FK100", "CTX_AREA_NK100")
            for r in rows:
                qty = _to_int(r.get("tot_ccld_qty"))
                if qty <= 0:
                    continue
                out.append(Fill(broker_order_id=str(r.get("odno", "")), market="kr",
                                code=str(r.get("pdno", "")),
                                side="sell" if str(r.get("sll_buy_dvsn_cd")) == "01" else "buy",
                                shares=qty, price=_to_float(r.get("avg_prvs")), date=date))
        elif market == "us":
            rows = self._query_pages(PATH_US_CCNL, self.tr["us_ccnl"], {
                "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
                "PDNO": "",                 # 모의는 전체("")만
                "ORD_STRT_DT": d, "ORD_END_DT": d,   # 현지(미국) 날짜
                "SLL_BUY_DVSN": "00", "CCLD_NCCS_DVSN": "00", "OVRS_EXCG_CD": "",
                "SORT_SQN": "DS", "ORD_DT": "", "ORD_GNO_BRNO": "", "ODNO": "",
                "CTX_AREA_NK200": "", "CTX_AREA_FK200": "",
            }, "CTX_AREA_FK200", "CTX_AREA_NK200", out_key="output")
            for r in rows:
                qty = _to_int(r.get("ft_ccld_qty"))
                if qty <= 0:
                    continue
                out.append(Fill(broker_order_id=str(r.get("odno", "")), market="us",
                                code=str(r.get("pdno", "")).upper(),
                                side="sell" if str(r.get("sll_buy_dvsn_cd")) == "01" else "buy",
                                shares=qty, price=_to_float(r.get("ft_ccld_unpr3")), date=date))
        else:
            raise _make_error("rejected", f"모르는 시장: {market}")
        return out

    # ── 잔고 ─────────────────────────────────────────────
    def holdings(self, market: str) -> dict[str, int]:
        held: dict[str, int] = {}
        if market == "kr":
            rows = self._query_pages(PATH_KR_BALANCE, self.tr["kr_balance"], {
                "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
                "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            }, "CTX_AREA_FK100", "CTX_AREA_NK100")
            for r in rows:
                q = _to_int(r.get("hldg_qty"))
                if q > 0:
                    held[str(r.get("pdno", ""))] = held.get(str(r.get("pdno", "")), 0) + q
        elif market == "us":
            for excg in ("NASD", "NYSE", "AMEX"):   # 모의는 거래소별로 따로 물어야 함
                rows = self._query_pages(PATH_US_BALANCE, self.tr["us_balance"], {
                    "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
                    "OVRS_EXCG_CD": excg, "TR_CRCY_CD": "USD",
                    "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
                }, "CTX_AREA_FK200", "CTX_AREA_NK200")
                for r in rows:
                    q = _to_int(r.get("ovrs_cblc_qty"))
                    code = str(r.get("ovrs_pdno", "")).upper()
                    if q > 0 and code:
                        held[code] = held.get(code, 0) + q
        else:
            raise _make_error("rejected", f"모르는 시장: {market}")
        return held

    # ── 매수 가능 수량 ───────────────────────────────────
    def buyable_shares(self, market: str, code: str, price: float) -> int | None:
        """매수 가능 수량. 조회에 실패하면 None (단, 모의 기간 만료는 크게 알리려고 예외)."""
        try:
            if market == "kr":
                data, _ = self._query(PATH_KR_PSBL, self.tr["kr_psbl"], {
                    "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
                    "PDNO": code, "ORD_UNPR": str(int(round(price))),
                    "ORD_DVSN": "01",       # 공식 설명: 증거금율 반영 수량은 01(시장가)로 조회
                    "CMA_EVLU_AMT_ICLD_YN": "N", "OVRS_ICLD_YN": "N",
                })
                out = data.get("output") or {}
                v = out.get("nrcvb_buy_qty")      # 미수 없는 매수 수량
            elif market == "us":
                data, _ = self._query(PATH_US_PSAMOUNT, self.tr["us_psamount"], {
                    "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
                    "OVRS_EXCG_CD": self.us_exchange(code),
                    "OVRS_ORD_UNPR": f"{float(price):.2f}", "ITEM_CD": code.upper(),
                })
                out = data.get("output") or {}
                v = out.get("ord_psbl_qty")       # 외화(달러) 기준 주문가능수량 — 환전은 범위 밖
            else:
                return None
        except BrokerError as e:
            if _kind_of(e) == "mock_expired":
                log.error("!!! KIS 모의투자 기간이 끝났습니다. 모의투자를 다시 신청하세요.")
                raise
            log.warning("매수가능 조회 실패 %s %s: %s", market, code, self._scrub(e))
            return None
        if v is None or str(v).strip() == "":
            return None
        return max(0, _to_int(v))
