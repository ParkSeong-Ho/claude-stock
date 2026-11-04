"""H1 단계 2b-1 독립 검토(docs/h1-review-2b1.md) B-1~B-10 고침 시험. 인터넷·claude 없음.

- B-1  (점검 시험은 tests/test_h1_check.py — 검토 돌연변이 스크립트의 시험 목록에 있게)
- B-2  분할 apply_split: 적용 뒤 여러 봉 L 0, 분할을 틀리게 적용(한 장부만·r 틀림·기록 한쪽만)이면 L
- B-3  엔진 안 L 은 Problem 으로(봉 처리 끝까지·지문 있음), 끝까지 못 가는 L 예외는 번호·지문, 사전 조건은 L 아님
- B-4  상장폐지 정보는 corp_actions 하나, last_date ≥ t 등록은 시세 필요(D2)
- B-5  모르는 판정 글자 → bad_verdict 폴백
- B-6  (tests/test_h1_check.py) L12 다시 세기·같은 시가 순서 L4·경계 보류
- B-7  T-F7, T-LATEDATA, 대기 종목 시가 None → D3 (L17·L20 음성 대조는 tests/test_h1_check.py)
- B-8  DecisionLog(read_only=True) 는 파일을 자르지 않음
- B-9  엄격 읽기: NaN·Infinity·항목 모양
- B-10 S 에서도 prev_cal_date 사전 조건
"""
import copy
import json
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
import screener     # noqa: E402


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("시험이 진짜 claude 를 부르려 했어요")
    monkeypatch.setattr(analyst, "analyze_logged", boom)
    monkeypatch.setattr(analyst, "analyze", boom)
    monkeypatch.setattr(analyst, "claude_cli_version", boom)


def all_problems(market, states, calendar=None, log=None, allowed=None, frames=None):
    p = []
    for arm in h1.ARMS:
        p += h1_check.check_ledger(market, arm, states[arm], calendar, log, allowed, frames=frames)
    p += h1_check.check_pair(market, states["A0"], states["A1"], log)
    return p


def lcodes(problems):
    return {p.code for p in h1_check.errors(problems)}


def jcopy(states, market="us"):
    """메모리 장부 → JSON 모양 깊은 사본(점검용)."""
    return json.loads(json.dumps({a: {t: h1.ledger_to_json(st, market) for t, st in by.items()}
                                  for a, by in states.items()}, ensure_ascii=False))


def register_delist(states, code, last_date, last_close):
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            states[arm][tn]["corp_actions"].append({"kind": "delist", "code": code, "last_date": last_date,
                                                    "last_close": last_close, "source": "시험", "at": "시험"})


# ======================= B-2 분할 =======================

def _plan_split(D):
    return {"마라토너": {"buy": [("AAA", D[0]), ("BBB", D[0])], "sell": [("BBB", D[4])]},
            "스프린터": {"buy": [("BBB", D[0])]}}


def _adjusted(world, code, r):
    """제공처가 분할을 소급 반영한 시세(모든 가격 ÷ r, 거래량 × r)."""
    out = dict(world.frames)
    g = world.frames[code].copy()
    for col in ("Open", "High", "Low", "Close"):
        g[col] = g[col] / r
    g["Volume"] = g["Volume"] * r
    out[code] = g
    return out


@pytest.fixture(scope="module")
def split_sc(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        w = hs.world_a()
        sc = hs.scenario(w, hs.S_A, _plan_split, tmp_path_factory.mktemp("sp") / "log.jsonl", upto=2,
                         leader_mode="replay")
        before = sc.runner.states
        frozen = json.dumps(jcopy(before), sort_keys=True)
        after = h1.apply_split(before, "BBB", 2, sc.D[3], "https://예시/공시", "2026-02-04T23:30:00+09:00")
        assert json.dumps(jcopy(before), sort_keys=True) == frozen          # 입력은 그대로
        sc.runner.states = hs.roundtrip(after, "us")
        adj = _adjusted(w, "BBB", 2)
        for k in range(3, 7):
            sc.step(sc.D[k], frames=adj)
    return sc, before, after, adj


def test_B2_분할_적용_모양(split_sc):
    sc, before, after, _ = split_sc
    for arm in h1.ARMS:
        for tn in ("마라토너", "스프린터"):
            b, a = before[arm][tn], after[arm][tn]
            assert a["positions"]["BBB"]["shares"] == 2 * b["positions"]["BBB"]["shares"]
            assert type(a["positions"]["BBB"]["shares"]) is int
            assert a["positions"]["BBB"]["buy_price"] == b["positions"]["BBB"]["buy_price"] / 2
            assert a["wallet"].holdings["BBB"].shares == 2 * b["wallet"].holdings["BBB"].shares
            assert a["wallet"].holdings["BBB"].avg_price == b["wallet"].holdings["BBB"].avg_price / 2
            assert a["pending"] == b["pending"] and a["wallet"].cash == b["wallet"].cash
        for tn in h1.TRAINERS:
            assert after[arm][tn]["corp_actions"][-1] == {
                "kind": "split", "code": "BBB", "r": 2, "date": sc.D[3], "applied_after": sc.D[2],
                "source": "https://예시/공시", "at": "2026-02-04T23:30:00+09:00"}
    # 평가액은 그 순간 그대로(수량 ×2, 가격 ÷2)
    st_b, st_a = before["A0"]["마라토너"], after["A0"]["마라토너"]
    px = st_b["days"][-1]["marks"]["BBB"]
    assert st_a["wallet"].value({"AAA": 1.0, "BBB": px / 2}) == st_b["wallet"].value({"AAA": 1.0, "BBB": px})


def test_B2_분할_뒤_여러_봉_L_0(split_sc):
    sc, _, _, adj = split_sc
    D = sc.D
    for res in sc.runner.results[3:]:
        assert res.ok
    m = sc.states["A0"]["마라토너"]
    sell = [f for f in m["fills"] if f["code"] == "BBB" and f["side"] == "sell"]
    buy = [f for f in m["fills"] if f["code"] == "BBB" and f["side"] == "buy"]
    assert sell[0]["date"] == D[5] and sell[0]["qty"] == 2 * buy[0]["qty"]           # 분할 뒤 수량으로 팜
    cut = {c: h1.cut_frame(f, D[6]) for c, f in adj.items()}
    probs = all_problems("us", sc.states, sc.world.calendar(hs.S_A, D[6]), sc.runner.log, sc.runner.allowed,
                         frames=cut)
    assert h1_check.errors(probs) == [], [(p.code, p.detail) for p in probs]


def test_B2_분할을_한_장부만_적용하면_L(split_sc):
    _, before, after, _ = split_sc
    s = jcopy(after)
    b = jcopy(before)
    st, bt = s["A1"]["마라토너"], b["A1"]["마라토너"]
    st["positions"]["BBB"] = bt["positions"]["BBB"]
    st["wallet"]["holdings"]["BBB"] = bt["wallet"]["holdings"]["BBB"]
    assert "L8" in lcodes(all_problems("us", s))


def test_B2_r_를_틀리게_적용하면_L(split_sc):
    _, before, after, _ = split_sc
    s = jcopy(after)
    n = jcopy(before)["A0"]["스프린터"]["positions"]["BBB"]["shares"]
    s["A0"]["스프린터"]["positions"]["BBB"]["shares"] = 3 * n
    s["A0"]["스프린터"]["wallet"]["holdings"]["BBB"]["shares"] = 3 * n
    assert "L8" in lcodes(all_problems("us", s))


def test_B2_분할_기록이_한_장부에만_있으면_L(split_sc):
    _, before, _, _ = split_sc
    s = jcopy(before)
    one = jcopy(h1.apply_split(before, "BBB", 2, "2026-02-05", "x", "y"))
    s["A0"] = one["A0"]                               # A0 만 분할(기록·수량 모두), A1 은 그대로
    assert lcodes(h1_check.check_ledger("us", "A0", s["A0"], None)) == set()
    assert "L8" in lcodes(h1_check.check_pair("us", s["A0"], s["A1"]))


def test_B2_정수가_아니면_거절_입력은_그대로(split_sc):
    _, before, _, _ = split_sc
    frozen = json.dumps(jcopy(before), sort_keys=True)
    n = before["A0"]["마라토너"]["positions"]["BBB"]["shares"]
    r = 0.5 if n % 2 else 1 / 3
    with pytest.raises(ValueError):
        h1.apply_split(before, "BBB", r, "2026-02-05", "x", "y")
    with pytest.raises(ValueError):
        h1.apply_split(before, "SPY", 2, "2026-02-05", "x", "y")
    with pytest.raises(ValueError):
        h1.apply_split(before, "BBB", 1, "2026-02-05", "x", "y")
    assert json.dumps(jcopy(before), sort_keys=True) == frozen


# ======================= B-3 사전 조건 · 예외 번호와 지문 =======================

@pytest.fixture
def sc2(tmp_path):
    return hs.scenario_a(tmp_path / "log.jsonl", upto=2)


def test_B3_B10_사전_조건은_L_이_아니다(tmp_path, sc2):
    w = hs.world_a()
    brains = hs.fake_brains({})
    r = hs.Runner(w, hs.S_A, tmp_path / "s.jsonl", leader_mode="replay", brains=brains)
    with hs.brains_patched(brains):
        with pytest.raises(h1.H1PreconditionError):                         # S 에서 prev_cal_date 없음 (B-10)
            r.bar(hs.S_A, prev_cal_date=None)
        with pytest.raises(h1.H1PreconditionError):                         # S 전 거래일이 아님
            r.bar(hs.S_A, prev_cal_date=w.at(hs.S_A, -2))
        assert r.bar(hs.S_A).ok
    D3 = sc2.D[3]
    bar = sc2.world.idle_bar(D3)
    cases = [
        dict(idle=h1.IdleBar("SPY", sc2.D[2], bar.open, bar.close)),       # 지수 봉 날짜 다름
        dict(idle=h1.IdleBar("QQQ", D3, bar.open, bar.close)),             # 대기 자산 코드 다름
        dict(halted=frozenset({"BBB"})),                                     # 정지라는데 BBB 에 D3 행이 있음
        dict(delist={"AAA": {"last_date": sc2.D[2], "last_close": 1.0}}),   # 장부에 없는 상장폐지 인자
        dict(calendar=[d for d in sc2.world.calendar(hs.S_A, D3) if d != sc2.D[2]]),   # 달력의 앞 거래일 다름
    ]
    for kw in cases:
        with pytest.raises(h1.H1PreconditionError) as e:
            sc2.bar(D3, **kw)
        assert isinstance(e.value, ValueError) and not isinstance(e.value, h1.H1LogicError), kw


def test_B3_장부끼리_어긋나_끝까지_못_가는_L_예외는_번호와_지문(sc2):
    s = hs.roundtrip(sc2.states, "us")
    s["A1"]["파이오니어"]["last_date"] = sc2.D[1]
    with pytest.raises(h1.H1LogicError) as e:
        sc2.bar(sc2.D[3], states=s)
    assert e.value.code == "L16" and e.value.fingerprint == h1.ledger_fingerprint(s) and e.value.date == sc2.D[3]


def test_B3_엄격_cache_예외는_L6_과_그때까지의_지문(sc2):
    """장부가 이미 어긋나(positions 6주인데 지갑 5주) 상장폐지 정리 매도를 지갑이 거절 → 보유가 남아 team ② 가
    받아 두지 않은 시세를 찾음 → H1LogicError(L6). 그때까지 엔진이 찾은 L2 와 장부 지문이 붙는다."""
    D = sc2.D
    s = hs.roundtrip(sc2.states, "us")
    st = s["A0"]["마라토너"]
    st["wallet"].holdings["AAA"].shares -= 1
    register_delist(s, "AAA", D[2], 50.0)
    frames = {c: f for c, f in sc2.world.frames.items() if c != "AAA"}
    with pytest.raises(h1.H1LogicError) as e:
        sc2.bar(D[3], states=s, frames=frames)
    assert e.value.code == "L6" and isinstance(e.value.fingerprint, str)
    assert [p.code for p in e.value.problems] == ["L2"]
    with pytest.raises(h1.H1LogicError) as e2:
        h1.StrictFrames({})["ZZZ"]
    assert e2.value.code == "L6"


# ======================= B-4 상장폐지 출처 · 미래 last_date =======================

def test_B4_last_date_가_t_이상이면_시세가_필요하다(sc2):
    D = sc2.D
    s = hs.roundtrip(sc2.states, "us")
    register_delist(s, "AAA", D[3], 50.0)                     # 마지막 거래일 = 처리할 봉 D3
    with pytest.raises(h1.H1DataProblem) as e:                # 시세가 없으면 L 이 아니라 D2
        sc2.bar(D[3], states=s, frames={c: f for c, f in sc2.world.frames.items() if c != "AAA"})
    assert e.value.kind == "D2"
    res = sc2.bar(D[3], states=s)                             # 시세가 있으면 그날은 평소대로(정리는 다음 봉)
    assert res.ok and "AAA" in res.states["A0"]["마라토너"]["positions"]
    assert not [f for st in (res.states["A0"]["마라토너"], res.states["A1"]["마라토너"]) for f in st["fills"]
                if f["purpose"] == "delist"]


def test_B4_장부마다_등록이_다르면_L23(sc2):
    s = hs.roundtrip(sc2.states, "us")
    s["A0"]["마라토너"]["corp_actions"].append({"kind": "delist", "code": "AAA", "last_date": sc2.D[2],
                                              "last_close": 1.0})
    with pytest.raises(h1.H1LogicError) as e:
        sc2.bar(sc2.D[3], states=s)
    assert e.value.code == "L23" and e.value.fingerprint is not None


# ======================= B-5 bad_verdict =======================

def test_B5_모르는_판정_글자는_bad_verdict_폴백(tmp_path):
    ask = hs.FakeAsk({"AAA": ("maybe", 0.3), "BBB": ("", 0.9)})
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=0, ask=ask)
    log = sc.runner.log
    for code, raw in (("AAA", "maybe"), ("BBB", "")):
        rec = log.get(f"us|{hs.S_A}|마라토너|{code}")
        assert (rec["status"], rec["source"], rec["verdict"], rec["verdict_raw"]) == ("bad_verdict", "fallback", None, raw)
        assert rec["conviction"] is None and rec["conviction_raw"] is not None
    for arm in h1.ARMS:
        eff = {e["code"]: e["effect"] for e in sc.states[arm]["마라토너"]["days"][0]["leader"]}
        assert eff == {"AAA": "ordered", "BBB": "ordered"}       # 규칙 그대로(확신도 0.3 을 쓰지 않음)
    w3 = [p for p in sc.runner.results[0].problems if p.code == "W3"]
    assert any("bad_verdict" in p.detail for p in w3)


# ======================= B-7 빠졌던 시험 (L17·L20 음성 대조는 tests/test_h1_check.py) =======================

@pytest.fixture(scope="module")
def sc_a(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        return hs.scenario_a(tmp_path_factory.mktemp("a") / "log.jsonl", upto=5)


def test_B7_T_F7_봉마다_스크리너_한_번_두_장부_같은_후보(tmp_path, monkeypatch):
    calls = []
    real = screener.scan_frames

    def counting(*a, **k):
        calls.append(k.get("asof"))
        return real(*a, **k)
    monkeypatch.setattr(screener, "scan_frames", counting)
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=4)
    assert calls == sc.D[:5]
    for res in sc.runner.results:
        for tn in h1.TRAINERS:
            r0, r1 = res.states["A0"][tn]["days"][-1], res.states["A1"][tn]["days"][-1]
            assert r0["screened"] == r1["screened"] == [c["code"] for c in res.found.get(tn, [])]


def test_B7_T_LATEDATA_첫_처리는_D3_다음_처리는_정상(tmp_path):
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=2)
    D3 = sc.D[3]
    late = {c: (f[f.index != pd.Timestamp(D3)] if c == "BBB" else f) for c, f in sc.world.frames.items()}
    with pytest.raises(h1.H1DataProblem) as e:                  # 보유 종목 BBB 의 D3 행이 아직 없음(정지 아님)
        sc.bar(D3, frames=late)
    assert e.value.kind == "D3"
    for k in (3, 4, 5):                                         # 다음 실행: 행이 생겨 정상 처리, 그 뒤도 정상
        assert sc.step(sc.D[k]).ok
    probs = all_problems("us", sc.states, sc.world.calendar(hs.S_A, sc.D[5]), sc.runner.log)
    assert lcodes(probs) == set()


def test_B7_대기_주문_종목의_시가가_없으면_D3(tmp_path):
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=2)
    D3 = sc.D[3]
    assert "DDD" in {o["code"] for o in sc.states["A0"]["스프린터"]["pending"]}
    frames = dict(sc.world.frames)
    g = frames["DDD"].copy()
    g.loc[pd.Timestamp(D3), "Open"] = float("nan")
    frames["DDD"] = g
    with pytest.raises(h1.H1DataProblem) as e:
        sc.bar(D3, frames=frames)
    assert e.value.kind == "D3" and "시가" in str(e.value)


# ======================= B-8 읽기 전용 판정 기록 =======================

def test_B8_읽기_전용은_자르지_않고_알리기만(tmp_path):
    p = tmp_path / "log.jsonl"
    h1.DecisionLog(p).append([{"key": "a"}, {"key": "b"}])
    raw = p.read_bytes() + b'{"key": "c", "st'
    p.write_bytes(raw)
    ro = h1.DecisionLog(p, read_only=True)
    assert [r["key"] for r in ro.records()] == ["a", "b"] and ro.truncated["cut"] is False
    assert p.read_bytes() == raw
    with pytest.raises(ValueError):
        ro.append([{"key": "d"}])
    rw = h1.DecisionLog(p)
    assert rw.truncated["cut"] is True and not p.read_bytes().endswith(b'"st')


# ======================= B-9 엄격 읽기 =======================

def _good(sc_a):
    return json.loads(json.dumps(h1.ledger_to_json(sc_a.states["A1"]["마라토너"], "us")))


def test_B9_NaN_Infinity_거절(sc_a):
    for text in ('{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', '{"a": 1'):
        with pytest.raises(h1.H1LogicError) as e:
            h1.json_loads_strict(text)
        assert e.value.code == "L24"
    assert h1.json_loads_strict('{"a": 1.5}') == {"a": 1.5}
    for path in (("days", 0, "value"), ("fills", 0, "qty"), ("wallet", "cash")):
        d = _good(sc_a)
        x = d
        for k in path[:-1]:
            x = x[k]
        x[path[-1]] = float("inf")
        with pytest.raises(h1.H1LogicError) as e:
            h1.ledger_from_json(d, "us", "A1", "마라토너")
        assert e.value.code == "L24"


def _mut(d, how):
    if how == "positions_빠진_칸":
        del next(iter(d["positions"].values()))["days_held"]
    elif how == "positions_수량_소수":
        next(iter(d["positions"].values()))["shares"] = 1.5
    elif how == "fills_타입":
        d["fills"][0]["qty"] = "10"
    elif how == "fills_남는_칸":
        d["fills"][0]["extra"] = 1
    elif how == "days_빠진_칸":
        del d["days"][0]["marks"]
    elif how == "days_late_글자":
        d["days"][0]["late"] = "no"
    elif how == "orders_빠진_칸":
        del d["orders"][0]["status"]
    elif how == "skips_타입":
        d["skips"].append({"date": "x", "code": "y", "kind": "0주", "reason": "z", "need": None, "avail": None,
                           "order_id": None, "price": "100"})
    elif how == "pending_빠진_칸":
        d["pending"].append({"code": "ZZZ", "signal_date": "2026-02-02", "reason": "x"})
    elif how == "corp_actions_모르는_종류":
        d["corp_actions"].append({"kind": "merger", "code": "AAA"})
    elif how == "split_r_없음":
        d["corp_actions"].append({"kind": "split", "code": "AAA", "date": "2026-02-02", "applied_after": "x"})
    return d


@pytest.mark.parametrize("how", ["positions_빠진_칸", "positions_수량_소수", "fills_타입", "fills_남는_칸", "days_빠진_칸",
                                 "days_late_글자", "orders_빠진_칸", "skips_타입", "pending_빠진_칸",
                                 "corp_actions_모르는_종류", "split_r_없음"])
def test_B9_항목_모양이_틀리면_L24(sc_a, how):
    d = _mut(_good(sc_a), how)
    with pytest.raises(h1.H1LogicError) as e:
        h1.ledger_from_json(d, "us", "A1", "마라토너")
    assert e.value.code == "L24"


def test_B9_정상_장부는_통과(sc_a):
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            d = json.loads(json.dumps(h1.ledger_to_json(sc_a.states[arm][tn], "us")))
            h1.ledger_from_json(copy.deepcopy(d), "us", arm, tn)
