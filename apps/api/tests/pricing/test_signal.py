from atlas_api.pricing.signal import classify, iv_rank


def test_iv_rank_positions_current_between_min_and_max():
    hist = [0.20 + 0.001 * i for i in range(40)]  # 0.20..0.239
    assert iv_rank(hist, 0.20) == 0.0    # at the low
    assert iv_rank(hist, 0.239) == 100.0  # at the high
    assert iv_rank(hist, 0.2195) == 50.0  # mid


def test_iv_rank_none_when_history_too_short():
    assert iv_rank([0.20, 0.25, 0.30], 0.25) is None  # < MIN_IV_HISTORY


def test_iv_rank_none_when_flat_window():
    assert iv_rank([0.30] * 40, 0.30) is None  # max == min -> undefined


def test_iv_rank_ignores_nan_history():
    hist = [float("nan")] * 5 + [0.10 + 0.01 * i for i in range(40)]
    assert iv_rank(hist, 0.10) == 0.0


def test_rico():
    assert classify(0.42, 0.33, band=0.10) == "rico"


def test_barato():
    assert classify(0.30, 0.40, band=0.10) == "barato"


def test_neutro():
    assert classify(0.40, 0.40, band=0.10) == "neutro"


def test_classify_nan_is_indisponivel():
    assert classify(float("nan"), 0.33) == "indisponivel"
    assert classify(0.40, float("nan")) == "indisponivel"
