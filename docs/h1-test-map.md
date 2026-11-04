# H1 시험 지도 (단계 3 "시험 보강")

- 작성: 2026-11-04 · 브랜치 `h1-forward` · 대상: a161e1c(단계 2 끝, 시험 755개) + 단계 3 변경(시험 804개)
- **고침(검토 3 반영)**: 처음 판(9039f3b)은 "157/157 완전"이라 했으나 독립 검토(`docs/h1-review-3.md` T-1~T-14)가 그중 일부가
  규칙 하나를 지키는 시험이 없음을 돌연변이로 보였다(HEAD 복구의 백업 확인, L15 분할 경계, L11 하한·L4 신호일·L17 짝 판정,
  G9 의 세율 날짜, status 의 늦은 봉·팀장 수 경계 등). 아래 "완전" 기준을 새로 적고, 그 기준으로 다시 세고, 빈 곳은 시험으로 채웠다.
- 기준 설계: `docs/h1-forward-design.md` **3판** §2.2·§2.5·§3.9·§4·§6·§10.2c·§10.2d·§10.2e
- 이 문서가 하는 일: 설계가 "이렇게 시험한다"고 적은 것마다 **실제로 어느 시험이 그것을 보는지**(파일::함수)와
  **얼마나 덮는지**(완전·일부·없음)를 적는다. 단계 3 에서 "일부·없음"을 새 시험(`tests/test_h1_gaps.py`)으로 채웠다.
- 낱말: **음성 대조** = 일부러 틀린 장부·자료를 넣었을 때 그 오류 코드가 정말 나는지(점검이 눈을 뜨고 있는지).
  **거짓 양성 없음** = 정상 장면에서는 그 코드가 나지 않는지(멀쩡한 장부를 틀렸다고 하지 않는지).
  **돌연변이 점검** = 코드 한 곳을 일부러 틀리게 바꿔 놓고 전체 시험이 그것을 잡는지(시험이 정말 지키고 있는지).
- **"완전"의 기준**: ① 설계가 그 항목에 적은 시험 점마다 그것을 **직접 단언하는** 시험이 있고, ② 그 항목 안의 규칙(조건 하나·
  경계 하나)마다 **그 규칙만 틀리게 바꾸면 실패하는** 시험(음성 대조·경계값 시험)이 있다. ②는 돌연변이 표본(작성자 41개 +
  검토자 25개, 8절)으로 실제로 확인한 것과, 표본 밖은 시험을 읽어서 판단한 것이 섞여 있다 — 읽어서 판단한 것은 틀릴 수 있다.
  "일부" = 시험 점 하나라도, 또는 규칙 하나라도 그런 시험이 없음. "없음" = 그 항목을 보는 시험이 없음.
  설계 §10.2f(진행 담당, 717a417)는 "완전 = 돌연변이가 실제로 시험에 잡힐 때만"으로 더 엄하게 정했다. 이 지도에서 그 기준을 실제로
  확인한 것은 8절 표의 규칙들(작성자 41 + 검토자 25, 지금 모두 잡힘)이고, 나머지 "완전"은 그 기준으로 보면 "읽어서 완전"이다.
- 파일 이름은 `tests/` 를 뺀다. 예) `test_h1_engine::test_T_START_…` = `tests/test_h1_engine.py` 의 그 함수.
  `[…]` 는 매개변수 이름(그 경우만), `…` 는 이름 뒷부분 줄임(파일 안에서 하나뿐인 앞부분).

---

## 0. 빠진 것 목록 (요약)

**세어 보면** (위 "완전" 기준으로. 단계 3 전 → 처음 판(9039f3b)이 실제로 덮던 것 → 지금)

| 묶음 | 항목 수 | 단계 3 전 완전 / 일부 / 없음 | 처음 판(검토 3 이 확인) | 지금 |
|---|---:|---|---|---|
| §6 시험 ID | 55 | 53 / 2 / 0 | 53 / 2 / 0 (T-HEAD·T-DELIST 일부) | 55 / 0 / 0 |
| §4 점검 코드 L1~L24·D1~D7·W1~W5 | 36 | 23 / 13 / 0 | 32 / 4 / 0 (L4·L11·L15·L17 일부) | 36 / 0 / 0 |
| §2.2 판정 규칙 ①②-1②-2②-3③⑤⑥⑦⑧⑩ | 10 | 5 / 5 / 0 | 9 / 1 / 0 (⑦-4 세율 날짜) | 10 / 0 / 0 |
| §2.5 시작·커밋·재시작 | 12 | 10 / 2 / 0 | 11 / 1 / 0 (커밋 지점의 백업 확인) | 12 / 0 / 0 |
| §3.9 종료 코드 0·1·2·3·4·5·6·7·8·9·130 | 11 | 10 / 0 / 1 | 11 / 0 / 0 | 11 / 0 / 0 |
| §10.2c·10.2d·10.2e 결정 | 33 | 31 / 1 / 1 | 32 / 1 / 0 (status 의 늦은 봉·팀장 수·연장 L·D7 요약) | 33 / 0 / 0 |
| **합** | **157** | **132 / 23 / 2** | **148 / 9 / 0** | **157 / 0 / 0** |

(§10.2d "운영 전 확인"은 단계 7 몫이라 세지 않음. 처음 판의 "단계 3 전 138/17/2" 는 느슨한 기준으로 센 것이라 위처럼 고침.)

**빠졌던 것과 채운 시험** (번호는 `tests/test_h1_gaps.py` 머리말과 같음)

| # | 빠졌던 것 (단계 3 전) | 어디 | 채운 시험 |
|---|---|---|---|
| 1 | `h1.py status`·실행 끝 요약의 L 오류 수가 보고서와 다른 규칙(errors.jsonl 줄 수만 셈: 같은 실행 두 줄이면 2, errors.jsonl 쓰기 실패면 0, ④ 거짓 양성도 그대로 셈, 같은 시각 재시작 줄도 셈) — **코드도 고침**(7절) | §10.2e 마지막 결정 | `test_h1_gaps::test_S1_…`·`test_S2_…`(4)·`test_S3_…`(3)·`test_S4_…`(4) |
| 2 | ②-3: 하루 기록의 **env 만** 다른 봉(code_hash 같음)을 '다른 지문'으로 세는지 — 시험 없음(돌연변이 M27 살아남음) | §2.2 ②-3 | `test_G1_하루_기록의_env_만_달라도_다른_지문으로_셈` |
| 3 | 종료 코드 1(파이썬이 cli 에 닿기 전에 죽음) 시험 없음 | §3.9 | `test_G2_파이썬이_cli_전에_죽으면_종료_코드_1` |
| 4 | 재시작해도 판정 기록이 남고 새 창의 같은 열쇠를 다시 쓰는지(LLM 0번) | §2.2 ⑤·§3.6 | `test_G3_재시작해도_판정_기록은_그대로_같은_열쇠는_다시_씀` |
| 5 | 실행 수준에서 판정 기록 가운데 줄 손상 → L24·종료 코드 2(엔진 수준만 있었음) | §4 L24 | `test_G4_판정_기록_가운데_줄이_깨지면_L24_2_장부_그대로` |
| 6 | L5 "그날그날 보유+매수 대기 ≤ 5" 음성 대조 없음(M35) | §4 L5·§10.2c | `test_G5_L5_그날그날_보유와_매수_대기가_5를_넘으면` |
| 7 | L10 "A1 S+1 부터 종가 현금 < 1(쓸어 담기 누락)" 음성 대조 없음(M36) | §4 L10 | `test_G6_L10_A1_종가_현금이_1_이상이면_쓸어_담기_누락` |
| 8 | L19 "빈자리 부족 후보가 있으면 빈자리를 다 채웠어야" 음성 대조 없음(M37) | §4 L19 | `test_G7_L19_빈자리_부족_후보가_있는데_빈자리를_다_안_채움` |
| 9 | 시각 **정각** 경계: 봉 시작이 next_open 정각 → late(M31), 묻기 직전 next_open 정각 → 안 물음(M32), KS200 22:30:00 정각 D7(M33), start 가 next_open(S) 정각이면 거절(M34) | §2.3-2·§2.5·§4 D7 | `test_G8_…` 4개(매개변수 포함 8건) |
| 10 | T-DELIST 국내: 정리 비용의 국내 매도세(그 봉 날짜 세율) 손계산, 실행 수준 dropped·기록 | §6 T-DELIST·§2.2 ⑦-4 | `test_G9_국내_상장폐지_정리_비용은_그_봉_날짜_매도세` |
| 11 | W1~W5 의 "정상 장면에서 안 남"을 직접 본 시험 없음 | §4 W | `test_G10_정상_장면에서는_W_가_하나도_없음` |
| 12 | ⑩ 고정 값 전부가 설계 숫자와 같은지·start 가 meta.rules 에 적는지·어느 칸이 달라도 3 인지(일부 칸만 봤음) | §2.2 ⑩ | `test_G11_…` 2개(3건) |
| 13 | ① 시장별 판정: 다른 시장의 L·멈춤 줄이 섞이지 않는지 | §2.2 ① | `test_G12_다른_시장의_L_과_멈춤은_이_시장_숫자에_안_섞임` |
| 14 | ⑦ 고른 것·출처·시각을 corp_actions.jsonl·changes.jsonl 에 남기는지(정정 확정·상장폐지) | §2.2 ⑦ | `test_G13_…`, `test_G9_…` |

**검토 3 반영으로 더 채운 것** (`tests/test_h1_gaps.py` 끝 절, 15건)

| # | 빠졌던 것 | 어디 | 채운 시험 |
|---|---|---|---|
| 15 | 장부가 HEAD 와 다르고 백업이 **있지만** HEAD 와 안 맞으면 되살리지 말고 L24(검토 T-1, 돌연변이 H-HEADrestore 살아남음) | §2.5 커밋 지점·T-HEAD | `test_T1_백업이_있어도_HEAD_와_안_맞으면_되살리지_않고_L24` |
| 16 | 산 날 장 마감 뒤 분할(효력 다음 날, `applied_after == 매수일`) 경계 — L15 매수가·L3 분할 전 체결(T-2, K-L15split) | §4 L15·L3 | `test_T2_산_날_장_마감_뒤_분할_적용_경계는_L_없음` |
| 17 | 저장소 깨끗함 점검이 "state/ 가 없다가 생겼나"뿐(맥처럼 state/h1 이 이미 있으면 꺼짐, T-3) | 시험 지킴이·도구 | 모든 h1 시험 fixture 를 앞뒤 비교로(`tests/h1_repo_guard.py`), `test_T3_…`(3: 도우미, 맥 흉내 가짜 저장소에서 도구) |
| 18 | 연장 봉 없이 S+63 처리 중 난 L 이 보고서에 안 보임(T-5) — **코드도 고침** | §10.2e·①(연장) | `test_T5_S62_다음_봉에서_난_L_은_연장_봉이_없어도_보고서에_보임` |
| 19 | 종료 코드 7 로 끝난 실행의 끝 요약이 자기 D7 을 안 셈(T-6) — **코드도 고침** | §10.2e status 와 보고서 | `test_T6_D7_로_끝난_실행의_끝_요약도_status_와_같은_숫자` |
| 20 | status 의 늦은 봉·팀장 수가 S+62 에서 끊기는지(T-7, R-lateExt·R-leaderExt) | §10.2e | `test_T7_status_늦은_봉과_팀장_수는_S62_에서_끊김` |
| 21 | G9 의 두 날짜가 같은 세율 구간이라 "그 봉 날짜 세율"을 못 가름(T-8, H-delistTaxDate) | ⑦-4·T-DELIST | `test_G9_…` 를 2025-12-30(0.15%) → 2026-01-02(0.20%) 장면으로 바꿈 |
| 22 | L11 하한·L4 신호일·check_pair L17 판정 비교에 따로 음성 대조(T-9, K-L11lo·K-L4sig·K-L17verdict) | §4 L11·L4·L17 | `test_T9_규칙마다_음성_대조`(3) |
| 23 | 국내 23:05 D7 → 다음 날 07:40 보조 실행, 늦은 봉 + D7 한 실행, 재시작 뒤 옛 창의 late_no_llm 기록 재사용(T-14) | §2.3·§2.4·§3.6 | `test_T14a_…`·`test_T14b_…`·`test_T14c_…` |
| 24 | 재시작 수를 status·restart 상한·start 도 보고서 R-7(세 출처 중 큰 값)로 — **코드도 고침** | §10.2e R-7·⑤ | `test_재시작_수는_status_restart_보고서가_같은_규칙` |

- 새 시험 49건(`tests/test_h1_gaps.py`, 약 10초)과 도우미 `tests/h1_repo_guard.py`. 골든 파일과 306개 원래 시험은 그대로다.
  기존 h1 시험 파일 셋(`test_h1_runner.py`·`test_h1_report.py`·`test_h1_review2b2.py`)은 꼭 필요한 곳만 고쳤다:
  각 파일의 지킴이 fixture 를 "state/ 가 생겼나" → "state/·results/ 아래가 앞뒤로 같나"로(T-3), `test_h1_report.py` 의
  R1 시험 한 줄은 지운 `_window_counts` 대신 `window_counts` 를 쓰게(T-12).
- 찾은 진짜 버그: **없음**(장부 계산·점검·보고서 판정이 설계와 다르게 도는 곳은 못 찾음). 검토 3 이 찾은 것도 "시험이 지키지
  않는 곳"이었고 코드는 바르게 돌았다(P5·P6 바른 코드 확인). 고친 코드(7절)는 status·요약·보고서가 같은 수를 보이게 하는 것뿐.

---

## 1. 설계 §6 시험 ID ↔ 실제 시험

| ID | 덮는 시험 (파일::함수) | 정도 | 빠진 부분 / 메모 |
|---|---|---|---|
| T-F1a | `test_h1_runner::test_T_F1a_경로_모양과_밖_경로_거절` | 완전 | 심볼릭 링크로 밖으로 새는 길·운영 상태 폴더를 H1 폴더로 받기도 거절 |
| T-F1b | `test_h1_runner::test_T_F1b_운영_장부_격리` | 완전 | start·run·status·corp-action 을 다 지남, `team._load·_save·main.load_state_file` 금지 |
| T-F2 | `test_h1_engine::test_T_F2_새_장부_총액_몫`·`test_T_F2_확신도_hold_veto_MAX_POSITIONS`·`test_T_F2_빈자리_부족과_대기_매수도_센다` | 완전 | |
| T-START | `test_h1_engine::test_T_START_S_는_입금만_S1_은_첫_전부_지수_손계산`, `test_h1_engine::test_R2_식_대조_…`(2), `test_h1_report::test_T_START_지수_BH_는_S_날_총액_S1_시가에서_시작` | 완전 | |
| T-A1-2 | `test_h1_engine::test_T_A1_2_매도1_매수2_매도대금_먼저_모자란_만큼만_지수`·`test_T_A1_2_매도_대금이_남으면_쓸어_담기` | 완전 | |
| T-A1-3 | `test_h1_engine::test_T_A1_3_현금_지수로도_모자라면_지수를_팔지_않고_보류`·`test_T_A1_3_시나리오_마라토너_네번째_매수는_두_장부_모두_보류` | 완전 | |
| T-A1-4 | `test_h1_engine::test_T_A1_4_경계_여유_위아래`·`test_T_A1_4_지수_판_뒤_매수_실패는_L11`·`test_T_A1_4_지수_판_뒤_매수_실패면_run_bar_는_저장_금지_결과와_지문`, `test_h1_check::test_B6_경계_보류_need_약_avail_1빼기_1e9` | 완전 | 종료 코드 2 는 `test_h1_runner::test_L_오류는_errors_jsonl_에_지문과_함께_2` |
| T-A1-5 | `test_h1_engine::test_T_A1_5_쓸어담기_문턱`(0.99·1.00·0.9999999999)·`test_T_A1_5_줄임_1e12_실패면_1e9`·`test_T_A1_5_줄임_셋_다_실패면_L11` | 완전 | |
| T-A1-6 | `test_h1_engine::test_T_A1_6_국내_매도세_표_경계`·`test_T_A1_6_국내_주식_매도세_지수_매도세0_비용`·`test_T_A1_6_미국_지수_다리_비용`, `test_h1_modules::test_T_PW_…` | 완전 | |
| T-A1-7 | `test_h1_engine::test_T_A1_7_저장_읽기_float_hex_정수_주식`·`test_T_A1_7_엄격_읽기`, `test_h1_modules::test_T_A1_7_…`(4), 화면 6자리 `test_h1_runner::test_status_와_요약` | 완전 | |
| T-A1-8 | `test_h1_engine::test_T_A1_8_A0_는_지수_체결_보유_0` | 완전 | |
| T-SIG | `test_h1_engine::test_T_SIG_신호_t_체결_t1_시가` | 완전 | |
| T-F4 | `test_h1_runner::test_T_F4_대기_자산_경로`·`test_T_F4_국내_KS200_은_allow_index_문과_22시30분`·`test_T_F4_하루_기록의_지수_시가_종가는_그_시세` | 완전 | |
| T-F5a | `test_h1_engine::test_T_F5a_호출마다_다른_답이어도_두_장부_같은_판정` | 완전 | |
| T-F5b | `test_h1_engine::test_T_F5b_기록에_없는_후보만_한_번에_묻는다`·`test_T_F5b_봉마다_호출_수_같은_봉_다시는_0번`, `test_h1_runner::test_T_F7_같은_봉_두번째_run_은_아무것도_안_바뀜` | 완전 | |
| T-F5c | `test_h1_engine::test_T_F5c_폴백_상태는_규칙_그대로`(6)·`test_T_F5c_답에서_빠진_종목은_missing_in_reply`, `test_h1_modules::test_T_F5c_…`(6), `test_h1_review2b1::test_B5_모르는_판정_글자는_bad_verdict_폴백` | 완전 | |
| T-F5d | `test_h1_engine::test_T_F5d_글자_정리는_H1_에서만`, `test_h1_modules::test_T_F5d_…`(2) | 완전 | |
| T-JSONL | `test_h1_engine::test_T_JSONL_…`(5), `test_h1_runner::test_T_JSONL_…`(3) | 완전 | 실행 수준 가운데 줄 손상은 `test_h1_gaps::test_G4_…` 로 보탬 |
| T-LLMTIME | `test_h1_engine::test_T_LLMTIME_next_open`·`test_T_LLMTIME_장_시작_전에만_llm`(6)·`test_T_LLMTIME_묻기_직전마다_시각_재확인`, `test_h1_runner::test_T_LLMTIME_국내_08시59분은_llm_10시는_late` | 완전 | 정각 경계는 없었음 → `test_h1_gaps::test_G8_봉_시작이_next_open_정각이면_late`(4)·`test_G8_묻기_직전_시각이_next_open_정각이면_묻지_않음` |
| T-F6a | `test_h1_runner::test_T_F6a_주문_실행기_경로는_H1_밖` | 완전 | |
| T-F6b | `test_h1_runner::test_T_F6b_H1_장부만_있으면_주문_0건` | 완전 | |
| T-F6c | `test_h1_runner::test_T_F6c_소스_격리`, `test_h1_engine::test_h1_은_주문_모듈을_읽지_않는다` | 완전 | |
| T-ENTRY | `test_h1_engine::test_T_ENTRY_team_에_h1_진입점_없음`·`test_T_ENTRY_운영_경로에서_h1_을_읽지_않는다`, run 장부 없음 8 은 `test_h1_runner::test_T_NEWSTART_명시_시작_규칙` | 완전 | |
| T-GOLD | `test_h1_golden::test_골든과_바이트까지_같다`(us·kr)·`test_골든_파일_수가_README_와_같고_git_이_무시하지_않는다`·`test_장면이_가지를_지난다`(us·kr) | 완전 | 저장소 밖 사본(git 없음)에서는 git 부분만 건너뜀 |
| T-F7 | `test_h1_runner::test_T_F7_같은_봉_두번째_run_은_아무것도_안_바뀜`·`test_T_F7_봉마다_scan_frames_한_번_두_장부_같은_후보`, `test_h1_review2b1::test_B7_T_F7_…` | 완전 | |
| T-SCR | `test_h1_modules::test_T_SCR_…`(7) | 완전 | |
| T-FETCH | `test_h1_runner::test_T_FETCH_main_load_prices_와_같은_단계`(Volume·거래량) | 완전 | |
| T-SHADOW | `test_h1_engine::test_T_SHADOW_경계와_전날_하루_기록`(5)·`test_T_SHADOW_S_날은_prev_없음_첫발동_표시`·`test_T_SHADOW_폭락_장면_두_장부`, `test_h1_report::test_T_SHADOW_보고서_첫_발동일과_날_수` | 완전 | team `prev_value` 를 일부러 다른 값으로 넣고 봄 |
| T-F8a | `test_h1_report::test_T_F8a_…`(9) | 완전 | |
| T-F8b | `test_h1_report::test_T_F8b_…`(6, R2 브랜치를 `python -I` 로 부른 대조 포함) | 완전 | R2 브랜치가 없으면 그 하나만 건너뜀 |
| T-F8c | `test_h1_report::test_T_F8c_…`(4) | 완전 | |
| T-L | `test_h1_check::test_음성_대조_그_잘못을_넣으면_그_코드`(33)·`test_음성_대조_L16_달력`·`test_음성_대조_L18_판정_기록`·`test_음성_대조_L22_코드_환경_종목군`·`test_음성_대조_전부_덮음`·`test_L24_장부_모양이_깨지면` | 완전 | 코드마다 자세히는 2절. 같은 코드 안의 세부 규칙 세 곳(L5·L10·L19)은 음성 대조가 없었음 → G5~G7 |
| T-FP | `test_h1_engine::test_T_FP_장부_내용_지문` | 완전 | |
| T-D | `test_h1_runner::test_T_D_자료_문제는_4_그_봉_저장_안함_다음_실행_정상`(D1~D6)·`test_T_D_D7_기준_지수_늦음은_7_앞_봉까지_저장`·`test_T_D_D6_분할_의심_비율_알림`·`test_T_D_확인용_대형주를_못_받으면_W5` | 완전 | |
| T-HALT | `test_h1_engine::test_T_HALT_국내_3일_정지`, `test_h1_check::test_정상_장부_여러_날_L_0[halt]` | 완전 | |
| T-LATEDATA | `test_h1_runner::test_T_LATEDATA_…`(2), `test_h1_review2b1::test_B7_T_LATEDATA_첫_처리는_D3_다음_처리는_정상` | 완전 | |
| T-RETRO | `test_h1_runner::test_T_RETRO_…`(2)·`test_T_LATEDATA_T_RETRO_국내_Volume0_행은_정지로_진행_정지일_marks_는_D6_안남`, `test_h1_review2b2::test_C2_…`·`test_C16_…` | 완전 | |
| T-DELIST | `test_h1_runner::test_T_DELIST_…`(2), `test_h1_engine::test_T_DELIST_정리_a_prime`, `test_h1_check::test_B1_…`(5), `test_h1_review2b1::test_B4_…`(2), `test_h1_gaps::test_G9_…` | **일부 → 완전** | 국내 매도세가 붙는 정리 비용 손계산이 없었음(미국만). 처음 G9 는 두 날짜가 같은 세율 구간이라 "그 봉 날짜 세율"을 못 갈랐음(검토 T-8) → 2025-12-30 → 2026-01-02 장면 |
| T-CORR | `test_h1_runner::test_T_CORR_정정_확정`, `test_h1_review2b2::test_C10_정정_확정은_분할_모양을_거절` | 완전 | 일지 기록은 `test_G13_…` 로 보탬 |
| T-AMEND | `test_h1_runner::test_T_AMEND_세율_줄_추가`, `test_h1_review2b2::test_C7_amend_rules_커밋_전후에_꺼짐` | 완전 | |
| T-CAL | `test_h1_runner::test_T_CAL_…`(3), `test_h1_review2b2::test_C18_연도_경계_KRX_휴장일을_뺀_달력`·`test_C17_D5_종목군_정확히_절반이_거래한_날도_구멍` | 완전 | 22:30:00 정각은 `test_G8_KS200_확정_시각_22시30분_정각` |
| T-CUT | `test_h1_runner::test_T_CUT_국내_20시와_22시31분` | 완전 | |
| T-DST | `test_h1_runner::test_T_DST_미국_서머타임_앞뒤_07시10분`, `test_h1_engine::test_T_LLMTIME_next_open` | 완전 | |
| T-LATE | `test_h1_runner::test_T_LATE_2봉_밀림은_차례로_late_6봉은_6`, `test_h1_review2b2::test_C17_밀린_봉_5개는_처리_6개는_6` | 완전 | |
| T-LOOK | `test_h1_engine::test_T_LOOK_전체_시세_자른_시세_흔든_미래`·`test_T_LOOK_진짜_브레인도_자른_시세와_같음` | 완전 | |
| T-GATE | `test_h1_runner::test_T_GATE_지문_env_다르면_3_파일_0개`·`test_T_GATE_규칙_상수가_다르면_3`·`test_C5_통과_기록이_줄거나_바뀌면_L_이_아니라_3` | 완전 | |
| T-LOCK | `test_h1_runner::test_T_LOCK_30분_넘게_잠금이면_5_모든_명령`(start·run·restart·corp-action·amend-rules·status)·`test_T_LOCK_기다리는_동안_풀리면_진행`, `test_h1_report::test_cli_잠금_30분_넘으면_5`(report) | 완전 | |
| T-HEAD | `test_h1_runner::test_T_HEAD_…`(4), `test_h1_review2b2::test_C1_디스크_가득은_ENV_4_L_아님_다음_실행이_되살림`·`test_C17_커밋_도중_남은_tmp_는_다음_실행이_치움`, `test_h1_gaps::test_T1_백업이_있어도_HEAD_와_안_맞으면_되살리지_않고_L24` | **일부 → 완전** | "HEAD 와 백업이 모두 안 맞음 → L24" 를 백업이 **없는** 경우로만 봤음. 백업이 있지만 다른 경우(검토 T-1)를 T1 이 봄 |
| T-STRICT | `test_h1_runner::test_T_STRICT_깨진_장부는_2_새로_시작_안함`(5), `test_h1_review2b1::test_B9_…`(3) | 완전 | |
| T-NEWSTART | `test_h1_runner::test_T_NEWSTART_…`(3), `test_h1_review2b2::test_C6_…`(2)·`test_C8_…`(5) | 완전 | next_open(S) 정각은 `test_G8_start_는_next_open_S_정각부터_거절` |
| T-UNIV | `test_h1_runner::test_T_UNIV_…`(2) | 완전 | |
| T-ORDERS | `test_h1_engine::test_T_ORDERS_…`(2) | 완전 | |
| T-PW | `test_h1_modules::test_T_PW_…`(3) + 기존 `test_paper_wallet.py` 그대로 | 완전 | |
| T-AN | `test_h1_modules::test_T_AN_…`(6)·`test_claude_cli_version_…`(2), `test_h1_runner::test_claude_cli_version_은_실행마다_한_번_llm_일_때만` | 완전 | |
| T-RSI | `test_h1_modules::test_T_RSI_2024_06_01_부터_계산해도_2026_06_이후는_같다` | 완전 | |

---

## 2. 설계 §4 점검 코드 — 음성 대조 / 거짓 양성 없음

**모든 L 에 공통인 "거짓 양성 없음" 시험**(아래 표에서 "공통"):
`test_h1_check::test_정상_장부_여러_날_L_0`(미국 시나리오 A·폭락·상장폐지·국내 3일 정지) — 봉마다 check_day 까지 다시,
`test_h1_runner::test_E2E_여러_날_저장_파일만으로_다시_점검_L0`(미국·국내 15거래일 넘게: 정지·분할·상장폐지·늦은 봉·늦은 자료),
그리고 엔진 시험의 모든 `Runner.step`(봉마다 `res.ok` 단언), `test_h1_report::test_T_F8a_장부_다시_점검_결과와_못_보는_점검`.
(설계 §4 끝 "(b) 재현 W1·W2 창에서 거짓 양성 0" 은 실데이터 재현이라 단계 5 몫이다. 단계 2b-1 에서 진행 담당이 R2 실데이터 6조합으로
한 번 확인했다 — 인계 메모.)

음성 대조 표기: `C[x]` = `test_h1_check::test_음성_대조_그_잘못을_넣으면_그_코드[x]`.

| 코드 | 음성 대조 (그 코드가 나는 시험) | 거짓 양성 없음 (공통 + 그 코드에 맞춘 것) | 정도 |
|---|---|---|---|
| L1 | `C[L1-m_L1]` | 공통 | 완전 |
| L2 | `C[L2-m_L2]`·`C[L2-m_L2b]` | 공통 | 완전 |
| L3 | `C[L3-m_L3]`·`C[L3-m_L3b]`, `test_h1_check::test_check_day_오늘_체결가_시세와_다름_L3_행_없음_L6`·`test_check_day_정지_목록_다름_L6_지수_봉_다름_L3` | 공통, 분할 뒤 지난 체결을 새 시세와 견주지 않음 `test_h1_runner::test_T_RETRO_분할_의심_…`·`test_h1_review2b1::test_B2_분할_뒤_여러_봉_L_0` | 완전 |
| L4 | `C[L4-m_L4]`(정지 아닌 날 남은 주문)·`C[L4-m_L4b]`(국내 정지 표시 지움), `test_h1_check::test_B6_매수가_매도보다_먼저면_L4`, **`test_h1_gaps::test_T9_규칙마다_음성_대조[L4신호일]`** | 공통(정지로 기다린 주문 `[halt]`), `test_h1_runner::test_T_LATEDATA_보유_종목_행이_늦게_오면_D3_다음_실행_정상` | **일부 → 완전** (신호일 < 체결일 규칙, 검토 T-9) |
| L5 | `C[L5-m_L5]`(보유 종목 매수 대기), **`test_h1_gaps::test_G5_L5_그날그날_보유와_매수_대기가_5를_넘으면`** | 공통, `test_h1_engine::test_T_F2_빈자리_부족과_대기_매수도_센다` | **일부 → 완전** (그날그날 ≤ 5 규칙에 음성 대조가 없었음, M35) |
| L6 | `C[L6-m_L6]`, `test_h1_check::test_check_day_오늘_체결가_시세와_다름_L3_행_없음_L6`, `test_h1_review2b1::test_B3_엄격_cache_예외는_L6_과_그때까지의_지문` | 공통(`[halt]`), `test_h1_engine::test_T_HALT_국내_3일_정지` | 완전 |
| L7 | `C[L7-m_L7]`, `test_h1_engine::test_R14_가격표에_보유_종목이_빠지면_L7` | 공통 | 완전 |
| L8 | `C[L8-m_L8]`, `test_h1_check::test_check_day_지난_체결_고침_L8`, `test_h1_review2b1::test_B2_분할을_한_장부만_적용하면_L`·`test_B2_r_를_틀리게_적용하면_L`·`test_B2_분할_기록이_한_장부에만_있으면_L` | 공통, `test_B2_분할_뒤_여러_봉_L_0` | 완전 |
| L9 | `C[L9-m_L9]` | 공통(미국·국내 매도세·지수 다리) | 완전 |
| L10 | `C[L10-m_L10]`(S+1 첫 체결)·`C[L10-m_L10b]`(A0 지수 보유), **`test_h1_gaps::test_G6_L10_A1_종가_현금이_1_이상이면_쓸어_담기_누락`** | 공통(S 날 예외 포함), `test_h1_engine::test_T_START_…` | **일부 → 완전** (종가 현금 < 1 규칙에 음성 대조가 없었음, M36) |
| L11 | `C[L11-m_L11]`·`C[L11-m_L11b]`, `test_h1_engine::test_T_A1_4_지수_판_뒤_매수_실패는_L11`·`test_T_A1_5_줄임_셋_다_실패면_L11`, **`test_T9_…[L11하한]`** | 공통, `test_T_A1_4_경계_여유_위아래` | **일부 → 완전** (메운 금액 하한, 검토 T-9) |
| L12 | `C[L12-m_L12]`·`C[L12-m_L12b]`, `test_h1_check::test_B6_다시_센_가능_금액과_다른_기록은_L12` | 공통, `test_B6_경계_보류_need_약_avail_1빼기_1e9` | 완전 |
| L13 | `C[L13-m_L13]` | 공통 | 완전 |
| L14 | `C[L14-m_L14]`·`C[L14-m_L14b]`, `test_h1_check::test_check_day_전날_대기가_아니던_주문의_체결_L14` | 공통 | 완전 |
| L15 | `C[L15-m_L15]`·`C[L15-m_L15b]`(국내 정지일도 셈) | 공통(`[halt]`), `test_T_LATEDATA_…`, **`test_h1_gaps::test_T2_산_날_장_마감_뒤_분할_적용_경계는_L_없음`**(L3 의 같은 경계도) | **일부 → 완전** (산 날 마감 뒤 분할 경계, 검토 T-2) |
| L16 | `C[L16-m_L16]`, `test_h1_check::test_음성_대조_L16_달력`·`test_check_day_오늘_하루_기록_없음_L16`, `test_h1_report::test_final_운영_기준_어기면_창_실패[빠진날]` | 공통, `test_h1_review2b2::test_C18_연도_경계_KRX_휴장일을_뺀_달력` | 완전 |
| L17 | `C[L17-m_L17]`·`C[L17-m_L17b]`, `test_h1_check::test_B7_두_장부를_똑같이_틀린_판정은_장부_점검이_L17`, **`test_T9_…[L17짝판정]`** | 공통, `test_h1_engine::test_T_F5a_…` | **일부 → 완전** (짝 점검의 판정 비교, 검토 T-9) |
| L18 | `test_h1_check::test_음성_대조_L18_판정_기록`, `test_h1_engine::test_T_JSONL_지난_줄_수정은_L18`·`test_T_JSONL_중간_줄_깨짐_중복_열쇠`, `test_h1_runner::test_T_JSONL_지난_줄이_바뀌면_L18` | 공통, `test_T_JSONL_반쯤_쓴_마지막_줄은_잘라냄`(L18 아님) | 완전 |
| L19 | `C[L19-m_L19]`·`C[L19-m_L19b]`, **`test_h1_gaps::test_G7_L19_빈자리_부족_후보가_있는데_빈자리를_다_안_채움`** | 공통, `test_T_F2_확신도_hold_veto_MAX_POSITIONS` | **일부 → 완전** (빈자리 다 채움 규칙에 음성 대조가 없었음, M37) |
| L20 | `C[L20-m_L20]`·`C[L20-m_L20b]`, `test_h1_check::test_B7_first_만_틀린_그림자_서킷은_L20` | 공통(`[crash]`), `test_T_SHADOW_폭락_장면_두_장부` | 완전 |
| L21 | `C[L21-m_L21]` | 공통 | 완전 |
| L22 | `test_h1_check::test_음성_대조_L22_코드_환경_종목군`(code·env·종목군), `test_h1_runner::test_T_UNIV_미국_종목군은_첫_S_목록_순서로_고정` | 공통, `test_C5_…`(⑥-i 새 통과 기록이면 통과) | 완전 |
| L23 | `C[L23-m_L23]`·`C[L23-m_L23b]`, `test_h1_check::test_B1_…`(4), `test_h1_review2b1::test_B4_장부마다_등록이_다르면_L23`, `test_h1_runner::test_T_DELIST_시세를_못_받는_상태에서_등록_다음_run_진행`(가격 바꾼 정리) | 공통(`[delist]`), `test_B1_한쪽만_보유한_상장폐지는_정상`, `test_G9_…` | 완전 |
| L24 | `test_h1_check::test_L24_장부_모양이_깨지면`, `test_h1_runner::test_T_STRICT_…`(5)·`test_T_HEAD_HEAD_도_백업도_안_맞으면_L24`, `test_h1_review2b1::test_B9_항목_모양이_틀리면_L24`, `test_h1_review2b2::test_C17_장부_last_date_가_HEAD_와_다르면_L24`·`test_C3_장부를_읽기_전_L24_도_창_S_로_기록`, `test_h1_engine::test_T_A1_7_엄격_읽기`, **`test_h1_gaps::test_G4_…`**(판정 기록 가운데 줄) | `test_B9_정상_장부는_통과`, `test_T_HEAD_3개_바꾼_뒤_멈춤은_백업으로_되살려_같은_결과`(백업으로 되살리면 L24 아님) | 완전 (실행 수준 판정 기록 손상은 G4 로 보탬) |
| D1 | `test_h1_runner::test_T_D_…[D1]`, `test_T_NEWSTART_starting_에_쓰다_멈추면_…`(start 의 D1) | 모든 정상 run(종료 코드 0) | 완전 |
| D2 | `test_T_D_…[D2]`, `test_T_DELIST_…`(등록 전), `test_h1_review2b2::test_C4_…`(3, 종목군 절반 넘게 실패), `test_h1_review2b1::test_B4_last_date_가_t_이상이면_시세가_필요하다` | `test_C4_비율_경계와_상장폐지_종목`(절반 이하는 W4), `test_T_DELIST_…`(등록 뒤 D2 없음) | 완전 |
| D3 | `test_T_D_…[D3]`, `test_T_LATEDATA_…`, `test_h1_review2b1::test_B7_대기_주문_종목의_시가가_없으면_D3`, `test_h1_review2b2::test_C13_…`(종가·지수 시가·종가 이상) | `test_T_LATEDATA_T_RETRO_국내_Volume0_행은_정지로_진행_…`(정지는 D3 아님), `test_T_HALT_…` | 완전 |
| D4 | `test_T_D_…[D4]`, `test_T_CAL_2026_에서_2027_첫_봉_연도_파일_늦음`(2026.csv 빠짐), `test_T_CAL_처리한_구간에_날짜가_끼어들면_D4` | `test_C18_…`(실제 휴장일), 모든 정상 run | 완전 |
| D5 | `test_T_D_…[D5]`, `test_C17_D5_종목군_정확히_절반이_거래한_날도_구멍` | `test_C18_…`(아무도 거래 안 한 휴장일은 구멍 아님) | 완전 |
| D6 | `test_T_D_…[D6]`·`test_T_D_D6_분할_의심_비율_알림`, `test_T_RETRO_…`, `test_T_CORR_…`, `test_C17_대기_자산_지난_시가가_바뀌면_D6`·`test_C17_오래_보유한_종목의_매수일_시가만_바뀌어도_D6` | `test_T_LATEDATA_T_RETRO_…`(정지일 marks), `test_C2_밀린_봉이_있을_때_분할_적용_뒤_처리한_봉은_나누지_않음`, `test_T_CORR_…`(확정 뒤 D6 없음) | 완전 |
| D7 | `test_T_D_D7_…`, `test_T_CAL_국내_22시29분_22시31분`(22:31)·`test_T_CAL_2026_에서_2027_…`, `test_C17_미국_16시15분_ET_경계`(16:16)·`test_C17_start_D7_거절`, **`test_h1_gaps::test_G8_KS200_확정_시각_22시30분_정각`** | `test_T_CAL_…`(22:29), `test_C17_…`(16:14), `test_T_CUT_…`(20:00), `test_T_D_확인용_대형주를_못_받으면_W5` | **일부 → 완전** (정각 22:30:00 이 D7 인지 없었음, M33) |
| W1 | `test_h1_engine::test_T_LLMTIME_장_시작_전에만_llm[late…]`(W1 단언), `test_T_LATE_…`(late_bars) | **`test_h1_gaps::test_G10_정상_장면에서는_W_가_하나도_없음`** | 일부 → 완전 |
| W2 | `test_h1_engine::test_T_HALT_국내_3일_정지`(W2 단언) | `test_G10_…` | 일부 → 완전 |
| W3 | `test_h1_engine::test_T_F5c_폴백_상태는_규칙_그대로`(W3 단언) | `test_G10_…` | 일부 → 완전 |
| W4 | `test_T_DELIST_시세를_못_받는_…`(정리 뒤 W4), `test_C4_비율_경계와_상장폐지_종목` | `test_G10_…` | 일부 → 완전 |
| W5 | `test_T_D_확인용_대형주를_못_받으면_W5`, `test_C4_확인용_대형주를_못_받으면_D7_판단_못_함을_기록` | `test_G10_…`(d7_checked true) | 일부 → 완전 |

---

## 3. §2.2 사전 등록 판정 규칙

| 규칙 | 덮는 시험 | 정도 |
|---|---|---|
| ① 판정 창 S~S+62, S+62 뒤 한 번 판정, 연장은 판정에 안 씀, **시장별** | `test_h1_report::test_final_창이_덜_찼으면_판정하지_않음`·`test_final_깨끗한_창은_통과`·`test_final_연장_구간_일지는_판정에_안_씀`·`test_final_S62_저장_뒤_다음_봉에서_멈춘_실행은_연장_몫`·`test_R8_연장_구간의_늦은_봉은_판정_창에_안_셈`, **`test_h1_gaps::test_G12_…`**·`test_S4_status_창이_다_차면_S62_까지_그_뒤는_연장으로_따로` | 일부 → 완전 (시장별 독립이 없었음) |
| ②-1 L 오류 0 | `test_final_운영_기준_어기면_창_실패[L오류]`, `test_R2_…`(3: errors.jsonl ∪ 종료 코드 2), `test_R2_종료_코드_2_만_남은_창은_최종_판정에서_실패`, `test_R4_…`(거짓 양성), `test_final_…[빠진날]`(다시 점검한 L), **`test_S2_…`·`test_S3_…`(status 도 같음)** | 완전 |
| ②-2 빠진 날 0·늦은 봉 ≤ 10·한 번에 ≤ 5 | `test_final_운영_기준_어기면_창_실패[늦은봉11·한번에6봉·밀린봉_종료6·빠진날]`·`test_final_경계값은_통과[늦은봉10·한번에5봉]`·`test_R8_한_장부만_하루_기록이_빠지면_빠진_날_실패`, `test_C17_밀린_봉_5개는_처리_6개는_6` | 완전 |
| ②-3 재현 통과 코드·환경만 | `test_final_…[다른지문]`(runs.jsonl), `test_final_깨끗한_창은_통과`(통과 기록 없으면 실패), **`test_G1_하루_기록의_env_만_달라도_다른_지문으로_셈`** | 일부 → 완전 (하루 기록 env 만 다른 경우, M27) |
| ③ 수익률은 기록만 | `test_h1_report::test_고정_문장과_절_순서`, `test_final_깨끗한_창은_통과`("③ 수익률은 기록만 \| 판정에 안 씀") | 완전 |
| ⑤ 재시작(사유 셋·최대 2번·마감·판정 기록·종목군 유지) | `test_h1_runner::test_T_NEWSTART_명시_시작_규칙`·`test_T_NEWSTART_재시작_상한`·`test_T_UNIV_…`, `test_h1_review2b2::test_C6_…`(2), `test_h1_report::test_final_재시작_상한을_넘으면_H1_포워드_실패`·`test_final_마감을_넘으면_…`·`test_final_마감까지_끝날_수_없으면_…`·`test_final_재시작_상한_밖의_창은_통과해도_실패`·`test_R7_…`, **`test_G3_재시작해도_판정_기록은_그대로_같은_열쇠는_다시_씀`** | 일부 → 완전 (판정 기록 유지·재사용이 없었음) |
| ⑥ 코드 동결(i 통과 기록 추가·ii 세율 줄 추가, 그 밖은 3) | `test_C5_통과_기록이_줄거나_바뀌면_L_이_아니라_3`(새 코드 통과 기록 더함), `test_T_AMEND_세율_줄_추가`, `test_T_GATE_…`(2), `test_C11_corp_action_도_관문과_규칙_확인` | 완전 |
| ⑦ 분할·합병·상장폐지(1 기다림·2 분할 공식·3 그 밖 재시작·4 상장폐지·5 정정 확정, 기록 두 곳) | `test_T_D_…[D6]`(1: 원래 값으로 돌아오면 정상), `test_T_RETRO_…`·`test_C2_…`·`test_C16_…`(2), `test_T_RETRO_정수가_아니면_split_거절`(3), `test_T_DELIST_…`(4), `test_T_CORR_…`·`test_C10_…`(5), **`test_G9_…`·`test_G13_…`(기록)** | 일부 → 완전 (상장폐지·정정 확정의 corp_actions.jsonl·changes.jsonl 기록, 정리 세율은 정리 봉 날짜 — G9 를 세율 구간이 다른 두 날짜로) |
| ⑧ 팀장 폴백 20% 표시 | `test_T_F8a_팀장_수와_폴백_20퍼센트`·`test_T_F8a_폴백_20퍼센트_경계` | 완전 |
| ⑩ 고정 값(meta.rules, 다르면 3) | `test_h1_engine::test_상수와_규칙값`(일부 칸), `test_T_GATE_규칙_상수가_다르면_3`(한 칸), **`test_G11_규칙_상수는_설계_숫자와_같다`(us·kr)·`test_G11_start_는_meta_rules_에_그대로_적고_어느_칸이_달라도_3`** | 일부 → 완전 |

(④ 점검 등급은 2절 표, ⑨ 는 ③ 과 같은 시험.)

---

## 4. §2.5 시작 · 늦은 봉 · 멱등 · 커밋 지점 · 재시작

| 결정 | 덮는 시험 | 정도 |
|---|---|---|
| 새 시작은 명시 명령으로만, 폴더 있으면 거절, 성공한 start 흔적 + 재시작 기록 없음 → 8, run 장부 없음 8 | `test_T_NEWSTART_명시_시작_규칙` | 완전 |
| `<m>.starting/` 에 다 쓴 뒤 이름 바꿈, 남은 폴더는 다음 start 가 지우고 다시(재시작 아님) | `test_T_NEWSTART_starting_에_쓰다_멈추면_다음_start_가_지우고_다시` | 완전 |
| S 는 입금만, S+1 시가 A1 a(전부 지수) → b → c → d → e | `test_T_START_…`, `test_R2_식_대조_…`(2), 돌연변이 M01·M02 | 완전 |
| L10 의 S 날 예외 | `test_T_START_…`, 공통 L 0 | 완전 |
| 지수 B&H 는 S+1 시가에서 | `test_h1_report::test_T_START_지수_BH_는_S_날_총액_S1_시가에서_시작` | 완전 |
| 첫 판단은 S 종가, start 시각 ≥ next_open(S) 이면 거절(8) | `test_C8_S_봉이_늦은_봉이_되는_start_는_거절`(5), **`test_G8_start_는_next_open_S_정각부터_거절`** | 일부 → 완전 (정각, M34) |
| 늦은 봉 정의(next_open 이후 처리 → 폴백·late) | `test_T_LATE_…`, `test_T_LLMTIME_…`, `test_G8_봉_시작이_next_open_정각이면_late` | 완전 |
| 한 번에 5봉 넘으면 6, 창 전체 10봉 넘으면 창 실패 | `test_C17_밀린_봉_5개는_처리_6개는_6`, `test_final_…[늦은봉11]`·`test_final_경계값은_통과` | 완전 |
| 멱등(장부 6개·meta·HEAD·backup·판정 기록 그대로, 일지는 줄 추가) | `test_T_F7_같은_봉_두번째_run_은_아무것도_안_바뀜` | 완전 |
| 커밋 순서(판정 기록 → 백업 → 장부 6개 → HEAD), 읽을 때 백업이 **HEAD 와 맞을 때만** 되살림, 그 밖은 L24 | `test_T_HEAD_…`(4), `test_T_JSONL_HEAD_전에_꺼지면_남은_판정_줄을_재사용`, `test_C1_디스크_가득은_…`, `test_C17_커밋_도중_남은_tmp_는_다음_실행이_치움`, **`test_T1_…`**, 돌연변이 M21·M22·H-backupAfter·H-HEADrestore | **일부 → 완전** (백업 확인, 검토 T-1) |
| 백업 열쇠 = HEAD run_id(corp-action·amend-rules 도 새 run_id), 최근 10개 | `test_T_HEAD_corp_action_뒤_같은_last_date_에서_멈춤`·`test_T_HEAD_백업은_최근_10개`, `test_T_AMEND_…`(run_id) | 완전 |
| 재시작(잠금 아래 archive 로 옮김·restarts.jsonl·그 밖 파일 그대로 → start) | `test_T_NEWSTART_명시_시작_규칙`, `test_C6_…`(2), `test_G3_…` | 완전 |

---

## 5. §3.9 종료 코드

| 코드 | 뜻 | 덮는 시험 | 정도 |
|---|---|---|---|
| 0 | 정상(새 봉·이미 처리됨) | 거의 모든 실행 시험, `test_T_F7_…`(이미 처리됨) | 완전 |
| 1 | 파이썬이 cli 전에 죽음 | **`test_h1_gaps::test_G2_파이썬이_cli_전에_죽으면_종료_코드_1`**(진짜 `python h1.py` + 깨진 pandas) | **없음 → 완전** |
| 2 | 장부 논리 오류·코드 버그 | `test_L_오류는_errors_jsonl_에_지문과_함께_2`, `test_끝까지_못_간_L_예외도_…`, `test_예상_밖_예외는_2_지문_없음`, `test_T_STRICT_…`, `test_T_HEAD_HEAD_도_백업도_안_맞으면_L24`, `test_C1_예외_분류[RuntimeError]`, `test_G4_…` | 완전 |
| 3 | 관문·규칙 다름 | `test_T_GATE_…`(2), `test_C5_…`, `test_C11_…`, `test_T_AMEND_…`, `test_G11_…` | 완전 |
| 4 | 자료 문제·PRE·ENV | `test_T_D_…`(6), `test_사전_조건_어긋남은_4`, `test_C1_디스크_가득은_ENV_4_…`·`test_C1_예외_분류[Memory·Permission]`, `test_C4_…` | 완전 |
| 5 | 잠금 30분 초과 | `test_T_LOCK_30분_넘게_잠금이면_5_모든_명령`, `test_h1_report::test_cli_잠금_30분_넘으면_5` | 완전 |
| 6 | 밀린 봉 5개 초과 | `test_T_LATE_…`, `test_C17_밀린_봉_5개는_처리_6개는_6` | 완전 |
| 7 | 기준 지수 늦음(앞 봉까지 저장) | `test_T_D_D7_…`, `test_T_CAL_…`(2), `test_G8_KS200_…` | 완전 |
| 8 | 장부 없음·start/restart 거절 | `test_T_NEWSTART_…`(3), `test_C8_…`, `test_cli_인자_오류는_9`(status·restart 장부 없음 8), `test_G8_start_…` | 완전 |
| 9 | 인자 오류·corp-action/amend-rules 조건 불충족 | `test_cli_인자_오류는_9`, `test_cli_python_h1_py_로_돌면_같은_모듈`, `test_T_RETRO_정수가_아니면_split_거절`, `test_T_DELIST_…`(두 번 등록), `test_T_AMEND_…`(출처 없음), `test_C1_C15_cli_는_모든_예외를_잡음`, `test_C2_…` | 완전 |
| 130 | Ctrl-C | `test_C1_예외_분류[KeyboardInterrupt]`, `test_C1_C15_cli_는_모든_예외를_잡음` | 완전 |

---

## 6. §10.2c · §10.2d · §10.2e 결정 ↔ 시험

**§10.2c (2a·2b-1 검토)**

| 결정 | 덮는 시험 | 정도 |
|---|---|---|
| 팀장 래퍼 analyze_logged·claude_cli_version 실행마다 한 번·bad_json·decode_error | `test_h1_modules::test_T_AN_…`·`test_T_F5c_…`, `test_h1_runner::test_claude_cli_version_은_실행마다_한_번_llm_일_때만` | 완전 |
| 모르는 판정 글자 bad_verdict | `test_B5_모르는_판정_글자는_bad_verdict_폴백` | 완전 |
| 예외로 끝난 L(지문 없음 → ④-나 못 씀) | `test_B3_장부끼리_어긋나_…`, `test_끝까지_못_간_L_예외도_…`, `test_예상_밖_예외는_2_지문_없음` | 완전 |
| 사전 조건 위반은 L 아님 | `test_B3_B10_사전_조건은_L_이_아니다`, `test_사전_조건_어긋남은_4` | 완전 |
| 상장폐지 corp_actions 하나·last_date ≤ 장부 last_date·L23 장부마다 | `test_B4_…`(2), `test_B1_…`(5), `test_T_DELIST_…`(last_date 거절 9) | 완전 |
| 분할 apply_split·corp_actions 모양 | `test_B2_…`(6) | 완전 |
| L4·L5·L12 넓힘 | `test_B6_…`(3), `C[L4-m_L4]`, **`test_G5_…`** | 일부 → 완전 (L5 그날그날) |
| check_day 의 L3 는 오늘 체결만(지난 체결 거짓 L3 없음) | `test_check_day_오늘_체결가_…`, 분할 뒤 run 들(`test_T_RETRO_…`, E2E) | 완전(간접) |
| L22 허용 지문 = (code_hash, env_key) | `test_음성_대조_L22_코드_환경_종목군` | 완전 |
| L18 check_decisions | `test_음성_대조_L18_판정_기록`, `test_T_JSONL_지난_줄_수정은_L18` | 완전 |

**§10.2d (2b-2 검토 C-1~C-18)** — 결정마다 `test_h1_review2b2::test_C<번호>_…` 가 있다.

| 결정 | 덮는 시험 | 정도 |
|---|---|---|
| 환경 문제 4·ENV, Ctrl-C 130 | `test_C1_…`(4) | 완전 |
| 분할 명령 조건(효력일·같은 비율·두 번 금지·분수) | `test_C2_…`(4), `test_C16_…`(2) | 완전 |
| 정정 확정은 분할 모양 거절 | `test_C10_…` | 완전 |
| corp-action 도 관문·규칙 | `test_C11_…` | 완전 |
| 기록의 창(장부 읽기 전 L24·관문 거절도 start_date) | `test_C3_…`(2), `test_T_GATE_…` | 완전 |
| 종목군 절반 넘게 실패 D2, 대형주 실패 W5·d7_checked | `test_C4_…`(4) | 완전 |
| replay_pass 추가만, 줄거나 바뀌면 3 | `test_C5_…`, `test_T_GATE_…` | 완전 |
| restart 순서(의도 줄 → 옮김 → 끝 줄) | `test_C6_…`(2) | 완전 |
| 일지 보충(장부·meta 가 원본) | `test_C2_C7_…`, `test_C7_…` | 완전 |
| start 시각 ≥ next_open(S) 거절 | `test_C8_…`(5), `test_G8_start_…`(2) | 완전 |
| D4·D5 안내에 ⑦-3 | `test_C12_…` | 완전 |
| 0 이하 가격 D3 | `test_C13_…`(5) | 완전 |
| 디스크 쓰기(부모 폴더 fsync·F_FULLFSYNC) | `test_C14_…`(3) | 완전 |
| 종료 코드 9·1·130 | `test_C1_C15_…`, `test_cli_인자_오류는_9`, `test_G2_…`(1) | 완전 |
| 운영 전 확인(단계 7) | — | 해당 없음(맥에서 실제 자료로 할 일) |

**§10.2e (2c 검토 R-1~R-9)**

| 결정 | 덮는 시험 | 정도 |
|---|---|---|
| 창 세기(at ≥ created_at, 같은 시각이면 창 만든 start 보다 먼저 시작한 실행 빼기, 실패한 start 는 창 밖) | `test_R1_…`(3), `test_S4_실패한_start_뒤_…`(2: status 도) | 완전 |
| ②-1 L 오류 수 = errors.jsonl ∪ 종료 코드 2, 끝 줄 없는 실행은 따로 | `test_R2_…`(5), `test_S2_…`(4) | 완전 |
| 경계 시각(끝 줄 없으면 하루 기록 run_at) | `test_R3_…` | 완전 |
| ④ 거짓 양성 자동 기록 | `test_R4_…`(3), `test_S3_…`(3) | 완전 |
| 월간 보고서(처리하려던 봉의 달) | `test_R5_…`(2), `test_R6_…`, `test_month_지난달_보고서는_그달_마지막_봉까지만` | 완전 |
| 재시작 수 = 세 출처 중 큰 값 | `test_R7_…`, **`test_재시작_수는_status_restart_보고서가_같은_규칙`**(status 머리·restart 상한·start 의 restart_no 도 같은 `h1.restart_info`) | 완전 |
| 폴백 비율 분모(이 창 하루 기록이 가리키는 기록) | `test_T_F8a_팀장_수와_폴백_20퍼센트`, 요약의 팀장 수도 같은 함수(`h1.window_decision_keys`) — `test_S1_…` 등 | 완전 |
| **status 와 보고서**(L 오류·거짓 양성 세기 맞추기) | **`test_S1_…`~`test_S4_…`(12건), `test_G12_…`, `test_T5_…`·`test_T6_…`·`test_T7_…`·`test_T14a_…`·`test_T14b_…`** | **없음 → 완전**(코드 고침, 7절. 처음 판은 연장 L·D7 요약·늦은 봉/팀장 경계가 빠져 일부였음 — 검토 T-5~T-7) |
| 마감 전 실패 | `test_final_마감까지_끝날_수_없으면_H1_포워드_실패` | 완전 |

---

## 7. status 와 보고서 세기 맞추기 (단계 3 코드 변경)

**왜**: 설계 §10.2e 마지막 결정 — `h1.py status` 와 실행 끝 요약의 L 오류 수가 보고서와 다른 규칙이었다.
옛 status 는 errors.jsonl 의 줄 수만 셌다. 그래서 (가) 같은 실행이 두 줄 남기면 2, (나) errors.jsonl 쓰기에 실패한
실행(종료 코드 2 만 남음)은 0, (다) 사전 등록 ④ 로 거짓 양성 판정된 L 도 그대로 1, (라) 시계가 거칠어 같은 시각에
다시 친 start 앞의 실패 줄도 1 로 셌다. 보고서는 넷 다 바르게 센다.

**어떻게** (구현을 하나로)
- `h1_report.py`
  - `_ops` 의 일지 세기 부분을 `_journal_counts(c, B, unknown_in)` 로 떼어 냈다. 보고서 출력은 바이트까지 그대로다: 기존 보고서 시험 전부 통과,
    그리고 보고서 시험의 세 장면(미국 E2E·국내 정지·깨끗한 63봉 창)을 한 번 만들어 단계 2 코드(a161e1c 사본)와 지금 코드로
    최종·이번 달·2026-02 보고서를 각각 만들어 보니 9개 모두 바이트까지 같았다(scratch 대조).
  - `_context(mk, root, loaded, decisions, exclude_run_ids, extra_runs)`: 이미 읽은 장부에 일지를 붙인다(`_load` 도 이것을 씀).
    `exclude_run_ids` = status 자기 시작 줄 빼기, `extra_runs` = 실행 끝 요약이 곧 쓸 자기 끝 줄을 더해 세기(검토 T-6).
  - `window_counts(market, root, loaded, *, decisions, exclude_run_ids, extra_runs)`: status·요약용. **보고서 --final 과 같은 범위**
    (창이 다 찼으면 S~S+62, 덜 찼으면 지금까지·어느 봉의 일인지 모르는 줄 포함). 연장 구간 L 은 `ext_l_errors` 로 따로.
    판정 창 크기 `window_bars`(meta.rules)도 돌려준다.
  - `_late_dates`·`_ext_l_errors` 를 떼어 `_ops`·`_extension` 과 같이 씀. 팀장 수는 `_leader` 그대로.
  - (검토 T-5) `--final` 에 `ext_l_errors` 를 넣고, 창이 다 찼는데 연장 봉이 아직 없어도 S+62 뒤 L 이 있으면 연장 절에
    "그 뒤 봉을 처리하다 난 L 오류(errors.jsonl·종료 코드 2) N건 — 판정에는 안 씀" 한 줄을 찍는다(그런 L 이 없으면 출력은 그대로).
  - `_restart_info(c)` 는 `h1.restart_info` 하나를 부른다(아래).
- `h1.py`
  - `window_counts(...)`: 함수 안에서만 `h1_report` 를 늦게 import 해 위를 부른다(모듈을 읽을 때 h1 → h1_report 의존 없음,
    두 파일 머리말의 import 설명도 고침).
  - `_status_lines`: 숫자를 모두 `window_counts` 에서. 줄 모양은 그대로("L 오류 N · 자료 멈춤 N (종류) · 관문 거절 N · 늦은 봉 N/10 ·
    한 번에 따라잡은 최대 N봉"). 0 이 아니면 덧붙임: "④ 거짓 양성으로 뺀 N건 따로", "errors.jsonl 기록 없이 종료 코드 2 만 N건",
    "밀린 봉 초과", "끝 기록 없는 실행", "연장 구간(S+62 뒤) L 오류", "창 밖 기록", "읽지 못한 일지 줄". status 자기 시작 줄은
    '끝 기록 없는 실행'으로 세지 않게 뺀다. 판정 기록이 깨져 있으면 status 는 죽지 않고 그 사실을 한 줄로 알린다.
    늦은 봉·한 번에 따라잡은 봉·자료 멈춤 종류도 보고서 숫자다(전에는 A0 마라토너 하루 기록 전부·run 명령만·문제 줄마다 셌음 —
    보통 장면에서는 같고, 창이 다 찬 뒤 연장 구간·start 봉·한 실행에 같은 D 가 둘 이상일 때만 달랐음).
  - `_print_summary`(run·start 끝 요약)도 `window_counts`. 곧 쓸 자기 끝 줄(`_RunLog.end_record`, `end` 가 쓰는 것과 같은 모양)을
    더해 세므로 종료 코드 7 로 끝나는 실행의 요약도 status 처럼 "자료 멈춤 1 (D7)"(검토 T-6). `summary_lines(…, counts=)` 는
    판정 창 크기·늦은 봉·거짓 양성 수·팀장 LLM/폴백 수(보고서 ⑧ 분모와 같은 `window_decision_keys`)를 거기서 쓴다.
  - (검토 T-10) status 머리의 "판정 창 n/63" 도 meta.rules 의 창 크기를 쓴다. 안내 줄은 실제로 같은 것만 말한다:
    "일지 숫자(L·④ 거짓 양성·자료 멈춤·관문 거절·늦은 봉·한 번에 따라잡은 봉·팀장 폴백)는 보고서 --final 과 같은 규칙·범위.
    저장 자료로 다시 점검한 L·빠진 날·다른 지문(②-3)은 보고서에서".
  - (검토 T-12) 운영 코드가 부르지 않던 길을 지웠다: `_window_counts`(시험만 불렀음 — `test_h1_report.py` R1 시험 한 줄과
    gaps 도우미를 `window_counts` 로 바꿈), `summary_lines` 의 decisions 만 준 가지(아무도 안 불렀음). grep 으로 다른 호출 없음 확인.
  - `window_decision_keys(states, start, upto)` 를 h1 에 두고 보고서 `_window_keys` 가 이것을 부른다.
  - **재시작 수**(진행 담당 결정): `h1.restart_info(market, root, meta, lines)` 하나가 보고서 R-7 규칙(meta.restart_no·
    restarts.jsonl 의 done 또는 보관 폴더 있는 restart_id·archive 폴더 수 중 큰 값, 다르면 mismatch, 끝나지 않은 moving 은 pending)
    으로 센다. 보고서 `_restart_info`, status 머리("재시작 N/2", 출처가 다르면 그 사실, pending 이 있으면 그 수), `restart` 의
    상한 확인, `start` 가 meta 에 적는 `restart_no` 가 모두 이것을 쓴다(보수적으로 큰 값). `_count_restarts`(restarts.jsonl
    의 restart_id 수)는 시험 몇 개가 쓰는 낮은 단계 도우미로만 남김.
- 시험: `test_h1_gaps::test_S1_…`~`test_S4_…`·`test_T5_…`~`test_T7_…`·`test_T14a_…`·`test_T14b_…`·`test_G12_…` 가 같은 장면에서
  status 글자(머리의 창 크기·L 줄·요약 줄)·`h1.window_counts`·보고서 `collect(final=True)`(ops·연장 L·팀장 수)의 숫자
  (L 오류·거짓 양성·종료 코드 2 만·자료 멈춤과 종류·관문 거절·밀린 봉 초과·한 번에 따라잡은 봉·잠금 초과·끝 기록 없는 실행·
  창 밖 기록·늦은 봉·연장 L·팀장 LLM/폴백)가 모두 같은지 본다(도우미 `same_counts`). 재시작 수는
  `test_재시작_수는_status_restart_보고서가_같은_규칙`.
- 보고서 출력: 위 변경 뒤에도 보고서 시험의 세 장면 × 최종·이번 달·2026-02 = 9개가 a161e1c 코드와 바이트까지 같다(scratch 대조,
  T-5 의 새 줄은 연장 봉 없이 S+62 뒤 L 이 있을 때만 나와 이 장면들에는 없음).

---

## 8. 돌연변이 점검 (작성자 41개 + 검토자 25개)

**방법**: `git archive HEAD | tar -x` 로 만든 사본(scratch, 저장소 밖)마다 **한 곳만** 틀리게 바꾸고 전체 pytest(`-x`, 처음 실패에서 멈춤)를
돌렸다. "잡힘" = 시험이 하나라도 실패(또는 정상 장면 준비가 깨짐). 1차는 단계 3 전 시험(755개)으로 M01~M37, 살아남은 8개(M27·M31~M37)는
새 시험(`test_h1_gaps.py`)을 넣은 사본으로 다시(2차). M38~M41 은 이번 status 맞추기를 지키는지 보는 것(2차).
스크립트: scratch `stage3/mut.py`(저장소에 넣지 않음 — 결과는 이 표). M40 은 그 뒤(검토 3 반영) 지운 `_window_counts` 를
겨눈 것이라 지금 코드에는 해당 줄이 없다.

| # | 규칙 | 틀리게 바꾼 것 | 1차(단계 3 전) | 처음 잡은 시험 | 2차(단계 3 뒤) |
|---|---|---|---|---|---|
| M01 | A1 시가 순서 | 주식 매수(d)를 매도(c)보다 먼저 | 잡힘 | `test_h1_check` 정상 장면 준비(봉마다 check_day 가 L4 를 냄) → `test_정상_장부_여러_날_L_0[a]` | — |
| M02 | A1 시가 순서 | S+1 첫 전부 지수(a) 없앰 | 잡힘 | 같음(L10) | — |
| M03 | 쓸어 담기 문턱 | 현금 < 1 → ≤ 1 | 잡힘 | `test_h1_engine::test_T_A1_5_쓸어담기_문턱[1.0-True]` | — |
| M04 | 쓸어 담기 줄임 | 줄임 1e-12 를 건너뜀 | 잡힘 | `test_h1_check::test_B6_경계_보류_need_약_avail_1빼기_1e9[5e-10-True]` | — |
| M05 | 여유 1e-9 | A1 보류 판단에서 (1−1e-9) 뺌 | 잡힘 | 같음 | — |
| M06 | 여유 1e-9 | 지수 매도량에서 (1+1e-9) 뺌 | 잡힘 | 정상 장면 준비(L11) | — |
| M07 | 세율 표 | 시행일 당일을 옛 세율로(≥ → >) | 잡힘 | `test_h1_engine::test_T_A1_6_국내_매도세_표_경계` | — |
| M08 | 세율 표 | 국내 지수 매도에도 주식 세율 | 잡힘 | 정상 장면 준비(L9) | — |
| M09 | 그림자 서킷 prev | prev = team `prev_value` | 잡힘 | 정상 장면 준비(L20) → `test_B1_한쪽만_보유한_상장폐지는_정상` | — |
| M10 | 그림자 서킷 한도 | 누적·하루 한도를 뒤바꿈 | 잡힘 | 정상 장면 준비(L20) | — |
| M11 | L4 판단 | 정지가 아닌 날 남은 주문을 안 봄 | 잡힘 | `test_h1_check::test_음성_대조_…[L4-m_L4]` | — |
| M12 | L4 판단 | 같은 시가 체결 순서를 안 봄 | 잡힘 | `test_h1_check::test_B6_매수가_매도보다_먼저면_L4` | — |
| M13 | L12 판단 | '0주' 보류를 안 봄 | 잡힘 | `test_h1_check::test_음성_대조_…[L12-m_L12b]` | — |
| M14 | L12 판단 | 보류 순간 다시 센 A1 가능 금액에서 지수 몫 뺌 | 잡힘 | 정상 장면 준비(거짓 L12) | — |
| M15 | L15 판단 | 정지일도 보유일수로 셈 | 잡힘 | 정상 장면 준비(국내 정지 장면에서 거짓 L15) | — |
| M16 | L23 판단 | 정리 가격 비교 없앰 | 잡힘 | `test_h1_check::test_음성_대조_…[L23-m_L23]` | — |
| M17 | L11 판단(여유) | 지수 매도 상한 여유 2e-9 → 2e-3 | 잡힘 | `test_h1_check::test_음성_대조_…[L11-m_L11]` | — |
| M18 | D3 | 보유·대기 종목 t 행 없음을 통과 | 잡힘 | `test_h1_engine::test_run_bar_거절_조건` | — |
| M19 | D6 | 소급 수정 허용 오차 1e-6 → 1e-3 | 잡힘 | `test_h1_review2b2::test_C17_대기_자산_지난_시가가_바뀌면_D6` | — |
| M20 | D7 | 국내 기준 지수 확정 시각 22:30 → 16:00 | 잡힘 | `test_h1_review2b2::test_C8_S_봉이_늦은_봉이_되는_start_는_거절[kr-…]` | — |
| M21 | 커밋 순서 | HEAD 를 장부 6개보다 먼저 씀 | 잡힘 | `test_h1_review2b2::test_C1_디스크_가득은_ENV_4_L_아님_다음_실행이_되살림` | — |
| M22 | 커밋 순서 | 백업(backup/<run_id>) 생략 | 잡힘 | 같음 | — |
| M23 | 늦은 봉 5 | 한 번에 5봉도 창 실패(> → ≥) | 잡힘 | `test_h1_review2b2::test_C17_밀린_봉_5개는_처리_6개는_6` | — |
| M24 | 늦은 봉 10 | 창 전체 10봉도 실패(≤ → <) | 잡힘 | `test_h1_report::test_final_경계값은_통과[늦은봉10]` | — |
| M25 | 판정 ②-1 | 저장 자료로 다시 점검한 L 을 무시 | 잡힘 | `test_h1_report::test_final_운영_기준_어기면_창_실패[빠진날]` | — |
| M26 | 판정 ②-1 | runs.jsonl 종료 코드 2 를 무시 | 잡힘 | `test_h1_report::test_R2_…[nowrite]` | — |
| M27 | 판정 ②-3 | 하루 기록 지문을 code_hash 만 보고 env 무시 | **못 잡음** | — | 잡힘 `test_h1_gaps::test_G1_…` |
| M28 | 판정 ②-3 | runs.jsonl 의 다른 지문 실행을 무시 | 잡힘 | `test_h1_report::test_final_운영_기준_어기면_창_실패[다른지문]` | — |
| M29 | 창 세기 | created_at(창이 만들어진 때)을 무시 | 잡힘 | `test_h1_report::test_R1_…[False]` | — |
| M30 | 창 세기 | start_date 'unknown' 줄을 창에서 뺌 | 잡힘 | `test_h1_report::test_T_F8a_운영_기준_칸` | — |
| M31 | LLM 시각 경계 | 봉 시작 판단 `지금 < next_open` → `≤`(정각에도 llm) | **못 잡음** | — | 잡힘 `test_G8_봉_시작이_next_open_정각이면_late[…late-us]` |
| M32 | LLM 시각 경계 | 묻기 직전 재확인 `≥ next_open` → `>`(정각에도 물음) | **못 잡음** | — | 잡힘 `test_G8_묻기_직전_시각이_next_open_정각이면_묻지_않음` |
| M33 | D7 | 확정 시각 정각(22:30:00)은 D7 아님(≥ → >) | **못 잡음** | — | 잡힘 `test_G8_KS200_확정_시각_22시30분_정각` |
| M34 | start 시각 | next_open(S) 정각의 start 를 받아 줌(≥ → >) | **못 잡음** | — | 잡힘 `test_G8_start_는_next_open_S_정각부터_거절[…-8]` |
| M35 | L5 판단 | 그날그날 보유+매수 대기 ≤ 5 를 안 봄 | **못 잡음** | — | 잡힘 `test_G5_…` |
| M36 | L10 판단 | A1 종가 현금 < 1(쓸어 담기 누락)을 안 봄 | **못 잡음** | — | 잡힘 `test_G6_…` |
| M37 | L19 판단 | 빈자리 부족이면 다 채웠는지 안 봄 | **못 잡음** | — | 잡힘 `test_G7_…` |
| M38 | status = 보고서 | status 가 ④ 거짓 양성을 빼지 않음 | (새 코드) | — | 잡힘 `test_S3_거짓_양성_판정은_status_와_요약에서도_빼고_따로` |
| M39 | status = 보고서 | status 가 자기 시작 줄을 '끝 기록 없는 실행'으로 셈 | (새 코드) | — | 잡힘 `test_S1_깨끗한_창은_모두_0_…` |
| M40 | status = 보고서 | `_window_counts` 를 옛 규칙(errors.jsonl 줄 수)으로 | (새 코드) | — | 잡힘 `test_S2_L_오류는_errors_jsonl_과_종료_코드_2_의_합집합_status_도_같음[nowrite]` |
| M41 | status = 보고서 | 창이 다 차도 끝까지 셈(연장 L 을 창에 넣음) | (새 코드) | — | 잡힘 `test_S4_status_창이_다_차면_S62_까지_그_뒤는_연장으로_따로` |

- **정리**: 1차 37개 중 29개 잡힘, 8개 못 잡음. 못 잡은 8개는 모두 "경계(정각)" 또는 "점검 코드 안의 세부 규칙 하나"였고, 새 시험 뒤 2차에서 모두 잡힘.
  status 맞추기 돌연변이 4개(M38~M41)도 모두 잡힘. 최종 41개 모두 잡힘.
- "정상 장면 준비"로 잡힌 것(M01·M02·M06·M08~M10·M14·M15)은 엔진을 틀리게 바꾸자 봉마다 도는 장부 점검(check_day)이 바로 L 을 내서
  시험용 정상 장면을 만드는 단계에서 멈춘 것이다(엔진 오류 → 점검이 잡음 = 설계가 의도한 두 겹 방어).

**검토자 돌연변이 25개** (`docs/h1-review-3.md` 부록 A, 검토자의 scratch `review3/mut.py` 를 그대로 — 사본만 지금 코드로 바꿔 다시 돌림,
전체 pytest `-x`). 검토 때(9039f3b) 17개 잡힘·8개 살아남음 → **지금 25개 모두 잡힘**.

| ID | 규칙 | 틀리게 바꾼 것 | 검토 3(9039f3b) | 지금 | 처음 잡은 시험(지금) |
|---|---|---|---|---|---|
| K-L11lo | L11 지수 자금 매도 | 하한 `short <= got` 지움 | **살아남음** | 잡힘 | `test_h1_gaps::test_T9_규칙마다_음성_대조[L11하한]` |
| K-L12A1 | L12 A1 여유 | A1 도 `need > avail` | 잡힘 | 잡힘 | `test_h1_check::test_B6_경계_보류_need_약_avail_1빼기_1e9[5e-10-True]` |
| K-L15split | L15 분할 반영 매수가 | `applied_after >= 매수일` → `>` | **살아남음** | 잡힘 | `test_h1_gaps::test_T2_산_날_장_마감_뒤_분할_적용_경계는_L_없음` |
| K-L22env | L22 | env 무시(code_hash 만) | 잡힘 | 잡힘 | `test_h1_check::test_음성_대조_L22_코드_환경_종목군` |
| K-L23pair | L23 짝 점검 | 두 장부 등록 비교 끔 | 잡힘 | 잡힘 | `test_h1_check::test_B1_두_장부의_등록이_다르면_짝_점검_L23` |
| K-L4sig | L4 신호일 < 체결일 | 끔 | **살아남음** | 잡힘 | `test_h1_gaps::test_T9_규칙마다_음성_대조[L4신호일]` |
| K-L17verdict | check_pair L17 | 판정 비교 끔(열쇠만) | **살아남음** | 잡힘 | `test_h1_gaps::test_T9_규칙마다_음성_대조[L17짝판정]` |
| K-L18prefix | L18 HEAD 앞부분 sha | 줄 수만 봄 | 잡힘 | 잡힘 | `test_h1_check::test_음성_대조_L18_판정_기록` |
| H-D3close | D3 이상한 종가 | 끔 | 잡힘 | 잡힘 | `test_h1_review2b2::test_C13_보유_종목_t_종가가_이상하면_D3[0.0]` |
| H-D6days | D6 비교 날 수 | 최근 5일 → 1일 | 잡힘 | 잡힘 | `test_h1_gaps::test_G13_정정_확정도_corp_actions_jsonl_과_changes_jsonl_에_남음` |
| H-D7plus1m | D7 확정 시각 | +1분 | 잡힘 | 잡힘 | `test_h1_gaps::test_G8_KS200_확정_시각_22시30분_정각` |
| H-D5half | D5 절반 | `>=` → `>` | 잡힘 | 잡힘 | `test_h1_review2b2::test_C17_D5_종목군_정확히_절반이_거래한_날도_구멍` |
| H-D2delist | D2 상장폐지 제외 | 등록 종목도 받기 대상 | 잡힘 | 잡힘 | `test_h1_gaps::test_G9_국내_상장폐지_정리_비용은_그_봉_날짜_매도세` |
| H-HEADrestore | HEAD 복구 | 백업이 HEAD 와 맞는지 안 봄 | **살아남음** | 잡힘 | `test_h1_gaps::test_T1_백업이_있어도_HEAD_와_안_맞으면_되살리지_않고_L24` |
| H-backupAfter | 커밋 순서 | 백업을 장부 6개 쓴 뒤에 | 잡힘 | 잡힘 | `test_h1_gaps::test_T1_백업이_있어도_HEAD_와_안_맞으면_되살리지_않고_L24` |
| H-L24mid | L24 판정 기록 가운데 줄 | 깨진 줄 건너뜀 | 잡힘 | 잡힘 | `test_h1_engine::test_T_JSONL_중간_줄_깨짐_중복_열쇠` |
| H-fpA | ④ (가) | 지문 비교 없이 통과 줄만 | 잡힘 | 잡힘 | `test_h1_gaps::test_S3_거짓_양성_조건이_틀리면_status_도_L_1[가]` |
| H-fpB | ④ (나) | 내용 지문 비교 끔 | 잡힘 | 잡힘 | `test_h1_gaps::test_S3_거짓_양성_조건이_틀리면_status_도_L_1[나]` |
| H-delistTaxDate | ⑦-4 정리 세율 날짜 | 정리 봉 → 등록 마지막 거래일 | **살아남음** | 잡힘 | `test_h1_gaps::test_G9_국내_상장폐지_정리_비용은_그_봉_날짜_매도세` |
| H-restartCap | ⑤ 재시작 상한 | `>=` → `>` | 잡힘 | 잡힘 | `test_h1_gaps::test_재시작_수는_status_restart_보고서가_같은_규칙` |
| R-lateExt | status 늦은 봉 경계 | S+62 대신 마지막 봉까지 | **살아남음** | 잡힘 | `test_h1_gaps::test_T7_status_늦은_봉과_팀장_수는_S62_에서_끊김` |
| R-leaderExt | status 팀장 수 경계 | S+62 대신 마지막 봉까지 | **살아남음** | 잡힘 | `test_h1_gaps::test_T7_status_늦은_봉과_팀장_수는_S62_에서_끊김` |
| R-preRuns | 창 세기(같은 시각) | 창 만든 start 전 실행 빼기 끔 | 잡힘 | 잡힘 | `test_h1_gaps::test_S4_실패한_start_뒤_같은_S_로_다시_시작한_창은_status_도_0[True]` |
| R-market | ① 시장별 | 일지 줄의 시장 확인 끔 | 잡힘 | 잡힘 | `test_h1_gaps::test_G12_다른_시장의_L_과_멈춤은_이_시장_숫자에_안_섞임` |
| R-fb20 | ⑧ 20% | `>` → `>=` | 잡힘 | 잡힘 | `test_h1_report::test_T_F8a_폴백_20퍼센트_경계[1-5-False]` |

- 살아남았던 8개를 잡는 시험은 모두 이번에 더한 것(T1·T2·T7·T9·G9 바꿈). 검토자가 "겹치는 규칙이라 사실상 같은 동작"이라 한
  K-L4sig·K-L17verdict 도 따로 음성 대조를 넣어 잡게 했다(진행 담당 결정).
- 검토자의 확인 시험(부록 B)을 지금 코드로 돌리면 P1(연장 L 이 보고서에 없음)·P2(요약이 자기 D7 을 안 셈)는 **이제 실패**(고쳐져서),
  P4~P7 은 바른 동작 그대로 통과.

---

## 9. 시험 환경 점검 (방법·결과·다시 돌리는 법)

**왜**: 시험이 진짜 인터넷·진짜 claude·진짜 장부(`state/`)를 건드리거나, 컴퓨터 설정(시간대·해시 씨앗·언어)이나 시험 순서에 따라
결과가 달라지면, 맥에서 운영할 때 "시험은 통과했는데 실제로는 다르게 도는" 일이 생길 수 있다.

**도구**: `tools/h1_test_guard.py` — **저장소에 두었다**(판단 이유: 단계 4 독립 검토와 단계 7 맥 운영 전 확인 때 같은 방법으로 다시
돌려야 한다. 운영 코드가 아니고 `CODE_FILES` 밖이라 code_hash·관문에 영향이 없고, h1.py 가 읽지 않으며, 저장소에는 아무것도 쓰지 않고
임시 폴더만 쓴다 — 예외로 끝나도 `try/finally` 로 지움). 검토 3(T-3·T-4·T-13) 뒤 하는 일:

| 점검 | 방법 |
|---|---|
| 인터넷(파이썬 수준) | 임시 폴더의 `sitecustomize.py` 를 PYTHONPATH 맨 앞에. `socket.socket.connect`·`connect_ex`, `_socket.socket`(C 소켓 형을 감싼 형으로 바꿔 끼움)의 `connect`·`connect_ex`, `socket.create_connection`, `socket.getaddrinfo`(localhost 밖), `urllib.request.urlopen` 을 부르면 기록하고 OSError. 기록 파일 경로는 sitecustomize 글자 안에 박혀 있어 env 와 상관없다. `subprocess.Popen` 도 감싸서 시험이 **env 를 새로 주거나 PYTHONPATH 를 덮어써** 하위 파이썬을 띄워도 지킴이 폴더를 PYTHONPATH 맨 앞에 다시 붙인다. 원래 sitecustomize(이 컨테이너의 zlib 고침)는 이어서 불러 준다 |
| 인터넷(이름공간, 리눅스 선택) | `--netns`: pytest 전체를 `unshare -rn`(네트워크가 없는 이름공간)에서. 아래 "못 막는 길"도 실제로는 밖으로 못 나간다(기록 대신 연결 실패로 드러남) |
| 진짜 claude | 임시 폴더의 가짜 `claude`(불리면 기록·종료 코드 97)를 PATH 맨 앞에. **기록 파일 절대 경로를 스크립트 글자에 박아** env 를 새로 준 하위 프로세스가 불러도 기록된다. 따로 진행 담당이 준 기존 가짜(scratch `trapbin/claude`)로도 전체 pytest 를 돌림 |
| 결정성 | `PYTHONHASHSEED` 0·12345 × `TZ` UTC·Asia/Seoul·America/New_York 6번, LANG 은 그중에서 `C`·`C.UTF-8`·`ko_KR.UTF-8`(이 컨테이너에는 없음 → C·C.UTF-8 만)을 돌아가며. `--grid` 이면 셋의 곱 전부. (파이썬은 C 로캘에서도 UTF-8 모드로 돌아 C 만으로는 비 UTF-8 이 안 된다 — 그래서 C.UTF-8·ko_KR 을 따로 돌림) |
| 순서 | 시험 항목 통째 역순 1번 + 시험 **파일** 순서를 씨앗(20261104)으로 섞은 1번(파일 안 순서는 그대로 — 파일 범위 준비물이 한 번만 만들어지게). 작은 pytest 플러그인 `-p h1_guard_order` |
| 비교 | 모든 실행의 junit xml 로 시험마다 결과(통과·실패·건너뜀)가 같은지 |
| 저장소 | 앞뒤로 ① `state/`·`results/` 아래 모든 항목(무시 파일 포함, **폴더가 이미 있어도**)의 크기·수정 시각·sha256 ② `git status --porcelain --ignored --untracked-files=all` ③ 그 목록의 추적 안 되는·무시되는 파일마다 크기·수정 시각·sha256. 바이트코드 캐시(`__pycache__`·`*.pyc`)는 `python -I` 하위 프로세스가 PYTHONDONTWRITEBYTECODE 를 무시하고 써서 따로 알리기만 함(실패로 안 침), `.pytest_cache`·`.ruff_cache` 는 도구 캐시라 뺌 |

**시험 쪽 지킴이**(T-3): h1 시험 파일 넷(`test_h1_runner`·`test_h1_report`·`test_h1_review2b2`·`test_h1_gaps`)의 fixture 가 시험마다 앞뒤로
`state/`·`results/` 아래 모든 항목(폴더가 이미 있어도)의 종류·크기·수정 시각을 견준다(`tests/h1_repo_guard.py`). 시험 수백 개마다
맥 `state/` 를 해시하면 느려서 sha256 은 안 본다 — 같은 크기로 쓰고 수정 시각까지 되돌린 바꿈은 못 보지만(`test_T3_저장소_도우미…` 가
이 한계를 그대로 시험으로 적음) 그런 바꿈은 지킴이 도구가 sha256 으로 본다.

**맥처럼 `state/h1` 이 이미 있는 상태**: 저장소에 `state/` 를 만들 수 없으므로(이 컨테이너 규칙) 가짜 저장소로 흉내 낸다 —
`test_T3_지킴이는_맥처럼_state_h1_이_이미_있어도_그_안의_변화를_잡음`: 임시 폴더에 `tools/h1_test_guard.py` 를 복사하고 `state/h1/us/HEAD.json`·
`state/h1/runs.jsonl` 을 미리 둔 뒤, 그 `runs.jsonl` 에 한 줄 더하는 시험을 지킴이로 돌리면 종료 코드 1·그 파일 이름을 알리고, 아무것도
안 건드리는 시험이면 통과(그 안의 파일 sha256 그대로)·임시 폴더 지워짐.

**못 막는 길(정직하게)** — 아래는 지킴이의 파이썬 수준 막기로는 **기록되지 않는다**(`--netns` 를 쓰면 실제 연결은 실패):
1. `python -I` 하위 프로세스(PYTHONPATH 무시). 이 저장소 시험 3개가 이렇게 띄운다(`test_h1_engine::test_T_ENTRY_운영_경로에서_h1_을_읽지_않는다`,
   `test_h1_engine::test_h1_h1_check_어느_쪽을_먼저_읽어도_된다`, `test_h1_report::test_T_F8b_R2_sim_team_을_python_I_로_부른_결과와_같음`) —
   셋 다 시세 받기·claude 를 쓰지 않는다(소스와 R2 `sim_team.load_frames` 가 저장된 CSV 만 읽음을 확인).
2. `subprocess` 를 거치지 않고 env 를 새로 준 하위 프로세스(`os.execve`·`os.posix_spawn` 등).
3. 파이썬 밖: ctypes 로 libc `connect`, C 로 만든 HTTP 라이브러리(이 venv 에 `curl_cffi`·`yfinance` 가 깔려 있음 — 저장소 코드는 안 씀),
   `curl` 같은 다른 프로그램.
4. 지킴이보다 먼저 `from _socket import socket` 처럼 잡아 둔 이름.
5. 가짜 claude: PATH 를 통째로 바꾸거나 claude 를 절대 경로로 부르는 길(시험 파일마다의 지킴이 — `analyst`·`subprocess.run` 바꿔 끼우기 — 가 그 몫).
검토 3 의 우회 시험(부록 C)을 새 지킴이로 다시 돌린 결과: 같은 프로세스(C0)·env 를 새로 준 하위 파이썬(B2)·PYTHONPATH 를 덮어쓴 하위
파이썬(B3)·`_socket` 직접(B4)은 **막히고 기록됨**(전에는 B2~B4 통과·기록 0), `python -I`(B1)·ctypes(B5)는 여전히 연결됨(위 1·3),
env 에 기록 변수가 없는 가짜 claude 호출(B6)은 **기록됨**(전에는 0).

**지킴이가 정말 잡는지(시험의 시험)**: 위 맥 흉내 시험 외에, scratch 의 일부러 나쁜 시험(인터넷·claude·TZ 의존·순서 의존)과 검토 3 우회
시험으로 확인(저장소에 넣지 않음).

**결과** (마지막 코드로)

| 실행 | 결과 |
|---|---|
| `--quick`(기본 seed0·UTC·C / 역순 seed12345·Seoul·C.UTF-8 / 파일 순서 섞기 seed12345·NewYork·C.UTF-8) | 3번 모두 **804 passed**, 결과 같음, 인터넷 0·claude 0, state/·results/ 그대로, git status(무시 파일·내용 포함) 그대로 |
| `--quick --netns`(네트워크 없는 이름공간) | 3번 모두 804 passed, 같은 결과, 모두 통과 |
| 전부(seed 0·12345 × TZ 3 = 6번, LANG 은 C·C.UTF-8 을 돌아가며 + 역순 + 섞기 = 8번) | 8번 모두 **804 passed**, 시험마다 결과 같음, 인터넷 0·claude 0, state/·results/ 그대로. 이 실행 도중 진행 쪽 스냅샷 커밋(ba65a42)이 들어와 git status 비교가 "바뀜"으로 나옴 — 지킴이가 저장소 변화를 제대로 알아챈 것이고 시험이 쓴 것이 아님(바뀐 줄은 모두 커밋된 작업 파일). 커밋 없이 다시 돌린 결과는 아래 줄 |
| 전부 다시(커밋 없는 상태) | 8번 모두 **804 passed**, 시험마다 결과 같음, 인터넷 0·claude 0, state/·results/ 그대로, git status(무시 파일·내용 포함) 그대로 → **모두 통과**(참고: `python -I` 하위 프로세스가 쓴 바이트코드 캐시 13줄은 따로 알림, 끝난 뒤 지움) |
| 진행 담당이 준 기존 가짜 claude(scratch `trapbin/claude`)를 PATH 맨 앞에 두고 전체 pytest | 804 passed, `claude_calls.log` 가 생기지 않음(호출 0) |

**다시 돌리는 법**
```
~/.venv-cs/bin/python tools/h1_test_guard.py              # 전부(pytest 8번, 3개씩 함께 → 이 컨테이너에서 약 5분)
~/.venv-cs/bin/python tools/h1_test_guard.py --quick      # 기본 + 역순 + 파일 순서 섞기, 3번
~/.venv-cs/bin/python tools/h1_test_guard.py --netns      # (리눅스) 네트워크 없는 이름공간에서
~/.venv-cs/bin/python tools/h1_test_guard.py --grid       # 씨앗 × TZ × LANG 전부
~/.venv-cs/bin/python tools/h1_test_guard.py -- tests/test_h1_gaps.py   # 대상 지정
# 종료 코드 0 = 모두 통과, 1 = 어긋남(무엇이 어긋났는지 화면에). --keep 이면 임시 폴더(로그·junit xml)를 남김
```

---

## 10. 설계에 반영할 것 (진행 담당 몫 — 시험 담당은 설계 문서를 고치지 않았다)

진행 담당이 717a417 에서 이미 반영한 것: ⑩ 의 "종목군 파일 지문은 L22", §4 D4 "이미 처리한 구간에 새 날짜가 끼어듦도 D4",
§4 끝 "음성 대조는 코드 안의 규칙마다", 정각 경계(봉 시작 next_open 정각 = 늦은 봉, 묻기 직전 정각 = 안 물음, D7 정각부터,
start 는 next_open(S) 정각부터 거절), §10.2e "status 와 보고서"(같은 함수·같은 범위·재시작 수도 같은 함수), §10.2f(지도·새 시험 ID·
지킴이 도구). 남은 것:

| # | 어디 | 지금 설계 | 실제 동작·제안 |
|---|---|---|---|
| 1 | §3.8-2 운영 기준 본문 | "L 오류 수(`errors.jsonl`)" | §10.2e R-2·"status 와 보고서" 대로 "errors.jsonl ∪ runs.jsonl 종료 코드 2(run_id 로 한 번), ④ 거짓 양성은 빼고 따로"로 본문 고치기 |
| 2 | §3.8 `--final` 연장 기록 | S+62 뒤 처리한 봉 | 연장 봉이 아직 없어도 S+62 뒤 봉을 처리하다 난 L 은 연장 절에 한 줄로 보인다(판정에는 안 씀, 검토 T-5) — 본문에 더하기 |
| 3 | §3.3 요약 | "점검 L 0 · 자료 멈춤 0 · … · 팀장 LLM 3 / 폴백 0" | 요약은 곧 쓸 자기 끝 줄을 더해 센다(종료 코드 7 이면 "자료 멈춤 1"), 판정 창 크기·늦은 봉·팀장 수는 S+62 까지·meta.rules, "점검 L N (④ 거짓 양성 K건 뺌)" 표시 — 요약 예 설명에 한 줄 |
| 4 | §3.7 runs.jsonl "창 세기" | `_in_window` 만 적음 | "같은 시각이면 창을 만든 start 보다 먼저 시작한 실행의 줄은 뺀다(보고서·status 모두)"를 더하기 |
| 5 | §2.2 ⑤·§3.9(8 거절) | 재시작 상한 2번 | 상한 확인과 `start` 가 meta 에 적는 restart_no 도 R-7 규칙(세 출처 중 큰 값, `h1.restart_info`)을 쓴다 — ⑤ 에 "재시작 수는 어디서나 이 규칙" 한 줄 |
| 6 | §3.6 판정 기록 | "재시작해도 지우지 않는다. 새 창의 같은 열쇠는 이 기록을 다시 쓴다" | 옛 창이 늦게 처리해 `late_no_llm` 으로 남긴 열쇠도 새 창이 그대로 다시 쓴다(새 창 S 가 제때여도 LLM 안 부름) → 새 창 ⑧ 폴백 비율에 들어간다(T14c). 의도가 맞는지 한 줄 |
| 7 | §6 표 | §10.2f 의 새 ID | §10.2f 에 더해: **T-RESTARTN**(재시작 수 한 규칙), T-HEAD 에 "백업이 있지만 HEAD 와 다름 → L24", T-RETRO 에 "산 날 마감 뒤 분할", T-DELIST 에 "세율 구간이 다른 두 날짜" — 본문 §6 표에도 옮기기 |
| 8 | §10.2f "완전" 기준 | "돌연변이가 실제로 시험에 잡힐 때만" | 이 지도는 그 기준을 66개 규칙(8절)에만 실제로 확인했고, 나머지는 시험을 읽어 판단했다(머리말). 남은 규칙까지 돌연변이로 넓힐지는 단계 4 검토에서 정하기 |
| 9 | §8 맥 운영·단계 7 | | 단계 7 맥 확인에 `tools/h1_test_guard.py`(맥은 `--netns` 없음, 저장소 `state/h1` 이 이미 있으면 그 안을 sha256 까지 앞뒤로 견줌)와 9절 "못 막는 길"을 넣기 |
