"""H1 단계 2b-1 — 장부 점검 시험 (설계 docs/h1-forward-design.md §4, §6 T-L). 인터넷·claude 없음.

- 정상 장부(합성 장면 4개: 미국 시나리오 A·폭락(그림자 서킷)·상장폐지 정리, 국내 3일 정지) 여러 날에서 L 오류 0.
- 음성 대조: L1~L23 마다 그 잘못을 일부러 넣은 장부 → 그 코드가 나온다(설계 §4 끝 "(a) 음성 대조").
- check_day: 처리 전 기록을 고침·오늘 체결가가 그날 시가와 다름·정지 목록이 다름 등도 잡는다.
- L24 는 코드 이름만(실제 판단은 2b-2 의 장부 읽기). 장부 모양이 깨져 점검을 끝낼 수 없을 때 L24 로 알리는지만 본다.
"""
import copy
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst      # noqa: E402
import h1           # noqa: E402
import h1_check     # noqa: E402
import h1_synth as hs  # noqa: E402
import main         # noqa: E402

L_REQUIRED = tuple(f"L{i}" for i in range(1, 24))


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("시험이 진짜 claude 를 부르려 했어요")
    monkeypatch.setattr(analyst, "analyze_logged", boom)
    monkeypatch.setattr(analyst, "analyze", boom)


class Base:
    """점검 대상 하나: 장부 6개(JSON 모양) + 달력 + 판정 기록 + 허용 지문 + 그날까지 시세 + HEAD 앞부분 지문."""

    def __init__(self, sc, k=None):
        r = sc.runner
        res = r.results[-1] if k is None else r.results[k]
        self.sc = sc
        self.market = sc.world.market
        self.date = res.date
        self.states = {a: {t: h1.ledger_to_json(st, self.market) for t, st in by.items()}
                       for a, by in res.states.items()}
        self.states = json.loads(json.dumps(self.states, ensure_ascii=False))
        self.calendar = sc.world.calendar(r.S, self.date)
        self.log = r.log
        self.allowed = set(r.allowed)
        self.frames = {c: h1.cut_frame(f, self.date) for c, f in sc.world.frames.items()}
        self.head = r.log.prefix_digest()

    def copy(self):
        return copy.deepcopy(self.states)


def run_all(b, states=None, *, calendar="base", allowed="base", head="base", frames="base", decisions=None):
    states = b.states if states is None else states
    cal = b.calendar if calendar == "base" else calendar
    al = b.allowed if allowed == "base" else allowed
    fr = b.frames if frames == "base" else frames
    hd = b.head if head == "base" else head
    log = b.log if decisions is None else decisions
    probs = []
    for arm in h1.ARMS:
        probs += h1_check.check_ledger(b.market, arm, states[arm], cal, log, al, frames=fr)
    probs += h1_check.check_pair(b.market, states["A0"], states["A1"], log)
    probs += h1_check.check_decisions(b.market, log, hd)
    return probs


def codes(probs):
    return {p.code for p in h1_check.errors(probs)}


@pytest.fixture(scope="module")
def bases(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        a = hs.scenario_a(tmp_path_factory.mktemp("a") / "log.jsonl", upto=7)
        crash = hs.scenario_a(tmp_path_factory.mktemp("c") / "log.jsonl", upto=4,
                              world=hs.world_a(crash={"AAA": ("2026-02-04", 0.55), "BBB": ("2026-02-04", 0.55)}))
        # 국내 3일 정지 (test_h1_engine T-HALT 와 같은 장면, D7 까지 = 000660 보유 중)
        kcodes = ("005930", "000660", "005380")
        D = [hs.World("kr", kcodes).at("2026-02-02", k) for k in range(10)]
        kw = hs.World("kr", kcodes, bases={"005930": 70000, "000660": 150000, "005380": 200000},
                      halts={"005380": D[1:4], "000660": D[5:7]})
        plan_h = lambda D: {"스프린터": {"buy": [("005380", D[0])]}, "파이오니어": {"buy": [("005380", D[0])]},  # noqa: E731
                            "마라토너": {"buy": [("000660", D[0])], "sell": [("000660", D[7])]}}
        halt = hs.scenario(kw, "2026-02-02", plan_h, tmp_path_factory.mktemp("h") / "log.jsonl", upto=7,
                           leader_mode="replay")
        # 상장폐지 정리
        plan_d = lambda D: {"마라토너": {"buy": [("AAA", D[0])]},  # noqa: E731
                            "스프린터": {"buy": [("AAA", D[0]), ("BBB", D[0])], "sell": [("AAA", D[2])]}}
        dl = hs.scenario(hs.world_a(), hs.S_A, plan_d, tmp_path_factory.mktemp("d") / "log.jsonl", upto=2,
                         leader_mode="replay")
        D = dl.D
        P = round(dl.world.close("AAA", D[2]) * 0.4, 4)
        for arm in h1.ARMS:
            for tn in h1.TRAINERS:
                dl.states[arm][tn]["corp_actions"].append(
                    {"kind": "delist", "code": "AAA", "last_date": D[2], "last_close": P, "source": "시험"})
        dl.runner.delist = {"AAA": {"last_date": D[2], "last_close": P}}
        fr = {c: f for c, f in dl.world.frames.items() if c != "AAA"}
        dl.step(D[3], frames=fr)
        dl.step(D[4], frames=fr)
    # 상장폐지 장면도 점검(재현·보고서)에는 지난 체결의 시세가 다 있는 시세를 쓴다(정리 뒤 시세를 안 받는 것은 run 쪽 일)
    return {"a": Base(a), "crash": Base(crash), "halt": Base(halt), "delist": Base(dl)}


# ======================= 정상 장부 → L 0 =======================

@pytest.mark.parametrize("name", ["a", "crash", "halt", "delist"])
def test_정상_장부_여러_날_L_0(bases, name):
    b = bases[name]
    assert len(b.states["A0"]["마라토너"]["days"]) >= 5
    probs = run_all(b)
    assert h1_check.errors(probs) == [], [(p.code, p.arm, p.trainer, p.date, p.detail) for p in probs]
    # 봉마다 run_bar 가 돌린 check_day 도 L 0 이었다(Runner.step 이 단언) — 여기서는 각 봉을 다시 한 번
    sc = b.sc
    for k in range(1, len(sc.runner.results)):
        r0, r1 = sc.runner.results[k - 1], sc.runner.results[k]
        before = r0.states
        if name == "delist" and r1.date == sc.D[3]:   # corp-action(봉 사이에 따로 커밋)이 더한 등록까지가 '처리 전'
            before = hs.roundtrip(r0.states, b.market)
            for arm in h1.ARMS:
                for tn in h1.TRAINERS:
                    before[arm][tn]["corp_actions"] = list(r1.states[arm][tn]["corp_actions"])
        p = h1_check.check_day(b.market, r1.date, before, r1.states,
                               {c: h1.cut_frame(f, r1.date) for c, f in sc.world.frames.items()
                                if not (name == "delist" and c == "AAA" and r1.date > sc.D[2])},   # 실행 때와 같은 시세
                               sc.world.idle_bar(r1.date), sc.world.calendar(sc.runner.S, r1.date),
                               sc.world.halted(r1.date), b.log, b.allowed)
        assert h1_check.errors(p) == [], [(x.code, x.detail) for x in p]


def test_장면이_점검할_거리를_다_가진다(bases):
    a = bases["a"].states
    fills = [f for arm in h1.ARMS for st in a[arm].values() for f in st["fills"]]
    assert {f["purpose"] for f in fills} >= {"start", "order", "sweep"} and any(
        f["purpose"].startswith("fund:") for f in fills)
    skips = {s["kind"] for arm in h1.ARMS for st in a[arm].values() for s in st["skips"]}
    assert skips == {"0주", "현금부족", "팀장hold", "확신도낮음"}
    effects = {e["effect"] for arm in h1.ARMS for st in a[arm].values() for r in st["days"] for e in r["leader"]}
    assert effects >= {"veto", "hold", "low_conv", "ordered"}
    assert any(r["events"] for st in bases["crash"].states["A0"].values() for r in st["days"])
    assert any(r["halted"] for r in bases["halt"].states["A0"]["마라토너"]["days"])
    assert any(f["purpose"] == "delist" for f in bases["delist"].states["A1"]["마라토너"]["fills"])


# ======================= 음성 대조 L1~L23 =======================

def _first(st, **m):
    return next(f for f in st["fills"] if all(f[k] == v for k, v in m.items()))


def m_L1(s, b):
    s["A0"]["마라토너"]["wallet"]["cash"] = -5.0


def m_L2(s, b):
    s["A1"]["스프린터"]["stopped"] = True


def m_L2b(s, b):
    st = s["A0"]["마라토너"]
    code = next(iter(st["positions"]))
    st["positions"][code]["shares"] += 1


def m_L3(s, b):
    f = _first(s["A1"]["마라토너"], kind="idle")
    f["price"] = f["price"] + 0.01


def m_L3b(s, b):                       # 주식 체결가 ≠ 그날 시가 (시세가 있을 때)
    f = _first(s["A0"]["스프린터"], kind="stock")
    f["price"] = f["price"] * 1.001


def m_L4(s, b):                        # 매도 주문이 생긴 날을 하루 앞으로 → 정지가 아닌 날 체결 안 되고 남은 꼴
    st = s["A0"]["스프린터"]
    o = next(o for o in st["orders"] if o["action"] == "매도")
    o["created_on"] = b.sc.D[1]


def m_L4b(s, b):                       # 국내: 정지로 기다린 날 하나에서 정지 표시를 지움
    st = s["A0"]["스프린터"]
    row = next(r for r in st["days"] if "005380" in r["halted"])
    row["halted"] = [c for c in row["halted"] if c != "005380"]


def m_L5(s, b):
    st = s["A0"]["마라토너"]
    code = next(iter(st["positions"]))
    o = {"code": code, "action": "매수", "signal_date": b.date, "reason": "x", "note": None}
    st["pending"].append(o)
    st["orders"].append({"id": h1.order_id(o), "signal_date": b.date, "code": code, "action": "매수", "reason": "x",
                         "origin": "candidate", "created_on": b.date, "status": "pending", "done_date": None,
                         "why": None})


def m_L6(s, b):
    st = s["A0"]["스프린터"]
    f = _first(st, kind="stock", side="buy")
    next(r for r in st["days"] if r["date"] == f["date"])["halted"].append(f["code"])


def m_L7(s, b):
    s["A1"]["파이오니어"]["days"][-1]["value"] += 1.0


def m_L8(s, b):
    s["A0"]["마라토너"]["days"][3]["cash"] += 0.5


def m_L9(s, b):
    f = _first(s["A1"]["스프린터"], kind="stock")
    f["fee"] *= 1.01


def m_L10(s, b):
    st = s["A1"]["마라토너"]
    _first(st, purpose="start")["purpose"] = "sweep"


def m_L10b(s, b):
    s["A0"]["파이오니어"]["wallet"]["holdings"]["SPY"] = {"shares": 1.5, "avg_price": 500.0}


def m_L11(s, b):
    f = next(f for f in s["A1"]["마라토너"]["fills"] if f["purpose"].startswith("fund:"))
    f["qty"] *= 1.001


def m_L11b(s, b):
    f = next(f for f in s["A1"]["마라토너"]["fills"] if f["purpose"].startswith("fund:"))
    f["purpose"] = "fund:ZZZ"


def m_L12(s, b):
    sk = next(x for x in s["A0"]["마라토너"]["skips"] if x["kind"] == "현금부족")
    sk["need"] = sk["avail"] - 1.0


def m_L12b(s, b):
    sk = next(x for x in s["A1"]["파이오니어"]["skips"] if x["kind"] == "0주")
    sk["price"] = 100.0


def m_L13(s, b):
    f = _first(s["A0"]["스프린터"], kind="stock", side="buy")
    f["qty"] += 1


def m_L14(s, b):
    f = _first(s["A0"]["스프린터"], kind="stock")
    f["order_id"] = "2000-01-01|ZZZ|매수"


def m_L14b(s, b):                      # 주문은 filled 인데 체결이 없음
    st = s["A0"]["파이오니어"]
    o = next(o for o in st["orders"] if o["status"] == "skipped")
    o["status"], o["why"] = "filled", None


def m_L15(s, b):
    st = s["A0"]["마라토너"]
    code = next(iter(st["positions"]))
    st["positions"][code]["days_held"] += 1


def m_L15b(s, b):                      # 국내: 정지일도 보유일수로 셈
    st = s["A0"]["마라토너"]
    st["positions"]["000660"]["days_held"] += 2


def m_L16(s, b):
    del s["A0"]["파이오니어"]["days"][2]


def m_L17(s, b):
    row = next(r for r in s["A1"]["스프린터"]["days"] if r["screened"])
    row["screened"] = row["screened"][::-1] + ["ZZZ"]


def m_L17b(s, b):
    row = next(r for r in s["A1"]["마라토너"]["days"] if r["leader"])
    row["leader"][0]["verdict"] = "veto" if row["leader"][0]["verdict"] != "veto" else "buy"


def m_L19(s, b):
    row = next(r for r in s["A0"]["스프린터"]["days"] if any(e["effect"] == "hold" for e in r["leader"]))
    next(e for e in row["leader"] if e["effect"] == "hold")["effect"] = "ordered"


def m_L19b(s, b):                      # 주문 순서를 바꿈(확신도 높은 순이 아님)
    st = s["A0"]["마라토너"]
    d0 = b.sc.D[0]
    i, j = [k for k, o in enumerate(st["orders"]) if o["created_on"] == d0][:2]
    st["orders"][i], st["orders"][j] = st["orders"][j], st["orders"][i]
    row = st["days"][0]
    row["over_slots"] = row["over_slots"]


def m_L20(s, b):
    row = next(r for r in s["A0"]["마라토너"]["days"] if r["events"])
    row["events"] = []


def m_L20b(s, b):
    s["A0"]["마라토너"]["days"][1]["events"] = [{"kind": "shadow_breaker", "why": "가짜", "first": True}]


def m_L21(s, b):
    row = next(r for r in s["A0"]["마라토너"]["days"] if r["marks"])
    code = next(iter(row["marks"]))
    row["marks"][code] = float("nan")


def m_L23(s, b):
    f = _first(s["A1"]["마라토너"], purpose="delist")
    f["price"] = f["price"] * 1.01


def m_L23b(s, b):
    for arm in h1.ARMS:
        s[arm]["스프린터"]["corp_actions"] = []


CASES = [
    ("L1", "a", m_L1), ("L2", "a", m_L2), ("L2", "a", m_L2b), ("L3", "a", m_L3), ("L3", "a", m_L3b),
    ("L4", "a", m_L4), ("L4", "halt", m_L4b), ("L5", "a", m_L5), ("L6", "a", m_L6), ("L7", "a", m_L7),
    ("L8", "a", m_L8), ("L9", "a", m_L9), ("L10", "a", m_L10), ("L10", "a", m_L10b), ("L11", "a", m_L11),
    ("L11", "a", m_L11b), ("L12", "a", m_L12), ("L12", "a", m_L12b), ("L13", "a", m_L13), ("L14", "a", m_L14),
    ("L14", "a", m_L14b), ("L15", "a", m_L15), ("L15", "halt", m_L15b), ("L16", "a", m_L16), ("L17", "a", m_L17),
    ("L17", "a", m_L17b), ("L19", "a", m_L19), ("L19", "a", m_L19b), ("L20", "crash", m_L20),
    ("L20", "a", m_L20b), ("L21", "a", m_L21), ("L23", "delist", m_L23), ("L23", "delist", m_L23b),
]


@pytest.mark.parametrize("code,base,mutate", CASES, ids=[f"{c}-{m.__name__}" for c, _, m in CASES])
def test_음성_대조_그_잘못을_넣으면_그_코드(bases, code, base, mutate):
    b = bases[base]
    s = b.copy()
    mutate(s, b)
    got = codes(run_all(b, s))
    assert code in got, f"{mutate.__name__}: {code} 가 안 나옴 (나온 것 {sorted(got)})"


def test_음성_대조_L16_달력(bases):
    b = bases["a"]
    cal = [d for d in b.calendar if d != b.sc.D[3]]
    assert "L16" in codes(run_all(b, calendar=cal))


def test_음성_대조_L18_판정_기록(bases, tmp_path):
    b = bases["a"]
    p = tmp_path / "log.jsonl"
    p.write_bytes(b.log.path.read_bytes())
    tampered = p.read_bytes().replace(b'"verdict":"veto"', b'"verdict":"buy"', 1)
    assert tampered != p.read_bytes()
    p.write_bytes(tampered)
    assert "L18" in codes(run_all(b, decisions=h1.DecisionLog(p)))
    p.write_bytes(b"\n".join(b.log.path.read_bytes().split(b"\n")[:3]) + b"\n")      # 줄이 사라짐
    assert "L18" in codes(run_all(b, decisions=h1.DecisionLog(p)))


def test_음성_대조_L22_코드_환경_종목군(bases):
    b = bases["a"]
    assert "L22" in codes(run_all(b, allowed={("다른 코드", h1.env_key({"python": "3.x-test"}))}))
    assert "L22" in codes(run_all(b, allowed={("h-test", h1.env_key({"python": "다른 버전"}))}))
    assert codes(run_all(b, allowed=None)) == set()                    # 허용 목록을 안 주면 그 부분은 안 봄
    sc = b.sc
    r0, r1 = sc.runner.results[-2], sc.runner.results[-1]
    p = h1_check.check_day("us", r1.date, r0.states, r1.states, b.frames, sc.world.idle_bar(r1.date), b.calendar,
                           frozenset(), b.log, b.allowed, universe_sha256="aaa", meta_universe_sha256="bbb")
    assert "L22" in codes(p)


def test_음성_대조_전부_덮음():
    covered = {c for c, _, _ in CASES} | {"L16", "L18", "L22"}
    assert covered >= set(L_REQUIRED), sorted(set(L_REQUIRED) - covered)
    assert h1_check.L_CODES == tuple(f"L{i}" for i in range(1, 25))


def test_L24_장부_모양이_깨지면(bases):
    s = bases["a"].copy()
    del s["A0"]["마라토너"]["fills"]
    assert "L24" in codes(run_all(bases["a"], s))


# ======================= check_day (처리 전후) =======================

def _day(b, mutate_after=None, *, frames="base", halted=None, idle=None):
    sc = b.sc
    r0, r1 = sc.runner.results[-2], sc.runner.results[-1]
    after = hs.roundtrip(r1.states, b.market)
    if mutate_after:
        mutate_after(after)
    fr = {c: h1.cut_frame(f, r1.date) for c, f in sc.world.frames.items()} if frames == "base" else frames
    return h1_check.check_day(b.market, r1.date, r0.states, after, fr, idle or sc.world.idle_bar(r1.date),
                              b.calendar, sc.world.halted(r1.date) if halted is None else halted, b.log, b.allowed)


@pytest.fixture(scope="module")
def b_day(bases):
    """체결이 있는 날로 끝나는 장면: 시나리오 A 를 D3(매도 1·매수 2) 까지로 자른 것."""
    sc = bases["a"].sc
    b = Base(sc, k=3)
    sub = type("SC", (), {})()
    sub.world, sub.D = sc.world, sc.D
    sub.runner = type("R", (), {"results": sc.runner.results[:4], "S": sc.runner.S, "log": sc.runner.log,
                                "allowed": sc.runner.allowed})()
    b.sc = sub
    return b


def test_check_day_정상(b_day):
    assert h1_check.errors(_day(b_day)) == []


def test_check_day_지난_체결_고침_L8(b_day):
    def mut(a):
        a["A0"]["마라토너"]["fills"][0]["cash_before"] += 0.0       # 같은 값 → 문제 없음
        a["A0"]["스프린터"]["fills"][0]["fee"] += 1e-3
    assert "L8" in codes(_day(b_day, mut))


def test_check_day_오늘_하루_기록_없음_L16(b_day):
    def mut(a):
        a["A1"]["파이오니어"]["days"].pop()
    assert "L16" in codes(_day(b_day, mut))


def test_check_day_오늘_체결가_시세와_다름_L3_행_없음_L6(b_day):
    t = b_day.date
    fr = {c: h1.cut_frame(f, t) for c, f in b_day.sc.world.frames.items()}
    bad = dict(fr)
    bad["DDD"] = fr["DDD"].copy()
    bad["DDD"].loc[bad["DDD"].index[-1], "Open"] += 0.5
    assert "L3" in codes(_day(b_day, frames=bad))
    gone = dict(fr)
    gone["DDD"] = fr["DDD"].iloc[:-1]
    assert "L6" in codes(_day(b_day, frames=gone))


def test_check_day_정지_목록_다름_L6_지수_봉_다름_L3(b_day):
    assert "L6" in codes(_day(b_day, halted=frozenset({"ZZZ"})))
    bar = b_day.sc.world.idle_bar(b_day.date)
    assert "L3" in codes(_day(b_day, idle=h1.IdleBar(bar.code, bar.date, bar.open + 1, bar.close)))


def test_check_day_전날_대기가_아니던_주문의_체결_L14(b_day):
    def mut(a):
        st = a["A0"]["스프린터"]
        f = next(f for f in st["fills"] if f["date"] == b_day.date and f["kind"] == "stock")
        o = next(o for o in st["orders"] if o["id"] == f["order_id"])
        o["created_on"] = b_day.date
    assert "L14" in codes(_day(b_day, mut))


def test_Problem_모양():
    p = h1_check.Problem("L", "L1", "us", "A0", "마라토너", "2026-02-02", "x")
    assert h1_check.errors([p, h1_check.Problem("W", "W1", "us", None, None, None, "y")]) == [p]
    with pytest.raises(Exception):
        p.code = "L2"
    assert math.isclose(h1_check.EPS_CASH, 1e-6) and math.isclose(h1_check.EPS_REL, 1e-9)


def test_판정_기록_없이도_거짓_양성_없음(bases):
    """보고서가 판정 기록 없이 돌려도(decisions=None) 정상 장부는 L 0."""
    b = bases["a"]
    probs = []
    for arm in h1.ARMS:
        probs += h1_check.check_ledger(b.market, arm, b.states[arm], b.calendar, None, None)
    probs += h1_check.check_pair(b.market, b.states["A0"], b.states["A1"], None)
    assert h1_check.errors(probs) == [], [(p.code, p.detail) for p in probs]


# ======================= 2b-1 독립 검토(docs/h1-review-2b1.md) 반영: B-1·B-6·B-7 점검 시험 =======================
FEE, SLIP = 0.001, 0.0005


def all_problems(market, states, calendar=None, log=None, allowed=None, frames=None):
    p = []
    for arm in h1.ARMS:
        p += h1_check.check_ledger(market, arm, states[arm], calendar, log, allowed, frames=frames)
    p += h1_check.check_pair(market, states["A0"], states["A1"], log)
    return p


def lcodes(problems):
    return {p.code for p in h1_check.errors(problems)}


def jcopy(states, market="us"):
    return json.loads(json.dumps({a: {t: h1.ledger_to_json(st, market) for t, st in by.items()}
                                  for a, by in states.items()}, ensure_ascii=False))


def register_delist(states, code, last_date, last_close):
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            states[arm][tn]["corp_actions"].append({"kind": "delist", "code": code, "last_date": last_date,
                                                    "last_close": last_close, "source": "시험", "at": "시험"})


@pytest.fixture(scope="module")
def sc_a5(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        return hs.scenario_a(tmp_path_factory.mktemp("a5") / "log.jsonl", upto=5)


# ======================= B-1 한쪽만 보유한 상장폐지 =======================

def _plan_one_side(D):
    return {"마라토너": {"buy": [("AAA", D[0]), ("BBB", D[0]), ("CCC", D[1])]}}


@pytest.fixture(scope="module")
def one_side(tmp_path_factory):
    """지수가 D1 종가부터 반토막 → D2 시가에 A0 마라토너는 CCC 를 사고 A1 은 '현금 부족' 보류.
    CCC 를 D2 마지막 거래일로 상장폐지 등록 → D3 에 A0 만 정리한다(둘 다 규칙대로)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        w = hs.world_a(idle_crash=("2026-02-03", 0.5))
        sc = hs.scenario(w, hs.S_A, _plan_one_side, tmp_path_factory.mktemp("os") / "log.jsonl", upto=2,
                         leader_mode="replay")
        D = sc.D
        assert "CCC" in sc.states["A0"]["마라토너"]["positions"] and "CCC" not in sc.states["A1"]["마라토너"]["positions"]
        P = round(w.close("CCC", D[2]) * 0.7, 4)
        register_delist(sc.states, "CCC", D[2], P)
        frames = {c: f for c, f in w.frames.items() if c != "CCC"}
        sc.step(D[3], frames=frames)
        sc.step(D[4], frames=frames)
    return sc, P


def test_B1_한쪽만_보유한_상장폐지는_정상(one_side):
    sc, P = one_side
    D = sc.D
    a0, a1 = sc.states["A0"]["마라토너"], sc.states["A1"]["마라토너"]
    assert [(f["code"], f["date"], f["price"]) for f in a0["fills"] if f["purpose"] == "delist"] == [("CCC", D[3], P)]
    assert [f for f in a1["fills"] if f["purpose"] == "delist"] == []
    assert lcodes(all_problems("us", sc.states, sc.world.calendar(hs.S_A, D[4]), sc.runner.log)) == set()


def test_B1_가진_장부의_정리_누락은_L23(one_side):
    sc, _ = one_side
    s = jcopy(sc.states)
    st = s["A0"]["마라토너"]
    st["fills"] = [f for f in st["fills"] if f["purpose"] != "delist"]
    assert "L23" in lcodes(all_problems("us", s, None, sc.runner.log))


def test_B1_두_장부의_등록이_다르면_짝_점검_L23(one_side):
    """A1 의 등록 last_date 만 하루 앞당김 → A1 혼자 보면 규칙대로(정리할 보유 없음)지만 두 장부의 '첫 처리 봉'이 다름."""
    sc, _ = one_side
    s = jcopy(sc.states)
    for ca in s["A1"]["마라토너"]["corp_actions"]:
        ca["last_date"] = sc.D[1]
    alone = h1_check.check_ledger("us", "A1", s["A1"], None, sc.runner.log)
    assert lcodes(alone) == set()
    pair = h1_check.check_pair("us", s["A0"], s["A1"], sc.runner.log)
    assert [p.code for p in h1_check.errors(pair)] == ["L23"]


def test_B1_안_가진_장부에_정리_체결이_있으면_L23(one_side):
    sc, _ = one_side
    s = jcopy(sc.states)
    f = next(f for f in s["A0"]["마라토너"]["fills"] if f["purpose"] == "delist")
    s["A1"]["마라토너"]["fills"].append(dict(f))
    assert "L23" in lcodes(h1_check.check_ledger("us", "A1", s["A1"], None, sc.runner.log))


def test_B1_첫_처리_봉에_정리_대신_다른_매도면_L23(one_side):
    """들고 있던 장부가 등록 뒤 첫 처리 봉에 '상장폐지 정리'가 아닌 다른 체결로 판 경우: 보유는 남지 않지만 정리 누락(L23)."""
    sc, _ = one_side
    s = jcopy(sc.states)
    f = next(f for f in s["A0"]["마라토너"]["fills"] if f["purpose"] == "delist")
    f["purpose"] = "order"
    got = h1_check.errors(h1_check.check_ledger("us", "A0", s["A0"], None, sc.runner.log))
    assert any(p.code == "L23" and "정리 체결이 없음" in p.detail for p in got)


# B-6

def _boundary_world(rel):
    """파이오니어 상한을 100% 로 둔 장면에서 FFF 1주 필요 금액이 A1 의 'S+1 가능 금액 × (1 − rel)' 이 되게 시가를 고른다."""
    w = hs.world_a()
    d1 = w.at(hs.S_A, 1)
    q = w.idle_bar(d1).open
    unit = q * (1 + SLIP) * (1 + FEE)
    u0 = 10000.0 / unit * (1 - 1e-12)
    e0 = q * (1 + SLIP)
    cash1 = 10000.0 - (e0 * u0 + e0 * u0 * FEE)
    avail = cash1 + u0 * (q * (1 - SLIP) - q * (1 - SLIP) * FEE)
    target = avail * (1 - rel)

    def need(p):
        n = h1.shares_within_cap(10000.0, 1.0, p, FEE, SLIP)
        e = p * (1 + SLIP)
        return n, e * n + e * n * FEE
    lo, hi = 9000.0, 9999.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if need(mid)[1] < target else (lo, mid)
    w.frames["FFF"].loc[pd.Timestamp(d1), "Open"] = hi
    n, nd = need(hi)
    assert n == 1
    return w, avail, nd


@pytest.mark.parametrize("rel,skipped", [(0.5e-9, True), (1.5e-9, False)])
def test_B6_경계_보류_need_약_avail_1빼기_1e9(monkeypatch, tmp_path, rel, skipped):
    monkeypatch.setitem(main.CONFIG["종목상한"], "파이오니어", 1.0)
    w, avail, need = _boundary_world(rel)
    assert (need > avail * (1 - 1e-9)) == skipped and need <= avail
    plan = lambda D: {"파이오니어": {"buy": [("FFF", D[0])]}}       # noqa: E731
    sc = hs.scenario(w, hs.S_A, plan, tmp_path / "log.jsonl", upto=2, leader_mode="replay")
    a1 = sc.states["A1"]["파이오니어"]
    a0 = sc.states["A0"]["파이오니어"]
    assert "FFF" in a0["positions"]                                       # A0 는 현금으로 산다
    if skipped:
        sk = [s for s in a1["skips"] if s["kind"] == "현금부족"]
        assert [s["code"] for s in sk] == ["FFF"] and sk[0]["need"] == need and sk[0]["avail"] == avail
        assert not [f for f in a1["fills"] if f["purpose"].startswith("fund:")]
    else:
        assert "FFF" in a1["positions"]
    probs = all_problems("us", sc.states, sc.world.calendar(hs.S_A, sc.D[2]), sc.runner.log)
    assert h1_check.errors(probs) == [], [(p.code, p.detail) for p in probs]


def test_B6_다시_센_가능_금액과_다른_기록은_L12(tmp_path, monkeypatch):
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=4)
    s = jcopy(sc.states)
    sk = next(x for x in s["A1"]["마라토너"]["skips"] if x["kind"] == "현금부족")
    sk["avail"] = sk["avail"] - 100.0                    # 기록만 보면 여전히 need > avail 이라 예전 L12 는 못 잡음
    got = h1_check.check_ledger("us", "A1", s["A1"], None, sc.runner.log)
    assert any(p.code == "L12" and "다시 센" in p.detail for p in got)


def test_B6_매수가_매도보다_먼저면_L4(tmp_path):
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=3)
    D3 = sc.D[3]
    s = jcopy(sc.states)
    st = s["A0"]["스프린터"]
    today = [f for f in st["fills"] if f["date"] == D3]
    assert [(f["side"]) for f in today] == ["sell", "buy", "buy"]
    rest = [f for f in st["fills"] if f["date"] != D3]
    st["fills"] = rest + [today[1], today[0], today[2]]
    assert "L4" in lcodes(h1_check.check_ledger("us", "A0", s["A0"], None, sc.runner.log))


# B-7

def test_B7_두_장부를_똑같이_틀린_판정은_장부_점검이_L17(sc_a5):
    s = jcopy(sc_a5.states)
    for arm in h1.ARMS:
        row = next(r for r in s[arm]["마라토너"]["days"] if r["leader"])
        row["leader"][0]["verdict"] = "veto" if row["leader"][0]["verdict"] != "veto" else "buy"
    assert not h1_check.errors(h1_check.check_pair("us", s["A0"], s["A1"], sc_a5.runner.log))   # 짝은 같다
    assert "L17" in lcodes(h1_check.check_ledger("us", "A0", s["A0"], None, sc_a5.runner.log))


def test_B7_first_만_틀린_그림자_서킷은_L20(tmp_path):
    w = hs.world_a(crash={"AAA": ("2026-02-04", 0.55), "BBB": ("2026-02-04", 0.55)})
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=4, world=w)
    s = jcopy(sc.states)
    st = s["A0"]["마라토너"]
    evs = [r["events"][0] for r in st["days"] if r["events"]]
    assert len(evs) >= 2 and evs[0]["first"] is True
    evs[0]["first"] = False
    assert lcodes(h1_check.check_ledger("us", "A0", {"마라토너": st}, None, sc.runner.log)) == {"L20"}
    evs[0]["first"], evs[1]["first"] = True, True
    assert lcodes(h1_check.check_ledger("us", "A0", {"마라토너": st}, None, sc.runner.log)) == {"L20"}
