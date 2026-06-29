# 04 — Design System & UI/UX

> Pesquisa de UI/UX de dashboards fintech/trading de elite (2026) → sistema de design concreto e acionável para o ATLAS (Next.js + TS).

## Tendências 2026 (referências: Linear, Vercel, Bloomberg, TradingView, Ramp, Mercury, Raycast)
- **Dark-first**, não dark-as-afterthought (produtos data-heavy desenham o escuro primeiro).
- **Bento grid** — cada tile = 1 dado + tendência, legível em ~4s.
- **"Lead com o número que importa"** — cada módulo tem um hero-number auditável.
- **Densidade alta sem caos** — o usuário avançado *espera* densidade (com modo compacto toggleável).
- **Command center dark** — 1 cor de acento "sua", resto grayscale.
- **Command palette (⌘K)** como navegação central.
- **Glassmorphism funcional** — só em overlays (palette, popovers), nunca sobre dados.
- **Motion como sinal de craft** — funcional (tick-flash, hover 150ms), nunca decorativo.
- **Fontes variáveis + mono para números** (Geist; tabular-nums).

## Navegabilidade (IA tri-modal)
> **Sidebar densa (estrutura) + Topbar contextual (status/ações) + ⌘K (velocidade) + split-view com workspaces salváveis (poder).**

- **Sidebar é a espinha** (não topbar) para apps data-dense; colapsável (rail 48-56px), atalho `[`.
- **Topbar contextual:** status do pregão, relógio B3, latência do feed, ações do módulo.
- **⌘K em 3 classes:** navegação ("PETR4"), comandos ("montar trava de alta"), cálculo inline ("greeks da carteira").
- **Atalhos:** `⌘K`, `/` busca, `G+S` go-to, `[`/`]` sidebar, `J`/`K` linhas, `1-5` módulos, `?` cheatsheet.
- **Split-view redimensionável + workspaces salváveis** — o que separa "dashboard" de "terminal".

## Tokens (dark-first, OKLCH — implementados em `apps/web/app/globals.css`)
```
--bg-base:    oklch(0.16 0.012 265)   /* nunca preto puro */
--bg-surface: oklch(0.19 0.014 265)
--accent:     oklch(0.80 0.16 75)     /* âmbar-elétrico — só marca/foco */
--up:         oklch(0.74 0.17 150)    /* alta — verde dessaturado */
--down:       oklch(0.64 0.20 25)     /* baixa — vermelho dessaturado */
```
**Disciplina de cor (regra dura):**
- 🟡 Âmbar = **só** marca/foco/seleção.
- 🟢🔴 Verde/vermelho = **exclusivo** alta/baixa de preço/P&L (sempre com seta ▲▼, acessível a daltônicos).
- 🔵🟣 **IV/vol = rampa térmica própria** (azul→âmbar→magenta) — assim "IV alta" não se confunde com "preço subindo".
- Elevação por **luminância**, não sombra pesada.

## Tipografia
**Geist Sans** (UI) + **Geist/JetBrains Mono** em todo número (`tabular-nums`, para o último dígito não "dançar" no tick). Base densa 13px.

## Stack de bibliotecas (Next.js + TS)
| Camada | Escolha |
|---|---|
| Componentes | **shadcn/ui** sobre Radix |
| Tabelas | **TanStack Table + Virtual** |
| ⌘K | **cmdk** |
| Candles | **lightweight-charts** (TradingView) |
| Viz custom (payoff, skew, scatter) | **visx** |
| KPIs | **Tremor** |
| Superfície de IV 3D | **echarts-gl** ou react-three-fiber |
| Animação | **Motion** (ex-Framer Motion) — spring p/ drag |
| Estado/streaming | **TanStack Query** + WebSocket |
| Split | **react-resizable-panels** |
| Ícones | **lucide-react** + Tabler |

## 5 toques de "uau" (específicos do produto)
1. **Superfície de IV 3D interativa** (strike × vencimento × IV), rotação/zoom; hover destaca skew + term-structure em 2D.
2. **Payoff que se redesenha ao arrastar** o strike/qtd/vol (Motion spring + visx); breakeven, max-gain/loss e gregas líquidas ao vivo.
3. **Scatter IV × RV com brushing** — selecionar região filtra a tabela (linked views). Fato, não profecia.
4. **Tape animado com tick-flash** (verde/vermelho 80ms), Canvas/virtualizado.
5. **⌘K com ações de mesa** — "montar trava", "alerta IV-rank > 80", "comparar skew jan vs fev".

## Blueprint visual (1 parágrafo)
> Um terminal escuro de grafite frio (OKLCH ~0.16, jamais preto puro), sidebar densa colapsável estilo Linear/Supabase + topbar fina contextual (status do pregão, relógio B3, latência), tudo em **Geist** com cada número em **mono tabular**. Corpo em **bento grid redimensionável**, cada tile com hero-number auditável, conectados por uma única **cor de acento âmbar-elétrico**, enquanto **verde/vermelho dessaturados** ficam só para alta/baixa e a **rampa térmica** colore só a volatilidade. Painéis em **split-view arrastável** (candle + cadeia virtualizada + payoff com spring physics), tudo operável por **⌘K**. Movimento discreto e funcional, glass só em overlays, respeitando `prefers-reduced-motion`. O resultado: um **Bloomberg reimaginado pela equipe da Linear/Vercel** — densidade máxima, calmo, auditável, que comunica **fatos, não profecias**.

## Fontes
[Outcrowd Fintech 2026](https://www.outcrowd.io/blog/fintech-design-trends-2026) · [925studios SaaS dashboards](https://www.925studios.co/blog/saas-dashboard-design-examples-2026) · [Muz.li dark systems](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/) · [UX Patterns — command palette](https://uxpatterns.dev/patterns/advanced/command-palette) · [Geist/Vercel](https://vercel.com/geist/introduction) · [Motion docs](https://motion.dev/docs/react) · [LogRocket — React charts 2026](https://blog.logrocket.com/best-react-chart-libraries-2026/) · [Lollypop — Trading App 2026](https://lollypop.design/blog/2026/june/trading-app-design/)
