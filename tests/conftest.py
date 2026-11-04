"""
conftest.py - pytest 공통 설정 (최소한만)
------------------------------------------------------------------
tests/ 안의 테스트가 저장소 루트의 모듈(analyst, risk_guard, team ...)을
`import analyst` 처럼 바로 불러올 수 있게, 루트 폴더를 파이썬 경로에 넣는다.

여러 세션이 tests/ 에 각자 파일을 더하므로, 여기에는 공용 fixture를 두지 않는다.
필요한 준비물은 각 테스트 파일 안에서 만든다(충돌 방지).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
