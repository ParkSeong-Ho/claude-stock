"""
h1_replay.py - H1 재현(단계 5, 설계 docs/h1-forward-design.md §5)
------------------------------------------------------------------
무엇을 하나 (주식 초보용 설명)
- H1 장부 프로그램(h1.py)이 연구 때 쓴 시뮬레이터(R2 sim_team.py)와 **같은 매매·같은 숫자**를 내는지 지난 시세로 맞춰 본다.
  "같은 규칙이면 같은 결과"가 확인된 코드·환경만 실제 운영(포워드 모의매매)에 쓸 수 있다(사전 등록 ②-3, 관문).
- 두 쪽을 따로 돌려 하나하나 비교한다.
    기준값(정답 쪽)  연구 브랜치 origin/research-r2-2026-11-04 를 임시 폴더에 풀어, 그 안에서만 R2 sim_team.py 를 돌린다.
                     운영 시작 규칙(S 는 입금만, S+1 시가에 먼저 전부 지수)을 넣은 하위 클래스 OperatingStartSim(설계 §5.1)을 쓴다.
                     연구 브랜치 파일은 읽기만 하고 고치지 않는다.
    새 코드 쪽       임시 장부 폴더에서 h1.start → 날마다 h1.run 을 실제 운영과 같은 시각으로 부른다(매일 저장·엄격 읽기·HEAD·
                     백업·달력·자료 점검을 그대로 거침). 같은 날 두 번 불러 두 번째는 아무 파일도 바꾸지 않아야 한다(멱등).
                     시세는 연구 브랜치 data/ 를 그날까지만 잘라, 운영 받기 층(h1_data.fetch·load_idle)을 그대로 거쳐 넣는다
                     (인터넷 대신 가짜 FinanceDataReader). 팀장(claude)은 부르지 않는다(leader_mode="replay").
- 창(비교하는 기간, §5.2)
    W1-us  미국 2026-06-01 ~ 2026-11-03 (R0 20종목 + SPY)       W1-kr  국내 같은 기간 (KR_UNIVERSE 32종목 + KS200)
    W2-kr  국내 2018-03-01 ~ 2018-12-31 (거래정지를 가로지른 보유 포함)
    W3     합성 시세 + 가짜 브레인(정해진 날·정해진 보유일수에만 사고팖)으로 드문 길 7장면(s1~s7)을 일부러 지나게 한 차등 재현
- 비교 항목 M1~M9(§5.4) + M10 보유 상태(날마다 트레이너마다 종목별 주식 수·매수가·보유일수·매수일, 검토 5 P-2)와
  받아들이는 차이 K1~K13(§5.5). 그 밖의 차이가 하나라도 있으면 "통과 아님".
- 기준값 연구 브랜치는 커밋을 고정한다(R2_COMMIT). 이름(origin/research-r2-2026-11-04)이 다른 커밋을 가리키면 멈춘다(4).
- 통과하면: 보고서(state/h1/reports/replay-<날짜>.md, 기록할 줄의 내용까지)와 기준값 결과(replay-<날짜>-baseline.json)를 먼저
  쓰고 → state/h1/replay_pass.json 에 한 줄(h1.replay_entry → h1.record_replay_pass, 전역 잠금 아래) → 보고서의 "기록함" 줄을
  채운다. 금리 첫 저장본(R2 data/rates/*.csv)은 state/h1/rates/ 에 (없을 때만) 둔다.

사용
  python h1_replay.py                         # 전부(W1·W2·W3), 기록 = 이 폴더의 state/h1
  python h1_replay.py --root /tmp/x/h1        # 다른 장부 폴더에 기록(시험·확인용)
  python h1_replay.py --windows W3            # 일부만(통과 기록은 남기지 않음 — W1·W2·W3 를 다 돌려야 기록, 종료 코드 3)
  python h1_replay.py --r2-ref REF --keep-temp
  종료 코드
    0   통과 + 기록함(관문이 이 코드·환경으로 열림)
    3   고른 창은 모두 같지만 기록하지 않음(일부 창만 돌림) — 관문은 열리지 않는다
    2   차이(통과 아님, 기록 없음) — 임시 폴더를 자동으로 남기고 경로를 알림
    4   환경 문제(git·R2 커밋 다름·파일·잠금·하네스·재현 도중 코드 바뀜·파이썬 3.12 미만) — 기록 없음, 임시 폴더 남김
    9   명령 인자 오류          130  사람이 멈춤(Ctrl-C, h1.run 안에서 눌러도 바로 멈춤)
  걸리는 시간: 이 개발 컨테이너에서 전부 약 8분(W1 미·국 각 2분여, W2 3분, W3 10초 안팎). 인터넷이 필요 없다.

주의
- 이 파일도 CODE_FILES 에 있다. 이 파일을 더하거나 고치면 코드 지문(code_hash)이 바뀌므로 그 코드로 재현을 다시 통과해야 한다.
- 재현 도중 코드·환경이 바뀌면(파일을 고침) 통과 기록을 남기지 않는다(종료 코드 4).
- 인터넷·진짜 claude 를 쓰지 않는다. git archive(로컬 저장소)만 쓴다 — 연구 브랜치가 없으면
  `git fetch origin research-r2-2026-11-04` 를 먼저 하라고 알리고 종료 코드 4.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
import types
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import analyst
import h1
import h1_check
import h1_data
import h1_report
import main
import markets
import screener
import team
from paper_wallet import shares_within_cap

REPO = Path(__file__).resolve().parent
R2_REF = "origin/research-r2-2026-11-04"
R2_DIR = "reports/research-r2-2026-11-04"
R2_COMMIT = "22b7934c4b183d38bf411d132ddec5e5d7742195"   # 기준값 연구 브랜치 커밋 고정(검토 5 P-5) — 다르면 4
EXIT_OK, EXIT_DIFF, EXIT_PARTIAL, EXIT_ENV, EXIT_USAGE, EXIT_INTERRUPT = 0, 2, 3, 4, 9, 130
EXIT_TEXT = {0: "통과 + 기록함", 2: "차이(통과 아님, 기록 없음)", 3: "고른 창은 같지만 기록하지 않음(일부 창만 돌림)",
             4: "환경 문제(기록 없음)", 9: "명령 인자 오류", 130: "사람이 멈춤(Ctrl-C)"}
KST = ZoneInfo("Asia/Seoul")
TOL_REL = 1e-9            # 상대 차 허용(M1 지수 수량·M4 매일 값·M6·M7, K12)
TOL_CASH = 1e-6           # 현금 절대 차 허용(M1 현금 변화·M4 현금, probe4)
W_ALLOWED = ("W2", "W3")          # M8: 모든 창에서 나도 되는 경고(W2 거래정지·W3 팀장 끔 폴백)
W4_ALLOWED_W2 = ("316140", "329180", "402340", "373220")   # M8: W4(종목군 시세 못 받음)는 W2 창에서 아직 상장 전인 이 넷만(설계 M8)

# W3 합성 세계: 국내, 2019-06-03 세율 경계(0.30% → 0.25%)를 지나는 45봉 창(S = 2019-04-22 월요일)
W3_HIST_START = "2018-09-03"
W3_START, W3_END = "2019-04-22", "2019-06-21"
W3_UNIVERSE = ("005930", "000660", "005380", "035420", "105560", "068270", "207940", "051910", "035720", "006400",
               "003550")      # 003550 = s7 '0주' 장면용 아주 비싼 합성 종목(파이오니어 상한 150만 원 안에서 1주도 못 삼)

WINDOWS = {
    "W1-us": {"group": "W1", "market": "us", "start": "2026-06-01", "end": "2026-11-03", "kind": "real"},
    "W1-kr": {"group": "W1", "market": "kr", "start": "2026-06-01", "end": "2026-11-03", "kind": "real"},
    "W2-kr": {"group": "W2", "market": "kr", "start": "2018-03-01", "end": "2018-12-31", "kind": "real",
              "w4_ok": W4_ALLOWED_W2},
    "W3-kr": {"group": "W3", "market": "kr", "start": W3_START, "end": W3_END, "kind": "synthetic"},
}
GROUPS = ("W1", "W2", "W3")
FINGERPRINT_WINDOWS = ("W1-us", "W1-kr", "W2-kr")      # 통과 기록 ledger_fingerprints 의 열쇠(설계 §5.6)
REQUIRED = {"W1": ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "K"),
            "W2": ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "K"),
            "W3": ("M1", "M2", "M3", "M4", "M5", "M8", "M9", "M10", "K", "S")}
CHECK_ORDER = ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "K", "S")
M_NAMES = {"M1": "체결", "M2": "보류", "M3": "주문", "M4": "매일 값", "M5": "그림자 서킷(M5′)", "M6": "지수 B&H",
           "M7": "이자 계산", "M8": "장부 점검", "M9": "멱등·저장", "M10": "보유 상태(주식 수·매수가·보유일수·매수일)",
           "K": "받아들이는 차이의 전제(K3·K4·K5·K9)", "S": "W3 장면이 실제로 그 길을 지남"}


class ReplayEnvError(Exception):
    """환경 문제(git·파일·잠금·하네스) → 종료 코드 4. 재현 결과가 아니므로 통과도 실패도 아니다."""


def _say(*args):
    try:
        print(*args, flush=True)
    except (OSError, ValueError):
        pass


# ============================ 1. 기준값: R2 를 임시 폴더에 풀고 하네스로 돌리기 (§5.1) ============================

def extract_r2(ref, dst, repo=None) -> Path:
    """git archive <ref> 를 dst(새 빈 폴더)에 푼다(tarfile 의 filter='data' 가 이상한 경로를 막음). R2 보고서 폴더를 돌려준다.
    연구 브랜치는 읽기만 한다. ref 가 없으면 ReplayEnvError(→ 4, `git fetch origin research-r2-2026-11-04` 안내)."""
    repo = Path(repo or REPO)
    try:
        p = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref], capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        raise ReplayEnvError(f"git 을 실행하지 못했어요({type(e).__name__}: {e})")
    if p.returncode != 0 or not p.stdout:
        msg = (p.stderr or b"").decode("utf-8", "replace").strip()[:300]
        raise ReplayEnvError(f"연구 브랜치 {ref} 를 읽지 못했어요({msg}) → 먼저 `git fetch origin research-r2-2026-11-04`")
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(dst, filter="data")
    rep = dst / R2_DIR
    for need in ("sim_team.py", "data/us/universe.json", "data/kr/KS200.csv.gz", "data/us/SPY.csv.gz",
                 "data/rates/us_tbill.csv", "data/rates/kr_shortrate.csv"):
        if not (rep / need).exists():
            raise ReplayEnvError(f"연구 브랜치에 {R2_DIR}/{need} 가 없어요 → 브랜치 내용 확인")
    for need in ("main.py", "team.py", "markets.py", "paper_wallet.py"):
        if not (dst / need).exists():
            raise ReplayEnvError(f"연구 브랜치 맨 위에 {need} 가 없어요 → 브랜치 내용 확인")
    return rep


def r2_commit(ref, repo=None) -> str | None:
    """ref 가 가리키는 커밋(태그면 그 커밋). 없으면 None."""
    try:
        p = subprocess.run(["git", "-C", str(Path(repo or REPO)), "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


def check_r2_commit(ref, repo=None) -> str:
    """기준값 연구 브랜치가 고정 커밋(R2_COMMIT)인지(검토 5 P-5). 맥에서 git fetch 가 그 가지를 다른 커밋으로 옮겼으면
    (연구 가지에 실수 커밋·강제 푸시) 기준값과 입력 시세가 함께 바뀌어도 모르므로 멈춘다(ReplayEnvError → 4)."""
    got = r2_commit(ref, repo)
    if got is None:
        raise ReplayEnvError(f"연구 브랜치 {ref} 를 찾지 못했어요 → 먼저 `git fetch origin research-r2-2026-11-04`")
    if got != R2_COMMIT:
        raise ReplayEnvError(f"연구 브랜치 {ref} 가 커밋 {got[:12]} 를 가리켜요. 재현 기준값은 커밋 {R2_COMMIT[:12]} 로 고정돼 "
                             "있어요(연구 브랜치는 읽기만 하고 바뀌면 안 됨) → 가지가 왜 옮겨졌는지 사람이 확인. 정말 바꿔야 하면 "
                             "h1_replay.py 의 R2_COMMIT 을 고치는 코드 변경(재현을 다시 통과)으로만")
    return got


# 하네스: R2 임시 폴더 안에 써 넣고 `python -I -B` 로만 돈다(지금 저장소 모듈을 읽지 않게, §7 R22).
# 인자: <R2 맨 위 폴더> <작업 JSON> <결과 JSON>. 종료 코드 3 = 모듈이 임시 폴더 밖에서 읽힘(기준값이 아님).
HARNESS = r'''
"""h1_replay 하네스 (h1_replay.py 가 자동으로 써 넣음 — 고치지 마세요).
R2 연구 브랜치를 풀어 둔 임시 폴더 안에서 python -I 로만 돈다. 그 폴더의 sim_team·main·team·markets·paper_wallet 만 읽는다."""
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

R2ROOT = Path(sys.argv[1]).resolve()
SPEC = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[3])
REP = R2ROOT / "reports" / "research-r2-2026-11-04"
sys.path.insert(0, str(REP))
sys.path.insert(0, str(R2ROOT))
import sim_team, main, team, markets, paper_wallet   # noqa: E401,E402

bad = [f"{m.__name__}={Path(m.__file__).resolve()}" for m in (sim_team, main, team, markets, paper_wallet)
       if not Path(m.__file__).resolve().is_relative_to(R2ROOT)]
if bad:
    print("기준값 모듈이 R2 임시 폴더 밖에서 읽혔어요(지금 저장소 모듈을 읽으면 '자기와 비교'가 됨): " + "; ".join(bad),
          file=sys.stderr)
    sys.exit(3)


class OperatingStartSim(sim_team.TeamSim):
    """설계 §5.1-3 그대로: S 는 입금만(쓸어 담기 없음), S+1 시가에 주문 전에 현금 전부 지수, 그다음 평소 순서."""
    def _sweep_to_index(self, s, t):
        if t == self.i0:                 # S: 입금만, 쓸어 담기 없음
            return
        return super()._sweep_to_index(s, t)

    def _open(self, t):
        if t == self.i0 + 1:             # S+1: 주문 전에 현금 전부 지수
            for s in self.sleeves:
                if s.mode(self.md, t) == "index":
                    super()._sweep_to_index(s, t)
        super()._open(t)                 # 그다음 평소 순서: 매도 → 매수 → 쓸어 담기


def _record_units(cls):
    """관찰용 하위 클래스(동작은 바꾸지 않음): 매일 종가 뒤
    - 종가 행에 트레이너별 지수 단위(units_<이름>)를 더 적고(M4),
    - 트레이너별 보유 상태 {종목: [주식 수, 매수가, 보유일수, 매수일]} 를 pos_snap 에 적는다(M10, 검토 5 P-2).
      보유일수는 R2 가 매일 시가에 그 종목 봉이 있을 때만 1 늘리는 days_held 그대로다(_decide 가 j − entry_own 과 같은지 확인하는 값)."""
    class Rec(cls):
        def _close(self, t):
            super()._close(t)
            snap = {}
            for s in self.sleeves:
                self.rows[-1]["units_" + s.name] = s.units(self.md.idx_code)
                snap[s.name] = {c: [p["shares"], p["buy_price"], p["days_held"], p["buy_date"]]
                                for c, p in s.positions.items()}
            if not hasattr(self, "pos_snap"):
                self.pos_snap = []
            self.pos_snap.append({"date": self.md.dstr[t], "sleeves": snap})
    Rec.__name__ = cls.__name__ + "Rec"
    return Rec


OpRec, OrigRec = _record_units(OperatingStartSim), _record_units(sim_team.TeamSim)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return x


def _plain(v):
    if isinstance(v, (str, bool)) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v) if isinstance(v, float) else v
    if hasattr(v, "item"):
        return v.item()
    return str(v)


def _market_data(job):
    if job["kind"] == "real":
        return sim_team.get_market(job["market"])
    d = Path(job["data_dir"]).resolve()
    if not d.is_relative_to(R2ROOT):
        raise SystemExit("W3 자료 폴더가 R2 임시 폴더 밖이에요")
    bf = Path(job["brains_file"]).resolve()
    if not bf.is_relative_to(R2ROOT):
        raise SystemExit("W3 가짜 브레인 파일이 R2 임시 폴더 밖이에요")
    spec = importlib.util.spec_from_file_location("h1_replay_w3_brains", bf)
    fake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fake)
    idx = sim_team._read(d / "KS200.csv")
    frames, zv = {}, {}
    for c in job["universe"]:
        raw = sim_team._read(d / f"{c}.csv")
        zv[c] = {x.date().isoformat() for x in raw.index[raw["Volume"] == 0]}
        frames[c] = sim_team.drop_zero_volume(raw)
    rates = sim_team._rate_series(sim_team.DATA / "rates" / "kr_shortrate.csv")
    return sim_team.MarketData("kr", idx, frames, rates, "prev_month", brains=fake.BRAINS, zero_volume=zv)


def _run(md, job, arm, cb, cls, interest=False):
    cfg = sim_team.Config(market=md.key, period=(job["start"], job["end"]), arm=arm, cb=cb, interest=interest,
                          with_refs=False)
    i0, i1 = sim_team.period_range(md, cfg.period)
    sim = cls(md, cfg, i0, i1)
    r = sim.run()
    r["pos_snap"] = getattr(sim, "pos_snap", [])
    return i0, i1, r


def _daily(r):
    rows = []
    for d, row in r["daily"].iterrows():
        x = {k: _f(v) for k, v in row.items() if k.startswith(("v_", "stock_", "index_", "cash_", "units_"))
             and not k.endswith("_frac")}
        x["date"] = d
        x["value"], x["stock"], x["index"], x["cash"] = _f(row["value"]), _f(row["stock"]), _f(row["index"]), _f(row["cash"])
        rows.append(x)
    return rows


out = {"modules": {m.__name__: str(Path(m.__file__).resolve().relative_to(R2ROOT))
                   for m in (sim_team, main, team, markets, paper_wallet)},
       "kr_universe": list(markets.KR_UNIVERSE.values()), "kr_sell_tax": [list(x) for x in sim_team.KR_SELL_TAX],
       "min_bars": sim_team.MIN_BARS, "warmup": sim_team.WARMUP, "totals": sim_team.TOTALS, "jobs": {}}
for job in SPEC["jobs"]:
    md = _market_data(job)
    res = {"arms": {}}
    for arm in ("A0", "A1"):
        res["arms"][arm] = {}
        for cb in ("none", "current"):
            i0, i1, r = _run(md, job, arm, cb, OpRec)
            res["arms"][arm][cb] = {
                "fills": [{k: _plain(f[k]) for k in ("sleeve", "date", "code", "side", "kind", "qty", "price", "cash",
                                                     "tax")} for f in r["fills"]],
                "skips": [{k: _plain(x[k]) for k in ("sleeve", "date", "code", "kind", "reason")} for x in r["skips"]],
                "orders": [{k: _plain(o[k]) for k in ("sleeve", "code", "action", "signal_date", "reason")}
                           for o in r["orders"]],
                "events": [{k: _plain(v) for k, v in ev.items()} for ev in r["events"]],
                "daily": _daily(r) if cb == "none" else [],
                "positions": [{"date": x["date"], "sleeves": {n: {c: [_plain(v) for v in p] for c, p in ps.items()}
                                                              for n, ps in x["sleeves"].items()}}
                              for x in r["pos_snap"]] if cb == "none" else [],
                "over_slots": {n: int(v["over_slots"]) for n, v in r["sleeves"].items()},
                "units_end": {n: float(v["units_end"]) for n, v in r["sleeves"].items()},
            }
    res["i0"], res["i1"] = md.dstr[i0], md.dstr[i1]
    res["dates"] = md.dstr[i0:i1 + 1]
    res["n_before_i0"] = int(i0)
    total = sim_team.TOTALS[md.key]
    bh = sim_team.index_buy_hold_fractional(md, i0 + 1, i1, total)
    res["bh"] = {"units": float(bh["units"]), "equity": [float(x) for x in bh["equity"]],
                 "dates": md.dstr[i0 + 1:i1 + 1], "last_close": float(md.idx_close[i1])}
    res["rates"] = {"rule": md.rate_rule, "dates": md.dstr[i0:i1 + 1],
                    "values": [float(x) for x in md.rate_pct[i0:i1 + 1]]}
    # 참고(통과 조건 아님): A0 를 이자 켜고(R2 기본) 돌린 끝 평가액 — "A0+이자" 근사와의 차이(M7 참고, §3.8-9)
    _, _, ri = _run(md, job, "A0", "none", OpRec, interest=True)
    res["ref_a0_interest"] = {"last_value": float(ri["daily"]["value"].iloc[-1]),
                              "interest": float(sum(v["interest"] for v in ri["sleeves"].values()))}
    # 참고(§5.1-6): 원래 sim_team(S 시가 전부 지수)과 운영 시작 규칙 하위 클래스의 차이(A1, 서킷 끔)
    _, _, ro = _run(md, job, "A1", "none", OrigRec)
    key = lambda f: (f["sleeve"], f["date"], f["kind"], f["code"], f["side"])   # noqa: E731
    op = Counter(key(f) for f in res["arms"]["A1"]["none"]["fills"])
    og = Counter(key(f) for f in ro["fills"])
    res["ref_original"] = {"fill_keys_only_original": sum((og - op).values()),
                           "fill_keys_only_operating": sum((op - og).values()),
                           "last_value_original": float(ro["daily"]["value"].iloc[-1]),
                           "last_value_operating": float(res["arms"]["A1"]["none"]["daily"][-1]["value"])}
    out["jobs"][job["name"]] = res
OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
'''


def run_harness(r2_rep, jobs, work, python=None) -> dict:
    """하네스를 R2 임시 폴더 맨 위에 써 넣고 `python -I -B` 로 돌려 기준값 JSON 을 받는다.
    jobs = [{"name", "kind": "real"|"synthetic", "market", "start", "end", (W3: "data_dir", "brains_file", "universe")}].
    모듈이 임시 폴더 밖에서 읽히면(종료 코드 3) 또는 하네스가 실패하면 ReplayEnvError."""
    r2_root = Path(r2_rep).resolve().parents[1]
    hpath = r2_root / "h1_replay_harness.py"
    hpath.write_text(HARNESS, encoding="utf-8")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    spec, out = work / "harness_spec.json", work / "harness_out.json"
    spec.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")
    try:
        p = subprocess.run([python or sys.executable, "-I", "-B", str(hpath), str(r2_root), str(spec), str(out)],
                           cwd=str(r2_root), capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as e:
        raise ReplayEnvError(f"기준값 하네스를 돌리지 못했어요({type(e).__name__}: {e})")
    if p.returncode == 3:
        raise ReplayEnvError("기준값 하네스: " + (p.stderr or "").strip()[-600:])
    if p.returncode != 0 or not out.exists():
        raise ReplayEnvError(f"기준값 하네스가 실패했어요(종료 코드 {p.returncode}): {(p.stderr or '').strip()[-1500:]}")
    return json.loads(out.read_text(encoding="utf-8"))


# ============================ 2. 새 코드 쪽: 가짜 자료 받는 곳 + 날마다 h1.start/run (§5.3) ============================

def read_raw(path) -> pd.DataFrame:
    """원본 시세 CSV(연구 브랜치 data/ 또는 W3 합성) → DataFrame(날짜 색인, 오름차순). 아무것도 버리지 않는다
    (종가 NaN·거래량 0 행을 버리는 것은 운영 받기 층 main.confirmed_bars 의 몫)."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df.sort_index()


def cut_day(df, day) -> pd.DataFrame:
    """day('YYYY-MM-DD') 이하 행만(정렬된 색인, 이분 탐색)."""
    pos = df.index.searchsorted(pd.Timestamp(day) + pd.Timedelta(days=1), side="left")
    return df.iloc[:pos]


def run_at(market, t) -> datetime:
    """봉 t 를 처리하는 운영 시각(설계 §5.3·§8.2): 국내 t 23:05 KST, 미국 t 다음 평일 07:10 KST."""
    d = pd.Timestamp(t)
    if h1._mkey(market) == "kr":
        return datetime(d.year, d.month, d.day, 23, 5, tzinfo=KST)
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return datetime(nxt.year, nxt.month, nxt.day, 7, 10, tzinfo=KST)


class ReplaySource:
    """h1 의 DataSource 자리(benchmark·fetch·universe·now). 원본을 '지금 시각의 그 시장 날짜' 이하로 자른 뒤 운영 받기 층
    h1_data.load_idle·h1_data.fetch 를 **그대로** 부른다 — 그 안의 FinanceDataReader 만 가짜(fdr_installed 동안)로 바꾼다.
    그래서 거래량 칸 이름 정리 → main.confirmed_bars(종가 NaN·국내 거래량 0·확정 시각 전 오늘 봉 버림) → 국내 정지 날짜가
    운영과 같은 코드로 돈다. 지표용 시작은 R2 처럼 처음부터다(운영은 team.START, 받아들이는 차이 K10)."""

    def __init__(self, market, idle_raw, raws, universe):
        self.mk = h1._mkey(market)
        self.m = markets.MARKETS[self.mk]
        self.idle_raw = idle_raw
        self.raws = dict(raws)
        self.uni = list(universe)
        self.clock = None
        self._day = None
        self.calls = Counter()

    def now(self):
        return self.clock

    def universe(self):
        self.calls["universe"] += 1
        return list(self.uni)

    def _local_day(self, now):
        return h1._aware(now).astimezone(ZoneInfo(self.m.tz)).date().isoformat()

    def _reader(self, code, start):
        """가짜 FinanceDataReader.DataReader: 원본을 self._day 이하로 잘라 돌려줌. 모르는 종목이면 받기 실패 흉내."""
        df = self.idle_raw if code == self.m.benchmark else self.raws.get(code)
        if df is None:
            raise LookupError(f"재현 자료에 {code} 없음")
        return cut_day(df, self._day).copy()

    def benchmark(self, now):
        self.calls["benchmark"] += 1
        self._day = self._local_day(now)
        return h1_data.load_idle(self.mk, now)

    def fetch(self, code, now):
        self.calls["fetch"] += 1
        self._day = self._local_day(now)
        return h1_data.fetch(self.mk, code, now)

    def dates(self, start, end):
        return [d.date().isoformat() for d in self.idle_raw.index if start <= d.date().isoformat() <= end]

    @contextlib.contextmanager
    def fdr_installed(self):
        """이 동안만 import FinanceDataReader 가 이 가짜를 돌려주게(끝나면 원래대로). 인터넷을 쓰지 않는다."""
        had = "FinanceDataReader" in sys.modules
        saved = sys.modules.get("FinanceDataReader")
        sys.modules["FinanceDataReader"] = types.SimpleNamespace(DataReader=self._reader, __version__="replay")
        try:
            yield self
        finally:
            if had:
                sys.modules["FinanceDataReader"] = saved
            else:
                sys.modules.pop("FinanceDataReader", None)


@contextlib.contextmanager
def no_claude():
    """재현 중에는 진짜 claude 를 절대 부르지 않는다(replay 모드는 원래 안 부름 — 혹시 불리면 바로 실패하게 막아 둠)."""
    saved = (analyst.analyze_logged, analyst.analyze, analyst.claude_cli_version)

    def boom(*a, **k):
        raise RuntimeError("재현 중 claude 호출 금지")
    analyst.analyze_logged = analyst.analyze = analyst.claude_cli_version = boom
    try:
        yield
    finally:
        analyst.analyze_logged, analyst.analyze, analyst.claude_cli_version = saved


@contextlib.contextmanager
def brains_swapped(brains):
    """W3 만: team.BRAINS·screener.BRAINS 를 가짜로 바꾸고, screener.scan_frames 는 늘 brains=가짜 로 부르게(설계 §5.2 W3).
    끝나면 원래대로."""
    if brains is None:
        yield
        return
    saved = (team.BRAINS, screener.BRAINS, screener.scan_frames)
    real_scan = screener.scan_frames

    def scan(frames, order, asof=None, min_bars=70, brains=None, _fake=brains):
        return real_scan(frames, order, asof=asof, min_bars=min_bars, brains=_fake)
    team.BRAINS, screener.BRAINS, screener.scan_frames = brains, brains, scan
    try:
        yield
    finally:
        team.BRAINS, screener.BRAINS, screener.scan_frames = saved


def _sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def snapshot(root, market) -> dict:
    """멱등 대상 파일(설계 §2.5·M9): 시장 폴더의 장부 6개·meta·HEAD·backup 과 그 시장 판정 기록의 sha256.
    실행 일지(runs.jsonl·calendar.jsonl)·기업 행위 일지는 줄이 더해지는 것이 정상이라 뺀다."""
    mk = h1._mkey(market)
    mdir = Path(root) / mk
    out = {str(p.relative_to(mdir)): _sha_file(p) for p in sorted(mdir.rglob("*"))
           if p.is_file() and p.name not in ("calendar.jsonl", "corp_actions.jsonl")}
    dl = h1.decisions_path(root, mk)
    out["(판정 기록)"] = _sha_file(dl) if dl.exists() else None
    return out


def positions_now(root, market) -> dict:
    """지금(마지막 커밋) 장부 6개의 보유 상태 {arm: {트레이너: {종목: [주식 수, 매수가, 보유일수, 매수일]}}} — 저장된 파일에서
    그대로 읽는다(M10, 검토 5 P-2: 엔진이 실제로 들고 있는 상태. 하루 기록에서 다시 계산하지 않음)."""
    mk = h1._mkey(market)
    out = {}
    for arm in h1.ARMS:
        out[arm] = {}
        for tn in h1.TRAINERS:
            d = json.loads(h1.ledger_path(mk, arm, tn, root).read_text(encoding="utf-8"))
            out[arm][tn] = {c: [p["shares"], p["buy_price"], p["days_held"], p["buy_date"]]
                            for c, p in d["positions"].items()}
    return out


def run_problems(rr) -> list:
    """실행 결과(run_h1_window)에서 멈춘·실패한 실행 목록: 첫 실행이 0 이 아니거나 같은 날 두 번째 실행이 0 이 아님(검토 5 P-7)."""
    return [x for x in rr["exit_codes"] if x["code"] != 0 or x["code2"] not in (0, None)]


def run_h1_window(name, spec, src, root, log_path, *, brains=None, twice=True, progress=_say) -> dict:
    """창 하나를 새 코드로: 첫 봉 = h1.start, 그 뒤 날마다 h1.run(운영 시각). twice 이면 같은 날 한 번 더 h1.run 을 불러
    멱등(M9)을 본다. 날마다 첫 실행 뒤 보유 상태를 장부 파일에서 적는다(M10). h1 의 실행 요약은 log_path 파일로,
    진행 표시(25봉마다)는 화면으로 보낸다(검토 5 P-6).
    첫 실행이든 두 번째 실행이든 0 이 아니면 거기서 멈춘다. h1 이 130(사람이 Ctrl-C)을 돌려주면 재현 전체를 바로 멈춘다
    (KeyboardInterrupt 를 다시 냄, 검토 5 P-7)."""
    mk = spec["market"]
    cal = src.dates(spec["start"], spec["end"])
    if not cal:
        raise ReplayEnvError(f"{name}: 대기 자산 시세에 {spec['start']} ~ {spec['end']} 날짜가 없어요")
    codes, same, seconds, pos = [], [], [], {}
    t0 = time.time()
    screen = sys.stdout                                   # 진행 표시는 h1 로그가 아니라 화면으로
    with open(log_path, "w", encoding="utf-8") as logf, contextlib.redirect_stdout(logf), src.fdr_installed(), \
            no_claude(), brains_swapped(brains):
        for i, b in enumerate(cal):
            src.clock = run_at(mk, b)
            t1 = time.time()
            if i == 0:
                c1 = h1.start(mk, root=root, source=src, leader_mode="replay", gate=False)
            else:
                c1 = h1.run(mk, root=root, source=src, leader_mode="replay", gate=False)
            if c1 == h1.EXIT_INTERRUPT:
                raise KeyboardInterrupt
            c2 = None
            if c1 == h1.EXIT_OK:
                pos[b] = positions_now(root, mk)
                if twice:
                    before = snapshot(root, mk)
                    c2 = h1.run(mk, root=root, source=src, leader_mode="replay", gate=False)
                    if c2 == h1.EXIT_INTERRUPT:
                        raise KeyboardInterrupt
                    same.append({"bar": b, "same": before == snapshot(root, mk), "code": c2})
            codes.append({"bar": b, "cmd": "start" if i == 0 else "run", "code": c1, "code2": c2})
            seconds.append(time.time() - t1)
            if c1 != h1.EXIT_OK or c2 not in (h1.EXIT_OK, None):
                break
            if progress and (i + 1) % 25 == 0:
                with contextlib.redirect_stdout(screen):
                    progress(f"    {name}: {i + 1}/{len(cal)}봉 ({time.time() - t0:.0f}초)")
    return {"cal": cal, "exit_codes": codes, "twice": same, "positions": pos, "seconds": time.time() - t0,
            "max_run_s": max(seconds) if seconds else 0.0}


# ============================ 3. 비교 (§5.4 M1~M10, §5.5 K1~K13) ============================

def _chk(ok, detail, diffs=()):
    return {"ok": bool(ok), "detail": detail, "diffs": list(diffs)[:30], "n_diffs": len(list(diffs))}


def _rel(a, b):
    """상대 차. 한쪽이라도 NaN·inf 면 무한대(= 늘 차이, 검토 5 P-4)."""
    a, b = float(a), float(b)
    if not (math.isfinite(a) and math.isfinite(b)):
        return math.inf
    if a == b:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b))


def _abs(a, b):
    """절대 차(현금). 한쪽이라도 NaN·inf 면 무한대(= 늘 차이, 검토 5 P-4)."""
    a, b = float(a), float(b)
    if not (math.isfinite(a) and math.isfinite(b)):
        return math.inf
    return abs(a - b)


_SIDE = {"매수": "buy", "매도": "sell"}
_KIND = {"stock": "stock", "index": "idle"}


def compare_fills(states, arm, base_none, upto) -> dict:
    """M1: (트레이너, 날짜, 주식/지수, 종목, 매수/매도) 모음이 같고, 짝마다 주식 수량 같음·지수 수량 상대 차 ≤ 1e-9·
    체결가 정확히 같음·현금 변화 절대 차 ≤ 1e-6. 체결은 마지막 봉도 포함(K1 은 판단만 뺌)."""
    h, r = {}, {}
    for tn in h1.TRAINERS:
        for f in states[arm][tn]["fills"]:
            if f["date"] <= upto:
                h.setdefault((tn, f["date"], f["kind"], f["code"], f["side"]), []).append(f)
    for f in base_none["fills"]:
        if f["date"] <= upto:
            r.setdefault((f["sleeve"], f["date"], _KIND[f["kind"]], f["code"], _SIDE[f["side"]]), []).append(f)
    diffs = []
    worst = {"qty_rel": 0.0, "cash_abs": 0.0}
    for k in sorted(set(h) | set(r)):
        a, b = h.get(k, []), r.get(k, [])
        if len(a) != len(b):
            diffs.append(f"{k}: H1 {len(a)}건 ≠ R2 {len(b)}건")
            continue
        for x, y in zip(a, b):
            if k[2] == "stock":
                if x["qty"] != y["qty"]:
                    diffs.append(f"{k}: 주식 수량 {x['qty']!r} ≠ {y['qty']!r}")
            else:
                q = _rel(x["qty"], y["qty"])
                worst["qty_rel"] = max(worst["qty_rel"], q)
                if q > TOL_REL:
                    diffs.append(f"{k}: 지수 수량 상대 차 {q:.2e} > {TOL_REL}")
            if x["price"] != y["price"]:
                diffs.append(f"{k}: 체결가 {x['price']!r} ≠ {y['price']!r}")
            c = _abs(x["cash_delta"], y["cash"])
            worst["cash_abs"] = max(worst["cash_abs"], c)
            if c > TOL_CASH:
                diffs.append(f"{k}: 현금 변화 차 {c:.2e} > {TOL_CASH}")
    n_h = sum(len(v) for v in h.values())
    n_r = sum(len(v) for v in r.values())
    return {**_chk(not diffs, f"H1 {n_h}건 / R2 {n_r}건, 지수 수량 최대 상대 차 {worst['qty_rel']:.1e}, "
                             f"현금 변화 최대 차 {worst['cash_abs']:.1e}", diffs), "n_h1": n_h, "n_r2": n_r, **worst}


def compare_skips(states, arm, base_none, upto) -> dict:
    """M2: (트레이너, 날짜, 종목, 종류 0주/현금부족) 모음. 재현은 팀장 끔이라 H1 에 팀장hold·확신도낮음 보류가 있으면 차이."""
    h = Counter((tn, s["date"], s["code"], s["kind"]) for tn in h1.TRAINERS for s in states[arm][tn]["skips"]
                if s["date"] <= upto)
    r = Counter((s["sleeve"], s["date"], s["code"], s["kind"]) for s in base_none["skips"] if s["date"] <= upto)
    diffs = [f"H1 에만 {k}" for k in sorted((h - r).elements())] + [f"R2 에만 {k}" for k in sorted((r - h).elements())]
    return {**_chk(not diffs, f"H1 {sum(h.values())}건 / R2 {sum(r.values())}건", diffs),
            "n_h1": sum(h.values()), "n_r2": sum(r.values())}


def compare_orders(states, arm, base_none, last) -> dict:
    """M3: (트레이너, 신호일, 종목, 매수/매도, 사유 글) 모음. K1: 마지막 봉에 생긴 주문은 뺀다(R2 는 마지막 봉에 판단 안 함)."""
    h = Counter((tn, o["signal_date"], o["code"], o["action"], o["reason"]) for tn in h1.TRAINERS
                for o in states[arm][tn]["orders"] if o["signal_date"] < last)
    r = Counter((o["sleeve"], o["signal_date"], o["code"], o["action"], o["reason"]) for o in base_none["orders"]
                if o["signal_date"] < last)
    k1 = sum(1 for tn in h1.TRAINERS for o in states[arm][tn]["orders"] if o["signal_date"] >= last)
    diffs = [f"H1 에만 {k[:4]}" for k in sorted((h - r).elements())] + \
        [f"R2 에만 {k[:4]}" for k in sorted((r - h).elements())]
    return {**_chk(not diffs, f"H1 {sum(h.values())}건 / R2 {sum(r.values())}건 (K1: 마지막 봉 주문 {k1}건 뺌)", diffs),
            "n_h1": sum(h.values()), "n_r2": sum(r.values()), "k1_excluded": k1}


def compare_daily(states, arm, base_none, upto) -> dict:
    """M4: 날짜 × 트레이너마다 종가 평가액·주식 평가액·지수 평가액·지수 단위 상대 차 ≤ 1e-9, 현금 절대 차 ≤ 1e-6.
    팀 합계도 같은 기준. 날짜 목록도 같아야 한다(빠진 날·남는 날 없음). K2: R2 끝값(매도 비용 뺀 값)이 아니라 매일 종가 평가만."""
    rows = {r["date"]: r for r in base_none["daily"] if r["date"] <= upto}
    diffs = []
    worst = {"value_rel": 0.0, "stock_rel": 0.0, "idle_rel": 0.0, "units_rel": 0.0, "cash_abs": 0.0}
    team = {}
    for tn in h1.TRAINERS:
        hd = [d for d in states[arm][tn]["days"] if d["date"] <= upto]
        if [d["date"] for d in hd] != sorted(rows):
            diffs.append(f"{tn}: 하루 기록 날짜가 R2 와 다름(H1 {len(hd)}일 / R2 {len(rows)}일)")
        for d in hd:
            rr = rows.get(d["date"])
            if rr is None:
                continue
            t = team.setdefault(d["date"], [0.0, 0.0, 0.0, 0.0])
            for i, k in enumerate(("value", "stock_value", "idle_value", "cash")):
                t[i] += float(d[k])
            for key, hk, rk in (("value_rel", "value", f"v_{tn}"), ("stock_rel", "stock_value", f"stock_{tn}"),
                                ("idle_rel", "idle_value", f"index_{tn}"), ("units_rel", "idle_units", f"units_{tn}")):
                q = _rel(d[hk], rr[rk])
                worst[key] = max(worst[key], q)
                if q > TOL_REL:
                    diffs.append(f"{tn} {d['date']} {hk}: 상대 차 {q:.2e}")
            c = _abs(d["cash"], rr[f"cash_{tn}"])
            worst["cash_abs"] = max(worst["cash_abs"], c)
            if c > TOL_CASH:
                diffs.append(f"{tn} {d['date']} 현금: 차 {c:.2e}")
    for day, (v, s, i, c) in sorted(team.items()):
        rr = rows[day]
        for name, a, b in (("팀 평가액", v, rr["value"]), ("팀 주식", s, rr["stock"]), ("팀 지수", i, rr["index"])):
            if _rel(a, b) > TOL_REL:
                diffs.append(f"{day} {name}: 상대 차 {_rel(a, b):.2e}")
        if _abs(c, rr["cash"]) > TOL_CASH:
            diffs.append(f"{day} 팀 현금: 차 {_abs(c, rr['cash']):.2e}")
    return {**_chk(not diffs, f"{len(rows)}일, 평가액 최대 상대 차 {worst['value_rel']:.1e}, 지수 단위 {worst['units_rel']:.1e}, "
                             f"현금 최대 차 {worst['cash_abs']:.1e}", diffs), **worst, "n_days": len(rows)}


def compare_shadow(states, arm, base_current, last) -> dict:
    """M5′: (장부, 트레이너)마다 H1 그림자 서킷 첫 발동일 == R2 cb="current" 서킷 사건 날짜. K1: 마지막 봉은 뺀다."""
    h, r = {}, {}
    for tn in h1.TRAINERS:
        for d in states[arm][tn]["days"]:
            if d["date"] >= last:
                continue
            if any(e.get("kind") == "shadow_breaker" for e in d["events"]):
                h[tn] = d["date"]
                break
    for ev in base_current["events"]:
        if ev.get("kind") == "서킷(지금)" and ev["date"] < last:
            r.setdefault(ev["sleeve"], ev["date"])
    diffs = [f"{tn}: H1 {h.get(tn)} ≠ R2 {r.get(tn)}" for tn in h1.TRAINERS if h.get(tn) != r.get(tn)]
    shown = ", ".join(f"{tn} {h[tn]}" for tn in h1.TRAINERS if tn in h) or "없음(둘 다)"
    return {**_chk(not diffs, f"첫 발동일 {shown}", diffs), "h1": h, "r2": r}


def compare_over_slots(states, arm, base_none, last) -> dict:
    """K11(참고): R2 over_slots 는 트레이너 합계, H1 은 하루 기록. K1: 마지막 봉은 뺀다. 같아야 한다(M3 의 일부로 본다)."""
    h = {tn: sum(d["over_slots"] for d in states[arm][tn]["days"] if d["date"] < last) for tn in h1.TRAINERS}
    r = {tn: int(base_none["over_slots"].get(tn, 0)) for tn in h1.TRAINERS}
    diffs = [f"{tn}: H1 {h[tn]} ≠ R2 {r[tn]}" for tn in h1.TRAINERS if h[tn] != r[tn]]
    return {**_chk(not diffs, f"빈자리 부족 합계 H1 {sum(h.values())} / R2 {sum(r.values())}", diffs), "h1": h, "r2": r}


def compare_bh(market, states, base) -> dict:
    """M6: 보고서 함수(h1_report.index_bh_from_states)의 같은 시작 지수 B&H 매일 값 == R2 index_buy_hold_fractional(i0+1).
    단위는 비트까지 같아야 하고, 마지막 날은 R2 가 매도 비용을 뺀 값이라(K2) 단위 × 종가로 비교."""
    o = h1_report.index_bh_from_states(market, states)
    bh = base["bh"]
    diffs = []
    if o["dates"][1:] != bh["dates"]:
        diffs.append(f"날짜 목록이 다름(H1 {len(o['dates']) - 1} / R2 {len(bh['dates'])})")
    if o["units"] != bh["units"]:
        diffs.append(f"지수 B&H 단위 {o['units']!r} ≠ {bh['units']!r}")
    worst = 0.0
    for a, b in zip(o["values"][1:-1], bh["equity"][:-1]):
        worst = max(worst, _rel(a, b))
    if worst > TOL_REL:
        diffs.append(f"매일 값 최대 상대 차 {worst:.2e}")
    if o["units"] is not None and _rel(o["values"][-1], bh["units"] * bh["last_close"]) > TOL_REL:
        diffs.append("마지막 날 단위 × 종가가 다름")
    return {**_chk(not diffs, f"단위 {'같음' if o['units'] == bh['units'] else '다름'}, 매일 값 최대 상대 차 {worst:.1e}", diffs),
            "units": o["units"]}


def compare_interest(market, states, base, series) -> dict:
    """M7: 보고서의 금리 규칙·이자 식(h1_report.a0_interest) vs R2 sim_team.rate_for_days(같은 달력·같은 R2 금리 파일).
    날마다 금리가 같고(NaN 은 NaN 끼리), 이자는 R2 금리로 같은 식을 따로 계산한 값과 상대 차 ≤ 1e-9."""
    a = h1_report.a0_interest(market, states, series)
    rb = base["rates"]
    diffs = []
    if a["dates"] != rb["dates"]:
        diffs.append(f"달력이 다름(H1 {len(a['dates'])} / R2 {len(rb['dates'])})")
    n_rate = 0
    for d, x, y in zip(a["dates"], a["rates"], rb["values"]):
        same = (math.isnan(x) and math.isnan(y)) or x == y
        if not same:
            n_rate += 1
            if n_rate <= 5:
                diffs.append(f"{d} 금리 H1 {x!r} ≠ R2 {y!r}")
    acc, ref = 0.0, []
    for c, r in zip(a["cash"], rb["values"]):
        q = 0.0 if not math.isfinite(r) else r / 100 / h1_report.DAYS_PER_YEAR
        acc = acc * (1 + q) + float(c) * q
        ref.append(acc)
    worst = max((_rel(x, y) for x, y in zip(a["interest"], ref)), default=0.0)
    if worst > TOL_REL:
        diffs.append(f"이자 최대 상대 차 {worst:.2e}")
    a0_last = sum(states["A0"][tn]["days"][-1]["value"] for tn in h1.TRAINERS)
    approx = a0_last + (a["interest"][-1] if a["interest"] else 0.0)
    ref_r2 = base.get("ref_a0_interest", {}).get("last_value")
    return {**_chk(not diffs, f"{len(a['dates'])}일 금리 같음, 이자 최대 상대 차 {worst:.1e}", diffs),
            "interest_last": a["interest"][-1] if a["interest"] else 0.0, "a0_plus_interest": approx,
            "r2_a0_interest_on_last": ref_r2,
            "approx_gap_pct": None if not ref_r2 else (approx / ref_r2 - 1) * 100}


POS_FIELDS = ("주식 수", "매수가", "보유일수", "매수일")


def compare_positions(h_pos, base, dates) -> dict:
    """M10 보유 상태(검토 5 P-2): 날마다 × 장부 × 트레이너마다 보유 종목 모음이 같고, 종목마다 주식 수·매수가·보유일수·매수일이
    **정확히** 같다. h_pos = {날짜: {arm: {트레이너: {종목: [주식 수, 매수가, 보유일수, 매수일]}}}}(새 코드: 날마다 커밋 뒤 장부
    파일의 positions), base = 하네스 결과(기준값: 날마다 종가 뒤 R2 sleeve.positions). 마지막 봉도 포함(체결 뒤 상태라 K1 무관).
    보유일수는 정지일(그 종목 봉이 없는 날)엔 늘지 않아야 하므로, 정지 중 '판단 쉼' 규칙이 R2 와 같은지 여기서 직접 본다."""
    diffs, n = [], 0
    for arm in h1.ARMS:
        r = {x["date"]: x["sleeves"] for x in base["arms"][arm]["none"].get("positions") or []}
        for d in dates:
            hd, rd = (h_pos or {}).get(d), r.get(d)
            if hd is None or rd is None:
                diffs.append(f"{arm} {d}: 보유 상태 기록 없음(H1 {'있음' if hd is not None else '없음'} / "
                             f"R2 {'있음' if rd is not None else '없음'})")
                continue
            for tn in h1.TRAINERS:
                a, b = hd[arm][tn], rd.get(tn, {})
                if set(a) != set(b):
                    diffs.append(f"{arm} {d} {tn}: 보유 종목 H1 {sorted(a)} ≠ R2 {sorted(b)}")
                for c in sorted(set(a) & set(b)):
                    n += 1
                    for i, name in enumerate(POS_FIELDS):
                        x, y = a[c][i], b[c][i]
                        if x != y or isinstance(x, bool) or isinstance(y, bool) or \
                                (isinstance(x, float) and not math.isfinite(x)):
                            diffs.append(f"{arm} {d} {tn} {c} {name}: H1 {x!r} ≠ R2 {y!r}")
    return {**_chk(not diffs, f"{len(dates)}일 × 장부 2 × 트레이너 3, 보유 종목·날 {n}건의 주식 수·매수가·보유일수·매수일", diffs),
            "n": n}


def compare_window(market, states, base, *, series=None, do_m6=True, do_m7=True, h_pos=None) -> dict:
    """한 창의 M1~M7(+ h_pos 를 주면 M10) 비교(M8·M9 는 실행 결과로 따로). base = 하네스 결과의 그 창. 돌려줌 {"M1": …, …}."""
    last = base["i1"]
    out = {}
    per_arm = {}
    for arm in h1.ARMS:
        bn, bc = base["arms"][arm]["none"], base["arms"][arm]["current"]
        per_arm[arm] = {"M1": compare_fills(states, arm, bn, last), "M2": compare_skips(states, arm, bn, last),
                        "M3": compare_orders(states, arm, bn, last), "K11": compare_over_slots(states, arm, bn, last),
                        "M4": compare_daily(states, arm, bn, last), "M5": compare_shadow(states, arm, bc, last)}
    for m in ("M1", "M2", "M3", "M4", "M5"):
        parts = [per_arm[a][m] for a in h1.ARMS]
        diffs = [f"{a}: {d}" for a in h1.ARMS for d in per_arm[a][m]["diffs"]]
        if m == "M3":                                     # K11 빈자리 부족 합계도 주문 비교의 일부로
            parts += [per_arm[a]["K11"] for a in h1.ARMS]
            diffs += [f"{a} 빈자리 부족: {d}" for a in h1.ARMS for d in per_arm[a]["K11"]["diffs"]]
        out[m] = {**_chk(all(p["ok"] for p in parts), " · ".join(f"{a} {per_arm[a][m]['detail']}" for a in h1.ARMS)
                         + (" · " + " / ".join(f"{a} {per_arm[a]['K11']['detail']}" for a in h1.ARMS)
                            if m == "M3" else ""), diffs),
                  "arms": {a: per_arm[a][m] for a in h1.ARMS}}
    if do_m6:
        out["M6"] = compare_bh(market, states, base)
    if do_m7:
        out["M7"] = compare_interest(market, states, base, series) if series is not None else \
            _chk(False, "금리 자료를 읽지 못함", ["R2 data/rates 금리 파일 없음"])
    if h_pos is not None:
        out["M10"] = compare_positions(h_pos, base, base["dates"])
    return out


def check_ledgers(market, root, ch, env, frames) -> dict:
    """M8 의 장부 점검: 재현 장부 전체에 check_ledger(그날 시세 frames 로 L3·L6 까지)·check_pair·check_decisions 의 L 오류 0.
    L22 허용 지문은 지금 재현 중인 (code_hash, env) 하나(설계 R2-2)."""
    mk = h1._mkey(market)
    loaded = h1.load_market(mk, root, repair=False)
    states = loaded.states
    decisions = h1.DecisionLog(h1.decisions_path(root, mk), read_only=True)
    cal_line = h1._last_ok_calendar_line(root, mk)
    cal = cal_line.get("dates") if cal_line else None
    allowed = {(ch, h1.env_key(env))}
    probs = []
    for arm in h1.ARMS:
        probs += h1_check.check_ledger(mk, arm, states[arm], cal, decisions, allowed, frames=frames)
    probs += h1_check.check_pair(mk, states["A0"], states["A1"], decisions)
    probs += h1_check.check_decisions(mk, decisions, h1._head_digest(loaded.head))
    errs = h1_check.errors(probs)
    return {"n_l": len(errs), "list": [f"{p.code} {p.arm or ''}/{p.trainer or ''} {p.date or ''}: {p.detail}"
                                       for p in errs[:20]], "states": states, "loaded": loaded}


def check_runs(root, market, w4_ok=()) -> dict:
    """M8 의 실행 일지 점검: 모든 실행의 끝 줄에서 D 등급 0, W 는 창마다 허용한 것만(검토 5 P-11):
    W2(거래정지)·W3(팀장 끔 폴백)은 모든 창, W4(종목군 시세 못 받음)는 w4_ok 종목만(W2 창의 아직 상장 전 넷). 경고 종류별 수를 센다."""
    import re
    mk = h1._mkey(market)
    ends = [r for r in h1.read_jsonl(Path(root) / "runs.jsonl") if r.get("event") == "end" and r.get("market") == mk]
    d = Counter()
    w = Counter()
    bad_exit = Counter()
    w4_codes = Counter()
    for r in ends:
        if r.get("exit_code") != 0:
            bad_exit[r.get("exit_code")] += 1
        for p in r.get("problems") or []:
            if isinstance(p, dict) and p.get("level") == "D":
                d[str(p.get("code"))] += 1
            if isinstance(p, dict) and p.get("level") == "W":
                w[str(p.get("code"))] += 1
                if p.get("code") == "W4":
                    m = re.search(r"종목군 (\S+) 시세", str(p.get("detail") or ""))
                    w4_codes[m.group(1) if m else "(종목 모름)"] += 1
    other = sorted(k for k in w if k not in W_ALLOWED and k != "W4")
    bad_w4 = sorted(c for c in w4_codes if c not in set(w4_ok))
    if bad_w4:
        other.append(f"W4({', '.join(bad_w4)})")
    return {"n_runs": len(ends), "d": dict(d), "w": dict(sorted(w.items())), "bad_exit": dict(bad_exit),
            "w_other": other, "w4_codes": dict(sorted(w4_codes.items()))}


def check_m9(run_res, root, market, states) -> dict:
    """M9: 하루 두 번째 실행이 장부 6개·meta·HEAD·backup·판정 기록을 바꾸지 않음, 저장 → 읽기 뒤 지수 단위가 float.hex 까지
    같음(파일 글자에서 직접 읽은 값 == 하루 기록에 적은 값 == 엄격 읽기 값)."""
    mk = h1._mkey(market)
    diffs = [f"{x['bar']}: 두 번째 실행이 파일을 바꿈(종료 코드 {x['code']})" for x in run_res["twice"] if not x["same"]]
    diffs += [f"{x['bar']}: 같은 날 두 번째 실행 종료 코드 {x['code']}" for x in run_res["twice"] if x["code"] != 0]
    if len(run_res["twice"]) != len(run_res["cal"]):
        diffs.append(f"두 번째 실행 {len(run_res['twice'])}번 ≠ 봉 {len(run_res['cal'])}개")
    idle = h1.idle_code(mk)
    n_hex = 0
    for tn in h1.TRAINERS:
        raw = json.loads(h1.ledger_path(mk, "A1", tn, root).read_text(encoding="utf-8"))
        held = raw["wallet"]["holdings"].get(idle)
        last = raw["days"][-1]
        mem = states["A1"][tn]["wallet"].holdings.get(idle)
        a = float(held["shares"]) if held else 0.0
        b = float(last["idle_units"])
        c = float(mem.shares) if mem else 0.0
        if not (a.hex() == b.hex() == c.hex()):
            diffs.append(f"A1/{tn}: 지수 단위가 저장·읽기에서 바뀜 {a.hex()} / {b.hex()} / {c.hex()}")
        n_hex += 1
    return _chk(not diffs, f"같은 날 두 번째 실행 {len(run_res['twice'])}번 모두 파일 그대로, 지수 단위 float.hex {n_hex}곳 같음",
                diffs)


def replay_last_day() -> str:
    """모든 재현 창(W1·W2·W3)의 끝 날짜 중 가장 늦은 날(K9 의 '뒤에 더한 세율 줄은 이 날보다 뒤' 기준)."""
    return max(s["end"] for s in WINDOWS.values())


def tax_table_problems(h_table, r2_table, last) -> list:
    """K9 국내 매도세 표(검토 5 P-1): H1 표의 앞줄(R2 표에 있는 줄 수만큼)이 R2 표와 **똑같고**, 그 뒤에 더한 줄(사전 등록 ⑥-ii
    세율 줄 추가)은 시행일이 날짜 순서대로이고 모든 재현 창의 마지막 날(last)보다 뒤여야 한다 — 그래야 재현 창 안의 모든 매도세가
    R2 와 같다. 앞줄이 바뀌었거나 줄었거나, 더한 줄이 재현 창 안에 들어오면 문제 목록."""
    h, r = h1._norm(h_table), h1._norm(r2_table)
    if len(h) < len(r) or h[:len(r)] != r:
        return [f"K9: 국내 매도세 표의 앞줄이 R2 표와 다름(앞줄을 바꾸거나 지움) — H1 {h[:len(r)]} / R2 {r}"]
    out, prev = [], (r[-1][0] if r else "")
    for row in h[len(r):]:
        d = row[0] if isinstance(row, list) and row else None
        if not isinstance(d, str) or d <= prev:
            out.append(f"K9: 더한 세율 줄 {row} 의 시행일이 앞줄보다 뒤가 아님(날짜 순서)")
        elif d <= last:
            out.append(f"K9: 더한 세율 줄 {row} 의 시행일이 재현 창 마지막 날 {last} 보다 뒤가 아님(재현 창 안의 매도세가 바뀜)")
        prev = d if isinstance(d, str) else prev
    return out


def k_checks(market, frames, universe, base, start_date, last) -> dict:
    """받아들이는 차이의 전제를 이번 자료로 다시 확인한다(설계 §5.5).
    K4 스크리너 70봉(H1) vs 60봉(R2): 창 시작 S 에 확정 봉이 1~69개인 종목이 없고, 창 안 신규 상장도 없다.
    K5 '오래된 봉' 기준: 창의 날마다 종목군 중 그날 확정 봉이 있는 종목이 있다(스캔 최근 봉 == t).
    K9 국내 매도세 표: R2 표가 H1 표의 앞부분이고, 더한 줄은 모든 재현 창 뒤(tax_table_problems).
    K3 종목군: 국내는 R2 KR_UNIVERSE 와 같은 32개·같은 순서."""
    mk = h1._mkey(market)
    diffs = []
    dates = base["dates"]
    for c in universe:
        df = frames.get(c)
        if df is None:
            continue
        ds = [x.date().isoformat() for x in df.index]
        n_before = sum(1 for d in ds if d < start_date)
        inside = [d for d in ds if start_date <= d <= last]
        if 0 < n_before < 70:
            diffs.append(f"K4: {c} 창 시작 전 확정 봉 {n_before}개(1~69 — H1 70봉 기준과 R2 60봉 기준이 갈릴 수 있음)")
        if n_before == 0 and inside:
            diffs.append(f"K4: {c} 창 안에서 새로 상장({inside[0]})")
    have = set()
    for c in universe:
        df = frames.get(c)
        if df is not None:
            have |= {x.date().isoformat() for x in df.index}
    stale = [d for d in dates if d not in have]
    if stale:
        diffs.append(f"K5: 종목군 어느 종목에도 확정 봉이 없는 날 {stale[:5]}")
    if base.get("_kr_sell_tax") is not None and mk == "kr":
        diffs += tax_table_problems([list(x) for x in h1.KR_SELL_TAX], base["_kr_sell_tax"], replay_last_day())
    if base.get("_kr_universe") is not None and mk == "kr" and base.get("_kind") == "real":
        if list(markets.KR_UNIVERSE.values()) != base["_kr_universe"]:
            diffs.append("K3: KR_UNIVERSE 가 R2 브랜치와 다름(32개·순서)")
    return _chk(not diffs, "K3·K4·K5·K9 전제 확인" + ("" if not diffs else f" — 어긋남 {len(diffs)}"), diffs)


# ============================ 4. W3 합성 차등 재현 (§5.2 W3, 장면 s1~s7) ============================

W3_BRAINS_TEMPLATE = '''"""h1_replay W3 가짜 브레인 (h1_replay.py 가 자동으로 만듦 — 고치지 마세요).
같은 파일을 기준값(R2 sim_team.MarketData(brains=...))과 새 코드(team·screener.BRAINS)가 함께 읽는다.
정해진 (종목, 날짜)에만 매수/매도 신호를 내고, 그 밖에는 '관망'. 종목은 시세의 Tag 칸("c" + 종목코드)으로 안다.
sell_after = [(종목, k)]: 그 종목을 들고 있고 보유일수(position["days_held"])가 k 이상이 된 첫 판단에서 매도 —
보유일수를 세는 규칙(정지일은 세지 않음)이 R2 와 다르면 매도 날이 달라져 체결 비교(M1)도 갈린다(검토 5 P-2)."""

PLAN = __PLAN__
TRAINERS = ("마라토너", "스프린터", "파이오니어")


def _make(tname):
    p = PLAN.get(tname, {})
    buys = frozenset(tuple(x) for x in p.get("buy", []))
    sells = frozenset(tuple(x) for x in p.get("sell", []))
    after = {x[0]: int(x[1]) for x in p.get("sell_after", [])}

    class W3Brain:
        def add_indicators(self, df):
            return df.copy()

        def decide(self, df, position):
            code = str(df["Tag"].iloc[-1])[1:]
            d = df.index[-1].date().isoformat()
            if position is None and (code, d) in buys:
                return "매수", f"재현 W3 가짜 매수 신호 {code} {d} ({tname})"
            if position is not None and (code, d) in sells:
                return "매도", f"재현 W3 가짜 매도 신호 {code} {d} ({tname})"
            if position is not None and code in after and int(position["days_held"]) >= after[code]:
                return "매도", f"재현 W3 가짜 보유일수 매도 {code} 보유 {int(position['days_held'])}일 ({tname})"
            return "관망", "재현 W3 가짜 관망"

    W3Brain.__name__ = "W3Brain_" + str(TRAINERS.index(tname))
    return W3Brain


BRAINS = {t: _make(t) for t in TRAINERS}
'''


def _w3_frame(rng, dates, base, *, ret=0.012, gap=0.004):
    """합성 일봉(시가·종가가 다르게, 값은 소수 2자리). 결정적(같은 씨앗 → 같은 값)."""
    o, c, prev = [], [], float(base)
    for _ in dates:
        op = round(prev * (1 + rng.uniform(-gap, gap)), 2)
        cl = round(prev * (1 + rng.uniform(-ret, ret)), 2)
        o.append(op)
        c.append(cl)
        prev = cl
    return o, c


def _w3_rows(o, c, vol):
    return [[op, round(max(op, cl) * 1.005, 2), round(min(op, cl) * 0.995, 2), cl, v] for op, cl, v in zip(o, c, vol)]


def _solve_open(target, q, fee, slip, tax):
    """매도 순수입(net) = P(1−slip)q − 수수료 − 매도세 가 target 이 되는 시가 P(소수 6자리). PaperWallet.sell 과 같은 식."""
    def net(p):
        proceeds = p * (1 - slip) * q
        return proceeds - proceeds * fee - proceeds * tax
    p = target / ((1 - slip) * q * (1 - fee - tax))
    best = round(p, 6)
    for step in range(-50, 51):                  # 소수 6자리 반올림 오차를 줄인다
        cand = round(p + step * 1e-6, 6)
        if abs(net(cand) - target) < abs(net(best) - target):
            best = cand
    return best, net(best)


def make_w3(dst) -> dict:
    """W3 합성 세계(국내)를 dst 에 만든다: KS200.csv·<종목>.csv(원본 모양 — 정지일은 거래량 0 행)·w3_brains.py·w3_meta.json.
    장면(설계 §5.2): s1 대기 매수가 3일 정지를 가로지름 / s2 보유 종목이 정지를 가로지르고 정지 전날 매도 신호 /
    s3 같은 날 매도 + 매수(지수를 팔아 자금) / s4 A1 현금 부족 보류 / s5 쓸어 담기 문턱(남은 현금 0.99… 그대로, 1.00… 지수로) /
    s6 세율 경계일(2019-05-31 0.30% → 2019-06-03 0.25%) 매도 + 그림자 서킷(누적 −10%·하루 −7%) /
    s7 '0주' 보류(종목 상한 안에서 1주도 못 삼, 검토 5 P-10).
    s5 는 A1 파이오니어의 남는 현금이 문턱 근처가 되게 그날 시가를 PaperWallet 과 같은 식으로 풀어 정한다.
    s2 의 G 는 '보유일수 31 이 되면 매도'(sell_after)라, 정지 3일(W33~W35)을 보유일수로 세지 않아야 W37 신호 → W38 매도가 된다
    (보유일수 규칙이 R2 와 다르면 매도 날이 달라짐, 검토 5 P-2)."""
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    all_days = [d.date().isoformat() for d in pd.bdate_range(W3_HIST_START, W3_END)]
    i0 = all_days.index(W3_START)
    W = all_days[i0:]
    A, B, C, D4 = "005380", "035420", "105560", "051910"         # 마라토너(30%): 셋 체결, 넷째는 현금 부족(s4)
    E, F, G, H = "000660", "068270", "207940", "005930"          # 스프린터(20%): s1·s2·s3
    X, Y = "035720", "006400"                                    # 파이오니어(15%): s5
    Z = "003550"                                                 # 파이오니어: s7 '0주'(시가가 상한 150만 원보다 큼)
    G_AFTER = 31                                                 # s2: G 는 보유일수 31 이 되면 매도
    rng = np.random.default_rng(20261105)
    bases = {"005930": 52000, "000660": 76000, "005380": 140000, "035420": 150000, "105560": 47000,
             "068270": 200000, "207940": 380000, "051910": 330000, "035720": 120000, "006400": 250000}
    first10 = [c for c in W3_UNIVERSE if c != Z]                 # 씨앗 순서를 그대로 두려고 Z 는 따로 만든다
    n = len(all_days)
    px = {c: _w3_frame(rng, all_days, bases[c]) for c in first10}
    idle_o, idle_c = _w3_frame(rng, all_days, 280.0, ret=0.006, gap=0.002)
    vol = {c: [float(rng.integers(500_000, 2_000_000)) for _ in all_days] for c in first10}
    rng_z = np.random.default_rng(20261106)
    px[Z] = _w3_frame(rng_z, all_days, 2_500_000.0)
    vol[Z] = [float(rng_z.integers(100_000, 300_000)) for _ in all_days]

    def at(k):
        return i0 + k

    def scale_from(o, c, k, mult):
        """k 번째 창 날의 종가부터 그 뒤 시가·종가를 모두 mult 배(그날 하루 변화 ≈ mult − 1, 그 뒤는 이어짐)."""
        j = at(k)
        c[j] = round(c[j] * mult, 2)
        for jj in range(j + 1, n):
            o[jj] = round(o[jj] * mult, 2)
            c[jj] = round(c[jj] * mult, 2)

    # s6-누적: 마라토너 보유 A·B·C 가 W5~W14 매일 약 −1.5% (하루 −7% 는 안 걸리고 누적 −10% 가 걸리게)
    for k in range(5, 15):
        for code in (A, B, C):
            scale_from(*px[code], k, 0.985)
    # s6-하루: 대기 자산(KS200)이 W20~W35 매일 약 +0.4% 오르다가 W36 종가 약 −10%
    #          (A1 파이오니어는 쉬는 돈 대부분이 지수라 하루 −8%대, 그동안 올라 있어 누적은 −10% 안 → '하루' 사유)
    for k in range(20, 36):
        scale_from(idle_o, idle_c, k, 1.004)
    scale_from(idle_o, idle_c, 36, 0.90)
    # s3: E 를 W25 시가에 산 값보다 6% 싸게(판 돈 < H 에 필요한 돈 → A1 은 모자란 만큼 지수를 팔아야 함)
    e_buy = px[E][0][at(10)]
    eo, ec = px[E]
    eo[at(25)] = round(e_buy * 0.94, 2)
    ec[at(25)] = round(e_buy * 0.945, 2)
    # 정지(원본 거래량 0 행: 시가·고가·저가 0, 종가 = 전날 종가)
    halts = {E: [7, 8, 9], F: [19, 20, 21], G: [33, 34, 35]}

    # s5: 파이오니어 X 를 W4 시가에 q 주 → W12 X 매도 + Y 매수(남는 돈 L1) → W16 Y 매도 + X 매수(남는 돈 L2)
    mkt = markets.MARKETS["kr"]
    fee, slip = mkt.fee_rate, mkt.slippage
    budget = h1.TOTALS["kr"] * main.CONFIG["배분비율"]["파이오니어"]
    cap = main.CONFIG["종목상한"]["파이오니어"]
    L1, L2 = 0.990, 0.012

    def need_of(p):
        n_ = shares_within_cap(budget, cap, p, fee, slip)
        e = p * (1 + slip)
        return n_, e * n_ + e * n_ * fee

    q_x = shares_within_cap(budget, cap, px[X][0][at(4)], fee, slip)
    n_y, need_y = need_of(px[Y][0][at(12)])
    p_x12, net1 = _solve_open(need_y + L1, q_x, fee, slip, h1.kr_sell_tax(W[12]))
    px[X][0][at(12)] = p_x12
    px[X][1][at(12)] = round(p_x12 * 1.001, 2)
    n_x2, need_x2 = need_of(px[X][0][at(16)])
    p_y16, net2 = _solve_open(need_x2 + L2, n_y, fee, slip, h1.kr_sell_tax(W[16]))
    px[Y][0][at(16)] = p_y16
    px[Y][1][at(16)] = round(p_y16 * 1.001, 2)
    s5 = {"q_x": q_x, "n_y": n_y, "n_x2": n_x2, "left1": net1 - need_y, "left2": net2 - need_x2,
          "x_open_w12": p_x12, "y_open_w16": p_y16}
    # s7: Z 를 W19 신호 → W20 시가에 사려 하면 상한(시작 예산 1천만 원 × 15%) 안에서 1주도 못 삼 → '0주' 보류
    if shares_within_cap(budget, cap, px[Z][0][at(20)], fee, slip) != 0:
        raise ReplayEnvError("W3 합성 세계: s7 종목이 상한 안에서 1주라도 살 수 있음(장면이 안 됨)")

    for code in W3_UNIVERSE:
        o, c = px[code]
        rows = _w3_rows(o, c, vol[code])
        for k in halts.get(code, []):
            j = at(k)
            rows[j] = [0.0, 0.0, 0.0, rows[j - 1][3], 0.0]
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(all_days, name="Date"),
                          columns=["Open", "High", "Low", "Close", "Volume"])
        df["Tag"] = "c" + code
        df.to_csv(dst / f"{code}.csv")
    idx = pd.DataFrame(_w3_rows(idle_o, idle_c, [1e9] * n), index=pd.DatetimeIndex(all_days, name="Date"),
                       columns=["Open", "High", "Low", "Close", "Volume"])
    idx.to_csv(dst / "KS200.csv")
    plan = {
        "마라토너": {"buy": [[A, W[2]], [B, W[2]], [C, W[2]], [D4, W[2]]], "sell": [[A, W[28]], [B, W[29]]]},
        "스프린터": {"buy": [[F, W[2]], [G, W[2]], [E, W[6]], [H, W[24]]], "sell": [[F, W[18]], [E, W[24]]],
                 "sell_after": [[G, G_AFTER]]},
        "파이오니어": {"buy": [[X, W[3]], [Y, W[11]], [X, W[15]], [Z, W[19]]], "sell": [[X, W[11]], [Y, W[15]]]},
    }
    (dst / "w3_brains.py").write_text(W3_BRAINS_TEMPLATE.replace("__PLAN__", json.dumps(plan, ensure_ascii=False,
                                                                                         indent=1)),
                                      encoding="utf-8")
    meta = {"W": W, "plan": plan, "halts": {c: [W[k] for k in ks] for c, ks in halts.items()},
            "codes": {"A": A, "B": B, "C": C, "D4": D4, "E": E, "F": F, "G": G, "H": H, "X": X, "Y": Y, "Z": Z},
            "s5": s5, "g_after": G_AFTER, "universe": list(W3_UNIVERSE)}
    # 저장 → 읽기에서 값이 비트까지 그대로인지(두 쪽이 같은 값을 읽어야 함)
    for code in (X, Y):
        back = read_raw(dst / f"{code}.csv")
        want = p_x12 if code == X else p_y16
        day = W[12] if code == X else W[16]
        if float(back.loc[pd.Timestamp(day), "Open"]) != want:
            raise ReplayEnvError("W3 합성 시세 CSV 가 값을 비트까지 지키지 못했어요")
    (dst / "w3_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def load_brains(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("h1_replay_w3_brains_local", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.BRAINS


def check_w3_scenes(states, meta) -> dict:
    """W3 장면이 새 코드 쪽에서 실제로 그 길을 지났는지(M1~M5′·M10 이 같으므로 기준값도 같은 길을 지남).
    장면마다 '그 전제'(예: 정말 들고 있었나)까지 확인한다 — 전제가 빠져 공허하게 참이 되지 않게(검토 5 P-3)."""
    W, c = meta["W"], meta["codes"]
    out = {}
    empty = {"halted": [], "marks": {}, "cash": math.nan, "events": []}

    def fills(arm, tn, date=None):
        return [f for f in states[arm][tn]["fills"] if date is None or f["date"] == date]

    def day(arm, tn, d):
        return next((r for r in states[arm][tn]["days"] if r["date"] == d), empty)

    def held(arm, tn, code, ks):
        """그 날들 종가에 그 종목을 들고 있었나(하루 기록 marks 는 그날 보유 종목의 평가 종가 = positions 의 열쇠)."""
        return all(isinstance(day(arm, tn, W[k])["marks"].get(code), float) for k in ks)
    sp, ma, pi = "스프린터", "마라토너", "파이오니어"
    # s1: 대기 매수(신호 W6)가 정지 W7~W9 를 넘겨 W10 시가에 체결, A1 은 그날 지수를 팔아 자금
    ok1 = all(any(f["code"] == c["E"] and f["side"] == "buy" and f["kind"] == "stock" for f in fills(a, sp, W[10]))
              and all(c["E"] in day(a, sp, W[k])["halted"] for k in (7, 8, 9))
              and not any(f["code"] == c["E"] for k in (7, 8, 9) for f in fills(a, sp, W[k])) for a in h1.ARMS)
    ok1 = ok1 and any(f["purpose"] == f"fund:{c['E']}" for f in fills("A1", sp, W[10]))
    out["s1"] = _chk(ok1, f"{c['E']} 매수 신호 {W[6]} → 정지 {W[7]}~{W[9]} → {W[10]} 시가 체결(A1 지수 매도로 자금)")
    # s2: 보유 F, 매도 신호 W18(정지 전날) → 정지 W19~W21 동안 대기·평가는 정지 전 종가 → W22 매도.
    #     G 는 W32~W35 를 들고 신호 없이 정지(W33~W35)를 넘기고(평가는 정지 전 종가), 보유일수 31 이 된 W37 에 매도 신호 → W38 매도
    ok2 = True
    ga = int(meta.get("g_after", 31))
    for a in h1.ARMS:
        o = [x for x in states[a][sp]["orders"] if x["code"] == c["F"] and x["action"] == "매도"]
        ok2 = ok2 and len(o) == 1 and o[0]["signal_date"] == W[18] and o[0]["done_date"] == W[22]
        ok2 = ok2 and held(a, sp, c["F"], range(18, 22))
        ok2 = ok2 and all(c["F"] in day(a, sp, W[k])["halted"] for k in (19, 20, 21))
        ok2 = ok2 and all(day(a, sp, W[k])["marks"].get(c["F"]) == day(a, sp, W[18])["marks"].get(c["F"])
                          for k in (19, 20, 21))
        ok2 = ok2 and held(a, sp, c["G"], range(32, 36))
        ok2 = ok2 and all(c["G"] in day(a, sp, W[k])["halted"] for k in (33, 34, 35))
        ok2 = ok2 and all(day(a, sp, W[k])["marks"].get(c["G"]) == day(a, sp, W[32])["marks"].get(c["G"])
                          for k in (33, 34, 35))
        og = [x for x in states[a][sp]["orders"] if x["code"] == c["G"] and x["action"] == "매도"]
        ok2 = ok2 and len(og) == 1 and og[0]["signal_date"] == W[37] and og[0]["done_date"] == W[38]
        ok2 = ok2 and any(f["code"] == c["G"] and f["side"] == "sell" for f in fills(a, sp, W[38]))
    out["s2"] = _chk(ok2, f"{c['F']} 매도 신호 {W[18]} → 정지 {W[19]}~{W[21]} → {W[22]} 체결 · {c['G']} 들고 정지 "
                          f"{W[33]}~{W[35]}(평가는 정지 전 종가, 보유일수 안 셈) → 보유일수 {ga} 인 {W[37]} 신호 → {W[38]} 매도")
    # s3: 같은 날 W25 매도(E) + 매수(H), A1 은 모자란 만큼 지수 매도(fund:H)
    ok3 = all({(f["code"], f["side"]) for f in fills(a, sp, W[25]) if f["kind"] == "stock"} >= {(c["E"], "sell"),
                                                                                            (c["H"], "buy")}
              for a in h1.ARMS)
    ok3 = ok3 and any(f["purpose"] == f"fund:{c['H']}" for f in fills("A1", sp, W[25]))
    out["s3"] = _chk(ok3, f"{W[25]} 같은 시가에 {c['E']} 매도 → {c['H']} 매수(A1 은 지수를 팔아 모자란 돈)")
    # s4: 마라토너 넷째 매수(D4)가 A1 에서 현금 부족 보류(지수를 팔지 않음)
    ok4 = any(s["code"] == c["D4"] and s["kind"] == "현금부족" and s["date"] == W[3] for s in states["A1"][ma]["skips"])
    ok4 = ok4 and not any(f["purpose"] == f"fund:{c['D4']}" for f in states["A1"][ma]["fills"])
    out["s4"] = _chk(ok4, f"A1 마라토너 {c['D4']} {W[3]} 현금 부족 보류(그 매수용 지수 매도 없음)")
    # s5: A1 파이오니어 W12 종가 현금이 [0.99, 1) 이고 쓸어 담기 없음 → W16 쓸어 담기 직전 현금 [1, 1.01) 이 지수로
    r12 = day("A1", pi, W[12])
    sw12 = [f for f in fills("A1", pi, W[12]) if f["purpose"] == "sweep"]
    sw16 = [f for f in fills("A1", pi, W[16]) if f["purpose"] == "sweep"]
    ok5 = 0.99 <= r12["cash"] < 1.0 and not sw12 and len(sw16) == 1 and 1.0 <= sw16[0]["cash_before"] < 1.01
    out["s5"] = _chk(ok5, f"A1 파이오니어 {W[12]} 남은 현금 {r12['cash']:.4f}(지수로 안 감) → {W[16]} 쓸어 담기 전 현금 "
                          f"{sw16[0]['cash_before'] if sw16 else float('nan'):.4f}(지수로 감)")
    # s6: 세율 경계 전날(2019-05-31, 0.30%)·당일(2019-06-03, 0.25%) 매도 + 그림자 서킷 누적·하루 둘 다
    ok6 = True
    rates = {}
    for a in h1.ARMS:
        for code, d, rate in ((c["A"], W[29], 0.0030), (c["B"], W[30], 0.0025)):
            f = [x for x in fills(a, ma, d) if x["code"] == code and x["side"] == "sell" and x["kind"] == "stock"]
            got = f[0]["tax"] / (f[0]["exec_price"] * f[0]["qty"]) if f else None
            rates[(a, d)] = got
            ok6 = ok6 and bool(f) and abs(got - rate) < 1e-12
    whys = [e["why"] for a in h1.ARMS for tn in h1.TRAINERS for r in states[a][tn]["days"] for e in r["events"]
            if e.get("kind") == "shadow_breaker" and e.get("first")]
    ok6 = ok6 and any(w.startswith("누적") for w in whys) and any(w.startswith("하루") for w in whys)
    out["s6"] = _chk(ok6, f"매도세 {W[29]} {rates.get(('A0', W[29]))} · {W[30]} {rates.get(('A0', W[30]))}, 그림자 서킷 첫 발동 "
                          f"누적 {sum(1 for w in whys if w.startswith('누적'))}건·하루 {sum(1 for w in whys if w.startswith('하루'))}건")
    # s7: 파이오니어 Z(아주 비싼 종목) 매수 신호 W19 → W20 시가에 상한 안에서 1주도 못 삼 → 두 장부 모두 '0주' 보류,
    #     주문은 skipped(0주), 체결 없음, A1 은 그 매수용 지수를 팔지 않음
    ok7 = True
    for a in h1.ARMS:
        sk = [x for x in states[a][pi]["skips"] if x["code"] == c["Z"] and x["date"] == W[20]]
        oz = [x for x in states[a][pi]["orders"] if x["code"] == c["Z"] and x["action"] == "매수"]
        ok7 = ok7 and len(sk) == 1 and sk[0]["kind"] == "0주"
        ok7 = ok7 and len(oz) == 1 and oz[0]["status"] == "skipped" and oz[0]["why"] == "0주" and oz[0]["done_date"] == W[20]
        ok7 = ok7 and not any(f["code"] == c["Z"] or f["purpose"] == f"fund:{c['Z']}" for f in fills(a, pi))
    out["s7"] = _chk(ok7, f"파이오니어 {c['Z']} 매수 신호 {W[19]} → {W[20]} 시가에 상한 안에서 1주도 못 삼 → 두 장부 '0주' 보류"
                          "(체결·지수 매도 없음)")
    return out


# ============================ 5. 한 창 전체 · 모든 창 ============================

def _frames_at(src, cal_last, codes):
    """마지막 봉 운영 시각으로 받은 확정 시세 {종목: DataFrame} (M8 의 L3·L6 그날 시세 비교, K4·K5 확인용)."""
    now = run_at(src.mk, cal_last)
    out = {}
    with src.fdr_installed():
        for c in codes:
            f = src.fetch(c, now)
            out[c] = None if f is None else f.df
    return out


def stop_cause(root, market, log_path, n_lines=12) -> list:
    """실행이 멈춘 창의 원인(검토 5 P-8): errors.jsonl 의 마지막 L 기록(문제 코드·내용 앞 몇 줄), runs.jsonl 의 마지막
    0 이 아닌 끝 줄(종료 코드·메시지·D 문제), h1 로그의 끝 몇 줄. 보고서·화면에 그대로 옮긴다."""
    out = []
    mk = h1._mkey(market)
    try:
        errs = [r for r in h1.read_jsonl(Path(root) / "errors.jsonl") if r.get("market") == mk]
        if errs:
            e = errs[-1]
            out.append(f"errors.jsonl 마지막 L 기록(봉 {e.get('date')}, 실행 {e.get('run_id')}):")
            for p in (e.get("problems") or [])[:6]:
                if isinstance(p, dict):
                    out.append(f"  {p.get('code')} {p.get('arm') or ''}/{p.get('trainer') or ''} {p.get('date') or ''}: "
                               f"{str(p.get('detail'))[:200]}")
            if e.get("exception"):
                out.append(f"  예외: {e['exception']}")
        ends = [r for r in h1.read_jsonl(Path(root) / "runs.jsonl")
                if r.get("event") == "end" and r.get("market") == mk and r.get("exit_code") not in (0, None)]
        if ends:
            r = ends[-1]
            out.append(f"runs.jsonl 마지막 실패 실행: 종료 코드 {r.get('exit_code')} — {str(r.get('message'))[:300]}")
            for p in [p for p in r.get("problems") or [] if isinstance(p, dict) and p.get("level") in ("D", "L")][:6]:
                out.append(f"  {p.get('level')} {p.get('code')} {p.get('date') or ''}: {str(p.get('detail'))[:200]}")
    except OSError as e:
        out.append(f"(일지를 읽지 못함: {e})")
    try:
        tail = [x for x in Path(log_path).read_text(encoding="utf-8").splitlines() if x.strip()][-n_lines:]
        if tail:
            out.append("h1 실행 로그 끝:")
            out += ["  " + x[:220] for x in tail]
    except OSError:
        pass
    return out


def replay_window(name, spec, base, src, work, ch, env, *, brains=None, meta=None, series=None, progress=_say,
                  twice=True) -> dict:
    """창 하나: 새 코드로 돌리고(run_h1_window) → 비교(M1~M7·M10) → 장부 점검(M8) → 멱등(M9) → K 전제 → (W3) 장면."""
    root = Path(work) / f"root-{name}" / "h1"
    root.mkdir(parents=True)
    mk = spec["market"]
    log_path = Path(work) / f"h1-{name}.log"
    progress(f"  [{name}] 새 코드: h1.start → 날마다 h1.run ×2 ({spec['start']} ~ {spec['end']}, 장부 폴더 {root})")
    rr = run_h1_window(name, spec, src, root, log_path, brains=brains, twice=twice, progress=progress)
    out = {"name": name, "spec": spec, "run": {k: rr[k] for k in ("seconds", "max_run_s")}, "root": str(root),
           "n_bars": len(rr["cal"]), "S": rr["cal"][0], "last": rr["cal"][-1], "log": str(log_path)}
    bad = run_problems(rr)
    out["exit_codes"] = dict(Counter(x["code"] for x in rr["exit_codes"]))
    out["exit_codes2"] = dict(Counter(x["code2"] for x in rr["exit_codes"] if x["code2"] is not None))
    checks = {}
    if bad or len(rr["exit_codes"]) != len(rr["cal"]):
        first = bad[0] if bad else None
        if first is None:
            detail = f"모든 봉을 돌지 못함({len(rr['exit_codes'])}/{len(rr['cal'])}봉)"
        elif first["code"] != 0:
            detail = f"실행이 멈춤: {first['bar']} {first['cmd']} 종료 코드 {first['code']}"
        else:
            detail = f"실행이 멈춤: {first['bar']} 같은 날 두 번째 run 종료 코드 {first['code2']}(첫 실행은 0)"
        if h1.code_hash()[0] != ch:                     # 재현 도중 CODE_FILES 를 고치면 지난 봉 지문이 달라 L22 로 멈춘다
            detail += " — 재현 도중 코드 파일이 바뀜(같은 코드로 처음부터 다시 돌리세요)"
        cause = stop_cause(root, mk, log_path)
        for m in CHECK_ORDER:
            checks[m] = _chk(False, detail, [detail] + cause)
        out["checks"] = checks
        out["stopped"] = {"detail": detail, "cause": cause}
        return out
    if rr["cal"] != base["dates"]:
        checks["K"] = _chk(False, "창 날짜가 R2 와 다름", [f"H1 {rr['cal'][:2]}…{rr['cal'][-1]} / R2 {base['dates'][:2]}…"])
    with no_claude():
        codes = list(src.uni) + [c for c in h1.CAL_PROBE[mk] if c not in src.uni]
        frames = _frames_at(src, rr["cal"][-1], codes)
        led = check_ledgers(mk, root, ch, env, frames)
    states = led["states"]
    checks.update(compare_window(mk, states, base, series=series, do_m6=True, do_m7=True, h_pos=rr["positions"]))
    runs = check_runs(root, mk, spec.get("w4_ok", ()))
    m8_diffs = list(led["list"])
    if runs["d"]:
        m8_diffs.append(f"자료 문제(D) {runs['d']}")
    if runs["w_other"]:
        m8_diffs.append(f"허용 밖 경고 {runs['w_other']} (모든 창 허용: {', '.join(W_ALLOWED)}; W4 허용 종목: "
                        f"{', '.join(spec.get('w4_ok', ())) or '없음'})")
    if runs["bad_exit"]:
        m8_diffs.append(f"0 이 아닌 종료 코드 {runs['bad_exit']}")
    checks["M8"] = _chk(not m8_diffs, f"L 오류 {led['n_l']} · D {sum(runs['d'].values())} · 경고 {runs['w'] or '없음'} "
                                      f"(실행 {runs['n_runs']}번)" + (f" · W4 종목 {runs['w4_codes']}" if runs["w4_codes"]
                                                                  else ""), m8_diffs)
    checks["M9"] = check_m9(rr, root, mk, states)
    kc = k_checks(mk, frames, list(src.uni), base, rr["cal"][0], rr["cal"][-1])
    if "K" in checks:
        kc = _chk(False, checks["K"]["detail"] + " · " + kc["detail"], checks["K"]["diffs"] + kc["diffs"])
    checks["K"] = kc
    if meta is not None:
        scenes = check_w3_scenes(states, meta)
        out["scenes"] = scenes
        miss = [s for s, v in scenes.items() if not v["ok"]]
        checks["S"] = _chk(not miss, f"장면 {', '.join(scenes)} 모두 지남" if not miss else f"지나지 않은 장면 {miss}",
                           [f"{s}: {scenes[s]['detail']}" for s in miss])
    out["checks"] = checks
    out["fingerprint"] = h1.ledger_fingerprint(states)
    out["warnings"] = runs["w"]
    return out


def window_ok(res) -> bool:
    req = REQUIRED[res["spec"]["group"]]
    return all(res["checks"].get(m, {}).get("ok") for m in req)


def _real_source(r2_rep, spec):
    mk = spec["market"]
    data = Path(r2_rep) / "data"
    if mk == "us":
        info = json.loads((data / "us" / "universe.json").read_text(encoding="utf-8"))
        uni = [c for c in info["종목"] if c != "SPY"]
        idle = read_raw(data / "us" / "SPY.csv.gz")
        raws = {c: read_raw(data / "us" / f"{c}.csv.gz") for c in uni}
    else:
        uni = list(markets.KR_UNIVERSE.values())
        idle = read_raw(data / "kr" / "KS200.csv.gz")
        raws = {}
        for c in uni:
            p = data / "kr" / f"{c}.csv.gz"
            if not p.exists():
                raise ReplayEnvError(f"연구 브랜치 data/kr/{c}.csv.gz 가 없어요")
            raws[c] = read_raw(p)
    return ReplaySource(mk, idle, raws, uni)


def replay(groups, r2_ref, work, *, progress=_say, repo=None, specs=None) -> dict:
    """선택한 창(W1·W2·W3)을 모두 돌리고 결과 묶음을 돌려준다(파일 기록은 finish 의 몫). 장부는 모두 work 아래 임시 폴더.
    specs: 창 정의를 바꿔 끼울 때만(시험이 실데이터 창을 몇 봉으로 줄여 돌릴 때). 바꾼 결과는 complete=False 라 기록되지 않는다."""
    t0 = time.time()
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    work = Path(work)
    ch0, files0 = h1.code_hash()
    env0 = h1.env_info()
    windows = WINDOWS if specs is None else specs
    names = [n for n, s in windows.items() if s["group"] in groups]
    progress(f"[재현] 코드 지문 {ch0[:12]}… · 파이썬 {env0.get('python')} · pandas {env0.get('pandas')} · "
             f"FinanceDataReader {env0.get('FinanceDataReader')} · 창 {', '.join(names)}")
    commit = check_r2_commit(r2_ref, repo)                # 고정 커밋인지 먼저(검토 5 P-5)
    progress(f"[재현] 1/4 연구 브랜치 {r2_ref}(커밋 {commit[:12]}, 고정값과 같음)를 임시 폴더에 풀기")
    r2_rep = extract_r2(commit, work / "r2", repo)
    r2_root = r2_rep.parents[1]
    jobs, meta, brains = [], None, None
    for n in names:
        s = windows[n]
        job = {"name": n, "kind": s["kind"], "market": s["market"], "start": s["start"], "end": s["end"]}
        if s["kind"] == "synthetic":
            progress("[재현]     W3 합성 시세·가짜 브레인 만들기(s1~s7)")
            meta = make_w3(work / "w3")
            inside = r2_root / "h1_replay_w3"
            shutil.copytree(work / "w3", inside)              # 기준값 쪽도 같은 파일을 읽는다(설계 §5.2 W3)
            for f in sorted((work / "w3").iterdir()):
                if _sha_file(f) != _sha_file(inside / f.name):
                    raise ReplayEnvError(f"W3 파일 복사본이 다름: {f.name}")
            job.update({"data_dir": str(inside), "brains_file": str(inside / "w3_brains.py"),
                        "universe": list(W3_UNIVERSE)})
            brains = load_brains(work / "w3" / "w3_brains.py")
        jobs.append(job)
    progress("[재현] 2/4 기준값(R2 OperatingStartSim, python -I 하네스) 만들기")
    tb = time.time()
    base_all = run_harness(r2_rep, jobs, work / "harness")
    t_base = time.time() - tb
    base_file = work / "harness" / "harness_out.json"
    base_sha = _sha_file(base_file)
    progress(f"[재현]     기준값 끝 ({t_base:.0f}초): 모듈 {base_all['modules']}")
    if list(markets.KR_UNIVERSE.values()) != base_all["kr_universe"] and any(
            windows[n]["market"] == "kr" and windows[n]["kind"] == "real" for n in names):
        progress("[재현]     ※ R2 브랜치의 KR_UNIVERSE 가 지금 markets.KR_UNIVERSE 와 다름(32개·같은 순서여야 함) → "
                 "국내 실데이터 창은 K3 로 통과할 수 없음")
    rates_dir = r2_rep / "data" / "rates"
    results = {}
    progress("[재현] 3/4 새 코드로 창마다 돌리고 비교")
    for n in names:
        s = windows[n]
        base = dict(base_all["jobs"][n])
        base["_kr_sell_tax"], base["_kr_universe"], base["_kind"] = base_all["kr_sell_tax"], base_all["kr_universe"], \
            s["kind"]
        series = h1_report.load_rates(h1_report.SERIES[s["market"]], rates_dir)
        if s["kind"] == "synthetic":
            d = work / "w3"
            src = ReplaySource("kr", read_raw(d / "KS200.csv"), {c: read_raw(d / f"{c}.csv") for c in W3_UNIVERSE},
                               W3_UNIVERSE)
            res = replay_window(n, s, base, src, work, ch0, env0, brains=brains, meta=meta, series=series,
                                progress=progress)
            # M9 셋째: 같은 코드로 W3 를 한 번 더 돌리면 장부 내용 지문이 같다
            if res.get("fingerprint"):
                src2 = ReplaySource("kr", read_raw(d / "KS200.csv"),
                                    {c: read_raw(d / f"{c}.csv") for c in W3_UNIVERSE}, W3_UNIVERSE)
                again = run_h1_window(n + "-again", s, src2, _fresh(work / "root-W3-again" / "h1"),
                                      work / "h1-W3-again.log", brains=brains, twice=False, progress=None)
                fp2 = None
                if all(x["code"] == 0 for x in again["exit_codes"]):
                    fp2 = h1.ledger_fingerprint(h1.load_market("kr", work / "root-W3-again" / "h1", repair=False).states)
                same = fp2 == res["fingerprint"]
                m9 = res["checks"]["M9"]
                res["checks"]["M9"] = _chk(m9["ok"] and same, m9["detail"] + (" · 두 번 돌린 장부 내용 지문 같음" if same
                                                                               else " · 두 번 돌린 지문이 다름"),
                                           m9["diffs"] + ([] if same else [f"지문 {res['fingerprint'][:12]} ≠ {str(fp2)[:12]}"]))
        else:
            src = _real_source(r2_rep, s)
            res = replay_window(n, s, base, src, work, ch0, env0, series=series, progress=progress)
        res["ok"] = window_ok(res)
        res["ref"] = {"original": base.get("ref_original"), "a0_interest": base.get("ref_a0_interest"),
                      "m7": {k: res["checks"].get("M7", {}).get(k) for k in ("a0_plus_interest", "approx_gap_pct")}}
        results[n] = res
        progress(f"    [{n}] {'같음' if res['ok'] else '차이 있음'} — " + ", ".join(
            f"{m} {'O' if res['checks'].get(m, {}).get('ok') else 'X'}" for m in REQUIRED[s["group"]])
            + f" ({res['run']['seconds']:.0f}초)")
    ch1, _ = h1.code_hash()
    env1 = h1.env_info()
    complete = set(groups) == set(GROUPS) and specs is None
    passed = all(r["ok"] for r in results.values())
    return {"code_hash": ch0, "files": files0, "env": env0, "code_changed": (ch1, env1) != (ch0, env0),
            "r2_ref": r2_ref, "r2_commit": commit, "modules": base_all["modules"],
            "windows": results, "groups": sorted(groups), "complete": complete, "passed": passed,
            "seconds": time.time() - t0, "baseline_seconds": t_base, "baseline_file": str(base_file),
            "baseline_sha256": base_sha, "started_at": started, "work": str(work)}


def _fresh(p):
    p = Path(p)
    p.mkdir(parents=True)
    return p


def data_golden_ok() -> dict:
    """자료 받기 골든(tests/golden_data/): 지금 h1_data 결과가 저장된 outputs.json 과 바이트까지 같아야 통과 기록을 남긴다
    (통과 기록의 data_golden_sha256 이 ⑥-i 판단에 쓰이므로, 깨진 받기 층으로 기록하지 않게)."""
    want = REPO.joinpath(*h1.DATA_GOLDEN_DIR, "outputs.json")
    try:
        with contextlib.redirect_stdout(io.StringIO()):      # 골든의 '받기 실패 흉내' 안내 줄은 화면에 내지 않음
            got = h1.data_golden_outputs()
    except Exception as e:      # noqa: BLE001 — 재는 쪽이 실패해도 기록하지 않는다
        return _chk(False, f"자료 받기 골든을 만들지 못함({type(e).__name__}: {e})", ["골든 실패"])
    if not want.exists():
        return _chk(False, "tests/golden_data/outputs.json 이 없음", ["골든 파일 없음"])
    same = got == want.read_bytes()
    return _chk(same, "자료 받기 골든 결과 == 저장본(바이트)" if same else "자료 받기 골든 결과가 저장본과 다름",
                [] if same else ["h1_data 결과가 tests/golden_data/outputs.json 과 다름"])


# ============================ 6. 기록 · 보고서 ============================

def _ok(b):
    return "통과" if b else "**차이**"


def _verdict_text(res, golden, recorded):
    good = res["passed"] and golden["ok"] and not res["code_changed"]
    if not good:
        return "통과 아님(차이 또는 환경 문제 — 기록 없음)"
    if not res["complete"]:
        return "고른 창은 모두 같음 — 일부 창만 돌려 통과 기록 없음(종료 코드 3, 관문은 열리지 않음)"
    return "통과 — 통과 기록함" if recorded else "통과 — 통과 기록 중"


def _entry_preview(entry) -> str:
    """보고서에 적는 '기록할 줄'(files 는 파일 수와 몇 개만 — 전체는 replay_pass.json 에)."""
    e = {k: v for k, v in entry.items() if k != "files"}
    e["files"] = f"{len(entry.get('files') or {})}개 파일의 sha256 (전체는 replay_pass.json)"
    return json.dumps(e, ensure_ascii=False, indent=1, sort_keys=True)


def render_report(res, *, golden, record_status, entry=None, baseline_rel=None) -> str:
    """재현 보고서(쉬운 말). res = replay() 결과. record_status = 통과 기록 상태 한 줄. entry = 기록할(또는 기록한) 줄."""
    L = []
    w = res["windows"]
    recorded = record_status.startswith("기록함")
    L.append(f"# H1 재현 보고서 — {_verdict_text(res, golden, recorded)}")
    L.append("")
    L.append(f"- 재현 시작: {res['started_at']} · 걸린 시간 {res['seconds']:.0f}초(기준값 {res['baseline_seconds']:.0f}초)")
    L.append(f"- 코드 지문(code_hash): `{res['code_hash']}`")
    env = res["env"]
    L.append(f"- 환경(env): 파이썬 {env.get('python')} · pandas {env.get('pandas')} · numpy {env.get('numpy')} · "
             f"ta {env.get('ta')} · FinanceDataReader {env.get('FinanceDataReader')}")
    L.append(f"- 기준값: 연구 브랜치 `{res['r2_ref']}` → 커밋 `{res['r2_commit']}`(고정값 `{R2_COMMIT}` 과 같음을 확인), 임시 폴더에 "
             f"풀어 그 안의 모듈만 읽음 ({', '.join(f'{k}={v}' for k, v in res['modules'].items())})")
    if res.get("baseline_sha256"):
        L.append(f"- 기준값 결과(하네스 출력) sha256: `{res['baseline_sha256']}`"
                 + (f" — 파일 `{baseline_rel}`" if baseline_rel else ""))
    L.append(f"- 돌린 창: {', '.join(res['groups'])}" + ("" if res["complete"] else " (일부만 — 통과 기록은 W1·W2·W3 를 다 돌릴 때만)"))
    L.append(f"- 자료 받기 골든: {golden['detail']}")
    L.append(f"- 통과 기록: {record_status}")
    if not (res["passed"] and golden["ok"] and not res["code_changed"]) and res.get("work"):
        L.append(f"- 임시 폴더(원인 확인용으로 남겨 둠): `{res['work']}` — 창마다 h1 실행 로그 `h1-<창>.log`, 재현 장부 "
                 "`root-<창>/h1/`(runs.jsonl·errors.jsonl), 기준값 `harness/harness_out.json`")
    L.append("")
    L.append("## 무엇을 했나 (쉬운 설명)")
    L.append("")
    L.append("- **기준값**: 연구 때 쓴 시뮬레이터(R2 `sim_team.py`)를 연구 브랜치 그대로(커밋 고정) 임시 폴더에 풀어 돌렸다. 운영과 "
             "같은 시작 규칙(첫 봉 S 는 돈만 넣고, 다음 봉 S+1 시가에 쉬는 돈을 먼저 전부 지수로 산 뒤 그날 주문)을 넣은 하위 클래스"
             "(`OperatingStartSim`, 설계 §5.1)를 썼다. 서킷(손실 한도)은 끈 것과 켠 것(그림자 비교용)을 둘 다 돌렸다. 날마다 종가 뒤 "
             "보유 상태(종목별 주식 수·매수가·보유일수·매수일)도 적었다.")
    L.append("- **새 코드**: 임시 장부 폴더에서 `h1.start` 한 번, 그 뒤 날마다 `h1.run` 을 실제 운영 시각(국내 그날 23:05, "
             "미국 다음 평일 아침 07:10)으로 불렀다. 같은 날 한 번 더 불러 아무 파일도 바뀌지 않는지(멱등)도 봤다. 시세는 연구 "
             "브랜치의 지난 시세를 그날까지만 잘라 운영 받기 층(`h1_data`)을 그대로 거쳐 넣었다. 팀장(claude)은 부르지 않았다. "
             "날마다 저장된 장부의 보유 상태를 읽어 두었다.")
    L.append("- **비교**: 체결 하나하나·보류·주문·매일 평가액·그림자 서킷 첫 날·지수 사서 들고 있기·이자 계산·장부 점검·멱등"
             "(M1~M9)·보유 상태(M10). 미리 정해 둔 '받아들이는 차이'(K1~K13) 밖의 차이가 하나라도 있으면 통과가 아니다.")
    L.append("")
    L.append("## 창별 결과")
    L.append("")
    L.append("| 항목 | " + " | ".join(w.keys()) + " |")
    L.append("|" + "---|" * (len(w) + 1))
    for m in CHECK_ORDER:
        cells = []
        for n, r in w.items():
            c = r["checks"].get(m)
            if c is None:
                cells.append("–")
                continue
            need = m in REQUIRED[r["spec"]["group"]]
            cells.append(("" if need else "(참고) ") + _ok(c["ok"]))
        L.append(f"| {m} {M_NAMES[m]} | " + " | ".join(cells) + " |")
    L.append("")
    for n, r in w.items():
        s = r["spec"]
        L.append(f"### {n} — {'같음' if r['ok'] else '차이 있음'}")
        L.append("")
        L.append(f"- 시장 {s['market']} · 창 {s['start']} ~ {s['end']} · 실제 S {r.get('S')} ~ 마지막 봉 {r.get('last')} "
                 f"({r.get('n_bars')}봉) · 새 코드 실행 {r['run']['seconds']:.0f}초(한 번 실행 최대 {r['run']['max_run_s']:.1f}초)")
        if r.get("stopped"):
            L.append(f"- **실행이 멈춤**: {r['stopped']['detail']}")
            for x in r["stopped"]["cause"]:
                L.append(f"    - {x}")
        if r.get("warnings") is not None:
            L.append(f"- 경고(멈추지 않음, 실행마다 센 수 — 같은 날 두 번째 실행 포함): {r['warnings'] or '없음'} — 허용: "
                     f"W2 거래정지·W3 팀장 끔(재현)" + (f"·W4 아직 상장 전 {', '.join(s['w4_ok'])}" if s.get("w4_ok") else ""))
        for m in CHECK_ORDER:
            c = r["checks"].get(m)
            if c is None or r.get("stopped"):
                continue
            L.append(f"- {m} {M_NAMES[m]}: {_ok(c['ok'])} — {c['detail']}")
            for d in c["diffs"][:10]:
                L.append(f"    - {d}")
        if r.get("scenes"):
            L.append("- W3 장면:")
            for k, v in r["scenes"].items():
                L.append(f"    - {k}: {_ok(v['ok'])} — {v['detail']}")
        if r.get("fingerprint"):
            L.append(f"- 장부 내용 지문(ledger_fingerprint): `{r['fingerprint']}`")
        L.append("")
    L.append("## 받아들인 차이 (설계 §5.5)")
    L.append("")
    k_rows = [
        ("K1", "R2 는 창 마지막 봉에서 판단을 하지 않음", "마지막 봉에 생긴 주문·빈자리 부족·그림자 서킷을 비교에서 뺐다(체결·매일 값·보유 상태는 포함)"),
        ("K2", "R2 끝값은 매도 비용을 뺀 값", "매일 종가 평가액만 비교, 지수 B&H 마지막 날은 단위 × 종가로"),
        ("K3", "종목군", "재현은 R2 종목군을 강제(미국 universe.json 순서, 국내 KR_UNIVERSE — R2 브랜치와 같은 32개·순서 확인)"),
        ("K4", "스크리너 70봉(H1) vs 60봉(R2)", "창 시작 때 확정 봉 1~69개인 종목·창 안 신규 상장이 없는지 매번 확인(K 칸)"),
        ("K5", "'오래된 봉' 기준", "창의 날마다 종목군 중 그날 확정 봉이 있는 종목이 있는지 확인(K 칸)"),
        ("K6", "team.py 의 저장 안 하는 날", "H1 은 매일 저장 → R2 와 같은 쪽(운영 장부와의 차이일 뿐)"),
        ("K7", "현금 이자", "기준값을 interest=False 로, 이자는 M7 로 따로"),
        ("K8", "팀장 판정 칸", "재현은 팀장 끔(replay_no_llm) → 비교하지 않음. ⑧ 폴백 비율 대신: **재현은 팀장 끔**"),
        ("K9", "국내 매도세", f"R2 표에 있는 줄은 H1 표와 똑같고, 뒤에 더한 줄(⑥-ii)은 시행일이 모든 재현 창 끝({replay_last_day()}) "
                         "뒤인지 확인(K 칸)"),
        ("K10", "지표 계산 길이", "재현은 R2 처럼 처음부터(운영은 2024-06-01 부터, 차이는 무시할 크기)"),
        ("K11", "빈자리 부족 합계", "트레이너 합계만 비교(K1 뺀 뒤 같아야 함, M3 안)"),
        ("K12", "부동소수점 더하는 순서", "M1·M4 의 허용 오차 안(상대 1e-9, 현금 1e-6). NaN·inf 는 늘 차이"),
        ("K13", "시작 규칙", "기준값이 운영 시작 규칙 하위 클래스라 차이 아님(원래 sim_team 과의 차이는 아래 참고)"),
    ]
    L.append("| # | 차이 | 이번 재현에서 |")
    L.append("|---|---|---|")
    for k, a, b in k_rows:
        L.append(f"| {k} | {a} | {b} |")
    L.append("")
    L.append("## 설명되지 않은 차이 (원인)")
    L.append("")
    any_diff = False
    for n, r in w.items():
        if r.get("stopped"):
            any_diff = True
            L.append(f"- {n}: {r['stopped']['detail']}")
            for x in r["stopped"]["cause"]:
                L.append(f"    - {x}")
            continue
        for m in CHECK_ORDER:
            c = r["checks"].get(m)
            if c is not None and not c["ok"]:
                any_diff = True
                L.append(f"- {n} {m} {M_NAMES.get(m, m)}: {c['detail']}")
                for d in c["diffs"][:15]:
                    L.append(f"    - {d}")
    if not golden["ok"]:
        any_diff = True
        L.append(f"- 자료 받기 골든: {golden['detail']}")
    if res["code_changed"]:
        any_diff = True
        L.append("- 재현 도중 코드 파일·환경이 바뀜 → 이 결과로는 기록하지 않음")
    if not any_diff:
        L.append("- 없음")
    L.append("")
    if entry is not None:
        L.append("## 통과 기록 줄 (replay_pass.json 에 더하는 내용)")
        L.append("")
        L.append("```json")
        L.append(_entry_preview(entry))
        L.append("```")
        L.append("")
    L.append("## 참고 (통과 조건 아님)")
    L.append("")
    for n, r in w.items():
        ro = (r.get("ref") or {}).get("original") or {}
        if ro:
            L.append(f"- {n} 원래 sim_team(S 시가에 바로 전부 지수)과 운영 시작 규칙의 차이(A1): 원래에만 있는 체결 열쇠 "
                     f"{ro.get('fill_keys_only_original')}개, 운영 규칙에만 {ro.get('fill_keys_only_operating')}개, 끝날 팀 평가액 "
                     f"원래 {ro.get('last_value_original'):,.2f} / 운영 {ro.get('last_value_operating'):,.2f}")
        m7 = (r.get("ref") or {}).get("m7") or {}
        ai = (r.get("ref") or {}).get("a0_interest") or {}
        if m7.get("a0_plus_interest") is not None and ai.get("last_value"):
            L.append(f"- {n} 'A0+이자'(보고서 근사) 끝값 {m7['a0_plus_interest']:,.2f} vs R2 A0 이자 켬 {ai['last_value']:,.2f} "
                     f"(차이 {m7['approx_gap_pct']:+.6f}% — 보고서는 이자를 따로 쌓기만 하고 매매에 쓰지 않는 근사라 다를 수 있음)")
    L.append("")
    L.append("※ 재현은 팀장(claude)을 끄고 돈다. 수익률 숫자는 기록용이며 판정에 쓰지 않는다(사전 등록 ③).")
    return "\n".join(L) + "\n"


def _report_path(root, day) -> Path:
    base = h1.h1_path(root, "reports")
    p = base / f"replay-{day}.md"
    i = 2
    while p.exists() or p.with_name(p.stem + "-baseline.json").exists():
        p = base / f"replay-{day}-{i}.md"
        i += 1
    return p


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def finish(res, root, r2_rep=None, *, progress=_say) -> int:
    """결과로 종료 코드를 정하고 파일을 쓴다(검토 5 P-7·P-8).
    통과(모든 창·자료 받기 골든·코드 그대로)면 순서대로:
      1 전역 잠금 아래 보고서(기록할 줄의 내용까지, 상태 '기록 전')와 기준값 결과 replay-<날짜>-baseline.json 을 쓴다
      2 replay_pass.json 에 한 줄(h1.replay_entry → record_replay_pass — 그 안에서 전역 잠금). passed_at = 기록하는 때,
        started_at = 재현 시작 때, baseline_sha256 = 기준값 결과 파일의 sha256
      3 전역 잠금 아래 보고서의 '통과 기록' 줄을 '기록함'으로 채우고, 금리 첫 저장본(없을 때만)을 둔다.
    종료 코드: 0 통과+기록 / 3 고른 창은 같지만 일부 창이라 기록 안 함 / 2 차이 / 4 코드·환경이 바뀜·기록 실패."""
    root = h1._root(root)
    progress("[재현] 4/4 자료 받기 골든 확인 → (통과면) 보고서 → 통과 기록 → 보고서에 '기록함'·금리 첫 저장본")
    golden = data_golden_ok()
    ok = res["passed"] and golden["ok"] and not res["code_changed"]
    day = datetime.now().astimezone().date().isoformat()
    with h1.h1_lock(root):
        rpath = _report_path(root, day)
    bpath = rpath.with_name(rpath.stem + "-baseline.json")
    rel, brel = "/".join(rpath.relative_to(root).parts), "/".join(bpath.relative_to(root).parts)
    has_base = bool(res.get("baseline_file")) and Path(res["baseline_file"]).exists()
    entry, status = None, ""
    if res["code_changed"]:
        status = "남기지 않음 — 재현 도중 코드·환경이 바뀜(같은 코드로 처음부터 다시 돌리세요)"
    elif not ok:
        status = "남기지 않음 — 차이가 있어 통과 아님"
    elif not res["complete"]:
        status = "남기지 않음 — 일부 창만 돌림(W1·W2·W3 를 다 돌려야 기록, 종료 코드 3)"
    else:
        fps = {n: res["windows"][n]["fingerprint"] for n in FINGERPRINT_WINDOWS}
        with contextlib.redirect_stdout(io.StringIO()):          # 자료 받기 골든의 '받기 실패 흉내' 안내 줄은 화면에 내지 않음
            entry = h1.replay_entry(fps, started_at=res["started_at"], passed_at=_now_iso(), report=rel,
                                    baseline=brel if has_base else None, baseline_sha256=res.get("baseline_sha256"),
                                    r2_ref=res["r2_ref"], r2_commit=res["r2_commit"], windows=sorted(res["windows"]))
        if entry["code_hash"] != res["code_hash"] or h1.env_key(entry["env"]) != h1.env_key(res["env"]):
            status = "남기지 않음 — 기록 직전 코드·환경이 재현 때와 다름"
            res["code_changed"] = True
            entry = None
        else:
            status = "기록 전 — 이 보고서를 먼저 쓰고 바로 아래 줄을 replay_pass.json 에 더함(이 줄이 남아 있으면 기록이 실패한 것)"

    def write(text):
        with h1.h1_lock(root):                                 # 보고서·기준값·금리 저장본 = 전역 잠금
            if has_base and not bpath.exists():
                blob = Path(res["baseline_file"]).read_bytes()
                if h1._sha256_bytes(blob) != res.get("baseline_sha256"):
                    raise ReplayEnvError("기준값 결과 파일이 재현 도중 바뀜")
                h1._write_atomic(bpath, blob)
            h1._write_atomic(rpath, text.encode("utf-8"))

    write(render_report(res, golden=golden, record_status=status, entry=entry, baseline_rel=brel if has_base else None))
    progress(f"[재현] 보고서: {rpath}" + (f" · 기준값 결과: {bpath.name}" if has_base else ""))
    recorded = False
    if entry is not None:
        try:
            n = h1.record_replay_pass(entry, root)
        except h1.H1Refused as e:
            write(render_report(res, golden=golden, entry=entry, baseline_rel=brel if has_base else None,
                                record_status=f"기록 실패(종료 코드 {e.code}): {e}"))
            raise ReplayEnvError(f"통과 기록을 쓰지 못함(종료 코드 {e.code}): {e}")
        recorded = True
        write(render_report(res, golden=golden, entry=entry, baseline_rel=brel if has_base else None,
                            record_status=f"기록함 — replay_pass.json {n}번째 줄(passed_at {entry['passed_at']})"))
        copied = []
        if r2_rep is not None:
            with h1.h1_lock(root):
                src = Path(r2_rep) / "data" / "rates"
                for f in sorted(src.glob("*.csv")):
                    dst = h1.h1_path(root, "rates", f.name)
                    if not dst.exists():
                        h1._write_atomic(dst, f.read_bytes())
                        copied.append(f.name)
        if copied:
            progress(f"[재현] 금리 첫 저장본을 rates/ 에 둠: {', '.join(copied)}")
        progress(f"[재현] 통과 — replay_pass.json {n}번째 줄 (종료 코드 0)")
        return EXIT_OK
    if ok and not res["complete"]:
        progress("[재현] 고른 창은 모두 같음 — 그러나 일부 창만 돌려 통과 기록을 남기지 않음 → 관문은 열리지 않음 (종료 코드 3)")
        return EXIT_PARTIAL
    if res["code_changed"]:
        progress(f"[재현] {status} (종료 코드 4)")
        return EXIT_ENV
    progress("[재현] 통과 아님 — 차이 표:")
    for n, r in res["windows"].items():
        if r.get("stopped"):
            progress(f"    {n}: {r['stopped']['detail']}")
            for x in r["stopped"]["cause"][:8]:
                progress(f"        {x}")
            continue
        for m in CHECK_ORDER:
            c = r["checks"].get(m)
            if c is not None and not c["ok"]:
                progress(f"    {n} {m} {M_NAMES.get(m, m)}: {c['detail']}")
                for d in c["diffs"][:5]:
                    progress(f"        - {d}")
    if not golden["ok"]:
        progress(f"    자료 받기 골든: {golden['detail']}")
    return EXIT_DIFF


# ============================ 7. 명령줄 ============================

class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def _parser():
    p = _Parser(prog="h1_replay.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                description="H1 재현(단계 5): R2 연구 시뮬레이터와 새 코드가 같은 매매·숫자를 내는지 비교.",
                epilog="종료 코드\n" + "\n".join(f"  {k:>3}  {v}" for k, v in EXIT_TEXT.items()))
    p.add_argument("--root", default=None, help="통과 기록·보고서를 쓸 H1 폴더(기본: 이 폴더의 state/h1)")
    p.add_argument("--r2-ref", default=R2_REF, help=f"연구 브랜치(기본 {R2_REF}). 커밋 {R2_COMMIT[:12]} 를 가리켜야 함")
    p.add_argument("--windows", default="W1,W2,W3", help="돌릴 창(쉼표로, 기본 W1,W2,W3). 일부만이면 기록 없이 종료 코드 3")
    p.add_argument("--keep-temp", action="store_true", help="통과해도 임시 폴더(풀어 둔 R2·재현 장부·실행 로그)를 남김"
                                                            "(차이·환경 문제면 늘 남김)")
    return p


def cli(argv=None) -> int:
    if sys.version_info < (3, 12):                   # tarfile filter="data" 등(검토 5 P-12) — 맥 venv 는 3.13
        _say(f"[재현] 환경 문제(종료 코드 4): 파이썬 {sys.version.split()[0]} — 3.12 이상(H1 venv 는 3.13, requirements-h1.txt)"
             "으로 돌리세요")
        return EXIT_ENV
    try:
        a = _parser().parse_args(sys.argv[1:] if argv is None else argv)
        groups = [g.strip().upper() for g in a.windows.split(",") if g.strip()]
        if not groups or any(g not in GROUPS for g in groups) or len(set(groups)) != len(groups):
            raise _UsageError(f"--windows 는 {', '.join(GROUPS)} 중에서 쉼표로(받은 값 {a.windows!r})")
        root = Path(a.root) if a.root else Path(h1.H1_DIR)
        try:
            h1._root(root)
        except ValueError as e:
            raise _UsageError(str(e))
    except _UsageError as e:
        _say(f"h1_replay.py: 명령 인자 오류 — {e}  (python h1_replay.py -h)")
        return EXIT_USAGE
    work = Path(tempfile.mkdtemp(prefix="h1-replay-"))
    _say(f"[재현] 임시 폴더 {work} · 기록할 곳 {root}")
    code = EXIT_DIFF
    try:
        res = replay(groups, a.r2_ref, work)
        code = finish(res, root, work / "r2" / R2_DIR)
    except ReplayEnvError as e:
        _say(f"[재현] 환경 문제(종료 코드 4): {e}")
        code = EXIT_ENV
    except KeyboardInterrupt:
        _say("[재현] 사람이 멈춤(Ctrl-C) — 통과 기록 없음 (종료 코드 130)")
        code = EXIT_INTERRUPT
    except OSError as e:
        _say(f"[재현] 환경 문제(종료 코드 4) {type(e).__name__}: {e}")
        code = EXIT_ENV
    except Exception as e:      # noqa: BLE001 — 예상 밖 오류는 통과가 아니다(기록 없음)
        _say(f"[재현] 예상 밖 오류 {type(e).__name__}: {e} — 통과 아님(기록 없음, 종료 코드 2)")
        traceback.print_exc()
        code = EXIT_DIFF
    finally:
        keep = a.keep_temp or code in (EXIT_DIFF, EXIT_ENV)
        if keep:
            _say(f"[재현] 임시 폴더를 남겨 둠(원인 확인용): {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    _say(f"[재현] 끝: 종료 코드 {code} — {EXIT_TEXT.get(code, '?')}")
    return code


if __name__ == "__main__":
    import h1_replay as _me                     # h1.py 와 같은 이유: 모듈이 두 벌이 되지 않게
    sys.exit(_me.cli())
