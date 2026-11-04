# kr-broker 설계 — 한국 증권사(KIS) 모의투자 연결 + 국내 종목

- 작성: 2026-11-04 · 포크 `ParkSeong-Ho/claude-stock` · 기준 브랜치 **`kr-broker`** (`v1`에서 분기)
- 근거: 원래 저장소 `조사/증권사 API·모의투자·수수료 비교.html`, `국내 수수료 심화·학생 기회·필수 지식.html`, `한국 주식 오픈소스 프로젝트 비교.html` (기준일 2026-11-02~03)
- 결정: 사용자 선택 **(C) 둘 다** — ① v1의 미국 종목을 KIS 모의계좌로 실제 주문, ② 국내 종목(원화) 시장 추가

## 1. 목표 / 비목표 / 안티목표

**목표**
- 지금 가짜 지갑(`paper_wallet`)으로 하던 매매를 **한국투자증권(KIS) 모의투자 계좌에 실제 지정가 주문**으로도 낼 수 있다.
- 국내 종목(KOSPI 대형주)도 미국과 같은 흐름(확정 봉 → 신호 → 다음 거래일 시가 → 비교 줄)으로 돌린다. 지갑은 시장별로 따로(원화/달러), 섞지 않는다.
- 장부의 정답은 계속 `paper_wallet`. 증권사 모의계좌는 "주문이 정말 들어가고 체결되는가"를 검증하는 용도. 장부와 체결이 다르면 기록한다.

**비목표**: 실전 계좌 주문, 환전, 소수점 주문, 텔레그램 승인, 장중 매매, 서킷 브레이커 재개(D6).

**안티목표**
- 증권사 키·계좌번호가 저장소·로그·커밋·클라우드에 들어가는 것.
- 주문 재시도로 같은 주문이 두 번 나가는 것.
- 실전 서버로 주문이 나가는 경로가 기본값으로 열리는 것.
- KIS 공식 저장소(라이선스 표기 없음)·키움 공식 저장소(복제 금지)·AGPL 코드의 **복사**. 스펙 참조만.
- 원래 저장소(kjh3291)에 PR·이슈.

## 2. 결정

| ID | 결정 |
|---|---|
| K-D1 | 증권사는 **KIS 모의투자** 하나. 서버 `https://openapivts.koreainvestment.com:29443`. 실전 서버 URL은 코드에 넣되 `KIS_MODE=real` + 확인 플래그 둘 다 있어야만 쓰이고, 이번 범위에서는 테스트도 하지 않는다. |
| K-D2 | **두 단계 실행.** 장 마감 후 `team.py` 가 신호를 `pending` 에 저장(지금 그대로) → 다음 장 개장 직후 `order_runner.py place` 가 pending 을 지정가 주문으로 낸다 → 장 마감 후 `order_runner.py reconcile` 이 체결을 조회해 장부와 비교. |
| K-D3 | `team.py` 는 지금처럼 다음 봉 시가로 **장부 체결**을 계속한다. 브로커 체결은 별도 파일에 기록하고 차이만 보고한다(장부를 브로커 값으로 덮어쓰지 않음). |
| K-D4 | 주문 안전: **지정가만**, 주문은 **재시도 안 함**(조회만 재시도), 같은 `client_id` 주문은 하루 한 번(파일 기반 중복 방지), 모의 기간 만료 오류 `40910000` 은 따로 감지해 크게 알린다. |
| K-D5 | 지정가 = 신호 봉 종가 × (1 ± 0.5%) 를 호가단위로 맞춤(매수는 올림, 매도는 내림). 수량은 `shares_within_cap` 과 브로커 매수가능수량 중 작은 값. |
| K-D6 | 비밀값은 **프로젝트 폴더의 `.env` 에서만** 읽는다: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT`(8자리-2자리), `KIS_MODE`(기본 `mock`). 토큰 캐시는 `state/kis_token.json`(gitignore). 로그에는 계좌번호를 가린다(`1234****-01`). 클라우드 세션은 키 없이 가짜 HTTP 로만 테스트한다. |
| K-D7 | 국내 시장: 종목은 **고정 목록**(KOSPI 시가총액 상위 약 30개, 6자리 코드, 목록은 코드에 명시). 시세는 FinanceDataReader(네이버). 벤치마크 ~~KODEX 200(`069500`)~~ → **KOSPI 200 가격지수(`KS200`)** (2026-11-04 변경, 아래 메모). KRX 전체 목록 조회는 쓰지 않는다(멈춤 문제).<br>**변경 메모 (2026-11-04, S0-1):** 처음 결정은 "벤치마크 KODEX 200(`069500`)"이었다(취소선은 기록으로 남김). 그런데 FDR(네이버)의 069500 시세는 **분배금 반영** 값이고 국내 주식 시세는 **배당 미반영**이라 비교가 벤치마크 쪽으로 연 약 2%p 기운다(2015-01-02 네이버 19,639원 vs 실제 종가 24,725원 / 2015~2026 네이버 069500 +354.8% vs `KS200` +261.8%). 사용자 결정으로 둘 다 '가격만'인 `KS200`(`fdr.DataReader("KS200", start)`, OHLCV 있음)을 쓴다. 지수 기호는 6자리 코드가 아니므로 `main.load_benchmark` 경로에서만 받는다(`load_prices(..., allow_index=True)`). 화면 이름은 "KOSPI 200(가격지수)". **KS200 출처(2026-11-04 확인):** 네이버가 아니라 FDR 0.9.110 이상이 GitHub `FinanceData/fdr_krx_data_cache` 의 `data/index/year_ks200/<연도>.csv` 를 읽는다(0.9.90~0.9.102 는 data.krx.co.kr 직접 호출 — 지금은 로그인 없이 거절 → `requirements.txt` 하한 `>=0.9.110`). 이 캐시는 거래일 12~14시 KST 에 **미완성 오늘 봉**을 올리고 16:50~21:53 KST 에 종가를 고친다 → 벤치마크만 확정 시각 22:30 KST(K-D9). 자세히: `docs/kr-fix-s0.md` |
| K-D8 | 국내 비용: 수수료 `0.00015`(KIS 0.0140527% + 유관기관 0.0036396%, 반올림), 매도세 `0.0020`, 슬리피지 `0.0005`. 정수 주식만. |
| K-D9 | 국내 확정 봉(D1의 한국판): 마지막 봉 날짜가 한국시간 "오늘"이고 현재가 **16:00 KST 이전**이면 버린다. Close NaN 행은 버린다. **추가 (2026-11-04, S0-2):** `Volume == 0` 행(거래정지일)도 버린다. 시가가 없는 봉에서는 종가로 대신 체결하지 않고(`main.open_price` → None) 주문을 다음 거래된 봉 시가까지 남긴다. team 은 기준 봉에 봉이 없는 종목(정지 중)의 판단·보유일수를 쉬고, 그런 종목은 매수 후보에서 뺀다. **추가 (2026-11-04, 검토 I2):** 벤치마크 `KS200` 만 확정 시각 **22:30 KST**(`Market.bench_cutoff`) — team 기준 날짜는 22:30 전이면 하루 전 봉. 국내 실행 권장: 22:30 KST 이후 또는 다음날 09:00 전. 자세히: `docs/kr-fix-s0.md` |
| K-D10 | 국내 가상자금 **₩10,000,000**(설계자 판단: 100만원이면 대형주 1주도 못 사는 종목이 많아 전략이 왜곡됨). 배분비율·종목상한은 미국과 같은 값. |
| K-D11 | 시장 선택은 인자: `python team.py 40 --market kr` / `--market us`(기본 us). 상태 파일은 시장별: 미국 `state/team_<트레이너>.json`(지금 그대로), 국내 `state/kr/team_<트레이너>.json`. |

## 3. 인터페이스 (세션 간 약속 — 이름·시그니처 그대로)

### `markets.py` (K4 소유)
```python
@dataclass(frozen=True)
class Market:
    key: str            # "us" | "kr"
    currency: str       # "USD" | "KRW"
    fee_rate: float
    sell_tax_rate: float
    slippage: float
    benchmark: str      # "SPY" | "KS200"   (처음 약속은 "069500" — 2026-11-04 K-D7 변경)
    tz: str             # "America/New_York" | "Asia/Seoul"
    close_cutoff: str   # "16:15" | "16:00"  (현지시간, 이 전이면 오늘 봉 버림)
    total_cash: float   # 10_000 | 10_000_000
    bench_cutoff: str | None = None   # 2026-11-04 추가: 벤치마크만의 확정 시각. us None(=close_cutoff), kr "22:30"
MARKETS: dict[str, Market]          # {"us": ..., "kr": ...}
get_market(key: str) -> Market
round_to_tick(market_key: str, price: float, side: str) -> float
    # us: 0.01 단위. kr: 2023 개편 호가단위표(2,000원 미만 1원 / 5,000 미만 5원 / 20,000 미만 10원 /
    #     50,000 미만 50원 / 200,000 미만 100원 / 500,000 미만 500원 / 이상 1,000원).
    # side="buy" 는 올림, "sell" 은 내림.
money(market_key: str, v: float, sign=True) -> str   # "$1,234.56" / "1,234,567원"
KR_UNIVERSE: dict[str, str]          # {"삼성전자": "005930", ...}
```

### `broker/` (K1 소유: `__init__.py`, `base.py`, `paper.py`, `fake.py`)
```python
@dataclass
class Order:
    market: str          # "us" | "kr"
    code: str            # "AAPL" / "005930"
    side: str            # "buy" | "sell"
    shares: int
    limit_price: float
    trainer: str
    signal_date: str     # 'YYYY-MM-DD'
    @property
    def client_id(self) -> str: ...   # f"{market}-{trainer}-{code}-{side}-{signal_date}"

@dataclass
class OrderResult:
    client_id: str
    ok: bool
    broker_order_id: str | None
    error_kind: str | None   # BrokerError.kind 값 중 하나
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
    kind: str   # "network" | "auth" | "rate_limit" | "rejected" | "mock_expired" | "unknown"

class Broker(Protocol):
    name: str
    def place(self, order: Order) -> OrderResult          # 예외를 던지지 않고 OrderResult(ok=False)로. 재시도 금지
    def fills(self, market: str, date: str) -> list[Fill] # 그날 체결 내역. 조회는 재시도 가능
    def holdings(self, market: str) -> dict[str, int]     # 종목 → 보유 주식 수
    def buyable_shares(self, market: str, code: str, price: float) -> int | None   # 모르면 None

PaperBroker(path)   # 주문을 파일에 기록하고 지정가에 즉시 체결된 것으로 본다(오프라인 기본값)
FakeBroker(script)  # 테스트용: 미리 정한 응답·오류를 순서대로 돌려준다
make_broker(name: str) -> Broker   # "paper" | "fake" | "kis" (kis 는 broker.kis.KisBroker 를 늦게 import)
```

### `broker/kis.py` (K2 소유)
```python
KisBroker(env: dict | None = None, http=None, token_path="state/kis_token.json", clock=time.time)
    # env 없으면 프로젝트 폴더 .env → os.environ 순서. http 는 테스트용 주입(기본 requests.Session).
    # Broker 프로토콜 구현. 국내·해외(미국) 주문·체결·잔고·매수가능 조회.
mask_account(acct: str) -> str
classify_error(status: int, body: dict) -> str     # BrokerError.kind 값
```
- 토큰: `/oauth2/tokenP`, 24시간 유효, 재발급은 1분에 1번 이하 → 파일 캐시.
- 호출 속도 제한: 모의 서버 기준 **초당 2회 이하**로 기본 설정.
- tr_id(모의)·URL은 KIS 공식 문서/`koreainvestment/open-trading-api`를 **읽고** 확인해 상수로 둔다(코드 복사 금지). 조사 노트 기준 해외 모의 매수 `VTTT1002U`, 매도 `VTTT1001U`. 국내 모의 주문 tr_id는 확인해서 적는다. 확인 못 한 값은 주석에 `(미확인)`.
- 미국 주문 거래소 코드(NASD/NYSE/AMEX)는 종목별 표 + 모르면 조회 API.

### `order_runner.py` (K3 소유)
```python
build_orders(market_key: str, states: dict[str, dict], last_close: dict[str, float], caps: dict[str, float]) -> list[Order]
    # states: 트레이너명 → team 상태 dict(pending·wallet·positions·start_cash). 순수 함수.
place(market_key: str, broker: Broker, now=None) -> list[OrderResult]
reconcile(market_key: str, broker: Broker, date: str) -> str     # 보고서 경로
# CLI: python order_runner.py place|reconcile --market us|kr --broker paper|kis [--date YYYY-MM-DD]
```
- 중복 방지: `state/broker/<market>-orders.jsonl` 에 `client_id` 가 이미 있으면 내지 않는다.
- 매도 수량은 장부 보유 수량, 매수 수량은 K-D5.
- `reconcile` 보고서: `reports/broker/<market>-<date>.md` — 주문별 (장부 체결가·수량) vs (브로커 체결가·수량), 미체결, 오류 종류.

## 4. 작업 나누기 (파일 소유권)

| 세션 | 브랜치 | 소유 파일 (이 파일만 수정) |
|---|---|---|
| K1 브로커 뼈대 | `kr-k1-broker` | `broker/__init__.py`, `broker/base.py`, `broker/paper.py`, `broker/fake.py`, `tests/test_broker_base.py` |
| K2 KIS 클라이언트 | `kr-k2-kis` | `broker/kis.py`, `tests/test_kis.py`, `.env.example`, `.gitignore`, `docs/kis-setup.md` |
| K3 주문 실행기 | `kr-k3-runner` | `order_runner.py`, `tests/test_order_runner.py`, `docs/broker-run.md` |
| K4 국내 시장 | `kr-k4-market` | `markets.py`, `main.py`, `team.py`, `live.py`, `screener.py`, `paper_wallet.py`(통화·기본값만), `tests/test_market_kr.py`, `README.md` |

공통 규칙
- 소유 파일 밖은 수정 금지(읽기 자유). 다른 세션 것은 §3 시그니처대로 있다고 가정하고, 테스트에서 필요하면 그 자리에서 최소한의 가짜를 만든다.
- 테스트는 **네트워크 없이**. 증권사 키 없이.
- 한국어 주석·커밋, 초보자용 설명 말투 유지. `requirements.txt` 를 바꿔야 하면 바꾸지 말고 보고서(커밋 메시지)에 적는다(`requests` 는 이미 FinanceDataReader 의존성으로 설치됨).
- 끝나면 자기 브랜치에 푸시만. PR 은 사람이 `kr-broker` 로 만든다. 원래 저장소에는 아무것도 하지 않는다.
- 의존성: `~/.venv-cs` 가 없으면 `python -m venv ~/.venv-cs && ~/.venv-cs/bin/pip install -q finance-datareader ta backtesting pandas pytest requests`.

## 5. 완료 기준

1. `kr-broker` 에 K1~K4 를 합친 상태에서 `pytest` 전부 통과.
2. `python team.py 40 --market kr` 이 실제 시세로 종료코드 0, 출력에 `nan` 없음, 금액이 전부 `원`, ~~KODEX 200~~ KOSPI 200(가격지수) 비교 줄 (2026-11-04 K-D7 변경).
3. `python order_runner.py place --market us --broker paper` / `--market kr` 이 pending 을 주문으로 바꾸고, 두 번 실행해도 주문이 한 번만 기록됨.
4. (사용자 맥, 키 준비 후) `--broker kis` 로 모의계좌에 국내 1건·미국 1건 지정가 주문이 들어가고 `reconcile` 보고서가 나옴.

## 6. 사용자 준비물 (개발과 병행)
1. 한국투자증권 계좌 개설(비대면) + 해외주식 거래 신청
2. 상시 모의투자 신청 → 모의 계좌번호
3. KIS Developers 에서 Open API 신청 → **모의투자용** 앱 키·시크릿
4. 키는 채팅·클라우드에 넣지 말고 맥의 프로젝트 폴더 `.env` 에만
