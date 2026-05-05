from __future__ import annotations

import json
from pathlib import Path

from pipeline.eprel import infer_eprel_product_group, resolve_eprel_energy_label
from pipeline.parser_product_manufacturer import ManufacturerProductParser
from pipeline.parser_product_skroutz import SkroutzProductParser


def test_infer_eprel_product_group_uses_resolved_oven_taxonomy() -> None:
    product_group = infer_eprel_product_group(
        family_key="built_in_appliance",
        breadcrumbs=["Home", "Home Appliances", "Built-in Appliances", "Ovens"],
        taxonomy_source_category="Home Appliances > Built-in Appliances > Ovens",
    )

    assert product_group == "ovens"


def test_resolve_eprel_energy_label_uses_model_identifier_search() -> None:
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_fetch_json(url: str, params: dict[str, object] | None = None) -> dict[str, object]:
        calls.append((url, params))
        if url.endswith("/api/products/ovens"):
            assert params is not None
            assert params["modelIdentifier"] == "HBG7241B1"
            return {
                "size": 1,
                "hits": [
                    {
                        "modelIdentifier": "HBG7241B1",
                        "eprelRegistrationNumber": "1334473",
                    }
                ],
            }
        if url.endswith("/api/products/ovens/1334473/labels"):
            assert params == {"noRedirect": "true", "format": "PNG"}
            return {"address": "/labels/ovens/Label_1334473.png"}
        raise AssertionError(f"unexpected_url:{url}")

    resolved = resolve_eprel_energy_label(
        family_key="built_in_oven",
        model_identifier="HBG7241B1",
        fetch_json=fake_fetch_json,
    )

    assert resolved.product_group == "ovens"
    assert resolved.registration_number == "1334473"
    assert resolved.label_url == "https://eprel.ec.europa.eu/labels/ovens/Label_1334473.png"
    assert resolved.search_strategy == "model_identifier"
    assert len(calls) == 2


def test_skroutz_parser_skips_energy_label_when_eprel_resolution_is_empty(monkeypatch) -> None:
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "providers"
        / "skroutz"
        / "taxonomy_cases"
        / "234217.html"
    )
    html = fixture_path.read_text(encoding="utf-8")

    monkeypatch.setattr("pipeline.parser_product_skroutz.resolve_eprel_energy_label_asset_url", lambda **_: "")

    parsed = SkroutzProductParser().parse(
        html,
        "https://www.skroutz.gr/s/57703834/bosch-sks2iti00e-plyntirio-piaton-pagou-gia-6-servitsia-p55-1xy45ek-gri.html",
    )

    assert parsed.source.brand == "Bosch"
    assert parsed.source.energy_label_asset_url == ""


def test_bosch_manufacturer_parser_uses_eprel_resolution_for_energy_label(monkeypatch) -> None:
    monkeypatch.setattr(
        "pipeline.parser_product_manufacturer.resolve_eprel_energy_label_asset_url",
        lambda **_: "https://eprel.ec.europa.eu/labels/ovens/Label_1334473.png",
    )

    parsed = ManufacturerProductParser().parse(
        _bosch_product_html(),
        "https://www.bosch-home.gr/el/mkt-product/mageirema-psisimo/entoixizomenes-kouzines-fournoi/entoixizomenoi-fournoi/HBG7241B1",
        source_name="manufacturer_bosch",
    )

    assert parsed.source.energy_label_asset_url == "https://eprel.ec.europa.eu/labels/ovens/Label_1334473.png"
    assert parsed.source.product_sheet_asset_url == "https://media3.bsh-group.com/Documents/eudatasheet/el-GR/HBG7241B1.pdf"


def test_bosch_manufacturer_parser_skips_icon_when_eprel_resolution_is_empty(monkeypatch) -> None:
    monkeypatch.setattr("pipeline.parser_product_manufacturer.resolve_eprel_energy_label_asset_url", lambda **_: "")

    parsed = ManufacturerProductParser().parse(
        _bosch_product_html(),
        "https://www.bosch-home.gr/el/mkt-product/mageirema-psisimo/entoixizomenes-kouzines-fournoi/entoixizomenoi-fournoi/HBG7241B1",
        source_name="manufacturer_bosch",
    )

    assert parsed.source.energy_label_asset_url == ""
    assert "Feature_Icons" not in parsed.source.energy_label_asset_url


def _bosch_product_html() -> str:
    product = {
        "productCode": "HBG7241B1",
        "productBrand": "BOSCH",
        "title": {
            "valueClass": "Bosch",
            "headline": "HBG7241B1 Built-in Oven",
        },
        "images": [
            {
                "url": "https://example.com/main.webp",
            }
        ],
        "energyLabel": {
            "icon": {
                "id": "21143877_ENERGY_CLASS_ICON_2010_A_PLUS",
                "mediaType": "Feature_Icons",
            },
            "pdf": {
                "link": {
                    "value": "https://media3.bsh-group.com/Documents/energylabel/el-GR/HBG7241B1.pdf",
                }
            },
            "energyClassValue": "A+",
        },
        "dataSheet": {
            "url": "https://media3.bsh-group.com/Documents/eudatasheet/el-GR/HBG7241B1.pdf",
        },
        "combinedBreadcrumbs": [
            {"title": "Products"},
            {"title": "Cooking"},
            {"title": "Built-in ovens"},
        ],
        "highlights": [
            {
                "headline": {"text": "Series 8"},
                "text": {"text": "Built-in oven"},
            }
        ],
        "specifications": [],
    }
    next_payload = json.dumps([1, json.dumps(product)])
    jsonld = json.dumps(
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Bosch HBG7241B1 Built-in Oven",
            "brand": {"@type": "Brand", "name": "BOSCH"},
            "mpn": "HBG7241B1",
            "image": ["https://example.com/main.webp"],
        }
    )
    return f"""
<html>
  <head>
    <link rel="canonical" href="https://www.bosch-home.gr/el/mkt-product/mageirema-psisimo/entoixizomenes-kouzines-fournoi/entoixizomenoi-fournoi/HBG7241B1" />
    <script type="application/ld+json">{jsonld}</script>
    <script>self.__next_f.push({next_payload})</script>
  </head>
  <body></body>
</html>
"""
