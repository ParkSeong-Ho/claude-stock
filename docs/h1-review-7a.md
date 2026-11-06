# 검토 7a — 커밋 d13a9f3 (맥 준비 도우미 `tools/h1_mac.py`·시험·안내서 지름길)

- **날짜**: 2026-11-06
- **대상**: 브랜치 `h1-forward` 커밋 d13a9f3 (`tools/h1_mac.py` 새 파일 350줄, `tests/test_h1_mac_tool.py` 시험 5개, `docs/h1-forward-run.md` 지름길 문단 4곳)
- **검토자**: 독립 검토자. 작성자 설명 없이 코드·시험·문서만 봄.
- **기준**: `docs/h1-forward-run.md` §3.3~§3.7·§4·§6·§7, `h1.py`(CODE_FILES·code_hash·EXIT), `h1_replay.py`, `tools/h1_test_guard.py`, `requirements-h1.txt`, `docs/h1-review-6c.md`·`6d.md`
- **지킨 것**: 저장소 안에는 아무 파일도 만들거나 고치지 않음(커밋·푸시 없음, 저장소에 state/·logs/ 없음 — 끝에 확인). 복사본·탐침은 모두 scratchpad `review7a/` 아래.
  **예외 하나(검토자 실수, 부록 메모 9)**: 표준 라이브러리 확인 중 scratch 복사본에서 setup 이 실제로 진행돼 pip 이 PyPI 에서 고정 버전 꾸러미를 받았고(인터넷 사용, scratch 안), PATH 에 fakebin 없이 pytest 가 약 2분 돌다 내가 멈춤. 진짜 claude 호출 흔적은 없음(시험 묶음은 지킴이가 "claude 호출 0번"을 확인하는 묶음).
- **상태**: 끝. 끝 확인: `/home/user/claude-stock` 의 `git status --short` 빈 결과, 저장소에 `state/`·`logs/` 없음, 가짜 claude 호출 기록(`fakebin/calls.log`) 없음.

## 0. 한눈에

| 볼 것 | 결과 |
|---|---|
| 1. plist 세 개 = 안내서 §4.1·§7 손 plist? | **칸 하나하나 같음**(Label·WorkingDirectory·PATH 순서·`caffeinate` 가 sh 바깥·sh 글·시각 11개씩·로그·보고서엔 PATH/caffeinate 없음). plistlib 로 써서 XML 깨짐 없음. sh 글은 dash·bash 에서 종료 코드·알림 맞음. **그러나 집 폴더에 빈칸이 있으면 매 실행 127**(M-2) |
| 2. setup = §3.3~§3.4? | 순서·확인 같음(파이썬 3.13.18 → venv → pip → pytest → R2 fetch → 지킴이 → 재현 → 지문). 실패하면 그 단계에서 종료 1·`--from N` 안내. venv 가 이미 있으면 버전만 확인하고 다르면 멈춤. git fetch 는 운영 폴더를 안 바꿈(직접 확인). 표준 라이브러리만(직접 확인). **그런데 태그 커밋 c30753e 에는 도우미 파일이 없어 지름길이 아예 안 됨**(M-1) |
| 3. check 는 읽기만·판단 맞나 | 운영 폴더는 안 건드림(H1 폴더 runs.jsonl·잠금 파일은 status 가 씀 — 손 길과 같음). **판단 빈틈**: KS200 이 일주일 묵거나 비어도·status 가 터져도 "모두 맞음"(M-4), 다른 폴더를 가리키는 H1 plist 를 못 봄(M-3) |
| 4. 몰래 하는 일 | 없음. `launchctl` 은 화면에 찍기만, 운영 폴더·운영 장부·주문 길 없음. `--force` 는 plist 를 백업 없이 덮음(경미) |
| 5. 시험의 힘 | **약함.** 돌연변이 26개가 모두 빠져나감(대조 4개는 잡힘): 실패해도 계속(`_run` 이 종료 코드 무시), 지문 비교 없앰, 재현 명령 바꿈, 보고서 Label, 알림 조건 뒤집힘, check 전부 등(M-9) |
| 6. 안내서 지름길 | 손 길과 결과는 거의 같음. 어긋남: 태그(M-1), 보고서 plist 켜기 빠짐(M-6), 다음 단계 순서(M-7), `mkdir -p logs`(M-11), "모두 맞음이면 됩니다"가 판단보다 셈(M-4) |

심함 집계: 치명 0 · 중요 3 · 보통 6 · 경미 6 (M-1 ~ M-15)

---

## 1. 문제 목록

### M-1 · 중요 · 안내서 §3.3·§3.4 지름길 — 태그 커밋 c30753e 에 `tools/h1_mac.py` 가 없어 지름길이 처음부터 안 됨
- **위치**: `docs/h1-forward-run.md` 89행 `git tag h1-forward-v1 c30753e`, 98행("진행 담당이 정한 커밋은 c30753e … 시험 944", "already exists 면 다음 줄로"), 106~111행(setup 지름길), 122행("지금 944개").
- **무엇**: `git cat-file -e c30753e:tools/h1_mac.py` → `fatal: … not in 'c30753e'`. 저장소의 `h1-forward-v1`(주석 태그)도 c30753e. scratch 에 운영 흉내 clone 을 만들어 안내서대로 `git worktree add … h1-forward-v1` → `cd` → `python tools/h1_mac.py setup` 을 그대로 치니 `can't open file '…/claude-stock-h1/tools/h1_mac.py': [Errno 2] No such file or directory`, 종료 2. §3.7 `check`·§4.1 `plists` 도 같음. 초보가 이 화면을 Claude Code 에 보여 주면 "H1 폴더에서 `git checkout origin/h1-forward -- tools/h1_mac.py`" 같은 손질이 나오기 쉬운데, 그러면 `check` 의 "고친 파일 없음"이 실패하고 태그 고정이 흐려진다.
  - 또 98행 "`git tag` 줄이 already exists 면 그대로 다음 줄로" 때문에, 맥에 이미 c30753e 로 태그를 붙인 사람은 태그를 옮겨도 옛 태그를 계속 쓴다.
  - 태그를 도우미가 든 커밋으로 옮기면 pytest 수는 **949**(이 검토에서 지킴이가 센 수)라 122행 "944" 와 다름.
- **고칠 방법**: (가) 도우미 검토가 끝난 커밋 X 로 태그를 정하고 89·98·122행을 X·949 로 바꾼다. c30753e..d13a9f3 차이는 문서·`tools/h1_mac.py`·새 시험뿐이고 CODE_FILES·requirements-h1.txt·설계 문서는 안 바뀌어(`git diff` 빈 결과) **코드 지문이 같다** → 재현 통과 기록·관문에는 영향 없음. (나) 98행에 "이미 c30753e 로 붙였으면 `git tag -f h1-forward-v1 X` 후, worktree 를 이미 만들었으면 `git -C /Users/나/claude-stock-h1 checkout h1-forward-v1`" 한 줄. (다) 인계 메모·`01-무엇을-만들었나.md` 의 944 도 같이. (라) 태그를 못 옮기면 지름길 문단에 "태그 커밋에 도우미가 없으면 손 길로" 를 적는다.

### M-2 · 중요 · `run_command`·보고서 plist — venv python 경로가 따옴표 없이 sh 글에 들어가 집 폴더에 빈칸이 있으면 매 실행 127
- **위치**: `tools/h1_mac.py` `run_command`(`f"{py} h1.py run …"`, `--icloud-status` 의 `f' {py} h1.py status …'`), `make_plist` 보고서(`do {py} h1_report.py`), `cmd_plists` 화면 출력(`plutil -lint …`, `launchctl load -w {경로}`).
- **무엇**: 직접 돌림(`probe/shell_probe.py`, 가짜 python·osascript): 집 `…/homes/김 철수` → dash·bash --posix 모두 `…/homes/김: not found`, **종료 127**(진짜 run 이 0 이든 4 든). 알림은 "H1 국내 종료 코드 127" 로 뜨지만 h1.py 는 한 번도 안 돌아 봉이 쌓이고 5거래일이면 창 실패(§8 표에 127 도 없음). 보고서 plist 도 127. 화면에 찍는 `launchctl load -w /Users/김 철수/…` 를 붙여 넣으면 zsh 가 둘로 나눠 실패.
  - 집 `kim`·`김철수`(한글, 빈칸 없음)는 정상: run 0 → 알림 없음·종료 0, run 4 → 알림 "H1 국내 종료 코드 4 (logs/h1-kr.log)"·종료 4, 보고서 for 줄 us→kr 두 번. iCloud 경로는 큰따옴표라 `Mobile Documents` 빈칸 괜찮음. H1 폴더(ROOT)는 WorkingDirectory·로그(plist 글자)로만 들어가 빈칸이 있어도 괜찮음(좋은 설계).
  - 참고: 맥 계정 이름(짧은 이름)은 보통 빈칸·한글을 못 써서 실제로 생길 일은 드묾. 손 plist(§4.1)도 같은 모양이라 "손 길과 같은 뜻"이긴 하지만, 도우미가 고치기 가장 쉬운 곳이다.
- **고칠 방법**: `import shlex` 후 `q = shlex.quote(str(py))` 를 sh 글 세 곳에, iCloud `dest` 도 `shlex.quote`. 화면 출력도 `shlex.quote(str(p))`. 시험: 집을 `tmp_path / "김 철수"` 로 두고 만든 sh 글을 `/bin/sh -c` 로 돌려(가짜 python 이 4 로 끝남, 가짜 osascript 가 인자를 파일에 적음) 종료 4·알림 글, 0 이면 알림 없음을 단언. (안내서 §4.1·§7 손 plist 도 `'/Users/나/.venv-h1/bin/python'` 처럼 작은따옴표로 감싸도 XML 은 안 깨짐 — 선택.)

### M-3 · 중요 · `check`·`plists` — 다른 폴더(예: 리허설)를 가리키는 `com.claude-stock.h1-*` plist 를 못 알아봄
- **위치**: `cmd_check.agents()`, `cmd_plists`, `LABELS`(고정), 안내서 §10 리허설.
- **무엇**: 직접 돌림(`probe/rehearsal_probe.py`): ROOT=`…/h1-rehearsal` 에서 `plists` → Label 은 진짜와 같은 `com.claude-stock.h1-kr`, WorkingDirectory = 리허설 폴더. 그다음 진짜 폴더(태그 맞음)에서 `check` → "H1 작업: com.claude-stock.h1-kr.plist …", **`[check] 모두 맞음`, 종료 0.** `agents()` 는 "H1 폴더를 가리키는 **다른** 작업"만 찾고, H1 이름 파일이 **어디를** 가리키는지는 안 본다.
  - 안내서 §10 은 리허설 plist 의 Label·폴더·로그를 **다르게**(h1r) 하라고 하는데, 도우미는 Label 이 고정이고 §10 에 "리허설에선 plists 를 쓰지 마세요"가 없다. setup·check 는 ROOT 를 파일 위치로 정하므로 리허설 폴더에서도 그대로 돈다 → plists 까지 쓰기 쉽다.
  - 진짜 준비 때 `plists` 는 "이미 있어 덮지 않았어요 … (다시 만들려면 --force)" 종료 1 — 그 파일이 어디를 가리키는지 말하지 않아 초보는 "이미 있구나"로 넘어갈 수 있다 → start 뒤 진짜 H1 은 한 번도 안 돌고(매일 status 를 보면 하루 이틀 안에 알 수는 있음) 5거래일이면 창 실패.
  - 같은 빈틈: `plists` 는 venv python 이 실제로 있는지, ROOT 가 태그 커밋인지 안 본다. `agents()` 의 `str(ROOT) in txt` 는 글자 포함이라 `/Users/x/claude-stock-h1-old` 도 걸리고, 경로에 `&` 가 있으면 plist 안에선 `&amp;` 라 못 찾는다.
- **고칠 방법**: (가) `check` 에서 `com.claude-stock.h1-*.plist` 를 `plistlib.load` 로 읽어 Label == 파일 이름, WorkingDirectory == ROOT, sh 글이 `venv_python(home)` 으로 시작, PATH 첫 칸에 실행 가능한 `claude` 가 있는지 확인하고 아니면 문제로 센다. 다른 작업 찾기도 plist 를 읽어 WorkingDirectory·ProgramArguments 로 비교. (나) `plists` 는 이미 있는 파일의 WorkingDirectory 를 화면에 보여 주고, ROOT 의 `git describe --exact-match` 가 TAG 가 아니면 멈춤(리허설은 `--label-prefix com.claude-stock.h1r` 같은 옵션으로 따로). (다) 안내서 §10 2번에 "리허설에서는 `tools/h1_mac.py plists` 를 쓰지 마세요(진짜와 같은 이름을 만들어요)".

### M-4 · 보통 · `check` 판단 빈틈 — KS200 이 묵거나 비어도, status 가 터져도 "모두 맞음"
- **위치**: `cmd_check.ks200()`·`status()`, 안내서 §3.7 지름길 "마지막에 `[check] 모두 맞음` 이 나오면 됩니다".
- **무엇**: 직접 돌림(scratch 복사본 + 로컬 태그 + PYTHONPATH 가짜 FinanceDataReader, 인터넷 없음):
  1. KS200 맨 아래 2026-10-30(오늘 11-06) → `모두 맞음`, 종료 0. `Empty DataFrame`(받기 전부 실패) → 역시 `모두 맞음`. FDR `KrxIndexReaderCache` 는 연도 파일 실패를 `except Exception: pass` 로 삼키므로 실제로 생길 수 있는 모양이다. 안내서는 "KS200 날짜만은 눈으로" 라고 하지만, 초보는 마지막 줄 "모두 맞음"을 믿기 쉽다.
  2. `h1.py status` 가 import 에서 터지게(가짜 pandas) → 화면엔 traceback **앞 3줄만**(진짜 오류 줄은 잘림), 종료 코드는 안 봄 → 문제로 안 셈. (이번엔 S&P500 항목이 같은 원인으로 잡혀 1 이 났지만 status 만 터지면 "모두 맞음".) 안내서 §3.7-2 의 판단("장부 없음" + "※ 사전 등록 파일 … 없음"이 정상)도 도우미는 하지 않는다.
  3. KS200 줄이 시작일 없이 `DataReader('KS200')` → FDR 기본 2010년부터 연도 파일 17개를 받음(손 길은 `'2026-10-01'`). 끝 줄은 같지만 느리고, 올해 파일만 실패하면 작년 12월 날짜가 보인다. "어제여야" 는 월요일·휴장 뒤엔 금요일·그 전 평일이 정상(6d D-13 과 같은 말).
- **고칠 방법**: KS200 은 `DataReader('KS200', '<오늘-30일>')` 의 마지막 날짜를 `YYYY-MM-DD` 로 찍고, 비었거나 "가장 최근 평일(22:30 전이면 그 전 평일)"보다 3일 넘게 앞이면 문제로 센다(공휴일 때문에 확실치 않으면 "확인 필요"로 따로). status 는 종료 코드가 0·8 이 아니면 문제로 세고 stderr **끝** 몇 줄을 보여 준다. 안내서 문장은 "모두 맞음이 나오고, KS200 날짜가 가장 최근 거래일이면 됩니다"로.

### M-5 · 보통 · `plists --claude` — 상대 경로·`~`·없는 경로도 받아 PATH 가 엉뚱해짐 → 매일 팀장 폴백
- **위치**: `claude_dir`.
- **무엇**: 직접 돌림(`probe/claude_arg.py`): `--claude claude`·`./claude` → PATH `.:/opt/homebrew/bin:…`(launchd 에선 상대 경로), `--claude '~/.local/bin/claude'`(zsh 에서 `--claude=~/…` 로 치면 `~` 가 안 풀림) → PATH `~/.local/bin:…`(launchd 는 `~` 모름), `/없는/폴더/claude` → 그대로 "만듦" 종료 0. 이름이 `claude` 가 아닌 것만 거절. 결과는 `"status":"no_claude"` → 매일 팀장 없이 규칙만(창 실패는 아니지만 실험의 뜻이 줄고, §4.2 확인은 start 뒤 첫 launchd 처리 다음 날에야 됨).
- **고칠 방법**: `p = Path(path).expanduser()`; 절대 경로가 아니거나 `p.is_file()` 이 아니거나 `os.access(p, os.X_OK)` 가 아니면 Stop. 화면에 "§3.5 에서 시험한 PATH 와 같은지 보세요: …" 한 줄.

### M-6 · 보통 · 안내서 §4.1 지름길 "켜는 명령은 … §4.2 대로 쳐요" + "§7 의 보고서 plist 만들기는 건너뛰어요" — 보고서 작업이 안 켜질 수 있음
- **위치**: 안내서 206·211행, §4.2 상자(294~296행: `plutil`·`load` 가 국내·미국 둘뿐), §7 387행("만들고 plutil -lint → launchctl load -w").
- **무엇**: 도우미 화면에는 보고서 `load -w` 줄이 있지만, 안내서는 "§4.2 대로" 치라고 하고 §4.2 상자엔 보고서가 없다. §7 의 "만들고 … load" 문단은 건너뛰라고 했다. 안내서대로 하면 `com.claude-stock.h1-report` 는 파일만 있고 안 켜진다 → 월간 보고서가 자동으로 안 생김(나중에 손으로 만들 수 있어 해는 작음 — 9절만 바뀔 수 있음).
- **고칠 방법**: 206행을 "화면에 나온 `plutil -lint` 한 줄과 `launchctl load -w` **세 줄**(보고서 포함)을 그대로 치고, 그다음 §4.2 의 `osascript`·`kickstart`·`tail` 줄을 쳐요"로.

### M-7 · 보통 · 다음 단계 안내가 셋이 서로 다름 (setup 끝 글 · check 끝 글 · 안내서 순서)
- **위치**: `cmd_setup` 끝 "다음: 안내서 §3.5·§3.6 → tools/h1_mac.py plists → check", `cmd_check` 끝 "다음: 안내서 §4(자동 실행 켜기) → §5", 안내서 순서 §3.7(check) → §4.1(plists).
- **무엇**: setup 글대로 plists → check 를 하면 check 가 "다음 §4" 라고 해서 §4.1 지름길 `plists` 를 또 치게 되고 "이미 있어 덮지 않았어요"(종료 1)에 놀란다(`--force` 를 치거나 nano 길로 덮어쓸 수 있음). 초보에게 "다음" 글은 길잡이다.
- **고칠 방법**: 안내서 순서 하나로 맞춘다. setup 끝: "다음: 안내서 §3.5·§3.6 → §3.7(check) → §4.1(plists)". check 끝: plist 가 아직 없으면 "다음: §4.1(plists)", 있으면 "다음: §4.2 켜기 확인 → §5".

### M-8 · 보통 · `plists --force` — 이미 켜진 작업은 `load -w` 로 다시 안 읽힘, 고친 내용이 안 먹음
- **위치**: `cmd_plists` 화면 출력.
- **무엇**: `--force` 로 고쳐 쓴 파일(예: M-5 를 고치려고 `--claude` 를 바꿈, 나중에 `--icloud-status` 를 더함)은 이미 load 된 작업에는 다음 로그인 전까지 반영되지 않는다. 화면은 `launchctl load -w` 만 보여 주는데, 이미 켜진 작업에 load 하면 다시 읽지 않는다(새 macOS 는 `Load failed: 5: Input/output error` — 맥이 아니라 직접 확인은 못 함). 안내서 §6 은 `unload -w` → `load -w` 를 하라고 한다. 또 `--force` 는 손으로 고친 plist 를 백업 없이 덮는다.
- **고칠 방법**: 파일이 이미 있었거나 `--force` 면 `launchctl unload -w …` 를 `load -w` 앞에 찍고 "이미 켜 둔 작업은 꺼졌다 켜져야 바뀐 내용이 먹어요"를 한 줄. 덮기 전에 `…plist.bak` 로 옮겨 두기(선택).

### M-9 · 보통 · 시험이 약함 — 돌연변이 26개 모두 빠져나감
- **위치**: `tests/test_h1_mac_tool.py`.
- **무엇**: 복사본에서 도우미에 하나씩 돌연변이를 넣고 이 시험 파일을 돌림(`mut/mutate.py`, 끝에 되돌림 확인). 대조 4개(국내 23:05→23:15, 이미 있어도 덮음, caffeinate 없앰, 패치 버전 안 봄)는 **잡힘** → 장치 정상. 아래는 **모두 5 passed**:
  - setup: m01 `_run` 이 종료 코드를 안 봄(**실패해도 다음 단계로** — 도우미의 핵심 약속), m02 지문 비교 늘 같음, m03 venv 버전 확인 없앰, m04 재현 명령을 `-c pass` 로, m05 pip 이 requirements 를 안 깜, m06 지킴이를 `-c pass` 로, m07 git fetch 가지 바꿈, m22 지킴이를 pytest 앞으로, m20 위치 막기에서 Desktop·iCloud 빠짐, m24 위치 확인 실패해도 계속.
  - plists: m08 PATH 에서 homebrew 빠짐, m09 PATH = claude 폴더만, m10 보고서 Label 을 `h1-kr` 로(launchctl 에서 국내와 부딪힘), m11 보고서 로그를 국내 로그로, m23 보고서 WorkingDirectory 를 집으로, **m12 알림 조건 뒤집힘(성공 때만 알림)**, m13 미국 plist 에 PATH 없음, m26 미국 PATH 에서 claude 폴더 빠짐, m14 미국 로그를 국내 로그로, m21 logs 폴더 안 만듦.
  - check: m15 태그 비교 없앰, m16 깨끗함 비교 없앰, m17 S&P500 수 비교 없앰, m18 다른 작업 찾기 없앰, m19 문제가 있어도 0, m25 KS200 항목 없앰 — **check 는 시험이 하나도 없다.**
  - 또 `_run`·`_out` 의 `cwd=ROOT` 기본값은 **정의할 때** 묶여서, 시험 fixture 가 `M.ROOT` 를 임시 폴더로 바꿔도 `_run` 은 진짜 저장소에서 돈다(지금은 그 길을 타는 시험이 없지만, 뒤에 "setup 한 단계" 시험을 더하면 진짜 저장소에서 pytest·git fetch 가 돈다).
  - `_fake_claude` 의 "bin with space" 는 PATH(셸이 안 나눔)라 괜찮은 곳만 빈칸을 시험한다 — 깨지는 곳(집 폴더, M-2)은 시험 안 함.
- **고칠 방법**: (1) `_run`: `subprocess.run` 을 가짜로(종료 1) 바꿔 `Stop` 이 나는지, setup 이 그 단계에서 1·`--from N` 으로 끝나는지. (2) `setup_steps(home)` 이 돌려주는 명령 목록을 직접 단언(순서·인자: pip `-r requirements-h1.txt`, pytest `-q`, `git fetch origin research-r2-2026-11-04`, `tools/h1_test_guard.py --quick`, `h1_replay.py`). (3) `_compare_hash`: 가짜 `replay_pass.json`(다른 지문·같은 지문·없음) 세 경우. (4) `_make_venv`: 가짜 venv python 이 3.13.17 을 찍으면 Stop. (5) 세 plist 모두 Label·로그·WorkingDirectory·PATH 전체 문자열을 손 plist(안내서 xml 상자)와 **통째로 비교**(이 검토의 `cmp_plists.py` 처럼 안내서에서 읽어 비교하면 문서와 코드가 따로 놀지 않음). (6) sh 글을 실제로 돌리는 시험(M-2 고칠 방법). (7) check: `_out`·`subprocess.run` 을 가짜로 두고 태그 다름·고친 파일 있음·S&P500 39·다른 작업이 H1 폴더를 가리킴·H1 plist 가 다른 폴더를 가리킴(M-3)·KS200 묵음(M-4)·status 종료 1 → 각각 종료 1. (8) `_run(cmd, *, cwd=None, …)` 로 바꾸고 안에서 `cwd or ROOT`.

### M-10 · 경미 · setup 이 pytest 를 R2 `git fetch` **앞**에서 돌림 — 새 clone 이면 R2 시험 20개를 건너뛰고도 "통과"
- **위치**: `setup_steps` 4·5단계(안내서 §3.4 손 길도 같은 순서).
- **무엇**: scratch 에서 R2 원격 가지가 없는 상태로 setup 전체를 돌림 → [4/8] `929 passed, 20 skipped`(`needs_r2`: "R2 브랜치 없음") → 종료 0 이라 그대로 [5/8] 로. 안내서는 "전부 통과해야 해요(지금 944개)". 뒤의 지킴이는 fetch 뒤라 R2 시험까지 949개를 돌려(이 검토: `시험 949개 결과 {'passed': 949}`) 실제로 빠지는 확인은 없지만, 초보가 "skipped 20" 을 보고 멈춰야 하는지 헷갈린다. §3.3 이 이제 `git fetch origin h1-forward`(가지 하나)라 R2 가 아직 없는 맥이 있을 수 있다.
- **고칠 방법**: fetch 를 pytest 앞(3단계 뒤)으로 옮기고 안내서 §3.4 손 길도 같게. 또는 pytest 줄 뒤에 "skipped 가 있으면 R2 fetch 뒤 다시"를 안내.

### M-11 · 경미 · setup 이 `mkdir -p logs`(§3.3 마지막 줄)를 안 함
- **위치**: `setup_steps`, 안내서 68·106행("§3.3 의 venv 만들기~§3.4 전부").
- **무엇**: logs/ 는 `plists` 만 만든다. setup 지름길 + §4.1 손(nano) 길을 섞으면 logs/ 가 없어 launchd 로그(`StandardOutPath`)를 못 쓰고 §4.2 `tail …/logs/h1-kr.log` 가 "No such file". (launchd 가 이때 작업 자체를 띄우는지는 맥에서 확인 못 함.)
- **고칠 방법**: setup 끝(모두 통과 직전)에 `(ROOT / "logs").mkdir(exist_ok=True)`.

### M-12 · 경미 · `_out`·`status()` 가 OSError 를 안 잡음 — 친절한 "멈춤" 대신 traceback
- **위치**: `_out`, `cmd_check.status`.
- **무엇**: 직접 돌림(`probe/venv_probe.py`): venv python 이 실행 권한 없음 → `_make_venv` 에서 `PermissionError` traceback(종료 1 이지만 "N번째에서 멈춤 · --from N" 안내 없음). venv 가 없을 때 `check` 를 치면 `status()` 의 `subprocess.run` 이 `FileNotFoundError`. Ctrl-C 도 traceback. (venv 버전이 다르면 Stop 으로 잘 멈춤 — 확인함.)
- **고칠 방법**: `_out` 에 `_run` 처럼 `except OSError → Stop`, `status()` 도 같은 처리. `main` 에서 `KeyboardInterrupt → "멈춤(사람이 멈춤) — 다시 --from N" · 130`.

### M-13 · 경미 · 1단계가 "python.org 파이썬인지"·"인증서 단계를 했는지"는 안 봄
- **위치**: `_check_python`, `_make_venv`.
- **무엇**: 버전(3.13.18)만 본다. brew 파이썬이 마침 3.13.18 이면 통과하고 그 파이썬으로 venv 를 만든다(이미 있는 venv 도 버전만 봄) → 뒤에 `brew upgrade` 한 번이면 매 실행 종료 코드 3(§3.1 이 막으려던 일). 지름길 명령은 전체 경로라 보통은 괜찮다. 6d D-2 의 `Install Certificates.command` 도 확인하지 않는다(안 하면 금리 받기가 조용히 실패).
- **고칠 방법**(선택): 맥(`sys.platform == "darwin"`)이면 `sys.base_prefix` 가 `/Library/Frameworks/Python.framework/Versions/3.13` 인지, venv 는 `pyvenv.cfg` 의 `home` 이 그 아래인지 확인. 인증서는 인터넷 없이 `os.path.exists(ssl.get_default_verify_paths().cafile or "")` 로 볼 수 있다(없으면 "§3.1 Install Certificates 를 먼저").

### M-14 · 경미 · 안내서 지름길 문단의 작은 어긋남
| 위치 | 지금 | 고칠 것 |
|---|---|---|
| 68행 | "§4.1 의 plist 세 개는 `plists`" | §4.1 에는 둘(국내·미국), 셋째(보고서)는 §7 → "§4.1·§7 의 plist 세 개" |
| 68·106행 | "§3.3 의 venv 만들기~§3.4 전부" | M-11 을 고치기 전이면 "`mkdir -p logs` 는 빼고" |
| 106행 | "(약 20분)" | 이 컨테이너 실측 **17분 32초**(pip 은 이미 깔린 상태, pytest 2분 41초, 지킴이·재현 나머지) — 맞음. 맥 첫 pip 은 몇 분 더 |
| 168행 | "KS200 날짜만은 눈으로 봐요(어제 날짜인지)" | "가장 최근 거래일(월요일이면 금요일)인지" (6d D-13 과 같은 말) |
| §6 휴대폰 | 손으로 plist 고치기만 | "§4.1 에서 도우미를 썼으면 `plists --icloud-status --force` → `unload -w`·`load -w`(M-8)" 한 줄 |
| §4.1 `which claude` 안내 | "나온 경로를 붙여" | zsh 에서 `claude: aliased to …` 가 나오면(옛 '로컬 설치') 그 뒤 경로를 붙이라는 말(선택) |

### M-15 · 경미 · 그 밖의 작은 것
- `check` 는 맥 시간대(§3.2 서울)를 안 본다. launchd 시각이 모두 한국 시간 기준이라 읽기만 하는 확인 하나(`datetime.now().astimezone().utcoffset() == 9시간`)를 더하면 좋다(선택).
- `check` 의 status 는 launchd 작업이 도는 중이면 잠금을 최대 30분 기다려 멈춘 듯 보인다(§6 의 status 와 같은 일) — check 첫 줄에 한 줄 안내(선택).
- `plistlib.loads(blob) != d` "다시 읽어 확인"은 plistlib 끼리라 늘 같다(해는 없음). 맥이면 `/usr/bin/plutil -lint` 를 직접 불러 확인할 수 있다(읽기만, 선택).
- 도우미 머리말 "사용"의 순서(setup → plists → check)도 M-7 과 함께 맞춘다.

---

## 2. 문제 없음으로 본 것 (근거)

1. **plist 내용**: 안내서 xml 상자 3개를 plistlib 로 읽어 `make_plist`(집 /Users/나, claude /Users/나/.local/bin/claude)와 비교 → 국내·미국·보고서 모두 **dict 가 같음**(`probe/cmp_plists.py`). 키 순서도 손 plist 와 같음(`sort_keys=False`). 국내 월~금 23:05 + 월~토 07:40, 미국 화~토 07:10 + 월~토 08:40, 보고서 매달 2일 09:30. `&` 를 안 쓰고, 쓰더라도 plistlib 가 `&amp;` 로 바꿈 — 6d D-1 같은 깨짐 없음. 한글 경로는 UTF-8 그대로.
2. **sh 글**: dash·bash --posix 에서 run 0 → 알림 없음·종료 0, run 4 → 알림 "H1 국내 종료 코드 4 (logs/h1-kr.log)" with title "claude-stock"·종료 4. `caffeinate -i` 는 sh 바깥(6c C-13 대로). `--icloud-status` 는 status|tee 를 알림 검사 앞에 두는데 `$c` 는 run 의 것이라 종료 코드·알림 뜻은 §6 손 길과 같다. `date -v-1m` 은 BSD date(맥) — 6c 에서 확인된 모양 그대로.
3. **setup 순서·확인**: 손 길 §3.3(venv·`-V`·pip)·§3.4(pytest → R2 fetch → 지킴이 → 재현 → 지문)와 같은 순서. scratch 에서 운영 흉내 clone(kr-broker) + worktree(복사본에서만 태그를 d13a9f3 으로)로 **setup 전체를 실제로 돌림**(PIP_NO_INDEX=1): 결과는 부록 메모 8·10. 실패 처리: 단계 실패 → "N번째에서 멈춤 … --from N", 종료 1(시험 있음). `--from` 범위 밖·숫자 아님 → 9. venv 가 이미 있으면 만들지 않고 버전만 확인, 3.13.17 이면 "지우고 다시" 로 멈춤(직접 확인). 지킴이·재현은 종료 코드 0/1·0/2/3/4 라 도우미가 종료 코드만 봐도 맞다. `import h1` 은 화면에 아무것도 안 찍어 지문 비교 글이 깨끗함(직접 확인). 지문 비교는 손 길과 같은 `[-1]['code_hash']`.
4. **git fetch 와 운영 폴더**: setup 전후로 운영 흉내 clone 의 HEAD·현재 가지·작업 트리 파일 52개 sha256·refs(R2 원격 추적 가지 빼고)·stash 를 비교 → 같음(부록 메모 10). fetch 는 공용 refs 의 `origin/research-r2-…` 만 새로 만든다.
5. **표준 라이브러리만**: import 는 `__future__, argparse, json, os, pathlib, plistlib, shutil, subprocess, sys` 뿐(전부 stdlib). `python3.13 -I -S`(site-packages 없음)로 `-h`·`setup --dry-run`·`plists` 가 돎. 3.9 문법으로도 읽힘(`ast.parse(feature_version=(3,9))`) → 맥 기본 `/usr/bin/python3`(3.9)로 잘못 쳐도 1단계에서 "3.13.18 이어야" 로 멈춘다.
6. **몰래 하는 일 없음**: `launchctl` 은 문자열로 찍기만(실행 0곳). 쓰는 곳은 `~/.venv-h1`(setup), ROOT/logs, `~/Library/LaunchAgents/com.claude-stock.h1-{kr,us,report}.plist`(+ 같은 이름 `.tmp` 를 바로 os.replace) 뿐. 운영 plist(`com.claude-stock.kr-…`·`us-…`)·운영 폴더·운영 장부·증권사 모듈을 건드리는 길 없음. 재현은 금리 첫 저장본을 "없을 때만" 두어 다시 돌려도 덮지 않음(`h1_replay.py` 24행).
7. **check 는 운영 쪽을 안 건드림**: git describe·git status·status(H1 폴더 state/h1/runs.jsonl·잠금 파일 — 손 길과 같음)·FDR 받기·LaunchAgents 읽기뿐. 시작 전 status 종료 코드 8.
8. **새 시험은 지킴이를 통과**: setup 6단계 지킴이 `--quick` → "시험 949개 결과 {'passed': 949} · 실행 3번 모두 같음 · 인터넷 0번 · claude 0번 · state/·git status 그대로 · 모두 통과". 새 시험은 plist 를 임시 폴더에만 쓴다.
9. **코드 지문 영향 없음**: `tools/h1_mac.py`·새 시험은 CODE_FILES 밖. `git diff c30753e d13a9f3 -- <CODE_FILES> requirements-h1.txt docs/h1-forward-design.md` 가 비어 있음 → 태그를 옮겨도 코드 지문·환경·설계 문서 sha 가 같다(복사본 지문 58aeadf1d94d…).

---

## 3. 쉬운 말 요약

- **잘 된 것**: 도우미가 만드는 자동 실행 설정 파일(plist) 세 개는 안내서에 손으로 적어 둔 것과 **한 칸도 다르지 않다.** 파일이 깨지지 않게(`&` 같은 글자도 안전하게) 만들고, 켜는 명령(`launchctl load`)은 화면에 보여 주기만 한다. 운영 폴더·운영 장부·진짜 주문을 건드리는 길은 없다. setup 은 안내서와 같은 순서(파이썬 확인 → venv → 라이브러리 → 시험 → 지킴이 → 재현 → 지문)로 돌고, 하나라도 실패하면 거기서 멈추고 "이어서 하는 번호"를 알려 준다. 실제로 끝까지 돌려 보니 통과했고 운영 흉내 폴더는 그대로였다.
- **꼭 고칠 것(중요 3)**:
  1. 안내서가 정한 태그(c30753e)에는 **이 도우미 파일이 없다.** 안내서대로 폴더를 만들고 지름길을 치면 "파일 없음"으로 끝난다 → 태그를 도우미가 든 커밋으로 옮기고(코드 지문은 그대로라 안전) 안내서의 커밋 번호·시험 수(949)를 고친다.
  2. 집 폴더 이름에 **빈칸**이 있으면 자동 실행이 매번 "종료 코드 127"로 실패한다(경로에 따옴표가 없음). 한글만 있으면 괜찮다. 따옴표 한 번이면 고쳐진다.
  3. 리허설 폴더에서 도우미로 plist 를 만들면 진짜와 **같은 이름**으로 리허설 폴더를 가리키게 되고, 진짜 폴더의 `check` 는 그래도 "모두 맞음"이라고 한다 → 진짜 H1 이 안 돌 수 있다. check 가 plist 가 가리키는 폴더를 직접 읽어 보게 하고, 리허설에선 도우미를 쓰지 말라고 적는다.
- **고치면 좋은 것(보통 6, 시험 포함)**: check 가 KS200 날짜가 일주일 묵거나 비어 있어도, status 가 오류로 터져도 "모두 맞음"이라고 함 / `--claude` 에 상대 경로·없는 경로를 넣어도 받아서 팀장이 매일 빠질 수 있음 / 안내서대로 하면 월간 보고서 자동 실행이 안 켜질 수 있음 / "다음에 할 일" 안내가 세 군데서 서로 다름 / 이미 켠 작업을 `--force` 로 고쳐도 다시 읽히지 않음.
- **시험은 약하다**: 도우미 안에 일부러 틀린 곳 26개를 넣어 봤는데 시험 5개가 **하나도 못 잡았다**(예: "실패해도 다음 단계로 넘어감", "성공했을 때만 알림", check 전부). 고칠 시험 목록은 M-9 에 있다.
- 나머지 6개(경미)는 작은 것(시험 앞에 R2 받기, logs 폴더, 오류 글 다듬기, python.org 파이썬·인증서 확인, 문장 몇 개).
- 도우미는 장부 계산 코드(CODE_FILES)가 아니라서, 이것들을 고쳐도 코드 지문·재현 통과 기록은 바뀌지 않는다. 다만 맥에서 쓰려면 **태그를 고친 도우미가 든 커밋에** 붙여야 한다.

---

## 부록: 진행 메모 (찾은 순서대로, 그대로 둠)

모두 `/tmp/claude-0/-home-user-claude-stock/c800b693-7b7e-5a25-8de4-2f198a802ec7/scratchpad/review7a/` 아래. 탐침: `probe/shell_probe.py`·`cmp_plists.py`·`claude_arg.py`·`run_check.py`·`rehearsal_probe.py`·`venv_probe.py`·`hash_mismatch.py`·`run_setup.sh`·`after_setup.sh`, 돌연변이 `mut/mutate.py`·`mut/control.py`, 복사본 `repo`(d13a9f3)·`repo2`(로컬 태그)·`origin.git`·`op`(운영 흉내)·`wt/claude-stock-h1`(worktree). 파이썬은 `~/.venv-h1/bin/python`(3.13.18).

### 메모 1 (확인됨) — 태그 커밋 c30753e 에 도우미가 없다
- `git cat-file -e c30753e:tools/h1_mac.py` → `fatal: path 'tools/h1_mac.py' exists on disk, but not in 'c30753e'`.
  `h1-forward-v1` (주석 태그) → c30753e. 안내서 §3.3 은 여전히 `git tag h1-forward-v1 c30753e` → `git worktree add … h1-forward-v1`.
- 그래서 안내서 지름길대로 `/Users/나/claude-stock-h1` 에서 `python3.13 tools/h1_mac.py setup` 을 치면 `No such file` (종료 2).
  c30753e..d13a9f3 차이: 문서 3개 + tools/h1_mac.py + tests/test_h1_mac_tool.py (CODE_FILES 는 안 바뀜).
- → M-1 (중요) 후보.

### 메모 2 (코드 읽기) — 셸 글에 venv 경로가 따옴표 없이 들어감
- `run_command`: `f"{py} h1.py run --market {mk}; …"`, 보고서 `do {py} h1_report.py`, `--icloud-status` 의 `{py} h1.py status`.
  집 폴더에 빈칸이 있으면 sh 가 둘로 나눔 → 매 실행 127. 화면 출력 `launchctl load -w {경로}`·`plutil -lint` 줄도 따옴표 없음.
- → 맥에서 직접 확인 예정(복사본·가짜 python 으로 sh/dash/bash 돌려 봄).

### 메모 3 (직접 돌림) — 빈칸 든 집 폴더면 plist 셸 글이 매번 127
- probe/shell_probe.py: 집 `…/homes/김 철수` → dash·bash --posix 둘 다 `…/homes/김: not found`, 종료 127(가짜 run 이 0 이든 4 든).
  알림은 "H1 국내 종료 코드 127" 로 뜨지만 h1.py 는 한 번도 안 돌아 봉이 쌓이고 5거래일이면 창 실패. 보고서 plist 도 127.
- 집 `kim`·`김철수`(한글만, 빈칸 없음)는 정상: run 0 → 알림 없음·종료 0, run 4 → 알림 "H1 국내 종료 코드 4 (logs/h1-kr.log)"·종료 4.
  보고서 for 줄도 us→kr 두 번 정상. `--icloud-status` 의 iCloud 경로는 큰따옴표라 `Mobile Documents` 빈칸 괜찮음.
- H1 폴더(ROOT)는 셸 글에 안 들어감(WorkingDirectory·로그 = plist 글자) → ROOT 의 빈칸은 괜찮음(좋은 설계).
- XML 깨짐: plistlib 가 &·<·> 를 바꿔 써서 없음.

### 메모 4 (직접 돌림) — check 판단 빈틈 (복사본 repo2 + 로컬 태그 + 가짜 FinanceDataReader, 인터넷 없음)
- KS200 맨 아래 날짜 2026-10-30(오늘 11-06, 일주일 묵음) → `[check] 모두 맞음`, 종료 0.
- KS200 이 `Empty DataFrame`(받기 전부 실패) → 역시 `모두 맞음`, 종료 0. (FDR KrxIndexReaderCache 는 연도 파일 실패를 `except Exception: pass` 로 삼킴)
- `h1.py status` 가 import 에서 터짐(가짜 pandas) → 화면엔 traceback 앞 3줄만(진짜 오류 줄은 잘림), 문제로 안 셈.
  이번엔 S&P500 항목이 같은 원인으로 잡혀 1 이 났지만, status 만 터지는 경우는 "모두 맞음".
- status 는 H1 폴더 state/h1/runs.jsonl·잠금 파일을 씀(손 길과 같음, 운영 폴더 아님). 시작 전 status 종료 코드 8.
- check 의 KS200 줄은 시작일 없이 `DataReader('KS200')` → FDR 기본 2010년부터 연도 파일 17개를 받음(손 길은 '2026-10-01'). 결과의 끝은 같지만 느리고, 올해 파일만 실패하면 작년 12월 날짜가 보임.

### 메모 5 (직접 돌림) — plist 내용 대조와 --claude 값
- probe/cmp_plists.py: 안내서 xml 상자 3개(§4.1 국내·미국, §7 보고서)를 plistlib 로 읽어 make_plist(집 /Users/나, claude /Users/나/.local/bin/claude) 와 비교 → **셋 다 칸 하나하나 같음**
  (Label·WorkingDirectory·PATH 순서·caffeinate 위치·sh -c 글·시각 11개·로그 경로·보고서엔 PATH/caffeinate 없음까지).
- `--icloud-status`: status|tee 줄을 알림 검사 **앞**에 넣음(§6 손 길은 `exit $c` 바로 앞 = 알림 뒤). 종료 코드·알림 뜻은 같음. 차이 없음으로 봄.
- probe/claude_arg.py: `--claude claude`·`./claude` → PATH `.:/opt/homebrew/bin:…`(상대 경로, launchd 에선 엉뚱한 폴더),
  `--claude '~/.local/bin/claude'`(zsh 에서 `--claude=~/…` 처럼 ~ 가 안 풀린 경우) → PATH `~/.local/bin:…`(launchd 는 ~ 모름),
  `/없는/폴더/claude` → 그대로 받아 종료 0. `/usr/bin/true` 만 거절. → 매일 팀장 폴백(no_claude)인데 만들 때는 "만듦".

### 메모 6 (직접 돌림) — 돌연변이 (mut/mutate.py, 복사본 repo 의 tools/h1_mac.py 만 바꾸고 tests/test_h1_mac_tool.py 실행, 끝에 되돌림 확인)
- 대조 4개(국내 23:05→23:15, 이미 있어도 덮음, caffeinate 없앰, 패치 버전 안 봄)는 모두 **잡음** → 장치는 정상.
- 아래 26개는 **모두 빠져나감**(5 passed):
```
m01 _run 이 종료 코드를 안 봄                         **빠져나감**   5 passed in 6.33s
m02 지문 비교가 늘 같음                               **빠져나감**   5 passed in 0.04s
m03 venv 버전 확인 없앰                             **빠져나감**   5 passed in 0.03s
m04 재현 명령을 아무것도 안 하는 것으로                      **빠져나감**   5 passed in 0.04s
m05 pip 이 requirements 를 안 깜                  **빠져나감**   5 passed in 0.04s
m06 지킴이 --quick 빼고 아무것도 안 함                   **빠져나감**   5 passed in 0.04s
m07 git fetch 를 다른 가지로                        **빠져나감**   5 passed in 0.05s
m08 PATH 에서 homebrew 빠짐                       **빠져나감**   5 passed in 0.04s
m09 PATH = claude 폴더만                         **빠져나감**   5 passed in 0.05s
m10 보고서 Label 을 국내 것으로                        **빠져나감**   5 passed in 0.04s
m11 보고서 로그를 국내 로그로                            **빠져나감**   5 passed in 0.04s
m12 알림 조건 뒤집힘(성공 때만 알림)                       **빠져나감**   5 passed in 0.04s
m13 미국 plist 에 PATH 없음                        **빠져나감**   5 passed in 0.04s
m14 미국 로그를 국내 로그로                             **빠져나감**   5 passed in 0.04s
m15 check 태그 비교 없앰                            **빠져나감**   5 passed in 0.04s
m16 check 깨끗함 비교 없앰                           **빠져나감**   5 passed in 0.04s
m17 check S&P500 수 비교 없앰                      **빠져나감**   5 passed in 0.04s
m18 check launchd 다른 작업 찾기 없앰                 **빠져나감**   5 passed in 0.05s
m19 check 문제가 있어도 0                           **빠져나감**   5 passed in 0.04s
m20 iCloud 위치 막기에서 Desktop·iCloud 빠짐          **빠져나감**   5 passed in 0.04s
m21 plists 가 logs 폴더 안 만듦                     **빠져나감**   5 passed in 0.04s
m22 단계 순서: 지킴이를 pytest 앞에                     **빠져나감**   5 passed in 0.04s
m23 보고서 WorkingDirectory 를 집으로                **빠져나감**   5 passed in 0.04s
m24 setup 이 위치 확인 실패해도 계속                     **빠져나감**   5 passed in 0.05s
m25 check KS200 항목 없앰                         **빠져나감**   5 passed in 0.04s
m26 미국 PATH 를 BASE_PATH 만(claude 폴더 빠짐)       **빠져나감**   5 passed in 0.04s
되돌림: True
```

### 메모 7 (직접 돌림) — 리허설 폴더에서 plists → 진짜 폴더 check 가 "모두 맞음"
- probe/rehearsal_probe.py: ROOT=…/h1-rehearsal 로 `plists` → Label 은 진짜와 같은 `com.claude-stock.h1-kr`, WorkingDirectory = 리허설 폴더.
  그다음 진짜 폴더(repo2, 태그 맞음)에서 `check` → launchd 항목 "H1 작업: com.claude-stock.h1-kr.plist …", `[check] 모두 맞음`, 종료 0.
- 안내서 §10 은 리허설 plist 의 Label·폴더·로그를 **다르게**(h1r) 하라고 하는데, 도우미는 Label 이 고정이고 §10 에도 "리허설에선 plists 쓰지 말기" 말이 없음.
  진짜 준비 때 `plists` 는 "이미 있어 덮지 않았어요"(종료 1) — 초보는 "이미 있구나"로 읽고 넘어갈 수 있음 → 진짜 H1 은 한 번도 안 돎.
- 같은 빈틈: plists 는 venv python 이 실제로 있는지, ROOT 가 태그에 맞는 H1 폴더인지 안 봄.

### 메모 8 (직접 돌림) — setup 전체를 worktree 에서 (진행 중)
- 꾸밈: scratch 에 로컬 origin(bare, R2 가지 포함) → 운영 흉내 clone `op`(kr-broker) → 태그를 복사본에서만 d13a9f3 으로 옮겨 `git worktree add wt/claude-stock-h1`.
  R2 원격 추적 가지는 지워 둠(맥에서 아직 안 받은 경우). PIP_NO_INDEX=1(인터넷 안 씀, 이미 깔린 버전이면 통과).
- [1]~[3] 통과. [4] pytest: `929 passed, 20 skipped`(합 949 — 안내서는 944). 건너뛴 20개는 `needs_r2`(R2 가지 없음) —
  도우미(와 손 길)는 pytest 를 R2 `git fetch` **앞**에서 돌림. 종료 코드 0 이라 도우미는 "통과"로 넘어감. (뒤 지킴이는 fetch 뒤라 R2 시험까지 돎.)
- [5] `git fetch origin research-r2-2026-11-04` → `* [new branch] … -> origin/research-r2-2026-11-04`.

### 메모 9 — 검토자 실수 기록(정직하게)
- 08:16 쯤 "표준 라이브러리만으로 도는지" 보려고 `/usr/bin/python3 -I -S tools/h1_mac.py setup --from 1` 을 scratch 복사본(repo)에서 쳤는데,
  이 컨테이너의 /usr/bin/python3 가 마침 3.13.18 이라 1단계를 통과해 **setup 이 실제로 진행**됨:
  scratch 의 가짜 집(probe/home_std)에 venv 를 만들고, **pip 이 PyPI 에서 고정 버전 꾸러미를 받음(인터넷 사용, 약 51MB, scratch 안)**,
  4단계 pytest 가 복사본에서 시작됐다가 약 2분 뒤 내가 멈춤(TaskStop). 이 명령에는 PATH 맨 앞 fakebin 을 안 붙였음.
- 진짜 claude(/opt/node22/bin/claude)를 부른 흔적: ~/.claude 에 그 사이 새 파일 없음(이 세션 기록 폴더 projects/ 제외).
  시험 묶음은 지킴이가 "claude 호출 0" 을 확인하는 묶음이라 불렸을 가능성은 낮지만, 100% 증명은 못 함.
- 저장소(/home/user/claude-stock)는 건드리지 않음. 받은 것은 scratch 안에만 있음.
- 이 일로 알게 된 것(도우미 쪽 사실): `setup` 은 "확인 없이 바로 venv 만들기·pip 설치·pytest…"를 시작한다. dry-run 이 기본이 아니고
  "진행할까요?" 도 없다. (맥에선 원하는 동작이라 문제로 치진 않음 — 다만 `check`·`plists` 와 이름이 비슷해 헷갈리면 20분짜리가 바로 돈다.)
- 지문 비교 실패 길(probe/hash_mismatch.py): 다른 지문 → '지문이 달라요' Stop, 깨진 JSON → '읽지 못함(JSONDecodeError) → --from 7', 빈 목록 → IndexError 로 같은 안내. 모두 맞음.

### 메모 10 (직접 돌림) — setup 전체 결과
- 08:11:32 → 08:29:04 (**17분 32초**), `SETUP_RC=0`. [6] 지킴이: `시험 949개 결과 {'passed': 949} · 실행 3번 모두 같음 · 인터넷 0번 · claude 0번 · state/·git status 그대로 · 모두 통과`.
  [7] 재현: 창 W1-us·W1-kr·W2-kr·W3-kr 모두 같음, `[재현] 끝: 종료 코드 0 — 통과 + 기록함`, 금리 첫 저장본 rates/ 에 둠. [8] 지문 58aeadf1d94d… = 통과 기록 → `같음`, `[setup] 모두 통과`.
- 운영 흉내 clone(op, kr-broker): setup 전후 HEAD·현재 가지·refs(R2 원격 추적 가지 빼고)·stash **같음**, 작업 트리 파일 52개 sha256 **같음**.
  달라진 것은 공용 refs 의 `refs/remotes/origin/research-r2-2026-11-04`(새로 생김, 22b7934c) 하나 — 운영 폴더의 작업 트리·가지와 무관.
- worktree `git status --short` 비어 있음(pytest·지킴이·재현 뒤에도). `setup --from 8` → 같음·종료 0. 이어서 check(가짜 FDR) → `모두 맞음`(태그·깨끗함·status 8·S&P500 40·launchd 없음).
