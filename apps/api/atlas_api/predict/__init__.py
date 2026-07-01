"""Motor de predição de vol/distribuição (ML-1).

Isolado do core pure-stdlib: este módulo (e só ele) usa numpy/scipy, declarados
no extra `predict` do pyproject. Prevê VOLATILIDADE e DISTRIBUIÇÃO, nunca direção;
nada entra sem bater o HAR pelo gate de validação (spec §2, §90).
"""
