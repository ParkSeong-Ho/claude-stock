"""
golden_data_make.py — 자료 받기 골든(tests/golden_data/) 만들기 (단계 4 F-1·F-9). pytest 가 모으지 않는 도우미.

무엇을 하나
- 합성 원본 시세(inputs/*.json)와 경우 목록(cases.json)을 쓰고, h1.data_golden_outputs 로 지금 h1_data.py 의 결과를
  outputs.json 에 적는다. 시험(tests/test_h1_data.py)은 지금 결과가 이 outputs.json 과 바이트까지 같은지 본다.
- 원본에 들어 있는 장면: 국내 거래정지 행 두 모양(시가·고가·저가 0 + 종가 = 직전 종가 / OHLC 전부 직전 종가, 거래량 0),
  거래량 칸 이름 둘('Volume'·'거래량'), 거래량 NaN(모름 → 그대로 둠), 종가 NaN(버림), 국내 장중 미완성 봉(16:00 KST 전후),
  KS200 22:30 KST 전후, 미국 SPY·종목 16:15 ET 전후, 받기 실패·빈 표·국내 시장에 미국 코드.
- 판정 창 동안 이 파일·inputs·cases 를 바꾸면 재현 통과 기록의 data_golden_sha256 이 달라져 ⑥ 확인에서 걸린다.
  h1_data.py 를 고친 결과가 바뀌면 시험이 실패한다(⑥-i: 받기 고침은 이 결과를 바꾸지 않아야 함).

사용: python tests/golden_data_make.py        (이미 있으면 덮어씀 — 처음 만들 때·의도한 변경 때만)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GDIR = Path(__file__).resolve().parent / "golden_data"
NaN = None

DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]


def ohlcv(base, k, vol):
    o = round(base * (1 + 0.004 * k), 2)
    return [o, round(o * 1.012, 2), round(o * 0.991, 2), round(o * 1.003, 2), vol]


def kr_halt():
    """005930: 11-04 정지(OHL 0, 종가 = 직전 종가, 거래량 0), 11-05 정지(OHLC 전부 직전 종가, 거래량 0),
    11-06 거래량 NaN, 11-09 종가 NaN, 11-10 = 장중 미완성 봉 시험용 마지막 봉."""
    rows = [ohlcv(70000, 0, 11_000_000), ohlcv(70000, 1, 9_500_000)]
    prev_close = rows[-1][3]
    rows.append([0.0, 0.0, 0.0, prev_close, 0])
    rows.append([prev_close, prev_close, prev_close, prev_close, 0])
    rows.append(ohlcv(70000, 4, NaN))
    r = ohlcv(70000, 5, 8_000_000)
    r[3] = NaN
    rows.append(r)
    rows.append(ohlcv(70000, 6, 7_000_000))
    return {"index": DAYS, "columns": ["Open", "High", "Low", "Close", "Volume"], "data": rows}


def kr_korean_volume():
    """000660: 거래량 칸 이름이 '거래량'(옛 제공처 모양), 11-05 정지(거래량 0)."""
    rows = [ohlcv(150000, k, 2_000_000 + k) for k in range(len(DAYS))]
    rows[3] = [rows[2][3]] * 4 + [0]
    return {"index": DAYS, "columns": ["Open", "High", "Low", "Close", "거래량"], "data": rows, "int_columns": ["거래량"]}


def kr_all_nan():
    """035420: 종가가 모두 NaN → 확정 봉 없음(None)."""
    rows = [ohlcv(180000, k, 1000) for k in range(3)]
    for r in rows:
        r[3] = NaN
    return {"index": DAYS[:3], "columns": ["Open", "High", "Low", "Close", "Volume"], "data": rows}


def us_stock():
    """AAPL: 11-05 종가 NaN, 11-10 = 16:15 ET 전후 시험용 마지막 봉, 거래량 정수."""
    rows = [ohlcv(190.0, k, 50_000_000 + k) for k in range(len(DAYS))]
    rows[3][3] = NaN
    rows[3][4] = 0
    return {"index": DAYS, "columns": ["Open", "High", "Low", "Close", "Volume"], "data": rows}


def spy():
    rows = [ohlcv(600.0, k, 80_000_000 + k) for k in range(len(DAYS))]
    return {"index": DAYS, "columns": ["Open", "High", "Low", "Close", "Volume"], "data": rows,
            "int_columns": ["Volume"]}


def ks200():
    rows = [ohlcv(400.0, k, 120_000 + k) for k in range(len(DAYS))]
    return {"index": DAYS, "columns": ["Open", "High", "Low", "Close", "Volume"], "data": rows,
            "int_columns": ["Volume"]}


INPUTS = {"kr_halt.json": kr_halt, "kr_korean_volume.json": kr_korean_volume, "kr_all_nan.json": kr_all_nan,
          "us_stock.json": us_stock, "spy.json": spy, "ks200.json": ks200}

CASES = [
    {"name": "국내 정지 두 모양·거래량 NaN·종가 NaN, 15:59 KST(마지막 봉 장중 → 버림)", "kind": "fetch",
     "market": "kr", "code": "005930", "now": "2026-11-10T15:59:00+09:00", "input": "inputs/kr_halt.json"},
    {"name": "국내 같은 원본, 16:01 KST(마지막 봉 확정)", "kind": "fetch",
     "market": "kr", "code": "005930", "now": "2026-11-10T16:01:00+09:00", "input": "inputs/kr_halt.json"},
    {"name": "국내 거래량 칸 이름 '거래량' + 정지", "kind": "fetch",
     "market": "kr", "code": "000660", "now": "2026-11-10T23:05:00+09:00", "input": "inputs/kr_korean_volume.json"},
    {"name": "국내 종가 모두 NaN → 확정 봉 없음", "kind": "fetch",
     "market": "kr", "code": "035420", "now": "2026-11-10T23:05:00+09:00", "input": "inputs/kr_all_nan.json"},
    {"name": "국내 시장에 미국 코드 → 오류", "kind": "fetch",
     "market": "kr", "code": "AAPL", "now": "2026-11-10T23:05:00+09:00", "input": "inputs/us_stock.json"},
    {"name": "미국 종목 16:14 ET(마지막 봉 미확정 → 버림), 종가 NaN 행", "kind": "fetch",
     "market": "us", "code": "AAPL", "now": "2026-11-10T16:14:00-05:00", "input": "inputs/us_stock.json"},
    {"name": "미국 종목 16:16 ET(마지막 봉 확정)", "kind": "fetch",
     "market": "us", "code": "AAPL", "now": "2026-11-10T16:16:00-05:00", "input": "inputs/us_stock.json"},
    {"name": "미국 받기 실패 → None", "kind": "fetch",
     "market": "us", "code": "MSFT", "now": "2026-11-11T07:10:00+09:00", "input": "raise"},
    {"name": "미국 빈 표 → None", "kind": "fetch",
     "market": "us", "code": "NVDA", "now": "2026-11-11T07:10:00+09:00", "input": "empty"},
    {"name": "대기 자산 SPY 16:14 ET(오늘 봉 버림)", "kind": "idle",
     "market": "us", "code": "SPY", "now": "2026-11-10T16:14:00-05:00", "input": "inputs/spy.json"},
    {"name": "대기 자산 SPY 16:16 ET(오늘 봉 확정)", "kind": "idle",
     "market": "us", "code": "SPY", "now": "2026-11-10T16:16:00-05:00", "input": "inputs/spy.json"},
    {"name": "대기 자산 KS200 22:29 KST(오늘 봉 버림 — 종목 16:00 과 다른 확정 시각)", "kind": "idle",
     "market": "kr", "code": "KS200", "now": "2026-11-10T22:29:00+09:00", "input": "inputs/ks200.json"},
    {"name": "대기 자산 KS200 22:31 KST(오늘 봉 확정)", "kind": "idle",
     "market": "kr", "code": "KS200", "now": "2026-11-10T22:31:00+09:00", "input": "inputs/ks200.json"},
    {"name": "대기 자산 받기 실패 → None", "kind": "idle",
     "market": "kr", "code": "KS200", "now": "2026-11-10T23:05:00+09:00", "input": "raise"},
]


def dump(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def main():
    sys.path.insert(0, str(ROOT))
    import h1
    (GDIR / "inputs").mkdir(parents=True, exist_ok=True)
    for name, fn in INPUTS.items():
        (GDIR / "inputs" / name).write_bytes(dump(fn()))
    (GDIR / "cases.json").write_bytes(dump(CASES))
    (GDIR / "outputs.json").write_bytes(h1.data_golden_outputs(GDIR))
    print(f"골든 {GDIR}: 원본 {len(INPUTS)}개, 경우 {len(CASES)}개, 지문 {h1.data_golden_digest(GDIR)}")


if __name__ == "__main__":
    main()
