"""
h1_fake_source.py — H1 실행기(h1.start·h1.run) 시험용 가짜 자료 (인터넷·claude 없음). pytest 가 모으지 않는 도우미.

- FakeSource: h1.DataSource 와 같은 모양(benchmark·fetch·universe·now).
  h1_synth.World 의 원본 시세(국내 정지는 Volume=0 행)를 "지금 시각의 그 시장 날짜 이하"로 자른 뒤,
  운영과 같은 단계(h1.fetched_from_raw = 이름 정리 → main.confirmed_bars,
  대기 자산은 main.confirmed_bars(…, bench_cutoff))를 거쳐 돌려준다.
  그래서 확정 시각 규칙(미국 16:15 ET, 국내 종목 16:00, KS200 22:30 KST)이 운영과 같은 조건으로 걸린다.
- 장면 만들기 손잡이: missing(받기 실패), drop(어떤 날짜 행이 아직 없음 = 늦은 자료), idle_drop·idle_until·idle_from
  (대기 자산 달력 줄어듦·늦음·연도 파일), transform(분할·정정처럼 시세를 바꿈, 지금 시각에 따라).
- run_at(market, t): 운영 시각. 국내 = t 23:05 KST, 미국 = t 다음 평일 07:10 KST (설계 §5.3·§8.2).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import h1
import main
import markets

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def run_at(market, t, hh=None, mm=None):
    """봉 t 를 처리하는 운영 시각(시간대 있음)."""
    d = pd.Timestamp(t)
    if market == "kr":
        return datetime(d.year, d.month, d.day, 23 if hh is None else hh, 5 if mm is None else mm, tzinfo=KST)
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return datetime(nxt.year, nxt.month, nxt.day, 7 if hh is None else hh, 10 if mm is None else mm, tzinfo=KST)


class FakeSource:
    def __init__(self, world, *, universe=None, now=None):
        self.world = world
        self.mk = world.market
        self.m = markets.MARKETS[self.mk]
        self.raw = {c: df.copy() for c, df in world.raw.items()}
        self.idle_raw = world.idle.copy()
        self.clock = now
        self.uni = list(universe if universe is not None else world.universe)
        self.missing = set()          # 받기 실패(None)인 종목
        self.drop = {}                # code → {날짜} 아직 없는 행(늦은 자료)
        self.idle_missing = False
        self.idle_drop = set()        # 대기 자산에서 빠진 날짜
        self.idle_until = None        # 대기 자산을 이 날짜까지만(연도 파일 늦음)
        self.idle_from = None         # 대기 자산을 이 날짜부터만(앞 연도 파일 못 받음)
        self.transform = {}           # code → f(df, now) → df
        self.universe_calls = 0
        self.fetch_calls = Counter()
        self.bench_calls = 0

    # ---- DataSource 모양 ----
    def now(self):
        return self.clock

    def universe(self):
        self.universe_calls += 1
        return list(self.uni)

    name_map = None                   # 설계 Q4: start 때 names() 가 돌려줄 {코드: 이름}(None = 이름 없음)

    def names(self):
        return self.name_map

    def _local_day(self, now):
        return now.astimezone(ZoneInfo(self.m.tz)).date()

    def _cut(self, df, now):
        day = self._local_day(now)
        return df[[x.date() <= day for x in df.index]]

    def benchmark(self, now):
        self.bench_calls += 1
        if self.idle_missing:
            return None
        df = self._cut(self.idle_raw, now)
        keep = [x.date().isoformat() not in self.idle_drop
                and (self.idle_until is None or x.date().isoformat() <= self.idle_until)
                and (self.idle_from is None or x.date().isoformat() >= self.idle_from) for x in df.index]
        df = df[keep]
        if len(df) == 0:
            return None
        cut = self.m.bench_cutoff if self.mk == "kr" else None
        out = main.confirmed_bars(df, now, self.mk, cut)
        return out if len(out) else None

    def fetch(self, code, now):
        self.fetch_calls[code] += 1
        if code in self.missing or code not in self.raw:
            return None
        df = self._cut(self.raw[code], now)
        drop = self.drop.get(code, ())
        if drop:
            df = df[[x.date().isoformat() not in drop for x in df.index]]
        if code in self.transform:
            df = self.transform[code](df.copy(), now)
        return h1.fetched_from_raw(self.mk, df, now)

    # ---- 시험 도우미 ----
    def at(self, t, **kw):
        self.clock = run_at(self.mk, t, **kw)
        return self


def split_after(day, r, tz):
    """day(분할 기준일, 그 시장 시간 tz) 이후에 받으면 지난 시세가 모두 ÷r 로 고쳐져 오는 제공처(소급 수정)."""
    def f(df, now):
        if now.astimezone(tz).date().isoformat() >= day:
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] / r
            df["Volume"] = df["Volume"] * r
        return df
    return f


def file_sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- 재현 통과 기록(단계 4 F-1: files·data_golden_sha256 필수) 시험 도우미 ----
_GOLDEN = {}


def golden_digest():
    """자료 받기 골든 지문(한 번만 계산)."""
    if "d" not in _GOLDEN:
        _GOLDEN["d"] = h1.data_golden_digest()
    return _GOLDEN["d"]


def code_variant(tag=None, file="h1_data.py"):
    """지금 코드의 파일별 sha256 에서 file 하나만 sha256(tag) 로 바꾼 '가짜 코드' → (code_hash, files).
    tag None 이면 지금 코드 그대로. 기본 file = h1_data.py(⑥-i 로 허용되는 자료 받기 고침)."""
    import hashlib
    ch, files = h1.code_hash()
    if tag is None:
        return ch, dict(files)
    files = dict(files)
    files[file] = hashlib.sha256(str(tag).encode("utf-8")).hexdigest()
    return h1.combine_code_hash(files), files


def pass_entry(code=None, env=None, ledger=None, golden=None, tax_free=None, **kw):
    """시험용 재현 통과 줄(h1.replay_entry 와 같은 모양). code = (code_hash, files) 또는 None(지금 코드),
    ledger = 장부 내용 지문 dict(기본 {"W1": "같음"}), golden = 자료 받기 골든 지문(기본 지금 값)."""
    ch, files = code if code is not None else h1.code_hash()
    return {"code_hash": ch, "files": dict(files), "env": dict(env or h1.env_info()),
            "data_golden_sha256": golden or golden_digest(),
            "h1_without_tax_table_sha256": tax_free if tax_free is not None else h1.tax_free_sha(),
            "fingerprint_version": h1.FINGERPRINT_VERSION,
            "ledger_fingerprints": {"W1": "같음"} if ledger is None else ledger, "passed_at": "2026-11-04", **kw}


def record_pass(root, code=None, env=None, **kw):
    """pass_entry 를 h1.record_replay_pass 로 기록. 돌려줌: 기록 줄 수."""
    return h1.record_replay_pass(pass_entry(code, env, **kw), root)


def give_l_evidence(root, market, start_date, at, date=None, code="L7"):
    """restart --reason L 의 근거가 되는 errors.jsonl L 기록 한 줄(그 창 S, 그 시각)을 더한다(시험용, 단계 4 F-4)."""
    import uuid
    h1._append_line(Path(root) / "errors.jsonl", {
        "at": at, "run_id": f"test-{uuid.uuid4().hex[:8]}", "command": "run", "market": market,
        "start_date": start_date, "date": date,
        "problems": [{"level": "L", "code": code, "market": market, "arm": None, "trainer": None, "date": date,
                      "detail": "시험용 L 근거"}], "fingerprint": None})


def tree_sha(root):
    """폴더 안 모든 파일 {상대경로: sha256}."""
    return {str(p.relative_to(root)): file_sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def read_lines(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def drop_days(world, days):
    """합성 세계에서 휴장일을 뺀다(모든 종목·대기 자산·달력). 예: KRX 2026-12-31·2027-01-01 휴장(2b-2 검토 C-18)."""
    gone = {pd.Timestamp(d) for d in days}
    keep = lambda df: df[[x not in gone for x in df.index]]   # noqa: E731
    world.raw = {c: keep(df) for c, df in world.raw.items()}
    world.frames = {c: keep(df) for c, df in world.frames.items()}
    world.idle = keep(world.idle)
    world.dates = [d for d in world.dates if pd.Timestamp(d) not in gone]
    return world
