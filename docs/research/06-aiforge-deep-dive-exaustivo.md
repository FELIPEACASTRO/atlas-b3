# 06 — AIForge: Deep-Dive Exaustivo (4 agentes, 48 arquivos, linha por linha)

> Double-check exaustivo do repositório `FELIPEACASTRO/AIForge` (branch `claude/ml-ai-repo-restructure-n1qe8j`, path `…/Financial_Markets`). Quatro agentes leram **integralmente os 48 arquivos** (não grep), verificaram saúde de repos ao vivo (`gh api`, 2026-06-29) e cruzaram tudo contra o motor ATLAS. Nada ficou de fora.

## Como ler
- §1 **Inventário completo de fontes de dados** — o mapa que faz tudo funcionar.
- §2 **Bibliotecas & técnicas** — adotar (pure-Python) / dev-only (oráculo) / descartar.
- §3 **Aplicado ao motor** — os achados que já viraram código (com commit).
- §4 **Fila de maior EV** — o que vem a seguir.
- §5 **Armadilhas** — mortos/pagos/frágeis.

---

## §1 — INVENTÁRIO COMPLETO DE FONTES DE DADOS

### 1.1 B3 / Brasil — gratuitas (núcleo)
| Fonte | Tipo | Custo | Entrega | Lacuna que preenche |
|---|---|---|---|---|
| **COTAHIST** (séries históricas B3) | bulk EOD | grátis | OHLC + opções (já é o nosso parser) | base EOD ✅ usado |
| **opcoes.net.br** | web (scraping) | grátis (EOD) | **cadeia de opções + IV pronta**, IV-rank | cadeia+IV (QA/validação) |
| **Boletim PR / BVBG.086** | XML (zip aninhado) | grátis oficial | **preço de ajuste/settlement** de futuros e opções | settlement (o que COTAHIST não dá) |
| **BCB-SGS** (`python-bcb`/urllib) | API REST | grátis | Selic(1178/11), CDI(12), IPCA(433), meta(432) | taxa livre de risco ✅ aplicado |
| **pyettj** | lib Python | grátis (MIT) | curva ETTJ B3+ANBIMA (PRE/DIC/DCL), histórico | curva DI histórica |
| **Tesouro Transparente CKAN** | CSV | grátis | taxa/PU de todos títulos públicos | curva de juros histórica (proxy) |
| **finbr** | lib Python | grátis (MIT) | COTAHIST+DI1+macro (sucessor do b3cotahist) | validar parser / DI1 |
| **brapi.dev** | API REST | grátis (4 tickers s/ token; 15k req/mês) | quotes, **dividendos/proventos**, fundamentos | proventos (cadeia de opções = Pro) |
| **yfinance** `.SA` | lib Python | grátis (não-oficial) | OHLCV ajustado (`auto_adjust`), `^BVSP` | spot/índice do underlying |
| **MetaTrader5** | lib + terminal | grátis (precisa corretora) | OHLCV **intraday** WIN/WDO/ações | intraday barato |
| **exchange_calendars** / **pandas-market-calendars** | lib Python | grátis | calendário/feriados **B3/BVMF** | dias úteis 252 ✅ (hardcoded) |
| **CVM Dados Abertos** | CSV (`;` Latin-1) | grátis | informe de fundos, DFP/ITR | fundamentos (não opções) |

### 1.2 Datasets de opções/IV (o ouro está aqui)
| Fonte | Custo | Entrega | Mercado | Uso p/ ATLAS |
|---|---|---|---|---|
| **Deribit API** | **grátis** | order book, **IV, gregas, vol** de opções BTC/ETH | cripto | **única API de opções+IV grátis** → validar nosso BS/IV/gregas |
| SPY Options EOD Vol Surface 2010-2023 (Kaggle) | grátis | EOD + IV surface + gregas (parquet) | US | sandbox de prototipagem do método |
| Nifty Options 2024 / NSE F&O (Kaggle) | grátis | cadeias de índice | Índia | estrutura de chain p/ exercitar parser/IV |
| VKOSPI options (Kaggle) | grátis | opções + índice de vol | Coreia | benchmark de IV/vol-index |
| Optiver Realized Volatility (Kaggle) | grátis | order-book → prever RV 10min | global | **calibrar/validar nosso RV/HAR** |
| ORATS / Cboe DataShop / OptionMetrics (IvyDB) | **pago** | superfícies IV históricas, gregas | US/global | referência (amostras free no Cboe) |

### 1.3 Global / multi-mercado (spot, macro, fatores)
| Fonte | Custo | Cobre B3? | Uso |
|---|---|---|---|
| **OpenBB** | grátis | sim (via providers) | fachada única de provedores de dados |
| **EODHD** | trial+barato | sim (`.SA`, opções) | rota de contingência paga p/ opções B3 |
| **Stooq** | grátis | parcial | 2ª fonte EOD p/ cross-check de gaps |
| Tiingo / FMP / Alpha Vantage | freemium | parcial | EOD/news/intraday (rate-limited) |
| **FRED** | grátis | não (US) | yield curves US / macro |
| **JKP Global Factor Data** | grátis | **sim (Brasil)** | 153 fatores, 93 países, até 2025 |
| Kenneth French / AQR | grátis | não | fatores (contexto) |

### 1.4 Dados alternativos (feature factual datada do briefing — PIT-safe)
| Fonte | Custo | Uso (anti-profecia) |
|---|---|---|
| **GDELT 2.0** | grátis | tom/eventos por ticker/setor BR como **fato datado** |
| **Pix (BCB)** | grátis | nowcast de atividade doméstica |
| **Wikimedia Pageviews** | grátis | timestamp de chegada de atenção a um evento |
| **Prediction markets** (Kalshi/Polymarket/Metaculus, read-only) | grátis | `P(Fed corta)`, `P(CPI>x)` como contexto exógeno de vol macro |
| **FinBERT-PT-BR** (lucas-leme) | grátis | sentimento financeiro **PT-BR** no briefing |
| Google Trends (pytrends) | grátis | atenção de varejo — **não-PIT**, só qualitativo |

### 1.5 Intraday / microestrutura (free, fora do core EOD)
| Fonte | Custo | Uso |
|---|---|---|
| Dukascopy / HistData | grátis | tick/M1 **FX** (proxy USD/BRL, WDO) |
| MetaTrader5 | grátis | intraday WIN/WDO (ver §1.1) |
| LOBSTER / Databento / Kaiko | pago (amostras) | LOB tick — **fora do escopo EOD** |

---

## §2 — BIBLIOTECAS & TÉCNICAS (verdicto, saúde verificada)

### 2.1 ADOTAR JÁ (pure-Python, preenche lacuna) — vários já aplicados (§3)
- **Estimadores de RV OHLC** (Parkinson/GK/RS/**Yang-Zhang**) — gap-robusto. ✅ YZ aplicado.
- **HAR-RV por OLS** — não há lib; é regressão. ✅ aplicado.
- **CRR binomial americano** — opção americana B3. ✅ aplicado.
- **Day-count 252 dias úteis** (calendário B3). ✅ aplicado.
- **Pré-flight de não-arbitragem + `iv_fail_reason`** — diagnosticar por que a IV é NaN.
- **Índice de vol model-free 30d** (estilo VIX) por subjacente a partir da cadeia OTM.
- **Max-drawdown trailing, downside-deviation, Amihud** (`|r|/volume$`) — features de risco/iliquidez zero-dep.
- **Split conformal** sobre o HAR → banda de cobertura (incerteza honesta). *Top pick do Agente 4.*
- **Deflated Sharpe + PBO** reimplementados (`math.erf`) — régua sem scipy.

### 2.2 DEV-ONLY (numpy/scipy/C++ — oráculo de teste, nunca no runtime)
- **py_vollib** (Jäckel "let's be rational") — oráculo de IV (revivido 2026).
- **QuantLib** (7.3k★, commit hoje) — golden-file de BS/CRR/curvas.
- **arch** (Sheppard, 1.5k★) — GARCH/HAR de referência (teste de regressão do HAR puro).
- **statsforecast** (Nixtla, 4.8k★) — AutoARIMA/Theta como challenger.
- **skfolio** (BSD-3, 2k★) — **CPCV + WalkForward + CVaR** (a régua de validação).

### 2.3 TÉCNICAS transferíveis (frontier, alinhadas à régua)
- **Conformal Prediction adaptativo (ACI)** — incerteza calibrada sob shift (MAPIE).
- **Regime de vol** (HMM `hmmlearn` / `ruptures` / Wasserstein) — *rotula o estado, não prevê*.
- **Dados sintéticos** (Quant GANs, SigCWGAN, CoFinDiff) — fábrica de caminhos p/ stress de cauda e validação multi-história. Gate: checklist de fatos estilizados + TSTR.
- **Deep Learning Volatility (Horvath), Learning Risk-Neutral IV Dynamics (Buehler)** — núcleo de IV/superfície (research).
- **Playbook de opções de índice da Índia** — IV-surface fitting, greeks-ML, OI, 0DTE/gamma/pin, custos no backtest.

### 2.4 DESCARTAR (peso/morto/HFT/profecia)
Foundation models de série temporal como preditor (Chronos/TimesFM/Moirai — zero-shot = profecia), LLM trading agents (TradingAgents/FinGPT-forecaster — alpha é leakage de pré-treino), RL de trading (FinRL), DeepLOB/microestrutura tick, engines pesados (Nautilus/LEAN/zipline/backtrader-GPL/backtesting.py-AGPL/vectorbt-CommonsClause), `mlfinlab` (fechou/pago), `fracdiff`/`finta`/`investpy` (mortos), TA-Lib (build C). **Use as fórmulas, não os pacotes mortos.**

---

## §3 — APLICADO AO MOTOR (achados → código, com commit)
| Achado | Commit |
|---|---|
| Guard de código de opções B3 (5ª letra ↔ TPMERC ↔ vencimento) | `feat(data): option-code convention guard` |
| HAR-RV real (OLS pure-Python) | `feat(pricing): real HAR-RV (OLS)` |
| Pricer americano CRR | `feat(pricing): American CRR pricer` |
| Parsing de OHLC (high/low) | `chore(data): parse OHLC` |
| **Yang-Zhang RV** (gap-robust) | `feat(data,pricing): Yang-Zhang RV` |
| **Taxa BCB-SGS real** (Selic 14,15% vs flat 11,65%) | `feat(data): BCB-SGS rate` |
| **Day-count 252 dias úteis** (calendário B3) | `fix(pricing): T em dias úteis/252` |

## §4 — FILA DE MAIOR EV (pure-Python, próxima leva)
1. **Split conformal** sobre o HAR → banda de incerteza no briefing.
2. **Pré-flight de não-arbitragem + `iv_fail_reason`** no store.
3. **Índice de vol model-free 30d** por subjacente (IV-vs-RV no nível do ativo).
4. **Amihud + max-drawdown + downside-dev** no briefing.
5. **Deflated Sharpe + PBO** pure-Python (régua sem scipy).
6. **Adapters de dado:** validação BS/IV contra **Deribit** (grátis); ingestor de QA do **opcoes.net.br**; settlement via **BVBG.086**; curva DI via **pyettj**.

## §5 — ARMADILHAS (marcadas)
- **Pagos/B2B:** B3 UP2DATA (resolve tudo, mas contratado), ORATS, OptionMetrics, B3 for Developers, OpLab (R$154+/mês), brapi Pro.
- **Mortos/frágeis:** `investpy`/`investiny`, `mlfinlab` (fechou), `fracdiff`/`finta` (archived), Papers with Code (sunset → HF Papers), Deutsche Börse PDS (deprecado), MOEX (sancionado), Tesouro live JSON (Cloudflare 403).
- **Free com ressalva:** yfinance/Stooq/scrapers = gaps silenciosos, rate-limit, ToS; SGS ~10 anos/request; CVM 12 meses Latin-1; datasets de opções Kaggle são **não-B3** (transferíveis em estrutura, não substituem dado B3).
- **Régua de viés (incorporar ao guard):** survivorship+look-ahead ~3.8% em 4 trimestres (Baquero et al. 2005); "sintético ≠ PIT por padrão".

## §6 — Pipeline de monitoramento de pesquisa
arXiv RSS `q-fin.PR+q-fin.ST` · SSRN-FEN (*Derivatives*) · OpenAlex (`country_code:BR`) · HF Papers · Quantocracy. Brasil: BCB-TD, RBFin/SBFin, SciELO Preprints, IDEAS JEL G13.
