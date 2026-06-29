# 01 — Dados e Mecânica da B3

> Dois executores: disponibilidade de dados gratuitos (COTAHIST, curva, proventos, liquidez) e mecânica/precificação (estilo de exercício, dividendos, extração de IV). Tudo verificado contra fontes oficiais B3/ANBIMA.

## 1. Dados gratuitos — o que existe

| Item | Veredito | Detalhe |
|---|---|---|
| **COTAHIST** (séries históricas) | ✅ grátis, inclui opções | Registro de 245 bytes; opções via `TPMERC` 070 (call) / 080 (put); campos `PREEXE` (strike, pos. 189-201) e `DATVEN` (vencimento, 203-210). **Só último negócio (`PREULT`), sem settlement.** |
| **IV / gregas no COTAHIST** | ❌ não tem | Você calcula (Black-Scholes + subjacente + taxa + dias úteis) |
| **Curva DI / pré (taxa livre de risco)** | ✅ grátis | B3 (taxas referenciais) e ANBIMA (ETTJ); **série histórica longa exige scraping** dia a dia (`pyettj`/`rb3`) |
| **Proventos / desdobramentos** | ✅ grátis | Arquivo "Ajuste de proventos" da B3 (ajusta strike de opções) |
| **Opções semanais** | ⚠️ só desde **jan/2024** | ~2,5 anos de histórico → usar **mensais** para profundidade |
| **API grátis com IV pronta** | ❌ não há | brapi e OpLab cobram pelas opções → caminho 100% grátis = COTAHIST + cálculo próprio |

### Liquidez — extremamente concentrada
PETR4 (~35%), BOVA11 (~28%), VALE3 (~12%), depois BBAS3/ITUB4. Dominada por **calls**, em **strikes ATM curtos**. Puts e asas quase não negociam → **superfície de vol cheia de buracos** (relative-value de superfície é inviável só com dado grátis). Universo realista: **3-5 subjacentes**, ATM, vencimentos mensais.

### Os 3 maiores obstáculos (Agente de dados)
1. **Sem preço de settlement no grátis** → `PREULT` stale envenena a IV.
2. **Liquidez concentradíssima e enviesada** → superfície esparsa, puts ilíquidas.
3. **Montagem point-in-time multi-fonte** (COTAHIST + curva + proventos) é trabalhosa e propensa a look-ahead.

## 2. Mecânica e precificação

| Afirmação | Veredito | Nota |
|---|---|---|
| Calls de ação americanas / puts europeias / índice europeu | ✅ (com nuance) | **Estilo é atributo por série** — leia, não assuma. Puts de ação e tudo de índice = europeu; *maioria* das calls de ação = americano |
| Call americana c/ dividendo exige árvore/BAW | ⚠️ parcial | Sem dividendo, call americana = europeia (BS serve). Só calls com **ex-dividendo antes do vencimento** precisam de binomial/BAW |
| **B3 ajusta o STRIKE por proventos em dinheiro** (`FatorPROPSTRIKE`) | ✅ **decisivo** | Atenua o exercício antecipado; **mas usar strike não-ajustado pós-provento explode a IV silenciosamente** |
| Taxa de desconto = curva pré-DI (base 252) | ✅ | Selic flat é aproximação ruim em juros voláteis |
| Vencimento 3ª sexta; liquidação física (ações) | ✅ | Exercício automático ~18:15; cuidado com séries semanais poluindo o calendário e dias úteis 252 |

### Extrair IV de EOD ilíquido — as armadilhas (o ponto mais perigoso)
- **Preço stale/defasado:** o "fechamento" da opção pode ser de horas antes → IV mede dessincronia, não vol.
- **Bid-ask largo / bounce:** usar último negócio em vez do **mid** gera superfície serrilhada (ruído de microestrutura disfarçado de "estrutura").
- **Violação de não-arbitragem:** mid abaixo do intrínseco → IV não existe (~15% das obs com butterfly arbitrage em dados reais).
- **Não-convergência:** deep OTM/ITM com vega minúsculo → solver diverge.

> **Mitigação obrigatória (virou `data/cotahist.py` + a régua do solver):** filtrar antes de inverter (descartar intrínseco-violado, spread largo, volume/negócios zero, stale); usar mid quando houver book; solver com bracketing + clamp de vega que retorna **NaN explícito** em vez de lixo.

### Veredito de viabilidade do motor de IV
> "Moderado em matemática, **alto em data-engineering** — o perigo está no que falha **silenciosamente**." O modelo é trivial; o que mata é: strike não-ajustado, stale price, último-negócio vs mid, taxa errada, mids violando o piso de não-arbitragem.

> **Validação real (commit `6e5a04e`):** sobre um COTAHIST real, 90% das opções líquidas da PETR4 deram IV válida; 10% caíram em NaN (stale/arbitragem) — exatamente o comportamento honesto previsto aqui.

## Fontes
- [Layout COTAHIST — B3 (PDF)](https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf) · [Séries Históricas B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/series-historicas/)
- [B3 — Ajuste de proventos (opções)](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-a-vista/opcoes/ajuste-de-proventos/) · [Caderno de Fórmulas — Opções (PDF)](https://www.b3.com.br/data/files/77/F6/65/3E/F1FB89100A29E189AC094EA8/OPCOES.pdf)
- [B3 — Opções sobre Ações](https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/opcoes-sobre-acoes.htm) · [Opções sobre Ibovespa](https://edu.b3.com.br/w/opcoes-ibovespab3)
- [pyettj (ETTJ B3/ANBIMA)](https://github.com/rafa-rod/pyettj) · [MathWorks — IV via Barone-Adesi-Whaley](https://www.mathworks.com/help/fininst/impvbybaw.html)
- [arXiv 2304.13128 — arbitrage violations em superfícies de vol](https://arxiv.org/pdf/2304.13128) · [Wilson Freitas — datasets de opções](https://www.wilsonfreitas.net/posts/2022-06-24-super-datasets-para-opcoes-de-acoes/super-datasets-para-opcoes-de-acoes)
- Liquidez: [Investidor10 — opções semanais](https://investidor10.com.br/noticias/b3-b3sa3-opcoes-semanais-ganham-dois-novos-tickers-para-aumentar-liquidez-105225/) · [opcoes.net.br](https://opcoes.net.br/opcoes/bovespa)
