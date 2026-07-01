"""O gate como teste: HAR-Leverage bate HAR — com um proxy de RV LIMPO.

Achado (medido, scripts de exploração da sessão; ver spec §2 e o plano ML-1 Task 4):
o termo de leverage só é DETECTÁVEL com um proxy de RV limpo. Com `r²` diário
(chi²_1, ruidoso) o edge fica abaixo do limiar do gate (DM-significativo em só 3/8
seeds). Com um proxy intradiário agregado — que é o que o **Yang-Zhang** do adapter
(Task 1) nos dá — o edge é robusto:
  - MSE vs variância verdadeira: DM-significativo em 8/8 seeds (robusto);
  - QLIKE production-faithful (vs RV realizado, como o gate real opera): 7/8 seeds.
Isso é por que o adapter prefere Yang-Zhang: não é só eficiência, é detectabilidade
do sinal. O DGP de leverage (GJR-GARCH, `γ·1{r<0}·r²`) é INDEPENDENTE da forma do
HAR-Lev (feature `r·1{r<0}`) — sem auto-confirmação (review F2).

seed=0 é representativo da maioria (não outlier): prodQLIKE p≈1.9e-6, oracMSE p≈3.5e-3.
"""
import numpy as np

from atlas_api.predict.forecast import har_leverage
from atlas_api.predict.validate import diebold_mariano, qlike


def _gjr_garch_intraday(n, seed, *, M=26, omega=2e-6, alpha=0.03, gamma=0.12, beta=0.90):
    """GJR-GARCH com agregação intradiária → RV limpo (≈ Yang-Zhang).

    Leverage POR CONSTRUÇÃO independente da forma do HAR-Lev. Estacionário:
    α + γ/2 + β = 0.99 < 1. Retorna (retorno diário, variância verdadeira, RV proxy).
    """
    rng = np.random.default_rng(seed)
    var = np.empty(n)
    r = np.empty(n)
    rvar = np.empty(n)
    var[0] = omega / (1 - alpha - gamma / 2 - beta)
    intr = rng.standard_normal(M) * np.sqrt(var[0] / M)
    r[0] = intr.sum()
    rvar[0] = float((intr ** 2).sum())
    for t in range(1, n):
        lev = gamma * (r[t - 1] < 0) * r[t - 1] ** 2
        var[t] = omega + alpha * r[t - 1] ** 2 + lev + beta * var[t - 1]
        intr = rng.standard_normal(M) * np.sqrt(var[t] / M)
        r[t] = intr.sum()
        rvar[t] = float((intr ** 2).sum())
    return r, var, rvar


def test_har_leverage_beats_har_through_the_gate():
    n, min_train = 900, 252
    r, var, rvar = _gjr_garch_intraday(n, seed=0)
    rv = rvar.tolist()
    neg = [x if x < 0 else 0.0 for x in r.tolist()]      # feature de leverage: retorno negativo

    realized_rv, truth, f_har, f_lev = [], [], [], []
    for t in range(min_train, n):                         # walk-forward point-in-time
        base, lev = har_leverage(rv[:t], neg[:t])
        realized_rv.append(rv[t])
        truth.append(var[t])
        f_har.append(base)
        f_lev.append(lev)
    realized_rv = np.array(realized_rv)
    truth = np.array(truth)
    f_har = np.array(f_har)
    f_lev = np.array(f_lev)

    # (A) production-faithful: gate avalia contra o RV REALIZADO (nunca vê a var verdadeira)
    q_har = float(qlike(realized_rv, f_har).mean())
    q_lev = float(qlike(realized_rv, f_lev).mean())
    stat_q, p_q = diebold_mariano(realized_rv, f_lev, f_har, loss="qlike")

    # (B) confirmação-oráculo: MSE contra a variância VERDADEIRA (robusto em toda seed)
    mse_har = float(((truth - f_har) ** 2).mean())
    mse_lev = float(((truth - f_lev) ** 2).mean())
    stat_m, p_m = diebold_mariano(truth, f_lev, f_har, loss="mse")

    # HAR-Lev DEVE bater HAR pelo gate — senão, não entra (decisão do gate, spec §40/§150)
    assert q_lev < q_har and stat_q < 0 and p_q < 0.05      # QLIKE production-faithful, significativo
    assert mse_lev < mse_har and stat_m < 0 and p_m < 0.05  # MSE-oráculo, significativo
