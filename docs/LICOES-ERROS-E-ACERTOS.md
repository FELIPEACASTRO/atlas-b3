# ATLAS — Lições: Erros, Acertos e Regras de Ouro

> Registro vivo dos erros que cometemos (e corrigimos), dos acertos que devemos repetir, e das regras para **não repetir os mesmos erros**. Atualize sempre que um bug/decisão ensinar algo. Cada erro: causa-raiz → correção → lição.

---

## Parte 1 — ERROS (bugs silenciosos, gaps, código morto, parametrização)

### 1.1 Bugs SILENCIOSOS (número plausível-porém-errado — os mais perigosos)
| # | Erro | Causa-raiz | Correção (commit) | Lição |
|---|---|---|---|---|
| S1 | Solver de IV devolvia vol falsa (~0,31 / floor 1e-6) quando vega≈0 (deep ITM/OTM) | tolerância **absoluta** em preço + aceitar qualquer não-NaN | gate reprice + vega mínimo → NaN | número que não reprecifica o quote **não é** uma IV |
| S2 | Solver de IV devolvia ~5,0 (500%) perto do bracket inferior | `f_lo*f_mid<0` falha quando `f_lo==0` | bisseção por **sinal** + NaN explícito | comparar sinal, não produto; nunca devolver número fora de raiz |
| S3 | **596 opções (8,8%)** mapeadas ao subjacente ERRADO (PETRA* → PETR4, mas são PETR3) | heurística "4 letras + sufixo" em vez da fonte autoritativa | mapear pelo **ISIN** (CODISI) | não adivinhar mapeamento quando há identificador autoritativo |
| S4 | Time-to-expiry em dias corridos/365 | inconsistente com anualização √252 | calendário B3, **252 dias úteis** | a convenção do mercado é parte da fórmula |
| S5 | Taxa livre de risco flat **11,65% hardcoded** (real: 14,15%) | número mágico chutado | BCB-SGS ao vivo (urllib) | todo parâmetro hardcoded é suspeito — buscar a fonte |
| S6 | CRR clampava `p∈[0,1]`, mascarando erro de até **95%** | "numerical guard" que escondia discretização inválida | `p` fora de [0,1] → NaN | clamp esconde erro; falhe alto |
| S7 | `var_pct` = variação intraday, rotulada "Var %" (usuário lê D−1) | COTAHIST de 1 dia não tem close anterior | (pendente) renomear/persistir D−1 | rótulo tem que casar com a semântica do número |
| S8 | Yang-Zhang mascarava OHLC corrompido (high<low) com `max(var,0)` | sem validação de barra | validar `low≤min(o,c)≤max(o,c)≤high` → NaN | não mascarar variância negativa de dado sujo |

### 1.2 Bugs de disponibilidade / contrato
| # | Erro | Correção (commit) | Lição |
|---|---|---|---|
| D1 | `/screener` dava **HTTP 500** se `ultimo` fosse NULL (papel sem negócio) | campos nuláveis + `_nan_to_none` | uma linha ruim não pode derrubar o endpoint |
| D2 | `ratio=inf` → vira `null` no JSON → **quebra o card** (`toFixed` em null) | `None` + guard no front | `inf`/`nan` não são JSON; nunca para o front |
| D3 | DB corrompido → **500 com stack trace**, sem o fallback prometido | try/except → fixture | fallback prometido tem que existir de fato |
| D4 | `liquidez` NULL fazia o ativo **sumir** do screener (`NULL>=0` é falso em SQL) | `COALESCE(liquidez,0)` | NULL em SQL é traiçoeiro; trate explícito |
| D5 | 1 linha malformada **derrubava o ingest do dia inteiro** | try/except por linha | um byte sujo não pode zerar o dia |
| D6 | `_sizing` aceitava capital negativo → "-3 lotes" | `max(0, ...)` | invariante: nunca sugerir posição negativa |

### 1.3 CÓDIGO MORTO / gaps (capacidade construída mas não ligada)
| # | Item | Status | Lição |
|---|---|---|---|
| G1 | `iv_vs_rv` **sempre None** no fluxo real (RV precisa de série multi-dia; ingest só faz 1 dia) | **gap aberto** — a feature-vedete não funciona com dado real | docstring convincente em código não-executado **mente** |
| G2 | `corp_actions.adjust_strike` — 0 chamadas | dead/gap (COTAHIST pode já trazer strike ajustado) | ou ligue no fluxo ou remova |
| G3 | `crr_price` (americano) — 0 chamadas; ingest precifica americana como europeia | **gap aberto** — falta `exercise_style` por série | ferramenta sem dado de entrada continua um gap |
| G4 | `q=0` (dividend yield) p/ PETR/VALE (dividendo alto) | **gap aberto** — enviesa gregas/IV | parametrização "0 por preguiça" é erro |
| G5 | option_code guard pode dropar **semanais** (convenção da letra difere) | a confirmar | permissividade só protege o que não parseia |
| G6 | calendário com feriados só 2024-2026; fora disso degrada silencioso | a confirmar | sem cobertura → avisar, não inflar T |

---

## Parte 2 — ACERTOS (repetir sempre)
- **Enquadramento honesto**: pivotar de "robô de alpha" (base rate ~3%, 97% dos PF perdem) para **painel de decisão**. Evitou perder dinheiro real perseguindo edge inexistente.
- **Core Python puro** (sem numpy/scipy): dependency-safe no 3.14, auditável, leve. Libs pesadas só como **oráculo de teste**.
- **NaN honesto**: o sistema **se recusa a inventar** IV em preço stale (10-12% das opções) — o produto que não mente.
- **Proveniência + `asof` em todo número**; sem profecia na UI.
- **Revisão imparcial independente**: agente que recomeça do zero pegou bugs que o autor não via (S1, S2, S3).
- **Verificar contra dado real**: confirmamos offsets do COTAHIST e a afirmação do ISIN no arquivo verdadeiro antes de codar.
- **Agentes em paralelo** para pesquisa e auditoria exaustiva (micro+macro), com fonte.
- **TDD vermelho→verde** + commits pequenos e rastreáveis (cada correção tem teste de regressão).

---

## Parte 3 — REGRAS DE OURO (para não repetir)
1. **Em finanças, número silencioso > crash em perigo.** Todo cálculo valida e devolve **NaN explícito** quando não confiável (reprice-check, bounds de não-arbitragem, vega mínimo).
2. **Não adivinhar quando há fonte autoritativa.** Opção→subjacente pelo **ISIN**, não por heurística de ticker.
3. **A convenção é parte da fórmula.** Dias úteis/252 consistente com √252; taxa pré-DI por prazo.
4. **Parâmetro hardcoded é suspeito.** Buscar a fonte oficial (BCB-SGS, B3).
5. **Clamp esconde erro — falhe alto.** `p∉[0,1]`, vega≈0, preço fora do bound → NaN/erro, nunca um número "ajustado".
6. **Teste a borda, não o caminho feliz.** NULL, NaN, deep ITM/OTM, linha malformada, capital negativo, DB corrompido.
7. **Código morto que promete no docstring é pior que ausência.** Ligue no fluxo ou remova; nunca deixe o doc mentir sobre o pipeline.
8. **Rótulo casa com semântica.** "Var %" tem que ser o que o usuário pensa (D−1), ou renomeie.
9. **Fallback prometido tem que existir.** Caminho de erro nunca vira 500/stack trace.
10. **Honestidade é regra de código.** Número sem proveniência/asof = proibido; nada de "compre/venda".

---

## Parte 4 — GAPS ABERTOS (rastrear até fechar)
- [ ] **G1** Persistir histórico de closes e computar RV → ligar `iv_vs_rv` (hoje sempre None).
- [ ] **G3/G4** Obter `exercise_style` e `dividend yield (q)` por série → rotear CRR p/ americanas e `q` real.
- [ ] **S7** Persistir close D−1 → `var_pct` verdadeiro.
- [ ] **G2** Decidir corp_actions: ligar no ex-date ou remover.
- [ ] **G5/G6** Confirmar convenção de semanais; estender calendário/derivá-lo.
- [ ] Frontend: consumir `/chain`; empty-state; guards de null; contraste WCAG do texto de proveniência; `asof` no card.
- [ ] Ligar BCB-SGS ao vivo no ingest de produção (hoje a função existe, mas o ingest usa default).
