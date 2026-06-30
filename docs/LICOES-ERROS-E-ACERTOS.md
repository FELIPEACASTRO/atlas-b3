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
| S9 | `/chain` exibia **IV de até 463%** (PETRB930: S=38,63 K=3,01) como se fosse real | gate de IV só rejeitava NaN/vega≈0; preço EOD **colado no intrínseco** (deep ITM/stale) reprecifica com vol absurda e vega não-trivial — escapa | gate econômico `iv_is_reliable` (extrínseco ≥ R$0,01 **e** IV ≤ 300%) → IV+gregas = None; fora do pick ATM. Re-ingerido: **−319 opções** (4,8%), max IV 463%→272%, 0 acima de 300%, 0 no intrínseco | reprecificar ≠ ser real: sem **valor extrínseco** a IV é indefinida, não importa que a bisseção ache um número |

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
- **NaN honesto**: o sistema **se recusa a inventar** IV em preço stale/colado no intrínseco (~5% das opções pelo gate econômico, S9) — o produto que não mente.
- **4 módulos sobre dado real**: Radar/Screener, Opções (chain IV+gregas), Analista (briefing 3 perfis, dois lados) e **Carteira** (gregas líquidas consolidadas) — todos servindo COTAHIST EOD real, 0 vazamento de fixture (auditado ao vivo).
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
- [x] **G1** Persistir histórico de closes e computar RV → ligar `iv_vs_rv`. **FEITO** — store `prices_daily` não-destrutivo; sinal IV-vs-RV (ATM IV vs RV) validado em 3 pregões reais (150 ações com sinal). Taxa BCB-SGS ligada.
- [x] **S9** Gate econômico de IV (extrínseco + banda de plausibilidade). **FEITO** — re-ingerido no DB ao vivo. Resíduo disclosed: IVs deep-ITM até ~272% permanecem (extrínseco real, porém ruidoso); o corte 300% é heurística documentada, não modelo. Aprofundar exigiria filtro por banda de delta (decisão de produto).
- [x] **Carteira** (4º módulo): posições ações+opções, gregas líquidas (Δ/Γ/vega) agregadas da tabela real de opções; `/positions` CRUD + `/portfolio`. Validado ao vivo (PETR4 long + put curta → Δ líquido coerente).
- [x] **G4** `dividend yield (q)` real por ticker via **brapi.dev** (`data/brapi.py`), era-correto via asof. **FEITO** — validado: PETR4 q=21,53% (2024) move IV ATM 25,5%→31,6% e delta 0,570→0,500. Resta **G3** (`exercise_style` p/ rotear CRR americano).
- [x] **S7** `var_pct` verdadeiro D−1 a partir do nosso `prices_daily` (sem dep. externa). **FEITO** — `_pct_change(prev_close, last)`; validado PETR4 −1,25(intraday)→−0,85(D−1).
- [x] **theta + IV Rank** (varredura AIForge v2): theta/dia em toda opção e na Carteira (net θ/dia); IV Rank (min-max tastytrade) com `iv_daily` acumulando, honestamente None até ≥20 sessões. Validado: 10 calls ATM curtas → net_theta +37,8 R$/dia.
- [ ] **G3** Obter `exercise_style` por série → rotear CRR p/ americanas (Bjerksund-Stensland valida contra o CRR).
- [ ] **G2** Decidir corp_actions: ligar no ex-date ou remover.
- [ ] **G5/G6** Confirmar convenção de semanais; estender calendário/derivá-lo.
- [ ] Frontend: consumir `/chain`; empty-state; guards de null; contraste WCAG do texto de proveniência; `asof` no card.
- [ ] Ligar BCB-SGS ao vivo no ingest de produção (hoje a função existe, mas o ingest usa default).
