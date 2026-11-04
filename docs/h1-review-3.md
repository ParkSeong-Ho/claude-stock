# H1 단계 3 "시험 보강" 독립 검토 (검토 3)

- 검토일: 2026-11-04 · 브랜치 `h1-forward` · 대상 커밋 **9039f3b** (기준 a161e1c, 범위 `git diff a161e1c 9039f3b` 에서 `docs/h1-guide/`·`docs/작업-이어가기.md` 제외)
- 대상: `docs/h1-test-map.md`, `tests/test_h1_gaps.py`(34건), `tools/h1_test_guard.py`, `h1.py`·`h1_report.py` 의 status ↔ 보고서 세기 맞추기
- 사양: `docs/h1-forward-design.md` 3판(§2.2, §3.3, §3.7, §3.8, §3.9, §4, §6, §10.2c~§10.2e)
- 검토자는 이 시험·코드를 쓰지 않았고 작성자 설명도 받지 않았다. 저장소에서 바꾼 것은 이 파일 하나다.

**직접 돌려 본 것** (scratch = 저장소 밖 `git archive` 사본, 진짜 claude 대신 PATH 맨 앞에 가짜 claude, 인터넷 안 씀)

| 무엇 | 결과 |
|---|---|
| 저장소에서 `tools/h1_test_guard.py --quick` | 기본·역순 둘 다 **789 passed**, 인터넷 시도 0·claude 0, 무시 파일까지 포함한 `git status --ignored` 전후 같음, 임시 폴더 지워짐 |
| scratch 사본 전체 pytest | 787 passed, 2 skipped(git 저장소·R2 브랜치가 없어서 — 정상) |
| 지도의 시험 이름 대조 | 지도에 적힌 `test_…` 참조 382개를 수집된 시험 항목과 맞춤 → 모두 실제로 있음 |
| 돌연변이 25개(작성자 41개와 겹치지 않게 고위험 규칙 위주, 전체 pytest `-x`) | **17개 잡힘, 8개 살아남음**(부록 A) |
| 보고서 바이트 대조 | 9개 장면(미국 E2E·국내 정지·깨끗한 66봉·연장 L·R3 끝 줄 없음·④ 거짓 양성·errors.jsonl 쓰기 실패·반쯤 쓴 줄·같은 시각 실패한 start) × (최종 + 달마다) = **29개 보고서**, a161e1c 코드와 9039f3b 코드가 **바이트까지 같음** |
| 확인용 시험 P1~P7(scratch, 부록 B) | 발견 T-1·T-2·T-5·T-6·T-8·T-9 의 재현 |
| 지킴이 우회 시험(scratch, 127.0.0.1 로컬 서버만) | 대조(보통 파이썬)는 막고 기록, 우회 6가지는 모두 통과(부록 C) |
| `python h1.py status --market us` 를 실제 CLI 로(scratch 사본의 `state/h1` 에 장면 복사) | 늦은 import 정상, 거짓 양성 장면에서 "L 오류 0 (④ 거짓 양성으로 뺀 1건 따로)" |

---

## 요약

- **치명 없음.** 장부 계산·점검·판정 코드에서 틀리게 도는 곳은 찾지 못했다. status 맞추기 변경은 보고서 출력을 바꾸지 않았고(29개 바이트 같음), h1 → h1_report 늦은 import 는 순환·관문 지문 문제가 없다.
- **지도는 이름 수준에서는 사실이지만 "157/157 완전"은 과장이다.** 고위험 항목 대부분(②-1·②-2·②-3, L12·L22·L23·L18·L24, D2·D3·D5·D6·D7, 커밋 순서의 백업 순서, ④ (가)(나), 창 세기, 시장별, 재시작 상한)은 돌연변이로 실제로 지켜진다. 그런데 **HEAD 복구의 "백업도 HEAD 와 맞아야 되살림"**(T-1)과 **L15 의 "산 날 마감 뒤 분할" 경계**(T-2)는 코드를 지워도 789개가 다 통과한다. 둘 다 장부 안전·거짓 L(재시작)에 바로 닿는 곳이다.
- **status ↔ 보고서**: L 오류·거짓 양성·종료 코드 2 만·자료 멈춤(종류)·관문 거절·밀린 봉·잠금 초과·끝 기록 없는 실행·창 밖 기록은 같은 함수(`_journal_counts`)를 써서 같다. 어긋나는 곳은 둘이다. (1) S+62 를 저장한 뒤 연장 봉을 하나도 못 저장한 채 난 L 은 status 에만 보이고 보고서 `--final` 에는 흔적이 없다(T-5). (2) 실행 끝 요약은 자기 실행의 D7(종료 코드 7) 멈춤을 빼고 센다(T-6). 늦은 봉·팀장 수의 S+62 경계는 지금 코드로는 같지만 시험이 지키지 못한다(T-7).
- **지킴이 도구**: 보통 길(같은 프로세스·`-I` 없이 띄운 파이썬)의 인터넷은 막고 기록한다. 그러나 `python -I` 말고도 env 를 새로 준 하위 프로세스, **PYTHONPATH 를 덮어쓴 하위 프로세스(새 시험 G2 가 바로 그렇다)**, `_socket`, ctypes/C 라이브러리(이 venv 의 curl_cffi 같은)는 못 막고, claude 호출 기록은 환경변수에 기대 env 를 바꾸면 남지 않는다(T-4). 가장 큰 문제는 **맥에서 `state/` 가 이미 있으면 "저장소를 더럽히지 않음" 점검이 사실상 꺼진다**는 것(T-3) — 단계 7 맥 확인이 바로 그 상황이다.
- 새 시험 34건은 모두 실패할 수 있고(작성자 돌연변이 + 검토자 돌연변이 7개를 gaps 시험이 먼저 잡음), 고정 시각·tmp_path·monkeypatch 되돌림이 바르며, 순수 중복은 없다. 다만 G9 의 "그 봉 날짜 세율"은 장면의 두 날짜가 같은 세율 구간이라 가르지 못한다(T-8).

---

## 발견

| ID | 심각도 | 파일:행 | 문제 | 근거(재현·돌연변이) | 고칠 것 |
|---|---|---|---|---|---|
| T-1 | 중요 | `h1.py:2403` (`load_market`) · 지도 4절 "커밋 순서… 그 밖은 L24 → 완전", 1절 T-HEAD "완전" | 장부가 HEAD 와 다를 때 `backup/<HEAD.run_id>/` 가 **있지만 HEAD 와 맞지 않으면** 되살리지 말고 L24 여야 한다. 이 확인(`not _mismatched(root, bparts, head)`)을 지키는 시험이 없다. `test_T_HEAD_HEAD_도_백업도_안_맞으면_L24` 는 **백업이 아예 없는** 경우만 본다 | 돌연변이 H-HEADrestore(확인 지움) → 전체 787 통과. 확인 시험 P6: 3개 바꾼 뒤 멈춤 → 백업 파일 한 글자 바꿈 → 바른 코드 종료 코드 2·L24, 돌연변이 **종료 코드 0**(맞지 않는 백업으로 조용히 되살리고 진행). 되살린 뒤 HEAD 와 다시 견주는 곳이 없어서 손상된 백업이 그대로 장부가 된다(이후 점검 L 이 일부를 잡을 수는 있음) | P6 같은 시험을 `test_h1_runner` T-HEAD 에 더하기(백업 있음·HEAD 와 다름 → L24·장부·백업 그대로). 지도 4절·1절 정도를 고치기 |
| T-2 | 중요 | `h1_check.py:562` (L15 분할 반영 매수가) · 지도 2절 L15 "완전" | `applied_after >= 매수일` 의 **같은 날** 경계(그 종목을 산 날 장 마감 뒤에 분할 적용, 다음 날 효력)에 시험이 없다. `>` 로 바뀌면 바른 장부에 **거짓 L15 → 종료 코드 2 → 재시작**이 나는데 아무 시험도 못 잡는다. `test_R8_분할_적용일에_산_주식은…` 은 보고서 `realized` 단위 시험이라 점검을 안 돈다 | 돌연변이 K-L15split(`>=`→`>`) → 전체 787 통과. 확인 시험 P5: 마라토너가 D4 시가에 BBB 매수 → D5 효력 2:1 분할(D6 → corp-action, applied_after=D4) → 바른 코드 다음 run 0, 돌연변이 **2**(A0·A1 L15 "매수일·매수가가 체결 기록(분할 반영)과 다름"). 40종목·63봉이면 일어날 수 있는 장면 | P5 를 시험으로(실행 수준 + `recheck` L 0). 같은 장면에 L3(분할 전 체결 비교 건너뜀 `>=`)도 같이 묶이게. 지도 2절 L15 "거짓 양성 없음" 칸에 넣기 |
| T-3 | 중요 | `tools/h1_test_guard.py:210-211,238-243` · `tests/test_h1_gaps.py:61,84`(다른 시험 파일의 `guards` 도 같음) | "저장소를 더럽히지 않음" 점검이 `state/`·`results/` 가 **없다가 생겼는지**와 `git status`(무시 파일 안 봄)뿐이다. 맥 운영 체크아웃·H1 worktree 에는 `state/`(start 뒤면 `state/h1/` 진짜 장부)가 이미 있으므로, 시험이 `H1_DIR`(= `state/h1`)에 쓰거나 고쳐도 지킴이도 시험 fixture 도 못 잡는다. 지도 9절은 이 도구를 "단계 7 맥 운영 전 확인 때 다시 돌린다"고 적었는데 그때가 바로 이 상황이다 | 코드 읽기: `before_dirs` 는 존재 여부만, `_git_status` 는 `--ignored` 없음, `.gitignore` 에 `state/`. 이 컨테이너에는 `state/` 가 없어 문제가 드러나지 않음(검토자가 직접 `--ignored` 로 전후를 견줘 이번에는 깨끗함을 확인) | 시작 전후 `state/`(있으면) 아래 파일 목록·크기·sha256 을 견주기, 또는 지킴이가 `git archive` 사본(또는 새 worktree)에서 pytest 를 돌리기(이번 검토가 쓴 방법). 시험 `guards` 도 "있었으면 그 안이 그대로인지"를 보게 |
| T-4 | 경미 | `tools/h1_test_guard.py:39-131,135-139` · 지도 9절 "못 막는 곳" | 막는 곳이 문서보다 좁다. 못 막는 길: ① `python -I`(문서에 있음) ② env 를 새로 준 하위 파이썬 ③ **PYTHONPATH 를 덮어쓴 하위 파이썬 — 새 시험 `test_G2_…`(`tests/test_h1_gaps.py:243`)가 이 모양**이라 지킴이 밖에서 `python h1.py` 를 띄운다(지도는 `-I` 3종만 예외라 함) ④ 같은 프로세스의 `_socket.socket.connect` ⑤ ctypes·C 라이브러리 수준 연결(이 venv 에 curl_cffi·yfinance 가 깔려 있음 — 저장소 코드는 안 씀). 가짜 claude 는 기록 파일을 환경변수 `H1_GUARD_CLAUDELOG` 로 받아서, env 를 새로 준 하위 프로세스가 부르면 **불렸어도 기록이 0** 이다 | 부록 C: 로컬 127.0.0.1 서버로 대조 C0 는 막힘·기록(2번), B1~B5 는 모두 연결됨·기록 0, B6 은 가짜 claude 가 종료 코드 97 로 불렸는데 "claude 호출 0번" | 문서 9절에 ②~⑤ 와 G2 를 적기. 가짜 claude 스크립트에 기록 경로를 글자로 박기. 더 단단히: 리눅스는 `unshare -rn`(네트워크 없는 이름공간)으로 pytest 를 감싸고, 맥은 `sandbox-exec` 로 바깥 연결 금지. G2 는 `PYTHONPATH = fake + os.pathsep + 기존` 으로 |
| T-5 | 경미 | `h1_report.py:1328` vs `h1_report.py:1454` | 창이 다 찼고(S+62 저장) 연장 봉이 **아직 하나도 없을 때** S+63 처리 중 난 L(종료 코드 2)은 status 에는 "연장 구간(S+62 뒤) L 오류 1건" 으로 보이지만, 보고서 `--final` 은 `extension = None` 이라 **그 L 을 어디에도 적지 않는다**. 같은 장면에서 시험 도우미 `same_counts` 도 깨진다(같은 수라는 지도 7절 설명과 다름). 판정에는 안 쓰는 몫이라 결과는 같다 | 확인 시험 P1: `meta.rules.window_bars=5`(S4 시험과 같은 손잡이)로 D0~D4 저장 → D5 의 L 줄·종료 코드 2 줄 → `window_counts.ext_l_errors == 1`, 보고서 글에 "L7"·실행 id 없음, `same_counts` 가 AssertionError | 보고서가 `last == s62` 여도 S+62 뒤 L 이 있으면 연장 절(또는 한 줄 "연장 구간 L N건")을 찍기. `test_S4_…` 에 이 장면 더하기 |
| T-6 | 경미 | `h1.py:3343-3346`(`_print_summary` 뒤 `log.end(EXIT_D7…)`), `h1.py:3306` | 실행 끝 요약은 자기 실행을 빼고 세므로, **종료 코드 7(기준 지수 늦음)로 끝나는 실행의 요약은 "자료 멈춤 0"**, 바로 뒤 status 는 "자료 멈춤 1 (D7 1)". 국내는 KS200 늦은 날이 잦아 운영자가 자주 볼 어긋남이다(종료 코드 4·6 은 요약을 안 찍음) | 확인 시험 P2·P4: `test_T_D_D7` 장면 → 요약 "점검 L 0 · 자료 멈춤 0 · 늦은 봉 1", status "자료 멈춤 1 (D7 1)" | d7 이 있으면 요약 숫자에 이번 실행 몫을 더하거나 "(이번 실행 D7 빼고)" 를 붙이기. 지도 7절에 적기 |
| T-7 | 경미 | `h1_report.py:1454,1457` · `tests/test_h1_gaps.py` S4 | status 의 **늦은 봉 수**와 **팀장 LLM/폴백 수**가 S+62 에서 끊기는지를 지키는 시험이 없다. S4 연장 장면에 S+62 뒤 늦은 봉·팀장 판정 차이가 없어서 `same_counts` 가 가르지 못한다. 늦은 봉은 ②-2 판정 숫자라 status 가 틀리면 운영자가 잘못 읽는다 | 돌연변이 R-lateExt(`_late_dates(c, 마지막 봉)`)·R-leaderExt(`_leader(c, S, 마지막 봉)`) → 둘 다 전체 787 통과 | S4 연장 장면에 S+62 뒤 `late=True` 봉(재커밋)과 연장 봉의 팀장 기록을 넣고 `same_counts` 로 보기 |
| T-8 | 경미 | `tests/test_h1_gaps.py:429-458`(G9) · `h1.py:1054` | G9 이름·지도는 "정리 비용은 **그 봉 날짜** 매도세"를 본다고 하지만 장면의 등록 마지막 거래일(D3)과 정리 봉(D4)이 같은 세율 구간(2026, 0.002)이라 어느 날짜 세율을 써도 같다 | 돌연변이 H-delistTaxDate(정리 세율을 `reg["last_date"]` 로) → 전체 787 통과. 운영에서는 L9 점검이 체결일 세율로 다시 보므로 두 겹 방어는 있음 | 연도 경계 장면(등록 마지막 거래일 2025-12-30·정리 봉 2026-01-02, 세율 0.0015 → 0.0020)으로 바꾸거나 하나 더 |
| T-9 | 경미 | `h1_check.py:304`(L11 하한 `short <= got`), `h1_check.py:338`(L4 신호일 < 체결일), `h1_check.py:769`(check_pair L17 판정 비교) · 지도 2절 "36/36 완전", 10절 #9 | 지도 10절 #9 가 "규칙마다 음성 대조"를 제안했는데, 같은 종류의 빈 곳이 셋 더 있다. 결과는 다른 코드가 같이 잡는다: P7(지수 자금 매도를 덜 팔게 함) 바른 코드 {L8, L9, L11}, 돌연변이 {L8, L9}. L4 신호일 규칙은 L14 "생긴 날 < 체결일"과 겹치고, check_pair 의 판정 비교는 장부 하나 점검(판정 기록과 비교)과 겹친다 | 돌연변이 K-L11lo·K-L4sig·K-L17verdict → 셋 다 전체 통과. P7 | 하한 전용 음성 대조(기록이 서로 맞게 덜 판 장부 → L11)를 더하거나, 지도에 "겹치는 규칙이라 따로 안 봄"을 적기. "완전" 수를 고치기 |
| T-10 | 경미 | `h1.py:3853,3879` | status 안내 줄 "(숫자는 보고서 --final 과 같은 규칙…)" 이 넓게 말한다: `--final` ②-1 은 일지 L 에 **저장 자료로 다시 점검한 L** 을 더하고, 빠진 날·②-3(다른 지문)은 status 에 없다. 머리 "판정 창 n/63" 은 코드 상수 `WINDOW_BARS`, 숫자는 `meta.rules.window_bars` 라 둘이 다르면 한 화면에서 어긋난다(S4 연장 시험 장면이 그 예: 머리 "8/63 남은 55봉", 숫자는 다 찬 5봉 창). 재시작 수(`_count_restarts`)가 보고서 R-7 과 다를 수 있음은 지도 10절 #10 에 이미 있음 | 코드 읽기, S4 장면의 status 글 | 문구를 "일지 숫자(L·멈춤·관문·늦은 봉)는 보고서 --final 과 같은 규칙, 다시 점검·빠진 날·지문은 보고서에서"로 좁히고, 머리도 `meta.rules` 를 쓰기 |
| T-11 | 경미 | `tests/test_h1_gaps.py:250`(G2) | "아무 파일도 안 만듦"을 하위 프로세스의 cwd 에서만 본다. `h1.py` 는 cwd 가 아니라 `<저장소>/state/h1` 에 쓰므로 이 단언은 거의 늘 참이다(지금은 pandas import 에서 먼저 죽어서 문제없음) | 코드 읽기(`H1_DIR = team.STATE_DIR / "h1"`, `STATE_DIR = Path(__file__).parent / "state"`) | 저장소 `state/` 전후 비교로 바꾸기(T-3 과 같이) |
| T-12 | 경미 | `h1.py:2908`(`_window_counts`), `h1.py:3938-3942`(`summary_lines` 의 decisions 만 준 가지) | 운영 코드에서 부르는 곳이 없는 길이다(`_window_counts` 는 시험만, `summary_lines(decisions=…)` 은 아무도). 이 길이 틀려도 시험이 모른다 | grep: 호출처는 `tests/test_h1_gaps.py:119`·`tests/test_h1_report.py:1366` 뿐 | 지우거나 "시험용"으로 적고 하나로 모으기 |
| T-13 | 경미 | `tools/h1_test_guard.py:141-150,153-160` | 결정성: 7번 모두 `LANG=C`(바꾸지 않음 — 그리고 파이썬은 C 로캘에서 UTF-8 모드로 돌아 비 UTF-8 도 아니다), 맥의 실제 로캘(ko_KR.UTF-8)이 없고, 순서는 통째 역순 1번뿐이다. `git status` 는 무시 파일(`*.log`·`error_log.txt`·`__pycache__`)을 안 본다. 예외·시간 초과로 끝나면 임시 폴더(`/tmp/h1-test-guard-*`)가 남는다 | 코드 읽기, `LC_ALL=C python -c 'sys.flags.utf8_mode'` → 1 | 문서에 "LANG 은 고정"으로 적거나 변형 하나 더(`ko_KR.UTF-8`), `--ignored` 비교, `try/finally` 로 임시 폴더 정리 |
| T-14 | 경미 | (시험 없음) 빠진 위험 | 시험이 없는 조합: (a) **국내 23:05 D7(종료 코드 7) → 다음 날 07:40 보조 실행**이 그 봉을 llm·제때로 처리(조각만 `test_T_CAL_국내_22시29분_22시31분`·`test_T_LLMTIME_국내_08시59분…` 에 따로 있음). (b) **늦은 봉 + D7 한 실행**: `test_T_D_D7_…` 이 바로 그 장면인데 `late_bars`·보고서 늦은 봉을 단언하지 않는다(P4 로 동작은 바름 — `late_bars=[D4]`, 보고서 late=[D4], data_kinds={D7:1}). (c) **재시작 뒤 판정 기록 재사용**은 같은 S(G3)만 — 옛 창이 늦게 처리해 `late_no_llm` 으로 남긴 열쇠를 새 창 S 가 다시 쓰는 경우(⑧ 폴백 셈에 들어감) 없음. 미국 07:10 + 08:40 은 `test_T_F7_…`(08:00 두 번째 run)이 덮음 | 코드·시험 읽기, P4 | (a)(b)를 실행 수준 시험 하나로(23:05 → 7, 07:40 → 0·mode llm·late False, status·보고서 숫자). (c)는 설계상 의도인지 §2.2 ⑤ 에 한 줄 |

---

## 부록 A. 검토자 돌연변이 25개 (전체 pytest `-x`, scratch)

| ID | 규칙 | 틀리게 바꾼 것 | 결과 | 처음 잡은 시험 |
|---|---|---|---|---|
| K-L11lo | L11 지수 자금 매도 | 하한 `short <= got` 지움 | **살아남음** | — (T-9) |
| K-L12A1 | L12 A1 여유 | A1 도 `need > avail` | 잡힘 | `test_h1_check::test_B6_경계_보류_need_약_avail_1빼기_1e9[5e-10-True]` |
| K-L15split | L15 분할 반영 매수가 | `applied_after >= 매수일` → `>` | **살아남음** | — (T-2) |
| K-L22env | L22 | env 무시(code_hash 만) | 잡힘 | `test_h1_check::test_음성_대조_L22_코드_환경_종목군` |
| K-L23pair | L23 짝 점검 | 두 장부 등록 비교 끔 | 잡힘 | `test_h1_check::test_B1_두_장부의_등록이_다르면_짝_점검_L23` |
| K-L4sig | L4 신호일 < 체결일 | 끔 | **살아남음** | — (T-9, L14 와 겹침) |
| K-L17verdict | check_pair L17 | 판정 비교 끔(열쇠만) | **살아남음** | — (T-9, 장부 하나 점검과 겹침) |
| K-L18prefix | L18 HEAD 앞부분 sha | 줄 수만 봄 | 잡힘 | `test_h1_check::test_음성_대조_L18_판정_기록` |
| H-D3close | D3 이상한 종가 | 끔 | 잡힘 | `test_h1_review2b2::test_C13_…[0.0]` |
| H-D6days | D6 비교 날 수 | 최근 5일 → 1일 | 잡힘 | `test_h1_gaps::test_G13_…` |
| H-D7plus1m | D7 확정 시각 | +1분 | 잡힘 | `test_h1_gaps::test_G8_KS200_확정_시각_22시30분_정각` |
| H-D5half | D5 절반 | `>=` → `>` | 잡힘 | `test_h1_review2b2::test_C17_D5_종목군_정확히_절반이…` |
| H-D2delist | D2 상장폐지 제외 | 등록 종목도 받기 대상 | 잡힘 | `test_h1_gaps::test_G9_…` |
| H-HEADrestore | HEAD 복구 | 백업이 HEAD 와 맞는지 안 봄 | **살아남음** | — (T-1) |
| H-backupAfter | 커밋 순서 | 백업을 장부 6개 쓴 **뒤**에 | 잡힘 | `test_h1_review2b2::test_C1_디스크_가득은_ENV_4…` |
| H-L24mid | L24 판정 기록 가운데 줄 | 깨진 줄 건너뜀 | 잡힘 | `test_h1_engine::test_T_JSONL_중간_줄_깨짐_중복_열쇠` |
| H-fpA | ④ (가) | 지문 비교 없이 통과 줄만 | 잡힘 | `test_h1_gaps::test_S3_거짓_양성_조건이_틀리면_status_도_L_1[가]` |
| H-fpB | ④ (나) | 내용 지문 비교 끔 | 잡힘 | `test_h1_gaps::test_S3_…[나]` |
| H-delistTaxDate | ⑦-4 정리 세율 날짜 | 정리 봉 → 등록 마지막 거래일 | **살아남음** | — (T-8) |
| H-restartCap | ⑤ 재시작 상한 | `>=` → `>` | 잡힘 | `test_h1_runner::test_T_NEWSTART_재시작_상한` |
| R-lateExt | status 늦은 봉 경계 | S+62 대신 마지막 봉까지 | **살아남음** | — (T-7) |
| R-leaderExt | status 팀장 수 경계 | S+62 대신 마지막 봉까지 | **살아남음** | — (T-7) |
| R-preRuns | 창 세기(같은 시각) | 창 만든 start 전 실행 빼기 끔 | 잡힘 | `test_h1_gaps::test_S4_실패한_start_뒤…[True]` |
| R-market | ① 시장별 | 일지 줄의 시장 확인 끔 | 잡힘 | `test_h1_gaps::test_G12_…` |
| R-fb20 | ⑧ 20% | `>` → `>=` | 잡힘 | `test_h1_report::test_T_F8a_폴백_20퍼센트_경계[1-5-False]` |

살아남은 8개 중 K-L4sig·K-L17verdict 는 다른 규칙과 겹치는 사실상 같은 동작이고, K-L11lo 는 다른 L 이 결과를 잡는다. T-1·T-2 는 겹치는 방어가 없다.

## 부록 B. 확인 시험 (scratch `review3/probe/tests/test_review3_probe.py`, 저장소에 넣지 않음)

| # | 장면 | 결과 |
|---|---|---|
| P1 | 창 다 참(S+62 저장)·연장 봉 없음 → S+63 L | status `ext_l_errors=1`, 보고서 `extension=None`·글에 흔적 없음, `same_counts` 깨짐 (T-5) |
| P2 | `test_T_D_D7` 장면 | 요약 "자료 멈춤 0", status "자료 멈춤 1 (D7 1)" (T-6) |
| P3 | G2 소스 | PYTHONPATH 덮어씀·cwd 만 봄 (T-4·T-11) |
| P4 | 늦은 봉 + D7 한 실행 | `late_bars=[D4]`, 보고서 late=[D4]·data_kinds={D7:1} — 동작은 바름 (T-14) |
| P5 | D4 시가 매수 → D5 효력 분할 | 바른 코드 0, K-L15split 돌연변이 2(L15) (T-2) |
| P6 | 3개 바꾼 뒤 멈춤 + 백업 한 글자 다름 | 바른 코드 2(L24), H-HEADrestore 돌연변이 0 (T-1) |
| P7 | 지수 자금 매도 수량만 줄임 | 바른 코드 {L8, L9, L11}, K-L11lo 돌연변이 {L8, L9} (T-9) |

## 부록 C. 지킴이 우회 확인 (scratch `review3/gcopy/tests/test_zz_bypass.py` 를 `h1_test_guard.py --quick` 로)

| # | 길 | 결과 |
|---|---|---|
| C0 | 같은 프로세스 `socket.create_connection` (대조) | 막힘·기록됨("인터넷 시도 2번") |
| B1 | `python -I -c …` 하위 프로세스 | 연결됨·기록 없음 |
| B2 | env 를 새로 준 하위 파이썬 | 연결됨·기록 없음 |
| B3 | `{**os.environ, "PYTHONPATH": …}` 하위 파이썬(G2 모양) | 연결됨·기록 없음 |
| B4 | `_socket.socket().connect` | 연결됨·기록 없음 |
| B5 | ctypes libc `connect` | 연결됨·기록 없음 |
| B6 | `H1_GUARD_CLAUDELOG` 없는 env 로 가짜 claude | 종료 코드 97 로 불림, "claude 호출 0번" |

---

## 그대로 둬도 되는 것

- **보고서 출력 불변**: `_ops` 에서 `_journal_counts`·`_late_dates`·`_ext_l_errors` 를 떼고 `_load` 가 `_context` 를 쓰게 한 변경은 29개 보고서(최종·달마다, 9개 장면)에서 a161e1c 와 바이트까지 같다.
- **늦은 import**: h1_report 는 모듈을 읽을 때 h1 을 import 하고, h1 은 `window_counts` 안에서만 h1_report 를 import 한다 → 순환 없음. `python h1.py status` 로 돌 때도 `__main__` 이 `import h1` 한 모듈에서 명령을 돌리므로 h1_report 가 같은 h1 을 본다(CLI 로 직접 확인). h1_report 는 이미 `CODE_FILES` 에 있어 code_hash·관문에 새 영향이 없다. `window_counts` 는 잠금을 다시 잡지 않아 run·start 의 잠금 안에서 불려도 교착이 없다.
- **같은 함수로 세기**: L 오류(errors.jsonl ∪ 종료 코드 2, run_id 로 한 번)·④ 거짓 양성 따로·종료 코드 2 만·자료 멈춤과 종류·관문 거절·밀린 봉 초과·잠금 초과·끝 기록 없는 실행·창 밖 기록은 status·요약·보고서 `--final` 이 같은 `_journal_counts` 로 센다. S1~S4·G12 가 숫자와 status 글자를 함께 보고, 돌연변이 R-preRuns·R-market·H-fpA·H-fpB 를 gaps 시험이 잡는다.
- **판정 기록이 깨졌을 때 status 가 죽지 않고 알림**(G4) — 옛 status 는 예외로 끝났다.
- **④ 자동 판단**: (가)(나) 각각을 지우면 S3[가]·S3[나](그리고 R4)가 잡는다.
- **새 시험 34건의 질**: 모두 실패할 수 있다(작성자 M27·M31~M41, 검토자 H-D2delist·H-D6days·H-D7plus1m·R-preRuns·R-market·H-fpA·H-fpB 를 gaps 시험이 먼저 잡음). G5~G7 은 `got == {코드}` 로 다른 코드가 섞이지 않음까지 본다. 고정 시각(FakeSource·`clock`)·`tmp_path`·`MonkeyPatch.context`/`monkeypatch` 되돌림이 바르고, 모듈 범위 장면(`scenes`)은 JSON 사본만 고친다. 기존 시험 파일·골든은 한 줄도 바뀌지 않았다(`git diff --stat a161e1c 9039f3b -- tests/`).
- **지도 이름**: 지도의 시험 참조 382개가 모두 실제 시험이다. 검토자가 읽어 본 "완전" 항목(30개 넘게: ②-1·②-2·②-3 판정 시험 전부, R1~R4, `C[L1…L23]` 33건과 L16·L18·L22·L24, T-HEAD 4·T-STRICT·T-NEWSTART 3·T-F7·T-JSONL 3·T-LATE·T-LLMTIME·T-CAL 3·T-CUT·T-DST·T-D D7·C17 늦은 봉 5/6·final 늦은 봉 10/11)은 이름만 비슷한 약한 단언이 아니라 실제로 그 규칙을 단언한다. 약한 곳은 위 T-1·T-2·T-7·T-8·T-9 뿐이다.
- **이번 달 월간 ≠ status**: 이번 달 월간은 "어느 달인지 모르는 줄"을 따로 세므로 status 와 다를 수 있다 — 설계 §10.2e R-5 대로.
- **재시작 수 출처 차이**(status `_count_restarts` vs 보고서 R-7 세 출처 최댓값) — 지도 10절 #10 에 이미 적혀 있고 최종 판정은 보고서가 잡는다.
- **지킴이의 보통 길**: 같은 프로세스·`-I` 없이 띄운 파이썬의 `socket`·`urllib` 연결은 막고 기록하며, 원래 sitecustomize(이 컨테이너 `/usr/local/lib/python3.13/sitecustomize.py`)를 이어서 부른다. 저장소에는 아무것도 쓰지 않는다(무시 파일 포함 `git status` 전후 같음). 맥에서 막힐 코드(경로·`/tmp` 심볼릭 링크·fork)는 읽어서는 찾지 못했다(맥에서 직접 돌려 보지는 못함).
