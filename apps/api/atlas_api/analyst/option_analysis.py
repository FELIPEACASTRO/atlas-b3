"""Per-option decision panel — deterministic, didactic, two-sided.

Click an option in the chain and this turns its model numbers (IV, IV Rank, VRP,
greeks, days-to-expiry, moneyness) into plain-Portuguese pros/cons and what to
look at to BUY (titular) vs SELL/EXIT (lançador). It never says "buy" or "sell":
the verdict is labeled analysis, the cons are always non-empty, and every claim
is derived from the data shown (honesty rule — no false analysis).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MULT = 100  # shares per equity option lot on B3


@dataclass
class OptionCtx:
    ticker: str
    underlying: str
    kind: str          # "call" | "put"
    strike: float
    venc: str
    dte: int
    last: float
    spot: float
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None     # per day (negative for a long option)
    iv_rank: float | None = None   # underlying IV Rank 0..100
    rv: float | None = None        # underlying realized vol (for VRP context)


@dataclass
class GreekNote:
    nome: str
    valor: str
    explicacao: str


@dataclass
class OptionAnalysis:
    ticker: str
    underlying: str
    kind: str
    tipo_label: str          # "CALL (compra)" / "PUT (venda)"
    strike: float
    venc: str
    dte: int
    last: float
    spot: float
    moneyness: str           # ITM/ATM/OTM
    moneyness_txt: str
    intrinsic: float
    extrinsic: float
    iv: float | None
    iv_rank: float | None
    vrp: float | None        # iv - rv (vol points)
    breakeven: float
    max_perda_titular: float    # premium x100 (per contract)
    custo_theta_dia: float      # |theta| x100 per contract
    resumo: str
    analogia: str = ""          # day-to-day analogy (insurance / down-payment)
    micro: str = ""             # this specific contract, in plain words
    macro: str = ""             # the market regime around it, in plain words
    pros: list[str] = field(default_factory=list)
    contras: list[str] = field(default_factory=list)
    comprar: str = ""
    vender_sair: str = ""
    gregas: list[GreekNote] = field(default_factory=list)
    veredito: str = ""


def _money(kind: str, spot: float, strike: float) -> tuple[str, str]:
    if abs(spot / strike - 1.0) < 0.02:
        return "ATM", "no dinheiro (strike ≈ preço atual)"
    if kind == "call":
        return ("ITM", "dentro do dinheiro") if spot > strike else ("OTM", "fora do dinheiro")
    return ("ITM", "dentro do dinheiro") if spot < strike else ("OTM", "fora do dinheiro")


def _dte_label(dte: int) -> str:
    if dte <= 7:
        return "pouquíssimo tempo (vence em até 1 semana)"
    if dte <= 21:
        return "curtíssimo prazo"
    if dte <= 45:
        return "curto prazo"
    if dte <= 120:
        return "prazo médio"
    return "prazo longo"


def analyze_option(c: OptionCtx) -> OptionAnalysis:
    side = "alta" if c.kind == "call" else "queda"
    tipo_label = "CALL (opção de compra)" if c.kind == "call" else "PUT (opção de venda)"
    mny, mny_txt = _money(c.kind, c.spot, c.strike)
    intrinsic = max(c.spot - c.strike, 0.0) if c.kind == "call" else max(c.strike - c.spot, 0.0)
    extrinsic = round(c.last - intrinsic, 4)
    breakeven = round(c.strike + c.last, 2) if c.kind == "call" else round(c.strike - c.last, 2)
    max_perda = round(c.last * MULT, 2)
    theta_dia = round(abs(c.theta or 0.0) * MULT, 2)
    vrp = round(c.iv - c.rv, 4) if (c.iv is not None and c.rv is not None) else None

    direcao = "subir acima de" if c.kind == "call" else "cair abaixo de"
    real_hoje, so_tempo = max(intrinsic, 0.0), max(extrinsic, 0.0)
    resumo = (
        f"{c.ticker} é uma {tipo_label} de {c.underlying}, com 'gatilho' (strike) em R$ {c.strike:.2f}, "
        f"{mny_txt}, e vence em {c.dte} dias ({_dte_label(c.dte)}). Quem COMPRA aposta na {side} de {c.underlying}. "
        f"Custa R$ {c.last:.2f} por unidade (R$ {max_perda:.0f} no lote de 100). Desse preço, "
        f"R$ {real_hoje:.2f} é 'valor que já vale hoje' e R$ {so_tempo:.2f} é só expectativa/tempo — "
        f"essa parte vai evaporando aos poucos até o vencimento."
    )

    # day-to-day analogy
    if c.kind == "call":
        analogia = (
            f"Pense como um SINAL para travar um preço: você paga R$ {c.last:.2f} agora pelo DIREITO "
            f"(sem obrigação) de comprar {c.underlying} a R$ {c.strike:.2f} até {c.venc}. Se {c.underlying} "
            f"disparar, você 'compra barato' e lucra a diferença; se não subir, perde só o sinal de R$ {c.last:.2f}. "
            f"É como reservar hoje, por uma taxa, o preço de algo que você acha que vai encarecer."
        )
    else:
        analogia = (
            f"Pense como um SEGURO: você paga R$ {c.last:.2f} de prêmio e, se {c.underlying} cair abaixo de "
            f"R$ {c.strike:.2f} até {c.venc}, você é 'indenizado' pela queda (lucra). Se não cair, perde só o "
            f"prêmio de R$ {c.last:.2f} — como o seguro do carro que, felizmente, você não precisou acionar."
        )

    micro = (
        f"No detalhe DESTE contrato: {c.underlying} vale R$ {c.spot:.2f} agora e o gatilho é R$ {c.strike:.2f}. "
        f"Para a opção valer a pena no fim, {c.underlying} precisa {direcao} R$ {breakeven:.2f} — o 'ponto de empate', "
        f"onde você não ganha nem perde. Quem compra arrisca no máximo R$ {max_perda:.0f} (o que pagou) e "
        f"perde cerca de R$ {theta_dia:.0f} por dia só com a passagem do tempo. Faltam {c.dte} dias."
    )

    if c.iv_rank is None:
        macro = (f"Sobre o mercado: ainda não há histórico suficiente de {c.underlying} para dizer se as opções "
                 "estão caras ou baratas em relação ao próprio passado.")
    else:
        if c.iv_rank < 30:
            nivel, opcoes = "baixo (perto da mínima do último ano)", "BARATAS"
        elif c.iv_rank > 70:
            nivel, opcoes = "alto (perto da máxima do último ano)", "CARAS"
        else:
            nivel, opcoes = "na média do último ano", "com preço normal"
        vrp_txt = ""
        if vrp is not None and vrp > 0.03:
            vrp_txt = (f" O mercado vem 'cobrando' mais nervosismo do que {c.underlying} de fato entregou — "
                       "isso costuma ajudar quem VENDE opção e atrapalhar quem compra.")
        elif vrp is not None and vrp < -0.03:
            vrp_txt = (f" E o mercado vem cobrando MENOS nervosismo do que {c.underlying} entregou — "
                       "o prêmio parece barato para quem compra.")
        macro = (
            f"Sobre o mercado: o 'preço do medo' (a volatilidade) de {c.underlying} está {nivel} — IV Rank "
            f"{c.iv_rank:.0f} de 100. Em palavras simples, as opções deste ativo estão {opcoes} comparadas à "
            f"própria história.{vrp_txt}"
        )

    pros: list[str] = []
    contras: list[str] = []

    # --- volatility level (the price you pay/receive) ---
    if c.iv_rank is not None:
        if c.iv_rank < 30:
            pros.append(f"IV Rank baixo ({c.iv_rank:.0f}/100): a volatilidade está barata vs a própria "
                        "história do ativo — comprar a opção custa um prêmio relativamente menor.")
            contras.append("Vol barata também pode ficar mais barata: se a IV cair mais, o titular perde por vega.")
        elif c.iv_rank > 70:
            contras.append(f"IV Rank alto ({c.iv_rank:.0f}/100): a vol está cara — como titular você paga um "
                           "prêmio gordo e sofre se a IV desinflar (vega contra).")
            pros.append("Vol cara favorece o LANÇADOR (vendedor): você recebe um prêmio inflado.")
        else:
            pros.append(f"IV Rank médio ({c.iv_rank:.0f}/100): vol nem cara nem barata vs a própria história.")
    if vrp is not None:
        if vrp > 0.03:
            contras.append(f"VRP positivo (IV {c.iv:.0%} > RV {c.rv:.0%}): historicamente o ativo entrega MENOS "
                           "vol do que a implícita cobra — estatisticamente favorece vender, não comprar prêmio.")
        elif vrp < -0.03:
            pros.append(f"VRP negativo (IV {c.iv:.0%} < RV {c.rv:.0%}): a implícita está abaixo da realizada — "
                        "o prêmio parece barato em relação ao que o ativo vem movimentando.")

    # --- time / theta ---
    if c.dte <= 21:
        contras.append(f"Vencimento próximo ({c.dte}d): o valor de tempo derrete rápido (theta ~R$ {theta_dia:.0f}/dia "
                       "por contrato). Bom para o lançador, ruim para o titular se o ativo ficar parado.")
        pros.append("Pouco tempo = pouco prêmio em risco e gamma alto: se o movimento vier, a opção reage forte.")
    elif c.dte >= 120:
        pros.append(f"Bastante tempo ({c.dte}d): o decaimento por theta é lento (~R$ {theta_dia:.0f}/dia), "
                    "dando fôlego para a tese se desenvolver.")
        contras.append("Prazo longo custa mais prêmio e prende mais capital até o desfecho.")

    # --- moneyness / delta ---
    if mny == "OTM":
        pros.append("Fora do dinheiro: prêmio baixo e muito alavancado — um acerto direcional rende múltiplos.")
        contras.append("OTM tem baixa probabilidade: precisa de movimento real e a favor, ou vira pó no vencimento.")
    elif mny == "ITM":
        pros.append("Dentro do dinheiro: comporta-se quase como o próprio ativo (delta alto), com menos valor de tempo a perder.")
        contras.append("ITM custa caro (tem intrínseco): menos alavancagem e mais capital exposto.")
    else:
        pros.append("No dinheiro: maior sensibilidade a movimento (gamma/vega altos) — o ponto de máxima 'ação'.")
        contras.append("ATM concentra valor de tempo: é o que mais sofre theta se o ativo ficar de lado.")

    if not contras:
        contras.append("Todo trade tem risco: defina antes o que invalida a tese (preço e tempo).")

    # --- buy / sell-exit narratives ---
    comprar = (
        f"Comprar (virar TITULAR): você paga R$ {c.last:.2f}/unidade (R$ {max_perda:.0f} por contrato), e essa é a "
        f"sua PERDA MÁXIMA — nada além disso. Para lucrar no vencimento, {c.underlying} precisa {direcao} "
        f"R$ {breakeven:.2f} (breakeven = strike {'+' if c.kind=='call' else '−'} prêmio). "
        f"O relógio joga contra você: ~R$ {theta_dia:.0f}/dia de decaimento por contrato enquanto nada acontece. "
        f"Faz mais sentido quando você espera um movimento de {side} FORTE e RÁPIDO"
        + (" e a vol está barata (IV Rank baixo)." if (c.iv_rank is not None and c.iv_rank < 40) else
           ", lembrando que aqui a vol não está barata.")
    )
    ganho_lancador = round(c.last * MULT, 2)
    risco_lancador = ("definido (perda limitada ao strike) " if c.kind == "put"
                      else "potencialmente ALTO/ilimitado a descoberto ")
    vender_sair = (
        f"Vender/Lançar (virar LANÇADOR) ou SAIR de uma posição comprada: como lançador você RECEBE "
        f"R$ {ganho_lancador:.0f} por contrato de prêmio — esse é seu ganho máximo — e assume risco {risco_lancador}"
        f"se {c.underlying} {direcao} {c.strike:.2f}. O theta agora joga A SEU FAVOR (~R$ {theta_dia:.0f}/dia). "
        f"Faz sentido quando a vol está cara (IV Rank alto) e você acredita que {c.underlying} NÃO vai {direcao} o strike. "
        f"Se você JÁ tem a opção comprada e quer sair: venda de volta no mercado para realizar lucro/cortar perda — "
        f"cada dia parado custa ~R$ {theta_dia:.0f}/contrato, então segurar opção comprada 'esperando' tem custo."
    )

    # --- the greeks, in plain words ---
    gregas: list[GreekNote] = []
    if c.delta is not None:
        gregas.append(GreekNote("Acompanha o preço (Delta)", f"{c.delta:+.2f}",
            f"Se {c.underlying} anda R$ 1, a opção anda cerca de R$ {abs(c.delta):.2f}. "
            f"Também serve de estimativa da 'chance de dar certo': por volta de {abs(c.delta)*100:.0f}%."))
    if c.gamma is not None:
        gregas.append(GreekNote("Aceleração (Gamma)", f"{c.gamma:.4f}",
            "O quanto esse acompanhamento ACELERA quando o ativo se move. Fica forte perto do vencimento — "
            "ganhos e perdas podem vir rápido."))
    if c.vega is not None:
        gregas.append(GreekNote("Sensível ao nervosismo (Vega)", f"{c.vega:.3f}",
            f"Se o 'medo' do mercado (a volatilidade) sobe 1 ponto, a opção ganha ~R$ {c.vega:.2f}. "
            "Quem comprou torce para o nervosismo subir; quem vendeu, para cair."))
    if c.theta is not None:
        gregas.append(GreekNote("Custo do tempo (Theta)", f"{c.theta:+.4f}",
            f"A opção perde ~R$ {abs(c.theta):.3f}/dia (R$ {theta_dia:.0f} no lote) só porque o prazo encurta. "
            "É o 'aluguel' que o comprador paga e o vendedor recebe."))

    veredito = (
        "Isto é análise transparente, não recomendação. Em uma frase: "
        + (
            f"comprar esta {c.kind} é apostar numa {side} de {c.underlying} forte e rápida, pagando theta todo dia; "
            f"vendê-la é receber prêmio e lucrar com o tempo/lateralização, assumindo o risco direcional. "
        )
        + (
            "Com a vol cara, o vento estatístico favorece o vendedor. "
            if (c.iv_rank is not None and c.iv_rank > 65)
            else "Com a vol barata, o comprador paga menos pela aposta. "
            if (c.iv_rank is not None and c.iv_rank < 35)
            else ""
        )
        + "A decisão é sua."
    )

    return OptionAnalysis(
        ticker=c.ticker, underlying=c.underlying, kind=c.kind, tipo_label=tipo_label,
        strike=c.strike, venc=c.venc, dte=c.dte, last=c.last, spot=c.spot,
        moneyness=mny, moneyness_txt=mny_txt, intrinsic=round(intrinsic, 2), extrinsic=round(max(extrinsic, 0), 2),
        iv=c.iv, iv_rank=c.iv_rank, vrp=vrp, breakeven=breakeven,
        max_perda_titular=max_perda, custo_theta_dia=theta_dia,
        resumo=resumo, analogia=analogia, micro=micro, macro=macro,
        pros=pros, contras=contras, comprar=comprar, vender_sair=vender_sair,
        gregas=gregas, veredito=veredito,
    )
