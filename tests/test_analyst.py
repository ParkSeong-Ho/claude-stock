"""
analyst.py 점검 - 원래 analyst.py의 __main__ 자체 점검(JSON 파싱·veto·폴백)을 pytest로 옮기고,
analyze()의 '팀장 부재 → None(규칙 폴백)' 안전원칙도 확인한다.

⚠️ 실제 claude CLI는 절대 부르지 않는다. shutil.which와 subprocess.run을 가짜로 바꿔(monkeypatch)
   "claude가 이렇게 답했다"고 흉내만 낸다. 그래서 네트워크·로그인 없이 돈다.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

import analyst


# ── 원래 __main__ 점검 ────────────────────────────────────────────

def test_extract_json_앞뒤_말이_있어도_뽑음():
    d = analyst._extract_json('앞말 {"analysis":[{"code":"AAPL","verdict":"veto","note":"악재"}]} 뒷말')
    assert d and d["analysis"][0]["code"] == "AAPL"


def test_extract_json_없으면_None():
    assert analyst._extract_json("설명만 있고 json 없음") is None


def test_extract_json_깨진_json이면_None():
    assert analyst._extract_json('{"analysis": [}') is None


def test_apply_팀장부재면_규칙_그대로():
    cands = [{"code": "AAPL"}, {"code": "MSFT"}]
    assert analyst.apply(cands, None) == cands


def test_apply_veto_제외하고_확신도_주석_반영():
    cands = [{"code": "AAPL"}, {"code": "MSFT"}]
    kept = analyst.apply(cands, {"AAPL": {"verdict": "veto"},
                                 "MSFT": {"verdict": "buy", "conviction": 0.8, "note": "좋음"}})
    assert [c["code"] for c in kept] == ["MSFT"]             # veto 제외
    assert kept[0]["conviction"] == 0.8                       # 확신도 반영
    assert kept[0]["note"] == "좋음"                          # 주석 반영


def test_apply_분석에_없는_종목은_그대로_통과():
    cands = [{"code": "NVDA", "price": 100.0}]
    assert analyst.apply(cands, {"AAPL": {"verdict": "veto"}}) == cands


# ── analyze(): claude 호출 부분 (가짜 subprocess) ─────────────────

CANDS = [{"code": "AAPL", "reason": "RSI 반등", "rsi": 28, "price": 190.0}]


@pytest.fixture
def fake_claude(monkeypatch):
    """claude가 '설치돼 있다'고 속이고, subprocess.run 호출을 기록·대체한다.
    반환값 state["result"]에 가짜 응답(또는 예외)을 넣어 쓴다."""
    state = {"calls": [], "result": None}

    def fake_run(cmd, **kwargs):
        state["calls"].append((cmd, kwargs))
        if isinstance(state["result"], BaseException):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(analyst.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(analyst.subprocess, "run", fake_run)
    return state


def _reply(stdout, returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def test_analyze_정상응답을_종목별_dict로(fake_claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = {"analysis": [{"code": "AAPL", "verdict": "buy", "conviction": 0.7, "note": "괜찮음"}]}
    fake_claude["result"] = _reply("분석 결과입니다:\n" + json.dumps(body, ensure_ascii=False))

    out = analyst.analyze("스프린터", CANDS)

    assert out == {"AAPL": body["analysis"][0]}
    cmd, kwargs = fake_claude["calls"][0]
    assert cmd[:2] == ["claude", "-p"]
    assert "AAPL" in cmd[2]                                    # 후보가 프롬프트에 들어감
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]            # 구독 사용 강제(API 키 제거)
    assert kwargs["timeout"] == analyst.TIMEOUT


def test_analyze_후보없으면_호출안함(fake_claude):
    assert analyst.analyze("스프린터", []) is None
    assert fake_claude["calls"] == []


def test_analyze_claude_미설치면_None(monkeypatch):
    monkeypatch.setattr(analyst.shutil, "which", lambda name: None)

    def must_not_run(*a, **k):
        raise AssertionError("claude 미설치인데 subprocess.run이 불렸다")

    monkeypatch.setattr(analyst.subprocess, "run", must_not_run)
    assert analyst.analyze("스프린터", CANDS) is None


@pytest.mark.parametrize("result", [
    subprocess.TimeoutExpired(cmd="claude", timeout=1),       # 시간 초과
    OSError("실행 실패"),                                      # 실행 자체 실패
    _reply("", returncode=1),                                  # 한도 초과 등 비정상 종료
    _reply("json이 없는 대답"),                                 # JSON 없음
    _reply('{"analysis": [}'),                                 # JSON 깨짐
    _reply('{"result": "다른 모양"}'),                          # analysis 키 없음
])
def test_analyze_실패하면_None으로_규칙폴백(fake_claude, result):
    fake_claude["result"] = result
    assert analyst.analyze("스프린터", CANDS) is None


def test_analyze_code없는_항목은_버림(fake_claude):
    fake_claude["result"] = _reply(json.dumps(
        {"analysis": [{"verdict": "veto"}, "문자열", {"code": "AAPL", "verdict": "hold"}]}))
    assert analyst.analyze("스프린터", CANDS) == {"AAPL": {"code": "AAPL", "verdict": "hold"}}
