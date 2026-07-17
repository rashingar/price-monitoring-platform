from __future__ import annotations

from io import BytesIO
from PIL import Image

from product_factory.seo_health import evaluate_seo_health, validate_seo_health_contract
from product_factory.seo_phase2 import (
    build_image_slug_candidate,
    catalog_similarity,
    description_heading,
    is_jpeg_bytes,
    plan_gallery_assets,
    recommend_related_products,
    section_image_alt,
    validate_gallery_assets,
)


_buffer = BytesIO()
Image.new("RGB", (1, 1), "white").save(_buffer, format="JPEG")
JPEG = _buffer.getvalue()
PNG = b"\x89PNG\r\n\x1a\nnot-a-jpeg"
WEBP = b"RIFFxxxxWEBPnot-a-jpeg"


def _assets(*, published: str = "", legacy: bool = False):
    return plan_gallery_assets(
        model="123456",
        image_slug_candidate="midea-solunar-ef-12rd1h-klimatistiko-12000-btu",
        product_identity="Midea Solunar EF-12RD1H κλιματιστικό 12000 BTU",
        published_image=published,
        images=[
            {"url": "https://img/1", "position": 1, "jpeg_valid": True, "content_hash": "a", "local_filename": "123456-1.jpg" if legacy else ""},
            {"url": "https://img/2", "position": 2, "jpeg_valid": True, "content_hash": "b", "source_alt": "Εσωτερική μονάδα Midea Solunar EF-12RD1H"},
            {"url": "https://img/3", "position": 3, "jpeg_valid": True, "content_hash": "b"},
        ],
    )


def test_new_ac_gallery_names_positions_and_jpeg_bytes() -> None:
    slug = build_image_slug_candidate(brand="Midea", commercial_series="Solunar", primary_model="EF-12RD1H", category_phrase="Κλιματιστικό", primary_spec="12000 BTU")
    assert slug == "midea-solunar-ef-12rd1h-klimatistiko-12000-btu"
    assets = _assets()
    assert [asset["filename_candidate"] for asset in assets] == [f"{slug}-{i}.jpg" for i in (1, 2, 3)]
    assert assets[0]["role"] == "main" and [asset["position"] for asset in assets] == [1, 2, 3]
    assert is_jpeg_bytes(JPEG) and not is_jpeg_bytes(PNG) and not is_jpeg_bytes(WEBP)
    assert validate_gallery_assets(assets) == []


def test_published_lock_legacy_fallback_and_duplicate_hash_are_reported() -> None:
    locked = _assets(published="catalog/01_main/123456/supplier-main.jpg")
    assert locked[0]["public_path"].endswith("supplier-main.jpg") and locked[0]["filename_locked"] is True
    legacy = _assets(legacy=True)
    assert legacy[0]["public_path"].endswith("123456-1.jpg")
    assert legacy[2]["duplicate_content"] is True


def test_gallery_alt_and_description_alt_policies() -> None:
    assets = _assets()
    assert assets[0]["alt"] == "Midea Solunar EF-12RD1H κλιματιστικό 12000 BTU"
    assert assets[1]["alt"] == "Εσωτερική μονάδα Midea Solunar EF-12RD1H"
    assert assets[2]["alt"].endswith("πρόσθετη εικόνα 3")
    assert section_image_alt({"title": "Τεχνολογία AI EcoMaster"}, "κλιματιστικό Midea Solunar")[0].startswith("Τεχνολογία AI EcoMaster")
    assert section_image_alt({"decorative": True}, "Midea Solunar") == ("", "decorative", "high")


def test_distinct_description_heading() -> None:
    identity = {"family": "air_conditioner", "commercial_series": "Solunar", "btu": "12000 BTU", "verified_features": ["AI EcoMaster"], "wifi": True}
    assert description_heading(brand="Midea", identity=identity) == "Midea Solunar 12000 BTU με AI EcoMaster"
    assert description_heading(brand="Midea", identity={"family": "air_conditioner"}) == ""


def test_related_products_prefer_same_series_and_exclude_self_inactive_duplicate() -> None:
    current = {"model": "100000", "manufacturer": "Midea", "category": "Κλιματιστικά", "mpn": "A-12", "seo_identity": {"commercial_series": "Solunar", "btu": "12000 BTU"}}
    catalog = [
        current,
        {"model": "100001", "manufacturer": "Midea", "category": "Κλιματιστικά", "mpn": "A-09", "status": "1", "seo_identity": {"commercial_series": "Solunar", "btu": "9000 BTU"}},
        {"model": "100002", "manufacturer": "Midea", "category": "Κλιματιστικά", "mpn": "A-18", "status": "0", "seo_identity": {"commercial_series": "Solunar", "btu": "18000 BTU"}},
        {"model": "100001", "manufacturer": "Midea", "category": "Κλιματιστικά", "mpn": "A-09", "status": "1", "seo_identity": {"commercial_series": "Solunar", "btu": "9000 BTU"}},
    ]
    identifiers, provenance = recommend_related_products(current, catalog)
    assert identifiers == ["100001"] and provenance[0]["reason"] == "same_series"


def test_catalog_similarity_thresholds_and_phase1_compatibility() -> None:
    source = "Το κλιματιστικό προσφέρει αξιόπιστη άνεση για κάθε χώρο."
    exact = catalog_similarity(source, [{"model": "2", "intro": source}], field="intro")
    distinct = catalog_similarity(source, [{"model": "3", "intro": "Μια τελείως διαφορετική περιγραφή προϊόντος."}], field="intro")
    assert exact["band"] == "fail" and distinct["band"] == "pass"
    fields = {"brand": "Midea", "mpn": "EF-12RD1H", "category_phrase": "Κλιματιστικό", "name": "Midea EF-12RD1H Κλιματιστικό", "meta_title": "Midea EF-12RD1H Κλιματιστικό | eTranoulis", "seo_keyword_candidate": "midea-ef-12rd1h-klimatistiko", "seo_identity": {"primary_model": "EF-12RD1H"}}
    row = {"name": fields["name"], "meta_title": fields["meta_title"], "meta_description": "Midea EF-12RD1H Κλιματιστικό 12000 BTU με επιβεβαιωμένα χαρακτηριστικά για άνεση σε κάθε χώρο του σπιτιού και πρακτικό καθημερινό έλεγχο.", "seo_keyword": fields["seo_keyword_candidate"], "product_url": "https://example.test/a"}
    phase1 = evaluate_seo_health(model="123456", row=row, deterministic_product=fields)
    assert len(phase1["checks"]) == 29 and validate_seo_health_contract(phase1) == []
    full = evaluate_seo_health(model="123456", row=row, deterministic_product=fields, profile="full", phase2={"image_assets": _assets(), "internal_links": {"canonical_category": "/ac", "related_products": ["100001"]}})
    assert {check["id"] for check in full["checks"]} >= {
        "images.gallery_filename_policy",
        "internal_linking.related_and_category",
    }
    assert validate_seo_health_contract(full) == []
