from pipeline.normalize import parse_euro_price


def test_parse_euro_price_greek_formats() -> None:
    assert parse_euro_price("798,00 €") == 798.0
    assert parse_euro_price("1.249,00 €") == 1249.0
    assert parse_euro_price("Τιμή e-shop 249,90 €") == 249.9
    assert parse_euro_price(None) is None

