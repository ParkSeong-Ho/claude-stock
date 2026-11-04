# H1 단계 2a 독립 코드 검토 — `paper_wallet`·`analyst`·`screener` + 골든

## 머리말

- **검토일**: 2026-11-04.
- **검토자**: 이 코드를 쓰지 않았고, 작성자 설명도 받지 않았다. 코드와 설계 문서만 보고 판단했다.
- **고친 것**: 저장소 코드·시험·문서는 고치지 않았다. 이 파일 하나만 새로 썼다.
- **대상**
  - `h1-forward` 6b1e5b6. 범위는 `git diff 7308529 6b1e5b6` 이다.
  - 바뀐 파일은 `paper_wallet.py`·`analyst.py`·`screener.py`·`.gitattributes` 이다.
  - 새 파일은 `tests/golden_scenarios.py`·`tests/golden/`·`tests/test_h1_golden.py`·`tests/test_h1_modules.py` 이다.
- **기준**: `docs/h1-forward-design.md` 3판의 다음 부분이다.
  - §3.1, §3.4.
  - §6 의 T-GOLD·T-PW·T-AN·T-F5c·T-F5d·T-SCR·T-A1-7·T-RSI.
  - §7 의 R4·R13·R20.
- **환경**: Linux x86_64, Python 3.13.18, pandas 3.1.0, numpy 2.5.4, ta 0.11.0.
- **직접 돌려 본 것**: 스크립트와 결과 요약(`outputs.txt`)은 scratch `review2a/` 에 있다. 확인용 worktree 둘은 끝나고 지웠고, 그 뒤 `git status` 는 깨끗하다.
  1. **전체 시험**: 저장소 작업 폴더에서 `pytest -q` 를 돌렸다. **365 passed** 다(306개 + 새 시험 59개).
  2. **골든 다시 만들기**
     - 847ad13 을 worktree 로 꺼냈다.
     - 지금 `tests/golden_scenarios.py`(sha256 `7ed68425…a167574`, README 와 같음)를 넣고 `--write` 로 돌렸다.
     - 결과는 "가지 확인 통과", 파일 151개다.
     - `diff -r` 로 비교하면 저장소 작업 폴더의 `tests/golden/us`·`kr` 와 **바이트까지 같다**.
  3. **깨끗한 checkout**: 6b1e5b6 을 새 worktree 로 꺼내 새 시험 두 파일을 돌렸다. **2 failed, 57 passed** 다(→ A-1).
  4. **결정성**
     - `PYTHONHASHSEED` 를 0·1·777·random 으로 바꿔 돌렸다.
     - `TZ=America/New_York` 과 `TZ=Asia/Seoul LANG=C` 로도 돌렸다.
     - 골든·모듈 시험이 모두 통과한다.
  5. **옛 `scan` 과 새 `scan` 의 차등 비교** (`diff_scan.py`)
     - 847ad13 의 `screener.py` 를 다른 이름으로 읽어, 지금 것과 같은 가짜 시세로 무작위 장면 150개를 돌렸다.
     - 장면에는 중복 코드, 받기 실패(예외 5종), 빈 자료, 짧은 이력, 오래된 봉, 0종목이 들어 있다.
     - **다른 결과 0개**, 후보는 합계 114개다.
  6. **골든이 지나는 줄·가지 측정** (`linecov.py`·`arccov.py`·`arcs2.py`·`slots.py`)
     - `settrace` 로 측정했다.
     - 대상은 `team.run_trainer`·`team.run`·`screener.scan_frames`·`scan` 이다.
  7. **돌연변이**
     - 6b1e5b6 worktree 에서만 하나씩 바꾸고 원래대로 되돌렸다.
     - `mutate.py`: 2a 코드 27개.
     - `mutate_team.py`: 다음 단계가 건드릴 team.py ①② 7개.
  8. **진짜 `subprocess` 로 `analyze_logged`** (`real_sub.py`)
     - PATH 앞에 가짜 `claude` 셸 스크립트(`fakebin/claude`)를 두었다.
     - 확인한 경우: 정상, 시간 초과, 0 아닌 종료, JSON 없음, `--version` 실패·느림, UTF-8 아닌 출력.
  9. **`.gitignore` 고침안 확인**
     - 버려도 되는 git 저장소를 하나 만들어 `state/` 다음 줄에 `!tests/golden/**/state/` 를 넣어 봤다.
     - 골든 state 는 추적되고, 루트 `state/` 는 계속 무시된다.

## 요약

**운영 동작(`h1=None`)은 코드상 보존됐다.**
- `screener.scan()`
  - 판단부를 `scan_frames` 로 글자 그대로 옮겼다.
  - 순서·`used` 세기·`latest`(가장 최근 봉 기준 오래된 봉 제외)·`except Exception`·후보 dict 값이 같다.
  - 골든 재생성과 차등 비교 150회 모두 차이 0 이다.
- `paper_wallet.sell(tax_rate=None)` 은 `proceeds * self.sell_tax_rate` 와 같은 식·같은 계산 순서다.
- `analyst._build_prompt`·`analyze`·`apply`, 그리고 `team.py`·`main.py` 는 한 글자도 바뀌지 않았다.

**그러나 골든의 핵심 절반이 커밋에 없다(A-1, 치명).**
- 상태 JSON 89개(151개 중)가 `.gitignore` 의 `state/` 에 걸려 커밋되지 않았다.
- 그래서 이 컴퓨터 작업 폴더에서만 시험이 통과한다.
- 맥 H1 worktree 나 새 checkout 에서는 골든 시험이 늘 실패한다.
- R13 의 유일한 방어인 "장부 바이트가 같다" 는 증거가 버전 관리 밖에 있다.

**골든 장면 자체는 믿을 만하다.**
- 바꿔 끼운 곳은 입출력 경계뿐이다: FDR 모듈, `shutil.which`·`subprocess.run`, `STATE_DIR`·`RESULTS_DIR`, `main.datetime`, API 키.
- 진짜 `team.run`·`screener.scan`·`analyst.analyze`·`main.load_prices`·`confirmed_bars` 가 돈다.
- 결정적이다.
- 설계 T-GOLD ①~⑧ 을 모두 지난다. 팀장 답 12종이 두 시장 모두에서 실제 효과(주문·hold·확신도 보류·빠짐)로 나타나고, 빈자리 초과(kept 2 > slots 1)도 지난다.
- `scan_frames`·`scan` 은 asof 경로와 "스캔 0종목" 말고는 모든 줄을 지난다.

**다음 단계에 걸리는 빈틈(A-2, 중요)**: 단계 3 의 G1·G2 가 손댈 team.py ①② 의 몇몇 가지를 골든이 지나지 않는다.
- 해당 가지: 시세 받기 실패, 시가 없음, 버려지는 주문, 대기 중 보유, 벤치마크 실패.
- 일부러 틀리게 바꾼 5개를 **전체 365개 시험이 하나도 못 잡았다**.

**새 함수는 설계대로 맞다.**
- `normalize_verdict`, `analyze_logged`(상태 7종·시간대 있는 시각·API 키 제거·`--version` 실패 무관), `scan_frames(asof, min_bars, brains)`, 소수 단위 JSON 왕복(`float.hex` 같음, 정수는 int) 모두 맞다.
- 시험은 돌연변이 27개 중 22개를 잡는다.
- 못 잡은 5개(예외 범위, 가격 반올림, 시각·걸린 시간 뜻)와 asof 형식 문제는 경미하다.

## 발견

| ID | 심각도 | 파일:행 | 문제 | 근거(재현 방법·숫자) | 고칠 것 |
|---|---|---|---|---|---|
| **A-1** | **치명** | `.gitignore:13` (`state/`), `tests/golden/README.md:16`, `tests/test_h1_golden.py:62-65` | **골든 상태 파일 89개가 커밋되지 않았다.** `.gitignore` 의 `state/` 는 어느 깊이의 `state` 폴더든 무시하므로 `tests/golden/<시장>/<장면>/state/team_*.json` 이 전부 빠졌다. 커밋 6b1e5b6 에는 `stdout.txt`·`step.json` 62개와 README 만 있다. 무시된 파일이라 `git status` 도 깨끗하게 보여 알아채기 어렵다. 결과: ① 맥 H1 전용 worktree·다른 세션·새 clone 에서 `test_골든과_바이트까지_같다[us/kr]` 가 늘 실패한다 ② 단계 3 의 R13 방어가 이 컴퓨터 밖에서는 없다 ③ "실패하니 지금 코드로 다시 만들자" 는 자기 비교 유혹이 생긴다 ④ 가장 중요한 증거(장부 바이트)가 버전 관리 밖에 있다 | `git ls-files tests/golden \| wc -l` → 63. 작업 폴더 `find` 로 세면 152, 이 중 `state/` 아래가 89. `git check-ignore -v tests/golden/us/01-first-0921/state/team_마라토너.json` → `.gitignore:13:state/`. 6b1e5b6 을 새 worktree 로 꺼내 `pytest tests/test_h1_golden.py tests/test_h1_modules.py` → **2 failed, 57 passed**. 실패 내용은 "골든에 없는 새 파일: us/01-first-0921/state/team_마라토너.json …"이다. README 는 "151개"라고 적었다. 지금 있는 시험 `test_골든_폴더가_있다` 는 폴더가 있는지만 봐서 이것을 못 잡는다 | ① `.gitignore` 의 `state/` 다음 줄에 `!tests/golden/**/state/` 를 넣는다. 버린 저장소에서 확인했다: 골든 state 는 추적되고 루트 `state/` 는 계속 무시된다 ② `git add tests/golden` 후 `git ls-files tests/golden \| wc -l` 이 152 인지 본다 ③ **새 worktree 에서** 전체 시험 통과를 확인한다 ④ `test_골든_폴더가_있다` 에 두 가지를 단언한다: 파일 수 == 151(README 와 같은 숫자), 그리고 저장이 있는 장면마다 `state/` 파일이 있는지 ⑤ 앞으로 시험 자료 폴더 이름에 `state`·`results` 를 쓸 때는 같은 예외를 둔다 |
| **A-2** | **중요** | `team.py` 160·165·185(거짓 쪽)·187·200·204·214·322-327 (847ad13 과 같은 줄), `tests/golden_scenarios.py` 장면 목록 | **골든이 run_trainer ①② 와 run 의 일부 가지를 한 번도 지나지 않는다.** 단계 3 의 G1 은 ① 전체를 `else:` 아래로 들여쓰고, G2 는 ② 뒤에 붙는다. 바로 이 코드가 다음 단계에서 바뀐다. 지나지 않는 가지: ① 대기 주문 종목의 시세 받기 실패(160 거짓) ② 확정 행인데 시가 없음 → 다음 봉(165 거짓) ③ 보유 중 종목의 매수 주문·보유 없는 매도 주문을 조용히 버림(185 거짓) ④ `sell` 실패(187 거짓) ⑤ 보유 종목 시세 받기 실패(200) ⑥ 기준 봉 이하 자료 없음(204) ⑦ 대기 주문이 있는 보유 종목(214) ⑧ 벤치마크 받기 실패 → 후보 날짜를 기준 봉으로(322-327) | `arcs2.py` 로 줄별 실행 횟수를 셌다: 201·205·215·323-327 은 0번이고, 165·185·187 은 한쪽만 지났다. `mutate_team.py` 로 다음을 넣어 봤다(6b1e5b6 worktree, 되돌림): T2(버리던 주문을 대기에 남김), T3(214 의 `continue` 삭제), T4(보유 종목 시세 실패에서 예외), T5(시세 실패한 대기 주문을 버림), T6(벤치마크 실패 시 `max`→`min`). 골든 6개가 통과했고, **전체 365개도 통과**했다. T1(시가 None 검사 삭제)은 기존 시험이 잡았다. 대조로 넣은 T7(체결 로그의 팀장 메모 삭제)은 골든이 잡았다 | team.py 를 고치기 **전에** 장면을 더하고 847ad13 worktree 에서 골든을 다시 만든다(README 규칙대로). 더할 장면: ① `World` 에 날짜별 받기 실패를 두어, 보유 종목·대기 주문 종목·벤치마크가 하루씩 실패하게 한다 ② 미국 확정 행 하나를 Open=NaN 으로 둔다(→165, 그리고 다음 날 214) ③ 185 거짓은 정상 흐름에서는 생기기 어렵다. 그래서 상태 dict 를 손으로 넣고 `run_trainer(h1=None)` 을 직접 부르는 작은 골든 장면으로 덮는다. A-1 을 먼저 고친다 |
| **A-3** | 경미 | `tests/test_h1_modules.py:362-371` | `test_T_SCR_세는_종목과_후보_모양` 의 후보 단언은 **한 번도 돌지 않는다**. 키 집합, price 2자리·rsi 1자리, 오래된 봉 T 제외, date 를 보는 단언이다. 2026-11-03 전체 시세로는 후보가 0개라 `for c in cs` 가 비어 있다 | `scan_frames(_frames(), ORDER)` → 세 트레이너 모두 `[]`. 돌연변이 S8(`round(Close, 2)`→`3`)이 골든과 모듈 시험 59개를 모두 통과했다. 골든 합성 가격은 이미 센트·원 단위라 반올림 자리가 바뀌어도 값이 같다 | 후보가 있는 asof(ASOFS 중 하나)로 바꾸고 `assert sum(len(cs) for cs in found.values()) > 0` 을 더한다. 모듈 시험의 합성 가격은 소수 셋째 자리 이상이 있어 S8 이 잡힌다 |
| **A-4** | 경미 | `screener.py:103-107`, `tests/test_h1_modules.py:409-` | `scan()` 이 받기 실패를 `except Exception` 으로 넘기는 것(예전과 같음, 코드는 맞음)을 지키는 시험이 `ConnectionError` 하나뿐이다. `load_prices` 의 실제 실패 몇 가지는 덮이지 않는다: `ValueError` 인 "데이터를 가져오지 못했어요"·"확정된 봉이 하나도 없어요"·국내 코드 아님 | 돌연변이 S7(`except ConnectionError:` 로 좁힘)이 골든·모듈 시험을 통과했다. 지금 코드는 맞다: 차등 비교에서 ValueError·KeyError·RuntimeError·OSError·ConnectionError 모두 옛 코드와 같았다 | `fake_load` 에 `ValueError` 를 던지는 종목 하나를 더한다 |
| **A-5** | 경미 | `analyst.py:160`·`171-172`, `tests/test_h1_modules.py` T-AN | meta 의 `asked_at`("물은 시각")·`elapsed_s`("`claude -p` 만 걸린 시간") **뜻**을 지키는 시험이 없다. 지금 시험은 "float 이고 ≥ 0", "시간대가 있다"만 본다 | 다음 돌연변이가 모두 통과했다: A5(`elapsed_s` 를 늘 0.0), A6(`elapsed_s` 에 `--version` 시간 포함), A7(`asked_at` 을 답을 받은 뒤 시각으로) | 가짜 `run` 이 가짜 monotonic 시계를 움직이게 하고 세 가지를 단언한다: `elapsed_s` == 가짜로 걸린 시간, `--version` 시간은 빠짐, `asked_at` ≤ 호출 시작. A-9 의 주입점이 있으면 쉽다 |
| **A-6** | 경미 | `analyst.py:162-170`·`185`, 설계 §3.4·§6 T-AN | ① `subprocess.run(text=True)` 의 출력 디코드 실패(`UnicodeDecodeError`, ValueError 하위)를 `analyze`·`analyze_logged` 둘 다 잡지 않는다. 그래서 H1 실행이 폴백·상태 기록 없이 멈춘다. ② `analyze_logged` 는 `{"analysis": 3}` 같은 TypeError 를 이미 `bad_json` 폴백으로 바꿨다. 이 차이는 정당하다(운영 `analyze` 라면 team.run 이 죽는 입력이다). 그러나 설계에는 "`analyze` 결과 == `analyze_logged(...)[0]`" 만 있고 이 예외 차이가 적혀 있지 않다 | `real_sub.py`: 가짜 claude 가 `\xff\xfe …` 를 내면 analyze·analyze_logged 둘 다 `UnicodeDecodeError` 를 낸다. `{"analysis": 3}` 은 analyze 에서는 TypeError, analyze_logged 에서는 `bad_json` 이다(시험 있음). 맥 launchd 의 C 로캘도 파이썬이 UTF-8 로 바꾸므로 실제로 일어날 가능성은 낮다 | 둘 중 하나를 고른다: `analyze_logged` 에서 `ValueError` 도 `bad_json` 으로 기록하거나, h1 `Leader` 가 analyze_logged 의 예외를 폴백 상태로 기록한다. 그리고 설계 §3.4·T-AN 에 "analyze 가 예외를 내는 입력에서는 analyze_logged 가 폴백한다" 를 적는다. 재현은 LLM 을 부르지 않으므로 영향이 없다 |
| **A-7** | 경미 | `tests/golden_scenarios.py:59-62` | "다른 폴더의 모듈을 읽으면 멈춤" 검사가 `main`·`team`·`screener`·`analyst` 넷만 본다. 2a 에서 바뀐 **`paper_wallet`** 은 보지 않고, `markets`·`risk_guard`·브레인 3개도 보지 않는다 | 코드를 읽어 확인했다. 새 프로세스에서는 `sys.path[0]=ROOT` 라 지금은 문제가 없다. 하지만 한 프로세스가 두 트리를 읽는 하네스에서는 미리 읽힌 다른 폴더 `paper_wallet` 이 조용히 섞일 수 있다(단계 5 재현이 그런 모양이다) | 목록을 team.py 가 import 하는 모듈 전부로 늘린다: `paper_wallet`·`markets`·`risk_guard`·`sprinter_brain`·`marathoner_brain`·`pioneer_brain` |
| **A-8** | 경미 | `screener.py:70-74` | ① `asof` 를 글자로 비교하므로 'YYYY-MM-DD' 가 아닌 값이 오면 **조용히 미래 봉을 본다**. ② `frames` 의 값이 `None` 이면 `TypeError` 가 난다. `team._prices` 캐시는 받기 실패를 `None` 으로 담으므로, h1 이 비슷한 캐시를 그대로 넘기면 깨진다 | `asof="2026-10-7"` → 10-30 봉 신호 5개가 후보로 나온다. 같은 날을 `asof="2026-10-07"` 로 주면 0개다. `scan_frames({"A": None}, ["A"])` → `TypeError` | 함수 머리에서 `date.fromisoformat(asof).isoformat() == asof` 를 확인하고, 아니면 `ValueError` 를 낸다. `None` 값은 받기 실패와 같이 건너뛸지, 명시적으로 막을지 정해 docstring 에 적는다. 운영 `scan()` 은 `None` 을 넣지 않으므로 어느 쪽이든 골든은 그대로다 |
| **A-9** | 경미 (다음 단계) | `analyst.py:123-133`·`160`·`171-172` | ① `analyze_logged` 가 부를 때마다 `claude --version` 을 따로 실행한다(최대 20초). 그래서 단계 3 의 시험(T-F5b 호출 횟수 셈 등)과 가짜 claude 가 `--version` 호출을 따로 걸러야 한다. `golden_scenarios.FakeClaude` 는 `--version` 을 프롬프트 호출로 기록한다. ② `asked_at`·`elapsed_s` 가 analyst 모듈의 `datetime`·`time` 에 묶여 있다. h1 시험(T-HEAD "끊기지 않은 실행과 같음", T-LLMTIME)을 결정적으로 만들려면 이것을 바꿔 끼워야 한다. `time` 은 전역 모듈이라 바꿔 끼우면 다른 곳까지 바뀐다 | 코드와 설계 §3.3 `Leader`·§6 을 대조했다. 한 봉에 트레이너 3명 × A0/A1 이 부르므로 `--version` 은 최대 6번이다 | 버전은 프로세스당 한 번만 구한다(모듈 캐시, 또는 h1 이 한 번 구해 넘김). `analyze_logged(..., now=None, clock=None)` 같은 주입점을 둔다. 기본값이면 지금과 같다 |
| **A-10** | 경미 | `tests/test_h1_modules.py:3-12` (머리말) | 설계 ID 몇 개는 2a 에서 일부만 했는데, 머리말은 다 한 것처럼 적었다(T-A1-7 만 "지갑 부분"이라고 밝힘). 남은 부분: T-F5c 의 "답에서 빠진 종목 → `missing_in_reply`, 규칙 폴백 동작", T-F5d 의 "H1 에서 veto·hold 로 동작", T-A1-7 의 "화면 6자리" | 설계 §6 표와 대조했다 | 머리말에 "(analyst 부분)" 을 붙이고, 단계 3 할 일에 남은 부분을 적는다 |
| **A-11** | 경미 | `tests/golden/README.md:17`, `requirements.txt` | 골든 바이트는 numpy(`Generator.integers` 흐름)·pandas·ta 의 버전과 CPU 에 기댄다. 그런데 `requirements.txt` 는 하한만 적었다. 맥(ARM·전용 venv)에서 버전이 다르면 운영 동작이 같아도 골든이 깨질 수 있다(거짓 경보). 그러면 A-1 과 같은 "다시 만들기" 유혹이 생긴다 | README 의 환경 표(pandas 3.1.0·numpy 2.5.4·ta 0.11.0)와 `requirements.txt` 하한을 비교했다. 리눅스 x86_64 에서만 확인했다 | 골든 실패 메시지에 지금 버전과 README 버전을 같이 찍고, 다르면 "환경 차이부터 확인"이라고 알린다. 맥 H1 venv 를 README 버전으로 고정하고(§8.1), 맥에서 골든 통과를 확인하는 일을 단계 7 체크리스트에 넣는다 |

## 그대로 둬도 되는 것

**골든이 감싼 경계는 좁고, 되돌리기는 확실하다.**
- `patched()` 는 `finally` 에서 7가지를 되돌린다: `sys.modules["FinanceDataReader"]`(없던 경우 pop), `team.STATE_DIR`, `main.RESULTS_DIR`, `main.datetime`, `shutil.which`, `subprocess.run`, `ANTHROPIC_API_KEY`.
- 모듈 시험은 모두 `monkeypatch` 를 쓴다.
- 전체 시험 뒤 저장소에 `state/`·`results/` 가 생기지 않는다.

**`screener.universe` 의 `random.seed(7)`** 이 전역 난수 상태를 바꾸는 것은 운영 코드의 원래 동작이다.

**`scan()` 은 이제 먼저 다 받고 나서 판단한다(예전에는 하나씩 번갈아).**
- `confirmed_bars(now=None)` 이 받을 때마다 시계를 보므로, 실행이 확정 시각(16:15 ET·16:00 KST)을 가로지르는 순간에만 이론상 차이가 난다.
- 운영 실행 시각(07:10·23:05 KST)에서는 생기지 않는다.
- 메모리도 50종목 시세라 문제없다.

**중복 종목 코드**
- 같은 코드가 universe 에 두 번 있고, 첫 받기는 실패하고 둘째는 성공하는 경우에만 옛 코드(1번 판단)와 새 코드(2번 판단)가 다르다.
- `KR_UNIVERSE` 32개는 중복이 없고, S&P 목록도 실제로는 중복이 없다.
- 무작위 차등 150회(중복 포함)에서 차이 0 이었다.

**`analyze_logged` 와 `analyze` 의 차이는 정당하다.**
- `analysis` 가 목록이 아닐 때 analyze_logged 는 `bad_json` 폴백, analyze 는 TypeError 다.
- analyze 가 죽는 입력을 H1 이 폴백으로 기록하는 것이므로 맞다. 문서화만 하면 된다(A-6).
- 그 밖의 결과는 모두 같다: 정상, 빈 analysis, 문자열 항목, code 없는 항목, `" VETO"` 원래 글자 그대로.
- 진짜 subprocess 로 확인한 것
  - API 키가 빠진다(가짜 claude 가 키를 보면 종료 9 → 실제로는 `ok`).
  - 시간 초과면 `timeout`·`elapsed≈1.0s` 이고, 0 아닌 종료면 `returncode=2`.
  - `--version` 이 실패·느림이어도 판정은 같고 `cli_version=None` 이다.

**`_cli_version` 을 시간 초과·OSError 뒤에도 부르는 것**: 최대 20초 늘어날 뿐이다. LLM 시각 규칙은 h1 `Leader` 가 호출 직전에 따로 본다(R2-14).

**`normalize_verdict`**: 앞뒤 공백 제거·소문자만 하고 그 밖은 `None` 이다. 설계 그대로다. `str.strip()` 은 전각 공백도 지운다.

**`paper_wallet`**
- `Holding.shares: float` 는 표기만 바꾼 것이다. 실행 시 변환이 없어 운영과 같다.
- JSON 은 `repr` 왕복이라 `float.hex` 가 같고, 정수 주식은 int 로 돌아온다. `team._save`→`_load` 경로까지 시험한다(R4·R20).
- `buy`·`sell` 의 `shares: int` 표기가 남은 것은 겉모양뿐이다.
- 소수 단위 전부를 팔 때는 가진 값과 **같은 float** 를 넘겨야 보유가 지워진다. 계산한 단위로 팔면 먼지가 남거나 `False` 가 된다. 이것은 h1 쪽 책임(§2.3 d·L11)이고 이 단계의 결함이 아니다.

**T-RSI**
- 합성 시세(2015~)로 `team.START` 부터 계산한 지표와 처음부터 계산한 지표를 2026-06 이후에서 비교한다.
- 대상은 RSI 와 브레인 세 개의 모든 칸이고, 차이 < 1e-9 다.

**T-SCR 의 asof 동등성 시험(69개 asof, 후보 73개)**
- 판단 앞에서 자르는 것을 잘 지킨다.
- 돌연변이 S5(`<=`→`<`)와 S9(자르기 삭제 = 미리보기)를 잡는다.
- `brains=None` 은 부를 때의 `screener.BRAINS` 를 쓴다. 재현 W3 가 바꿔 끼울 수 있다.

**`.gitattributes`(`tests/golden/** -text`)·NFC 파일 이름 정규화**: 맥에서도 바이트 비교가 흔들리지 않게 한 것으로 맞다.

## 돌연변이 결과 (참고)

`mutate.py` 로 2a 코드를 바꿔 본 결과, 27개 중 22개가 잡혔다.

**잡힌 것**
- 스크리너
  - S1 `min_bars` `<`→`<=`
  - S2 오래된 봉 제외 끔
  - S3 받기 실패도 셈
  - S4 latest 를 가장 오래된 봉으로
  - S5 asof `<=`→`<`
  - S6 scan 순서 정렬
  - S9 asof 자르기 삭제
  - S10 brains 무시
- 지갑
  - P1 `tax_rate or …`
  - P2 세금을 수수료 뺀 금액에
  - P3 `Holding` int
  - P4 tax_rate 가 지갑 세율을 바꿈
- 팀장(analyst)
  - A1 strip 없음
  - A2 API 키 안 지움
  - A3 TypeError 안 잡음
  - A4 시간대 없는 시각
  - A8 빈 ANTHROPIC_MODEL
  - A9 analysis 없으면 ok
  - A10 timeout 인자 무시
  - A11 프롬프트 바뀜
  - A12 `--version` 실패가 상태를 바꿈
  - A13 returncode 안 적음

**못 잡은 것**
- S7 예외 좁힘(A-4)
- S8 price 반올림 자리(A-3)
- A5·A6·A7 시각·걸린 시간 뜻(A-5)

`mutate_team.py` 로 team ①② 를 바꿔 본 결과(A-2)는 이렇다.
- 골든만으로는 T1~T6 6개를 모두 못 잡았다.
- 전체 시험으로는 T1 만 잡혔다.
- 대조로 넣은 T7 은 골든이 잡았다.
