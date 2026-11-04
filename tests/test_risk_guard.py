"""
risk_guard.py(서킷 브레이커) 점검 - 원래 risk_guard.py의 __main__ 자체 점검을 pytest로 옮김.
발동해야 할 때 발동하고(설명 문장 반환), 아닐 때 안 하는지(None) 본다.
"""

import pytest

from risk_guard import CircuitBreaker


@pytest.fixture
def cb():
    return CircuitBreaker(cum_limit=0.10, day_limit=0.07)


def test_누적손실_한도초과면_발동(cb):
    assert cb.check(100, 95, 89) is not None          # 누적 -11% → 발동


def test_하루급락_한도초과면_발동(cb):
    assert cb.check(100, 100, 92) is not None         # 하루 -8% → 발동


def test_한도_안쪽이면_통과(cb):
    assert cb.check(100, 100, 95) is None             # 누적 -5%, 하루 -5% → 통과


def test_어제값_없어도_누적으로_발동(cb):
    assert cb.check(100, 0, 89) is not None           # prev_value=0(첫날) → 누적만으로 판단


def test_이익구간이면_통과(cb):
    assert cb.check(100, 108, 105) is None            # 하루 -2.8%, 누적 +5% → 통과


def test_발동_문장에_이유가_들어감(cb):
    assert "누적" in cb.check(100, 95, 89)
    assert "하루" in cb.check(100, 100, 92)
