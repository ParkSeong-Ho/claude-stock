"""
tune.py · validate.py 가 '하나가 실패해도 전체는 끝까지 돈다'를 확인하는 테스트.
네트워크 없이 main.load_prices 를 합성 데이터로 바꿔 끼운다.
  - GOOD1, GOOD2 : 정상 데이터
  - NANX         : 마지막 행 Close 가 NaN (yahoo 미완성 봉 재현)
  - BAD          : 받기 자체가 예외
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 저장소 루트를 import 경로에

import main      # noqa: E402
import tune      # noqa: E402
import validate  # noqa: E402
from sprinter_brain import SprinterBrain  # noqa: E402
from pioneer_brain import PioneerBrain    # noqa: E402

STOCKS = {"좋은1": "GOOD1", "좋은2": "GOOD2", "빈값": "NANX", "실패": "BAD"}


def _synthetic(seed, start="2018-01-01", end="2026-06-30"):
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, len(idx))))
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.003, len(idx))),
        "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": rng.integers(1_000_000, 3_000_000, len(idx)).astype(float),
    }, index=idx)


def _fake_load(code, start, *a, **k):
    if code == "BAD":
        raise ConnectionError("가짜 네트워크 오류")
    df = _synthetic({"GOOD1": 1, "GOOD2": 2, "NANX": 3}[code])
    if code == "NANX":
        df.iloc[-1, df.columns.get_loc("Close")] = np.nan   # 거래량만 있고 종가 없는 행
    return df.loc[start:]


def _fake_trainer(name, brain, df, cash, cap, code, breaker=None):
    """빠르고 결정적인 가짜 트레이너: 첫날 사서 마지막 날 평가. 마지막 종가가 NaN 이면 손익도 NaN."""
    first, last = float(df["Close"].iloc[0]), float(df["Close"].iloc[-1])
    profit = cash * (last / first - 1)
    return {"profit": profit, "mdd": -0.1 if not math.isnan(profit) else float("nan"),
            "buys": 1, "closed": 1, "wins": int(profit > 0) if not math.isnan(profit) else 0,
            "stopped": False}


SMALL_GRIDS = {
    "스프린터": {"class": SprinterBrain,
              "params": {"take_profit": [0.03, 0.05], "stop_loss": [0.015]}},   # 0.05/0.015 = 기본값
    "파이오니어": {"class": PioneerBrain,
               "params": {"volume_surge": [1.5], "rsi_oversold": [35]}},       # 기본값 하나
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "load_prices", _fake_load)
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setitem(main.CONFIG, "종목목록", dict(STOCKS))
    monkeypatch.setattr(tune, "GRIDS", SMALL_GRIDS)
    monkeypatch.setattr(validate, "_CACHE", {})
    monkeypatch.setattr(validate, "STOCKS", dict(STOCKS))
    monkeypatch.setattr(validate, "AUDIT_STOCKS", dict(STOCKS))
    monkeypatch.setattr(validate, "REGIMES", {"앞": ("2018-01-01", "2020-12-31"),
                                              "전체": ("2018-01-01", "2026-12-31")})
    monkeypatch.setattr(validate, "ERAS", {"앞": ("2018-01-01", "2021-12-31"),
                                           "뒤": ("2022-01-01", "2026-12-31")})
    return tmp_path


def test_is_nan_and_helpers():
    assert tune.is_nan(float("nan")) and tune.is_nan(None)
    assert not tune.is_nan(0) and not tune.is_nan("계산 불가(x)")
    assert tune.unavailable("이유") == "계산 불가(이유)"
    assert tune.fmt_money(12345) == "12,345" and tune.fmt_money("계산 불가(x)") == "계산 불가(x)"


def test_tune_one_records_failures_and_keeps_going(env, monkeypatch):
    monkeypatch.setattr(main, "run_one_trainer", _fake_trainer)
    failures = []
    rows = tune.tune_one("스프린터", failures)
    assert len(rows) == 2                                    # 조합 2개 모두 결과가 있다
    for r in rows:
        assert isinstance(r["검증_순손익"], int)             # round(NaN) 없이 정상 숫자
        assert r["계산_종목수"] == "2/4"
        assert r["제외_종목"].startswith("계산 불가(") and "빈값" in r["제외_종목"]
    reasons = {(f["대상"], f["사유"]) for f in failures}
    assert any(t == "실패" and "ConnectionError" in why for t, why in reasons)   # 받기 실패
    assert any(t == "빈값" and "NaN" in why for t, why in reasons)               # NaN 결과
    assert sum(r["기본값"] == "예" for r in rows) == 1


def test_tune_one_all_stocks_fail_gives_unavailable_rows(env, monkeypatch):
    monkeypatch.setitem(main.CONFIG, "종목목록", {"빈값": "NANX", "실패": "BAD"})
    monkeypatch.setattr(main, "run_one_trainer", _fake_trainer)
    failures = []
    rows = tune.tune_one("스프린터", failures)
    assert len(rows) == 2
    assert all(r["검증_순손익"].startswith("계산 불가(") for r in rows)
    assert failures


def test_tune_one_trainer_exception_is_per_combo(env, monkeypatch):
    def boom_on_003(name, brain, df, *a, **k):
        if getattr(brain, "take_profit", None) == 0.03:
            raise RuntimeError("조합 폭발")
        return _fake_trainer(name, brain, df, *a, **k)
    monkeypatch.setattr(main, "run_one_trainer", boom_on_003)
    failures = []
    rows = tune.tune_one("스프린터", failures)
    by_tp = {r["take_profit"]: r for r in rows}
    assert isinstance(by_tp[0.05]["검증_순손익"], int)
    assert by_tp[0.03]["검증_순손익"].startswith("계산 불가(")
    assert rows[-1]["take_profit"] == 0.03                    # 계산 불가 조합은 맨 아래
    assert any("RuntimeError: 조합 폭발" in f["사유"] for f in failures)


def test_tune_main_run_writes_csv_and_summary(env, monkeypatch, capsys):
    monkeypatch.setattr(main, "run_one_trainer", _fake_trainer)
    failures = tune.main_run()
    out = capsys.readouterr().out
    assert (env / "results" / "tune_스프린터.csv").exists()
    assert (env / "results" / "tune_파이오니어.csv").exists()
    assert "튜닝 실패 요약: 실패" in out and "ConnectionError" in out
    assert "nan" not in out                                    # 화면에 nan 이 찍히지 않는다
    assert failures


def test_tune_main_run_survives_whole_trainer_crash(env, monkeypatch, capsys):
    monkeypatch.setattr(main, "run_one_trainer", _fake_trainer)
    real = tune.tune_one

    def flaky(name, failures=None, params=None):
        if name == "스프린터":
            raise KeyError("설정 없음")
        return real(name, failures, params)
    monkeypatch.setattr(tune, "tune_one", flaky)
    failures = tune.main_run()
    out = capsys.readouterr().out
    assert "계산 불가(KeyError" in out
    assert (env / "results" / "tune_파이오니어.csv").exists()   # 다음 트레이너는 계속
    assert any(f["단계"] == "스프린터" for f in failures)


def test_validate_run_all_survives(env, monkeypatch, capsys):
    monkeypatch.setattr(main, "run_one_trainer", _fake_trainer)
    orig_load = main.load_prices
    failures = validate.run_all([])
    out = capsys.readouterr().out
    assert "국면 리포트" in out and "교차-시대 감사" in out
    assert "검증 실패 요약: 실패" in out
    assert "계산 불가" in out
    assert "nan" not in out
    stages = {f["단계"].split()[0] for f in failures}
    assert {"국면", "스프린터", "파이오니어"} & stages
    assert main.load_prices is orig_load                       # 바꿔 끼운 함수는 원상복구
    assert main.CONFIG["종목목록"] == STOCKS


def test_validate_audit_era_failure_does_not_stop(env, monkeypatch, capsys):
    monkeypatch.setattr(main, "run_one_trainer", _fake_trainer)
    real = tune.tune_one
    calls = {"n": 0}

    def first_fails(name, failures=None, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("시대 하나 폭발")
        return real(name, failures, params)
    monkeypatch.setattr(tune, "tune_one", first_fails)
    failures = []
    validate.overfit_audit(failures)
    out = capsys.readouterr().out
    assert "계산 불가(ValueError: 시대 하나 폭발)" in out
    assert "판정 보류" in out
    assert calls["n"] == 4                                     # 2 트레이너 × 2 시대 모두 시도


def test_real_trainer_smoke(env, monkeypatch):
    """진짜 run_one_trainer 로 작은 격자를 돌려도 죽지 않는다(NaN 마지막 행·예외 종목 포함)."""
    monkeypatch.setitem(main.CONFIG, "시작일", "2024-01-01")
    failures = []
    rows = tune.tune_one("스프린터", failures, params={"take_profit": [0.05], "stop_loss": [0.015]})
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r["검증_순손익"], int)
    assert not any(tune.is_nan(v) for v in r.values() if isinstance(v, float))
    assert any(f["대상"] == "실패" for f in failures)
