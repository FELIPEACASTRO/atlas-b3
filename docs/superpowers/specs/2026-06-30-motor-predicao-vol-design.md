# Motor de Predição de Volatilidade & Distribuição — Design (ATLAS)

> Validado por **6 agentes isentos** (2 rodadas, red-team adversarial). A espinha dorsal
> sobreviveu ao ataque; ganhou camadas de calibração. Este doc é a fonte da verdade.
> Data: 2026-06-30.

**Goal:** dar ao consultor de estratégias do ATLAS uma **distribuição de cenários física e
calibrada** (não a direção do preço) — da qual o POP, o cenário-alvo e o risco caem como
integrais honestas, com incerteza medida.

**Princípio inviolável:** "análise, não recomendação; fatos, não profecia". Toda predição
sai com incerteza explícita e **auditada** (PIT/cobertura). Nunca prevê direção.

**Tech stack:** pure-Python + numpy/scipy (stdlib-first, como o resto do `atlas_api`); libs
leves só onde valem muito (`arch` p/ GARCH; opcional `lightgbm`/`ngboost` como *challengers*).
Dados: **EOD COTAHIST** (fechamento diário; sem intraday/book) + brapi (q/Selic) + B3-Ibovespa-VIX.

---

## 1. Contexto — o que já existe (não reinventar)

`apps/api/atlas_api/pricing/`:
- `har.py` → **HAR-RV (Corsi 2009)** real, OLS, pure-stdlib: `fit_har()` + `forecast_har()`. **É o baseline obrigatório a bater.**
- `rv.py` → `realized_vol()` (close-to-close) + `har_components()` + **`yang_zhang()` (OHLC, já existe — reusar, não reimplementar)**.
- `features.py` → `vrp()`, `put_call_ratio()`, `skew_25d()`.
- `iv.py` → `implied_vol()` + `iv_is_reliable()` (gate de extrínseco).
- `bs.py` / `american.py` → Black-Scholes, Bjerksund-Stensland, gregas.

O motor **pluga** nessas peças; não as substitui.

**Dado real (MEDIDO em 30/jun no `atlas.db`; memória `reference-dataset-atlas`):** ~1 ano (252 pregões). `prices_daily` tem **OHLC completo e limpo** → o Yang-Zhang é alimentável **direto, sem brapi** (corrige a suposição de gap G4/S7), porém **13,5% das barras são colapsadas** (O=H=L=C) e exigem gate de qualidade. Universos: **738 nomes** com ≥252 barras (forecast RV-only) e **~60 nomes** com IV≥252d (VRP/densidade/regime). **Consequência:** 1 ano é o **gargalo de acurácia** — walk-forward de baixa potência → ML-1 para em HAR-Lev + conformal; challenger pesado é improvável de passar (resultado negativo é resultado).

**Dependências:** numpy/scipy entram **só no módulo `predict/`** (optional-dependency isolada `predict`); o **core (pricing/api/deploy) continua pure-stdlib** — não muda o que sobe no túnel.

## 2. A decisão central (com evidência)

**Prever VOLATILIDADE e a DISTRIBUIÇÃO, nunca a DIREÇÃO.** Em EOD, retornos do ativo são ≈
ruído; edge direcional derrete após spread/liquidez da B3. O edge defensável é **vol + VRP**.

Convergência dos 6 agentes (resumo das fontes na §9):
- **HAR é o teto quase-imbatível** em vol diária; "se não bate HAR OOS, é bug ou história, não modelo".
- **MEDIDO na execução (ML-1 Task 4):** o ganho do **leverage só é detectável pelo gate com um proxy de RV LIMPO**. Sob `r²` diário (ruidoso) o edge fica abaixo do limiar (DM-significativo em 3/8 seeds sintéticas); com RV intradiário-agregado (= o que o Yang-Zhang entrega) é robusto (MSE 8/8, QLIKE 7/8). **Por isso o adapter prefere Yang-Zhang — detectabilidade, não só eficiência.** Em EOD puro, é plausível que HAR-Lev não bata HAR em alguns nomes: HAR puro fica de baseline, ensemble como hedge. Resultado negativo é resultado.
- **DL/foundation models são miragem em EOD:** TimesFM-500M dá R² OOS **−2,8%** vs CatBoost; look-ahead bias; ~50k GPU-h só p/ empatar (arXiv 2511.18578). LSTM/TFT/N-BEATS empatam com uma reta (DLinear, Zeng 2022).
- **VRP positivo e significativo na B3** (IVol-BR/SciELO) — paradoxo: a iliquidez que dificulta a execução é a que mantém o prêmio vivo. **Medir no dado B3, nunca importar magnitude dos EUA** (lá virou ~0 desde 2012).
- **O maior risco não é o modelo — é aceitar um ganho que não sobrevive ao gate.** O harness de validação é o produto.

## 3. Arquitetura — 4 camadas

```
EOD (COTAHIST + B3-VIX + COPOM) + chain (IV/strikes)
        │
        ▼
 CAMADA 1 — FORECAST DE VOL  (σ̂ com incerteza)
   HAR (baseline) → HAR-Leverage alimentado por Yang-Zhang
                  → HARX (+B3-VIX +flag COPOM) + THAR/STHAR (regime)
                  → +features PDV (R₁ tendência, Σ vol-trajetória)   [gated]
   combinar por MÉDIA SIMPLES (não pesos "ótimos")
   challenger: NGBoost / quantile-GBM                                 [gated]
        │
        ▼
 CAMADA 2 — DISTRIBUIÇÃO DE CENÁRIOS  (densidade física calibrada)
   base: Student-t (cauda gorda), drift≈0 declarado, σ da Camada 1
   ajuste FÍSICO: encolher IV→RV pelo VRP medido  (σ_fís = RV + (1−λ)·VRP)
   envelope: CONFORMAL (split + adaptativo/DCP) = cobertura GARANTIDA
   recalibração pós-hoc: isotônica (PIT→uniforme)
   SSVI/eSSVI = densidade de MERCADO (risco-neutra) p/ COMPARAR        [gated, nomes líquidos]
        │
        ▼
 SAÍDA → POP, cenário-alvo, intervalos  →  Consultor de Estratégias
        ▲
        │
 CAMADA 3 — O GATE (gateia tudo): walk-forward · Diebold-Mariano · Model
   Confidence Set/Hansen SPA · Deflated Sharpe · CV purgada/embargada ·
   CRPS + log-score + PIT + cobertura · P&L líquido de custos B3
 CAMADA 4 — REGIME→ESTRATÉGIA: IVR + VRP-B3 + estrutura-a-termo + skew
   → viés (vender/comprar vol) · gates de realidade B3 (liquidez/exercício/imposto)
```

### Camada 1 — Forecast de vol
- **Baseline:** `forecast_har` (já existe). Tudo é medido contra ele.
- **HAR-Leverage:** adiciona termo de retorno negativo (semivariância-EOD) — maior ganho honesto sobre HAR puro (Patton-Sheppard).
- **Input Yang-Zhang:** o YZ (≈14× mais eficiente que close-to-close) é a perna de RV do HAR-RV-X. Já temos `realized_vol`; precisamos do estimador YZ a partir de OHLC.
- **HARX + THAR/STHAR:** + B3-Ibovespa-VIX (nível/Δ1d) + flag COPOM; threshold de regime. Único upgrade com ganho OOS *comprovado* (autores BR). **Fase 2.**
- **PDV (Guyon-Lekeufack):** `R₁ = Σ wᵢ·r_{t−i}` (tendência) e `Σ = √(Σ wᵢ·r²_{t−i})` (vol-trajetória), kernel exponencial (Markoviano, O(1)/update). Retornos diários, puro-numpy. **Fase 2, gated** (R₁ sobrepõe parcialmente o leverage — só fica se bater HAR-Lev).
- **Combinação:** média simples (combination puzzle — Clements 2024).
- **Challenger:** NGBoost / LightGBM-quantile (distribuição), só se passar o gate.

### Camada 2 — Distribuição (o coração de "distribuição, não direção")
- **Densidade-base Student-t** (não Gaussiana — opção vive na cauda), ν calibrado pela curtose histórica; drift ≈ 0 declarado.
- **Ajuste físico via VRP:** a IV embute prêmio → encolher a σ-implícita em direção à RV pelo VRP medido (λ calibrado p/ minimizar CRPS OOS). Resultado: o que o ativo *tende* a fazer, não o que o mercado cobra. **Limitação declarada:** EOD ajusta o *nível*, não a forma completa (Recovery Theorem é inalcançável — citar como fronteira, não implementar).
- **Conformal Prediction (split + adaptativo/ACI; variante DCP):** envelopa a densidade → **cobertura marginal garantida**, distribution-free, ~30 linhas numpy. DCP mantém ~90% de cobertura mesmo quando a vol explode (CP-de-ponto cai a ~50%). **A maior alavanca de honestidade.**
- **Recalibração isotônica** (sklearn) pós-hoc → PIT uniforme.
- **SSVI/eSSVI** (Gatheral-Jacquier) = densidade risco-neutra de mercado via Breeden-Litzenberger, **só nos nomes líquidos** (PETR4/VALE3/BOVA11). Não é o POP — é o painel "mercado cobra X, estimamos Y". **Fase 2, gated por liquidez.**

### Camada 3 — O GATE (o verdadeiro produto)
Nada entra em produção sem **bater HAR através deste gate**:
- **Forecast pontual:** walk-forward + QLIKE/RMSE + **Diebold-Mariano** (par-a-par) + **Model Confidence Set / Hansen SPA** (multiple-testing) + **Deflated Sharpe** + **CV purgada/embargada**.
- **Distribuição:** **CRPS** (forma fechada Gaussiana/mistura; numérico Student-t) + **log-score** + **PIT histogram** (teste de uniformidade KS/χ²) + **cobertura** (50/80/95% nominal vs realizado).
- **Econômico:** medir em **P&L de opções líquido** de corretagem/emolumentos/slippage **e imposto (15%/20%; isenção de R$20k NÃO vale p/ opções)** — a régua que importa (arXiv 2506.07928).
- **Point-in-time** em toda feature (OI é EOD/revisado → leakage); **no-arbitrage** antes de qualquer PCA/ML; prever **RV futura/superfície** (nunca o preço — circular).

### Camada 4 — Regime → estratégia (alimenta o consultor)
- IVR + VRP-B3 + estrutura-a-termo (IV90−IV30) + skew 25Δ → **regime** → viés: IVR alto + VRP+ e sem backwardation → vender prêmio; **backwardation → parar venda a descoberto**; IVR baixo → comprar/debit/calendar.
- **Gates de realidade B3:** liquidez hiperconcentrada (multi-perna só nos top ~10) · exercício americano (ação) vs europeu (índice/semanais) · `EM ≈ S·IV·√(T/365)` p/ strike · gestão 45/21/50% (heurística regime-dependente, re-testar nos spreads B3) · imposto no EV · concentração = aposta macro.

## 4. Estrutura de arquivos (novo módulo `atlas_api/predict/`)

```
apps/api/atlas_api/predict/
  __init__.py
  forecast.py     # HAR-Leverage, YZ-RV, ensemble (média simples), forecast σ̂ + incerteza
  distribution.py # Student-t + ajuste VRP (físico) → densidade; integra POP/quantis
  conformal.py    # split + ACI (+ DCP) — cobertura garantida
  calibrate.py    # isotônica pós-hoc + utilidades PIT
  regime.py       # IVR/VRP/term/skew → regime + viés de estrutura
  validate.py     # O GATE: walk-forward, DM, MCS/SPA, deflated, CRPS, PIT, coverage
  # fase 2:
  harx.py         # HARX + THAR/STHAR (regime-switching), features B3-VIX/COPOM
  pdv.py          # features Guyon-Lekeufack (R₁, Σ) — gated
  ssvi.py         # superfície SSVI/eSSVI + Breeden-Litzenberger (nomes líquidos) — gated
apps/api/atlas_api/pricing/rv.py   # +yang_zhang_rv() (OHLC)
```
API: `GET /predict/{ativo}` (σ̂, distribuição, POP de um alvo, intervalos calibrados, regime) — consumido pelo consultor e por um **painel de calibração** no front.

## 5. Encaixe no Consultor (a "distribuição plugável")

O consultor já foi desenhado com um **ponto de injeção de distribuição**. Hoje (v0) seria
lognormal-IV; o motor entrega a **densidade física calibrada** que substitui isso:
- `POP = ∫ densidade_física sobre a região de lucro da estrutura`.
- `cenário-alvo` = a condição (preço/vol) que a estrutura precisa, com a **probabilidade conformal**.
- O painel mostra **mercado (SSVI) vs nossa estimativa (física)** e o **PIT da calibração** ("nossa calibração nos últimos 250 dias") — o que separa um ATLAS profissional de um POP de corretora.

## 6. Faseamento

- **Fase ML-1 (o núcleo honesto + calibração — entrega o maior salto):**
  HAR-Leverage(YZ) + ensemble · Student-t + ajuste VRP (densidade física) · **Conformal (split+ACI)** · PIT/CRPS/cobertura · `validate.py` (gate) · `regime.py` · endpoint + painel de calibração. → POP **calibrado e auditado**.
- **Fase ML-2 (os diferenciais, cada um pelo gate):**
  features PDV · HARX/THAR · SSVI density nos líquidos · NGBoost/quantile challenger · DCP.

## 7. Não-objetivos (com evidência) — não fazer

LSTM/GRU/TFT/N-BEATS/PatchTST · foundation models (TimesFM/Chronos/Moirai/TabPFN-TS) ·
diffusion/VAE/GAN de superfície · rough Heston · Deep Hedging/RL · GEX/dealer-gamma/max-pain ·
HARQ-em-EOD (precisa RQ intraday) · Recovery Theorem completo (mal-posto em EOD) · prever direção.
Todos refutados como miragem/inviáveis sob EOD/B3/pure-Python.

## 8. Testes (TDD)

Cada módulo nasce com testes (pytest, como o resto do `atlas_api`):
- `forecast`: HAR-Lev reproduz HAR quando o termo leverage=0; YZ-RV bate valor conhecido; ensemble = média.
- `distribution`: Student-t integra a 1; ajuste VRP encolhe a σ; POP de um alvo conhecido confere.
- `conformal`: cobertura empírica ≥ nominal numa série sintética; ACI reage a shift.
- `validate`: CRPS forma-fechada bate o numérico; PIT de dados uniformes passa no KS; DM detecta diferença injetada.
- `regime`: backwardation dispara "parar venda".
**Regra de ouro nos testes de integração:** todo modelo novo só "passa" se bater `forecast_har` no walk-forward — é um teste, não uma opinião.

## 9. Evidência (fontes-chave validadas)
- Régua econômica: *Can Anything Beat The Benchmark?* arXiv 2506.07928.
- HAR-Leverage/semivar: Patton-Sheppard 2015; HAR prático: Clements-Preve 2021; combination puzzle: Clements 2024 (10.1002/for.3029).
- Foundation models dominados: arXiv 2511.18578; *HARd to Beat* 2406.08041.
- VRP-B3: IVol-BR/SciELO; VRP-EUA→0: Dew-Becker-Giglio (Chicago Fed WP 2025-17); VRP teoria: Bollerslev-Tauchen-Zhou; Carr-Wu.
- Calibração: Distributional Conformal (PNAS/1909.07889); Adaptive CI 2106.00170; CP-séries 2511.13608 / 2601.18509; CRPS fechada; PIT (scores).
- Densidade: SSVI Gatheral-Jacquier 1204.0646; Breeden-Litzenberger (NY Fed SR677); NGBoost 1910.03225.
- PDV: Guyon-Lekeufack SSRN 4174589 / HAR-PD 2503.00851 / 4FPDV 2406.02319.

## 10. Riscos & questões abertas
- **B3-VIX tem <2 anos** de história → backtests de HARX/regime limitados; tratar como feature, não como série longa de treino.
- **Liquidez de strikes B3** pode inviabilizar SSVI fora dos 3-4 nomes líquidos → SSVI é gated por liquidez.
- **PDV pode não bater HAR-Lev em EOD-B3** (validado em RV 5-min) → só entra pelo gate; risco de sobreposição com o leverage.
- **Custo de re-treino/atualização diária** deve ser O(1) por update (por isso PDV exponencial e modelos lineares) — manter local e barato.
