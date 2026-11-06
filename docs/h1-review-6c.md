# 검토 6c — 단계 6 문서(`docs/h1-forward-run.md`·README "H1 포워드 모의매매" 절) 독립 검토

- 검토 대상: 브랜치 `h1-forward` 커밋 156d41a 의 `docs/h1-forward-run.md`, `README.md` H1 절
- 검토자: 독립 검토자(작성자 설명 없음). 2026-11-06.
- 상태: **작성 중**(찾은 것을 그때그때 적음)

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

### C-4 · 중요 · §3.3·§3.4·§3.5·§6 코드 블록 — 줄 끝 `# 설명` 이 맥 기본 셸(zsh)에서는 주석이 아님
- **무엇이 틀렸나**: 맥 터미널의 기본 셸 zsh 는 대화형으로 친 줄에서 `#` 를 주석으로 보지 않는다(`INTERACTIVE_COMMENTS` 옵션이 기본으로 꺼져 있음. 이 컨테이너에는 zsh 가 없어 직접 돌리지는 못했고, 알려진 동작으로 적음). 그래서 `#` 와 그 뒤 한국어 낱말이 **명령의 인자로 붙는다**. 괄호가 섞인 줄(`통과(지금 939개)`·`폴더(그대로 둔다)`·`기준값(R2)`)은 zsh 가 glob 으로 읽어 오류를 낼 수도 있다. 어느 쪽이든 명령이 실패한다.
  - bash 에서 같은 인자를 따옴표로 붙여 직접 재현: `h1_replay.py '#' '약' '8분.'` → `명령 인자 오류 — unrecognized arguments` 종료 코드 9, `h1_report.py --market us --month 2026-12 '#' '그달'` → 종료 코드 9. `git fetch origin research-r2-2026-11-04 '#' …` 는 `#` 를 브랜치 이름으로 받아 실패한다. `cd /Users/나/claude-stock  # 운영 폴더(그대로 둔다)` 는 `cd` 가 실패해 **다음 줄들이 엉뚱한 폴더에서** 돈다.
  - 해당 줄(문서 줄 번호): 72·74(§3.3), 87~91(§3.4 의 `pytest`·`git fetch`·`h1_test_guard`·`h1_replay`·`code_hash`), 101(§3.5 `which claude`), **128·129(§3.8 `start` 두 줄 — 인자 오류 9 로 start 가 안 됨)**, 215(§6 첫 `h1_report.py`). (§4·§6 plist 안의 `sh -c` 글은 sh 가 읽으므로 괜찮음.) 해가 되는 쪽으로 바뀌는 줄은 없고 모두 "실패"로 끝나지만, 초보는 왜 실패하는지 알 수 없다.
- **고칠 문장**: 코드 블록 안의 `# …` 설명을 모두 빼서 블록 **아래 글**로 옮긴다(예: "`pytest` 는 전부 통과해야 해요(지금 939개, 약 4분)"). 그리고 §3 머리에 한 줄: "코드 블록은 한 줄씩 복사해 붙여 넣으세요. 블록 안에는 설명(#)을 넣지 않았어요."

### C-5 · 중요 · §12 "`--force` 는 … state/·logs/ 까지 지워요" / §9 리허설 지우기 — `--force` 가 없어도 state/ 는 지워짐
- **무엇이 틀렸나**: scratch 의 빈 git 저장소로 직접 확인(git 2.43): 태그로 worktree 를 만들고 git 이 무시하는 `state/h1/x.json`·`logs/h1.log` 만 넣은 뒤 **`--force` 없이** `git worktree remove` → 종료 코드 0, **폴더 전체(state/·logs/ 포함)가 지워졌다.** `--force` 가 필요한 경우는 "무시되지 않는 새 파일이나 고친 파일"이 있을 때뿐이다(예: 보고서를 그 폴더에 복사해 둔 경우 → `fatal: … contains modified or untracked files, use --force`). 지금 문장은 "`--force` 를 안 붙이면 state/ 는 남는다"로 읽혀, 장부를 지키려고 `--force` 만 빼고 치는 실수를 부른다.
- 또 리허설 폴더 이름 `claude-stock-h1-rehearsal` 이 진짜 폴더 `claude-stock-h1` 과 앞부분이 같아 탭 자동 완성·오타로 **진짜 H1 폴더를 지울 수 있다**(되돌릴 수 없음, 판정 창 장부 전부).
- **고칠 문장**(§12): "`git worktree remove` 는 `--force` 가 있든 없든 **그 폴더 전체를 지워요**(`state/` 장부·`logs/` 포함, 되돌릴 수 없음). 보고서·장부를 먼저 다른 곳에 복사한 뒤에만 치세요. `--force` 는 그 폴더에 git 이 모르는 새 파일이 있을 때 필요해요." §9: 리허설 폴더 이름을 진짜 폴더와 앞부분이 다른 `/Users/나/h1-rehearsal` 로 바꾸고, 지우기 줄 앞에 "**경로가 `h1-rehearsal` 인지 두 번 확인**"을 넣는다.

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

