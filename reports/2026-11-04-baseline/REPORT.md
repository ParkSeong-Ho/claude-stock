# 기준선(baseline) 모의매매 실행 기록 — 2026-11-04

> 브랜치 `run/baseline-2026-11-04` (포크 ParkSeong-Ho/claude-stock). 코드·프롬프트·기존 문서는 **수정하지 않음**. 새 파일은 이 폴더에만 있음.
> 진짜 돈 0원. 이 문서는 "있는 그대로 돌려 보니 무슨 일이 있었나"의 기록이다.

## 1. 한눈 요약

1. **돌았나:** 오프라인 자체점검 4개(`team.py check`, `analyst.py`, `paper_wallet.py`, `risk_guard.py`)는 모두 **PASS**. 시세가 필요한 6개 단계(`main.py`, `team.py 40` ×2, `live.py`, `validate.py`, `tune.py`)는 **전부 1초 안에 실패**했다.
2. **성적:** **없음.** 시세를 한 줄도 못 받아서 거래 0건이고 `results/`·`state/`도 생기지 않았다. 손익 숫자를 만들어 내지 않았다.
3. **가장 큰 문제(코드):** `team.py`가 **달러 가격을 원화로 취급**한다. S&P500 종목을 $500에 사면 원화 예산의 약 420배를 산 셈이 된다(합성 재현). 그다음은 `max(1, …)` 때문에 비싼 종목에서 **종목상한을 3~6배 넘겨** 사는 문제다.
4. **데이터 접근:** 시세 도메인 3곳이 **모두 프록시 403**이다. `fchart.stock.naver.com`, `query2.finance.yahoo.com`, `en.wikipedia.org` (`Tunnel connection failed: 403 Forbidden`). pypi와 github는 된다. 과제에 "허용 도메인"이라고 적혀 있지만 이 세션의 네트워크 정책에는 빠져 있다.
5. **팀장(LLM) 호출:** `team.py` 실행에서는 스크리너 단계에서 죽어 **analyst까지 가지도 못했다**. 따로 점검했을 때는 `claude` CLI 2.1.318로 **실제 호출에 성공**했다(3.5초, 올바른 JSON). 즉 폴백이 아니라 실제 응답이다. 다만 팀장은 실시간 뉴스를 볼 수 없다는 점을 스스로 밝혔다.

> 푸시: 아래 10단계 참고(성공 시 이 줄 아래에 별도 기록 없음).

## 2. 실행 표

| 단계 | 명령 | 결과 | 걸린 시간 | 비고 |
|---|---|---|---|---|
| 1 | `git checkout -b run/baseline-2026-11-04` | 성공 | <1s | |
| 2a | `pip install finance-datareader ta backtesting pandas pytest` | **실패** | 5s | `pip`는 **Python 3.13**용이고 `python`은 **3.11.18**이라 버전이 어긋난다. `ta` 휠 빌드가 실패했다(`AttributeError: install_layout`, 데비안 setuptools 68). `logs/02_pip.txt` 참고 |
| 2b | `python -m pip install …` | **실패** | 6s | 같은 `ta` 빌드 오류 (`logs/02_pip_py311.txt`) |
| 2c | `python -m venv ~/.venv-cs` 후 설치 | 성공 | 14s | 이후 모든 단계는 이 venv에서 실행. 버전: finance-datareader 0.9.202 · ta 0.11.0 · backtesting 0.6.6 · pandas 3.1.0 · numpy 2.4.6 · pytest 9.2.0 · requests 2.34.2 |
| 3 | `python team.py check` | 성공 | 0.3s | `[PASS] team 매수 후보 확신도 필터 점검 통과` |
| 3 | `python analyst.py` | 성공 | 0.03s | `[PASS] analyst JSON파싱·veto·폴백 점검 통과` |
| 3 | `python paper_wallet.py` | 성공 | 0.03s | `[PASS] 왕복 비용 310원(0.31%)` |
| 3 | `python risk_guard.py` | 성공 | 0.01s | `[PASS] CircuitBreaker 자체 점검 통과` |
| 3 | `screener.py`, `universe_check.py`, `main/live/validate/tune.py` | 해당 없음 | — | `__main__`에 assert가 없고 네트워크가 필요하다. 브레인 3개 파일에는 `__main__`이 없다 |
| 4 | FDR 005930 / SPY / S&P500 목록 | **실패** | 1s | 3개 모두 프록시 403. `StockListing('KRX')`는 `UnboundLocalError`(라이브러리 내부 오류, 네트워크 실패 때문에 생긴 것으로 보임). `logs/04_data.txt` 참고 |
| 5 | `python main.py` | **실패** | 0s | 삼성전자 첫 종목에서 중단. `error_log.txt`에 기록됨. CSV 0개 |
| 6 | `python team.py 40` | **실패** | 0s | `screener.universe()` → wikipedia 403. **traceback이 그대로 나오고 error_log에도 안 남는다**(main/live와 다르게 감싼 try가 없음). `state/team_*.json` 생성 안 됨. analyst 호출 안 됨 |
| 7 | `python team.py 40` (재실행) | **실패** | 1s | 같은 오류. 상태 파일이 없어서 멱등성은 **실측 불가**. 합성 재현은 4-⑧ 참고 |
| 8 | `python live.py` | **실패** | 1s | 첫 종목 시세에서 실패. error_log에 기록 |
| 9 | `python validate.py` | **실패** | 0s | 005930 naver 403 |
| 9 | `python tune.py` | **실패** | 1s | 005930 naver 403 |
| + | 오프라인 점검 `probes/offline_probes.py` | 성공 | ~2s | 합성 데이터와 monkeypatch만 사용(저장소 코드 수정 없음). `logs/10_offline_probes.txt` |
| + | analyst 실호출 점검 | 성공 | 3.7s | `logs/11_analyst_probe.txt` |

10분 넘게 걸린 명령은 없다. 원본 `error_log.txt`(저장소 루트, gitignore 대상)는 `logs/error_log.txt`로 옮겼다.

## 3. 성적표

**main.py (트레이너별 순손익·승률·MDD·거래 수):** 데이터를 못 받아 **산출하지 못했다.** 숫자를 지어내지 않는다.

| 트레이너 | 순손익 | 승률 | MDD | 거래 수 |
|---|---|---|---|---|
| 마라토너 | — | — | — | 0 |
| 스프린터 | — | — | — | 0 |
| 파이오니어 | — | — | — | 0 |

**team.py 하루치:** 스크리너 단계에서 중단됐다. 후보·매수·평가 모두 없음.

## 4. 관찰한 문제

심각도: 높음(돈 계산·판단이 틀림) / 중간(특정 상황에서 틀리거나 멈춤) / 낮음(정리·문서).
아래 "실제 출력"은 이번 실행 로그나 `probes/offline_probes.py`의 합성 재현 출력이다.

### ① 데이터 도메인이 막혀 있다 — 환경 · 높음
- 증상: `HTTPSConnectionPool(host='fchart.stock.naver.com'…) Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))` (yahoo, wikipedia도 같음)
- 위치: 환경(네트워크 정책). 코드 쪽 진입점은 `main.py:67`, `screener.py:30`
- 원인: 세션 네트워크 허용 목록에 위 3개 도메인이 없다.
- 방향: 클라우드 환경 네트워크 정책에 3개 도메인을 추가하고 다시 실행한다.

### ② 원화 지갑에 달러 가격이 섞인다 — 높음
- 증상(합성): `가격 $500.0 를 '500.0원'으로 계산 → 360주 매수, 지갑 차감 180,117원 / 실제 가치는 … 252,000,000원 (예산 600,000원의 420배)`
- 위치: `team.py:113-115` (S&P500 후보의 `price`를 그대로 원화 예산으로 나눔), `main.py:39-44,135`, `live.py:112` (005930과 AAPL을 같은 원화 예산으로 매매)
- 원인: 통화 개념이 없다. `PaperWallet`은 숫자만 다룬다. main/live는 종목별로 지갑이 따로라 손익 숫자가 원/달러 섞인 단위가 되고, team.py는 한 지갑에서 달러 종목을 원화로 사므로 노출이 수백 배 부풀려진다.
- 방향: 종목마다 통화를 붙이고, 매수 수량은 `예산(원) / (가격 × 환율)`로 계산한다. 또는 트레이너 지갑을 통화별로 나눈다.

### ③ `max(1, int(cash*cap/price))`가 종목상한을 넘긴다 — 높음
- 증상(합성): `파이오니어 예산 100,000 상한 15%(=15,000) 가격 90,000 → 1주, 체결=True, 실제투입 90,059 = 예산의 90% (상한의 6.0배)` / `스프린터 … 가격 250,000 → 1주 … 상한의 4.2배`
- 위치: `team.py:114`, `main.py:135`, `live.py:112`
- 원인: 상한으로 0주가 나와도 최소 1주를 강제한다. 예산보다 비싸면 `wallet.buy`가 False를 내고 **조용히** 넘어간다(`마라토너 … 가격 700,000 → 체결=False`). 기획서 3.1의 "상한을 절대 넘지 않는다"를 어긴다.
- 방향: `shares = int(cash*cap/price)`로 바꾸고 0이면 매수를 건너뛰며 "상한 미달로 보류" 로그를 남긴다.

### ④ 체결가 = 신호를 계산한 그 날의 종가 — 중간
- 증상(합성): `판단은 window=df.iloc[:day+1](당일 종가 포함), 체결도 같은 row['Close'] → '종가 보고 종가에 산다'. 미래 봉 참조는 없음.`
- 위치: `main.py:106-110,135-136`, `live.py:79-81,113`, `team.py:87,113` (`screener.py:55`)
- 원인: 다음 날 이후 데이터를 쓰지는 않는다. 그러나 당일 종가로 지표를 계산한 뒤 **같은 종가에 체결**하므로 현실보다 약간 유리하다(현실에선 다음 날 시가). team.py를 미국장 개장 중(한국 밤)에 돌리면 마지막 봉이 **장중 미완성 봉**일 수 있다.
- 방향: 백테스트는 "신호 다음 날 시가 체결"로 바꾸고, live/team은 장 마감이 확정된 봉만 쓴다.

### ⑤ 승률이 비용을 무시한다 — 낮음
- 위치: `main.py:123,143` (`if price > entry: wins += 1`)
- 원인: 수수료·세금·슬리피지 0.31%를 빼지 않아, 0.1% 오른 거래도 "승리"로 센다(실제로는 손실).
- 방향: 매도 순수령액과 매수 총비용을 비교해 승패를 정한다.

### ⑥ 거래세 0.18% (현행 0.20% 기준) — 중간
- 증상: `PaperWallet 기본 sell_tax_rate = 0.0018 (0.18%) / 과제 기준 현행 0.20%`
- 위치: `paper_wallet.py:31`, `team.py:57` (기본값 0.0018 하드코딩), 기획서 `AI트레이너_주식자동매매_기획서.md:212` ("0.15~0.18%"), `공유사항.md:17`
- 원인: 기획서를 쓸 당시의 세율 그대로다. 미국 종목에도 똑같이 부과한다(공유사항에서 의도적 과대추정으로 결정됨).
- 방향: 0.0020으로 올리고, 시장별(KR/US) 분기는 ②와 함께 처리한다.

### ⑦ analyst 응답 파싱·conviction 타입 — 중간~높음
- 증상(합성):
  - `JSON 뒤에 중괄호 섞인 설명 → None(폴백)`, `JSON 두 개 → None(폴백)`: 탐욕 정규식 `\{.*\}`가 첫 `{`부터 마지막 `}`까지 잡는다.
  - `conviction='0.8' keep_candidate → 예외 TypeError: '>=' not supported between instances of 'str' and 'float'`: LLM이 숫자를 문자열로 주면 **team.py 전체가 죽는다**(analyst의 "팀장 없어도 멈추지 않는다" 안전원칙이 깨짐). 정렬(`team.py:109`)도 같은 TypeError가 난다.
  - `verdict='hold', conviction=0.9 → apply 후 남음=True keep=True (hold인데 매수됨)`: `apply`는 veto만 제외한다. 프롬프트의 "확신 없으면 hold"가 매수를 막지 못한다.
- 위치: `analyst.py:55` (정규식), `analyst.py:84-96` (hold 무시, 타입 검증 없음), `team.py:37-39,109`
- 실호출 결과: `{"analysis":[{"code":"AAPL","verdict":"hold","conviction":0.4,…}]}` 형식은 정상이었다. 그러나 note에 "실시간 악재·실적 확인 불가"라고 적혔다. 프롬프트는 "최근 시장 상황·악재를 고려하라"고 하지만 `claude -p`에는 뉴스나 시세를 줄 수단이 없다.
- 방향: `json.JSONDecoder().raw_decode`로 첫 객체만 파싱하고, conviction은 `float()`로 바꾸되 실패하면 None으로 둔다. hold는 매수 보류로 처리하고, 프롬프트에는 실제로 줄 수 있는 정보만 요구한다.

### ⑧ 실행 판단이 '달력 날짜' 기준 — 주말·휴장일도 하루로 센다 — 높음
- 증상(합성, 마지막 봉은 그대로인데 날짜만 바꿔 실행):
  ```
  2025-06-20(금) … 매수 SYNx447@134.00 | days_held={'SYN': 0}
  2025-06-21(토) … 변화 없음 | days_held={'SYN': 1}
  2025-06-22(일) … 변화 없음 | days_held={'SYN': 2}
  2025-06-23(월) … 매도 SYN@134.00(3일이 지났는데 기세가 없); 매수 SYNx447 | days_held={'SYN': 0}
  ```
- 위치: `team.py:75-76` (`datetime.now().date()`로 멱등 판단), `team.py:88` (`days_held += 1`)
- 원인: 데이터 날짜가 아니라 컴퓨터 날짜를 쓴다. 주말·휴장일에 돌리면 같은 봉을 "새 하루"로 처리하고 스프린터의 3일 시간제한이 거래일 없이 소진된다. 같은 날 다시 실행하는 멱등 자체는 막힌다. `live.py:80,91`는 데이터 마지막 봉 날짜를 써서 이 문제가 없다.
- 추가: 같은 실행 안에서 ①에서 판 종목을 ③에서 **같은 가격에 다시 산다**(위 월요일 줄). 왕복 비용만 날아간다.
- 방향: 기준 날짜를 `df.index[-1]`(거래일)로 바꾸고, 그날 판 종목은 그날 재매수 후보에서 뺀다.

### ⑨ 예외 한 번에 루프 전체가 죽는다 / 상태 저장이 원자적이지 않다 — 중간
- 증상(실측): `team.py 40` → 스크리너 목록 실패 traceback으로 즉시 종료. 다른 진입점과 달리 try/except 래퍼가 없어 `error_log.txt`에도 남지 않는다.
- 증상(합성): `깨진 state 파일 로드 → JSONDecodeError: Unterminated string … (run() 전체 중단, 이후 트레이너 미실행)` / `_save: write_text 직접 덮어쓰기(임시파일+rename 아님)`
- 위치: `team.py:127-142` (트레이너별 try 없음), `team.py:42-52`, `live.py:56-62,135-138` (한 종목 실패면 나머지 종목·트레이너 전부 중단)
- 반대 문제: 보유 종목 시세 조회가 실패하면 `team.py:84-86`이 `continue`로 **조용히** 넘어간다. 평가액은 매입가로 계산돼(`paper_wallet.py:83`) 손실이 가려지고, 손절·서킷 브레이커 판단에서도 빠진다.
- 방향: 트레이너·종목 단위로 try를 걸어 로그를 남기고 계속 진행한다. 저장은 임시 파일에 쓴 뒤 `os.replace`로 바꾼다. 시세 실패는 경고로 표시한다.

### ⑩ 기타 — 낮음
- `live.py:43` `_wallet_from_dict`는 `sell_tax_rate`·`slippage`를 복원하지 않는다(합성: `0.002, 0.001 → 복원 후 0.0018, 0.0005`). 지금은 기본값이라 차이가 없지만, ⑥을 고치면 저장된 지갑이 옛 세율로 돌아간다.
- `main.py:235`, `live.py:153`: `error_log.txt`를 **현재 작업 폴더**에 쓴다(스크립트 폴더가 아님).
- `main.py:199-207`: 종목마다 트레이너 예산 전체를 새로 쓴다. 5종목이면 마라토너 60만원 × 5로, 포트폴리오 성적이 아니라 종목별 성적이다(설명 필요).
- 환경: `pip` 실행 파일이 다른 파이썬(3.13)을 가리키고 데비안 setuptools로 `ta` 빌드가 실패한다. README의 설치 한 줄은 venv 없이는 이 환경에서 안 된다.

### ⑪ 계획서·코드·프롬프트 숫자 불일치 — 낮음(혼란 유발)
| 항목 | 기획서 | 코드 | 프롬프트 |
|---|---|---|---|
| 스프린터 익절/손절 | +3% / -2% (`기획서:49`) | +5% / -1.5% (`sprinter_brain.py:25`), 그런데 같은 파일 docstring `:9-10`은 +3%/-2% | +5% / -1.5% (`prompts/스프린터.md:4`) |
| 스프린터 진입 RSI | 70 미만 | 55 이상 70 미만 (`sprinter_brain.py:26`) | 55~70 |
| 파이오니어 과냉 RSI | 30 이하 (`기획서:63`) | **35** (`pioneer_brain.py:26`), 주석 `:73`은 "30 이하" | **40 이하** (`prompts/파이오니어.md:4`) |
| 파이오니어 거래량 급증 | (배수 없음) | 1.5배 (`pioneer_brain.py:26`) | — |
| 거래세 | 0.15~0.18% (`기획서:212`) | 0.18% | — |

특히 파이오니어는 팀장(LLM)이 프롬프트에서 "RSI 40 이하"로 배우는데 실제 규칙은 35라서, 팀장 판단의 전제가 틀린다.

## 5. 다음 수정 후보 (원래 저장소 이슈 제목 형태, 우선순위 순)

1. `[환경] 클라우드 세션에서 naver/yahoo/wikipedia 시세 도메인 403 — 네트워크 허용 목록 추가 필요`
2. `[team] S&P500(달러) 가격을 원화 예산으로 나눠 매수 — 통화·환율 반영 필요 (노출 수백 배 과대)`
3. `[team/main/live] max(1, …)로 종목상한 초과 매수 — 0주면 매수 보류`
4. `[team] 실행 날짜를 달력 대신 데이터 마지막 거래일 기준으로 — 주말 실행 시 days_held 증가·시간제한 오작동`
5. `[analyst/team] conviction 문자열이면 TypeError로 루프 전체 중단 — 숫자 변환·검증`
6. `[analyst] verdict=hold가 매수를 막지 않음 — hold를 보류로 처리`
7. `[team/live] 예외 하나에 전체 루프 중단 + 상태 JSON 비원자적 저장 — 단위별 try, 임시파일+os.replace`
8. `[team] 보유 종목 시세 실패 시 조용히 continue → 매입가 평가로 손실 은폐`
9. `[analyst] JSON 추출 정규식 탐욕 매칭 — raw_decode 사용`
10. `[backtest] 신호 당일 종가 체결 → 다음 날 시가 체결로 (낙관 편향 제거)`
11. `[team] 같은 실행에서 매도한 종목을 즉시 재매수 — 당일 재진입 금지`
12. `[wallet] 증권거래세 0.18% → 0.20% 갱신 + live 상태 복원 시 비용 필드 유지`
13. `[main] 승률을 비용 차감 후 손익 기준으로`
14. `[docs] 기획서·브레인 docstring·프롬프트의 파이오니어 RSI(30/35/40)·스프린터 익손절 숫자 통일`
15. `[docs] README 설치 안내에 venv 권장 (pip/python 버전 불일치·ta 빌드 실패 사례)`

---
### 파일
- `logs/`: 단계별 전체 출력(`02_*` 설치, `03_offline`, `04_data`, `05_main`, `06/07_team`, `08_live`, `09_validate/tune`, `10_offline_probes`, `11_analyst_probe`, `error_log.txt`)
- `probes/offline_probes.py`: 4장 합성 재현 스크립트(네트워크 불필요, 저장소 코드 무수정)
- `results/README.txt`: CSV가 없는 이유
