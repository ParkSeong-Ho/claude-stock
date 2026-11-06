# 검토 6c — 단계 6 문서(`docs/h1-forward-run.md`·README "H1 포워드 모의매매" 절) 독립 검토

- 검토 대상: 브랜치 `h1-forward` 커밋 156d41a 의 `docs/h1-forward-run.md`, `README.md` H1 절
- 검토자: 독립 검토자(작성자 설명 없음). 2026-11-06.
- 상태: **완성**(치명 0 · 중요 9 · 보통 8 · 경미 11). 번호는 찾은 순서이고, 심한 순서는 맨 아래 "한눈에" 표에 있다.
- 지킨 것: 저장소의 다른 파일은 고치지 않았고 커밋·푸시하지 않았다. 진짜 `claude` 를 부르지 않았다(돌린 것은 모두 PATH 맨 앞에 가짜 `claude`, 또는 직접 만든 가짜 `claude`). 인터넷을 쓰지 않았다. 저장소 안에 `state/` 를 만들지 않았다(끝에 `ls` 로 확인). 직접 돌린 것은 모두 scratch 의 저장소 사본(`review6c/`)·임시 장부 폴더에서 했다.

## 찾은 것 (번호·심함·위치·무엇·고칠 문장)

### C-1 · 중요 · §3.4 "지문 확인" — `tail -1 state/h1/replay_pass.json` 은 `]` 한 글자만 보여 줌
- **무엇이 틀렸나**: `replay_pass.json` 은 한 줄에 하나씩 쌓는 JSONL 이 아니라 **들여쓰기한 JSON 목록**이다(`h1.record_replay_pass` → `_dump(new)`, `[` … `]`). 가짜 자료로 통과 기록을 만들어 보니 파일은 40줄, `tail -1` 의 결과는 `]` 였다. 문서대로 따라 하면 "마지막 줄 code_hash" 를 찾을 수 없다(설계 §8.1 은 `tail` 없이 "replay_pass.json 의 code_hash 와 같아야 함"이라고만 적었다).
- **고칠 문장**(§3.4 코드 블록의 마지막 두 줄을 바꿈):
  ```
  $P -c "import h1, json; now = h1.code_hash()[0]; last = json.load(open('state/h1/replay_pass.json'))[-1]['code_hash']; print(now); print(last); print('같음' if now == last else '다름 — 멈추고 물어보기')"
  ```
  설명 줄: "마지막에 `같음` 이 나오면 됩니다."

### C-2 · 중요 · §4 끝 "`runs.jsonl` 마지막 줄의 `cli_version`" — 그런 칸이 없음
- **무엇이 틀렸나**: `runs.jsonl` 의 줄(시작·끝)에는 `cli_version` 칸이 아예 없다(`_RunLog.begin`·`end_record` 의 칸: at·bars·code_hash·command·commits·env·event·exit_code·late_bars·market·meaning·message·mode·notes·problems·run_id·start_date). 가짜 자료로 start→11번 run 을 돌린 뒤 `runs.jsonl` 에서 `cli_version` 은 0번 나왔다. `cli_version` 과 팀장 호출 결과(`status`: ok / no_claude …)는 **판정 기록 `state/h1/analyst_cache_<시장>.jsonl`** 에만 적힌다(`Leader`, h1.py 641줄 부근). 그래서 문서대로 보면 늘 "비어 있음"으로 보여 "launchd 에서 claude 를 못 찾았다"고 잘못 판단하게 된다(검토 4 목록 3 의 문장을 그대로 옮긴 것으로 보임).
- 또 `launchctl kickstart` 로 돌려도 **새 확정 봉이 없으면**(이미 처리됨) `claude --version` 도 `claude -p` 도 부르지 않는다(`_cli_version_once` 는 처리할 봉이 있을 때만). 매수 후보가 없는 날도 팀장을 부르지 않는다. 즉 kickstart 한 번으로는 확인이 안 될 수 있다.
- **고칠 문장**: "launchd 로 **처음 새 봉을 처리한 다음 날** `tail -3 state/h1/analyst_cache_kr.jsonl` 을 봐요. `"status":"ok"` 이고 `"cli_version"` 에 `2.x.x (Claude Code)` 같은 글자가 있으면 OK. `"status":"no_claude"` 면 launchd 의 PATH 에 claude 폴더가 없는 것(§3.5 로 돌아가 PATH 고치기). 파일이 없거나 줄이 안 늘었으면 그날은 매수 후보가 없어 팀장을 안 부른 것이니 하루 더 기다려요. `kickstart` 는 '실행이 되는지'(로그 `logs/h1-kr.log` 에 '종료 코드 0')만 보는 용도예요."

### C-3 · 중요 · §8.3 재시작 명령 `--reason L|backlog|rule-change` — 그대로 붙여 넣으면 셸 파이프가 되어 `--reason L` 로 바로 실행됨
- **무엇이 틀렸나**: `|` 는 셸에서 "파이프"다. 문서의 코드 블록을 그대로 붙여 넣으면 `h1.py restart --market kr --confirm kr --reason L` 이 실행되고, `backlog`·`rule-change` 는 "command not found" 로 끝난다. 직접 돌려 봄(scratch 사본, 장부 없음): 화면 `backlog: command not found`, `rule-change: command not found`, `PIPESTATUS=8 127 127`, `runs.jsonl` 에 `"args":{"reason":"L","note":null,"confirm":"kr"}` — 즉 **사유 L·설명 없이 restart 가 실제로 불렸다.** 장부가 있고 L 근거가 일지에 있으면 그대로 시장 폴더가 보관 폴더로 옮겨지고 재시작 횟수 1 이 쓰인다(되돌릴 수 없음, 상한 2번). restart 는 "정말 할까요?" 같은 확인을 묻지 않는다.
- 문서에 "이 명령은 바로 실행되고 되돌릴 수 없다"는 경고도 없다.
- **고칠 문장**(§8.3 코드 블록):
  ```
  cd /Users/나/claude-stock-h1
  /Users/나/.venv-h1/bin/python h1.py restart --market kr --confirm kr --reason L --note "무슨 일이었는지"
  ```
  그리고 바로 위에 "**`--reason` 뒤에는 `L`, `backlog`, `rule-change` 중 하나만 적어요**(셋을 `|` 로 이어 쓰면 안 됨). **이 명령은 묻지 않고 바로 실행되고 되돌릴 수 없어요**(재시작 1번을 씀). 치기 전에 Claude Code 에 로그를 보여 주고 사유가 맞는지 먼저 확인하세요." 부록 A 의 `--reason …` 줄에도 "(셋 중 하나)"를 붙인다.

### C-4 · 중요 · §3.3·§3.4·§3.5·§3.8·§6 코드 블록 — 줄 끝 `# 설명` 이 맥 기본 셸(zsh)에서는 주석이 아님
- **무엇이 틀렸나**: 맥 터미널의 기본 셸 zsh 는 대화형으로 친 줄에서 `#` 를 주석으로 보지 않는다(`INTERACTIVE_COMMENTS` 옵션이 기본으로 꺼져 있음. 이 컨테이너에는 zsh 가 없어 직접 돌리지는 못했고, 알려진 동작으로 적음). 그래서 `#` 와 그 뒤 한국어 낱말이 **명령의 인자로 붙는다**. 괄호가 섞인 줄(`통과(지금 939개)`·`폴더(그대로 둔다)`·`기준값(R2)`)은 zsh 가 glob 으로 읽어 오류를 낼 수도 있다. 어느 쪽이든 명령이 실패한다.
  - bash 에서 같은 인자를 따옴표로 붙여 직접 재현: `h1_replay.py '#' '약' '8분.'` → `명령 인자 오류 — unrecognized arguments` 종료 코드 9, `h1_report.py --market us --month 2026-12 '#' '그달'` → 종료 코드 9. `git fetch origin research-r2-2026-11-04 '#' …` 는 `#` 를 브랜치 이름으로 받아 실패한다. `cd /Users/나/claude-stock  # 운영 폴더(그대로 둔다)` 는 `cd` 가 실패해 **다음 줄들이 엉뚱한 폴더에서** 돈다.
  - 해당 줄(문서 줄 번호): 72·74(§3.3), 87~91(§3.4 의 `pytest`·`git fetch`·`h1_test_guard`·`h1_replay`·`code_hash`), 101(§3.5 `which claude`), **128·129(§3.8 `start` 두 줄 — 인자 오류 9 로 start 가 안 됨)**, 215(§6 첫 `h1_report.py`). (§4·§6 plist 안의 `sh -c` 글은 sh 가 읽으므로 괜찮음.) 해가 되는 쪽으로 바뀌는 줄은 없고 모두 "실패"로 끝나지만, 초보는 왜 실패하는지 알 수 없다.
- **고칠 문장**: 코드 블록 안의 `# …` 설명을 모두 빼서 블록 **아래 글**로 옮긴다(예: "`pytest` 는 전부 통과해야 해요(지금 939개, 약 4분)"). 그리고 §3 머리에 한 줄: "코드 블록은 한 줄씩 복사해 붙여 넣으세요. 블록 안에는 설명(#)을 넣지 않았어요."

### C-5 · 중요 · §12 "`--force` 는 … state/·logs/ 까지 지워요" / §9 리허설 지우기 — `--force` 가 없어도 state/ 는 지워짐
- **무엇이 틀렸나**: scratch 의 빈 git 저장소로 직접 확인(git 2.43): 태그로 worktree 를 만들고 git 이 무시하는 `state/h1/x.json`·`logs/h1.log` 만 넣은 뒤 **`--force` 없이** `git worktree remove` → 종료 코드 0, **폴더 전체(state/·logs/ 포함)가 지워졌다.** `--force` 가 필요한 경우는 "무시되지 않는 새 파일이나 고친 파일"이 있을 때뿐이다(예: 보고서를 그 폴더에 복사해 둔 경우 → `fatal: … contains modified or untracked files, use --force`). 지금 문장은 "`--force` 를 안 붙이면 state/ 는 남는다"로 읽혀, 장부를 지키려고 `--force` 만 빼고 치는 실수를 부른다.
- 또 리허설 폴더 이름 `claude-stock-h1-rehearsal` 이 진짜 폴더 `claude-stock-h1` 과 앞부분이 같아 탭 자동 완성·오타로 **진짜 H1 폴더를 지울 수 있다**(되돌릴 수 없음, 판정 창 장부 전부).
- **고칠 문장**(§12): "`git worktree remove` 는 `--force` 가 있든 없든 **그 폴더 전체를 지워요**(`state/` 장부·`logs/` 포함, 되돌릴 수 없음). 보고서·장부를 먼저 다른 곳에 복사한 뒤에만 치세요. `--force` 는 그 폴더에 git 이 모르는 새 파일이 있을 때 필요해요." 이 경고는 지금처럼 코드 블록 **아래**가 아니라 **위**에 둔다(초보는 블록을 먼저 붙여 넣고 아래 글을 나중에 읽음). 블록 첫 줄로 보관 명령 `cp -R /Users/나/claude-stock-h1/state/h1/reports /Users/나/H1-보고서/` 를 넣어도 좋다. §9: 리허설 폴더 이름을 진짜 폴더와 앞부분이 다른 `/Users/나/h1-rehearsal` 로 바꾸고, 지우기 줄 앞에 "**경로가 `h1-rehearsal` 인지 두 번 확인**"을 넣는다.

### C-6 · 중요 · §6 보관 2번 "운영 폴더에서 별도 브랜치(h1-reports)를 만들어 … 커밋·푸시" — 운영 폴더를 건드림
- **무엇이 틀렸나**: (가) 운영 폴더에서 `git checkout -b h1-reports`(또는 `git switch`)를 하면 **운영 폴더의 체크아웃 자체가 바뀐다.** 그 폴더에서 launchd 로 `team.py`·`order_runner.py` 가 돌고 있으므로, 브랜치를 어디서 만들었느냐에 따라 운영 코드가 바뀐 채 돌 수 있고, 원래 브랜치로 돌아오는 것을 잊으면 다음 `git pull` 도 엉뚱한 곳에 된다. (나) 운영 폴더의 `reports/` 에는 증권사 맞춰 보기 보고서 `reports/broker/*.md`(주문번호 포함)가 있고 `docs/broker-run.md` 는 "`reports/` 는 커밋하지 마세요"라고 적었다. 초보가 `git add reports` 나 `git add .` 를 치면 주문번호가 든 파일이 함께 올라간다. 문서에는 정확한 명령도 경고도 없다.
- **고칠 문장**: 2번을 지우거나 이렇게 바꾼다. "2. (git 으로 남기고 싶으면) 운영 폴더의 브랜치는 **바꾸지 말고**, 보고서 전용 폴더를 하나 더 만들어요: `cd /Users/나/claude-stock && git worktree add -b h1-reports /Users/나/h1-reports-git origin/h1-forward` → 보고서를 `/Users/나/h1-reports-git/reports/h1-forward/` 에 복사 → 그 폴더에서 `git add reports/h1-forward && git commit -m '…' && git push -u origin h1-reports`. **`git add .`·`git add reports` 는 쓰지 마세요.**" 그리고 휴대폰이 아이폰이면 "iCloud Drive 의 폴더(파인더 → iCloud Drive)에 복사하면 휴대폰 '파일' 앱에서 바로 보여요"를 1번 옆에 더하면 가장 쉽다(H1 폴더 자체는 iCloud 밖이어야 하지만 보고서 사본은 괜찮음).

### C-7 · 중요 · §3.6 `sudo pmset repeat wakeorpoweron MTWRFS 07:00:00` — 운영의 깨우기 설정을 덮어씀
- **무엇이 틀렸나**: `pmset repeat` 는 "깨우기" 반복 일정을 **하나만** 가진다(문서도 "하나만 둘 수 있어요"라고 적음). 그런데 `docs/broker-run.md` 는 운영 주문(`kr-place` 09:05)을 위해 `sudo pmset repeat wakeorpoweron MTWRF 09:00:00` 을 권한다. 운영에서 이미 그렇게 해 두었다면 H1 문서의 명령이 **그것을 지우고 07:00 으로 바꾼다.** 그러면 07:00 에 깨어 H1 작업을 한 뒤 맥이 다시 잠들 경우, 운영 `kr-place`(09:05 지정가 주문)가 사람이 맥을 열 때까지 밀려 늦게 나간다(`broker-run.md` "늦게 깬 맥" 주의와 같은 문제). 운영을 건드리는 지시인데 경고가 없다.
- 또 07:00 에 한 번 깨워도 아무도 맥을 쓰지 않으면 곧 다시 잠들 수 있어, 07:10(미국)·07:40(국내 보조)·08:40(미국 보조)이 제때 돈다는 보장이 없다(`caffeinate -i` 는 **작업이 도는 동안만** 막음). 미국 봉은 23:30 KST 전에만 처리되면 늦은 봉이 아니라 큰 문제는 아니지만, 국내 23:05 가 실패한 날의 07:40 보조는 09:00 전에 돌아야 한다.
- **고칠 문장**: "① 먼저 `pmset -g sched` 로 지금 깨우기 일정을 봐요. 운영용(예: 09:00)이 이미 있으면 **이 명령이 그것을 바꿔요.** 두 일정은 하나로 합쳐야 해요. ② 가장 쉬운 방법은 맥을 **전원에 꽂아 두고 잠자기를 끄는 것**(시스템 설정 → 배터리(또는 에너지 절약) → '전원 어댑터 사용 시 디스플레이가 꺼져 있을 때 자동으로 잠자기 방지' 켬, 노트북은 덮개를 연 채로). 그다음 `sudo pmset repeat wakeorpoweron MTWRFS 07:00:00` 은 '혹시 잠들었을 때'의 보조예요. ③ 운영 09:05 주문도 같은 맥에서 돈다면 깨우기를 07:00 으로 바꿔도 맥이 09:05 까지 깨어 있어야 해요(①의 잠자기 끔)."

### C-8 · 중요 · §3.7-3 "KS200 캐시가 최근까지 갱신되는지(`docs/kr-fix-s0.md` §5)" — 가리킨 절이 운영 폴더 명령 묶음
- **무엇이 틀렸나**: `docs/kr-fix-s0.md` §5 는 "프로젝트 폴더에서" `git checkout kr-fix-s0` → `git pull` → `python -m pip install -r requirements.txt` → `python -m pytest` → `python kr_halt_check.py` → `python team.py 40 --market kr` 를 차례로 치는 **운영 폴더용 절차**다. KS200 확인은 그 절 맨 끝의 한 줄뿐이다. 초보가 §5 를 처음부터 따라 하면 (가) 운영 폴더를 옛 브랜치 `kr-fix-s0`(맥에 로컬 가지가 남아 있으면)로 바꾸거나 `git pull` 로 운영 코드를 바꾸고, (나) `team.py 40 --market kr` 를 손으로 돌려 **운영 장부(`state/kr/`)에 정해진 시각 밖에서 쓰게** 된다. H1 폴더에서 치면 그 폴더의 태그 고정을 깨서 관문 거절(종료 코드 3)이 된다. 미국 "S&P500 목록 받기가 되는지"도 확인 명령이 없다.
- **고칠 문장**(§3.7-3 을 명령으로 바꿈, H1 폴더에서):
  ```
  cd /Users/나/claude-stock-h1
  /Users/나/.venv-h1/bin/python -c "import FinanceDataReader as f; print(f.DataReader('KS200', '2026-10-01').tail(3))"
  /Users/나/.venv-h1/bin/python -c "import screener; print(len(screener.universe(40)))"
  ```
  "첫 줄: 맨 아래 날짜가 어제(22:30 뒤면 오늘)여야 해요. 며칠 전에 멈춰 있으면 start 하지 말고 물어보기. 둘째 줄: `40` 이 나오면 OK. (`docs/kr-fix-s0.md` §5 의 다른 명령은 운영 폴더용이라 여기서 치지 않아요.)"

### C-9 · 보통 · §3.4·§3.7·§3.8·§6·§8.3·§10 — `$P` 와 "지금 있는 폴더"에 기대는 코드 블록
- **무엇이 틀렸나**: `P=/Users/나/.venv-h1/bin/python` 은 §3.4·§6 블록 안에서만 정해진다. 터미널을 새로 열면 사라지므로 몇 주 뒤 §8.3(재시작)·§10(최종 보고서)·§3.8(start)을 따로 칠 때 `$P h1.py …` 는 `h1.py: command not found` 같은 오류가 된다. 또 §3.4·§3.7·§3.8·§6·§8.3·§10 블록에는 `cd /Users/나/claude-stock-h1` 이 없다. 새 터미널은 홈 폴더에서 열리고, 초보가 운영 폴더에서 치면 **운영 폴더의 `h1.py`(그 폴더가 h1-forward 를 체크아웃하고 있다면)가 운영 폴더 안에 `state/h1/` 를 만들고 그곳에서 start** 할 수 있다(태그 고정·재현 기록과 무관한 엉뚱한 장부).
- **고칠 문장**: 명령이 있는 모든 블록 첫 두 줄을 똑같이 둔다.
  ```
  cd /Users/나/claude-stock-h1
  P=/Users/나/.venv-h1/bin/python
  ```
  그리고 §3 머리에 "H1 명령은 **언제나 `/Users/나/claude-stock-h1` 폴더에서** 쳐요. 터미널 맨 앞에 `claude-stock-h1` 이 보이는지 확인하세요."

### C-10 · 보통 · §12 "잠시 멈춤: `launchctl unload …`" / "완전히 지우기" — plist 파일이 남아 다시 켜짐
- **무엇이 틀렸나**: `~/Library/LaunchAgents/` 에 있는 plist 는 **로그인할 때마다 launchd 가 다시 읽는다.** `launchctl unload` 만 하면 맥을 재시동·다시 로그인했을 때 H1 작업이 저절로 다시 켜진다(잠시 멈춤이 풀리고, 지운 폴더를 가리키는 작업이 매일 실패). "완전히 지우기" 블록도 plist 파일을 지우지 않는다. §9 리허설 plist 도 같다.
- **고칠 문장**: 잠시 멈춤 → "`launchctl unload -w ~/Library/LaunchAgents/com.claude-stock.h1-kr.plist`(`-w` 를 붙여야 재시동 뒤에도 꺼진 채로 있어요. 다시 켤 때는 `launchctl load -w …`)". 완전히 지우기 블록 끝에 `rm ~/Library/LaunchAgents/com.claude-stock.h1-*.plist` 를 더한다(운영 plist 이름은 `com.claude-stock.kr-…`·`us-…` 라 이 패턴에 걸리지 않음 — 문장으로 함께 적기).

### C-11 · 보통 · §6 월간 보고서 plist "§4 와 같은 모양에서 두 곳만 바꿔요" / §4 미국 plist 한 줄 설명
- **무엇이 틀렸나**: 실제로는 **Label**(`com.claude-stock.h1-report`), **파일 이름**, **StartCalendarInterval**, **`sh -c` 명령**, **StandardOutPath·StandardErrorPath**(`logs/h1-report.log`) 다섯 곳 이상을 바꿔야 한다. 초보가 "두 곳만" 바꾸면 Label 이 `com.claude-stock.h1-kr` 그대로 남아 `launchctl load` 가 "이미 있음"으로 실패하거나 국내 작업과 엉킨다. 미국 plist 도 "`--market us`, 화(2)~토(6) 07:10 + 월(1)~토(6) 08:40, 로그 `logs/h1-us.log`" 한 줄 설명뿐이라 Label·알림 글자("H1 국내")·dict 11개를 초보가 직접 고쳐 써야 한다. plist 파일을 무엇으로 만드는지(텍스트 편집기는 기본이 서식 있는 글이라 깨짐)도 없다.
- **고칠 문장**: 미국 plist 와 보고서 plist 를 **전체 그대로** 싣는다(복사해 `나` 만 바꾸면 되게). 보고서 plist 의 명령 칸 예:
  `<string>m=$(date -v-1m +%Y-%m); for k in us kr; do /Users/나/.venv-h1/bin/python h1_report.py --market $k --month $m; done</string>`
  그리고 "plist 파일은 터미널에서 `nano ~/Library/LaunchAgents/com.claude-stock.h1-kr.plist` 로 만들고 붙여 넣은 뒤 Ctrl-O, Enter, Ctrl-X. 다 만든 뒤 `plutil -lint ~/Library/LaunchAgents/com.claude-stock.h1-*.plist` 가 모두 `OK` 인지 확인"을 더한다. (§4 의 국내 plist 는 python `plistlib` 로 읽어 보니 모양이 맞았고, 시각 11개·요일·명령이 표와 같았다.)

### C-12 · 보통 · §3.1·§3.3 파이썬 3.13.18 — 확인 순서가 거꾸로이고, 어떻게 설치하는지가 비어 있음
- **무엇이 틀렸나**: (가) §3.1 의 확인 `/Users/나/.venv-h1/bin/python -V` 는 venv 를 만드는 §3.3 **보다 앞**에 있어 처음 따라 하면 "No such file" 이 난다. (나) §3.3 의 `python3.13 -m venv` 가 어느 3.13 을 집을지 정해지지 않았다(brew 3.13.x 와 python.org 3.13.18 이 같이 있으면 PATH 앞쪽 것). (다) `brew pin python@3.13` 은 **이미 설치된 버전**을 묶을 뿐이라 brew 가 이미 3.13.19 이상이면 3.13.18 을 얻을 수 없다. "방법 하나: python.org 또는 uv/pyenv"는 초보에게 고를 기준·명령이 없다.
- **고칠 문장**: §3.3 의 venv 줄 바로 앞에 `python3.13 -V`(→ `Python 3.13.18` 이어야 함, 아니면 멈춤)를 두고, §3.1 의 확인 줄은 §3.3 블록 끝으로 옮긴다. 설치는 한 가지 길만 적는다(예: "python.org 의 3.13.18 macOS 설치 파일 → 설치 뒤 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -m venv /Users/나/.venv-h1`", 설치 파일이 없으면 진행 담당에게 uv 명령을 받기). brew 줄은 "brew 의 python 으로 venv 를 만들지 마세요(업그레이드 한 번에 종료 코드 3)"로 바꾼다.

### C-13 · 보통 · §4 plist 명령 `caffeinate -i python …; c=$?` — 종료 코드가 python 의 것인지 맥에서 확인 안 됨, 알림 권한
- **무엇이 틀렸나**: 알림은 `c=$?` 가 `h1.py` 의 종료 코드일 때만 맞다. 그런데 이 줄에서 `$?` 는 **`caffeinate` 의 종료 코드**다. `caffeinate` 가 감싼 명령의 종료 코드를 그대로 돌려주는지는 이 컨테이너(리눅스)에서 확인할 수 없고 문서·설계 어디에도 확인 기록이 없다. 만약 늘 0 이면 **알림이 한 번도 안 뜬다.** (scratch 에서 `caffeinate` 자리에 `sh -c 'exit 4'` 를 넣어 보니 나머지 셸 줄은 맞게 동작: 알림 글 "H1 국내 종료 코드 4 (logs/h1-kr.log)", 종료 4.) 또 최근 macOS 는 `osascript` 의 `display notification` 을 '스크립트 편집기' 이름으로 띄우고, 알림 권한이 꺼져 있으면 조용히 안 보인다.
- **고칠 문장**: `caffeinate` 를 셸 바깥에 두어 이 문제를 없앤다: `<string>/usr/bin/caffeinate</string><string>-i</string><string>/bin/sh</string><string>-c</string><string>/Users/나/.venv-h1/bin/python h1.py run --market kr; c=$?; …; exit $c</string>`. 그리고 §4 끝에 "처음 한 번 `osascript -e 'display notification "시험" with title "claude-stock"'` 를 터미널에서 쳐서 알림이 뜨는지 봐요. 안 뜨면 시스템 설정 → 알림 → 스크립트 편집기 → 허용."

### C-14 · 보통 · §3.6·§12 "껐다 켜면/다시 켜면 밀린 봉을 5개까지 따라잡아요" — 따라잡은 봉은 "늦은 봉"으로 셈
- **무엇이 틀렸나**: 다음 장 시작(국내 09:00, 미국 09:30 ET) 뒤에 처리한 봉은 **늦은 봉**이고(설계 §2.5, 팀장 없이 규칙만), 창 전체 10개를 넘으면 그 창은 실패다(사전 등록 ②-2). 문서는 "5개까지 따라잡아요"만 적어, 초보는 "5일 안에만 다시 켜면 괜찮다"고 읽는다. 실제로는 사흘 멈추면 늦은 봉 3개를 쓴다(10개 중).
- **고칠 문장**(§3.6 과 §12 잠시 멈춤 줄 뒤): "따라잡은 봉은 **늦은 봉**으로 세요(팀장 없이 규칙만, 판정 창 전체 10개까지). 그래서 판정 창 동안은 맥을 끄거나 launchd 를 멈추지 않는 게 좋아요. 멈춘 날 수만큼 10개 중에서 빠져요."

### C-15 · 보통 · §8.2 "아직 모르겠음·공시 없음 → 기다림(그날만 멈춤…)" — 기다리는 동안 그 시장 장부 전체가 멈춤
- **무엇이 틀렸나**: D6(분할 의심)은 그 종목만이 아니라 **그 시장 실행 전체**를 멈춘다(종료 코드 4, 장부 6개 모두 저장 안 함). 하루 기다릴 때마다 그 봉은 다음 장 시작 뒤 늦은 봉이 되고, 5거래일 넘게 밀리면 종료 코드 6 → 창 실패다. "그날만 멈춤"·"며칠 넘으면 … 주의"는 시간 압박을 너무 약하게 말한다. 또 이 절 첫 문장은 D6 만 말하지만 표의 상장폐지는 보통 **D2(시세 못 받음)·D3** 로 멈춘다(설계 §10.2g "다음 거래일 run 이 D2·D3 로 멈춤 → 등록").
- **고칠 문장**: 첫 문장 → "매일 실행이 `D6 분할 의심 r=…` 또는 보유 종목의 `D2`(시세 못 받음)로 멈추면(종료 코드 4) **그 시장 장부 전체가 멈춰요.** 하루 지날 때마다 늦은 봉이 하나씩 쓰이고(10개까지), 5거래일을 넘기면 창 실패예요. 그러니 **1~2일 안에** 1차 출처를 확인해 아래 하나를 고르세요(모르면 바로 Claude Code 에 로그를 보여 주기)." 표의 첫 줄 "그날만 멈춤"은 "그동안 그 시장 전체가 멈춤"으로.

### C-16 · 보통 · §3.5 claude 시험 — 초보가 채울 수 없는 자리표시와 막힐 때의 길
- **무엇이 틀렸나**: (가) `PATH=<plist 에 넣을 PATH>` 를 무엇으로 채우는지 예가 없다(그대로 붙이면 `<` 가 셸의 입력 돌리기라 "no such file" 오류). `which claude` 는 **파일 경로**(`…/bin/claude`)를 내는데 넣을 것은 그 **폴더**라는 설명도 없다. (나) "로그인 창·오류가 나오면 키체인 로그인·`node` 경로·전역 훅을 확인"은 초보가 할 수 있는 일이 아니다. (다) 두 번째 시험은 `cd /tmp` 에서 부르는데 H1 은 `state/h1/claude_cwd/` 에서 부른다(`h1._leader_ask`). 저장소에 CLAUDE.md·`.claude/` 가 없어 지금은 차이가 없지만, 같은 폴더에서 시험하는 편이 맞다.
- **고칠 문장**: "`which claude` 가 `/Users/나/.local/bin/claude` 이면 넣을 폴더는 `/Users/나/.local/bin` 이에요. 그 폴더를 앞에 둔 `/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin` 을 아래 `PATH=` 뒤와 plist 에 **똑같이** 넣어요." 예시 줄은 자리표시 없이 그 값으로 적고, 막히면 "화면에 나온 글을 그대로 Claude Code 에 보여 주세요"로 바꾼다. 두 번째 시험의 `cd /tmp` 는 `mkdir -p /Users/나/claude-stock-h1/state/h1/claude_cwd && cd /Users/나/claude-stock-h1/state/h1/claude_cwd` 로.

### C-17 · 경미 · §8.1 허용 변경 순서 — 빠진 단계
- **무엇이 틀렸나**: "커밋 → 태그 → H1 폴더에서 `git checkout <새 태그>` → `h1_replay.py` 통과 → 다음 실행" 에 (가) 새 태그를 받는 `git fetch origin --tags` 가 없어 `git checkout` 이 "pathspec … did not match" 로 실패하고, (나) 2번(라이브러리 올림)일 때 venv 에 실제로 까는 `$P -m pip install -r requirements-h1.txt` 가 없어 재현이 **옛 라이브러리로** 통과한다(바꾼 것이 반영되지 않음). (다) checkout 과 재현(약 8분) 사이에 launchd 실행이 끼면 관문 거절(3)이 일지에 남는다(판정 실패는 아니지만 status 의 "관문 거절" 숫자가 늘어 놀람). (라) 재현이 0 이 아니면 어떻게 하는지 없다.
- **고칠 문장**: "H1 폴더에서: `git fetch origin --tags` → `git checkout <새 태그>` → (라이브러리 올림이면) `$P -m pip install -r requirements-h1.txt` → `$P h1_replay.py`. 낮 10시~밤 10시 사이에 하면 launchd 실행과 겹치지 않아요. 재현이 0 이 아니면 `git checkout <원래 태그>` 로 되돌리고 화면을 Claude Code 에 보여 주세요."

### C-18 · 경미 · §5 status 읽기 — 작은 사실 차이
- `runs.jsonl` 은 "실행마다 한 줄"이 아니라 **두 줄**(시작 줄 + 끝 줄, `_RunLog` 설명).
- 표의 "트레이너별 요약 줄"은 실제로는 **시장 요약**(A0·A1 합계, A1−A0, 지수 들고 있기, 점검·팀장 수)이다. 가짜 자료로 돌린 실제 출력: `A0 쉬는 돈=현금  $100,000 → $99,125 (-0.88%)` / `A1 쉬는 돈=SPY …` / `A1−A0 +$99 · SPY 들고 있기 … +1.36%`.
- 실제 출력에 있는 `재시작 0/2 (남은 2) · 마감 2027-06-30 까지 236일` 줄이 표에 없다(남은 재시작·마감은 초보가 꼭 볼 줄).
- start 전(§3.7-2)에는 `장부 없음 → python h1.py start --market kr` 다음에 `※ 사전 등록 파일 prereg_kr.json 없음(상한·마감은 코드 상수로 보임)` 이 붙는데, 이것도 정상이라는 말이 없다.
- "로그 확인"의 명령이 없다 → `tail -40 /Users/나/claude-stock-h1/logs/h1-kr.log`.
- launchd 실행이 도는 중(국내 23:05 무렵, 팀장 호출로 몇 분)에 status 를 치면 `다른 H1 명령이 잠금 중이라 기다려요(최대 30분)` 가 나오고 멈춘 듯 보인다. "그러면 몇 분 뒤 다시 치세요(Ctrl-C 해도 장부는 안전)" 한 줄이 있으면 좋다.
- (나머지 줄 모양 `시작 S … · 마지막 처리 봉 … · 판정 창 12/63 (남은 51봉)`, `L 오류 0 · 자료 멈춤 0 · 관문 거절 0 · 늦은 봉 0/10 · 한 번에 따라잡은 최대 1봉`, `⑩ … 이 창 meta.rules 와 맞음`, `⑥ 코드 동결: 창 안 코드·환경 지문 변경 0번` 은 실제 출력과 같았다.)

### C-19 · 경미 · README H1 절 "위의 운영 파일들은 하나도 바꾸지 않아요"
- **무엇이 틀렸나**: `git diff --stat origin/kr-broker...HEAD` 로 보면 `team.py`(갈고리)·`analyst.py`(H1 함수 추가)·`paper_wallet.py`(소수 단위·`tax_rate`)·`screener.py`(`scan_frames`)가 바뀌었다(4파일 +298/−57). 바뀌지 않은 것은 **운영 동작**(골든 153파일 바이트 같음)이다. 또 README 의 바로 아래 "처음 한 번만: 준비하기"는 "python.org 에서 최신 버전 설치"·`pip install …` 이라 H1 의 "파이썬 3.13.18 고정·전용 venv"와 부딪친다.
- **고칠 문장**: "운영 파일의 **동작**은 하나도 바뀌지 않아요(`team.py` 등에는 H1 용 갈고리·함수만 더했고, 바꾸기 전과 결과가 바이트까지 같은지 시험으로 확인)." 그리고 H1 절 끝에 "H1 은 아래 '처음 한 번만: 준비하기'가 아니라 운영 안내서 §3 대로 준비해요(파이썬 3.13.18 전용 venv)."

### C-20 · 경미 · §8.2 상장폐지 취소 `--cancel-delist --confirm X` — 빠진 인자
- `corp-action` 은 `--market`·`--code`·`--source` 가 늘 필수다(`h1.py corp-action -h` 로 확인). 줄인 모양을 그대로 치면 인자 오류 9. → "`h1.py corp-action --market m --code X --cancel-delist --confirm X --source <근거>`".

### C-21 · 경미 · §3.8·§8.3 start 시각
- 미국 "16:30 ET 뒤"는 코드의 확정 시각 **16:15 ET**(`markets.close_cutoff`, `h1._settle_time`)보다 보수적인 말이라 틀리진 않지만, 초보에게 ET 는 계산이 어렵다. 한국 시간으로 바꾸면(코드 `next_open` = 다음 평일 09:30 ET): 화~금은 그날 아침(겨울 06:15·여름 05:15 확정)부터 그날 밤(겨울 23:30·여름 22:30) 전까지, 토·일·월은 금요일 봉으로 월요일 밤(겨울 23:30·여름 22:30) 전까지 start 가 된다. "07:10 무렵"이라는 권장은 그대로 두고 "한국 시간 아침 7시~밤 10시 사이면 돼요"를 더하면 쉽다.
- 국내 "22:30 뒤"는 KS200 이 22:30 직후 아직 안 올라온 날 D7(7) 또는 S 가 하루 전으로 잡혀 늦은 start 거절(8)이 난다. 운영 일정처럼 **23:00 이후** 권장이 안전하다.
- §8.3 의 `restart` 바로 뒤 `start` 도 같은 시각 규칙을 받는다(낮에 restart 하고 곧바로 start 하면 거절 8). 문장 하나: "start 는 §3.8 의 시각에만 돼요."

### C-22 · 경미 · §2 머리 문장과 다른 문서와의 어긋남(13가지 중 12번)
- §2 "첫 start 가 **아래 숫자를** `prereg_<시장>.json` 에 적고" — D-1(프롬프트)·D-3(분할 처리 방식)은 prereg 숫자가 아니라 **코드 동결**(⑥, CODE_FILES)로 고정된다. → "아래 결정은 start 뒤에 바꿀 수 없어요(숫자는 `prereg_<시장>.json` 에, 프롬프트·분할 처리는 코드 지문으로 고정)."
- `docs/작업-이어가기.md` §4 표는 아직 "Q4(H1 전용 프롬프트)는 보류한다"이고 §6 은 N1·N2 를 "정할 것"으로 둔다. 설계 §10.3 도 N1·N2 를 "남은 질문"으로만 적었다(2026-11-06 사용자 결정 기록 없음). 의도 대조 §5-12("인계 메모 고치기")가 아직 안 됐다. 설계 문서 sha256 은 start 때 `meta.json`·prereg 에 박히므로 **태그 전에** 설계 §10.3 에 "2026-11-06 사용자: N1 기본값·N2 공식·D-4 받아들임"을 적어 두는 것이 맞다(이 두 문서 밖의 일이라 검토 범위 밖이지만 적어 둠).

### C-23 · 경미 · 확인 목록에서 빠지거나 명령이 없는 것
- 검토 4 목록 11 의 뒷부분 "H1 worktree 에 order_runner 작업이 없는지"가 없고, §3.7-4 에 확인 명령이 없다 → `grep -l claude-stock-h1 ~/Library/LaunchAgents/*.plist` 결과가 `com.claude-stock.h1-…` 파일뿐이면 OK.
- 검토 4 목록 12(`F_FULLFSYNC`, "리허설에서 종료 코드 4(ENV)가 안 나는지")가 §9 "잴 것"에 없다.
- 검토 4 목록 7 뒷부분(start 뒤 `meta.design_doc_sha256` 과 설계 파일 비교)이 없다. 태그 고정·`git status` 깨끗이면 저절로 맞으므로 경미. §3.7-1 "`git log -1` 이 태그 커밋"은 초보가 판단하기 어렵다 → `git describe --tags --exact-match` 가 `h1-forward-v1` 을 내면 OK.
- 의도 대조 §4.2-9(운영 쪽 확인 두 가지: `kr_halt_check.py`, `team.py 40 --market kr` 비교 줄)는 H1 과 무관한 운영 일이지만 "맥 할 일" 목록에 있다. 한 줄로 "운영 폴더에서 따로 할 일(이 문서 밖): `docs/작업-이어가기.md` §6" 이라고 가리키면 빠짐이 없다(C-8 처럼 그 명령을 H1 폴더에서 치지 않게).

### C-24 · 경미 · §9 리허설
- `git worktree add …` 는 저장소 폴더 안에서만 된다 → 앞에 `cd /Users/나/claude-stock`.
- "임시 plist"는 Label·파일 이름·경로를 진짜와 **다르게**(예 `com.claude-stock.h1r-kr`, WorkingDirectory·로그를 리허설 폴더로) 해야 진짜 작업과 엉키지 않는다. 지금 문장으로는 §4 plist 를 그대로 복사할 위험이 있다.
- 리허설 동안 팀장 호출은 운영 + H1 리허설(+ 진짜 H1 을 이미 시작했다면 그것까지)로 늘어난다(같은 구독 한도).

### C-25 · 경미 · 막혔을 때의 공통 규칙·걸리는 시간
- `pytest` 실패, 지킴이 실패, 재현 종료 코드 2·3·4 가 나왔을 때 "다음으로 넘어가지 말고 화면을 Claude Code 에 보여 주기"라는 공통 규칙이 없다(§7 은 `h1.py` 종료 코드만). §3 머리에 한 줄 상자로 두면 좋다.
- 걸리는 시간: 재현 "약 8분"만 있다. 이 컨테이너 기준 `pytest` 약 4분(939개, 229초), 지킴이 `--quick` 약 4~5분(세 번을 함께 돌림)이다. 초보가 멈춘 줄 알고 Ctrl-C 하지 않게 적어 두면 좋다.

### C-26 · 경미 · §10 최종 보고서 파일 위치
- 최종 보고서는 `state/h1/reports/<시장>-final-<S>.md` 로 생긴다(`h1_report.report_name`). §10 에 위치가 없고 §6 보관 안내도 월간만 말한다 → §10 에 경로와 "이 파일도 §6 처럼 보관"을 더한다.

### C-27 · 경미(제안) · 휴대폰으로 매일 확인
- 사용자는 대개 휴대폰만 들고 있는데 §5 "매일 확인 습관"은 맥 앞에서만 된다. 아이폰이면 plist 명령 끝에 status 를 iCloud Drive 로 떨구는 한 줄을 더하면 휴대폰 '파일' 앱에서 매일 볼 수 있다. 예(국내 plist 의 `sh -c` 글, `exit $c` 앞): `/Users/나/.venv-h1/bin/python h1.py status --market kr > "/Users/나/Library/Mobile Documents/com~apple~CloudDocs/H1-상태-kr.txt" 2>&1;` (H1 폴더 자체는 iCloud 밖 그대로, 사본 글만 iCloud).

### C-28 · 중요 · §3.8(start) → §4(launchd) 순서 — start 와 launchd 사이가 벌어지면 창이 바로 실패할 수 있음
- **무엇이 틀렸나**: 문서는 §3 "처음 한 번 — 준비"의 마지막에 start(§3.8)를 두고, 매일 실행(launchd)은 다음 절 §4 에 둔다. 초보가 §3 을 한 저녁에 끝내고 §4 를 며칠 뒤에 하면, 그 사이의 봉은 처리되지 않다가 나중에 **늦은 봉**으로 처리되고(창 전체 10개 중에서 빠짐), **5거래일이 넘게 비면 첫 실행이 종료 코드 6(밀린 봉 초과) → 그 창은 실패**, 재시작 1번을 쓴다(`h1._run_body`: 처리할 봉이 `MAX_LATE_BATCH`=5 보다 많으면 바로 `EXIT_BACKLOG`). 이 위험을 알리는 말이 없다. 가짜 자료로 직접 확인: 미국 start(S=2026-02-02) 뒤 6거래일째에 첫 `run` → `거절: 밀린 봉 6개(2026-02-03~2026-02-10) > 5 → 판정 창 실패(사전 등록 ②-2)`, 종료 코드 6.
  (참고·코드 쪽: 이 거절 글의 안내 `python h1.py restart --market us → start` 에는 `--confirm`·`--reason` 이 빠져 있어 그대로 치면 인자 오류 9 — 해는 없음.)
- **고칠 문장**: 순서를 바꿔 §4(launchd 켜기)를 start **앞**에 둔다. "launchd 를 먼저 켜 두면 start 전에는 매 실행이 종료 코드 8(장부 없음) 알림을 띄워요 — 해가 없고, 오히려 launchd·알림이 잘 도는지 확인하는 방법이에요(`launchctl kickstart …` 로 한 번 돌려 알림 '종료 코드 8' 이 뜨면 OK)." 순서를 못 바꾸면 §3.8 에 굵게: "**start 한 그날 안에 §4 까지 끝내세요.** 다음 처리 시각(국내 23:05·미국 07:10)까지 launchd 가 없으면 그 봉부터 늦은 봉이 되고, 5거래일 넘게 비면 창 실패예요."

---

## 목록 대조 — 빠진 것이 있나

| 기준 목록 | 결과 |
|---|---|
| 의도 대조 §5 의 13가지 | 1~11 은 모두 들어 있음(§2 결정 상자, §1 말할 수 있는 것/없는 것, §6 월간 보고서, §10 통과 뒤 9가지, §8.1 코드 동결·FDR 주의, §8.2 결정표, §8.3 재시작, §5 status, §11, §12, §9). **12(인계 메모 고치기)는 아직 안 됨**(C-22). 13 은 이 검토 |
| D-1~D-7 | 7개 모두 §2 표에 있음. D-7 의 보고서 11절 문장도 `h1_report.py` 에 들어간 것을 확인 |
| 의도 대조 §4.2 맥 할 일 1~10 | 1~8 있음(7 일정은 표·plist 와 일치). **9(운영 쪽 확인 두 가지) 없음**(C-23). 10(`/t4.out`)은 컨테이너 일이라 해당 없음 |
| 검토 4 "맥 운영 전 확인 목록" 12개 | 1·2·4·5·6·8·9·10 있음. **3 은 확인 위치가 틀림**(C-2), 7·11 은 일부만(C-23), **12 없음**(C-23) |
| 작업-이어가기 §5 단계 6 줄 | worktree·venv·순서·start 시각·launchd 시각·`caffeinate`·PATH·종료 코드·`--confirm`·사유 코드 모두 있음 |
| 설계 §8·§3.9·§10.2d·§10.2g·§10.2h | 종료 코드 표(0·1·2·3·4·5·6·7·8·9·130)가 `h1.EXIT_TEXT` 와 같음. 재현 명령·종료 코드가 §10.2h 와 같음. §10.2g 의 `--confirm`·사유 코드·월요일 보조 실행·`claude_cwd` 반영(단 시험 폴더는 C-16) |
| 2026-11-06 사용자 결정 | Q4 "H1 에서만 날짜·시장·이름"(§2 D-1·§11), N1 기본값(D-2), N2 공식(D-3), "통과 = 장부가 잘 돌았다, 검토는 3개월 뒤"(§0·§1·§10, D-4) 모두 반영 |

## 맞게 확인한 것 (직접 돌려 봄 또는 코드와 맞춰 봄)

- `python h1.py -h` 와 하위 명령 6개 `-h`: `start`·`run`·`status` 는 `--market {us,kr}` 만, `restart` 는 `--confirm`(필수)·`--reason {L,backlog,rule-change}`(필수)·`--note`, `corp-action` 은 `--code`·`--split`·`--date`·`--delist`·`--cancel-delist`·`--confirm`·`--last-date`·`--last-close`·`--accept-correction`·`--source`(필수), `amend-rules` 는 `--source`. 문서의 명령·인자 이름과 맞다(줄인 모양 C-20 하나 빼고).
- `h1_report.py -h`: `--market`·`--month YYYY-MM`(없으면 마지막 처리 봉의 달)·`--final`·`--offline`·`--fetch-rates`, 결과 `state/h1/reports/<시장>-<YYYY-MM>.md`, 장부 없음 8. 문서와 같다. 인터넷이 없을 때도 저장본으로 보고서를 쓴다(`--offline` 은 필수가 아님).
- `h1_replay.py -h`: `--root`(기본 `state/h1`), 종료 코드 0·2·3·4·9·130, 마지막 줄 `[재현] 끝: 종료 코드 0 — 통과 + 기록함`. `tools/h1_test_guard.py --quick` 의 마지막 줄 `[지킴이] 모두 통과`. 문서와 같다.
- `pytest --collect-only`: **939개**(문서와 같음).
- 문서의 `python -c 'import analyst; print(analyst._build_prompt_h1(...))'` 줄을 그대로 돌림: 종료 0, 글에 `기준 날짜: 2026-11-06 (이 날 종가까지의 자료로 낸 신호, 체결은 다음 거래일 시가) · 시장: 국내 주식(…)`, 종목 줄 `- 005930: 이름=삼성전자 신호사유=시험 RSI=45 종가=70000`, JSON 틀 "code 에는 … 종목 코드만". 진짜 claude 시험 두 줄의 따옴표는 직접 만든 가짜 `claude` 로 돌려 보니 프롬프트 26줄이 **인자 하나로** 그대로 들어가고, `{"ok": true}` 글도 그대로 들어갔다.
- 가짜 자료로 미국 start → 11번 run → status: 상태 줄 모양이 §5 표와 같았다(C-18 의 작은 차이 빼고).
- §4 국내 plist: `plistlib` 로 읽힘, 23:05×월~금 5개 + 07:40×월~토 6개, 명령 셸 줄은 종료 코드 4 를 넣으면 알림 글·종료 코드가 맞게 나옴. `launchctl load`·`launchctl kickstart gui/$(id -u)/<Label>` 모양, `date -v-1m +%Y-%m`(BSD date, 2일에 돌므로 달 끝 문제 없음), `pmset repeat wakeorpoweron MTWRFS 07:00:00`(S=토) 모양은 맞다.
- start 시각 거절: 코드는 `지금 ≥ next_open(S)` 이면 거절 8 — 문서의 "국내 22:30 뒤 ~ 다음 날 09:00 전" 과 맞다. 07:10 KST = 겨울 17:10·여름 18:10 ET 도 맞다.
- 사실: §1 의 R2 숫자(미국 트레이너 백분위 12%·16%, 생존편향을 줄이면 A1 이 SPY 에 짐, 2018·2022 하락 국면에서 A1 이 A0 보다 더 잃음 — 세 종목군 모두)는 `origin/research-r2-2026-11-04:…/REPORT.md` 와 같다. 재현 숫자 $99,217.87 vs $97,473.91, ₩75,291,686 vs ₩71,923,477 은 의도 대조 §7.2 와 같고, 차이는 1.8%·4.7% 라 "2~5%"도 맞다. 배당·SPY 보수·KS200 보수 문장, "R2 와 달리 팀장이 켜져 있음", 국내 `KR_UNIVERSE` 32종목도 맞다.
- 두 문서가 가리키는 대상 커밋 156d41a 이후 `h1-forward` 에 커밋이 더 생겼지만(오류노트·검토 6b·이 파일 스냅샷), 검토한 두 문서는 바뀌지 않았다(`git diff 156d41a HEAD`).

## 한눈에 (심한 순서)

| 심함 | 번호 | 한 줄 |
|---|---|---|
| 중요 | C-3 | 재시작 명령의 `L\|backlog\|rule-change` 를 그대로 붙이면 파이프가 되어 `--reason L` 로 **바로, 되돌릴 수 없게** 실행됨 |
| 중요 | C-28 | start 와 launchd 켜기 사이가 5거래일 넘게 벌어지면 첫 실행이 종료 코드 6 → 창 실패(직접 확인). 순서를 바꾸거나 "그날 안에" 경고 |
| 중요 | C-5 | `git worktree remove` 는 `--force` 없이도 `state/` 장부까지 지움. 리허설 폴더 이름이 진짜와 비슷해 오타로 진짜를 지울 수 있음 |
| 중요 | C-6 | 보고서 보관 2번이 운영 폴더의 브랜치를 바꾸게 하고, 주문번호 든 `reports/broker/` 를 함께 커밋할 위험 |
| 중요 | C-7 | `pmset repeat` 가 운영(`broker-run.md`)의 09:00 깨우기를 덮어씀 |
| 중요 | C-8 | KS200 확인으로 가리킨 `kr-fix-s0.md` §5 가 운영 폴더 `git checkout`·`team.py` 실행 묶음 |
| 중요 | C-4 | 코드 블록 줄 끝 `# 설명` 때문에 맥 기본 셸(zsh)에서 start·재현·보고서 명령이 인자 오류로 실패 |
| 중요 | C-1 | `tail -1 replay_pass.json` 은 `]` 만 보여 줌 — 지문 확인을 할 수 없음 |
| 중요 | C-2 | `cli_version` 은 `runs.jsonl` 이 아니라 `analyst_cache_<시장>.jsonl` 에 있음 — launchd 의 claude 확인이 늘 "실패"로 보임 |
| 보통 | C-9 | `$P`·`cd` 없는 블록 — 새 터미널·운영 폴더에서 치면 실패하거나 엉뚱한 폴더에 장부 |
| 보통 | C-10 | `launchctl unload` 만으로는 재시동 뒤 다시 켜짐, plist 파일을 안 지움 |
| 보통 | C-11 | 보고서·미국 plist 를 "두 곳만 바꿔요"로 설명 — Label·로그 경로도 바꿔야 함 |
| 보통 | C-12 | 파이썬 3.13.18 확인이 venv 만들기보다 앞, 설치 방법이 비어 있음 |
| 보통 | C-13 | `caffeinate` 가 python 종료 코드를 넘겨주는지 미확인 → 알림이 안 뜰 수 있음, 알림 권한 |
| 보통 | C-14 | 껐다 켜서 따라잡은 봉은 늦은 봉(10개 한도)으로 센다는 말이 없음 |
| 보통 | C-15 | D6 기다리는 동안 그 시장 전체가 멈춤 — 1~2일 안에 정해야 함 |
| 보통 | C-16 | claude 시험의 `PATH=<…>` 자리표시·막힐 때 길·시험 폴더 |
| 경미 | C-17~C-27 | 허용 변경 순서의 빠진 단계, status 표의 작은 차이, README "운영 파일 하나도 안 바꿈", `--cancel-delist` 인자, 시각 설명, §2 머리 문장·인계 메모, 확인 목록 빠짐, 리허설 plist, 막힐 때 규칙·걸리는 시간, 최종 보고서 위치, 휴대폰 확인 제안 |

## 쉬운 말 요약

- **내용(무엇을 왜 하는지)은 맞다.** R2 숫자, "통과 = 장부가 잘 돌았다는 뜻일 뿐", "하락장이면 A1 이 더 잃는 게 정상", 사용자 결정(D-1~D-7), 종료 코드 표, 명령 이름·인자는 코드와 맞았다. 상태 화면 모양도 실제로 돌려 본 것과 거의 같다.
- **그런데 "맥 앞에서 그대로 따라 하기"에서 막히거나 위험한 곳이 9군데 있다.**
  1. 맥 기본 터미널(zsh)은 명령 뒤에 붙인 `# 설명` 을 설명으로 안 보고 명령에 붙여 버려서, start·재현·보고서 명령이 오류로 끝난다 → 코드 블록 안 설명을 빼야 한다.
  2. 재시작 명령의 `L|backlog|rule-change` 를 그대로 붙이면 "셋 중 하나"가 아니라 **L 로 바로 재시작**이 실행된다(묻지 않고, 되돌릴 수 없음).
  3. start 해 놓고 매일 자동 실행(launchd)을 일주일쯤 늦게 켜면 **첫 실행에서 바로 그 창이 실패**한다 → 자동 실행을 먼저 켜고 start 하게 순서를 바꿔야 한다.
  4. `git worktree remove` 는 `--force` 를 안 붙여도 **장부까지 지운다.** 리허설 폴더 이름도 진짜와 헷갈리게 비슷하다.
  5. "보고서를 운영 폴더 새 브랜치에 커밋"·"pmset 깨우기"·"kr-fix-s0 §5 보고 확인" 세 곳은 **운영 쪽을 건드린다**(운영 코드가 바뀌거나, 주문번호가 올라가거나, 운영 09:00 깨우기가 지워지거나, 운영 장부를 손으로 돌림).
  6. 확인 단계 두 개가 문서대로 하면 확인이 안 된다: 재현 지문(`tail -1` 은 `]` 만 보임), launchd 의 claude 확인(`cli_version` 은 다른 파일에 있음).
- **보통 8개**는 주로 초보가 막힐 곳이다: `$P`·`cd` 를 매 블록에 넣기, 끄기(`unload -w`·plist 지우기), plist 를 통째로 싣기, 파이썬 3.13.18 설치 길, 알림이 정말 뜨는지, 맥을 끄면 늦은 봉이 쓰인다는 것, 분할 의심은 1~2일 안에 정해야 한다는 것.
- 고칠 문장은 각 항목에 적었다. 코드(CODE_FILES)는 고칠 필요가 없고 **문서만** 고치면 된다(C-28 의 참고 한 줄 — `run` 의 거절 글에 `--confirm`·`--reason` 이 빠진 것 — 만 코드 쪽이며 해는 없다).
