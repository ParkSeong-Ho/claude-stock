# H1 구현 전체 독립 검토 (검토 4)

- 검토일: 2026-11-05 · 브랜치 `h1-forward` · 대상 커밋 **48537a7** (847ad13 이후 H1 구현 전체: `team.py` 갈고리, `paper_wallet.py`·`analyst.py`·`screener.py` 더한 것, `h1.py`, `h1_check.py`, `h1_report.py`, `tools/h1_test_guard.py`, `tests/`, `requirements-h1.txt`)
- 사양: `docs/h1-forward-design.md` 3판(§10.2b~§10.2f 포함). 덩어리별 검토(2a·2b1·2b2·2c·3)의 지적은 고쳐진 것으로 보고, **덩어리 사이 이음새와 전체 흐름**만 봤다. `docs/h1-guide/` 는 범위 밖.
- 검토자는 이 코드를 쓰지 않았고 작성자 설명도 받지 않았다. 저장소에서 바꾼 것은 이 파일 하나다(확인용 장부·스크립트는 모두 scratch).
- 진짜 claude·인터넷은 쓰지 않았다(팀장은 `leader_mode="replay"` 또는 시험의 가짜 팀장, 시세는 가짜 `DataSource`, PATH 맨 앞에 기록용 가짜 `claude` — 호출 0번).

**직접 돌려 본 것**

| 무엇 | 결과 |
|---|---|
| `pytest -q` | **804 passed** (93.9초), 가짜 claude 호출 0 |
| `tools/h1_test_guard.py --quick` | 3번(UTC·Seoul·NewYork, 기본·역순·섞음) 모두 804 passed·결과 같음, 인터넷 0·claude 0, `state/`·`results/`·`git status`(무시 파일 포함) 그대로 |
| **실행기 전체 R2 대조**(이번 검토의 중심) | R2 data 로 운영과 같은 단계(원본 → 그날 b 이하로 자름 → `h1.fetched_from_raw`/`main.confirmed_bars`, 대기 자산은 `confirmed_bars(bench_cutoff)` → 정지 날짜)를 거치는 가짜 `DataSource`, 운영 시각 `now`(국내 b 23:05 KST, 미국 b 다음 평일 07:10 KST), 종목군은 R2 와 같게 강제. `h1.start` → 매일 `h1.run`(매일 저장·엄격 읽기·HEAD·백업·달력·D 점검·check_day 를 그대로 거침). 기준값은 R2 브랜치를 scratch 에 풀어 `python -I` 하네스 안에서만 만든 `OperatingStartSim`(설계 §5.1-3), `interest=False`, `cb="none"`·`"current"` |
| 대조한 창 | W1 미국·국내 2026-06-01~11-03(끝까지, 109·105봉), **W2 국내 2018-03-02~12-28(204봉, 정지 보유 포함)**, 그리고 따라잡기 길(W2 를 5봉씩·W1 미국을 4봉씩 한 실행에 처리) |
| 멱등(M9) | W2 204봉 모두 같은 시각에 두 번 실행 → 두 번째 실행 뒤 장부 6개·meta·HEAD·backup·판정 기록 sha256 그대로(203/203), 종료 코드 모두 0 |
| 지수 B&H(M6) | `h1_report.index_bh_from_states` 와 R2 `index_buy_hold_fractional(i0+1)`: 단위 비트 같음, 매일 값 상대 차 0.0(마지막 날 제외, 설계대로) |
| 사전 등록 판정 장면(scratch) | 창 중간 코드 변경, 같은 코드의 일시적 L, 잘못 친 restart·delist, 사전 등록 숫자를 바꾼 뒤 재시작 — 아래 F-1~F-5 |
| CLI 를 다른 작업 폴더에서 | `cd / && python <사본>/h1.py status --market us` → 정상, 일지는 사본의 `state/h1` 에 씀(작업 폴더 무관) |

---

## 요약

**실행기 전체가 R2 와 같은 숫자를 낸다.** 엔진만이 아니라 `start` → 매일 `run`(저장·엄격 읽기·HEAD·백업·달력·D 점검을 다 거친 것)도 W1 미·국, W2 국내 2018 의 6조합에서 체결·보류·주문·매일 값·그림자 서킷 첫 발동일이 R2 기준값과 같다. 받아들이는 차이(K1: 마지막 봉 판단 제외)만 빼고 차이는 0 이다. 따라잡기(한 실행에 여러 봉)와 같은 날 두 번 실행도 같다.

| 창 | 장부 | 체결 H1/R2 (짝 못 맞춘 것) | 체결가·주식 수 | 지수 수량 상대 차 | 체결 현금 절대 차 | 보류 | 주문(K1 제외) | 매일 값 상대 차 / 현금 절대 차 | 그림자 서킷 첫 발동일 | over_slots |
|---|---|---|---|---|---|---|---|---|---|---|
| W1 미국 | A0 | 170/170 (0) | 정확히 같음 | – | 3.6e-12 | 140/140 | 310/310 | 2.6e-16 / 0.0 | 같음(마라토너 10-16, 스프린터 08-27) | 89/89 |
| W1 미국 | A1 | 301/301 (0) | 정확히 같음 | 0.0 | 1.8e-12 | 130/130 | 296/296 | 2.6e-16 / 0.0 | 같음(스프린터 08-31) | 84/84 |
| W1 국내 | A0 | 241/241 (0) | 정확히 같음 | – | 3.7e-9 | 209/209 | 450/450 | 0.0 / 0.0 | 같음(마 06-08, 스 08-19, 파 10-13) | 281/281 |
| W1 국내 | A1 | 410/410 (0) | 정확히 같음 | 0.0 | 3.7e-9 | 216/216 | 453/453 | 4.3e-16 / 0.0 | 같음(셋 다 06-08) | 281/281 |
| W2 국내 2018 | A0 | 317/317 (0) | 정확히 같음 | – | 3.7e-9 | 306/306 | 623/623 | 0.0 / 0.0 | 같음(마 06-18, 스 12-26, 파 10-23) | 134/134 |
| W2 국내 2018 | A1 | 557/557 (0) | 정확히 같음 | 0.0 | 1.9e-9 | 305/305 | 622/622 | 3.6e-16 / 0.0 | 같음(마 06-18, 스·파 10-11) | 133/133 |
| W2 5봉씩 따라잡기 / W1 미국 4봉씩 | 둘 다 | 위와 같음(차이 0) | | | | | | | | |

- 허용 오차(설계 §5.4): 체결 현금 ≤ 1e-6, 매일 값 ≤ 1e-9, 현금 ≤ 1e-6 — 모두 안. 모든 실행 종료 코드 0, 하루 기록 모드는 모두 `replay`/늦지 않음.
- W2 에서 정지가 실제로 지나갔다: 하루 기록 `halted` 칸에 오른 (장부, 날, 종목) 144개(005930 18·035420 18·207940 108), 그중 보유 중 정지 42개(005930 2018-04-30~05-03, 207940 2018-11-15~12-10 포함). D6 거짓 경보 없음.
- 보고서 `--final` 을 W1 국내 결과에 돌리면 ②-1·②-2 통과, ②-3 은 재현 통과 기록이 없어서 실패(관문을 끈 대조라 정상). 저장 자료로 다시 점검한 L 0.

**발견: 치명 0 · 중요 4 · 경미 6.** 숫자를 내는 길에는 문제를 찾지 못했다. 문제는 **판정이 사전 등록의 "바꾸지 않는다"를 기계적으로 지키지 않는 곳**(F-1·F-2: 코드·사전 등록 숫자를 바꾸고 재현만 다시 통과하면 `--final` 이 "통과")과 **사람이 치는 명령의 확인 부족**(F-3 delist, F-4 restart)이다. 그 밖은 맥 운영 일정·환경(F-6~F-8)과 구조(F-9).

---

## 발견

| ID | 심각도 | 파일:행 | 문제 | 근거(재현 방법·숫자) | 고칠 것 |
|---|---|---|---|---|---|
| F-1 | 중요 | `h1_report.py:1337-1339`(`_verdict` c3), `h1.py:1910-1931`(`check_gate`·`allowed_fingerprints`), `h1.py:3210-3220` | **판정 창 안의 코드·환경 변경(⑥ 코드 동결)을 판정이 보지 않는다.** ②-3 은 "하루 기록의 (code_hash, env) 가 replay_pass 에 있나"만 본다. 창 중간에 장부 계산을 바꾼 코드라도 재현 통과 줄만 더하면 관문도 `--final` 도 통과한다. ⑥-i 조건(새 코드의 재현 `ledger_fingerprints` == 직전 통과 값)과 ⑤-c(그 밖의 변경 → 재시작)를 어디서도 확인하지 않는다. 보고서는 지문이 바뀐 날짜만 나열한다. 덧붙여 (1) 재현은 팀장 끔·가짜 `DataSource` 라 `prompts/*.md`·`analyst.py`·`fetch`/`load_idle` 변경은 ⑥-i 의 객관 조건이 **늘 참**이 되고, (2) `--final` 보고서는 자기를 돌린 `h1_report.py` 의 code_hash 를 찍지 않는다(판정 코드를 고친 뒤 판정해도 흔적이 없음) | scratch `verdict_scenarios.py` P1: 코드 A(지문 "옛 계산")로 S~D30, 코드 B(재현 지문 "새 계산(다름)")로 D31~D62 → `result="pass"`, c1·c2·c3 모두 통과, `changes={}`(변경 기록 없음), 지문 목록에만 2026-03-17 code bbbb… 가 보임 | ① `_verdict` 에 "⑥ 코드 동결" 칸: 창(S~S+62)에서 쓰인 (code_hash, env) 가 바뀔 때마다 앞·뒤 통과 줄의 `ledger_fingerprints`(+`fingerprint_version`)가 비어 있지 않고 같으며, 통과 줄의 `files`(파일별 sha256)로 바뀐 파일을 보고, 재현이 보지 못하는 파일(`prompts/*.md`·`analyst.py`)이나 판정 코드(`h1_report.py`)가 바뀌었으면 ⑥-i 로 받지 않음(④ 의 `h1_check.py` 고침은 ④ 기록이 있을 때만) → 아니면 `fail_window`. ② 같은 확인을 `run` 관문에도(창 첫 지문과 다르면 종료 코드 3) 두면 더 일찍 멈춘다. ③ 보고서 머리에 보고서 실행 code_hash·env 와 "창의 마지막 지문과 같은가"를 찍는다. ④ ⑥-i 변경은 `changes.jsonl` 에 종류·바뀐 파일을 남기게(지금은 replay-pass 줄뿐) |
| F-2 | 중요 | `h1_report.py:826,870,897,906-907,1268`(`c.rule(...)`), `h1.py:3129`(`start` 가 `rule_constants` 를 새 meta 에), `h1.py:3458-3461`(`restart` 상한 = 코드 상수 `MAX_RESTARTS`, 관문·규칙 확인 없음), `h1.py:3871,3920`(status 는 코드 상수) | **사전 등록 숫자(재시작 상한 2·창 63·늦은 봉 10·5·마감)가 창마다 새로 정해진다.** `start` 가 그때 코드 상수로 `meta.rules` 를 쓰고 보고서는 **지금 창의** `meta.rules` 로 판정한다. 첫 창의 규칙·`design_doc_sha256`(meta 에 적기만 하고 아무도 비교 안 함)과 대조하지 않는다. `restart` 는 관문·`_check_rules` 없이 코드의 `MAX_RESTARTS` 를 쓴다. 그래서 상수를 고치고(재현은 장부가 안 바뀌니 통과) restart → start 하면 늘어난 상한·줄어든 창으로 "통과" | scratch `rules_anchor.py` P5: 재시작 2번 뒤 세 번째 restart 는 거절 8 → `MAX_RESTARTS=3`·`WINDOW_BARS=10` 으로 바꾸자 세 번째 restart 허용 → 새 start 의 meta.rules `{max_restarts: 3, window_bars: 10}` → 10봉 처리 뒤 `--final` **"pass"**(재시작 3번, 창 10봉) | 첫 `start` 때 `state/h1/preregistration.json`(시장별 `rules`·`design_doc_sha256`·`universe_sha256`, 한 번 쓰고 안 바꿈, 세율 표는 amend-rules 로 뒤에 줄만)을 쓰고 ① `start`·`restart` 가 지금 상수와 그것을 비교(다르면 거절 3) ② 보고서는 판정 숫자를 그 파일에서 읽고 지금 창 `meta.rules`·설계 문서 sha 가 다르면 `fail_h1`/경고 ③ `restart` 에도 관문·규칙 확인 |
| F-3 | 중요 | `h1.py:3705-3739`(`_corp_delist`) | **`corp-action --delist` 가 상장폐지 증거를 하나도 보지 않는다.** 분할은 "지금 D6 이 같은 비율의 분할 모양일 때만" 받는데, 상장폐지는 대기 자산이 아니고·이미 등록 안 됐고·날짜가 last_date 이하면 받는다. 멀쩡히 거래되는 보유 종목을 잘못 치면(종목 오타·다른 종목) 다음 봉 시가에 두 장부 전량을 marks 값으로 강제 정리하고, L 이 아니어서 창은 그대로 "통과"한다. 보유하지 않은 종목을 잘못 치면 그 종목은 창이 끝날 때까지 매일 매수 주문 → 다음 봉 `dropped(delist)` 로 사실상 거래 금지. 되돌리는 명령도 없다 | scratch `delist_typo.py` P4: 시세가 정상으로 받히는 보유 종목 AAA 에 `--delist --last-date D11` → 종료 코드 0, 2026-02-18 두 장부에 `purpose="delist"` 정리 체결(290주 @64.3151), `--final` **"pass"**(기업 행위 표에 delist 1 만 보임) | 등록 조건에 ① 그 종목이 어느 장부에 보유·대기 중 ② 지금 `fetch` 가 None 이거나 마지막 확정 봉 < 장부 last_date(=D2·D3 가 실제로 나는 중) ③ `--confirm <코드>` 처럼 다시 치게 하기. 다음 run 전이면 등록을 취소하는 길(`--revoke`)도 |
| F-4 | 중요 | `h1.py:3396-3496`(`restart`), `h1.py:4074-4076`(cli) | **`restart` 에 확인이 없다.** `--market` 을 잘못 치면(국내를 멈추려다 `us`) 그 자리에서 멀쩡한 창을 archive 로 옮기고 재시작 1번(최대 2번)을 쓴다. 되돌리는 명령이 없고, 손으로 폴더를 되돌려도 `restarts.jsonl` 의 `done` 줄 때문에 횟수는 그대로 1 이다. 재시작 사유(L·종료 코드 6·⑤-c)가 기록에 있는지도 보지 않는다 | scratch `verdict_scenarios.py` P3: 정상 창(D4 까지)에 `h1.restart("us", "실수")` → 바로 `archive/us-…` 로 옮김, `restart_info.used=1` | `--confirm-start <S>`(지금 창의 S 를 다시 치게) 또는 대화형 확인. 화면에 S·마지막 봉·L 오류 수·남은 재시작을 먼저 보여 주고, 사유 기록(L·6·⑤-c)이 없으면 `--force` 없이는 거절 |
| F-5 | 경미 | `h1.py:3253-3260`(`_false_positive_check` (가)) | **④ 거짓 양성 자동 판정이 코드가 안 바뀐 경우에도 성립한다.** (가)는 "옛 code_hash 의 통과 줄과 지금 code_hash 의 통과 줄의 `ledger_fingerprints` 가 같음"인데 둘이 같은 code_hash 면 같은 줄을 자기와 비교해 늘 참이다. 그래서 고친 코드 없이 다시 돌려 사라진 L(입력·시각에 따라 흔들린 L)도 자동으로 "점검 함수 잘못"이 되어 ②-1 에서 빠진다. 지금 코드의 L 은 대부분 결정적이라 실제로 날 길은 좁다 | scratch `verdict_scenarios.py` P2: 같은 코드에서 D11 에 한 번만 L7 이 나게 한 뒤 다시 실행 → `changes.jsonl` `false_positive`(`code_hash_old == code_hash_new`), `--final` "pass"(거짓 양성 1건 뺌) | (가)에 `h_old != ch`(또는 env 가 다름)를 더한다. 같은 지문이면 기록하지 않고 "같은 코드에서 사라진 L — 그대로 셈"으로 알림 |
| F-6 | 경미 | 설계 `docs/h1-forward-design.md:1170-1171,1200-1202`(§8.2·§8.3) | **금요일 봉의 기회가 주말 앞 2번뿐이다.** 국내 금요일 봉은 금 23:05·토 07:40 다음이 월 23:05(월 09:00 뒤 → 늦은 봉), 미국 금요일 봉은 토 07:10·08:40 다음이 화 07:10(월 22:30/23:30 KST 뒤 → 늦은 봉). 국내는 KS200 이 늦는 날(D7)이 잦아 토요일 아침에도 안 따라오면 늦은 봉이 된다. 또 §8.3 "깨어난 뒤 launchd 가 놓친 작업을 한 번 돌린다"는 **잠자기**에만 맞다 — `pmset … wakeorpoweron` 으로 **꺼져 있다가 켜진** 경우에는 놓친 달력 작업을 다시 돌리지 않는다(그리고 일요일은 깨우지 않음) | 코드 `next_open`(주말을 건너 다음 평일)과 설계 시각표를 대조 | 국내 보조에 월 07:40, 미국 보조에 일·월(예: 월 07:10) 추가. §8.3 에 "꺼짐은 놓친 작업을 안 돌림" 적기 |
| F-7 | 경미 | `h1.py:2016-2060`(`h1_lock`, 두 시장 공용 `state/h1/h1.lock`), `h1.py:100`(`LOCK_WAIT_S` 30분), `analyst.py:37`(150초) | 두 시장이 잠금 하나를 쓴다. 미국 07:10 실행이 팀장 호출(봉마다 최대 6번×150초, 따라잡기면 더)로 길어지면 국내 07:40 보조는 30분 기다린 뒤 종료 코드 5 → 그 국내 봉은 23:05 에 **늦은 봉**. 깨어난 직후(07:00) 놓친 국내 23:05·미국 07:10 이 한꺼번에 뜰 때도 같다. 맥에서 `time.monotonic` 은 잠자기 동안 멈춰 30분이 늘어날 수 있다 | 코드 읽기(잠금 범위 = 명령 전체, 팀장 호출 포함) | 국내 보조를 미국 앞(예: 06:50)으로 옮기거나 보조 실행만 대기 시간을 늘리기. 길게는 시장 폴더 잠금 + 공용 파일(판정 기록·일지)용 짧은 잠금으로 나누기 |
| F-8 | 경미 | `analyst.py:188-191`(`subprocess.run(["claude","-p",…])` 에 `cwd` 없음), 설계 §8.3 | `claude -p` 가 부르는 쪽의 작업 폴더에서 돈다. launchd `WorkingDirectory` 가 빠지면 `/`, 있으면 H1 worktree 이고, Claude Code 는 그 폴더·사용자 전역의 설정(CLAUDE.md·훅·권한·도구)을 읽는다. 전역 Stop 훅 같은 것이 있으면 출력이 JSON 이 아니거나 시간 초과로 폴백이 늘 수 있다(⑧ 에만 드러남). 실행 중 맥이 잠들지 않게 하는 장치도 없다 | 코드 읽기 | `analyze_logged` 에서 `cwd=` 를 빈 고정 폴더로(운영 `analyze()` 는 그대로), 또는 맥 확인 목록에서 launchd 와 같은 환경으로 `claude -p` 한 번 확인. plist 에 `/usr/bin/caffeinate -i` 로 감싸기 |
| F-9 | 경미 | `h1.py:1940-2011`(`fetched_from_raw`·`fetch`·`load_idle`·`live_source`), `main.py:135,185`(`confirmed_bars`·`load_prices`, 운영과 공유) | ⑥-i 자료 고침을 해야 할 곳이 4,100줄 `h1.py` 안에 엔진·실행기와 섞여 있고, 일부는 운영과 같이 쓰는 `main.py` 다. 고침 자체는 장부 내용 지문을 바꾸지 않게 할 수 있지만, 재현(가짜 `DataSource`)이 `fetch`·`load_idle` 을 지나지 않아 "재현 지문이 같다"는 조건이 그 고침을 **실제로 확인하지 못한다**(F-1 과 겹침). 동결 중 `h1.py` 한 줄 고침도 4,100줄 파일의 diff 로 검토해야 한다 | 코드 읽기, 설계 §5.3(재현 자료는 가짜 DataSource) | 받기 층(`fetch`·`load_idle`·`fetched_from_raw`·`live_source`)을 `h1_data.py` 로 떼어 CODE_FILES 에 넣고(지문 판단 단위가 작아짐), 녹화한 원본 응답으로 `fetch` 길을 지나는 재현·시험을 하나 더 |
| F-10 | 경미 | `h1.py:2258`(`_count_restarts`) | 쓰는 곳이 없는 함수(재시작 수는 `restart_info` 로 바뀜). 고칠 때 잘못 부를 수 있다 | grep: 정의 1곳뿐 | 지우기 |

---

## 이음새 점검 (같은 개념을 두 곳에서 계산하는 곳)

| 개념 | 계산하는 곳 | 결과 |
|---|---|---|
| 창 세기 | `h1._in_window`(status·요약·보고서·④ 후보) + 보고서만 `pre_runs` | 같다. ④ 후보(`_pending_l_records`)는 `pre_runs` 를 안 빼지만 그 줄은 실패한 start(S 봉)라 run 의 처리 봉에 없어 영향 없음 |
| 늦은 봉 | 하루 기록 `late`(봉 시작 시각) → 보고서·status 모두 `_late_dates` / `late_calls` 는 ⑧ 에만 / `runs.jsonl late_bars` 는 참고(저장 못 한 봉도 들어감) | 판정은 하루 기록 하나만 씀 — 일관 |
| 내용 지문 | `ledger_fingerprint` 하나(errors.jsonl·④·replay_pass) | 일관. 단 ④(가)의 같은 코드 경우는 F-5 |
| 판정 기록 열쇠 | `decision_key`(Leader·`_leader_effects`·L17·보고서 `window_decision_keys`) | 일관 |
| 상장폐지·분할 모양 | 장부 `corp_actions` 하나(엔진·D6 `_adjusted`·L7/L8/L15/L23·보고서 `realized`) | 일관. 등록 조건은 F-3 |
| 세율 표 | 엔진·점검 = 코드 `KR_SELL_TAX`, `meta.rules` 는 같음 확인·amend 용 | run 마다 같음을 강제(다르면 3) — 일관 |
| 판정 상수 | 보고서 = 지금 창 `meta.rules`, status·restart = 코드 상수 | run 이 도는 동안은 같지만 restart·start 를 거치면 바뀔 수 있음(F-2) |
| 시각 | 자료 확정(`now` 한 번) / 봉마다 모드(`source.now`) / LLM 직전 재확인 | 따라잡기에서도 R2 와 같음(위 표) |

## 사전 등록 판정 끝에서 끝까지

- 정상 길: 기존 시험(깨끗한 66봉 창·L·늦은 봉 10/11·한 번에 5/6·종료 코드 6·다른 지문·빠진 날·재시작 상한·마감)과 이번 장면에서 **사람이 규칙을 지키는 한** ①~③·⑤ 대로 판정한다.
- 잘못 "통과"가 나는 길(모두 사람이 바꾸거나 잘못 친 경우): 창 중간 코드 변경(F-1), 사전 등록 숫자를 바꾼 뒤 재시작(F-2), 잘못된 상장폐지 등록(F-3), 같은 코드에서 사라진 L(F-5). 일지(`runs.jsonl`·`errors.jsonl`)를 지우면 L 이 사라지는 것은 HEAD 로 보호되지 않지만(판정 기록만 보호) 의도적 조작이라 범위 밖으로 봤다.

---

## 맥 운영 전 확인 목록

1. **파이썬 고정**: env 지문에 파이썬 **패치 버전**까지 들어간다(`platform.python_version()`). brew 파이썬으로 venv 를 만들면 `brew upgrade` 한 번에 3.13.x 가 바뀌어 매 실행 종료 코드 3. `brew pin python@3.13` 또는 python.org/uv 고정 파이썬으로 venv(`requirements-h1.txt` 의 3.13.18).
2. **폴더 위치**: worktree 를 iCloud 동기화되는 `~/Desktop`·`~/Documents` 밖, 로컬 APFS 에(설계 예 `/Users/나/claude-stock-h1` 은 괜찮음). 원자적 이름 바꾸기·flock 이 동기화 폴더에서 깨질 수 있다.
3. **launchd 환경 그대로 `claude -p` 확인**: plist 의 PATH·`WorkingDirectory` 로 `env -i HOME=$HOME PATH=<plist PATH> sh -c 'cd <worktree> && claude -p "JSON 하나만"'` 이 JSON 을 내는지(키체인 로그인·npm 설치면 `node` 경로·전역 훅 영향, F-8). `launchctl kickstart` 로 한 번 돌려 `runs.jsonl` 의 `cli_version` 이 비어 있지 않은지.
4. **잠자기**: plist 명령을 `/usr/bin/caffeinate -i …` 로 감싸기. 노트북이면 덮개 닫힘·배터리에서 `pmset repeat wake` 가 깨우는지 실제로 확인. 꺼짐(poweron)은 놓친 작업을 다시 돌리지 않음(F-6).
5. **일정**: 국내 보조 월 07:40·미국 보조 일/월 추가(F-6), 국내 보조를 미국 07:10 과 겹치지 않게(F-7).
6. **리허설(권장)**: `state/h1` 위치가 코드 폴더에 고정이고 `start` 는 한 번 성공하면 다시 못 하므로, **다른 clone** 에서 1~2주 실데이터·진짜 claude 로 `start`/`run` 을 돌려 D6(미국 일봉 뒤늦은 수정, RETRO_TOL 1e-6)·D7(KS200 캐시)·팀장 호출 시간·잠금 대기 빈도를 잰 뒤 그 clone 을 지운다.
7. **재현 먼저**: `h1_replay.py`(단계 5)가 생기면 CODE_FILES 지문이 바뀐다 → 그 코드로 `replay_pass.json` 을 만든 뒤 태그를 찍고 start. 태그·설계 문서 sha256 을 적어 두고 start 뒤 `meta.design_doc_sha256` 과 비교(F-2 를 고치기 전까지는 사람이 확인).
8. **시험**: 맥 venv 에서 `pytest -q`(골든은 `requirements-h1.txt` 버전 기준), `tools/h1_test_guard.py --quick`(맥에는 `--netns` 없음).
9. **시간**: 시스템 시간대 Asia/Seoul·자동 시간(NTP) 켬. 늦은 봉 판단이 맥 시계에 달려 있다.
10. **자료 원본**: start 전에 KS200 캐시 갱신 상태(`docs/kr-fix-s0.md` §5), 미국 S&P500 목록 받기(`screener.universe(40)`)가 되는지. 국내 보유 종목의 유상증자·비정수 무상증자 같은 수정주가는 `--split`(정수 아님)·`--accept-correction`(분할 모양 거절) 둘 다 안 되어 ⑦-3 재시작밖에 없다는 것을 운영자가 알고 있을 것.
11. **운영 쪽 분리**: 운영 체크아웃의 launchd(team.py·order_runner)가 H1 worktree 를 가리키지 않는지, H1 worktree 에 order_runner 작업이 없는지.
12. `F_FULLFSYNC`: 맥에서 `_fsync_dir` 가 폴더에 F_FULLFSYNC 를 못 하면 조용히 넘어가도록 이미 되어 있음(OSError 삼킴) — 리허설에서 ENV(4)가 안 나는지만 확인.

---

## 그대로 둬도 되는 것

- **숫자**: 실행기 전체(저장·읽기·HEAD·백업·달력·D 점검 포함)가 R2 와 같고, 따라잡기·같은 날 두 번 실행·지수 B&H 도 같다(위 표). 금리 규칙은 기존 시험(T-F8b, R2 를 `python -I` 로 부름)이 통과.
- **진짜 주문과 분리**: `h1*.py` 가 `order_runner`·`broker` 를 import 하지 않고(`import h1, h1_report` 로 읽히는 저장소 모듈이 모두 CODE_FILES 안임을 확인), 비밀값·키 없음, 경로는 `h1_path` 가 H1 폴더 밖·운영 `state/` 자체를 거절.
- **`python h1.py` 두 번 읽기**: `__main__` 에서 `import h1` 한 모듈로 명령을 돌려 예외 클래스가 두 벌이 되지 않는다. 다른 작업 폴더에서 불러도 `state/h1` 은 코드 폴더 기준이다(직접 확인).
- **맥 파일 시스템**: 한글 파일 이름은 이름을 직접 열기만 하고 폴더 목록과 비교하지 않아 NFC/NFD·대소문자 무시와 부딪히지 않는다. 잠금(`fcntl.flock`)·`os.replace`·`F_FULLFSYNC`(없거나 실패하면 넘어감)는 맥에서 그대로 쓸 수 있다. `/tmp` 를 쓰지 않는다.
- **시간대·서머타임**: 모든 비교가 시간대 있는 시각이고, 07:10 KST 는 사계절 미국 16:15 ET 확정 뒤·09:30 ET 전, 국내 23:05·07:40 은 22:30 확정 뒤·09:00 전이다. `next_open` 은 휴장일을 안 따져 늦은 쪽으로 보수적.
- **연말연초**: KS200 연도 파일 누락은 D4(이미 처리한 날 사라짐)·D7(새해 봉 늦음)로 멈추고, 12-31·01-01 휴장은 달력이 그대로 따른다. 2027 세율 변경은 알려진 것이 없고, 생기면 `amend-rules` 길(시험 있음).
- **3개월 크기·속도**: W2 204봉×하루 두 번(408 실행)에서 장부 한 개 0.3~0.6MB, `runs.jsonl` 0.7MB, `calendar.jsonl` 0.65MB(실행마다 날짜 목록 전체라 제곱으로 늘지만 작음), 백업 10개 포함 폴더 전체 31MB. 실행 한 번 0.5→1.4초(오프라인, 5봉 따라잡기 최대 3.8초). 63~100봉 운영에 문제 없다.
- **멱등·커밋 순서·엄격 읽기·잠금**: 위 대조에서 매일 저장 → 다시 읽기를 거쳐도 비트까지 같고, 두 번째 실행은 파일을 바꾸지 않는다.
- **amend-rules·corp-action --split·--accept-correction** 의 잘못된 인자: 시장 코드 확인, 효력일·D6 증거·정수 확인, 세율 표 "앞줄 그대로 + 뒤에 줄" 확인으로 막힌다(F-3·F-4 의 delist·restart 만 빈 곳).

---

## 부록: 확인 스크립트 (scratch, 저장소에 넣지 않음)

| 파일 | 하는 일 |
|---|---|
| `r2_baseline.py` | R2 브랜치를 푼 폴더에서 `python -I` 로 `OperatingStartSim` 기준값(W1 미·국, W2 국내; A0·A1 × cb none·current, interest 끔) → JSON |
| `h1_exec_run.py` | R2 data 가짜 `DataSource` 로 `h1.start` → 매일 `h1.run`(운영 시각, 종목군 강제, `--twice` 같은 날 두 번, `--step=N` N봉씩 따라잡기) |
| `compare_exec.py` | 장부 6개(HEAD 로 엄격하게 읽음) vs 기준값: M1 체결·M2 보류·M3 주문(K1)·M4 매일 값·M5′ 그림자 서킷·over_slots |
| `compare_bh.py` | M6 지수 B&H |
| `verdict_scenarios.py` | P1 창 중간 코드 변경(F-1), P2 같은 코드의 일시적 L(F-5), P3 확인 없는 restart(F-4) |
| `delist_typo.py` | P4 멀쩡한 보유 종목 delist(F-3) |
| `rules_anchor.py` | P5 사전 등록 숫자 바꾼 뒤 재시작(F-2) |
