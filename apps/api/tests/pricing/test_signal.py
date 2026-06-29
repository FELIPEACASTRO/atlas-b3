from atlas_api.pricing.signal import classify


def test_rico():
    assert classify(0.42, 0.33, band=0.10) == "rico"


def test_barato():
    assert classify(0.30, 0.40, band=0.10) == "barato"


def test_neutro():
    assert classify(0.40, 0.40, band=0.10) == "neutro"
