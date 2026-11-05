"""H1 단계 4 — 자료 받기 층 h1_data.py 와 ⑥ 코드 동결 확인 함수 시험 (docs/h1-review-4.md F-1·F-9). 인터넷·claude 없음.

- T-DGOLD   자료 받기 골든(tests/golden_data/): 지금 h1_data 결과 == 저장된 outputs.json (바이트), 장면이 실제로 들어 있음
            (국내 정지 두 모양·거래량 칸 이름 둘·종가 NaN·장중 미완성 봉·KS200 22:30·미국 16:15·받기 실패·빈 표)
- T-DLAYER  h1_data 는 h1 을 import 하지 않음, h1.fetch 등은 h1_data 것 그대로, CODE_FILES 에 h1_data.py, 시계는 h1 쪽
- T-ENTRY   replay_entry 모양·record_replay_pass 필수 칸(files·data_golden_sha256)·code_hash == files 로 계산한 값
- T-TAX     세율 표(KR_SELL_TAX 값)만 바꾼 h1.py 는 h1_without_tax_table_sha256 이 같고, 다른 곳을 바꾸면 다름
- T-FREEZE  freeze_transition: 허용(h1_data.py·라이브러리 버전·세율 표 + amend 기록·h1_check.py + ④ 기록) / 거절(그 밖 파일·
            프롬프트·파이썬·장부 지문 다름·골든 다름·통과 줄 없음·files 없음·기록 없음)
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import h1               # noqa: E402
import h1_data          # noqa: E402
import h1_fake_source as fs   # noqa: E402

GDIR = Path(__file__).resolve().parent / "golden_data"


# ============================ T-DGOLD ============================

def test_T_DGOLD_지금_결과가_저장된_골든과_바이트까지_같음():
    want = (GDIR / "outputs.json").read_bytes()
    assert h1.data_golden_outputs() == want, ("h1_data.py 의 받기 결과가 골든과 달라요 — ⑥-i 고침은 이 결과를 바꾸면 안 돼요"
                                              "(의도한 변경이면 판정 창 밖에서 tests/golden_data_make.py 로 다시 만듦)")
    assert h1.data_golden_digest() == hashlib.sha256(want).hexdigest()


def test_T_DGOLD_골든에_장면이_다_들어_있음():
    out = {c["name"]: c["result"] for c in json.loads((GDIR / "outputs.json").read_text(encoding="utf-8"))}
    cases = {c["name"]: c for c in json.loads((GDIR / "cases.json").read_text(encoding="utf-8"))}
    assert set(out) == set(cases) and len(cases) == 14

    def dates(name):
        return [x[:10] for x in out[name]["df"]["index"]]
    early = next(n for n in out if "15:59" in n)
    late = next(n for n in out if "16:01" in n)
    assert out[early]["halt_dates"] == ["2026-11-04", "2026-11-05"]                 # 정지 두 모양(OHL 0 / OHLC 직전 종가)
    assert dates(early) == ["2026-11-02", "2026-11-03", "2026-11-06"]               # 정지·종가 NaN·장중 봉 빠짐
    assert dates(late)[-1] == "2026-11-10"                                          # 16:00 KST 뒤면 그날 봉 확정
    assert "nan" in [row[4] for row in out[early]["df"]["data"]]                    # 거래량 NaN(모름)은 그대로
    kv = next(n for n in out if "'거래량'" in n)
    assert out[kv]["df"]["columns"][-1] == "Volume" and out[kv]["halt_dates"] == ["2026-11-05"]
    assert out[next(n for n in out if "모두 NaN" in n)] is None
    assert out[next(n for n in out if "미국 코드" in n)] == {"error": "ValueError"}
    us14, us16 = next(n for n in out if "16:14 ET(마지막" in n), next(n for n in out if "16:16 ET(마지막" in n)
    assert dates(us14)[-1] == "2026-11-09" and dates(us16)[-1] == "2026-11-10"
    assert "2026-11-05" not in dates(us16)                                          # 미국 종가 NaN 행
    assert out[next(n for n in out if "SPY 16:14" in n)]["df"]["index"][-1][:10] == "2026-11-09"
    assert out[next(n for n in out if "SPY 16:16" in n)]["df"]["index"][-1][:10] == "2026-11-10"
    assert out[next(n for n in out if "KS200 22:29" in n)]["df"]["index"][-1][:10] == "2026-11-09"
    assert out[next(n for n in out if "KS200 22:31" in n)]["df"]["index"][-1][:10] == "2026-11-10"
    assert out[next(n for n in out if "받기 실패 → None" in n and cases[n]["kind"] == "fetch")] is None
    assert out[next(n for n in out if "대기 자산 받기 실패" in n)] == {"df": None}
    assert out[next(n for n in out if "빈 표" in n)] is None


def test_T_DGOLD_가짜_FinanceDataReader_는_되돌려_놓음(monkeypatch):
    marker = object()
    monkeypatch.setitem(sys.modules, "FinanceDataReader", marker)
    h1.data_golden_outputs()
    assert sys.modules["FinanceDataReader"] is marker
    monkeypatch.delitem(sys.modules, "FinanceDataReader")
    h1.data_golden_outputs()
    assert "FinanceDataReader" not in sys.modules


def test_T_DGOLD_받기_층을_바꾸면_골든이_잡음(monkeypatch):
    """⑥-i 로 h1_data.py 를 고쳤는데 결과가 바뀌면(예: 정지 날짜를 안 셈) 골든 지문이 달라진다."""
    before = h1.data_golden_digest()
    real = h1_data.main.confirmed_bars
    monkeypatch.setattr(h1_data.main, "confirmed_bars", lambda df, now=None, market="us", cutoff=None:
                        real(df, now, market, None))                              # KS200 22:30 규칙을 잊은 고침
    assert h1.data_golden_digest() != before


# ============================ T-DLAYER ============================

def test_T_DLAYER_받기_층은_h1_data_에만():
    src = (ROOT / "h1_data.py").read_text(encoding="utf-8")
    mods = {n.names[0].name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import)} | \
           {n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
    assert "h1" not in mods and "h1_check" not in mods and "datetime" not in src.split("import")[0]
    assert h1.fetch is h1_data.fetch and h1.load_idle is h1_data.load_idle
    assert h1.fetched_from_raw is h1_data.fetched_from_raw and h1.Fetched is h1_data.Fetched
    assert h1.DataSource is h1_data.DataSource
    assert "h1_data.py" in h1.CODE_FILES and h1.FREEZE_DATA_FILES == ("h1_data.py",)
    assert h1.live_source("kr").now is h1._local_now                               # 시계(늦은 봉 판단)는 h1.py 쪽
    h1_src = (ROOT / "h1.py").read_text(encoding="utf-8")
    assert "fdr.DataReader" not in h1_src and "def fetched_from_raw" not in h1_src


def test_F10_쓰지_않는_count_restarts_는_지움():
    assert not hasattr(h1, "_count_restarts")


# ============================ T-ENTRY ============================

def test_T_ENTRY_replay_entry_모양():
    e = h1.replay_entry({"W1-us": "x"}, passed_at="2026-11-05")
    ch, files = h1.code_hash()
    assert e["code_hash"] == ch and e["files"] == files and h1.combine_code_hash(files) == ch
    assert e["data_golden_sha256"] == h1.data_golden_digest() and e["h1_without_tax_table_sha256"] == h1.tax_free_sha()
    assert e["ledger_fingerprints"] == {"W1-us": "x"} and e["passed_at"] == "2026-11-05"
    assert e["env"] == h1.env_info() and e["fingerprint_version"] == h1.FINGERPRINT_VERSION


def test_T_ENTRY_record_replay_pass_는_files_와_골든_지문이_필요(tmp_path):
    root = tmp_path / "h1"
    good = fs.pass_entry()
    for k in ("files", "data_golden_sha256", "code_hash", "env"):
        bad = {x: v for x, v in good.items() if x != k}
        with pytest.raises(ValueError):
            h1.record_replay_pass(bad, root)
    with pytest.raises(ValueError):                                     # code_hash 가 files 로 계산한 값과 다름
        h1.record_replay_pass({**good, "code_hash": "a" * 64}, root)
    with pytest.raises(ValueError):
        h1.record_replay_pass({**good, "files": {}}, root)
    assert not root.exists() or not (root / "replay_pass.json").exists()
    assert h1.record_replay_pass(good, root) == 1
    assert sorted(p.name for p in root.iterdir()) == ["changes.jsonl", "h1-global.lock", "replay_pass.json",
                                                      "replay_pass.seal.json"]          # 전역 잠금(시장 잠금 아님)
    B = fs.code_variant("고침")
    assert fs.record_pass(root, B) == 2
    ch = fs.read_lines(root / "changes.jsonl")
    assert ch[0]["files_changed_vs_prev"] is None and ch[1]["files_changed_vs_prev"] == ["h1_data.py"]
    assert ch[1]["env_changed_vs_prev"] == [] and ch[1]["data_golden_sha256"] == fs.golden_digest()


# ============================ T-TAX ============================

def test_T_TAX_세율_표만_바꾸면_같은_지문():
    blob = (ROOT / "h1.py").read_bytes()
    base = h1._without_tax_table(blob)
    assert base is not None and b"<KR_SELL_TAX>" in base and h1.tax_free_sha() == hashlib.sha256(base).hexdigest()
    added = blob.replace(b'("2026-01-01", 0.0020))', b'("2026-01-01", 0.0020), ("2027-01-01", 0.0015))', 1)
    assert added != blob and h1._without_tax_table(added) == base                 # 줄 추가만 → 같음
    other = blob.replace(b"WINDOW_BARS = 63", b"WINDOW_BARS = 10", 1)
    assert other != blob and h1._without_tax_table(other) != base                 # 다른 상수 → 다름
    assert h1._without_tax_table(b"KR_SELL_TAX = make()\n") is None                # 글자 그대로가 아님
    assert h1._without_tax_table(b"def (\n") is None


# ============================ T-FREEZE ============================

ENV = {"python": "3.13.18", "pandas": "2.2.3", "numpy": "2.1.0", "ta": "0.11.0", "FinanceDataReader": "0.9.96"}


def _e(code, env=ENV, **kw):
    return fs.pass_entry(code, env, **kw)


def _rp(code, env=ENV):
    return {"kind": "replay-pass", "code_hash": code[0], "env": env}


def _t(old, new, entries, changes, pending=(), old_env=ENV, new_env=ENV):
    return h1.freeze_transition("kr", (old[0], old_env), (new[0], new_env), entries, changes, pending)


A = fs.code_variant(None)


def test_T_FREEZE_h1_data_고침은_조건이_다_맞으면_허용():
    B = fs.code_variant("받기 고침")
    r = _t(A, B, [_e(A), _e(B)], [_rp(B)])
    assert r["ok"] and r["files"] == ["h1_data.py"] and r["kinds"] == ["⑥-i 자료 받기 고침(h1_data.py)"]
    assert not _t(A, B, [_e(A), _e(B)], [])["ok"]                                   # (d) changes 기록 없음
    assert "(b)" in "".join(_t(A, B, [_e(A), _e(B, ledger={"W1": "다름"})], [_rp(B)])["why"])
    assert "(b)" in "".join(_t(A, B, [_e(A, ledger={}), _e(B, ledger={})], [_rp(B)])["why"])   # 빈 지문은 안 됨
    assert "(c)" in "".join(_t(A, B, [_e(A), _e(B, golden="0" * 64)], [_rp(B)])["why"])
    assert "(a)" in "".join(_t(A, B, [_e(A)], [_rp(B)])["why"])                      # 바뀐 뒤 통과 줄 없음
    no_files = {**_e(A), "files": None}
    assert "(a)" in "".join(_t(A, B, [no_files, _e(B)], [_rp(B)])["why"])


@pytest.mark.parametrize("file", ["analyst.py", "prompts/마라토너.md", "h1_report.py", "team.py", "main.py",
                                  "marathoner_brain.py", "screener.py"])
def test_T_FREEZE_그_밖_파일은_장부_지문이_같아도_거절(file):
    B = fs.code_variant("다른 고침", file=file)
    r = _t(A, B, [_e(A), _e(B)], [_rp(B)])
    assert not r["ok"] and r["files"] == [file] and "⑤-c" in "".join(r["why"])


def test_T_FREEZE_라이브러리_버전은_허용_파이썬은_거절():
    env2 = {**ENV, "FinanceDataReader": "0.9.99", "pandas": "2.2.4"}
    r = _t(A, A, [_e(A), _e(A, env=env2)], [_rp(A, env2)], new_env=env2)
    assert r["ok"] and r["env"] == ["FinanceDataReader", "pandas"] and r["kinds"] == ["⑥-i 라이브러리 버전"]
    env3 = {**ENV, "python": "3.13.19"}
    r = _t(A, A, [_e(A), _e(A, env=env3)], [_rp(A, env3)], new_env=env3)
    assert not r["ok"] and "python" in "".join(r["why"])


def test_T_FREEZE_세율_표만_바꾼_h1_py_는_amend_기록이_있을_때만():
    B = fs.code_variant("세율 줄", file="h1.py")
    ents = [_e(A, tax_free="t" * 64), _e(B, tax_free="t" * 64)]
    amend = {"kind": "amend-rules", "status": "done", "market": "kr", "code_hash": B[0]}
    assert _t(A, B, ents, [amend])["ok"]
    assert _t(A, B, ents, [], pending=("amend",))["ok"]                              # amend-rules 가 곧 적을 기록
    assert not _t(A, B, ents, [])["ok"]
    assert not _t(A, B, ents, [{**amend, "market": "us"}])["ok"]                     # 다른 시장의 기록
    assert not _t(A, B, [ents[0], _e(B, tax_free="u" * 64)], [amend])["ok"]          # 세율 표 밖도 바뀜
    assert not _t(A, B, [_e(A, tax_free=""), _e(B, tax_free="")], [amend])["ok"]


def test_T_FREEZE_점검_고침은_거짓_양성_기록이_있을_때만():
    B = fs.code_variant("점검 고침", file="h1_check.py")
    ents = [_e(A), _e(B)]
    fp = {"kind": "false_positive", "market": "kr", "code_hash_new": B[0]}
    assert _t(A, B, ents, [fp])["ok"] and _t(A, B, ents, [], pending=("fp",))["ok"]
    assert not _t(A, B, ents, [])["ok"]
    assert not _t(A, B, [_e(A), _e(B, ledger={"W1": "다름"})], [fp])["ok"]           # ④(가)와 같은 조건


def test_T_FREEZE_통과_줄이_여럿이면_맞는_짝이_있으면_허용():
    B = fs.code_variant("받기 고침")
    ents = [_e(A, ledger={"W1": "옛"}), _e(A), _e(B)]
    assert _t(A, B, ents, [_rp(B)])["ok"]


def test_T_FREEZE_창_전체를_걸으며_바뀐_곳마다():
    B, C = fs.code_variant("받기 고침"), fs.code_variant("다른", file="analyst.py")
    rows = [{"date": "d1", "code_hash": A[0], "env": ENV}, {"date": "d2", "code_hash": A[0], "env": ENV},
            {"date": "d3", "code_hash": B[0], "env": ENV}, {"date": "d4", "code_hash": C[0], "env": ENV}]
    tr = h1.freeze_window("kr", rows, [_e(A), _e(B), _e(C)], [_rp(B), _rp(C)])
    assert [(t["date"], t["ok"]) for t in tr] == [("d3", True), ("d4", False)]
    assert h1.freeze_window("kr", rows[:2], [], []) == []                            # 바뀐 곳 없으면 확인할 것도 없음
