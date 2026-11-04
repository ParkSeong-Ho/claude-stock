# 증권사 주문 돌리기 — 언제 무엇을 실행하나

`order_runner.py` 사용 설명서. 설계는 `docs/kr-broker-design.md`(K-D2~K-D5), 키 준비는 `docs/kis-setup.md`.

## 한눈에

장부(가짜 지갑 `paper_wallet`)가 **정답**이에요. 증권사 모의계좌는 "주문이 정말 들어가고 체결되는가"를 확인하는 용도예요.
그래서 하루는 세 단계로 돌아요.

| 단계 | 명령 | 하는 일 |
|---|---|---|
| ① 신호 | `python team.py 40 --market kr` | 확정 봉으로 판단 → 내일 주문을 `pending` 에 저장. 어제 주문은 오늘 시가로 **장부 체결** |
| ② 주문 | `python order_runner.py place --market kr --broker kis` | `pending` → 증권사 **지정가** 주문 |
| ③ 맞춰 보기 | `python order_runner.py reconcile --market kr --broker kis` | 그날 증권사 체결 조회 → 장부와 비교 → `reports/broker/kr-<날짜>.md` |

- 처음엔 `--broker paper` 로 연습하세요(인터넷·키 없이 파일에만 기록, 지정가에 바로 체결된 것으로 봄).
- `--market` 은 꼭 적어야 해요(`us` 또는 `kr`). 지갑·상태 파일이 시장별로 따로예요:
  미국 `state/team_<트레이너>.json`, 국내 `state/kr/team_<트레이너>.json`.

## 시간표 (맥 시계 = 한국시간 기준)

### 국내 (KOSPI, 장 09:00~15:30 KST)

| 시각 (평일) | 실행 | 메모 |
|---|---|---|
| 22:35 (또는 다음 날 08:00) | `team.py 40 --market kr` | 종목 봉은 16:00 이면 확정이지만, 기준 날짜를 정하는 **KS200 은 22:30 KST 뒤에야 오늘 봉을 인정**(2026-11-04 변경, `docs/kr-fix-s0.md`). 16:30 에 돌리면 기준 날짜가 하루 전이라 주문이 하루씩 밀림 |
| 다음 날 09:05 | `order_runner.py place --market kr --broker kis` | 08:30~09:00 동시호가가 끝난 뒤 |
| 15:40 | `order_runner.py reconcile --market kr --broker kis` | 장 마감(15:30) 뒤. 장부 칸은 아직 "미반영"이 정상 |
| (선택) 22:50 또는 다음 날 08:10 | `order_runner.py reconcile --market kr --broker kis --date <그날>` | team.py 가 그날 시가로 장부 체결한 뒤라 **장부 칸까지 채워짐** |

- 거래정지 종목: 장부(team)는 정지 중 체결하지 않고 정지가 풀린 첫 거래일 시가에 체결한다. 지정가는 신호일 이하
  마지막 **거래된** 봉의 종가 기준(2026-11-04). 다만 **종이 브로커(`--broker paper`)는 거래정지를 모른다** —
  정지 중에도 place 하면 지정가에 바로 '체결'로 적는다(그날 reconcile 이 장부와 어긋나는 게 정상). KIS 는 정지 종목
  주문을 거절하고, 거절(rejected)은 다음 거래일에 다시 낼 수 있다.

### 미국 (장 09:30~16:00 ET)

미국 시간은 서머타임 때문에 한국시간이 1시간씩 바뀌어요.

| 단계 | 미국 동부(ET) | 한국 — 겨울(11월 첫 일요일~3월 둘째 일요일) | 한국 — 여름 |
|---|---|---|---|
| team.py | 마감 후 16:15 이후 | **다음 날 06:30** (화~토) | 05:30 (화~토) |
| place | 다음 개장 직후 09:35 | **23:35** (월~금) | 22:35 (월~금) |
| reconcile | 마감 후, team.py 뒤 | **다음 날 06:45** (화~토) | 05:45 (화~토) |

- 미국 `reconcile` 은 team.py **다음**에 돌리세요. 그래야 장부 칸이 채워져요.
- `--date` 를 안 주면 **그 시장 현지 날짜의 오늘**이에요. 한국 06:45 는 뉴욕으로 아직 전날 16:45 라서, 방금 끝난 미국 거래일이 자동으로 잡혀요.
- 지난 날짜를 다시 보고 싶으면 `--date 2026-11-05` (그 시장 현지 날짜).
- 서머타임이 바뀌는 날(3월 둘째 일요일, 11월 첫 일요일) launchd 시각도 바꿔 주세요.

## 자동 실행 (launchd 예시)

맥에서는 `cron` 보다 `launchd` 가 잠자기 후에도 놓친 작업을 챙겨 줘요.
`~/Library/LaunchAgents/` 에 아래 파일을 만들고 `launchctl load ~/Library/LaunchAgents/<파일>` 로 켭니다.
`/Users/나/claude-stock` 과 `/Users/나/.venv-cs` 는 내 경로로 바꾸세요(launchd 는 `~` 를 못 알아들어요).

국내 place (`com.claude-stock.kr-place.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.claude-stock.kr-place</string>
  <key>WorkingDirectory</key><string>/Users/나/claude-stock</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/나/.venv-cs/bin/python</string>
    <string>order_runner.py</string>
    <string>place</string>
    <string>--market</string><string>kr</string>
    <string>--broker</string><string>kis</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key><string>/Users/나/claude-stock/logs/kr-place.log</string>
  <key>StandardErrorPath</key><string>/Users/나/claude-stock/logs/kr-place.log</string>
</dict>
</plist>
```

나머지도 같은 모양으로 `Label`·`ProgramArguments`·시각만 바꿔요.

| 파일 | ProgramArguments (python 다음) | 시각 (Weekday: 1=월 … 6=토) |
|---|---|---|
| `kr-team` | `team.py 40 --market kr` | 월~금 16:30 |
| `kr-place` | `order_runner.py place --market kr --broker kis` | 월~금 09:05 |
| `kr-reconcile` | `order_runner.py reconcile --market kr --broker kis` | 월~금 15:40, 16:45 (dict 를 두 벌) |
| `us-team` | `team.py 40 --market us` | 화~토 06:30 (겨울) |
| `us-place` | `order_runner.py place --market us --broker kis` | 월~금 23:35 (겨울) |
| `us-reconcile` | `order_runner.py reconcile --market us --broker kis` | 화~토 06:45 (겨울) |

- `logs/` 폴더는 미리 만들어 두세요(`mkdir -p logs`). `*.log` 는 이미 gitignore 돼 있어요.
- 잠자기 중이면 실행이 안 되니 `시스템 설정 → 배터리 → 옵션` 또는 `sudo pmset repeat wakeorpoweron MTWRF 09:00:00` 처럼 깨우기를 걸어 두세요.
- `launchctl list | grep claude-stock` 로 켜졌는지, 로그 파일로 결과를 확인해요.

## place 가 지키는 규칙

- **지정가만**(K-D4). 가격 = 신호 봉 종가 × (1 ± 0.5%) 를 호가단위로: 매수는 올림, 매도는 내림(K-D5).
- **매수 수량** = 상한(트레이너 예산 × 종목상한) 안에서 살 수 있는 수와 증권사 매수가능수량 중 작은 값.
  0주면 주문을 내지 않고 `보류` 로 사유를 남겨요(상한 부족 / 매수가능 0주 / 종가 못 구함 / 장부에 이미 보유).
- **매도 수량** = 장부에 있는 보유 수량.
- **중복 방지**: `state/broker/<시장>-orders.jsonl` 에 주문마다 "보내는 중"을 **먼저** 적고 보낸 뒤 결과를 적어요.
  주문 이름(`client_id` = `시장-트레이너-종목-매수/매도-신호일`)이 이미 있으면 다시 내지 않아요. 몇 번을 돌려도 주문은 한 번.
- **주문은 재시도 안 함.** 오류가 나도 같은 날 다시 내지 않아요.
  - `rejected`(거절)·`rate_limit`·`auth`·`mock_expired` 는 "확실히 안 들어간" 경우라, 다음 거래일에 아직 `pending` 에 남아 있으면 그때 다시 낼 수 있어요(예: 휴장일에 돌렸다가 거절된 주문).
  - `network`·`unknown`·**결과 불명**(보내다 꺼짐)은 실제로 들어갔을 수도 있어서 **다시는 안 내요**.
- **오류가 나면**: 그 주문만 실패로 적고 다음 주문으로 넘어가요. 단 아래 둘은 남은 주문을 **멈춰요**.
  - `mock_expired` (KIS 오류 `40910000`): 모의투자 기간 만료. 화면에 `!!!!` 줄로 크게 알려요. KIS 홈페이지에서 모의투자를 다시 신청하세요.
  - `auth`: 키·시크릿·계좌번호·토큰 문제. `.env` 를 확인하세요.
  - 멈춘 뒤 남은 주문은 기록하지 않으니, 고치고 **같은 날 다시 place** 하면 그것만 나가요.
- 종료코드: 0 = 전부 성공, 1 = 실패한 주문 있음, 2 = mock_expired/auth 로 중단. 로그에서 확인하세요.
- 주말(그 시장 현지 기준)에는 아무것도 내지 않아요.

## reconcile 보고서 읽는 법

`reports/broker/<시장>-<날짜>.md` — 몇 번을 돌려도 같은 파일을 새로 써요. 장부는 절대 고치지 않아요(K-D3).

| 상태 | 뜻 |
|---|---|
| 일치 | 증권사 체결 수량 = 장부 체결 수량. 가격 차이 칸에 (증권사 평균가 ÷ 장부 시가 − 1) |
| 부분체결 / 미체결 | 지정가에 일부만·전혀 안 닿음. 시가가 0.5% 넘게 튀면 흔해요(장부는 시가로 체결되므로 차이로 남음) |
| 체결 (장부 미반영) | 증권사는 체결, 장부는 team.py 가 아직 이 날 봉을 처리 안 함 → team.py 뒤 다시 reconcile |
| 장부는 보류 / 수량 다름 | 장부와 증권사가 다르게 처리함 — 원인을 살펴볼 것 |
| 주문 오류(종류) | place 때 실패. 메모 칸에 증권사 메시지 |
| 결과 불명 | 보내다 멈춘 주문. **증권사 앱에서 직접 확인** |

"주문 기록에 없는 체결"은 이 프로그램이 내지 않은 체결이에요(앱에서 손으로 낸 주문 등).

## 주의사항

- **실전 계좌 금지.** `.env` 의 `KIS_MODE` 는 `mock`(기본) 그대로. 키·계좌번호는 맥의 프로젝트 폴더 `.env` 에만, 채팅·클라우드·커밋에 넣지 마세요.
- **휴장일**(설·추석·미국 공휴일 등)은 달력으로 거르지 않아요. 휴장일엔 place 를 끄거나, 돌렸다면 거절(`rejected`) 기록이 남고 다음 거래일에 다시 나가요.
- **늦게 깬 맥**: launchd 는 놓친 작업을 깨어난 뒤 바로 돌려요. 장 중간에 늦게 나간 지정가 주문은 아침 시가와 동떨어질 수 있으니 로그 시각을 확인하세요.
- **"결과 불명" 을 다시 내고 싶을 때**: 증권사 앱에서 정말 안 들어간 걸 확인한 뒤에만, `state/broker/<시장>-orders.jsonl` 을 백업하고 그 `client_id` 줄을 지우세요. 그 외에는 이 파일을 손대지 마세요.
- 국내 지정가 주문은 당일만 유효해요. 안 닿은 주문은 장 마감에 사라지고, 장부는 그날 시가로 체결되므로 보고서에 "미체결"로 남아요. 정상이에요.
- 세 트레이너가 **모의계좌 하나**를 같이 써요. 증권사 매수가능수량은 계좌 전체 기준이에요.
- `reports/` 는 아직 `.gitignore` 에 없어요. 커밋하지 마세요(주문번호가 들어 있음). `.gitignore` 에 `reports/` 를 넣는 건 K2 담당 파일이라 따로 요청합니다.
- 순서: team.py(신호) → place(주문) → reconcile(맞춰 보기). place 는 마지막 team.py 가 남긴 `pending` 을 그대로 내요. team.py 가 하루 빠져도 이미 낸 주문은 건너뛰니 두 번 나가지 않아요.
