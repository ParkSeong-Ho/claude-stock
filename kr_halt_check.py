"""
kr_halt_check.py - 국내 장부에 '거래정지일 체결'이 남아 있는지 확인한다 (읽기만 함, 아무것도 안 고침)
------------------------------------------------------------------
왜 필요한가 (docs/kr-fix-s0.md, S0-2, 2026-11-04):
- 2026-11-04 전 코드는 시가(Open)가 0 이하이면 종가로 대신 체결했다(main.open_price).
- 그런데 네이버(FinanceDataReader) 국내 시세의 거래정지일 행은 이렇게 생겼다.
    · 'Open=High=Low=0, Close=직전 종가, Volume=0'          (예: 삼성전자 2018-04-30 ~ 05-03)
    · 'Open=High=Low=Close=직전 종가, Volume=0'             (삼성바이오로직스 2018-11-15 ~ 12-10)
  그래서 거래가 하나도 없던 날 직전 종가로 '체결'된 기록이 장부에 남았을 수 있다.
- 이 스크립트는 장부의 체결(매수·매도) 날짜를 **새로 받은 원본 시세**와 맞춰 보고,
  그날이 그 종목의 거래정지일(Volume == 0 또는 Open <= 0)이면 알려 준다.

보는 파일 (전부 '읽기'만 한다. 쓰기·이름 바꾸기·지우기 없음):
  state/kr/team_<트레이너>.json              team.py 장부 (지갑의 거래 기록 wallet.log)
  state/kr/<종목>_<트레이너>.json             live.py 장부 (wallet.log)
  state/kr/*.old-*.json                      예전 형식이라 보관된 장부 (있으면 같이 보고 '보관본'이라 표시)
  results/kr_<종목>_<트레이너>_거래내역.csv     main.py 백테스트 거래내역 (main.py 는 state 를 안 쓰고 여기만 씀)
  ※ state/broker/ (order_runner 의 증권사 주문 기록)는 장부가 아니라서 보지 않는다.

실행 (프로젝트 폴더에서, 인터넷 필요):
    python kr_halt_check.py
    python kr_halt_check.py --state state/kr --results results     # 폴더를 직접 지정
종료코드: 0 = 정지일 체결 없음 / 1 = 정지일 체결 있음 / 2 = 확인 못 함(시세를 못 받음 등)

찾았을 때: 이 스크립트는 장부를 고치지 않는다. 어떻게 할지는 사람이 정한다
(예: 그 트레이너 상태 파일을 다른 이름으로 보관하고 새로 시작). docs/kr-fix-s0.md 참고.
"""

import argparse
import csv
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import markets   # 표준 라이브러리만 쓰는 가벼운 파일 (국내 6자리 코드 확인용)

ROOT = Path(__file__).parent
FILL_KINDS = ("매수", "매도")      # 장부에서 '체결'로 보는 종류 (입금·보류는 체결이 아님)


# ---------------- ① 장부에서 체결 모으기 ----------------

def _fills_from_log(log, source, trainer):
    """지갑 거래 기록(list of dict) → 체결 목록. 매수·매도만."""
    out = []
    for e in log or []:
        if not isinstance(e, dict) or e.get("종류") not in FILL_KINDS:
            continue
        out.append({
            "source": source, "trainer": trainer, "kind": e["종류"],
            "code": str(e.get("종목") or ""), "date": str(e.get("시각") or "")[:10],
            "shares": e.get("수량"), "amount": e.get("금액"),
        })
    return out


def collect_fills(state_dir, results_dir):
    """국내 장부 파일들에서 체결을 모은다. (체결 목록, 참고 메모 목록)을 돌려준다. 파일은 읽기만."""
    fills, notes = [], []
    state_dir, results_dir = Path(state_dir), Path(results_dir)
    if state_dir.is_dir():
        for f in sorted(state_dir.glob("*.json")):
            try:
                st = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                notes.append(f"{f.name}: 읽지 못함({type(e).__name__}) — 건너뜀")
                continue
            wallet = st.get("wallet") if isinstance(st, dict) else None
            if not isinstance(wallet, dict):
                notes.append(f"{f.name}: 지갑(wallet)이 없어 장부 파일이 아님 — 건너뜀")
                continue
            kind = "team" if f.name.startswith("team_") else "live"
            if ".old-" in f.name:
                kind += "(보관본)"
            fills += _fills_from_log(wallet.get("log"), f"{kind} {f.name}", wallet.get("name", "?"))
    else:
        notes.append(f"{state_dir} 폴더가 없음 (team/live 국내 장부 없음)")
    if results_dir.is_dir():
        for f in sorted(results_dir.glob("kr_*_거래내역.csv")):
            try:
                with open(f, encoding="utf-8-sig", newline="") as fp:
                    rows = list(csv.DictReader(fp))
            except (OSError, csv.Error, UnicodeDecodeError) as e:
                notes.append(f"{f.name}: 읽지 못함({type(e).__name__}) — 건너뜀")
                continue
            trainer = f.name[:-len("_거래내역.csv")].rsplit("_", 1)[-1]
            fills += _fills_from_log(rows, f"main {f.name}", trainer)
    return fills, notes


# ---------------- ② 원본 시세에서 거래정지일 찾기 ----------------

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return f


def halt_days(df):
    """원본 시세(거래정지 행을 버리기 전) → {'YYYY-MM-DD': 이유}. 이유: 'Volume=0' / 'Open<=0' / 'Open 없음'."""
    out = {}
    has_vol, has_open = "Volume" in df.columns, "Open" in df.columns
    for ts, row in df.iterrows():
        why = []
        if has_vol and _num(row["Volume"]) == 0:
            why.append("Volume=0")
        o = _num(row["Open"]) if has_open else float("nan")
        if not math.isfinite(o):
            why.append("Open 없음")
        elif o <= 0:
            why.append("Open<=0")
        if why:
            out[ts.date().isoformat()] = ", ".join(why)
    return out


def fdr_raw(code, start):
    """FinanceDataReader 원본 시세. main.load_prices 는 이제 정지 행을 버리므로 일부러 쓰지 않는다."""
    import FinanceDataReader as fdr
    return fdr.DataReader(code, start)


# ---------------- ③ 맞춰 보기 ----------------

def check(fills, loader=fdr_raw):
    """체결 목록을 종목별 원본 시세와 맞춘다. (정지일 체결, 날짜 없는 체결, 참고 메모, 확인한 종목 수)."""
    bad, missing, notes = [], [], []
    by_code = {}
    for x in fills:
        by_code.setdefault(x["code"], []).append(x)
    checked = 0
    for code, xs in sorted(by_code.items()):
        if not markets.code_ok("kr", code):
            notes.append(f"{code}: 국내 6자리 종목코드가 아님 — 건너뜀 ({len(xs)}건)")
            continue
        days = sorted(x["date"] for x in xs)
        try:
            start = (date.fromisoformat(days[0]) - timedelta(days=10)).isoformat()
        except ValueError:
            notes.append(f"{code}: 체결 날짜를 읽을 수 없음({days[0]!r}) — 건너뜀")
            continue
        try:
            df = loader(code, start)
        except BaseException as e:            # 라이브러리 없음(SystemExit 등)·인터넷 오류
            if isinstance(e, KeyboardInterrupt):
                raise
            notes.append(f"{code}: 시세를 못 받아 확인 못 함({type(e).__name__}) — {len(xs)}건")
            continue
        if df is None or len(df) == 0:
            notes.append(f"{code}: 시세가 비어 있어 확인 못 함 — {len(xs)}건")
            continue
        checked += 1
        halts = halt_days(df)
        have = {ts.date().isoformat() for ts in df.index}
        first, last = min(have), max(have)
        for x in xs:
            if x["date"] in halts:
                bad.append({**x, "why": halts[x["date"]]})
            elif first <= x["date"] <= last and x["date"] not in have:
                missing.append(x)
    return bad, missing, notes, checked


def _line(x):
    amt = x.get("amount")
    try:
        amt_txt = markets.money("kr", float(amt), sign=False)
    except (TypeError, ValueError):
        amt_txt = str(amt)
    why = f" ({x['why']})" if x.get("why") else ""
    return (f"    - {x['source']} | {x['trainer']} | {x['kind']} {x['code']} {x['date']}"
            f" {x.get('shares')}주 {amt_txt}{why}")


def main(argv=None, loader=fdr_raw, out=print):
    ap = argparse.ArgumentParser(description="국내 장부의 거래정지일 체결 점검 (읽기만 함)")
    ap.add_argument("--state", default=str(ROOT / "state" / "kr"), help="국내 상태 폴더 (기본 state/kr)")
    ap.add_argument("--results", default=str(ROOT / "results"), help="main.py 결과 폴더 (기본 results)")
    ns = ap.parse_args(argv)

    out("=" * 60)
    out(" 국내 장부 '거래정지일 체결' 점검 — 읽기만 해요 (파일은 하나도 안 고쳐요)")
    out("=" * 60)
    fills, notes = collect_fills(ns.state, ns.results)
    if not fills:
        for n in notes:
            out(f"  (참고) {n}")
        out("  장부에 체결(매수·매도)이 하나도 없어요. 확인할 것이 없음 → 끝.")
        return 0
    codes = {x["code"] for x in fills}
    out(f"  장부 체결 {len(fills)}건 (종목 {len(codes)}개) — 원본 시세를 받아 맞춰 보는 중...")
    bad, missing, more, checked = check(fills, loader)
    for n in notes + more:
        out(f"  (참고) {n}")
    if missing:
        out(f"  (참고) 시세에 그 날짜 봉이 아예 없는 체결 {len(missing)}건 — 데이터가 바뀌었을 수 있어요:")
        for x in missing:
            out(_line(x))
    if checked == 0:
        out("  ❓ 시세를 하나도 못 받아 확인하지 못했어요. 인터넷 연결과 finance-datareader 설치를 확인하세요.")
        return 2
    if not bad:
        out(f"  ✅ 거래정지일 체결 없음 (확인한 종목 {checked}개).")
        return 0
    out(f"  ⚠️ 거래정지일 체결 {len(bad)}건 — 실제로는 거래가 없던 날이라 불가능한 체결이에요:")
    for x in bad:
        out(_line(x))
    out("  → 이 스크립트는 장부를 고치지 않아요. 어떻게 할지(예: 그 상태 파일을 보관하고 새로 시작)는")
    out("    사람이 정하세요. 자세한 설명: docs/kr-fix-s0.md")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
