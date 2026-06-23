import argparse

from product_factory.input_validation import validate_input
from product_factory.mapping import build_row
from product_factory.models import (
    CLIInput,
    ParsedProduct,
    SchemaMatchResult,
    SourceProductData,
    TaxonomyResolution,
)

SAMPLES = {
    "143481": {
        "url": "https://www.skroutz.gr/s/61800471/tcl-q65h-soundbar-5-1-bluetooth-hdmi-kai-wi-fi-me-asyrmato-subwoofer-mayro.html",
        "photos": 8,
        "sections": 9,
        "skroutz_status": 1,
        "boxnow": 0,
        "price": "269",
    },
    "344317": {
        "url": "https://www.skroutz.cy/s/65282590/tefal-subito-kafetiera-filtrou-1000w.html",
        "photos": 2,
        "sections": 0,
        "skroutz_status": 0,
        "boxnow": 0,
        "price": "39",
    },
    "341490": {
        "url": "https://www.skroutz.gr/s/51055155/Estia-Intense-Vrastiras-1-7lt-2200W-Luminus-Mat.html",
        "photos": 7,
        "sections": 0,
        "skroutz_status": 0,
        "boxnow": 1,
        "price": "19",
    },
}


def make_cli(model: str) -> CLIInput:
    sample = SAMPLES[model]
    return CLIInput(
        model=model,
        url=sample["url"],
        photos=sample["photos"],
        sections=sample["sections"],
        skroutz_status=sample["skroutz_status"],
        boxnow=sample["boxnow"],
        price=sample["price"],
        out="unused",
    )


def test_validate_input_accepts_skroutz_sections_for_v2() -> None:
    args = argparse.Namespace(
        model="143481",
        url=SAMPLES["143481"]["url"],
        photos=8,
        sections=9,
        skroutz_status=1,
        boxnow=0,
        price="269",
        out="out",
    )
    cli = validate_input(args)
    assert cli.model == "143481"
    assert cli.sections == 9
    assert cli.skroutz_status == 1


def test_validate_input_accepts_bestprice_product_url() -> None:
    args = argparse.Namespace(
        model="143667",
        url="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html",
        photos=1,
        sections=0,
        skroutz_status=1,
        boxnow=0,
        price="0",
        out="out",
    )
    cli = validate_input(args)
    assert cli.model == "143667"
    assert cli.url == args.url


def test_validate_input_accepts_apothema_product_url() -> None:
    args = argparse.Namespace(
        model="345145",
        url="https://www.apothema.gr/hisense-hbd5a-dianemhths-mpyras-5lt-304513p?source=bestprice",
        photos=10,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="0",
        out="out",
    )
    cli = validate_input(args)
    assert cli.model == "345145"
    assert cli.url == args.url


def test_validate_input_accepts_kotsovolos_product_url() -> None:
    args = argparse.Namespace(
        model="412917",
        url="https://www.kotsovolos.gr/air-condition-heaters/air-condition/7000-to-15000-btu/245318-a-c-in18btu-inventor-ar5vi-18wfi-aria",
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="0",
        out="out",
    )
    cli = validate_input(args)
    assert cli.model == "412917"
    assert cli.url == args.url


def test_validate_input_accepts_estia_product_url() -> None:
    args = argparse.Namespace(
        model="343089",
        url="https://estiahomeart.com/01-32098",
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=1,
        price="16.60",
        out="out",
    )
    cli = validate_input(args)
    assert cli.model == "343089"
    assert cli.url == args.url


def test_validate_input_accepts_marketquest_product_url() -> None:
    args = argparse.Namespace(
        model="344876",
        url="https://www.marketquest.gr/product/1336/bra-tigani-grill-signature-me-rabdwseis-apo-anoxeidwto.html",
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=1,
        price="45",
        out="out",
    )
    cli = validate_input(args)
    assert cli.model == "344876"
    assert cli.url == args.url


def test_validate_input_rejects_tefal_manufacturer_product_url() -> None:
    args = argparse.Namespace(
        model="344709",
        url="https://shop.tefal.gr/products/dolci-%CF%80%CE%B1%CE%B3%CF%89%CF%84%CE%BF%CE%BC%CE%B7%CF%87%CE%B1%CE%BD%CE%AE-ig602a",
        photos=3,
        sections=7,
        skroutz_status=0,
        boxnow=1,
        price="219",
        out="out",
    )
    try:
        validate_input(args)
    except ValueError as exc:
        assert (
            str(exc)
            == "Input URL must be an Electronet, Dream Electric, Skroutz, BestPrice, Kotsovolos, Estia, Apothema, MarketQuest, Euragora, or Pampoukidis product URL"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_validate_input_rejects_non_product_skroutz_url() -> None:
    args = argparse.Namespace(
        model="341490",
        url="https://www.skroutz.gr/c/699/vrastires.html",
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="19",
        out="out",
    )
    try:
        validate_input(args)
    except ValueError as exc:
        assert (
            str(exc)
            == "Input URL must be an Electronet, Dream Electric, Skroutz, BestPrice, Kotsovolos, Estia, Apothema, MarketQuest, Euragora, or Pampoukidis product URL"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_validate_input_rejects_non_product_tefal_url() -> None:
    args = argparse.Namespace(
        model="344709",
        url="https://shop.tefal.gr/collections/all",
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="219",
        out="out",
    )
    try:
        validate_input(args)
    except ValueError as exc:
        assert (
            str(exc)
            == "Input URL must be an Electronet, Dream Electric, Skroutz, BestPrice, Kotsovolos, Estia, Apothema, MarketQuest, Euragora, or Pampoukidis product URL"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_build_row_keeps_prompt_price_contract() -> None:
    cli = CLIInput(model="341490", url=SAMPLES["341490"]["url"], price="0")
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="skroutz",
            brand="Estia",
            mpn="06-24567",
            name="Estia 06-24567",
            price_value=15.9,
        )
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΞΞ™ΞΞ™Ξ‘ΞΞΞ£ Ξ•ΞΞΞ Ξ›Ξ™Ξ£ΞΞΞ£",
        leaf_category="Ξ£Ο…ΟƒΞΊΞµΟ…Ξ­Ο‚ ΞΞΏΟ…Ξ¶Ξ―Ξ½Ξ±Ο‚",
        sub_category="Ξ’ΟΞ±ΟƒΟ„Ξ®ΟΞµΟ‚",
        cta_url="https://example.com",
    )
    row, _, _ = build_row(
        cli=cli, parsed=parsed, taxonomy=taxonomy, schema_match=SchemaMatchResult()
    )
    assert row["price"] == "0"
