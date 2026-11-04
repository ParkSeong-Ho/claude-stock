# R1 오픈소스 조사: 세 트레이너 구조를 지키면서 시장에 지지 않으려면 (2026-11-04)

> 브랜치 `research-oss-2026-11-04` (포크 ParkSeong-Ho/claude-stock, `kr-broker`에서 분기). 저장소 코드(.py)는 **한 줄도 고치지 않았다.** 새 파일은 이 폴더에만 있다. 백테스트는 돌리지 않았다(그건 R2). 진짜 돈은 0원이다.
>
> 먼저 읽은 것: `AI트레이너_주식자동매매_기획서.md`, `docs/v1-design.md`, `docs/kr-broker-design.md`, `research-2026-11-04` 브랜치의 `reports/research-2026-11-04/REPORT.md`(이하 **R0 조사**), `audit-2026-11-04` 브랜치의 `reports/audit-2026-11-04.md`(이하 **감사**), 그리고 `team.py`·`analyst.py`(팀장 veto/hold 흐름 확인용).
>
> 조사 방법: GitHub 검색 API(`gh api search/repositories`)로 저장소를 찾고 별 수·마지막 push·라이선스를 받았다(값은 **2026-11-04 06:23 UTC 기준**). README는 `raw.githubusercontent.com`으로 읽었고, 핵심 코드는 얕은 복제(`git clone --depth 1`)로 직접 열어 봤다(bt, ai-hedge-fund, QuantConnect Lean, pykrx, FinRL 일부 파일). 논문·블로그는 웹 검색으로 1차 출처를 확인했다. 확인하지 못한 값은 **(미확인)**이라고 적었다.

---

## 0. 결론 한눈에

**짧은 답.** 조사한 오픈소스 중 "일봉 규칙 타이밍으로 지수를 꾸준히 이긴다"를 믿을 만한 근거(긴 기간·여러 종목·실운용 기록)로 보여 준 곳은 **하나도 없었다.** 시장에 지지 않으려고 실제로 쓰는 방법은 "더 잘 맞히기"가 아니라 대부분 아래 세 가지다.

1. **돈을 놀리지 않는다.** 전략이 쉬는 동안 돈을 현금이 아니라 지수에 둔다(cash equitization, "쉬는 돈 지수화").
2. **위험은 '끄기'보다 '줄이기'.** 크게 빠지면 매매를 영구 정지하는 대신 크기를 절반으로 줄이고, 회복하면 돌아온다.
3. **검증을 미리 정한 대로 한다.** 비교 대상·성공 기준을 먼저 적고(사전 등록), 무작위 대조·생존편향 없는 종목군으로 확인한다.

**우리 문제의 핵심 숫자 (R0 조사 결과로 계산, 추정).** R0 조사의 보유 비율(마라토너 46%·스프린터 7%·파이오니어 33%)을 60/30/10으로 섞으면, 2015~2026 동안 **돈의 평균 약 33%만 주식에 들어가 있었다.** 나머지 약 3분의 2는 현금으로 쉬었다. 같은 방식으로 섞은 세 트레이너 합산 수익은 약 **+154%**, SPY는 **+263%**였다. 국면별로 보면 2023-26 상승장에서 투자 비율 32%, 합산 +34.8%(SPY +95.6%)였다. **"고르는 실력"보다 "돈이 쉬는 시간"이 먼저 우리를 지게 만든다.**
(계산: 설정 A의 국면별 `수익률`·`보유비율`을 0.6/0.3/0.1로 가중합. 세 트레이너 지갑이 서로 섞이지 않으므로 최종 금액은 선형으로 더해진다. 실제 팀 단위 시뮬레이션은 R2에서 한다.)

### 가져올 것 상위 5개

| # | 가져올 것 | 출처 (라이선스) | 우리 어디에 | 기대 효과 | 코드 참고 |
|---|---|---|---|---|---|
| 1 | **쉬는 돈 지수화**: 트레이너가 안 쓰는 현금은 SPY(국내는 KODEX 200 `069500`)에 넣어 두고, 매수 신호가 나오면 지수를 팔아 그 돈을 쓴다. 트레이너는 자기 몫 100%의 주인으로 남는다. | 기관의 cash equitization 관행(§2), `pmorissette/bt` 트리 구조(MIT), Antonacci·Faber(아이디어) | `paper_wallet.py`(대기 자금 칸), `team.py`(매수 전 지수 매도·매도 후 지수 매수), `markets.py`(시장별 대기 자산) — **세 트레이너 모두** | 쉬는 3분의 2가 시장 수익을 받는다. "시장보다 크게 지는" 주원인 제거 | 가능(MIT) |
| 2 | **대기 자금에만 추세 필터**: 지수가 10개월 평균선 아래면 대기 자금은 현금, 위면 지수. 트레이너 매매 규칙은 그대로. | Faber 10개월선, Antonacci 절대 모멘텀, Keller DAA 카나리아(아이디어), `oronimbus/tactical-asset-allocation`(MIT) | 새 함수(예: `markets.py` 또는 새 모듈) + `team.py` 월말 1회 | 1번이 2022 같은 하락장에서 잃는 것을 일부 막는다 | 가능(MIT) / 논문은 아이디어 |
| 3 | **단계적 서킷 브레이커**: 고점 대비 -10%면 새 매수 크기 절반, -20%면 정리 후 대기, 고점 재설정 후 복귀. 지금의 "한 번 걸리면 영구 정지"(감사 C9, D6 미정) 대체 후보. | `virattt/ai-hedge-fund` `RiskLimits.halve_drawdown_pct`·`max_drawdown_pct`(MIT), QuantConnect Lean `MaximumDrawdownPercentPortfolio`(Apache-2.0) | `risk_guard.py`, `team.py` | 영구 현금화(=가장 큰 현금 낭비) 방지, D6 재개 규칙의 구체안 | 가능(MIT·Apache) |
| 4 | **팀장 LLM 결정 성적표 + 과거 백테스트 금지**: veto/hold한 후보가 N일 뒤 실제로 어땠는지 자동 채점. LLM은 과거 구간 백테스트에 넣지 않는다(모델이 과거를 "외우고" 있음). | `TauricResearch/TradingAgents` 결정 기록·사후 채점(Apache-2.0), `ai-hedge-fund` scorecard(MIT), FINSABER 논문·LLM 미리보기 편향 연구 | `analyst.py`·`team.py`(verdict 기록), 새 채점 스크립트 | 팀장이 실제로 손실을 줄이는지, 아니면 현금만 늘리는지 숫자로 안다 | 가능(Apache·MIT) |
| 5 | **검증 틀 고정**: 사전 등록 + 무작위 대조(이미 R0에 있음) + 생존편향 없는 종목군(그때의 S&P500·KOSPI200 구성) + **한국 시장과 앞으로의 모의매매를 홀드아웃(안 보고 남겨 둔 시험)**으로 쓴다. | `bt.backtest.benchmark_random`(MIT), `fja05680/sp500`(MIT), `sharebook-kr/pykrx` 지수 구성종목(날짜 지정), Deflated Sharpe·PBO 논문 | `validate.py`, `universe_check.py`, R2 스크립트 | "운 좋은 한 칸"을 실력으로 착각하는 일을 막는다 | bt·sp500 가능 / pykrx는 LICENSE 파일 없음 → 라이브러리 사용만 |

**사용자 요구("세 트레이너 구조 유지, 지수를 큰 몫으로 따로 떼지 않기")와의 관계.** 1번은 "지수 70% + 트레이너 30%"(지수를 고정된 큰 몫으로 떼어 두는 방식)와 다르다. 세 트레이너가 여전히 60/30/10 전부를 맡고, 지수는 **주차장**일 뿐이다. 신호가 나오면 언제든 꺼내 쓴다. 다만 솔직히 말하면, 지금 규칙대로면 돈의 약 3분의 2가 평소 그 주차장에 있게 된다. 결과가 지수와 비슷해 보일 것이다. 트레이너가 "지수보다 나은 것"을 보태는지는 R2의 무작위 대조로 따로 잰다(§7).

---

## 1. 여러 전략·여러 에이전트에 자금을 나눠 운용하는 프로젝트

| 저장소 | 별 | 마지막 push | 라이선스 | 핵심 아이디어 | 근거 수준 | 우리에게 맞는 점 | 안 맞는 점 |
|---|---:|---|---|---|---|---|---|
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,470 | 2026-11-03 | MIT | 펀드 = 여러 "포드(pod, 전략팀)". 각 포드에 자본 몫(`weight`) → **배분기(allocator)**가 포드 성적의 t-통계량으로 몫을 천천히 조정: `몫 = 기본몫 × clip(1 + 0.25·t, 0.25, 2.0)`, 기록이 20기간 미만이면 기본몫 그대로(`hedge_fund/fund/spec.py` `AllocationPolicy`). 공통 위험 한도(`max_position_pct`, `halve_drawdown_pct` 10%, `max_drawdown_pct` 20%) | 코드만. 성과 기록 없음. README: "교육용, 실제 매매 아님" | 구조가 우리와 거의 같다(예시 설정이 0.6/0.4 두 포드). "증거가 쌓이기 전엔 몫을 안 움직인다"는 규칙이 명시적 | LLM 투자자 페르소나가 판단의 중심. 데이터는 유료 API(Financial Datasets) |
| [pmorissette/bt](https://github.com/pmorissette/bt) | 3,016 | 2026-11-03 | MIT | **전략의 전략**: 트리 구조로 "자식이 종목일 수도, 다른 전략일 수도" 있다. 문서가 "헤지펀드처럼 여러 전략에 규칙으로 자본을 배분"한다고 설명(`docs/source/tree.md`). 배분 알고: `WeighEqually`, `WeighInvVol`(변동성 역비례), `WeighERC`(위험 균등), `TargetVol`. **`benchmark_random`**: 같은 구조에서 일부를 무작위로 바꾼 전략 N개와 비교 | 백테스트 도구(성과 주장 없음) | 세 트레이너 = 세 자식 전략, 대기 자금 = 지수 자식. R2 시뮬레이터 설계 참고에 가장 가깝다. 무작위 대조가 내장 | 일 단위 리밸런싱 전제. 우리 `paper_wallet` 장부와 직접 연결되지 않음 |
| [pst-group/pysystemtrade](https://github.com/pst-group/pysystemtrade) (Rob Carver) | 3,578 | 2026-11-02 | GPL-3.0 | 여러 규칙(forecast)과 여러 종목에 **가중치**를 준다. 저자 권장은 "handcrafting"(상관·변동성으로 손으로 짓는 가중치)이고, Sharpe 같은 성과 추정은 "같게 놓기(equalise_SR)"나 "강하게 줄이기(shrinkage)"를 쓴다. 추정 창 기본값은 `expanding`(과거만 사용). 자본 보정은 기본 "고정 자본" | 저자 본인 실운용(선물)에 쓰는 엔진. 공개 성과 기록 (미확인) | "과거 성과로 비중을 크게 움직이지 말라"는 설계 원칙이 R0 결과(훈련↔시험 순위상관 -0.32)와 맞는다 | 선물·레버리지·IB 전용. **GPL → 코드 복사 금지, 아이디어만** |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | 22,377 | 2026-11-03 | Apache-2.0 | 알파(신호) → 포트폴리오 구성 → 위험 관리 → 실행을 **분리**. `ConfidenceWeightedPortfolioConstructionModel`(신호의 확신도를 비중으로), `RiskParityPortfolioConstructionModel`, `MaximumDrawdownPercentPortfolio`(고점 대비 손실 넘으면 정리 후 다음 리밸런싱에 재시작) | 엔진(성과 주장 없음) | 우리 구조(브레인 → team → risk_guard → order_runner)가 이미 같은 분리를 따른다는 확인. 확신도 가중·낙폭 재시작 코드 참고 가능 | C#/클라우드 중심, 우리 규모엔 무겁다 |
| [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 16,976 | 2026-11-03 | MIT | **앙상블**: 분기마다 여러 강화학습 에이전트(A2C·PPO·DDPG…)를 학습하고, 직전 검증 창에서 Sharpe가 가장 높은 것 하나에 다음 분기를 맡김. "난기류(turbulence) 지수"가 문턱(표본 내 90% 또는 99% 분위 — 최근 난기류 평균에 따라 고름)을 넘으면 위험 회피(`finrl/agents/stablebaselines3/models.py` `DRLEnsembleAgent`) | 논문 백테스트(ICAIF 2020, 다우30) | 성과 기반 선택의 대표 사례. 난기류 필터는 국면 필터의 한 형태 | **"직전 1등에게 맡기기"는 R0 walk-forward에서 실패한 방식 그대로**(파이오니어 순위상관 -0.32). 강화학습은 우리 범위 밖 |
| [dcajasn/Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) · [skfolio/skfolio](https://github.com/skfolio/skfolio) | 4,585 · 2,586 | 2026-11-04 · 2026-10-29 | BSD-3 · BSD-3 | 위험 균등(risk parity)·HRP 등 **비중 계산기**. skfolio는 `WalkForward`·`CombinatorialPurgedCV`도 제공 | 라이브러리(성과 주장 없음) | 나중에 60/30/10 대신 "변동성 맞춤 배분"을 시험할 때 계산기로 쓸 수 있다 | 세 트레이너 수익 기록이 아직 짧아(포워드 2026-09~) 추정이 불안정 |
| [MohamedAklamaash/RAMPART](https://github.com/MohamedAklamaash/RAMPART) | 1 | 2026-06-26 | NOASSERTION | "국면 인식 감독자"가 전문 전략들에게 자본을 나눔. README가 **불리한 결과도 그대로** 적음: 국면이 바뀌는 데이터에선 1/N(균등)을 못 이김 — 비중 바꾸는 매매비용이 분산 효과를 먹음 | 합성(가짜) 가격 백테스트만 | "감독자가 자본을 옮기면 비용이 이득을 먹는다"는 정직한 반례 | 별 1개, 합성 데이터. 라이선스 불명 → 아이디어만 |

**정리 — 자금 배분은 실제로 어떻게 하나**
- **고정 비율이 기본값이다.** bt·ai-hedge-fund 모두 사람이 정한 몫에서 시작한다. 우리 60/30/10과 같다.
- **성과로 몫을 옮기는 곳은 "느리게, 증거가 쌓인 뒤에, 상·하한을 두고" 옮긴다.** ai-hedge-fund는 20기간 미만이면 안 움직이고, 아무리 못해도 0.25배, 아무리 잘해도 2배까지만이다. Carver는 아예 성과 추정을 믿지 않는 쪽을 권한다.
- **"직전 1등에게 몰아주기"(FinRL 앙상블)는 우리 데이터에서 이미 실패했다.** R0 walk-forward에서 과거 2년 1등 설정이 다음 해에 오히려 나빴다(순위상관 -0.32). 같은 일이 트레이너 사이 배분에도 일어날 수 있다. 그래서 성과 기반 재배분은 R2에서 **떨어질 것으로 예상하고** 시험한다(§7 H4).
- **배분을 자주 바꾸면 비용이 이득을 먹는다**(RAMPART의 정직한 반례).

---

## 2. 쉬는 현금 처리 — cash drag, 쉬는 돈 지수화, 듀얼 모멘텀, 국면 필터

**용어 풀이 (초보자용)**
- **cash drag(현금 끌림)**: 돈 일부가 현금으로 놀면, 시장이 오를 때 그만큼 못 따라간다. 시장이 1년에 10% 오르는데 돈의 3분의 2가 놀면, 고르는 실력이 아무리 좋아도 출발선이 이미 뒤다.
- **cash equitization(쉬는 돈 지수화)**: 펀드가 들고 있어야 하는 현금을 지수 선물이나 ETF로 "시장에 담가 두는" 관행. 필요할 때 바로 빼 쓴다.
- **절대 모멘텀**: "지수가 최근 12개월 동안 현금(단기 국채)보다 많이 올랐나?" 아니면 위험자산에서 빠진다.
- **추세 필터(국면 필터)**: "지수가 10개월(약 200거래일) 평균보다 위인가?" 위면 위험자산, 아래면 현금.
- **카나리아(canary)**: 광산의 카나리아처럼 먼저 아픈 자산(예: 신흥국 주식·채권)의 모멘텀을 보고 위험을 줄인다.

| 저장소 | 별 | 마지막 push | 라이선스 | 핵심 아이디어 | 근거 수준 | 맞는 점 | 안 맞는 점 |
|---|---:|---|---|---|---|---|---|
| [alexjansenhome/GEM](https://github.com/alexjansenhome/GEM) | 62 | 2017-11-09 | 표기 없음 | Antonacci GEM: S&P500 12개월 수익이 단기 국채보다 낮으면 채권(AGG), 높으면 미국·해외 주식 중 강한 쪽. 1970년(해외)·1926년(절대 모멘텀)부터의 데이터 포함 | 백테스트(장기 지수 데이터) | **절대 모멘텀을 "대기 자금"에만 적용**하는 데 그대로 쓸 수 있는 가장 단순한 규칙 | 월 1회 자산 전환 전략. 종목 고르기 없음. 라이선스 없음 → 아이디어만. 2017 이후 관리 안 됨 |
| [oronimbus/tactical-asset-allocation](https://github.com/oronimbus/tactical-asset-allocation) (pyTAA) | 55 | 2024-12-23 | MIT | 여러 전술적 자산배분(TAA) 전략을 같은 틀로 백테스트·비교. 참고문헌에 Antonacci·Keller(DAA·PAA)·Butler(AAA) | 백테스트 도구 | 추세 필터 변형들을 같은 조건에서 비교하는 틀 | ETF 자산배분용, 개별 종목 매매와는 층이 다르다 |
| [penny-vault/defensive-asset-allocation](https://github.com/penny-vault/defensive-asset-allocation) | 0 | 2026-07-15 | Apache-2.0 | Keller DAA: 모멘텀 점수 `12·(p0/p1)+4·(p0/p3)+2·(p0/p6)+(p0/p12)-19`. 카나리아(VWO·BND) 중 음수 개수가 0이면 위험자산 100%, 1이면 50%, 2면 방어자산 100% | 규칙 설명(성과 수치 없음) | "전부 아니면 전무" 대신 **절반**이라는 중간 단계 | 별 0개. 카나리아 자산이 우리 데이터에 없음 |
| [Kim-Nam-Il/Vigilant-Asset-Allocation](https://github.com/Kim-Nam-Il/Vigilant-Asset-Allocation) | 9 | 2022-11-15 | 표기 없음 | Keller VAA(공격·방어 자산군, 하나라도 모멘텀 음수면 방어) ETF 구현 | 코드만 | 한국 개인 투자자 사이에 많이 알려진 규칙의 구현 예 | 라이선스 없음 → 아이디어만. 설명 거의 없음 |
| [pmorissette/bt](https://github.com/pmorissette/bt) (다시) | 3,016 | 2026-11-03 | MIT | 트리에서 한 자식은 전략, 한 자식은 지수(예: 문서 예시는 "모멘텀 전략 + 채권 AGG"). `TargetVol`로 목표 변동성 맞추기 | 도구 | "트레이너 전략 + 지수 주차장"을 같은 장부에서 표현 | 위와 같음 |
| [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) (다시) | 16,976 | 2026-11-03 | MIT | 난기류 지수 > 표본 내 90% 분위면 매수 중단·정리 | 논문 백테스트 | 시장 전체 위험이 높을 때 신규 매수를 막는 "국면 스위치"의 예 | 임계값이 표본 내 분위수 → 과최적화 위험 |
| [nutcrackerhf/jrp_equitization](https://github.com/nutcrackerhf/jrp_equitization) | 0 | 2025-09-11 | 표기 없음 | 현금을 한 번에/나눠서/늦게 지수에 넣는 방법 비교(Streamlit 장난감 모델) | 장난감 모델 | — | **"쉬는 돈 지수화"를 다룬 오픈소스가 거의 없다는 증거.** 이 아이디어의 근거는 GitHub가 아니라 기관 문서·논문(아래)이다 |

**논문·기관 자료 (웹에서 1차 출처 확인)**

<!-- LIT-A -->

**정리 — 다른 사람들은 쉬는 돈을 어떻게 하나**
- **TAA(듀얼 모멘텀·10개월선·DAA·VAA)는 "종목을 고르는" 전략이 아니라 "지금 주식에 있을지 말지"를 월 1회 정하는 전략이다.** 우리는 종목 고르기를 트레이너가 하므로, 이 규칙을 **트레이너가 안 쓰는 돈(대기 자금)에만** 붙이는 것이 구조를 지키는 방법이다.
- **함정 두 가지.** ① 대기 자금을 지수에 넣으면 2022 같은 하락장에서 "현금이라 덜 잃던" 효과가 사라진다. R0에서 세 트레이너가 이긴 유일한 국면이 2022였는데, 그것도 같이 사라질 수 있다. 그래서 2번(추세 필터)을 짝으로 시험한다. ② 추세 필터는 늦다. 2020년 같은 V자 반등에서는 바닥 근처에서 팔고 한참 위에서 다시 산다(위 문헌의 휩소 비용 참고).
- **매매비용.** 대기 자금을 지수↔주식으로 옮길 때마다 비용이 든다. 스프린터는 11년간 1,286번 샀다(R0). 이 비용을 R2에서 그대로 뗀다.

---

## 3. LLM 트레이딩 에이전트 프로젝트

| 저장소 | 별 | 마지막 push | 라이선스 | LLM이 맡는 역할 | 성과 주장의 근거 | 한계 (직접 확인) | 우리에게 |
|---|---:|---|---|---|---|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 120,445 | 2026-10-27 | Apache-2.0 | **결정.** 분석가(기본·심리·뉴스·기술) → 강세/약세 연구원 토론 → 트레이더 → 위험관리팀 → **포트폴리오 매니저가 승인/거부** | 논문 백테스트(§3 아래 표) | README 스스로 "공개된 수치와 같다는 보장 없음, 연구용 뼈대로 다루라". 같은 날짜·종목도 실행마다 결과가 다름. **2026-07~10에도 미리보기(look-ahead) 수정이 계속 나왔다**(v0.3.1 Alpha Vantage 필터, v0.4.0 FRED·심리·기억, v0.5.0 시점 무결성, v0.7.1 "실행일 이후 공시를 읽던 문제"). 즉 논문 당시 코드에는 이런 누수가 있을 수 있었다 | 결정 기록을 남기고, 보유기간이 지나면 **실현 수익·벤치마크 대비 초과수익으로 자동 채점**, 등급별로 묶어 보는 기능 → 우리 팀장 veto 성적표의 본보기 |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,470 | 2026-11-03 | MIT | **결정(일부).** 버핏·멍거·그레이엄·린치·드러켄밀러 페르소나 LLM + 퀀트 신호(PEAD) → 결정론적 포트폴리오 구성 → **LLM이 못 넘는 위험 한도**. 실행 전 승인 단계 | 없음("교육용", "실제 매매 안 함") | 성과 기록 없음 | 분석가별 정보계수(IC) t-통계로 가중치를 움직이는 scorecard. "위험 한도는 분석가가 못 넘는다" = 우리 risk_guard 원칙과 같다 |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 8,366 | 2026-10-24 | Apache-2.0 | **설명·리서치.** 리서치 보고서, DCF 등 계산은 결정론 엔진, LLM은 분석·작성 | 성과 주장 없음(리서치 도구) | V0(AutoGen)은 "교육용"이라고 명시 | 기획서의 "LLM은 설명·리서치 보조" 원칙과 같은 방향 |
| [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) | 969 | 2024-08-18 | MIT | **결정.** 층별 기억(단기·중기·장기) + 성격(위험 성향) 설정 | 논문 백테스트(아래) | 2024년 이후 관리 안 됨. train 모드에서 기억을 채운 뒤 test | 성격 설정 = 우리 트레이너 페르소나와 비슷. 단, 결정권을 LLM에 줌 |
| [The-FinAI/FinCon](https://github.com/The-FinAI/FinCon) | 71 | 2026-10-08 | MIT | **결정.** 매니저-분석가 위계 + 위험 통제 + "개념적 언어 강화(반성)" | 논문 백테스트(NeurIPS 2024) | 같은 그룹이 라이브 벤치마크(Agent Market Arena, WWW 2026)도 운영 | 위계 구조는 비슷하나 결정권을 LLM에 줌 |
| [waylonli/FINSABER](https://github.com/waylonli/FINSABER) | 152 | 2026-09-17 | Apache-2.0 | **평가 틀.** 기술적 분석·ML·LLM 에이전트(FinMem·FinAgent·FinCon 등)를 같은 조건에서 길게 비교 | 논문(KDD 2026) | 기본 체결이 "다음 날 시가"(같은 날 종가 미리보기 방지) — 우리 D3와 같음 | **"길게·넓게 보면 LLM 우위가 사라진다"는 반대 증거**(아래) |
| [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | 23,099 | 2026-06-11 | 표기 없음 | **결정.** 에이전트들이 거래 아이디어를 공유·모의매매하는 플랫폼(미국 주식·폴리마켓 모의) | 라이브 모의 리더보드 | 모의(가짜 돈) 체결, 기간·표본 짧음 (미확인) | 라이선스 없음 → 아이디어만 |
| [wquguru/nof0](https://github.com/wquguru/nof0) | 2,756 | 2025-12-07 | 표기 없음 | nof1 "Alpha Arena"(LLM 실돈 매매 대회) 재현 | 대회 기록 재현 | 대회 자체가 짧고(수 주), 코인·레버리지 중심 (아래 문헌) | 라이선스 없음 → 아이디어만 |
| [hsliuping/TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 32,787 | 2026-09-22 | NOASSERTION | TradingAgents 중국어·A주 판 | 주장만 | 라이선스 불명 | 아시아 시장 적용 예. 아이디어만 |

**논문 속 주장과 그 한계 (웹에서 1차 출처 확인)**

<!-- LIT-C -->

**정리 — LLM은 어디까지 맡기나**
- 조사한 프로젝트 대부분은 **LLM에게 결정을 맡긴다.** 우리처럼 "규칙이 후보를 내고 LLM은 veto/hold만"인 구조는 TradingAgents의 "포트폴리오 매니저 승인/거부"와 ai-hedge-fund의 "LLM이 못 넘는 위험 한도"가 가장 가깝다. **결정권을 LLM에 주지 않은 지금 설계가 더 보수적이고, 그게 맞다.**
- 다만 우리 구조에는 **숨은 비용**이 있다. 쉬는 돈이 현금이면, 팀장의 veto/hold는 모두 "현금으로 더 쉬기"가 된다. R0에서 이미 돈의 3분의 2가 쉬었다. 대기 자금을 지수에 두면(가져올 것 1), veto는 "지수에 머물기"가 되어 비용이 거의 0이 된다. 두 아이디어는 **짝으로 효과가 있다.**
- **LLM을 과거 구간에 넣은 백테스트는 믿지 않는다.** 모델이 2022 하락·2023 반등을 학습 데이터로 이미 알고 있을 수 있다(미리보기 편향 연구, 위). 팀장 LLM은 **앞으로의 모의매매에서만** 평가한다. R2는 LLM 없는 규칙 폴백으로 돌린다.
- **별 수는 근거가 아니다.** 별 12만 개짜리 TradingAgents의 근거도 몇 달짜리 백테스트다.

---

## 4. 검증 방식 — walk-forward, 무작위 대조, 생존편향, 과최적화 방지

| 저장소 | 별 | 마지막 push | 라이선스 | 핵심 아이디어 | 근거 수준 | 맞는 점 | 안 맞는 점 |
|---|---:|---|---|---|---|---|---|
| [pmorissette/bt](https://github.com/pmorissette/bt) `benchmark_random` | 3,016 | 2026-11-03 | MIT | 같은 구조에서 선택/비중만 무작위로 바꾼 전략 N개(기본 100)와 비교. 날짜·초기자본·비용·정수주 규칙을 그대로 유지(`bt/backtest.py`) | 도구 | R0의 "무작위 타이밍 대조"와 같은 생각. 팀 단위로 넓힐 때 참고 | — |
| [fja05680/sp500](https://github.com/fja05680/sp500) | 960 | 2026-09-07 | MIT | **1996년 이후 S&P500 구성종목 이력**(날짜별). 특정 날짜 스냅샷 예제 포함. 원본은 Clenow 『Trading Evolved』 부록 | 데이터(저자가 위키백과와 대조) | R0 최대 약점(생존편향) 보완: "2015년 1월에 실제로 큰 종목"으로 종목군을 고를 수 있다 | README 스스로 **상장폐지 종목 가격은 Norgate·EODdata 같은 유료 데이터가 필요**하다고 적음. 무료 yahoo로는 빠진 종목이 생긴다 |
| [hanshof/sp500_constituents](https://github.com/hanshof/sp500_constituents) | 31 | 2025-08-24 | MIT | 같은 목적(날짜별 구성 CSV) | 데이터 | 교차 확인용 | 위와 같은 가격 공백 |
| [esvhd/pypbo](https://github.com/esvhd/pypbo) | 145 | 2026-07-06 | **AGPL-3.0** | 백테스트 과최적화 확률(PBO), Probabilistic/Deflated Sharpe, 최소 기록 길이(MinTRL) | 논문 구현 | "격자 32개 중 1등"이 운일 확률을 숫자로 | **AGPL → 코드 복사 금지.** 공식은 논문을 보고 직접 구현 |
| [eslazarev/purged-cross-validation](https://github.com/eslazarev/purged-cross-validation) (purgedcv) | 60 | 2026-10-25 | MIT | purged k-fold, embargo, walk-forward, CPCV(조합 정화 교차검증), deflated Sharpe | 라이브러리 | MIT라 참고 가능. walk-forward 창 나누기 검증 | ML 모델 학습용 설계. 우리 규칙은 학습이 거의 없다 |
| [skfolio/skfolio](https://github.com/skfolio/skfolio) | 2,586 | 2026-10-29 | BSD-3 | `WalkForward(train_size=252, test_size=60)`, `CombinatorialPurgedCV` | 라이브러리 | 같음 | 같음 |
| [bettyguo/agent-backtest-lab](https://github.com/bettyguo/agent-backtest-lab) | 7 | 2026-06-11 | Apache-2.0 | LLM 트레이딩 에이전트 **감사 도구**: 미리보기 누수 탐지, 비용, 다중검정 보정, 기준선 3개(B&H·단순 모멘텀 등) 고정, 경고문 삭제 불가 | 도구(합성 예제) | "에이전트가 단순 추세추종 이상을 하나?"라는 기준선 아이디어 | 별 7개, 신생 |
| [hudson-and-thames/mlfinlab](https://github.com/hudson-and-thames/mlfinlab) | 4,966 | 2023-10-02 | 독점(all rights reserved) | López de Prado 방법(CPCV 등) 구현 | 유료 제품 | — | **독점 → 코드 금지, 아이디어만** |
| [waylonli/FINSABER](https://github.com/waylonli/FINSABER) (다시) | 152 | 2026-09-17 | Apache-2.0 | 긴 기간·넓은 종목·선택기(selector)로 "좋은 종목만 골라 시험" 편향 줄이기, 다음 날 시가 체결 | 논문 | 우리 R0와 같은 방향의 검증 | — |

**논문 (웹에서 1차 출처 확인)**

<!-- LIT-B -->

**정리 — 우리 검증에 더할 것**
- **이미 잘하고 있는 것**: 다음 날 시가 체결(D3), 비용 포함, 무작위 타이밍 대조, walk-forward. R0는 오픈소스 평균보다 엄격하다.
- **더할 것 ① 사전 등록**: 규칙·비교 대상·성공 기준을 결과를 보기 전에 적는다(§7). 시험 횟수도 센다(시험이 많을수록 우연히 하나 걸린다).
- **더할 것 ② 생존편향 줄이기**: 2015년 1월의 S&P500 상위 종목으로 다시 고른다(`fja05680/sp500`). 가격이 없는 종목은 **빠진 개수를 보고서에 적는다**(완전한 해결은 유료 데이터).
- **더할 것 ③ 홀드아웃**: 미국 2015~2026은 R0에서 이미 다 봤다. 진짜 "안 본 시험지"는 **한국 시장(KR 30종목, R0에서 안 씀)**과 **앞으로 쌓일 모의매매**뿐이다. R2 후보는 미국에서 통과해도 한국에서 방향이 같아야 채택한다.

---

## 5. 한국 시장 특화 오픈소스

| 저장소 | 별 | 마지막 push | 라이선스 | 핵심 아이디어 | 근거 수준 | 맞는 점 | 안 맞는 점 |
|---|---:|---|---|---|---|---|---|
| [sharebook-kr/pykrx](https://github.com/sharebook-kr/pykrx) | 1,109 | 2026-10-29 | GitHub 표기 없음(`pyproject.toml`에는 MIT 선언, LICENSE 파일 없음) | KRX 데이터 수집. **`get_index_portfolio_deposit_file(ticker, date)`로 날짜별 지수 구성종목**(예: 코스피 200)을 조회. 코드 주석: "2014년 5월 2일 까지만 조회 가능"(조회 가능 시작일로 읽힘, 실제 범위 (미확인)) | 데이터 라이브러리 | 국내판 생존편향 해결: "그때의 코스피 200"으로 종목군 구성 | **일부 API는 KRX 회원 로그인 필요**(`KRX_ID`·`KRX_PW` 환경변수, README). LICENSE 파일이 없어 코드 복사는 피하고 라이브러리로만 사용 |
| [FinanceData/FinanceDataReader](https://github.com/FinanceData/FinanceDataReader) | 1,561 | 2026-05-13 | MIT | 한국·미국 시세 한 줄 조회 | 라이브러리(이미 사용 중) | 그대로 | 상장폐지 종목 과거 가격은 제한적 (미확인) |
| [HongJunhyoung/Snowball](https://github.com/HongJunhyoung/Snowball) | 4 | 2026-10-07 | MIT | **한국 자산배분 백테스트 패키지.** 예: KODEX 200(`069500`) 60% + 국고채 ETF(`114820`) 40% 월말 리밸런싱, 비용 0.2%. 동일비중·리스크 패리티·사용자 규칙 | 예제 백테스트 | 대기 자금을 KODEX 200에 둘 때의 국내 비교 대상 만들기에 바로 쓸 수 있다(FDR 사용) | 별 4개. 종목 매매는 없음 |
| [hyunyulhenry/quant_py](https://github.com/hyunyulhenry/quant_py) | 270 | 2024-05-14 | 표기 없음 | 책 『파이썬을 이용한 퀀트 투자 포트폴리오 만들기』 코드: 국내 데이터 수집, 가치·모멘텀·퀄리티 팩터, 포트폴리오 구성(riskfolio-lib) | 책 예제 백테스트 | 국내 데이터 수집(네이버·KRX) 방법 참고 | 라이선스 없음 → 아이디어만. 팩터 투자는 우리 일봉 기술적 규칙과 층이 다름 |
| [quantylab/rltrader](https://github.com/quantylab/rltrader) | 366 | 2026-07-25 | MIT | 책 『파이썬을 이용한 딥러닝/강화학습 주식투자』 코드: 국내 종목 강화학습 매매 | 책 예제 | — | 강화학습은 범위 밖, 과최적화 위험 큼 |
| [younghwan91/krx-quant-core](https://github.com/younghwan91/krx-quant-core) | 0 | 2026-11-02 | Apache-2.0 | 국내 비용 모델: **증권거래세가 시행일마다 다름**(README 기재: "2019년 0.25% → 2025년 0.15% → 2026년 0.20%, 여섯 단계"), 가격제한폭 비대칭(호가단위 절사), Deflated Sharpe·purged walk-forward | 저장소 주장(실측 일부, 데이터는 저장소 밖) | 국내 과거 백테스트에서 **세율을 날짜별로** 적용해야 한다는 점 | 별 0개, 막 만든 저장소. 세율 값은 이 조사에서 1차 출처로 확인 못 함 (미확인) |
| [Kim-Nam-Il/Vigilant-Asset-Allocation](https://github.com/Kim-Nam-Il/Vigilant-Asset-Allocation) | 9 | 2022-11-15 | 표기 없음 | VAA(위 §2) | 코드만 | — | 아이디어만 |
| [koreainvestment/open-trading-api](https://github.com/koreainvestment/open-trading-api) | 1,655 | 2026-10-27 | 표기 없음 | KIS 공식 예제(이미 K2에서 "읽기만" 함) | 공식 예제 | — | 코드 복사 금지(kr-broker 설계 안티목표) |

**정리 — 한국 시장**
- **일봉 기술적 규칙으로 KOSPI·KODEX 200을 이긴 기록을 믿을 만하게 보여 주는 국내 오픈소스는 찾지 못했다.** 별이 많은 국내 저장소는 대부분 **데이터 수집·증권사 연결·책 예제**다.
- 국내에서 가져올 것은 전략이 아니라 **재료**다. ① `pykrx`의 날짜별 코스피 200 구성종목(생존편향 줄이기), ② KODEX 200을 대기 자산으로 쓰는 비교(Snowball 예제처럼 FDR로 바로 가능), ③ 날짜별 거래세(국내 과거 백테스트에서 2026 세율 하나로 고정하면 2025년 등이 틀린다).
- **국내 비용은 미국보다 무겁다.** K-D8 기준 왕복 약 0.33%(수수료 0.015%×2 + 매도세 0.20% + 슬리피지 0.05%×2). 미국 D8은 약 0.30%. 스프린터처럼 자주 사고파는 트레이너는 국내에서 더 불리하다. 반대로 국내 주식형 ETF 매도에는 증권거래세가 붙지 않는 것으로 알려져 있다. 그렇다면 대기 자금을 KODEX 200에 두는 비용은 수수료·슬리피지뿐이다. **이 면제 여부는 이 조사에서 1차 출처로 확인하지 못했다 (미확인)** — R2 전에 확인한다.

---

## 6. "가져올 것" 목록

라이선스 규칙: **MIT·Apache·BSD만 코드 참고 가능**(그래도 복사보다 다시 쓰기를 권함, 고지문 유지). **GPL·AGPL·LGPL·표기 없음·NOASSERTION·독점·Commons Clause는 아이디어만.**

| ID | 아이디어 | 출처 | 우리 파일 / 트레이너 | 어떻게 맞출지 | 기대 효과 | 위험 | 코드 차용 |
|---|---|---|---|---|---|---|---|
| G1 | **쉬는 돈 지수화** | 기관 cash equitization(§2 문헌), bt 트리(MIT), Lean 포트폴리오 구성(Apache) | `paper_wallet.py`(대기 자산 보유 칸·평가), `team.py`(①체결 단계에서 매수 필요액만큼 대기 자산 매도 → 같은 시가에 매수, 매도 대금은 대기 자산 매수), `markets.py`(`Market.benchmark`를 대기 자산으로) / 세 트레이너 모두 | 트레이너별로 따로(지갑 섞지 않음). 대기 자산 매매도 비용 D8/K-D8 그대로. 장부에 "대기 자산"을 보유 종목과 구분해 표시 | 상승장 cash drag 제거. R0 기준 돈의 약 3분의 2가 시장 수익을 받음 | 하락장에서 덜 잃던 효과 사라짐, 스프린터 회전 비용 증가, 결과가 지수와 비슷해져 "트레이너 실력"이 가려짐 | bt(MIT) 가능 |
| G2 | **대기 자금 추세 필터** | Faber 10개월선, Antonacci 절대 모멘텀, Keller DAA(논문·아이디어), pyTAA(MIT) | 새 함수(예: `idle_asset(date)`) + `team.py` 월말 1회 / 대기 자금만 | 월말 종가가 10개월(월말 종가) 평균 위 → 대기 자산 = 지수, 아래 → 현금. 다음 거래일 시가 전환 | G1의 하락장 손실 일부 방어 | 휩소(2020 V자), 매개변수 하나라도 고르면 과최적화 → **10개월 하나만 사전 등록** | pyTAA(MIT) 가능 / GEM은 아이디어만 |
| G3 | **단계적 서킷 브레이커 + 재개 규칙** | ai-hedge-fund `halve_drawdown_pct`·`max_drawdown_pct`(MIT), Lean `MaximumDrawdownPercentPortfolio` 재시작(Apache) | `risk_guard.py`, `team.py` / 트레이너별 | 트레이너 고점 대비 -10% → 새 매수 상한 절반, -20% → 정리·20거래일 대기 → 고점 재설정 후 절반 크기로 재개, 새 고점이면 원래 크기 | 영구 현금화 방지(D6 구체안), 손실 구간에서 크기 축소 | 숫자(10/20/20일)를 바꿔 가며 고르면 과최적화 → 사전 등록 값 고정. **D6은 원래 저장소 공동작업자 합의 사항**(v1 설계) — R2 결과는 제안 자료로만 | 가능 |
| G4 | **팀장 결정 성적표** | TradingAgents 결정 기록·사후 채점(Apache), ai-hedge-fund analyst IC scorecard(MIT) | `analyst.py`·`team.py`(이미 `wallet.skip(..., "팀장 hold")` 기록 있음 → veto도 같은 형식으로), 새 채점 스크립트 / 팀장 | 매 veto/hold/buy마다 (날짜, 종목, 판정, 확신도) 저장 → 20거래일 뒤 "샀다면 수익 − 같은 기간 지수 수익"을 채점, 판정별 평균·개수 보고 | 팀장이 손실을 막는지, 현금만 늘리는지 숫자로 확인 | 표본이 적으면 판단 불가 → 최소 개수(예: 판정별 30건) 전엔 결론 금지 | 가능 |
| G5 | **LLM은 과거 백테스트 금지, 규칙 폴백이 기준선** | FINSABER(Apache), LLM 미리보기 편향 연구 | `validate.py`·`tune.py` 문서, R2 스크립트 | 과거 시험은 항상 `analysis=None`(규칙 폴백). LLM 효과는 포워드 모의매매에서 G4로만 | 오염된 백테스트로 LLM을 과대평가하는 일 방지 | 없음(원칙) | — |
| G6 | **느린 성과 기반 재배분** | ai-hedge-fund `AllocationPolicy`(MIT) | `main.CONFIG["배분비율"]`을 분기마다 계산 / 세 트레이너 | 60/30/10 × clip(1+0.25·t, 0.25, 2.0), 기록 20개월 미만이면 고정 | (기대 낮음) 잘하는 트레이너에 조금 더 | **R0에서 과거 성적 → 미래 성적 상관이 음수** → 오히려 해로울 가능성. 시험만 하고 기본값은 고정 유지 | 가능 |
| G7 | **변동성 맞춤 크기** | Carver(GPL, 아이디어), bt `WeighInvVol`·`TargetVol`(MIT), Riskfolio(BSD) | `paper_wallet.shares_within_cap` 주변 / 세 트레이너 | 종목 변동성이 크면 상한 안에서 덜 산다 | 종목 간 위험 고르게, 큰 손실 줄임 | 매개변수 추가 → R3 이후로 | bt·Riskfolio 가능 / pysystemtrade 아이디어만 |
| G8 | **팀 단위 무작위 대조** | bt `benchmark_random`(MIT), R0 `sim.random_factors` | R2 스크립트 → 나중에 `validate.py` / 세 트레이너 | 트레이너 매매를 같은 횟수·보유기간의 무작위 시점으로 바꾼 팀 1,000개와 비교 | "트레이너 기여 = 실제 − 무작위"를 지수화 상태에서도 잴 수 있음 | 계산 시간 | 가능 |
| G9 | **그때의 종목군** | fja05680/sp500(MIT), pykrx(라이브러리만) | `universe_check.py`, R2 스크립트 | 2015-01-02 기준 S&P500 시총 상위 20(국내는 그날 코스피 200 상위 20). 가격 없는 종목 수 보고 | 생존편향 축소 | 시총 순위 자료가 별도로 필요 (미확인), 상장폐지 가격 공백 | sp500 데이터 가능 / pykrx 라이브러리만 |
| G10 | **날짜별 국내 거래세** | krx-quant-core(Apache, 신생) | `markets.py`(KR `sell_tax_rate`를 날짜 함수로, 과거 백테스트용) / 국내 | 시행일 표를 1차 출처(법령·KRX)로 확인한 뒤 적용 | 국내 과거 성적 정확도 | 값 미확인 → 1차 출처 확인 전엔 쓰지 않음 | 가능(단 값은 다시 확인) |
| G11 | **"단순 추세추종" 기준선 추가** | agent-backtest-lab(Apache), Faber | R2 비교표 | 비교표에 "SPY 10개월선"(G2를 대기 자금 100%에 적용한 것)을 참고 줄로 추가 | 트레이너가 "지수 + 단순 추세" 이상을 하는지 확인 | 없음 | — |

**가져오지 않을 것(이번에는)**: 강화학습 앙상블(FinRL·rltrader — 과최적화 위험, 범위 밖), LLM에게 결정권 주기(TradingAgents·FinMem·FinCon 방식), 공매도·레버리지(pysystemtrade 선물), 유료 데이터 의존(ai-hedge-fund Financial Datasets, Norgate).

---

## 7. R2(백테스트)에서 시험할 후보 — 사전 등록

> **사전 등록**이란 결과를 보기 전에 규칙·비교 대상·성공 기준·실패 시 판단을 먼저 적어 두는 것이다. 결과를 본 뒤 기준을 바꾸면 그 결과는 "탐색"으로만 보고하고 채택 근거로 쓰지 않는다. 아래 숫자는 R2 시작 전에 고치지 않는다(고친다면 커밋으로 남기고 이유를 적는다).

### 7.0 공통 조건

| 항목 | 값 |
|---|---|
| 데이터 | `research-2026-11-04` 브랜치 `reports/research-2026-11-04/data/` 그대로(20종목 + SPY, 2015-01-02 ~ 2026-11-03, 분할 반영·배당 미포함, `universe.json`). 새로 받지 않는다. |
| 국면 | R0와 같은 6개: 2015-17 상승 / 2018 조정 / 2020 급락·회복 / 2022 하락 / 2023-26 상승 / 전체 2015-26. 국면마다 현금에서 새로 시작, 지표는 그 이전 데이터로 워밍업. |
| 판단 | 브레인 `decide()` 그대로, 기본값 그대로. **LLM 없음**(규칙 폴백, conviction=None → 통과). |
| 체결·비용 | 봉 t 종가 신호 → 봉 t+1 시가 체결(D3). 수수료 0.1%·슬리피지 0.05%·매도세 0(D8). **지수(SPY) 매매에도 같은 비용.** |
| 팀 구조 | 팀 단위 시뮬레이션(R0의 종목별 슬롯과 다름): 총 **$100,000**, 60/30/10, 트레이너당 지갑 1개, `MAX_POSITIONS=5`, 종목상한 30/20/15%(`team.py`와 같음). 후보가 빈자리보다 많으면 `universe.json` 순서(시총 순위)대로. 정수 주, 0주면 보류 기록. **$100,000 이유**: 감사 C7 — $10,000이면 파이오니어 종목당 $150이라 R0 설정 B의 2023-26에서 파이오니어 매수 시도의 78%(547번 중 429번)가 보류됨. $10,000 결과는 참고로만 같이 낸다. |
| 현금 이자 | 쉬는 현금에 단기 국채 금리(`^IRX` 일할)를 준다. 못 받으면 0%로 하고 표에 표시. (이자를 0으로 두면 "현금 쪽"이 부당하게 불리해진다. 2023-26 단기금리 연 4~5% × 쉬는 비율 3분의 2 ≈ 연 3%p라 결과를 바꿀 수 있는 크기다.) |
| 서킷 브레이커 | H1·H2·H4에서는 **끔**(R0와 같음, 규칙 효과만 보기 위해). H3에서만 비교. |
| 국면 판단에 쓰는 지수 | SPY(국내는 `069500`). |
| 기록 | 수익률, MDD, 보유(주식) 비율, 대기 자산 비율, 매매 수, 보류 수, 비용 합계, SPY·20종목 B&H 대비. |

**비교 대상 (모든 후보에 공통으로 같은 표에 찍는다)**

| 이름 | 내용 |
|---|---|
| **A0 지금 방식** | 세 트레이너, 쉬는 돈 = 현금 |
| **A1 쉬는 돈을 지수에** | 세 트레이너, 쉬는 돈 = SPY (= 후보 H1) |
| **A2 지수 70% + 트레이너 30%** | 처음에 SPY 70%를 사서 끝까지 보유(리밸런싱 없음) + 나머지 30%를 60/30/10으로 세 트레이너가 A0 방식으로 운용 |
| 참고 | SPY 100% B&H, 20종목 동일비중 B&H, SPY 10개월선 단순 추세추종(G11) |

### H1. 쉬는 돈 지수화 (A1)

- **정확한 규칙**: 각 트레이너 지갑에서 주식에 안 들어간 돈은 전부 SPY로 보유한다. 봉 t에 매수 신호가 나오면 t+1 시가에 필요 금액(주식 수 × 시가 × (1+비용))만큼 SPY를 팔고 같은 시가에 종목을 산다. 매도 신호면 t+1 시가에 종목을 팔고 그 대금으로 같은 시가에 SPY를 산다. 첫날 시가에 지갑 현금 전부 SPY 매수. SPY 수량은 소수 허용(정수 주 문제로 대기 자금이 남지 않게. 남는 금액이 $1 미만이 되도록).
- **성공 기준(모두 충족해야 채택)**:
  1. 전체 2015-26 수익률: A1 > A0 **그리고** A1 ≥ A2.
  2. 상승 국면 3개(2015-17, 2020, 2023-26) 중 **2개 이상**에서 A1 > A0.
  3. 전체 MDD: A1의 MDD가 SPY B&H MDD보다 5%p 넘게 나쁘지 않다.
  4. **트레이너 기여 보고(판정에는 안 씀)**: 같은 A1 구조에서 트레이너 매매를 같은 횟수·보유기간의 무작위 시점으로 바꾼 1,000번과 비교한 백분위. 50% 근처면 "구조가 시장을 따라간 것이지 트레이너가 보탠 것은 아님"이라고 쓴다.
- **"시장에 안 짐" 판정(별도 보고)**: 전체 기간 A1 수익률 ≥ SPY B&H 수익률(같은 비용·같은 배당 미포함 기준).
- **실패 시 판단**: 1번이 실패하면(쉬는 돈을 지수에 둬도 A0보다 못하거나 A2보다 못함) → 문제는 cash drag가 아니라 **트레이너 매매 자체가 지수보다 못한 것**이다. 그러면 세 트레이너 규칙을 바꾸지 않는 한 구조 유지로는 시장을 못 따라간다고 사용자에게 그대로 보고한다. 2번만 실패하면 효과가 한 국면에 몰린 것 → 채택 보류.

### H2. 쉬는 돈 지수화 + 대기 자금 추세 필터 (A1-T)

- **정확한 규칙**: H1과 같되, 대기 자산을 매달 마지막 거래일 종가로 정한다. SPY 월말 종가 > 직전 10개 월말 종가(그 달 포함)의 평균이면 다음 달 대기 자산 = SPY, 아니면 = 현금(이자 `^IRX`). 전환은 다음 거래일 시가에 한 번. 트레이너의 종목 매매 규칙은 바꾸지 않는다. 10개월 외의 다른 값은 시험하지 않는다.
- **성공 기준(모두 충족해야 채택, H1보다 우선하려면)**:
  1. 2022 하락 국면 손실: A1-T가 A1보다 5%p 이상 덜 잃는다.
  2. 전체 2015-26 수익률: A1-T ≥ A2 **그리고** A1-T ≥ A1 × 0.9(전체 수익을 10% 넘게 포기하지 않음; 예: A1이 +200%면 A1-T ≥ +180%).
  3. 전체 MDD: A1-T < A1.
- **실패 시 판단**: 1은 되는데 2가 안 되면 "보험료가 너무 비싸다" → H1만 채택 후보로 둔다. 1이 안 되면 필터가 늦어서 쓸모없음 → 폐기. 2020 국면은 휩소 손실이 예상되므로 따로 적는다(판정에는 안 씀).

### H3. 단계적 서킷 브레이커 (G3)

- **정확한 규칙**: 트레이너 지갑 평가액의 고점 대비 낙폭 d를 매 봉 종가로 계산. d ≤ -10%면 그 뒤 신규 매수의 종목상한을 절반으로(30→15%, 20→10%, 15→7.5%). d ≤ -20%면 다음 시가에 보유 종목 전부 정리(대기 자산으로), 20거래일 동안 신규 매수 금지, 그 뒤 고점을 현재 평가액으로 재설정하고 절반 상한으로 재개. 새 고점을 넘으면 원래 상한. 기존 일일 -7% 규칙은 그대로 둔다.
- **비교**: A0·A1 각각에 대해 (가) 서킷 없음 (나) 지금 서킷(누적 -10%·하루 -7%, 영구 정지) (다) H3.
- **성공 기준**: A0·A1 **둘 다에서** (다)의 전체 MDD가 (가)보다 3%p 이상 작고, 전체 수익률이 (나)보다 높다.
- **실패 시 판단**: MDD를 못 줄이면 폐기. 수익이 (나)보다 낮으면 지금 서킷을 유지. 어느 쪽이든 **D6은 원래 저장소 공동작업자와 합의할 사항**이므로 결과는 제안 자료로만 쓴다.

### H4. 느린 성과 기반 재배분 (G6) — 떨어질 것으로 예상하고 시험

- **정확한 규칙**: H1(A1) 구조 위에서. 매달 말 각 트레이너의 월 수익률에서 SPY 월 수익률을 뺀 초과수익 기록을 쌓는다. 분기 첫 거래일에 t = 평균 / 표준편차 × √n(지난 모든 달). n < 20이면 60/30/10 그대로. n ≥ 20이면 몫 ∝ 기본몫 × min(2.0, max(0.25, 1 + 0.25·t)), 합 1로 정규화. 몫이 바뀌면 그날 시가에 트레이너 간 대기 자산(SPY)만 옮긴다(보유 종목은 건드리지 않음, 옮길 대기 자산이 모자라면 가능한 만큼만). ai-hedge-fund 기본값(20, 0.25, 0.25, 2.0)을 그대로 써서 우리가 고르지 않는다.
- **성공 기준**: 전체 2015-26 수익률이 H1보다 높고, **그리고** 2020 이후 국면 3개(2020, 2022, 2023-26) 중 2개 이상에서 H1보다 높다.
- **실패 시 판단(예상)**: 60/30/10 고정을 유지하고, "성과 기반 재배분은 우리 데이터에서 득이 없다"를 기록한다. R0의 음수 순위상관과 같은 방향이면 그 근거를 하나 더 얻은 것이다.

### 7.5 확인 단계 (홀드아웃) — 채택 전에 반드시

1. **한국 시장**: H1~H4 중 미국에서 통과한 것만, `markets.KR_UNIVERSE`(R0에서 안 쓴 시장)에서 같은 규칙으로 2015-01 ~ 2026-11. 대기 자산 = KODEX 200(`069500`), 비용 K-D8, 총 ₩100,000,000(미국 $100,000과 같은 이유). **미국과 방향이 같아야**(예: H1이면 KR에서도 A1 > A0) 채택한다. 국내 거래세는 날짜별 값을 1차 출처로 확인했으면 날짜별로, 아니면 0.20% 고정으로 돌리고 표시한다.
2. **생존편향 확인**: 미국에서 2015-01-02 시점 S&P500 구성종목(`fja05680/sp500`) 중 그때 시총 상위 20으로 H1만 다시 돌린다. 시총 자료를 못 구하면 "이 단계 못 함"이라고 적는다. 가격 없는 종목은 개수를 적고 빼고 돌린다(완전하지 않음).
3. **포워드**: 채택된 것은 코드 반영 전 모의매매(`team.py`)에서 최소 3개월, 매달 A0 방식 그림자 장부와 비교 기록.

### 7.6 시험 횟수 세기 (다중 비교)

이번 사전 등록의 판정은 **H1·H2·H3·H4 4개 × 위에 적은 기준**뿐이다. 국면별 숫자는 모두 보고하지만, 위 기준에 없는 "이 국면에서 이겼다"는 채택 근거로 쓰지 않는다. 결과를 보고 새 변형(예: 10개월 대신 8개월)을 만들면 "탐색"으로 따로 표시하고, 다음 사전 등록(R3)의 후보로만 넘긴다.

---

## 8. 하지 말 것 / 과장된 주장 목록

**하지 말 것**
1. **LLM이 들어간 과거 백테스트를 성과 근거로 쓰기.** 모델이 그 시기를 이미 알고 있을 수 있다(§3). 팀장 LLM 평가는 포워드에서만.
2. **"직전 1등"에게 돈·설정을 몰아주기**(FinRL 앙상블, `tune.py` 1등 채택). R0 순위상관 -0.32.
3. **추세 필터 기간·서킷 숫자를 여러 개 돌려 제일 좋은 것 고르기.** 고르는 순간 그 숫자는 과거에 맞춘 것이 된다. 사전 등록 값 하나만.
4. **2022 한 해(또는 파이오니어 2022 한 칸)를 실력 근거로 쓰기.** 현금이 많아 덜 잃은 것이다(R0).
5. **GPL·AGPL·라이선스 없는 저장소 코드 복사.** 해당: pysystemtrade(GPL-3.0), pypbo(AGPL-3.0), backtesting.py(AGPL-3.0 — `requirements.txt`에 있지만 지금 `.py`에서 import하지 않음), nautilus_trader(LGPL-3.0), GEM·quant_py·AI-Trader·nof0·VAA(표기 없음), TradingAgents-CN·RAMPART(NOASSERTION), mlfinlab(독점), vectorbt(Apache 2.0 + Commons Clause), KIS open-trading-api(표기 없음), pykrx(LICENSE 파일 없음 — 라이브러리 사용만).
6. **레버리지·공매도·코인으로 "만회"하기.** 범위 밖이고, Alpha Arena류 대회의 큰 손익은 대부분 여기서 나온다.
7. **쉬는 돈 지수화를 "공짜 이득"으로 여기기.** 시장 위험을 더 지는 것이다. 하락장에서는 지금보다 더 잃는다(H2가 필요한 이유).
8. **모의투자 체결을 실전 체결로 여기기.** KIS 모의 서버는 주문 경로 검증용이다(kr-broker 설계 K-D3).

**과장된 주장 (조사 중 본 것)**
- "LLM 에이전트가 몇 달 만에 수십 % 수익" — 몇 달짜리 백테스트, 몇 개 종목. TradingAgents README 스스로 "공개 수치와 같을 보장 없음". 미리보기 누수 수정이 2026-10까지 이어졌다.
- "별 12만 개 = 검증됨" — 별은 인기이지 성과 증거가 아니다.
- "AI 헤지펀드" — ai-hedge-fund는 "교육용, 실제 매매 안 함"이라고 스스로 적는다.
- 라이브 LLM 매매 대회 순위 — 기간이 짧고 표본이 작아 운과 구별이 어렵다(§3 문헌).
- "듀얼 모멘텀은 하락장을 피한다" — 월 1회 신호라 급락의 초입은 맞고, V자 반등에서는 늦게 돌아온다(휩소). 성과 수치는 대부분 저자 본인 백테스트다.
- 국내 "○○ 전략 연 30%" 류 — 이번 조사에서 실운용 기록·사전 등록이 있는 국내 오픈소스는 찾지 못했다.

---

## 9. 출처 (모두 2026-11-04 접근)

### GitHub 저장소 (별·push·라이선스는 GitHub 검색 API, 2026-11-04 06:23 UTC)

| 분류 | 저장소 |
|---|---|
| 1 배분 | https://github.com/virattt/ai-hedge-fund · https://github.com/pmorissette/bt · https://github.com/pst-group/pysystemtrade · https://github.com/QuantConnect/Lean · https://github.com/AI4Finance-Foundation/FinRL · https://github.com/dcajasn/Riskfolio-Lib · https://github.com/skfolio/skfolio · https://github.com/MohamedAklamaash/RAMPART · https://github.com/microsoft/qlib |
| 2 현금 | https://github.com/alexjansenhome/GEM · https://github.com/oronimbus/tactical-asset-allocation · https://github.com/penny-vault/defensive-asset-allocation · https://github.com/Kim-Nam-Il/Vigilant-Asset-Allocation · https://github.com/andrewjesaitis/dual-momentum · https://github.com/nutcrackerhf/jrp_equitization |
| 3 LLM | https://github.com/TauricResearch/TradingAgents · https://github.com/AI4Finance-Foundation/FinRobot · https://github.com/pipiku915/FinMem-LLM-StockTrading · https://github.com/The-FinAI/FinCon · https://github.com/waylonli/FINSABER · https://github.com/HKUDS/AI-Trader · https://github.com/wquguru/nof0 · https://github.com/hsliuping/TradingAgents-CN |
| 4 검증 | https://github.com/fja05680/sp500 · https://github.com/hanshof/sp500_constituents · https://github.com/esvhd/pypbo · https://github.com/eslazarev/purged-cross-validation · https://github.com/bettyguo/agent-backtest-lab · https://github.com/hudson-and-thames/mlfinlab |
| 5 한국 | https://github.com/sharebook-kr/pykrx · https://github.com/FinanceData/FinanceDataReader · https://github.com/HongJunhyoung/Snowball · https://github.com/hyunyulhenry/quant_py · https://github.com/quantylab/rltrader · https://github.com/younghwan91/krx-quant-core · https://github.com/koreainvestment/open-trading-api |
| 라이선스 확인만 | https://github.com/polakowo/vectorbt · https://github.com/kernc/backtesting.py · https://github.com/nautechsystems/nautilus_trader · https://github.com/freqtrade/freqtrade |

직접 연 코드 파일: `bt/backtest.py`(`benchmark_random`), `bt/algos.py`(`TargetVol` 등), `bt` `docs/source/tree.md`; `ai-hedge-fund` `hedge_fund/fund/spec.py`(`AllocationPolicy`), `hedge_fund/scorecard/allocation.py`, `hedge_fund/risk/limits.py`, `hedge_fund/fund/example.yaml`, `VISION.md`; Lean `Algorithm.Framework/Portfolio/ConfidenceWeightedPortfolioConstructionModel.py`, `Algorithm.Framework/Risk/MaximumDrawdownPercentPortfolio.py`; FinRL `finrl/agents/stablebaselines3/models.py`; pysystemtrade `docs/backtesting.md`(Optimisation·Capital correction 절); pykrx `pykrx/stock/stock_api.py`(`get_index_portfolio_deposit_file`), `pyproject.toml`.

### 논문·기관 자료

<!-- LIT-SRC -->

### 접근하지 못한 곳 (추측하지 않음)

<!-- LIT-FAIL -->
- `api.github.com/repos/<owner>/<repo>` 직접 조회: 이 세션 범위 밖 저장소라 403. → 같은 값을 검색 API(`search/repositories?q=repo:...`)로 받았다.
- 저장소들의 실운용 성과 기록: 조사한 저장소 어디에도 감사받은 실운용 기록은 없었다(없다는 것을 확인한 것이지, 접근 실패는 아님).
