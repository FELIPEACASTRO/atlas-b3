# 03 — Ferramentas, Modelos e Técnicas

> Varredura tripla independente (Hugging Face, Kaggle, arXiv). Filtro: o que é **acionável** para previsão de RV/vol, separando o que bate baseline do que é hype.

## A convergência tripla (o achado central)
Kaggle, arXiv e HF chegaram à **mesma conclusão**: o ganho real **não vem do modelo**, vem da **informação** (IV/opções + features exógenas) e da **metodologia** (validação sem leakage). HAR-RV é um adversário brutal; foundation models genéricos em zero-shot são **piores que baseline** em finanças.

## Núcleo (começar por aqui)
- **HAR-RV → HAR-X (com IV)** — o teto a bater *e* o regularizador. `arch` + numpy/statsmodels.
- **Options-driven RV via rough Heston** ([arXiv 2604.02743](https://arxiv.org/html/2604.02743v2), *confirmar ano*) — quase o nosso caso: **−9% MAE, 73,6% acerto direcional vs 68%**, bate o VIX.

## Validação (inegociável)
Purged + Embargoed CV → **CPCV → PBO → Deflated Sharpe** (López de Prado). Treinar com **loss QLIKE**, não MSE.

## Challengers de ML (só entram se baterem HAR no CPCV)
| Modelo | Link | Por quê |
|---|---|---|
| **Kronos** | [NeoQuasar/Kronos-base](https://huggingface.co/NeoQuasar/Kronos-base) (MIT) | Único FM **finance-native** com vol forecasting medido (−9% MAE); ingere OHLCV |
| **TabPFN** | [Prior-Labs/TabPFN-v2-reg](https://huggingface.co/Prior-Labs/TabPFN-v2-reg) | RV como regressão tabular com features HAR+IV; **brilha em dados pequenos** (nosso caso) |
| **FinText** | [huggingface.co/FinText](https://huggingface.co/FinText) | TimesFM/Chronos **re-treinados em finanças, datados por ano** (anti-leakage); 8-20M fine-tunáveis |
| **Toto / Sundial** | [Datadog/Toto-2.0](https://huggingface.co/Datadog/Toto-2.0-313m) · [thuml/sundial](https://huggingface.co/thuml/sundial-base-128m) | FMs **probabilísticos** para a **densidade** de RV (VRP precisa da distribuição) |

## Incerteza, sizing e cauda
- **Conformal prediction adaptativo / change-point** ([2511.13608](https://arxiv.org/abs/2511.13608) · [2509.02844](https://arxiv.org/abs/2509.02844)) → **confidence-scaled hedging** (sizing pela largura do intervalo).
- **Meta-labeling (triple-barrier):** sinal primário "IV > RV prevista"; meta-modelo decide se e quanto.
- **Métrica primária CVaR + max drawdown** (não Sharpe); safety layer de cauda ([Tail-Safe 2510.04555](https://arxiv.org/abs/2510.04555)).

## Feature exclusiva BR
**FinBERT-PT-BR** ([lucas-leme/FinBERT-PT-BR](https://huggingface.co/lucas-leme/FinBERT-PT-BR)) — sentimento financeiro **em português**, como covariável exógena.

## Lições do Kaggle (Optiver Realized Volatility — a mais relevante)
- **RV = sqrt(Σ log-ret² do WAP)** — a definição que usamos.
- **RV passada é a feature dominante** — exatamente o que o HAR captura.
- **Agregação cross-sectional** (estatística de RV/IV entre ativos no mesmo dia) foi o **maior ganho** — adaptável ao nosso caso.
- **Purged/Embargoed Time-Series CV** separou ganhadores de quem explodiu (G-Research, Jane Street).
- **GBDT > NN** no nosso regime (baixa breadth, EOD); NN venceu onde havia breadth gigante.
- **Otimize a métrica econômica, não o RMSE de RV.**

## Datasets — a verdade dura
**Não existe** dataset de RV/opções da B3 no HF nem no Kaggle → temos que construir (COTAHIST). Sandbox limpo para prototipar o método:
- [SPY Options EOD + IV surface 2010-2023 (Kaggle)](https://www.kaggle.com/datasets/dudesurfin/spy-options-eod-volatility-surface-2010-2023)
- [fomc-text-volatility-data (HF)](https://huggingface.co/datasets/yusufizzetmurat/fomc-text-volatility-data)

## O que NÃO usar (anti-hype)
TimesFM/Chronos/Moirai **genéricos zero-shot** (perdem pra baseline); leaderboards de FM têm **leakage documentado** ([2510.13654](https://huggingface.co/papers/2510.13654)); LLMs "forecaster" (FinGPT/FinMA) só servem p/ sentimento; **Moirai tem licença não-comercial** (CC-BY-NC).

## Veredito honesto (arXiv)
> A literatura é majoritariamente otimista demais. O ganho legítimo e replicável está em **enriquecer o HAR com a informação que as opções já te dão** (sua vantagem natural no VRP), medir incerteza com conformal, e ser implacável com Deflated/PBO/CPCV. Foundation models e DL pesado: **monitore, não aposte ainda.**
