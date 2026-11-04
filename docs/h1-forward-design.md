# H1 포워드 모의매매 설계 — "쉬는 돈을 지수에" 장부(A1)와 "지금 방식" 장부(A0)를 3개월 나란히

- 작성: 2026-11-04 · 브랜치 `h1-forward` (`kr-fix-s0` 847ad13 에서 분기) · 커밋은 사람이 검토한 뒤 직접
- 이 단계는 **설계만** 한다. `.py` 는 한 줄도 고치지 않았다(`pytest -q` → 306 passed 그대로).
- 근거
  - `origin/research-r2-2026-11-04` 의 `reports/research-r2-2026-11-04/`: `REPORT.md`(H1 = 채택 후보, 한계), `STAGE0.md` §6·6b·6c(보완 A1~A9, B1~B11), `SIM_NOTES.md` §1(하루 순서)·§3(구현 선택 I1~I25), `sim_team.py`(A1 참조 구현)
  - `origin/research-oss-2026-11-04` 의 `reports/research-oss-2026-11-04/REPORT.md` §6 G1, §7 H1, 7.5-3("최소 3개월 포워드 모의매매, 매달 A0 그림자 장부와 비교")
  - 지금 코드: `team.py`, `main.py`, `paper_wallet.py`, `markets.py`, `analyst.py`, `screener.py`, `order_runner.py`, `broker/`, `docs/kr-broker-design.md`, `docs/kr-fix-s0.md`
  - 할 일 목록(참고만, 구현 안 함): `origin/docs-knowledge-2026-11-04:docs/개선-후보-2026-11-04.md`
- 사용자가 이미 정한 결정 F1~F8 은 그대로 구체 규칙으로 옮겼다. 이견이나 사람이 정할 것은 **§10 질문**에만 적었다.

**설계하면서 직접 확인한 것** (코드·연구 브랜치는 고치지 않음. 연구 브랜치를 `git archive` 로 scratch 폴더에 풀어 돌려 봄)
- `sim_team.run(Config(period=("2026-06-01","2026-11-03"), interest=False, ...))` 처럼 **기간을 튜플로 주면 그대로 돈다.** 그래서 재현(§5)에 sim_team 을 복사·수정할 필요가 없다.
- 재현 창(2026-06-01 ~ 2026-11-03) 데이터: 미국 SPY 109봉, 국내 KS200 105봉. 이 창 안에는 **국내 거래정지 행(Volume=0)·시가 0 행·빠진 종목 봉이 하나도 없다.** 모든 종목이 창 시작 전에 70봉 이상 있다. → 거래정지 규칙은 재현이 아니라 합성 시험(§6)이 맡아야 한다.
- 같은 창에서 sim_team A1(서킷 끔)은 미국 매수 87·매도 79·지수 다리 136·현금 부족 보류 152건, 국내 매수 125·매도 116·지수 다리 177·보류 203건이 나온다 → 재현이 A1 규칙의 길을 충분히 지나간다.
- 같은 창에서 **서킷을 켜면**(team.py 지금 규칙) 국내 A1 은 세 트레이너가 **6번째 거래일(2026-06-08)에 모두 영구 정지**되고, 미국은 A0·A1 모두 두 트레이너가 정지된다(§10 Q1).

---

## 용어 (처음 보는 사람용)

| 말 | 뜻 |
|---|---|
| 장부(ledger) | 가짜 지갑 + 보유 종목 + 대기 주문을 적은 파일. 트레이너 한 명당 하나. 진짜 돈은 0원 |
| **A0** | 지금 방식. 트레이너가 주식에 안 쓴 돈은 **현금**으로 둔다 |
| **A1 (= H1)** | 트레이너가 주식에 안 쓴 돈을 **지수**(미국 SPY, 국내 KOSPI 200 가격지수 KS200)로 둔다. 주식을 살 때 모자란 만큼만 지수를 판다 |
| 대기 자산(idle asset) | A1 에서 쉬는 돈을 넣어 두는 곳 = SPY / KS200 |
| 그림자 장부 | 실제로 쓰지는 않고 비교용으로만 같이 쌓는 장부. 여기서는 A0 |
| 확정 봉 | 장이 끝나고 값이 확정된 하루치 시세(`main.confirmed_bars`). 미국 16:15 ET, 국내 종목 16:00 KST, KS200 만 22:30 KST |
| 소수 단위 | 지수는 0.123456단위처럼 소수로 산다(남는 돈이 1 미만이 되게). 주식은 정수 주 |
| 팀장 판정 | `analyst.py` 가 `claude -p` 로 받아 오는 buy/hold/veto·확신도. 없으면 규칙 그대로(폴백) |
| 재현(replay) | 과거 데이터로 새 코드를 돌려 R2 `sim_team.py` 와 체결 하나하나가 같은지 맞춰 보는 시험(§5) |
| 사전 등록 | 결과를 보기 전에 기간·기준·실패 시 할 일을 먼저 적어 두는 것(§2.2) |

---

## 0. 한눈에

| 무엇 | 어떻게 |
|---|---|
| 돌리는 법 | `python team.py 40 --market us --h1` / `--market kr --h1` → **A0·A1 두 장부를 한 번에**, 같은 스크리너 결과로 |
| 장부 위치 | `state/h1/<market>/<A0\|A1>/team_<트레이너>.json` (기존 `state/` 파일은 읽지도 쓰지도 않음) |
| 시작 자금 | 미국 $100,000, 국내 ₩100,000,000. 60/30/10, 종목상한·MAX_POSITIONS·확신도 규칙은 team.py 그대로 |
| A1 규칙 | R2 `sim_team.py` A1 그대로: 같은 시가에 주식 매도 → 주식 매수(모자란 만큼만 지수 매도) → 남은 현금 ≥ 1 이면 지수 매수. 첫날 전부 지수. 현금+지수로도 모자라면 지수 안 팔고 보류 |
| 팀장 | 두 장부가 같은 (날짜, 트레이너, 종목)에 **같은 판정**을 쓴다. 판정 기록 `state/h1/analyst_cache.json`, 덮어쓰기 금지 |
| 주문 | **증권사 주문 없음.** `order_runner.py` 는 `state/h1` 을 못 읽는다(시험으로 확인) |
| 점검 | 날마다 장부 점검 함수(§4). 오류가 하나라도 있으면 그날은 **저장하지 않고 멈춘다** |
| 보고서 | `python h1_report.py --market us\|kr` → `reports/h1-forward/<market>-<YYYY-MM>.md` |
| 운영 전 | 재현(§5)을 통과한 코드만 돈다(코드 지문 확인) |
| `--h1` 없이 | team.py 동작이 **바이트 하나 안 바뀐다**(골든 시험) |

---

## 1. 목적과 범위

### 1.1 목적
R2 백테스트에서 H1(쉬는 돈을 지수에)은 채택 후보가 됐다(미국 기준 1~3 통과, 국내 같은 방향). 다만 R2 는 과거 데이터·연구용 시뮬레이터였다. 이 작업은 **실제 운영 코드(team.py) 위에서 H1 장부가 3개월 이상 오류 없이 매일 돌아가는지** 확인한다. 동시에 지금 방식(A0) 그림자 장부를 같이 쌓아 매달 숫자를 **기록**한다(판정은 하지 않는다, §2.2).

### 1.2 범위 안
- team.py 에 `--h1` 경로 추가(두 장부, 같은 스크리너, 같은 팀장 판정)
- 대기 자산(지수) 소수 단위 보유·저장·표시
- 팀장 판정 기록(나중에 채점할 수 있는 형태, 할 일 목록 2번)
- 날마다 장부 점검, 월간 보고서(A0 현금 이자 계산값 포함), 재현 시험, 오프라인 시험
- H1 경로 안에서만: 밀린 봉 따라잡기(할 일 7번), 보유 종목 시세 실패 시 멈춤(1번), 깨진 장부를 새 지갑으로 덮지 않기(3번), 판정 대소문자 정리(§3-2), 팀장 프롬프트에 날짜·시장·종목명(10번, §10 Q4)

### 1.3 범위 밖 (이번에 하지 않음)
- **진짜 주문**: 증권사(KIS) 주문, 069500·SPY 실제 매수. 장부만 쓴다(F4·F6)
- **소수점 실제 주문**: 지수 소수 단위는 장부 계산일 뿐이다
- **H2~H4**: 10개월선 필터, 단계적 서킷, 성과 기반 재배분(R2 에서 폐기·채택 안 함)
- **전략 숫자**: 익절·손절·RSI·상한·60/30/10 을 바꾸지 않는다
- **운영 장부 전환**: 기존 `state/team_*.json`·`state/kr/` 장부를 H1 으로 바꾸지 않는다. 3개월 뒤 "기본 장부로 할지 검토"만 한다
- **D6**(서킷 재개 규칙): 원래 저장소 공동작업자와 합의할 일
- **S0-3**(국내 거래량 분할 미반영)
- **엔진 합치기**(할 일 14번, main `trade_day` ↔ team `run_trainer`): 시험 중간에 엔진을 바꾸면 A0·A1 비교 조건이 흔들린다 → 3개월 뒤
- 배당·현금 이자를 장부에 넣기(할 일 15번). 이자는 보고서에서 **계산만** 한다(F8)
- 원래 저장소(kjh3291)에 PR·이슈

---

## 2. 규칙

### 2.1 F1~F8 → 구체 규칙

| ID | 결정 | 구체 규칙 |
|---|---|---|
| **F1** 장부 | `state/h1/<market>/<A0\|A1>/team_<trainer>.json` | 시장 `us`·`kr` × 장부 `A0`·`A1` × 트레이너 3명 = **시장마다 파일 6개**. H1 코드는 `state/h1/` 밖의 파일을 열지 않는다. 특히 `team._load`·`team._save`·`main.load_state_file` 을 H1 경로에서 부르지 않는다(부르면 기존 `state/team_*.json` 을 읽거나 "예전 형식"으로 보관해 버린다). 경로 함수는 결과가 `state/h1/` 아래인지 확인하고 아니면 예외를 던진다 |
| **F2** 시작 | 미국 $100,000, 국내 ₩100,000,000 | 트레이너 몫 = 총액 × 60/30/10(`main.CONFIG["배분비율"]`). 종목상한 30/20/15% 는 **시작 예산** 기준(`shares_within_cap(start_cash, cap, 시가, fee, slip)`, team.py 그대로). `team.MAX_POSITIONS`(5, 매수 대기 주문 포함), `team.CONV_MIN`(0.5), `team.keep_candidate`, `team.to_conviction` 을 **import 해서** 쓴다(복사 안 함). 비용은 `markets.MARKETS[시장]` 그대로(미국 수수료 0.1%·슬리피지 0.05%·매도세 0, 국내 0.015%·0.05%·주식 매도세 0.20%). 서킷 브레이커는 team.py 그대로 켠다(누적 −10%·하루 −7%·영구 정지, 지갑 전체로 잼 = R2 B2) — **§10 Q1** |
| **F3** A1 규칙 | R2 `sim_team.py` A1 | §2.3 의 시가 단계 c~e 가 `sim_team.TeamSim._open`·`_fill_buy`·`_raise_cash`·`_sweep_to_index` 와 **같은 식·같은 순서·같은 여유값**이다. 신호는 봉 t 종가, 체결은 봉 t+1 시가. 지수는 소수 단위(반올림 안 함), 주식은 정수 주. 소수 단위는 JSON 저장·읽기에서 비트까지 그대로 살아야 하고(파이썬 `json` 은 float 를 `repr` 로 써서 그대로 돌아온다), 화면에는 소수 6자리로 찍는다. `paper_wallet.Holding.shares` 표기를 `float`(주식은 정수 값, 지수는 소수)로 고친다 |
| **F4** 대기 자산 | 미국 SPY, 국내 KS200 | 대기 자산 코드 = `markets.MARKETS[시장].benchmark`(지금 `SPY`·`KS200`). 시세는 `main.load_benchmark(team.START, 시장)` 이 주는 것 **그대로**(국내는 `bench_cutoff` 22:30 KST 적용된 확정 봉). 1단위 = 지수 1포인트(국내는 원, 미국은 SPY 1주 가격). 지수 다리 비용 = 그 시장 수수료 + 슬리피지, **국내 지수 매도세 0**(STAGE0 A3). ETF 운용보수는 넣지 않는다(R2 와 같음, 한계로 표시). 069500·SPY 실제 주문은 범위 밖 |
| **F5** 팀장 | 같은 판정, 판정 기록 | 두 장부는 같은 (시장, 날짜, 트레이너, 종목)에 같은 판정을 쓴다. 판정 기록 `state/h1/analyst_cache.json` 의 열쇠 = `"<시장>\|<날짜>\|<트레이너>\|<종목>"`(F5 의 날짜·트레이너·종목에 시장을 앞에 붙임 — 두 시장이 파일 하나를 같이 쓰므로). 기록에 **없는** 종목만 팀장에게 묻는다. 팀장이 없으면(claude 없음·시간 초과·JSON 깨짐) 지금처럼 규칙 폴백(전부 통과, 확신도 없음)이고, 그 사실도 기록한다. 기록은 판정(정리된 값)·원래 값·확신도·이유·폴백/실패 여부와 사유·모델 이름(알면)·시각을 담는다. **한 번 쓴 기록은 고치지도 지우지도 않는다**(§3.6) |
| **F6** 주문 없음 | order_runner 는 `state/h1` 못 읽음 | `order_runner.state_path` 는 지금도 `state/team_*.json`·`state/kr/team_*.json` 만 만든다(`--market` 은 `us`·`kr` 만). H1 코드는 `order_runner`·`broker` 를 import 하지 않는다. 시험으로 확인(§6 T-F6). order_runner 코드는 고치지 않는다 |
| **F7** 실행 | `team.py 40 --market us\|kr --h1` | 한 번 실행에 두 장부를 같은 봉·같은 스크리너 결과(`screener.scan_frames(...)` 한 번)로 돌린다. 같은 확정 봉으로 다시 돌리면 **아무 파일도 바뀌지 않는다**(멱등, 팀장도 다시 안 부름). `--h1` 이 없으면 지금 `team.run()` 이 그대로 돈다(h1 모듈을 import 조차 하지 않음) |
| **F8** 월간 보고서 | `python h1_report.py --market us\|kr` | `reports/h1-forward/<market>-<YYYY-MM>.md`. 내용은 §3.8. "A0 현금 + 단기금리 이자"는 **계산만** 한다: 미국 FRED `DTB3` 전 거래일 값(A1), 국내 FRED `IR3TIB01KRM156N` 전달 값(A2), 연%/100/252 를 거래일마다(B4). 금리는 맥에서 FRED CSV 를 받고 `state/h1/rates/` 에 저장, 인터넷이 없으면 저장본을 쓰고 표시, 저장본도 없으면 그 줄만 "계산 불가" |

### 2.2 포워드 사전 등록 (운영 시작 전에 이 문서를 커밋한다)

> 아래는 **첫 `--h1` 실행 전에** 커밋한다. 운영 중에는 고치지 않는다. 고쳐야 하면 고친 이유를 커밋으로 남기고, 규칙이 바뀌면 두 장부를 새로 시작한다(아래 ④).

**① 기간**
- 시장마다 **시작 봉 S 부터 63거래일 이상**(S 포함, 그 시장 대기 자산 달력 = SPY/KS200 확정 봉으로 셈).
- S = 재현을 통과한 코드로 그 시장에서 처음 `--h1` 을 돌렸을 때 처리한 확정 봉. `state/h1/<market>/meta.json` 에 S·규칙 상수·코드 지문·이 문서의 sha256 을 적는다.
- 미국과 국내의 S 는 달라도 된다. 두 장부(A0·A1)의 S 는 같다.

**② 운영 기준** — 아래가 **모두** 맞아야 "H1 을 기본 장부로 할지 검토" 단계로 넘어간다.
1. **하루 장부 점검 오류 0건.** §4 의 오류(error) 등급 전부. 특히: 현금·단위가 음수, 체결가 ≠ 그날 시가, 중복 주문, 국내 거래정지일 체결.
2. **처리 빠진 날 0일, 두 장부 모두.** "빠진 날" = S ~ 마지막 봉 사이의 확정 봉인데 그 장부에 그날 하루 기록(day row)이 없는 날. 두 장부의 날짜 목록이 다르면 그것도 빠진 날로 본다. 늦게 따라잡은 날(§2.5)은 빠진 날이 아니지만 따로 센다(§10 Q2).
3. **재현(§5, 단계 5)을 통과한 코드만 돈다.** 실행 때마다 코드 지문을 재현 통과 기록과 비교하고, 다르면 그날은 돌지 않는다.

**③ 수익률은 기록만 한다.** A1−A0, 지수 대비, MDD 는 보고서에 숫자로 남기지만 **판정에 쓰지 않는다**(3개월은 너무 짧다). 보고서 첫머리에 이 문장을 고정으로 찍는다.

**④ 장부 오류가 나면**
1. 그날 처리를 멈춘다(그날은 아무것도 저장하지 않음, §2.3 단계 4).
2. 원인을 고친다. 고친 코드는 재현(§5)을 다시 통과해야 한다.
3. **두 장부를 모두 새로 시작한다**(`python h1.py restart --market <m> --reason "..."`). 옛 장부는 지우지 않고 보관 폴더로 옮긴다. 63거래일은 새 S 부터 다시 센다(§10 Q3).
4. 보고서에 오류·재시작을 적는다(`state/h1/<market>/errors.jsonl`, `state/h1/restarts.jsonl`).

**⑤ 판정에 쓰지 않는 것**: 수익률·MDD·A1−A0·지수 대비·팀장 성적. 팀장 판정 기록은 나중 채점(G4)용으로 쌓기만 한다.

**⑥ 고정 값**: §2.1 의 숫자와 §2.3 의 순서·여유값(1e-9, 쓸어 담기 문턱 1, 줄임 1e-12→1e-9→1e-6), 대기 자산 SPY/KS200, 총액, 비용. `meta.json` 에 적힌 값과 코드 상수가 다르면 그 시장 H1 은 돌지 않는다(규칙을 몰래 바꾸는 것을 막음).

### 2.3 하루 순서 (A0·A1) — `SIM_NOTES.md` §1 과 같은 모양

**준비 (실행마다 한 번, 시장별)**
1. 잠금 `state/h1/h1.lock` 을 잡는다(미국·국내 작업이 겹쳐도 판정 기록 파일이 꼬이지 않게). 못 잡으면 종료 코드 5.
2. 코드 지문(§3.3 `code_hash`)이 `state/h1/replay_pass.json` 에 있는지 본다. 없으면 종료 코드 3(운영 기준 ②-3).
3. 대기 자산(= 벤치마크) 확정 시세를 받는다: `main.load_benchmark(team.START, m)`. 실패(None)면 종료 코드 4, 아무것도 저장하지 않음. 이 시세의 날짜가 **H1 달력**이다.
4. 장부 6개 + `meta.json` 을 **엄격하게** 읽는다(§3.5). 하나도 없으면 새로 시작(S = 달력의 마지막 확정 봉). 일부만 있거나 형식이 다르거나 깨졌으면 멈춘다(종료 코드 2). 저장이 중간에 끊긴 흔적이면 §2.5 대로 백업에서 되살린다.
5. 처리할 봉 = 달력에서 `last_date` 다음 봉 ~ 마지막 확정 봉. 없으면 "이미 처리됨"을 찍고 끝(멱등, 종료 코드 0). `MAX_LATE_BARS`(5)개보다 많으면 사람 확인을 위해 멈춘다(종료 코드 6).
6. 종목 시세: 종목군(미국 `screener.universe(n)`, 국내 `KR_UNIVERSE[:n]`) + 두 장부의 보유·대기 주문 종목을 **한 번씩만** 받아 `cache` 에 넣는다(두 장부가 같은 데이터). 보유·대기 종목의 시세를 못 받으면 멈춘다(종료 코드 4, 할 일 1번). 종목군에만 있는 종목은 스크리너처럼 건너뛰고 기록한다.

**봉 t 하나** (처리할 봉마다 오래된 것부터 차례로. 두 장부가 같은 봉을 같이 지난다)

1. **스크리너(봉 t 기준) 한 번**: `screener.scan_frames(frames, universe, asof=t)` — 모든 종목 시세를 t 이하로 잘라서 판단한다. 결과를 두 장부가 같이 쓴다(F7).
2. **팀장 방식**: t 가 이번 실행의 마지막 확정 봉이면 LLM(`mode="llm"`), 따라잡는 옛 봉이면 LLM 을 부르지 않는다(`mode="late"`, 그 뒤 소식을 본 판정이 되므로). 재현은 `mode="replay"`(LLM 끔).
3. **트레이너마다(마라토너 → 스프린터 → 파이오니어), A0 → A1 순서로** `team.run_trainer(..., st=그 장부, h1=H1Day(...))` 를 부른다. 그 안의 순서:

**시가 (봉 t)** — 트레이너 지갑마다
- a. 시작 봉 S 면: 시작 금액을 S 날짜로 입금(`team._new_state` 와 같은 모양, h1.py 가 만듦).
- b. 대기 주문 나누기: **오늘 체결 가능** = 그 종목 확정 시세에 날짜 t 행이 있고 `main.open_price(행)` 이 None 이 아님. 나머지(국내 거래정지로 행이 없음 등)는 그대로 대기 목록에 남긴다(STAGE0 A5).
- c. **주식 매도**: 오늘 체결 가능한 매도 주문(보유 중인 종목만)을 그 종목 시가로 `PaperWallet.sell`. 주식 매도세 = 그 시장 값(국내 0.20%).
- d. **주식 매수**: 오늘 체결 가능한 매수 주문을 대기 목록 순서대로(이미 보유 중이면 건너뜀).
  - 주식 수 `n = shares_within_cap(start_cash, cap, P, fee, slip)`. 0 이면 "0주" 보류(`wallet.skip`, 사유 team.py 그대로).
  - 필요 금액 `need = E·n + E·n·fee`, `E = P·(1+slip)` (`PaperWallet.buy` 와 같은 계산 순서).
  - **A0**: `need > cash` 이면 "현금 부족" 보류.
  - **A1**: 지수 1단위 매도 수령액 `u_net = Q·(1−slip) − Q·(1−slip)·fee` (Q = 그날 지수 시가, 매도세 0). `avail = cash + units·u_net`. `need > avail·(1−1e-9)` 이면 **지수를 팔지 않고** "현금 부족" 보류(R2 I2·R6). 아니면 `need > cash` 일 때만 `u = min(units, (need − cash)/u_net·(1+1e-9))` 단위를 지수 시가로 팔고(모자란 만큼만), 주식을 산다. 매수가 그래도 실패하면 "현금 부족" 보류(판 지수는 되사지 않음 — e 에서 쓸어 담김).
- e. **A1 만: 쓸어 담기.** 현금 ≥ 1(달러/원)이면 `u = cash / (Q·(1+slip)·(1+fee)) · (1−s)` 를 지수 시가로 산다. s 는 1e-12 → 1e-9 → 1e-6 순서로 처음 성공하는 값(R2 `_sweep_to_index`). 시작 봉에는 시작 금액 전부가 여기서 지수로 간다(**첫날 전부 지수**, R2 와 같이 시작 봉의 시가). 매도 대금·서킷 정리 대금도 여기서 지수로 간다.

**종가 (봉 t)** — 트레이너 지갑마다 (team.py ②~④ 그대로)
- f. **보유 종목**: 그 종목의 t 이하 마지막 봉이 t 보다 앞이면(국내 거래정지, 미국 자료 지연) 그 종가로 평가만 하고 보유일수·매도 판단은 쉰다("판단 쉼", kr-fix-s0 I1). 아니면 어제부터 들고 있던 종목만 보유일수 +1, 대기 주문이 없으면 `brain.decide(t 이하 시세, 보유)` → 매도면 다음 시가 매도 주문.
  H1 만: 평가용 가격표에 **대기 자산 종가**를 넣는다(넣지 않으면 `PaperWallet.value` 가 지수를 평균 매입가로 평가한다 — §7 R14).
- g. **서킷**: `breaker.check(start_cash, prev_value, wallet.value(가격표))` — A1 은 현금 + 주식 + 지수 전체. 걸리면 대기 주문을 "보유 전부 매도"로 바꾸고(매수 대기는 버림) 영구 정지. 정리 대금은 다음 시가 e 단계에서 A1 은 지수로, A0 는 현금으로 남는다(R2 I11).
- h. **신규 후보**: 정지가 아니고 보유 + 매수 대기 < 5 이면, 1 의 후보 − 보유·대기 종목 − 오래된 봉 후보(신호 봉 < t). 후보가 있으면 **판정 기록을 거친 팀장**(§3.6)에게 묻는다 → veto 는 빠짐, hold 는 "팀장 hold" 보류, 확신도 < 0.5 는 보류, 남은 것을 확신도 높은 순(같으면 스크리너 순서) → 빈자리만큼 다음 시가 매수 주문(신호일 t).
- i. **기록**: 평가액 = 현금 + Σ주식 수×종가(정지 종목은 마지막 종가) + 지수 단위×지수 종가. `prev_value` = 평가액, `last_date` = t. 하루 기록(day row, §3.5)을 **변화가 없는 날에도** 붙인다(team.py 의 "저장 안 함" 규칙을 쓰지 않는다 — 빠진 날을 셀 수 있어야 하므로).

4. **점검**: 두 장부 각각과 짝(A0↔A1)을 §4 로 점검한다. 오류가 하나라도 있으면 그 봉과 그 뒤 봉은 **저장하지 않고** `errors.jsonl` 에 적고 종료 코드 2.
5. **저장**: 바로 전 장부 6개를 `backup/<전 last_date>/` 에 복사 → 6개 파일 + 판정 기록을 한꺼번에 저장(§2.5).

마지막에 두 장부 요약을 찍는다(§3.3 `summary_lines`).

**A0 와 A1 이 다른 곳은 여기뿐이다**

| 단계 | A0 | A1 |
|---|---|---|
| d 매수 가능 여부 | `need ≤ cash` | `need ≤ (cash + units·u_net)·(1−1e-9)` |
| d 매수 자금 | 현금 | 현금 먼저, 모자란 만큼만 지수 매도 |
| e 쓸어 담기 | 없음(현금으로 남김) | 현금 ≥ 1 이면 전부 지수 |
| f~i 평가 | 현금 + 주식 | 현금 + 주식 + 지수 |
| 시작 봉 | 현금 | 시작 금액 전부 지수(S 시가) |

**team.py 지금 동작과 일부러 다르게 한 것 (두 장부 모두, H1 경로에서만)**
- 같은 시가에서 **매도를 먼저** 처리한다(team.py 는 대기 목록 순서. 국내 정지로 밀린 옛 매수가 앞에 있으면 결과가 달라질 수 있다). R2 I1 과 같게 맞춘 것.
- 매일 저장한다(위 i).
- 스크리너를 봉 t 기준으로 자른다(국내 16:00~22:30 사이 실행 때 종목 봉만 하루 앞서는 문제를 없앰, §2.4).
- 팀장 판정을 기록을 거쳐 쓰고, 판정 글자를 정리한다(`" VETO"` → `veto`). §10 Q5.

### 2.4 국내 거래정지일 · 오래된 봉 · 기준 지수 확정 시각

| 경우 | H1 동작 | 근거 |
|---|---|---|
| 국내 거래정지일(Volume=0) | 그 행은 `main.confirmed_bars(..., market="kr")` 가 이미 버림 → 그 종목은 그날 "봉 없음" | kr-fix-s0 S0-2 |
| 정지 중 대기 주문 | b 에서 그대로 남김. 정지가 풀린 첫 거래된 봉의 시가에 c·d 로 체결. A1 은 그날에야 모자란 지수를 판다(정지 중에는 돈이 지수에 그대로 있음) | A5 |
| 정지 중 보유 종목 | 마지막 거래 종가로 평가, 보유일수·매도 판단 쉼 | kr-fix-s0 I1, R2 I14 |
| 정지 중 종목의 매수 후보 | 스크리너(마지막 봉 < 그 스캔의 최근 봉)와 team ④(신호 봉 < t)가 두 번 뺀다 | kr-fix-s0 M1 |
| 미국 보유 종목의 봉이 t 에 없음(자료 지연) | 위와 같이 "판단 쉼" + 경고 W2. 시세를 아예 못 받으면 멈춤(종료 코드 4) | 할 일 1번 |
| 국내 16:00~22:30 KST 실행 | 종목 봉은 오늘까지 확정, KS200 은 22:30 전이라 어제까지 → H1 달력의 마지막 봉 = 어제. 스크리너·판단·체결을 **모두 어제 기준으로 자른다**(asof). 오늘 봉은 다음 실행(22:30 뒤)에 처리 | `bench_cutoff` |
| KS200 이 멈춤(캐시 4주 멈춤 사례, kr-fix-s0 §6-5) | H1 달력이 안 늘어나 처리할 봉이 없음 → 경고 W5("종목 봉은 있는데 기준 지수 봉이 없음 N일"). 풀리면 따라잡기(§2.5). 달력 **중간에 빠진 날**이 있으면 오류 C26 | M8 |

### 2.5 시작 · 밀린 봉 · 멱등 · 끊긴 저장 · 재시작

- **시작**: 장부가 하나도 없으면 S = 그 실행의 마지막 확정 봉. A0·A1 모두 S 날짜로 입금, A1 은 S 시가로 전부 지수(R2 와 같다. 시가는 실행 전에 이미 지났지만 가격을 보고 고르는 판단이 아니라 고정 규칙이라 미리보기가 아니다 — §10 Q8). 첫 판단은 S 종가, 첫 주식 체결은 S 다음 봉 시가. `meta.json` 에 규칙 상수 묶음을 적는다.
- **밀린 봉(따라잡기)**: 맥이 꺼져 있었으면 다음 실행이 빠진 봉을 오래된 것부터 하나씩 처리한다(§2.3 "봉 t 하나"를 반복, 각 봉은 그 날짜 이하 데이터로만). 옛 봉에는 LLM 을 부르지 않고 폴백을 쓰고 판정 기록에 `status="late_no_llm"` 으로 적는다. 하루 기록에 `late=true`. 5봉 넘게 밀리면 멈추고 사람에게 묻는다.
- **멱등**: 여섯 장부의 `last_date` 가 모두 마지막 확정 봉 이상이면 스캔도 팀장 호출도 하지 않고 끝난다. 데이터가 나중에 고쳐져도 이미 처리한 봉은 다시 처리하지 않는다(team.py D2 와 같음).
- **끊긴 저장**: 저장은 "임시 파일 6개 다 쓰기 → 하나씩 교체" 순서다. 교체 도중 꺼지면 장부마다 `last_date` 가 다르다. 읽을 때 이 모양(일부는 t, 나머지는 t 전 봉)이고 `backup/<t 전 봉>/` 이 온전하면 **백업으로 되살린 뒤 t 를 다시 처리**한다(같은 데이터·같은 판정 기록이라 결과가 같다). 그 밖의 어긋남은 오류로 멈춘다.
- **재시작**: `python h1.py restart --market <m> --reason "..."` → `state/h1/<m>/` 전체를 `state/h1/archive/<m>-<시각>/` 로 옮기고 `state/h1/restarts.jsonl` 에 한 줄 적는다. 판정 기록(`analyst_cache.json`)은 시장 폴더 밖이라 그대로 남는다(지우지 않음). 다음 `--h1` 실행이 새 S 로 시작한다.

---

## 3. 인터페이스

### 3.1 파일 (바꿀 것 / 새로 만들 것)

| 파일 | 새/변경 | 왜 |
|---|---|---|
| `team.py` | 변경(작게) | `run_trainer(..., h1=None)` 갈고리 5곳, `__main__` 에서 `--h1` 이면 `h1.cli()`. `h1=None` 이면 지금 코드 그대로 |
| `paper_wallet.py` | 변경(작게) | `Holding.shares` 표기 `float`(F3). `sell(..., tax_rate=None)` 선택 인자(국내 지수 매도세 0 을 R2 처럼 `sell_tax_rate` 를 잠깐 바꿔치기하지 않고 넘기려고). 기본값이면 지금과 같음 |
| `analyst.py` | 변경(더하기만) | `normalize_verdict()`, `analyze_logged()`(상태·시각·모델·CLI 버전을 같이 돌려줌), `_build_prompt(..., context=None)`. **`analyze()`·`apply()` 는 그대로** |
| `screener.py` | 변경(더하기만) | `scan_frames(frames, order, asof)` — 이미 받은 시세로, 날짜 t 이하로 잘라서 스캔. **`scan()` 은 그대로** |
| `h1.py` | **새** | H1 실행기: 경로·엄격 읽기/저장·백업·잠금·코드 지문, 대기 자산 체결(A0/A1), 판정 기록·팀장 래퍼, 하루 기록, 따라잡기, 요약, `status`·`check`·`restart` 명령 |
| `h1_check.py` | **새** | 장부 점검 함수(§4). 시험·재현·맥 실행·보고서가 같이 씀. 순수 함수(인터넷·파일 쓰기 없음) |
| `h1_report.py` | **새** | 월간 보고서(F8), FRED 금리 받기·저장본, 이자 계산 |
| `h1_replay.py` | **새** | 단계 5 재현: R2 브랜치를 임시 폴더에 풀어 sim_team 기준값 → 새 코드 재현 → 비교 → 보고서·통과 기록 |
| `tests/test_h1.py` 등 | **새** | §6 시험(네트워크 없음). 골든 파일 `tests/golden/` |
| `README.md` | 변경(문서) | `--h1`·보고서·재현 사용법 |
| `docs/h1-forward-design.md` | 새 | 이 문서 |
| `main.py`, `markets.py`, `order_runner.py`, `broker/`, `live.py`, 브레인, `risk_guard.py`, `metrics.py` | **안 바꿈** | 필요한 것은 이미 있다(`load_benchmark`, `prices_for`, `confirmed_bars`, `open_price`, `save_json_atomic`, `make_wallet`) |

### 3.2 `team.py` 변경 (갈고리 5곳)

```python
def run_trainer(tname, cash, cap, breaker, screened, bar_date,
                st=None, cache=None, mk=None, h1=None):          # h1: h1.H1Day 또는 None
```
- **G0 시작**: `h1 is not None and st is None` 이면 `ValueError`(H1 장부는 h1.py 가 읽어서 넘긴다 — F1. `_load` 를 부르면 기존 `state/` 를 읽게 됨).
- **G1 ①체결**: `if h1 is not None: changed = h1.fill(st, tname, cap, bar_date, cache, m, logs) or changed` / `else:` 지금 ① 코드 그대로(들여쓰기만 한 칸).
- **G2 ②뒤**: `if h1 is not None: prices[h1.idle.code] = h1.idle.close`.
- **G3 ③서킷 발동 시**: `if h1 is not None: h1.note_breaker(tname, bar_date, hit)`.
- **G4 ④팀장**: `ask = h1.leader if h1 is not None else analyst.analyze` → `analysis = ask(tname, cands)`. 주문을 다 낸 뒤 `if h1 is not None: h1.note_leader(tname, bar_date, cands_before_apply, analysis, kept, slots)`.
- **G5 저장**: `if not changed and h1 is None: return ...`(H1 은 항상 진행). `if h1 is None: _save(tname, st, m)` / `else: h1.close_day(st, tname, bar_date, prices, value_now)`(파일 저장은 h1.py 가 6개를 한꺼번에).
- `__main__`: `_rest` 에 `"--h1"` 이 있으면 `--h1`(과 있으면 `--catch-up`)을 빼고 `import h1; sys.exit(h1.cli_team(n, _market, catch_up=...))`. `--h1` 이 없으면 지금 줄 그대로(`--catch-up` 도 보지 않음). `--h1` 이 숫자 앞에 와도 되게 먼저 뺀다.

h1 은 team 을 import 하지만 team 은 h1 을 맨 위에서 import 하지 않는다(순환 없음, `--h1` 없으면 h1 모듈이 아예 안 읽힘).

### 3.3 `h1.py`

```python
H1_DIR = team.STATE_DIR / "h1"                    # state/h1 (F1)
ARMS = ("A0", "A1")
TOTALS = {"us": 100_000, "kr": 100_000_000}       # F2
SCHEMA = {"us": "h1-us-1", "kr": "h1-kr-1"}
SWEEP_MIN = 1.0                                   # R2 SWEEP_MIN
SHORT_MARGIN = 1e-9                               # R2 R6 · _raise_cash
SWEEP_SHRINK = (1e-12, 1e-9, 1e-6)                # R2 _sweep_to_index
MAX_LATE_BARS = 5
H1_BREAKER = True                                 # §10 Q1
CODE_FILES = ("team.py", "h1.py", "h1_check.py", "main.py", "markets.py", "paper_wallet.py",
              "screener.py", "analyst.py", "risk_guard.py", "metrics.py",
              "marathoner_brain.py", "sprinter_brain.py", "pioneer_brain.py")

def idle_code(market) -> str                      # markets.MARKETS[market].benchmark (F4)
def ledger_path(market, arm, trainer, root=H1_DIR) -> Path   # root 아래인지 확인, 아니면 예외
def rule_constants(market) -> dict                # meta.json 에 적고 매번 비교할 상수 묶음
def code_hash(root_dir=REPO, files=CODE_FILES) -> str        # 파일별 sha256 → 합친 sha256
def check_gate(root=H1_DIR) -> None               # replay_pass.json 의 hashes 에 없으면 H1Refused(3)

def new_ledgers(market, start_date) -> dict[str, dict[str, dict]]   # {arm: {trainer: st}}
def load_ledgers(market, root=H1_DIR) -> tuple[dict | None, dict | None]   # (states, meta). 엄격
def save_ledgers(market, states, meta, decisions, root=H1_DIR) -> None     # 백업 → 임시 6개 → 교체

@dataclass(frozen=True)
class IdleBar:
    code: str; date: str; open: float; close: float

def decision_key(market, date, trainer, code) -> str          # "us|2026-11-05|마라토너|AAPL"
class DecisionLog:                                             # state/h1/analyst_cache.json
    def __init__(self, path): ...
    def get(self, key) -> dict | None
    def add(self, record: dict) -> None                        # 이미 있으면 예외(덮어쓰기 금지)
    def save(self) -> None                                     # 옛 기록이 글자 하나 안 바뀌었는지 확인 후 저장

class Leader:                                                  # team.run_trainer 의 h1.leader
    def __init__(self, market, date, log: DecisionLog, mode: str)   # "llm" | "late" | "replay" | "off"
    def __call__(self, trainer, cands) -> dict:                # analyst.apply 가 받는 모양 {code: {...}}

class H1Day:                                                   # team.run_trainer(h1=...)
    market: str; arm: str; idle: IdleBar; leader: Leader; late: bool; code_hash: str
    def fill(self, st, tname, cap, bar_date, cache, m, logs) -> bool    # §2.3 b~e
    def note_breaker(self, tname, bar_date, reason) -> None
    def note_leader(self, tname, bar_date, cands, analysis, kept, slots) -> None
    def close_day(self, st, tname, bar_date, prices, value) -> None     # day row

@dataclass
class DataSource:                                              # 운영/재현이 데이터 받는 곳을 바꿔 끼움
    benchmark: Callable[[], "pd.DataFrame | None"]             # 대기 자산 확정 시세
    prices: Callable[[str], "pd.DataFrame | None"]             # 종목 확정 시세
    universe: Callable[[int], list[str]]                       # 종목군 순서
    now: Callable[[], datetime]
def live_source(market) -> DataSource                          # main.load_benchmark / prices_for / screener.universe

def run(n=40, market="us", root=H1_DIR, source=None, leader_mode="llm",
        breaker=None, max_late=MAX_LATE_BARS, gate=True) -> int        # 종료 코드(§3.9)
def run_bar(market, t, states, frames, universe, idle: IdleBar, leader, breaker, late) -> dict
def summary_lines(market, states) -> list[str]
def restart(market, reason, root=H1_DIR) -> Path
def cli_team(n, market, catch_up=False) -> int                 # team.py --h1 이 부름. catch_up=True 면 그 실행만 max_late 제한 없음
def cli(argv=None) -> int                                      # python h1.py status|check|restart --market us|kr
```

- `Leader.__call__`: 후보마다 열쇠를 만들고, 기록에 없는 후보만 모아 `mode="llm"` 이면 `analyst.analyze_logged(trainer, 없는 후보, context=...)` 한 번, 아니면 부르지 않는다. 없는 후보 하나하나에 기록을 `add` 한다(LLM 이 답에서 빠뜨린 종목은 `status="missing_in_reply"` 폴백). 돌려주는 값은 기록에서 `source="llm"` 이고 판정이 있는 종목만 `{code: {"code", "verdict"(정리된 값), "conviction"(숫자 또는 None), "note"}}`. 빈 dict 는 team.py 에서 None(폴백)과 똑같이 동작한다(`apply` 가 손대지 않고, `verdicts` 가 비어 있음).
- 같은 트레이너에서 A0 가 먼저 묻고 A1 은 A0 에 없던 후보만 묻는다. 그래서 같은 (날짜, 트레이너, 종목)은 **반드시 같은 기록 한 줄**을 쓴다.
- 요약 예:
  ```
  [H1 us] 기준 봉 2026-11-05 · 시작 2026-11-05 · 1/63거래일
    A0 쉬는 돈=현금  $100,000 → $99,812 (-0.19%)
    A1 쉬는 돈=SPY   $100,000 → $100,231 (+0.23%) · SPY 37.123457단위
    A1−A0 +$419 · SPY 들고 있기(같은 시작, 소수 단위) +0.31%
    점검 오류 0 · 경고 0 · 팀장 LLM 3 / 폴백 0
    ※ 3개월은 판단하기에 너무 짧다 — 숫자는 기록용(사전 등록)
  ```

### 3.4 `paper_wallet.py` · `analyst.py` · `screener.py` (더하기만)

```python
# paper_wallet.py
@dataclass
class Holding:
    shares: float        # 주식은 정수 값, 대기 자산(지수)은 소수 단위 (H1)
    avg_price: float
def sell(self, code, price, shares, date=None, tax_rate=None) -> bool
    # tax_rate=None 이면 self.sell_tax_rate (지금과 같음). H1 지수 다리는 tax_rate=0.0

# analyst.py
def normalize_verdict(v) -> str | None      # " VETO" → "veto", "Hold" → "hold", 그 밖은 None
def _build_prompt(trainer, candidates, context=None) -> str
    # context=None 이면 지금과 글자까지 같은 문자열(골든 시험).
    # context={"date","market","currency","names"} 이면 머리에 한 줄: 날짜·시장·통화·종목명
def analyze_logged(trainer, candidates, timeout=TIMEOUT, context=None) -> tuple[dict | None, dict]
    # 반환 meta = {"status": "ok"|"no_claude"|"timeout"|"os_error"|"nonzero_exit"|"bad_json"|"empty",
    #              "asked_at": ISO 시각(시간대 포함), "elapsed_s": float, "returncode": int|None,
    #              "model": os.environ.get("ANTHROPIC_MODEL") 또는 None, "cli_version": "claude --version" 첫 줄 또는 None}
    # analyze() 는 손대지 않는다(같은 하위 함수 _extract_json 을 씀)

# screener.py
def scan_frames(frames: dict[str, "pd.DataFrame"], order: list[str], asof: str | None = None,
                min_bars: int = 70) -> tuple[dict[str, list[dict]], int]
    # scan() 과 같은 규칙(70봉 미만 제외, 보유 없음 기준 매수 신호, 마지막 봉 < 그 스캔 최근 봉이면 제외)을
    # 이미 받은 시세로. asof 가 있으면 각 시세를 asof 이하로 자른 뒤 판단. 순서 = order.
```

### 3.5 장부 파일 형식 `state/h1/<market>/<arm>/team_<trainer>.json`

team.py 상태 키를 그대로 두고 H1 칸을 더한다.

```jsonc
{
  "schema": "h1-us-1",
  "h1": {"market": "us", "arm": "A1", "trainer": "마라토너",
         "idle_code": "SPY", "idle_mode": "index",        // A0 는 "cash"
         "restart_no": 0, "code_hash": "…", "updated_at": "2026-11-06T07:12:03+09:00"},
  "wallet": {"name": "마라토너", "cash": 0.37, "currency": "USD", "fee_rate": 0.001, "sell_tax_rate": 0.0,
             "slippage": 0.0005,
             "holdings": {"SPY": {"shares": 74.21876543210987, "avg_price": 755.737},   // 소수 단위 (A1 만)
                          "AAPL": {"shares": 21, "avg_price": 271.26}},                // 정수
             "log": [ … PaperWallet 기록 그대로 (지수 다리도 매수/매도로 남음) … ]},
  "positions": {"AAPL": {"buy_price": 271.13, "days_held": 3, "shares": 21, "buy_date": "2026-11-06"}},
  "pending": [{"code": "MSFT", "action": "매수", "signal_date": "2026-11-09", "reason": "…", "note": null}],
  "prev_value": 60123.4, "stopped": false, "last_date": "2026-11-09",
  "start_cash": 60000.0, "start_date": "2026-11-05",
  "basis": {"SPY": 56021.3, "AAPL": 5704.1},          // 평균원가법 취득가(수수료·슬리피지 포함)
  "fills": [ 체결 기록 … ], "skips": [ 보류 기록 … ], "days": [ 하루 기록 … ]
}
```

- `positions` 에는 **주식만** 있다. 지수는 `wallet.holdings[idle_code]` 에만 있다(R2 I19 와 같음). 그래서 team.py ②·④ 가 지수를 종목으로 착각하지 않는다.
- A0 의 `holdings` 에는 대기 자산 코드가 **절대** 없다(점검 C10).

**체결 기록 (`fills` 한 줄)**
| 칸 | 내용 |
|---|---|
| `date`, `code`, `kind` | 체결일, 종목, `"stock"` 또는 `"idle"` |
| `side`, `qty` | `"buy"`/`"sell"`, 수량(주식 정수, 지수 소수 그대로) |
| `price` | 그날 시가(주식은 그 종목 행의 Open, 지수는 대기 자산 Open) |
| `exec_price`, `fee`, `slip_cost`, `tax`, `cash_delta` | 실제 체결가(±슬리피지), 수수료, 슬리피지 비용(= qty×price×slip), 매도세, 현금 변화 |
| `cash_before`, `cash_after`, `units_before`, `units_after` | 점검용 |
| `signal_date`, `reason` | 주식 다리: 신호일과 사유 **전체**(team.py 출력처럼 14자로 자르지 않음, 할 일 9번) |
| `purpose` | 지수 다리: `"start"`(첫날), `"fund:<종목>"`(그 매수 자금), `"sweep"` |
| `need`, `short` | 매수 필요 금액, 지수로 메운 금액(A1) |
| `realized`, `basis_out` | 매도만: 실현손익 = 순수령액 − 평균원가 × 판 비율 |

**보류 기록 (`skips` 한 줄)**: `date, code, kind("0주"|"현금부족"|"팀장hold"|"확신도낮음"), reason(사유 글), need, avail`. 빈자리가 모자라 주문을 못 낸 후보는 보류가 아니라 하루 기록의 `over_slots` 로 센다(R2 I23).

**하루 기록 (`days` 한 줄, 처리한 봉마다 꼭 하나)**
```jsonc
{"date": "2026-11-09", "run_at": "2026-11-10T07:11:40+09:00", "late": false, "code_hash": "…",
 "idle_open": 752.73, "idle_close": 754.35,
 "cash": 0.37, "stock_value": 5810.2, "idle_units": 74.2187654321, "idle_value": 55987.3, "value": 61797.87,
 "n_buys": 1, "n_sells": 0, "n_idle_legs": 2, "n_skips": 0, "over_slots": 0,
 "costs": {"fee": 61.5, "slip": 30.7, "tax": 0.0}, "events": [],
 "screened": ["AAPL", "MSFT"], "universe_hash": "…",
 "leader": [{"code": "AAPL", "key": "us|2026-11-09|마라토너|AAPL", "verdict": "buy", "effect": "ordered"}],
 "halted": [], "stale": []}
```
- `effect`: `"veto"`(빠짐) · `"hold"` · `"low_conv"` · `"ordered"` · `"over_slots"`.
- 종목군 목록 자체는 `state/h1/<market>/universe.json`(지문 → 목록, 한 번 쓰면 안 바꿈)에 둔다(할 일 11번: 미국 종목군이 바뀌면 알 수 있게).

**`state/h1/<market>/meta.json`**: `{"market","start_date","restart_no","created_at","rules": rule_constants(), "code_hash_at_start","design_doc_sha256","breaker": true}`.

### 3.6 판정 기록 `state/h1/analyst_cache.json` (F5 + 할 일 2번)

```jsonc
{"schema": "h1-leader-1",
 "entries": {
  "us|2026-11-09|마라토너|AAPL": {
    "market": "us", "date": "2026-11-09", "trainer": "마라토너", "code": "AAPL",
    "verdict": "buy",                  // normalize_verdict: "buy"|"hold"|"veto"|null
    "verdict_raw": "Buy",              // 팀장이 쓴 글자 그대로 (없으면 null)
    "conviction": 0.7, "conviction_raw": "0.7",
    "note": "실적 발표 전 변동성 주의",   // 500자까지
    "source": "llm",                   // "llm" | "fallback"
    "status": "ok",                    // ok | missing_in_reply | no_claude | timeout | os_error | nonzero_exit
                                       // | bad_json | empty | late_no_llm | replay_no_llm | disabled
    "model": null, "cli_version": "2.x.y (Claude Code)",
    "asked_at": "2026-11-10T07:11:22+09:00", "elapsed_s": 41.2,
    "call_id": "us|2026-11-09|마라토너|1",   // 같이 물은 후보 묶음 이름
    "batch": ["AAPL", "MSFT"],         // 그 묶음에 들어 있던 종목
    "signal": {"price": 271.4, "rsi": 47.2, "reason": "…", "date": "2026-11-09"}
  }}}
```
- **덮어쓰기 금지**: `add` 는 같은 열쇠가 있으면 예외. `save` 는 읽을 때의 옛 기록 전부가 글자 하나 안 바뀌고 그대로 있는지 확인한 뒤에만 저장(아니면 오류 C15). 재시작해도 지우지 않는다.
- 폴백도 기록한다(F5). 그래서 "이 판정은 팀장 부재였다"를 나중에 가려 채점할 수 있다.
- 채점(G4: 20거래일 뒤 "샀다면 수익 − 지수 수익")은 이번 범위 밖. 기록에 날짜·종목·신호 가격이 있어 나중에 시세만으로 계산할 수 있다.

### 3.7 그 밖의 파일 (`state/h1/` 아래, 모두 gitignore 된 `state/` 안)

| 파일 | 내용 |
|---|---|
| `h1.lock` | 실행 잠금(fcntl). 미국·국내 작업이 겹치면 뒤 작업이 기다리다 종료 코드 5 |
| `replay_pass.json` | 재현 통과 기록 `{"hashes": [{"code_hash", "files": {이름: sha256}, "passed_at", "report"}]}` |
| `<market>/errors.jsonl` | 점검 오류가 난 날(한 줄 = 한 번, 문제 목록 포함) |
| `<market>/backup/<날짜>/` | 저장 직전 장부 6개 + meta (최근 10개만 남김) |
| `<market>/universe.json` | 종목군 지문 → 목록 |
| `restarts.jsonl` | 재시작 기록 `{at, market, old_start, old_last, reason, archive}` |
| `archive/<market>-<시각>/` | 재시작 때 옮긴 옛 장부 |
| `rates/DTB3.csv`, `rates/IR3TIB01KRM156N.csv` | FRED 금리 저장본 + `fetched_at` |

### 3.8 월간 보고서 `h1_report.py`

```python
def build(market, month=None, root=H1_DIR, online=True) -> str      # 마크다운
def write(market, month=None, root=H1_DIR, out_dir=REPO/"reports"/"h1-forward", online=True) -> Path
def fetch_rates(series_id, cache_dir, timeout=20) -> Path | None    # urllib(표준 라이브러리). 실패하면 None
def load_rates(series_id, cache_dir) -> "pd.Series | None"          # FRED 원본·R2 형식 둘 다 읽음, "." 은 빈값
def rate_for_days(dates: list[str], series, rule: str) -> list[float]   # "prev_day" | "prev_month" (sim_team 과 같은 규칙)
def interest_overlay(dates, cash, rate_pct) -> list[float]
def realized(fills) -> dict
def cli(argv=None) -> int     # python h1_report.py --market us|kr [--month YYYY-MM] [--offline]
                              #        python h1_report.py --fetch-rates   (금리 저장본만 받기)
```

- **입력**: 장부 6개(`fills`·`skips`·`days`), `meta.json`, 판정 기록, `errors.jsonl`·`restarts.jsonl`, 금리 저장본. **대기 자산 시가·종가는 하루 기록에 이미 있어서** 지수 B&H 계산에 인터넷이 필요 없다.
- **출력**: `reports/h1-forward/<market>-<YYYY-MM>.md`. `--month` 가 없으면 마지막 처리 봉의 달(그달 말일까지 안 됐으면 "중간 보고"로 표시). 같은 달을 다시 만들면 덮어쓴다(장부가 원본이고 보고서는 계산값).
- **내용**
  1. 운영 기준 상황: 처리한 거래일 수(63 중 몇), 점검 오류 수, 빠진 날, 늦게 따라잡은 날, 재현 미통과 실행 수(0 이어야 함), 쓴 코드 지문, 재시작 이력. 고정 문장 "수익률은 기록만, 판정 안 함".
  2. 두 장부의 평가액·수익률(S 이후, 그달)·MDD(S 이후 매일 종가 평가액, `metrics.max_drawdown`, R2 와 같은 방식), **A1−A0**(금액, %p), **지수 B&H 같은 시작**(소수 단위 = 총액 ÷ (S 지수 시가 × (1+slip)(1+fee)), 매일 단위 × 지수 종가. R2 B9 와 같은 기준). 트레이너별 줄.
  3. 주식·지수·현금 비율(그달 평균, 그달 마지막 날).
  4. 매매: 주식 매수·매도, 지수 매수·매도 수, 보류(0주·현금부족·팀장 hold·확신도 낮음), 빈자리 부족, 비용(수수료·슬리피지·세금, 주식 다리/지수 다리 따로).
  5. **실현손익**(평균원가법, 그달·그해 누적, 주식/지수 따로): 미국은 "해외주식 양도세(연 250만 원 초과분) 인식용 참고값 — 달러 기준이고 환율·신고 방식(선입선출 등)은 반영 안 함(미확인)"을 적는다. A1 은 지수를 자주 팔아 실현 이익이 늘어날 수 있다(R2 한계 3).
  6. 팀장: 그달 판정 수(buy/hold/veto/없음 × llm/폴백, 상태별), 장부별 효과(veto 로 빠짐, hold 보류, 확신도 보류, 주문). 채점은 안 함.
  7. **A0 현금 + 단기금리 이자(계산만)**: `q_t = r_t/100/252`, `I_t = I_{t−1}·(1+q_t) + C_t·q_t`(C_t = A0 세 트레이너 종가 현금 합). "A0+이자" = A0 평가액 + I_t. 금리 규칙: 미국 = H1 달력의 **전 거래일 날짜 이하** 마지막 DTB3 값(A1), 국내 = **m−1월 1일 이하** 마지막 IR3TIB01KRM156N 값(A2, 없으면 이월). 쓴 금리 날짜 표를 같이 찍는다.
     - 근사임을 적는다: R2 A0 는 이자가 현금에 들어가 매수·서킷에 쓰이지만 여기서는 따로 쌓기만 한다. 금리는 보고서를 만들 때 받은 자료로 다시 계산한다(R2 와 같은 방식, 나중에 발표된 전달 값이 들어갈 수 있음).
     - **맥에서 금리 받기**: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3`, `...?id=IR3TIB01KRM156N`(API 키 없음, STAGE0 §2). 받으면 `state/h1/rates/` 에 저장. 첫 저장본은 R2 `data/rates/*.csv` 를 복사해도 된다(재현 단계가 복사해 둠).
     - **인터넷이 없으면**: 저장본을 쓴다. 필요한 날보다 저장본이 짧으면 마지막 값을 이월하고(A1·A2 의 "없으면 직전 값") 표에 "(오프라인: YYYY-MM-DD 값 이월)"을 붙인다. 저장본도 없으면 이 절만 "금리 자료 없음 → 계산 불가", 나머지는 그대로 만든다.
  8. 장부 다시 점검: `h1_check.check_ledger` 를 전체 기록에 다시 돌린 결과(오류 0 이어야 함)와 경고 목록.
  9. 메모: 오류·재시작, 한계(배당 미포함, ETF 운용보수 없음, 생존편향, 3개월).

### 3.9 종료 코드 (`team.py --h1`, `h1.py`)

| 코드 | 뜻 | 저장 |
|---|---|---|
| 0 | 정상(새 봉 처리 또는 이미 처리됨) | 처리한 봉 |
| 2 | 장부 점검 오류·장부 파일 이상 | **안 함** |
| 3 | 재현 통과 기록에 없는 코드 | 안 함 |
| 4 | 시세 받기 실패(대기 자산 또는 보유·대기 종목) | 안 함 |
| 5 | 다른 H1 실행이 잠금 중 | 안 함 |
| 6 | 밀린 봉이 5개 초과 — 사람 확인 필요 | 안 함 |

---

## 4. 하루 장부 점검 함수 (`h1_check.py`)

```python
@dataclass(frozen=True)
class Problem:
    level: str            # "error" | "warn"
    code: str             # "C1" … / "W1" …
    market: str; arm: str | None; trainer: str | None; date: str | None
    detail: str

def check_day(market, date, before: dict, after: dict, frames: dict, idle: IdleBar,
              calendar: list[str], decisions_before: dict, decisions_after: dict) -> list[Problem]
    # before/after: {arm: {trainer: st}} — 그 봉 처리 전후. frames: 그 실행이 쓴 종목 시세(확정 봉)
def check_pair(market, a0: dict, a1: dict, decisions: dict) -> list[Problem]
def check_ledger(market, arm, states: dict, calendar: list[str], frames: dict | None = None) -> list[Problem]
    # 전체 기록을 처음부터 다시 점검(보고서·재현). frames 가 없으면 기록된 가격으로만
def errors(problems) -> list[Problem]
```

- **쓰는 곳**: ① `h1.run` 이 봉마다 저장 직전에(오류면 저장 안 함) ② 시험(§6) ③ 재현(§5, 모든 봉) ④ 월간 보고서(전체 다시 점검).
- 허용 오차: 현금 `EPS_CASH = 1e-6`(달러/원), 비율 `EPS_REL = 1e-9`. 가격 비교는 **정확히 같음**(같은 메모리 값·JSON `repr` 왕복이라 같아야 함).

| 코드 | 등급 | 확인 | 사전 등록 ②-1 분류 |
|---|---|---|---|
| C1 | error | 모든 지갑 현금 ≥ −EPS_CASH, 유한한 수 | 현금 음수 |
| C2 | error | 보유 수량 > 0·유한, 주식 수량은 정수 값, 지수 단위 ≥ 0, `positions` ↔ `holdings`(주식) 수량 일치, 대기 자산 외에 `positions` 없는 보유 없음 | 단위 음수 |
| C3 | error | 체결마다 `price` == 그날 그 종목 행의 Open(주식) / 그날 대기 자산 Open(지수) | 체결가 ≠ 시가 |
| C4 | error | 체결일 == 처리한 봉 t. 주식 다리는 신호일 < 체결일 이고 그 사이에 그 종목의 거래된 봉이 없음(= "신호 다음 거래된 봉") | 체결가 ≠ 시가(날짜) |
| C5 | error | 대기 목록에 같은 종목 주문 2개 이상 없음, 보유 종목의 매수 주문 없음, 없는 종목의 매도 주문 없음, (종목·방향·날짜) 체결 중복 없음, 보유 + 매수 대기 ≤ MAX_POSITIONS | 중복 주문 |
| C22 | error | 주식 체결마다 전날 끝 대기 목록에 그 주문이 있었음(없는 주문이 체결되지 않음), 주문 하나는 한 번만 체결 | 중복 주문 |
| C6 | error | 체결일에 그 종목 확정 시세 행이 있고 Volume > 0(국내)·Open > 0. 원본 시세가 주어지면(시험·재현) Volume=0 날 체결 없음 | 국내 거래정지일 체결 |
| C7 | error | 하루 기록 `value` == 현금 + Σ주식×종가(정지 종목은 마지막 종가) + 단위×지수 종가 == `wallet.value(가격표)` (EPS_REL) | 장부 무결성 |
| C8 | error | 현금 원장: 전날 현금(시작 봉은 0 + 입금) + Σ`cash_delta` == 오늘 현금. 단위 원장: 전날 단위 + 매수 − 매도 == 오늘 단위 | 장부 무결성 |
| C9 | error | 비용식: 매수 `cash_delta = −(E·q + E·q·fee)`, 매도 `= E'·q − E'·q·fee − E'·q·tax` (E = P(1±slip)). tax = 국내 주식 다리 0.20%, 지수 다리 0, 미국 0 | 장부 무결성 |
| C10 | error | A1: 시가 처리 뒤(= 종가) 현금 < SWEEP_MIN. A0: 대기 자산 보유·지수 체결 0 | A1 규칙 |
| C11 | error | A1 지수 매도마다 `purpose="fund:<종목>"` 이고 그 종목 매수가 같은 날 성공했으며 `short ≤ u·u_net ≤ short·(1+2e-9) + EPS_CASH`. "현금 부족" 보류된 매수에 쓰인 지수 매도 없음 | A1 규칙 |
| C12 | error | "현금 부족" 보류마다 기록된 `need > avail`(A1 은 `avail·(1−1e-9)`), "0주" 보류마다 `shares_within_cap == 0` | A1 규칙 |
| C19 | error | 주식 매수 수량 == `shares_within_cap(start_cash, cap, price, fee, slip)` | F2 |
| C13 | error | 여섯 장부 `last_date` 가 같고, 각 장부 `days` 날짜 목록 == 달력의 S ~ t (빠짐·중복 없음) | **빠진 날**(②-2) |
| C14 | error | 짝 점검: A0·A1 날짜 목록 같음, 같은 (날짜, 트레이너)의 `screened` 같음, 하루 기록 `leader` 의 같은 종목은 같은 열쇠·같은 판정, 그 열쇠가 판정 기록에 있음 | F5·F7 |
| C15 | error | 판정 기록: 전 기록 ⊆ 후 기록, 옛 기록 글자 그대로 | F5 |
| C16 | error | 서킷 정지 뒤 새 주식 매수 체결 없음, 정지된 장부의 대기 목록은 매도만 | 서킷 |
| C17 | error | 보유일수 == 그 종목의 (매수일, t] 사이 거래된 봉 수 | team ② |
| C24 | error | 모든 숫자 유한(NaN·inf 없음) | 무결성 |
| C25 | error | `meta.json` 규칙 상수 == 코드 상수, 하루 기록 `code_hash` 가 재현 통과 목록에 있음 | **재현 통과 코드**(②-3) |
| C26 | error | 달력 구멍: S ~ t 에서 종목군 절반 이상이 거래한 날인데 H1 달력에 없음 | 빠진 날 |
| W1 | warn | 늦게 따라잡은 봉(`late`) | |
| W2 | warn | 보유·대기 종목이 t 에 봉 없음(국내 정지는 정보, 미국은 자료 지연 의심) | |
| W3 | warn | 팀장 폴백(`status != ok`) 수 | |
| W4 | warn | 종목군 지문이 전날과 다름 | |
| W5 | warn | 종목 최근 봉 > 대기 자산 최근 봉(기준 지수 지연·멈춤) | |
| W6 | warn | 보고서 때 다시 받은 시가가 기록된 체결가와 다름(데이터 수정 의심. 장부는 기록 기준) | |

(빈 번호 C18·C20·C21·C23 은 설계 중 다른 줄에 합쳤다: MAX_POSITIONS → C5, 0주 보류 → C12, 보유↔지갑 일치 → C2. 번호는 다시 매기지 않는다.)
- 운영 기준 ②-1 의 "점검 오류 0" 은 위 **error 등급 전부**가 0 이라는 뜻이다. warn 은 멈추지 않고 보고서에 센다.

---

## 5. 재현 계획 (단계 5) — `h1_replay.py`

### 5.1 무엇을 하나
1. **기준값(R2)**: `git archive origin/research-r2-2026-11-04` 를 **임시 폴더**에 푼다(연구 브랜치는 읽기만, 절대 안 고침). 그 폴더 안에 작은 실행 파일을 써 넣고 `python -I` 로 돌려 R2 자신의 `main.py`·`team.py`·`paper_wallet.py` 와 `sim_team.py` 로 계산한다. 실행 파일은 처음에 `main.__file__`·`sim_team.__file__` 이 임시 폴더 안인지 확인한다(지금 저장소 모듈을 잘못 읽으면 기준값이 아니게 됨, §7 R22).
   - `sim_team.run(Config(market=m, period=("2026-06-01","2026-11-03"), arm=a, cb=c, interest=False, with_refs=True))`, m ∈ {us, kr}, a ∈ {A0, A1}, c ∈ {"none", "current"} → 8개.
   - 기간을 튜플로 줄 수 있어 **sim_team 을 복사하거나 고칠 필요가 없다**(확인함). 시작은 두 시장 모두 2026-06-01(60번째 봉 이후 조건 충족), 끝 2026-11-03.
   - 저장: `fills`, `skips`, `orders`, `events`, `daily`(트레이너별 `v_`·`cash_`·`stock_`·`index_`), `refs["index_bh_frac"]["equity"]` → JSON.
2. **새 코드**: 지금 브랜치의 `h1.run` 을 **하루에 한 번씩** 부른다(맥에서 매일 도는 것처럼).
   - 임시 장부 폴더(`root=<임시>/h1`, 운영 `state/h1` 이 아님), `leader_mode="replay"`(LLM 끔 → `analyst.apply(후보, None)` 과 같음), `gate=False`.
   - `DataSource`: 연구 브랜치 `data/us/`(R0 20종목 + SPY), `data/kr/`(KR_UNIVERSE 32종목 + KS200)를 읽어 **그날 b 이하로 자른 뒤** `main.confirmed_bars(df, now=b 의 장 마감 뒤 시각, market)` 을 거친다(국내 Volume=0 행 버림 = 운영과 같은 함수). 시작일 데이터는 R2 처럼 처음부터(2014·2015~) 준다.
   - 종목군 순서를 R2 와 같게 **강제**: 미국 = `data/us/universe.json` 순서(SPY 제외), 국내 = `markets.KR_UNIVERSE` 순서(R2 브랜치 `markets.KR_UNIVERSE` 와 같은 32개·같은 순서인지 먼저 확인).
   - 서킷: (가) `breaker=CircuitBreaker(0.10, 0.07)` ↔ R2 `cb="current"`, (나) `breaker=CircuitBreaker(inf, inf)`(절대 안 걸림) ↔ R2 `cb="none"`. 코드 변경 없이 인자로만.
   - 매일 두 번 부른다: 두 번째는 아무 파일도 안 바뀌어야 한다(멱등). 매일 저장·읽기를 거친다(소수 단위 왕복 확인).
3. **비교** → `reports/h1-forward/replay-<날짜>.md`. 모두 맞으면 `state/h1/replay_pass.json` 에 코드 지문을 더한다. 첫 금리 저장본으로 R2 `data/rates/*.csv` 를 `state/h1/rates/` 에 복사해 둔다(이미 있으면 그대로).

### 5.2 반드시 같아야 하는 것

| # | 항목 | 같음의 뜻 |
|---|---|---|
| M1 | 체결 | (트레이너, 날짜, 주식/지수, 종목, 매수/매도) 모음이 정확히 같다. 짝마다 주식 수량 정수 같음, 지수 수량 상대 차 ≤ 1e-9, 체결가 **정확히 같음**, 현금 변화 차 ≤ 1e-9 × max(1, 값) |
| M2 | 보류 | (트레이너, 날짜, 종목, 종류 0주/현금부족) 모음이 같다 |
| M3 | 주문 | 신호일 < 2026-11-03 인 (트레이너, 신호일, 종목, 매수/매도) 모음이 같다. 사유 글도 같다 |
| M4 | 매일 값 | 날짜 × 트레이너마다 종가 평가액·현금·주식 평가액·지수 평가액·지수 단위, 그리고 팀 합계: 상대 차 ≤ 1e-9 |
| M5 | 서킷 | 발동한 (트레이너, 날짜)가 같다((가) 설정) |
| M6 | 지수 B&H | 보고서 함수의 "같은 시작 지수 B&H" 매일 값 == R2 `index_bh_frac` equity(마지막 날은 R2 가 매도 비용을 뺀 값이라 단위 × 종가로 비교) |
| M7 | 이자 계산 | 보고서의 금리 규칙(`rate_for_days`)과 이자 식을 R2 `sim_team.rate_for_days` 로 따로 계산한 값과 비교: 날마다 금리 같음, 이자 상대 차 ≤ 1e-9. (참고로만: "A0+이자" 끝값과 R2 A0 `interest=True` 끝값의 차이를 적는다 — §3.8 근사) |
| M8 | 장부 점검 | 재현 장부 전체에 `check_ledger` 오류 0, 매일 `check_day` 오류 0 |
| M9 | 멱등·저장 | 하루 두 번째 실행에서 파일 지문 그대로·판정 기록 늘지 않음. 저장 → 읽기 뒤 지수 단위가 `float.hex` 까지 같음 |
| M10 | 같은 결과 | 재현을 두 번 돌리면 비교 보고서 숫자가 같다 |

### 5.3 받아들이는 차이 (이 목록 밖의 차이는 설명하거나 고친다)

| # | 차이 | 처리 |
|---|---|---|
| K1 | R2 는 국면 마지막 봉(2026-11-03)의 신호를 버린다(I17). H1 은 주문으로 남긴다 | 신호일 2026-11-03 주문은 비교에서 뺀다 |
| K2 | R2 `final`·`metrics` 는 끝에 매도 비용을 뺀 값, H1 은 종가 평가 | 매일 종가 평가액만 비교(M4) |
| K3 | 종목군: 재현은 R2 종목군을 강제. 운영 미국은 S&P500 섞기 40종목 | 재현 안에서는 차이 아님. 운영과 다른 점으로 보고서에 적음 |
| K4 | 스크리너 70봉 기준(H1) vs R2 60봉(A7, R11) | 이 창에서는 모든 종목이 창 전에 70봉 이상(확인함) → 영향 없음. 재현이 이것을 다시 확인 |
| K5 | 스크리너의 "오래된 봉" 기준은 그 스캔의 최근 봉, R2 는 "그 종목 오늘 봉 있음" | 이 창에서는 빠진 봉 0 → 같음. 재현이 매일 "스캔 최근 봉 == t" 를 확인 |
| K6 | team.py 의 "후보·보유·주문 없으면 저장 안 함" / "이미 처리됨" | H1 은 매일 저장하고 봉마다 처리 → R2 와 같은 쪽. 운영 team.py 와의 차이로만 적음 |
| K7 | 현금 이자: R2 기본은 켬 | 기준값을 `interest=False` 로 돌림 → 차이 아님(이자는 M7 로 따로) |
| K8 | 판정 기록·하루 기록의 팀장 칸 | R2 에 없음. LLM 끔이라 모두 `replay_no_llm` 폴백 → 비교 대상 아님 |
| K9 | 국내 매도세: R2 날짜별 표, H1 은 `markets` 0.20% 고정 | 이 창(2026)은 둘 다 0.20% → 같음. 다른 해 창을 돌릴 때는 기준값 쪽 표를 0.20% 로 바꿔 넣어 맞춘다(실행 파일 안에서만, 연구 브랜치 파일은 안 고침) |
| K10 | 지표 계산 길이: 운영은 2024-06-01 부터 받음(team.START), 재현은 처음부터 | 재현은 R2 와 같게 처음부터. 운영과의 차이(RSI 의 지수평활 시작값 영향 ≈ (13/14)^500 ≈ 1e-16)는 시험 T-RSI 로 무시할 크기임을 확인 |
| K11 | R2 `over_slots` 는 트레이너 합계, H1 은 하루 기록 | 합계만 비교(같아야 함, 참고) |
| K12 | 부동소수점 더하는 순서 | 허용 오차 1e-9 안 |

### 5.4 보조 재현 (권장, 필수 아님)
- 국내 정지 구간 창 2025-09-01 ~ 2025-12-31(207940 정지 2025-10-30 ~ 11-21 포함). 미리 돌려 보니 **정지를 가로지르는 대기 주문은 이 창에 없다**(정지 중 후보 제외만 지나감). 그래서 정지 체결 규칙은 합성 시험 T-HALT 가 주로 맡는다. 이 창은 K9 처리(0.20% 고정)를 넣어 돌린다.

### 5.5 통과 조건
- 8개 조합 모두 M1~M10 이 맞고, 남은 차이가 K1~K12 로만 설명된다 → 통과. 하나라도 설명 안 되는 차이가 있으면 **통과 아님**(고치거나, 왜 다른지 적고 사람이 받아들일지 정한다).
- 맥에서도 돌릴 수 있다(약 몇 분, 인터넷 불필요. `git fetch origin research-r2-2026-11-04` 는 필요). 코드를 바꿀 때마다 다시 돌린다(운영 기준 ②-3).

---

## 6. 시험 계획 (오프라인, 합성 데이터)

모두 `pytest -q` 에 들어가고 인터넷·claude·키 없이 돈다. 시세는 `test_flow.synth` 같은 결정적 가짜 시세, 장부 폴더는 `tmp_path`.

| ID | 규칙 | 시험 |
|---|---|---|
| T-F1a | F1 경로 | 6개 경로 모양, `state/h1` 밖 경로는 예외 |
| T-F1b | F1 격리 | 가짜 `state/team_*.json`·`state/kr/*` 를 두고 H1 을 돌림 → 그 파일 지문·수정시각 그대로, `team._load`·`team._save`·`main.load_state_file` 은 불리면 실패하도록 바꿔 끼움 |
| T-F2 | F2 시작·규칙 | 새 장부 총액(미국 100,000·국내 1억)·몫 60/30/10·상한이 시작 예산 기준, MAX_POSITIONS(대기 매수 포함), 확신도 0.5 경계·None 통과·문자열 확신도, hold 보류, veto 빠짐 — team.py 기존 시험 장면을 H1 두 장부로 다시 |
| T-A1-1 | 첫날 전부 지수 | S 뒤 A1 현금 < 1, 단위 = 예산/(Q(1+s)(1+f))·(1−1e-12), A0 현금 = 예산 |
| T-A1-2 | 같은 시가 순서 | 한 날에 매도 1·매수 2: 매도 대금 먼저, 모자란 만큼만 지수 매도, 남은 돈 지수로 — 손으로 계산한 숫자와 같음 |
| T-A1-3 | 현금 부족 | need > 현금+지수: "현금 부족" 보류, 그 매수용 지수 매도 0, 단위 그대로 |
| T-A1-4 | 경계 여유 | need = avail·(1−1e-9) 근처 위/아래, 매수 실패 뒤 되사기 없음(R6) |
| T-A1-5 | 쓸어 담기 문턱 | 현금 0.99 는 그대로, 1.00 은 지수로. 줄임 1e-12 실패 → 1e-9 성공 경로 |
| T-A1-6 | 지수 다리 비용 | 미국·국내 지수 매수·매도 수수료+슬리피지, 국내 지수 매도세 0 / 주식 매도세 0.20%(`sell(tax_rate=0.0)`) |
| T-A1-7 | 소수 단위 | 저장 → 읽기 `float.hex` 같음, 정수 주식은 int 로 돌아옴, 화면 6자리, `Holding` 표기 |
| T-A1-8 | A0 대조 | A0 는 지수 체결·보유 0 |
| T-D3 | 신호 t → 체결 t+1 | 두 장부 모두 체결 날짜·시가 |
| T-F4 | 대기 자산 | 코드 = 벤치마크, 국내는 `allow_index` 경로로만 받음, 시가·종가가 그 시세 값 |
| T-F5a | 같은 판정 | 가짜 analyze 가 호출마다 다른 답을 내게 해도 A0·A1 이 같은 (날짜, 트레이너, 종목)에 같은 판정 |
| T-F5b | 없을 때만 호출 | 호출 횟수 셈. 같은 봉 두 번째 실행 → 0번. A1 은 A0 에 없던 후보만 |
| T-F5c | 폴백 종류 | claude 없음·시간 초과·0 아닌 종료·JSON 깨짐·답에서 빠진 종목 → 각 `status`, 규칙 폴백 동작 |
| T-F5d | 덮어쓰기 금지 | `add` 두 번 → 예외. 파일의 옛 기록을 손으로 바꾸면 C15 오류 |
| T-F5e | 글자 정리 | `" VETO"`·`"Hold"` → H1 에서 veto·hold 로 동작. 운영 `analyst.apply` 동작은 그대로 |
| T-F5f | 늦은 봉 | 따라잡는 옛 봉은 LLM 0번, `late_no_llm` |
| T-F6a | order_runner 격리 | `state_path("us"\|"kr", 트레이너)` 가 `state/h1` 아래가 아님 |
| T-F6b | 〃 | `STATE_DIR` 을 tmp 로, 그 안에 대기 주문 있는 H1 장부만 → `load_states` 빈 결과, `place(FakeBroker)` 주문 0건 |
| T-F6c | 〃 | `order_runner.py` 소스에 `h1` 없음, `h1*.py` 가 `order_runner`·`broker` 를 import 하지 않음 |
| T-F7a | `--h1` 인자 | `team.py 40 --market us --h1`, `--h1 40` 둘 다. `--h1` 없으면 `team.run` 이 같은 인자로 불리고 `h1` 이 `sys.modules` 에 없음 |
| T-F7b | 바이트 같음 | **골든**: 코드를 바꾸기 전 커밋(847ad13)으로 만든 `team.run` 결과(상태 JSON·화면 출력)를 `tests/golden/` 에 두고, 바꾼 코드의 결과가 바이트까지 같음(미국·국내). `analyst._build_prompt(context=None)` 문자열도 골든 |
| T-F7c | 같은 스크리너 | 봉마다 `scan_frames` 1번, 두 장부가 같은 후보 |
| T-F7d | 멱등 | 같은 봉 두 번 → 파일 지문 그대로, "이미 처리됨" |
| T-SCR | 스크리너 동등 | 같은 가짜 시세에서 `scan_frames(...)` == `scan()`(prices_for 바꿔 끼움), asof 로 자른 결과 == 미리 자른 시세 결과 |
| T-F8a | 보고서 숫자 | 손으로 만든 장부로 평가액·수익률·MDD·A1−A0·지수 B&H·비율·매매 수·비용·실현손익(평균원가 손계산)·팀장 수 |
| T-F8b | 금리 규칙 | 미국 전 거래일(빈 날 이월, 그날 값은 다음 날), 국내 m−1월(빈 달 이월), 이자 식 손계산 |
| T-F8c | 오프라인 | `urlopen` 이 실패하게 → 저장본 사용·"오프라인" 표시. 저장본 없음 → 그 절만 "계산 불가", 파일은 만들어짐 |
| T-CHK | 점검 음성 대조 | §4 오류 코드마다 그 잘못을 일부러 넣은 장부 → 그 코드로 오류(예: 현금 −1, 단위 −1e-6, 시가 아닌 체결가, 정지일 체결, 중복 주문, 없는 주문 체결, value 어긋남, 원장 어긋남, A1 현금 ≥ 1, 보류인데 지수 매도, 빠진 날, 판정 다름, 판정 기록 수정, 정지 뒤 매수) |
| T-HALT | 국내 정지 | 합성 국내 시세에 Volume=0 3일: 대기 매수는 정지 중 체결 0 → 첫 거래된 봉 시가 체결, A1 은 그날만 지수 매도. 보유 종목 판단 쉼·보유일수 그대로·마지막 종가 평가. 정지 종목 후보 제외. 저장/읽기 거침 |
| T-STALE | 미국 오래된 봉 | 보유 종목 오늘 봉 없음 → 판단 쉼 + W2. 종목군 종목 오래된 봉 → 후보 아님. 보유 종목 시세 실패 → 종료 코드 4, 저장 없음 |
| T-CUT | 국내 확정 시각 | 20:00 KST(종목 오늘 봉 있음, KS200 오늘 봉 버림) → 어제 봉만 처리, 오늘 날짜 후보·주문 없음. 22:31 KST → 오늘 처리 |
| T-DST | 미국 서머타임 | 2026-03-08·11-01 앞뒤, 한국 시각 07:10 실행 → 바로 전 미국 거래일이 확정 봉 |
| T-LATE | 따라잡기 | 2봉 밀림 → 차례로 처리(각 봉은 그 날짜 이하 데이터), 옛 봉 `late=true`. 6봉 밀림 → 종료 코드 6 |
| T-LOOK | 미리보기 없음 | 봉 t 를 전체 시세로 처리 == t 에서 자른 시세로 처리. t 의 종가·고가·저가·거래량과 그 뒤 봉을 흔들어도 t 시가 체결·t 전날까지 기록 그대로(R2 점검 3·16 과 같은 생각) |
| T-GATE | 재현 통과 코드만 | 지문 다름 → 종료 코드 3, 파일 0개 씀. 지문 있음 → 돎. `meta` 상수 다름 → 멈춤 |
| T-LOCK | 잠금 | 잠금 중 두 번째 실행 → 종료 코드 5 |
| T-CRASH | 끊긴 저장 | 6개 중 3개 교체 뒤 멈춘 상황 → 다음 실행이 백업으로 되살려 다시 처리, 끊기지 않은 실행과 결과 같음 |
| T-STRICT | 깨진 장부 | JSON 깨짐·형식 다름 → 멈춤(종료 코드 2), 보관·새로 시작 **안 함**(운영 `load_state_file` 과 다름, 할 일 3번) |
| T-CB | 서킷 | A1 서킷이 지수 포함 평가액으로 잼, 발동 → 다음 시가 전량 정리, A1 대금 → 지수, A0 → 현금, 그 뒤 매수 없음. 절대 안 걸리는 서킷 인자 |
| T-PW | 지갑 | `sell(tax_rate=None)` 은 지금과 같음(기존 시험 그대로 통과), `tax_rate=0.0` 은 세금 0 |
| T-AN | 팀장 래퍼 | `analyze_logged` 상태별(which·subprocess 바꿔 끼움), `analyze` 결과가 `analyze_logged(...)[0]` 과 같음 |
| T-RSI | 지표 길이 | 2024-06-01 부터 계산한 RSI 와 처음부터 계산한 RSI 가 2026-06 이후 차 < 1e-9 |

---

## 7. 위험 목록 — R2 와 조용히 달라질 수 있는 곳

| # | 위험 | 왜 위험한가 | 막는 법 / 시험 |
|---|---|---|---|
| R1 | 같은 시가 순서 | 매도 전에 매수하면 지수를 괜히 팔고 왕복 비용. 정지로 밀린 옛 매수가 앞이면 결과가 바뀜 | 매도 → 매수 → 쓸어 담기 고정. T-A1-2, T-HALT, 재현 M1 |
| R2 | 쓸어 담기 문턱 | `≥ 1` 을 `> 1`, 또는 매수 전/매수 없는 날 빼먹기 | 상수 하나, T-A1-5, 점검 C10, 재현 M4 |
| R3 | 여유값 1e-9 | 빼면 경계에서 지수만 팔고 매수 실패(R6) | `SHORT_MARGIN`, T-A1-4, C11·C12 |
| R4 | 반올림 | 지수 단위를 저장·표시 때 반올림하면 원장이 어긋남. `int()` 로 바꾸는 곳 | 저장은 float 그대로, 화면만 6자리. T-A1-7, C8, 코드에서 보유 수량 `int(` 검색 |
| R5 | 지수 다리 비용 | 국내 지수에 주식 매도세 0.20% 를 붙이거나, 지수에 비용을 안 붙임 | `sell(tax_rate=0.0)`, T-A1-6, C9 |
| R6 | 시작 봉 | 입금 날짜, 첫날 전부 지수(S 시가), 서킷 `prev_value=None`, 지수 B&H 시작점이 서로 다르면 비교가 틀어짐 | T-A1-1, 재현 첫날 M1·M4·M6 |
| R7 | KS200 22:30 vs 종목 16:00 | 16:00~22:30 실행이면 종목만 하루 앞섬 → 장부 날짜와 신호 날짜가 섞임 | asof 자르기(스크리너·판단·체결), T-CUT |
| R8 | 미국 서머타임 | launchd 는 한국 시각. 실행이 16:15 ET 전이면 하루 늦음(빠지진 않음) | `confirmed_bars` 가 ET 로 판단, 07:10 KST 는 사계절 모두 마감 뒤, T-DST |
| R9 | 빠진 날 | 맥이 꺼져 하루를 건너뛰면 그날 신호가 사라짐 | 봉 하나씩 따라잡기, C13, T-LATE |
| R10 | 두 장부 판정이 다름 | 따로 물으면 같은 종목에 다른 답 | 판정 기록 열쇠, C14, T-F5a |
| R11 | 기존 장부 건드림 | `_load` 가 `state/team_*.json` 을 읽거나 예전 형식으로 보관 | G0 예외, 경로 확인, T-F1b |
| R12 | order_runner 가 H1 장부로 주문 | 진짜(모의) 계좌에 주문 | 경로가 다름 + T-F6 |
| R13 | `--h1` 없는 동작 변화 | 운영 장부 결과가 바뀜 | 갈고리 5곳만, 골든 T-F7b |
| R14 | 지수 평가 누락 | `PaperWallet.value` 는 가격표에 없는 종목을 **평균 매입가**로 평가 → 서킷·평가가 조용히 틀림 | G2, C7, T-CB |
| R15 | 서킷 의미 | 운영 team.py 는 저장 안 한 날 `prev_value` 가 며칠 전 값(I15). H1 은 매일 갱신 | 매일 저장, 재현 (가) 설정 M5 |
| R16 | 데이터 수정 | 제공처가 시가·종가를 나중에 고치면 다시 계산한 값이 달라짐 | 체결가·대기 자산 시가/종가를 장부에 저장, 보고서는 기록 기준, W6 |
| R17 | KS200 멈춤 | 달력이 안 늘어나거나 구멍 | W5, C26, 따라잡기 |
| R18 | 미국 종목군 변화 | S&P500 목록 하나만 바뀌어도 40종목이 바뀜 | 하루 기록 `universe_hash`·`universe.json`, W4 |
| R19 | 지표 길이 | 운영 2024-06-01 시작 vs R2 전체 | T-RSI |
| R20 | 가격 같음 비교 | float 를 문자열로 바꿔 저장하면 같음 비교가 깨짐 | JSON float 그대로, C3 는 정확히 같음 |
| R21 | 국내 정지일 체결 | 불가능한 체결 | 데이터 층(Volume=0 버림) + C4·C6, T-HALT |
| R22 | 기준값이 R2 가 아님 | 재현 실행 파일이 지금 저장소 모듈을 읽으면 "자기와 비교" | 임시 폴더 안에서 실행, 모듈 경로 확인 |
| R23 | 늦은 봉의 LLM 미리보기 | 다음날 소식을 보고 전날 후보를 판정 | 늦은 봉은 LLM 안 부름(T-F5f) |
| R24 | 동시 실행 | 판정 기록 파일이 덮임 | 잠금(T-LOCK), 판정 기록 저장 때 옛 기록 확인 |
| R25 | 이자 근사 | "A0+이자"는 R2 A0(이자 켬)와 조금 다름 | 보고서에 근사라고 적음, 재현 M7 에서 차이 크기를 참고로 적음 |
| R26 | 국내 세율 고정 | `markets` 0.20% 고정. 2027 에 세율이 바뀌면 그대로 | 이번 기간(2026-11 ~ 2027-02)에 세율 변경 공지가 있으면 재시작 사유로 적음(§10 Q9) |
| R27 | 마라토너 구조적 보류 | 30% × 5종목 = 150% → 4·5번째 매수가 늘 "현금 부족" | team.py 그대로. 보고서에서 보류를 읽을 때 같이 적음(R2 P6) |
| R28 | 실현손익 방식 | 평균원가법은 세법 신고 방식과 다를 수 있음 | 참고값이라고 적음(미확인) |
| R29 | 판정 기록 망가짐 | 파일이 깨지면 같은 판정 보장이 깨짐 | 원자적 저장, 백업, C15 |

---

## 8. 맥 운영

### 8.1 처음 한 번
```bash
cd /Users/나/claude-stock
git fetch origin && git checkout <H1 코드를 합친 브랜치> && git pull
python -m pip install -r requirements.txt
python -m pytest -q                                      # 전부 통과
git fetch origin research-r2-2026-11-04                  # 재현 기준값 데이터
python h1_replay.py                                      # 단계 5. "통과" + state/h1/replay_pass.json
python h1_report.py --fetch-rates                        # (선택) FRED 금리 저장본 미리 받기
mkdir -p logs
which claude                                             # launchd PATH 에 넣을 경로 확인(아래)
```
- 첫 `--h1` 실행이 그 시장의 시작 봉 S 를 정한다. 그 전에 이 문서(사전 등록)가 커밋돼 있어야 한다.

### 8.2 실행 시각 (맥 시계 = 한국 시간)
| 시장 | 실행 | 시각 | 메모 |
|---|---|---|---|
| 국내 | `python team.py 40 --market kr --h1` | **월~금 23:05** (KS200 22:30 확정 뒤) + 보조 **화~토 07:40** | 보조 실행은 23:05 가 실패했거나 KS200 캐시가 늦은 날을 챙긴다(이미 처리됐으면 바로 끝남) |
| 미국 | `python team.py 40 --market us --h1` | **화~토 07:10** + 보조 **화~토 08:40** | 07:10 KST = 겨울 17:10 ET / 여름 18:10 ET → 사계절 모두 16:30 ET 뒤. 서머타임 때 시각을 안 바꿔도 된다 |
| 둘 다 | `python h1_report.py --market us` / `--market kr` | 매달 첫 평일 아침(그 전 달) + 아무 때나 | 인터넷이 있으면 금리도 받음 |
| 상태 | `python h1.py status --market us` | 아무 때나 | 시작 봉, 처리한 거래일 수, 마지막 봉, 오류·경고 |

- 기존 운영 작업(`team.py 40 --market kr` 22:35, `--market us` 06:30, order_runner)은 그대로 둔다. H1 은 따로 돈다(장부 폴더가 다름). 팀장 호출이 하루에 대략 두 배가 된다.
- 휴장일에는 새 봉이 없어 "이미 처리됨"으로 바로 끝난다. 할 일 없음.

### 8.3 launchd
`docs/broker-run.md` 의 plist 모양 그대로, 아래만 다르게.
```xml
<key>Label</key><string>com.claude-stock.h1-kr</string>
<key>WorkingDirectory</key><string>/Users/나/claude-stock</string>
<key>EnvironmentVariables</key>
<dict><key>PATH</key><string>/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>  <!-- which claude 로 나온 폴더를 넣기 -->
<key>ProgramArguments</key>
<array>
  <string>/bin/sh</string><string>-c</string>
  <string>/Users/나/.venv-cs/bin/python team.py 40 --market kr --h1 || osascript -e 'display notification "H1 국내 실행 실패 (logs/h1-kr.log)" with title "claude-stock"'</string>
</array>
<key>StartCalendarInterval</key>
<array> <!-- 월~금 23:05, 화~토 07:40 : dict 를 요일마다 -->
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
  <!-- … -->
</array>
<key>StandardOutPath</key><string>/Users/나/claude-stock/logs/h1-kr.log</string>
<key>StandardErrorPath</key><string>/Users/나/claude-stock/logs/h1-kr.log</string>
```
- launchd 의 PATH 에 `claude` 가 없으면 팀장은 매일 폴백(`no_claude`)이 된다 → 로그와 보고서의 "팀장 폴백 수"로 알 수 있다(할 일 목록: launchd 에서 claude 경로 미확인).
- 잠자기 중에는 안 돈다: `sudo pmset repeat wakeorpoweron MTWRFS 07:00:00` 처럼 깨우기를 건다. 깨어난 뒤 launchd 가 놓친 작업을 한 번 돌리고, H1 은 밀린 봉을 따라잡는다.
  `pmset repeat` 는 깨우는 시각을 하나만 둘 수 있다. 국내 23:05 에 맥이 자고 있으면 보조 07:40 실행이 전날 봉을 처리한다(늦은 날이 아님 — 그 시각에도 마지막 확정 봉이 전날 봉이므로).

### 8.4 오류가 나면

| 종료 코드 | 화면 | 할 일 |
|---|---|---|
| 2 | `장부 점검 오류` + 문제 목록 | 그날은 저장 안 됨(장부 안전). ① 로그와 `state/h1/<m>/errors.jsonl` 을 Claude Code 에 보여 주고 원인 찾기 ② 고친 코드로 `python h1_replay.py` 다시 통과 ③ `python h1.py restart --market <m> --reason "<무엇이 틀렸나>"` ④ 다음 실행부터 새 S, 63거래일 다시 셈(사전 등록 ④) |
| 3 | `재현을 통과하지 않은 코드` | `git pull` 로 코드가 바뀐 것. `python h1_replay.py` 를 돌려 통과시킨 뒤 다시 실행(그날 안에 하면 빠진 날 없음) |
| 4 | `시세 받기 실패` | 인터넷·FinanceDataReader 확인(`docs/kr-fix-s0.md` §5 명령). 보조 실행 시각에 다시 돈다. 하루 넘게 실패하면 다음 성공 실행이 따라잡음 |
| 5 | `다른 H1 실행 중` | 잠시 뒤 저절로 다음 실행. 계속 나면 멈춘 python 이 있는지 확인 |
| 6 | `밀린 봉 N개` | 맥이 오래 꺼져 있었음. 보고서에 적힐 늦은 날을 확인하고 `python team.py 40 --market <m> --h1 --catch-up` 으로 따라잡기를 허락 |
| (경고) | `팀장 폴백 N`, `KS200 늦음` 등 | 멈추지 않음. 보고서에 셈. 폴백이 매일이면 launchd PATH 확인 |

---

## 9. 구현 순서 (단계)

| 단계 | 내용 | 끝 조건 |
|---|---|---|
| 1 | 설계(이 문서) | 사람 검토 |
| 2 | 골든 만들기(지금 코드 847ad13 로) → `paper_wallet`(표기·`tax_rate`), `analyst`(`normalize_verdict`·`analyze_logged`·`context`), `screener.scan_frames` + 시험 | 306 + 새 시험 통과, 골든 같음 |
| 3 | `h1.py`·`h1_check.py`·team 갈고리 + 시험(§6 대부분) | 시험 통과, 골든 같음 |
| 4 | `h1_report.py` + 시험 | T-F8 통과 |
| 5 | **재현** `h1_replay.py` | §5.5 통과, `replay_pass.json` |
| 6 | 독립 검토(결과 없이 코드만, R2 B5 와 같은 방식) → 고침 → 재현 다시 | 검토 지적 처리 |
| 7 | 맥 운영 시작: 이 문서 커밋 확인 → 첫 `--h1` 실행(S 결정) | 63거래일 뒤 보고서 |

---

## 10. 질문 (사람이 정할 것)

| # | 질문 | 설계 기본값 | 이유·대안 |
|---|---|---|---|
| **Q1** | **H1 두 장부에 서킷 브레이커를 켤까?** | 켬(team.py 그대로, `H1_BREAKER=True`) | F2 의 "team.py 그대로"를 따랐다. 그러나 R2 의 H1 결과는 서킷을 **끈** 조건이다(§7.0). 그리고 A1 지갑은 거의 100% 시장에 있어 시장 하락 한 번에 걸린다(R2 B2·P2). 재현 창에서 확인: 서킷을 켜면 국내 A1 은 **6번째 거래일에 세 트레이너가 모두 영구 정지**되고, 그 뒤로는 지수만 들고 있게 된다. 포워드에서 이렇게 되면 "A1 규칙이 3개월 동안 오류 없이 도는가"(운영 기준)를 확인할 매매가 거의 남지 않는다. 대안: 두 장부 모두 끔(= R2 H1 조건). 어느 쪽이든 두 장부는 같은 설정이고, 재현은 두 설정을 모두 맞춘다. D6(재개 규칙)은 범위 밖 |
| Q2 | 늦게 따라잡은 날(팀장 폴백)은 "빠진 날"인가? | 아님. 따로 세어 보고서에 적음. 5봉 넘게 밀리면 멈추고 물음 | 빠진 날로 세면 맥이 하루만 꺼져도 3개월을 다시 시작해야 한다 |
| Q3 | 장부 오류로 재시작하면 63거래일을 새로 셀까? | 새로 셈(새 S 부터) | 운영 기준 ②-1 이 "기간 동안 오류 0"이라서 |
| Q4 | H1 팀장 프롬프트에 날짜·시장·통화·종목명을 넣을까? | 넣음(H1 에서만, 할 일 10번) | 운영 team.py 의 프롬프트와 달라진다. 두 H1 장부는 같은 프롬프트라 A1−A0 비교에는 영향 없음 |
| Q5 | 판정 글자 정리(`" VETO"` → veto)를 H1 에서 할까? | 함(할 일 §3-2) | F2 "확신도 규칙은 team.py 그대로"와는 별개지만, 운영 team.py 는 대문자 VETO 를 매수 후보로 남긴다. H1 만 다르게 동작 |
| Q6 | 팀장 모델을 고정할까(`claude -p --model …`)? | 고정 안 함, 알 수 있으면 기록만 | 3개월 중 구독 기본 모델이 바뀌면 판정 기록 채점이 섞인다. 고정하려면 모델 ID 를 정해 주세요 |
| Q7 | 미국 종목군을 운영처럼 매일 S&P500 섞기로 할까, S 날 목록으로 고정할까? | 운영처럼 매일, 날마다 기록 | 고정하면 재현성이 좋아지지만 운영 장부와 달라진다 |
| Q8 | A1 첫날 전부 지수를 S 시가(R2 와 같음, 실행 시각엔 이미 지난 가격)로 할까, S 다음 봉 시가로 할까? | S 시가 | 고정 규칙이라 미리보기는 아니고, 재현과 지수 B&H 시작점이 R2 와 같아진다 |
| Q9 | 기간 중 국내 증권거래세가 바뀌면? | 바뀐 날을 보고서에 적고 재시작 여부를 그때 정함 | 지금 `markets` 는 0.20% 고정(R2 는 날짜별) |
| Q10 | "A0+이자"를 지금처럼 계산값(근사)으로 둘까, 이자를 현금에 넣는 세 번째 그림자 장부(R2 A0 와 똑같음)를 둘까? | 계산값(F8 "계산만") | 세 번째 장부는 정확하지만 파일·점검이 늘어난다 |
| Q11 | 실현손익을 평균원가법으로 낼까? | 평균원가법, 달러 기준, 참고값 | 신고 방식(선입선출 등)·환율은 반영 안 함(미확인) |
| Q12 | F5 열쇠에 시장을 붙여도 될까? | 붙임 `"us\|날짜\|트레이너\|종목"` | 두 시장이 파일 하나를 같이 쓴다. 코드가 겹칠 일은 없지만 명확하게 |
| Q13 | KS200 은 ETF 운용보수가 없어 A1 이 연 0.15% 정도 유리하다(069500 기준, 미확인) | 그대로(R2 A3 와 같음), 한계로 적음 | 보수를 빼려면 새 규칙이 필요 |

### 10.1 결정 (2026-11-04, 진행 담당이 사용자 위임으로 정함 — 바꾸려면 이 표를 고치고 커밋한 뒤 구현에 반영)

| # | 결정 | 이유 |
|---|---|---|
| **Q1** | **두 H1 장부 모두 서킷 브레이커 끔** (`H1_BREAKER=False`). 대신 매일 "서킷이 켜져 있었다면 걸렸을지"(지금 규칙: 누적 -10%·하루 -7%)를 계산해 판정 기록·월간 보고서에 그림자 사건으로만 남긴다 | R2 H1 은 서킷을 끈 조건에서 채택 후보가 됐다. 켜면 A1 은 시장 하락 한 번에 세 트레이너가 멈춰(재현 창 국내 6번째 거래일) 운영 기준을 확인할 매매가 남지 않는다. 시험 장부는 가짜 돈이라 끄는 위험이 없다. 재현은 끔·켬 두 설정을 모두 맞춘다(설계 §5 그대로) |
| Q2 | 설계 기본값대로: 늦게 따라잡은 날은 "빠진 날"이 아니고 따로 세어 보고서에 적는다. 5봉 넘게 밀리면 멈추고 사람에게 묻는다 | 하루 꺼짐으로 3개월을 버리지 않기 위해 |
| Q3 | 설계 기본값대로: 장부 오류로 재시작하면 63거래일을 새 S 부터 다시 센다 | 운영 기준 ①이 "기간 동안 오류 0" |
| Q4 | 설계 기본값대로: H1 에서만 팀장 프롬프트에 날짜·시장·통화·종목명을 넣는다 | 두 H1 장부가 같은 프롬프트라 A1−A0 비교에 영향 없음. 운영 team.py 는 안 바꿈 |
| Q5 | 설계 기본값대로: H1 에서 판정 글자를 정리한다(원래 값도 기록) | 버그 수정. 운영 쪽 수정은 개선 후보 목록으로 따로 |
| Q6 | 설계 기본값대로: 모델은 고정하지 않고, 알 수 있으면 기록한다. 기간 중 바뀌면 보고서에 적는다 | 구독 기본 모델을 3개월 고정할 수 있다는 보장이 없음 |
| **Q7** | **미국 종목군을 S 날 목록으로 고정**(그날 스크리너가 쓴 종목 목록과 순서를 `state/h1/us/universe.json` 에 저장하고 기간 내내 사용) | 포워드 결과를 나중에 똑같이 다시 만들 수 있어야 한다(개선 후보 11번). 두 장부 비교에는 어느 쪽이든 공정하지만, 재현성이 시험의 목적이다 |
| **Q8** | **A1 첫날 전부 지수는 S 다음 봉 시가**에 한다. A0 도 같은 날부터 매매 시작. 재현 모드(`h1_replay.py`)에서만 R2 와 맞추려고 S 시가 옵션을 쓴다 | 포워드에서는 실행 시각에 이미 지난 가격으로 살 수 없다. 장부는 실제로 가능했던 가격만 써야 한다 |
| Q9 | 설계 기본값대로(바뀐 날을 보고서에 적고 그때 정함). 단 국내 매도세는 R2 의 날짜별 표(STAGE0 §1.2)를 쓰는 함수로 두어, 세율이 바뀌면 표만 고치게 한다 | 2026 세율 0.20% 와 같고, 나중 변경에 안전 |
| Q10 | 설계 기본값대로: "A0+이자"는 계산값만 | F8 그대로 |
| Q11 | 설계 기본값대로: 평균원가법, 달러 기준 참고값 | 실제 신고는 증권사 자료 기준 |
| Q12 | 설계 기본값대로: 열쇠에 시장을 붙인다 | 명확성 |
| Q13 | 설계 기본값대로: 그대로 두고 한계로 적는다 | R2 A3 와 같음 |
