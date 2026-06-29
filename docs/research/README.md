# ATLAS — Corpus de Pesquisa

> Base de conhecimento versionada da investigação que fundamentou o ATLAS (terminal B3).
> Gerada por uma constelação de agentes especialistas em paralelo (jun/2026), cada achado com fonte.

Esta pasta preserva, em forma destilada e auditável, **tudo** que sustentou as decisões do projeto — desde o veredito brutal que matou a ideia original até o levantamento de ferramentas e o sistema de design. Os relatórios brutos viveram no chat; aqui ficam as conclusões, com as fontes.

## Ordem de leitura

| # | Documento | O que responde |
|---|-----------|----------------|
| 00 | [Veredito e tese](00-veredito-e-tese.md) | Por que a ideia original foi reprovada e por que o painel é a forma legítima |
| 01 | [Dados e mecânica da B3](01-dados-e-mecanica-b3.md) | O que dá (e o que não dá) para fazer com dado grátis de opções B3 |
| 02 | [Red-team metodológico](02-red-team-metodologico.md) | Base rate, VRP, custos, leakage, replicação — a evidência que mata |
| 03 | [Ferramentas, modelos e técnicas](03-ferramentas-modelos-tecnicas.md) | Varredura HF + Kaggle + arXiv — o acionável vs. o hype |
| 04 | [Design system & UI/UX](04-design-system-uiux.md) | Tendências 2026, navegação, tokens, stack, toques de "uau" |
| 05 | [Revisão de código — núcleo quant](05-revisao-codigo-quant.md) | A auditoria imparcial que achou o bug crítico de IV |

## A tese em uma frase

> O variance risk premium **existe** (até no Brasil), mas **existência ≠ capturabilidade líquida** para o varejo. Como *fonte de renda*, a estrutura (poucos ativos, EOD, short-vol, custos) condena: base rate ~3%, EV negativo vs. passivo. Como *ferramenta de decisão honesta + capital intelectual*, é excelente. Por isso o ATLAS é um **painel que mostra fatos, não um oráculo que finge prever**.

## Como esta pesquisa virou produto

- O **veredito (00)** definiu o pivô: decision-support, não alpha-bot.
- **Dados/mecânica (01)** viraram o `data/cotahist.py` e a régua de higiene de IV.
- O **red-team (02)** virou a régua de honestidade e os gates de validação.
- As **ferramentas (03)** definiram o stack (HAR-first, ML como challenger).
- O **design (04)** virou o `apps/web` (tokens OKLCH, shell).
- A **revisão (05)** corrigiu o solver de IV antes de qualquer uso.

Ver também: [`../specs`](../specs), [`../plans`](../plans), [`../architecture`](../architecture).
