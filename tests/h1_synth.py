"""
h1_synth.py — H1 엔진 시험용 합성 시장 (인터넷·claude 없음). 시험 파일이 아니라 도우미라 pytest 가 모으지 않는다.

- make_frame: 정해진 씨앗으로 만든 일봉(Open·High·Low·Close·Volume + Code 칸). 시가와 종가를 일부러 다르게.
  Code 칸은 가짜 브레인이 "어느 종목인지" 알게 하려는 것(진짜 브레인은 이 칸을 쓰지 않음).
- World: 종목들 + 대기 자산(SPY/KS200) + 국내 거래정지(원본 Volume=0 → 확정 시세에서 빠짐, halted 로 따로 앎) + 폭락.
- fake_brains(plan): 정해진 (종목, 날짜)에만 매수/매도 신호를 내는 가짜 브레인(트레이너 3명).
- FakeAsk: analyst.analyze_logged 대신 넣는 가짜 팀장(호출을 세고, 정해진 답을 냄).
- Runner: h1.new_ledgers → 봉마다 h1.run_bar → 저장·읽기(JSON 왕복)로 장부를 이어 간다.
"""
from __future__ import annotations

import contextlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import h1

ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")
TRAINERS = h1.TRAINERS


def make_frame(seed, base, dates, kr=False, code=None):
    rng = np.random.default_rng(seed)
    n = len(dates)
    ret = rng.integers(-150, 161, n)
    gap = rng.integers(-60, 61, n)
    vol = rng.integers(1_000_000, 3_000_001, n)
    rows, prev = [], float(base)
    for i in range(n):
        c = prev * (1 + int(ret[i]) / 10000)
        o = prev * (1 + int(gap[i]) / 10000)
        if kr:
            c, o = float(round(c)), float(round(o))
        else:
            c, o = round(c, 4), round(o, 4)
        rows.append((o, max(o, c) * 1.01, min(o, c) * 0.99, c, float(vol[i])))
        prev = c
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex(dates))
    df["Code"] = code
    return df


class World:
    def __init__(self, market="us", codes=("AAA", "BBB"), *, start="2025-06-02", end="2026-04-30", bases=None,
                 halts=None, crash=None, idle_base=500.0, seed0=100, idle_crash=None):
        self.market = market
        kr = market == "kr"
        self.dates = [d.date().isoformat() for d in pd.bdate_range(start, end)]
        self.universe = list(codes)
        self.raw, self.frames, self.halt_dates = {}, {}, {}
        bases = bases or {}
        for i, code in enumerate(codes):
            df = make_frame(seed0 + i, bases.get(code, 50.0 + 10 * i) if not kr else bases.get(code, 50_000 + 7_000 * i),
                            self.dates, kr, code)
            if crash and code in crash:            # 그날 종가부터 mult 배 (그 뒤 시세도 같이 내려감)
                day, mult = crash[code]
                ts = pd.Timestamp(day)
                df.loc[ts, "Close"] = df.loc[ts, "Close"] * mult
                after = df.index > ts
                for col in ("Open", "High", "Low", "Close"):
                    df.loc[after, col] = df.loc[after, col] * mult
            for day in (halts or {}).get(code, ()):
                ts = pd.Timestamp(day)
                prev_close = float(df["Close"].iloc[df.index.get_loc(ts) - 1])
                df.loc[ts, ["Open", "High", "Low"]] = 0.0
                df.loc[ts, "Close"] = prev_close
                df.loc[ts, "Volume"] = 0.0
            self.raw[code] = df
            self.frames[code] = df[df["Volume"] != 0] if kr else df
            self.halt_dates[code] = {d.date().isoformat() for d in df.index[df["Volume"] == 0]}
        self.idle_code = h1.idle_code(market)
        self.idle = make_frame(9, idle_base if not kr else 400.0, self.dates, False, self.idle_code)
        if idle_crash:                              # 대기 자산(지수)이 그날 종가부터 mult 배
            day, mult = idle_crash
            ts = pd.Timestamp(day)
            self.idle.loc[ts, "Close"] = self.idle.loc[ts, "Close"] * mult
            after = self.idle.index > ts
            for col in ("Open", "High", "Low", "Close"):
                self.idle.loc[after, col] = self.idle.loc[after, col] * mult

    def idle_bar(self, t):
        row = self.idle.loc[pd.Timestamp(t)]
        return h1.IdleBar(self.idle_code, t, float(row["Open"]), float(row["Close"]))

    def halted(self, t):
        return frozenset(c for c in self.universe if t in self.halt_dates[c])

    def prev(self, t):
        return self.dates[self.dates.index(t) - 1]

    def at(self, t, k):
        return self.dates[self.dates.index(t) + k]

    def calendar(self, S, t):
        return self.dates[self.dates.index(S) - 1:self.dates.index(t) + 1]

    def open(self, code, t):
        return float(self.frames[code].loc[pd.Timestamp(t), "Open"])

    def close(self, code, t):
        return float(self.frames[code].loc[pd.Timestamp(t), "Close"])


def fake_brains(plan):
    """plan = {트레이너: {"buy": [(종목, 날짜), …], "sell": [(종목, 날짜), …]}}."""
    out = {}
    for tname in TRAINERS:
        p = plan.get(tname, {})
        buys, sells = frozenset(p.get("buy", ())), frozenset(p.get("sell", ()))

        class FakeBrain:
            _buys, _sells, _name = buys, sells, tname

            def add_indicators(self, df):
                return df.copy()

            def decide(self, df, position):
                code = df["Code"].iloc[-1]
                d = df.index[-1].date().isoformat()
                if position is None and (code, d) in self._buys:
                    return "매수", f"가짜 매수 신호 {code} ({self._name}) — 사유 글은 14자보다 길게 그대로 남아야 함"
                if position is not None and (code, d) in self._sells:
                    return "매도", f"가짜 매도 신호 {code} ({self._name}) — 사유 글은 14자보다 길게 그대로 남아야 함"
                return "관망", "가짜 관망"

        FakeBrain.__name__ = f"Fake_{tname}"
        out[tname] = FakeBrain
    return out


class FakeAsk:
    """analyst.analyze_logged 자리. answers = {종목: (verdict, conviction) 또는 None(답에서 빠짐)} 기본 ("buy", 0.8).
    status 를 주면 그 상태로 폴백(결과 None). per_call 이 있으면 호출 번호마다 다른 답 함수."""

    def __init__(self, answers=None, status="ok", per_call=None, clock_after=None):
        self.answers = answers or {}
        self.status = status
        self.per_call = per_call
        self.calls = []
        self.clock_after = clock_after

    def __call__(self, trainer, candidates, timeout=None, now=None, cli_version=None):
        codes = [c["code"] for c in candidates]
        self.calls.append((trainer, codes))
        if self.clock_after is not None:
            self.clock_after()
        meta = {"status": self.status, "asked_at": now().isoformat(timespec="seconds") if now else None,
                "elapsed_s": 1.5, "returncode": 0 if self.status == "ok" else None, "model": None,
                "cli_version": cli_version}
        if self.status != "ok":
            return None, meta
        out = {}
        for code in codes:
            ans = self.per_call(len(self.calls), code) if self.per_call else self.answers.get(code, ("buy", 0.8))
            if ans is None:
                continue
            out[code] = {"code": code, "verdict": ans[0], "conviction": ans[1], "note": f"가짜 팀장 메모 {code}"}
        return out, meta


@contextlib.contextmanager
def brains_patched(brains):
    """team.BRAINS 와 screener.BRAINS 를 둘 다 가짜로 바꿨다가 끝나면 되돌린다(재현 W3 와 같은 방식)."""
    import screener
    import team
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(team, "BRAINS", brains)
        mp.setattr(screener, "BRAINS", brains)
        yield brains


def evening(market, t):
    """봉 t 를 처리하는 '다음 장 시작 전' 시각(그날 저녁, 그 시장 시간)."""
    d = pd.Timestamp(t)
    tz = ET if market == "us" else KST
    return datetime(d.year, d.month, d.day, 23, 0, tzinfo=tz)


def roundtrip(states, market):
    """저장 → 읽기 (JSON 왕복)."""
    out = {}
    for arm, by in states.items():
        out[arm] = {}
        for tname, st in by.items():
            blob = json.dumps(h1.ledger_to_json(st, market), ensure_ascii=False, allow_nan=False, indent=1)
            out[arm][tname] = h1.ledger_from_json(json.loads(blob), market, arm, tname)
    return out


class Runner:
    def __init__(self, world, S, log_path, *, leader_mode="replay", ask=None, clock=None, code_hash="h-test",
                 env=None, brains=None):
        self.world, self.S = world, S
        self.market = world.market
        self.leader_mode, self.ask, self.brains = leader_mode, ask, brains
        self.clock = clock
        self.code_hash, self.env = code_hash, dict(env or {"python": "3.x-test"})
        self.allowed = {(self.code_hash, h1.env_key(self.env))}
        self.states = h1.new_ledgers(self.market, S, code_hash=code_hash, env=self.env)
        self.log = h1.DecisionLog(log_path)
        self.results = []
        self.delist = None          # 상장폐지 정보는 장부 corp_actions 에서(2b-1 검토 B-4). 주면 같은지 확인만

    def bar(self, t, *, frames=None, states=None, idle=None, **kw):
        w = self.world
        clock = self.clock or (lambda: evening(self.market, t))
        args = dict(decisions=self.log, leader_mode=self.leader_mode, halted=w.halted(t), delist=self.delist,
                    prev_cal_date=w.prev(t), calendar=w.calendar(self.S, t), now=clock, ask=self.ask,
                    cli_version="9.9.9 (가짜)", code_hash=self.code_hash, env=self.env, allowed=self.allowed,
                    brains=self.brains)
        args.update(kw)
        return h1.run_bar(self.market, t, self.states if states is None else states,
                          w.frames if frames is None else frames, w.universe,
                          w.idle_bar(t) if idle is None else idle, **args)

    def step(self, t, **kw):
        res = self.bar(t, **kw)
        assert res.ok, "\n".join(f"{p.code} {p.arm}/{p.trainer} {p.date}: {p.detail}" for p in res.errors)
        self.results.append(res)
        self.states = roundtrip(res.states, self.market)
        return res

    def run_to(self, t_end):
        t = self.S if not self.results else self.world.at(self.results[-1].date, 1)
        while t <= t_end:
            self.step(t)
            t = self.world.at(t, 1)
        return self.states


# ============================ 시나리오 A (미국, 여러 가지를 한 번에 지나는 장면) ============================
# S=2026-02-02. D[k] = S 뒤 k번째 거래일.
#  마라토너: D0 AAA·BBB 매수 신호 → D1 체결(A1 은 첫 전부 지수 → fund 지수 매도 → 매수) / D1 CCC(buy)·HHH(" VETO")
#            D2 DDD → D3 '현금 부족' 보류(30% × 4) / D3 AAA 매도 신호 → D4 매도(A1 쓸어 담기) / D4 GGG → D5 매수
#  스프린터: D0 AAA·BBB·CCC → D1 3개 매수 / D1 III(확신도 0.3 → 보류)·JJJ("Hold" → 보류)
#            D2 AAA 매도 + DDD·EEE 매수 신호 → D3 매도 1·매수 2(A1: 매도 대금 먼저, 모자란 만큼만 지수 매도)
#  파이오니어: D1 FFF(1주 $2,000 > 상한 $1,500 → D2 0주 보류) / D2 GGG → D3 매수
CODES_A = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ")
S_A = "2026-02-02"
ASK_A = {"HHH": (" VETO", 0.9), "III": ("buy", 0.3), "JJJ": ("Hold", 0.7)}


def world_a(**kw):
    return World("us", CODES_A, bases={"FFF": 2000.0}, **kw)


def plan_a(D):
    return {
        "마라토너": {"buy": [("AAA", D[0]), ("BBB", D[0]), ("CCC", D[1]), ("HHH", D[1]), ("DDD", D[2]), ("GGG", D[4])],
                 "sell": [("AAA", D[3])]},
        "스프린터": {"buy": [("AAA", D[0]), ("BBB", D[0]), ("CCC", D[0]), ("III", D[1]), ("JJJ", D[1]),
                         ("DDD", D[2]), ("EEE", D[2])],
                 "sell": [("AAA", D[2])]},
        "파이오니어": {"buy": [("FFF", D[1]), ("GGG", D[2])]},
    }


class Scenario:
    def __init__(self, world, runner, D, brains, ask):
        self.world, self.runner, self.D, self.brains, self.ask = world, runner, D, brains, ask

    @property
    def states(self):
        return self.runner.states

    def step(self, t, **kw):
        with brains_patched(self.brains):
            return self.runner.step(t, **kw)

    def bar(self, t, **kw):
        with brains_patched(self.brains):
            return self.runner.bar(t, **kw)


def scenario(world, S, plan_fn, log_path, *, upto, leader_mode="llm", ask=None, n_days=12, delist_at=None):
    D = [world.at(S, k) for k in range(n_days)]
    brains = fake_brains(plan_fn(D))
    r = Runner(world, S, log_path, leader_mode=leader_mode, ask=ask, brains=brains)
    sc = Scenario(world, r, D, brains, ask)
    for k in range(upto + 1):
        sc.step(D[k])
    return sc


def scenario_a(log_path, *, upto=7, leader_mode="llm", ask=None, world=None):
    ask = FakeAsk(ASK_A) if ask is None and leader_mode == "llm" else ask
    return scenario(world or world_a(), S_A, plan_a, log_path, upto=upto, leader_mode=leader_mode, ask=ask)
