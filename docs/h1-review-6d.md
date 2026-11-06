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
