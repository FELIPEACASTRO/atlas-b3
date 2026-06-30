# 07 — AIForge / Financial_Markets (branch `master`) — varredura v2 para o ATLAS

> Reanálise do diretório `05_VERTICAL_APPLICATIONS/02_Finance_and_Fintech_AI/Financial_Markets`
> (52 arquivos, 19 subáreas) com foco no que **dá ganho real e acionável** ao ATLAS —
> terminal de decisão de opções B3, EOD, núcleo Python puro. Todos os achados abaixo foram
> **lidos na fonte** e os principais **validados em dado real** (sem achismo). Jun/2026.

## Como li
GitHub API (árvore recursiva) → conteúdo bruto dos 7 arquivos de maior alavancagem
(`Brazil_B3_Market_Data_APIs`, `B3_Options_and_Derivatives_Brazil`, `Options_Market_Prediction/{Datasets,Features,Models}`, `Risk_Management_and_Derivatives_Pricing`, `B3_Brazilian_Stock_Market`) →
URLs vivas acessadas (brapi.dev) e biases quantificados com o nosso próprio núcleo de pricing.

---

## 1. Achados que VALIDEI ao vivo (prontos para virar correção)

### 1.1 `q=0` (G4) é um viés material — e a brapi.dev entrega o `q` real de graça
- **brapi.dev** (free, sem token p/ PETR4/VALE3/ITUB4/MGLU3) expõe `dividendsData.cashDividends`
  (167 registros p/ PETR4, campos `paymentDate`+`rate`). Trailing-12m → **q(PETR4) ≈ 7,47%**.
- **Viés validado no nosso core** (call quase-ATM real PETRA398, S=38,63 K=38,52 T=0,044a):
  | q | IV | delta | vega |
  |---|----|-------|------|
  | 0,00 (atual) | 0,2552 | 0,5697 | 3,171 |
  | 0,0747 (real) | **0,2772** | **0,5419** | 3,190 |
  → **+2,2 pontos de IV (~9% rel.)** e **delta −5%**. Afeta o veredito "prêmio caro?" do Analista
  e o delta líquido da Carteira. **Ação:** buscar `q` por ticker na brapi no ingest; fallback q=0.
- **Bônus same source:** `regularMarketPreviousClose` → fecha **S7** (`var_pct` verdadeiro D−1,
  hoje é intraday). `fiftyTwoWeekHigh/Low`, `priceEarnings`, `marketCap` de brinde.

### 1.2 Nosso fix S9 (gate de IV) é exatamente a prática recomendada
- `Datasets_and_Data_Sources_for_Options.md` §9 ("traps that break backtests"):
  *"Stale/wide quotes → nonsensical IV, parity violations → filter by OI/volume/spread; prefer mid; **drop deep OTM**."*
  Confirma o que fizemos (gate extrínseco+banda). Sugestão extra deles: filtrar também por
  **volume/negócios** (temos `negocios` no COTAHIST) e por spread.

### 1.3 HAR-RV e Yang–Zhang: escolhas certas (confirmação)
- `Models_…_for_Options.md` §1: *"HAR-RV (Corsi 2009) … shockingly hard to beat"*; Pollok 2025
  mostra ganhos de ML **marginais** sobre HAR. Reforça o pivô (não perseguir deep model).
- `Features_…Prediction.md` §3 traz a fórmula exata YZ `k=0.34/(1.34+(n+1)/(n−1))` → **conferido: a nossa bate** (`rv.py:77`).
- **Taxa `r` conferida ao vivo:** usamos SGS **1178 (Selic anualizada base 252, %a.a.)** — escolha correta; `fetch_annual_rate()` retorna **0,1415 (14,15% hoje)** de fato (não o fallback 0,1165). Sem bug.

---

## 2. Enhancements de ALTO valor / BAIXO esforço (Python puro, cabem na arquitetura)

| # | Feature | Por que ganha | O que precisa | Esforço |
|---|---------|---------------|---------------|---------|
| A | **IV Rank / IV Percentile (1y)** | "Cheap, robust mean-reversion feature" (#2 do starter set deles). É **o** indicador prático de opções: a IV de hoje está cara/barata vs a própria história? Potencializa o veredito VRP do Analista. | Persistir ATM IV por subjacente/dia (já temos `prices_daily`; criar `iv_daily`). | Baixo |
| B | **Theta** nas gregas | Para uma tese de **venda de prêmio**, theta (decaimento diário que se ganha) é essencial e hoje **não exibimos**. | BS theta (já temos `bs_greeks`); somar na cadeia e na Carteira. | Trivial |
| C | **VRP numérico** (IV²−RV²) | Hoje só rotulamos rico/barato. Mostrar o prêmio de variância em pontos é mais honesto/quantitativo. | Já temos IV ATM e RV; subtrair. | Trivial |
| D | **Skew / smirk** (`OTM put IV − ATM call IV`) | Sinal **publicado** (Xing–Zhang–Zhao, JFQA 2010): smirk íngreme prevê retorno negativo. Temos IV+delta por strike. | Calcular por subjacente. | Baixo |
| E | **Put/Call ratio (volume)** | Sentimento contrário em extremos. Temos `volume`+`kind` por opção no COTAHIST. | Agregar por subjacente. | Baixo |
| F | **Term-structure slope** (IV 3m−1m) | Contango/backwardation = regime de vol. Temos múltiplos vencimentos. | ATM IV por (subjacente,venc). | Baixo |
| G | **Stress/cenários na Carteira** (Taylor Δ-Γ-vega) | "What-if" de P&L sob choque de spot (±5/10%) e vol — risco que um terminal **precisa** ter; usamos as gregas que já temos. | Grade de choques + reavaliação Taylor. | Baixo |
| H | **VaR / Expected Shortfall** da Carteira | `Risk_…Pricing.md`: ES é o padrão Basel/FRTB. Temos histórico (`prices_daily`) p/ VaR histórico/paramétrico no delta-equivalente. | Compor exposição + quantil. | Médio |

---

## 3. Correções de dado/convenção a investigar

- **Exercício americano (G3):** a fonte confirma — B3 lista **americanas e europeias**, e *"a letra do código
  NÃO revela o estilo"*. Logo não dá p/ derivar do ticker; precisa de tabela de referência (PDF B3
  "Formação do Código de Liquidação das Opções") ou heurística (ações ≈ americana, Ibovespa ≈ europeia/cash).
  Pricing: **Bjerksund–Stensland** (fechado, rápido, valida contra nosso CRR já existente) ou LSM.
- **Opções semanais (G5):** existem (toda sexta exceto a 3ª). Nosso guard de código pode dropá-las — **revisar**
  contra o PDF de formação de código da B3.
- **Curva DI (taxa por prazo):** DI1 dá a estrutura a termo; hoje usamos taxa flat. UP2DATA tem curva pronta (pago);
  alternativa: derivar do DI1.
- **Ajuste por proventos (G2):** raw close B3 não é ajustado por dividendos/JCP/splits — usar série ajustada
  (brapi/yfinance `auto_adjust`) ou nosso `corp_actions` no ex-date.

---

## 4. Fontes de dados B3 (mapa, com status)

| Fonte | Dá | Grátis? | Uso no ATLAS |
|-------|-----|---------|--------------|
| **brapi.dev** | quote, **dividendos (q)**, prevClose (D−1), fundamentais | Free tier (4 tickers sem token) | **q p/ G4, var_pct p/ S7** — alto valor já validado |
| **MetaTrader5 (pkg Python)** | OHLCV EOD/intraday + **cadeia de opções** via corretora | Free (precisa MT5/corretora) | upgrade do EOD COTAHIST stale → preços sincronizados |
| **opcoes.net.br** | IV histórica e implícita por ação B3 | Free (web) | **cross-check da nossa IV** (anti-análise-falsa) |
| **OpLab** | IV rank/percentile, séries de vol, simulador | Freemium | referência p/ feature A |
| **S&P/B3 Ibovespa VIX** | índice de vol implícita 30d do Ibovespa (lançado 19/03/2024) | publicado B3/S&P | gauge de **regime** no Radar (hoje `bova11` placeholder) |
| **b3-api-dados-historicos** (cvscarlos, GitHub) | wrapper histórico B3 | Free | simplificar/validar ingest |
| **BCB SGS** | Selic anualizada **1178** (usamos, conferido = 14,15% hoje), meta=432, over=11, CDI=12/4389 | Free | r já ao vivo e correto |
| **B3 UP2DATA** | oficial: superfícies de vol, curvas, corp actions, OI | Pago | "fonte da verdade" se virar produto |

> Nota importante: **não existe superfície IV grau-OptionMetrics grátis p/ B3** — a fonte confirma que
> *"você constrói a IV você mesmo"*. Ou seja, nosso núcleo próprio é o caminho certo; o ganho está em
> melhorar **inputs** (q, taxa, ajuste, estilo) e **cross-check** (opcoes.net.br), não em achar um feed pronto.

---

## 5. Pesquisa de fronteira (registrar; não implementar agora)
- **IV surface arbitrage-free**: SVI/SSVI (Gatheral–Jacquier 1204.0646), Deep Smoothing (1906.05065),
  VAE/GAN/diffusion de superfície (VolGAN, VolaDiff, 2511.07571). Só faz sentido com cadeia densa/intraday.
- **Pricing B3-específico**: Gueiros et al. 2025 (ResNet em opções PETR, 2016–2025, arXiv 2504.20088) — template DL p/ B3.
- **VRP Brasil acadêmico**: Astorino, Chague, Giovannetti, da Silva — índice **IVol-BR** + prêmio de variância
  em mercado fino (SciELO) — referência direta p/ a nossa tese.
- **Deep Hedging** (Buehler 1802.03042) e **Differential ML** (Huge–Savine 2005.02347): ganho é velocidade/hedge, não alpha.
- **Benchmark de features de RV**: Kaggle Optiver Realized Volatility (Felipe tem Kaggle).

---

## 6. Recomendação (ordem de implementação proposta)
1. ✅ **FEITO** — **q real por ticker (G4)** + **var_pct D−1 (S7)** via brapi no ingest (commit 7fb1719). Validado: PETR4 q=21,53% → IV ATM 25,5%→31,6%.
2. ✅ **FEITO** — **Theta (B)** + **IV Rank (A)** na cadeia/screener/Carteira (commit 33fb02f). Validado: 10 calls curtas → net θ/dia +37,8.
3. ✅ **FEITO** — **VRP numérico (C)** + **put/call (E)** + **skew (D)** por subjacente (commit f08f403).
4. ✅ **FEITO** — **Stress Δ-Γ-vega na Carteira (G)** (commit f3c6886).
5. ✅ **FEITO** — **Americana via Bjerksund–Stensland (G3)** validado contra o CRR, ligado no ingest (commit a5e2a62).
6. Restantes: **term-slope (F)**; **cross-check IV vs opcoes.net.br**; **curva DI** (taxa por prazo); **VaR/ES (H)** — adiado até haver histórico de retornos.
