"""H1 단계 2c — 보고서 h1_report.py 시험 (설계 docs/h1-forward-design.md §3.8, §6). 인터넷·claude·키 없음.

장부는 가짜 자료(tests/h1_fake_source.py)로 h1.start·h1.run 을 여러 날 돌려 만든다(tmp 폴더, 저장소 state/ 는 안 만듦).
진짜 claude 는 부르지 않는다(analyst 를 가짜로 바꾸고 claude 프로세스를 막음). 인터넷도 막는다:
urllib.request.urlopen 을 부르면 BaseException 으로 시험이 깨진다(받기 실패로 조용히 넘어가지 않게). 받기 장면만 가짜 urlopen 을 넣는다.

설계 §6 ID ↔ 시험
- T-F8a  test_T_F8a_*     평가액·수익률(S 이후·그달)·MDD·A1−A0·지수 B&H(S+1)·비율·매매 수·비용·실현손익·팀장 수·폴백 20%·
                           운영 기준 칸(늦은 봉·빠진 날·관문 거절·자료 멈춤 종류별)을 장부 파일에서 따로 센 값과 비교
- T-F8b  test_T_F8b_*     금리 규칙(미국 전 거래일·빈 날 이월·S 날, 국내 m−1월·빈 달 이월), 이자 식 손계산,
                           R2 rate_for_days 와 같은 결과(R2 식을 옮긴 기준 + R2 브랜치를 tmp 에 풀어 python -I 로 부른 결과)
- T-F8c  test_T_F8c_*     urlopen 실패 → 저장본·"오프라인" 표시 / 저장본 없음 → 그 절만 "계산 불가", 파일은 만들어짐
- T-SHADOW test_T_SHADOW_* 보고서의 (장부, 트레이너)별 첫 발동일·발동한 날 수 == 하루 기록 값으로 다시 계산한 것
- T-START test_T_START_*  지수 B&H: S 날 = 총액, 단위 = 총액 ÷ (S+1 시가 × (1+slip)(1+fee))
- --final test_final_*    창이 덜 참 → 판정 안 함, 깨끗한 창 → 통과, 경계(늦은 봉 10·한 번에 5봉)는 통과,
                           L·늦은 봉 11·한 번에 6봉·종료 코드 6·다른 지문·빠진 날 → 창 실패,
                           재시작 상한·마감(지남·끝날 수 없음) → "H1 포워드 실패"
- 월간     test_month_*     지난달 보고서는 S ~ 그달 마지막 처리 봉까지만(그 뒤 일지 줄이 섞이지 않음)
- 그 밖    파일을 고치지 않음(sha256), 같은 입력 → 같은 바이트, 지수 단위 화면 6자리, cli 종료 코드(0·2·4·5·8·9)
"""
import fcntl
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst          # noqa: E402
import h1               # noqa: E402
import h1_fake_source as fs   # noqa: E402
import h1_report as R   # noqa: E402
import h1_synth as hs   # noqa: E402
import markets          # noqa: E402
import metrics          # noqa: E402
import test_h1_runner as tr   # noqa: E402  (장면 도우미 H·세계·계획을 같이 씀)
from risk_guard import CircuitBreaker   # noqa: E402

US = markets.MARKETS["us"]
KR = markets.MARKETS["kr"]


class NoNet(BaseException):
    """시험이 인터넷(urlopen)을 쓰려 함 — Exception 이 아니라서 fetch_rates 가 '받기 실패'로 삼키지 못한다."""


def _boom(*a, **k):
    raise AssertionError("시험이 진짜 claude 를 부르려 했어요")


def _no_net(*a, **k):
    raise NoNet("시험이 인터넷에 나가려 했어요")


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    import h1_repo_guard as rg                                   # 저장소 state/·results/ 앞뒤 비교(단계 3 검토 T-3)
    repo_before = rg.snapshot(ROOT)
    monkeypatch.setattr(analyst, "analyze_logged", _boom)
    monkeypatch.setattr(analyst, "analyze", _boom)
    monkeypatch.setattr(analyst, "claude_cli_version", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", _no_net)
    real_run = subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]).endswith("claude"):
            raise AssertionError("시험이 claude 프로세스를 띄우려 했어요")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guarded)

    def no_wait(s):
        raise AssertionError("잠금이 실제로 기다리려 했어요")
    monkeypatch.setattr(h1, "_lock_sleep", no_wait)
    yield
    moved = rg.changes(repo_before, rg.snapshot(ROOT))
    assert not moved, "시험이 저장소 state/·results/ 를 건드렸어요(이미 있던 맥 장부 포함): " + "; ".join(moved[:5])


# ============================ 장면 (모듈마다 한 번 만들고 복사해 씀) ============================

def _us_scenario(tmp):
    """미국 S=2026-02-02 ~ 2026-03-09(26봉): 2b-2 E2E 장면(분할·상장폐지·늦은 봉·늦은 자료) + 관문 거절 1번 +
    2026-03-03 SPY 종가 −15%(A1 그림자 서킷)."""
    base = tr.us_world(end="2026-06-30")
    crash_day = base.at(hs.S_A, 21)
    w = tr.us_world(end="2026-06-30", idle_crash=(crash_day, 0.85))
    h = tr.H(tmp, w, hs.S_A, tr.plan_e2e_us, hs.FakeAsk(hs.ASK_A), n_days=30)
    D = h.D
    assert h.start() == 0
    assert h.run(D[1]) == 0
    assert h.run(D[2], gate=True) == 3                            # 재현 통과 기록 없음 → 관문 거절
    for k in range(2, 6):
        assert h.run(D[k]) == 0
    h.src.transform["BBB"] = fs.split_after(D[6], 2, tr.ET)
    assert h.run(D[6]) == 4                                       # D6 분할 의심
    assert h.corp("BBB", split=2, date=D[6]) == 0
    assert h.run(D[6]) == 0 and h.run(D[7]) == 0 and h.run(D[8]) == 0
    h.src.missing = {"CCC"}
    assert h.run(D[9]) == 4                                       # D2
    assert h.corp("CCC", delist=True, last_date=D[8]) == 0
    assert h.run(D[9]) == 0 and h.run(D[10]) == 0
    assert h.run(D[12]) == 0                                      # D11 늦은 봉 + D12 (한 번에 2봉)
    h.src.drop = {"BBB": {D[13]}}
    assert h.run(D[13]) == 4                                      # D3
    h.src.drop = {}
    for k in range(13, 26):
        assert h.run(D[k]) == 0
    return h


def _kr_scenario(tmp):
    """국내 S=2026-02-02 ~ 2026-03-06(25봉), 정지 포함, 팀장은 늘 시간 초과(폴백 100%)."""
    base = tr.kr_world()
    D0 = [base.at("2026-02-02", k) for k in range(30)]
    w = tr.kr_world(halts={"005380": D0[3:6], "000660": D0[8:10]})
    h = tr.H(tmp, w, "2026-02-02", tr.plan_e2e_kr, hs.FakeAsk(status="timeout"), n_days=30)
    assert h.start() == 0
    for k in range(1, 25):
        assert h.run(h.D[k]) == 0
    return h


def _plan_fin(D):
    return {"마라토너": {"buy": [("AAA", D[0]), ("BBB", D[0]), ("CCC", D[20])], "sell": [("AAA", D[30])]},
            "스프린터": {"buy": [("DDD", D[2]), ("EEE", D[40])], "sell": [("DDD", D[50])]},
            "파이오니어": {"buy": [("GGG", D[5])], "sell": [("GGG", D[45])]}}


def _final_scenario(tmp):
    """깨끗한 판정 창: 재현 통과 기록에 지금 코드·환경을 적고 관문을 켜서 S ~ S+65(66봉) 처리."""
    w = tr.us_world(end="2026-07-31")
    h = tr.H(tmp, w, hs.S_A, _plan_fin, hs.FakeAsk(hs.ASK_A), n_days=70)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0
    for k in range(1, 66):
        assert h.run(h.D[k], gate=True) == 0, k
    return h


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", _boom)
        mp.setattr(analyst, "claude_cli_version", _boom)
        mp.setattr(h1, "_lock_sleep", _boom)
        mp.setattr(urllib.request, "urlopen", _no_net)
        out["us"] = _us_scenario(tmp_path_factory.mktemp("rep-us"))
        out["kr"] = _kr_scenario(tmp_path_factory.mktemp("rep-kr"))
        out["fin"] = _final_scenario(tmp_path_factory.mktemp("rep-fin"))
    return out


def copy_of(h, tmp_path, name="h1"):
    """장면의 장부 폴더를 복사(시험마다 고쳐 써도 다른 시험에 영향 없게)."""
    dst = Path(tmp_path) / name
    shutil.copytree(h.root, dst)
    return dst


def load(root, mk):
    return h1.load_market(mk, root, repair=False)


def recommit(root, mk, fn_states=None, fn_meta=None, prereg=True):
    """장면 사본의 장부·meta 를 고친 뒤 h1.commit 으로 HEAD 까지 맞춰 쓴다(엄격 읽기를 통과하게).
    prereg: meta.rules 를 고쳤으면 사전 등록 파일(prereg_<m>.json)의 rules 도 같은 값으로(단계 4 F-2 — 판정 숫자는 사전
    등록 파일에서 읽으므로 '처음부터 그 숫자로 사전 등록한 창'을 흉내 냄). False 면 meta 만 바꿈(⑩ 위반 장면)."""
    ld = load(root, mk)
    if fn_states:
        fn_states(ld.states)
    if fn_meta:
        fn_meta(ld.meta)
        if prereg:
            p = h1.prereg_path(mk, root)
            pre = json.loads(p.read_text(encoding="utf-8"))
            pre["rules"] = json.loads(json.dumps(ld.meta["rules"]))
            p.write_text(json.dumps(pre, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    dec = h1.DecisionLog(h1.decisions_path(root, mk), read_only=True)
    h1.commit(root, mk, ld.states, ld.meta, dec, "test-rewrite", ld.head["written_at"], ld.head)


def jline(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def files_sha(root):
    """보고서·금리 저장본·잠금 파일(빈 파일 — 보고서가 금리 받을 때 전역 잠금 h1-global.lock 을 만들 수 있음)을 뺀
    모든 파일의 sha256(장부·HEAD·meta·일지·판정 기록·백업·사전 등록)."""
    return {k: v for k, v in fs.tree_sha(root).items() if not k.startswith(("reports/", "rates/"))
            and not k.endswith(".lock")}


def team_values(st, arm, upto=None):
    dates = [r["date"] for r in st[arm]["마라토너"]["days"] if upto is None or r["date"] <= upto]
    out = []
    for d in dates:
        out.append(sum(r["value"] for tn in h1.TRAINERS for r in st[arm][tn]["days"] if r["date"] == d))
    return dates, out


def hand_mdd(vals):
    peak, worst = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def fred_csv(rows):
    """FRED fredgraph.csv 모양 글자. rows = [(날짜, 값 글자)] ('.' = 빈값)."""
    return "observation_date,DTB3\n" + "".join(f"{d},{v}\n" for d, v in rows)


# ============================ T-F8a 보고서 숫자 ============================

def test_T_F8a_값_수익률_MDD_A1A0_지수BH(built, tmp_path):
    h = built["us"]
    root = copy_of(h, tmp_path)
    st = load(root, "us").states
    D = h.D
    d = R.collect("us", "2026-03", root=root, online=False)
    cut = D[25]
    assert d["cut"] == cut and d["period_start"] == "2026-03-01" and d["last"] == cut
    total = 100_000.0
    for arm in h1.ARMS:
        dates, vals = team_values(st, arm, cut)
        a = d["values"]["arms"][arm]
        assert dates[0] == hs.S_A and len(dates) == 26
        assert a["value"] == pytest.approx(vals[-1], rel=1e-12)
        assert a["ret"] == pytest.approx(vals[-1] / total - 1, rel=1e-12)
        feb_end = vals[dates.index(D[19])]                        # 2026-02-27 = 2월 마지막 봉
        assert a["ret_period"] == pytest.approx(vals[-1] / feb_end - 1, rel=1e-12)
        assert a["mdd"] == pytest.approx(hand_mdd(vals), rel=1e-12)
    v0 = d["values"]["arms"]["A0"]["value"]
    v1 = d["values"]["arms"]["A1"]["value"]
    assert d["values"]["diff"] == pytest.approx(v1 - v0, rel=1e-12)
    assert d["values"]["diff_pp"] == pytest.approx((v1 / total - v0 / total) * 100, rel=1e-9)
    # 지수 B&H(같은 시작): 단위 = 총액 ÷ (S+1 시가 × (1+slip)(1+fee)), 값 = 단위 × 그날 종가
    q1 = float(h.w.idle.loc[pd.Timestamp(D[1]), "Open"])
    units = total / (q1 * (1 + US.slippage) * (1 + US.fee_rate))
    bh = d["values"]["bh"]
    assert bh["units"] == units
    closes = [float(h.w.idle.loc[pd.Timestamp(x), "Close"]) for x in D[:26]]
    bh_vals = [total] + [units * c for c in closes[1:]]
    assert bh["value"] == bh_vals[-1] and bh["return"] == bh_vals[-1] / total - 1
    assert bh["mdd"] == pytest.approx(hand_mdd(bh_vals), rel=1e-12)
    assert bh["ret_period"] == pytest.approx(bh_vals[-1] / bh_vals[19] - 1, rel=1e-12)
    full = R.index_bh_from_states("us", st, cut)                     # 재현 M6 이 쓰는 도우미: 매일 값 그대로
    assert full["dates"] == D[:26] and full["units"] == units and full["values"] == bh_vals
    assert R.index_bh_from_states("us", st, hs.S_A)["values"] == [total]
    # 트레이너별
    for line in d["values"]["trainers"]:
        tn = line["trainer"]
        for arm in h1.ARMS:
            rows = st[arm][tn]["days"]
            assert line[arm]["value"] == rows[-1]["value"]
            assert line[arm]["ret"] == pytest.approx(rows[-1]["value"] / st[arm][tn]["start_cash"] - 1, rel=1e-12)
            assert line[arm]["mdd"] == pytest.approx(hand_mdd([r["value"] for r in rows]), rel=1e-12)
    text = R.render(d)
    assert R.markets.money("us", v1 - v0, True) in text
    assert f"{(v1 / total - 1) * 100:+.2f}%" in text


def test_T_F8a_비율_매매_비용(built, tmp_path):
    h = built["us"]
    root = copy_of(h, tmp_path)
    st = load(root, "us").states
    d = R.collect("us", "2026-03", root=root, online=False)
    lo, hi = "2026-03-01", d["cut"]
    for arm in h1.ARMS:
        rows = {}
        for tn in h1.TRAINERS:
            for r in st[arm][tn]["days"]:
                if lo <= r["date"] <= hi:
                    acc = rows.setdefault(r["date"], [0.0, 0.0, 0.0, 0.0])
                    for i, k in enumerate(("stock_value", "idle_value", "cash", "value")):
                        acc[i] += r[k]
        fr = [(a[0] / a[3], a[1] / a[3], a[2] / a[3]) for _, a in sorted(rows.items())]
        got = d["ratios"]["period"][arm]
        assert got["n"] == len(fr) == 6
        for i in range(3):
            assert got["mean"][i] == pytest.approx(sum(x[i] for x in fr) / len(fr), rel=1e-12)
            assert got["last"][i] == pytest.approx(fr[-1][i], rel=1e-12)
        for key, lo2 in (("period", lo), ("since_s", hs.S_A)):
            t = d["trades"][key][arm]
            fills = [f for tn in h1.TRAINERS for f in st[arm][tn]["fills"] if lo2 <= f["date"] <= hi]
            assert t["stock_buy"] == sum(1 for f in fills if f["kind"] == "stock" and f["side"] == "buy")
            assert t["stock_sell"] == sum(1 for f in fills if f["kind"] == "stock" and f["side"] == "sell")
            assert t["idle_buy"] == sum(1 for f in fills if f["kind"] == "idle" and f["side"] == "buy")
            assert t["idle_sell"] == sum(1 for f in fills if f["kind"] == "idle" and f["side"] == "sell")
            assert t["delist"] == sum(1 for f in fills if f["purpose"] == "delist")
            for kind in ("stock", "idle"):
                mine = [f for f in fills if f["kind"] == kind]
                assert t["cost"][kind]["fee"] == pytest.approx(sum(f["fee"] for f in mine), abs=1e-9)
                assert t["cost"][kind]["slip"] == pytest.approx(sum(f["slip_cost"] for f in mine), abs=1e-9)
                assert t["cost"][kind]["tax"] == 0.0                  # 미국은 매도세 0
            skips = [s for tn in h1.TRAINERS for s in st[arm][tn]["skips"] if lo2 <= s["date"] <= hi]
            for k in R.SKIP_KINDS:
                assert t["skips"][k] == sum(1 for s in skips if s["kind"] == k)
            assert t["over_slots"] == sum(r["over_slots"] for tn in h1.TRAINERS for r in st[arm][tn]["days"]
                                          if lo2 <= r["date"] <= hi)
    s = d["trades"]["since_s"]
    assert s["A0"]["idle_buy"] == s["A0"]["idle_sell"] == 0 and s["A1"]["idle_sell"] > 0
    assert s["A0"]["delist"] == 2 and s["A0"]["skips"]["현금부족"] >= 1 and s["A0"]["skips"]["0주"] == 1
    assert s["A0"]["skips"]["팀장hold"] == 2 and s["A0"]["skips"]["확신도낮음"] == 2


def test_T_F8a_국내_매도세는_주식_다리만(built, tmp_path):
    h = built["kr"]
    root = copy_of(h, tmp_path)
    st = load(root, "kr").states
    d = R.collect("kr", "2026-02", root=root, online=False)
    for arm in h1.ARMS:
        t = d["trades"]["since_s"][arm]
        sells = [f for tn in h1.TRAINERS for f in st[arm][tn]["fills"] if f["kind"] == "stock" and f["side"] == "sell"
                 and f["date"] <= d["cut"]]
        assert sells and t["cost"]["stock"]["tax"] == pytest.approx(sum(f["tax"] for f in sells), abs=1e-6)
        assert t["cost"]["stock"]["tax"] > 0 and t["cost"]["idle"]["tax"] == 0.0


def test_T_F8a_실현손익_평균원가_손계산():
    def f(date, code, side, qty, cash_delta, kind="stock"):
        return {"date": date, "code": code, "kind": kind, "side": side, "qty": qty, "cash_delta": cash_delta}
    fills = [
        f("2026-01-02", "AAA", "buy", 10, -1000.0),           # 10주 원가 1,000
        f("2026-01-05", "AAA", "buy", 10, -1200.0),           # 20주 원가 2,200 → 평균 110
        f("2026-01-06", "AAA", "sell", 5, 600.0),             # 원가 550 → +50
        f("2026-02-03", "AAA", "sell", 15, 1500.0),           # 원가 1,650 → −150
        f("2026-02-03", "SPY", "buy", 2.5, -1000.0, "idle"),  # 지수 2.5단위 원가 1,000 (400/단위)
        f("2026-02-04", "SPY", "sell", 0.5, 230.0, "idle"),   # 원가 200 → +30
        f("2026-02-05", "BBB", "buy", 10, -1000.0),
        f("2026-02-09", "BBB", "sell", 20, 1100.0),           # 2:1 분할 뒤 20주 원가 1,000 그대로 → +100
    ]
    split = [{"kind": "split", "code": "BBB", "r": 2.0, "date": "2026-02-09", "applied_after": "2026-02-06"}]
    r = R.realized(fills, split)
    assert [s["gain"] for s in r["sells"]] == pytest.approx([50.0, -150.0, 30.0, 100.0])
    assert r["stock"]["total"] == pytest.approx(0.0) and r["stock"]["n_sells"] == 3
    assert r["stock"]["by_month"] == pytest.approx({"2026-01": 50.0, "2026-02": -50.0})
    assert r["stock"]["by_year"] == pytest.approx({"2026": 0.0})
    assert r["stock"]["by_code"] == pytest.approx({"AAA": -100.0, "BBB": 100.0})
    assert r["idle"]["total"] == pytest.approx(30.0) and r["idle"]["n_sells"] == 1
    assert r["open"] == {"SPY": {"kind": "idle", "qty": 2.0, "cost": pytest.approx(800.0)}}
    # 분할 없이 보면 10주를 20주 팔아 원가 전부(1,000)가 빠진다 — 분할 반영 여부가 결과를 바꾼다
    assert R.realized(fills)["stock"]["by_code"]["BBB"] == pytest.approx(100.0)
    assert R.realized(fills)["open"].get("BBB") is None


def test_T_F8a_실현손익_장면_항등식(built, tmp_path):
    """장부마다: 평가액 − 시작 금액 == 실현손익(주식+지수) + (남은 보유 평가 − 남은 원가). 분할(BBB)·상장폐지(CCC) 포함."""
    root = copy_of(built["us"], tmp_path)
    st = load(root, "us").states
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            led = st[arm][tn]
            r = R.realized(led["fills"], led["corp_actions"])
            last = led["days"][-1]
            mv = 0.0
            for code, p in r["open"].items():
                px = last["idle_close"] if p["kind"] == "idle" else last["marks"][code]
                mv += p["qty"] * px
                held = led["wallet"].holdings[code].shares
                assert p["qty"] == pytest.approx(held, rel=1e-12)
            lhs = last["value"] - led["start_cash"]
            rhs = r["stock"]["total"] + r["idle"]["total"] + mv - sum(p["cost"] for p in r["open"].values())
            assert lhs == pytest.approx(rhs, abs=1e-6), (arm, tn)
    d = R.collect("us", root=root, online=False)
    a1 = d["realized"]["A1"]
    assert a1["idle"]["n"] > 0 and a1["stock"]["since_s"] == pytest.approx(d["realized"]["A0"]["stock"]["since_s"],
                                                                         abs=1e-6)
    text = R.render(d)
    assert R.US_TAX_NOTE in text


def test_T_F8a_팀장_수와_폴백_20퍼센트(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    d = R.collect("us", "2026-03", root=root, online=False)
    recs = [r for r in h1.DecisionLog(h1.decisions_path(root, "us"), read_only=True).records()
            if r["market"] == "us" and hs.S_A <= r["date"] <= d["cut"]]
    ld = d["leader"]
    assert ld["n"] == len(recs) > 0
    fb = sum(1 for r in recs if r["status"] != "ok")
    assert ld["fallback"] == fb == 1                               # 늦은 봉(D11)의 late_no_llm 하나
    assert ld["ratio"] == fb / len(recs) and not ld["unrepresentative"]
    vs = {}
    for r in recs:
        k = (r["verdict"] or "없음", r["source"])
        vs[k] = vs.get(k, 0) + 1
    assert ld["by_verdict"] == dict(sorted(vs.items()))
    assert ld["by_verdict"][("veto", "llm")] == 1 and ld["by_verdict"][("hold", "llm")] == 2
    assert ld["first_cli"] == tr.CLI_VER and ld["changes"] == []
    text = R.render(d)
    assert "**팀장 판정 대표성 없음**" not in text and "폴백 비율 5.0%" in text
    # 국내: 팀장이 늘 시간 초과 → 폴백 100% > 20% → "팀장 판정 대표성 없음"
    rk = copy_of(built["kr"], tmp_path, "kr")
    dk = R.collect("kr", root=rk, online=False)
    assert dk["leader"]["ratio"] == 1.0 and dk["leader"]["unrepresentative"]
    assert dk["leader"]["by_status"] == {"timeout": dk["leader"]["n"]}
    assert "**팀장 판정 대표성 없음**" in R.render(dk)


class _FakeDec:
    def __init__(self, recs):
        self._r, self.truncated = recs, None

    def records(self):
        return list(self._r)


class _FakeCtx:
    mk = "us"

    def __init__(self, recs, used_keys):
        self.decisions = _FakeDec(recs)
        self.states = {arm: {tn: {"days": []} for tn in h1.TRAINERS} for arm in h1.ARMS}
        # 이 창이 쓴 기록 = 하루 기록 팀장 칸의 열쇠(A0 는 앞 절반, A1 은 나머지 — 두 장부 합집합)
        half = len(used_keys) // 2
        for arm, ks in (("A0", used_keys[:half]), ("A1", used_keys[half:])):
            self.states[arm]["마라토너"]["days"] = [{"date": "2026-02-03", "leader": [{"key": k} for k in ks]}]

    def rule(self, key, default):
        return default


@pytest.mark.parametrize("n_fb,n,flag", [(1, 5, False), (2, 10, False), (2, 9, True), (3, 10, True)])
def test_T_F8a_폴백_20퍼센트_경계(n_fb, n, flag):
    recs = [{"key": f"us|2026-02-03|마라토너|C{i}", "market": "us", "date": "2026-02-03",
             "status": "timeout" if i < n_fb else "ok",
             "source": "fallback" if i < n_fb else "llm", "verdict": None if i < n_fb else "buy"} for i in range(n)]
    # 같은 날짜 범위지만 이 창의 하루 기록이 쓰지 않은 폴백 기록(재시작 전 창 등) → 세지 않음
    extra = [{"key": f"us|2026-02-03|스프린터|X{i}", "market": "us", "date": "2026-02-03", "status": "timeout",
              "source": "fallback", "verdict": None} for i in range(5)]
    ld = R._leader(_FakeCtx(recs + extra, [r["key"] for r in recs]), "2026-02-02", "2026-02-28")
    assert ld["n"] == n and ld["fallback"] == n_fb and ld["unrepresentative"] is flag   # 20% 를 '넘을 때'만
    assert ld["unused"] == 5 and ld["missing"] == 0


def test_T_F8a_운영_기준_칸(built, tmp_path):
    h = built["us"]
    root = copy_of(h, tmp_path)
    D = h.D
    ops = R.collect("us", root=root, online=False)["ops"]
    assert ops["n_bars"] == 26 and ops["bars_left"] == 63 - 26
    assert ops["late"] == [D[11]] and ops["batch_max"] == 2
    assert ops["missing"] == [] and ops["extra"] == [] and ops["ledger_dates_differ"] == []
    assert ops["gate_refused"] == 1
    assert ops["data_stops"] == 3 and ops["data_kinds"] == {"D2": 1, "D3": 1, "D6": 1}
    assert ops["l_errors"] == 0 and ops["restarts_used"] == 0 and ops["restarts_left"] == 2
    assert {k: len(v) for k, v in ops["corp"].items()} == {"split": 1, "delist": 1, "delist_cancel": 0, "correction": 0}
    assert ops["other_fp"] == h.D[:26]                             # 재현 통과 기록 없음(관문 끈 시험) → 모두 '다른 지문'
    assert ops["deadline"] == "2027-06-30" and ops["days_to_deadline"] == (
        pd.Timestamp("2027-06-30") - pd.Timestamp(D[25])).days
    # 빠진 날: calendar.jsonl 정상 줄에 하루 기록에 없는 날이 있으면 센다
    cal = fs.read_lines(root / "us" / "calendar.jsonl")[-1]
    jline(root / "us" / "calendar.jsonl", {**cal, "dates": sorted(cal["dates"] + ["2026-02-14"]), "check": "ok"})
    # 자료 멈춤 종류별: 4(PRE·ENV)·7(D7). 마지막 저장 봉(3월 9일) 뒤의 실행이라 '처리하려던 봉'은 다음 거래일.
    # D7 은 문제에 날짜(3월 10일)가 있어 3월로 셈. PRE·ENV 는 날짜·달력 줄이 없어 아직 어느 달인지 모름(따로 셈).
    S = hs.S_A
    for kind, code, date in (("PRE", 4, None), ("ENV", 4, None), ("D7", 7, "2026-03-10")):
        jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S,
                                    "at": "2026-03-10T07:10:00+09:00", "exit_code": code, "bars": [],
                                    "problems": [{"level": "D", "code": kind, "date": date}]})
    jline(root / "errors.jsonl", {"market": "us", "start_date": "unknown", "at": "2026-03-10T07:11:00+09:00",
                                  "date": None, "problems": [{"level": "L", "code": "L24"}]})
    jline(root / "errors.jsonl", {"market": "us", "start_date": "2025-01-01", "at": "2026-03-10T07:11:00+09:00",
                                  "date": None, "problems": [{"level": "L", "code": "L7"}]})   # 다른 창 → 안 셈
    jline(root / "errors.jsonl", {"market": "us", "start_date": "unknown", "at": "2026-03-10T07:12:00+09:00",
                                  "date": "2026-03-10", "problems": [{"level": "L", "code": "L9"}]})
    d = R.collect("us", root=root, online=False)
    ops = d["ops"]
    assert ops["missing"] == ["2026-02-14"]
    assert ops["data_stops"] == 4 and ops["data_kinds"] == {"D2": 1, "D3": 1, "D6": 1, "D7": 1}
    assert ops["l_errors"] == 1 and ops["l_codes"] == {"L9": 1}
    assert ops["unknown"] == {"자료 멈춤(4·7)": 2, "장부 논리 오류(L)": 1}
    text = R.render(d)
    assert "빠진 날(calendar.jsonl vs 하루 기록) | 1개 (2026-02-14)" in text
    assert ops["data_by_exit"] == {4: {"n": 3, "kinds": {"D2": 1, "D3": 1, "D6": 1}}, 7: {"n": 1, "kinds": {"D7": 1}}}
    assert ("자료 멈춤(종료 코드 4·7) | 4번 — 종료 코드 4(자료 D1~D6·사전 조건 PRE·환경 ENV) 3번: D2 1, D3 1, D6 1 / "
            "종료 코드 7(기준 지수 늦음) 1번: D7 1 (재시작 아님)") in text
    assert ("| 어느 달인지 모름(처리하려던 봉을 아직 모름 — 이 달 숫자에 안 넣음) | 자료 멈춤(4·7) 2, "
            "장부 논리 오류(L) 1 |") in text
    assert "관문 거절(종료 코드 3: 재현 미통과 코드·환경 또는 규칙 다름) | 1번" in text
    assert "늦은 봉(다음 장 시작 뒤 처리) | 1개 / 상한 10" in text
    assert "| 한 번에 따라잡은 최대 봉 수 | 2봉 / 상한 5 |" in text
    assert "| 재시작 | 0번 / 상한 2 (남은 2번) |" in text
    assert f"| 판정 창 진행 | 26/63봉 · 시작 S {S} · S+62 예정" in text
    assert "| 끝 기록 없는 실행(kill·전원 꺼짐 — 판정에는 안 씀) | 0번 |" in text
    assert "기업 행위(장부 corp_actions 기준): 분할 1건 · 상장폐지 1건 · 정정 확정 0건" in text
    assert "코드·규칙 변경 일지(changes.jsonl, 이 창이 만들어진 뒤 ~ 2026-03-09 저장 때): 기업 행위 상장폐지 1, 기업 행위 분할 1" in text
    # 덜 찬 창의 --final(지금까지 전부)은 어느 달인지 모르는 줄도 이 창의 것으로 넣는다
    f = R.collect("us", final=True, root=root, online=False)["ops"]
    assert f["data_stops"] == 6 and f["data_kinds"] == {"D2": 1, "D3": 1, "D6": 1, "D7": 1, "ENV": 1, "PRE": 1}
    assert f["l_errors"] == 2 and f["l_codes"] == {"L24": 1, "L9": 1} and f["unknown"] == {}


def test_T_F8a_장부_다시_점검_결과와_못_보는_점검(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    d = R.collect("us", root=root, online=False)
    assert d["recheck"]["n"] == 0 and d["recheck"]["universe_ok"] is True
    text = R.render(d)
    assert "**L 오류 0건**" in text and "L3(주식 체결가" in text and "D1~D7" in text


# ============================ T-SHADOW · T-START ============================

def test_T_SHADOW_보고서_첫_발동일과_날_수(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    st = load(root, "us").states
    d = R.collect("us", root=root, online=False)
    cb = CircuitBreaker(*h1.SHADOW_BREAKER)
    hit_any = False
    for s in d["shadow"]:
        rows = st[s["arm"]][s["trainer"]]["days"]
        prev, hits = None, []
        for r in rows:
            why = cb.check(st[s["arm"]][s["trainer"]]["start_cash"], prev, r["value"])
            if why:
                hits.append((r["date"], why))
            prev = r["value"]
        assert s["days"] == len(hits)
        assert s["first"] == (hits[0][0] if hits else None) == s["flag_first"]
        assert s["why"] == (hits[0][1] if hits else None)
        hit_any = hit_any or bool(hits)
    assert hit_any
    a1 = [s for s in d["shadow"] if s["arm"] == "A1" and s["first"]]
    assert a1 and all(s["first"] == built["us"].D[21] for s in a1)   # SPY −15% 날
    text = R.render(d)
    for s in a1:
        assert f"| A1 {s['trainer']} | {s['first']} |" in text


def test_T_START_지수_BH_는_S_날_총액_S1_시가에서_시작(tmp_path):
    h = tr.us_h(tmp_path)
    assert h.start() == 0
    d = R.collect("us", root=h.root, online=False)
    bh = d["values"]["bh"]
    assert not bh["started"] and bh["value"] == 100_000.0 and bh["units"] is None
    assert "아직 없음(S+1 시가에 시작)" in R.render(d)
    assert h.run(h.D[1]) == 0
    d = R.collect("us", root=h.root, online=False)
    row = load(h.root, "us").states["A0"]["마라토너"]["days"][1]
    units = 100_000 / (row["idle_open"] * (1 + US.slippage) * (1 + US.fee_rate))
    assert d["values"]["bh"]["units"] == units and d["values"]["bh"]["value"] == units * row["idle_close"]
    # MDD 는 S 종가(= 시작 금액)부터 잰다: S+1 에 지수를 사며 낸 비용만큼 내려간 것도 낙폭이다(R2 처럼 첫 값부터)
    st = load(h.root, "us").states
    for arm in h1.ARMS:
        _, vals = team_values(st, arm)
        assert vals[0] == 100_000.0 and d["values"]["arms"][arm]["mdd"] == metrics.max_drawdown(vals)
    a1 = d["values"]["arms"]["A1"]
    assert a1["value"] < 100_000.0                       # 이 장면: S+1 에 지수를 사며 낸 비용 + 그날 움직임으로 시작 금액 아래
    assert a1["mdd"] < 0 and a1["mdd"] == pytest.approx(a1["value"] / 100_000.0 - 1, rel=1e-12)
    res = R.index_buy_hold_same_start([500.0, 400.0, 420.0], [510.0, 410.0, 380.0], 1000.0, 0.001, 0.0005)
    u = 1000.0 / (400.0 * 1.0005 * 1.001)
    assert res["values"] == [1000.0, u * 410.0, u * 380.0] and res["units"] == u
    assert res["return"] == u * 380.0 / 1000.0 - 1 and res["mdd"] == metrics.max_drawdown(res["values"])


# ============================ T-F8b 금리 규칙 · 이자 ============================

def _us_rates(days):
    """2026-01-26 ~ 2026-03-05 평일 금리(날짜마다 다른 값), 2026-02-02·2026-02-16 은 '.'(휴장)."""
    rows = []
    for i, x in enumerate(pd.bdate_range("2026-01-26", "2026-03-05")):
        dd = x.date().isoformat()
        rows.append((dd, "." if dd in ("2026-02-02", "2026-02-16") else f"{3.5 + i / 100:.2f}"))
    return rows


def _hand_asof(rows, key):
    got = [(dd, float(v)) for dd, v in rows if v != "." and dd <= key]
    return got[-1] if got else (None, math.nan)


def test_T_F8b_미국_전_거래일_규칙과_이자_손계산(built, tmp_path):
    h = built["us"]
    root = copy_of(h, tmp_path)
    rows = _us_rates(None)
    R.store_rates("DTB3", root / "rates", fred_csv(rows).encode(), "2026-03-10T08:00:00+09:00", "가짜 주소")
    st = load(root, "us").states
    d = R.collect("us", "2026-03", root=root, online=False)
    it = d["interest"]
    assert it["ok"] and it["mode"] == "offline" and it["fetched_at"] == "2026-03-10T08:00:00+09:00"
    assert it["first_rate"] == "2026-01-26" and it["last_rate"] == "2026-03-05"
    days0 = st["A0"]["마라토너"]["days"]
    # 손계산: 금리 = 하루 기록 prev_cal_date 이하 마지막 값(S 날도), q = r/100/252, I = I·(1+q) + C·q
    acc, table = 0.0, []
    for r in days0:
        key = r["prev_cal_date"]
        got, rate = _hand_asof(rows, key)
        cash = sum(x["cash"] for tn in h1.TRAINERS for x in st["A0"][tn]["days"] if x["date"] == r["date"])
        q = rate / 100 / 252
        acc = acc * (1 + q) + cash * q
        table.append((r["date"], key, got, rate, acc))
    assert table[0][1] == "2026-01-30"                                     # S 날 = 저장 달력의 S 전 거래일
    assert table[1][2] == "2026-01-30"                                     # 2026-02-02 '.' → 직전 값 이월
    assert table[2][2] == "2026-02-03"                                     # 그날 값은 다음 날에 쓰임
    mar = [x for x in table if x[0] >= "2026-03-01"]
    assert [(x["date"], x["key"], x["rate_date"]) for x in it["table"]] == [x[:3] for x in mar]
    for got, want in zip(it["table"], mar):
        assert got["rate"] == want[3] and got["interest"] == pytest.approx(want[4], rel=1e-12)
    assert it["interest"] == pytest.approx(table[-1][4], rel=1e-12)
    res = R.a0_interest("us", st, R.load_rates("DTB3", root / "rates"))     # 재현 M7 이 쓰는 도우미
    assert res["dates"] == [x[0] for x in table] and res["keys"] == [x[1] for x in table]
    assert res["rate_dates"] == [x[2] for x in table] and res["rates"] == [x[3] for x in table]
    assert res["interest"] == pytest.approx([x[4] for x in table], rel=1e-12) and res["prev_mismatch"] == []
    feb_last = [x for x in table if x[0] < "2026-03-01"][-1][4]
    assert it["interest_period"] == pytest.approx(table[-1][4] - feb_last, rel=1e-9)
    v0 = d["values"]["arms"]["A0"]["value"]
    assert it["a0_plus"] == pytest.approx(v0 + table[-1][4], rel=1e-12)
    # 2026-03-06 이후 기준 날짜(자료 끝 2026-03-05 뒤) → 이월 + 오프라인 표시
    late_rows = [x for x in it["table"] if x["key"] > "2026-03-05"]
    assert late_rows and all(x["rate_date"] == "2026-03-05" for x in late_rows)
    assert all("(오프라인: 2026-03-05 값 이월)" in x["note"] for x in late_rows)
    text = R.render(d)
    assert "받은 시각 2026-03-10T08:00:00+09:00" in text and "**근사**" in text
    assert "| 2026-03-02 | 2026-02-27 | 2026-02-27 |" in text


def test_T_F8b_국내_전달_규칙과_빈_달_이월(built, tmp_path):
    h = built["kr"]
    root = copy_of(h, tmp_path)
    (root / "rates").mkdir()
    src = "FRED IR3TIB01KRM156N (시험)"
    (root / "rates" / "kr_shortrate.csv").write_text(   # R2 형식·R2 이름(재현이 복사해 둔 첫 저장본 모양), 2026-01 없음
        "date,rate_pct,source,frequency\n"
        f"2025-11-01,2.70,\"{src}\",monthly\n2025-12-01,2.80,\"{src}\",monthly\n2026-02-01,2.95,\"{src}\",monthly\n",
        encoding="utf-8")
    st = load(root, "kr").states
    d = R.collect("kr", "2026-03", root=root, online=False)
    it = d["interest"]
    assert it["ok"] and it["format"] == "r2" and it["fetched_at"] is None and it["path"] == "kr_shortrate.csv"
    days0 = st["A0"]["마라토너"]["days"]
    acc, want = 0.0, []
    for r in days0:
        if r["date"] < "2026-03-01":
            key, got, rate = "2026-01-01", "2025-12-01", 2.80          # 2월 → 1월 값 없음 → 2025-12 값 이월
        else:
            key, got, rate = "2026-02-01", "2026-02-01", 2.95
        cash = sum(x["cash"] for tn in h1.TRAINERS for x in st["A0"][tn]["days"] if x["date"] == r["date"])
        q = rate / 100 / 252
        acc = acc * (1 + q) + cash * q
        want.append((r["date"], key, got, rate, acc))
    mar = [x for x in want if x[0] >= "2026-03-01"]
    assert [(x["date"], x["key"], x["rate_date"], x["rate"]) for x in it["table"]] == [x[:4] for x in mar]
    assert it["interest"] == pytest.approx(want[-1][4], rel=1e-12)
    feb = R.collect("kr", "2026-02", root=root, online=False)["interest"]
    assert all(x["note"] == "전달(2026-01) 값 없음 → 2025-12 값 이월" for x in feb["table"])
    assert all(x["note"] == "전달(2026-02) 값 사용(월 금리)" for x in it["table"])
    assert "받은 시각 기록 없음" in R.render(d)


def test_T_F8b_이자_식_손계산():
    acc = R.interest_overlay(["a", "b", "c"], [1000.0, 2000.0, 0.0], [5.04, float("nan"), 2.52])
    q1, q3 = 5.04 / 100 / 252, 2.52 / 100 / 252
    i1 = 1000.0 * q1
    i2 = i1                                     # 금리 NaN → 0 (R2 rate_missing 과 같음)
    i3 = i2 * (1 + q3) + 0.0 * q3
    assert acc == [i1, i2, i3]
    with pytest.raises(ValueError):
        R.interest_overlay(["a"], [1.0, 2.0], [1.0])


def r2_asof(series, keys):
    """R2 sim_team._asof 그대로 옮김(기준)."""
    keys = pd.DatetimeIndex(keys)
    pos = series.index.searchsorted(keys, side="right") - 1
    vals = series.to_numpy(float)
    return np.where(pos >= 0, vals[np.clip(pos, 0, None)], np.nan)


def r2_rate_for_days(cal, series, rule):
    """R2 sim_team.rate_for_days 그대로 옮김(기준)."""
    if rule == "prev_day":
        out = r2_asof(series, cal[:-1])
        return np.concatenate(([np.nan], out))
    if rule == "prev_month":
        first_of_prev = (cal.to_period("M") - 1).to_timestamp()
        return r2_asof(series, first_of_prev.values)
    raise ValueError(rule)


def _same(a, b):
    return len(a) == len(b) and all((math.isnan(x) and math.isnan(y)) or x == y for x, y in zip(a, b))


@pytest.mark.parametrize("rule", ["prev_day", "prev_month"])
def test_T_F8b_R2_rate_for_days_와_같은_결과_옮긴_식(rule):
    cal = pd.bdate_range("2025-10-01", "2026-04-30")
    rng = np.random.default_rng(7)
    if rule == "prev_day":
        idx = [d for d in pd.bdate_range("2025-10-15", "2026-03-20") if rng.random() > 0.2]   # 빈 날 섞임
    else:
        idx = [pd.Timestamp(m) for m in ("2025-08-01", "2025-09-01", "2025-11-01", "2026-01-01", "2026-02-01")]
    vals = np.round(rng.uniform(1, 5, len(idx)), 2)
    vals[3] = np.nan                                                         # 값 자체가 NaN 인 줄도 같게
    series = pd.Series(vals, index=pd.DatetimeIndex(idx))
    want = list(r2_rate_for_days(cal, series, rule))
    got = R.rate_for_days([d.date().isoformat() for d in cal], series, rule)
    assert _same(got, want)
    assert _same(R.rate_for_days(list(cal), series, rule), want)            # 날짜 객체도 받음
    assert any(math.isnan(x) for x in want) and any(not math.isnan(x) for x in want)


R2_REF = "origin/research-r2-2026-11-04"
R2_DIR = "reports/research-r2-2026-11-04"

# R2 sim_team 을 따로 프로세스(python -I)에서 불러 값을 JSON 으로 내보내는 하네스. 시험이 tmp 에 써서 쓴다(저장소에 두지 않음).
# 첫 인자 = 풀어 둔 R2 의 reports/research-r2-2026-11-04, 둘째 인자 = 결과 JSON 경로. float 는 hex 로(비트까지 비교).
R2_PROBE = """
import json, sys
from pathlib import Path
from types import SimpleNamespace
R2DIR = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(R2DIR))
import pandas as pd
import sim_team, main, markets
TOP = R2DIR.parents[1]
for m in (sim_team, main, markets):                      # 지금 저장소 모듈을 잘못 읽으면 '자기와 비교'가 됨(설계 §7 R22)
    assert Path(m.__file__).resolve().is_relative_to(TOP), m.__file__
out = {}
for key in ("us", "kr"):
    idx, _frames, rates, rule, _zv = sim_team.load_frames(key)
    cal = idx.index
    r = sim_team.rate_for_days(cal, rates, rule)
    mk = markets.MARKETS[key]
    md = SimpleNamespace(idx_open=idx["Open"].to_numpy(float), idx_close=idx["Close"].to_numpy(float),
                         idx_fee=mk.fee_rate, idx_slip=mk.slippage)       # MarketData 의 지수 칸과 같은 값
    i0 = int(cal.searchsorted(pd.Timestamp("2026-06-01")))               # 재현 W1 창(설계 §5.2)
    i1 = int(cal.searchsorted(pd.Timestamp("2026-11-03"), side="right")) - 1
    bh = sim_team.index_buy_hold_fractional(md, i0 + 1, i1, sim_team.TOTALS[key])
    out[key] = {"rule": rule, "dates": [d.date().isoformat() for d in cal], "rates": [float(x).hex() for x in r],
                "series": [[d.date().isoformat(), float(v).hex()] for d, v in rates.items()],
                "i0": i0, "i1": i1, "total": sim_team.TOTALS[key], "fee": mk.fee_rate, "slip": mk.slippage,
                "opens": [float(x).hex() for x in md.idx_open], "closes": [float(x).hex() for x in md.idx_close],
                "bh_units": float(bh["units"]).hex(), "bh_equity": [float(x).hex() for x in bh["equity"]]}
Path(sys.argv[2]).write_text(json.dumps(out), encoding="utf-8")
"""


def _r2_tree(dst):
    """R2 브랜치를 dst(빈 새 폴더)에 푼다(git archive → tarfile, 위험한 경로는 filter='data' 가 막음). 못 하면 None."""
    import tarfile
    try:
        p = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", R2_REF], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    dst.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(dst, filter="data")
    return dst / R2_DIR


def test_T_F8b_R2_sim_team_을_python_I_로_부른_결과와_같음(tmp_path):
    """R2 브랜치를 tmp 에 풀고 sim_team 을 따로 프로세스(python -I)에서 불러, 전체 달력의 rate_for_days 와
    재현 W1 창의 index_buy_hold_fractional(md, i0+1, i1, total) 을 받아 보고서 함수와 비트까지 비교한다(재현 M6·M7 과 같은 비교).
    금리는 R2 data/rates 파일을 보고서의 load_rates 로 읽은 것(R2 이름 그대로의 복사본 = 재현이 만드는 첫 저장본 모양)을 쓴다.
    R2 브랜치가 없으면 건너뜀(git fetch origin research-r2-2026-11-04 필요)."""
    r2 = _r2_tree(tmp_path / "r2")
    if r2 is None:
        pytest.skip("R2 브랜치를 읽을 수 없음(git fetch origin research-r2-2026-11-04 필요)")
    probe = tmp_path / "probe" / "r2_probe.py"
    probe.parent.mkdir()
    probe.write_text(R2_PROBE, encoding="utf-8")
    out_json = tmp_path / "probe" / "out.json"
    p = subprocess.run([sys.executable, "-I", str(probe), str(r2), str(out_json)], cwd=str(tmp_path / "probe"),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(out_json.read_text(encoding="utf-8"))
    fx = lambda xs: [float.fromhex(x) for x in xs]                      # noqa: E731
    for key, sid in (("us", "DTB3"), ("kr", "IR3TIB01KRM156N")):
        o = out[key]
        assert o["rule"] == R.RULE[key]
        info = R.rates_info(sid, r2 / "data" / "rates")
        assert info["ok"] and info["format"] == "r2" and info["file"] == R.R2_RATE_NAMES[sid]
        series = info["series"]
        assert [[d.date().isoformat(), float(v)] for d, v in series.items()] == \
            [[d, float.fromhex(v)] for d, v in o["series"]]                 # 같은 파일을 같은 값으로 읽음
        got = R.rate_for_days(o["dates"], series, o["rule"])
        want = fx(o["rates"])
        assert len(got) > 2900 and _same(got, want)
        # 지수 B&H (W1): 단위 비트까지 같음, 매일 값 같음, 마지막 날은 R2 가 매도 비용을 뺀 값(M6) → 단위 × 종가로
        i0, i1 = o["i0"], o["i1"]
        opens, closes = fx(o["opens"]), fx(o["closes"])
        mine = R.index_buy_hold_same_start(opens[i0:i1 + 1], closes[i0:i1 + 1], o["total"], o["fee"], o["slip"])
        eq = fx(o["bh_equity"])
        assert mine["units"] == float.fromhex(o["bh_units"]) and mine["values"][0] == o["total"]
        assert len(mine["values"]) == len(eq) + 1 and mine["values"][1:-1] == eq[:-1]
        assert mine["values"][-1] == mine["units"] * closes[i1] and eq[-1] < mine["values"][-1]
        # 보고서 S 날 금리(prev_day: 저장 달력의 S 전 거래일 이하 마지막 값) == R2 전체 달력의 i0 번째 값
        if o["rule"] == "prev_day":
            cal = [o["dates"][i0 - 1]] + o["dates"][i0:i1 + 1]
            assert _same(R.rate_for_days(cal, series, "prev_day")[1:], want[i0:i1 + 1])
        else:
            assert _same(R.rate_for_days(o["dates"][i0:i1 + 1], series, "prev_month"), want[i0:i1 + 1])


def test_T_F8b_금리_파일_두_형식과_빈값():
    t, fmt = R._parse_rates("observation_date,DTB3\n2026-01-02,3.61\n2026-01-05,.\n2026-01-06,\n2026-01-07,3.60\n",
                            "DTB3")
    assert fmt == "fred" and t == [("2026-01-02", 3.61), ("2026-01-07", 3.60)]
    t, fmt = R._parse_rates("DATE,DTB3\n2026-01-02,3.61\n")
    assert fmt == "fred" and t == [("2026-01-02", 3.61)]
    t, fmt = R._parse_rates('date,rate_pct,source\n2026-01-05,3.6,"FRED DTB3 (x, y)"\n2026-01-02,3.61,"s"\n')
    assert fmt == "r2" and t == [("2026-01-02", 3.61), ("2026-01-05", 3.6)]
    for bad in ("x,y\n1,2\n", "observation_date,DTB3\n2026-13-01,3\n", "observation_date,DTB3\n2026-01-02,nan\n"):
        with pytest.raises(ValueError):
            R._parse_rates(bad, "DTB3")
    with pytest.raises(ValueError):
        R._parse_rates("observation_date,IR3TIB01KRM156N\n2026-01-01,3\n", "DTB3")    # 다른 시리즈


# ============================ T-F8c 오프라인 ============================

class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_T_F8c_받기_실패면_저장본과_오프라인_표시(built, tmp_path, monkeypatch):
    root = copy_of(built["us"], tmp_path)
    R.store_rates("DTB3", root / "rates", fred_csv(_us_rates(None)).encode(), "2026-03-01T08:00:00+09:00")
    before = fs.file_sha(root / "rates" / "DTB3.csv")
    calls = []

    def fail(req, timeout=None):
        calls.append((req.full_url, timeout))
        raise urllib.error.URLError("인터넷 없음(시험)")
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    p = R.write("us", root=root, online=True)
    assert calls == [(R.FRED_URL.format("DTB3"), 20)]
    assert fs.file_sha(root / "rates" / "DTB3.csv") == before                 # 저장본 그대로
    text = p.read_text(encoding="utf-8")
    assert "오프라인(받기 실패): 저장본만 봄" in text and "(오프라인: 2026-03-05 값 이월)" in text
    assert "받은 시각 2026-03-01T08:00:00+09:00" in text and "A0+이자" in text


def test_T_F8c_저장본도_없으면_그_절만_계산_불가(built, tmp_path, monkeypatch):
    root = copy_of(built["us"], tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("없음")))
    p = R.write("us", "2026-02", root=root, online=True)
    assert p == root / "reports" / "us-2026-02.md" and p.exists()
    text = p.read_text(encoding="utf-8")
    assert "금리 자료 없음 → 계산 불가" in text
    for sec in ("## 2. 운영 기준", "## 3. 값", "## 5. 매매", "## 8. 팀장", "## 10. 장부 다시 점검", "## 11. 한계"):
        assert sec in text
    assert not (root / "rates" / "DTB3.csv").exists()


def test_T_F8c_offline_이면_받지_않음_받으면_받은_시각(built, tmp_path, monkeypatch):
    root = copy_of(built["us"], tmp_path)
    R.write("us", root=root, online=False)                                 # 가드: urlopen 을 부르면 NoNet
    body = fred_csv(_us_rates(None) + [("2026-03-06", "3.90"), ("2026-03-09", ".")]).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp(body))
    p = R.write("us", root=root, online=True)
    side = json.loads((root / "rates" / "DTB3.json").read_text(encoding="utf-8"))
    assert side["series_id"] == "DTB3" and side["last"] == "2026-03-06" and side["url"] == R.FRED_URL.format("DTB3")
    assert side["sha256"] == fs.file_sha(root / "rates" / "DTB3.csv")
    text = p.read_text(encoding="utf-8")
    assert f"받은 시각 {side['fetched_at']}" in text and "인터넷에서 새로 받음" in text and "(오프라인:" not in text
    # 짧아진 자료는 저장본을 덮지 않음
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp(fred_csv(_us_rates(None)[:5]).encode()))
    assert R.fetch_rates("DTB3", root / "rates") is None
    assert json.loads((root / "rates" / "DTB3.json").read_text(encoding="utf-8"))["last"] == "2026-03-06"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp(b"<html>bad</html>"))
    assert R.fetch_rates("DTB3", root / "rates") is None


def test_T_F8c_깨진_저장본은_건너뛰고_R2_이름_복사본을_씀(built, tmp_path):
    d = tmp_path / "rates"
    d.mkdir()
    (d / "DTB3.csv").write_text("<html>깨짐</html>\n", encoding="utf-8")
    (d / "us_tbill.csv").write_text('date,rate_pct,source\n2026-01-02,3.6,"s"\n', encoding="utf-8")
    info = R.rates_info("DTB3", d)
    assert info["ok"] and info["file"] == "us_tbill.csv" and info["skipped"][0].startswith("DTB3.csv: 깨짐")
    (d / "us_tbill.csv").unlink()
    info = R.rates_info("DTB3", d)
    assert not info["ok"] and info["series"] is None and "쓸 수 있는 금리 저장본이 없음" in info["why"]
    assert R.load_rates("DTB3", d) is None
    root = copy_of(built["us"], tmp_path)
    (root / "rates").mkdir()
    (root / "rates" / "DTB3.csv").write_text("<html>깨짐</html>\n", encoding="utf-8")
    text = R.build("us", root=root, online=False)
    assert "금리 자료 없음 → 계산 불가 (쓸 수 있는 금리 저장본이 없음 — DTB3.csv: 깨짐" in text
    assert "## 10. 장부 다시 점검" in text


# ============================ --final ============================

def _verdict(root, **kw):
    d = R.collect("us", final=True, root=root, online=False, **kw)
    return d, d["verdict"]


def test_final_창이_덜_찼으면_판정하지_않음(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    d, v = _verdict(root)
    assert not d["complete"] and v["result"] == "not_finished" and v["passed"] is None
    p = R.write("us", final=True, root=root, online=False)
    assert p.name == f"us-final-{hs.S_A}.md"
    text = p.read_text(encoding="utf-8")
    assert f"**아직 판정 창이 끝나지 않음** — 처리 26/63봉, 남은 봉 37개" in text
    assert "②-1 장부 논리 오류" not in text and "운영 기준 통과" not in text and "H1 포워드 실패" not in text


def test_final_깨끗한_창은_통과(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    d, v = _verdict(root)
    assert d["complete"] and d["s62"] == h.D[62] and d["cut"] == h.D[62]
    assert v["result"] == "pass" and v["passed"] and v["c1"]["ok"] and v["c2"]["ok"] and v["c3"]["ok"], v
    assert d["ops"]["other_fp"] == [] and d["ops"]["n_bars"] == 63 and d["ops"]["window_end"] == h.D[62]
    assert d["extension"] == {**d["extension"], "n": 3, "first": h.D[63], "last": h.D[65]}
    text = R.render(d)
    assert "**운영 기준 통과**" in text and "## 연장 기록 (S+62 뒤" in text
    assert "| ②-1 장부 논리 오류 0건 | 통과 |" in text and "| ②-3 재현을 통과한 코드·환경만 | 통과 |" in text
    assert "| ① 판정 창 63봉(S ~ S+62)을 다 처리함 | 통과 | 처리 63/63봉 |" in text
    assert "| ③ 수익률은 기록만 | 판정에 안 씀 |" in text
    assert text.index("## 판정") < text.index("## 2. 운영 기준 (판정 창 안: S") < text.index("## 3. 값")
    # 값은 판정 창(S~S+62)까지만
    st = load(root, "us").states
    _, vals = team_values(st, "A1", h.D[62])
    assert d["values"]["arms"]["A1"]["value"] == pytest.approx(vals[-1], rel=1e-12)
    # 재현 통과 기록이 없으면 ②-3 실패
    (root / "replay_pass.json").unlink()
    (root / "replay_pass.seal.json").unlink()
    _, v = _verdict(root)
    assert not v["c3"]["ok"] and v["result"] == "fail_window"


def _end_at(root, bar):
    return next(r["at"] for r in fs.read_lines(root / "runs.jsonl")
                if r.get("event") == "end" and bar in (r.get("bars") or []))


@pytest.mark.parametrize("case", ["L오류", "늦은봉11", "한번에6봉", "밀린봉_종료6", "다른지문", "빠진날"])
def test_final_운영_기준_어기면_창_실패(built, tmp_path, case):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    D, S = h.D, hs.S_A
    mid_at = _end_at(root, D[30])
    if case == "L오류":
        jline(root / "errors.jsonl", {"market": "us", "start_date": S, "at": mid_at, "date": D[31],
                                      "problems": [{"level": "L", "code": "L7", "detail": "시험"}]})
    elif case == "늦은봉11":
        def late(states):
            for arm in h1.ARMS:
                for tn in h1.TRAINERS:
                    for r in states[arm][tn]["days"]:
                        if D[1] <= r["date"] <= D[11]:
                            r["late"] = True
        recommit(root, "us", late)
    elif case == "한번에6봉":
        jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S, "at": mid_at,
                                    "exit_code": 0, "bars": D[20:26], "code_hash": h1.code_hash()[0],
                                    "env": h1.env_info()})
    elif case == "밀린봉_종료6":
        jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S, "at": mid_at,
                                    "exit_code": 6, "bars": []})
    elif case == "다른지문":
        jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S, "at": mid_at,
                                    "exit_code": 0, "bars": [D[30]], "code_hash": "다른코드", "env": h1.env_info()})
    elif case == "빠진날":
        cal = fs.read_lines(root / "us" / "calendar.jsonl")[-1]
        jline(root / "us" / "calendar.jsonl", {**cal, "dates": sorted(cal["dates"] + ["2026-03-14"])})
    d, v = _verdict(root)
    fails = {"L오류": {"c1"}, "다른지문": {"c3"}, "빠진날": {"c1", "c2"}}.get(case, {"c2"})   # 빠진 날은 L16 이기도 함
    assert {k for k in ("c1", "c2", "c3") if not v[k]["ok"]} == fails, v
    assert v["result"] == "fail_window" and not v["passed"], v
    if case == "빠진날":
        assert d["recheck"]["codes"] == {"L16": 6}
    text = R.render(d)
    assert "**판정 창 실패**" in text and "재시작 대상" in text and "**실패**" in text


def test_final_연장_구간_일지는_판정에_안_씀(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    end_at = _end_at(root, h.D[62])
    later = _end_at(root, h.D[64])
    assert later > end_at
    jline(root / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": later, "date": h.D[65],
                                  "problems": [{"level": "L", "code": "L7"}]})
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": hs.S_A, "at": later,
                                "exit_code": 6, "bars": []})
    d, v = _verdict(root)
    assert v["result"] == "pass" and d["extension"]["l_errors"] == 1


def test_final_S62_저장_뒤_다음_봉에서_멈춘_실행은_연장_몫(built, tmp_path):
    """한 실행이 S+62 를 저장한 뒤 다음 봉(S+63)에서 자료 문제로 멈추면 일지 끝 줄은 bars=[S+62]·종료 코드 4 하나다.
    그 멈춤은 S+63 의 일이라 판정 창(최종)에서는 세지 않는다. 월간은 S+63 이 든 달(이 세계에서 2026-04-30)부터 센다."""
    h = built["fin"]
    root = copy_of(h, tmp_path)
    s62 = h.D[62]
    lines = (root / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    out = []
    for ln in lines:
        r = json.loads(ln)
        if r.get("event") == "end" and r.get("bars") == [s62]:
            r.update(exit_code=4, problems=[{"level": "D", "code": "D3", "date": h.D[63]}])
        out.append(json.dumps(r, ensure_ascii=False))
    (root / "runs.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")
    d, v = _verdict(root)
    assert d["end_at"] is not None and v["result"] == "pass" and d["ops"]["data_stops"] == 0
    assert s62 == "2026-04-29" and h.D[63] == "2026-04-30"
    assert d["ops"]["n_bars"] == 63 and d["ops"]["batch_max"] == 1
    # 3월(마지막 봉 저장 뒤 시각의 일)에는 안 들어가고, 4월·5월(S ~ 그달 누적)에는 들어감
    assert R.collect("us", "2026-03", root=root, online=False)["ops"]["data_stops"] == 0
    assert R.collect("us", "2026-04", root=root, online=False)["ops"]["data_kinds"] == {"D3": 1}
    assert R.collect("us", "2026-05", root=root, online=False)["ops"]["data_kinds"] == {"D3": 1}
    # 문제에 날짜가 없어도(D2) 같다: 저장한 마지막 봉(S+62) 다음 봉의 일
    rows = [json.loads(ln) for ln in (root / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    for r in rows:
        if r.get("event") == "end" and r.get("bars") == [s62]:
            r["problems"] = [{"level": "D", "code": "D2", "date": None}]
    (root / "runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    d, v = _verdict(root)
    assert v["result"] == "pass" and d["ops"]["data_stops"] == 0
    assert R.collect("us", "2026-04", root=root, online=False)["ops"]["data_kinds"] == {"D2": 1}


def test_final_재시작_상한을_넘으면_H1_포워드_실패(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    for i in (1, 2):
        rid = f"재시작{i}"
        jline(root / "restarts.jsonl", {"status": "moving", "restart_id": rid, "market": "us", "at": f"2025-1{i}-01T00:00:00+09:00",
                                        "old_start": f"2025-1{i}-01", "old_last": f"2025-1{i}-20", "reason": f"시험 {i}",
                                        "archive": f"archive/us-{i}", "restart_no": i})
        jline(root / "restarts.jsonl", {"status": "done", "restart_id": rid, "market": "us",
                                        "at": f"2025-1{i}-01T00:00:01+09:00", "archive": f"archive/us-{i}"})
    d, v = _verdict(root)
    assert v["result"] == "pass" and d["ops"]["restarts_used"] == 2       # 기준을 지켰으면 상한과 상관없이 통과
    jline(root / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": _end_at(root, h.D[10]),
                                  "date": h.D[11], "problems": [{"level": "L", "code": "L9"}]})
    d, v = _verdict(root)
    assert v["result"] == "fail_h1" and "재시작이 2번을 넘게 필요함" in v["why"]
    text = R.render(d)
    assert "**H1 포워드 실패(운영 기준 미충족)**" in text and "| 재시작 | 2번 / 상한 2 (남은 0번) |" in text
    assert "옛 S 2025-11-01 ~ 2025-11-20" in text
    # 창이 덜 찬 시장도: 이미 어겼고 남은 재시작이 없으면 실패
    root2 = copy_of(built["us"], tmp_path, "us2")
    shutil.copy(root / "restarts.jsonl", root2 / "restarts.jsonl")
    jline(root2 / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": "2026-02-10T07:10:00+09:00",
                                   "date": built["us"].D[6], "problems": [{"level": "L", "code": "L9"}]})
    _, v = _verdict(root2)
    assert v["result"] == "fail_h1" and not v["complete"]


def test_final_마감을_넘으면_H1_포워드_실패(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    recommit(root, "us", fn_meta=lambda m: m["rules"].update(deadline="2026-04-01"))
    d, v = _verdict(root)
    assert v["c1"]["ok"] and v["c2"]["ok"] and v["c3"]["ok"]
    assert v["result"] == "fail_h1" and v["over_deadline"] and "마감 2026-04-01" in v["why"]
    assert d["rules_changed"]                                                # meta.rules ≠ 코드 상수 경고도 찍힘
    assert "**H1 포워드 실패(운영 기준 미충족)**" in R.render(d)
    root2 = copy_of(built["us"], tmp_path, "us2")                           # 창이 덜 찼는데 마감이 지남
    recommit(root2, "us", fn_meta=lambda m: m["rules"].update(deadline="2026-02-20"))
    _, v = _verdict(root2)
    assert v["result"] == "fail_h1" and not v["complete"] and "깨끗한 판정 창이 끝나지 않음" in v["why"]


@pytest.mark.parametrize("case", ["늦은봉10", "한번에5봉"])
def test_final_경계값은_통과(built, tmp_path, case):
    """늦은 봉 '10봉 이하'·한 번에 '5봉 이하' — 딱 상한이면 통과(11·6 은 위 시험에서 실패)."""
    h = built["fin"]
    root = copy_of(h, tmp_path)
    D, S = h.D, hs.S_A
    if case == "늦은봉10":
        def late(states):
            for arm in h1.ARMS:
                for tn in h1.TRAINERS:
                    for r in states[arm][tn]["days"]:
                        if D[1] <= r["date"] <= D[10]:
                            r["late"] = True
        recommit(root, "us", late)
    else:
        jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S,
                                    "at": _end_at(root, D[30]), "exit_code": 0, "bars": D[20:25],
                                    "code_hash": h1.code_hash()[0], "env": h1.env_info()})
    d, v = _verdict(root)
    assert v["result"] == "pass", v
    assert (len(d["ops"]["late"]), d["ops"]["batch_max"]) == ((10, 1) if case == "늦은봉10" else (0, 5))


def test_final_마감까지_끝날_수_없으면_H1_포워드_실패(built, tmp_path):
    """마감 전이라도 '휴장일 없이 매일 처리해도 S+62 가 마감 뒤'면 확실한 실패(거래일은 평일보다 일찍 올 수 없음)."""
    h = built["us"]
    root = copy_of(h, tmp_path)
    fs.record_pass(root)                                              # 이 창을 깨끗하게
    _, v = _verdict(root)
    assert v["result"] == "not_finished" and not v["violated"]
    edge = R._add_weekdays(h.D[25], 37)                               # 남은 37봉 → S+62 는 빨라야 이 날
    recommit(root, "us", fn_meta=lambda m: m["rules"].update(deadline=edge))
    _, v = _verdict(root)
    assert v["result"] == "not_finished" and v["this_min_end"] == edge
    before = (pd.Timestamp(edge) - pd.Timedelta(days=1)).date().isoformat()
    recommit(root, "us", fn_meta=lambda m: m["rules"].update(deadline=before))
    d, v = _verdict(root)
    assert v["result"] == "fail_h1" and f"빨라야 {edge}" in v["why"]
    assert "**H1 포워드 실패(운영 기준 미충족)**" in R.render(d)
    # 다 찬 창이 기준을 어겼고 재시작이 남아도, 새 창(62봉 뒤 S+62)이 마감 전에 끝날 수 없으면 실패
    hf = built["fin"]
    rf = copy_of(hf, tmp_path, "fin")
    jline(rf / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": _end_at(rf, hf.D[10]), "date": hf.D[11],
                                "problems": [{"level": "L", "code": "L9"}]})
    nxt = R._add_weekdays(hf.D[65], 62)
    recommit(rf, "us", fn_meta=lambda m: m["rules"].update(deadline=nxt))
    _, v = _verdict(rf)
    assert v["result"] == "fail_window" and v["next_min_end"] == nxt
    recommit(rf, "us", fn_meta=lambda m: m["rules"].update(deadline=(pd.Timestamp(nxt) - pd.Timedelta(days=1))
                                                          .date().isoformat()))
    _, v = _verdict(rf)
    assert v["result"] == "fail_h1" and "재시작해도 새 창의 S+62 가 빨라야" in v["why"]


def test_final_재시작_상한_밖의_창은_통과해도_실패(built, tmp_path):
    root = copy_of(built["fin"], tmp_path)
    for i in (1, 2, 3):
        jline(root / "restarts.jsonl", {"status": "done", "restart_id": f"r{i}", "market": "us",
                                        "at": f"2025-0{i}-01T00:00:00+09:00", "old_start": f"2025-0{i}-01",
                                        "old_last": f"2025-0{i}-20", "reason": f"시험 {i}"})
    _, v = _verdict(root)
    assert v["c1"]["ok"] and v["c2"]["ok"] and v["c3"]["ok"]
    assert v["result"] == "fail_h1" and "상한 2번을 넘은 창" in v["why"]


def test_final_과_month_는_같이_못_씀(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    with pytest.raises(R.ReportError) as e:
        R.collect("us", "2026-03", final=True, root=root, online=False)
    assert e.value.code == 9


# ============================ 월간: 지난달은 S ~ 그달 마지막 봉까지 ============================

def test_month_지난달_보고서는_그달_마지막_봉까지만(built, tmp_path):
    h = built["us"]
    root = copy_of(h, tmp_path)
    D, S = h.D, hs.S_A
    feb = R.collect("us", "2026-02", root=root, online=False)
    ops = feb["ops"]
    assert feb["cut"] == D[19] and feb["period_start"] == S and ops["last"] == D[19]
    assert ops["n_bars"] == 20 and ops["bars_left"] == 43 and ops["late"] == [D[11]] and ops["batch_max"] == 2
    assert ops["gate_refused"] == 1 and ops["data_kinds"] == {"D2": 1, "D3": 1, "D6": 1}
    assert ops["other_fp"] == D[:20]
    for arm in h1.ARMS:                                                 # S 가 있는 달: 그달 수익률 = S 이후 수익률
        a = feb["values"]["arms"][arm]
        assert a["ret_period"] == pytest.approx(a["ret"], rel=1e-12, abs=1e-15)
    before = R.build("us", "2026-02", root=root, online=False)
    assert "## 2. 운영 기준 (판정 아님 — 이 창의 S 2026-02-02 ~ 2026-02 끝까지)" in before
    assert "- **이 달 숫자(2~9절)는 그달 마지막 처리 봉 2026-02-27 까지로 고정**이다" in before
    assert "보고서를 만든 때의 장부 전체** 기준이다" in before
    # 3월(2월 마지막 봉을 저장한 뒤)에 생긴 일 → 2월 보고서는 바이트까지 그대로, 이번 달(3월) 보고서에는 들어감
    at = "2026-03-05T07:10:00+09:00"
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S, "at": at,
                                "exit_code": 4, "bars": [], "problems": [{"level": "D", "code": "ENV"}]})
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": "unknown", "at": at,
                                "exit_code": 6, "bars": []})
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S, "at": at,
                                "exit_code": 3, "bars": []})
    jline(root / "errors.jsonl", {"market": "us", "start_date": S, "at": at, "date": D[23],
                                  "problems": [{"level": "L", "code": "L7"}]})
    assert R.build("us", "2026-02", root=root, online=False) == before
    mar = R.collect("us", "2026-03", root=root, online=False)["ops"]
    assert mar["n_bars"] == 26 and mar["data_kinds"]["ENV"] == 1 and mar["backlog_fail"] == 1
    assert mar["l_errors"] == 1 and mar["gate_refused"] == 2
    # 2월 마지막 봉을 저장하기 전의 봉 없는 멈춤은 2월 보고서에 들어감
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S,
                                "at": "2026-02-25T07:10:00+09:00", "exit_code": 4, "bars": [],
                                "problems": [{"level": "D", "code": "D1"}]})
    assert R.collect("us", "2026-02", root=root, online=False)["ops"]["data_kinds"] == {"D1": 1, "D2": 1, "D3": 1,
                                                                                         "D6": 1}


# ============================ 파일을 고치지 않음 · 같은 출력 · 단위 6자리 ============================

def test_보고서는_장부와_일지를_고치지_않음(built, tmp_path, monkeypatch):
    for key, mk in (("us", "us"), ("kr", "kr"), ("fin", "us")):
        root = copy_of(built[key], tmp_path, key)
        before = files_sha(root)
        R.write(mk, root=root, online=False)
        R.build(mk, root=root, online=False)
        R.write(mk, final=True, root=root, online=False)
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        R.write(mk, root=root, online=True)
        monkeypatch.setattr(urllib.request, "urlopen", _no_net)
        assert files_sha(root) == before, key


def test_보고서는_반쯤_쓴_판정_기록_줄도_자르지_않음(built, tmp_path):
    """판정 기록 마지막 줄이 반쯤 쓰였어도(run 이 쓰다 꺼짐) 보고서는 읽기 전용 — 자르지 않고 알리기만(다음 run 이 자름)."""
    root = copy_of(built["us"], tmp_path)
    with open(h1.decisions_path(root, "us"), "ab") as f:
        f.write(b'{"key": "us|2026-03-10|')
    before = files_sha(root)
    text = R.write("us", root=root, online=False).read_text(encoding="utf-8")
    assert files_sha(root) == before
    assert "판정 기록 마지막 줄이 반쯤 쓰여 있음(" in text


def test_같은_입력이면_같은_바이트(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    R.store_rates("DTB3", root / "rates", fred_csv(_us_rates(None)).encode(), "2026-03-10T08:00:00+09:00")
    p = R.write("us", "2026-02", root=root, online=False)
    first = p.read_bytes()
    assert R.write("us", "2026-02", root=root, online=False).read_bytes() == first   # 같은 달 다시 → 덮어씀, 같음
    assert R.build("us", "2026-02", root=root, online=False).encode("utf-8") == first
    other = copy_of(built["us"], tmp_path, "again")                       # 다른 폴더의 같은 파일들 → 같은 글
    shutil.copytree(root / "rates", other / "rates")
    assert R.build("us", "2026-02", root=other, online=False).encode("utf-8") == first
    assert {x.name for x in (root / "reports").iterdir()} == {"us-2026-02.md"}


def test_지수_단위는_화면_6자리(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    st = load(root, "us").states
    text = R.build("us", root=root, online=False)
    units = sum(st["A1"][tn]["wallet"].holdings["SPY"].shares for tn in h1.TRAINERS)
    assert f"A1 이 들고 있는 SPY: {units:.6f}단위" in text
    nums = re.findall(r"(\d+\.\d+)단위", text) + re.findall(r"단위 (\d+\.\d+)", text)
    assert len(nums) >= 2 and all(len(n.split(".")[1]) == 6 for n in nums)
    assert repr(units) not in text


def test_고정_문장과_절_순서(built, tmp_path):
    root = copy_of(built["kr"], tmp_path)
    text = R.build("kr", root=root, online=False)
    assert R.FIXED_RECORD_ONLY in text and R.FIXED_A0 in text
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    nums = [int(m.group(1)) for ln in heads if (m := re.match(r"## (\d+)\.", ln))]
    assert nums == list(range(1, 12))
    assert R.US_TAX_NOTE not in text                                     # 국내에는 미국 양도세 문구 없음
    assert "원" in text and "$" not in text.split("## 3. 값")[1].split("## 4.")[0]


def test_없는_달은_9(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    for bad in ("2026-01", "2026-04", "2026-3", "2026-13"):
        with pytest.raises(R.ReportError) as e:
            R.collect("us", bad, root=root, online=False)
        assert e.value.code == 9, bad


# ============================ cli ============================

def test_cli_종료_코드(built, tmp_path, monkeypatch, capsys):
    root = copy_of(built["us"], tmp_path)
    monkeypatch.setattr(h1, "H1_DIR", root)
    assert R.cli(["--market", "us", "--offline"]) == 0
    assert (root / "reports" / "us-2026-03.md").exists()
    assert R.cli(["--market", "us", "--month", "2026-02", "--offline"]) == 0
    assert R.cli(["--market", "us", "--final", "--offline"]) == 0
    assert (root / "reports" / f"us-final-{hs.S_A}.md").exists()
    assert "아직 판정 창이 끝나지 않음" in capsys.readouterr().out
    assert R.cli(["--market", "kr", "--offline"]) == 8 and not (root / "kr").exists()
    assert R.cli(["--market", "us", "--month", "2025-12", "--offline"]) == 9
    assert R.cli(["--market", "us", "--final", "--month", "2026-03"]) == 9
    assert R.cli([]) == 9 and R.cli(["--market", "jp"]) == 9 and R.cli(["--fetch-rates", "--final"]) == 9
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert R.cli(["--fetch-rates"]) == 4
    body = {"DTB3": fred_csv([("2026-01-02", "3.6")]).encode(),
            "IR3TIB01KRM156N": b"observation_date,IR3TIB01KRM156N\n2026-01-01,2.9\n"}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResp(body[req.full_url.split("id=")[1]]))
    assert R.cli(["--fetch-rates"]) == 0
    assert (root / "rates" / "DTB3.json").exists() and (root / "rates" / "IR3TIB01KRM156N.csv").exists()
    # 손상된 장부 → 2(L24)
    p = root / "us" / "A1" / "team_마라토너.json"
    p.write_text(p.read_text(encoding="utf-8").replace('"cash"', '"cash" ', 1), encoding="utf-8")
    assert R.cli(["--market", "us", "--offline"]) == 2


def test_cli_환경_문제는_4_코드_버그는_2(built, tmp_path, monkeypatch, capsys):
    import errno
    root = copy_of(built["us"], tmp_path)
    monkeypatch.setattr(h1, "H1_DIR", root)
    before = files_sha(root)

    def disk_full(path, data):
        raise OSError(errno.ENOSPC, "No space left on device")
    with monkeypatch.context() as mp:
        mp.setattr(h1, "_write_atomic", disk_full)
        assert R.cli(["--market", "us", "--offline"]) == 4
    assert "환경 문제(ENV) OSError" in capsys.readouterr().out
    with monkeypatch.context() as mp:
        mp.setattr(R, "_shadow", lambda *a: (_ for _ in ()).throw(MemoryError()))
        assert R.cli(["--market", "us", "--offline"]) == 4
    with monkeypatch.context() as mp:
        mp.setattr(R, "_shadow", lambda *a: 1 / 0)
        assert R.cli(["--market", "us", "--offline"]) == 2
    assert "예상 밖 오류 ZeroDivisionError" in capsys.readouterr().out
    assert not (root / "reports" / "us-2026-03.md").exists() and files_sha(root) == before
    assert R.cli(["--market", "us", "--offline"]) == 0                     # 고친 뒤엔 정상


def test_cli_잠금_30분_넘으면_5(built, tmp_path, monkeypatch):
    root = copy_of(built["us"], tmp_path)
    monkeypatch.setattr(h1, "H1_DIR", root)
    clock = tr.FakeClock()

    def fake_sleep(s):
        clock.t += s
    monkeypatch.setattr(h1, "_lock_clock", clock)
    monkeypatch.setattr(h1, "_lock_sleep", fake_sleep)
    before = files_sha(root)
    fd = os.open(root / "h1-us.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert R.cli(["--market", "us", "--offline"]) == 5
        assert clock.t >= h1.LOCK_WAIT_S
        assert not (root / "reports").exists() and files_sha(root) == before
    finally:
        os.close(fd)


# ============================ 2c 독립 검토 반영 (docs/h1-review-2c.md R-1 ~ R-9) ============================

def _fin_h(tmp_path, name="h1", n_days=70):
    """깨끗한 창 장면과 같은 세계·계획(재현 통과 기록은 시험마다 따로)."""
    w = tr.us_world(end="2026-07-31")
    return tr.H(tmp_path, w, hs.S_A, _plan_fin, hs.FakeAsk(hs.ASK_A), n_days=n_days, name=name)


def _pass_now(root, code=None, fps=None):
    """재현 통과 기록(단계 4 F-1 모양). code = (code_hash, files) 또는 None(지금 코드)."""
    fs.record_pass(root, code, ledger=fps if fps is not None else {"W1-us": "같음"})


@pytest.mark.parametrize("same_clock", [False, True])
def test_R1_실패한_start_뒤_같은_S_로_다시_시작한_창은_깨끗함(tmp_path, monkeypatch, same_clock):
    """S 를 정한 뒤 코드 버그로 실패한 start 의 일지 줄(start_date == S)은 창이 만들어지기 전 것이라 어느 창에도 안 넣는다.
    고친 뒤 다시 친 start 가 같은 S 를 받아도 그 창의 ②-1 은 깨끗하다. status 의 셈(window_counts)도 같은 규칙.
    same_clock: 두 start 가 같은 시각(시계가 거침)이어도 보고서는 실행 순서로 가른다."""
    h = _fin_h(tmp_path, n_days=70)
    _pass_now(h.root)
    real = h1.run_bar
    monkeypatch.setattr(h1, "run_bar", lambda *a, **k: (_ for _ in ()).throw(KeyError("코드 버그(시험)")))
    assert h.start(gate=True) == 2
    monkeypatch.setattr(h1, "run_bar", real)
    err = fs.read_lines(h.root / "errors.jsonl")
    assert len(err) == 1 and err[0]["command"] == "start" and err[0]["start_date"] == hs.S_A
    clock = None if same_clock else fs.run_at("us", hs.S_A, hh=7, mm=40)       # 07:10 실패 → 07:40 다시(장 시작 전)
    assert h.start(gate=True, clock=clock) == 0
    for k in range(1, 4):
        assert h.run(h.D[k], gate=True) == 0
    d = R.collect("us", final=True, root=h.root, online=False)
    ops = d["ops"]
    assert ops["l_errors"] == 0 and ops["outside"] == 2 and d["verdict"]["c1"]["ok"]
    assert "창 밖 기록 2줄" in R.render(d)
    meta = h.meta()
    if not same_clock:
        assert h1.window_counts("us", h.root)["l_errors"] == 0                       # status 도 같은 규칙(시각)
        assert h1._in_window(err[0], hs.S_A, meta["created_at"]) is False
    else:
        assert err[0]["at"] == meta["created_at"]                       # 시각으로는 못 가름 → 보고서는 실행 순서로 뺌


def test_R1_창이_만들어진_뒤의_줄만_지금_창(tmp_path):
    c = "2026-02-03T07:10:00+09:00"
    assert h1._in_window({"start_date": hs.S_A, "at": "2026-02-03T07:09:59+09:00"}, hs.S_A, c) is False
    assert h1._in_window({"start_date": hs.S_A, "at": c}, hs.S_A, c) is True
    assert h1._in_window({"start_date": "unknown", "at": "2026-02-04T07:10:00+09:00"}, hs.S_A, c) is True
    assert h1._in_window({"start_date": "2026-01-05", "at": "2026-02-04T07:10:00+09:00"}, hs.S_A, c) is False
    assert h1._in_window({"start_date": hs.S_A, "at": "엉망"}, hs.S_A, c) is True      # 못 읽으면 보수적으로 넣음
    assert h1._in_window({"start_date": hs.S_A, "at": "2020-01-01T00:00:00+09:00"}, hs.S_A, None) is True


def _short_with_l_run(tmp_path, how):
    """S ~ D2 정상 → D3 처리 중 예상 밖 오류(종료 코드 2) → D3·D4 정상. how: 'ok'(errors.jsonl 온전) /
    'nowrite'(errors.jsonl 쓰기 실패 — _log_errors 가 OSError 를 삼킴) / 'half'(errors.jsonl 마지막 줄 반쯤)."""
    h = _fin_h(tmp_path, n_days=70)
    assert h.start() == 0
    for k in (1, 2):
        assert h.run(h.D[k]) == 0
    real_bar, real_append = h1.run_bar, h1._append_log
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(h1, "run_bar", lambda *a, **k: (_ for _ in ()).throw(KeyError("일시적 버그")))
        if how == "nowrite":
            def append(root, name, rec):
                if name == "errors.jsonl":
                    raise OSError(28, "No space left on device")
                return real_append(root, name, rec)
            mp.setattr(h1, "_append_log", append)
        assert h.run(h.D[3]) == 2
    assert h1.run_bar is real_bar
    if how == "half":
        b = (h.root / "errors.jsonl").read_bytes()
        (h.root / "errors.jsonl").write_bytes(b[:-30])
    for k in (3, 4):
        assert h.run(h.D[k]) == 0
    return h


@pytest.mark.parametrize("how", ["ok", "nowrite", "half"])
def test_R2_L_오류는_errors_jsonl_과_종료_코드_2_의_합집합(tmp_path, how):
    h = _short_with_l_run(tmp_path, how)
    ends2 = [r for r in h.ends() if r["exit_code"] == 2]
    assert len(ends2) == 1
    ops = R.collect("us", final=True, root=h.root, online=False)["ops"]
    assert ops["l_errors"] == 1                                            # 한 실행 = 한 번(run_id 로 합침)
    assert ops["l_runs_only"] == (0 if how == "ok" else 1)
    assert ops["l_list"][0][1] == h.D[3]                                  # 그 실행이 처리하려던 봉
    if how == "half":                       # 줄바꿈 없이 끝난 마지막 줄 = 쓰는 중일 수 있음 → 깨진 줄과 따로(단계 4 F-7)
        assert ops["broken"] == {} and ops["tail"] == {"errors.jsonl": 1}
        assert "줄바꿈 없이 끝난 마지막 줄(다른 시장 명령이 지금 쓰는 중이거나 쓰다 꺼짐 — 깨진 줄로 세지 않음): " \
               "errors.jsonl 1줄" in R.build("us", final=True, root=h.root, online=False)


def test_R2_끝_기록_없는_실행은_L_이_아니고_따로_셈(tmp_path):
    h = _fin_h(tmp_path, n_days=70)
    assert h.start() == 0
    assert h.run(h.D[1]) == 0
    jline(h.root / "runs.jsonl", {"event": "start", "run_id": "죽은실행", "command": "run", "market": "us",
                                  "at": fs.run_at("us", h.D[2]).isoformat(), "start_date": hs.S_A})
    assert h.run(h.D[2], hh=8, mm=0) == 0
    d = R.collect("us", final=True, root=h.root, online=False)
    assert d["ops"]["no_end"] == 1 and d["ops"]["l_errors"] == 0
    assert "| 끝 기록 없는 실행(kill·전원 꺼짐 — 판정에는 안 씀) | 1번 |" in R.render(d)


def test_R2_종료_코드_2_만_남은_창은_최종_판정에서_실패(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    jline(root / "runs.jsonl", {"event": "end", "run_id": "버그실행", "command": "run", "market": "us",
                                "start_date": hs.S_A, "at": _end_at(root, h.D[30]), "exit_code": 2, "bars": [],
                                "message": "예상 밖 오류(코드 버그) KeyError"})
    d, v = _verdict(root)
    assert not v["c1"]["ok"] and v["result"] == "fail_window" and d["ops"]["l_list"][0][1] == h.D[31]


def _drop_end_line(root, bar):
    rows = (root / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    keep = [ln for ln in rows if not (json.loads(ln).get("event") == "end" and bar in (json.loads(ln).get("bars") or []))]
    assert len(rows) - len(keep) == 1
    (root / "runs.jsonl").write_text("\n".join(keep) + "\n", encoding="utf-8")


def test_R3_S62_를_저장한_실행의_끝_줄이_없어도_경계를_정함(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    s62 = h.D[62]
    later = _end_at(root, h.D[64])
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": hs.S_A, "at": later,
                                "exit_code": 6, "bars": []})
    jline(root / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": later, "date": None,
                                  "problems": [{"level": "L", "code": "L18"}]})
    d, v = _verdict(root)
    assert v["result"] == "pass" and d["extension"]["l_errors"] == 1
    # S+62 를 저장한 바로 뒤(S+63 실행 전)의 종료 코드 6 — 끝 줄이 없어도 'S+62 뒤의 일'로 셈(하루 기록 run_at 으로 자리 잡음)
    t = datetime.fromisoformat(_end_at(root, s62)) + timedelta(minutes=30)
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": hs.S_A,
                                "at": t.isoformat(), "exit_code": 6, "bars": []})
    _drop_end_line(root, s62)                                          # S+62 를 커밋한 뒤 kill — 시작 줄만 남음
    d, v = _verdict(root)
    row = load(root, "us").states["A0"]["마라토너"]["days"][62]
    assert d["end_at"] == row["run_at"] and v["result"] == "pass"
    assert d["ops"]["backlog_fail"] == 0 and d["ops"]["l_errors"] == 0 and d["ops"]["no_end"] == 1
    # 월간: 3월 마지막 봉을 저장한 실행의 끝 줄이 없어도 4월의 멈춤이 3월에 섞이지 않음
    r2 = copy_of(h, tmp_path, "m")
    mar_last = max(x for x in h.D if x <= "2026-03-31")
    i = h.D.index(mar_last)
    jline(r2 / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": hs.S_A,
                              "at": _end_at(r2, h.D[i + 3]), "exit_code": 4, "bars": [],
                              "problems": [{"level": "D", "code": "D1"}]})
    before = R.collect("us", "2026-03", root=r2, online=False)["ops"]
    _drop_end_line(r2, mar_last)
    after = R.collect("us", "2026-03", root=r2, online=False)["ops"]
    assert before["data_kinds"] == after["data_kinds"] == {}
    assert R.collect("us", "2026-04", root=r2, online=False)["ops"]["data_kinds"] == {"D1": 1}


def _fp_scenario(tmp_path, *, same_fps=True, tamper=False):
    """D3 에서 점검 함수가 거짓 L 을 냄(종료 코드 2) → 점검을 '고친'(code_hash 가 바뀐) 코드로 D3·D4 처리."""
    h = _fin_h(tmp_path, n_days=70)
    H_old = h1.code_hash()[0]
    _pass_now(h.root)
    assert h.start(gate=True) == 0
    for k in (1, 2):
        assert h.run(h.D[k], gate=True) == 0
    real = h1_check_mod().check_day

    def fake(mk, t, *a, **k):
        p = real(mk, t, *a, **k)
        if t == h.D[3]:
            p = p + [h1_check_mod().Problem("L", "L7", mk, "A1", "마라토너", t, "시험용 거짓 양성")]
        return p
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(h1_check_mod(), "check_day", fake)
        assert h.run(h.D[3], gate=True) == 2
    err = fs.read_lines(h.root / "errors.jsonl")[-1]
    assert err["date"] == h.D[3] and err["fingerprint"] and err["code_hash"] == H_old
    if tamper:                                                         # (나) 가 틀리게: 그때 지문이 다른 값이었다고
        lines = (h.root / "errors.jsonl").read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[-1])
        rec["fingerprint"] = "0" * 64
        lines[-1] = json.dumps(rec, ensure_ascii=False)
        (h.root / "errors.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    NEW = fs.code_variant("점검 고침", file="h1_check.py")              # 점검 함수(h1_check.py)만 고친 코드
    H_new = NEW[0]
    _pass_now(h.root, NEW, {"W1-us": "같음"} if same_fps else {"W1-us": "다름"})
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(h1, "code_hash", lambda *a, **k: NEW)
        code = h.run(h.D[4], gate=True)                               # 밀린 D3(늦은 봉) + D4
    return h, err, code, H_old, H_new


def h1_check_mod():
    import h1_check
    return h1_check


def test_R4_거짓_양성_조건이_맞으면_기록하고_보고서_L_오류에서_뺌(tmp_path):
    h, err, code, H_old, H_new = _fp_scenario(tmp_path)
    assert code == 0 and h.last() == h.D[4]
    fp = [r for r in fs.read_lines(h.root / "changes.jsonl") if r.get("kind") == "false_positive"]
    assert len(fp) == 1
    assert {k: fp[0][k] for k in ("market", "bar", "error_run_id", "fingerprint", "code_hash_old", "code_hash_new",
                                  "replay_fingerprints_equal")} == {
        "market": "us", "bar": h.D[3], "error_run_id": err["run_id"], "fingerprint": err["fingerprint"],
        "code_hash_old": H_old, "code_hash_new": H_new, "replay_fingerprints_equal": True}
    assert h1.ledger_fingerprint(h.states()) != err["fingerprint"]          # 지금 장부는 D4 까지라 다름(그때 D3 지문과 비교함)
    d = R.collect("us", final=True, root=h.root, online=False)
    ops = d["ops"]
    assert ops["l_errors"] == 0 and ops["l_false_positive"] == 1 and d["verdict"]["c1"]["ok"]
    assert ops["late"] == [h.D[3]]                                       # 그동안 못 한 봉은 늦은 봉으로 이미 셈
    text = R.render(d)
    assert "거짓 양성으로 판정(사전 등록 ④) 1건은 뺌" in text
    end = h.ends()[-1]
    assert end["false_positive"] == [{"bar": h.D[3], "error_run_id": err["run_id"]}]
    assert d["verdict"]["c6"]["ok"]                                       # ⑥: h1_check.py 고침은 ④ 기록이 있어 허용
    # 같은 기록으로 다시 판정하지 않음(다음 실행에서 또 쓰지 않음)
    NEW = fs.code_variant("점검 고침", file="h1_check.py")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(h1, "code_hash", lambda *a, **k: NEW)
        assert h.run(h.D[5], gate=True) == 0
    assert len([r for r in fs.read_lines(h.root / "changes.jsonl") if r.get("kind") == "false_positive"]) == 1


@pytest.mark.parametrize("which", ["가", "나"])
def test_R4_조건이_하나라도_틀리면_기록하지_않고_L_오류는_그대로(tmp_path, capsys, which):
    h, err, code, _, _ = _fp_scenario(tmp_path, same_fps=(which != "가"), tamper=(which == "나"))
    assert not [r for r in fs.read_lines(h.root / "changes.jsonl") if r.get("kind") == "false_positive"]
    out = capsys.readouterr().out
    if which == "가":                       # 재현 장부 지문이 다른 코드 = 장부 계산이 바뀜 → ⑥ 위반, 관문이 먼저 거절(단계 4 F-1)
        assert code == 3 and h.last() == h.D[2]
        assert "⑥ 코드 동결" in h.ends()[-1]["message"] and "(b)" in h.ends()[-1]["message"]
    else:
        assert code == 0 and h.last() == h.D[4]                          # 처리·커밋은 평소대로
        assert "④ 조건 안 맞음 → 그 L 오류는 그대로(재시작 대상)" in out and f"({which})" in out
    d = R.collect("us", final=True, root=h.root, online=False)
    ops = d["ops"]
    assert ops["l_errors"] == 1 and ops["l_false_positive"] == 0
    if which == "나":                       # 점검 함수(h1_check.py)가 바뀌었는데 ④ 기록이 없음 → ⑥ 칸도 실패
        assert not d["verdict"]["c6"]["ok"] and "false_positive" in d["verdict"]["c6"]["detail"]


def test_R5_월간은_처리하려던_봉의_달로_나눔_언제_만들어도_같음(tmp_path):
    h = _fin_h(tmp_path, n_days=70)
    assert h.start() == 0
    k = 1
    while h.D[k] < "2026-03-31":
        assert h.run(h.D[k]) == 0
        k += 1
    # 3월 30일까지 저장 → 3월 31일 처리 중 D2(문제에 날짜 없음): 그 실행의 calendar.jsonl 줄로 '3월 31일의 일'임을 앎
    held = sorted({c for _, _, st in h1._flat(h.states()) for c in st["positions"]})
    h.src.missing = {held[0]}
    assert h.run(h.D[k]) == 4 and h.ends()[-1]["problems"][-1].get("date") is None
    h.src.missing = set()
    mar = R.collect("us", root=h.root, online=False)["ops"]
    assert mar["data_kinds"] == {"D2": 1} and mar["unknown"] == {}
    assert h.run(h.D[k], hh=8, mm=0) == 0
    k += 1
    apr1 = h.D[k]
    assert h.last() == "2026-03-31" and apr1 == "2026-04-01"
    held = sorted({c for _, _, st in h1._flat(h.states()) for c in st["positions"]})
    h.src.drop = {held[0]: {apr1}}
    assert h.run(apr1) == 4                                            # 4월 첫 봉 D3 (calendar.jsonl 줄 있음)
    h.src.drop = {}
    assert h.run(apr1, gate=True, hh=7, mm=20) == 3                    # 관문 거절(달력 줄 없음, 마지막 저장 봉 = 3월 31일)

    def secs(text):
        return text[text.index("## 2."):text.index("## 10.")]
    mar_before = R.collect("us", root=h.root, online=False)
    assert mar_before["month"] == "2026-03" and mar_before["ops"]["data_kinds"] == {"D2": 1}
    assert mar_before["ops"]["gate_refused"] == 0 and mar_before["ops"]["unknown"] == {}
    t_before = R.build("us", "2026-03", root=h.root, online=False)
    assert h.run(apr1, hh=8, mm=0) == 0
    assert secs(R.build("us", "2026-03", root=h.root, online=False)) == secs(t_before)
    apr = R.collect("us", "2026-04", root=h.root, online=False)["ops"]
    assert apr["data_kinds"] == {"D2": 1, "D3": 1} and apr["gate_refused"] == 1          # 4월 보고서 = S ~ 4월 누적


def test_R5_이번_달_마지막_저장_봉_뒤_어느_달인지_모르는_줄은_따로(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    D = built["us"].D
    jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": hs.S_A,
                                "at": "2026-03-10T07:30:00+09:00", "exit_code": 3, "bars": []})
    d = R.collect("us", root=root, online=False)
    assert d["ops"]["gate_refused"] == 1 and d["ops"]["unknown"] == {"관문 거절(3)": 1}
    assert d["ops"]["last"] == D[25]


def test_R6_월간_10절은_그달_마지막_봉까지와_만든_때_전체를_나눔(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    d = R.collect("us", "2026-02", root=root, online=False)
    assert d["recheck"]["cut"] == built["us"].D[19] and d["recheck"]["n_upto"] == 0
    text = R.render(d)
    assert "**그달 마지막 봉 2026-02-27 까지의 하루 기록**(날짜가 그 봉 이하)에서 찾은 L 오류 0건" in text
    assert "만든 때의 장부 전체로 다시 돈 check_ledger" in text and "만든 때 기준)" in text
    D = built["us"].D

    def bad_value(states):                                             # 3월 봉 하나의 평가액을 틀리게(L7, 날짜 = 그 봉)
        for r in states["A1"]["마라토너"]["days"]:
            if r["date"] == D[22]:
                r["value"] += 1.0
    recommit(root, "us", bad_value)
    feb = R.collect("us", "2026-02", root=root, online=False)["recheck"]
    mar = R.collect("us", "2026-03", root=root, online=False)["recheck"]
    assert feb["n"] >= 1 and feb["n_upto"] == 0 and mar["n_upto"] >= 1
    assert "2~9절" in R.__doc__ and "만든 때의 장부 전체" in R.__doc__


def test_R7_재시작_수는_세_출처_중_가장_큰_값(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    # 지금 창을 옮기려다 폴더 이동 전에 꺼진 restart(의도 줄만, 보관 폴더 없음) → 재시작으로 안 셈, 따로 보임
    jline(root / "restarts.jsonl", {"status": "moving", "restart_id": "꺼진재시작", "market": "us",
                                    "at": "2026-05-05T08:00:00+09:00", "old_start": hs.S_A, "old_last": h.D[65],
                                    "reason": "시험", "archive": "archive/us-20260505-080000", "restart_no": 1})
    d, v = _verdict(root)
    assert d["ops"]["restarts_used"] == 0 and len(d["ops"]["restarts_pending"]) == 1 and v["result"] == "pass"
    assert "끝나지 않은 restart 기록(폴더를 아직 옮기지 않음 — 재시작으로 세지 않음)" in R.render(d)
    # 일지 줄은 없는데 보관 폴더가 2개 → 2번으로 셈, 출처가 달라 경고
    for n in ("us-20251101-000000", "us-20251201-000000"):
        (root / "archive" / n).mkdir(parents=True)
    d, _ = _verdict(root)
    assert d["ops"]["restarts_used"] == 2 and d["ops"]["restart_mismatch"]
    assert d["ops"]["restart_sources"] == {"meta.restart_no": 0, "restarts.jsonl": 0, "archive 폴더": 2}
    assert "재시작 수의 출처가 서로 다름" in R.render(d)
    # 의도 줄의 보관 폴더가 실제로 있으면(옮긴 뒤 끝 줄 전에 꺼짐) 재시작으로 셈
    (root / "archive" / "us-20260505-080000").mkdir()
    d, _ = _verdict(root)
    assert d["ops"]["restarts_used"] == 3 and d["ops"]["restart_sources"]["restarts.jsonl"] == 1
    # meta.restart_no(HEAD 로 보호)가 더 크면 그것으로
    root2 = copy_of(h, tmp_path, "m")
    recommit(root2, "us", fn_meta=lambda m: m.update(restart_no=2))
    d, _ = _verdict(root2)
    assert d["ops"]["restarts_used"] == 2 and d["ops"]["restarts_left"] == 0


# ---- R-8 살아남은 돌연변이 4개 ----

def test_R8_다_찬_창의_S62_가_마감_당일이면_통과(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)
    recommit(root, "us", fn_meta=lambda m: m["rules"].update(deadline=h.D[62]))
    _, v = _verdict(root)
    assert v["result"] == "pass" and not v["over_deadline"]


def test_R8_분할_적용일에_산_주식은_분할_전_수량으로(tmp_path):
    def f(date, side, qty, cash_delta):
        return {"date": date, "code": "BBB", "kind": "stock", "side": side, "qty": qty, "cash_delta": cash_delta}
    fills = [f("2026-02-06", "buy", 10, -1000.0),                       # applied_after 날의 체결 = 분할 전 10주
             f("2026-02-09", "sell", 10, 600.0)]                          # 분할(×2) 뒤 20주 중 10주 → 원가 500
    split = [{"kind": "split", "code": "BBB", "r": 2.0, "date": "2026-02-09", "applied_after": "2026-02-06"}]
    r = R.realized(fills, split)
    assert r["sells"][0]["cost"] == pytest.approx(500.0) and r["stock"]["total"] == pytest.approx(100.0)
    assert r["open"]["BBB"]["qty"] == 10.0 and r["open"]["BBB"]["cost"] == pytest.approx(500.0)


def test_R8_한_장부만_하루_기록이_빠지면_빠진_날_실패(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)

    def drop(states):
        states["A1"]["파이오니어"]["days"] = [r for r in states["A1"]["파이오니어"]["days"] if r["date"] != h.D[30]]
    recommit(root, "us", drop)
    d, v = _verdict(root)
    assert d["ops"]["ledger_dates_differ"] == ["A1/파이오니어"] and d["ops"]["missing"] == []
    assert not v["c2"]["ok"] and not v["c2"]["parts"]["빠진 날 0"] and v["result"] == "fail_window"


def test_R8_연장_구간의_늦은_봉은_판정_창에_안_셈(built, tmp_path):
    h = built["fin"]
    root = copy_of(h, tmp_path)

    def late(states):
        for arm in h1.ARMS:
            for tn in h1.TRAINERS:
                for r in states[arm][tn]["days"]:
                    if h.D[53] <= r["date"] <= h.D[63]:
                        r["late"] = True
    recommit(root, "us", late)
    d, v = _verdict(root)
    assert len(d["ops"]["late"]) == 10 and v["result"] == "pass" and d["extension"]["late"] == 1


# ---- R-9 읽는 사람 ----

def test_R9_그림자_서킷_사유는_쉬운_말_MDD_0_은_부호_없음_마라토너_문장(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    d = R.collect("us", root=root, online=False)
    text = R.render(d)
    sh = [s for s in d["shadow"] if s["first"]]
    assert sh and all("서킷이 켜져 있었다면 멈췄을 날(실제로는 팔거나 멈추지 않음)" in s["desc"] for s in sh)
    a1p = next(s for s in sh if s["arm"] == "A1" and s["trainer"] == "파이오니어")
    assert a1p["desc"].startswith("하루 -13.7%(한도 -7%)") and "전부 팔고" in a1p["why"]
    table6 = text[text.index("## 6."):text.index("## 7.")]
    assert "전부 팔고" not in table6.split("|---|")[1].split("\n\n")[0]
    assert "MDD(최대 낙폭) = 최고점에서 가장 많이 떨어진 비율" in text
    assert R._mdd_pct(0.0) == "0.00%" and R._mdd_pct(-0.0424) == "-4.24%" and R._mdd_pct(None) == "계산 불가"
    assert "늘 '현금 부족'" not in text
    ms = {arm: sum(1 for s in load(root, "us").states[arm]["마라토너"]["skips"]
                   if s["kind"] == "현금부족" and "2026-03-01" <= s["date"] <= d["cut"]) for arm in h1.ARMS}
    assert f"이 기간 마라토너의 '현금 부족' 보류: A0 {ms['A0']}건 · A1 {ms['A1']}건." in text
    h = tr.us_h(tmp_path / "s")
    assert h.start() == 0
    t0 = R.build("us", root=h.root, online=False)                        # S 날만: 낙폭 없음
    rows = [ln for ln in t0.splitlines() if ln.startswith("| A0 쉬는 돈") or ln.startswith("| A1 쉬는 돈")]
    assert rows and all(ln.rstrip(" |").endswith("0.00%") and "+0.00% |" != ln[-9:] for ln in rows)
    assert all(not ln.rstrip(" |").endswith("+0.00%") for ln in rows)


def test_한계_절은_시장별로_맞는_말을_한다(built, tmp_path):
    """종합 확인(docs/h1-intent-check.md §1.2 #5): SPY 는 ETF 라 보수는 가격에 이미 있음, 미국 종목군은 무작위 40,
    하락장에서 A1 이 더 잃는 것·트레이너 매매 시점이 무작위보다 못했던 것을 적는다."""
    def sec11(mk):
        text = R.render(R.collect(mk, root=copy_of(built[mk], tmp_path, mk), online=False))
        return text[text.index("## 11. 한계"):]
    us, kr = sec11("us"), sec11("kr")
    assert "ETF 라 운용보수는 이미 가격에" in us and "ETF 운용보수가 없다" not in us
    assert "무작위로 섞은 40종목" in us and "상위 섞기" not in us
    assert "ETF 운용보수가 없다: 대기 자산은 지수(KS200)" in kr and "KR_UNIVERSE 32종목" in kr
    for t in (us, kr):
        assert "A1 이 A0 보다 더 잃는다" in t and "무작위보다 못했다" in t
