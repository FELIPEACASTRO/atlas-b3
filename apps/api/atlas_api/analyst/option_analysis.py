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

    resumo = (
        f"{c.ticker} é uma {tipo_label} de {c.underlying} com strike R$ {c.strike:.2f}, "
        f"{mny} ({mny_txt}), faltando {c.dte} dias para o vencimento ({_dte_label(c.dte)}). "
        f"O titular aposta na {side} de {c.underlying}; custa R$ {c.last:.2f} por unidade "
        f"(R$ {max_perda:.0f} por contrato de 100). Destes, R$ {max(intrinsic,0):.2f} é valor "
        f"intrínseco e R$ {max(extrinsic,0):.2f} é valor de tempo (que derrete até o vencimento)."
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
    direcao = "subir acima de" if c.kind == "call" else "cair abaixo de"
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

    # --- greeks, explained in context ---
    gregas: list[GreekNote] = []
    if c.delta is not None:
        gregas.append(GreekNote("Delta (Δ)", f"{c.delta:+.2f}",
            f"Para cada R$ 1 que {c.underlying} se move, a opção varia ~R$ {abs(c.delta):.2f}. "
            f"Em módulo, ~{abs(c.delta)*100:.0f}% é uma proxy da 'chance' de terminar no dinheiro."))
    if c.gamma is not None:
        gregas.append(GreekNote("Gamma (Γ)", f"{c.gamma:.4f}",
            "A velocidade com que o delta muda quando o ativo anda. Alto perto do dinheiro e do vencimento — "
            "amplifica ganhos e perdas rapidamente."))
    if c.vega is not None:
        gregas.append(GreekNote("Vega (ν)", f"{c.vega:.3f}",
            f"Para cada +1 ponto de volatilidade implícita, a opção ganha ~R$ {c.vega:.2f}. "
            "Titular ganha se a IV sobe; lançador ganha se a IV cai."))
    if c.theta is not None:
        gregas.append(GreekNote("Theta (Θ/dia)", f"{c.theta:+.4f}",
            f"Só pela passagem do tempo a opção perde ~R$ {abs(c.theta):.3f}/dia por unidade "
            f"(R$ {theta_dia:.0f}/contrato). O relógio é inimigo do titular e amigo do lançador."))

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
        resumo=resumo, pros=pros, contras=contras, comprar=comprar, vender_sair=vender_sair,
        gregas=gregas, veredito=veredito,
    )
