"""오프라인 점검(probe): 네트워크가 막혀 실제 시세 없이, 합성 데이터로 의심 지점만 재현한다.
저장소 코드는 수정하지 않고 import + monkeypatch만 사용. 실행: python reports/2026-11-04-baseline/probes/offline_probes.py
"""
import sys, json, tempfile, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
import main, team, analyst, live
from paper_wallet import PaperWallet
from risk_guard import CircuitBreaker

def hdr(t): print("\n" + "=" * 70 + f"\n[P] {t}\n" + "=" * 70)

# ---------- P1: max(1, int(cash*cap/price)) 상한 초과 ----------
hdr("P1 종목상한 초과 매수 (max(1, ...))")
for tname, price in [("파이오니어", 50_000), ("파이오니어", 90_000), ("스프린터", 250_000), ("마라토너", 700_000)]:
    cash = int(main.CONFIG["총_가상자금"] * main.CONFIG["배분비율"][tname]); cap = main.CONFIG["종목상한"][tname]
    shares = max(1, int(cash * cap / price))
    w = PaperWallet(name=tname); w.deposit(cash); ok = w.buy("X", price, shares)
    spent = cash - w.cash
    print(f"{tname} 예산 {cash:,} 상한 {cap:.0%}(={cash*cap:,.0f}) 가격 {price:,} → {shares}주, 체결={ok}, "
          f"실제투입 {spent:,.0f} = 예산의 {spent/cash:.0%} (상한의 {spent/(cash*cap):.1f}배)" if ok else
          f"{tname} 예산 {cash:,} 상한 {cash*cap:,.0f} 가격 {price:,} → {shares}주, 체결=False(현금부족, 조용히 무시)")

# ---------- P2: 원화/달러 혼합 ----------
hdr("P2 원화 지갑으로 달러 종목 매수 (team.py는 S&P500만 → 달러가격을 원으로 취급)")
tname = "마라토너"; cash = int(1_000_000 * 0.60); cap = 0.30
usd_price = 500.0; fx = 1400
shares = max(1, int(cash * cap / usd_price))
w = PaperWallet(name=tname); w.deposit(cash); w.buy("MSFT", usd_price, shares)
print(f"가격 ${usd_price} 를 '{usd_price}원'으로 계산 → {shares}주 매수, 지갑 차감 {cash - w.cash:,.0f}원")
print(f"실제 가치는 {shares}주 × ${usd_price} × {fx}원 = {shares*usd_price*fx:,.0f}원 (예산 {cash:,}원의 {shares*usd_price*fx/cash:,.0f}배)")
print("main.py/live.py도 005930(원)과 AAPL(달러)을 같은 CONFIG 원화 예산으로 매매 → 순손익 단위가 종목마다 다름")

# ---------- P3: 체결가 = 신호 낸 그 봉의 종가 ----------
hdr("P3 체결가 = 신호를 계산한 당일 종가 (main.py run_one_trainer)")
idx = pd.bdate_range("2025-01-01", periods=120)
rng = np.random.default_rng(0)
close = pd.Series(100 * np.cumprod(1 + rng.normal(0.001, 0.02, len(idx))), index=idx)
df = pd.DataFrame({"Open": close.shift(1).fillna(100), "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1e6}, index=idx)
from sprinter_brain import SprinterBrain
r = main.run_one_trainer("스프린터", SprinterBrain(), df, 300_000, 0.20, "SYN", CircuitBreaker())
print(f"합성 데이터 매수 {r['buys']}회. 판단은 window=df.iloc[:day+1](당일 종가 포함), 체결도 같은 row['Close'] → "
      "'종가 보고 종가에 산다'(현실에선 다음날 시가). 미래 봉 참조는 없음.")
# 승률이 비용 무시
print(f"승률 계산: price > entry (비용 무시). 결과 승률={r['win_rate']}")

# ---------- P4: analyst 파싱 ----------
hdr("P4 analyst._extract_json / conviction 타입")
cases = {
  "코드블록": '```json\n{"analysis":[{"code":"A","verdict":"buy","conviction":0.7,"note":"x"}]}\n```',
  "JSON 뒤에 중괄호 섞인 설명": '{"analysis":[{"code":"A","verdict":"buy","conviction":0.7}]}\n참고: {예시} 입니다',
  "JSON 두 개": '{"a":1}\n{"analysis":[{"code":"A","verdict":"buy","conviction":0.7}]}',
  "note 안에 } 포함": '{"analysis":[{"code":"A","verdict":"buy","conviction":0.7,"note":"MA{20}"}]}',
}
for k, v in cases.items():
    print(f"  {k:<28} → {'파싱OK' if analyst._extract_json(v) else 'None(폴백)'}")
for conv in ["0.8", "높음", 0, None]:
    c = {"code": "A", "conviction": conv}
    try:
        print(f"  conviction={conv!r:<8} keep_candidate → {team.keep_candidate(c)}")
    except Exception as e:
        print(f"  conviction={conv!r:<8} keep_candidate → 예외 {type(e).__name__}: {e}")
kept = analyst.apply([{"code": "A"}], {"A": {"verdict": "hold", "conviction": 0.9, "note": "확신 없음"}})
print(f"  verdict='hold', conviction=0.9 → apply 후 남음={bool(kept)} keep={team.keep_candidate(kept[0])} (hold인데 매수됨)")
try:
    l = [{"code": "A", "conviction": "0.8"}, {"code": "B", "conviction": 0.6}]
    l.sort(key=lambda c: c.get("conviction") or 0, reverse=True); print("  정렬 OK")
except Exception as e:
    print(f"  str/float 섞인 conviction 정렬 → {type(e).__name__}: {e}")

# ---------- P5: team.py 달력날짜 멱등/휴장일, 예외 전파, 비원자적 저장 ----------
hdr("P5 team.run_trainer: 달력 날짜, 휴장일, 예외")
tmp = Path(tempfile.mkdtemp()); team.STATE_DIR = tmp
fri = df.copy()
calls = {"n": 0}
def fake_load(code, start): calls["n"] += 1; return fri
main.load_prices = fake_load
analyst.analyze = lambda t, c, timeout=0: None   # claude 호출 차단
import datetime as _dt
class FakeDT(_dt.datetime):
    cur = _dt.datetime(2025, 6, 20, 17)   # 금요일
    @classmethod
    def now(cls, tz=None): return cls.cur
team.datetime = FakeDT
cand = [{"code": "SYN", "price": float(fri["Close"].iloc[-1]), "rsi": 60, "reason": "합성"}]
br = CircuitBreaker(0.10, 0.07)
for day in [_dt.datetime(2025, 6, 20, 17), _dt.datetime(2025, 6, 21, 17), _dt.datetime(2025, 6, 22, 17), _dt.datetime(2025, 6, 23, 17)]:
    FakeDT.cur = day
    out = team.run_trainer("스프린터", 300_000, 0.20, br, cand)
    st = json.loads((tmp / "team_스프린터.json").read_text(encoding="utf-8"))
    dh = {k: v["days_held"] for k, v in st["positions"].items()}
    print(f"  {day.date()}({'월화수목금토일'[day.weekday()]}) 데이터 마지막봉={fri.index[-1].date()} → {out[:70]} | days_held={dh}")
print("  → 데이터는 그대로(같은 봉)인데 토·일 실행도 '하루'로 세어 days_held 증가 → 스프린터 3일 시간제한이 주말에 소진")

# 예외 한 번에 전체 루프 사망
def boom(code, start): raise RuntimeError("시세 서버 오류(가정)")
main.load_prices = boom
FakeDT.cur = _dt.datetime(2025, 6, 24, 17)
out = team.run_trainer("스프린터", 300_000, 0.20, br, cand)
print(f"  보유종목 시세 실패 시: {out[:90]} → 'continue'로 조용히 넘어가고 평가는 매입가로 계산(손실 은폐)")
# 저장 중 죽으면?
import inspect
src = inspect.getsource(team._save)
print("  _save:", "write_text 직접 덮어쓰기(임시파일+rename 아님) → 저장 중 중단 시 JSON 절단 가능" if "write_text" in src and "replace" not in src else src)
(tmp / "team_마라토너.json").write_text('{"wallet": {"name": "마', encoding="utf-8")   # 깨진 파일 가정
try:
    team.run_trainer("마라토너", 600_000, 0.30, br, [])
except Exception as e:
    print(f"  깨진 state 파일 로드 → {type(e).__name__}: {str(e)[:60]} (run() 전체 중단, 이후 트레이너 미실행)")

# ---------- P6: live.py 상태 복원 시 비용 필드 누락 ----------
hdr("P6 live._wallet_from_dict 가 sell_tax_rate/slippage를 버림")
w = PaperWallet(name="t", sell_tax_rate=0.002, slippage=0.001); w.deposit(1)
w2 = live._wallet_from_dict(json.loads(json.dumps(live._wallet_to_dict(w))))
print(f"  저장 전 sell_tax_rate={w.sell_tax_rate}, slippage={w.slippage} → 복원 후 {w2.sell_tax_rate}, {w2.slippage}")

hdr("P7 거래세")
print(f"  PaperWallet 기본 sell_tax_rate = {PaperWallet(name='x').sell_tax_rate} (0.18%) / 과제 기준 현행 0.20%")
