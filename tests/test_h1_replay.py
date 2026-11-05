"""H1 단계 5 — 재현 h1_replay.py 시험 (설계 docs/h1-forward-design.md §5). 인터넷·claude 없음.

- 비교 함수(M1~M7·K)를 손으로 만든 입력으로: 받아들이는 차이(K1·K2·K8·K11·K12)는 통과, 그 밖의 차이는 실패.
- 하네스 모듈 경로 확인: 가짜 R2 폴더에서 저장소 모듈을 읽게 하면 종료 코드 3 → 환경 문제(통과도 기록도 없음).
- W3 합성 차등 재현 전체(빠름): 기준값(R2 sim_team, python -I) == 새 코드(h1.start·run), 장면 s1~s6 이 실제로 그 길을 지남.
  일부러 규칙을 바꾼 새 코드(쓸어 담기 문턱 1 → 0.5)는 W3 가 잡는다(차등 재현이 실제로 가른다는 확인).
- 실데이터 W1 을 몇 봉으로 줄여 한 번(기준값·실행기 전체가 같은 숫자).
- 기록 갈래: 통과(모든 창)면 replay_pass.json 한 줄 + 관문이 그 줄로 열림, 실패·일부 창·코드가 바뀜이면 기록 없음.
R2 브랜치(origin/research-r2-2026-11-04)가 없으면 그 시험만 건너뜀(git fetch 필요).
"""
import json
import math
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst          # noqa: E402
import h1               # noqa: E402
import h1_check         # noqa: E402
import h1_replay as RP  # noqa: E402

TR = h1.TRAINERS


def _boom(*a, **k):
    raise AssertionError("시험이 진짜 claude 를 부르려 했어요")


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    import h1_repo_guard as rg
    before = rg.snapshot(ROOT)
    monkeypatch.setattr(analyst, "analyze_logged", _boom)
    monkeypatch.setattr(analyst, "analyze", _boom)
    monkeypatch.setattr(analyst, "claude_cli_version", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("인터넷")))
    real_run = subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]).endswith("claude"):
            raise AssertionError("시험이 claude 프로세스를 띄우려 했어요")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guarded)
    yield
    moved = rg.changes(before, rg.snapshot(ROOT))
    assert not moved, "시험이 저장소 state/·results/ 를 건드렸어요: " + "; ".join(moved[:5])


def _r2_available():
    p = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "-q", RP.R2_REF], capture_output=True)
    return p.returncode == 0


needs_r2 = pytest.mark.skipif(not _r2_available(), reason="R2 브랜치 없음(git fetch origin research-r2-2026-11-04)")


# ============================ 비교 함수: 손으로 만든 입력 ============================

D = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
LAST = D[-1]


def _day(d, value=100.0, cash=1e-8, stock=0.0, idle=100.0, units=1.0, events=(), over=0):
    return {"date": d, "value": value, "cash": cash, "stock_value": stock, "idle_value": idle, "idle_units": units,
            "events": list(events), "over_slots": over}


def _states():
    """세 트레이너가 똑같은 아주 작은 장부(A0·A1)."""
    out = {}
    for arm in h1.ARMS:
        out[arm] = {}
        for tn in TR:
            out[arm][tn] = {
                "fills": [{"date": D[1], "kind": "idle", "code": "SPY", "side": "buy", "qty": 1.25, "price": 80.0,
                           "cash_delta": -100.0},
                          {"date": D[2], "kind": "stock", "code": "AAA", "side": "buy", "qty": 3, "price": 10.0,
                           "cash_delta": -30.03}],
                "skips": [{"date": D[2], "code": "BBB", "kind": "현금부족"}],
                "orders": [{"signal_date": D[1], "code": "AAA", "action": "매수", "reason": "가짜 매수"}],
                "days": [_day(d) for d in D],
            }
    return out


def _base():
    """하네스 결과 모양(그 창 하나)."""
    arms = {}
    for arm in h1.ARMS:
        none = {"fills": [], "skips": [], "orders": [], "events": [], "daily": [], "over_slots": {}}
        for tn in TR:
            none["fills"] += [{"sleeve": tn, "date": D[1], "kind": "index", "code": "SPY", "side": "매수", "qty": 1.25,
                               "price": 80.0, "cash": -100.0},
                              {"sleeve": tn, "date": D[2], "kind": "stock", "code": "AAA", "side": "매수", "qty": 3,
                               "price": 10.0, "cash": -30.03}]
            none["skips"].append({"sleeve": tn, "date": D[2], "code": "BBB", "kind": "현금부족"})
            none["orders"].append({"sleeve": tn, "signal_date": D[1], "code": "AAA", "action": "매수",
                                   "reason": "가짜 매수"})
            none["over_slots"][tn] = 0
        for d in D:
            row = {"date": d, "value": 300.0, "stock": 0.0, "index": 300.0, "cash": 3e-8}
            for tn in TR:
                row.update({f"v_{tn}": 100.0, f"stock_{tn}": 0.0, f"index_{tn}": 100.0, f"cash_{tn}": 1e-8,
                            f"units_{tn}": 1.0})
            none["daily"].append(row)
        arms[arm] = {"none": none, "current": {"events": []}}
    return {"i1": LAST, "dates": list(D), "arms": arms}


def test_같은_입력이면_M1_M5_모두_통과():
    out = RP.compare_window("us", _states(), _base(), do_m6=False, do_m7=False)
    assert all(out[m]["ok"] for m in ("M1", "M2", "M3", "M4", "M5")), out


@pytest.mark.parametrize("field,delta,ok", [
    ("idle_qty", 1e-12, True),      # K12: 지수 수량 상대 차 ≤ 1e-9
    ("idle_qty", 1e-6, False),
    ("stock_qty", 1, False),         # 주식 수량은 정확히
    ("price", 1e-13, False),         # 체결가는 정확히 같아야(1ulp 도 차이)
    ("cash", 1e-8, True),            # 현금 변화 절대 차 ≤ 1e-6
    ("cash", 1e-3, False),
])
def test_M1_체결_허용_오차(field, delta, ok):
    st = _states()
    f_idle, f_stock = st["A1"][TR[0]]["fills"]
    if field == "idle_qty":
        f_idle["qty"] = f_idle["qty"] * (1 + delta)
    elif field == "stock_qty":
        f_stock["qty"] += delta
    elif field == "price":
        f_stock["price"] = f_stock["price"] + delta
    else:
        f_stock["cash_delta"] += delta
    assert RP.compare_fills(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"] is ok


def test_M1_빠지거나_더한_체결은_실패():
    st = _states()
    st["A0"][TR[1]]["fills"].pop()
    assert not RP.compare_fills(st, "A0", _base()["arms"]["A0"]["none"], LAST)["ok"]
    st = _states()
    st["A0"][TR[1]]["fills"].append({"date": LAST, "kind": "stock", "code": "CCC", "side": "sell", "qty": 1,
                                     "price": 5.0, "cash_delta": 4.9})
    out = RP.compare_fills(st, "A0", _base()["arms"]["A0"]["none"], LAST)
    assert not out["ok"], "마지막 봉의 체결은 K1 대상이 아님(체결은 마지막 봉도 비교)"


def test_M2_보류_차이와_재현에서_팀장_보류는_차이():
    st = _states()
    st["A1"][TR[2]]["skips"][0]["kind"] = "0주"
    assert not RP.compare_skips(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"]
    st = _states()
    st["A1"][TR[2]]["skips"].append({"date": D[2], "code": "CCC", "kind": "팀장hold"})   # 재현은 팀장 끔 → 있으면 안 됨
    assert not RP.compare_skips(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"]


def test_M3_K1_마지막_봉_주문은_빼고_그_전은_비교():
    b = _base()["arms"]["A0"]["none"]
    st = _states()
    st["A0"][TR[0]]["orders"].append({"signal_date": LAST, "code": "ZZZ", "action": "매수", "reason": "마지막 봉"})
    out = RP.compare_orders(st, "A0", b, LAST)
    assert out["ok"] and out["k1_excluded"] == 1
    st["A0"][TR[0]]["orders"].append({"signal_date": D[2], "code": "ZZZ", "action": "매수", "reason": "그 전 봉"})
    assert not RP.compare_orders(st, "A0", b, LAST)["ok"]
    st = _states()
    st["A0"][TR[0]]["orders"][0]["reason"] = "사유 글이 다름"                 # 사유 글도 비교(14자 자르지 않음)
    assert not RP.compare_orders(st, "A0", b, LAST)["ok"]


def test_K11_빈자리_부족은_마지막_봉을_빼고_합계만():
    b = _base()["arms"]["A1"]["none"]
    st = _states()
    st["A1"][TR[1]]["days"][-1]["over_slots"] = 4                               # 마지막 봉 → 뺌
    assert RP.compare_over_slots(st, "A1", b, LAST)["ok"]
    st["A1"][TR[1]]["days"][1]["over_slots"] = 1
    assert not RP.compare_over_slots(st, "A1", b, LAST)["ok"]
    b["over_slots"][TR[1]] = 1
    assert RP.compare_over_slots(st, "A1", b, LAST)["ok"]


@pytest.mark.parametrize("key,delta,ok", [
    ("value", 1e-12, True), ("value", 1e-6, False), ("idle_units", 1e-12, True), ("idle_units", 1e-5, False),
    ("cash", 1e-8, True),           # 현금은 절대 차: 1e-8 vs 2e-8 은 상대로는 50% 지만 받아들임(probe4)
    ("cash", 1e-3, False),
])
def test_M4_매일_값_허용_오차(key, delta, ok):
    st = _states()
    row = st["A1"][TR[0]]["days"][2]
    row[key] = row[key] * (1 + delta) if key != "cash" else row[key] + delta
    assert RP.compare_daily(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"] is ok


def test_M4_빠진_날은_실패():
    st = _states()
    st["A0"][TR[2]]["days"].pop(1)
    assert not RP.compare_daily(st, "A0", _base()["arms"]["A0"]["none"], LAST)["ok"]


def test_M5_그림자_서킷_첫_발동일과_K1():
    ev = {"kind": "shadow_breaker", "why": "하루", "first": True}
    st = _states()
    st["A1"][TR[0]]["days"][-1]["events"] = [ev]                                # 마지막 봉만 → K1 로 뺌
    cur = {"events": []}
    assert RP.compare_shadow(st, "A1", cur, LAST)["ok"]
    st["A1"][TR[0]]["days"][2]["events"] = [ev]
    assert not RP.compare_shadow(st, "A1", cur, LAST)["ok"]
    cur = {"events": [{"kind": "서킷(지금)", "sleeve": TR[0], "date": D[2]}]}
    assert RP.compare_shadow(st, "A1", cur, LAST)["ok"]
    cur = {"events": [{"kind": "서킷(지금)", "sleeve": TR[0], "date": D[1]}]}   # 날짜가 다르면 실패
    assert not RP.compare_shadow(st, "A1", cur, LAST)["ok"]


def _bh_states(opens, closes, total=100_000.0):
    st = {"A0": {}, "A1": {}}
    for arm in h1.ARMS:
        for tn in TR:
            st[arm][tn] = {"start_cash": total / 3, "wallet": {"fee_rate": 0.001, "slippage": 0.0005},
                           "days": [{"date": d, "idle_open": o, "idle_close": c} for d, o, c in zip(D, opens, closes)]}
    return st


def test_M6_지수_BH_K2_마지막_날은_단위_곱하기_종가():
    opens, closes = [100.0, 101.0, 102.0, 103.0], [100.5, 101.5, 102.5, 103.5]
    st = _bh_states(opens, closes)
    total = sum(st["A1"][tn]["start_cash"] for tn in TR)
    units = total / (opens[1] * (1 + 0.0005) * (1 + 0.001))
    eq = [units * c for c in closes[1:]]
    sold = closes[-1] * (1 - 0.0005) * units
    eq[-1] = sold - sold * 0.001                                                 # R2 는 마지막 날 매도 비용을 뺌(K2)
    base = {"bh": {"units": units, "equity": eq, "dates": D[1:], "last_close": closes[-1]}}
    assert RP.compare_bh("us", st, base)["ok"]
    base["bh"]["units"] = units * (1 + 1e-15)
    assert not RP.compare_bh("us", st, base)["ok"]                               # 단위는 비트까지


def test_M7_이자_금리가_다르면_실패():
    import pandas as pd
    st = {"A0": {tn: {"days": [{"date": d, "value": 100.0, "cash": 50.0, "stock_value": 50.0, "idle_value": 0.0,
                                "idle_units": 0.0, "prev_cal_date": prev}
                               for d, prev in zip(D, ["2026-01-02"] + D[:-1])]} for tn in TR}}
    series = pd.Series([4.0, 4.1, 4.2, 4.3, 4.4], index=pd.DatetimeIndex(["2026-01-02"] + D))
    base = {"rates": {"dates": list(D), "values": [4.0, 4.1, 4.2, 4.3]}}       # 전 거래일 값(prev_day)
    assert RP.compare_interest("us", st, base, series)["ok"]
    base["rates"]["values"][2] = 9.9
    assert not RP.compare_interest("us", st, base, series)["ok"]


def test_K_전제_확인_70봉_새상장_세율_종목군():
    import pandas as pd
    idx = pd.bdate_range("2025-06-02", "2026-01-08")
    full = pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=idx)
    base = {"dates": list(D), "_kr_sell_tax": [list(x) for x in h1.KR_SELL_TAX], "_kr_universe": None,
            "_kind": "synthetic"}
    assert RP.k_checks("kr", {"111111": full}, ["111111"], base, D[0], LAST)["ok"]
    young = full[full.index >= pd.Timestamp("2025-11-01")]                      # 창 시작 전 50봉 남짓
    assert not RP.k_checks("kr", {"111111": young}, ["111111"], base, D[0], LAST)["ok"]
    new = full[full.index >= pd.Timestamp(D[1])]                               # 창 안에서 새로 상장
    assert not RP.k_checks("kr", {"111111": full, "222222": new}, ["111111", "222222"], base, D[0], LAST)["ok"]
    bad = dict(base, _kr_sell_tax=[["0000-01-01", 0.003]])
    assert not RP.k_checks("kr", {"111111": full}, ["111111"], bad, D[0], LAST)["ok"]
    uni = dict(base, _kr_universe=["005930"], _kind="real")
    assert not RP.k_checks("kr", {"111111": full}, ["111111"], uni, D[0], LAST)["ok"]


def test_M8_실행_일지_D_와_허용_밖_경고(tmp_path):
    root = tmp_path / "h1"
    root.mkdir()
    lines = [{"event": "end", "market": "kr", "exit_code": 0,
              "problems": [{"level": "W", "code": "W2"}, {"level": "W", "code": "W3"}]},
             {"event": "end", "market": "kr", "exit_code": 0, "problems": [{"level": "W", "code": "W5"}]},
             {"event": "end", "market": "kr", "exit_code": 4, "problems": [{"level": "D", "code": "D3"}]},
             {"event": "end", "market": "us", "exit_code": 0, "problems": [{"level": "W", "code": "W1"}]}]
    (root / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    r = RP.check_runs(root, "kr")
    assert r["w_other"] == ["W5"] and r["d"] == {"D3": 1} and r["bad_exit"] == {4: 1} and r["n_runs"] == 3


# ============================ 하네스 · R2 풀기 ============================

def test_R2_가_없으면_환경_문제와_fetch_안내(tmp_path):
    with pytest.raises(RP.ReplayEnvError, match="git fetch origin research-r2-2026-11-04"):
        RP.extract_r2("refs/없는/가지-12345", tmp_path / "r2")


def test_하네스는_모듈이_임시_폴더_밖에서_읽히면_멈춤(tmp_path):
    """가짜 R2 폴더: sim_team.py 가 지금 저장소를 sys.path 맨 앞에 넣으면 main·team 등이 저장소에서 읽힌다 → 종료 코드 3."""
    fake = tmp_path / "fake_r2"
    rep = fake / RP.R2_DIR
    rep.mkdir(parents=True)
    (rep / "sim_team.py").write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n", encoding="utf-8")
    with pytest.raises(RP.ReplayEnvError, match="R2 임시 폴더 밖"):
        RP.run_harness(rep, [], tmp_path / "work")


# ============================ W3 합성 차등 재현 (전체) ============================

def test_W3_합성_세계는_결정적이고_값이_비트까지_보존(tmp_path):
    m1 = RP.make_w3(tmp_path / "a")
    m2 = RP.make_w3(tmp_path / "b")
    for f in sorted((tmp_path / "a").iterdir()):
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name
    assert m1["s5"] == m2["s5"]
    assert 0.98 < m1["s5"]["left1"] < 0.995 and 0.0 < m1["s5"]["left2"] < 0.02
    assert m1["W"][29] == "2019-05-31" and m1["W"][30] == "2019-06-03"          # 세율 경계 전날·당일


@pytest.fixture(scope="module")
def w3_result(tmp_path_factory):
    if not _r2_available():
        pytest.skip("R2 브랜치 없음")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", _boom)
        mp.setattr(analyst, "claude_cli_version", _boom)
        work = tmp_path_factory.mktemp("w3")
        res = RP.replay(["W3"], RP.R2_REF, work / "w", progress=lambda *a: None)
    return res, work


@needs_r2
def test_W3_전체_기준값과_같고_장면이_모두_그_길을_지남(w3_result):
    res, _ = w3_result
    w = res["windows"]["W3-kr"]
    assert w["ok"], {m: c["detail"] for m, c in w["checks"].items() if not c["ok"]}
    for m in RP.REQUIRED["W3"]:
        assert w["checks"][m]["ok"], (m, w["checks"][m])
    assert set(w["scenes"]) == {"s1", "s2", "s3", "s4", "s5", "s6"}
    assert all(v["ok"] for v in w["scenes"].values()), w["scenes"]
    assert w["checks"]["M1"]["arms"]["A1"]["n_h1"] > 20 and w["checks"]["M2"]["arms"]["A1"]["n_h1"] >= 1
    assert set(w["warnings"]) <= {"W2", "W3"} and w["warnings"].get("W2")
    assert not res["complete"] and res["passed"]                                 # 일부 창 → 기록 대상 아님


@needs_r2
def test_W3_일부_창은_기록하지_않고_보고서만(w3_result, tmp_path):
    res, _ = w3_result
    root = tmp_path / "h1"
    code = RP.finish(res, root, progress=lambda *a: None)
    assert code == RP.EXIT_OK
    assert not (root / "replay_pass.json").exists()
    rep = list((root / "reports").glob("replay-*.md"))
    assert len(rep) == 1 and "통과 기록 없음" in rep[0].read_text(encoding="utf-8")


@needs_r2
def test_W3_는_규칙을_바꾼_새_코드를_잡는다(tmp_path, monkeypatch):
    """쓸어 담기 문턱을 1 → 0.5 로 바꾸면(R2 는 1) s5 의 남은 현금 0.99 를 새 코드만 지수로 보내 M1 이 갈린다."""
    monkeypatch.setattr(h1, "SWEEP_MIN", 0.5)
    res = RP.replay(["W3"], RP.R2_REF, tmp_path / "w", progress=lambda *a: None)
    w = res["windows"]["W3-kr"]
    assert not w["ok"] and not res["passed"]
    assert not w["checks"]["M1"]["ok"] and not w["checks"]["S"]["ok"]


@needs_r2
def test_실데이터_W1_을_몇_봉으로_줄여도_기준값과_같음(tmp_path):
    specs = {n: dict(s, end="2026-06-10") for n, s in RP.WINDOWS.items() if s["group"] == "W1"}
    res = RP.replay(["W1"], RP.R2_REF, tmp_path / "w", progress=lambda *a: None, specs=specs)
    for n in ("W1-us", "W1-kr"):
        w = res["windows"][n]
        assert w["n_bars"] >= 6 and w["S"] == "2026-06-01" and w["last"] == "2026-06-10", (n, w["n_bars"], w["S"])
        assert w["ok"], {m: c["detail"] for m, c in w["checks"].items() if not c["ok"]}
    assert not res["complete"]                                                    # 창을 바꿨으므로 기록 대상 아님


# ============================ 기록 갈래 ============================

def _fake_result(passed=True, complete=True, code_changed=False):
    ch, files = h1.code_hash()
    env = h1.env_info()
    win = {}
    for n, s in RP.WINDOWS.items():
        checks = {m: RP._chk(True, "같음") for m in RP.REQUIRED[s["group"]]}
        if not passed and n == "W2-kr":
            checks["M1"] = RP._chk(False, "체결 차이", ["A1: 가짜 차이"])
        win[n] = {"spec": s, "checks": checks, "ok": passed or n != "W2-kr", "run": {"seconds": 1.0, "max_run_s": 0.1},
                  "n_bars": 3, "S": s["start"], "last": s["end"], "fingerprint": "f" * 64 if n != "W3-kr" else "e" * 64,
                  "warnings": {}, "ref": {}}
    return {"code_hash": ch, "files": files, "env": env, "code_changed": code_changed, "r2_ref": RP.R2_REF,
            "r2_commit": "0" * 40, "modules": {"sim_team": "x"}, "windows": win, "groups": ["W1", "W2", "W3"],
            "complete": complete, "passed": passed, "seconds": 1.0, "baseline_seconds": 0.5,
            "started_at": "2026-11-05T10:00:00+09:00"}


def test_통과면_기록하고_관문이_그_줄로_열림(tmp_path):
    root = tmp_path / "h1"
    r2rep = tmp_path / "r2rep"
    (r2rep / "data" / "rates").mkdir(parents=True)
    (r2rep / "data" / "rates" / "us_tbill.csv").write_text("date,rate_pct,source\n2026-01-02,3.6,s\n", encoding="utf-8")
    (r2rep / "data" / "rates" / "kr_shortrate.csv").write_text("date,rate_pct,source\n2026-01-01,2.5,s\n",
                                                               encoding="utf-8")
    (root / "rates").mkdir(parents=True)
    (root / "rates" / "kr_shortrate.csv").write_text("이미 있음", encoding="utf-8")   # 있으면 덮지 않는다
    code = RP.finish(_fake_result(), root, r2rep, progress=lambda *a: None)
    assert code == RP.EXIT_OK
    entries = h1.replay_pass_entries(root)
    assert len(entries) == 1
    e = entries[0]
    assert e["code_hash"] == h1.code_hash()[0] and e["files"] == h1.code_hash()[1]
    assert e["ledger_fingerprints"] == {"W1-us": "f" * 64, "W1-kr": "f" * 64, "W2-kr": "f" * 64}
    assert e["data_golden_sha256"] == h1.data_golden_digest() and e["fingerprint_version"] == h1.FINGERPRINT_VERSION
    assert e["report"].startswith("reports/replay-") and (root / e["report"]).exists()
    h1.check_gate(root)                                                          # 이 줄로 관문이 열린다(거절 없음)
    assert (root / "rates" / "us_tbill.csv").exists()
    assert (root / "rates" / "kr_shortrate.csv").read_text(encoding="utf-8") == "이미 있음"
    changes = h1.read_jsonl(root / "changes.jsonl")
    assert [c["kind"] for c in changes] == ["replay-pass"]


@pytest.mark.parametrize("kw,want", [({"passed": False}, RP.EXIT_DIFF), ({"code_changed": True}, RP.EXIT_ENV),
                                     ({"complete": False}, RP.EXIT_OK)])
def test_실패_코드바뀜_일부는_기록_없음(tmp_path, kw, want):
    root = tmp_path / "h1"
    lines = []
    code = RP.finish(_fake_result(**kw), root, progress=lines.append)
    assert code == want
    assert not (root / "replay_pass.json").exists() and not (root / "rates").exists()
    rep = list((root / "reports").glob("replay-*.md"))
    assert len(rep) == 1
    if kw.get("passed") is False:
        assert any("W2-kr M1" in x for x in lines)                               # 차이 표를 화면에
        assert "통과 아님" in rep[0].read_text(encoding="utf-8")


def test_기록_직전_코드가_바뀌면_기록하지_않음(tmp_path):
    res = _fake_result()
    res["code_hash"] = "0" * 64                                                   # 재현 때 지문 ≠ 지금 지문
    root = tmp_path / "h1"
    assert RP.finish(res, root, progress=lambda *a: None) == RP.EXIT_ENV
    assert not (root / "replay_pass.json").exists()


def test_cli_인자_오류는_9(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert RP.cli(["--windows", "W4"]) == RP.EXIT_USAGE
    assert RP.cli(["--windows", "W1,W1"]) == RP.EXIT_USAGE
    assert RP.cli(["--root", str(ROOT / "state")]) == RP.EXIT_USAGE              # 운영 상태 폴더는 거절
    assert RP.cli(["--없는-옵션"]) == RP.EXIT_USAGE


def test_cli_R2_가_없으면_4(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert RP.cli(["--root", str(tmp_path / "h1"), "--windows", "W3", "--r2-ref", "refs/없는/가지-12345"]) == RP.EXIT_ENV
    assert not (tmp_path / "h1" / "replay_pass.json").exists()
    assert not list(tmp_path.glob("h1-replay-*"))                                # 임시 폴더는 지움
