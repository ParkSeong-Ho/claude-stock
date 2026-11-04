"""
analyst.py - 로직이 팀장(Claude)에게 연락하는 다리. (운영모델 2단계)
------------------------------------------------------------------
프로그램이 후보를 들고 `claude -p`(헤드리스)로 나를 호출 → 내가 시장·뉴스·위험을 보고
분석/코칭을 JSON으로 회신 → 프로그램이 파싱해 규칙 판단에 반영.

구독 로그인 상태면 API 종량과금이 아니라 '구독 사용량'을 쓴다(ANTHROPIC_API_KEY 안 걸 때).
그래서 여기서는 env의 ANTHROPIC_API_KEY를 제거해 **구독 사용을 강제**한다.

🔒 안전 원칙(중요): 내가 없어도(미설치·타임아웃·한도초과·JSON깨짐) 프로그램은 멈추지 않는다.
   그 경우 analyze()는 None을 돌려주고, apply()는 후보를 규칙 그대로 통과시킨다(팀장 부재 → 규칙만).
   즉 내 응답은 '있으면 반영하는 오버레이'일 뿐, 매수/매도 방아쇠는 규칙이 당긴다.

H1 포워드 모의매매용 추가 (docs/h1-forward-design.md §3.4, 2026-11-04):
- normalize_verdict(): 팀장 판정 글자 정리(" VETO" → "veto", "Hold" → "hold"). H1 판정 기록에서만 쓴다.
  운영 apply()·team.py 는 지금 그대로(공백·대문자가 섞인 글자는 veto·hold 로 보지 않음).
- analyze_logged(): analyze() 와 같은 프롬프트·같은 호출·같은 파싱으로 같은 결과를 내고,
  "어떻게 됐는지"(상태·물은 시각·걸린 시간·종료 코드·모델·CLI 버전)를 함께 돌려준다 → 나중 채점·폴백 비율용.
  analyze() 와 결과가 다른 곳은 둘뿐이다(2a 검토 A-6): 답의 "analysis" 가 목록이 아니면 analyze() 는 TypeError 로
  멈추지만 analyze_logged 는 bad_json 폴백, 출력 글자를 읽지 못하면(UnicodeDecodeError 등) decode_error 폴백.
- claude_cli_version(): `claude --version` 첫 줄(실패하면 None). H1 은 실행마다 한 번 불러 analyze_logged 에 넘긴다.
  _build_prompt()·analyze()·apply() 는 한 글자도 바꾸지 않았다(프롬프트는 운영과 같음, 설계 Q4).
"""

from __future__ import annotations

import os
import re
import json
import time
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"
TIMEOUT = 150   # 초. 넘으면 포기하고 규칙 폴백


def _persona(trainer: str) -> str:
    f = PROMPTS_DIR / f"{trainer}.md"
    try:
        return f.read_text(encoding="utf-8") if f.exists() else ""
    except OSError:
        return ""


def _build_prompt(trainer: str, candidates: list[dict]) -> str:
    persona = _persona(trainer)
    lines = [f"- {c['code']}: 신호사유={c.get('reason','')} RSI={c.get('rsi','?')} 종가={c.get('price','?')}"
             for c in candidates]
    return f"""{persona}

너는 '{trainer}' 트레이너의 팀장(애널리스트)이다. 아래는 규칙이 '매수' 신호를 낸 후보다.
각 종목의 최근 시장 상황·악재·위험을 성실히 고려해 평가하라. 확신 없으면 hold, 위험하면 veto.

후보:
{chr(10).join(lines) if lines else "(없음)"}

반드시 아래 JSON 객체 '하나만' 출력하라(다른 설명 금지):
{{"analysis": [{{"code": "<종목>", "verdict": "buy|hold|veto", "conviction": 0.0~1.0, "note": "<한 줄 근거>"}}]}}
"""


def _extract_json(text: str):
    """모델 출력에서 첫 JSON 객체를 뽑아 파싱. 실패하면 None."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def analyze(trainer: str, candidates: list[dict], timeout: int = TIMEOUT):
    """claude -p로 후보 분석을 요청. 성공 시 {code: {verdict,conviction,note}}, 실패 시 None(규칙 폴백)."""
    if not candidates or shutil.which("claude") is None:
        return None
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # 구독 강제
    try:
        r = subprocess.run(
            ["claude", "-p", _build_prompt(trainer, candidates)],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    data = _extract_json(r.stdout)
    if not isinstance(data, dict) or "analysis" not in data:
        return None
    return {it["code"]: it for it in data["analysis"] if isinstance(it, dict) and "code" in it}


def apply(candidates: list[dict], analysis):
    """분석 결과를 후보에 반영. analysis=None이면 규칙 그대로(팀장 부재 폴백), veto면 제외."""
    if analysis is None:
        return candidates
    kept = []
    for c in candidates:
        a = analysis.get(c["code"])
        if a and a.get("verdict") == "veto":
            continue
        if a:
            c = {**c, "conviction": a.get("conviction"), "note": a.get("note")}
        kept.append(c)
    return kept


# ---------------- H1 용 추가 (위 함수들은 그대로) ----------------

VERDICTS = ("buy", "hold", "veto")
VERSION_TIMEOUT = 20   # 초. `claude --version` 이 이보다 오래 걸리면 버전은 "모름"(None)


def normalize_verdict(v):
    """팀장 판정 글자를 정리한다. 앞뒤 공백을 지우고 소문자로 바꿔 "buy"/"hold"/"veto" 이면 그 값, 아니면 None.
    예) " VETO" → "veto", "Hold" → "hold", "BUY\n" → "buy", "maybe"·""·None·숫자 → None."""
    if not isinstance(v, str):
        return None
    w = v.strip().lower()
    return w if w in VERDICTS else None


def claude_cli_version():
    """`claude --version` 의 첫 줄(예 "2.1.7 (Claude Code)"). claude 가 없거나 어떤 이유로든 실패하면 None.
    H1 은 실행마다 한 번만 불러 analyze_logged(cli_version=…) 에 넘긴다(판정 호출마다 부르지 않음)."""
    if shutil.which("claude") is None:
        return None
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # 판정 호출과 같은 환경
    try:
        r = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                           timeout=VERSION_TIMEOUT, env=env)
        if r.returncode != 0:
            return None
        lines = (r.stdout or "").strip().splitlines()
        return lines[0].strip() if lines and lines[0].strip() else None
    except Exception:      # 시간 초과·OSError·글자 깨짐 등 무엇이든 "모름"
        return None


def _local_now():
    return datetime.now().astimezone()


def analyze_logged(trainer: str, candidates: list[dict], timeout: int = TIMEOUT, now=None, cli_version=None):
    """analyze() 와 같은 일을 하고 (결과, meta) 를 돌려준다. 결과는 analyze() 와 같은 값이다
    (같은 _build_prompt, 같은 `claude -p` 호출, 같은 환경(ANTHROPIC_API_KEY 제거), 같은 _extract_json 파싱).
    다른 곳은 둘뿐: "analysis" 가 목록이 아님 → bad_json 폴백(analyze 는 TypeError), 출력 디코드 실패 → decode_error 폴백.

    now: 시간대가 있는 datetime 을 돌려주는 함수(시험·재현에서 시계를 바꿔 끼울 때). 없으면 이 컴퓨터의 지금 시각.
    cli_version: 이번 실행의 `claude --version` 값(claude_cli_version() 으로 한 번 구해 넘김). 받은 그대로 meta 에 적고,
                 이 함수는 `claude --version` 을 부르지 않는다.

    meta (설계 §3.4):
      status      "ok" | "no_claude" | "timeout" | "os_error" | "nonzero_exit" | "decode_error" | "bad_json" | "empty"
                  (bad_json = JSON 이 없거나 깨짐, "analysis" 키가 없음, "analysis" 가 목록이 아님 /
                   decode_error = claude 출력 글자를 읽지 못함 / empty = 후보가 없어 묻지 않음)
      asked_at    `claude -p` 를 부르기 직전 시각(시간대가 붙은 ISO, 예 "2026-11-10T07:11:22+09:00").
                  묻지 않았으면(empty·no_claude) 이 함수를 부른 시각
      elapsed_s   `claude -p` 한 번이 걸린 초(묻지 않았으면 0.0)
      returncode  `claude -p` 종료 코드(끝까지 돌지 못했으면 None)
      model       환경변수 ANTHROPIC_MODEL (없거나 빈 값이면 None = "모름". launchd 에서는 보통 None)
      cli_version 넘겨받은 값 그대로
    후보가 빈 목록이면 claude 를 부르지 않는다."""
    clock = _local_now if now is None else now

    def stamp():
        t = clock()
        if t.tzinfo is None:
            raise ValueError("now() 는 시간대가 있는 시각을 돌려줘야 해요")
        return t.isoformat(timespec="seconds")

    meta = {"status": None, "asked_at": stamp(), "elapsed_s": 0.0, "returncode": None,
            "model": os.environ.get("ANTHROPIC_MODEL") or None, "cli_version": cli_version}
    if not candidates:
        meta["status"] = "empty"
        return None, meta
    if shutil.which("claude") is None:
        meta["status"] = "no_claude"
        return None, meta
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # 구독 강제 (analyze 와 같음)
    prompt = _build_prompt(trainer, candidates)
    meta["asked_at"] = stamp()                    # 묻기 직전
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        meta["status"] = "timeout"
    except OSError:
        meta["status"] = "os_error"
    except ValueError:     # UnicodeDecodeError 등: claude 출력 글자를 읽지 못함 → 멈추지 않고 폴백
        meta["status"] = "decode_error"
    meta["elapsed_s"] = round(time.monotonic() - t0, 3)
    if meta["status"] is not None:
        return None, meta
    meta["returncode"] = r.returncode
    if r.returncode != 0:
        meta["status"] = "nonzero_exit"
        return None, meta
    data = _extract_json(r.stdout)
    if not isinstance(data, dict) or "analysis" not in data:
        meta["status"] = "bad_json"
        return None, meta
    try:
        result = {it["code"]: it for it in data["analysis"] if isinstance(it, dict) and "code" in it}
    except TypeError:      # "analysis" 가 목록이 아님(숫자 등)·code 가 dict 열쇠가 될 수 없음 → 폴백
        meta["status"] = "bad_json"
        return None, meta
    meta["status"] = "ok"
    return result, meta

if __name__ == "__main__":
    # 자체 점검: JSON 파싱 + 폴백/veto (실제 claude 호출은 하지 않음)
    d = _extract_json('앞말 {"analysis":[{"code":"AAPL","verdict":"veto","note":"악재"}]} 뒷말')
    assert d and d["analysis"][0]["code"] == "AAPL"
    assert _extract_json("설명만 있고 json 없음") is None
    cands = [{"code": "AAPL"}, {"code": "MSFT"}]
    assert apply(cands, None) == cands                       # 팀장 부재 → 규칙 그대로
    kept = apply(cands, {"AAPL": {"verdict": "veto"},
                         "MSFT": {"verdict": "buy", "conviction": 0.8, "note": "좋음"}})
    assert [c["code"] for c in kept] == ["MSFT"]             # veto 제외
    assert kept[0]["conviction"] == 0.8                       # 주석·확신도 반영
    print("[PASS] analyst JSON파싱·veto·폴백 점검 통과")
