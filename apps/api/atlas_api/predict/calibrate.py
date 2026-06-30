"""Recalibração isotônica de distribuições preditivas (ML-2, herdada do spec §131).

Motivada por uma MEDIÇÃO do ML-1: o PIT flagrou que a Student-t de ν fixo não casa a
forma em alguns nomes (ex.: PETR4 pit_ok=False). Kuleshov et al. (2018) recalibram
ajustando uma função isotônica R (o ECDF dos PIT de calibração) tal que R∘CDF fique
uniforme. PAVA (pool adjacent violators) faz o ajuste isotônico em pure-Python/numpy.
"""
from __future__ import annotations

import numpy as np


def pava(y, w=None):
    """Regressão isotônica (não-decrescente) por Pool Adjacent Violators, mínimos quadrados.

    Preserva a média (solução L2). ``w`` são pesos opcionais. Retorna o vetor ajustado.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    w = np.ones(n) if w is None else np.asarray(w, dtype=float)
    vals: list[float] = []
    wts: list[float] = []
    cnts: list[int] = []
    for i in range(n):
        v, ww, c = float(y[i]), float(w[i]), 1
        while vals and vals[-1] > v:                 # violação: bloco anterior maior → funde
            pv, pw, pc = vals.pop(), wts.pop(), cnts.pop()
            v = (pv * pw + v * ww) / (pw + ww)
            ww += pw
            c += pc
        vals.append(v)
        wts.append(ww)
        cnts.append(c)
    out = np.empty(n)
    j = 0
    for v, c in zip(vals, cnts):
        out[j:j + c] = v
        j += c
    return out


class IsotonicRecalibrator:
    """R: [0,1]→[0,1] isotônica que mapeia o PIT observado para uniforme (Kuleshov 2018)."""

    def __init__(self) -> None:
        self._x: np.ndarray | None = None
        self._r: np.ndarray | None = None

    def fit(self, pit_cal) -> "IsotonicRecalibrator":
        """Ajusta R aos PIT de calibração: x = PIT ordenado, alvo = posições uniformes."""
        x = np.sort(np.asarray(pit_cal, dtype=float))
        n = x.size
        if n < 2:
            raise ValueError("need >= 2 calibration PIT values")
        targets = (np.arange(n) + 0.5) / n           # plotting positions uniformes
        self._x = x
        self._r = pava(targets)                       # já monotônico; PAVA p/ robustez a empates
        return self

    def apply(self, p):
        """Aplica R a um PIT (ou array): ``R(p)`` por interpolação, clampada em [0,1]."""
        if self._x is None or self._r is None:
            raise RuntimeError("fit() before apply()")
        out = np.interp(np.asarray(p, dtype=float), self._x, self._r, left=0.0, right=1.0)
        return np.clip(out, 0.0, 1.0)

    def inverse(self, q):
        """R⁻¹(q): nível de CDF crua que recalibrado vira ``q`` — usado p/ recalibrar quantis."""
        if self._x is None or self._r is None:
            raise RuntimeError("fit() before inverse()")
        out = np.interp(np.asarray(q, dtype=float), self._r, self._x, left=0.0, right=1.0)
        return np.clip(out, 0.0, 1.0)


def online_recalibrator(pit_history, *, window: int = 60) -> IsotonicRecalibrator | None:
    """Recalibrador ajustado na JANELA RECENTE do PIT (online, point-in-time).

    Decisão de design medida no dado real: o ajuste com split estático PIORA sob
    não-estacionariedade (chegou a derrubar o PIT da VALE3 de 0.67→0.0001); a versão
    rolante conserta o caso quebrado (PETR4 0.006→0.79) e é inócua nos já calibrados.
    Retorna ``None`` se não há janela suficiente.
    """
    pit_history = np.asarray(pit_history, dtype=float)
    if pit_history.size < window:
        return None
    return IsotonicRecalibrator().fit(pit_history[-window:])
