# KIS(한국투자증권) 모의투자 연결 안내

이 문서는 두 부분입니다.

- **A. 사용자가 할 일** — 계좌 만들기부터 첫 실행까지 (처음 하는 사람용)
- **B. API 스펙 표** — `broker/kis.py` 가 쓰는 주소·tr_id·필드와 그 출처 (개발자용)

> ⚠️ 앱 키·앱 시크릿·계좌번호는 **내 컴퓨터의 프로젝트 폴더 `.env` 파일에만** 적습니다.
> 채팅, 클라우드 세션, 깃 커밋, 스크린샷에 넣지 마세요. `.env` 는 `.gitignore` 에 들어 있어 커밋되지 않습니다.

---

## A. 사용자가 할 일

### 1단계 — 한국투자증권 계좌 만들기

1. 휴대폰에 **한국투자증권 앱**을 설치하고 **비대면 계좌 개설**을 합니다(신분증 필요).
   종합계좌(위탁)로 만들면 됩니다.
2. 미국 주식도 주문하려면 앱에서 **해외주식 거래 신청**을 합니다.

### 2단계 — 모의투자 신청

1. 한국투자증권 홈페이지 또는 앱에서 **상시 모의투자**를 신청합니다.
2. 신청하면 **모의투자 계좌번호**(`8자리-2자리`, 예: `5xxxxxxx-01`)가 생깁니다. 실제 계좌번호와 다릅니다.
3. 모의투자는 **기간이 정해져 있습니다.** 기간이 끝나면 주문이 `40910000` 오류로 거절되고,
   프로그램이 `!!! KIS 모의투자 기간이 끝났습니다` 라고 크게 알립니다. 그때 다시 신청하세요.

### 3단계 — Open API 앱 키 받기

1. [KIS Developers](https://apiportal.koreainvestment.com) 에 로그인 → **API 신청**.
2. **모의투자용** 앱을 신청합니다(실전용과 따로 발급됨). 계좌는 2단계의 모의 계좌를 고릅니다.
3. 발급된 **App Key**, **App Secret** 을 확인합니다. (다른 사람에게 보여주지 마세요.)

### 4단계 — `.env` 파일 만들기 (내 맥에서)

터미널에서 프로젝트 폴더로 이동한 뒤 예시 파일을 복사합니다.

```bash
cp .env.example .env
```

`.env` 를 텍스트 편집기로 열어 빈칸을 채웁니다.

```
KIS_APP_KEY=발급받은_모의투자_앱키
KIS_APP_SECRET=발급받은_모의투자_시크릿
KIS_ACCOUNT=모의계좌_8자리-01
KIS_MODE=mock
KIS_I_UNDERSTAND_REAL=
```

- `KIS_MODE` 는 `mock` 그대로 둡니다. 실전 서버는 `KIS_MODE=real` 과 `KIS_I_UNDERSTAND_REAL=yes`
  **둘 다** 있어야만 열리고, 이 프로젝트 범위는 모의투자뿐입니다.
- 커밋에 안 들어가는지 확인:

```bash
git check-ignore -v .env
```

  `.gitignore:… .env` 처럼 한 줄이 나오면 안전합니다(아무것도 안 나오면 멈추고 물어보세요).

### 5단계 — 첫 실행 (연결 확인)

가상환경이 없으면 먼저 만듭니다.

```bash
python3 -m venv ~/.venv-cs && ~/.venv-cs/bin/pip install -q finance-datareader ta backtesting pandas pytest requests
```

연결만 확인합니다(주문은 내지 않음 — 국내 잔고만 조회).

```bash
~/.venv-cs/bin/python -c "from broker.kis import KisBroker; b = KisBroker(); print(b.mode, b.account_masked, b.holdings('kr'))"
```

`mock 1234****-01 {}` 처럼 나오면 성공입니다(계좌번호는 가려져서 나옵니다).
처음 실행하면 접속 토큰이 `state/kis_token.json` 에 저장되고, 24시간 동안 재사용합니다.
토큰을 새로 받을 때마다 KIS 가 **알림톡**을 보냅니다(정상입니다). 하루에 여러 번 오면 토큰 파일이 지워지고 있는지 확인하세요.

그다음 실제 모의 주문은 주문 실행기(K3, `docs/broker-run.md`)로 냅니다.

```bash
~/.venv-cs/bin/python order_runner.py place --market kr --broker kis
```

### 자주 보는 오류

| 메시지 / 종류 | 뜻 | 할 일 |
|---|---|---|
| `KIS 설정이 없습니다: KIS_APP_KEY …` | `.env` 에 값이 빠짐 | 4단계 다시 |
| `실전 서버는 막혀 있습니다` | `KIS_MODE=real` 이 적혀 있음 | `KIS_MODE=mock` 으로 |
| `토큰 재발급은 1분에 1번만` (`rate_limit`) | KIS 규칙: 토큰은 1분에 1번만 발급 | 1분 뒤 다시 실행 |
| `auth` | 앱 키·시크릿이 틀렸거나 모의용이 아님 | 3단계 키 확인 |
| `rate_limit` (EGW00201) | 초당 호출 한도 초과 | 잠시 뒤 다시. 프로그램은 기본 초당 2회 이하로 부름 |
| `mock_expired` (40910000) | 모의투자 기간 끝 | 모의투자 다시 신청 |
| `network` + "주문이 들어갔는지 알 수 없습니다" | 주문 중 연결 끊김 | **다시 주문하지 말고** 체결 조회(`reconcile`)로 확인 |

---

## B. API 스펙 표 (모의투자 기준)

출처: 한국투자증권 공식 저장소 `koreainvestment/open-trading-api` (확인한 커밋 `3a9be59`, 2026-10-28).
이 저장소는 라이선스 표기가 없어서 **읽기만 하고 코드는 복사하지 않았습니다.** 아래 경로는 그 저장소 안의 경로입니다.
확인 못 한 값은 **(미확인)** 으로 적었습니다.

### B-1. 서버·토큰·공통 헤더

| 항목 | 값 | 출처 |
|---|---|---|
| 모의 서버 | `https://openapivts.koreainvestment.com:29443` | `kis_devlp.yaml` (`vps`) |
| 실전 서버 (막아 둠) | `https://openapi.koreainvestment.com:9443` | `kis_devlp.yaml` (`prod`) |
| 토큰 발급 | `POST /oauth2/tokenP`, 바디 `{"grant_type":"client_credentials","appkey","appsecret"}` | `examples_user/kis_auth.py` `auth()` |
| 토큰 응답 | `access_token`, `access_token_token_expired`(만료 일시) — `expires_in` 은 (미확인), 없으면 24시간으로 봄 | `examples_user/kis_auth.py` `auth()` |
| 토큰 수명·재발급 | 유효 1일, 재발급 **1분당 1회**, 6시간 이내 재신청은 같은 토큰, 발급 시 알림톡 | `examples_user/kis_auth.py` 주석, `README.md` §5 "토큰 오류 시" |
| 공통 헤더 | `content-type: application/json; charset=utf-8`, `authorization: Bearer <토큰>`, `appkey`, `appsecret`, `tr_id`, `custtype: P`(개인), `tr_cont`(연속조회: 처음 `""`, 다음 쪽 `N`) | `examples_user/kis_auth.py` `_base_headers`, `_url_fetch()` |
| 연속조회 | 응답 헤더 `tr_cont` 가 `M`/`F` 면 다음 쪽 있음 → 응답 본문 `ctx_area_fk100/nk100`(국내) 또는 `ctx_area_fk200/nk200`(해외)을 다음 요청에 넣음 | `examples_user/domestic_stock/domestic_stock_functions.py` `inquire_daily_ccld()` |
| 성공 판정 | HTTP 200 이고 본문 `rt_cd == "0"`. 실패 시 `msg_cd`, `msg1` | `examples_user/kis_auth.py` `APIResp` |
| hashkey | 주문 시 선택. 공식 예제도 꺼 둠 → 안 씀 | `examples_user/kis_auth.py` `_url_fetch()` (주석 처리된 `set_order_hash_key`) |
| 모의 호출 한도 | "모의투자 계좌는 REST API 호출 제한이 낮음". 정확한 초당 수치는 (미확인) → 우리는 **0.5초 간격(초당 2회)** | `README.md` §5 "초당 거래건수 초과", `examples_user/kis_auth.py` (`vps` 일 때 `_smartSleep = 0.5`) |

### B-2. 국내 주식

| 기능 | 메서드·경로 | 모의 tr_id (실전) | 필수 필드 (우리 값) | 출처 |
|---|---|---|---|---|
| 현금 **매수** | `POST /uapi/domestic-stock/v1/trading/order-cash` | `VTTC0012U` (`TTTC0012U`) | `CANO`, `ACNT_PRDT_CD`, `PDNO`(6자리), `ORD_DVSN`=`00`(지정가), `ORD_QTY`, `ORD_UNPR`(원, 문자열), `EXCG_ID_DVSN_CD`=`KRX`, `SLL_TYPE`=`""`, `CNDT_PRIC`=`""`. 바디 키는 **대문자**, 값은 **문자열** | `examples_user/domestic_stock/domestic_stock_functions.py` `order_cash()` |
| 현금 **매도** | 같음 | `VTTC0011U` (`TTTC0011U`) | 위와 같고 `SLL_TYPE`=`01`(일반매도) | 같음 |
| 주문 응답 | — | — | `output.ODNO`(주문번호), `KRX_FWDG_ORD_ORGNO`, `ORD_TMD` | `examples_llm/domestic_stock/order_cash/chk_order_cash.py` |
| **일별 체결** 조회 | `GET /uapi/domestic-stock/v1/trading/inquire-daily-ccld` | `VTTC0081R` (`TTTC0081R`), 3개월 이전은 `VTSC9215R` | `CANO`, `ACNT_PRDT_CD`, `INQR_STRT_DT`/`INQR_END_DT`(YYYYMMDD), `SLL_BUY_DVSN_CD`=`00`, `PDNO`=`""`, `CCLD_DVSN`=`01`(체결), `INQR_DVSN`=`00`, `INQR_DVSN_3`=`00`, `ORD_GNO_BRNO`, `ODNO`, `INQR_DVSN_1`, `CTX_AREA_FK100/NK100`, `EXCG_ID_DVSN_CD`=`KRX`. 모의는 한 번에 15건 | `domestic_stock_functions.py` `inquire_daily_ccld()` |
| 체결 응답 | — | — | `output1[]`: `odno`, `pdno`, `sll_buy_dvsn_cd`(01 매도/02 매수), `tot_ccld_qty`, `avg_prvs`(평균가) | `examples_llm/domestic_stock/inquire_daily_ccld/chk_inquire_daily_ccld.py` |
| **잔고** | `GET /uapi/domestic-stock/v1/trading/inquire-balance` | `VTTC8434R` (`TTTC8434R`) | `CANO`, `ACNT_PRDT_CD`, `AFHR_FLPR_YN`=`N`, `OFL_YN`=`""`, `INQR_DVSN`=`02`(종목별), `UNPR_DVSN`=`01`, `FUND_STTL_ICLD_YN`=`N`, `FNCG_AMT_AUTO_RDPT_YN`=`N`, `PRCS_DVSN`=`00`, `CTX_AREA_FK100/NK100`. 모의는 한 번에 20건 | `domestic_stock_functions.py` `inquire_balance()` |
| 잔고 응답 | — | — | `output1[]`: `pdno`, `hldg_qty`(보유수량), `ord_psbl_qty` | `examples_llm/domestic_stock/inquire_balance/chk_inquire_balance.py` |
| **매수가능** | `GET /uapi/domestic-stock/v1/trading/inquire-psbl-order` | `VTTC8908R` (`TTTC8908R`) | `CANO`, `ACNT_PRDT_CD`, `PDNO`, `ORD_UNPR`, `ORD_DVSN`=`01`(공식 설명: 증거금율 반영 수량은 시장가 `01`로 조회), `CMA_EVLU_AMT_ICLD_YN`=`N`, `OVRS_ICLD_YN`=`N` | `domestic_stock_functions.py` `inquire_psbl_order()` |
| 매수가능 응답 | — | — | `output.nrcvb_buy_qty`(미수 없는 매수수량) ← 우리가 씀, `max_buy_qty` | `examples_llm/domestic_stock/inquire_psbl_order/chk_inquire_psbl_order.py` |

(미확인) 모의 주문에서 `EXCG_ID_DVSN_CD` 가 필수인지 / 빈 값이어도 되는지. 공식 함수는 필수로 검사함.

### B-3. 해외(미국) 주식

| 기능 | 메서드·경로 | 모의 tr_id (실전) | 필수 필드 (우리 값) | 출처 |
|---|---|---|---|---|
| 미국 **매수** | `POST /uapi/overseas-stock/v1/trading/order` | `VTTT1002U` (`TTTT1002U`) | `CANO`, `ACNT_PRDT_CD`, `OVRS_EXCG_CD`(NASD/NYSE/AMEX), `PDNO`(티커), `ORD_QTY`, `OVRS_ORD_UNPR`(달러, 소수 2자리), `CTAC_TLNO`=`""`, `MGCO_APTM_ODNO`=`""`, `SLL_TYPE`=`""`, `ORD_SVR_DVSN_CD`=`0`, `ORD_DVSN`=`00`(**모의는 지정가만**) | `examples_user/overseas_stock/overseas_stock_functions.py` `order()` |
| 미국 **매도** | 같음 | `VTTT1001U` (`TTTT1006U`) ※ | 위와 같고 `SLL_TYPE`=`00` | 같음 + `legacy/postman/실전계좌_POSTMAN_샘플코드_v2.6.json` |
| 주문 응답 | — | — | `output.ODNO`, `KRX_FWDG_ORD_ORGNO`, `ORD_TMD` | `examples_llm/overseas_stock/order/chk_order.py` |
| **체결** 조회 | `GET /uapi/overseas-stock/v1/trading/inquire-ccnl` | `VTTS3035R` (`TTTS3035R`) | `CANO`, `ACNT_PRDT_CD`, `PDNO`=`""`, `ORD_STRT_DT`/`ORD_END_DT`(YYYYMMDD, **현지 날짜**), `SLL_BUY_DVSN`=`00`, `CCLD_NCCS_DVSN`=`00`, `OVRS_EXCG_CD`=`""`, `SORT_SQN`=`DS`, `ORD_DT`/`ORD_GNO_BRNO`/`ODNO`=`""`, `CTX_AREA_NK200/FK200`. **모의는 PDNO·거래소 `""`, 구분 `00` 만 가능** | `overseas_stock_functions.py` `inquire_ccnl()` |
| 체결 응답 | — | — | `output[]`: `odno`, `pdno`, `sll_buy_dvsn_cd`(01 매도/02 매수), `ft_ccld_qty`, `ft_ccld_unpr3`(체결단가), `nccs_qty`(미체결) | `examples_llm/overseas_stock/inquire_ccnl/chk_inquire_ccnl.py` |
| **잔고** | `GET /uapi/overseas-stock/v1/trading/inquire-balance` | `VTTS3012R` (`TTTS3012R`) | `CANO`, `ACNT_PRDT_CD`, `OVRS_EXCG_CD`(모의: NASD=나스닥만, NYSE, AMEX → **세 번** 조회), `TR_CRCY_CD`=`USD`, `CTX_AREA_FK200/NK200` | `overseas_stock_functions.py` `inquire_balance()` |
| 잔고 응답 | — | — | `output1[]`: `ovrs_pdno`, `ovrs_cblc_qty`(잔고수량), `ord_psbl_qty` | `examples_llm/overseas_stock/inquire_balance/chk_inquire_balance.py` |
| **매수가능** | `GET /uapi/overseas-stock/v1/trading/inquire-psamount` | `VTTS3007R` (`TTTS3007R`) | `CANO`, `ACNT_PRDT_CD`, `OVRS_EXCG_CD`, `OVRS_ORD_UNPR`, `ITEM_CD` | `overseas_stock_functions.py` `inquire_psamount()` |
| 매수가능 응답 | — | — | `output.ord_psbl_qty`(외화 기준) ← 우리가 씀(환전은 범위 밖), `max_ord_psbl_qty`, `echm_af_ord_psbl_qty`(환전 후) | `examples_llm/overseas_stock/inquire_psamount/chk_inquire_psamount.py` |
| 거래소 코드 찾기 | `GET /uapi/overseas-price/v1/quotations/price` | `HHDFS00000300` (모의·실전 공통) | `AUTH`=`""`, `EXCD`(NAS/NYS/AMS), `SYMB` → `output.last` 가 있으면 그 거래소 | `overseas_stock_functions.py` `price()`, `examples_llm/overseas_stock/price/chk_price.py` |

※ **미국 모의 매도 tr_id 불일치**: 문서·주석·Postman 은 `VTTT1001U`, 공식 예제 코드는 `'V' + TTTT1006U` 로 만들어
`VTTT1006U` 가 됩니다. 우리는 문서값 `VTTT1001U` 를 씁니다 — **(미확인)**, 첫 모의 매도 때 확인 필요.
거절되면 `broker/kis.py` 의 `TR_IDS["mock"]["us_sell"]` 하나만 바꾸면 됩니다.

주문용 거래소 코드 ↔ 시세용 코드: `NASD↔NAS`, `NYSE↔NYS`, `AMEX↔AMS`.

### B-4. v1 미국 종목 거래소 표 (`broker/kis.py` `US_EXCHANGE`)

| 종목 | 거래소 | 비고 |
|---|---|---|
| AAPL, MSFT, NVDA, GOOGL, AMZN | `NASD` | 나스닥 상장 |
| SPY | `AMEX` | NYSE Arca 상장. KIS 는 Arca 를 AMEX 로 분류하는 것으로 알려짐 **(미확인)** |

표에 없는 종목은 위 "거래소 코드 찾기" API 로 NAS → NYS → AMS 순으로 물어보고 기억합니다.

### B-5. 오류 코드 → `classify_error` 분류

| 조건 | 분류 | 출처 |
|---|---|---|
| 연결 실패·시간 초과, HTTP 5xx(코드 없음) | `network` | — |
| `EGW00201` (초당 거래건수 초과), HTTP 429 | `rate_limit` | `README.md` §5, `backtester/examples/README.md` |
| `EGW00133` (토큰 1분 제한) | `rate_limit` | (미확인) |
| `EGW00123` (기간이 만료된 token) | `auth` | `legacy/rest/current_price_samle.py` |
| `EGW00121`, `EGW00102`, `EGW00103`, `EGW00105` (토큰·앱 키 오류), HTTP 401/403 | `auth` | (미확인) |
| `40910000` (모의투자 기간 만료) | `mock_expired` | 설계 K-D4. 공식 저장소에서 못 찾음 **(미확인)** |
| HTTP 200 인데 `rt_cd != "0"` (잔고 부족·가격 오류 등), 그 밖 4xx | `rejected` | — |
| 그 밖 | `unknown` | — |

### B-6. `broker/kis.py` 안전장치 요약

- 주문(`place`)은 **재시도하지 않음**. 예외도 던지지 않고 `OrderResult(ok=False, error_kind=…)`.
  연결이 끊기면 증권사가 받았는지 모르므로 메시지로 "체결 조회로 확인"을 안내.
- 조회(`fills`/`holdings`/`buyable_shares`)만 `network`·`rate_limit`·`auth` 일 때 최대 3번 재시도(1초, 2초, 3초 쉬고).
- 모든 호출 사이 0.5초 이상(초당 2회 이하).
- 토큰은 `state/kis_token.json` 에 저장(권한 600, gitignore). 앱 키 자체는 저장하지 않고 키의 해시 앞 12자리로 "같은 키인지"만 확인.
  재발급 시도 시각을 먼저 기록해서, 실패해도 다른 실행이 1분 안에 또 요청하지 않음.
- 로그·메시지의 계좌번호는 `1234****-01` 로, 앱 키·시크릿·토큰은 `***` 로 가림.
- 실전 서버는 `KIS_MODE=real` + `KIS_I_UNDERSTAND_REAL=yes` 일 때만. 하나라도 없으면 `KisConfigError` 로 시작부터 멈춤.
