# 검토 6d — 커밋 b0e003d..4107136 (검토 6b·6c 반영분)

- **날짜**: 2026-11-06
- **대상**: 브랜치 `h1-forward`, `git diff b0e003d 4107136 -- . ':!docs/h1-review-6b.md' ':!docs/h1-review-6c.md'` (커밋 0267d10·4107136, 11파일 +418/−160). 고치려 한 지적: `docs/h1-review-6b.md` B-1~B-9(코드), `docs/h1-review-6c.md` C-1~C-28(운영 안내서 `docs/h1-forward-run.md`·README).
- **검토자**: 코드를 쓰지 않은 독립 검토자. 작성자 설명은 받지 않고 코드·시험·문서만 봤다.
- **지킨 것**: 이 파일 말고는 저장소를 고치지 않았다. 커밋·푸시 안 함. 진짜 `claude` 를 부르지 않았다(돌린 것은 모두 PATH 맨 앞에 scratchpad `fakebin`, 그 호출 기록 `fakebin/calls.log` 는 끝까지 안 생김). 인터넷 안 씀(R2 ref 는 로컬 저장소에서 clone·fetch). 저장소 안에 `state/` 를 만들지 않았다. 복사본·돌연변이·탐침은 모두 scratchpad `review6d/` 아래. 재현 전체(`h1_replay.py`)·지킴이는 맡긴 대로 돌리지 않았다.
- **참고**: 검토 도중 진행 담당의 스냅샷 커밋 8f4e63c(대상 밖)가 생겼고, 이 파일의 첫 뼈대도 거기에 함께 들어갔다. 8f4e63c 의 다른 변경(인계 메모 등)은 대상 밖이라 B-8 표에서만 짧게 언급한다.
- **상태**: 끝.

---

## 0. 한눈에

| 볼 것 | 결과 |
|---|---|
| 1. B-1~B-9 | **고쳐짐 6**(B-2·B-3·B-4·B-5·B-6·B-9), **일부 2**(B-1·B-8), **안 됨 1**(B-7). 6b §4 참고(재현 하네스 오류 글이 긴 경로에서 잘림)도 고쳐짐(긴 경로에서 고친 코드 통과·옛 코드 실패 확인). 자세히 §1 |
| 1. C-1~C-28 | **고쳐짐 24**, **일부 4**(C-12·C-17·C-27·C-2). C-27·C-12·C-17 을 고치면서 새로 틀린 곳이 생김 → D-1·D-2·D-3. 자세히 §2 |
| 2. 코드 — 운영 동작 | **그대로.** 이 범위의 운영 파일 변경은 `analyst.py` 머리말 docstring 한 줄뿐(`team.py`·`screener.py`·`main.py`·`markets.py`·`paper_wallet.py`·`order_runner.py`·`prompts/` 0). 고치지 않은 복사본 pytest 전체 **942 통과**(골든 포함) |
| 2. 엉뚱한 종목에 판정 | **길이 없다.** `_reply_item` 은 정확한 열쇠가 먼저, 아니면 맨 앞 낱말(빈칸·괄호·쌍점·대괄호 앞)을 대문자로 바꿔 코드와 **완전히 같은** 열쇠가 **하나일 때만**. 한 열쇠의 맨 앞 낱말은 하나라 한 답이 두 코드에 붙을 수 없고, 미국 코드는 대소문자를 무시해도 서로 다르다. `GOOG`↔`GOOGL`, `A`↔`AAPL`·`A.O. Smith`, `BRK`↔`BRK.B` 모두 안 붙음(시험이 못 박음). 새로 바뀐 점: 정확한 열쇠의 값이 비어 있으면 그 열쇠도 겹침으로 세어 폴백 — 답은 `analyst` 가 `{it["code"]: it}`(값은 늘 dict)로 만들어 실제로는 생기지 않음 |
| 2. 새 시험의 힘 | 돌연변이 19개 중 **14개 잡힘**(6b 에서 빠져나간 m01·m08·m09·m13·m17 모양 모두 잡힘). 빠져나간 것(pytest 전체 통과): 제어 문자 바꾸기, 읽을 때 정리, 이름 수 note 의 두 모양, 밀린 봉 안내 글 → D-6(경미) |
| 2. start 일지 note | 이름이 모자라면 `runs.jsonl` 끝 줄 notes 와 화면 `※` 에 "종목 이름 n/N" — 동작 맞음. 다만 안내서에 그 뜻·할 일이 없고, 재시작해도 종목군 파일을 그대로 써서 고칠 길이 없다 → D-5 |
| 2. h1_replay·11절·밀린 봉 글 | 재현 오류 글 앞뒤 보존 맞음. 11절 정의가 R2(같은 종목·금액·보유기간, 시작일만 무작위 1,000번)와 같아짐, 다만 "'우연이 아니다'의 기준 95%" 는 R2("약한 근거")보다 셈 → D-8. 밀린 봉 안내 글은 `restart` 인자로 그대로 나뉘고 backlog 근거와 맞음 |
| 3. 안내서 따라 하기 | 상자 안 `#` **0개**, h1 명령 상자 모두 `cd`·`P=`(또는 절대 경로) 있음, 명령·인자·경로·시각·plist(plistlib 로 셋 다 읽힘) 코드와 맞음, 운영 폴더 브랜치·운영 장부를 바꾸는 지시 없음, `§n` 참조 모두 맞음. 그러나 **§6 휴대폰 한 줄을 안내대로 plist 에 넣으면 plist 가 깨진다**(D-1, 중요). 라이브러리 올림 실패 때 되돌리기가 반쪽(D-3), 금리 받기 인증서(D-2) |

심함 집계: 치명 0 · 중요 1 · 보통 2 · 경미 10 (D-1~D-13).

---

## 1. 6b 지적(B-1~B-9) 확인

| 6b | 이 범위에서 한 것 | 판단 |
|---|---|---|
| B-1 (보통) 미국 이름 실패가 조용·영구 | start 가 종목군을 새로 받을 때 정리 뒤 이름 수가 종목 수보다 적으면 `log.note("종목 이름 n/N — …")` → 화면 `※` 한 줄 + `runs.jsonl` start 끝 줄 `notes`. 시험: 이름 0개일 때 note 가 남는지 | **일부.** 기록은 남는다(6b 고칠 방법 2 의 앞부분). start 거절(방법 1)·실패 사유 기록(`h1_data.universe_names` 는 안 바뀜)·안내서 확인 항목은 없음. 시험은 0개 경우만이라 "일부만 빠짐" 경우의 실수를 못 잡음(M10·M11). → D-5·D-6 |
| B-2 (보통) 경계·이름 받기 시험 없음 | `test_Q4_답_찾기는_앞글자만_같은_종목을_잡지_않는다`(GOOG·A·BRK 음성, AAPL(Apple)·빈칸·소문자 양성, 정확한 열쇠 먼저), `test_Q4_이름_받기_universe_names_와_live_source`(가짜 FDR) | **고쳐짐.** 6b m01 모양(M01)·m13 모양(M02) 잡힘. 6b m08 모양(`t["Security"]`, N18)·m09 모양(`live_source` 가 names 안 넘김, N19) 잡힘 |
| B-3 (경미) 이름 값 검사 없음 | `NAME_MAX = 60`, `_clean_name`(글자 아님 → 버림, 인쇄 못 하는 글자 → 빈칸, 빈칸 하나로, 60자 자름) 을 `_universe_blob`(쓸 때)·`read_universe_names`(읽을 때) 둘 다에 | **고쳐짐.** 6b 탐침 글(`"Evil Corp\n- AAPL: …"`)은 한 줄이 되어 가짜 후보 줄이 안 생김(시험 있음). start 봉도 정리된 이름(blob 에서 다시 읽은 것)을 씀. `_build_prompt_h1` 쪽 방어 정리는 안 했지만 들어오는 두 길(종목군 파일, `KR_UNIVERSE` 상수)이 모두 정리·고정돼 실해 없음. 시험은 `\n`·`\t`·길이만 → 제어 문자 바꾸기(M07)·읽을 때 정리(M09)는 못 박음 안 됨(D-6) |
| B-4 (경미) 빈칸·소문자 못 찾음 | `k.strip() != code` 조건 지움, 비교를 `.upper()` 로 | **고쳐짐.** `"005930 "`·`"aapl"` 찾음(시험). `"A O Smith"` → `A` 는 그대로(6b 도 선택으로 둠) |
| B-5 (경미) 찾아 쓴 사실 기록 없음 | 판정 기록에 `reply_code`(맨 앞 낱말로 찾았을 때만 답의 원래 열쇠, 아니면 null) | **고쳐짐(코드).** 시험이 값까지 봄(M05·M06 잡힘). 보고서 팀장 절의 수(선택)는 안 넣음, 안내서 §3.5 "잦으면 알려 주세요"에 세는 법이 없음 → D-12 |
| B-6 (경미) 11절 무작위 정의 | "같은 종목·같은 금액·같은 보유 기간으로 시작일만 무작위로 1,000번 고른 매매", "미국 두 종목군에서 12%·16%", "국내 88%(… 95% 에는 못 미침)" + 시험 단언 | **고쳐짐.** R2 REPORT 184행 정의와 같음, 6b m17 모양(M14)·95% 빠짐(M17) 잡힘. 말 하나가 R2 보다 셈 + 옛 "한 번의 과거 시험" 문장이 빠짐 → D-8 |
| B-7 (경미) 위키백과 받기 timeout 없음 | 없음 | **안 됨.** 코드도 문서도 그대로. 오히려 §3 머리 "멈춘 것처럼 보여도 Ctrl-C 하지 마세요"가 start 에도 걸리게 읽힘 → D-7 |
| B-8 (경미) 문서 옛 문구 | 설계 §3.7 파일 표 `names` 칸, `DataSource` 스케치 `names`, `analyst.py` 머리말, 시험 지도(9개 이름 — 모두 실제 시험과 일치 확인) | **일부.** 이 범위에서는 위 넷을 고침. `docs/작업-이어가기.md` 는 뒤 커밋 8f4e63c(대상 밖)에서 고침. `docs/h1-intent-check.md` 맨 위 안내 한 줄은 HEAD 에도 없음(경미, 선택). 설계 표의 "start 일지에 '종목 이름 n/N'" 은 모자랄 때만 남는다는 말이 빠짐(D-13) |
| B-9 (경미) A-10 이유 문장 | 설계 Q4 칸: "물은 때의 코드 지문 — runs.jsonl·하루 기록에 있음 — 로 알 수 있다. 다만 재시작 뒤 같은 열쇠는 앞 창에서 받은 판정을 그대로 쓴다" | **고쳐짐** |
| 6b §4 참고 (재현 하네스 오류 글 뒤 600자만) | 1200자 넘으면 앞 600 + " … " + 뒤 600 | **고쳐짐.** 경로 약 295자 복사본에서 `test_하네스는_모듈이_임시_폴더_밖에서_읽히면_멈춤` — 고친 코드 통과, `[-600:]` 로 되돌린 코드 실패 |

---

## 2. 6c 지적(C-1~C-28) 확인

| 6c | 새 안내서(4107136) | 판단 |
|---|---|---|
| C-1 `tail -1 replay_pass.json` | §3.4 마지막 줄을 `json.load(...)[-1]['code_hash']` 비교로. 복사본에서 그대로 쳐 봄 → 두 지문과 `같음` | 고쳐짐 |
| C-2 `cli_version` 위치 | §4.2: `tail -3 …/analyst_cache_kr.jsonl`, `status`·`cli_version` 보기, kickstart 는 실행 확인용 | **일부** — 파일·칸은 맞음. 글의 `"status": "ok"` 는 실제 줄(`"status":"ok"`, 빈칸 없음)과 다르고, S 봉(터미널에서 친 start)의 줄이 끝에 남아 "launchd 에서도 됨"으로 잘못 볼 수 있음, 미국 없음 → D-4 |
| C-3 재시작 `L\|backlog\|rule-change` | §9.3 상자는 `--reason L` 하나, 위에 "묻지 않고 바로 실행·되돌릴 수 없음"·"하나만" 경고, 부록 A "중 하나" | 고쳐짐 |
| C-4 상자 안 `# 설명` | 상자 27개 중 `#` 0개(스크립트로 확인), §3 머리 공통 규칙 | 고쳐짐 |
| C-5 `worktree remove` 가 `--force` 없이도 지움 | §13 경고를 상자 **위**에, `--force` 뜻 바로잡음, 먼저 `cp -R` 보관 줄. 리허설 폴더 `/Users/나/h1-rehearsal`, "두 번 확인" | 고쳐짐. (`.gitignore` 가 `state/`·`*.log`·`__pycache__/` 를 무시해 실제로 `--force` 없이 지워짐 — 경고 문장이 사실과 맞음) |
| C-6 운영 폴더 브랜치 바꿈·`reports/broker` | §7 보관 1번 iCloud 복사, 2번 별도 worktree `h1-reports`, `git add .`·`git add reports` 금지 | 고쳐짐(`reports/` 는 무시 대상이 아니라 `git add reports/h1-forward` 가 됨. 복사 줄에 `mkdir -p` 가 없는 것은 사소) |
| C-7 `pmset repeat` 덮어씀 | §3.6: 잠자기 끄기 먼저, `pmset -g sched` 로 보고 운영 09:00 이 있으면 바꾸지 않기, 없을 때만 07:00 | 고쳐짐(`broker-run.md` 100행 `MTWRF 09:00:00` 과 맞음) |
| C-8 `kr-fix-s0.md` §5 가리킴 | §3.7 에 KS200·S&P500 확인 명령, 운영 폴더용 명령은 치지 말라는 말 | 고쳐짐 |
| C-9 `$P`·`cd` 없는 상자 | h1 명령 상자 모두 `cd /Users/나/claude-stock-h1` 로 시작, `$P` 쓰는 상자는 모두 `P=` 먼저 | 고쳐짐(§9.2 표 안 명령은 상자가 아니고 `h1.py …` 만 적힘 → D-9) |
| C-10 `unload` 만 | `unload -w`, 지우기에 `rm …h1-*.plist`(이름을 하나씩) | 고쳐짐 |
| C-11 plist "두 곳만" | 국내·미국·보고서 plist 전체, `nano`·`plutil -lint` | 고쳐짐(셋 다 `plistlib` 로 읽힘, 시각이 §4 표와 같음) |
| C-12 파이썬 3.13.18 | §3.1 python.org 설치 파일 한 길, 확인 순서 바로잡음, brew 금지 이유 | **일부** — 고친 길(python.org)이 인증서 설치 단계를 빠뜨려 금리 받기가 조용히 실패 → D-2 |
| C-13 `caffeinate` 종료 코드 | `caffeinate -i /bin/sh -c '…; c=$?; …; exit $c'`, 알림 시험·권한 | 고쳐짐 |
| C-14 따라잡은 봉 = 늦은 봉 | §3.6·§13 | 고쳐짐 |
| C-15 D6 기다리는 동안 전체 멈춤 | §9.2 첫 문단·표 첫 줄 | 고쳐짐 |
| C-16 claude 시험 자리표시·폴더 | 예시 값, "끝의 /claude 를 뺀 폴더", `state/h1/claude_cwd` 에서 시험 | 고쳐짐 |
| C-17 허용 변경 순서 | `git fetch --tags` → `checkout` → `pip install` → 재현, 낮 시간, 실패 때 되돌리기 | **일부** — 되돌리기가 코드만 되돌림 → D-3 |
| C-18 status 표 | 두 줄, 재시작·마감 줄, 사전 등록 없음 줄, 로그 명령, 잠금 대기 | 고쳐짐(탐침의 실제 status 출력과 같음) |
| C-19 README "하나도 안 바꿈" | "**동작**은 하나도 바뀌지 않아요(… 갈고리·함수만 더했고 …)", 준비는 안내서 §3 | 고쳐짐 |
| C-20 `--cancel-delist` 인자 | `--market m --code X --cancel-delist --confirm X --source <근거>` | 고쳐짐 |
| C-21 start 시각 | 국내 23:00 뒤, 미국 한국 시간 07~22시, 재시작 뒤 start 도 §5 시각 | 고쳐짐(16:15 ET = 06:15/05:15 KST, 09:30 ET = 23:30/22:30 KST 로 겨울·여름 모두 07~22시 안) |
| C-22 §2 머리 문장 | "숫자는 prereg, 프롬프트·분할 처리는 코드 지문" | 고쳐짐(인계 메모 쪽은 대상 밖 8f4e63c) |
| C-23 확인 목록 빠짐 | `git describe --tags --exact-match`, `grep -l claude-stock-h1 …plist`, 리허설에 ENV(4), 운영 쪽 확인은 `작업-이어가기.md` §6 | 고쳐짐(§6 에 두 확인이 있음) |
| C-24 리허설 | `cd` 먼저, plist Label·폴더·로그 다르게, 호출 늘어남 | 고쳐짐(문서 안 위치는 D-11) |
| C-25 막힐 때 규칙·시간 | §3 머리 "멈춤 규칙"·걸리는 시간 | 고쳐짐(Ctrl-C 문장은 D-7) |
| C-26 최종 보고서 위치 | §11 `state/h1/reports/kr-final-<S>.md` | 고쳐짐(`h1_report.report_name` 과 같음) |
| C-27 휴대폰으로 매일 확인 | §6 에 plist 에 넣을 한 줄 | **일부(새로 틀림)** — 그 줄의 `2>&1` 때문에 plist 가 깨짐 → D-1 |
| C-28 start → launchd 순서 | §4 를 start 앞으로, "왜 먼저", 종료 코드 8 알림이 정상 | 고쳐짐(탐침: start 전 run 2번이 8 로 끝나고, 뒤의 status·창 셈에 안 섞임) |

---

## 3. 문제 목록

### D-1 · 중요 · §6 "휴대폰으로 보기" 한 줄을 안내대로 plist 에 넣으면 plist 가 깨져 매일 실행이 조용히 멈출 수 있다 (C-27 을 고치며 새로 틀림)

- **위치**: `docs/h1-forward-run.md` §6 끝 "휴대폰으로 보기(아이폰, 선택)" (323~324행) → §4.1 의 plist `sh -c` 글.
- **무엇이 틀렸나**: 넣으라는 글 `… h1.py status --market kr > "…/H1-상태-kr.txt" 2>&1;` 의 `2>&1` 에 있는 `&` 는 XML(plist)에서 쓸 수 없는 글자다(`&amp;` 로 써야 함). §4.1 국내 plist 의 `exit $c` 앞에 그대로 넣어 보니 `plistlib`: `ExpatError: not well-formed (invalid token)`, `xmllint`: `xmlParseEntityRef: no name`. §6 은 고친 뒤 `plutil -lint`·다시 load 하라는 말도 없다. 그래서
  - 이미 켜 둔 작업에 넣고 그냥 두면: 지금은 옛 설정으로 돌다가 **다음 재시동·로그인 때 launchd 가 이 파일을 못 읽어 작업이 아예 안 뜬다.** 셸이 안 뜨니 알림도 없다 → 봉이 쌓여 늦은 봉 → 5거래일 넘으면 종료 코드 6, 창 실패.
  - `launchctl unload -w` → `load -w` 를 하면: unload 는 되고 load 가 실패해 그 자리에서 작업이 꺼진다.
  - 미국용 줄(`--market us`, 파일 이름)이 따로 없다. launchd 작업이 iCloud Drive(`~/Library/Mobile Documents`)에 쓰는 것을 맥 개인정보 보호(파일 및 폴더)가 막을 수도 있다(이 컨테이너에서는 확인 못 함 — 막혀도 `;` 뒤 `exit $c` 라 H1 실행 결과는 그대로).
- **고칠 방법**: (가) 줄에서 `2>&1` 을 뺀다(status 의 오류 글은 어차피 그 작업 로그로 간다; `>` 는 XML 에서 써도 됨):
  `/Users/나/.venv-h1/bin/python h1.py status --market kr > "/Users/나/Library/Mobile Documents/com~apple~CloudDocs/H1-상태-kr.txt";`
  (미국 plist 에는 `--market us`·`H1-상태-us.txt`.) `2>&1` 을 꼭 두려면 `2&gt;&amp;1`. (나) 바로 아래에 상자로:
  ```
  plutil -lint /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  launchctl load -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  launchctl kickstart gui/$(id -u)/com.claude-stock.h1-kr
  ```
  설명: "`plutil -lint` 가 `OK` 가 아니면 load 하지 말고 줄을 되돌리세요. kickstart 몇 초 뒤 휴대폰 '파일' 앱(iCloud Drive)에 `H1-상태-kr.txt` 가 생기는지 보고, 안 생기면 이 줄을 빼고 다시 lint·load 하세요."

### D-2 · 보통 · §3.1 python.org 파이썬: 인증서 단계가 빠져 금리 받기가 조용히 실패, 기본 설치가 터미널의 `python3` 를 바꿀 수 있음 (C-12 를 고치며 새로 생김)

- **위치**: `docs/h1-forward-run.md` §3.1·§3.3, `h1_report.fetch_rates`(표준 `urllib`).
- **무엇이 틀렸나**(맥이 아니라 직접 돌리지는 못함 — python.org 맥 설치 파일의 알려진 동작):
  1. python.org 맥 파이썬은 자기 OpenSSL 을 쓰고 맥 키체인 인증서를 안 쓴다. 설치 뒤 `/Applications/Python 3.13/Install Certificates.command` 를 한 번 돌려야 `urllib` 의 https 가 된다(설치 프로그램 안내문에 있는 단계). H1 에서 `urllib` 을 쓰는 곳은 FRED 금리 받기 하나다(시세·S&P500 표는 FDR → `requests`+certifi 라 상관없음). `fetch_rates` 는 모든 예외를 "오프라인"으로 삼키고 화면에 `[금리] … 받기 실패 → 저장본 있음 (… 까지)` 한 줄만 남기며, 보고서 9절은 재현이 처음 깔아 둔 R2 금리 저장본(2026-11-04 수집분, `h1_replay.py` 24행)의 마지막 값을 이월한다. 안내서 §7 은 "인터넷이 있으면 금리도 받아요"라고만 해서, 3개월 내내 낡은 금리로 'A0+이자'(참고값)가 계산돼도 모를 수 있다.
  2. python.org 설치 프로그램은 기본으로 'UNIX command-line tools'(`/usr/local/bin/python3` 등 링크)와 'Shell profile updater'(`~/.zprofile` PATH 앞에 3.13)를 설치한다. H1 은 절대 경로를 써서 상관없지만, 운영 venv(`broker-run.md` 68행 `/Users/나/.venv-cs/bin/python`)가 `/usr/local/bin/python3` 를 가리키게 만들어졌거나 운영 명령을 터미널에서 `python3 …` 로 치는 경우에는 **운영 쪽 파이썬이 바뀔 수 있다**(운영 환경을 건드리는 지시가 될 수 있음 — 맥에서 확인 필요).
  3. 나중에 python.org 에서 3.13 의 다른 패치 버전을 설치하면 같은 `/Library/Frameworks/Python.framework/Versions/3.13` 을 덮어써 H1 venv 의 파이썬도 바뀐다 → 매 실행 종료 코드 3. §3.1 은 brew 만 경고한다.
- **고칠 방법**(§3.1):
  - 설치 전: `ls -l /Users/나/.venv-cs/bin/python*` 와 `/Users/나/.venv-cs/bin/python -V` 를 적어 두기. 설치 화면의 '사용자화'에서 'UNIX command-line tools'·'Shell profile updater' 를 끄기(H1 은 전체 경로를 쓰므로 필요 없음). 설치 뒤 같은 두 줄이 똑같은지 확인.
  - 설치 뒤: "Finder → 응용 프로그램 → Python 3.13 → `Install Certificates.command` 더블클릭(한 번만)" + 확인 줄
    `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -c "import urllib.request; urllib.request.urlopen('https://fred.stlouisfed.org', timeout=20); print('OK')"` → `OK`.
  - "판정 창 동안 python.org 에서 다른 3.13 버전을 설치하지 마세요(종료 코드 3)." §7 에 "보고서 화면에 `[금리] … 받기 실패` 가 나오면 Claude Code 에 보여 주기".

### D-3 · 보통 · §9.1 "재현이 0 이 아니면 `git checkout h1-forward-v1` 로 되돌리고" — 라이브러리는 안 되돌아가 매 실행 종료 코드 3 (C-17 을 고치며 반쪽)

- **위치**: `docs/h1-forward-run.md` §9.1 410~411행.
- **무엇이 틀렸나**: 같은 상자에서 `pip install -r requirements-h1.txt`(새 태그의 새 버전)를 이미 쳤다. 코드만 옛 태그로 되돌리면 venv 는 새 버전 그대로라, 관문의 환경 지문(`h1.env_info` = 파이썬 + pandas·numpy·ta·FinanceDataReader 버전)이 옛 통과 기록과 다르다 → **다음 실행부터 매번 종료 코드 3**(관문 거절), 봉이 안 쌓여 늦은 봉 → 5거래일이 넘으면 창 실패. 초보에게 §8 의 3 줄("무엇이 바뀌었는지 확인")만으로는 원인을 찾기 어렵다.
- **고칠 방법**: 되돌리기를 상자로:
  ```
  cd /Users/나/claude-stock-h1
  P=/Users/나/.venv-h1/bin/python
  git checkout h1-forward-v1
  $P -m pip install -r requirements-h1.txt
  $P h1.py status --market kr
  ```
  설명: "`pip install` 이 라이브러리를 옛 태그의 고정 버전으로 되돌려요. status 의 `⑥ … 지금 코드·환경 = 마지막 봉과 같음` 이 나오면 됐어요(미국도 같은 줄로 확인). 그다음 화면을 Claude Code 에 보여 주세요."

### D-4 · 경미 · §4.2 "launchd 에서 claude 가 정말 불리는지" 확인 — 글자 모양이 실제와 다르고, 터미널에서 친 start 의 줄로 착각할 수 있음 (C-2 일부)

- **위치**: §4.2 272~276행.
- **무엇이 틀렸나**: (가) 판정 기록 줄은 빈칸 없는 JSON 이다(`h1.DecisionLog.append` 의 `separators=(",", ":")`) → 실제는 `"status":"ok"`·`"cli_version":"…"`. 문서의 `"status": "ok"` 로 찾으면(⌘F·grep) 안 맞는다. (나) S 봉은 **터미널에서 친 start 가 팀장을 부른다**(탐침 start 화면 "팀장 LLM 호출 2번"). 그날 이후 launchd 실행이 매수 후보가 없어 팀장을 안 불렀으면 `tail -3` 의 줄은 터미널 환경의 결과인데 `"status":"ok"` 라 "launchd 에서도 된다"로 잘못 볼 수 있다. (다) 미국 확인(`analyst_cache_us.jsonl`, `kickstart …h1-us`)이 없다.
- **고칠 방법**: "줄의 `"date":"…"` 가 **S 가 아닌 날**(launchd 가 처리한 봉)인 줄을 봐요. `"status":"ok"` 이고 `"cli_version":"2.x.x (Claude Code)"` 면 OK(빈칸 없이 붙어 있어요). 미국은 `analyst_cache_us.jsonl`." 그리고 §4.2 상자에 `launchctl kickstart gui/$(id -u)/com.claude-stock.h1-us` 와 `tail -20 …/logs/h1-us.log` 도.

### D-5 · 경미 · B-1 남은 것 — "종목 이름 n/N" note 의 뜻·할 일이 안내서에 없고, 고칠 길도 없다

- **위치**: `h1._start_locked`(note), 안내서 §3.7·§5.
- **무엇이 틀렸나**: 미국 start 에서 이름을 일부·전부 못 받으면 화면에 `※ 종목 이름 0/40 — …(이 창 동안 그대로)` 가 나온다. 안내서는 이 줄을 말하지 않는다. "멈춤 규칙"대로 물어봐도 start 는 이미 끝났고, 재시작은 같은 종목군 파일을 써서(이름 포함, sha 고정) 이름을 다시 받을 길이 없다 — 사용자 결정 D-1 의 "종목 이름"이 그 시장 창 전체(재시작 포함)에서 빠진다. 이름 받기 바로 앞에 같은 표를 막 받았으므로 실패는 대개 잠깐의 인터넷 문제다.
- **고칠 방법**: (권장, 코드 — 태그 전에만) 미국 start 에서 정리 뒤 이름 수가 종목 수보다 적으면 "이름 목록을 받지 못함 → 잠시 뒤 다시 start" 로 거절(종목군 파일·장부는 start 끝에 쓰므로 거절해도 깨끗. 일부러 이름 없이 가려면 옵션 하나). (최소, 문서) §3.7 에 `$P -c "import h1_data; print(len(h1_data.universe_names('us')))"` → 500 안팎이면 OK, §5 에 "`※ 종목 이름 n/40` 이 나오면 이름 없는 종목은 팀장 글에 코드만 가요. 판정·장부에는 영향 없고 이 창 동안 그대로예요."

### D-6 · 경미 · 새 시험이 못 박지 않는 것 — 돌연변이 5개가 pytest 전체를 통과

- **위치**: `tests/test_h1_modules.py::test_Q4_이름은_한_줄로_정리하고_길이를_자른다`, `tests/test_h1_runner.py::test_Q4_국내_start_run_은_KR_UNIVERSE_이름_미국_이름_실패면_코드만`, 밀린 봉 글(시험 없음).
- **무엇이 틀렸나**(§5 표):
  - M11 `n_named = len(u_names)`(받은 이름 전체 수): 실제 미국 출처는 S&P500 표 500여 개를 주므로 **종목군 이름이 빠져도 note 가 절대 안 남는데** 시험은 이름 0개 출처만 써서 통과. M10(0개일 때만 note)도 같은 까닭으로 통과. 둘 다 "단순하게" 고치기 쉬운 모양이다.
  - M07 인쇄 못 하는 글자 바꾸기 없앰: 시험 입력이 `\n`·`\t` 뿐이라 `split()` 만으로도 통과(줄바꿈 종류는 `split()` 이 다 처리하므로 실해는 작음 — ESC·NUL 같은 글자만 남음).
  - M09 `read_universe_names` 의 정리 없앰: 파일은 쓸 때 이미 정리돼 방어용이지만, 옛 모양 파일·손댄 파일을 읽는 길의 시험이 없음.
  - M15 밀린 봉 안내 글을 옛 글(`restart --market kr → start`, 인자 빠짐)로: pytest 전체 통과 — 6c C-28 참고로 고친 글을 지키는 시험이 없음.
- **고칠 방법**: (1) 가짜 출처 이름을 "종목군 6개 중 3개 + 종목군 밖 10개"로 주고 `notes` 에 `"종목 이름 3/6"` 단언(M10·M11). (2) `_clean_name("A\x1b[31mB\x00C")` 가 `"A [31mB C"` 처럼 제어 글자가 빈칸이 되는지(M07). (3) `names` 칸에 `"X\nY"` 를 직접 쓴 종목군 파일을 `read_universe_names` 로 읽어 `"X Y"`(M09). (4) 종료 코드 6 시험에 `"--confirm kr --reason backlog"` 가 글에 있는지(M15).

### D-7 · 경미 · B-7 남음 — start 가 인터넷에서 멈췄을 때의 안내가 없고, "Ctrl-C 하지 마세요"가 모든 명령에 걸리게 읽힌다

- **위치**: `h1_data.universe_names`(FDR 안 `requests.get` timeout 없음, 바뀌지 않음), 안내서 §3 머리 67행.
- **무엇이 틀렸나**: 67행 "걸리는 시간(대략): pytest 4분, 지킴이 5분, 재현 8분. 멈춘 것처럼 보여도 Ctrl-C 하지 마세요." 는 앞 셋을 두고 한 말이지만 문장만 보면 start 에도 걸린다. start 가 위키백과·시세 받기에서 멈추면 초보는 끝없이 기다린다. start 는 Ctrl-C(130) 해도 종목군·장부를 아직 안 썼고 남은 `<시장>.starting` 폴더는 다음 start 가 지우므로 안전하다(`_start_locked`).
- **고칠 방법**: "pytest·지킴이·재현은 멈춘 것처럼 보여도 Ctrl-C 하지 마세요. **start 가 5분 넘게 새 글 없이 멈추면** Ctrl-C 하고 다시 쳐도 돼요(아직 아무것도 고정되지 않았어요)." (코드로는 6b B-7 의 `socket.setdefaulttimeout` — 선택.)

### D-8 · 경미 · 11절 "'우연이 아니다'의 기준 95%" 는 R2 보다 세게 말하고, "한 번의 과거 시험"이 빠졌다 (B-6 을 고치며)

- **위치**: `h1_report.py` 1683~1686행.
- **무엇이 틀렸나**: R2 REPORT 35행 "95% 이상이어야 **약한 근거**다", 186행 "95%에 못 미치고, 여러 칸 중 하나라 우연일 수 있다". 새 글 "무작위보다 낫지만 '우연이 아니다'의 기준 95% 에는 못 미침"은 "95% 를 넘으면 우연이 아니다"로 읽혀 R2 보다 세다. 또 옛 글의 "시장마다 다르고 한 번의 과거 시험이다"가 빠졌다(6b 가 "맞는 것"으로 든 문장).
- **고칠 방법**: "…국내 88%(무작위보다 낫지만 R2 가 '약한 근거'로 본 95% 에는 못 미침)였다(수익률이 아니라 순위, 한 번의 과거 시험)." 시험 단언 `"95% 에는 못 미침"` 은 그대로 둘 수 있게 끝말을 맞춘다. `h1_report.py` 는 코드 지문에 들어가므로 **재현·태그 전에**.

### D-9 · 경미 · §9.2 표 안 명령 — 그대로 붙이면 안 되고, 주소는 따옴표가 필요하며, 되돌릴 수 없다는 말이 없다

- **위치**: §9.2 표(421~423행).
- **무엇이 틀렸나**: (가) 표 칸 명령은 `h1.py corp-action …` 으로 시작한다(앞 문단에 python 경로를 붙이라고 했지만 표에서 복사하면 `command not found`). (나) `<효력일>`·`<공시 주소>`·`<근거>` 를 그대로 붙이면 `<` 가 셸의 입력 돌리기라 오류. (다) 공시 주소에는 대개 `?`·`&` 가 있다(KIND 등). 따옴표 없이 치면 zsh 는 `no matches found` 로 안 돌고(안전), bash 라면 `&` 에서 잘린 주소로 **뒤에서 실행된다**. (라) `--split` 은 장부를 바로 바꾸고 되돌리는 명령이 없다(`--cancel-delist` 같은 것이 split 에는 없음, `h1.py corp-action -h`). §9.3·§13 과 달리 경고가 없다.
- **고칠 방법**: 표 아래에 상자 하나: `cd /Users/나/claude-stock-h1` / `P=/Users/나/.venv-h1/bin/python` / `$P h1.py corp-action --market kr --code 005930 --split 50 --date 2026-12-01 --source "https://…"`, 설명 "주소는 꼭 큰따옴표 안에. **장부가 바로 바뀌고 되돌리는 명령이 없어요** — 치기 전에 Claude Code 에 공시와 이 줄을 보여 주고 확인받기."

### D-10 · 경미 · §7 "나중에 다시 만들어도 2~9절 숫자가 같아요" — 9절은 바뀔 수 있다

- **위치**: §7 337행(옛 문서부터 있던 문장, 6c 가 안 짚음).
- **무엇이 틀렸나**: 9절(A0 현금 + 단기금리 이자)은 보고서를 만들 때 가진 금리로 다시 계산하고, 보고서 자체가 "국내 월 금리는 발표가 1~2달 늦어 이월값이 섞이고, 나중에 다시 만들면 바뀔 수 있다"고 적는다(`h1_report.py` 2025~2026행).
- **고칠 방법**: "2~8절 숫자는 같아요. 9절(A0+이자)은 그사이 새 금리가 나오면 조금 바뀔 수 있어요."

### D-11 · 경미 · 위에서부터 따라 하면 start(§5)를 한 뒤에야 리허설(§10, "start 전에")을 만나고, §5 상자 앞에 "되돌릴 수 없음" 경고가 없다

- **위치**: §0 순서(18행), §5, §10.
- **무엇이 틀렸나**: §0 순서 "준비 → launchd → 시작 → status → 보고서"에 리허설이 없고, D-6 표에만 "권장(§10)". 초보가 위에서부터 그대로 하면 리허설 없이 start 한다. 또 §9.3·§13 은 상자 **위**에 경고가 있는데, 한 번 하면 63봉 창이 시작되고 다시 못 하는 §5 start 상자 앞에는 없다(시각이 틀리면 거절 8 로 안전하지만, 준비가 덜 된 채 시작하는 것은 못 막음).
- **고칠 방법**: §5 맨 위에 "> **start 전에**: 리허설(§10)을 할 거면 지금 먼저 해요. start 는 한 번 성공하면 그 시장의 63봉 창이 시작되고, 정해 둔 사유(§9.3) 없이는 다시 못 해요." §0 순서에 "(권장) 리허설 §10 → 시작".

### D-12 · 경미 · §3.5 "그런 일이 잦으면 알려 주세요" — 새 `reply_code` 칸으로 세는 법이 안내서에 없다 (B-5)

- **위치**: §3.5 132행.
- **고칠 방법**: §6 에 한 줄: `grep -c '"reply_code":"' /Users/나/claude-stock-h1/state/h1/analyst_cache_kr.jsonl` — "0 이 아니면 팀장이 코드에 이름을 붙여 답한 횟수예요(판정은 살렸어요). 많으면 알려 주세요." (`null` 은 `"reply_code":null` 이라 안 셈.)

### D-13 · 경미 · 작은 문장들

| 위치 | 지금 | 고칠 것 |
|---|---|---|
| 설계 §3.7 표 `universe/<m>.json` 줄 | "start 일지에 '종목 이름 n/N'" | "이름이 모자랄 때만 start 일지에 …" (코드는 n<N 일 때만 남김) |
| 안내서 §3.7-3 | "KS200 줄: 맨 아래 날짜가 어제(22:30 뒤면 오늘)" | "가장 최근 거래일(월요일·휴장 뒤면 그 전 평일, 22:30 뒤면 오늘)" — 월요일에 하면 금요일이 정상 |
| 안내서 §4 | start 전 종료 코드 8 알림이 정상 | 한 시장만 먼저 시작할 거면 "그 시장 plist 만 load"(아니면 다른 시장 알림이 주 5~6번씩 몇 주 — 알림을 무시하는 버릇이 생김) |
| 안내서 §4.2 | `kickstart` 바로 다음 줄 `tail` | "몇 초 뒤 `tail`"(kickstart 는 기다리지 않음) |
| 안내서 §7 보관 2번 | "보고서를 …/reports/h1-forward/ 에 복사" (명령 없음) | `mkdir -p /Users/나/h1-reports-git/reports/h1-forward && cp /Users/나/claude-stock-h1/state/h1/reports/*.md /Users/나/h1-reports-git/reports/h1-forward/` |
| 안내서 §13 "판정 창을 포기" | "위처럼 끄고" (위 상자는 국내 plist 하나) | "그 시장 plist 를 `unload -w`" |
| README H1 머리 | "`team.py`·`analyst.py`·`paper_wallet.py`·`screener.py` 에는 H1 용 갈고리·함수만 더했고" | `paper_wallet` 은 보유 수량 소수·`sell(tax_rate=)` 처럼 **바꾼 곳**도 있음 → "갈고리·함수를 더하고 몇 곳을 넓혔지만" (동작이 같다는 말은 맞음, 선택) |
| 설계 §8.1·§8.3(`docs/h1-forward-design.md` 1150~1215행) | 6c 이전 안내 그대로: 상자 안 `# 설명`, start 뒤에 launchd, 국내 start "22:30 KST 뒤", `python3.13 -m venv`(어느 3.13 인지 모름), `caffeinate` 없는 plist, `sudo pmset repeat … 07:00:00` 무조건(운영 09:00 덮어씀) | §8 머리에 "맥에서 따라 할 순서·명령은 `docs/h1-forward-run.md` 가 최신(검토 6c·6d 반영). 이 절은 설계 때 메모라 다를 수 있음" 한 줄. 설계 문서 sha 는 start 때 고정되므로 **태그 전에** |
| `docs/h1-intent-check.md` 맨 위 | 안내 없음(HEAD 에도) | "Q4 는 9189216·156d41a·0267d10 에서 반영" 한 줄(6b B-8, 선택) |

---

## 4. 문제 없음으로 본 것 (근거)

1. **운영 동작**: 이 범위의 운영 파일 변경은 `analyst.py` 17행 docstring 한 줄. `git diff b0e003d 4107136 --stat` 에 `team.py`·`screener.py`·`main.py`·`markets.py`·`paper_wallet.py`·`order_runner.py`·`prompts/` 없음. 복사본 pytest 전체 942 통과(골든 바이트 비교 포함).
2. **`_reply_item` 의 엉뚱한 연결**(§0): 정확한 열쇠 먼저 → 맨 앞 낱말이 코드와 대소문자 무시로 **완전히 같고** 그런 열쇠가 하나일 때만. 국내 6자리 숫자는 접두어 관계 없음, 미국 코드는 대문자 고유. 바뀐 반환값 `(item, 열쇠)` 를 쓰는 곳은 `_ask_and_record` 하나(다른 호출 없음, grep). 겹침이 넓어진 것(정확한 열쇠 값이 null 이고 이름 붙은 열쇠가 또 있을 때 폴백)은 `analyst` 가 답을 `{it["code"]: it}`(값은 늘 dict, `code` 가 숫자·null 이면 열쇠가 글자가 아니라 건너뜀)로 만들어 실제로는 생기지 않음.
3. **`reply_code` 칸**: 판정 기록 줄에 칸 하나 더함. `h1_check`·`h1_report`·`h1_replay` 어디도 판정 기록의 칸 집합을 엄격히 보지 않음(grep), L18 은 열쇠 중복만. 재현 모드는 늘 null. 장부 지문(`ledger_fingerprint`)에는 판정 기록이 안 들어감.
4. **이름 정리**: `_universe_blob` 이 종목군 코드만 돌며 정리 → 종목군 밖 이름이 안 남음(M12 잡힘), start 봉은 blob 을 다시 읽은 정리된 이름, run 은 `read_universe_names`(읽을 때 또 정리). 이름은 장부 계산·점검에 안 들어감. 미국 이름 열쇠와 종목군 코드는 같은 FDR 표의 같은 칸에서 나옴(`zip(Symbol, Name)`).
5. **start note**: `n_named` 는 정리 뒤 blob 의 이름 수(종목군 안만). `log.note` 는 화면 `※` 와 끝 줄 `notes` 둘 다. 국내 실제 운영은 `KR_UNIVERSE` 32/32 라 note 안 남(가짜 자료 시험에서만 "0/6" 이 보이는데, 국내는 Leader 가 `KR_UNIVERSE` 로 채우므로 note 의 "코드만 가요"는 국내에는 맞지 않음 — 실제로는 안 나오는 글이라 문제 삼지 않음).
6. **밀린 봉 안내 글**: `python h1.py restart --market kr --confirm kr --reason backlog --note "…" → start(그 시장 start 시각에)` — `shlex` 로 나누면 restart 인자 모양 그대로, `_restart_evidence` 의 backlog 근거(종료 코드 6 기록)와 맞음(탐침).
7. **11절**: R2 REPORT 35·36·37·184·186행과 대조 — 정의·12%·16%·88%·95% 맞음(말 하나는 D-8).
8. **안내서 명령·값**: §3.4 지문 비교 줄을 복사본에서 그대로 쳐서 `같음` 확인. plist 셋 `plistlib` 로 읽힘(Label·로그 모두 다름, 시각이 §4 표와 같음, `caffeinate` 바깥). `analyst_cache_<시장>.jsonl`·`kr-final-<S>.md`·`logs/h1-kr.log`·`state/h1/claude_cwd` 이름이 코드와 같음. start 전 `run` = 종료 코드 8 + 로그 "장부가 없어요 … 장부 없음(start 필요)" (탐침) — §4.2 말과 맞음. status 줄 모양(재시작·마감·⑩·⑥·A0/A1)이 탐침 출력과 같음. 미국 start 시각 07~22시 KST 는 겨울·여름 모두 16:15 ET 뒤·09:30 ET 전.
9. **운영 쪽**: 운영 폴더에서 치는 명령은 `git fetch origin --tags`·`git worktree add/remove`(옆 폴더만)뿐, 브랜치·장부를 바꾸는 지시 없음. `pmset` 은 운영 09:00 이 있으면 바꾸지 말라고 함. 지우는 plist 는 이름을 하나씩 적음(운영 `com.claude-stock.kr-…`·`us-…` 안 걸림).
10. **`§n` 참조**: 안내서 안 절 참조(설계 문서 쪽 §2.2·§10 빼고 약 35곳, 줄마다 앞뒤 글로 확인) 모두 새 번호와 맞음(§1·§3.3·§3.4·§3.5·§3.7·§4·§4.2·§5·§6·§7·§9.1·§9.2·§9.3·§10·§11·§13). 다른 문서가 안내서 절을 가리키는 곳은 README "§1"·"§3", `docs/h1-guide/07-오류노트.md` "§3.5" — 모두 맞음. `docs/작업-이어가기.md` §6, `docs/h1-intent-check.md` §3.3 가리킴도 맞음.
11. **pytest 수**: 942(문서와 같음). `git fetch origin --tags`(§3.3)는 기본 refspec 의 가지도 함께 받으므로 §3.4 에서 pytest 가 R2 ref 를 보고 재현 시험까지 돈다(그래서 pytest 를 R2 fetch 앞에 둬도 수가 맞음, 단일 가지 clone 이 아니라면).

---

## 5. 직접 해 본 것

모두 `/tmp/claude-0/-home-user-claude-stock/c800b693-7b7e-5a25-8de4-2f198a802ec7/scratchpad/review6d/` 아래, `~/.venv-h1/bin/python`(3.13.18), PATH 맨 앞에 가짜 `claude`.

- `repo/`: 4107136 로컬 clone + R2 ref 로컬 fetch. pytest 전체 **942 통과**(250초).
- 탐침 `repo/tests/test_zz_probe6d.py`(복사본에만): start 전 run → 8, start → 4봉 → status·`window_counts`, 밀린 봉 안내 글 → `shlex`.
- `blocks.py`(상자 검사), `plists.py`(plist 셋 읽기), `icloud.py`(§6 한 줄을 넣은 plist → `ExpatError`, `xmllint` 도 실패).
- 긴 경로(약 295자) 사본 둘: 재현 하네스 오류 글 시험 — 고친 코드 통과 / 옛 코드 실패(확인 뒤 지움).
- 돌연변이 `mut/`(관련 시험 → 통과하면 전체):

  | # | 바꾼 것 | 결과 |
  |---|---|---|
  | M01 | `_reply_item` 앞글자만(`startswith`) | 잡음 |
  | M02 | `.` 에서도 자름 | 잡음 |
  | M03 | 대소문자 구별 | 잡음 |
  | M04 | `k.strip() != code` 되살림 | 잡음 |
  | M05 | `reply_code` 늘 null | 잡음 |
  | M06 | `reply_code` 늘 찾은 열쇠 | 잡음 |
  | M07 | `_clean_name` 의 인쇄 못 하는 글자 바꾸기 없앰 | **전체 942 통과** |
  | M08 | 60자 자르기 없앰 | 잡음 |
  | M09 | `read_universe_names` 정리 없앰(옛 거르기) | **전체 942 통과** |
  | M10 | 이름 note 를 0개일 때만 | **전체 942 통과** |
  | M11 | 이름 수를 `len(u_names)`(종목군 밖 포함) | **전체 942 통과** |
  | M12 | 종목군 파일에 정리 없이 씀 | 잡음 |
  | M13 | 겹쳐도 첫 것 | 잡음 |
  | M14 | 11절 옛 정의 | 잡음 |
  | M15 | 밀린 봉 안내 글을 옛 글로 | **전체 942 통과** |
  | M16 | 정확한 열쇠 먼저 보기 없앰 | 잡음 |
  | M17 | 11절 "95% 에 못 미침" 없앰 | 잡음 |
  | N18 | `universe_names` 가 `t["Security"]`(6b m08) | 잡음 |
  | N19 | `live_source` 가 `names=` 안 넘김(6b m09) | 잡음 |

- 저장소: `git status` 에 이 파일 말고 내 변경 없음, 저장소에 `state/` 없음, 가짜 claude 호출 기록 없음.

---

## 6. 쉬운 말 요약

- 지난 두 검토(6b 코드 9건, 6c 안내서 28건)는 **거의 다 고쳐졌다.** 코드 쪽 6건·안내서 쪽 24건은 완전히, 나머지는 일부만이다. 운영(진짜 쓰는 프로그램)은 한 글자도 동작이 안 바뀌었고, 시험 942개가 모두 통과한다.
- **팀장 판정이 엉뚱한 종목에 붙는 길은 없다.** `GOOG`↔`GOOGL`, `A`↔`AAPL` 같은 "앞글자만 같은" 경우를 이제 시험이 막는다. 답에 이름이 붙어 와도 찾아 쓰고, 그랬다는 사실(`reply_code`)도 기록에 남는다.
- 안내서는 맥 초보가 따라 하기 훨씬 좋아졌다: 상자 안 `#` 없음, 모든 H1 상자가 `cd`·`P=` 로 시작, 자동 실행을 start 보다 먼저, 재시작·지우기 앞에 굵은 경고, 운영 폴더·운영 장부를 바꾸는 지시 없음, plist 세 개가 모두 올바른 파일.
- **꼭 고칠 것 하나(중요, D-1)**: "휴대폰으로 매일 상태 보기" 한 줄을 안내대로 plist 에 넣으면, 그 줄의 `2>&1` 때문에 plist 파일이 깨진다. 그러면 다음에 맥을 다시 켤 때 매일 자동 실행이 **알림도 없이** 안 돌고, 5거래일이 지나면 판정 창이 실패한다. `2>&1` 을 빼고, 고친 뒤 `plutil -lint` 로 확인하라는 줄을 붙이면 된다.
- **고치면 좋은 것 둘(보통)**: (D-2) python.org 파이썬은 설치 뒤 "Install Certificates" 를 한 번 눌러야 인터넷 금리 받기가 된다 — 안 하면 보고서의 'A0+이자'가 조용히 옛 금리로 계산된다. 기본 설치가 터미널의 `python3` 를 바꿔 운영 쪽에 닿을 수 있으니 설치 전후로 운영 venv 를 확인하자. (D-3) 판정 창 중 라이브러리를 올렸다가 재현이 실패해 되돌릴 때, 코드만 되돌리면 매일 "종료 코드 3"이 난다 — `pip install` 을 한 번 더 쳐야 한다.
- 나머지 10개는 작은 것이다: 이름을 못 받았다는 알림의 뜻 적기(또는 start 거절), 시험 몇 줄 더(이름 수 note·제어 문자·밀린 봉 글), start 가 인터넷에서 멈출 때 Ctrl-C 해도 된다는 말, 보고서 한 문장(95% 의 뜻), 분할 명령의 따옴표·경고, "2~9절 같음" 문장, 리허설을 start 앞에, `reply_code` 세는 법, 작은 문장들.
- D-5(start 거절을 고른다면)·D-6·D-8 은 코드(시험·보고서)를 고치는 일이라 **재현·태그 전에** 해야 한다. 설계 §8 머리 한 줄(D-13 표)도 설계 문서 지문이 start 때 고정되므로 태그 전에. 나머지는 운영 안내서만 고치면 된다.

---

## 부록: 작업 메모 (진행하며 적은 것, 그대로 둠)

- (메모 1) 복사본 `review6d/repo` = 4107136 checkout(로컬 clone) + R2 ref 로컬 fetch. 코드 변경 파일: `h1.py`(`_reply_item`·`reply_code`·`NAME_MAX`·`_clean_name`·`_universe_blob`·`read_universe_names`·start 의 이름 수 note·밀린 봉 안내 글), `h1_replay.py`(하네스 오류 글 앞 600 + 뒤 600), `h1_report.py`(11절 R2 정의), `analyst.py`(머리말 한 줄). `h1_data.py` 는 **안 바뀜**(B-1 의 "실패 사유를 돌려주기"·B-7 timeout 은 코드로 안 함).
- (메모 2) 이름 흐름: start 는 `_universe_blob` 이 정리한 `names` 를 Leader 에 넘김(정리 전 원본이 아님 — 좋음), run 은 `read_universe_names`(읽을 때 한 번 더 정리). 국내는 `KR_UNIVERSE` 로 빈 이름을 채움(상수라 정리 불필요). `_build_prompt_h1` 자체에는 정리가 없음(B-3 의 "방어 한 번 더"는 안 함 — 들어오는 두 길이 모두 정리돼 있어 실해 없음).
- (메모 3) B-6: R2 REPORT 35행 "95% 이상이어야 **약한 근거**", 186행 "95%에 못 미치고, 여러 칸 중 하나라 우연일 수 있다". 새 11절 "'우연이 아니다'의 기준 95%" 는 R2 보다 세게 말함. 또 옛 문장의 "시장마다 다르고 한 번의 과거 시험이다" 가 빠짐.
- (메모 4) B-8: 설계 §3.7 표·DataSource 스케치·analyst 머리말·시험 지도(9개 이름 모두 실제 시험과 일치 확인)는 이 범위에서 고침. `docs/작업-이어가기.md`·`docs/h1-intent-check.md` 는 이 범위(…4107136)에서 안 바뀜 — 뒤 커밋 8f4e63c(대상 밖)에서 손댐. 참고: 8f4e63c 는 이 검토 파일의 첫 뼈대(10줄)도 함께 커밋했다(진행 담당 스냅샷).
- (메모 5) 고치지 않은 복사본 pytest 전체: **942 통과**(250초, R2 ref 있음). 가짜 claude 호출 기록 없음. 문서의 "942개" 와 같음.
- (메모 6) 코드 상자 27개 검사(스크립트): 상자 안 `#` **0개**. h1 명령이 든 상자는 모두 `cd /Users/나/claude-stock-h1` 로 시작하고, `$P` 를 쓰는 상자는 모두 `P=` 를 먼저 둠(§6·§11 상자는 절대 경로 python). 표 안 명령(§9.2)·글 안 한 줄(§6 휴대폰)은 상자가 아님.
- (메모 7) plist 세 개(국내·미국·보고서) `plistlib` 로 읽힘. 시각: 국내 월~금 23:05 + 월~토 07:40, 미국 화~토 07:10 + 월~토 08:40, 보고서 매달 2일 09:30 — §4 표와 같음. Label·로그 경로 모두 다름. `caffeinate` 가 셸 바깥(C-13 대로).
- (메모 8) **§6 "휴대폰으로 보기" 한 줄을 안내대로 plist 의 `exit $c` 앞에 넣으면 plist 가 깨진다**: 그 줄의 `2>&1` 의 `&` 가 XML 에서 금지 글자. `plistlib`: `ExpatError not well-formed (invalid token)`, `xmllint`: `xmlParseEntityRef: no name`. 이미 load 된 작업은 다음 로그인·재시동 때 이 파일을 못 읽어 **조용히 안 돈다**(알림도 안 뜸 — 셸이 아예 안 뜸) → 늦은 봉 → 5거래일 넘으면 창 실패. → D-1 로.
- (메모 9) 탐침 `review6d/repo/tests/test_zz_probe6d.py`(복사본에만): start 전 run 두 번(종료 코드 8, 화면 "거절: kr 장부가 없어요 … → 먼저 python h1.py start") 뒤 start → 4봉 run → status·window_counts 에 start 전 실행이 안 섞임(관문 거절 0·늦은 봉 0·자료 멈춤 0). §4 "launchd 먼저" 순서는 안전. 밀린 봉 안내 글(`… restart --market kr --confirm kr --reason backlog --note "…" → start(…)`)을 shlex 로 나누면 restart 인자로 맞는 모양이고, `_restart_evidence` 의 backlog 근거(종료 코드 6 기록)와 맞음.
- (메모 10) 6b §4 참고(재현 하네스 오류 글이 긴 경로에서 잘림) 고침 확인: 경로 길이 약 295자 복사본에서 `test_하네스는_모듈이_임시_폴더_밖에서_읽히면_멈춤` — 고친 코드 **통과**, `[-600:]` 로 되돌린 코드 **실패**. 고쳐짐.
- (메모 11) `h1_report.fetch_rates` 는 FRED 를 **표준 `urllib`** 로 받는다(`requests` 아님). C-12 고침으로 파이썬을 python.org 설치 파일로 정했는데, python.org 맥 파이썬은 설치 뒤 `Install Certificates.command` 를 돌리지 않으면 `urllib` 의 https 가 인증서 확인 실패한다(알려진 동작 — 이 컨테이너에서는 맥이 아니라 직접 못 봄). `fetch_rates` 는 모든 예외를 "오프라인"으로 삼켜 화면에 `[금리] … 받기 실패 → 저장본 …` 한 줄만 남기고 옛 금리를 이월 → 보고서 'A0+이자'(참고값)가 조용히 낡음. FDR(시세·S&P500 표)은 `requests`+certifi 라 영향 없음. → D-2 로.
- (메모 12) B-7(start 때 위키백과 받기 timeout 없음): 코드 안 고침, 문서에도 "start 가 1분 넘게 멈추면" 안내 없음. 오히려 §3 머리 "멈춘 것처럼 보여도 Ctrl-C 하지 마세요" 가 모든 명령에 걸리는 말처럼 읽힘.
- (메모 13) §9.1 허용 변경: "재현이 0 이 아니면 `git checkout h1-forward-v1` 로 되돌리고" — 라이브러리 올림(`pip install`)을 한 뒤라면 코드만 되돌아가고 venv 는 새 버전 그대로다. 관문의 환경 지문(`env_info`: 파이썬 + pandas·numpy·ta·FinanceDataReader 버전)이 옛 통과 기록과 달라 **매 실행 종료 코드 3** → 봉이 안 쌓여 늦은 봉 → 5거래일 넘으면 창 실패. 되돌릴 때 `$P -m pip install -r requirements-h1.txt` 를 한 번 더(옛 태그의 고정 버전으로 내림) 쳐야 한다. → D-3 로.
- (메모 14) §7 "같은 달 보고서는 나중에 다시 만들어도 **2~9절** 숫자가 같아요" — 9절(A0 현금 + 단기금리 이자)은 보고서를 만들 때 가진 금리로 다시 계산하고, 보고서 자체가 "국내 월 금리는 발표가 1~2달 늦어 … 나중에 다시 만들면 바뀔 수 있다"고 적는다(h1_report 2025행). 옛 문서부터 있던 문장(6c 가 안 짚음). 경미.
- (메모 15) 맞게 확인: `.gitignore` 에 `state/`·`*.log`·`__pycache__/` → H1 폴더 `git status --short` 는 pytest·logs 뒤에도 깨끗(복사본에서 확인, pytest 캐시는 자체 .gitignore). `reports/` 는 무시 대상이 아니라 §7 보관 2번 `git add reports/h1-forward` 가 된다. 최종 보고서 이름 `<시장>-final-<S>.md`(`h1_report.report_name`) = §11. `docs/broker-run.md` 100행 깨우기 `MTWRF 09:00:00` = §3.6 말과 같음. `docs/작업-이어가기.md` §6 에 운영 쪽 확인 두 가지 있음(§3.7 가리킴 맞음). 다른 문서·코드가 운영 안내서 절 번호를 가리키는 곳은 `docs/h1-guide/07-오류노트.md` 의 "§3.5" 하나 → 새 번호에서도 §3.5(claude 시험) 맞음.
- (메모 16) 돌연변이(`review6d/mut/`, 관련 시험 = `test_h1_modules.py`·`test_h1_runner.py`·11절 시험): **잡힘** — M01 앞글자만(`startswith`, 6b m01), M02 `.` 에서도 자름(6b m13), M03 대소문자 구별, M04 `k.strip() != code` 되살림, M05 reply_code 늘 None, M06 reply_code 늘 열쇠(정확해도), M08 길이 자르기 없앰, M12 종목군 파일에 정리 없이 씀, M13 겹쳐도 첫 것, M14 11절 옛 정의, M16 정확한 열쇠 먼저 보기 없앰, M17 "95% 에 못 미침" 없앰. **관련 시험 통과 → 전체도 통과(메모 20)** — M07 제어 문자 바꾸기 없앰(줄바꿈은 `split()` 이 이미 처리하므로 시험 입력 `\n`·`\t` 로는 구별 안 됨), M09 `read_universe_names` 의 정리 없앰(파일은 이미 정리돼 있어 방어용), M10 이름 note 를 0개일 때만, M11 이름 수를 종목군 밖 이름까지 센 수(`len(u_names)`, 미국 표 503개 → 이름이 빠져도 note 가 **절대 안 남음**), M15 밀린 봉 안내 글을 옛 글로.
- (메모 17) 돌연변이 전체 결과(중간): M07·M09·M10 은 pytest **전체 942 통과**. N18(`t["Security"]`)·N19(`live_source` 가 names 안 넘김)은 `test_Q4_이름_받기_universe_names_와_live_source` 가 잡음(6b B-2 의 m08·m09 고쳐짐). M15 는 `grep -v log` 실수로 첫 묶음에서 빠져 따로 돌림(관련 시험 162 통과).
- (메모 18) 판정 기록 줄은 `separators=(",", ":")` — 실제 글은 `"status":"ok"`(빈칸 없음). 안내서 §4.2 는 `"status": "ok"`. start(S 봉)도 터미널에서 팀장을 부름(탐침 start 화면 "팀장 LLM 호출 2번") → `tail -3` 의 줄이 launchd 결과가 아닐 수 있음. → D-4.
- (메모 19) `corp-action` 인자에 분할 취소가 없음(`--cancel-delist` 만). 안내서 §9.2 표는 `h1.py …` 로 시작하고 `<…>` 자리표시·따옴표 없는 주소. → D-9.
- (메모 20) 남은 돌연변이 pytest **전체** 결과: M07·M09·M10·M11·M15 모두 **942 통과**(각 약 4분). → D-6.
- (메모 21) 설계 §8.1·§8.3 은 6c 이전 맥 안내(상자 안 `#`, start 뒤 launchd, `pmset … 07:00` 무조건, `caffeinate` 없는 plist) 그대로 — 운영 안내서와 어긋남. 설계 sha 는 start 때 고정 → 태그 전에 "안내서가 최신" 한 줄(D-13 표).
- (메모 22) 끝 확인: 저장소 `git status --short` 는 이 파일 하나, 저장소에 `state/` 없음, `fakebin/calls.log` 없음(진짜·가짜 claude 호출 0).
