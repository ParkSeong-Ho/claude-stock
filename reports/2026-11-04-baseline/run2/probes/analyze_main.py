"""run2 분석 스크립트: main.py를 고치지 않고 import해서 같은 계산을 다시 돌리며
(1) 매수 시점 투입액 vs 종목상한, (2) 실패한 매수 시도, (3) buy&hold 비교, (4) NaN 마지막 봉을 기록한다.
실행: (저장소 루트에서) python reports/2026-11-04-baseline/run2/probes/analyze_main.py"""
import sys, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import main as M
from paper_wallet import PaperWallet

events = []
_orig_buy = PaperWallet.buy
def spy_buy(self, code, price, shares):
    ok = _orig_buy(self, code, price, shares)
    events.append(dict(trainer=self.name, code=code, price=price, shares=shares, ok=ok,
                       amount=price*(1+self.slippage)*shares*(1+self.fee_rate)))
    return ok
PaperWallet.buy = spy_buy

C = M.CONFIG
breaker = M.CircuitBreaker(cum_limit=C["서킷브레이커"]["누적한도"], day_limit=C["서킷브레이커"]["일일한도"])
brains = {"마라토너": M.MarathonerBrain(), "스프린터": M.SprinterBrain(), "파이오니어": M.PioneerBrain()}
rows = []
for nm, code in C["종목목록"].items():
    df = M.load_prices(code, C["시작일"])
    nan_tail = df["Close"].tail(3).isna().tolist()
    print(f"\n[{nm} {code}] 마지막 3봉 Close NaN 여부={nan_tail}, 마지막 날짜={df.index[-1].date()}")
    for t, brain in brains.items():
        cash = int(C["총_가상자금"] * C["배분비율"][t]); cap = C["종목상한"][t]
        events.clear()
        r = M.run_one_trainer(t, brain, df, cash, cap, code, breaker)
        need = 60 if t == "마라토너" else 20
        cl = df["Close"].dropna()
        # buy&hold: 지표 준비된 첫날 종가에 예산 전부 매수, 마지막 유효 종가 평가(비용 0.31% 왕복 차감)
        p0 = float(df["Close"].iloc[need]); p1 = float(cl.iloc[-1])
        bh = (p1 / p0 - 1) - 0.0031
        okb = [e for e in events if e["ok"]]; fail = [e for e in events if not e["ok"]]
        over = [e for e in okb if e["amount"] > cash*cap*1.0001]
        maxratio = max((e["amount"]/(cash*cap) for e in okb), default=0)
        maxbudget = max((e["amount"]/cash for e in okb), default=0)
        eq = [v for _, v in r["equity_curve"]]
        stop_day = None
        if r["stopped"]:
            # 마지막으로 평가금액이 변한 날 = 정지일 근사
            for i in range(len(r["equity_curve"])-1, 0, -1):
                if r["equity_curve"][i][1] != r["equity_curve"][i-1][1]:
                    stop_day = r["equity_curve"][i][0]; break
        last_eq = eq[-1] if eq else cash
        rows.append((nm, t, r["profit"], last_eq-cash, r["win_rate"], r["mdd"], r["buys"], r["closed"], bh, cash*bh, len(over), maxratio, maxbudget, len(fail), stop_day))
        print(f"  {t}: 예산 {cash:,} 상한 {cap:.0%}={cash*cap:,.0f} | 매수성공 {len(okb)} 실패 {len(fail)} | 상한초과 {len(over)}건 (최대 상한의 {maxratio:.1f}배, 예산의 {maxbudget:.0%})"
              f" | 순손익(출력) {r['profit']:+,.0f} | 마지막 유효일 평가 기준 {last_eq-cash:+,.0f} | B&H {bh:+.1%} ({cash*bh:+,.0f}) | 정지일≈{stop_day}")
        for e in fail[:3]:
            print(f"     실패 예: 가격 {e['price']:,.2f} × {e['shares']}주 = {e['amount']:,.0f} > 현금")
        for e in over[:2]:
            print(f"     초과 예: 가격 {e['price']:,.2f} × {e['shares']}주 = {e['amount']:,.0f} (상한 {cash*cap:,.0f})")
        if okb and code.isalpha():
            e = okb[0]
            print(f"     통화 예: {code} ${e['price']:,.2f} × {e['shares']}주를 '{e['amount']:,.0f}원'으로 처리 → 환율 1,400원 가정 실제 약 {e['amount']*1400:,.0f}원")

print("\n|종목|트레이너|순손익(출력)|순손익(마지막 유효봉)|승률|MDD|매수|완료|B&H 수익률|B&H 같은 예산 손익|상한초과 건수|최대 상한배수|정지일≈|")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for nm,t,p,p2,wr,mdd,b,c,bh,bhw,no,mr,mb,nf,sd in rows:
    pf = "nan" if (isinstance(p,float) and math.isnan(p)) else f"{p:+,.0f}"
    print(f"|{nm}|{t}|{pf}|{p2:+,.0f}|{'-' if wr is None else f'{wr:.0f}%'}|{mdd:.0%}|{b}|{c}|{bh:+.1%}|{bhw:+,.0f}|{no}|{mr:.1f}|{sd or '-'}|")
