"""Back-ajuste de splits/agrupamentos: neutraliza o salto espúrio antes de RV/retornos."""
import math

from atlas_api.predict.series import (
    _split_factors,
    neg_return_series,
    rv_series,
    split_adjust_closes,
)


def _ohlc(closes: list[float]) -> list[tuple]:
    # barra sintética coerente (low ≤ o,c ≤ high) em torno do close
    return [(c, c * 1.01, c * 0.99, c) for c in closes]


def test_no_split_leaves_series_unchanged():
    closes = [10.0, 10.2, 9.9, 10.4, 10.1, 10.3]
    assert split_adjust_closes(closes) == closes                 # sem salto → fator 1.0 em tudo
    assert all(f == 1.0 for f in _split_factors(closes))


def test_split_is_neutralized():
    # 1:5 split no meio: 100 → 20; as barras ANTES devem ser reescaladas p/ ~1/5 (série contínua)
    pre = [100.0, 101.0, 99.0, 102.0]
    post = [20.4, 20.6, 20.2, 20.5]                              # 102 → 20.4 (queda de ~5×)
    closes = pre + post
    adj = split_adjust_closes(closes)
    # pós-split inalterado; pré-split reescalado p/ o nível pós (contínuo, sem salto de 5×)
    assert adj[-4:] == post
    assert all(15.0 < c < 25.0 for c in adj[:4])                 # os 100s viraram ~20
    # o retorno espúrio de −1.6 (log(20.4/102)) some após o ajuste
    rets = [math.log(adj[i + 1] / adj[i]) for i in range(len(adj) - 1)]
    assert max(abs(r) for r in rets) < 0.35                      # nenhum salto de split remanescente


def test_split_removes_spurious_rv_spike():
    # RV com o salto de split seria enorme; após o ajuste fica em nível normal
    closes = [50.0] * 10 + [10.0] * 10                           # agrupamento/split 5× no meio
    rv = rv_series(_ohlc(closes), window=5)
    assert max(rv) < 1.0                                          # sem o pico espúrio (seria >>1 com o salto)
    # e o indicador de retorno negativo não crava o −1.6 do dia do split
    neg = neg_return_series(closes)
    assert min(neg) > -0.35
