# 05 — Revisão de Código: Núcleo Quant

> Auditoria imparcial (agente especialista) do núcleo `pricing/`, contra a spec e boas práticas quant/Python. Validou numericamente cada afirmação. Achou **1 bug crítico** que violava a régua de honestidade.

## O que estava correto (validado por diferenças finitas)
- **BS preço e gregas corretos:** delta∈(0,1), gamma>0, vega>0, put-call parity; theta analítico = `-dV/dT` (por ano) para call e put; vega por 1.00 de vol.
- CDF/PDF via `math.erf` (sem dependência externa) — correto.
- Bounds de não-arbitragem no solver, com forward-discount — corretos para europeu.
- RV: ddof amostral, anualização ×√252 — corretos.
- `signal.classify` honesto (banda simétrica, sem recomendação).

## 🔴 Crítico — corrigido (commit `4348518`)
**Solver de IV retornava ~5.0 (vol falsa de 500%) em vez de NaN** quando o preço fica colado no limite inferior do bracket (opção quase sem valor de tempo — caso comuníssimo no EOD da B3). A lógica `f_lo * f_mid < 0` falhava quando `f_lo == 0.0` (arredondamento), o ramo `else` executava sempre, e o solver retornava `~_HIGH`.

**Por que importa:** viola diretamente a régua da spec (§6: "NaN explícito quando não há raiz"). O terminal exibiria IV=500% para deep OTM/ITM perto do vencimento.

**Correção:** bisseção que ramifica pelo **sinal** dos resíduos (`(f_lo<0) != (f_mid<0)`) em vez do produto; trata `f_lo==0`/`f_hi==0`; critério de parada por largura do bracket.

## 🟡 Importantes — corrigidos
| # | Achado | Correção |
|---|---|---|
| 2 | `bs_greeks` estourava `ZeroDivisionError` em T≤0/σ≤0 | guard → gregas degeneradas |
| 3 | `_d1_d2` quebrava com S/K≤0 (`math.log`) | guard → `nan` |
| 4 | `implied_vol` validava `kind` tarde demais | validação no topo |
| 5 | HAR `rv_d` (stdev de 2 retornos) é proxy frágil | documentado honestamente |
| 6 | `realized_vol(window=0)` pegava a série inteira (bug de slicing) | `if window < 2: raise ValueError` |

## 🟢 Nice-to-have (parcialmente aplicados)
`classify` com NaN → rótulo `indisponivel` (aplicado, em vez de mascarar como "neutro"); TypedDict para gregas, keyword-only args, `_ARB_EPS` nomeado (futuros).

## Resultado
Cobertura subiu de **16 → 28 testes**, cada achado virou um teste de regressão (incl. o teste que pega o ~5.0 falso). Suíte verde.

## Veredito do revisor
> "A álgebra de Black-Scholes está **correta e validada numericamente** — bom trabalho no que é mais fácil de errar. O trade-off bisseção vs Newton/Brent é aceitável para EOD, desde que a bisseção seja implementada corretamente — e **não estava**. O achado #1 é um falso positivo que viola a régua de honestidade e deve ser corrigido antes de qualquer uso."

## Lição de processo
O loop **construir → revisão imparcial → bug crítico → corrigir por TDD → verificar** funcionou exatamente como deveria. A revisão por um agente independente (que recomeça do zero, sem o viés de quem escreveu) pegou um erro que o autor não pegaria sozinho. É a melhor prática que justifica o custo.
