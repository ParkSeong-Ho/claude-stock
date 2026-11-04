# claude-stock v1 설계

- 작성: 2026-11-04 · 대상: 포크 `ParkSeong-Ho/claude-stock`, 기준 브랜치 `v1`
- 근거: 브랜치 `run/baseline-2026-11-04`의 `reports/2026-11-04-baseline/REPORT.md`(1차, 합성 재현)와 `run2/REPORT.md`(2차, 실제 시세)
- 진행: 문제 확인 → **설계(이 문서)** → v1 구현 → 실측 → 새 문제 수정 → 반복

## 1. 목표 / 비목표

**목표**: main / team / live / validate / tune 이 실제 시세로 **nan·크래시 없이** 끝까지 돌고, 모든 성적표에 buy&hold·SPY 비교가 찍힌다. 돈 계산(통화·주식 수·체결가·비용)이 현실과 맞는다.

**비목표 (v1에서 안 함)**
- 서킷 브레이커 재개 규칙(D6) — 원래 저장소 공동작업자와 합의 후. 지금 동작 유지.
- 전략 숫자(익절·손절·RSI 등) 튜닝 — v1 실측 결과를 보고 판단.
- 한국 종목, 환율, 실거래.

**안티목표**: 성적을 좋게 보이게 만드는 변경. 미래 데이터를 보는 변경. 원래 저장소(kjh3291)에 PR·이슈 생성.

## 2. 확정된 결정

| ID | 결정 |
|---|---|
| D1 | **확정 봉만 쓴다.** `Close`가 NaN인 행은 버린다. 마지막 봉의 날짜가 미국 동부시간 기준 "오늘"이고 현재가 16:15 ET 이전이면 그 봉도 버린다. |
| D2 | "이미 처리" 판단은 달력 날짜가 아니라 **마지막 확정 봉의 날짜**. 새 확정 봉이 없으면(주말·휴장·장중) 아무것도 저장하지 않고 끝낸다. |
| D3 | **체결은 다음 거래일 시가(Open).** 봉 t의 종가로 신호 → 봉 t+1의 Open으로 체결. 백테스트와 일일 루프 모두. 일일 루프는 신호를 상태 파일의 `pending`에 저장하고 다음 실행에서 새 봉의 Open으로 체결한다. |
| D4 | **v1은 미국 종목 전용, 지갑은 달러.** 모든 금액 표기는 `$`. 한국 종목은 종목 목록에서 뺀다. |
| D5 | 상한 안에서 1주도 못 사면 **매수 보류 + 사유 로그**. 상한을 넘겨 1주 사는 `max(1, …)`는 없앤다. |
| D6 | (v1 제외) 서킷 브레이커는 현행 유지. |
| D7 | 모든 성적표에 **buy&hold(같은 투입액)와 SPY 대비** 비교를 기본 출력. "이겼다"는 이 숫자로만 말한다. |
| D8 | 미국 기준 비용: 매매 수수료 `fee_rate = 0.001`(양방향, 설정값), 매도세 `0`, 슬리피지 `0.0005` 유지. |

설계자 판단(바꿔도 됨): 총 가상자금 **$10,000**, 배분비율·종목상한은 현행 유지. main.py 종목 목록은 `AAPL, MSFT, NVDA, GOOGL, AMZN`.

## 3. 인터페이스 (세션 간 약속)

병렬 세션이 서로의 코드를 보지 않고 작업하므로, 아래 이름·시그니처를 그대로 지킨다.

### paper_wallet.py (S1 소유)
```python
PaperWallet(name, cash=0.0, currency="USD", fee_rate=0.001, sell_tax_rate=0.0, slippage=0.0005)
wallet.buy(code, price, shares, date: str | None = None) -> bool    # date=거래일 'YYYY-MM-DD', 없으면 현재시각
wallet.sell(code, price, shares, date: str | None = None) -> bool
wallet.skip(code, reason: str, date: str | None = None) -> None     # 매수 보류 등 '안 한 거래'도 log에 남김(종류="보류")
wallet.value(prices) -> float
shares_within_cap(budget: float, cap: float, price: float, fee_rate=0.001, slippage=0.0005) -> int
    # 예산*상한 안에서 비용 포함해 살 수 있는 최대 주식 수. 1주도 안 되면 0. 절대 상한 초과 금지.
```
log 항목 키: `시각, 종류, 종목, 수량, 금액, 통화, 사유`(사유는 보류일 때만).

### metrics.py (S2 소유, 새 파일, pandas만 사용)
```python
max_drawdown(values: list[float]) -> float                     # 음수 비율, 예: -0.12
total_return(values) -> float
sharpe(values, periods_per_year=252) -> float | None           # 일별 평가금액 → 연환산, 데이터 부족 시 None
buy_and_hold(prices: pd.Series, budget: float, fee_rate=0.001, slippage=0.0005) -> dict
    # {"start", "end", "shares", "profit", "return"}  첫 날 Open(없으면 Close)에 사서 마지막 Close 평가
benchmark_return(bench_prices: pd.Series, start: str, end: str) -> float   # 예: SPY
compare_line(name, profit, bh: dict, spy_ret: float, budget: float) -> str  # 사람이 읽을 비교 한 줄
```
NaN이 들어와도 예외 대신 `None`/`nan`을 돌려주지 말고 **NaN 행을 먼저 제거**하고 계산한다.

### 데이터 (S4 소유, main.py)
```python
main.load_prices(code, start, now=None) -> pd.DataFrame   # D1 적용된 확정 봉만
main.confirmed_bars(df, now=None) -> pd.DataFrame          # 순수 함수, 테스트용
```

## 4. 작업 나누기 (파일 소유권)

| 세션 | 브랜치 | 소유 파일 (이 파일만 수정) | 내용 |
|---|---|---|---|
| S0 기반 | `v1/s0-ci` | `tests/conftest.py`, `tests/test_analyst.py`, `tests/test_risk_guard.py`, `tests/test_team_filter.py`, `pytest.ini`, `requirements.txt`, `.github/workflows/test.yml` | 기존 `__main__` assert를 pytest로 옮김(네트워크 없음). CI: push·PR에서 `pytest` 실행. |
| S1 지갑 | `v1/s1-wallet` | `paper_wallet.py`, `tests/test_paper_wallet.py` | D4·D5·D8, 거래일 기록, `skip`, `shares_within_cap`. |
| S2 지표 | `v1/s2-metrics` | `metrics.py`, `tests/test_metrics.py` | D7 함수들. |
| S3 검증도구 | `v1/s3-validate` | `tune.py`, `validate.py`, `tests/test_tune_validate.py` | 조합 단위 예외 처리, NaN이면 "계산 불가"로 기록하고 계속, 끝에 실패 요약. 전략 숫자는 건드리지 않음. |
| S4 흐름 (2차) | `v1/s4-flow` | `main.py`, `live.py`, `team.py`, `screener.py`, `universe_check.py`, `README.md` | D1·D2·D3·D5 적용, S1·S2 연결, 미국 전용 종목 목록. S0~S3 합친 뒤 시작. |
| 실측 (3차) | `run/v1-measure` | `reports/` | 기준선과 같은 절차로 실측, 기준선과 나란히 비교. |

공통 규칙
- 소유 파일 밖은 **수정 금지**(읽기는 자유). 다른 세션의 인터페이스가 필요하면 §3 시그니처대로 쓴다고 가정.
- 테스트는 네트워크 없이 돌아야 한다(합성 DataFrame 사용).
- 커밋 메시지·주석은 한국어, 기존 코드 말투(초보자용 설명) 유지.
- 끝나면 자기 브랜치에 푸시만. PR은 사람이 `v1`로 만든다. 원래 저장소에는 아무것도 하지 않는다.
- 의존성: `~/.venv-cs`가 없으면 `python -m venv ~/.venv-cs && ~/.venv-cs/bin/pip install finance-datareader ta backtesting pandas pytest`. 시스템 `pip`는 다른 파이썬을 가리키니 쓰지 않는다.

## 5. v1 완료 기준

1. `pytest` 전부 통과(CI 초록).
2. 실측에서 main / team(2회) / live / validate / tune 모두 종료코드 0, 출력에 `nan` 없음.
3. 상한 초과 매수 0건, 원화·달러 혼합 0건, 매수 보류는 사유와 함께 로그에 있음.
4. 모든 성적표에 buy&hold·SPY 비교 줄.
5. 실측 보고서에 기준선 대비 변화와 **새로 생긴 문제** 목록 → 다음 반복의 입력.
