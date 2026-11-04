"""H1 단계 2c — 보고서 h1_report.py 시험 (설계 docs/h1-forward-design.md §3.8, §6). 인터넷·claude·키 없음.

장부는 가짜 자료(tests/h1_fake_source.py)로 h1.start·h1.run 을 여러 날 돌려 만든다(tmp 폴더, 저장소 state/ 는 안 만듦).
진짜 claude 는 부르지 않는다(analyst 를 가짜로 바꾸고 claude 프로세스를 막음). 인터넷도 막는다:
urllib.request.urlopen 을 부르면 BaseException 으로 시험이 깨진다(받기 실패로 조용히 넘어가지 않게). 받기 장면만 가짜 urlopen 을 넣는다.

설계 §6 ID ↔ 시험
- T-F8a  test_T_F8a_*     평가액·수익률(S 이후·그달)·MDD·A1−A0·지수 B&H(S+1)·비율·매매 수·비용·실현손익·팀장 수·폴백 20%·
                           운영 기준 칸(늦은 봉·빠진 날·관문 거절·자료 멈춤 종류별)을 장부 파일에서 따로 센 값과 비교
- T-F8b  test_T_F8b_*     금리 규칙(미국 전 거래일·빈 날 이월·S 날, 국내 m−1월·빈 달 이월), 이자 식 손계산,
                           R2 rate_for_days 와 같은 결과(R2 식을 옮긴 기준 + R2 브랜치에서 꺼낸 함수·자료)
- T-F8c  test_T_F8c_*     urlopen 실패 → 저장본·"오프라인" 표시 / 저장본 없음 → 그 절만 "계산 불가", 파일은 만들어짐
- T-SHADOW test_T_SHADOW_* 보고서의 (장부, 트레이너)별 첫 발동일·발동한 날 수 == 하루 기록 값으로 다시 계산한 것
- T-START test_T_START_*  지수 B&H: S 날 = 총액, 단위 = 총액 ÷ (S+1 시가 × (1+slip)(1+fee))
- --final test_final_*    창이 덜 참 → 판정 안 함, 깨끗한 창 → 통과, L·늦은 봉 11·한 번에 6봉·다른 지문 → 실패,
                           재시작 상한·마감 → "H1 포워드 실패"
- 그 밖    파일을 고치지 않음(sha256), 같은 입력 → 같은 바이트, 지수 단위 화면 6자리, cli 종료 코드
"""
import ast
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
    repo_state = ROOT / "state"
    existed = repo_state.exists()
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
    if not existed:
        assert not repo_state.exists(), "시험이 저장소에 state/ 를 만들었어요"


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
    h1.record_replay_pass({"code_hash": h1.code_hash()[0], "env": h1.env_info()}, h.root)
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


def recommit(root, mk, fn_states=None, fn_meta=None):
    """장면 사본의 장부·meta 를 고친 뒤 h1.commit 으로 HEAD 까지 맞춰 쓴다(엄격 읽기를 통과하게)."""
    ld = load(root, mk)
    if fn_states:
        fn_states(ld.states)
    if fn_meta:
        fn_meta(ld.meta)
    dec = h1.DecisionLog(h1.decisions_path(root), read_only=True)
    h1.commit(root, mk, ld.states, ld.meta, dec, "test-rewrite", ld.head["written_at"], ld.head)


def jline(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def files_sha(root):
    """보고서·금리 저장본을 뺀 모든 파일의 sha256(장부·HEAD·meta·일지·판정 기록·백업·잠금 파일)."""
    return {k: v for k, v in fs.tree_sha(root).items() if not k.startswith(("reports/", "rates/"))}


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
    recs = [r for r in h1.DecisionLog(h1.decisions_path(root), read_only=True).records()
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

    def __init__(self, recs):
        self.decisions = _FakeDec(recs)
        self.states = {arm: {tn: {"days": []} for tn in h1.TRAINERS} for arm in h1.ARMS}

    def rule(self, key, default):
        return default


@pytest.mark.parametrize("n_fb,n,flag", [(1, 5, False), (2, 10, False), (2, 9, True), (3, 10, True)])
def test_T_F8a_폴백_20퍼센트_경계(n_fb, n, flag):
    recs = [{"market": "us", "date": "2026-02-03", "status": "timeout" if i < n_fb else "ok",
             "source": "fallback" if i < n_fb else "llm", "verdict": None if i < n_fb else "buy"} for i in range(n)]
    ld = R._leader(_FakeCtx(recs), "2026-02-02", "2026-02-28")
    assert ld["n"] == n and ld["fallback"] == n_fb and ld["unrepresentative"] is flag   # 20% 를 '넘을 때'만


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
    assert {k: len(v) for k, v in ops["corp"].items()} == {"split": 1, "delist": 1, "correction": 0}
    assert ops["other_fp"] == h.D[:26]                             # 재현 통과 기록 없음(관문 끈 시험) → 모두 '다른 지문'
    assert ops["deadline"] == "2027-06-30" and ops["days_to_deadline"] == (
        pd.Timestamp("2027-06-30") - pd.Timestamp(D[25])).days
    # 빠진 날: calendar.jsonl 정상 줄에 하루 기록에 없는 날이 있으면 센다
    cal = fs.read_lines(root / "us" / "calendar.jsonl")[-1]
    jline(root / "us" / "calendar.jsonl", {**cal, "dates": sorted(cal["dates"] + ["2026-02-14"]), "check": "ok"})
    # 자료 멈춤 종류별: 4(PRE·ENV)·7(D7)
    S = hs.S_A
    for kind, code in (("PRE", 4), ("ENV", 4), ("D7", 7)):
        jline(root / "runs.jsonl", {"event": "end", "command": "run", "market": "us", "start_date": S,
                                    "at": "2026-03-10T07:10:00+09:00", "exit_code": code, "bars": [],
                                    "problems": [{"level": "D", "code": kind}]})
    jline(root / "errors.jsonl", {"market": "us", "start_date": "unknown", "at": "2026-03-10T07:11:00+09:00",
                                  "date": None, "problems": [{"level": "L", "code": "L24"}]})
    jline(root / "errors.jsonl", {"market": "us", "start_date": "2025-01-01", "at": "2026-03-10T07:11:00+09:00",
                                  "date": None, "problems": [{"level": "L", "code": "L7"}]})   # 다른 창 → 안 셈
    d = R.collect("us", root=root, online=False)
    ops = d["ops"]
    assert ops["missing"] == ["2026-02-14"]
    assert ops["data_stops"] == 6 and ops["data_kinds"] == {"D2": 1, "D3": 1, "D6": 1, "D7": 1, "ENV": 1, "PRE": 1}
    assert ops["l_errors"] == 1 and ops["l_codes"] == {"L24": 1}
    text = R.render(d)
    assert "빠진 날(calendar.jsonl vs 하루 기록) | 1개 (2026-02-14)" in text
    assert "자료 멈춤(종료 코드 4·7) | 6번 · 종류별 D2 1, D3 1, D6 1, D7 1, ENV 1, PRE 1" in text
    assert "관문 거절(종료 코드 3) | 1번" in text and "늦은 봉(다음 장 시작 뒤 처리) | 1개 / 상한 10" in text


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
    assert all(x["note"] == "그날 값 없음 → 2025-12-01 값" for x in feb["table"])
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


def _git_show(path):
    try:
        p = subprocess.run(["git", "-C", str(ROOT), "show", f"{R2_REF}:{path}"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def test_T_F8b_R2_브랜치_함수_자료와_같은_결과(tmp_path):
    """R2 브랜치에서 sim_team.py 의 함수(_asof·rate_for_days·_rate_series·_read·index_buy_hold_fractional)와 자료
    (SPY·KS200·금리 파일)를 꺼내 전체 달력에서 비교한다(재현 M6·M7 과 같은 비교). R2 브랜치가 없으면 건너뜀."""
    src = _git_show(f"{R2_DIR}/sim_team.py")
    if src is None:
        pytest.skip("R2 브랜치를 읽을 수 없음(git fetch origin research-r2-2026-11-04 필요)")
    tree = ast.parse(src.decode("utf-8"))
    want = {"_asof", "rate_for_days", "_rate_series", "_read", "index_buy_hold_fractional"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
    assert {n.name for n in nodes} == want
    ns = {"np": np, "pd": pd, "Path": Path, "math": math, "metrics": metrics, "MarketData": object}   # 표기용 이름
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "r2_sim_team", "exec"), ns)
    for key, idxf, ratef, sid in (("us", "us/SPY.csv.gz", "us_tbill.csv", "DTB3"),
                                  ("kr", "kr/KS200.csv.gz", "kr_shortrate.csv", "IR3TIB01KRM156N")):
        d = tmp_path / key
        d.mkdir()
        (d / Path(idxf).name).write_bytes(_git_show(f"{R2_DIR}/data/{idxf}"))
        (d / ratef).write_bytes(_git_show(f"{R2_DIR}/data/rates/{ratef}"))
        idx = ns["_read"](d / Path(idxf).name)
        r2_rates = ns["_rate_series"](d / ratef)
        mine_series = R.load_rates(sid, d)                                  # R2 이름 그대로(복사본)도 읽음
        assert list(mine_series.to_numpy(float)) == list(r2_rates.to_numpy(float))
        cal = idx.index
        want = list(ns["rate_for_days"](cal, r2_rates, R.RULE[key]))
        got = R.rate_for_days([x.date().isoformat() for x in cal], mine_series, R.RULE[key])
        assert len(got) > 2900 and _same(got, want)
        # 지수 B&H (W1 창 2026-06-01 ~ 2026-11-03): R2 index_buy_hold_fractional(md, i0+1, i1, total)

        class MD:
            pass
        md = MD()
        md.idx_open, md.idx_close = idx["Open"].to_numpy(float), idx["Close"].to_numpy(float)
        mk = markets.MARKETS[key]
        md.idx_fee, md.idx_slip = mk.fee_rate, mk.slippage
        ds = [x.date().isoformat() for x in cal]
        i0 = next(i for i, x in enumerate(ds) if x >= "2026-06-01")
        i1 = max(i for i, x in enumerate(ds) if x <= "2026-11-03")
        total = h1.TOTALS[key]
        r2 = ns["index_buy_hold_fractional"](md, i0 + 1, i1, total)
        mine = R.index_buy_hold_same_start(list(md.idx_open[i0:i1 + 1]), list(md.idx_close[i0:i1 + 1]), total,
                                           mk.fee_rate, mk.slippage)
        assert mine["units"] == r2["units"] and mine["values"][0] == total
        assert mine["values"][1:-1] == [float(x) for x in r2["equity"][:-1]]
        assert mine["values"][-1] == r2["units"] * md.idx_close[i1]           # R2 마지막 날은 매도 비용을 뺀 값(M6)


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


def test_final_과_month_는_같이_못_씀(built, tmp_path):
    root = copy_of(built["us"], tmp_path)
    with pytest.raises(R.ReportError) as e:
        R.collect("us", "2026-03", final=True, root=root, online=False)
    assert e.value.code == 9


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


def test_cli_잠금_30분_넘으면_5(built, tmp_path, monkeypatch):
    root = copy_of(built["us"], tmp_path)
    monkeypatch.setattr(h1, "H1_DIR", root)
    clock = tr.FakeClock()

    def fake_sleep(s):
        clock.t += s
    monkeypatch.setattr(h1, "_lock_clock", clock)
    monkeypatch.setattr(h1, "_lock_sleep", fake_sleep)
    before = files_sha(root)
    fd = os.open(root / "h1.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert R.cli(["--market", "us", "--offline"]) == 5
        assert clock.t >= h1.LOCK_WAIT_S
        assert not (root / "reports").exists() and files_sha(root) == before
    finally:
        os.close(fd)
