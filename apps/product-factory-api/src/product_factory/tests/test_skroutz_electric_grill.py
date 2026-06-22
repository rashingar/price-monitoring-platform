from product_factory.parser_product_skroutz import SkroutzProductParser
from product_factory.source_detection import is_skroutz_product_url


def test_skroutz_electric_grill_family_supports_category_and_title_variants() -> None:
    parser = SkroutzProductParser()

    assert (
        parser._resolve_family(
            "Ηλεκτρικές Ψηστιέρες",
            "https://www.skroutz.gr/c/2225/electric_barbeque.html",
            "Rohnson R-250 Επιτραπέζια Ηλεκτρική Ψησταριά",
        )
        == "electric_grill"
    )
    assert (
        parser._resolve_family(
            "",
            "",
            "Rohnson R-250 Ilektriki Psistaria Scharas 2200W",
        )
        == "electric_grill"
    )


def test_skroutz_scope_accepts_product_routes_but_not_listing_routes() -> None:
    assert is_skroutz_product_url(
        "https://www.skroutz.gr/s/123456/a-new-product-family.html"
    )
    assert not is_skroutz_product_url(
        "https://www.skroutz.gr/c/123456/a-category.html"
    )
