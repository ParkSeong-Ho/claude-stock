# 검토 6d — 커밋 b0e003d..4107136 (검토 6b·6c 반영분)

- **날짜**: 2026-11-06
- **대상**: 브랜치 `h1-forward`, `git diff b0e003d 4107136 -- . ':!docs/h1-review-6b.md' ':!docs/h1-review-6c.md'` (커밋 0267d10·4107136). 고치려 한 지적: `docs/h1-review-6b.md` B-1~B-9(코드), `docs/h1-review-6c.md` C-1~C-28(운영 안내서·README).
- **검토자**: 독립 검토자, 작성자 설명 없음.
- **지킨 것**: 이 파일 말고 저장소를 고치지 않음. 커밋·푸시 안 함. 진짜 `claude` 안 부름(PATH 맨 앞 fakebin). 인터넷 안 씀. 저장소 안 `state/` 안 만듦. 복사본·탐침은 scratchpad `review6d/`.
- **상태**: 작성 중(찾는 대로 적음).

## 작업 메모 (진행하며 적음)

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
