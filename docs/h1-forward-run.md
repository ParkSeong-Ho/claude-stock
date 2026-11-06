# H1 포워드 모의매매 — 맥에서 돌리는 법 (운영 안내서)

> **진짜 돈도, 진짜 주문도 없습니다.** 실제 시세로 "가짜 장부" 두 개를 3개월 넘게 매일 쌓아 비교하는 시험이에요.
> 설계는 `docs/h1-forward-design.md`(3판 + §10), 원래 의도와 맞는지 대조한 것은 `docs/h1-intent-check.md`,
> 공부용 안내서는 `docs/h1-guide/`(README 부터)에 있어요. 이 문서는 **맥 앞에서 그대로 따라 하는 순서**만 적었어요.

---

## 0. 한 쪽 요약 (먼저 이것만 읽어도 됨)

- **무엇을 하나**: 같은 날·같은 돈($100,000 / ₩1억)으로 장부 두 개를 시작해요.
  - **A0**: 지금 방식. 트레이너가 주식을 안 산 돈(쉬는 돈)은 현금으로 둠.
  - **A1**: H1 방식. 쉬는 돈을 **지수**(미국 SPY, 국내 코스피200 지수 KS200)에 넣어 둠. 주식을 살 때 모자란 만큼만 지수를 팔아 씀.
  - 두 장부는 같은 트레이너 규칙·같은 후보·**같은 팀장 판정**을 써요. 다른 것은 "쉬는 돈을 어디에 두나" 하나뿐이에요.
- **얼마나**: 시장마다 시작 봉 S 부터 63거래일(S~S+62, 약 3개월). 미국·국내는 따로 시작하고 따로 판정해요.
- **어디서**: 운영 폴더(지금 `team.py` 를 돌리는 폴더)와 **다른 폴더**(H1 전용 worktree)에서, **다른 파이썬 환경**(H1 전용 venv)으로.
- **매일**: launchd 가 `h1.py run` 을 알아서 돌려요. 사람은 가끔 `h1.py status` 한 줄을 보고, 매달 보고서를 남기면 돼요.
- **통과의 뜻**: "장부가 63일 동안 틀린 계산 없이, 빠진 날 없이, 검사받은 코드로만 돌았다". **"A1 이 돈을 더 번다"는 뜻이 아니에요**(§1).
- **운영은 그대로**: 기존 `team.py`·`order_runner.py`·`state/` 는 하나도 안 바뀌고 평소처럼 돌아요.

---

## 1. 이 결과로 말할 수 있는 것 / 없는 것 (꼭 읽기)

| 말할 수 있는 것 | 말할 수 없는 것 |
|---|---|
| H1 장부가 실제 운영 조건(시세가 늦는 날, 맥이 꺼진 날, 팀장이 늦는 날)에서 63일 동안 **틀리지 않고** 돌았는지 | **H1(A1)이 A0 보다 낫다** — 3개월은 너무 짧아요 |
| 쉬는 돈을 지수에 두는 장치가 설계대로 움직였는지(지수 사고판 기록, 비용) | **트레이너가 지수보다 잘한다** — 과거 연구(R2)에서 트레이너 매매 시점은 미국에서 무작위보다 못했어요(백분위 12%·16%) |
| 매달 A1−A0 가 얼마였는지(기록) | **시장을 이긴다** — R2 에서 미국이 지수를 이긴 것은 "지금 큰 회사"를 고른 덕(생존편향)이었고, 그걸 줄이면 A1 이 지수에 졌어요 |

- **3개월의 A1−A0 는 대부분 "그동안 지수가 올랐나 내렸나"로 정해져요.**
  - 오르는 3개월이면 A1 이 앞서요(쉬는 돈도 같이 오르니까).
  - 내리는 3개월이면 A1 이 A0 보다 **더 잃어요**(현금 방석이 없음, R2 의 2018·2022 년이 그랬어요).
  - **둘 다 정상**이에요. "H1 이 증명됐다/틀렸다"로 읽으면 안 돼요.
- 숫자가 얼마나 흔들리는지 예: 재현에서 **시작을 하루만 미뤘는데** 몇 달 뒤 A1 평가액이 2~5% 달라졌어요
  (W1 미국 $99,217.87 vs $97,473.91, 국내 ₩75,291,686 vs ₩71,923,477). 그래서 수익률로 판정하지 않기로 미리 정했어요(사전 등록 ③).
- 배당은 넣지 않았어요(주식·지수 모두 가격만). SPY 는 ETF 라 운용보수는 이미 가격에 들어 있고, KS200 은 지수라 실제 ETF 보수가 빠져 있어요.
- R2 와 달리 이번에는 **팀장(claude)이 켜져 있어요**. 두 장부가 같은 판정을 쓰니 A1−A0 비교에는 문제가 없어요.

---

## 2. 시작 전에 정한 것 (사용자 결정, 2026-11-06)

첫 `h1.py start` 가 아래 숫자를 `state/h1/prereg_<시장>.json` 에 적고, **그 뒤로는 바꿀 수 없어요**(바꾸면 그 결과는 "탐색"일 뿐).

| # | 정할 것 | 정한 값 | 메모 |
|---|---|---|---|
| D-1 | Q4 팀장 프롬프트 | **H1 에서만 기준 날짜·시장·종목 이름을 넣음** | 국내는 회사 이름(예 `005930(삼성전자)`), 미국은 티커 그대로(예 `AAPL`). 운영 팀장 글은 그대로 |
| D-2 | N1 숫자 | **기본값 그대로**: 재시작 최대 2번 · 마감 2027-06-30 · 늦은 봉 창 전체 10·한 번에 5 · 팀장 폴백 20% 넘으면 "대표성 없음" 표시 | |
| D-3 | N2 주식 분할·병합 | **공식으로 이어 가기**(`corp-action --split`) | 유상증자·정수가 아닌 무상증자는 공식이 없어 재시작 |
| D-4 | 통과의 뜻 | **받아들임**: 통과 = 장부가 잘 돌았다. 수익률은 기록만. 바꿀지 검토는 3개월 뒤 따로(§10) | |
| D-5 | 어느 시장부터·언제 | 사용자가 맥에서 정함 | 국내 22:30 KST 뒤 ~ 다음 날 09:00 전, 미국 07:10 KST 무렵 |
| D-6 | 리허설 | 권장(§9) | start 는 한 번 성공하면 정해 둔 사유 없이는 다시 못 해요 |
| D-7 | 보고서 문장 고침 | **start 전에 넣음(끝)** | `h1_report.py` 11절 |

---

## 3. 처음 한 번 — 준비 (맥, 순서대로)

아래 `/Users/나/` 는 내 홈 폴더로 바꾸세요(launchd 는 `~` 를 못 알아들어요).

### 3.1 파이썬 3.13.18 고정
- 장부의 "환경 지문"에 파이썬 **패치 버전**(3.13.**18**)까지 들어가요. `brew upgrade` 로 3.13.19 가 되면 **매 실행 종료 코드 3**(재현 안 한 환경)이 나요.
- 방법 하나: python.org 설치본 또는 `uv`/`pyenv` 로 3.13.18 을 따로 두기. brew 를 쓰면 `brew pin python@3.13`.
- 확인: `/Users/나/.venv-h1/bin/python -V` → `Python 3.13.18`.

### 3.2 시계
- 시스템 설정 → 일반 → 날짜 및 시간: 시간대 **서울**, 자동으로 시간 설정 **켬**. "늦은 봉" 판단이 맥 시계에 달려 있어요.

### 3.3 H1 전용 폴더(worktree)와 venv
```bash
cd /Users/나/claude-stock                         # 운영 폴더(그대로 둔다)
git fetch origin
git worktree add /Users/나/claude-stock-h1 <H1 태그>   # 예: h1-forward-v1. 태그에 고정
cd /Users/나/claude-stock-h1
python3.13 -m venv /Users/나/.venv-h1
/Users/나/.venv-h1/bin/python -m pip install -r requirements-h1.txt
mkdir -p logs
```
- 폴더는 **iCloud 동기화 밖**에(`~/Desktop`·`~/Documents` 말고). 파일 이름 바꾸기·잠금이 동기화 폴더에서 깨질 수 있어요.
- 이 폴더의 `state/` 는 운영 폴더의 `state/` 와 **다른 폴더**예요. 운영 장부는 여기 없어요.
- **태그**: 아직 없어요(2026-11-06 기준). 단계 6 문서 검토가 끝난 커밋에 진행 담당(또는 사용자)이 `h1-forward-v1` 같은 태그를 찍고 푸시해요. 태그를 찍은 뒤로는 그 코드로만 돌려요.

### 3.4 시험 → 지킴이 → 재현 → 지문 확인 (이 순서 그대로)
```bash
P=/Users/나/.venv-h1/bin/python
$P -m pytest -q                                    # 전부 통과(지금 936개)
git fetch origin research-r2-2026-11-04            # 재현 기준값(R2) 자료
$P tools/h1_test_guard.py --quick                  # 인터넷 0·claude 0·결정성. "모두 통과"
$P h1_replay.py                                     # 약 8분. "종료 코드 0 — 통과 + 기록함"
$P -c "import h1; print(h1.code_hash()[0])"        # 아래 파일의 마지막 줄 code_hash 와 같아야 함
tail -1 state/h1/replay_pass.json
```
- 재현(`h1_replay.py`)은 과거 시세로 새 코드와 R2 연구 시뮬레이터를 같이 돌려 **체결 하나하나까지 같은지** 봐요. 통과하면 `replay_pass.json` 에 "이 코드·이 환경은 검사받았다"가 적혀요.
- 이 기록이 없거나 코드·환경이 다르면 `h1.py` 는 실행을 거절해요(종료 코드 3, "관문").
- 재현 종료 코드: 0 통과·기록 / 3 일부 창만 통과(기록 안 함) / 2 차이 있음 / 4 환경 문제 / 9 인자 오류 / 130 멈춤.

### 3.5 launchd 와 같은 환경에서 팀장(claude) 한 번 시험
launchd 는 터미널과 PATH·환경이 달라서, 터미널에서 되던 `claude` 가 안 될 수 있어요(그러면 팀장이 매일 폴백).
```bash
which claude                                        # 이 폴더를 plist PATH 에 넣음
env -i HOME=$HOME PATH=<plist 에 넣을 PATH> sh -c 'cd /Users/나/claude-stock-h1/state/h1 2>/dev/null || cd /tmp; claude -p "JSON 하나만: {\"ok\": true}"'
```
- JSON 이 나오면 OK. 로그인 창·오류가 나오면 키체인 로그인·`node` 경로·전역 훅을 확인해요.
- **`ANTHROPIC_API_KEY` 는 설정하지 마세요**(구독 대신 종량 요금). 코드도 이 변수를 지우고 부르지만, 설정 자체를 하지 않는 게 안전해요.

### 3.6 잠자기
- `sudo pmset repeat wakeorpoweron MTWRFS 07:00:00` — 매일 아침 7시에 깨움(깨우는 시각은 하나만 둘 수 있어요).
- 실행 중 잠들지 않게 launchd 명령 앞에 `/usr/bin/caffeinate -i` 를 붙여요(§4).
- launchd 는 **잠자기**에서 깨면 놓친 작업을 한 번 돌리지만, **껐다 켜면** 돌리지 않아요. 그래도 다음 예정 실행이 밀린 봉을 5개까지 따라잡아요.
- 노트북이면 덮개를 닫은 채·배터리에서 정말 깨는지 한 번 확인해요.

### 3.7 시작 전 마지막 확인
1. 설계 문서 최종판이 커밋돼 있는지(`git status` 깨끗, `git log -1` 이 태그 커밋).
2. `$P h1.py status --market kr` → "장부 없음 → python h1.py start" 가 나오면 정상.
3. 자료 원본: KS200 캐시가 최근까지 갱신되는지(`docs/kr-fix-s0.md` §5), 미국은 S&P500 목록 받기가 되는지.
4. 운영 쪽 launchd(team.py·order_runner)가 H1 폴더를 가리키지 않는지.

### 3.8 시작
```bash
$P h1.py start --market kr     # 국내: 22:30 KST 뒤 ~ 다음 날 09:00 전 (그 뒤면 "늦은 start" 거절 8, 파일은 안 남음)
$P h1.py start --market us     # 미국: 07:10 KST 무렵 (16:30 ET 뒤 ~ 09:30 ET 전)
```
- S 날은 **입금만** 해요. 다음 봉(S+1) 시가에 A1 은 현금을 먼저 전부 지수로 바꾸고, 그날 주문을 처리해요.
- 미국 종목군은 S 날 S&P500 을 정해 둔 seed 로 섞은 40종목으로 **고정**돼요(재시작해도 그대로). 국내는 `KR_UNIVERSE` 32종목.
- start 가 성공하면 `prereg_<시장>.json`(사전 등록 숫자)이 생겨요. 이 파일은 지우거나 고치지 마세요.

---

## 4. 매일 — launchd 일정

| 시장 | 명령 | 시각(맥 = 한국 시간) | 왜 이 시각 |
|---|---|---|---|
| 국내 | `h1.py run --market kr` | **월~금 23:05** + 보조 **월~토 07:40** | KS200 이 22:30 뒤에 오늘 봉을 인정. 보조는 23:05 실패·KS200 늦은 날(종료 코드 7)을 챙김. 07:40 은 09:00 전이라 "늦은 봉"이 아님. 월요일 07:40 은 금요일 봉의 세 번째 기회 |
| 미국 | `h1.py run --market us` | **화~토 07:10** + 보조 **월~토 08:40** | 07:10 KST = 겨울 17:10 ET / 여름 18:10 ET → 늘 미국 장 마감(16:00 ET) 뒤·다음 장(09:30 ET) 전. 서머타임이 바뀌어도 시각을 안 고쳐도 돼요 |
| 둘 다 | `h1_report.py --market us` / `kr` | 매달 2일 09:30 (§6) | |

- 휴장일에는 새 봉이 없어 "이미 처리됨"(종료 코드 0)으로 바로 끝나요. 같은 봉을 두 번 돌려도 파일이 안 바뀌어요.
- 국내 보조(07:40)와 미국(07:10)은 시장별 잠금이 따로라 겹쳐도 괜찮아요.
- 팀장 호출이 하루에 대략 **두 배**가 돼요(운영 + H1, 같은 구독 한도).

plist 하나 예(국내, `~/Library/LaunchAgents/com.claude-stock.h1-kr.plist`). 모양은 `docs/broker-run.md` 와 같아요.
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.claude-stock.h1-kr</string>
  <key>WorkingDirectory</key><string>/Users/나/claude-stock-h1</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>  <!-- which claude 로 나온 폴더 -->
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string><string>-c</string>
    <string>/usr/bin/caffeinate -i /Users/나/.venv-h1/bin/python h1.py run --market kr; c=$?; [ $c -eq 0 ] || osascript -e "display notification \"H1 국내 종료 코드 $c (logs/h1-kr.log)\" with title \"claude-stock\""; exit $c</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <!-- 월(1)~금(5) 23:05 -->
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
    <!-- 보조: 월(1)~토(6) 07:40 -->
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
- 미국(`com.claude-stock.h1-us`)은 `--market us`, 화(2)~토(6) 07:10 + 월(1)~토(6) 08:40, 로그 `logs/h1-us.log`.
- 켜기: `launchctl load ~/Library/LaunchAgents/com.claude-stock.h1-kr.plist`. 한 번 바로 돌려 보기: `launchctl kickstart gui/$(id -u)/com.claude-stock.h1-kr`.
- 처음 한 번 돌린 뒤 `state/h1/runs.jsonl` 마지막 줄의 `cli_version` 이 비어 있지 않은지 봐요(비었으면 launchd 에서 claude 를 못 찾은 것).
- 알림은 **맥 화면에만** 떠요. 맥 앞에 없으면 놓쳐요 → §5 의 매일 확인 습관.

---

## 5. 매일 확인 습관 — `status` 한 줄 읽기

```bash
cd /Users/나/claude-stock-h1 && /Users/나/.venv-h1/bin/python h1.py status --market kr
```
나오는 줄(예)과 읽는 법:

| 줄 | 보는 것 |
|---|---|
| `시작 S … · 마지막 처리 봉 … · 판정 창 12/63 (남은 51봉)` | 마지막 처리 봉이 **가장 최근 거래일**인지. 하루 넘게 뒤처지면 로그 확인 |
| `L 오류 0 · 자료 멈춤 0 · 관문 거절 0 · 늦은 봉 0/10 · 한 번에 따라잡은 최대 1봉` | **L 오류는 0 이어야** 해요(1 이상이면 재시작 대상). 늦은 봉이 10 에 가까우면 맥을 더 자주 켜 두기 |
| `⑩ 사전 등록(prereg_kr.json, …): … 이 창 meta.rules 와 맞음` | "다름"이 나오면 판정 실패 |
| `⑥ 코드 동결: 창 안 코드·환경 지문 변경 0번` | 0번 또는 "모두 ⑥ 허용"이어야 해요 |
| 트레이너별 요약 줄 | A0·A1 평가액. **기록일 뿐 판정에 안 써요** |

로그는 `logs/h1-kr.log`·`logs/h1-us.log`, 자세한 기록은 `state/h1/runs.jsonl`(실행마다 한 줄), `errors.jsonl`(L 오류).

---

## 6. 매달 — 월간 보고서와 보관

```bash
P=/Users/나/.venv-h1/bin/python
$P h1_report.py --market us --month 2026-12        # 그달 보고서. --month 없으면 마지막 처리 봉의 달
$P h1_report.py --market kr --month 2026-12
```
- 결과: `state/h1/reports/<시장>-<YYYY-MM>.md`. 인터넷이 있으면 금리도 받아요(없으면 `--offline`, 저장본 사용).
- **같은 달 보고서는 나중에 다시 만들어도 2~9절 숫자가 같아요.** 그래서 한 달을 놓쳐도 나중에 만들 수 있어요.
- **자동 실행(권장)**: launchd(`com.claude-stock.h1-report`)로 매달 2일 09:30 에 지난달 보고서를 만들어요. plist 는 §4 와 같은 모양에서 두 곳만 바꿔요.
  - 시각: `<key>StartCalendarInterval</key><dict><key>Day</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>`
  - `sh -c` 안의 명령(맥의 `date -v-1m` = 한 달 전):
    ```sh
    m=$(date -v-1m +%Y-%m); for k in us kr; do /Users/나/.venv-h1/bin/python h1_report.py --market $k --month $m; done
    ```
  - 로그는 `logs/h1-report.log`. 그 시장을 아직 start 하지 않았으면 종료 코드 8(장부 없음)이 나와도 괜찮아요.
- **보관**: `state/` 는 git 이 무시하고 H1 폴더는 태그에 고정이라 거기서 커밋하지 않아요. 대신
  1. 보고서 파일을 `/Users/나/H1-보고서/` 같은 보관 폴더에 복사(가장 쉬움), 또는
  2. 운영 폴더에서 별도 브랜치(예 `h1-reports`)를 만들어 `reports/h1-forward/` 아래에 복사해 커밋·푸시(휴대폰 GitHub 에서도 보임).
- **읽는 순서**: 1절 고정 문장("수익률은 기록만", "A0 는 운영 장부가 아님") → 2절 운영 기준(오류·빠진 날·지문) → 3절 값(A1−A0, 지수 들고 있기) → 11절 한계.
- 판정 창이 끝나면(S+62 를 처리한 뒤) `--final` 로 최종 보고서(§10).

---

## 7. 종료 코드가 0 이 아닐 때

| 코드 | 화면 | 뜻(쉽게) | 할 일 |
|---|---|---|---|
| 2 | `장부 논리 오류` | 장부 계산 점검(L1~L24)에서 틀린 곳을 찾음. **그 봉은 저장 안 됨**(장부는 안전) | ① 로그와 `state/h1/errors.jsonl` 을 Claude Code 에 보여 주고 원인 찾기 ② 점검 함수 쪽 잘못(거짓 양성)이면 설계 §2.2 ④ 길 ③ 아니면 고친 코드로 재현 통과 → 재시작(§8) |
| 3 | `재현을 통과하지 않은 코드·환경` / `규칙이 시작 때와 다름` | 코드나 venv(파이썬·라이브러리 버전)가 검사받은 것과 다름 | 무엇이 바뀌었는지 확인(brew 업그레이드?). §8.1 허용 변경이면 재현 통과 뒤 다시, 아니면 원래대로 되돌리거나 재시작 |
| 4 | `자료 문제 D?` / `환경 문제(ENV)` | 시세를 못 받았거나 이상함, 또는 디스크·권한 문제. **재시작 아님** | 보조 시각에 저절로 다시 해요. D6(분할 의심)이면 §8.2. 며칠 계속되면 늦은 봉 상한(10·5)에 주의 |
| 5 | `다른 H1 명령이 잠금 중` | 다른 h1 명령이 아직 도는 중 | 잠시 뒤 다음 실행이 해요. 계속되면 멈춘 python 확인 |
| 6 | `밀린 봉 N개 > 5` | 한 번에 따라잡을 수 있는 5봉을 넘김(맥이 1주 넘게 꺼짐 등) → **판정 창 실패** | 재시작(§8, 사유 `backlog`) |
| 7 | `기준 지수 늦음(D7)` | KS200(또는 SPY)이 아직 오늘 봉을 안 줌. 처리할 수 있던 봉은 저장됨 | 보조 실행이 다시 확인. 하루 넘게 계속되면 KS200 캐시 확인(`docs/kr-fix-s0.md` §5). 연말·연초면 FinanceDataReader 연도 파일 문제 의심 |
| 8 | `장부 없음` / `start 거절` | 아직 start 안 함, 또는 늦은 start·재시작 상한 등으로 거절 | 처음이면 start. "폴더가 사라짐"이면 무엇이 지웠는지 먼저 확인 |
| 9 | `인자 오류` / `조건 불충족` | 명령을 잘못 침. **아무것도 안 바뀜** | 명령을 고쳐 다시(`python h1.py -h`) |
| 1 | 파이썬 오류(실행 전) | venv·라이브러리 문제 | `requirements-h1.txt` 로 venv 다시 확인 |
| 130 | 사람이 멈춤 | Ctrl-C | 다음 실행이 이어 가요 |
| (경고) | `늦은 봉`, `팀장 폴백`, `정지`, `W5` | 멈추지 않고 셈만 함 | 보고서에서 확인 |

---

## 8. 판정 창 동안 — 할 수 있는 것 / 없는 것

### 8.1 코드 동결
판정 창 동안은 코드·라이브러리를 바꾸지 않아요. **허용되는 변경은 넷뿐**이에요:
1. `h1_data.py`(시세 받기 층) 고침 — 자료 받기 골든 `tests/golden_data/` 이 그대로일 때
2. 라이브러리 버전 올림(`requirements-h1.txt`, 파이썬은 그대로)
3. 국내 매도세 표에 **줄 추가**(법이 바뀔 때) → 그다음 `h1.py amend-rules --market kr --source <법령 주소>`
4. 거짓 양성(점검 함수가 틀린 것) 고침 — 설계 §2.2 ④ 조건일 때

허용 변경 순서: **커밋 → 태그 → H1 폴더에서 `git checkout <새 태그>` → `h1_replay.py` 통과 → 다음 실행.**
- 주의: 재현은 FinanceDataReader 를 가짜로 바꿔 쓰기 때문에 **FinanceDataReader 버전 올림이 시세 모양을 바꿔도 재현은 못 봐요.** 그건 매일 실행의 D6(이미 처리한 날 값이 바뀌었는지 확인)이 지켜요.
- 그 밖의 변경(프롬프트·`analyst.py`·트레이너 두뇌·점검 규칙·`h1_report.py` 등)은 **재시작 사유**예요.

### 8.2 기업 행위(분할·상장폐지·정정) 결정표
매일 실행이 "D6 분할 의심 r=…" 로 멈추면(종료 코드 4), **1차 출처**(거래소 공시·회사 발표)를 사람이 확인하고 하나를 골라요.

| 확인 결과 | 명령 |
|---|---|
| 아직 모르겠음·공시 없음 | 기다림(그날만 멈춤, 다음 실행이 다시 봄). 며칠 넘으면 늦은 봉 상한 주의 |
| 정수/분수 분할·병합이 맞음 | `h1.py corp-action --market m --code X --split r --date <효력일> --source <공시 주소>` (r = 새 주식 수 ÷ 옛 주식 수, 효력일 = 새 주식 수로 거래되는 첫 날) |
| 시세 제공처가 과거 값을 고친 것(분할 아님) | `h1.py corp-action --market m --code X --accept-correction --source <근거>` (장부는 그대로) |
| 상장폐지 | `h1.py corp-action --market m --code X --delist --confirm X --last-date <마지막 거래일> [--last-close <종가>] --source <공시>`. 실수였으면 정리 전에 `--cancel-delist --confirm X` |
| 유상증자·정수가 아닌 무상증자 등 공식으로 못 고치는 것 | 재시작(사유 `rule-change`) |

### 8.3 재시작
```bash
$P h1.py restart --market kr --confirm kr --reason L|backlog|rule-change --note "무슨 일이었는지"
$P h1.py start --market kr
```
- 사유 코드: `L` = 창 안의 장부 논리 오류 / `backlog` = 밀린 봉 초과·늦은 봉 상한 초과 / `rule-change` = 허용 밖 코드 변경 또는 공식으로 못 고치는 기업 행위.
  **수익률이 나빠서는 재시작 사유가 아니에요.** 사유의 근거가 일지에 없으면 거절돼요.
- 재시작은 **최대 2번**, 마감 **2027-06-30**. 남은 평일로 63봉을 마감까지 못 채우면 그 시장은 "H1 포워드 실패"예요.
- 재시작해도 미국 종목군과 팀장 판정 기록은 그대로 이어져요. 이전 창 폴더는 보관돼요(지워지지 않음).

---

## 9. 리허설 (권장, start 전에)

`start` 는 한 번 성공하면 쉽게 다시 못 하므로, **다른 폴더**에서 1~2주 미리 돌려 보면 좋아요.
1. `git worktree add /Users/나/claude-stock-h1-rehearsal <태그>` → §3.4 그대로(재현까지).
2. 진짜 claude·실시세로 `start` → 며칠 `run`(launchd 없이 손으로 또는 임시 plist).
3. 잴 것: D6(미국 일봉이 뒤늦게 고쳐지는 일)이 얼마나 자주 나는지, D7(KS200 늦음), 팀장 한 번 묻는 데 걸리는 시간, 잠금 대기(종료 코드 5).
4. 끝나면 그 폴더를 지워요: `git worktree remove /Users/나/claude-stock-h1-rehearsal`(리허설 plist 도 끄기).

---

## 10. 판정 창이 끝난 뒤 — "통과"의 뜻과 그다음

```bash
$P h1_report.py --market kr --final
```
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
- 판정 창이 끝난 뒤에도 launchd 를 계속 두면 "연장 구간"으로 기록이 쌓여요(판정에는 안 씀). 그만두려면 §12.

---

## 11. 운영과 H1 의 관계

- 운영 `team.py`·`order_runner.py` 는 운영 폴더에서 **그대로** 돌아요(국내 team.py 22:35, 미국 06:30 등 `docs/broker-run.md`).
- H1 코드는 증권사 모듈을 아예 읽지 않아요. H1 장부로 진짜 주문이 나갈 길이 없어요.
- **H1 의 A0 숫자를 운영 장부와 비교하면 안 돼요.** A0 는 $100,000·서킷 끔·고정 종목군이라 운영 장부와 조건이 달라요.
- H1 팀장 글에는 날짜·시장·국내 회사 이름이 더 들어가요(D-1). 운영 팀장 글은 그대로예요.

---

## 12. 멈추기·지우기

- 잠시 멈춤: `launchctl unload ~/Library/LaunchAgents/com.claude-stock.h1-kr.plist`(미국도 같게). 다시 켜면 밀린 봉을 5개까지 따라잡아요(넘으면 종료 코드 6 → 창 실패).
- 판정 창을 포기: 위처럼 끄고, 그때까지의 보고서를 보관(§6). 장부 폴더는 지우지 않아도 돼요.
- 완전히 지우기(운영 폴더는 그대로):
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.claude-stock.h1-*.plist
  cd /Users/나/claude-stock && git worktree remove --force /Users/나/claude-stock-h1
  rm -rf /Users/나/.venv-h1
  ```
  `--force` 는 H1 폴더의 `state/`·`logs/`(git 이 무시하는 파일)까지 지워요. 보고서를 먼저 보관하세요.

---

## 부록 A. 명령 한눈에

| 명령 | 하는 일 |
|---|---|
| `h1.py start --market m` | 새 판정 창 시작(S 는 입금만) |
| `h1.py run --market m` | 매일 실행(새 확정 봉 처리, 밀린 봉 5개까지) |
| `h1.py status --market m` | 상태 보기(아무 때나, 아무것도 안 바꿈) |
| `h1.py restart --market m --confirm m --reason … [--note …]` | 시장 폴더를 보관하고 재시작 기록 → 다음은 start |
| `h1.py corp-action --market m --code X …` | 분할·상장폐지(등록·취소)·정정 확정(§8.2) |
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
