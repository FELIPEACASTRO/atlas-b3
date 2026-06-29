# ATLAS — Terminal B3 (painel integrado de decisão) — Design / Spec

**Data:** 2026-06-29
**Status:** design aprovado (direção), pronto para plano de implementação
**Autor:** Felipe + Claude

---

## 1. Visão e enquadramento honesto

ATLAS é um **painel de apoio à decisão** (decision-support terminal) para o mercado brasileiro (B3), cobrindo **ações, opções e derivativos**. Ele agrega dados, calcula análises transparentes e deixa o usuário **filtrar e decidir mais fácil**.

**O que ATLAS NÃO é (decisão consciente, fundamentada em red-team):** não é um robô que prevê preços nem gera sinais de "compre/venda" com promessa de edge. Um double-check devastador (3 agentes independentes sobre SSRN/NBER/RePEc) estabeleceu que a tese de *gerar renda prevendo o mercado* tem base rate ~3% e EV negativo vs. passivo para o varejo (Chague & De-Losso: 97% dos PF da B3 perdem; VRP é prêmio de risco de cauda, não alpha; custos comem o edge; ML não bate HAR honesto). **O painel é a forma legítima de extrair valor:** organizar informação e análises auditáveis para um humano decidir — sem fingir profecia.

**Régua de honestidade (inegociável):** todo número tem **proveniência + timestamp** visível; análises como IV-vs-RV são **heurísticas rotuladas** ("rico/barato"), nunca recomendações; o carimbo "dados EOD" é sempre visível.

## 2. Usuário e job-to-be-done

- **Usuário:** trader/investidor avançado (o próprio Felipe), capital próprio.
- **Job:** "me mostre o raio-X do mercado e me deixe filtrar rapidamente o produto que importa agora, para eu decidir."

## 3. Escopo e faseamento

- **v1 (núcleo):** Screener universal + Mesa de opções. Shell completo (sidebar + topbar + ⌘K + bento). Dados EOD.
- **v2:** Carteira/risco + alertas + watchlist + **Analista (consultor)** — o módulo de briefing.
- **v3:** Detalhe do ativo rico (candles + indicadores + fundamentos), superfície de IV 3D, workspaces salváveis.

## 4. Módulos

1. **Screener universal** — tabela única (ações + opções + derivativos) com filtros: liquidez/volume, preço/variação, técnico; e para opções: IV, gregas, moneyness, DTE, sinal IV-vs-RV. Ordenável, com visões salváveis.
2. **Mesa de opções** — cadeia por subjacente, smile/superfície de IV, gregas, IV-vs-RV (rico/barato), construtor de estruturas (spreads) com payoff (vencimento + T+0) e gregas líquidas.
3. **Carteira / risco** (v2) — posições, P&L do dia, gregas líquidas consolidadas, alertas.
4. **Detalhe do ativo** (v3) — candles + indicadores (médias, RSI) + fundamentos básicos + opções relacionadas.
5. **Analista (consultor)** (v2) — para cada oportunidade, gera um **briefing estruturado**: setup (fato), caso a favor, caso contra/risco, risco-retorno, **tamanho sugerido nos TRÊS perfis simultâneos** (conservador/moderado/agressivo), o que invalida, nível de confiança e veredito honesto. Diz "o que olhar e os dois lados", e devolve a decisão ao usuário. **Nunca** uma chamada de "compre/venda" com edge fingido — é análise transparente, rotulada, com a perda máxima sempre visível.

## 5. Arquitetura

- **Frontend:** Next.js (App Router) + React + TypeScript. shadcn/Radix, TanStack Table+Virtual+Query, cmdk (⌘K), lightweight-charts (candle), visx (payoff/skew/scatter), Tremor (KPIs), echarts-gl (IV 3D, v3), Motion, react-resizable-panels, next-themes, lucide+tabler.
- **Backend de dados/quant:** FastAPI (Python) servindo JSON. Ingestão e cálculo offline; o front não faz quant.
- **Armazenamento:** DuckDB + Parquet (point-in-time), refresh diário (EOD).
- **Analista (LLM):** um serviço `analyst/` monta o briefing a partir de **regras transparentes + dados** (IV/gregas/RV) e usa um **LLM** (chaves já disponíveis: Claude/GPT/Gemini) só para *redigir* a leitura legível dos dois lados. O LLM não inventa edge nem prevê preço — recebe os fatos/heurísticas e escreve o caso, com confiança e invalidação. Saída validada contra a régua de honestidade (sem "compre/venda").
- **Fronteiras claras:** `data/` (ingestão) → `pricing/` (IV/gregas/RV) → `analyst/` (briefing) → `api/` (FastAPI) → `web/` (Next.js). Cada um testável isoladamente.

## 6. Pipeline de dados (carrega as armadilhas pesquisadas)

- **Fontes gratuitas:** B3 COTAHIST (ações+opções EOD; `TPMERC` 070/080; strike `PREEXE`, venc `DATVEN`; **só último negócio, sem settlement**), curva **pré-DI** (B3/ANBIMA via pyettj/rb3), **ajuste de strike por provento** (`FatorPROPSTRIKE`), brapi free/yfinance.
- **Cálculo próprio:** IV (BS/Black-76; puts de ação e índice = europeu; maioria das calls de ação = americano → binomial/BAW só quando há ex-dividendo antes do vencimento), gregas, RV (HAR-style), IV-vs-RV.
- **Higiene obrigatória (senão a IV mente em silêncio):** usar **strike ajustado** por evento corporativo; **mid das ofertas** quando houver, marcar **stale** por timestamp; filtrar liquidez mínima e violações de não-arbitragem; **curva pré-DI** por vencimento (não Selic flat); solver com bracketing + clamp de vega retornando **NaN explícito** quando não há raiz.
- **Universo v1:** PETR4, VALE3, BOVA11 (+BBAS3/ITUB4); opções **mensais** (semanais só desde jan/2024).
- **Honestidade:** dado é **EOD/atrasado**; intraday é pago (plugável depois sem refazer arquitetura).

## 7. Sistema de design (resumo — ver pesquisa UI/UX completa)

- **Dark-first**, tokens **OKLCH** (grafite frio, nunca preto puro; elevação por luminância), 3 camadas (primitivo→semântico→componente), Tailwind v4 + CSS vars + next-themes.
- **Navegação tri-modal:** sidebar densa colapsável (espinha) + topbar contextual (status do pregão/relógio/latência) + **⌘K** com ações de mesa + split-view com workspaces salváveis; atalhos de teclado.
- **Layout:** bento grid redimensionável; hero-number por módulo; modo compacto toggleável.
- **Disciplina de cor:** âmbar-elétrico = só marca/foco; **verde/vermelho dessaturados = só alta/baixa de preço** (com seta ▲▼); **IV/vol = rampa térmica própria** (azul→âmbar→magenta).
- **Tipografia:** Geist Sans (UI) + Geist/JetBrains Mono em todo número (`tabular-nums`). Base densa 13px.
- **Motion funcional:** tick-flash 80ms, hover 150ms, painel 220ms ease-out, spring no payoff; respeita `prefers-reduced-motion`; glass só em overlays.

## 8. Não-objetivos (YAGNI)

- Sem execução de ordens / conexão com corretora (o usuário executa).
- Sem tempo real na v1 (EOD).
- Sem sinais preditivos de compra/venda; IV-vs-RV é heurística rotulada.
- Sem cobertura de "todos os mercados do mundo" — foco B3.

## 9. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Qualidade do dado B3 (stale, sem settlement) | Filtros de liquidez/stale, mid das ofertas, NaN explícito, badges de proveniência |
| IV silenciosamente errada (strike não-ajustado, taxa errada) | Ajuste por provento, curva pré-DI, validação contra referência |
| Escopo crescer (todos módulos de uma vez) | Faseamento v1/v2/v3 rígido |
| Painel virar "robô de profecia" | Régua de honestidade aplicada na UI (rótulos, sem sinais) |

## 10. Critérios de aceitação da v1

- App Next.js roda localmente com shell (sidebar + topbar + ⌘K + bento), dark-first.
- Screener carrega o universo (PETR4/VALE3/BOVA11 + opções mensais) de dados EOD reais, filtrável por liquidez/IV/gregas/moneyside.
- Mesa de opções mostra cadeia + IV/gregas calculadas + IV-vs-RV rotulado + payoff de uma estrutura de 2 pernas.
- Todo número exibe proveniência/timestamp; carimbo EOD visível.
- IV/gregas validadas contra uma referência conhecida em ao menos 1 série.
