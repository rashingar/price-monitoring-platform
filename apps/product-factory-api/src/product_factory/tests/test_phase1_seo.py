from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from product_factory.deterministic_fields import build_deterministic_product_fields
from product_factory.mapping import build_row, derive_seo_keyword
from product_factory.models import CLIInput, ParsedProduct, SchemaMatchResult, SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from product_factory.seo_health import CHECK_WEIGHTS, calculate_score, evaluate_seo_health, round_half_up, validate_seo_health_contract
from product_factory.seo_identity import MetaTitleComponent, compose_meta_title, lock_seo_keyword
from product_factory.validator import validate_candidate_csv


AC_TAXONOMY = TaxonomyResolution(
    parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
    leaf_category="Κλιματιστικά",
    sub_category="Τοίχου",
    gender="neut",
)


def _ac_source(*, series: str = "Solunar", mpn: str = "EF-12RD1H/MX1-12RD1H", wifi: str = "Ναι", ionizer: str = "", name: str | None = None) -> SourceProductData:
    return SourceProductData(
        source_name="skroutz",
        brand="Midea",
        mpn=mpn,
        name=name or f"Midea {series} {mpn} Κλιματιστικό Inverter 12000 BTU",
        key_specs=[
            SpecItem(label="Σειρά", value=series),
            SpecItem(label="Ισχύς Ψύξης (BTU)", value="12.000 BTU"),
            SpecItem(label="Inverter", value="Ναι"),
            SpecItem(label="Wi-Fi", value=wifi),
            SpecItem(label="Ιονιστής", value=ionizer),
        ],
        spec_sections=[
            SpecSection(
                section="Ενεργειακή Ετικέτα",
                items=[
                    SpecItem(label="Ενεργειακή Κλάση Ψύξης", value="A++"),
                    SpecItem(label="Ενεργειακή Κλάση Θέρμανσης", value="A+"),
                ],
            )
        ],
    )


def _fields(source: SourceProductData) -> dict[str, object]:
    return build_deterministic_product_fields(source, AC_TAXONOMY, "123456", derive_seo_keyword)


def test_solunar_identity_name_title_and_slug() -> None:
    fields = _fields(_ac_source())
    identity = fields["seo_identity"]

    assert identity["commercial_series"] == "Solunar"
    assert identity["set_model"] == "EF-12RD1H/MX1-12RD1H"
    assert identity["primary_model"] == "EF-12RD1H"
    assert identity["indoor_model"] == "EF-12RD1H"
    assert identity["outdoor_model"] == "MX1-12RD1H"
    assert identity["inverter"] is True
    assert identity["wifi"] is True
    assert identity["btu"] == "12000 BTU"
    assert identity["cooling_energy_class"] == "A++"
    assert identity["heating_energy_class"] == "A+"
    assert fields["name"] == "Midea Solunar EF-12RD1H/MX1-12RD1H – Κλιματιστικό Inverter 12000 BTU A++/A+ με Wi-Fi"
    assert fields["meta_title"] == "Midea Solunar EF-12RD1H Κλιματιστικό 12000 BTU | eTranoulis"
    assert fields["seo_keyword_candidate"] == "midea-solunar-ef-12rd1h-klimatistiko-12000-btu"


def test_two_word_and_named_ac_series_are_preserved() -> None:
    air_green = _fields(_ac_source(series="Air Green", mpn="AG-12IN/AG-12OUT"))
    ora = _fields(_ac_source(series="Ora", mpn="ORA-12I/ORA-12O", name="Toyotomi Ora ORA-12I/ORA-12O Κλιματιστικό 12000 BTU"))
    gosai = _fields(_ac_source(series="Gosai", mpn="GOS-12I/GOS-12O", name="Toyotomi Gosai GOS-12I/GOS-12O Κλιματιστικό 12000 BTU"))

    assert air_green["seo_identity"]["commercial_series"] == "Air Green"
    assert ora["seo_identity"]["commercial_series"] == "Ora"
    assert gosai["seo_identity"]["commercial_series"] == "Gosai"


def test_unverified_series_and_explicit_false_capabilities_are_not_invented() -> None:
    fields = _fields(
        _ac_source(
            series="Inverter",
            wifi="Όχι",
            ionizer="Δεν υποστηρίζεται",
            name="Midea EF-12RD1H/MX1-12RD1H Κλιματιστικό 12000 BTU",
        )
    )
    identity = fields["seo_identity"]

    assert identity["commercial_series"] == ""
    assert identity["wifi"] is False
    assert identity["ionizer"] is False
    assert "Wi-Fi" not in fields["name"]
    assert "Ιονιστή" not in fields["name"]


def test_ac_model_split_is_scoped_and_non_ac_slash_mpn_is_unchanged() -> None:
    ac = _fields(_ac_source())
    non_ac = build_deterministic_product_fields(
        SourceProductData(brand="Toyotomi", mpn="THMUSG416/3R32", name="Toyotomi THMUSG416/3R32 Αντλία Θερμότητας"),
        TaxonomyResolution(leaf_category="Αντλίες Θερμότητας", sub_category="Monoblock"),
        "123456",
        derive_seo_keyword,
    )

    assert ac["seo_identity"]["indoor_model"] == "EF-12RD1H"
    assert non_ac["mpn"] == "THMUSG416/3R32"
    assert "seo_identity" not in non_ac


def test_meta_title_budget_never_removes_required_identity() -> None:
    title = compose_meta_title(
        [
            MetaTitleComponent("Midea", required=True),
            MetaTitleComponent("Solunar", required=True),
            MetaTitleComponent("EF-12RD1H", required=True),
            MetaTitleComponent("Κλιματιστικό", priority=1),
            MetaTitleComponent("12000 BTU", priority=2),
            MetaTitleComponent("A++/A+", priority=3),
            MetaTitleComponent("με Wi-Fi", priority=4),
        ]
    )
    assert title == "Midea Solunar EF-12RD1H Κλιματιστικό 12000 BTU | eTranoulis"
    assert len(title) <= 65


def test_published_slug_locking_and_new_candidate() -> None:
    candidate = "midea-solunar-ef-12rd1h-klimatistiko-12000-btu"
    assert lock_seo_keyword(candidate) == (candidate, False)
    assert lock_seo_keyword(candidate, "existing-product-slug") == ("existing-product-slug", True)


def test_empty_meta_keywords_do_not_fail_csv_validation(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.csv"
    candidate.write_text(
        "model,mpn,name,description,characteristics,category,image,manufacturer,price,meta_keyword,meta_title,meta_description,seo_keyword,product_url\n"
        "123456,EF-12RD1H,Name,Description,Characteristics,Category,image.jpg,Midea,0,,Midea EF-12RD1H | eTranoulis,Meta description.,midea-ef-12rd1h,https://example.test/midea-ef-12rd1h\n",
        encoding="utf-8",
    )
    assert validate_candidate_csv(candidate, template_path=candidate)["ok"] is True


def test_build_row_locks_an_existing_published_slug() -> None:
    source = _ac_source()
    row, normalized, _ = build_row(
        CLIInput(model="123456", url="https://example.test/ac"),
        ParsedProduct(source=source),
        AC_TAXONOMY,
        SchemaMatchResult(),
        published_seo_keyword="midea-solunar-existing",
    )
    assert row["seo_keyword"] == "midea-solunar-existing"
    assert normalized["deterministic_product"]["seo_keyword_locked"] is True
    assert normalized["deterministic_product"]["seo_keyword_candidate"] == "midea-solunar-ef-12rd1h-klimatistiko-12000-btu"


def test_meta_description_length_bands_and_unsupported_numeric_claims() -> None:
    fields = _fields(_ac_source())
    base_row = {
        "name": fields["name"], "meta_title": fields["meta_title"],
        "seo_keyword": fields["seo_keyword"], "product_url": "https://example.test/ac",
    }

    def description(length: int, *, btu: str = "12000") -> str:
        prefix = f"Midea Solunar κλιματιστικό {btu} BTU A++ Inverter Wi-Fi "
        return prefix + ("α" * (length - len(prefix) - 1)) + "."

    statuses = []
    for length in (130, 110, 109, 181):
        report = evaluate_seo_health(
            model="123456", row={**base_row, "meta_description": description(length)}, deterministic_product=fields
        )
        statuses.append(next(check["status"] for check in report["checks"] if check["id"] == "meta_description.length"))
    assert statuses == ["pass", "warn", "fail", "fail"]
    unsupported = evaluate_seo_health(
        model="123456", row={**base_row, "meta_description": description(130, btu="99999")}, deterministic_product=fields
    )
    numeric_check = next(check for check in unsupported["checks"] if check["id"] == "meta_description.no_unsupported_numeric_claims")
    assert numeric_check["status"] == "fail"
    assert "99999" in numeric_check["observed"]


def test_meta_description_accepts_numeric_claim_in_verified_hero_summary() -> None:
    source = _ac_source()
    source.hero_summary = "Self Clean 56°C με προεγκατεστημένο Wi-Fi."
    fields = _fields(source)
    row = {
        "name": fields["name"],
        "meta_title": fields["meta_title"],
        "seo_keyword": fields["seo_keyword"],
        "product_url": "https://example.test/ac",
        "meta_description": "Το Midea Solunar είναι κλιματιστικό 12000 BTU με A++ στην ψύξη, Inverter, Wi-Fi και λειτουργία Self Clean 56°C για άνεση κάθε ημέρα.",
    }
    report = evaluate_seo_health(model="123456", row=row, deterministic_product=fields)
    numeric_check = next(check for check in report["checks"] if check["id"] == "meta_description.no_unsupported_numeric_claims")
    assert "56" in fields["seo_identity"]["numeric_evidence"]
    assert numeric_check["status"] == "pass"


def test_all_seo_health_statuses_scoring_and_rounding() -> None:
    checks = [
        {"weight": 1, "status": "pass", "earned_points": 1},
        {"weight": 1, "status": "warn", "earned_points": 0.5},
        {"weight": 1, "status": "fail", "earned_points": 0},
        {"weight": 1, "status": "not_applicable", "earned_points": 0},
        {"weight": 1, "status": "not_run", "earned_points": 0},
    ]
    score = calculate_score(checks)
    assert score["score"] == 50
    assert score["coverage"]["percentage"] == 80
    assert score["summary"]["not_applicable"] == 1
    assert score["summary"]["not_run"] == 1
    assert round_half_up(Decimal("12.5")) == 13
    assert round_half_up(Decimal("12.4")) == 12
    assert sum(weight for _, _, weight in CHECK_WEIGHTS) == 100


def test_seo_health_enforcement_modes_and_schema() -> None:
    source = _ac_source()
    fields = _fields(source)
    row, normalized, _ = build_row(
        CLIInput(model="123456", url="https://example.test/ac"),
        ParsedProduct(source=source),
        AC_TAXONOMY,
        SchemaMatchResult(),
        llm_product={"meta_description": "Το Midea Solunar είναι κλιματιστικό 12000 BTU με A++ στην ψύξη, Inverter και Wi-Fi για άνετο έλεγχο κάθε ημέρα.", "meta_keywords": []},
    )
    assert row["meta_keyword"] == ""
    report = evaluate_seo_health(
        model="123456",
        row=row,
        deterministic_product={**fields, "llm_product": normalized["llm_product"]},
        settings={"enforcement_mode": "strict", "thresholds": {"minimum_score": 80, "minimum_coverage": 100, "blocking_failures_must_be_zero": True}},
    )
    schema_path = Path(__file__).parents[3] / "docs" / "contracts" / "seo_health.schema.json"
    assert '"$schema": "https://json-schema.org/draft/2020-12/schema"' in schema_path.read_text(encoding="utf-8")
    assert validate_seo_health_contract(report) == []
    assert report["publish_gate"]["enforcement_mode"] == "strict"
    assert report["publish_gate"]["enforced_allowed"] == report["publish_gate"]["recommended_allowed"]

    blocked_row = {**row, "meta_description": ""}
    modes = {
        mode: evaluate_seo_health(model="123456", row=blocked_row, deterministic_product=fields, settings={"enforcement_mode": mode})
        for mode in ("report_only", "blockers_only", "strict")
    }
    assert modes["report_only"]["publish_gate"]["enforced_allowed"] is True
    assert modes["blockers_only"]["publish_gate"]["enforced_allowed"] is False
    assert modes["strict"]["publish_gate"]["enforced_allowed"] is False


def test_non_ac_output_remains_on_existing_deterministic_path() -> None:
    source = SourceProductData(
        brand="LG",
        mpn="GSGV80PYLL",
        name="LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt",
        key_specs=[SpecItem(label="Χωρητικότητα", value="635 Lt")],
    )
    fields = build_deterministic_product_fields(
        source,
        TaxonomyResolution(leaf_category="Ψυγεία Ντουλάπες", sub_category="Ψυγεία Ντουλάπες"),
        "123456",
        derive_seo_keyword,
    )
    assert fields["name"] == "LG GSGV80PYLL – Ψυγείο Ντουλάπα 635Lt"
    assert "seo_identity" not in fields


def test_tv_and_cooker_continue_to_use_existing_output_profiles() -> None:
    tv = build_deterministic_product_fields(
        SourceProductData(brand="TCL", mpn="43P6K", name="TCL 43P6K Τηλεόραση 43", key_specs=[SpecItem(label="Διαγώνιος", value="43")]),
        TaxonomyResolution(leaf_category="Τηλεοράσεις", sub_category="40''-43''"), "123456", derive_seo_keyword,
    )
    cooker = build_deterministic_product_fields(
        SourceProductData(brand="Bosch", mpn="HBA514BS3", name="Bosch HBA514BS3 Φούρνος", key_specs=[SpecItem(label="Χωρητικότητα Φούρνου", value="71 Lt")]),
        TaxonomyResolution(leaf_category="Φούρνοι", sub_category="Εντοιχιζόμενοι"), "123456", derive_seo_keyword,
    )
    assert tv["name"].startswith("TCL 43P6K")
    assert cooker["name"].startswith("Bosch HBA514BS3")
    assert "seo_identity" not in tv and "seo_identity" not in cooker
