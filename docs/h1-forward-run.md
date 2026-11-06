# H1 포워드 모의매매 — 맥에서 돌리는 법 (운영 안내서)

> **진짜 돈도, 진짜 주문도 없습니다.** 실제 시세로 "가짜 장부" 두 개를 3개월 넘게 매일 쌓아 비교하는 시험이에요.
> 설계는 `docs/h1-forward-design.md`(3판 + §10), 원래 의도와 맞는지 대조한 것은 `docs/h1-intent-check.md`,
> 공부용 안내서는 `docs/h1-guide/`(README 부터)에 있어요. 이 문서는 **맥 앞에서 그대로 따라 하는 순서**만 적었어요.
> 문서 검토: `docs/h1-review-6c.md`(C-1~C-28 반영).

---

## 0. 한 쪽 요약 (먼저 이것만 읽어도 됨)

- **무엇을 하나**: 같은 날·같은 돈($100,000 / ₩1억)으로 장부 두 개를 시작해요.
  - **A0**: 지금 방식. 트레이너가 주식을 안 산 돈(쉬는 돈)은 현금으로 둠.
  - **A1**: H1 방식. 쉬는 돈을 **지수**(미국 SPY, 국내 코스피200 지수 KS200)에 넣어 둠. 주식을 살 때 모자란 만큼만 지수를 팔아 씀.
  - 두 장부는 같은 트레이너 규칙·같은 후보·**같은 팀장 판정**을 써요. 다른 것은 "쉬는 돈을 어디에 두나" 하나뿐이에요.
- **얼마나**: 시장마다 시작 봉 S 부터 63거래일(S~S+62, 약 3개월). 미국·국내는 따로 시작하고 따로 판정해요.
- **어디서**: 운영 폴더(지금 `team.py` 를 돌리는 폴더)와 **다른 폴더**(H1 전용 폴더 `/Users/나/claude-stock-h1`)에서, **다른 파이썬 환경**(H1 전용 venv)으로.
- **순서**: 준비(§3) → (권장: 리허설 §10) → **매일 자동 실행(launchd) 먼저 켜기(§4)** → 시작(§5) → 매일 status 보기(§6) → 매달 보고서(§7).
- **통과의 뜻**: "장부가 63일 동안 틀린 계산 없이, 빠진 날 없이, 검사받은 코드로만 돌았다". **"A1 이 돈을 더 번다"는 뜻이 아니에요**(§1).
- **운영은 그대로**: 기존 `team.py`·`order_runner.py`·`state/` 는 평소처럼 돌아요. 이 문서는 운영 폴더의 브랜치·장부를 바꾸라고 하지 않아요.

---

## 1. 이 결과로 말할 수 있는 것 / 없는 것 (꼭 읽기)

| 말할 수 있는 것 | 말할 수 없는 것 |
|---|---|
| H1 장부가 실제 운영 조건(시세가 늦는 날, 맥이 꺼진 날, 팀장이 늦는 날)에서 63일 동안 **틀리지 않고** 돌았는지 | **H1(A1)이 A0 보다 낫다** — 3개월은 너무 짧아요 |
| 쉬는 돈을 지수에 두는 장치가 설계대로 움직였는지(지수 사고판 기록, 비용) | **트레이너가 지수보다 잘한다** — 과거 연구(R2)에서 트레이너 매매 시점은 미국에서 무작위보다 못했어요(백분위 12%·16%, 국내는 88%) |
| 매달 A1−A0 가 얼마였는지(기록) | **시장을 이긴다** — R2 에서 미국이 지수를 이긴 것은 "지금 큰 회사"를 고른 덕(생존편향)이었고, 그걸 줄이면 A1 이 지수에 졌어요 |

- **3개월의 A1−A0 는 대부분 "그동안 지수가 올랐나 내렸나"로 정해져요.**
  - 오르는 3개월이면 A1 이 앞서기 쉬워요(쉬는 돈도 같이 오르니까).
  - 내리는 3개월이면 A1 이 A0 보다 **뒤처지기 쉬워요**(현금 방석이 없음, R2 의 2018·2022 년이 그랬어요).
  - **둘 다 정상**이에요. "H1 이 증명됐다/틀렸다"로 읽으면 안 돼요.
- 숫자가 얼마나 흔들리는지 예: 재현에서 **시작을 하루만 미뤘는데** 몇 달 뒤 A1 평가액이 2~5% 달라졌어요
  (W1 미국 $99,217.87 vs $97,473.91, 국내 ₩75,291,686 vs ₩71,923,477). 그래서 수익률로 판정하지 않기로 미리 정했어요(사전 등록 ③).
- 배당은 넣지 않았어요(주식·지수 모두 가격만). SPY 는 ETF 라 운용보수는 이미 가격에 들어 있고, KS200 은 지수라 실제 ETF 보수가 빠져 있어요.
- R2 와 달리 이번에는 **팀장(claude)이 켜져 있어요**. 두 장부가 같은 판정을 쓰니 A1−A0 비교에는 문제가 없어요.

---

## 2. 시작 전에 정한 것 (사용자 결정, 2026-11-06)

아래 결정은 **start 뒤에는 바꿀 수 없어요**. 숫자는 첫 `h1.py start` 가 `state/h1/prereg_<시장>.json` 에 적고,
프롬프트·분할 처리 방식은 코드 지문(재현을 통과한 코드)으로 고정돼요. 바꾸면 그 결과는 "탐색"일 뿐이에요.

| # | 정할 것 | 정한 값 | 메모 |
|---|---|---|---|
| D-1 | Q4 팀장 프롬프트 | **H1 에서만 기준 날짜·시장·종목 이름을 넣음** | 종목 줄이 `- 005930: 이름=삼성전자 …`·`- AAPL: 이름=Apple Inc. …` 모양이 돼요. 이름은 start 때 종목군 파일에 함께 고정(미국은 S&P500 표의 이름, 받지 못하면 코드만). 운영 팀장 글은 그대로 |
| D-2 | N1 숫자 | **기본값 그대로**: 재시작 최대 2번 · 마감 2027-06-30 · 늦은 봉 창 전체 10·한 번에 5 · 팀장 폴백 20% 넘으면 "대표성 없음" 표시 | |
| D-3 | N2 주식 분할·병합 | **공식으로 이어 가기**(`corp-action --split`) | 유상증자·정수가 아닌 무상증자는 공식이 없어 재시작 |
| D-4 | 통과의 뜻 | **받아들임**: 통과 = 장부가 잘 돌았다. 수익률은 기록만. 바꿀지 검토는 3개월 뒤 따로(§11) | |
| D-5 | 어느 시장부터·언제 | 사용자가 맥에서 정함 | 시각은 §5 |
| D-6 | 리허설 | 권장(§10) | start 는 한 번 성공하면 정해 둔 사유 없이는 다시 못 해요 |
| D-7 | 보고서 문장 고침 | **start 전에 넣음(끝)** | `h1_report.py` 11절 |

---

## 3. 처음 한 번 — 준비 (맥, 순서대로)

> **먼저 읽기 — 이 문서의 공통 규칙**
> - 아래 `/Users/나/` 는 내 홈 폴더로 바꾸세요(예 `/Users/kim/`). launchd 는 `~` 를 못 알아들어요.
> - 코드 상자는 **한 줄씩** 복사해 붙여 넣으세요. 상자 안에는 설명(#)을 넣지 않았어요(맥 기본 터미널 zsh 는 줄 끝 `# 설명` 을 명령의 일부로 읽어 오류를 내요). 설명은 상자 아래에 있어요.
> - H1 명령은 **언제나 `/Users/나/claude-stock-h1` 폴더에서** 쳐요. 그래서 명령 상자는 `cd /Users/나/claude-stock-h1` 와 `P=/Users/나/.venv-h1/bin/python` 두 줄로 시작해요(새 터미널을 열면 `P` 가 사라지니 매번 다시 쳐요).
> - **멈춤 규칙**: pytest 실패, 지킴이 실패, 재현 종료 코드가 0 이 아님, 그 밖에 예상과 다른 글이 나오면 **다음으로 넘어가지 말고** 화면 글을 그대로 Claude Code 에 보여 주세요.
> - 걸리는 시간(대략): pytest 4분, 지킴이 5분, 재현 8분. 이 셋은 멈춘 것처럼 보여도 Ctrl-C 하지 마세요(start 는 §5 참고).
> - **도우미(지름길)**: 손으로 칠 것을 줄이려고 `tools/h1_mac.py` 를 만들어 두었어요. §3.3 의 venv 만들기~§3.4 전부는 `setup`, §3.7 은 `check`, §4.1 의 plist 세 개는 `plists` 한 줄이에요(아래 각 절에 적었어요). 도우미가 멈추면 그 화면을 그대로 Claude Code 에 보여 주세요. 손으로 하는 길도 그대로 남겨 두었어요.

### 3.1 파이썬 3.13.18 설치 (brew 의 파이썬은 쓰지 않기)
- 장부의 "환경 지문"에 파이썬 **패치 버전**(3.13.**18**)까지 들어가요. brew 파이썬으로 venv 를 만들면 `brew upgrade` 한 번에 3.13.19 가 되어 **매 실행 종료 코드 3**(재현 안 한 환경)이 나요.
- 그래서 **python.org 에서 macOS 용 Python 3.13.18 설치 파일**을 받아 설치해요(목록에 3.13.18 이 없으면 멈추고 Claude Code 에 물어보세요 — 다른 방법(uv)을 알려 줘요).
- 설치 창에서 **"사용자화(Customize)" → "Shell profile updater" 의 체크를 빼고** 설치해요. 그래야 터미널의 기본 `python3` 이 바뀌지 않아 운영 쪽(`team.py` 등)에 영향이 없어요.
- 설치가 끝나면 Finder → 응용 프로그램 → Python 3.13 폴더의 **`Install Certificates.command` 를 두 번 눌러** 실행해요. 이것을 안 하면 금리 받기(인터넷 인증서 확인)가 조용히 실패해 보고서의 'A0+이자'가 옛 금리로 계산돼요.
- 설치 뒤 확인(첫 줄은 `Python 3.13.18`, 둘째 줄은 설치 전과 같은 경로여야 해요 — 운영 쪽 파이썬이 그대로라는 뜻):
  ```
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -V
  which python3
  ```
- 이 두 가지(설치 옵션 이름, 인증서 단계)는 맥에서 직접 확인하지 못했어요. 화면이 다르면 Claude Code 에 보여 주세요.

### 3.2 시계
- 시스템 설정 → 일반 → 날짜 및 시간: 시간대 **서울**, 자동으로 시간 설정 **켬**. "늦은 봉" 판단이 맥 시계에 달려 있어요.

### 3.3 H1 전용 폴더(worktree)와 venv
```
cd /Users/나/claude-stock
git fetch origin h1-forward
git tag h1-forward-v1 c30753e
git worktree add /Users/나/claude-stock-h1 h1-forward-v1
cd /Users/나/claude-stock-h1
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -m venv /Users/나/.venv-h1
/Users/나/.venv-h1/bin/python -V
/Users/나/.venv-h1/bin/python -m pip install -r requirements-h1.txt
mkdir -p logs
```
- 첫 줄의 운영 폴더(`claude-stock`)는 **브랜치를 바꾸지 않아요**. `git worktree add` 는 옆에 새 폴더를 만들 뿐이에요.
- `h1-forward-v1` 은 H1 태그(코드에 붙인 이름표)예요. 진행 담당이 정한 커밋은 **`c30753e`** 예요(2026-11-06, 단계 1~6 끝, 시험 944·지킴이·재현 통과). 클라우드 작업 환경에서는 태그를 GitHub 에 올릴 수 없어서, 위 `git tag …` 줄로 **맥에서 직접** 이름표를 붙여요(맥 안에만 있는 이름표라도 똑같이 쓸 수 있어요). `git tag` 줄이 "already exists" 라고 하면 이미 있는 것이니 그대로 다음 줄로 가요.
- 태그를 붙인 뒤로는 그 코드로만 돌려요.
- `-V` 줄은 `Python 3.13.18` 이어야 해요.
- 폴더는 **iCloud 동기화 밖**에(`~/Desktop`·`~/Documents` 말고). 파일 이름 바꾸기·잠금이 동기화 폴더에서 깨질 수 있어요.
- 이 폴더의 `state/` 는 운영 폴더의 `state/` 와 **다른 폴더**예요. 운영 장부는 여기 없어요.

### 3.4 시험 → 지킴이 → 재현 → 지문 확인 (이 순서 그대로)

**지름길**: §3.3 의 `git worktree add` 까지 한 뒤, 아래 두 줄이면 §3.3 의 venv·라이브러리와 이 절 전부를 순서대로 해요(약 20분). 하나라도 실패하면 거기서 멈추고 "`--from N` 으로 이어서"를 알려 줘요.
```
cd /Users/나/claude-stock-h1
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 tools/h1_mac.py setup
```
마지막에 `[setup] 모두 통과` 가 나오면 §3.5 로 가요. 아래는 같은 일을 손으로 하는 길이에요.

```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
$P -m pytest -q
git fetch origin research-r2-2026-11-04
$P tools/h1_test_guard.py --quick
$P h1_replay.py
$P -c "import h1, json; now = h1.code_hash()[0]; last = json.load(open('state/h1/replay_pass.json'))[-1]['code_hash']; print(now); print(last); print('같음' if now == last else '다름 - 멈추고 물어보기')"
```
- `pytest` 는 전부 통과해야 해요(지금 944개, 약 4분).
- `git fetch …` 는 재현의 기준값(과거 연구 R2) 자료를 받아요.
- 지킴이는 마지막에 `[지킴이] 모두 통과` 가 나와야 해요(인터넷·claude 를 쓰지 않는지, 세 번 돌려 결과가 같은지 봐요).
- 재현(`h1_replay.py`, 약 8분)은 과거 시세로 새 코드와 R2 연구 시뮬레이터를 같이 돌려 **체결 하나하나까지 같은지** 봐요. 마지막에 `[재현] 끝: 종료 코드 0 — 통과 + 기록함` 이 나와야 해요. 통과하면 `state/h1/replay_pass.json` 에 "이 코드·이 환경은 검사받았다"가 적혀요. 이 기록이 없거나 코드·환경이 다르면 `h1.py` 는 실행을 거절해요(종료 코드 3, "관문").
- 마지막 줄은 지금 코드의 지문과 재현 통과 기록의 지문을 비교해요. 끝에 `같음` 이 나오면 됩니다.

### 3.5 launchd 와 같은 환경에서 팀장(claude) 시험
launchd 는 터미널과 PATH·환경이 달라서, 터미널에서 되던 `claude` 가 안 될 수 있어요(그러면 팀장이 매일 폴백).
```
which claude
```
- 나온 것이 `/Users/나/.local/bin/claude` 라면 **넣을 폴더**는 끝의 `/claude` 를 뺀 `/Users/나/.local/bin` 이에요.
- 그 폴더를 맨 앞에 둔 `/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin` 을 아래 두 시험과 §4 의 plist 에 **똑같이** 넣어요(아래는 `.local/bin` 인 경우의 예. 다른 폴더면 그 부분만 바꿔요).
```
mkdir -p /Users/나/claude-stock-h1/state/h1/claude_cwd
env -i HOME=$HOME PATH=/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin sh -c 'cd /Users/나/claude-stock-h1/state/h1/claude_cwd && claude -p "JSON 하나만: {\"ok\": true}"'
```
- JSON 이 나오면 OK. 로그인 요청·오류가 나오면 화면 글을 그대로 Claude Code 에 보여 주세요.

그다음 **H1 이 실제로 보내는 글**로 한 번 물어봐요(이 글은 진짜 claude 로 시험한 적이 아직 없어요, 검토 6a A-12):
```
cd /Users/나/claude-stock-h1
/Users/나/.venv-h1/bin/python -c 'import analyst; print(analyst._build_prompt_h1("마라토너", [{"code":"005930","reason":"시험","rsi":45,"price":70000}], {"market":"kr","date":"2026-11-06","names":{"005930":"삼성전자"}}))' > /tmp/h1-prompt.txt
env -i HOME=$HOME PATH=/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin sh -c 'cd /Users/나/claude-stock-h1/state/h1/claude_cwd && claude -p "$(cat /tmp/h1-prompt.txt)"'
```
- 답에 `{"analysis": [{"code": "005930", ...}]}` 처럼 **code 가 숫자 코드만** 있으면 좋아요. `"005930(삼성전자)"`처럼 이름이 붙어 와도 H1 이 맨 앞 코드로 다시 찾아 판정을 살리지만, 그런 일이 잦으면 알려 주세요.
- **`ANTHROPIC_API_KEY` 는 설정하지 마세요**(구독 대신 종량 요금). 코드도 이 변수를 지우고 부르지만, 설정 자체를 하지 않는 게 안전해요.

### 3.6 잠자기 (운영과 함께 정하기)
- 가장 쉬운 방법: 맥을 **전원에 꽂아 두고 잠자기를 끄기**(시스템 설정 → 배터리(또는 에너지 절약) → "전원 어댑터 사용 시 디스플레이가 꺼져 있을 때 자동으로 잠자기 방지" 켬. 노트북은 덮개를 연 채로).
- 깨우기 일정(`pmset repeat`)은 **맥 전체에 하나만** 둘 수 있어요. 먼저 지금 일정을 봐요:
  ```
  pmset -g sched
  ```
  - 운영 문서(`docs/broker-run.md`)대로 이미 `09:00` 깨우기가 있으면, **H1 때문에 바꾸지 마세요.** 위의 "잠자기 끄기"로 충분해요.
  - 아무것도 없을 때만 보조로 `sudo pmset repeat wakeorpoweron MTWRFS 07:00:00`(월~토 07:00 깨우기). 이 줄은 있던 깨우기 일정을 **지우고 바꿔요**.
- 실행 중 잠들지 않게 launchd 작업은 `caffeinate -i` 로 감싸 두었어요(§4).
- launchd 는 **잠자기**에서 깨면 놓친 작업을 한 번 돌리지만, **껐다 켜면** 돌리지 않아요. 다음 예정 실행이 밀린 봉을 5개까지 따라잡지만, **따라잡은 봉은 "늦은 봉"으로 세요**(팀장 없이 규칙만, 판정 창 전체 10개까지). 그래서 판정 창 동안은 맥을 끄지 않는 게 좋아요.

### 3.7 시작 전 확인

**지름길**(아래 1~5를 한 번에):
```
cd /Users/나/claude-stock-h1
/Users/나/.venv-h1/bin/python tools/h1_mac.py check
```
마지막에 `[check] 모두 맞음` 이 나오면 됩니다. KS200 날짜만은 눈으로 봐요(어제 날짜인지). 아래는 손으로 하는 길이에요.

```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
git describe --tags --exact-match
git status --short
$P h1.py status --market kr
$P -c "import FinanceDataReader as f; print(f.DataReader('KS200', '2026-10-01').tail(3))"
$P -c "import screener; print(len(screener.universe(40)))"
grep -l claude-stock-h1 /Users/나/Library/LaunchAgents/*.plist
```
1. `git describe …` 가 태그 이름(`h1-forward-v1`)을 내고, `git status --short` 가 아무것도 안 내면 OK(설계 문서 최종판이 그 태그에 있어요).
2. `status` 가 `장부 없음 → python h1.py start --market kr` 와 `※ 사전 등록 파일 prereg_kr.json 없음 …` 을 내면 정상이에요(아직 시작 전).
3. KS200 줄: 맨 아래 날짜가 어제(22:30 뒤면 오늘)여야 해요. 며칠 전에 멈춰 있으면 start 하지 말고 물어보세요.
4. `screener` 줄: `40` 이 나오면 미국 S&P500 목록 받기가 돼요.
5. `grep` 줄: `com.claude-stock.h1-…` 파일만 나와야 해요(운영 작업 team.py·order_runner 가 H1 폴더를 가리키면 안 됨). §4 전이라 아무것도 안 나와도 OK.
- `docs/kr-fix-s0.md` §5 의 다른 명령(`git checkout`·`team.py` 등)은 **운영 폴더용**이라 여기서 치지 않아요. 운영 쪽 확인 두 가지(`kr_halt_check.py`, `team.py 40 --market kr` 비교 줄)는 이 문서 밖의 일이에요(`docs/작업-이어가기.md` §6).

---

## 4. 매일 자동 실행(launchd) — start **전에** 켜기

**왜 먼저 켜나**: start 한 뒤 launchd 를 며칠 늦게 켜면 그 사이 봉이 "늦은 봉"이 되고, **5거래일 넘게 비면 첫 실행이 종료 코드 6 → 판정 창 실패**예요.
start 전에 켜 두면 매 실행이 종료 코드 8(장부 없음) 알림을 띄우는데, 해가 없고 오히려 "자동 실행·알림이 잘 되는지" 확인하는 방법이에요.

| 시장 | 명령 | 시각(맥 = 한국 시간) | 왜 이 시각 |
|---|---|---|---|
| 국내 | `h1.py run --market kr` | **월~금 23:05** + 보조 **월~토 07:40** | KS200 이 22:30 뒤에 오늘 봉을 인정. 보조는 23:05 실패·KS200 늦은 날(종료 코드 7)을 챙김. 07:40 은 09:00 전이라 "늦은 봉"이 아님. 월요일 07:40 은 금요일 봉의 세 번째 기회 |
| 미국 | `h1.py run --market us` | **화~토 07:10** + 보조 **월~토 08:40** | 07:10 KST = 겨울 17:10 ET / 여름 18:10 ET → 늘 미국 장 마감 뒤·다음 장 전. 서머타임이 바뀌어도 시각을 안 고쳐도 돼요 |
| 둘 다 | `h1_report.py` (지난달) | 매달 2일 09:30 | §7 |

- 휴장일에는 새 봉이 없어 "이미 처리됨"(종료 코드 0)으로 바로 끝나요. 같은 봉을 두 번 돌려도 파일이 안 바뀌어요.
- 국내 보조(07:40)와 미국(07:10)은 시장별 잠금이 따로라 겹쳐도 괜찮아요.
- 팀장 호출이 하루에 대략 **두 배**가 돼요(운영 + H1, 같은 구독 한도).

### 4.1 plist 파일 만들기

**지름길(권장)**: 아래 두 줄이면 국내·미국·월간 보고서 plist 세 개를 `/Users/나/Library/LaunchAgents/` 에 만들어요. claude 위치(§3.5)를 스스로 찾아 PATH 맨 앞에 넣고, 파일이 깨지지 않게 만들어 다시 읽어 확인해요. 켜는 명령은 화면에 보여 주기만 하니 §4.2 대로 쳐요. 휴대폰으로 상태를 보고 싶으면 끝에 `--icloud-status` 를 붙여요(§6).
```
cd /Users/나/claude-stock-h1
/Users/나/.venv-h1/bin/python tools/h1_mac.py plists
```
`claude 를 찾지 못했어요` 가 나오면 `which claude` 로 나온 경로를 `--claude` 뒤에 붙여 다시 쳐요(예 `… plists --claude /Users/나/.local/bin/claude`). 이 길을 썼으면 아래 nano 길과 §7 의 보고서 plist 만들기는 건너뛰어요.

**손으로 하는 길**:
plist 는 터미널 편집기 `nano` 로 만들어요(텍스트 편집기 앱은 서식이 섞여 파일이 깨질 수 있어요).
```
nano /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
```
아래 내용을 붙여 넣고 `/Users/나/` 와 PATH(§3.5 에서 정한 값)를 바꾼 뒤, Ctrl-O → Enter → Ctrl-X 로 저장해요. 미국도 같은 방법으로 `com.claude-stock.h1-us.plist` 를 만들어요.

**국내** (`com.claude-stock.h1-kr.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.claude-stock.h1-kr</string>
  <key>WorkingDirectory</key><string>/Users/나/claude-stock-h1</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>/bin/sh</string><string>-c</string>
    <string>/Users/나/.venv-h1/bin/python h1.py run --market kr; c=$?; [ $c -eq 0 ] || osascript -e "display notification \"H1 국내 종료 코드 $c (logs/h1-kr.log)\" with title \"claude-stock\""; exit $c</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
  </array>
  <key>StandardOutPath</key><string>/Users/나/claude-stock-h1/logs/h1-kr.log</string>
  <key>StandardErrorPath</key><string>/Users/나/claude-stock-h1/logs/h1-kr.log</string>
</dict>
</plist>
```

**미국** (`com.claude-stock.h1-us.plist`, 화~토 07:10 + 월~토 08:40):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.claude-stock.h1-us</string>
  <key>WorkingDirectory</key><string>/Users/나/claude-stock-h1</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>/bin/sh</string><string>-c</string>
    <string>/Users/나/.venv-h1/bin/python h1.py run --market us; c=$?; [ $c -eq 0 ] || osascript -e "display notification \"H1 미국 종료 코드 $c (logs/h1-us.log)\" with title \"claude-stock\""; exit $c</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
  </array>
  <key>StandardOutPath</key><string>/Users/나/claude-stock-h1/logs/h1-us.log</string>
  <key>StandardErrorPath</key><string>/Users/나/claude-stock-h1/logs/h1-us.log</string>
</dict>
</plist>
```

### 4.2 켜고 확인하기
```
plutil -lint /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist /Users/나/Library/LaunchAgents/com.claude-stock.h1-us.plist
launchctl load -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
launchctl load -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-us.plist
osascript -e 'display notification "시험" with title "claude-stock"'
launchctl kickstart gui/$(id -u)/com.claude-stock.h1-kr
tail -20 /Users/나/claude-stock-h1/logs/h1-kr.log
```
1. `plutil -lint` 가 두 파일 모두 `OK` 여야 해요.
2. `osascript` 줄을 쳤을 때 화면 오른쪽 위에 "시험" 알림이 떠야 해요. 안 뜨면 시스템 설정 → 알림 → 스크립트 편집기 → 알림 허용.
3. `kickstart` 는 지금 한 번 돌려 보는 것이에요. start 전이면 알림 "H1 국내 종료 코드 8" 이 뜨고, 로그에 `장부 없음` 이 보이면 정상이에요.
- **팀장(claude)이 launchd 에서 정말 불리는지**는 start 뒤 **launchd 가 처음 새 봉을 처리한 다음 날** 봐요(국내·미국 따로):
  ```
  tail -3 /Users/나/claude-stock-h1/state/h1/analyst_cache_kr.jsonl
  tail -3 /Users/나/claude-stock-h1/state/h1/analyst_cache_us.jsonl
  ```
  줄 안에 `"status":"ok"`(빈칸 없이 붙어 있어요)가 있고 `"cli_version":"2.` 처럼 버전 글자가 있으면 OK. `"status":"no_claude"` 면 plist 의 PATH 에 claude 폴더가 없는 것(§3.5). 마지막 줄의 `"asked_at"` 시각이 터미널에서 start 를 친 시각이면 아직 launchd 결과가 아니에요(하루 더 기다리기). 줄이 안 늘었으면 그날은 매수 후보가 없어 팀장을 안 부른 것이에요.
- 팀장 답의 종목 코드에 이름이 붙어 와서 H1 이 다시 찾아 쓴 횟수(`reply_code`)는 가끔 이렇게 세어 봐요. 0 이 아니어도 판정은 살아 있지만, 많으면 Claude Code 에 알려 주세요:
  ```
  grep -c '"reply_code":"' /Users/나/claude-stock-h1/state/h1/analyst_cache_kr.jsonl
  ```
- 알림은 **맥 화면에만** 떠요. 맥 앞에 없으면 놓쳐요 → §6 의 매일 확인 습관(휴대폰으로 보는 방법도 있어요).

---

## 5. 시작 (start)

> **start 는 되돌릴 수 없어요.** 한 번 성공하면 정해 둔 사유(재시작) 없이는 다시 못 해요. 리허설(§10)을 하려면 **지금 먼저** §10 으로 가세요.

국내:
```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
$P h1.py start --market kr
```
미국:
```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
$P h1.py start --market us
```
- **국내 start 시각**: 밤 **23:00 뒤** ~ 다음 날 09:00 전(22:30 직후는 KS200 이 아직 안 올라와 거절될 수 있어요). 09:00 이 지나면 "늦은 start" 거절(종료 코드 8, 파일은 안 남음) — 그날 밤에 다시.
- **미국 start 시각**: 한국 시간 **아침 7시 ~ 밤 10시** 사이면 돼요(07:10 무렵 권장). 정확히는 미국 장 마감(16:15 ET) 뒤 ~ 다음 장 시작(09:30 ET) 전.
- S 날은 **입금만** 해요. 다음 봉(S+1) 시가에 A1 은 현금을 먼저 전부 지수로 바꾸고, 그날 주문을 처리해요.
- 미국 종목군은 S 날 S&P500 을 정해 둔 seed 로 섞은 40종목으로 **고정**돼요(재시작해도 그대로). 국내는 `KR_UNIVERSE` 32종목.
- start 가 성공하면 `prereg_<시장>.json`(사전 등록 숫자)이 생겨요. 이 파일은 지우거나 고치지 마세요.
- start 는 인터넷으로 시세·종목 목록·종목 이름을 받아요(보통 몇 분). 10분 넘게 아무 글도 안 나오면 Ctrl-C 로 멈춰도 돼요 — start 는 다 쓴 뒤에만 장부를 만들므로, 멈추면 아무것도 안 남고 다시 start 하면 돼요.
- 미국 start 가 `자료 문제 D2 … 종목 이름을 하나도 받지 못함` 으로 끝나면(종료 코드 4) 인터넷이 잠깐 끊긴 것이에요. 아무 파일도 안 남으니 몇 분 뒤 다시 start 하세요(이름은 start 때 한 번 고정돼요).
- start 화면에 `※ 종목 이름 38/40 …` 처럼 나오면 이름이 일부 빠진 것이에요. 빠진 종목은 팀장 글에 코드만 가요(판정·장부와는 상관없음). 그대로 진행해도 돼요.
- §4 의 launchd 가 이미 켜져 있으니, 그날 밤(국내)·다음 날 아침(미국)부터 자동으로 이어져요.

---

## 6. 매일 확인 습관 — `status` 읽기

```
cd /Users/나/claude-stock-h1
/Users/나/.venv-h1/bin/python h1.py status --market kr
```
나오는 줄(예)과 읽는 법:

| 줄 | 보는 것 |
|---|---|
| `시작 S … · 마지막 처리 봉 … · 판정 창 12/63 (남은 51봉)` | 마지막 처리 봉이 **가장 최근 거래일**인지. 하루 넘게 뒤처지면 로그 확인 |
| `L 오류 0 · 자료 멈춤 0 · 관문 거절 0 · 늦은 봉 0/10 · 한 번에 따라잡은 최대 1봉` | **L 오류는 0 이어야** 해요(1 이상이면 재시작 대상). 늦은 봉이 10 에 가까우면 맥을 더 꾸준히 켜 두기 |
| `재시작 0/2 (남은 2) · 마감 2027-06-30 까지 …일` | 남은 재시작 횟수와 마감 |
| `⑩ 사전 등록(prereg_kr.json, …): … 이 창 meta.rules 와 맞음` | "다름"이 나오면 판정 실패 |
| `⑥ 코드 동결: 창 안 코드·환경 지문 변경 0번` | 0번 또는 "모두 ⑥ 허용"이어야 해요 |
| `A0 쉬는 돈=현금 …` / `A1 쉬는 돈=SPY …` / `A1−A0 …` | 시장 요약. **기록일 뿐 판정에 안 써요** |

- 로그 보기: `tail -40 /Users/나/claude-stock-h1/logs/h1-kr.log`. 자세한 기록은 `state/h1/runs.jsonl`(실행마다 시작·끝 두 줄), `errors.jsonl`(L 오류).
- 자동 실행이 도는 중(국내 23:05 무렵, 팀장 호출로 몇 분)에 status 를 치면 `다른 H1 명령이 잠금 중이라 기다려요` 가 나오고 멈춘 듯 보여요. 몇 분 뒤 다시 치세요(Ctrl-C 해도 장부는 안전).
- **휴대폰으로 보기(아이폰, 선택)**: §4 plist 의 `sh -c` 글에서 `exit $c` 바로 앞에 아래 한 줄을 그대로 넣으면, 실행 뒤 상태 글이 iCloud Drive 에 생겨 휴대폰 '파일' 앱에서 볼 수 있어요(H1 폴더 자체는 iCloud 밖 그대로, 상태 글 사본만). plist 는 XML 이라 `&`·`<`·`>` 를 그대로 쓰면 파일이 깨지므로, 이 줄에는 그런 글자를 넣지 않았어요.
  `/Users/나/.venv-h1/bin/python h1.py status --market kr | tee "/Users/나/Library/Mobile Documents/com~apple~CloudDocs/H1-상태-kr.txt" ;`
  넣은 뒤에는 꼭 아래로 확인하고 다시 읽혀요(`OK` 가 아니면 고친 줄을 지우고 다시):
  ```
  plutil -lint /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  launchctl load -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  ```
  plist 가 깨지면 다음 재시동부터 매일 실행이 **알림도 없이** 멈춰요(5거래일이면 창 실패).

---

## 7. 매달 — 월간 보고서와 보관

```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
$P h1_report.py --market us --month 2026-12
$P h1_report.py --market kr --month 2026-12
```
- 결과: `state/h1/reports/<시장>-<YYYY-MM>.md`. 인터넷이 있으면 금리도 받아요(없어도 저장본으로 써요).
- **같은 달 보고서는 나중에 다시 만들어도 장부 숫자(2~8절)가 같아요.** 그래서 한 달을 놓쳐도 나중에 만들 수 있어요. 9절('A0+이자')만은 그사이 새 금리가 나오면 바뀔 수 있어요.
- **자동 실행(권장)**: 매달 2일 09:30 에 지난달 보고서. `nano /Users/나/Library/LaunchAgents/com.claude-stock.h1-report.plist` 로 아래를 만들고 `plutil -lint` → `launchctl load -w` (§4.2 와 같게).
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0">
  <dict>
    <key>Label</key><string>com.claude-stock.h1-report</string>
    <key>WorkingDirectory</key><string>/Users/나/claude-stock-h1</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/sh</string><string>-c</string>
      <string>m=$(date -v-1m +%Y-%m); for k in us kr; do /Users/나/.venv-h1/bin/python h1_report.py --market $k --month $m; done</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Day</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <key>StandardOutPath</key><string>/Users/나/claude-stock-h1/logs/h1-report.log</string>
    <key>StandardErrorPath</key><string>/Users/나/claude-stock-h1/logs/h1-report.log</string>
  </dict>
  </plist>
  ```
  그 시장을 아직 start 하지 않았으면 종료 코드 8(장부 없음)이 나와도 괜찮아요.
- **보관**(H1 폴더는 태그에 고정이라 거기서 커밋하지 않아요):
  1. **가장 쉬움**: 보고서를 iCloud Drive 의 폴더에 복사 → 휴대폰 '파일' 앱에서 바로 보여요.
     ```
     mkdir -p "/Users/나/Library/Mobile Documents/com~apple~CloudDocs/H1-보고서"
     cp /Users/나/claude-stock-h1/state/h1/reports/*.md "/Users/나/Library/Mobile Documents/com~apple~CloudDocs/H1-보고서/"
     ```
  2. git 으로 남기고 싶으면 운영 폴더의 브랜치는 **바꾸지 말고** 보고서 전용 폴더를 하나 더 만들어요:
     `cd /Users/나/claude-stock && git worktree add -b h1-reports /Users/나/h1-reports-git origin/h1-forward` →
     보고서를 `/Users/나/h1-reports-git/reports/h1-forward/` 에 복사 → 그 폴더에서
     `git add reports/h1-forward && git commit -m "H1 보고서 2026-12" && git push -u origin h1-reports`.
     **`git add .`·`git add reports` 는 쓰지 마세요**(다른 파일이 같이 올라갈 수 있어요).
- **읽는 순서**: 1절 고정 문장("수익률은 기록만", "A0 는 운영 장부가 아님") → 2절 운영 기준(오류·빠진 날·지문) → 3절 값(A1−A0, 지수 들고 있기) → 11절 한계.

---

## 8. 종료 코드가 0 이 아닐 때

| 코드 | 화면 | 뜻(쉽게) | 할 일 |
|---|---|---|---|
| 2 | `장부 논리 오류` | 장부 계산 점검(L1~L24)에서 틀린 곳을 찾음. **그 봉은 저장 안 됨**(장부는 안전) | ① 로그와 `state/h1/errors.jsonl` 을 Claude Code 에 보여 주고 원인 찾기 ② 점검 함수 쪽 잘못(거짓 양성)이면 설계 §2.2 ④ 길 ③ 아니면 고친 코드로 재현 통과 → 재시작(§9.3) |
| 3 | `재현을 통과하지 않은 코드·환경` / `규칙이 시작 때와 다름` | 코드나 venv(파이썬·라이브러리 버전)가 검사받은 것과 다름 | 무엇이 바뀌었는지 확인(파이썬이 업그레이드됐나?). §9.1 허용 변경이면 재현 통과 뒤 다시, 아니면 되돌리거나 재시작 |
| 4 | `자료 문제 D?` / `환경 문제(ENV)` | 시세를 못 받았거나 이상함, 또는 디스크·권한 문제. **재시작 아님** | 보조 시각에 저절로 다시 해요. D6(분할 의심)·보유 종목 D2 면 §9.2(1~2일 안에). 며칠 계속되면 늦은 봉 상한(10·5)에 주의 |
| 5 | `다른 H1 명령이 잠금 중` | 다른 h1 명령이 아직 도는 중 | 잠시 뒤 다음 실행이 해요. 계속되면 멈춘 python 확인 |
| 6 | `밀린 봉 N개 > 5` | 한 번에 따라잡을 수 있는 5봉을 넘김(맥이 1주 넘게 꺼짐 등) → **판정 창 실패** | 재시작(§9.3, 사유 `backlog`) |
| 7 | `기준 지수 늦음(D7)` | KS200(또는 SPY)이 아직 오늘 봉을 안 줌. 처리할 수 있던 봉은 저장됨 | 보조 실행이 다시 확인. 하루 넘게 계속되면 §3.7 의 KS200 줄로 확인. 연말·연초면 FinanceDataReader 연도 파일 문제 의심 |
| 8 | `장부 없음` / `start 거절` | 아직 start 안 함, 또는 늦은 start·재시작 상한 등으로 거절 | 처음이면 start(§5 시각). "폴더가 사라짐"이면 무엇이 지웠는지 먼저 확인 |
| 9 | `인자 오류` / `조건 불충족` | 명령을 잘못 침. **아무것도 안 바뀜** | 명령을 고쳐 다시(`python h1.py -h`) |
| 1 | 파이썬 오류(실행 전) | venv·라이브러리 문제 | `requirements-h1.txt` 로 venv 다시 확인 |
| 130 | 사람이 멈춤 | Ctrl-C | 다음 실행이 이어 가요 |
| (경고) | `늦은 봉`, `팀장 폴백`, `정지`, `W5` | 멈추지 않고 셈만 함 | 보고서에서 확인 |

---

## 9. 판정 창 동안 — 할 수 있는 것 / 없는 것

### 9.1 코드 동결
판정 창 동안은 코드·라이브러리를 바꾸지 않아요. **허용되는 변경은 넷뿐**이에요:
1. `h1_data.py`(시세 받기 층) 고침 — 자료 받기 골든 `tests/golden_data/` 이 그대로일 때
2. 라이브러리 버전 올림(`requirements-h1.txt`, 파이썬은 그대로)
3. 국내 매도세 표에 **줄 추가**(법이 바뀔 때) → 그다음 `h1.py amend-rules --market kr --source <법령 주소>`
4. 거짓 양성(점검 함수가 틀린 것) 고침 — 설계 §2.2 ④ 조건일 때

허용 변경 순서(진행 담당이 커밋·새 태그를 만든 뒤, **낮 10시 ~ 밤 10시 사이**에 — 자동 실행과 안 겹치게):
```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
git fetch origin --tags
git checkout h1-forward-v2
$P -m pip install -r requirements-h1.txt
$P h1_replay.py
```
- `h1-forward-v2` 는 새 태그 이름의 예예요. `pip install` 줄은 라이브러리 올림일 때 꼭 쳐요(아니면 재현이 옛 라이브러리로 통과해 버려요).
- 재현이 0 이 아니면 원래대로 되돌리고 화면을 Claude Code 에 보여 주세요. 라이브러리도 같이 되돌려야 해요(안 하면 매 실행 종료 코드 3):
  ```
  cd /Users/나/claude-stock-h1
  git checkout h1-forward-v1
  /Users/나/.venv-h1/bin/python -m pip install -r requirements-h1.txt
  ```
- 주의: 재현은 FinanceDataReader 를 가짜로 바꿔 쓰기 때문에 **FinanceDataReader 버전 올림이 시세 모양을 바꿔도 재현은 못 봐요.** 그건 매일 실행의 D6(이미 처리한 날 값이 바뀌었는지 확인)이 지켜요.
- 그 밖의 변경(프롬프트·`analyst.py`·트레이너 두뇌·점검 규칙·`h1_report.py` 등)은 **재시작 사유**예요.

### 9.2 기업 행위(분할·상장폐지·정정) 결정표
매일 실행이 `D6 분할 의심 r=…` 또는 보유 종목의 `D2`(시세 못 받음)로 멈추면(종료 코드 4) **그 시장 장부 전체가 멈춰요.** 하루 지날 때마다 늦은 봉이 하나씩 쓰이고(10개까지), 5거래일을 넘기면 창 실패예요. 그러니 **1~2일 안에** 1차 출처(거래소 공시·회사 발표)를 확인해 아래 하나를 골라요.

> **이 명령들은 장부를 바로 고치고 되돌릴 수 없어요**(상장폐지 등록만 정리 전 취소 가능). 표의 명령은 모양만 보여 주는 것이에요. `m`·`X`·`r`·`<…>` 를 실제 값으로 바꾼 명령을 **먼저 Claude Code 에 보여 주고 확인받은 뒤** 쳐요. 주소는 따옴표로 감싸요(예 `--source "https://…"`).

명령은 모두 아래 두 줄 뒤에 `$P h1.py corp-action …` 로 쳐요:
```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
```

| 확인 결과 | 명령 |
|---|---|
| 아직 모르겠음·공시 없음 | 기다림. **그동안 그 시장 전체가 멈춤**(위 설명) |
| 정수/분수 분할·병합이 맞음 | `h1.py corp-action --market m --code X --split r --date <효력일> --source <공시 주소>` (r = 새 주식 수 ÷ 옛 주식 수, 효력일 = 새 주식 수로 거래되는 첫 날) |
| 시세 제공처가 과거 값을 고친 것(분할 아님) | `h1.py corp-action --market m --code X --accept-correction --source <근거>` (장부는 그대로) |
| 상장폐지 | `h1.py corp-action --market m --code X --delist --confirm X --last-date <마지막 거래일> --last-close <종가> --source <공시>` (`--last-close` 를 비우면 장부 값). 실수였으면 정리 전에 `h1.py corp-action --market m --code X --cancel-delist --confirm X --source <근거>` |
| 유상증자·정수가 아닌 무상증자 등 공식으로 못 고치는 것 | 재시작(사유 `rule-change`) |

### 9.3 재시작
> **이 명령은 묻지 않고 바로 실행되고 되돌릴 수 없어요**(재시작 1번을 씀, 최대 2번). 치기 전에 Claude Code 에 로그를 보여 주고 사유가 맞는지 먼저 확인하세요.
> `--reason` 뒤에는 `L`, `backlog`, `rule-change` 중 **하나만** 적어요.

```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
$P h1.py restart --market kr --confirm kr --reason L --note "무슨 일이었는지"
```
그다음 그 시장의 start 시각(§5)에:
```
cd /Users/나/claude-stock-h1
P=/Users/나/.venv-h1/bin/python
$P h1.py start --market kr
```
- 사유 코드: `L` = 창 안의 장부 논리 오류 / `backlog` = 밀린 봉 초과·늦은 봉 상한 초과 / `rule-change` = 허용 밖 코드 변경 또는 공식으로 못 고치는 기업 행위.
  **수익률이 나빠서는 재시작 사유가 아니에요.** 사유의 근거가 일지에 없으면 거절돼요.
- 마감은 **2027-06-30**. 남은 평일로 63봉을 마감까지 못 채우면 그 시장은 "H1 포워드 실패"예요.
- 재시작해도 미국 종목군과 팀장 판정 기록은 그대로 이어져요. 이전 창 폴더는 보관돼요(지워지지 않음).

---

## 10. 리허설 (권장, start 전에)

`start` 는 한 번 성공하면 쉽게 다시 못 하므로, **이름이 전혀 다른 폴더**에서 1~2주 미리 돌려 보면 좋아요.
```
cd /Users/나/claude-stock
git worktree add /Users/나/h1-rehearsal h1-forward-v1
```
1. 그 폴더에서 §3.3 의 나머지(venv 는 같은 `/Users/나/.venv-h1` 을 써도 돼요)·§3.4(재현까지)를 해요. 명령의 `claude-stock-h1` 을 모두 `h1-rehearsal` 로 바꿔요.
2. 진짜 claude·실시세로 `start` → 며칠 `run`. 자동 실행을 쓰려면 plist 의 Label·파일 이름·폴더·로그를 **진짜와 다르게**(예 `com.claude-stock.h1r-kr`, `/Users/나/h1-rehearsal`) 만들어요. §4 plist 를 그대로 복사하면 진짜 작업과 엉켜요.
3. 잴 것: D6(미국 일봉이 뒤늦게 고쳐지는 일)이 얼마나 자주 나는지, D7(KS200 늦음), 팀장 한 번 묻는 데 걸리는 시간, 잠금 대기(종료 코드 5), 디스크 쓰기 문제(ENV, 종료 코드 4)가 안 나는지.
4. 리허설 동안 팀장 호출이 더 늘어요(운영 + 리허설, 같은 구독 한도).
5. 끝나면 지워요. **경로가 `h1-rehearsal` 인지 두 번 확인**하고(§13 의 경고 참고):
   ```
   launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1r-kr.plist
   rm /Users/나/Library/LaunchAgents/com.claude-stock.h1r-kr.plist
   cd /Users/나/claude-stock
   git worktree remove /Users/나/h1-rehearsal
   ```

---

## 11. 판정 창이 끝난 뒤 — "통과"의 뜻과 그다음

```
cd /Users/나/claude-stock-h1
/Users/나/.venv-h1/bin/python h1_report.py --market kr --final
```
- 결과: `state/h1/reports/kr-final-<S>.md`. 이 파일도 §7 처럼 보관해요.
- 최종 보고서 맨 위 "판정" 절이 **운영 기준 ①~③ 통과/실패**를 알려 줘요:
  ① 장부 논리 오류 0 ② 처리 누락일 0(늦은 봉은 상한 안) ③ 재현을 통과한 코드로만 운영.
- **통과해도 바로 운영을 바꾸지 않아요.** 통과는 "H1 장부가 잘 돌았다"는 뜻이고, 그다음에 "기본 장부를 H1 로 바꿀지 검토"를 따로 해요(사용자 결정 D-4).
- 그 검토에 필요한 것(지금은 아무것도 정해지지 않음, `docs/h1-intent-check.md` §3.3):
  1. 검토 기준(누가·무엇을 보고·언제 바꾼다/안 바꾼다). "쉬는 돈을 지수에 두면 시장 위험을 더 진다"를 받아들이는지.
  2. 운영 코드에 A1 길이 없음 — 운영도 `h1.py` 엔진으로 돌릴지, `team.py` 에 새로 넣을지(엔진 합치기, 개선 후보 14번).
  3. 서킷(운영은 켬, 영구 정지). A1 은 거의 100% 시장에 있어 하락 한 번에 걸리기 쉬움 → 그림자 서킷 기록이 근거 자료. 재개 규칙(D6)은 원래 저장소 공동작업자와 합의할 일.
  4. 금액(포워드 $100,000, 운영 $10,000).
  5. 실제 주문: KS200 은 지수라 못 삼 → 069500 같은 ETF(분배금·보수·정수 주). SPY 도 정수 주.
  6. 세금: 국내 날짜별 세율·지수 매도세 0 은 H1 경로에만 있음. 미국 양도세는 보고서 참고값뿐.
  7. H1 에만 있는 개선(판정 글자 정리·종목군 고정·사유 전체 저장·밀린 봉·깨진 장부 안 덮기·시세 실패 멈춤)을 운영에 옮길지.
  8. 팀장 채점 도구(판정별 30건 전엔 결론 금지).
  9. 미국·국내는 따로 판정 — 한 시장만 통과하면 그 시장만 검토 대상.
- 판정 창이 끝난 뒤에도 자동 실행을 계속 두면 "연장 구간"으로 기록이 쌓여요(판정에는 안 씀). 그만두려면 §13.

---

## 12. 운영과 H1 의 관계

- 운영 `team.py`·`order_runner.py` 는 운영 폴더에서 **그대로** 돌아요(국내 team.py 22:35, 미국 06:30 등 `docs/broker-run.md`).
- H1 코드는 증권사 모듈을 아예 읽지 않아요. H1 장부로 진짜 주문이 나갈 길이 없어요.
- **H1 의 A0 숫자를 운영 장부와 비교하면 안 돼요.** A0 는 $100,000·서킷 끔·고정 종목군이라 운영 장부와 조건이 달라요.
- H1 팀장 글에는 기준 날짜·시장·종목 이름이 더 들어가요(D-1). 운영 팀장 글은 그대로예요.

---

## 13. 멈추기·지우기

- **잠시 멈춤**:
  ```
  launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  ```
  (`-w` 를 붙여야 재시동 뒤에도 꺼진 채로 있어요. 다시 켤 때는 `launchctl load -w …`.) 다시 켜면 밀린 봉을 5개까지 따라잡지만, 따라잡은 봉은 **늦은 봉**(10개 한도)으로 세고, 5개를 넘으면 종료 코드 6 → 창 실패예요. 판정 창 동안은 멈추지 않는 게 좋아요.
- **판정 창을 포기**: 위처럼 끄고, 그때까지의 보고서를 보관(§7). 장부 폴더는 지우지 않아도 돼요.
- **완전히 지우기**(운영 폴더는 그대로):
  > **경고**: `git worktree remove` 는 `--force` 가 있든 없든 **그 폴더 전체를 지워요**(`state/` 장부·`logs/` 포함, 되돌릴 수 없음). 보고서·장부를 먼저 복사한 뒤에만 치세요. `--force` 는 그 폴더에 git 이 모르는 새 파일이 있을 때 필요해요. 경로가 `claude-stock-h1` 인지 두 번 확인하세요.
  ```
  cp -R /Users/나/claude-stock-h1/state/h1 "/Users/나/Library/Mobile Documents/com~apple~CloudDocs/H1-장부-보관"
  launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist
  launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-us.plist
  launchctl unload -w /Users/나/Library/LaunchAgents/com.claude-stock.h1-report.plist
  rm /Users/나/Library/LaunchAgents/com.claude-stock.h1-kr.plist /Users/나/Library/LaunchAgents/com.claude-stock.h1-us.plist /Users/나/Library/LaunchAgents/com.claude-stock.h1-report.plist
  cd /Users/나/claude-stock
  git worktree remove /Users/나/claude-stock-h1
  rm -rf /Users/나/.venv-h1
  ```
  운영 plist 는 이름이 `com.claude-stock.kr-…`·`us-…` 라 위 줄에 걸리지 않아요.

---

## 부록 A. 명령 한눈에 (모두 `/Users/나/claude-stock-h1` 에서, `python` = `/Users/나/.venv-h1/bin/python`)

| 명령 | 하는 일 |
|---|---|
| `h1.py start --market m` | 새 판정 창 시작(S 는 입금만) |
| `h1.py run --market m` | 매일 실행(새 확정 봉 처리, 밀린 봉 5개까지) |
| `h1.py status --market m` | 상태 보기(아무 때나, 아무것도 안 바꿈) |
| `h1.py restart --market m --confirm m --reason <L·backlog·rule-change 중 하나> --note "…"` | 시장 폴더를 보관하고 재시작 기록 → 다음은 start. **바로 실행, 되돌릴 수 없음** |
| `h1.py corp-action --market m --code X … --source …` | 분할·상장폐지(등록·취소)·정정 확정(§9.2) |
| `h1.py amend-rules --market kr --source …` | 국내 매도세 표 줄 추가 반영 |
| `h1_report.py --market m [--month YYYY-MM] [--final] [--offline]` | 월간·최종 보고서 |
| `h1_report.py --fetch-rates` | 금리만 받아 저장 |
| `h1_replay.py [--root state/h1]` | 재현(약 8분) |
| `tools/h1_test_guard.py --quick` | 시험 환경 지킴이 |

## 부록 B. 쓴 말

| 말 | 뜻 |
|---|---|
| 봉 | 하루치 시세(시가·고가·저가·종가). "확정 봉" = 장이 끝나 더 안 바뀌는 봉 |
| S, S+62 | 시작 봉, 63번째 봉(판정 창 끝) |
| 쉬는 돈 | 트레이너가 주식을 안 사서 남은 돈 |
| 지수 / ETF | 지수 = 여러 회사 주가를 모은 숫자(KS200). ETF = 지수를 따라가게 만든, 실제로 살 수 있는 상품(SPY, 069500) |
| 팀장 폴백 | 팀장(claude)이 답을 못 해 규칙만으로 정한 것 |
| 늦은 봉 | 다음 장이 이미 열린 뒤에 처리한 봉(팀장 없이 규칙만) |
| 사전 등록 | 결과를 보기 전에 규칙·기준을 적어 고정해 두는 것 |
| 코드 동결 | 판정 창 동안 코드·라이브러리를 바꾸지 않는 것 |
| 재현 | 과거 시세로 새 코드와 연구(R2) 시뮬레이터를 같이 돌려 같은지 맞춰 보는 것 |
| 관문 | 재현을 통과한 코드·환경이 아니면 실행을 거절하는 문 |
| 그림자 서킷 | 서킷(손실 한도 자동 정지)이 켜져 있었다면 걸렸을 날을 계산만 해서 적는 것 |
| 생존편향 | 지금 살아남은 큰 회사만 골라 과거를 보면 성적이 좋아 보이는 착시 |
| worktree | 한 저장소에서 다른 버전을 옆 폴더에 따로 꺼내 두는 git 기능 |
| launchd / plist | 맥의 "정해진 시각에 자동 실행" 기능 / 그 설정 파일 |
