# Motor de Predição de Vol — Fase ML-1 — Plano de Implementação

> **For agentic workers:** REQUIRED: use superpowers:subagent-driven-development (se houver subagents) ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).
>
> Spec (fonte da verdade): `docs/superpowers/specs/2026-06-30-motor-predicao-vol-design.md`

**Goal:** entregar um **POP/cenário calibrado e auditado** para o consultor — densidade física da vol (não direção), com cobertura conformal garantida e gate de validação contra o HAR.

**Architecture:** novo módulo `apps/api/atlas_api/predict/` (pure-Python + numpy/scipy) que pluga no `pricing/` existente (HAR, RV, VRP, IV). Forecast de vol (HAR-Leverage alimentado por Yang-Zhang, ensemble por média simples) → densidade Student-t ajustada ao físico via VRP → envelope conformal (cobertura garantida) → auditoria (CRPS/PIT/cobertura). Tudo gateado por `validate.py` (walk-forward + Diebold-Mariano + CRPS + PIT): **nada entra sem bater o HAR**.

**Tech Stack:** Python 3.14. numpy/scipy entram **só no módulo `predict/`**, como optional-dependency isolada (`pyproject` extra `predict`) — o **core (pricing/api/deploy) continua pure-stdlib**, não muda o que sobe no túnel. pytest; FastAPI (endpoint). Sem DL, sem libs pesadas. Reusa `atlas_api.pricing.{har,rv,features,iv}` + o adapter `predict.series`.

**Restrição de acurácia (MEDIDA — memória `reference-dataset-atlas`):** a base tem **só ~1 ano (252 pregões, 2025-06 → 2026-06)**. Isso rege a potência do gate (walk-forward sobra ~120 dias OOS, DM de baixa potência) e é a razão de o ML-1 parar em **HAR-Lev + conformal** — nada de challenger pesado (sem amostra). OHLC é **completo e limpo** (Yang-Zhang alimentável direto, sem brapi), mas **13,5% das barras são colapsadas (O=H=L=C)** → exige gate de qualidade no adapter (Task 1). Universos: **738 nomes** servem forecast RV-only; **~60 nomes** têm IV≥252d p/ VRP/densidade/regime.

**Convenções do repo:** testes em `apps/api/tests/predict/`; rodar com `./.venv/Scripts/python.exe -m pytest` a partir de `apps/api`; commits em inglês, terminando com `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## Mapa de arquivos (ML-1)

| Arquivo | Responsabilidade |
|---|---|
| `apps/api/pyproject.toml` *(modificar)* | `+ [project.optional-dependencies] predict = ["numpy>=2.5","scipy>=1.18"]` — isolado do core |
| `apps/api/atlas_api/pricing/rv.py` *(reusar — NÃO reimplementar)* | **já tem** `yang_zhang(ohlc)` (rv.py:45) e `realized_vol`/`har_components` — o forecast reusa, não duplica |
| `apps/api/atlas_api/predict/series.py` *(criar)* | **adapter store→entradas do modelo**: `rolling_yang_zhang`, `rv_series`, `neg_return_series` (reusam `rv.yang_zhang`/`rv.realized_vol`) — é o elo que alimenta HAR-Lev e o endpoint |
| `apps/api/atlas_api/predict/__init__.py` *(criar)* | exports do módulo |
| `apps/api/atlas_api/predict/forecast.py` *(criar)* | `har_leverage`, `vol_ensemble` → `VolForecast(sigma, lo, hi)` |
| `apps/api/atlas_api/predict/distribution.py` *(criar)* | `physical_density` (Student-t + ajuste VRP), `pop`, `quantiles` |
| `apps/api/atlas_api/predict/conformal.py` *(criar)* | `split_conformal`, `aci_update` — cobertura garantida |
| `apps/api/atlas_api/predict/validate.py` *(criar)* | o GATE: `walk_forward`, `qlike`, `diebold_mariano`, `crps_gaussian`, `pit`, `coverage` |
| `apps/api/atlas_api/predict/regime.py` *(criar)* | `regime` + `strategy_bias` (IVR/VRP/term/skew + gates B3) |
| `apps/api/atlas_api/api/main.py` *(modificar)* | `GET /predict/{ativo}` |
| `apps/web/components/calibration-panel.tsx` *(criar)* | painel "calibração nos últimos N dias" (PIT/cobertura) |
| `apps/api/tests/predict/*` *(criar)* | testes por módulo |

---

## Chunk 1: Forecast de vol + o gate

### Task 0: Dependência isolada (numpy/scipy só no `predict/`) — pré-requisito do TDD

> **Review BR-1:** hoje `apps/api/pyproject.toml` tem `dependencies = []` e o venv é pure-stdlib (Python 3.14.5, sem numpy/scipy). Como os testes do `predict/` importam numpy/scipy, **sem este passo o "Step 2 — ver falhar" quebraria por `ModuleNotFoundError`, não pelo motivo certo**. Wheels cp314 confirmados instaláveis (numpy 2.5.0, scipy 1.18.0). O core (pricing/api/deploy) **não** ganha dependência — só o módulo novo.

**Files:** Modify `apps/api/pyproject.toml`

- [ ] **Step 1 — declarar** em `[project.optional-dependencies]`: `predict = ["numpy>=2.5", "scipy>=1.18"]` (ao lado de `dev`/`chat`).
- [ ] **Step 2 — instalar** no venv: `cd apps/api && ./.venv/Scripts/python.exe -m pip install -e ".[predict]"`.
- [ ] **Step 3 — sanity:** `./.venv/Scripts/python.exe -c "import numpy, scipy; print(numpy.__version__, scipy.__version__)"` → imprime versões (numpy 2.x).
- [ ] **Step 4 — commit:** `build(api): isolated numpy/scipy optional-deps for predict module`.

### Task 1: Adapter de dados (store → séries de entrada) — REUSA `rv.yang_zhang`

> **Por que existe (resolve 2 bloqueadores do review):** (B1) `rv.yang_zhang(ohlc)` **já existe e está testado** (rv.py:45, 5 testes) — **proibido reimplementar**. (B2) o endpoint precisa de séries que o store **não** entrega prontas: uma **RV diária**, uma **YZ rolante** e os **neg_returns alinhados**. Esta task materializa esse elo, uma vez, e o reusa no forecast e no endpoint.

**Files:** Create `apps/api/atlas_api/predict/series.py` · Test `apps/api/tests/predict/test_series.py`

- [ ] **Step 1 — teste que falha:**
```python
from atlas_api.predict.series import rolling_yang_zhang, rv_series, neg_return_series
from atlas_api.pricing.rv import yang_zhang, realized_vol
def test_rolling_yz_reuses_existing_estimator():
    ohlc = [(10+0.1*i, 10.3+0.1*i, 9.9+0.1*i, 10.1+0.1*i) for i in range(8)]
    out = rolling_yang_zhang(ohlc, window=4)
    assert len(out) == len(ohlc) - 4 + 1
    assert out[-1] == yang_zhang(ohlc[-4:])         # mesma função — sem duplicar a fórmula
def test_rv_series_prefers_yang_zhang_from_real_ohlc():
    ohlc = [(10+0.1*i, 10.3+0.1*i, 9.9+0.1*i, 10.1+0.1*i) for i in range(8)]
    s = rv_series(ohlc, window=4)
    assert s[-1] == rolling_yang_zhang(ohlc, window=4)[-1]   # usa YZ (OHLC real, ~5× mais eficiente)
def test_rv_series_gates_collapsed_bars():
    # janela DOMINADA por colapsadas (O=H=L=C, 13,5% da base) + 1 barra com range VÁLIDO:
    # o YZ cru seria contaminado p/ ~0 (artefato) → o gate cai p/ close-to-close (closes movem)
    ohlc = [(10.0,10.0,10.0,10.0)]*3 + [(10.0,10.3,9.9,10.2)]
    s = rv_series(ohlc, window=4)
    assert s[-1] > 0.0     # gate disparou: c2c dos closes (10,10,10,10.2) dá vol>0
def test_rv_series_all_collapsed_is_honest_zero():
    # tudo parado: a vol REAL é 0 — reportar 0.0, NÃO fabricar (distingue "gate→c2c útil" de "sem sinal")
    s = rv_series([(10.0,10.0,10.0,10.0)]*5, window=4)
    assert s[-1] == 0.0
def test_neg_return_series_is_strictly_negative_indicator():
    closes = [10.0, 10.2, 10.0, 9.8, 9.9]           # alta, queda, queda, alta
    nr = neg_return_series(closes)
    assert len(nr) == len(closes) - 1
    assert all(v <= 0.0 for v in nr) and any(v < 0.0 for v in nr)   # estritamente r<0 (não r≤0)
```
- [ ] **Step 2 — rodar e ver falhar:** `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/predict/test_series.py -v` → FAIL (módulo não existe).
- [ ] **Step 3 — implementar** `series.py`:
  - `rolling_yang_zhang(ohlc, window)` → lista chamando `rv.yang_zhang(ohlc[i-window:i])` em cada janela (REUSA; zero fórmula nova).
  - `rv_series(ohlc, window)` → a **série RV diária do HAR**, preferindo **Yang-Zhang do OHLC real** (mais eficiente que close-to-close — AIForge §3, ~5×; dado já existe, sem brapi). **Gate de qualidade (reaproveitamento):** se a janela é dominada por **barras colapsadas** (O=H=L=C, 13,5% da base), o YZ≈0 é artefato → cair para `realized_vol` close-to-close (declarado no docstring). Upgrade p/ RV intradiária é ML-2.
  - `neg_return_series(closes)` → log-retorno diário se `r < 0` senão `0.0` (indicador **estrito** `r<0`); o caller extrai `closes` do OHLC (`ohlc[i][3]`). Alinhado à série RV; é a entrada de leverage da Task 2.
- [ ] **Step 4 — rodar e passar.**
- [ ] **Step 5 — commit:** `feat(predict): data adapter (store→model inputs) reusing rv.yang_zhang`.

### Task 2: HAR-Leverage + ensemble

**Files:** Create `apps/api/atlas_api/predict/__init__.py`, `forecast.py` · Test `tests/predict/test_forecast.py`

- [ ] **Step 1 — teste que falha:** (a) com termo de leverage zerado, `har_leverage` reproduz `forecast_har` (±1e-6; na prática 0.0 exato); (b) `vol_ensemble([a,b])` == média simples; (c) `VolForecast` tem `sigma>0` e `lo<sigma<hi`.
```python
from atlas_api.predict.forecast import har_leverage, vol_ensemble, VolForecast
def test_har_leverage_reduces_to_har_when_no_leverage():
    rv = [0.2,0.21,0.19,0.22,0.2,0.23,0.21]*5
    base, lev = har_leverage(rv, neg_returns=[0.0]*len(rv))
    from atlas_api.pricing.har import fit_har, forecast_har
    assert abs(lev - forecast_har(fit_har(rv), rv)) < 1e-6
def test_ensemble_is_simple_average():
    assert vol_ensemble([0.2,0.3,0.4]) == 0.30
```
- [ ] **Step 2 — rodar/ver falhar.**
- [ ] **Step 3 — implementar:** `har_leverage(rv, neg_returns)` = HAR-RV (reusa `pricing.har`) + termo `β·1{r<0}·RV_d` — o `neg_returns` vem de `series.neg_return_series` (indicador **estrito** `r<0`, já alinhado); com `neg_returns` todo-zero o termo zera e reproduz o HAR (testado acima). `vol_ensemble(forecasts: list[float])` = média simples (combination puzzle — NÃO pesos ótimos); `VolForecast` dataclass `(sigma, lo, hi)`. **Unidade:** a série `rv` é a de `series.rv_series` (vol); manter consistência com o QLIKE da Task 3 (ver nota de unidade lá).
- [ ] **Step 4/5 — passar + commit:** `feat(predict): HAR-Leverage forecaster + simple-average ensemble`.

### Task 3: O GATE (forecast pontual) — walk-forward + Diebold-Mariano

**Files:** Create `apps/api/atlas_api/predict/validate.py` · Test `tests/predict/test_validate_point.py`

- [ ] **Step 1 — teste que falha:** (a) `qlike(y, yhat)` ≥ 0, =0 quando yhat=y; (b) `diebold_mariano` retorna p-valor < 0.05 quando um forecaster é injetadamente melhor; (c) `walk_forward` não vaza (treina em [0,t), prevê t).
```python
from atlas_api.predict.validate import qlike, diebold_mariano, walk_forward
def test_dm_detects_injected_edge():
    import numpy as np; rng=np.random.default_rng(0)
    var = np.abs(rng.normal(0.04, 0.008, 600))          # UNIDADE = variância (σ²), canônica do QLIKE
    good = var * np.exp(rng.normal(0, 0.05, 600))        # ruído MULTIPLICATIVO log-normal → preserva >0
    bad  = var * np.exp(rng.normal(0, 0.40, 600))        # 'bad' mais ruidoso; SEM variância negativa (review B-A)
    stat, p = diebold_mariano(var, good, bad, loss="qlike")
    assert p < 0.05 and stat < 0   # 'good' tem perda menor
def test_qlike_zero_at_equality():
    assert abs(qlike(0.04, 0.04)) < 1e-12
```
- [ ] **Step 2 — ver falhar.**
- [ ] **Step 3 — implementar:**
  - **`qlike(y,yhat) = yhat/y − log(yhat/y) − 1`** — a QLIKE de Patton é robusta a proxy ruidoso **sobre VARIÂNCIA**. **Trava de unidade:** `qlike` consome **variância (σ²)**. Como `series.rv_series`/`forecast` produzem **vol**, o `walk_forward`/gate **eleva ao quadrado** (vol→variância) antes de chamar `qlike`. Documentar no docstring; a inconsistência vol-vs-variância seria medir a coisa errada (review F5). **Domínio (review B-A):** exige `y>0, yhat>0`; o gate/`walk_forward` aplica floor `yhat=max(yhat,1e-12)` (previsão de variância é estritamente positiva) — evita `log` de valor não-positivo.
  - **`diebold_mariano(y,f1,f2,loss)`** com correção **HAC Newey-West**, lag de truncamento **declarado** = `floor(4·(n/100)**(2/9))` (regra automática), p-valor t-Student com `n−1` g.l.
  - **`walk_forward(series, fit_fn, predict_fn, min_train)`** gerador point-in-time (sem look-ahead).
- [ ] **Step 4/5 — passar + commit:** `feat(predict): validation gate — walk-forward + Diebold-Mariano + QLIKE`.

### Task 4: Provar HAR-Lev > HAR pelo gate (teste de integração) — o gate como teste

> **Review F2 (anti-circularidade):** o DGP do leverage (GJR-GARCH, `γ·1{r<0}·r²`) é **independente da forma** do HAR-Lev (feature `r·1{r<0}`) — sem auto-confirmação.
>
> **⚠ ACHADO da execução (medido, scripts da sessão) — mudou o desenho:** o termo de leverage **só é detectável com um proxy de RV LIMPO**. Com `r²` diário (chi²₁, ruidoso) o edge fica **abaixo do limiar do gate** (DM-significativo em só **3/8** seeds — *resultado negativo é resultado*). Com um proxy **intradiário agregado** — exatamente o que o **Yang-Zhang** do adapter (Task 1) entrega — o edge é robusto: **MSE vs variância verdadeira significativo em 8/8 seeds**; QLIKE production-faithful (vs RV realizado) em **7/8**. **Isto é por que o adapter prefere Yang-Zhang: não é só eficiência (~5×), é detectabilidade do sinal.** O teste usa o cenário realista e ancora no **MSE robusto** + QLIKE num seed representativo (seed 0, onde 7/8 concordam — não é cherry-pick).

**Files:** Test `tests/predict/test_har_lev_beats_har.py`

- [ ] **Step 1 — teste (gate como teste):** GJR-GARCH **com agregação intradiária** (`M≈26 barras/dia` → RV limpo, ≈ Yang-Zhang), `n=900`, `min_train=252`, seed 0. Walk-forward HAR vs HAR-Lev; o gate avalia **(A)** QLIKE contra o **RV realizado** (production-faithful — nunca vê a var verdadeira) e **(B)** MSE contra a **variância verdadeira** (confirmação-oráculo, robusta).
```python
def test_har_leverage_beats_har_through_the_gate():
    r, var, rvar = _gjr_garch_intraday(900, seed=0, M=26)   # leverage independente da forma do HAR-Lev
    rv = rvar.tolist(); neg = [x if x < 0 else 0.0 for x in r.tolist()]
    # walk-forward point-in-time: f_har, f_lev de har_leverage(rv[:t], neg[:t])
    # (A) production-faithful:  q_lev < q_har  e  DM(realized_rv, f_lev, f_har, "qlike") p<0.05, stat<0
    # (B) oráculo:              mse_lev < mse_har  e  DM(true_var, f_lev, f_har, "mse")  p<0.05, stat<0
    assert q_lev < q_har and stat_q < 0 and p_q < 0.05
    assert mse_lev < mse_har and stat_m < 0 and p_m < 0.05
```
- [ ] **Step 2/3/4 — rodar; se falhar, é sinal de bug no HAR-Lev (NÃO relaxar o p-valor nem o `<`, NÃO trocar a seed p/ passar).** Se HAR-Lev genuinamente não bater HAR com RV limpo, ele **não entra** (decisão do gate, spec §40/§150).
- [ ] **Step 5 — commit:** `test(predict): HAR-Leverage must beat HAR through the gate (clean RV, independent GJR DGP)`.

> **Implicação de design (honesta):** com **dados EOD diários** o proxy de RV (mesmo o Yang-Zhang sobre OHLC EOD) é mais limpo que `r²` mas ainda longe do intradiário. Logo, no dado real, o gate decide caso a caso; é plausível que HAR-Lev **não** seja promovido sobre HAR puro em alguns nomes — e a `vol_ensemble` (média HAR + HAR-Lev) é o hedge conservador. **HAR puro permanece o baseline; nada é chumbado.**

---

## Chunk 2: Distribuição física calibrada

### Task 5: Densidade física (Student-t + ajuste VRP) + POP

**Files:** Create `apps/api/atlas_api/predict/distribution.py` · Test `tests/predict/test_distribution.py`

- [ ] **Step 1 — teste que falha:** (a) `physical_density` integra ≈ 1; (b) ajuste VRP **encolhe** a σ (σ_fís < σ_iv quando VRP>0); (c) `pop(dist, target, side)` de um alvo na média ≈ 0.5; (d) cauda Student-t (ν finito) dá mais massa na cauda que a Normal.
```python
from atlas_api.predict.distribution import physical_density, pop
def test_vrp_shrinks_sigma():
    d_iv = physical_density(spot=38.0, sigma_iv=0.31, rv=0.24, vrp=0.07, T=30/365, lam=0.5)
    assert d_iv.sigma < 0.31 and d_iv.sigma > 0.24
def test_pop_at_mean_is_half():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30/365)
    assert abs(pop(d, target=38.0, side="above") - 0.5) < 0.02
```
- [ ] **Step 2 — ver falhar.**
- [ ] **Step 3 — implementar:** Student-t (scipy.stats.t) com `σ_fís = rv + (1−lam)·vrp` (λ default 0.5, calibrável depois), `ν` da curtose histórica (default 5), drift=0 **declarado**; `pop(dist,target,side)` via CDF; `quantiles(dist, qs)`. **Review F6 — coerência de argumentos:** `σ_fís` depende só de `rv` e `vrp`; `sigma_iv` é **redundante** (por construção `vrp ≈ sigma_iv − rv`, features.py:18). Para não permitir estados incoerentes, **validar** na entrada que `abs((rv+vrp) − sigma_iv) < tol` (ou derivar `vrp = sigma_iv − rv` internamente) e documentar que `sigma_iv` serve só ao painel "mercado vs físico".
- [ ] **Step 4/5 — passar + commit:** `feat(predict): physical density (Student-t + VRP adjustment) + POP`.

### Task 6: Conformal — cobertura garantida

**Files:** Create `apps/api/atlas_api/predict/conformal.py` · Test `tests/predict/test_conformal.py`

- [ ] **Step 1 — teste que falha:** três asserts — (a) cobertura ≥ nominal **sob má-especificação** (σ subestimada); (b) cobertura também sob **σ heterocedástico** (resíduo padronizado — onde mora o bug, review F4); (c) **ACI reage a shift** de regime (review: `aci_update` não pode entrar sem teste).
```python
from atlas_api.predict.conformal import split_conformal, aci_update
def test_conformal_guarantees_coverage_under_misspecification():
    import numpy as np; rng=np.random.default_rng(1)
    y = rng.standard_t(4, 2000)*0.05                       # cauda gorda real
    mu = np.zeros_like(y); sigma = np.full_like(y, 0.03)   # σ SUBestimada de propósito
    lo,hi = split_conformal(y[:1000], mu[:1000], sigma[:1000], mu[1000:], sigma[1000:], alpha=0.2)
    cov = np.mean((y[1000:]>=lo)&(y[1000:]<=hi))
    assert cov >= 0.79     # split-conformal garante ≥ 1−α−1/(n+1) ≈ 0.799; 0.79 pega off-by-one
def test_conformal_coverage_under_heteroscedastic_sigma():
    import numpy as np; rng=np.random.default_rng(3)
    sig = np.linspace(0.02, 0.08, 2000)                    # σ cresce (heterocedástico)
    y = rng.standard_normal(2000)*sig
    lo,hi = split_conformal(y[:1000], np.zeros(1000), sig[:1000], np.zeros(1000), sig[1000:], alpha=0.2)
    assert np.mean((y[1000:]>=lo)&(y[1000:]<=hi)) >= 0.79  # padronização por σ mantém cobertura
def test_aci_reacts_to_shift_and_stays_bounded():
    a = 0.2
    for _ in range(8): a = aci_update(a, covered=False, gamma=0.02)  # série de "não cobriu"
    assert 0.0 < a < 0.2   # α desce (alarga o intervalo) SEM divergir — aci_update clampa em [0,1] (NIT-1)
```
- [ ] **Step 2 — ver falhar.**
- [ ] **Step 3 — implementar:** `split_conformal` (quantil empírico dos resíduos **padronizados por σ** de calibração → ajusta a largura; garantia **marginal**, distribution-free) + `aci_update(alpha, covered, gamma)` (Gibbs-Candès, adaptativo p/ regime; `α ← clip(α + γ·(target − miss), 0, 1)` — **clamp obrigatório em [0,1]**, senão diverge, review NIT-1). ~30 linhas numpy.
- [ ] **Step 4/5 — passar + commit:** `feat(predict): split + adaptive conformal coverage`.

### Task 7: Auditoria da distribuição (CRPS + PIT + cobertura)

**Files:** Modify `apps/api/atlas_api/predict/validate.py` · Test `tests/predict/test_validate_dist.py`

- [ ] **Step 1 — teste que falha:** (a) `crps_gaussian` (forma fechada) bate a integral numérica ±1e-4 em **vários** (μ,σ,y); (b) PIT de um modelo **bem calibrado** passa no KS e de um **subdisperso real** falha; (c) `coverage(y,lo,hi)` ≈ nominal.
```python
import numpy as np
from scipy import stats
from atlas_api.predict.validate import crps_gaussian, pit_uniformity, coverage
def test_crps_matches_numeric_over_grid():
    for mu, sigma, y in [(0,1,0.5),(0.2,0.3,0.0),(-1,2,3.0)]:
        grid = np.linspace(mu-12*sigma, mu+12*sigma, 400000)  # grid fino: erro quadratura ~2e-5 << 1e-4 (review N-A, validado)
        cdf = stats.norm.cdf(grid, mu, sigma)
        numeric = np.trapezoid((cdf - (grid >= y))**2, grid)  # np.trapz foi removido no numpy 2.x
        assert abs(crps_gaussian(y, mu, sigma) - numeric) < 1e-4
def test_pit_flags_underdispersion_honestly():
    rng = np.random.default_rng(2)
    sigma_real, sigma_model = 0.05, 0.03                       # modelo ESTREITO demais
    y = rng.normal(0.0, sigma_real, 4000)
    pit_vals = stats.norm.cdf(y, 0.0, sigma_model)             # PIT da CDF Normal do MODELO (não um tanh)
    assert pit_uniformity(pit_vals) < 0.05                     # U-shape pelo motivo certo: subdispersão
    pit_ok = stats.norm.cdf(y, 0.0, sigma_real)               # modelo bem calibrado
    assert pit_uniformity(pit_ok) > 0.05
```
- [ ] **Step 2 — ver falhar.**
- [ ] **Step 3 — implementar:** `crps_gaussian(y,mu,sigma)=σ[z(2Φ(z)−1)+2φ(z)−1/√π]`, z=(y−μ)/σ (forma fechada de Gneiting — confirmada correta no review); `pit(y,cdf_fn)` e `pit_uniformity` (KS contra Uniforme[0,1]); `coverage(y,lo,hi)`.
- [ ] **Step 4/5 — passar + commit:** `feat(predict): distribution audit — CRPS + PIT + coverage`.

---

## Chunk 3: Regime, API e calibração na UI

### Task 8: Regime → viés de estrutura

**Files:** Create `apps/api/atlas_api/predict/regime.py` · Test `tests/predict/test_regime.py`

- [ ] **Step 1 — teste que falha:** (a) IVR alto + VRP>0 + term em contango → bias "vender prêmio"; (b) **backwardation → bias "parar venda a descoberto"**; (c) IVR baixo → "comprar/debit".
- [ ] **Step 2 — rodar e ver falhar** (função não existe).
- [ ] **Step 3 — implementar** `regime(iv_rank, vrp, term_slope, skew)` → str; `strategy_bias(regime)` + gates B3 (flag liquidez, exercício). **Entradas reais (reaproveitamento):** `term_slope` e `skew` vêm da tabela `options` (tem `strike/venc/delta/iv`) — `skew` reusa `features.skew_25d` (25Δ put − ATM); `term_slope` = IV(venc longo) − IV(venc curto) por subjacente. `iv_rank`/`vrp` reusam `signal.iv_rank`/`features.vrp`. Sem números chumbados que não venham do dado; `None` honesto quando o nome não tem cadeia líquida (universo de ~60-154 nomes com IV).
- [ ] **Step 4/5 — passar + commit:** `feat(predict): regime detection + strategy bias (B3 gates)`.

### Task 9: Endpoint `GET /predict/{ativo}`

**Files:** Modify `apps/api/atlas_api/api/main.py` · Test `tests/predict/test_predict_route.py`

- [ ] **Step 1 — teste que falha:** com o store seedado, `GET /predict/PETR4` → 200 com `{sigma, dist:{pop_targets, quantiles}, regime, calibration:{pit_ok, coverage}}`; sem store → 503 (padrão honesto já existente).
- [ ] **Step 2 — rodar e ver falhar** (rota não existe → 404).
- [ ] **Step 3 — implementar** o endpoint usando `_require_conn`, montando as entradas **via `predict.series`** (fecha o elo de dados, review B2):
  - `store.price_history(conn, ativo, limit=…)` → `series.rolling_yang_zhang` (série YZ) **e** `series.rv_series` (RV diária do HAR);
  - `store.close_series` (devolve `(date, close)` — extrair `closes = [c for _, c in ...]`) → `series.neg_return_series` (leverage, alinhado);
  - `store.iv_history` → IV/VRP (reusa `pricing.features`).
  Depois: `forecast → distribution → conformal → auditoria`. Se as séries forem curtas demais p/ o walk-forward, devolver `calibration` com flag honesta (sem fabricar número). Provenance + asof como nos outros endpoints.
- [ ] **Step 4/5 — passar + commit:** `feat(api): GET /predict/{ativo} — calibrated vol/distribution`.

### Task 10: Painel de calibração (frontend)

**Files:** Create `apps/web/components/calibration-panel.tsx` · (verificar tsc/eslint/build)

- [ ] **Step 1 — implementar** componente que consome `/api/predict/{ativo}` e mostra o **PIT/cobertura dos últimos N dias** + "mercado cobra X (IV), estimamos Y (física)" + selo "predição calibrada, não profecia". Responsivo (abas mobile já existem). Estados honestos de erro (sem dado → mensagem).
- [ ] **Step 2 — verificar:** `npx tsc --noEmit` + `npx eslint` limpos; build de produção; conferir no preview (mobile + laptop).
- [ ] **Step 3 — commit:** `feat(web): calibration panel (PIT/coverage + market-vs-physical)`.

---

## Critérios de aceite da Fase ML-1
1. `pytest` verde (todos os novos testes) + os 178 existentes intactos; o **core segue pure-stdlib** (numpy/scipy só em `predict/`, opt-in — o deploy do túnel não muda).
2. **HAR-Leverage bate HAR no gate** (Task 4) — senão, não promove.
3. O endpoint devolve POP com **intervalo conformal** e o **PIT** auditado.
4. `tsc` + `eslint` + build limpos; painel funciona em mobile e laptop.
5. Zero mock/hardcoded onde deveria ser dinâmico (regra do projeto).

## Fora de escopo (vai para o plano ML-2) — decisões conscientes do review
- features PDV (Guyon-Lekeufack) · HARX/THAR/STHAR · SSVI/eSSVI density (nomes líquidos) · NGBoost/quantile-GBM challenger · DCP · Model Confidence Set/Hansen SPA · Deflated Sharpe.
- **Recalibração isotônica (PIT→uniforme, `calibrate.py`)** — o spec §131 a listava na Camada 2. **Movida conscientemente para ML-2**: em ML-1 o **conformal já garante cobertura marginal** (a maior alavanca de honestidade); a isotônica é refinamento de calibração e será PAVA **pure-Python** (sem sklearn, coerente com "sem libs pesadas").
- **Régua econômica (P&L líquido de custos+imposto B3)** — spec §94, parte da espinha do gate. **Entra em ML-2** junto do Deflated Sharpe/MCS (precisa de back-test de P&L, não só de erro de previsão).

Cada um **só entra pela porta do gate** (bater HAR em walk-forward + DM/MCS).
