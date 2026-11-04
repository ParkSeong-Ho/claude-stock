# H1 포워드 모의매매 설계 — "쉬는 돈을 지수에" 장부(A1)와 "쉬는 돈은 현금" 그림자 장부(A0)를 나란히

- 작성: 2026-11-04 · 브랜치 `h1-forward` · **3판**: 독립 검토 1회(`docs/h1-forward-design-review-1.md`, 대상 11a5711)와 2판 재검토(`docs/h1-forward-design-review-2.md`, 대상 2afb019)를 반영했다
- 이 단계는 **설계만** 한다. `.py` 는 한 줄도 고치지 않았다(`pytest -q` → 306 passed 그대로).
- 근거
  - `origin/research-r2-2026-11-04` 의 `reports/research-r2-2026-11-04/`
    - `REPORT.md`: H1 = 채택 후보, 한계
    - `STAGE0.md` §6·6b·6c: 보완 A1~A9, B1~B11
    - `SIM_NOTES.md` §1(하루 순서)·§3(구현 선택 I1~I25)
    - `sim_team.py`: A1 참조 구현
  - `origin/research-oss-2026-11-04` 의 `reports/research-oss-2026-11-04/REPORT.md` §6 G1, §7 H1, 7.5-3("최소 3개월 포워드 모의매매, 매달 A0 그림자 장부와 비교")
  - 지금 코드: `team.py`, `main.py`, `paper_wallet.py`, `markets.py`, `analyst.py`, `screener.py`, `order_runner.py`, `broker/`, `risk_guard.py`, `docs/kr-broker-design.md`, `docs/kr-fix-s0.md`
  - 할 일 목록(참고만, 구현하지 않음): `origin/docs-knowledge-2026-11-04:docs/개선-후보-2026-11-04.md`
- 사용자 결정 F1~F8 을 구체 규칙으로 옮겼다. 그 뒤 진행 담당이 정한 결정 Q1~Q13 과 검토 반영 결정은 §10 에 모았다. **본문은 §10 의 결정과 같은 규칙만 담는다.** 다르면 §10 이 맞고, 본문을 고쳐야 한다.

**1판 → 2판 바뀐 것** (검토 ID → 고친 곳)

| 검토 ID | 바뀐 것 | 위치 |
|---|---|---|
| X1 | 두 장부 모두 서킷 끔. 매일 "켜져 있었다면"을 그림자 사건으로만 남긴다(식·저장·보고·재현 비교). 서킷 켠 재현, 1판 점검 C16, 시험 T-CB 는 없앴다 | §2.6, §4 L20, §5 M5′ |
| X2 | 시작 규칙을 하나로 정했다: S 는 입금만, S+1 시가에 A1 은 먼저 전부 지수 → 그날 주문. L10 은 S 날 예외를 둔다. 지수 B&H 도 S+1 시가에서 시작한다. 재현 기준값도 같은 규칙으로 맞췄다(하네스 하위 클래스) | §2.5, §4 L10, §5 |
| I1·I2 | 점검을 두 등급으로 나눴다: 장부 논리 오류(L, 재시작) / 자료 문제·지연(D, 그날 멈추고 다시). 국내는 "행 없음"을 원본 거래량 0 행으로 거래정지와 가려낸다. L4·L15 는 그날 기록한 정지 목록으로 센다 | §2.2 ④, §2.4, §4 |
| I3 | 사전 등록에 넣은 것: 판정 창 S~S+62(시장별), 재시작 조건·최대 2번·마감 2027-06-30, 늦은 봉 상한, 팀장 폴백 표시, 코드 동결 | §2.2 |
| I4·I5·I6 | 추가한 것: 달력 점검(종료 코드 7, 2026→2027 연도 파일 경계 포함), 소급 수정(분할) 감지와 미리 정한 처리, LLM 은 "다음 장 시작 전"에만 부른다 | §2.2 ⑦, §2.3, §2.4, §4 D |
| I7·I8 | 판정 기록을 추가 전용 JSONL 로 바꾸고 장부보다 먼저 쓴다. 커밋 지점은 HEAD 하나, 잠금도 하나다. 진입점은 `python h1.py run`(team.py `--h1` 없음). 맥에서는 H1 전용 worktree·venv 를 쓴다 | §2.5, §3, §8 |
| I9·I10 | 장부에 `orders` 를 더했다. 현금은 절대 오차로 비교한다. K1 을 넓혔다. 재현은 실제 운영 시각으로 돈다. 국내 2018 창을 필수로 했고, sim_team 과의 합성 차등 재현을 더했다 | §3.5, §5 |
| I11·m1 | 미국 종목군은 S 날 목록으로 고정한다. 국내 매도세는 날짜별 표를 쓴다 | §2.1, §2.2 ⑥ |
| m3~m9 | 추가: `runs.jsonl`·`calendar.jsonl`·하루 기록 `marks`, 지문에 프롬프트·라이브러리 버전 포함, 새 시작은 명시 명령으로만, 보고서는 `state/h1/reports/` 에, 보고서 첫머리에 "A0 ≠ 운영 장부". 잘라 낸 것: 장부의 실현손익 칸(보고서 계산만 남김), `h1.py check`, 1판 M10, Q4 프롬프트 변경(보류) | 곳곳, §10 |

**2판 → 3판 바뀐 것** (2차 검토 ID → 고친 곳)

| 검토 ID | 바뀐 것 | 위치 |
|---|---|---|
| R2-1 (치명) | **장부 내용 지문**(`ledger_fingerprint`)을 따로 정의했다. 실행 메타 칸(`h1` 머리, 하루 기록의 `run_at`·`mode`·`late`·`code_hash`·`env`)을 빼고 정렬 JSON 의 sha256 을 낸다. 거짓 양성 규칙 ④, 코드 동결 ⑥, `replay_pass`, `errors.jsonl` 이 모두 이것을 쓴다. 라이브러리 올림은 ⑥-(i) 과 같은 조건으로 허용한다 | §2.2 ④⑥, §3.3, §3.7, §5.6 |
| R2-2 | 재현·시험은 "지금 재현 중인 지문"을 허용 목록으로 넘겨 L22 를 본다(관문 실행에서만 `replay_pass` 를 본다). M8 의 W 허용 목록에 W3(`replay_no_llm`)를 넣었다 | §4 L22, §5.4 M8 |
| R2-3 | 상장폐지: `corp-action --delist` 로 등록한 종목은 D2·D3·D6 대상에서 빠진다. 가격은 명령이 적은 마지막 거래 종가. 정리 체결은 L3·L4·L6·L14 의 예외이고, 대신 새 점검 L23 이 등록 내용과 같은지 본다 | §2.2 ⑦-4, §2.3, §4 L23 |
| R2-4 | ⑦-5 **정정 확정** 길(장부 그대로, D6 비교 기준만 새 값으로)을 사전 등록했다. 정지일 `marks` 비교는 "그 날짜 이하 마지막 확정 종가" | §2.2 ⑦, §4 D6 |
| R2-5 | 세율 줄 추가는 `h1.py amend-rules` 명령으로만 한다(잠금 아래 `meta.rules` 갱신·`changes.jsonl`). 규칙 상수 불일치는 종료 코드 3 하나로, L22 에서는 뺐다 | §2.2 ⑥, §2.3 준비 4, §4 L22 |
| R2-6~R2-17 | W3 에서 `screener.BRAINS` 도 바꿈(`scan_frames(brains=)`), 멱등 대상 파일 한정, `calendar.jsonl` 에 날짜 목록 전체, 준비 순서 5→7→6→8·확인용 종목 실패는 W5, 백업 열쇠 = HEAD `run_id`·corp-action 도 커밋 순서·끝나지 않은 start 다시 하기, 파일 손상 = L24, ⑩ 에 상수 추가·`h1_replay.py`·`h1_report.py` 를 CODE_FILES 에, 시가 없는 확정 행 = D3, LLM 호출 직전 시각 재확인, v1 결정 번호 표기, 머리 숫자 | 곳곳, §10.2 |

**설계하면서 직접 확인한 것**
- 연구 브랜치는 `git archive` 로 scratch 폴더에 풀어 `python -I` 로 읽기만 했다. 코드·연구 브랜치는 고치지 않았다.
- `sim_team.run(Config(period=("2026-06-01","2026-11-03"), interest=False, ...))` 처럼 **기간을 튜플로 주면 그대로 돈다.** sim_team 을 복사하거나 고칠 필요가 없다.
- 재현 창(2026-06-01 ~ 2026-11-03)
  - 미국 SPY 109봉, 국내 KS200 105봉. 창 안에 국내 정지 행·빠진 종목 봉이 0개다.
  - 같은 창에서 서킷을 켜면 국내 A1 은 세 트레이너가 **6번째 거래일(2026-06-08)에 모두 영구 정지**된다 → Q1 끔.
  - (검토 probe1) **그림자 서킷 첫 발동일 == R2 `cb="current"` 사건 날짜.** 4조합(미·국 × A0·A1) 모두 같다.
  - (2차 검토 p1) 채택한 시작 규칙(S 입금만 → S+1 시가 a→c→d→e)은 R2 원래(S 시가 전부 지수)와 A1 체결 열쇠가 미국 25개·국내 20개·2018 국내 창 14개 다르다(1차 probe1 의 Q8Sim(c→d→e) 기준으로는 21·23) → 재현 기준값도 운영 시작 규칙으로 맞춘다.
- 국내 정지
  - (검토 probe2·3) 2015~2026 전체에서 정지를 가로질러 기다린 **대기 주문은 0건**, 정지를 가로질러 **보유한 거래는 4건**이다.
  - (직접 확인) 국내 2018-03-01~12-31 창(운영 시작 규칙)
    - 장부마다 정지를 가로지른 보유가 2건 있다: 005930 2018-04-30~05-03, 207940 2018-11-15~12-10.
    - 서킷 사건(켰다면)도 있다.
    - 창 시작 때 70봉이 안 되는 종목이 없다.
- (검토 probe4) A1 쓸어 담기 뒤 남는 현금(1e-8 정도)은 부동소수점 1ulp 차이에도 상대값이 1.2e-4 바뀐다 → 현금은 절대 오차로 비교한다.

---

## 용어 (처음 보는 사람용)

| 말 | 뜻 |
|---|---|
| 장부(ledger) | 가짜 지갑 + 보유 종목 + 대기 주문 + 기록을 적은 파일. 트레이너 한 명당 하나. 진짜 돈은 0원 |
| **A1 (= H1)** | 트레이너가 주식에 안 쓴 돈을 **지수**(미국 SPY, 국내 KOSPI 200 가격지수 KS200)로 둔다. 주식을 살 때 모자란 만큼만 지수를 판다 |
| **A0 (그림자)** | 쉬는 돈을 **현금**으로 두는 비교용 장부. R2 의 A0 규칙이다. **운영 team.py 장부가 아니다**(§1.1 표) |
| 대기 자산 | A1 에서 쉬는 돈을 넣어 두는 곳 = SPY / KS200 |
| 확정 봉 | 장이 끝나고 값이 확정된 하루치 시세(`main.confirmed_bars`). 미국 16:15 ET, 국내 종목 16:00 KST, KS200 은 22:30 KST |
| 시작 봉 S | `h1.py start` 때의 마지막 확정 봉. S 에는 입금만 하고, 매매는 S 다음 봉(S+1)부터 |
| 판정 창 | S 부터 63개 확정 봉(S … S+62). 운영 기준을 이 안에서만 본다 |
| 소수 단위 | 지수는 0.123456단위처럼 소수로 산다(남는 돈이 1 미만이 되게). 주식은 정수 주 |
| 그림자 서킷 | 서킷 브레이커가 켜져 있었다면 그날 걸렸을지를 계산만 해서 적는 것. 장부는 바뀌지 않는다 |
| 팀장 판정 | `analyst.py` 가 `claude -p` 로 받아 오는 buy/hold/veto·확신도. 없으면 규칙 그대로(폴백) |
| 장부 논리 오류 (L) | 장부 계산·순서·기록이 규칙과 다른 것. 고치고 **재시작**한다 |
| 자료 문제 (D) | 시세를 못 받음·늦음·나중에 고쳐짐·달력이 줄어듦. 그날만 멈추고 **다음 실행이 다시** 한다 |
| 커밋 지점(HEAD) | 장부 6개를 다 쓴 뒤 마지막에 바꾸는 `HEAD.json`. 이 파일이 가리키는 상태만 "저장된 것"이다 |
| 장부 내용 지문 | 장부에서 "언제·어떤 코드로 돌렸나" 같은 실행 메모를 뺀 **매매 내용만**의 sha256(§3.3 `ledger_fingerprint`). 코드를 고쳐도 매매가 같으면 같은 값이 나온다 |
| 재현(replay) | 과거 데이터로 새 코드를 돌려 R2 `sim_team.py` 와 체결 하나하나가 같은지 맞춰 보는 시험(§5) |
| worktree | 한 git 저장소에서 폴더를 하나 더 만들어 다른 커밋을 꺼내 두는 기능. H1 은 운영 폴더와 따로 돈다 |

---

## 0. 한눈에

| 무엇 | 어떻게 |
|---|---|
| 시작 | `python h1.py start --market us\|kr` (시장마다 한 번, 명시 명령). S 에는 입금만 |
| 매일 | `python h1.py run --market us\|kr` → A0·A1 을 같은 봉·같은 스크리너 결과·같은 팀장 판정으로 한 번에. **team.py 에는 `--h1` 이 없다** |
| 장부 | `state/h1/<market>/<A0\|A1>/team_<트레이너>.json` 6개 + 커밋 지점 `state/h1/<market>/HEAD.json`. 기존 `state/` 파일은 읽지도 쓰지도 않는다 |
| 시작 자금 | 미국 $100,000, 국내 ₩100,000,000. 60/30/10, 종목상한·MAX_POSITIONS·확신도 규칙은 team.py 그대로 |
| 서킷 | **두 장부 모두 끔.** 매일 "켜져 있었다면" 걸렸을지를 그림자 사건으로 기록만 한다 |
| A1 규칙 | R2 `sim_team.py` A1 그대로: 같은 시가에 주식 매도 → 주식 매수(모자란 만큼만 지수 매도) → 남은 현금 ≥ 1 이면 지수. 현금+지수로도 모자라면 지수를 팔지 않고 보류. **첫날 전부 지수는 S+1 시가**(그 시가에 먼저 전부 지수로 바꾼 뒤 그날 주문) |
| 팀장 | 두 장부가 같은 (날짜, 트레이너, 종목)에 같은 판정을 쓴다. 판정 기록 `state/h1/analyst_cache.jsonl`(추가만, 장부보다 먼저 씀). 프롬프트는 운영과 같다. LLM 은 다음 장 시작 전에만 부른다 |
| 종목군 | 미국은 S 날 40종목 목록·순서로 고정, 국내는 `KR_UNIVERSE` 32종목 |
| 점검 | 장부 논리 오류(L) → 그날 저장 안 함, 고치고 재시작 / 자료 문제(D) → 그날 저장 안 함, 다음 실행이 다시 |
| 재현 | 2026-06~11 미·국 + **2018 국내**(정지 보유 포함) + 합성 차등. **운영 시작 규칙으로 맞춘** sim_team 과 비교 |
| 보고서 | `python h1_report.py --market us\|kr` → `state/h1/reports/<market>-<YYYY-MM>.md` |
| 맥 | H1 전용 git worktree + 전용 venv. launchd 는 `h1.py` 를 부른다 |
| 운영 쪽 | team.py 는 `h1=None` 이면 동작이 바이트까지 같다. order_runner 는 `state/h1` 을 못 읽는다 |

---

## 1. 목적과 범위

### 1.1 목적
- R2 백테스트에서 H1(쉬는 돈을 지수에)은 채택 후보가 됐다(미국 기준 1~3 통과, 국내 같은 방향). 하지만 R2 는 과거 데이터·연구용 시뮬레이터였다.
- 이 작업은 **team.py 엔진 위에서 H1 장부가 63거래일 동안 장부 오류 없이 매일 돌아가는지** 확인한다.
- 같은 규칙에서 쉬는 돈만 현금인 그림자 장부(A0)를 같이 쌓아 매달 숫자를 **기록**한다. 판정은 하지 않는다(§2.2 ③).

**A0 는 운영 장부가 아니다** — 보고서 숫자를 운영 `state/team_*.json` 과 견주면 안 된다.

| | 운영 team.py 장부 | H1 A0 (그림자) | H1 A1 |
|---|---|---|---|
| 쉬는 돈 | 현금 | 현금 | 지수 |
| 총액 | $10,000 / ₩10,000,000 | $100,000 / ₩100,000,000 | 같음 |
| 서킷 | 켬(영구 정지) | 끔(그림자만) | 끔(그림자만) |
| 같은 시가의 순서 | 대기 목록 순서 | 매도 먼저 | 매도 먼저 |
| 저장 | 변화가 있는 날만 | 매일 | 매일 |
| 팀장 판정 글자 | 그대로(`" VETO"` 는 veto 아님) | 정리 | 정리 |
| 미국 종목군 | 매일 S&P500 섞기 | S 날 목록 고정 | 같음 |
| 국내 매도세 | 0.20% 고정 | 날짜별 표 | 같음 |
| 첫 매매 | 시작 다음 봉 | S+1 | S+1(먼저 전부 지수) |

### 1.2 범위 안
- `h1.py`(시작·매일·재시작·상태), team.py `run_trainer` 갈고리, 대기 자산 소수 단위 보유·저장·표시
- 팀장 판정 기록(나중에 채점할 수 있는 형태, 할 일 목록 2번), 판정 글자 정리(§3-2)
- 하루 장부 점검(L/D/W 등급), 그림자 서킷, 월간 보고서(A0 현금 이자 계산값·실현손익 참고값 포함), 재현, 오프라인 시험
- H1 경로에서만 하는 것
  - 밀린 봉 따라잡기(할 일 7번)
  - 보유 종목 시세 실패 시 멈춤(1번)
  - 깨진 장부를 새 지갑으로 덮지 않기(3번)
  - 미국 종목군 고정(11번)
  - 사유 글 자르지 않기(9번)

### 1.3 범위 밖 (이번에 하지 않음)
- **진짜 주문**: 증권사(KIS) 주문, 069500·SPY 실제 매수. 장부만 쓴다(F4·F6)
- **소수점 실제 주문**: 지수 소수 단위는 장부 계산일 뿐이다
- **H2~H4**: 10개월선 필터, 단계적 서킷, 성과 기반 재배분
- **전략 숫자**: 익절·손절·RSI·상한·60/30/10
- **운영 장부 전환**: 기존 `state/team_*.json`·`state/kr/` 장부는 그대로. 63거래일 뒤 "기본 장부로 할지 검토"만 한다
- **H1 장부의 서킷**: 그림자로만 계산한다(Q1). v1 결정 D6(서킷 재개 규칙)은 원래 저장소 공동작업자와 합의할 일(§4 자료 등급 D6 와 다른 것)
- **S0-3**: 국내 거래량 분할 미반영
- **엔진 합치기**(할 일 14번): 3개월 뒤
- **장부에 배당·현금 이자 넣기**(15번): 이자는 보고서에서 계산만(F8)
- **팀장 프롬프트 변경**(Q4 보류): 날짜·시장·종목명을 넣는 일은 나중에
- **자동 분할 조정**: 프로그램이 스스로 고치지 않는다. 사람이 미리 정한 규칙 중 하나를 고른다(§2.2 ⑦)
- **장부의 실현손익·취득가 칸**: 보고서가 `fills` 로 계산만 한다
- 원래 저장소(kjh3291)에 PR·이슈

---

## 2. 규칙

### 2.1 F1~F8 → 구체 규칙

| ID | 결정 | 구체 규칙 |
|---|---|---|
| **F1** 장부 | `state/h1/<market>/<A0\|A1>/team_<trainer>.json` | 시장 `us`·`kr` × 장부 `A0`·`A1` × 트레이너 3명 = 시장마다 6개.<br>H1 코드는 `state/h1/` 밖을 열지 않는다. 경로 함수는 결과가 `state/h1/` 아래인지 확인하고, 아니면 예외를 던진다.<br>H1 경로에서는 `team._load`·`team._save`·`main.load_state_file` 을 부르지 않는다. 부르면 기존 장부를 읽거나 "예전 형식"으로 보관해 버린다.<br>맥에서는 H1 이 전용 worktree 에서 돌아 `state/` 폴더 자체가 운영과 따로다(§8) |
| **F2** 시작 | 미국 $100,000, 국내 ₩100,000,000 | 트레이너 몫 = 총액 × 60/30/10(`main.CONFIG["배분비율"]`).<br>종목상한 30/20/15% 는 **시작 예산** 기준(`shares_within_cap(start_cash, cap, 시가, fee, slip)`).<br>`team.MAX_POSITIONS`(5, 매수 대기 포함)·`team.CONV_MIN`(0.5)·`team.keep_candidate`·`team.to_conviction` 을 import 해서 쓴다.<br>수수료·슬리피지는 `markets.MARKETS[시장]` 값. 국내 주식 매도세는 **체결일 기준 날짜별 표**(STAGE0 §1.2, Q9).<br>**서킷: 장부에는 절대 안 걸리는 `CircuitBreaker(inf, inf)` 를 넘긴다(Q1).** 지금 규칙(누적 −10%·하루 −7%)은 그림자로만 계산한다(§2.6) |
| **F3** A1 규칙 | R2 `sim_team.py` A1 | 같은 시가의 식·순서·여유값이 `sim_team.TeamSim._open`·`_fill_buy`·`_raise_cash`·`_sweep_to_index`·`_idx_net_per_unit` 와 같다(§2.3).<br>신호는 봉 t 종가, 체결은 봉 t+1 시가. **시작은 Q8**: S 는 입금만, S+1 시가에 A1 은 먼저 전부 지수(§2.5).<br>지수는 소수 단위(반올림 금지), 주식은 정수 주. 소수 단위는 JSON 저장·읽기에서 비트까지 그대로 살고, 화면에는 소수 6자리로 찍는다. `paper_wallet.Holding.shares` 표기를 `float` 로 바꾼다 |
| **F4** 대기 자산 | 미국 SPY, 국내 KS200 | 대기 자산 코드 = `markets.MARKETS[시장].benchmark`. 시세는 `main.load_benchmark(team.START, 시장)` 그대로(국내는 22:30 KST 확정 규칙).<br>1단위 = 지수 1포인트(국내 원, 미국 SPY 1주 가격). 지수 다리 비용 = 그 시장 수수료 + 슬리피지, 국내 지수 매도세는 0(STAGE0 A3).<br>ETF 운용보수는 넣지 않는다(한계로 표시). 실제 주문은 범위 밖 |
| **F5** 팀장 | 같은 판정, 판정 기록 | 두 장부는 같은 (시장, 날짜, 트레이너, 종목)에 같은 판정을 쓴다.<br>판정 기록은 **`state/h1/analyst_cache.jsonl`**(F5 의 `.json` 을 추가 전용 JSONL 로 바꿈, 검토 I7). 열쇠는 `"<시장>\|<날짜>\|<트레이너>\|<종목>"`(Q12).<br>기록에 없는 종목만 묻는다. LLM 이 없거나 늦으면 규칙 폴백이고, 그 사실도 기록한다.<br>판정은 정리한 값과 원래 값을 같이 남긴다. 기록은 한 번 쓰면 고치지도 지우지도 않는다. **장부보다 먼저** 디스크에 쓴다(§3.6) |
| **F6** 주문 없음 | order_runner 는 `state/h1` 못 읽음 | `order_runner.state_path` 는 `state/team_*.json`·`state/kr/team_*.json` 만 만든다(`--market` 은 `us`·`kr`). H1 코드는 `order_runner`·`broker` 를 import 하지 않는다. 시험으로 확인한다(§6 T-F6). order_runner 는 고치지 않는다 |
| **F7** 실행 | 한 번에 두 장부, 같은 스크리너, 멱등 | **진입점은 `python h1.py run --market us\|kr`** 이다(검토 I8: team.py `--h1` 은 그 기능이 없는 옛 코드가 조용히 무시하고 운영 장부를 돌리므로 두지 않음).<br>봉마다 `screener.scan_frames(...)` 를 한 번 부르고 두 장부가 같이 쓴다. 같은 확정 봉으로 다시 돌리면 **장부 6개·`meta.json`·`HEAD.json`·`backup/`·판정 기록**이 바뀌지 않고, 팀장도 다시 부르지 않는다(실행 일지 `runs.jsonl`·`calendar.jsonl` 에는 줄이 더해진다, 2차 검토 R2-7) |
| **F8** 월간 보고서 | `python h1_report.py --market us\|kr` | 출력은 **`state/h1/reports/<market>-<YYYY-MM>.md`**(F8 의 `reports/h1-forward/` 에서 바꿈: 운영 체크아웃의 추적 폴더를 더럽히지 않게, 검토 m8). 사람이 골라 커밋한다. 내용은 §3.8.<br>"A0 현금 + 단기금리 이자"는 계산만 한다. 금리 규칙: 미국 FRED `DTB3` 전 거래일 값(STAGE0-A1), 국내 FRED `IR3TIB01KRM156N` 전달 값(STAGE0-A2), 거래일마다 연%/100/252(B4) |

### 2.2 포워드 사전 등록 (`h1.py start` 전에 이 문서의 최종판(지금 3판)을 커밋한다)

> 운영 중에는 이 절을 고치지 않는다. 고쳐야 하면 이유를 커밋으로 남기고, 규칙이 바뀌면 ⑤ 대로 재시작한다. `h1.py start` 는 이 문서의 sha256 을 `meta.json` 에 적는다.

**① 판정 창**
- 시장마다 따로 정한다. 시작 봉 S = `h1.py start --market m` 때의 마지막 확정 봉(대기 자산 달력 기준).
- **판정 창 = S 부터 63개 확정 봉**(S, S+1, …, S+62). S 는 입금만 하는 날이지만 창에 넣는다.
- S+62 를 처리한 직후 **한 번** 판정한다(`h1_report.py --market m --final`). 그 뒤 봉은 "연장 기록"으로 쌓기만 하고 판정에 쓰지 않는다. 창을 늘리거나 줄이지 않는다.
- **미국·국내는 각각 판정한다.** 통과한 시장만 "그 시장에서 H1 을 기본 장부로 할지 검토"로 넘어간다. 다른 시장의 결과를 기다리지 않고, 다른 시장의 실패가 통과를 취소하지도 않는다.

**② 운영 기준** — 판정 창 안에서 **모두** 맞아야 통과
1. **장부 논리 오류(§4 L 등급) 0건.** 특히: 현금·단위 음수(L1·L2), 체결가 ≠ 그날 시가(L3·L4), 중복 주문(L5·L14), 국내 거래정지일 체결(L6).
2. **빠진 날 0.**
   - 창의 63봉 모두 두 장부에 하루 기록이 있고, 두 장부의 날짜 목록이 같다(L16).
   - 늦게 처리한 봉(§2.5)이 **창 전체 10봉 이하**.
   - 한 번에 따라잡은 봉이 **5봉 이하**.
3. **재현을 통과한 코드·환경만 돌았다.**
   - 창의 모든 하루 기록의 `code_hash`·`env` 가 `state/h1/replay_pass.json` 에 있다.
   - `runs.jsonl` 에 다른 지문으로 봉을 처리한 실행이 없다.

**③ 수익률은 기록만 한다.**
- A1−A0, 지수 대비, MDD, 그림자 서킷, 팀장 성적은 보고서에 숫자로 남긴다. 하지만 **판정에도, 재시작 사유에도 쓰지 않는다**(3개월은 너무 짧다).
- 보고서 첫머리에 이 문장을 고정으로 찍는다.

**④ 점검 등급과 처리**

| 등급 | 무엇 | 그날 | 기간 |
|---|---|---|---|
| **장부 논리 오류 (L)** | 장부 계산·순서·기록이 규칙과 다름, 또는 장부 파일 손상(§4 L1~L24) | 종료 코드 2. 그 봉은 저장 안 함. `errors.jsonl` 에 문제와 **저장하려던 장부 6개의 내용 지문**(§3.3 `ledger_fingerprint`)을 남김 | 운영 기준 ②-1 위반 → 고치고 재현 통과 → 두 장부 재시작(⑤) |
| **자료 문제·지연 (D)** | 시세 못 받음·늦음·소급 수정·달력 줄어듦/구멍(§4 D1~D7) | 종료 코드 4(기준 지수 늦음 D7 은 7). 그 봉은 저장 안 함. 다음 실행이 다시 | **재시작 아님**, 횟수만 보고. 단, 이 때문에 ②-2 의 늦은 봉 상한을 넘으면 창 실패 → 재시작 |
| 경고 (W) | 늦은 봉·정지·팀장 폴백·종목군 일부 시세 없음 | 멈추지 않음 | 보고만 |

- **점검 함수의 거짓 양성.** L 오류가 나중에 점검 함수 자체의 잘못으로 밝혀질 수 있다. 다음 둘이 **모두** 맞을 때만 재시작하지 않는다.
  - (가) 고친 코드로 돌린 재현 장부의 **내용 지문**(필수 창 W1·W2 의 장부 전부)이 직전 통과 때 `replay_pass.json` 에 적은 값과 같다. 즉 점검만 바뀌고 장부 계산은 안 바뀌었다.
  - (나) 멈췄던 봉을 고친 코드로 처리해 나온 장부 6개의 **내용 지문**이 `errors.jsonl` 에 남긴 "저장하려던 내용 지문"과 같다. 내용 지문은 `late`·`mode`·`run_at`·`code_hash`·`env` 를 빼고 계산하므로 늦게 다시 처리한 차이는 걸리지 않는다. 판정 기록 줄은 그때 이미 써 두었으므로 같은 판정을 다시 쓴다.
  - 그동안 처리하지 못한 봉은 늦은 봉으로 센다. 둘 중 하나라도 아니면 재시작한다.
  - **기록은 프로그램이 자동으로 한다**(사람이 판단하지 않음, 2c 검토 R-4): 고친 코드의 `h1.py run` 이 errors.jsonl 에 L 기록이 있는 봉을 다시 처리할 때 (가)(나)를 확인한다. (가) = `replay_pass.json` 에서 옛 code_hash 와 지금 code_hash 의 통과 줄이 모두 있고 `ledger_fingerprints` 가 같음. (나) = 그 봉 결과 내용 지문 == errors.jsonl 의 지문. 둘 다 맞으면 커밋 전에 `changes.jsonl` 에 `kind: "false_positive"` 를 남기고, 보고서 ②-1 은 그 L 오류를 빼고 센다(뺀 건수는 따로 보임). 안 맞으면 기록하지 않고 그 L 오류는 그대로 남는다.

**⑤ 재시작**
- 재시작하는 경우는 셋뿐이다.
  - (a) 장부 논리 오류(L1~L24, 장부 파일 손상 L24 포함)
  - (b) ②-2 늦은 봉 상한 초과(창 실패)
  - (c) 커밋된 규칙 변경: ⑥ 이 허용하지 않는 코드·환경 변경, 그리고 ⑦-3 의 기업 행위
- 수익률·MDD·A1−A0·그림자 서킷은 재시작 사유가 아니다.
- 방법: `python h1.py restart --market m --reason "..."` → 그 시장 폴더를 보관 폴더로 옮김 → `python h1.py start --market m` 으로 새 S.
  - 63봉은 새 S 부터 다시 센다.
  - 판정 기록과 고정 종목군 파일(첫 S 의 목록)은 그대로 쓴다. 재시작으로 종목군을 다시 고를 수 없다.
- **상한: 시장마다 재시작은 최대 2번**(판정 창 최대 3개).
  - 재시작 수는 어디서나(status·`restart` 상한·보고서) `h1.restart_info` 한 함수로 센다: `meta.restart_no`·restarts.jsonl(done 또는 archive 있음)·archive 폴더 수 중 가장 큰 값. 끝나지 않은 `moving` 은 따로 보인다.
- **마감: 2027-06-30.** 그때까지 깨끗한 창(②를 다 지킨 63봉)이 끝나지 않았거나, 재시작이 2번을 넘게 필요하면 그 시장은 **"H1 포워드 실패(운영 기준 미충족)"** 로 보고하고 멈춘다.

**⑥ 코드 동결** — 판정 창 동안 `CODE_FILES`(§3.3, `prompts/*.md`·`h1_replay.py`·`h1_report.py` 포함)와 라이브러리 버전(`meta.env`)을 바꾸지 않는다. 허용하는 것은 아래 둘뿐이다(각각 `state/h1/changes.jsonl` 에 적고, 커밋하고, 재현을 다시 통과해야 함).
- (i) **자료 문제 고침과 라이브러리 올림**: 시세 받기·형식 읽기·재시도 같은 코드 고침, 그리고 `ENV_PACKAGES` 버전 올림(예: FinanceDataReader 출처가 깨졌을 때). 조건: 고친 코드·환경으로 돌린 재현 장부의 **내용 지문**(필수 창 W1·W2 의 장부 전부)이 직전 통과 때 `replay_pass.json` 값과 **같아야** 한다 = 장부 계산이 안 바뀐 것이 객관적으로 확인된 것만. `code_hash`·`env` 는 당연히 바뀌므로 비교하지 않는다. 라이브러리 올림이 지난 시세를 바꾸면 D6 이 잡는다.
- (ii) **국내 매도세 표에 줄 추가**: 법령 1차 출처로 확인한 새 세율로, 시행일이 마지막 처리 봉보다 뒤인 것. 지난 체결은 그대로다. 순서: 표 상수에 줄을 더한 코드를 커밋 → 재현 통과((i) 과 같은 조건: 재현 창은 2018·2026 이라 새 줄이 쓰이지 않아 **내용 지문**이 같아야 한다) → `python h1.py amend-rules --market kr --source URL` 이 잠금 아래에서 "앞줄은 그대로이고 뒤에 줄만 더해졌는지"를 확인한 뒤 `meta.rules` 를 고치고 `changes.jsonl` 에 적는다. 그 전까지 `run` 은 종료 코드 3(규칙 다름)으로 아무것도 저장하지 않는다.
- 그 밖의 변경은 규칙 변경 → ⑤-c 재시작.

**⑦ 분할·합병·상장폐지** — **프로그램은 스스로 고치지 않는다.**
- 매일 D6(소급 수정 감지) → 자료 문제로 멈추고 알린다.
- 사람이 1차 출처(거래소 공시·회사 발표)로 원인을 확인한 뒤, 아래 중 **하나만** 고른다. 고른 것·출처·시각은 `state/h1/<m>/corp_actions.jsonl` 과 `changes.jsonl` 에 남긴다.
- `corp-action` 명령은 `run` 과 같은 잠금·커밋 순서(백업 → 장부 6개 → `HEAD.json`, §2.5)를 거친다. 장부를 바꾸지 않는 4·5 도 장부의 `corp_actions` 칸에 한 줄을 더하므로 같은 순서로 쓴다.
  1. **제공처 자료 실수**: 제공처가 틀린 값을 냈다가 원래 값으로 돌아오기를 기다린다(자료 문제, ②-2 상한 적용).
  2. **순수 액면분할·병합** (비율 r = 새 주식 수 ÷ 옛 주식 수, `2`·`0.5`·`1/3`·`3:1` 처럼 분수로도): `python h1.py corp-action --market m --code X --split r --date D --source URL`
     - D = 새 주식 수로 거래되는 첫 날(효력일). D 가 장부 `last_date` 보다 뒤가 아니면 거절(그때는 정정 확정 또는 ⑦-3).
     - 지금 D6 이 그 종목에 같은 비율 r 의 "분할 의심"을 보고 있을 때만, 그리고 같은 종목·효력일 기록이 없을 때만 받는다(두 번 적용 막기, 2b-2 검토 C-2·C-9).
     - 두 장부에 똑같이: 주식 수 × r, 매수가·평균가 ÷ r. 대기 주문은 그대로다.
     - r 을 곱한 주식 수가 정수가 아니면 3번으로 간다.
     - 평가액은 그 순간 그대로다. D6 는 **분할을 장부에 적용하기 전(`applied_after` 이하)에 쓴 기록 가격**을 ÷ r 해서 비교한다(효력일 기준으로 나누면 밀린 봉을 따라잡을 때 거짓 D6 이 남, 2b-2 구현).
  3. **그 밖**(인적분할·주식 교환·현금 인수 등 1·2·4 로 안 되는 것): 규칙 변경 → ⑤-c 재시작.
  4. **상장폐지**(더 거래되지 않음): `python h1.py corp-action --market m --code X --delist --last-date D --last-close P --source URL`
     - `--last-date`·`--last-close` 는 1차 출처의 마지막 거래일·종가다. `--last-close` 를 비우면 장부의 그 종목 마지막 `marks` 값을 쓴다. 둘 다 `corp_actions` 에 적는다.
     - 등록한 뒤에는 그 종목을 준비 7 의 시세 받기(D2)·준비 8 의 소급 수정(D6)·봉 0 의 자료 준비(D3) 대상에서 **뺀다**(시세를 못 받아도 멈추지 않게).
     - D 보다 뒤인 다음 처리 봉의 시가 단계 맨 앞(a′)에서 두 장부 모두 그 종목 전부를 P 로 판 것으로 적는다. 매도 비용(그 봉 날짜의 세율)을 뺀다. 그 종목의 대기 주문은 `dropped`(why `"delist"`)로 지운다. 체결 기록 `purpose="delist"`, `order_id=None`.
     - 이 체결은 L3·L4·L6·L14 의 예외이고, 대신 L23 이 "등록한 종목·가격·전량·비용식과 같은지"를 본다.
     - A1 은 그 돈이 같은 시가의 e 단계에서 지수로 간다.
  5. **정정 확정**(제공처가 지난 값을 고쳤고, 1차 출처로 보니 **새 값이 맞음**. 분할·병합이 아님): `python h1.py corp-action --market m --code X --accept-correction --source URL`
     - 장부(체결·평가·보유)는 **그대로 둔다**. 이미 처리한 봉은 다시 처리하지 않는다(§2.5 멱등).
     - 그 종목에서 D6 이 지금 다르다고 본 (날짜, 칸, 옛 값, 새 값)을 모두 `corp_actions` 에 적고, 그 뒤 D6 은 그 칸들을 새 값과 비교한다.
     - 재시작 아님. 보고서에 횟수와 목록을 적는다.

**⑧ 팀장 폴백 표시** — 창의 판정 기록 중 폴백(`status != "ok"`)이 **20% 를 넘으면** 보고서에 "팀장 판정 대표성 없음"을 찍는다. 실패 사유는 아니다(팀장은 판정 대상이 아님). 늦은 봉 폴백도 센다.

**⑨ 판정에 쓰지 않는 것**: 수익률·MDD·A1−A0·지수 대비·그림자 서킷·팀장 성적. 판정 기록은 나중 채점(G4)용으로 쌓기만 한다.

**⑩ 고정 값** (`meta.json` 의 `rules` 에 적고, 매 실행 코드 상수와 비교 → 다르면 종료 코드 3)
- 총액(미국 100,000·국내 100,000,000), 배분 60/30/10, 상한 30/20/15%, MAX_POSITIONS 5, CONV_MIN 0.5
- 수수료·슬리피지(`markets`), 국내 매도세 표(⑥-ii 로 줄 추가만 허용), 지수 매도세 0
- 장부 서킷 = 끔(inf), 그림자 서킷 = (0.10, 0.07)
- 쓸어 담기 문턱 1, 여유 1e-9, 줄임 1e-12 → 1e-9 → 1e-6
- 대기 자산 SPY/KS200, 종목군 N=40 (종목군 **파일 지문**은 여기서 비교하지 않고 L22 로 본다 → 종료 코드 2, 단계 3 확인)
- 늦은 봉 상한 5·10, 판정 창 63, 재시작 2, 마감 2027-06-30, 폴백 표시 20%
- 소급 수정 허용 오차 1e-6·비교 날 수 5(`RETRO_TOL`·`RETRO_DAYS`), 달력 확인용 대형주(미국 AAPL·MSFT, 국내 005930·000660), 달력 구멍 비율 0.5(D5)
- 다음 장 시작 `NEXT_OPEN`(미국 09:30 America/New_York, 국내 09:00 Asia/Seoul)
- 점검 허용 오차 `EPS_CASH` 1e-6·`EPS_REL` 1e-9, 장부 내용 지문 판 `FINGERPRINT_VERSION`
- 규칙 상수가 다르면 종료 코드 3 하나로 처리한다(아무것도 저장 안 함). 세율 줄 추가만 `amend-rules` 로 `meta.rules` 를 고칠 수 있다(⑥-ii)

### 2.3 하루 순서 (A0·A1) — `SIM_NOTES.md` §1 과 같은 모양

**준비** (명령 한 번에 한 번, 시장별. `start` 도 같은 순서이고 4 의 "장부 없음"만 다르다)

1. **잠금**: `state/h1/h1.lock` 을 잡는다. 최대 30분 기다리고, 그래도 못 잡으면 종료 코드 5. 모든 명령(start·run·restart·corp-action·amend-rules·status·report, 재현의 마지막 쓰기)이 같은 잠금을 쓴다.
2. **기록 시작**: `state/h1/runs.jsonl` 에 시작 줄(명령·시장·시각·코드 지문·env)을 적는다. 끝날 때 종료 코드·처리한 봉을 적는다. 관문 거절도 적는다.
3. **관문**: 코드 지문(§3.3 `code_hash`)과 `env`(python·pandas·numpy·ta·FinanceDataReader 버전)가 `replay_pass.json` 에 함께 있는지 본다. 없으면 종료 코드 3(②-3).
4. **장부 읽기**(엄격)
   - `HEAD.json` → 장부 6개 + `meta.json` + 판정 기록(§3.6). 장부가 없으면 `run` 은 종료 코드 8(`start` 필요).
   - 6개 파일 sha256 ≠ HEAD 이면 `backup/<HEAD 의 run_id>/` 로 되살린다(§2.5). 그것도 안 맞으면 L24(장부 파일 손상) → 종료 코드 2.
   - `meta.rules` ≠ 지금 상수이면 종료 코드 3(아무것도 저장 안 함. 세율 줄 추가는 ⑥-ii 의 `amend-rules`).
   - 실행 순서는 아래 번호 그대로가 아니라 **5 → 7 → 6 → 8 → 9** 다(6·8 이 7 에서 받은 종목 시세를 쓴다, 2차 검토 R2-9). 번호는 1판부터 쓰던 이름이라 그대로 둔다.
5. **대기 자산 시세**: `main.load_benchmark(team.START, m)`. 실패(None)면 D1 → 종료 코드 4. 이 시세의 날짜가 **H1 달력**이다.
7. **종목 시세**(5 다음에 한다): 고정 종목군(§3.7 `universe/<m>.json`)과 두 장부의 보유·대기 종목, 그리고 확인용 대형주(`CAL_PROBE`)를 **한 번씩만** 받는다(§3.3 `fetch`: 원본 → `main.confirmed_bars` → 확정 시세 + 국내 원본 거래량 0 날짜).
   - 보유·대기 종목을 못 받으면 D2 → 종료 코드 4(할 일 1번). **`--delist` 로 등록한 종목은 받지 않는다**(⑦-4).
   - 종목군에만 있는 종목을 못 받으면 W4 로 남기고 건너뛴다(스크리너와 같음).
   - 확인용 대형주를 못 받으면 W5("D7 판단 불가")로 남기고 계속한다.
   - 받은 시세는 **엄격한 cache** 로 넘긴다: 없는 종목을 찾으면 인터넷으로 받지 않고 예외(검토 m6).
6. **달력 점검**(7 다음에 한다, §4 D4·D5·D7)
   - 새 달력 ⊇ 이미 처리한 날짜(`calendar.jsonl` 의 마지막 줄 날짜 목록과 장부 하루 기록).
   - 새로 처리할 구간에 구멍이 없다(D5: 7 에서 받은 종목군의 절반 이상이 거래한 날이 달력에 없으면 구멍).
   - 확인용 대형주의 최신 확정 봉 ≤ 달력 마지막 봉(기준 지수 확정 시각이 지났는데도 더 늦으면 D7).
   - 받은 달력에서 **S 전 거래일(시작 전이면 마지막 봉 전 거래일) ~ 마지막 봉의 날짜 목록 전체**를 `calendar.jsonl` 에 한 줄로 남긴다(2차 검토 R2-8).
8. **소급 수정 점검**(§4 D6): 보유 종목의 매수 체결가·최근 5일 `marks`, 대기 자산의 최근 5일 시가·종가를 새로 받은 값과 견준다. 다르면 종료 코드 4(§2.2 ⑦). `--delist` 등록 종목은 보지 않는다.
9. **처리할 봉**: 달력에서 `last_date` 다음 봉 ~ 마지막 확정 봉.
   - 없으면 "이미 처리됨" → 종료 코드 0(6 에서 D7 이 있었으면 7).
   - 5봉보다 많으면 종료 코드 6(창 실패, ②-2).
10. 처리할 봉 t 마다 오래된 것부터 아래 "봉 t 하나"를 한다. 앞 봉은 저장된 채로 남는다.

**봉 t 하나** (두 장부가 같은 봉을 같이 지난다)

0. **자료 준비 확인**(§4 D3): 두 장부의 보유·대기 종목(`--delist` 등록 종목 제외)마다 t 의 확정 행이 있고, **대기 주문 종목은 그 행의 `main.open_price` 가 None 이 아니어야** 한다.
   - 국내는 원본에 t 행이 있고 거래량이 0 이면 **정지**(그날 `halted` 에 적고 진행).
   - 그 밖에 행이 없거나, 확정 행은 있는데 대기 주문 종목의 시가가 None 이면 자료 미준비 → 종료 코드 4(t 와 그 뒤 봉은 처리 안 함, 2차 검토 R2-13).
1. **스크리너 한 번**: `screener.scan_frames(frames, universe, asof=t)` — 모든 시세를 t 이하로 자른 뒤 판단한다. 두 장부가 결과를 같이 쓴다(F7).
2. **팀장 방식**(검토 I6)
   - 지금 시각 < `next_open(t)`(t 다음 평일의 국내 09:00 KST / 미국 09:30 ET) 이면 `mode="llm"`, 아니면 `mode="late"`(LLM 안 부름). 휴장일은 따지지 않아 조금 이르게 끊는 쪽이다.
   - `mode="llm"` 이어도 `Leader` 는 **LLM 을 부르기 직전마다** 지금 시각을 다시 본다. `next_open(t)` 를 지났으면 그 호출부터는 부르지 않고 `late_no_llm` 폴백으로 적는다(한 봉 안의 호출이 최대 6번 × 150초라 장 시작을 넘을 수 있다, 2차 검토 R2-14). 하루 기록의 `late` 는 봉 시작 때 값 그대로이고, 이런 호출 수는 하루 기록 `late_calls` 에 센다(⑧ 폴백 비율에 들어감).
   - 재현은 `mode="replay"`.
3. **트레이너마다(마라토너 → 스프린터 → 파이오니어), A0 → A1 순서로** `team.run_trainer(..., st=그 장부, breaker=CircuitBreaker(inf, inf), cache=엄격 cache, h1=H1Day(...))`. 그 안의 순서:

**시가 (봉 t)** — 트레이너 지갑마다. **t = S 이면 시가 단계가 없다**(입금만, §2.5).
- a. **(A1, t = S+1 에만) 첫날 전부 지수**: 현금(= 시작 금액) 전부를 지수 시가로 산다. 식은 아래 e 와 같다. 체결 기록 `purpose="start"`.
- a′. **(`--delist` 로 등록했고 아직 정리 안 한 종목이 있으면, 등록한 `last_date` 보다 뒤인 첫 처리 봉에서)** 두 장부 모두 그 종목 전부를 등록한 `last_close` 로 판 것으로 적고 그 종목 대기 주문을 지운다(§2.2 ⑦-4). 대기 주문 정리 b 보다 먼저 한다.
- b. **대기 주문 나누기**
  - **오늘 체결 가능** = 그 종목 확정 시세에 날짜 t 행이 있고 `main.open_price(행)` 이 None 이 아님.
  - t 에 `halted` 인 종목의 주문은 그대로 남긴다(STAGE0 A5).
- c. **주식 매도**: 오늘 체결 가능한 매도 주문(보유 중인 종목만)을 그 종목 시가로 판다. `PaperWallet.sell(..., tax_rate=체결일 세율)`, 미국은 0.
- d. **주식 매수**: 오늘 체결 가능한 매수 주문을 대기 목록 순서대로 처리한다(이미 보유 중이면 건너뜀).
  - 주식 수 `n = shares_within_cap(start_cash, cap, P, fee, slip)`. 0 이면 "0주" 보류(`wallet.skip`, 사유는 team.py 그대로).
  - 필요 금액 `need = E·n + E·n·fee`, `E = P·(1+slip)` (`PaperWallet.buy` 와 같은 계산 순서).
  - **A0**: `need > cash` 이면 "현금 부족" 보류.
  - **A1**
    - 지수 1단위 매도 수령액 `u_net = Q·(1−slip) − Q·(1−slip)·fee`(Q = 그날 지수 시가, 매도세 0).
    - `avail = cash + units·u_net`.
    - `need > avail·(1−1e-9)` 이면 **지수를 팔지 않고** "현금 부족" 보류(R2 I2·R6).
    - 아니면 `need > cash` 일 때만 `u = min(units, (need − cash)/u_net·(1+1e-9))` 단위를 지수 시가로 판다(`u > 0` 일 때만). 그다음 주식을 산다.
    - 이 여유값 때문에 지수를 판 뒤의 매수는 항상 성공한다. **그래도 실패하면 장부 논리 오류(L11)** 로 멈춘다(검토 m2: 일어날 수 없게 만든 길).
- e. **A1 쓸어 담기**: 현금 ≥ 1(달러/원)이면 `u = cash / (Q·(1+slip)·(1+fee)) · (1−s)` 를 지수 시가로 산다.
  - s 는 1e-12 → 1e-9 → 1e-6 순서로 처음 성공하는 값(R2 `_sweep_to_index`).
  - 매도 대금·정리 대금도 여기서 지수로 간다.

**종가 (봉 t)** — 트레이너 지갑마다 (team.py ②~④ 그대로)
- f. **보유 종목**
  - t 에 `halted` 이면(그 종목의 t 이하 마지막 봉 < t): 마지막 거래 종가로 평가만 하고 보유일수·매도 판단은 쉰다(kr-fix-s0 I1).
  - 아니면 어제부터 들고 있던 종목만 보유일수 +1. 대기 주문이 없으면 `brain.decide(t 이하 시세, 보유)` → 매도면 다음 시가 매도 주문.
  - H1 만: 평가용 가격표에 **대기 자산 종가**를 넣는다(넣지 않으면 `PaperWallet.value` 가 지수를 평균 매입가로 평가한다, §7 R14). 쓴 종가는 하루 기록 `marks` 에 적는다.
- g. **서킷**: team.py ③ 이 장부 서킷(inf)을 부르지만 절대 걸리지 않는다. 그림자 서킷은 i 에서 계산한다.
- h. **신규 후보**
  - 보유 + 매수 대기 < 5 일 때, 1 의 후보에서 보유·대기 종목과 오래된 봉 후보(신호 봉 < t)를 뺀다.
  - 후보가 있으면 **판정 기록을 거친 팀장**에게 묻는다(§3.3 `Leader`).
  - veto 는 빠지고, hold 는 "팀장 hold" 보류, 확신도 < 0.5 는 보류.
  - 남은 것을 확신도 높은 순(같으면 스크리너 순서)으로 빈자리만큼 다음 시가 매수 주문(신호일 t)으로 낸다. 정렬 열쇠는 team.py 그대로 `conviction or 0`(확신도 없음 = 0 으로 친다), 안정 정렬이다.
  - H1 은 이 단계의 결과(후보·판정·효과·빈자리 부족)를 `note_leader` 로 넘겨 받아 두었다가 i 에서 `skips`·`orders`·하루 기록에 쓴다(§3.2 G4).
- i. **기록**
  - 평가액 = 현금 + Σ주식 수×`marks` + 지수 단위×지수 종가.
  - 그림자 서킷(§2.6).
  - `prev_value`·`last_date` = t.
  - 새로 생긴 주문을 `orders` 에 적는다.
  - 하루 기록(day row)을 **변화가 없는 날에도** 붙인다(빠진 날을 셀 수 있어야 하므로).

4. **점검**: 두 장부 각각과 짝(A0↔A1)을 §4 L 등급으로 점검한다. 오류가 있으면 종료 코드 2. t 는 저장하지 않는다.
5. **저장**(§2.5 커밋 순서): 판정 기록 줄은 3 의 h 에서 이미 디스크에 있다 → 백업 → 장부 6개 → `HEAD.json`.

마지막에 두 장부 요약을 찍는다(§3.3 `summary_lines`).

**A0 와 A1 이 다른 곳은 여기뿐이다**

| 단계 | A0 | A1 |
|---|---|---|
| S | 입금만, 현금 | 입금만, 현금 |
| a (S+1) | 없음 | 현금 전부 지수 |
| d 매수 가능 여부 | `need ≤ cash` | `need ≤ (cash + units·u_net)·(1−1e-9)` |
| d 매수 자금 | 현금 | 현금 먼저, 모자란 만큼만 지수 매도 |
| e 쓸어 담기 | 없음(현금으로 남김) | 현금 ≥ 1 이면 전부 지수 |
| f~i 평가 | 현금 + 주식 | 현금 + 주식 + 지수 |

### 2.4 국내 거래정지일 · 자료 늦음 · 기준 지수 확정 시각

| 경우 | H1 동작 | 근거 |
|---|---|---|
| 국내 거래정지일 | 원본에 그 날짜 행이 있고 Volume=0 → `confirmed_bars` 가 그 행을 버리므로 확정 시세에는 없음 → 그날 `halted` | kr-fix-s0 S0-2, STAGE0 A5 |
| 정지 중 대기 주문 | b 에서 그대로 남김. 정지가 풀린 첫 거래된 봉의 시가에 c·d 로 체결. A1 은 그날에야 모자란 지수를 판다 | A5 |
| 정지 중 보유 종목 | 마지막 거래 종가로 평가, 보유일수·매도 판단 쉼 | kr-fix-s0 I1, R2 I14 |
| 정지 중 종목의 매수 후보 | 스크리너(마지막 봉 < 그 스캔의 최근 봉)와 team ④(신호 봉 < t)가 두 번 뺀다 | kr-fix-s0 M1 |
| 국내 보유·대기 종목에 t 행이 없고 원본에 거래량 0 행도 없음 | 정지가 아니라 **자료 미준비** → D3, 종료 코드 4, 다음 실행이 다시 | 검토 I1 (가) |
| 미국 보유·대기 종목에 t 행 없음 | 자료 미준비 → D3. 여러 날 이어지면 ②-2 상한, 인수·상장폐지면 §2.2 ⑦ | 검토 I1 |
| 종목군에만 있는 종목에 t 행 없음 | 후보에서 빠질 뿐(스크리너 오래된 봉 규칙). 오류 아님 | M1 |
| 국내 16:00~22:30 KST 실행 | 종목 봉은 오늘까지 확정, KS200 은 어제까지 → H1 달력의 마지막 봉 = 어제. 스크리너·판단·체결을 모두 어제 기준으로 자른다(asof). 오늘 봉은 다음 실행에서 | `bench_cutoff` |
| KS200 늦음·멈춤 | 확인용 대형주(005930·000660)에 22:30 KST 가 지난 새 봉이 있는데 KS200 에는 없음 → **D7, 종료 코드 7**(처리할 수 있는 앞 봉까지는 저장) + 알림. 계속되면 늦은 봉 → ②-2 상한 | kr-fix-s0 §6-5(4주 멈춤 사례), 검토 I4 |
| **2026→2027 연도 경계** | FDR 은 KS200 을 연도 파일(`year_ks200/<연도>.csv`)로 읽고, 한 해 파일을 못 받으면 **그 해를 조용히 뺀다**(kr-fix-s0 M8). 2027.csv 가 늦게 생기면 → 2027 첫 봉부터 D7. 2026.csv 를 한 번 못 받으면 이미 처리한 날짜가 사라짐 → D4, 종료 코드 4 | 검토 I4 |
| 미국 SPY 늦음 | 확인용 AAPL·MSFT 에 16:15 ET 가 지난 새 봉이 있는데 SPY 에는 없음 → D7 | 같음 |
| LLM 시각 | 봉 t 를 `next_open(t)` 뒤에 처리하면(맥이 늦게 깸 등) LLM 을 부르지 않고 폴백(`late_no_llm`) | 검토 I6 |

### 2.5 시작 · 늦은 봉 · 멱등 · 커밋 지점 · 재시작

**새 시작은 명시 명령으로만** (검토 m7)
- `python h1.py start --market m`.
- `start` 는 모든 파일(meta·장부 6개·HEAD·calendar)을 **`state/h1/<m>.starting/`** 에 다 쓴 뒤, 마지막에 `os.replace` 로 `state/h1/<m>/` 로 이름을 바꾼다. 그래서 `<m>/` 이 있으면 늘 HEAD 까지 있는 온전한 시작이다(2차 검토 R2-10).
  - `<m>.starting/` 이 남아 있으면(도중에 꺼짐·D 로 멈춤) 다음 `start` 가 그것을 지우고 처음부터 다시 한다. 재시작으로 세지 않는다.
- 그 시장 폴더(`<m>/`)가 이미 있으면 거절한다.
- 폴더가 없는데 `runs.jsonl` 에 그 시장의 **성공한(종료 코드 0) start** 기록이 있고 `restarts.jsonl` 에 그 뒤의 재시작 기록이 없으면 거절한다(실수로 지운 경우). 종료 코드 8, 사람이 확인.
- `run` 은 장부가 없으면 시작하지 않고 종료 코드 8.

**시작 규칙 (Q8, 검토 X2)** — 한 가지로 고정한다.
- **S**(start 명령이 처리하는 봉)
  - A0·A1 모두 시작 금액을 S 날짜로 입금한다. **시가 단계 없음**(체결·지수 매수 없음).
  - 종가에 f~i: 보유가 없고, 그림자 서킷 prev=None 이라 안 걸린다. h 에서 후보 → S+1 시가 주문.
  - A1 의 S 종가 현금 = 시작 금액.
- **S+1 시가**
  - A0 는 평소대로 b→c→d.
  - A1 은 **a(현금 전부 지수) → b → c(팔 것 없음) → d(모자란 만큼 지수 매도) → e** 순서.
- **왜 a 를 주문보다 먼저 하나**
  - R2 sim_team 의 첫날 규칙("입금 → 그 시가에 전부 지수")을 한 봉 미룬 것이다. 그 뒤는 sim_team 같은 시가 순서(매도 → 매수 → 쓸어 담기) 그대로다.
  - 그래서 A1 은 S+1 부터 매일 "지수만 든 채로 주문을 받는" 같은 길을 지난다(첫날만 "현금으로 매수"하는 다른 길이 생기지 않는다).
  - 지수 B&H 와 같은 가격·같은 비용으로 출발한다.
  - 대가: S+1 에 지수를 산 뒤 곧 일부를 팔아 그 몫만 왕복 비용(미국 약 0.3%)을 한 번 낸다. R2 첫 이틀(i0 전부 지수 → i0+1 지수 매도)과 같은 구조다.
  - 대안(주문 먼저 → 쓸어 담기 나중)은 이 비용이 없지만 첫날만 다른 길이라 채택하지 않았다.
- **L10 예외**: S 날 A1 은 현금 == 시작 금액, 지수 단위 0, 체결 0. S+1 부터 종가 현금 < 1. S+1 의 첫 체결은 `purpose="start"` 지수 매수.
- **지수 B&H(같은 시작)**: 단위 = 총액 ÷ (S+1 지수 시가 × (1+slip)(1+fee)). S 날 값은 총액, S+1 부터 단위 × 지수 종가. = R2 `index_buy_hold_fractional(md, i0+1, i1, total)`.
- 첫 판단은 S 종가에 한다(LLM 은 §2.3-2 시각 규칙). 그래서 `start` 는 장 마감 뒤 ~ 다음 장 시작 전에 돌린다.

**늦은 봉** (Q2, 검토 I3·I6)
- 정의: 봉 t 를 `next_open(t)` 이후에 처리한 것. 팀장은 폴백(`late_no_llm`), 하루 기록 `late=true`.
- 맥이 꺼져 있었으면 다음 실행이 빠진 봉을 오래된 것부터 하나씩 처리한다(각 봉은 그 날짜 이하 자료로만).
- 한 번에 5봉 넘게 밀리면 종료 코드 6 → 창 실패(②-2) → 재시작. 창 전체에서 늦은 봉이 10봉을 넘어도 창 실패.

**멱등**: 여섯 장부의 `last_date` 가 모두 마지막 확정 봉 이상이면 스캔도 팀장 호출도 하지 않고 끝난다. 이미 처리한 봉은 자료가 나중에 고쳐져도 다시 처리하지 않는다(D6 가 그 고침을 알린다).
- 멱등으로 "안 바뀌는" 파일은 장부 6개·`meta.json`·`HEAD.json`·`backup/`·판정 기록이다. 실행 일지(`runs.jsonl`·`calendar.jsonl`)는 실행마다 줄이 더해진다(2차 검토 R2-7).

**커밋 지점 하나** (검토 I7) — 시장마다 `state/h1/<m>/HEAD.json`
- 내용: `{last_date, files: {상대경로: sha256}, meta_sha256, decision_log: {lines, prefix_sha256}, run_id, written_at}`.
- 쓰는 순서
  1. 판정 기록 줄 추가 + fsync. 팀장에게 묻는 순간에 이미 씀.
  2. 지금 장부 6개 + meta(= HEAD 상태)를 `backup/<HEAD.run_id>/` 에 복사(이미 있으면 건너뜀, 최근 10개만 남김). 열쇠가 날짜가 아니라 그 HEAD 를 쓴 실행의 `run_id` 라서, 같은 `last_date` 에서 장부를 바꾸는 `corp-action`·`amend-rules` 뒤에도 백업이 HEAD 와 맞는다(2차 검토 R2-10). `corp-action`·`amend-rules` 도 이 1~4 순서로 쓰고 새 `run_id` 를 받는다.
  3. 새 장부 6개를 `.tmp` 로 쓰고 fsync 한 뒤 하나씩 `os.replace`.
  4. `HEAD.json.tmp` → fsync → `os.replace`. **여기서 그 봉이 저장된다.**
- 읽을 때
  - 6개 sha256 == HEAD → 정상.
  - 다르면(3과 4 사이에서 꺼짐) `backup/<HEAD.run_id>/` 가 HEAD 와 맞을 때 그것으로 되살리고 그 봉을 다시 처리한다. 같은 자료·같은 판정 기록이라 결과가 같다. 그 밖은 L24(장부 파일 손상) → 종료 코드 2.
- 판정 기록에 장부보다 먼저 쓴 줄이 남아도 무해하다. 다음 실행이 같은 열쇠를 다시 쓴다.

**재시작**: `python h1.py restart --market m --reason "..."`
- 잠금 아래에서 `state/h1/<m>/` 를 `state/h1/archive/<m>-<시각>/` 로 옮기고 `restarts.jsonl` 에 한 줄 적는다.
- 판정 기록·`runs.jsonl`·`errors.jsonl`·고정 종목군은 시장 폴더 밖이라 그대로 남는다.
- 그다음 `h1.py start`.

### 2.6 그림자 서킷 (Q1, 검토 X1)

- **계산**: 매일 i 단계에서 두 장부 × 트레이너마다
  `hit = CircuitBreaker(누적한도, 일일한도).check(start_cash, prev, value)`
  - 누적한도·일일한도 = `main.CONFIG["서킷브레이커"]`(지금 0.10·0.07). 규칙은 `risk_guard.CircuitBreaker` 그대로다: 누적 = value ÷ start_cash − 1 ≤ −10%, 하루 = value ÷ prev − 1 ≤ −7%.
  - `prev` = **그 장부의 바로 전 하루 기록(day row)의 `value`**. S 날은 None.
  - team.py 의 `st["prev_value"]` 는 쓰지 않는다(G5 전에 그날 값으로 덮어써지므로).
- **저장**: 걸리면 그 day row 의 `events` 에 `{"kind": "shadow_breaker", "why": hit, "first": 이 트레이너 첫 발동이면 true}`.
  - 장부는 아무것도 바뀌지 않는다: 정리 주문 없음, `stopped` 는 늘 False.
  - 첫 발동 뒤에도 매일 계산한다. 영구 정지를 흉내 내지 않고 "그날 걸렸을지"만 본다.
- **보고**: (장부, 트레이너)별 첫 발동일·사유·발동한 날 수. 판정에는 쓰지 않는다(§2.2 ③).
- **재현 M5′**: H1 그림자 첫 발동일(창 마지막 봉 제외, K1) == R2 기준값(같은 운영 시작 하위 클래스, `cb="current"`)의 서킷 사건 날짜. (장부, 트레이너)마다 비교하고, 둘 다 없으면 같음.
  - 첫 발동 전까지 R2 의 서킷 켠 실행은 끈 실행과 똑같으므로 이 비교가 성립한다. 검토 probe1 로 재현 창 4조합 모두 같음을 확인했다.

---

## 3. 인터페이스

### 3.1 파일 (바꿀 것 / 새로 만들 것)

| 파일 | 새/변경 | 왜 |
|---|---|---|
| `team.py` | 변경(작게) | `run_trainer(..., h1=None)` 갈고리 4곳(G0·G1·G2·G4, 마무리 G5). **`__main__`·`run()` 은 안 바꾼다**(`--h1` 없음). `h1=None` 이면 지금 코드 그대로 |
| `paper_wallet.py` | 변경(작게) | `Holding.shares` 표기를 `float` 로(F3). `sell(..., tax_rate=None)` 선택 인자(국내 지수 매도세 0·날짜별 주식 세율). 기본값이면 지금과 같음 |
| `analyst.py` | 변경(더하기만) | `normalize_verdict()`, `analyze_logged()`(상태·시각·모델·CLI 버전을 같이 돌려줌). **`_build_prompt`·`analyze()`·`apply()` 는 그대로**(프롬프트 운영과 같음, Q4 보류) |
| `screener.py` | 변경 | `scan_frames(frames, order, asof)` 를 더하고 **`scan()` 이 그것을 부르게** 해서 구현을 하나로 둔다(검토 m5). 골든으로 결과가 바이트까지 같음을 확인 |
| `h1.py` | **새** | H1 실행기: `start`·`run`·`restart`·`corp-action`·`status`, 경로·엄격 읽기·커밋 지점·백업·잠금·관문, 시세 받기, 대기 자산 체결, 판정 기록·팀장 래퍼, 하루 기록·그림자 서킷, 따라잡기, 요약 |
| `h1_check.py` | **새** | 장부 점검 함수(§4). 순수 함수(인터넷·파일 쓰기 없음) |
| `h1_report.py` | **새** | 월간·최종 보고서(F8), FRED 금리 받기·저장본, 이자·실현손익 계산(보고서 안에서만) |
| `h1_replay.py` | **새** | 단계 5 재현: R2 를 임시 폴더에 풀어 하네스로 기준값 → 새 코드 재현 → 비교 → 보고서·통과 기록 |
| `tests/test_h1_*.py` | **새** | §6 시험(네트워크 없음). 골든 `tests/golden/`. 기존 306개 시험은 한 줄도 안 고친다 |
| `README.md`, `docs/h1-forward-run.md` | 변경/새(문서) | 맥 설치(worktree·venv)·명령·시각·오류 대처 |
| `main.py`, `markets.py`, `order_runner.py`, `broker/`, `live.py`, 브레인, `risk_guard.py`, `metrics.py` | **안 바꿈** | 필요한 것은 이미 있다: `load_benchmark`, `prices_for`, `confirmed_bars`, `open_price`, `save_json_atomic`, `make_wallet`, `code_ok` |

### 3.2 `team.py` 변경 (갈고리)

```python
def run_trainer(tname, cash, cap, breaker, screened, bar_date,
                st=None, cache=None, mk=None, h1=None):          # h1: h1.H1Day 또는 None
```

| 갈고리 | 내용 |
|---|---|
| **G0** 시작 | `h1 is not None and st is None` 이면 `ValueError`. H1 장부는 h1.py 가 읽어서 넘긴다(F1). `_load` 를 부르면 기존 `state/` 를 읽게 된다 |
| **G1** ① 체결 | `if h1 is not None: changed = h1.fill(st, tname, cap, bar_date, cache, m, logs) or changed`<br>`else:` 지금 ① 코드 그대로(들여쓰기만 한 칸) |
| **G2** ② 뒤 | `if h1 is not None: prices[h1.idle.code] = h1.idle.close` |
| **G4** ④ 팀장 | `ask = h1.leader if h1 is not None else analyst.analyze` → `analysis = ask(tname, cands)`.<br>`analyst.apply` 를 부르기 **바로 앞에** `cands0 = list(cands)` 한 줄을 넣는다(지금 team.py 에는 apply 전 후보를 담는 이름이 없다).<br>주문을 다 낸 뒤 `if h1 is not None: h1.note_leader(st, tname, bar_date, cands0, analysis, kept, slots)`.<br>`note_leader` 는 장부를 직접 고치지 않고 H1Day 의 트레이너별 버퍼에 담는다. `close_day` 가 그 버퍼로 `skips`(팀장hold·확신도낮음)·`orders`(새 매수 주문)·하루 기록(`leader`·`over_slots`)을 쓴다(2차 검토 R2-15) |
| **G5** 마무리 | `if not changed and h1 is None: return ...` (H1 은 항상 진행)<br>`if h1 is None: _save(tname, st, m)`<br>`else: h1.close_day(st, tname, bar_date, prices, value_now)` (그림자 서킷·marks·orders·day row. 파일 저장은 h1.py 가 6개를 한꺼번에) |

- ③ 서킷 코드는 그대로 둔다. H1 은 `breaker=CircuitBreaker(inf, inf)` 를 넘기므로 걸리지 않는다.
- h1 은 team 을 import 하지만 team 은 h1 을 import 하지 않는다(순환 없음). `h1=None` 경로에서는 h1 모듈이 아예 읽히지 않는다.

### 3.3 `h1.py`

```python
H1_DIR = team.STATE_DIR / "h1"                    # state/h1 (F1)
ARMS = ("A0", "A1")
TOTALS = {"us": 100_000, "kr": 100_000_000}       # F2
SCHEMA = {"us": "h1-us-2", "kr": "h1-kr-2"}
N_UNIVERSE = 40                                   # Q7
SWEEP_MIN = 1.0                                   # R2 SWEEP_MIN
SHORT_MARGIN = 1e-9                               # R2 R6 · _raise_cash
SWEEP_SHRINK = (1e-12, 1e-9, 1e-6)                # R2 _sweep_to_index
LEDGER_BREAKER = (float("inf"), float("inf"))     # Q1: 장부 서킷 끔
SHADOW_BREAKER = (main.CONFIG["서킷브레이커"]["누적한도"], main.CONFIG["서킷브레이커"]["일일한도"])
KR_SELL_TAX = (("0000-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
               ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
               ("2026-01-01", 0.0020))            # STAGE0 §1.2 (Q9), 체결일 기준
WINDOW_BARS = 63; MAX_LATE_BATCH = 5; MAX_LATE_TOTAL = 10; MAX_RESTARTS = 2; DEADLINE = "2027-06-30"
FALLBACK_FLAG = 0.20; RETRO_TOL = 1e-6; RETRO_DAYS = 5; LOCK_WAIT_S = 1800; BACKUPS_KEEP = 10
CAL_PROBE = {"us": ("AAPL", "MSFT"), "kr": ("005930", "000660")}
CAL_HOLE_RATIO = 0.5                              # D5: 종목군 절반 이상이 거래한 날
NEXT_OPEN = {"us": ("09:30", "America/New_York"), "kr": ("09:00", "Asia/Seoul")}
FINGERPRINT_VERSION = 1                           # ledger_fingerprint 계산 방식 판
CODE_FILES = ("team.py", "h1.py", "h1_check.py", "h1_report.py", "h1_replay.py",
              "main.py", "markets.py", "paper_wallet.py",
              "screener.py", "analyst.py", "risk_guard.py", "metrics.py",
              "marathoner_brain.py", "sprinter_brain.py", "pioneer_brain.py",
              "prompts/마라토너.md", "prompts/스프린터.md", "prompts/파이오니어.md")
# EPS_CASH·EPS_REL 은 h1_check.py 에 있고, rule_constants() 가 함께 적는다(§2.2 ⑩)
ENV_PACKAGES = ("pandas", "numpy", "ta", "FinanceDataReader")   # + python 버전

class H1LogicError(Exception)        # 종료 코드 2
class H1DataProblem(Exception)       # 종료 코드 4 (kind="D1"…"D6")
class H1Refused(Exception)           # 종료 코드 3·5·6·8 (code 속성)

def idle_code(market) -> str                       # markets.MARKETS[market].benchmark (F4)
def kr_sell_tax(date: str) -> float                # 표에서 체결일 세율
def ledger_path(market, arm, trainer, root=H1_DIR) -> Path   # root 아래인지 확인
def rule_constants(market) -> dict                 # §2.2 ⑩
def code_hash(repo=REPO, files=CODE_FILES) -> tuple[str, dict]   # (합친 sha256, 파일별 sha256)
def env_info() -> dict                             # python·ENV_PACKAGES 버전
def check_gate(root=H1_DIR) -> None                # (code_hash, env) 가 replay_pass 에 없으면 H1Refused(3)
def ledger_fingerprint(states: dict) -> str        # 장부 내용 지문 (2차 검토 R2-1), 아래 설명
def next_open(market, bar_date: str) -> datetime   # t 다음 평일의 장 시작(시간대 있음)

@dataclass
class Fetched:
    df: "pd.DataFrame"            # main.confirmed_bars 를 거친 확정 시세
    halt_dates: frozenset[str]    # 국내: 원본에서 Volume == 0 인 날짜. 미국은 빈 집합
def fetch(market, code, now) -> Fetched | None    # 원본 fdr.DataReader(code, team.START) → 이름 정리 → confirmed_bars
                                                   # (main.load_prices 와 같은 단계, 시험으로 같음을 확인)

class StrictFrames(dict)          # team._prices 에 넘기는 cache: `in` 은 늘 True, 없는 열쇠는 H1LogicError

@dataclass(frozen=True)
class IdleBar:
    code: str; date: str; open: float; close: float

def decision_key(market, date, trainer, code) -> str        # "us|2026-11-09|마라토너|AAPL"
class DecisionLog:                                           # state/h1/analyst_cache.jsonl
    def __init__(self, path, read_only=False)                # 읽기: 중복 열쇠·깨진 줄 → H1LogicError(L18/L24). read_only 면 반쯤 쓴 마지막 줄을 자르지 않고 알리기만(2b-1 검토 B-8)
                                                             #       (마지막 줄만 반쯤 쓰였으면 잘라내고 runs.jsonl 에 기록)
    def get(self, key) -> dict | None
    def append(self, records: list[dict]) -> None            # 줄 추가 + flush + fsync. 이미 있는 열쇠면 H1LogicError
    def prefix_digest(self) -> tuple[int, str]               # (줄 수, 앞부분 sha256) — HEAD 에 적음

class Leader:                                                # team.run_trainer 의 h1.leader
    def __init__(self, market, date, log: DecisionLog, mode: str)   # "llm" | "late" | "replay"
    def __call__(self, trainer, cands) -> dict               # analyst.apply 가 받는 모양 {code: {...}}

class H1Day:                                                 # team.run_trainer(h1=...)
    market: str; arm: str; idle: IdleBar; leader: Leader; late: bool
    start_date: str; halted: frozenset[str]; delist: dict; code_hash: str; env: dict
    def fill(self, st, tname, cap, bar_date, cache, m, logs) -> bool   # §2.3 a~e
    def note_leader(self, st, tname, bar_date, cands0, analysis, kept, slots) -> None  # 트레이너별 버퍼에 담기만
    def close_day(self, st, tname, bar_date, prices, value) -> None    # marks·orders·그림자 서킷·day row

@dataclass
class DataSource:                                            # 운영/재현이 자료 받는 곳을 바꿔 끼움
    benchmark: Callable[[datetime], "pd.DataFrame | None"]   # 대기 자산 확정 시세
    fetch: Callable[[str, datetime], "Fetched | None"]      # 종목
    universe: Callable[[], list[str]]                        # start 때 한 번만 부름
    now: Callable[[], datetime]                              # 시간대 있는 시각
def live_source(market) -> DataSource                        # main.load_benchmark / fetch / screener.universe(40) 또는 KR_UNIVERSE

def start(market, root=H1_DIR, source=None, leader_mode="llm") -> int
def run(market, root=H1_DIR, source=None, leader_mode="llm", gate=True) -> int   # 종료 코드(§3.9)
def run_bar(market, t, states, frames, universe, idle: IdleBar, *, decisions, leader_mode, halted, prev_cal_date,
            calendar, now, ask, cli_version, code_hash, env, allowed, head, universe_sha256, meta_universe_sha256,
            brains=None) -> BarResult
    # 실제 인자는 h1.py docstring 이 기준(2b-1 구현). 입력 장부는 고치지 않고 BarResult.states 로 돌려준다.
    # BarResult: date, states, problems(L+W), lines, found, used, mode, late, llm_calls, late_calls, new_records,
    #            fingerprint(처리 뒤 장부 6개의 ledger_fingerprint), errors, ok(False 면 저장 금지)
    # 상장폐지 정보는 장부 corp_actions 하나에서만 읽는다(2b-1 검토 B-4).
    # 사전 조건(앞 거래일 == last_date, 지수 봉 날짜, S 의 prev_cal_date 등) 위반은 L 이 아니라 H1Refused/ValueError —
    # 달력·자료 문제는 h1.run 이 D4·D5 로 먼저 거른다(2b-1 검토 B-3·B-10)
def apply_split(states, code, r, date, source, at) -> dict   # ⑦-2: 6개 장부에 같게 적용, 정수가 아니면 거절
def restart(market, reason, root=H1_DIR) -> Path
def corp_action(market, code, *, split=None, date=None, delist=False, last_date=None, last_close=None,
                accept_correction=False, source=None, root=H1_DIR, source_data=None) -> int
def amend_rules(market, source, root=H1_DIR) -> int   # ⑥-ii: 세율 표 뒤에 줄이 더해진 것만 meta.rules 에 반영
def status(market, root=H1_DIR) -> list[str]
def summary_lines(market, states) -> list[str]
def cli(argv=None) -> int     # python h1.py start|run|restart|corp-action|amend-rules|status --market us|kr …
```

**`ledger_fingerprint(states)`** — `states = {arm: {trainer: st}}`(한 시장의 장부 6개)
- 장부마다 아래 칸만 남긴 사본을 만든다.
  - 남김: `wallet`(`cash`·`currency`·`fee_rate`·`sell_tax_rate`·`slippage`·`holdings`·`log`), `positions`, `pending`, `prev_value`, `stopped`, `last_date`, `start_cash`, `start_date`, `orders`, `fills`, `skips`, `corp_actions`, `days`.
  - 뺌: `schema`, `h1` 머리 전체, 하루 기록마다 `run_at`·`mode`·`late`·`late_calls`·`code_hash`·`env`.
- `{"v": FINGERPRINT_VERSION, "ledgers": {"A0/마라토너": 사본, …}}` 를 `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)` 로 바꿔 sha256. float 는 파이썬 `repr` 그대로라 비트가 같으면 글자도 같다.
- 쓰는 곳: `errors.jsonl` 의 "저장하려던 내용 지문"(④-나), `replay_pass.json` 의 `ledger_fingerprints`(④-가, ⑥), 재현 M9.

**`Leader.__call__`**
- 후보마다 열쇠를 만든다. 기록에 없는 후보만 모은다.
  - `mode="llm"` 이면 `analyst.analyze_logged(trainer, 없는 후보, now=시계, cli_version=이번 실행 값)` 를 한 번 부른다. `cli_version` 은 실행마다 한 번 `analyst.claude_cli_version()` 으로 얻어 둔다.
  - 아니면 부르지 않는다(`status="late_no_llm"`·`"replay_no_llm"`).
- 없는 후보 하나하나에 기록을 만들어 **곧바로 `append`(fsync)** 한다. LLM 이 답에서 빠뜨린 종목은 `status="missing_in_reply"` 폴백이다.
- 돌려주는 값: 기록에서 `source="llm"` 이고 판정이 있는 종목만 `{code: {"code", "verdict"(정리된 값), "conviction"(숫자 또는 None), "note"}}`.
  - 빈 dict 는 team.py 에서 None(폴백)과 똑같이 동작한다(`apply` 가 손대지 않고 `verdicts` 가 비어 있음).
- 같은 트레이너에서 A0 가 먼저 묻고, A1 은 A0 에 없던 후보만 묻는다. 그래서 같은 (날짜, 트레이너, 종목)은 **반드시 같은 기록 한 줄**을 쓴다.

**요약 예**
```
[H1 us] 기준 봉 2026-11-06 · 시작 2026-11-05 · 판정 창 2/63
  A0 쉬는 돈=현금  $100,000 → $99,812 (-0.19%)
  A1 쉬는 돈=SPY   $100,000 → $100,231 (+0.23%) · SPY 131.234567단위
  A1−A0 +$419 · SPY 들고 있기(S+1 시가 시작, 소수 단위) +0.31%
  점검 L 0 · 자료 멈춤 0 · 늦은 봉 0 · 팀장 LLM 3 / 폴백 0 · 그림자 서킷 없음
  ※ 3개월은 판단하기에 너무 짧다 — 숫자는 기록용(사전 등록). A0 는 운영 장부가 아니다
```

### 3.4 `paper_wallet.py` · `analyst.py` · `screener.py`

```python
# paper_wallet.py
@dataclass
class Holding:
    shares: float        # 주식은 정수 값, 대기 자산(지수)은 소수 단위 (H1)
    avg_price: float
def sell(self, code, price, shares, date=None, tax_rate=None) -> bool
    # tax_rate=None 이면 self.sell_tax_rate (지금과 같음). H1: 지수 다리 0.0, 국내 주식 kr_sell_tax(체결일)

# analyst.py   (_build_prompt·analyze·apply 는 그대로)
def normalize_verdict(v) -> str | None      # " VETO" → "veto", "Hold" → "hold", 그 밖은 None
def claude_cli_version() -> str | None      # "claude --version" 첫 줄, 실패하면 None (H1 실행마다 한 번)
def analyze_logged(trainer, candidates, timeout=TIMEOUT, now=None, cli_version=None) -> tuple[dict | None, dict]
    # 같은 프롬프트(_build_prompt), 같은 호출(claude -p). 반환 meta =
    # now: 시간대 있는 datetime 을 돌려주는 함수(시험·재현용, 기본 지금 시각). cli_version: 받은 값을 meta 에 그대로(이 함수는 --version 을 부르지 않음)
    # {"status": "ok"|"no_claude"|"timeout"|"os_error"|"nonzero_exit"|"decode_error"|"bad_json"|"empty",
    #  "asked_at": ISO 시각(시간대), "elapsed_s": float, "returncode": int|None,
    #  "model": os.environ.get("ANTHROPIC_MODEL") 또는 None(launchd 에서는 보통 None = "모름"),
    #  "cli_version": 넘겨받은 값}
    # analyze() 와 결과가 다른 곳(2a 검토 A-6): 답의 "analysis" 가 목록이 아니면 analyze() 는 TypeError 로 멈추지만
    # analyze_logged 는 bad_json 폴백, 출력 디코드 실패는 decode_error 폴백. 운영 analyze() 는 그대로 둔다(개선 후보로 따로).

# screener.py
def scan_frames(frames: dict[str, "pd.DataFrame"], order: list[str], asof: str | None = None,
                min_bars: int = 70, brains=None) -> tuple[dict[str, list[dict]], int]
    # brains=None 이면 screener.BRAINS. 재현 W3 의 가짜 브레인을 team.BRAINS 와 같이 넘길 수 있게(2차 검토 R2-6)
    # 70봉 미만 제외, 보유 없음 기준 매수 신호, 마지막 봉 < 그 스캔의 최근 봉이면 제외. 순서 = order.
    # asof 가 있으면 각 시세를 asof 이하로 자른 뒤 판단.
def scan(n=50, market="us")   # 시세를 받아 scan_frames 를 부른다(바깥 동작은 그대로, 골든으로 확인)
```

### 3.5 장부 파일 형식 `state/h1/<market>/<arm>/team_<trainer>.json`

team.py 상태 키를 그대로 두고 H1 칸을 더한다.

```jsonc
{
  "schema": "h1-us-2",
  "h1": {"market": "us", "arm": "A1", "trainer": "마라토너", "idle_code": "SPY", "idle_mode": "index",  // A0 "cash"
         "restart_no": 0, "code_hash": "…", "env": {…}, "updated_at": "2026-11-07T07:12:03+09:00"},
  "wallet": {"name": "마라토너", "cash": 0.0000000588, "currency": "USD", "fee_rate": 0.001,
             "sell_tax_rate": 0.0, "slippage": 0.0005,
             "holdings": {"SPY": {"shares": 74.21876543210987, "avg_price": 755.737},   // 소수 단위 (A1 만)
                          "AAPL": {"shares": 21, "avg_price": 271.26}},                // 정수
             "log": [ … PaperWallet 기록 그대로 (금액은 소수 2자리로 반올림 — 점검은 이것을 쓰지 않음) … ]},
  "positions": {"AAPL": {"buy_price": 271.13, "days_held": 3, "shares": 21, "buy_date": "2026-11-06"}},
  "pending": [{"code": "MSFT", "action": "매수", "signal_date": "2026-11-09", "reason": "…", "note": null}],
  "prev_value": 60123.4, "stopped": false, "last_date": "2026-11-09",
  "start_cash": 60000.0, "start_date": "2026-11-05",
  "orders": [ 주문 기록 … ], "fills": [ 체결 기록 … ], "skips": [ 보류 기록 … ],
  "corp_actions": [ 기업 행위 적용 기록 … ], "days": [ 하루 기록 … ]
}
```
- `positions` 에는 **주식만** 있다. 지수는 `wallet.holdings[idle_code]` 에만 있다(R2 I19). A0 의 `holdings` 에는 대기 자산이 절대 없다(L10).
- `stopped` 는 늘 False 다(L2).

**주문 기록 (`orders`, 생길 때 한 줄, 검토 I9)**

| 칸 | 내용 |
|---|---|
| `id` | `"<signal_date>\|<code>\|<action>"` (장부 안에서 하나뿐, L5) |
| `signal_date`, `code`, `action`, `reason` | 신호일, 종목, `"매수"`/`"매도"`, 사유 **전체**(team.py 출력처럼 14자로 자르지 않음, 할 일 9번) |
| `origin` | `"sell_signal"`(②) / `"candidate"`(④) |
| `created_on` | 주문을 낸 처리 봉 |
| `status`, `done_date`, `why` | `"pending"` / `"filled"` / `"skipped"`(0주·현금부족) / `"dropped"`(이미 보유·보유 없음)와 그 날짜·사유 |

**체결 기록 (`fills` 한 줄)**

| 칸 | 내용 |
|---|---|
| `date`, `code`, `kind` | 체결일, 종목, `"stock"` 또는 `"idle"` |
| `side`, `qty` | `"buy"`/`"sell"`, 수량(주식 정수, 지수 소수 그대로) |
| `price` | 그날 시가(주식은 그 종목 행의 Open, 지수는 대기 자산 Open). `purpose="delist"` 만 마지막 거래 종가 |
| `exec_price`, `fee`, `slip_cost`, `tax`, `cash_delta` | 실제 체결가(±슬리피지), 수수료, 슬리피지 비용(= qty×price×slip), 매도세, 현금 변화 |
| `cash_before`, `cash_after`, `units_before`, `units_after` | 점검용 |
| `order_id` | 주식 다리: 그 주문의 `id` |
| `purpose` | 지수 다리: `"start"`(S+1 첫 전부 지수), `"fund:<종목>"`(그 매수 자금), `"sweep"` / 주식 다리: `"order"`, `"delist"` |
| `need`, `short` | 매수 필요 금액, 지수로 메운 금액(A1) |

**보류 기록 (`skips` 한 줄)**: `date, code, kind("0주"|"현금부족"|"팀장hold"|"확신도낮음"), reason, need, avail, price, order_id(있으면)`. `price` 는 L12 가 "0주" 를 다시 계산하려고 둔다.

**기업 행위 기록 (`corp_actions` 한 줄)**: 분할 `{"kind": "split", "code", "r", "date": 출처의 분할 기준일, "applied_after": 적용 때 장부 last_date, "source", "at"}` / 상장폐지 `{"kind": "delist", "code", "last_date", "last_close", "source", "at"}`(`last_date` ≤ 등록 때 장부 last_date 여야 함) / 정정 확정 `{"kind": "correction", "code", "items": [{date, field, old, new}], "source", "at"}`. 점검(L7·L8·L15·L23)은 `applied_after` 시점에 수량 ×r·매수가 ÷r 를 반영해 원장을 다시 걷는다(2b-1 검토 B-2).
- 빈자리가 모자라 주문을 못 낸 후보는 보류가 아니라 하루 기록의 `over_slots` 로 센다(R2 I23).

**하루 기록 (`days` 한 줄, 처리한 봉마다 꼭 하나)**
```jsonc
{"date": "2026-11-09", "prev_cal_date": "2026-11-06", "run_at": "2026-11-10T07:11:40+09:00",
 "mode": "llm", "late": false, "late_calls": 0, "code_hash": "…", "env": {…},
 "idle_open": 752.73, "idle_close": 754.35, "marks": {"AAPL": 276.4},
 "cash": 0.0000000588, "stock_value": 5804.4, "idle_units": 74.2187654321, "idle_value": 55987.3, "value": 61791.7,
 "n_buys": 1, "n_sells": 0, "n_idle_legs": 2, "n_skips": 0, "over_slots": 0,
 "costs": {"fee": 61.5, "slip": 30.7, "tax": 0.0},
 "events": [{"kind": "shadow_breaker", "why": "누적 -10.2% …", "first": true}],
 "screened": ["AAPL", "MSFT"],
 "leader": [{"code": "AAPL", "key": "us|2026-11-09|마라토너|AAPL", "verdict": "buy", "effect": "ordered"}],
 "halted": []}
```
- `effect`: `"veto"`(빠짐) · `"hold"` · `"low_conv"` · `"ordered"` · `"over_slots"`.
- `marks` = 평가에 쓴 보유 종목 종가(정지 종목은 마지막 거래 종가). 보고서가 저장 자료만으로 L7·L15 를 다시 볼 수 있게 한다(검토 m3).

**`state/h1/<market>/meta.json`**:
```
{"market", "start_date", "restart_no", "created_at", "rules": rule_constants(),
 "universe_sha256", "code_hash_at_start", "env_at_start", "design_doc_sha256",
 "ledger_breaker": "off", "shadow_breaker": [0.10, 0.07]}
```

### 3.6 판정 기록 `state/h1/analyst_cache.jsonl` (F5 + 할 일 2번, 검토 I7)

한 줄 = 기록 하나. 추가만 한다(덮어쓰기·지우기 없음). 팀장에게 물은 직후 **장부보다 먼저** fsync 한다.

```jsonc
{"key": "us|2026-11-09|마라토너|AAPL", "market": "us", "date": "2026-11-09", "trainer": "마라토너", "code": "AAPL",
 "verdict": "buy",            // normalize_verdict: "buy"|"hold"|"veto"|null
 "verdict_raw": "Buy", "conviction": 0.7, "conviction_raw": "0.7",
 "note": "실적 발표 전 변동성 주의",   // 500자까지
 "source": "llm",             // "llm" | "fallback"
 "status": "ok",              // ok | missing_in_reply | no_claude | timeout | os_error | nonzero_exit
                              // | decode_error | bad_json | empty | bad_verdict | late_no_llm | replay_no_llm
                              // bad_verdict: LLM 이 답했지만 판정 글자를 정리하면 buy/hold/veto 가 아님 → source="fallback", 폴백으로 셈(2b-1 검토 B-5)
 "model": null, "cli_version": "2.x.y (Claude Code)",
 "asked_at": "2026-11-10T07:11:22+09:00", "elapsed_s": 41.2, "next_open": "2026-11-10T09:30:00-05:00",
 "call_id": "us|2026-11-09|마라토너|1", "batch": ["AAPL", "MSFT"],
 "signal": {"price": 271.4, "rsi": 47.2, "reason": "…", "date": "2026-11-09"}}
```
- 읽을 때 같은 열쇠가 두 번 있으면 L18 오류.
- 마지막 줄만 반쯤 쓰였으면(쓰는 중 꺼짐) 그 줄은 잘라 낸다. 그 줄은 아직 어느 장부에도 쓰이지 않았다. `runs.jsonl` 에 남긴다.
- `HEAD.json` 이 (줄 수, 앞부분 sha256)을 적어 두므로, 지난 줄이 바뀌면 다음 실행에서 L18 로 잡힌다.
- 재시작해도 지우지 않는다. 새 창의 같은 (날짜, 트레이너, 종목)은 이 기록을 다시 쓴다(그 뒤 소식을 본 판정이 생기지 않게).
  - 옛 창이 남긴 `late_no_llm`·폴백 기록도 새 창에서 그대로 다시 쓴다(같은 열쇠는 늘 같은 판정이 원칙). 그 기록은 새 창 ⑧ 폴백 비율에 들어간다.
- 채점(G4: 20거래일 뒤 "샀다면 수익 − 지수 수익")은 범위 밖이다. 날짜·종목·신호 가격이 있어 나중에 시세만으로 계산할 수 있다.

### 3.7 그 밖의 파일 (`state/h1/` 아래, 모두 gitignore 된 `state/` 안)

| 파일 | 내용 |
|---|---|
| `h1.lock` | 잠금(fcntl). 모든 명령. 최대 30분 기다린 뒤 종료 코드 5 |
| `analyst_cache.jsonl` | 판정 기록(§3.6) |
| `runs.jsonl` | 명령 한 번 = 시작 줄 + 끝 줄: 명령·시장·시각·코드 지문·env·`mode`·처리한 봉·종료 코드·메시지(관문 거절·자료 멈춤 포함), `start_date`(모르면 `unknown`), `d7_checked`·`journal_recovered`·`bar_modes`. **창 세기**: `start_date == S` 이거나 `unknown`·None 이면서 `at ≥ meta.created_at` 인 줄(보고서도 `h1._in_window` 를 그대로 씀) |
| `errors.jsonl` | L 오류: 시장·봉·문제 목록·**저장하려던 장부 6개의 내용 지문**(`ledger_fingerprint`, §2.2 ④). 시장 폴더 밖이라 재시작 뒤에도 남음 |
| `restarts.jsonl` | 재시작: `{at, market, restart_id, status: "moving"\|"done", old_start, old_last, reason, archive}`. 의도 줄 → 폴더 이동 → 끝 줄. 횟수는 `restart_id` 로 한 번 |
| `changes.jsonl` | 코드 동결 중 허용 변경(§2.2 ⑥)·기업 행위 결정(⑦). amend-rules 는 `pending` → `done`/`abandoned`. 장부·meta 에는 있는데 일지에 없던 줄은 다음 명령이 `recovered: true` 로 채움 |
| `replay_pass.json` | 재현 통과: `[{code_hash, files, env, ledger_fingerprints: {"W1-us": 내용 지문, "W1-kr": …, "W2-kr": …}, fingerprint_version, passed_at, report}]`. **`h1.record_replay_pass` 로만 추가**(잠금 아래, 지난 줄 안 바꿈) |
| `replay_pass.seal.json` | 통과 기록 줄마다 sha256. 목록이 줄거나 바뀌면 관문 거절 3 |
| `universe/us.json`, `universe/kr.json` | 종목군 목록·순서(첫 S 에 한 번 쓰고 안 바꿈. 재시작해도 그대로). 미국은 받은 시각·FDR 버전도 |
| `<market>/HEAD.json`, `<market>/meta.json` | 커밋 지점, 시작 때 고정 값 |
| `<market>/calendar.jsonl` | 실행마다 한 줄: 받은 시각, 달력의 **S 전 거래일 ~ 마지막 봉 날짜 목록 전체**, 그 sha256, 처리한 날짜 |
| `<market>/corp_actions.jsonl` | 기업 행위 적용 |
| `<market>/backup/<run_id>/` | 커밋 직전(= 그 HEAD 상태) 장부 6개 + meta (최근 10개) |
| `<market>.starting/` | `start` 가 쓰는 중인 임시 폴더(다 쓰면 `<market>/` 로 이름 바뀜) |
| `archive/<market>-<시각>/` | 재시작 때 옮긴 옛 시장 폴더 |
| `rates/DTB3.csv`, `rates/IR3TIB01KRM156N.csv` | FRED 금리 저장본 + `fetched_at` |
| `reports/` | 월간·최종·재현 보고서 |

### 3.8 보고서 `h1_report.py`

```python
def build(market, month=None, final=False, root=H1_DIR, online=True) -> str      # 마크다운
def write(market, month=None, final=False, root=H1_DIR, online=True) -> Path     # state/h1/reports/<market>-<YYYY-MM>.md
                                                                                  # (--final 이면 <market>-final-<S>.md)
def fetch_rates(series_id, cache_dir, timeout=20) -> Path | None    # urllib(표준 라이브러리). 실패하면 None
def load_rates(series_id, cache_dir) -> "pd.Series | None"          # FRED 원본·R2 형식 둘 다, "." 은 빈값
def rate_for_days(dates: list[str], series, rule: str) -> list[float]   # "prev_day" | "prev_month" (sim_team 과 같은 규칙)
def interest_overlay(dates, cash, rate_pct) -> list[float]
def realized(fills) -> dict                                          # 평균원가법, 보고서 안에서만
def cli(argv=None) -> int   # python h1_report.py --market us|kr [--month YYYY-MM] [--final] [--offline]
                            #        python h1_report.py --fetch-rates
```

- **입력**: 장부 6개(`orders`·`fills`·`skips`·`days`), `meta.json`, `HEAD.json`, `calendar.jsonl`, 판정 기록, `runs.jsonl`·`errors.jsonl`·`restarts.jsonl`·`changes.jsonl`, 금리 저장본.
  - 대기 자산 시가·종가와 보유 종목 종가(`marks`)가 하루 기록에 있어서 시세를 다시 받지 않는다.
- **출력**: `state/h1/reports/`. 같은 달을 다시 만들면 덮어쓴다(장부가 원본, 보고서는 계산값). 사람이 골라 저장소에 커밋한다.
- **내용**
  1. **고정 문장**: "수익률은 기록만, 판정 안 함(사전 등록 ③)" / "A0 는 R2 A0 규칙의 그림자 장부이고 운영 team.py 장부가 아니다(설계 §1.1 표)".
  2. **운영 기준**
     - 판정 창 진행(처리 봉/63, 시작·예정 끝)
     - L 오류 수 = `errors.jsonl` 의 L 줄 ∪ `runs.jsonl` 끝 줄 종료 코드 2 (run_id 로 한 번), 사전 등록 ④ 거짓 양성은 빼고 따로, 끝 기록 없는 실행은 따로
     - 빠진 날(`calendar.jsonl` 마지막 줄의 날짜 목록 중 S~마지막 처리 봉 vs 하루 기록)
     - 늦은 봉 수와 한 번에 따라잡은 최대 봉 수
     - 다른 지문으로 처리한 봉 수(0 이어야 함)
     - 관문 거절 수
     - 자료 멈춤 수(종료 코드 4·7, 종류별)
     - 재시작·코드 변경·기업 행위(분할·상장폐지·정정 확정 따로 셈) 기록
     - 남은 재시작·마감까지 남은 날
  3. **값**
     - 두 장부의 평가액·수익률(S 이후, 그달)·MDD(S 종가부터 매일 종가 평가액, `metrics.max_drawdown`, R2 와 같은 방식)
     - **A1−A0**(금액, %p)
     - **지수 B&H(같은 시작)**: S+1 시가 소수 단위(§2.5)
     - 트레이너별 줄
  4. 주식·지수·현금 비율(그달 평균, 그달 마지막 날).
  5. 매매: 주식 매수·매도, 지수 매수·매도 수, 보류(0주·현금부족·팀장 hold·확신도 낮음), 빈자리 부족, 비용(수수료·슬리피지·세금, 주식/지수 다리 따로).
  6. **그림자 서킷**: (장부, 트레이너)별 첫 발동일·사유·발동한 날 수.
  7. **실현손익(참고값)**: 보고서 안에서 `fills` 로 평균원가법 계산, 그달·그해 누적, 주식/지수 따로. 미국은 "해외주식 양도세(연 250만 원 초과분) 인식용 참고값 — 달러 기준, 환율·신고 방식(선입선출 등) 미반영(미확인)"을 적는다. A1 은 지수를 자주 팔아 실현 이익이 늘 수 있다(R2 한계 3).
  8. **팀장**
     - 판정 수(buy/hold/veto/없음 × llm/폴백, 상태별)
     - 장부별 효과(veto, hold, 확신도 보류, 주문)
     - 폴백 비율. 20% 를 넘으면 "대표성 없음"(§2.2 ⑧)
     - CLI 버전·모델이 바뀐 날
     - 채점은 안 한다.
  9. **A0 현금 + 단기금리 이자(계산만)**
     - 식: `q_t = r_t/100/252`, `I_t = I_{t−1}·(1+q_t) + C_t·q_t`(C_t = A0 세 트레이너 종가 현금 합, S 날부터). "A0+이자" = A0 평가액 + I_t.
     - 금리 규칙
       - 미국(STAGE0-A1): H1 달력의 **전 거래일 날짜 이하** 마지막 DTB3 값. 전 거래일은 하루 기록의 `prev_cal_date` 로 읽는다(S 날도 같다).
       - 국내(STAGE0-A2): **m−1월 1일 이하** 마지막 IR3TIB01KRM156N 값, 없으면 이월.
     - 쓴 금리 날짜 표와 **금리 파일을 받은 시각**을 같이 찍는다.
     - **근사**임을 적는다: R2 A0 는 이자가 현금에 들어가 매수·서킷에 쓰이지만 여기서는 따로 쌓기만 한다. 금리는 보고서를 만들 때 가진 자료로 다시 계산한다(R2 와 같은 방식). 국내 월 금리는 발표가 1~2달 늦어 이월값이 섞이고, 나중에 다시 만들면 바뀔 수 있다.
     - **맥에서 금리 받기**
       - 주소: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3`, `...?id=IR3TIB01KRM156N`(API 키 없음, STAGE0 §2).
       - 받으면 `state/h1/rates/` 에 저장한다.
       - 첫 저장본은 재현이 R2 `data/rates/*.csv` 로 만들어 둔다(미국 2026-11-02, 국내 2026-09 까지).
     - **인터넷이 없으면**
       - 저장본을 쓴다. 필요한 날보다 짧으면 마지막 값을 이월하고(STAGE0-A1·A2 의 "없으면 직전 값") "(오프라인: YYYY-MM-DD 값 이월)"을 붙인다.
       - 저장본도 없으면 이 절만 "금리 자료 없음 → 계산 불가", 나머지는 그대로 만든다.
  10. **장부 다시 점검**: 저장 자료로 `h1_check.check_ledger` 를 다시 돈다. 결과(L 오류 0 이어야 함)와 **오프라인으로는 다시 못 보는 점검 번호**(L3·L6: 그날 시세 필요, D 등급 전부)를 적는다.
  11. **한계**: 배당 미포함, ETF 운용보수 없음, 생존편향(종목군), 3개월, 이자 근사.
- **`--final`**: S+62 를 처리한 뒤 운영 기준 ①~③의 통과/실패만 적는다. 수익률 숫자는 기록 절에만.
  - 창이 다 찼는데 연장 봉이 없어도 S+62 뒤 처리 중 난 L 은 "연장 구간" 절에 한 줄로 보인다(판정에는 안 씀).
  - `h1.py status`·실행 끝 요약은 같은 함수(`window_counts`)로 세며, 실행 끝 요약은 곧 쓸 자기 끝 줄(종료 코드 7 의 D7 포함)까지 센다. 창 크기는 `meta.rules` 값.

### 3.9 종료 코드 (`h1.py`)

| 코드 | 뜻 | 저장 |
|---|---|---|
| 0 | 정상(새 봉 처리, 또는 이미 처리됨) | 처리한 봉 |
| 2 | **장부 논리 오류**(L1~L24, 장부 파일 손상 L24 포함) | 그 봉 **안 함**. 재시작 대상 |
| 3 | 재현 미통과 코드·환경, 또는 규칙 상수가 시작 때와 다름(세율 줄 추가는 `amend-rules` 뒤 풀림) | 안 함 |
| 4 | **자료 문제**(D1~D6) | 그 봉 안 함. 다음 실행이 다시 |
| 5 | 잠금 30분 대기 초과 | 안 함 |
| 6 | 밀린 봉 5개 초과 → 창 실패 | 안 함. 재시작 대상 |
| 7 | 기준 지수 늦음(D7) | 처리할 수 있던 앞 봉까지는 저장. 알림 |
| 8 | 장부 없음(`start` 필요) / `start`·`restart` 거절(폴더가 사라짐, 장 시작 뒤 start, 재시작 상한 등) | 안 함 |
| 9 | 명령 인자 오류, `corp-action`·`amend-rules` 조건 불충족 | 아무것도 안 바뀜 |
| 1 | 파이썬이 `cli` 에 닿기 전에 죽음(import 실패 등) | 안 함 |
| 130 | 사람이 멈춤(Ctrl-C) | 안 함(다음 실행이 HEAD·백업으로 이어감) |

- 디스크 가득 참·권한 같은 **환경 문제**(`OSError`·`MemoryError`)는 종료 코드 4, `runs.jsonl` 에 `ENV` 로 남고 재시작 사유가 아니다. "예상 밖 예외 → 2"는 그 밖의 예외(코드 버그)만이다(2b-2 검토 C-1).

---

## 4. 하루 장부 점검 (`h1_check.py`)

```python
@dataclass(frozen=True)
class Problem:
    level: str            # "L" | "D" | "W"
    code: str             # "L1" … / "D1" … / "W1" …
    market: str; arm: str | None; trainer: str | None; date: str | None
    detail: str

def check_day(market, date, before: dict, after: dict, frames: dict, idle: IdleBar,
              calendar: list[str], halted: frozenset, decisions: DecisionLog,
              allowed: set[tuple[str, str]]) -> list[Problem]
    # allowed: L22 가 받아 주는 (code_hash, env 지문) 모음. 관문 실행은 replay_pass 에서 읽고,
    #          재현·시험은 "지금 재현 중인 지문" 하나를 넘긴다(2차 검토 R2-2)
    # before/after: {arm: {trainer: st}} — 그 봉 처리 전후. frames: 그 실행이 쓴 확정 시세
def check_pair(market, a0: dict, a1: dict, decisions) -> list[Problem]
def check_ledger(market, arm, states: dict, calendar: list[str], decisions, allowed=None) -> list[Problem]
    # 전체 기록을 저장 자료만으로 다시 점검(보고서·재현). L3·L6 은 frames 가 있을 때만
def errors(problems) -> list[Problem]     # level == "L"
```
- **쓰는 곳**: ① `h1.run`·`start` 가 봉마다 저장 직전에 ② 시험 ③ 재현(모든 봉) ④ 보고서(저장 자료로 다시).
- D 등급은 `h1.py` 가 준비 단계·봉마다 직접 판단하고, 같은 `Problem` 모양으로 `runs.jsonl` 에 남긴다.
- 허용 오차: 현금 `EPS_CASH = 1e-6`(달러/원), 비율 `EPS_REL = 1e-9`. 체결가 비교는 **정확히 같음**(같은 메모리 값, JSON `repr` 왕복).
- 점검은 지갑 로그(금액이 소수 2자리로 반올림됨)가 아니라 `fills`·`days` 를 쓴다.

**장부 논리 오류 (L) — 종료 코드 2, 운영 기준 ②-1**

| 코드 | 확인 | 1판 번호 |
|---|---|---|
| L1 | 모든 지갑 현금 ≥ −EPS_CASH | C1 |
| L2 | 보유 수량 > 0·유한, 주식 수량은 정수 값, 지수 단위 ≥ 0, `positions` ↔ `holdings`(주식) 수량 일치, 대기 자산 외에 `positions` 없는 보유 없음, `stopped == False` | C2 (+1판 C16 대신) |
| L3 | 체결마다 `price` == 그날 그 종목 행 Open(주식) / 그날 대기 자산 Open(지수). 예외는 `purpose="delist"` 뿐(L23 이 대신 봄) | C3 |
| L4 | 체결일 == 처리한 봉 t. 주식 다리(`purpose="delist"` 제외)는 신호일 < 체결일이고, 신호일 다음 처리 봉부터 체결일 전까지 **그날 하루 기록의 `halted` 에 그 종목이 있었다**(= 정지로만 기다렸다, 검토 I1 (나)) | C4 |
| L5 | 대기 목록에 같은 종목 주문 2개 이상 없음, 보유 종목의 매수 주문 없음, 없는 종목의 매도 주문 없음, (종목·방향·날짜) 체결 중복 없음, 보유 + 매수 대기 ≤ MAX_POSITIONS | C5 |
| L6 | 그날 `halted` 인 종목의 체결 없음, 체결 종목은 그날 확정 행이 있음(`purpose="delist"` 제외) | C6 |
| L7 | 하루 기록 `value` == 현금 + Σ주식×`marks` + 단위×지수 종가 == `wallet.value(가격표)` (EPS_REL) | C7 |
| L8 | 현금 원장: 전날 현금(S 는 0 + 입금) + Σ`cash_delta` == 오늘 현금(EPS_CASH). 단위 원장: 전날 단위 + 매수 − 매도 == 오늘 단위 | C8 |
| L9 | 비용식: 매수 `cash_delta = −(E·q + E·q·fee)`, 매도 `= E′·q − E′·q·fee − E′·q·tax` (E = P(1±slip)). tax = 국내 주식 `kr_sell_tax(체결일)`, 지수 0, 미국 0 | C9 |
| L10 | **A1**: S 날 현금 == start_cash·단위 0·체결 0. S+1 첫 체결은 `purpose="start"` 지수 매수. S+1 부터 종가 현금 < SWEEP_MIN. **A0**: 대기 자산 체결·보유 0 | C10 (S 예외 추가) |
| L11 | A1 지수 매도마다 `purpose="fund:X"` 이고 그날 X 매수가 성공, `short ≤ u·u_net ≤ short·(1+2e-9) + EPS_CASH`. "현금 부족" 보류된 매수에 쓰인 지수 매도 없음. **지수를 판 뒤 매수 실패 = 오류** | C11 (검토 m2) |
| L12 | "현금 부족" 보류마다 기록된 `need > avail`(A1 은 `avail·(1−1e-9)`), "0주" 보류마다 `shares_within_cap == 0` | C12 |
| L13 | 주식 매수 수량 == `shares_within_cap(start_cash, cap, price, fee, slip)` | C19 |
| L14 | 체결마다(`purpose="delist"` 제외) `order_id` 의 주문이 전날 끝에 `pending` 상태로 있었다. 주문 하나는 한 번만 체결·보류·버림 | C22 |
| L15 | 보유일수 == 매수일 뒤 처리 봉 중 그 종목이 `halted` 가 아니었던 봉 수 | C17 |
| L16 | 하루 기록 날짜 == `calendar.jsonl` 마지막 줄 날짜 목록의 S~t(빠짐·중복 없음), 하루 기록 `prev_cal_date` == 그 목록의 바로 앞 날짜, 두 장부 같음, 여섯 장부 `last_date` 같음 | C13 |
| L17 | 짝: A0·A1 같은 (날짜, 트레이너)의 `screened` 같음, 하루 기록 `leader` 의 같은 종목은 같은 열쇠·같은 판정, 그 열쇠가 판정 기록에 있음 | C14 |
| L18 | 판정 기록 추가 전용: 중복 열쇠 없음, HEAD 에 적힌 앞부분 지문 그대로 | C15 |
| L19 | 팀장 적용: veto 종목 주문 없음, hold·확신도 < 0.5 는 보류, 주문 순서 = `conviction or 0` 높은 순(같으면 스크리너 순서), 주문 수 ≤ 빈자리 | 새로(검토 §2-5) |
| L20 | 그림자 서킷 사건 == 하루 기록 `value` 로 다시 계산한 결과(§2.6) | 새로 |
| L21 | 모든 숫자 유한(NaN·inf 없음) | C24 |
| L22 | 종목군 파일 지문 == `meta.universe_sha256`, 하루 기록 (`code_hash`, `env`) ∈ `allowed`(관문 실행은 `replay_pass`, 재현·시험은 지금 재현 중인 지문). `meta.rules` 불일치는 L 이 아니라 준비 4 의 종료 코드 3 | C25 |
| L23 | 상장폐지 정리(`purpose="delist"`): `corp_actions` 에 그 종목 `delist` 등록이 있고, 체결일 > 등록 `last_date`, 가격 == 등록 `last_close`, 수량 == 그 직전 보유 전량, 비용식은 L9(그 날짜 세율), 정리 뒤 `positions`·`holdings`·대기 주문에 그 종목 없음, 두 장부가 같은 날 정리 | 새로(2차 R2-3) |
| L24 | 장부 파일 손상: HEAD·백업 모두 sha256 불일치, JSON 깨짐·형식(schema) 다름, 판정 기록 마지막이 아닌 줄 깨짐 | 새로(2차 R2-11) |

**자료 문제·지연 (D) — 그 봉 저장 안 함, 재시작 아님(§2.2 ④)**

| 코드 | 확인 | 종료 코드 |
|---|---|---|
| D1 | 대기 자산 시세를 못 받음 | 4 |
| D2 | 보유·대기 종목 시세를 못 받음(인수·상장폐지 의심 포함 → §2.2 ⑦) | 4 |
| D3 | 보유·대기 종목(`--delist` 등록 제외)에 t 확정 행이 없고 국내 원본 거래량 0 행(정지)도 아님, 또는 대기 주문 종목의 t 확정 행 시가가 None → 자료 미준비 | 4 |
| D4 | 달력 바뀜: 이미 처리한 날짜가 새 달력에 없음(FDR 연도 파일 누락 등), 또는 이미 처리한 구간에 새 날짜가 끼어듦 | 4 |
| D5 | 달력 구멍: 새로 처리할 구간에 종목군 절반 이상이 거래한 날이 달력에 없음 | 4 |
| D6 | 소급 수정: 보유 종목(`--delist` 등록 제외)의 매수 체결가(`fills.price` vs 새 시세의 그 날짜 Open)·최근 5일 `marks`(vs 새 시세에서 **그 날짜 이하 마지막 확정 종가** — 정지일이면 정지 전 마지막 종가), 대기 자산 최근 5일 시가·종가가 새로 받은 값과 상대 1e-6 넘게 다름. 비교 전에 기록된 기업 행위를 반영한다(분할: 그 날짜 전 기록 가격 ÷ r, 정정 확정: 적어 둔 새 값). 모든 날짜에서 같은 비율로 다르면 "분할 의심(비율 r)"으로 알림 | 4 |
| D7 | 기준 지수 늦음: 확인용 대형주의 최신 확정 봉 > 달력 마지막 봉이고, 지금이 그 봉의 기준 지수 확정 시각(국내 22:30 KST, 미국 16:15 ET) 뒤 | 7 |

**경고 (W) — 멈추지 않음**

| 코드 | 내용 |
|---|---|
| W1 | 늦은 봉(`late`) |
| W2 | 정지(국내 `halted`, 정보) |
| W3 | 팀장 폴백(`status != "ok"`) |
| W4 | 종목군에만 있는 종목 시세를 못 받음 |
| W5 | 확인용 대형주(`CAL_PROBE`) 시세를 못 받음 → D7 판단 불가 |

- 모든 L 점검은 **넣기 전에** 두 가지를 통과해야 한다. (a) 그 잘못을 일부러 넣은 장부로 그 코드가 나는 음성 대조 — 코드마다가 아니라 **코드 안의 규칙마다**. (b) 재현 W1·W2 창과 합성 정지에서 거짓 양성 0.
- **정각 경계**: 봉 처리 시작이 `next_open(t)` 정각이면 늦은 봉, LLM 호출 직전이 정각이면 묻지 않음, D7 은 22:30:00(국내)·16:15:00(미국) 정각부터, `start` 는 `next_open(S)` 정각부터 거절.

---

## 5. 재현 계획 (단계 5) — `h1_replay.py`

### 5.1 기준값 (R2, 운영 시작 규칙)

1. `git archive origin/research-r2-2026-11-04` 를 **임시 폴더**에 푼다. 연구 브랜치는 읽기만 하고 절대 안 고친다.
2. 그 폴더 안에 하네스 파일을 써 넣고 `python -I` 로 돌린다. 하네스는 처음에 `main.__file__`·`sim_team.__file__` 이 임시 폴더 안인지 확인한다(지금 저장소 모듈을 잘못 읽으면 기준값이 아니게 됨, §7 R22).
3. **운영 시작 규칙 하위 클래스**(하네스 파일 안에서만, 검토 probe1 `Q8Sim` 을 넓힌 것)
   ```python
   class OperatingStartSim(sim_team.TeamSim):
       def _sweep_to_index(self, s, t):
           if t == self.i0:                 # S: 입금만, 쓸어 담기 없음
               return
           return super()._sweep_to_index(s, t)
       def _open(self, t):
           if t == self.i0 + 1:             # S+1: 주문 전에 현금 전부 지수
               for s in self.sleeves:
                   if s.mode(self.md, t) == "index":
                       super()._sweep_to_index(s, t)
           super()._open(t)                 # 그다음 평소 순서: 매도 → 매수 → 쓸어 담기
   ```
   - A0 는 대기 자산이 현금이라 이 하위 클래스로 바뀌는 것이 없다.
   - `run()` 대신 `OperatingStartSim(md, cfg, i0, i1).run()` 을 직접 부른다(`sim_team.run` 의 참고선 계산은 쓰지 않음).
   - 지수 B&H 는 `index_buy_hold_fractional(md, i0+1, i1, total)`.
4. 설정: `interest=False`, `cb="none"`(비교 본체)과 `cb="current"`(그림자 비교 M5′ 용 사건 날짜만).
5. 저장: `fills`, `skips`, `orders`, `events`, `daily`(트레이너별 `v_`·`cash_`·`stock_`·`index_` + 지수 단위), B&H equity → JSON.
6. **참고만**(통과 조건 아님): 원래 sim_team(S 시가 전부 지수)과 하위 클래스의 차이(체결 열쇠 수, 끝값)를 보고서에 적는다. 운영 코드에는 S 시가 옵션이 없다.

### 5.2 창

| 창 | 내용 | 필수 |
|---|---|---|
| **W1** | 2026-06-01 ~ 2026-11-03, 미국(R0 20종목 + SPY)·국내(KR_UNIVERSE 32 + KS200) × A0·A1 = H1 4개. 기준값 `cb="none"` 4개 + `cb="current"` 4개 | 예 |
| **W2** | **국내 2018-03-01 ~ 2018-12-31**(실제 S = 2018-03-02, 204봉) × A0·A1 = H1 2개. 기준값 `cb="none"` 2개 + `cb="current"` 2개.<br>장부마다 정지를 가로지른 보유 2건(005930 2018-04-30~05-03, 207940 2018-11-15~12-10)이 있다. 국내 매도세 0.30%(Q9 표 = R2 표라 K 처리 불필요) | 예 |
| **W3** | **합성 차등 재현**: 같은 합성 시세·같은 가짜 브레인(정해진 날에만 매수/매도 신호)을 기준값(`OperatingStartSim`, `sim_team.MarketData(..., brains=가짜)` 로 만든 md)과 H1(합성 `DataSource`, 하네스 프로세스 안에서만 `team.BRAINS` 와 `screener.BRAINS` 를 **둘 다** 같은 가짜로 바꾸고 `scan_frames(brains=가짜)` 로 부름)에 넣는다. 가짜 브레인은 파일 하나(`h1_replay.py` 가 만듦)를 R2 임시 폴더에도 복사해 두 프로세스가 같은 코드를 읽는다(2차 검토 R2-6). 장면은 아래 6가지 | 예 |

W3 장면
- (s1) 국내 대기 매수가 3일 정지(원본 Volume=0 행)를 가로지름. 실데이터에는 이런 경우가 0건이다(검토 probe2).
- (s2) 보유 종목이 정지를 가로지르고, 정지 전날 매도 신호가 남.
- (s3) 같은 날 매도 + 매수.
- (s4) A1 현금 부족 보류.
- (s5) 쓸어 담기 문턱 근처(현금 0.99·1.00).
- (s6) 국내 세율 경계일(2019-06-03·2021-01-01 등) 전날·당일 매도, 그림자 서킷(하루 −7%·누적 −10%).

"지수 전 단위 매도"·"지수 판 뒤 매수 실패"는 여유값 때문에 일어날 수 없는 길이라(검토 probe1: 0건) 장면에 넣지 않는다. 생기면 L11 오류다.

### 5.3 새 코드 쪽
- `h1.start` → `h1.run` 을 **하루에 한 번씩** 부른다(맥에서 매일 도는 것처럼).
  - 임시 장부 폴더(`root=<임시>/h1`), `leader_mode="replay"`, 관문은 끈다.
  - 매일 저장·읽기(커밋 지점 포함)를 거친다.
  - 같은 날 **두 번** 부르고, 두 번째에는 장부 6개·meta·HEAD·backup·판정 기록이 안 바뀌어야 한다(M9, 실행 일지는 줄이 더해짐).
  - L22 의 허용 지문(`allowed`)은 지금 재현 중인 (`code_hash`, `env`) 하나를 넘긴다(관문을 끄므로 `replay_pass` 를 보지 않음).
- `DataSource`: 연구 브랜치 `data/` 를 읽어 **그날 b 이하로 자른 뒤** `fetch` 와 같은 단계(원본 → `main.confirmed_bars` → 정지 날짜)를 거친다. 지표용 시작은 R2 처럼 처음부터.
- **`now` = 실제 운영 시각**(검토 I9): 국내 b 23:05 KST(22:30 규칙을 지나 KS200 b 행이 남음), 미국 b 다음 평일 07:10 KST(= b 17:10 EST / 18:10 EDT). 그래서 `late=false` 이고 확정 시각 규칙을 운영과 같은 조건으로 지난다.
- 종목군은 R2 와 같게 **강제**한다: 미국 = `data/us/universe.json` 순서(SPY 제외), 국내 = `markets.KR_UNIVERSE` 순서(R2 브랜치의 `KR_UNIVERSE` 와 같은 32개·같은 순서인지 먼저 확인).
- 금리 첫 저장본: R2 `data/rates/*.csv` 를 `state/h1/rates/` 에 복사해 둔다(이미 있으면 그대로).

### 5.4 반드시 같아야 하는 것

| # | 항목 | 같음의 뜻 |
|---|---|---|
| M1 | 체결 | (트레이너, 날짜, 주식/지수, 종목, 매수/매도) 모음이 정확히 같다. 짝마다: 주식 수량 같음(정수), 지수 수량 상대 차 ≤ 1e-9, 체결가 **정확히 같음**, 현금 변화 절대 차 ≤ 1e-6 |
| M2 | 보류 | (트레이너, 날짜, 종목, 종류 0주/현금부족) 모음이 같다 |
| M3 | 주문 | H1 `orders` 의 (트레이너, 신호일, 종목, 매수/매도, 사유 글) 모음 == R2 `orders`(K1 제외) |
| M4 | 매일 값 | 날짜 × 트레이너마다 종가 평가액·주식 평가액·지수 평가액·지수 단위는 상대 차 ≤ 1e-9. **현금은 절대 차 ≤ 1e-6**(쓸어 담기 뒤 1e-8 수준이라 상대 비교는 1ulp 에도 깨짐, probe4). 팀 합계도 같은 기준 |
| M5′ | 그림자 서킷 | (장부, 트레이너)마다 H1 그림자 첫 발동일 == 기준값 `cb="current"` 사건 날짜(창 마지막 봉 제외), 둘 다 없으면 같음 |
| M6 | 지수 B&H | 보고서 함수의 "같은 시작 지수 B&H" 매일 값 == `index_buy_hold_fractional(md, i0+1, i1, total)` equity. 마지막 날은 R2 가 매도 비용을 뺀 값이라 단위 × 종가로 비교 |
| M7 | 이자 계산 | 보고서의 `rate_for_days` 와 이자 식을 R2 `sim_team.rate_for_days`(같은 달력·R2 금리 파일)로 따로 계산한 값과 비교: 날마다 금리 같음, 이자 상대 차 ≤ 1e-9. (참고로만: "A0+이자" 끝값과 기준값 A0 `interest=True` 끝값의 차이) |
| M8 | 장부 점검 | 재현 장부 전체에 `check_ledger` L 오류 0, 매일 `check_day` L 오류 0(L22 는 지금 재현 중인 지문으로), D 등급 0. W 는 W2(정지), W3(팀장 기록이 모두 `replay_no_llm` 이라 후보 있는 날마다 남), W4(W2 창에서 아직 상장 전인 316140·329180·402340·373220)만. 재현 보고서는 ⑧ 폴백 비율 대신 "재현은 팀장 끔" 고정 문장을 찍는다 |
| M9 | 멱등·저장 | 하루 두 번째 실행에서 장부 6개·meta·HEAD·backup 의 파일 sha256 그대로·판정 기록 줄 수 그대로. 저장 → 읽기 뒤 지수 단위가 `float.hex` 까지 같다. 같은 코드로 재현을 두 번 돌리면 `ledger_fingerprint` 가 같다 |

### 5.5 받아들이는 차이 (이 목록 밖의 차이는 설명하거나 고친다)

| # | 차이 | 처리 |
|---|---|---|
| K1 | R2 는 창 마지막 봉에서 **판단 자체를 하지 않는다**(sim_team `t < self.i1`, I17): 매도 판단·서킷·신규 후보·over_slots | 마지막 봉에 생긴 것 전부(주문·over_slots·그림자 서킷 사건·팀장 효과)를 비교에서 뺀다. 체결·매일 값은 마지막 봉 포함 |
| K2 | R2 `final`·`metrics` 는 끝에 매도 비용을 뺀 값, H1 은 종가 평가 | 매일 종가 평가액만 비교(M4) |
| K3 | 종목군: 재현은 R2 종목군을 강제한다. 운영 미국은 S 날 고정 S&P500 섞기 40종목(Q7) | 재현 안에서는 차이 아님. 운영 목록 고정은 시험 T-UNIV 가 맡는다 |
| K4 | 스크리너 70봉 기준(H1) vs R2 60봉(A7, R11) | W1·W2 모두 창 시작 때 70봉이 안 되는 종목이 없고 창 안 신규 상장도 없다(확인함). 재현이 매번 다시 확인 |
| K5 | 스크리너 "오래된 봉" 기준은 그 스캔의 최근 봉, R2 는 "그 종목 오늘 봉 있음" | 재현이 매일 "스캔 최근 봉 == t" 를 확인하면 같음 |
| K6 | team.py 의 "저장 안 하는 날"·"이미 처리됨" | H1 은 매일 저장·봉마다 처리 → R2 와 같은 쪽. 운영 장부와의 차이로만 적음 |
| K7 | 현금 이자: R2 기본은 켬 | 기준값을 `interest=False` 로 돌림(이자는 M7 로 따로) |
| K8 | 판정 기록·하루 기록의 팀장 칸 | R2 에 없음. LLM 끔이라 모두 `replay_no_llm` → 비교 대상 아님 |
| K9 | 국내 매도세 | 둘 다 날짜별 표(2018 0.30%, 2026 0.20%) → 차이 아님 |
| K10 | 지표 계산 길이: 운영은 2024-06-01 부터, 재현은 처음부터 | 재현은 R2 와 같게 처음부터. 운영과의 차이는 무시할 크기(검토가 직접 계산: RSI 차 ≤ 2.1e-14), 시험 T-RSI |
| K11 | R2 `over_slots` 는 트레이너 합계, H1 은 하루 기록 | 합계만 비교(K1 뺀 뒤 같아야 함, 참고) |
| K12 | 부동소수점 더하는 순서 | M1·M4 의 허용 오차 안 |
| K13 | 시작 규칙 | 기준값이 하위 클래스(운영 규칙)라 차이 아님. 원래 sim_team 과의 차이는 참고로만 적음(§5.1-6) |

### 5.6 통과 조건과 기록
- W1 4조합·W2 2조합에서 M1~M9(M5′ 포함)가 모두 맞고, W3 6장면에서 M1~M5′ 가 맞고, 남은 차이가 K1~K13 으로만 설명되면 **통과**다. 설명 안 되는 차이가 하나라도 있으면 통과가 아니다.
- 통과하면 잠금 아래에서 `replay_pass.json` 에 `{code_hash, files, env, ledger_fingerprints(W1-us·W1-kr·W2-kr 마다 끝난 장부 6개의 `ledger_fingerprint`), fingerprint_version, passed_at, report}` 를 더한다. 보고서는 `state/h1/reports/replay-<날짜>.md`.
- `ledger_fingerprints` 는 코드 동결 중 허용 변경 판단(§2.2 ⑥-i·ii)과 점검 함수 거짓 양성 판단(④-가)에 쓴다. 장부 **내용** 지문이라 `code_hash`·`env` 가 바뀌어도 매매가 같으면 같다(2차 검토 R2-1).
- 맥에서도 돌린다: H1 전용 worktree·venv, 인터넷 불필요, `git fetch origin research-r2-2026-11-04` 는 필요. 코드·환경을 바꿀 때마다 다시 돌린다(②-3).

---

## 6. 시험 계획 (오프라인, 합성 데이터)

- 모두 `pytest -q` 에 들어가고 인터넷·claude·키 없이 돈다. 시세는 `test_flow.synth` 같은 결정적 가짜 시세, 장부 폴더는 `tmp_path`.
- 시계는 시간대 있는 고정 시각을 쓴다(한국 시간 기준 장면 포함).
- 바꿔 끼우는 곳은 **입출력 경계로만** 한정한다: `FinanceDataReader`, `shutil.which`/`subprocess.run`, `STATE_DIR`·`H1_DIR`, 시계.
- 기존 306개 시험은 한 줄도 고치지 않는다.

| ID | 규칙 | 시험 |
|---|---|---|
| T-F1a | F1 경로 | 6개 경로 모양, `state/h1` 밖 경로는 예외 |
| T-F1b | F1 격리 | 가짜 `state/team_*.json`·`state/kr/*` 를 두고 H1 을 돌림 → 그 파일 지문·수정시각 그대로. `team._load`·`team._save`·`main.load_state_file` 은 불리면 실패하게 바꿔 끼움 |
| T-F2 | F2 | 새 장부 총액·몫·시작 예산 기준 상한, MAX_POSITIONS(대기 매수 포함), 확신도 0.5 경계·None 통과·문자열 확신도, hold 보류, veto 빠짐을 H1 두 장부로 |
| T-START | Q8 시작 | S: 두 장부 입금만·체결 0·A1 현금 = 시작 금액(L10 예외 통과). S+1: A1 첫 체결 `purpose="start"` 단위 = 현금/(Q(1+s)(1+f))·(1−1e-12), 그다음 S 종가 주문을 `fund:` 지수 매도로 체결, 남은 돈 쓸어 담기 — 손계산과 같음. A0 는 평소대로. 지수 B&H 가 S+1 시가에서 시작 |
| T-A1-2 | 같은 시가 순서 | 한 날에 매도 1·매수 2: 매도 대금 먼저, 모자란 만큼만 지수 매도, 남은 돈 지수로 — 손계산과 같음 |
| T-A1-3 | 현금 부족 | need > 현금+지수: "현금 부족" 보류, 그 매수용 지수 매도 0, 단위 그대로 |
| T-A1-4 | 경계 여유 | need = avail·(1−1e-9) 근처 위/아래. 지수 판 뒤 매수 실패를 억지로 만들면 L11 오류·종료 코드 2 |
| T-A1-5 | 쓸어 담기 문턱 | 현금 0.99 는 그대로, 1.00 은 지수로. 줄임 1e-12 실패 → 1e-9 성공 경로 |
| T-A1-6 | 비용·세율 | 미국·국내 지수 매수·매도 수수료+슬리피지, 국내 지수 매도세 0, 국내 주식 매도세 = 표(세율 경계일 전날·당일), `sell(tax_rate=…)` |
| T-A1-7 | 소수 단위 | 저장 → 읽기 `float.hex` 같음, 정수 주식은 int 로 돌아옴, 화면 6자리, `Holding` 표기 |
| T-A1-8 | A0 대조 | A0 는 지수 체결·보유 0 |
| T-SIG | 신호 t → 체결 t+1 (v1 결정 D3) | 두 장부 모두 체결 날짜·시가 |
| T-F4 | 대기 자산 | 코드 = 벤치마크, 국내는 `allow_index` 경로로만 받음, 시가·종가가 그 시세 값 |
| T-F5a | 같은 판정 | 가짜 analyze 가 호출마다 다른 답을 내도 A0·A1 이 같은 (날짜, 트레이너, 종목)에 같은 판정 |
| T-F5b | 없을 때만 호출 | 호출 횟수 셈. 같은 봉 두 번째 실행 → 0번. A1 은 A0 에 없던 후보만 |
| T-F5c | 폴백 종류 | claude 없음·시간 초과·0 아닌 종료·JSON 깨짐·답에서 빠진 종목 → 각 `status`, 규칙 폴백 동작 |
| T-F5d | 글자 정리 | `" VETO"`·`"Hold"` → H1 에서 veto·hold 로 동작. 운영 `analyst.apply` 는 그대로 |
| T-JSONL | 판정 기록 | 추가 전용, 장부보다 먼저 fsync. 장부 커밋 전에 꺼짐 → 남은 줄을 다음 실행이 재사용(LLM 0번). 반쯤 쓴 마지막 줄은 잘라 냄. 중복 열쇠·지난 줄 수정 → L18 |
| T-LLMTIME | LLM 시각(I6) | 국내 08:59 KST 실행 → llm, 10:00 KST 실행(KS200 오늘 봉 없음 → 어제 봉) → late·LLM 0번. 미국 09:29/09:31 ET 같은 경계 |
| T-F6a | order_runner 격리 | `state_path("us"\|"kr", 트레이너)` 가 `state/h1` 아래가 아님 |
| T-F6b | 〃 | `STATE_DIR` 을 tmp 로, 그 안에 대기 주문 있는 H1 장부만 → `load_states` 빈 결과, `place(FakeBroker)` 주문 0건 |
| T-F6c | 〃 | `order_runner.py` 소스에 `h1` 없음, `h1*.py` 가 `order_runner`·`broker` 를 import 하지 않음 |
| T-ENTRY | 진입점(I8) | team.py 에 `--h1` 처리 코드가 없음, `team.run`·`run_trainer(h1=None)` 경로에서 `h1` 이 `sys.modules` 에 없음, `h1.py run` 은 장부 없으면 8 |
| T-GOLD | `h1=None` 바이트 같음 | **골든**: 코드를 바꾸기 전 커밋(847ad13)으로 만든 결과(상태 JSON·화면 출력)를 `tests/golden/` 에 두고, 바꾼 코드 결과가 바이트까지 같음.<br>장면(여러 날): 미국·국내 각각 ① 후보·팀장 buy/hold/veto/낮은 확신도/문자열 확신도 ② 다음날 체결 ③ 매도 ④ 같은 봉 다시(멱등) ⑤ 후보 없는 날(저장 안 함) ⑥ 서킷 발동 ⑦ 국내 정지 대기·보유 판단 쉼·오래된 후보 제외 ⑧ KS200 22:30 전후 ⑨ team ①② 의 드문 가지: 보유·대기 종목 시세 받기 실패, 시가 없는 행, 버려지는 주문(이미 보유 매수·보유 없는 매도), 대기 주문 있는 보유 종목, 벤치마크 받기 실패(2a 검토 A-2). `scan()` 결과도 골든.<br>골든 파일은 `.gitignore` 의 `state/` 예외(`!tests/golden/**/state/`)로 커밋하고, 시험이 파일 수를 단언한다(2a 검토 A-1). 골든은 `requirements-h1.txt` 의 라이브러리 버전 기준 |
| T-F7 | 같은 스크리너·멱등 | 봉마다 `scan_frames` 1번, 두 장부가 같은 후보. 같은 봉 두 번 → 장부 6개·meta·HEAD·backup·판정 기록 sha256 그대로(`runs.jsonl`·`calendar.jsonl` 은 줄 추가) |
| T-SCR | 스크리너 | `scan_frames` asof 로 자른 결과 == 미리 자른 시세 결과 |
| T-FETCH | 시세 받기 | `h1.fetch` 의 확정 시세 == 같은 가짜 fdr 로 `main.load_prices`, 국내 정지 날짜 = 원본 Volume=0 날짜 |
| T-SHADOW | 그림자 서킷 | 하루 −7%·누적 −10% 경계 위/아래, prev 는 전날 day row(team `prev_value` 를 일부러 다른 값으로 바꿔도 결과 같음), S 날 prev=None, `events` 에 기록, 장부 바뀌지 않음(`stopped` False·정리 주문 0), 보고서 첫 발동일 |
| T-F8a | 보고서 숫자 | 손으로 만든 장부로 평가액·수익률·MDD·A1−A0·지수 B&H(S+1)·비율·매매 수·비용·실현손익(평균원가 손계산)·팀장 수·폴백 20% 표시·운영 기준 칸(늦은 봉·빠진 날·관문 거절) |
| T-F8b | 금리 규칙 | 미국 전 거래일(빈 날 이월, 그날 값은 다음 날, S 날은 저장 달력의 전 거래일), 국내 m−1월(빈 달 이월), 이자 식 손계산 |
| T-F8c | 오프라인 | `urlopen` 이 실패하게 → 저장본 사용·"오프라인" 표시. 저장본 없음 → 그 절만 "계산 불가", 파일은 만들어짐 |
| T-L | L 음성 대조 | L1~L24 마다 그 잘못을 일부러 넣은 장부 → 그 코드로 오류 |
| T-FP | 장부 내용 지문 | `code_hash`·`env`·`run_at`·`late`·`mode`·`late_calls`·`h1` 머리만 바꾼 장부 → 지문 같음. 체결 수량·현금을 1ulp 바꾼 장부 → 지문 다름. 순서가 다른 dict 키 → 같음 |
| T-D | D 등급 | D1~D7 마다 그 상황 → 종료 코드 4/7, 그 봉 저장 안 함, `errors.jsonl`·`restarts.jsonl` 에 아무것도 안 생김, 다음 실행이 정상 처리 |
| T-HALT | 국내 정지 | 합성 국내 시세에 Volume=0 3일: 대기 매수는 정지 중 체결 0 → 첫 거래된 봉 시가 체결. A1 은 그날만 지수 매도. 보유 종목 판단 쉼·보유일수 그대로·마지막 종가 평가. 정지 종목 후보 제외. 저장/읽기 거침 |
| T-LATEDATA | 자료 지연(I1) | 보유 종목 t 행이 첫 실행엔 없고(원본에도 없음) 다음 실행엔 생김 → 첫 실행 D3·종료 코드 4, 다음 실행이 t 를 정상 처리, L4·L15 오류 없음. 국내 원본 Volume=0 행이면 정지로 진행 |
| T-RETRO | 분할(I5) | 산 날 장 마감 뒤 분할 적용 경계(`>=`)에서 L 없음(단계 3 T-2). 새로 받은 시세의 지난 가격을 ÷2 → D6·"분할 의심 r=2"·종료 코드 4. `corp-action --split 2` 뒤 두 장부 주식 수 ×2·매수가 ÷2·평가액 그대로, 다음 실행 정상. 국내 정지일 `marks` 는 정지 전 마지막 종가와 비교해 D6 이 안 남(T-HALT 장면 위에서) |
| T-DELIST | 상장폐지(2차 R2-3) | 세율 구간이 다른 두 날짜로 "정리 봉 날짜 세율" 확인(단계 3 T-8). 보유 종목 시세를 **못 받는** 상태(D2)에서 `--delist --last-date D --last-close P` → 다음 run 이 D2·D3·D6 없이 진행, 두 장부 같은 날 P 로 전량 정리·비용 손계산·대기 주문 dropped, L23 통과·L3/L4/L6/L14 오류 없음. 가격을 바꾼 정리 체결 → L23 오류 |
| T-CORR | 정정 확정(2차 R2-4) | 지난 종가 하나를 바꾼 시세 → D6. `--accept-correction` 뒤 장부 그대로·다음 run 정상·`corp_actions` 에 옛 값·새 값 |
| T-AMEND | 세율 줄 추가(2차 R2-5) | 표 뒤에 줄을 더한 상수 → run 종료 코드 3·저장 안 함. `amend-rules` 뒤 정상. 앞줄을 바꾼 표 → `amend-rules` 거절 |
| T-CAL | 달력(I4) | 이미 처리한 날짜가 빠진 달력 → D4. 대형주 새 봉 + KS200 없음, 22:29/22:31 KST → 22:31 만 D7(종료 코드 7, 앞 봉은 저장). 2026-12-30 → 2027 첫 봉 연도 파일 늦음 장면 |
| T-CUT | 국내 확정 시각 | 20:00 KST(종목 오늘 봉 있음, KS200 오늘 봉 버림) → 어제 봉만 처리, 오늘 날짜 후보·주문 없음. 22:31 KST → 오늘 처리 |
| T-DST | 미국 서머타임 | 2026-03-08·11-01 앞뒤, 한국 시각 07:10 실행 → 바로 전 미국 거래일이 확정 봉, `next_open` 계산 |
| T-LATE | 따라잡기 | 2봉 밀림 → 차례로 처리(각 봉은 그 날짜 이하 자료), `late` 표시·폴백. 6봉 밀림 → 종료 코드 6 |
| T-LOOK | 미리보기 없음 | 봉 t 를 전체 시세로 처리 == t 에서 자른 시세로 처리. t 의 종가·고가·저가·거래량과 그 뒤 봉을 흔들어도 t 시가 체결·t 전날까지 기록 그대로 |
| T-GATE | 관문 | 지문·env 다름 → 종료 코드 3, 파일 0개 씀(`runs.jsonl` 에는 기록). `meta.rules` 다름 → 3 |
| T-LOCK | 잠금 | 잠금 중 두 번째 명령(run·start·restart·report·status) → 기다림, 시간 초과(가짜 시계) → 5 |
| T-RESTARTN | 재시작 수(단계 3) | status·`restart` 상한·보고서가 같은 `restart_info` 규칙, archive 폴더만 2개여도 상한에 걸림 |
| T-HEAD | 커밋 지점 | 백업이 HEAD 와 한 글자라도 다르면 되살리지 않고 L24·2(단계 3 T-1). 6개 중 3개 교체 뒤 멈춘 상황 → 다음 실행이 백업(`backup/<run_id>/`)으로 되살려 다시 처리, 끊기지 않은 실행과 결과 같음. 같은 `last_date` 에서 `corp-action` 한 뒤 다음 봉 커밋 도중 멈춤 → 백업이 corp-action 뒤 상태와 맞음. HEAD 와 백업이 모두 안 맞음 → L24·종료 코드 2 |
| T-STRICT | 깨진 장부 | JSON 깨짐·형식 다름 → 2. 보관·새로 시작 **안 함**(운영 `load_state_file` 과 다름, 할 일 3번) |
| T-NEWSTART | 명시 시작(m7) | 폴더 있음 → start 거절. 폴더가 없는데 재시작 기록 없이 `runs.jsonl` 에 성공한 start 흔적 → 거절(8). restart 뒤 start 는 됨. `start` 가 `<m>.starting/` 에 쓰다 멈춤(D1 등) → `<m>/` 없음, 다음 start 가 지우고 다시 함(재시작 아님) |
| T-UNIV | 종목군(Q7) | 미국 S 날 `screener.universe(40)` 목록·순서 저장, 다음날 S&P 목록이 바뀌어도 같은 목록, 재시작해도 첫 목록, 파일을 고치면 L22 |
| T-ORDERS | 주문 기록(I9) | 매도 신호·후보·보류·이미 보유·보유 없음 주문이 `orders` 에 생기고 상태가 맞게 바뀜 |
| T-PW | 지갑 | `sell(tax_rate=None)` 은 지금과 같음(기존 시험 그대로 통과), `tax_rate=0.0` 은 세금 0 |
| T-AN | 팀장 래퍼 | `analyze_logged` 상태별(which·subprocess 바꿔 끼움), 프롬프트 문자열 == `_build_prompt`, `analyze` 결과 == `analyze_logged(...)[0]`(정상 답에서. "analysis" 가 목록이 아닌 답·디코드 실패는 위 차이), `asked_at`·`elapsed_s` 의 뜻, `analyze_logged` 안에서 `--version` 을 안 부름 |
| T-RSI | 지표 길이 | 2024-06-01 부터 계산한 RSI 와 처음부터 계산한 RSI 의 2026-06 이후 차 < 1e-9 |

---

## 7. 위험 목록 — R2 와 조용히, 또는 운영 중에 어긋날 수 있는 곳

| # | 위험 | 왜 위험한가 | 막는 법 / 시험 |
|---|---|---|---|
| R1 | 같은 시가 순서 | 매수를 매도보다 먼저 하면 지수를 괜히 팔아 왕복 비용이 생긴다. 정지로 밀린 옛 매수가 앞에 있으면 결과가 바뀐다 | 매도 → 매수 → 쓸어 담기로 고정. T-A1-2, W3(s3), M1 |
| R2 | 쓸어 담기 문턱 | `≥ 1` 을 `> 1` 로 쓰거나, 매수 없는 날에 빼먹는다 | 상수 하나, T-A1-5, L10, M4 |
| R3 | 여유값 1e-9 | 빼면 경계에서 지수만 팔고 매수가 실패한다(R6) | `SHORT_MARGIN`, T-A1-4, L11·L12 |
| R4 | 반올림 | 지수 단위를 저장·표시 때 반올림하면 원장이 어긋난다. `int()`·`round()` 로 바꾸는 곳 | 저장은 float 그대로, 화면만 6자리. T-A1-7, L8 |
| R5 | 비용·세율 | 국내 지수에 주식 매도세를 붙이거나, 세율 표 경계를 틀린다 | `sell(tax_rate=)`, 표 하나, T-A1-6, W3(s6), L9 |
| R6 | 시작(Q8) | S 체결, S+1 순서, B&H 시작점이 어긋나면 비교가 틀어진다. 이 경로는 재시작마다 한 번만 돈다 | §2.5 한 가지 규칙, L10 예외, T-START, 기준값 하위 클래스(W1·W2 첫 이틀 M1·M4·M6) |
| R7 | KS200 22:30 vs 종목 16:00 | 16:00~22:30 실행이면 종목만 하루 앞서 장부 날짜와 신호 날짜가 섞인다 | asof 자르기, T-CUT |
| R8 | 미국 서머타임 | launchd 는 한국 시각으로 돈다 | `confirmed_bars`·`next_open` 은 ET 기준, 07:10 KST 는 사계절 모두 마감 뒤, T-DST |
| R9 | 빠진 날 | 맥이 꺼지면 그날 신호가 사라진다 | 봉 하나씩 따라잡기·상한, L16, T-LATE |
| R10 | 두 장부 판정이 다름 | 따로 물으면 같은 종목에 다른 답이 온다 | 판정 기록 열쇠, L17, T-F5a |
| R11 | 기존 장부 건드림 | `_load` 가 `state/team_*.json` 을 읽거나 예전 형식으로 보관한다 | G0 예외, 경로 확인, 전용 worktree, T-F1b |
| R12 | order_runner 가 H1 장부로 주문 | 모의 계좌에 주문이 나간다 | 경로가 다름 + T-F6 |
| R13 | `h1=None` 동작 변화 | 운영 장부 결과가 바뀐다 | 갈고리만, 골든 T-GOLD |
| R14 | 지수 평가 누락 | `PaperWallet.value` 는 가격표에 없는 종목을 **평균 매입가**로 평가 → 평가·그림자 서킷이 조용히 틀린다 | G2, `value()` 전에 모든 보유 가격 키 확인(assert), L7 |
| R15 | 그림자 서킷 prev 값 | team.py 가 `prev_value` 를 덮어쓴 뒤 읽으면 하루 변화가 0 이 된다 | 전날 day row `value` 사용, L20, T-SHADOW, M5′ |
| R16 | 소급 수정·분할 | 장부 매수가·주식 수와 새 시세가 어긋나 가짜 손절이 생긴다. C 점검은 같은 틀린 종가로 일관돼 못 잡는다 | D6, §2.2 ⑦, T-RETRO |
| R17 | KS200 멈춤·연도 파일 | 달력이 안 늘어 몇 주 동안 "이미 처리됨"만 나온다. 또는 달력이 줄어든다 | D4·D7(종료 코드 7·알림), T-CAL |
| R18 | 미국 종목군 변화 | S&P500 목록 하나만 바뀌어도 40종목이 바뀐다 | S 날 고정 파일, 재시작해도 유지, L22, T-UNIV |
| R19 | 지표 길이 | 운영 2024-06-01 시작 vs R2 전체 | T-RSI(검토: ≤ 2.1e-14) |
| R20 | 가격 같음 비교 | float 를 문자열로 바꿔 저장하면 같음 비교가 깨진다 | JSON float 그대로, L3 은 정확히 같음 |
| R21 | 국내 정지일 체결 | 불가능한 체결이 생긴다 | 데이터 층(Volume=0 버림) + 원본으로 정지 판정 + L4·L6, W2·W3(s1·s2), T-HALT |
| R22 | 기준값이 R2 가 아님 | 하네스가 지금 저장소 모듈을 읽으면 "자기와 비교"가 된다 | 임시 폴더 안에서 실행, 모듈 경로 확인 |
| R23 | 늦은 LLM 미리보기 | 다음 장이 열린 뒤 소식을 보고 전날 후보를 판정한다 | `next_open` 시각 규칙, T-LLMTIME |
| R24 | 동시 실행 | 판정 기록·장부가 덮이거나 반쯤 바뀐 장부를 읽는다 | 모든 명령에 잠금 하나, T-LOCK |
| R25 | 이자 근사 | "A0+이자"가 R2 A0(이자 켬)와 조금 다르다 | 보고서에 근사라고 적음, M7 에 차이 크기를 참고로 |
| R26 | 국내 세율 변경 | 기간 중 법이 바뀐다 | 표에 줄 추가만 허용(§2.2 ⑥-ii), meta 비교 |
| R27 | 마라토너 구조적 보류 | 30% × 5종목 = 150% → 4·5번째 매수가 늘 "현금 부족" | team.py 그대로. 보고서에서 보류를 읽을 때 같이 적음(R2 P6) |
| R28 | 실현손익 방식 | 평균원가법이 신고 방식과 다를 수 있다 | 보고서 참고값, 장부 칸 없음 |
| R29 | 판정 기록 망가짐 | 같은 판정 보장이 깨진다 | JSONL·fsync·HEAD 앞부분 지문, L18, T-JSONL |
| R30 | 배포 실수 | 운영 체크아웃을 다른 브랜치로 바꾸면 H1 작업이 옛 코드로 돌거나, `--h1` 을 무시하고 운영 장부를 돌린다 | 전용 worktree(태그 고정), 진입점 `h1.py`(옛 코드에는 없어 실패), team.py `--h1` 없음, T-ENTRY |
| R31 | 라이브러리 바뀜 | FDR 버전이 KS200 출처를 바꾼다(kr-fix-s0 §1) | 전용 venv, `env` 지문 관문, ⑥ 동결 |
| R32 | 판정 기록과 장부 저장 순서 | 장부만 저장되고 판정 기록이 없으면 L17 이 깨진다 | 판정 기록 먼저, HEAD 하나, T-HEAD·T-JSONL |
| R33 | 자료 지연이 논리 오류로 둔갑 | 늦게 온 행 때문에 다음 날 L4·L15 가 거짓 오류를 낸다 → 3개월을 잃는다 | D3 로 멈춤 + L4·L15 를 저장된 `halted` 로 셈, T-LATEDATA |
| R34 | 미국 보유 종목의 여러 날 정지·인수 | D3 가 매일 나서 늦은 봉 상한을 넘는다 | §2.2 ⑦(상장폐지 정리) 또는 상한 초과 → 창 실패(사전 등록대로) |
| R35 | 점검 함수 버그 | 거짓 양성으로 재시작해야 할 수 있다 | L 점검마다 음성 대조 + W1·W2·합성에서 거짓 양성 0, §2.2 ④ 거짓 양성 규칙 |
| R36 | 지문에 실행 메모가 섞임 | 코드를 고치면 지문이 늘 달라져 사전 등록의 예외 길(④·⑥)이 닫힌다 | `ledger_fingerprint` 가 실행 메타 칸을 뺌, T-FP |
| R37 | 상장폐지 종목 시세 | 시세를 못 받아 매일 D2 로 멈춘다 | `--delist` 등록 종목은 D2·D3·D6 에서 뺌, L23, T-DELIST |

---

## 8. 맥 운영

### 8.1 처음 한 번 — H1 전용 worktree·venv (검토 I8)
```bash
cd /Users/나/claude-stock                       # 운영 체크아웃(그대로 둔다)
git fetch origin
git worktree add /Users/나/claude-stock-h1 <H1 태그, 예: h1-forward-v1>   # H1 전용 폴더, 태그에 고정
cd /Users/나/claude-stock-h1
python3 -m venv /Users/나/.venv-h1                # H1 전용 파이썬(라이브러리 동결, §2.2 ⑥)
/Users/나/.venv-h1/bin/python -m pip install -r requirements.txt
/Users/나/.venv-h1/bin/python -m pytest -q        # 전부 통과
git fetch origin research-r2-2026-11-04           # 재현 기준값 데이터
/Users/나/.venv-h1/bin/python h1_replay.py        # 단계 5. "통과" + state/h1/replay_pass.json (이 폴더 안의 state/)
mkdir -p logs
which claude                                       # launchd PATH 에 넣을 경로 확인
```
- 이 폴더의 `state/` 는 운영 체크아웃의 `state/` 와 **다른 폴더**다. 운영 장부는 이 폴더에 없다.
- 코드를 올릴 때(판정 창 밖에서만, 또는 §2.2 ⑥ 허용 변경): 이 폴더에서 `git checkout <새 태그>` → `h1_replay.py` 통과 → 다음 실행.
- 그다음 **사전 등록 확인**(이 문서 최종판이 커밋돼 있고, `meta.json` 의 `design_doc_sha256` 이 그 파일과 같은지) 뒤 시작:
```bash
/Users/나/.venv-h1/bin/python h1.py start --market kr    # 국내: 22:30 KST 뒤 ~ 다음날 09:00 전
/Users/나/.venv-h1/bin/python h1.py start --market us    # 미국: 07:10 KST 무렵(16:30 ET 뒤 ~ 09:30 ET 전)
```

### 8.2 실행 시각 (맥 시계 = 한국 시간)

| 시장 | 명령(WorkingDirectory = H1 폴더) | 시각 | 메모 |
|---|---|---|---|
| 국내 | `.venv-h1/bin/python h1.py run --market kr` | **월~금 23:05** + 보조 **화~토 07:40** | 보조는 23:05 실패·KS200 늦은 날(종료 코드 7)을 챙긴다. 07:40 은 09:00 전이라 늦은 봉이 아니다 |
| 미국 | `.venv-h1/bin/python h1.py run --market us` | **화~토 07:10** + 보조 **화~토 08:40** | 07:10 KST = 겨울 17:10 ET / 여름 18:10 ET → 사계절 모두 16:30 ET 뒤이고 다음 장 09:30 ET 전. 서머타임 때 시각을 안 바꿔도 된다 |
| 둘 다 | `python h1_report.py --market us` / `--market kr` | 매달 첫 평일 아침 + 아무 때나. S+62 뒤 `--final` | 인터넷이 있으면 금리도 받음. 결과는 `state/h1/reports/` |
| 상태 | `python h1.py status --market us` | 아무 때나 | S, 판정 창 진행, 마지막 봉, L·D·늦은 봉 수, 남은 재시작·마감 |

- 기존 운영 작업(`team.py 40 --market kr` 22:35, `--market us` 06:30, order_runner)은 운영 체크아웃에서 그대로 돈다.
- 팀장 호출은 하루에 대략 두 배가 된다(같은 구독 한도).
- 휴장일에는 새 봉이 없어 "이미 처리됨"으로 바로 끝난다.

### 8.3 launchd
`docs/broker-run.md` 의 plist 모양 그대로 쓰고, 아래만 다르게 한다.
```xml
<key>Label</key><string>com.claude-stock.h1-kr</string>
<key>WorkingDirectory</key><string>/Users/나/claude-stock-h1</string>
<key>EnvironmentVariables</key>
<dict><key>PATH</key><string>/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>  <!-- which claude 로 나온 폴더 -->
<key>ProgramArguments</key>
<array>
  <string>/bin/sh</string><string>-c</string>
  <string>/Users/나/.venv-h1/bin/python h1.py run --market kr; c=$?; [ $c -eq 0 ] || osascript -e "display notification \"H1 국내 종료 코드 $c (logs/h1-kr.log)\" with title \"claude-stock\""; exit $c</string>
</array>
<key>StartCalendarInterval</key>
<array> <!-- 월~금 23:05, 화~토 07:40 : 요일마다 dict -->
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
  <!-- … -->
</array>
<key>StandardOutPath</key><string>/Users/나/claude-stock-h1/logs/h1-kr.log</string>
<key>StandardErrorPath</key><string>/Users/나/claude-stock-h1/logs/h1-kr.log</string>
```
- launchd PATH 에 `claude` 가 없으면 팀장은 매일 폴백(`no_claude`)이 된다 → 보고서 폴백 비율 20% 표시로 드러난다.
- 잠자기 중에는 안 돈다: `sudo pmset repeat wakeorpoweron MTWRFS 07:00:00`.
  - `pmset repeat` 는 깨우는 시각을 하나만 둘 수 있다. 국내 23:05 에 자고 있으면 보조 07:40 이 처리한다(09:00 전이라 늦은 봉 아님).
  - 깨어난 뒤 launchd 가 놓친 작업을 한 번 돌리고, H1 은 밀린 봉을 따라잡는다(5봉까지).

### 8.4 종료 코드별 할 일

| 종료 코드 | 화면 | 할 일 |
|---|---|---|
| 2 | `장부 논리 오류` + 문제 목록 | 그 봉은 저장 안 됨(장부 안전). ① 로그와 `state/h1/errors.jsonl` 을 Claude Code 에 보여 주고 원인 찾기 ② 점검 함수 잘못이면 §2.2 ④ 거짓 양성 규칙 확인 ③ 아니면 고친 코드로 `h1_replay.py` 통과 → `h1.py restart --market <m> --reason "…"` → `h1.py start --market <m>` (63봉 다시, 재시작 상한·마감 확인) |
| 3 | `재현을 통과하지 않은 코드·환경` 또는 `규칙이 시작 때와 다름` | 이 폴더 코드나 venv 가 바뀐 것. 판정 창 중이면 §2.2 ⑥ 허용 변경인지 확인 → `h1_replay.py` 통과 뒤 다시(세율 줄 추가면 그다음 `h1.py amend-rules`). 허용 변경이 아니면 재시작 |
| 4 | `자료 문제 D?` | 저장 안 됨, 재시작 아님. 보조 시각에 저절로 다시. D2·D6(분할 의심)이면 §2.2 ⑦ 대로 1차 출처 확인 후 하나를 고름. 며칠 계속되면 늦은 봉 상한(5·10)에 주의 |
| 5 | `다른 H1 명령이 잠금 중` | 잠시 뒤 다음 실행. 계속되면 멈춘 python 확인 |
| 6 | `밀린 봉 N개 > 5` | 판정 창 실패(사전 등록 ②-2). `h1.py restart` → `h1.py start` |
| 7 | `기준 지수 늦음(D7)` | 처리할 수 있던 봉은 저장됨. 보조 실행이 다시 확인. 하루 넘게 계속되면 KS200 캐시 상태 확인(`docs/kr-fix-s0.md` §5 명령). 연말·연초면 FDR 연도 파일 문제 의심 |
| 8 | `장부 없음` / `start 거절` | 처음이면 `h1.py start`. 폴더가 사라진 거절이면 무엇이 지웠는지 먼저 확인 |
| 9 | `인자 오류` / `조건 불충족` | 명령을 고쳐 다시. 분할이면 D6 의 "분할 의심 r"·효력일 확인 |
| 1 | 파이썬 오류(cli 전) | venv·라이브러리 확인(`requirements-h1.txt`) |
| (경고) | `늦은 봉`, `팀장 폴백`, `정지`, `D7 판단 불가(W5)` | 멈추지 않음. 보고서에 셈 |

---

## 9. 구현 순서 (단계)

| 단계 | 내용 | 끝 조건 |
|---|---|---|
| 1 | 설계(이 문서 3판) | 2차 재검토 반영 끝 |
| 2 | **골든 먼저**(847ad13 에서, 코드 한 줄도 바꾸기 전) → `paper_wallet`(표기·`tax_rate`), `analyst`(`normalize_verdict`·`analyze_logged`), `screener`(`scan_frames`, `scan()` 이 부름) + 시험 | 306 + 새 시험 통과, 골든 같음 |
| 3 | `h1.py`·`h1_check.py`·team 갈고리 + 시험(§6 대부분) | 시험 통과, 골든 같음 |
| 4 | `h1_report.py` + 시험 | T-F8 통과 |
| 5 | **재현** `h1_replay.py`: W1·W2·W3 | §5.6 통과, `replay_pass.json` |
| 6 | 독립 검토(결과 없이 코드만) → 고침 → 재현 다시 | 검토 지적 처리 |
| 7 | 맥 운영: 태그·worktree·venv → 재현 → 2판 커밋 확인 → `h1.py start` | S+62 뒤 `--final` |

---

## 10. 결정과 질문

### 10.1 결정 Q1~Q13 (2026-11-04, 진행 담당이 사용자 위임으로 정함 · 검토 1회 뒤 갱신 — 바꾸려면 이 표를 고치고 커밋한 뒤 본문·구현에 반영)

| # | 결정 | 이유 |
|---|---|---|
| **Q1** | **두 H1 장부 모두 서킷 끔**(`CircuitBreaker(inf, inf)`). 매일 지금 규칙(누적 −10%·하루 −7%)으로 "켜져 있었다면"을 계산해 **하루 기록 `events`** 에 그림자 사건으로만 남기고 보고서에 첫 발동일을 적는다(§2.6). 재현은 끈 장부만 맞추고, 그림자 첫 발동일 == R2 `cb="current"` 사건(M5′)으로 확인한다. 서킷 켠 장부 재현·1판 C16·T-CB 는 없앴다 | R2 H1 은 서킷을 끈 조건에서 채택 후보가 됐다. 켜면 재현 창 국내 6번째 거래일에 A1 세 트레이너가 멈춰 운영 기준을 확인할 매매가 남지 않는다. probe1: 그림자 첫 발동일이 R2 사건과 4/4 같음 |
| Q2 | 늦은 봉(다음 장 시작 뒤 처리, 팀장 폴백)은 빠진 날이 아니고 따로 센다. **단 창 전체 10봉·한 번에 5봉을 넘으면 창 실패**(검토 I3 로 상한 추가) | 하루 꺼짐으로 3개월을 버리지 않되, 오래 꺼진 것은 운영 실패로 본다 |
| Q3 | 장부 논리 오류로 재시작하면 63봉을 새 S 부터 센다. **재시작 최대 2번, 마감 2027-06-30**(검토 I3) | 운영 기준 ②-1 이 "창 동안 오류 0". 결과를 보고 끝없이 다시 시작하지 못하게 |
| Q4 | **보류 — 나중에.** 팀장 프롬프트는 운영과 같게 둔다(날짜·시장·종목명 넣지 않음) | 범위를 줄이고 A0 를 운영과 덜 멀게. 나중에 하면 별도 결정 |
| Q5 | H1 에서 판정 글자를 정리한다(원래 값도 기록), 판정 기록 유지 | 버그 수정. 운영 쪽 수정은 개선 후보 목록으로 따로 |
| Q6 | 모델은 고정하지 않는다. 알 수 있으면 기록(launchd 에서는 대개 "모름"), `claude --version` 은 항상 기록. 바뀌면 보고서에 적음 | 구독 기본 모델을 3개월 고정할 수 있다는 보장이 없음 |
| **Q7** | **미국 종목군은 첫 S 날 `screener.universe(40)` 목록·순서로 고정**(`state/h1/universe/us.json`, 재시작해도 그대로). N=40 도 고정 | 포워드 결과를 다시 만들 수 있어야 한다(개선 후보 11번). 재시작으로 종목군을 고를 수 없게 |
| **Q8** | **S 는 입금만, S+1 시가에 A1 은 먼저 현금 전부 지수 → 그날 주문(매도 → 매수 → 쓸어 담기)**. A0 는 S+1 부터 평소대로. 지수 B&H 도 S+1 시가. 재현 기준값도 같은 규칙(하위 클래스). **S 시가 옵션은 없앴다**(원래 sim_team 과의 차이는 참고로만) | 포워드에서는 실행 시각에 이미 지난 가격으로 살 수 없다. 전부 지수를 주문보다 먼저 하면 R2 첫날 규칙을 한 봉 미룬 것이 되고, A1 이 첫날부터 매일 같은 길을 지나며 B&H 와 같은 가격으로 출발한다(§2.5) |
| Q9 | 국내 매도세는 **날짜별 표**(STAGE0 §1.2)를 체결일 기준으로 쓴다. 기간 중 새 세율은 표에 줄 추가만 허용(재시작 아님, §2.2 ⑥-ii) | 2026 세율 0.20% 와 같고, 2018 재현 창(0.30%)도 R2 와 같아진다 |
| Q10 | "A0+이자"는 계산값만 | F8 그대로 |
| Q11 | 실현손익은 **보고서 안에서만** `fills` 로 평균원가법 계산(장부 칸 없음), 달러 기준 참고값 | 사전 등록 대상이 아님. 검토 "잘라도 되는 것" 중 보고서 줄만 남김 |
| Q12 | 판정 기록 열쇠에 시장을 붙인다 | 명확성 |
| Q13 | KS200 에 ETF 운용보수 없음 — 그대로 두고 한계로 적는다 | R2 A3 와 같음 |

### 10.2 검토 1회 반영으로 정한 것

| 항목 | 결정 | 검토 ID |
|---|---|---|
| 진입점 | `python h1.py start\|run\|restart\|corp-action\|status`. team.py 에 `--h1` 없음(F7 의 명령을 바꿈) | I8 |
| 판정 기록 | `state/h1/analyst_cache.jsonl`(F5 의 `.json` 을 바꿈), 추가 전용, 장부보다 먼저 fsync | I7 |
| 커밋 지점·잠금 | 시장마다 `HEAD.json` 하나, 모든 명령에 잠금 하나(30분) | I7 |
| 오류 등급 | L(재시작) / D(그날 멈춤, 종료 코드 4·7) / W | I1·I2 |
| 사전 등록 숫자 | 판정 창 63(S~S+62, 시장별), 늦은 봉 10·한 번에 5, 재시작 2, 마감 2027-06-30, 폴백 표시 20%, 소급 수정 오차 1e-6 | I3·I5 |
| 분할·상장폐지 | 프로그램은 감지만(D6). 사람이 1차 출처 확인 뒤 미리 정한 넷 중 하나: 기다림 / `corp-action --split r` 공식 / 재시작 / `--delist` 정리 | I5 |
| 보고서 위치 | `state/h1/reports/`(F8 의 `reports/h1-forward/` 를 바꿈) | m8 |
| 맥 | H1 전용 worktree(태그 고정)·전용 venv, launchd 는 `h1.py` | I8·m4 |
| 잘라 낸 것 | 장부의 실현손익·취득가 칸(보고서 계산만 남김), 서킷 켠 재현, 1판 C16·T-CB·G3, `h1.py check`, 1판 M10, Q4 프롬프트 변경, 종목군 지문 경고 | §5 잘라도 되는 것 |

### 10.2c 구현 중 정한 것 (단계 2a·2b-1 독립 검토 반영)

| 항목 | 결정 | 근거 |
|---|---|---|
| 팀장 래퍼 | `analyze_logged(now, cli_version)`, `claude_cli_version()` 실행마다 한 번. "analysis" 가 목록이 아니면 bad_json, 디코드 실패는 decode_error(운영 `analyze()` 는 그대로) | 2a A-6·A-9 |
| 모르는 판정 글자 | `bad_verdict`, 폴백으로 셈(운영 team 과 달리 그 답의 확신도는 쓰지 않음) | 2b-1 B-5 |
| 예외로 끝난 L | 엔진은 장부 논리 점검을 되도록 `Problem` 으로 모아 처리 뒤 장부·내용 지문을 남긴다. 끝까지 갈 수 없어 예외(L 번호 있음)로 끝난 봉은 지문이 없어 ④-(나) 를 쓸 수 없다 → 재시작. 예상 밖 예외(코드 버그)도 종료 코드 2·지문 없음으로 같게 본다 | 2b-1 B-3 |
| 사전 조건 위반 | 앞 거래일 ≠ last_date, 지수 봉 날짜, S 의 `prev_cal_date` 등은 L 이 아니다(실행기가 D4·D5 를 먼저 보고, 그래도 어긋나면 거절) | 2b-1 B-3·B-10 |
| 상장폐지 | 장부 `corp_actions` 하나가 출처. `corp-action --delist` 는 `last_date` ≤ 장부 last_date 만 받는다. L23 은 장부마다 "등록 뒤 첫 처리 봉에 들고 있었으면 정리 체결" + 두 장부의 그 날짜가 같은지 | 2b-1 B-1·B-4 |
| 분할 | `apply_split` 순수 함수 + `corp_actions` 분할 기록 모양(위 §3.5). 점검이 반영 | 2b-1 B-2 |
| L4·L5·L12 넓힘 | L4: 정지가 아닌 처리 봉을 지난 대기 주문도 오류, 같은 시가에 주식 매수 체결이 매도 체결보다 앞이면 오류. L5: 그날그날 보유+매수 대기 ≤ 5. L12: 보류 순간 `avail` 을 그날 체결 순서로 다시 계산 | 2b-1 구현·B-6 |
| check_day 의 L3 | 오늘 체결만 그날 시세와 맞춘다(뒤에 시세가 고쳐져도 지난 체결이 거짓 L3 이 되지 않게). 지난 체결은 `check_ledger(frames=…)` 에서만 | 2b-1 구현 |
| L22 허용 지문 | `(code_hash, env_key(env))` 짝. `env_key` = env 정렬 JSON 의 sha256 | 2b-1 구현 |
| L18 | `check_decisions(market, decisions, head)` 로 판정 기록 앞부분 지문·중복 열쇠 | 2b-1 구현 |

### 10.2d 단계 2b-2 독립 검토 반영으로 정한 것

| 항목 | 결정 | 근거 |
|---|---|---|
| 환경 문제 | `OSError`·`MemoryError` → 종료 코드 4·`ENV`(재시작 아님). Ctrl-C → 130 | C-1 |
| 분할 명령 | 효력일 > 장부 last_date, 지금 D6 의 분할 의심 비율과 같을 때만, 같은 기록 두 번 금지, 분수 입력 | C-2·C-9·C-16 |
| 정정 확정 | 차이가 모든 날짜에서 같은 비율(분할 모양)이면 거절 | C-10 |
| 관문 | `corp-action` 도 관문·규칙 확인을 거친다(status·restart 는 아님) | C-11 |
| 기록의 창 | 장부를 읽기 전 L24·관문 거절도 `start_date`(모르면 `unknown` = 지금 창)를 남긴다 | C-3 |
| 종목군 시세 | 고정 종목군의 절반 넘게 못 받으면 D2(4, 상장폐지 등록 종목은 비율에서 뺌, start 도 같음). 확인용 대형주 실패는 W5 와 "D7 판단 못 함" 표시(runs.jsonl `d7_checked: false`) | C-4 |
| replay_pass | `record_replay_pass` 로 추가만. 지난 줄이 줄거나 바뀌면 관문 거절 3(L 아님) | C-5 |
| restart 순서 | `restarts.jsonl` 의도 줄 → 폴더 이동 → 끝 줄. 중간에 꺼지면 다음 restart 가 마저 함(횟수 한 번) | C-6 |
| 일지 보충 | 장부 `corp_actions`·`meta` 가 원본. 모든 명령이 시작할 때 일지에 빠진 줄을 채움 | C-7 |
| start 시각 | 지금 ≥ `next_open(S)` 이면 start 거절(8) | C-8 |
| D4·D5 가 풀리지 않을 때 | 제공처가 고치지 않으면 1차 출처 확인 뒤 ⑤-c(⑦-3) 재시작 | C-12 |
| 0 이하 가격 | 보유·대기 종목 종가, 대기 자산 시가·종가가 0 이하·NaN 이면 D3 | C-13 |
| 디스크 쓰기 | 새 폴더·바꾼 파일의 부모 폴더도 fsync, 맥은 `F_FULLFSYNC` | C-14 |
| 종료 코드 | 9 = 인자·조건 오류, 1 = cli 전 파이썬 오류, 130 = Ctrl-C | C-15 |
| 운영 전 확인(단계 7) | 미국 일봉이 나중에 고쳐져 D6 이 자주 나는지, KS200 캐시 갱신 시각, 파이썬 자동 업그레이드(brew)로 env 가 바뀌어 종료 코드 3 이 나는지(전용 venv 의 파이썬을 고정) | 2b-2 검토 "운영 전에 확인할 것" |

### 10.2e 단계 2c(보고서) 독립 검토 반영으로 정한 것

| 항목 | 결정 | 근거 |
|---|---|---|
| 창 세기 | 모든 일지 줄은 `at ≥ meta.created_at` 일 때만 지금 창(`start_date == S` 줄도). 시각이 같으면 보고서는 창을 만든 start 보다 runs.jsonl 에서 먼저 시작한 실행의 줄을 뺀다. 실패한 start 의 줄은 어느 창에도 안 넣고 "창 밖 기록"으로만. 읽지 못한(깨진) 일지 줄 수도 보고서에 보임 | R-1 |
| ②-1 L 오류 수 | errors.jsonl 의 L 줄 ∪ runs.jsonl 끝 줄 `exit_code == 2` (run_id 로 합침). 끝 줄 없는 실행은 L 아님, "끝 기록 없는 실행"으로 따로 보임 | R-2 |
| 경계 시각 | 실행 끝 줄이 없으면 하루 기록 `run_at`(HEAD 로 보호)으로 S+62·월 경계를 정함 | R-3 |
| ④ 거짓 양성 기록 | §2.2 ④ 의 (가)(나)를 `h1.py run` 이 자동 확인해 `changes.jsonl` `false_positive` 로 남김 | R-4 |
| 월간 보고서 | 봉이 없는 실행 줄은 그 실행이 처리하려던 봉 날짜로 달을 정함(모르면 "어느 달인지 모름"). 같은 달 보고서는 언제 만들어도 2~9절 같음 | R-5·R-6 |
| 재시작 수 | `meta.restart_no`·restarts.jsonl(done 또는 archive 있음)·archive 폴더 수 중 가장 큰 값, 서로 다르면 경고. 끝나지 않은 `moving` 은 따로 보임 | R-7 |
| 폴백 비율 분모 | 두 장부 하루 기록 `leader` 가 가리키는 판정 기록(이 창이 실제로 쓴 것). 늦은 봉 폴백 포함 | 2c 구현 |
| status 와 보고서 | `h1.py status`·실행 끝 요약의 일지 숫자(L 오류 = errors.jsonl ∪ runs.jsonl 종료 코드 2, ④ 거짓 양성은 빼고 따로, 자료 멈춤(D7 포함)·관문 거절·늦은 봉·팀장 폴백)는 보고서와 **같은 함수**(`h1_report.window_counts`)로 센다. 범위는 보고서 `--final` 과 같다(창이 다 차면 S~S+62, 그 뒤는 연장 구간 따로). 다시 점검한 L·빠진 날·지문 확인은 보고서에만 있다. 재시작 수도 세 출처 중 가장 큰 값으로 같은 함수 | 단계 3·검토 3 |
| 마감 전 실패 | 남은 평일로 63봉 창을 마감까지 끝낼 수 없음이 확실하면 마감 전이라도 "H1 포워드 실패" | 2c 구현 |

### 10.2f 단계 3(시험 보강) 반영으로 정한 것

| 항목 | 결정 | 근거 |
|---|---|---|
| 시험 지도 | `docs/h1-test-map.md` 가 §6 시험 ID·L/D/W·사전 등록·종료 코드·§10 결정과 실제 시험을 잇는다. "완전"은 돌연변이(그 규칙을 지우거나 바꾼 코드)가 실제로 시험에 잡힐 때만 | 단계 3·검토 3 T-1·T-2 |
| §6 새 시험 ID | T-STATUS(status↔보고서 같은 수), T-EXIT1(cli 전 파이썬 오류 = 1), T-W(정상 장면 W 0), T-RULES(⑩ 고정 값 전부, 한 칸이라도 다르면 3). T-LLMTIME·T-CAL·T-NEWSTART 에 정각 경계 추가 | 단계 3 |
| 환경 점검 도구 | `tools/h1_test_guard.py`(인터넷·claude 차단, 시드·시간대·LANG·순서 결정성, `state/`·`results/` 파일 지문 전후 비교). 단계 4·7 확인 목록에 넣는다. 못 막는 길(ctypes, C 수준 HTTP, env 를 통째로 바꾼 하위 프로세스)은 도구 머리말에 적는다 | 단계 3·검토 3 T-3·T-4·T-13 맥에는 `--netns`(리눅스 전용 네트워크 격리)가 없으므로 단계 7 확인에서는 sitecustomize 차단과 "못 막는 길" 목록을 함께 본다. "완전" 기준을 돌연변이로 남은 규칙까지 넓힐지는 단계 4 에서 정한다 |

### 10.2b 2차 검토 반영으로 정한 것 (3판)

| 항목 | 결정 | 검토 ID |
|---|---|---|
| 장부 내용 지문 | 실행 메타 칸을 뺀 정렬 JSON sha256(`ledger_fingerprint`). ④·⑥·`replay_pass`·`errors.jsonl` 이 이것을 씀. 라이브러리 올림은 ⑥-(i) 같은 조건으로 허용 | R2-1 |
| 재현의 L22·W3 | L22 는 넘겨받은 허용 지문으로 봄(관문 실행만 `replay_pass`), M8 의 W 허용 목록에 W3 | R2-2 |
| 상장폐지 | `--delist --last-date --last-close` 등록 → D2·D3·D6 에서 빠짐, a′ 정리, L3·L4·L6·L14 예외 + L23 | R2-3 |
| 정정 확정 | ⑦-5 `--accept-correction`: 장부 그대로, D6 기준만 새 값. 재시작 아님 | R2-4 |
| 세율 줄 추가 | `h1.py amend-rules`(뒤에 줄만 더한 표만 받음). 규칙 불일치는 종료 코드 3 하나 | R2-5 |
| 준비 순서 | 5 → 7 → 6 → 8. 확인용 종목 실패는 W5 | R2-9 |
| 백업·시작 | 백업 열쇠 = HEAD `run_id`, corp-action·amend-rules 도 커밋 순서, start 는 `<m>.starting/` 에 다 쓴 뒤 이름 바꿈 | R2-10 |
| 파일 손상 | L24(재시작 사유 (a)) | R2-11 |
| CODE_FILES·⑩ | `h1_report.py`·`h1_replay.py` 를 CODE_FILES 에. `NEXT_OPEN`·`RETRO_DAYS`·`EPS_*`·`CAL_HOLE_RATIO`·`FINGERPRINT_VERSION` 을 ⑩ 에 | R2-12 |
| 그 밖 | 시가 없는 확정 행 = D3(R2-13), LLM 호출 직전 시각 재확인·`late_calls`(R2-14), G4 `cands0`·note_leader 버퍼(R2-15), `scan_frames(brains=)`(R2-6), 멱등 대상 파일 한정(R2-7), `calendar.jsonl` 날짜 목록 전체(R2-8), v1 결정 번호 표기·T-SIG(R2-16), 머리 숫자(R2-17) | R2-6~17 |

### 10.3 남은 질문 (사람이 정할 것)

| # | 질문 | 설계 기본값 |
|---|---|---|
| N1 | 사전 등록 숫자를 이대로 둘까: 재시작 최대 2번, 마감 2027-06-30, 늦은 봉 창 전체 10봉·한 번에 5봉, 팀장 폴백 표시 20% | 이대로. 첫 창이 2027-02 초에 끝나므로 마감까지 깨끗한 창을 약 두 번 시도할 수 있다 |
| N2 | 분할·병합을 `corp-action --split` 공식으로 이어 갈까, 무조건 재시작할까 | 공식으로 이어 감(사람이 1차 출처를 확인하고 명령을 침, 프로그램이 스스로 고치지는 않음). 3개월 안에 보유 종목 분할이 한 번이라도 나면 재시작은 비용이 너무 크다 |
