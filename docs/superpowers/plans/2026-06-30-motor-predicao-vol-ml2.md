# Motor de Predição de Vol — Fase ML-2 (Challengers) — Plano de Implementação

> **For agentic workers:** REQUIRED: use superpowers:subagent-driven-development ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).
>
> **Pré-requisito:** Fase ML-1 concluída e verde. Spec: `docs/superpowers/specs/2026-06-30-motor-predicao-vol-design.md`.

**Goal:** elevar o motor além do baseline ML-1, **adicionando só o que sobrevive ao gate** — features PDV, HARX/THAR, densidade SSVI nos nomes líquidos, e challengers probabilísticos (NGBoost/quantile) — cada um com prova de bater o ML-1.

**Architecture:** estende `atlas_api/predict/`. **Princípio nº 1: todo modelo é um CHALLENGER.** Ele só é promovido se bater a config ML-1 no **walk-forward + Diebold-Mariano + Model Confidence Set/Hansen SPA + Deflated Sharpe** (forecast) e **CRPS/PIT** (distribuição). O `HAR-Leverage(YZ)` da ML-1 é o **fallback** permanente. *"O risco nº 1 é aceitar um ganho que não sobrevive ao gate."*

**Tech Stack:** numpy/scipy (extra `predict`, herdado do ML-1); `lightgbm`/`ngboost` como **extras separados opt-in** (`predict-ml`), APENAS como challengers atrás do gate. Nada de DL/foundation models (refutados no spec §7). **Lembrete de amostra:** só ~1 ano de dado (memória `reference-dataset-atlas`) → challenger pesado é **improvável de passar**; resultado negativo é resultado válido e registrado.

**Convenções:** testes em `apps/api/tests/predict/`; `./.venv/Scripts/python.exe -m pytest` em `apps/api`; commits em inglês + `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## Mapa de arquivos (ML-2)

| Arquivo | Responsabilidade |
|---|---|
| `predict/validate.py` *(modificar)* | `+ model_confidence_set`, `+ hansen_spa`, `+ deflated_sharpe`, `+ pnl_net_b3` (custos+imposto) |
| `predict/calibrate.py` *(criar)* | recalibração isotônica PAVA pure-Python (PIT→uniforme) — herdada do ML-1 (spec §131) |
| `predict/pdv.py` *(criar)* | features Guyon-Lekeufack `r1_trend`, `sigma_path` (kernel exponencial, Markoviano) |
| `predict/harx.py` *(criar)* | `harx` (HAR + exógenas) + `thar` (regime-switching por threshold) |
| `predict/challenger.py` *(criar)* | `ngboost_forecast` / `quantile_gbm` — distribuição via boosting (opt-in) |
| `predict/ssvi.py` *(criar)* | `fit_ssvi`, `risk_neutral_density` (Breeden-Litzenberger) — nomes líquidos |
| `predict/distribution.py` *(modificar)* | `+ dcp_interval` (distributional conformal p/ vol alta) |
| `predict/select.py` *(criar)* | seleção do melhor modelo gate-aprovado (com fallback HAR-Lev) + "model card" |
| `data/calendar_copom.py` *(criar)* | datas COPOM/eventos (point-in-time) p/ a feature do HARX |
| `pricing/rv.py` ou `data/` *(usar)* | série OHLC + B3-Ibovespa-VIX |
| `apps/web/components/calibration-panel.tsx` *(modificar)* | enriquecer: "mercado (SSVI) vs físico" + model card |

---

## Chunk 1: Fortalecer o gate (pra julgar os challengers com honestidade)

### Task 1: Model Confidence Set + Hansen SPA + Deflated Sharpe

**Files:** Modify `predict/validate.py` · Test `tests/predict/test_validate_mcs.py`

- [ ] **Step 1 — teste que falha:** (a) `model_confidence_set` mantém só os modelos indistinguíveis do melhor (num conjunto onde 1 domina, retorna {melhor}); (b) `hansen_spa` rejeita H0 ("nenhum bate o benchmark") quando há um vencedor claro; (c) `deflated_sharpe` < `sharpe` cru quando há multiple-testing (N trials).
- [ ] **Step 2 — ver falhar.**
- [ ] **Step 3 — implementar:** MCS (Hansen-Lunde-Nason, bootstrap de blocos), SPA (estatística de Hansen 2005), Deflated Sharpe (López de Prado — desconta nº de trials e não-normalidade), `pnl_net_b3(trades)` = P&L **líquido de custos+imposto B3** (corretagem/emolumentos + IR) — a régua econômica do gate (spec §94, herdada do ML-1). **Reaproveita** `pricing.risk.{stress_pnl,payoff_at_expiry,payoff_grid}` + `pricing.american.bjerksund_stensland`/`bs.bs_price` para reprecificar as pernas — não cria pricing do zero. numpy/scipy.
- [ ] **Step 4/5 — passar + commit:** `feat(predict): MCS + Hansen SPA + Deflated Sharpe (multiple-testing gate)`.

---

## Chunk 2: Upgrades lineares (pure-Python, gated)

### Task 2: Features PDV (Guyon-Lekeufack)

**Files:** Create `predict/pdv.py` · Test `tests/predict/test_pdv.py`

- [ ] **Step 1 — teste que falha:** (a) `r1_trend(returns, halflife)` é soma ponderada exponencial (pesos somam ~1; reage a tendência recente); (b) `sigma_path` = √(soma ponderada de r²) ≥ 0; (c) ambos são O(1) por update (estado recursivo) — testar que `update(state, r)` bate o cálculo batch.
- [ ] **Step 2/3 — implementar:** kernels exponenciais (representação 2-exp, Markoviana), recursivos.
- [x] **GATE — REJEITOU (FEITO, commit `29572a1`):** walk-forward HAR-Lev vs HAR-Lev+PDV no dado real, DM sobre QLIKE → **PDV não passa em nenhum nome** (PETR4 p=0.93, VALE3 p=0.77, BBAS3 p=0.98, BOVA11 p=0.34; QLIKE idêntico até a 4ª casa). HAR-RV+leverage já captura tendência/vol-recente; 1 ano deixa o sinal abaixo do gate. **NÃO promovido** — `pdv.py` fica como bloco testado, não ligado no forecast. Resultado negativo é resultado.

### Task 3: HARX (HAR + B3-VIX + flag COPOM)

**Files:** Create `predict/harx.py`, `data/calendar_copom.py` · Test `tests/predict/test_harx.py`

- [ ] **Step 1 — teste que falha:** `harx(rv, exog)` recupera o HAR quando `exog` é nulo; `calendar_copom` é point-in-time (não vaza data futura); a flag "≤N dias do COPOM" liga/desliga corretamente.
- [ ] **Step 2/3 — implementar:** HARX = HAR + colunas exógenas (B3-VIX nível/Δ, flag COPOM); OLS. `calendar_copom` com as datas reais (point-in-time).
- [ ] **Step 4 — GATE:** HARX deve bater HAR-Lev no walk-forward + DM + MCS. **Caveat de dados (pré-requisito):** o S&P/B3 Ibovespa VIX **ainda não está ingerido na base** — é dado novo a buscar (lançado mar/2024, <2 anos). Sem ele, a task não roda; com ele, a janela de teste é curta → relatar IC honesto.
- [ ] **Step 5 — commit:** `feat(predict): HARX with B3-VIX + COPOM (gated)`.

### Task 4: THAR/STHAR (regime-switching)

**Files:** Modify `predict/harx.py` · Test `tests/predict/test_thar.py`

- [ ] **Step 1 — teste que falha:** `thar(rv, threshold_var)` ajusta 2 regimes (alta/baixa vol) e prevê pelo regime corrente; reduz ao HAR quando os 2 regimes coincidem.
- [ ] **Step 2/3 — implementar:** THAR por threshold (variável de transição = nível de vol/RV); OLS por regime.
- [ ] **Step 4 — GATE:** THAR vs HARX/HAR-Lev no walk-forward + DM + MCS. ⚠ ganhos de regime tendem a evaporar sob teste — só promove se sobreviver.
- [ ] **Step 5 — commit:** `feat(predict): THAR regime-switching (gated)`.

---

## Chunk 3: Upgrades de distribuição (gated)

### Task 5: SSVI/eSSVI + densidade risco-neutra (nomes líquidos)

**Files:** Create `predict/ssvi.py` · Test `tests/predict/test_ssvi.py`

- [x] **FEITO (commits `8510cc0`+`29f1d3b`):** `predict/ssvi.py` — SVI raw (Gatheral-Jacquier) + densidade de Gatheral (≡ Breeden-Litzenberger) + checagem butterfly g(k)≥0. **2 achados medidos no dado real, ambos no design:** (1) smile crua de nome individual é ruidosa demais p/ fit arb-free (3/4 com arbitragem/RMSE 5-7pts) → núcleo ATM estreito (0.85-1.15) + peso ATM → PETR4/VALE3/BOVA11 arb-free a ~2pts; **gate de qualidade** (`usable` = arb-free E RMSE≤0.04) recusa o resto (BBAS3); (2) seleção de vencimento prefere os **mensais ricos** (≥20 strikes), não semanais finos. Ligado no engine: a vol SVI vira a vol de mercado (mercado/física/gap consistentes), fallback ao ponto IV; painel mostra "mercado (smile SVI) · N strikes · sem arbitragem · densidade RN". 4 testes, suíte 229 verde, verificado no preview. **eSSVI multi-slice (sem calendar arb) fica p/ depois — 1 slice basta p/ o horizonte único.**

### Task 6: DCP — cobertura conformal em vol alta + recalibração isotônica

**Files:** Modify `predict/distribution.py`/`conformal.py`, Create `predict/calibrate.py` · Test `tests/predict/test_dcp.py`, `tests/predict/test_calibrate.py`

- [ ] **Step 1 — teste que falha (DCP):** numa série com **explosão de vol** no fim, a cobertura do `dcp_interval` ≥ nominal, enquanto o split-conformal de ponto cai (< nominal). É o ponto do DCP.
- [ ] **Step 2/3 — implementar:** Distributional Conformal (conformaliza sobre a CDF prevista).
- [ ] **Step 4 — GATE:** cobertura em regime de vol alta ≥ split-conformal, sem alargar demais os intervalos em regime calmo (trade-off medido).
- [x] **Step 5 — recalibração isotônica (FEITA, commit `8c258be`):** `calibrate.py` com PAVA pure-Python + recalibrador de Kuleshov. **ACHADO medido (rigor):** o split ESTÁTICO **piora** sob não-estacionariedade (derrubou o PIT da VALE3 0.67→0.0001) — rejeitado; a versão **ONLINE (janela rolante)** conserta o caso quebrado (PETR4 PIT 0.006→0.79) e é inócua nos já calibrados → entrou pela porta do gate. Ligada no engine (POP/quantis servidos recalibrados via R/R⁻¹) + painel reporta cru→recal. No dado real: os 3 nomes pit_ok=True, cobertura ~0.80. 6 testes, suíte 225 verde.

### Task 7: Challenger probabilístico (NGBoost / quantile-GBM)

**Files:** Create `predict/challenger.py` · Test `tests/predict/test_challenger.py`

- [ ] **Step 1 — teste que falha:** `quantile_gbm` emite quantis monotônicos (sem cruzamento, com sorting/isotônica); a distribuição preditiva integra ≈ 1.
- [ ] **Step 2/3 — implementar:** LightGBM-quantile (ou NGBoost) sobre features EOD (HAR-RV, YZ-RV, IV, VRP, lags, PDV) com **CV purgada/embargada**.
- [ ] **Step 4 — GATE:** deve bater o ensemble ML-1 em **CRPS** + sobreviver no **MCS**, com **Deflated Sharpe** no P&L. ⚠ teto baixo sem intraday — provável que NÃO passe; documentar honestamente se for o caso (resultado negativo é resultado).
- [ ] **Step 5 — commit:** `feat(predict): probabilistic GBM challenger (gated; may not promote)`.

---

## Chunk 4: Seleção e UI

### Task 8: Seleção do melhor modelo + model card

**Files:** Create `predict/select.py` · Test `tests/predict/test_select.py`

- [ ] **Step 1 — teste que falha:** `select_model(candidates, gate_results)` escolhe o melhor **gate-aprovado**; se nenhum bate, **cai no fallback HAR-Lev**; produz um `model_card` (qual venceu, DM p-valor, pertence ao MCS?, ΔCRPS, janela).
- [ ] **Step 2/3 — implementar** a seleção determinística + o model card auditável.
- [ ] **Step 4/5 — passar + commit:** `feat(predict): gated model selection + auditable model card`.

### Task 9: Enriquecer o painel de calibração

**Files:** Modify `apps/web/components/calibration-panel.tsx`

- [ ] **Step 1 — implementar:** painel mostra **"mercado (SSVI) vs nossa física"**, o **regime** atual, e o **model card** (qual modelo está no ar e por quê passou no gate). Responsivo; estados honestos de erro.
- [ ] **Step 2 — verificar** tsc/eslint/build + preview (mobile/laptop).
- [ ] **Step 3 — commit:** `feat(web): calibration panel — market-vs-physical + model card`.

---

## Critérios de aceite da Fase ML-2
1. `pytest` verde; os testes da ML-1 intactos.
2. **Cada modelo promovido tem um resultado de gate documentado** (DM p-valor, pertence ao MCS, ΔCRPS) — e o que NÃO passou foi descartado com evidência (resultado negativo registrado).
3. `HAR-Leverage(YZ)` permanece como fallback se nenhum challenger passar.
4. SSVI só ativa nos nomes com strikes líquidos; recusa honesta nos demais.
5. UI: "mercado vs físico" + model card; tsc/eslint/build limpos; mobile e laptop.
6. Zero mock/hardcoded onde deveria ser dinâmico.

## Princípio inegociável da ML-2
Nenhuma linha de modelo entra em produção sem **bater o ML-1 através do gate** (walk-forward + DM + MCS/SPA + Deflated Sharpe + CRPS/PIT). O harness é o juiz; a vontade não. Resultado negativo (ex: "PDV não adicionou ganho", "NGBoost não passou") é um **resultado válido e deve ser registrado** — é o que separa ciência de hype.
