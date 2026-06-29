# 02 — Red-Team Metodológico

> Três frentes: red-team de VRP/estatística, crise de reprodutibilidade do ML em finanças, e um pré-mortem brutal. Postura: tentar **matar** o plano.

## 1. Variance Risk Premium — real, mas não é alpha

- **Existe e é documentado**, inclusive no Brasil (IVol-BR, Astorino et al. 2017; VRP de emergentes incl. Brasil, JBF 2024). Mas o paper brasileiro precisou de **heroísmo metodológico** só para *medir* o prêmio (volume ~US$20M/dia ≈ 1,5% do S&P; ~10 strikes/vencimento).
- **A literatura é explícita sobre a natureza:** o VRP é **compensação por risco de salto/cauda** (Bollerslev-Todorov), não ineficiência. Você é pago para **vender seguro de catástrofe** — ganha 11 meses e devolve tudo no 12º.

## 2. Poder estatístico — overfit garantido

Com **2-4 subjacentes correlacionados** + EOD + alvos de RV **sobrepostos**: ~12 obs não-sobrepostas/ano × 3 ativos × 5 anos ≈ **180 apostas quase-independentes**, e altamente correlacionadas (fator de vol brasileiro comum). A breadth efetiva (Lei Fundamental de Grinold) é dramaticamente menor que o nº de trades.

> O **Deflated Sharpe Ratio** existe para punir isto. Com amostra curta + muitas tentativas, **o DSR tende a zero. "O DSR reprova tudo" não é bug — é o plano funcionando.**

## 3. ML não bate HAR (reprodutível)

- **HARd to Beat** (1.445 ações EUA, código aberto): *"Despite extensive hyperparameter tuning, ML models fail to surpass the linear benchmark set by HAR."* Boa parte do "ML vence" da literatura é **HAR mal-fitado** (janela errada) ou leakage.
- O ganho real **não vem do modelo, vem da informação:** IV/opções (rough Heston → −9% MAE, 73,6% direcional) + features exógenas + **loss QLIKE** em vez de MSE.
- **Foundation models genéricos zero-shot em finanças: R² negativo** (Chronos −1,37%, TimesFM −2,80%) e benchmarks com leakage documentado.

## 4. Custos e backtest — o P&L de papel é fantasia

- Slippage realista ~**75% da largura bid-ask** por perna; muitos "closes" são de strikes que **não negociaram**.
- Barber-Lee-Liu-Odean (Taiwan): day traders pesados tinham **lucro bruto e prejuízo líquido**.
- Santa-Clara-Saretto: o alpha de vender opções some com fricções + **margin calls** que forçam realizar perda no pior momento — *no S&P, o mercado mais líquido do mundo*.

## 5. Reprodutibilidade — leakage é a causa nº 1

- Kapoor & Narayanan (*Patterns* 2023): **648 papers, 30 campos** afetados por leakage → conclusões "wildly overoptimistic".
- *When Alpha Disappears* (2026): leakage de tempo-de-decisão inflou **Sharpe em +19 a +26 pts** sobre um Sharpe limpo de ~0,5.
- López de Prado (*Pseudo-Mathematics…*, AMS 2014): **~7 configurações** já produzem Sharpe>1 espúrio quando o verdadeiro é 0.

> **Veredito de reprodutibilidade:** ~10-20% de chance de um ganho de ML sobre HAR no nosso backtest ser **real**; ~80-90% de ser **artefato**.

## 6. Pré-mortem — kill-list por letalidade

1. 🔴 **VRP é beta de cauda, não alpha.** Sizing por CVaR de regime calmo → você *aumenta* o tamanho antes do crash.
2. 🔴 **Custos/iliquidez B3 comem o edge inteiro.** Resultado modal do varejo.
3. 🟠 **Breadth insuficiente → overfit garantido.** PBO/DSR são *detectores de morte, não curas*.
4. 🟠 **Leakage infla o backtest PARA CIMA** → aloca mais capital no que tem menos edge.
5. 🟠 **Regime shift quebra a exchangeability do conformal** → intervalos confiantes-demais no pior momento.
6. 🟠 **Gap SPY→B3:** sandbox serve para depurar *pipeline*, jamais como evidência de edge transferível.
7. 🟡 Risco operacional (execução manual EOD, fill parcial vira posição direcional).
8. 🟡 Risco comportamental — o gatilho que converte latência em perda realizada.

### Base rate honesto: ~3%
*"Mesmo nos ~3% de 'deu certo', o EV ajustado a risco e a horas-de-vida provavelmente não compensa vs. BOVA11 + Treasuries."*

### Salvaguardas mínimas (viraram a régua do produto)
1. CV purgado/embargoed + baseline HAR com a **mesma janela** do challenger.
2. Deflated Sharpe + trial-count honesto, em **PnL líquido** (não QLIKE).
3. CPCV + PBO + paper-trading real na própria B3 + stress de cauda; benchmark "vender vol cega líquida".

## Fontes
- VRP: [Carr & Wu (RFS 2009)](https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf) · [Bollerslev-Tauchen-Zhou (SSRN 948309)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=948309) · [Bollerslev-Todorov JFE 2015](https://public.econ.duke.edu/~boller/Published_Papers/jfe_15.pdf) · [Astorino et al. (IVol-BR)](https://www.scielo.br/j/rbe/a/RjTbzmbfFtJyNSTWgNYmxNQ/?lang=en)
- ML vs HAR: [HARd to Beat (arXiv 2406.08041)](https://arxiv.org/pdf/2406.08041) · [Can Anything Beat The Benchmark? (2506.07928)](https://arxiv.org/html/2506.07928v1) · [Re(Visiting) TSFMs in Finance (2511.18578)](https://huggingface.co/papers/2511.18578)
- Custos/varejo: [Barber-Lee-Liu-Odean](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trade%20040330.pdf) · [Santa-Clara-Saretto (SSRN 681643)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=681643)
- Reprodutibilidade: [Kapoor-Narayanan (2207.07048)](https://arxiv.org/pdf/2207.07048) · [When Alpha Disappears (2605.23959)](https://arxiv.org/html/2605.23959) · [Pseudo-Mathematics (AMS 2014)](https://www.ams.org/notices/201405/rnoti-p458.pdf)
- Overfitting: [PBO/CSCV](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) · [Deflated Sharpe](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) · [CPCV (skfolio)](https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html)
- Conformal: [Beyond Exchangeability](https://www.stat.berkeley.edu/~ryantibs/papers/nexcp.pdf) · [Covariate Shift](https://www.stat.berkeley.edu/~ryantibs/statlearn-s23/lectures/conformal_ds.pdf)
- Comportamental: [Barber-Odean — Speculator Skill](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf)
