# 00 — Veredito e Tese

> Consolidação de 3 executores independentes (SSRN/NBER/RePEc, agregadores de reprodutibilidade, pré-mortem). A convergência por caminhos diferentes é o que dá força ao veredito.

## A pergunta original

"Criar uma solução de ML (com auto-learning) que obtenha predições em **todas as modalidades** do mercado — ações, opções, derivativos — e que diga **o que/quando comprar e vender**."

## O atestado de óbito (da versão "gerar renda")

A tese de *prever o mercado para gerar renda* está estatisticamente reprovada por evidência convergente e revisada por pares:

| Vetor | Evidência | Número que mata |
|---|---|---|
| **Base rate (Brasil)** | Chague & De-Losso (dados B3) | **97% perdem**; "no learning"; 0,5% batem um caixa de banco |
| **Natureza do VRP** | Bollerslev-Todorov; Bondarenko | Não é alpha — é **prêmio por risco de cauda**. Vender vol = vender seguro de catástrofe |
| **Custos** | Barber-Lee-Liu-Odean; Santa-Clara-Saretto | Lucro **bruto**, prejuízo **líquido**. E isso no S&P (mais líquido do mundo) |
| **Replicação** | Harvey-Liu-Zhu; Hou-Xue-Zhang; McLean-Pontiff | t>3 exigido; **85% das anomalias somem**; edges caem **58% pós-publicação** |
| **ML vs HAR** | HARd to Beat (1.445 ações, código aberto) | ML **não bate HAR** com baseline honesto |
| **Leakage** | When Alpha Disappears (2026) | Vazamento sutil infla Sharpe em **+19 a +26 pts** sobre um Sharpe limpo ~0,5 |
| **Reprodutibilidade** | síntese | **~80-90%** de qualquer ganho de ML no nosso backtest seria **artefato** |

**Probabilidade honesta de sucesso (alpha líquido sustentável 2+ anos): ~3%.** E mesmo nos 3%, o EV ajustado a risco e a horas-de-vida provavelmente perde para comprar BOVA11 + CDI.

## Os argumentos de primeiros princípios (não dependem de citação)

1. **Erro de categoria:** não é problema de *predição*, é de *competição*. Seu P&L é o que sobra depois que contrapartes mais rápidas/informadas/capitalizadas tiram a parte delas. Com dado EOD grátis você é o participante menos informado da mesa.
2. **O VRP não é seu para capturar:** o VRP acadêmico é medido com retornos **delta-hedgeados intradiariamente**. Com EOD você não consegue o hedge → roda short-vol direcional, e o resultado dos papers **não se aplica** à sua implementação.
3. **Efeito-seleção:** se a estratégia HAR+IV com dado grátis funcionasse, já estaria arbitrada. Estar "disponível" de graça é evidência de que não sobrevive a custos.
4. **Aritmética de custo:** spread bid-ask de opção B3 (5-20% do prêmio fora do ATM líquido) come um edge de poucos % a.a. em um round-trip.

## O que sobrevive (o steelman)

- O VRP **existe e é real**, inclusive no Brasil (IVol-BR).
- **HAR-RV é a escolha técnica correta** para prever RV.
- **Risco definido** (spreads) é a forma *menos suicida* de jogar.
- O ferramental de rigor (CPCV, PBO, Deflated Sharpe, conformal, pricing) é **capital intelectual genuíno e transferível**.

O problema nunca foi o motor — foi o **veículo** (varejo + B3 rasa + manual + short-vol).

## A decisão: PIVOTAR

De *"sistema que ganha dinheiro prevendo o mercado"* → para **"painel de apoio à decisão honesto"** (e, opcionalmente, um programa de P&D com capital simbólico e gates de morte). Você sai com um skillset raro e **sem perder dinheiro real** — que, dado o base rate, é a verdadeira vitória.

### Gates de morte pré-comprometidos (se um dia for operar)
- **Gate A (custos):** edge bruto sobrevive a custos round-trip *reais* da B3? (este sozinho mata a maioria — e custa R$0 numa planilha)
- **Gate B (estatística):** Deflated Sharpe > 0 e PBO < 0.5 sob CPCV, em PnL líquido, com trial-count honesto
- **Gate C (cauda):** backtest com stress de crash; perda de cauda sobrevivível
- **Gate D (transferência):** SPY só vale como teste de software; zero capital B3 antes de paper-trade na própria B3 por ≥6 meses

> "O sofisticado aqui não é proteção — é anestesia. O antídoto são os gates, e o primeiro deles é uma planilha de custos, não um modelo."

## Fontes
- Chague, De-Losso & Giovannetti, *Day Trading for a Living?* — [SSRN 3423101](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101) · [RePEc](https://ideas.repec.org/p/spa/wpaper/2019wpecon47.html)
- Bollerslev & Todorov, *Tails, Fears and Risk Premia* (JF 2011) — [SSRN 1418488](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1418488)
- Bondarenko, *Why are Put Options So Expensive?* — [SSRN 375784](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784)
- Santa-Clara & Saretto, *Option strategies: Good deals and margin calls* — [SSRN 681643](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=681643)
- Barber, Lee, Liu & Odean, *Do Individual Day Traders Make Money? (Taiwan)* — [PDF](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trade%20040330.pdf)
- Harvey, Liu & Zhu, *…and the Cross-Section of Expected Returns* — [SSRN 2249314](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2249314)
- Hou, Xue & Zhang, *Replicating Anomalies* — [SSRN 2961979](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2961979)
- McLean & Pontiff, *Does Academic Research Destroy Stock Return Predictability?* — [SSRN 2156623](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623)
- Bailey & López de Prado, *The Deflated Sharpe Ratio* — [SSRN 2460551](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- Astorino et al., *Variance Premium in a Low-Liquidity Option Market (IVol-BR)* — [SciELO](https://www.scielo.br/j/rbe/a/RjTbzmbfFtJyNSTWgNYmxNQ/?lang=en)
