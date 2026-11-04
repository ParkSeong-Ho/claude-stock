"""
team.py 매수 후보 확신도 필터(keep_candidate) 점검 - 원래 `python team.py check`의 assert를 pytest로 옮김.
네트워크 없이 필터 함수만 본다. (team.py를 import하면 main·screener도 import되지만,
그 모듈들은 import 시점에 시세를 받지 않으므로 네트워크가 필요 없다.)
"""

import pytest

import team


@pytest.mark.parametrize("cand, keep", [
    ({"code": "A"}, True),                        # 팀장 부재(키 없음) → 통과(안전원칙)
    ({"code": "A", "conviction": None}, True),    # 팀장 무의견 → 통과(안전원칙)
    ({"code": "A", "conviction": 0.8}, True),     # 확신 높음 → 통과
    ({"code": "A", "conviction": 0.5}, True),     # 경계값(=CONV_MIN) → 통과
    ({"code": "A", "conviction": 0.3}, False),    # 확신 낮음 → 보류
])
def test_keep_candidate(cand, keep):
    assert team.keep_candidate(cand) is keep


def test_경계값은_CONV_MIN과_같다():
    # 위 경계값 케이스(0.5)가 의미 있으려면 CONV_MIN이 0.5여야 한다
    assert team.CONV_MIN == 0.5
