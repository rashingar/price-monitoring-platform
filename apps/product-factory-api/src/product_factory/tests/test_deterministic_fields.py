from product_factory.deterministic_fields import (
    _build_preferred_spec_lookup,
    apply_name_rule,
    build_deterministic_product_fields,
    compose_name,
    is_dimension_model_token,
    resolve_name_rule_component,
)
from product_factory.mapping import derive_seo_keyword
from product_factory.models import (
    SourceProductData,
    SpecItem,
    SpecSection,
    TaxonomyResolution,
)


def test_skroutz_ironing_board_uses_source_mpn_and_dimensions_name_schema() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Afer",
        product_code="2062",
        mpn="2062",
        name="Afer Homie Pro Σιδερώστρα για Σύστημα Σιδερώματος Σπαστή Γκρι 124x40x95cm",
        key_specs=[
            SpecItem(label="Κωδικός Προϊόντος", value="2062"),
            SpecItem(label="Τύπος Σιδερώστρας", value="Για Σύστημα Σιδερώματος"),
            SpecItem(label="Είδος", value="Σπαστή"),
            SpecItem(label="Μήκος Ανοιχτής", value="124 cm"),
            SpecItem(label="Πλάτος Ανοιχτής", value="40 cm"),
            SpecItem(label="Ύψος", value="95 cm"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σιδέρωμα",
        sub_category="Σιδερώστρες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "328984", derive_seo_keyword
    )

    assert is_dimension_model_token("124X40X95CM")
    assert fields["mpn"] == "2062"
    assert fields["name"] == "Afer 2062 – Σιδερώστρα Homie Pro 124x40x95cm Γκρι"
    assert (
        fields["meta_title"]
        == "Afer 2062 Σιδερώστρα Homie Pro 124x40x95cm Γκρι | eTranoulis"
    )
    assert fields["seo_keyword"] == "afer-2062-siderostra-homie-pro-124x40x95cm-gkri"


def test_skroutz_fridge_freezer_uses_requested_name_schema() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Bosch",
        mpn="KGN36NLEA",
        name="Bosch Ψυγειοκαταψύκτης 305lt Total NoFrost Υ186xΠ60xΒ66εκ. Metal Look KGN36NLEA",
        key_specs=[
            SpecItem(label="Σύστημα Ψύξης", value="Total NoFrost"),
            SpecItem(label="Συνολική Χωρητικότητα", value="305 lt"),
            SpecItem(label="Χρώμα", value="Inox"),
        ],
        spec_sections=[
            SpecSection(
                section="Νέα Ενεργειακή Ετικέτα",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="E")],
            ),
            SpecSection(
                section="Διαστάσεις", items=[SpecItem(label="Πλάτος", value="60 cm")]
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Ψυγεία & Καταψύκτες",
        sub_category="Ψυγειοκαταψύκτες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "229957", derive_seo_keyword
    )

    assert fields["name"] == "Bosch KGN36NLEA – Ψυγειοκαταψύκτης Total No Frost 305Lt E"
    assert (
        fields["meta_title"]
        == "Bosch KGN36NLEA Ψυγειοκαταψύκτης Total No Frost 305Lt | eTranoulis"
    )
    assert (
        fields["seo_keyword"]
        == "bosch-kgn36nlea-psygeiokatapsyktis-total-no-frost-305lt-e"
    )


def test_skroutz_air_conditioner_uses_compact_requested_name_schema() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Toyotomi",
        mpn="OTN/OTG-24QINV",
        name="Toyotomi Ora Κλιματιστικό Inverter 24000 BTU A++/A+ με Ιονιστή και WiFi",
        key_specs=[
            SpecItem(label="Απόδοση (BTU)", value="24000 BTU"),
            SpecItem(label="Ιονιστής", value="Ναι"),
        ],
        spec_sections=[
            SpecSection(
                section="Ενεργειακή Κλάση",
                items=[
                    SpecItem(label="Ψύξης", value="A++"),
                    SpecItem(label="Θέρμανσης (Μέση Ζώνη)", value="A+"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "414833", derive_seo_keyword
    )

    assert (
        fields["name"]
        == "Toyotomi OTN/OTG-24QINV – Κλιματιστικό 24000 BTU A++/A+ με Ιονιστή"
    )
    assert (
        fields["meta_title"]
        == "Toyotomi OTN/OTG-24QINV Κλιματιστικό 24000 BTU A++/A+ | eTranoulis"
    )
    assert (
        fields["seo_keyword"]
        == "toyotomi-otn-otg-24qinv-klimatistiko-24000-btu-a-a-me-ionisti"
    )


def test_skroutz_air_conditioner_omits_ionizer_when_not_supported() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Toyotomi",
        mpn="GTN/GTG-18CMW",
        name="Toyotomi Gosai Κλιματιστικό Inverter 18000 BTU A+++/A++ με WiFi",
        key_specs=[SpecItem(label="Απόδοση (BTU)", value="18000 BTU")],
        spec_sections=[
            SpecSection(
                section="Ενεργειακή Κλάση",
                items=[
                    SpecItem(label="Ψύξης", value="A+++"),
                    SpecItem(label="Θέρμανσης (Μέση Ζώνη)", value="A++"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[SpecItem(label="Ιονιστής", value="Όχι")],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "415899", derive_seo_keyword
    )

    assert fields["name"] == "Toyotomi GTN/GTG-18CMW – Κλιματιστικό 18000 BTU A+++/A++"
    assert (
        fields["meta_title"]
        == "Toyotomi GTN/GTG-18CMW Κλιματιστικό 18000 BTU A+++/A++ | eTranoulis"
    )
    assert fields["seo_keyword"] == "toyotomi-gtn-gtg-18cmw-klimatistiko-18000-btu-a-a"


def test_compose_name_collapses_category_prefixed_first_differentiator() -> None:
    name = compose_name("Bosch", "HBA514BS3", "Φούρνος", ["Φούρνος ηλεκτρικός", "71Lt"])

    assert name == "Bosch HBA514BS3 – Φούρνος ηλεκτρικός 71Lt"


def test_tv_name_uses_size_resolution_panel_and_concrete_platform() -> None:
    source = SourceProductData(
        source_name="electronet",
        brand="TCL",
        mpn="43P6K",
        name="TV TCL 43P6K 43'' Smart 4K",
        hero_summary="Τηλεόραση 43'' Smart 4K με Google TV, HDR10+ και AiPQ επεξεργαστή",
        key_specs=[
            SpecItem(label="Τεχνολογία Οθόνης", value="LED"),
        ],
        spec_sections=[
            SpecSection(
                section="Εικόνα - Ήχος",
                items=[
                    SpecItem(label="Διαγώνιος Οθόνης ( Ίντσες )", value="43"),
                    SpecItem(label="Ανάλυση Οθόνης", value="ULTRA HD ( 4K )"),
                ],
            ),
            SpecSection(
                section="Λειτουργίες",
                items=[
                    SpecItem(label="Λειτουργικό Σύστημα", value="Android TV"),
                    SpecItem(
                        label="Λειτουργίες Smart", value="Google Assistant,Google TV"
                    ),
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="33''-50''",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "142659", derive_seo_keyword
    )

    assert fields["name"] == 'TCL 43P6K – Τηλεόραση 43" 4K UHD LED Google TV'
    assert fields["name_differentiators"] == ['43"', "4K UHD", "LED", "Google TV"]
    assert fields["meta_title"] == 'TCL 43P6K Τηλεόραση 43" 4K UHD | eTranoulis'
    assert fields["seo_keyword"] == "tcl-43p6k-tileorasi-43-4k-uhd-led-google-tv"


def test_tv_name_uses_smart_tv_only_when_no_specific_platform_exists() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Kydos",
        mpn="K32NH22CD02",
        name='Kydos Τηλεόραση LED 32" HD Ready',
        key_specs=[
            SpecItem(label="Τεχνολογία Οθόνης", value="LED"),
            SpecItem(label="Διαγώνιος", value='32 "'),
            SpecItem(label="Ευκρίνεια", value="HD Ready"),
        ],
        spec_sections=[
            SpecSection(
                section="Λειτουργίες",
                items=[SpecItem(label="Smart TV", value="Υποστηρίζεται")],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="Έως 32''",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "141435", derive_seo_keyword
    )

    assert fields["name"] == 'Kydos K32NH22CD02 – Τηλεόραση 32" HD Ready LED Smart TV'
    assert fields["name_differentiators"] == ['32"', "HD Ready", "LED", "Smart TV"]


def test_electronet_emagie_cooker_uses_specific_name_schema_and_primary_color() -> None:
    source = SourceProductData(
        source_name="electronet",
        brand="Eskimo",
        mpn="EM5070W",
        name="Κουζίνα Εμαγιέ Eskimo ES EM5070W Λευκή Α",
        key_specs=[
            SpecItem(
                label="Τύπος Συσκευής", value="Ηλεκτρική κουζίνα με εμαγιέ εστίες"
            ),
            SpecItem(label="Χωρητικότητα Φούρνου σε Λίτρα", value="60"),
            SpecItem(label="Τύπος Εστίας", value="Εμαγιέ βάση με 4 ηλεκτρικές εστίες"),
            SpecItem(label="Ενεργειακή Κλάση", value="A"),
            SpecItem(label="Χρώμα", value="Λευκό,Μαύρο"),
            SpecItem(label="Πλάτος Συσκευής σε Εκατοστά", value="59,8"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Κουζίνες",
        sub_category="Κουζίνες Εμαγιέ",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "233859", derive_seo_keyword
    )

    assert (
        fields["name"]
        == "Eskimo EM5070W – Ηλεκτρική κουζίνα με εμαγιέ εστίες 59,8cm Λευκό 60Lt A"
    )
    assert (
        fields["meta_title"]
        == "Eskimo EM5070W Ηλεκτρική κουζίνα με εμαγιέ εστίες 59,8cm Λευκό | eTranoulis"
    )
    assert (
        fields["seo_keyword"]
        == "eskimo-em5070w-ilektriki-kouzina-me-emagie-esties-598cm-leyko-60lt-a"
    )


def test_electronet_built_in_oven_capacity_alias_keeps_liter_unit() -> None:
    source = SourceProductData(
        source_name="electronet",
        brand="Bosch",
        mpn="HBA514BS3",
        name="Φούρνος Εντοιχιζόμενος Bosch HBA514BS3",
        key_specs=[
            SpecItem(label="Τύπος Φούρνου", value="Φούρνος ηλεκτρικός"),
            SpecItem(label="Χωρητικότητα Φούρνου σε Λίτρα", value="71"),
            SpecItem(label="Ενεργειακή Κλάση", value="A+"),
            SpecItem(label="Χρώμα", value="Inox"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Φούρνοι",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "234070", derive_seo_keyword
    )

    assert fields["name"] == "Bosch HBA514BS3 – Φούρνος ηλεκτρικός 71Lt A+ Inox"
    assert (
        fields["meta_title"] == "Bosch HBA514BS3 Φούρνος ηλεκτρικός 71Lt | eTranoulis"
    )
    assert fields["seo_keyword"] == "bosch-hba514bs3-fournos-ilektrikos-71lt-a-inox"


def test_deterministic_name_and_meta_title_follow_business_rules() -> None:
    source = SourceProductData(
        brand="LG",
        mpn="GSGV80PYLL",
        name="Ψυγείο Ντουλάπα LG GSGV80PYLL Ασημί E",
        key_specs=[
            SpecItem(label="Συνολική Καθαρή Χωρητικότητα", value="635"),
            SpecItem(label="Τεχνολογία Ψύξης", value="Total No Frost"),
            SpecItem(label="Συνδεσιμότητα", value="WiFi"),
        ],
        spec_sections=[
            SpecSection(
                section="Ενεργειακά χαρακτηριστικά",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="E")],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Ψυγεία & Καταψύκτες",
        sub_category="Ψυγεία Ντουλάπες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "233541", derive_seo_keyword
    )

    assert fields["name"] == "LG GSGV80PYLL – Ψυγείο Ντουλάπα Total No Frost 635Lt E"
    assert (
        fields["meta_title"]
        == "LG GSGV80PYLL Ψυγείο Ντουλάπα Total No Frost 635Lt | eTranoulis"
    )
    assert (
        fields["seo_keyword"] == "lg-gsgv80pyll-psygeio-ntoulapa-total-no-frost-635lt-e"
    )


def test_fridge_cabinet_subcategory_owns_category_phrase() -> None:
    source = SourceProductData(
        brand="Bosch",
        mpn="KFN96AXEA",
        name="Ψυγείο Bosch KFN96AXEA No Frost E",
        key_specs=[
            SpecItem(label="Συνολική Καθαρή Χωρητικότητα", value="605"),
            SpecItem(label="Τεχνολογία Ψύξης", value="No Frost"),
        ],
        spec_sections=[
            SpecSection(
                section="Ενεργειακά χαρακτηριστικά",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="E")],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Ψυγεία & Καταψύκτες",
        sub_category="Ψυγεία Ντουλάπες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "231025", derive_seo_keyword
    )

    assert fields["name"] == "Bosch KFN96AXEA – Ψυγείο Ντουλάπα No Frost 605Lt E"
    assert (
        fields["meta_title"]
        == "Bosch KFN96AXEA Ψυγείο Ντουλάπα No Frost 605Lt | eTranoulis"
    )
    assert fields["seo_keyword"] == "bosch-kfn96axea-psygeio-ntoulapa-no-frost-605lt-e"


def test_color_rule_recovers_title_color_and_omits_irrelevant_type_value() -> None:
    source = SourceProductData(
        brand="Rohnson",
        mpn="R-2116",
        name="Τοστιέρα Rohnson MOD R-2116 Γκρι",
        key_specs=[
            SpecItem(label="Τύπος Συσκευής", value="Τοστιέρα"),
            SpecItem(label="Χρώμα", value=None),
            SpecItem(label="Ισχύς σε Watts", value="1500"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Τοστιέρες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "340864", derive_seo_keyword
    )

    assert fields["name"] == "Rohnson R-2116 – Τοστιέρα 1500W Γκρι"
    assert fields["meta_title"] == "Rohnson R-2116 Τοστιέρα 1500W Γκρι | eTranoulis"
    assert fields["seo_keyword"] == "rohnson-r-2116-tostiera-1500w-gkri"


def test_color_rule_omits_missing_color_after_recovery_attempt() -> None:
    source = SourceProductData(
        brand="Rohnson",
        mpn="R-2116",
        name="Τοστιέρα Rohnson MOD R-2116",
        key_specs=[
            SpecItem(label="Τύπος Συσκευής", value="Τοστιέρα"),
            SpecItem(label="Χρώμα", value=None),
            SpecItem(label="Ισχύς σε Watts", value="1500"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Τοστιέρες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "340864", derive_seo_keyword
    )

    assert fields["name"] == "Rohnson R-2116 – Τοστιέρα 1500W"
    assert fields["meta_title"] == "Rohnson R-2116 Τοστιέρα 1500W | eTranoulis"
    assert fields["seo_keyword"] == "rohnson-r-2116-tostiera-1500w"


def test_kettle_rule_uses_single_capacity_differentiator() -> None:
    source = SourceProductData(
        brand="Rohnson",
        mpn="R-7616",
        name="Βραστήρας Rohnson MOD R-7616 1.7lt Inox",
        key_specs=[
            SpecItem(label="Χωρητικότητα σε Λίτρα", value="1,7"),
            SpecItem(label="Ισχύς σε Watts", value="2200"),
            SpecItem(label="Χρώμα", value="Inox"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Συσκευές Κουζίνας",
        sub_category="Βραστήρες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "344347", derive_seo_keyword
    )

    assert fields["name"] == "Rohnson R-7616 – Βραστήρας 1,7Lt 2200W Inox"
    assert fields["meta_title"] == "Rohnson R-7616 Βραστήρας 1,7Lt 2200W | eTranoulis"
    assert fields["seo_keyword"] == "rohnson-r-7616-vrastiras-17lt-2200w-inox"


def test_kettle_rule_keeps_explicit_skroutz_mpn_when_title_contains_capacity_token() -> (
    None
):
    source = SourceProductData(
        source_name="skroutz",
        brand="Estia",
        product_code="06-24567",
        mpn="06-24567",
        name="Estia Intense Βραστήρας 1.7lt 2200W Luminus Mat",
        key_specs=[
            SpecItem(label="Χωρητικότητα σε Λίτρα", value="1,7"),
            SpecItem(label="Ισχύς σε Watts", value="2200"),
            SpecItem(label="Χρώμα", value="Λευκό"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Συσκευές Κουζίνας",
        sub_category="Βραστήρες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "341490", derive_seo_keyword
    )

    assert fields["mpn"] == "06-24567"
    assert fields["name"] == "Estia 06-24567 – Βραστήρας 1,7Lt 2200W Λευκό Ματ"
    assert fields["seo_keyword"] == "estia-06-24567-vrastiras-1-7lt-2200w-luminus-mat"


def test_egg_boiler_uses_specific_kettle_category_phrase() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Philips",
        mpn="HD9137/90",
        name="Philips Βραστήρας Αυγών 6 Θέσεων 400W Μαύρος",
        key_specs=[
            SpecItem(label="Ισχύς", value="400 W"),
            SpecItem(label="Χρώμα", value="Μαύρο"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Συσκευές Κουζίνας",
        sub_category="Βραστήρες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "340144", derive_seo_keyword
    )

    assert fields["name"] == "Philips HD9137/90 – Βραστήρας Αυγών 400W Μαύρο"
    assert (
        fields["meta_title"]
        == "Philips HD9137/90 Βραστήρας Αυγών 400W Μαύρο | eTranoulis"
    )
    assert (
        fields["seo_keyword"]
        == "philips-hd9137-90-vrastiras-aygon-6-theseon-400w-mayros"
    )


def test_deterministic_fields_rebuild_name_from_schema_with_title_family_and_color() -> (
    None
):
    source = SourceProductData(
        brand="Rowenta",
        mpn="RH2099",
        name="Σκούπα Stick Rowenta X-Force Flex 9.60 RH2099 Κόκκινο",
        key_specs=[
            SpecItem(label="Τάση Volt", value="18,5"),
            SpecItem(label="Χρόνος Λειτουργίας σε Λεπτά", value="45"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκούπες Stick",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "343700", derive_seo_keyword
    )

    assert fields["preserve_parsed_title"] is False
    assert fields["name"] == "Rowenta RH2099 – Σκούπα Stick X-Force Flex 9.60 Κόκκινο"
    assert (
        fields["meta_title"]
        == "Rowenta RH2099 Σκούπα Stick X-Force Flex 9.60 Κόκκινο | eTranoulis"
    )
    assert (
        fields["seo_keyword"] == "rowenta-rh2099-skoupa-stick-x-force-flex-960-kokkino"
    )


def test_deterministic_fields_keep_family_and_color_for_small_appliances() -> None:
    source = SourceProductData(
        brand="Tefal",
        mpn="DN853B",
        name="Πολυκόπτης Tefal Fresh Express DN853B Γκρι",
        key_specs=[
            SpecItem(label="Τύπος Πολυκόπτη", value="Κοπτήριο άμεσου σερβιρίσματος"),
            SpecItem(label="Ισχύς σε Watts", value="150"),
            SpecItem(label="Χρώμα", value="Γκρι"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Συσκευές Κουζίνας",
        sub_category="Κοπτήρια-Ράβδοι",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "344424", derive_seo_keyword
    )

    assert fields["name"] == "Tefal DN853B – Πολυκόπτης Fresh Express Γκρι"
    assert (
        fields["meta_title"]
        == "Tefal DN853B Πολυκόπτης Fresh Express Γκρι | eTranoulis"
    )
    assert fields["seo_keyword"] == "tefal-dn853b-polykoptis-fresh-express-gkri"


def test_deterministic_fields_never_use_product_code_as_mpn_and_extract_unicode_model() -> (
    None
):
    source = SourceProductData(
        source_name="electronet",
        brand="Tefal",
        product_code="339576",
        mpn="339576",
        name="Αποχυμωτής Tefal Frutelia + ΖΕ3701 Λευκό",
        key_specs=[
            SpecItem(label="Ισχύς σε Watts", value="350"),
            SpecItem(label="Στόμιο Τροφοδοσίας Ø σε Χιλιοστά", value="60"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Καφές-Ροφήματα-Χυμοί",
        sub_category="Αποχυμωτές",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "339576", derive_seo_keyword
    )

    assert fields["mpn"] == "ΖΕ3701"
    assert fields["name"] == "Tefal ΖΕ3701 – Αποχυμωτής Frutelia + Λευκό"
    assert fields["seo_keyword"] == "tefal-ze3701-apochymotis-frutelia-leyko"
    assert "339576" not in fields["name"]


def test_deterministic_fields_rejects_mismatched_product_code_as_mpn() -> None:
    source = SourceProductData(
        source_name="electronet",
        brand="Tefal",
        product_code="654321",
        mpn="654321",
        name="Αποχυμωτής Tefal Frutelia + ΖΕ3701 Λευκό",
        key_specs=[
            SpecItem(label="Ισχύς σε Watts", value="350"),
            SpecItem(label="Στόμιο Τροφοδοσίας Ø σε Χιλιοστά", value="60"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Καφές-Ροφήματα-Χυμοί",
        sub_category="Αποχυμωτές",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "123456", derive_seo_keyword
    )

    assert fields["mpn"] == "ΖΕ3701"
    assert fields["name"] == "Tefal ΖΕ3701 – Αποχυμωτής Frutelia + Λευκό"
    assert "654321" not in fields["name"]
    assert "123456" not in fields["name"]


def test_deterministic_fields_extract_spaced_mpn_and_do_not_inject_specs_into_complete_title() -> (
    None
):
    source = SourceProductData(
        source_name="electronet",
        brand="Miele",
        product_code="226826",
        mpn="226826",
        name="Εστία Κεραμική Miele KM 6520 FR",
        key_specs=[
            SpecItem(
                label="Τεχνολογία Πλατώ Εστιών", value="Αυτόνομο κεραμικό ηλεκτρικό"
            ),
            SpecItem(
                label="Αριθμός Ζωνών", value="5 ηλεκτρικές (4+1 διπλού δακτυλίου)"
            ),
        ],
        spec_sections=[
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(
                        label="Πλάτος Διάστασης Εντοιχισμού σε Εκατοστά", value="56,00"
                    )
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Εστίες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "226826", derive_seo_keyword
    )

    assert fields["mpn"] == "KM 6520 FR"
    assert fields["name"] == "Miele KM 6520 FR – Εστία Κεραμική"
    assert fields["name_differentiators"] == []
    assert fields["seo_keyword"] == "miele-km-6520-fr-estia-keramiki"
    assert "226826" not in fields["name"]


def test_smartphone_name_uses_mobile_model_and_specs_not_storage_as_mpn() -> None:
    source = SourceProductData(
        source_name="electronet",
        brand="POCO",
        product_code="580852",
        mpn="8GB/256GB",
        name="Smartphone Poco M8 5G 8GB/256GB Green",
        key_specs=[
            SpecItem(label="Μνήμη Ram", value="8 GB"),
            SpecItem(label="Εσωτερική Μνήμη", value="256GB"),
            SpecItem(label="5G", value="Υποστηρίζεται"),
        ],
        spec_sections=[
            SpecSection(
                section="Γενικά", items=[SpecItem(label="Χρώμα", value="Green")]
            ),
            SpecSection(
                section="Εξοπλισμός",
                items=[
                    SpecItem(
                        label="Επιπλέον Εξοπλισμός", value="Καλώδιο Type-C σε USB-A"
                    )
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΤΗΛΕΦΩΝΙΑ",
        leaf_category="Smartphones",
        sub_category="Android",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "580852", derive_seo_keyword
    )

    assert fields["mpn"] == "M8"
    assert fields["name"] == "POCO M8 – Smartphone 5G 8 GB 256 GB Green"
    assert fields["name_differentiators"] == ["5G", "8 GB 256 GB", "Green"]
    assert "Type-C" not in fields["name"]


def test_smartphone_name_keeps_manufacturer_and_subbrand_model() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Xiaomi",
        product_code="65005733",
        mpn="8/256GB",
        name="Xiaomi Poco M8 5G Dual SIM (8/256GB) Πράσινο",
        key_specs=[
            SpecItem(label="Μνήμη Ram", value="8 GB"),
            SpecItem(label="Εσωτερική Μνήμη", value="256 GB"),
            SpecItem(label="5G", value="Ναι"),
        ],
        spec_sections=[
            SpecSection(
                section="Γενικά", items=[SpecItem(label="Χρώμα", value="Πράσινο")]
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΤΗΛΕΦΩΝΙΑ",
        leaf_category="Smartphones",
        sub_category="Android",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "580852", derive_seo_keyword
    )

    assert fields["manufacturer"] == "Xiaomi"
    assert fields["mpn"] == "Poco M8"
    assert fields["name"] == "Xiaomi Poco M8 – Smartphone 5G 8 GB 256 GB Πράσινο"


def test_smartphone_name_prefers_verified_source_mpn_over_title_model_family() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Xiaomi",
        product_code="65005733",
        mpn="MZB0MA8EU",
        name="Xiaomi Poco M8 5G Dual SIM (8/256GB) Πράσινο",
        key_specs=[
            SpecItem(label="Μνήμη Ram", value="8 GB"),
            SpecItem(label="Εσωτερική Μνήμη", value="256 GB"),
            SpecItem(label="5G", value="Ναι"),
        ],
        spec_sections=[
            SpecSection(
                section="Γενικά", items=[SpecItem(label="Χρώμα", value="Πράσινο")]
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΤΗΛΕΦΩΝΙΑ",
        leaf_category="Smartphones",
        sub_category="Android",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "000009", derive_seo_keyword
    )

    assert fields["manufacturer"] == "Xiaomi"
    assert fields["mpn"] == "MZB0MA8EU"
    assert fields["name"].startswith("Xiaomi MZB0MA8EU")
    assert "Poco M8" not in fields["name"]
    assert "5G" in fields["name"]
    assert "8 GB 256 GB" in fields["name"]


def test_deterministic_fields_use_capacity_and_energy_for_dryers() -> None:
    source = SourceProductData(
        brand="LG",
        mpn="RHX5009TWB",
        name="Στεγνωτήριο ρούχων LG RHX5009TWB 9 kg B",
        key_specs=[
            SpecItem(label="Χωρητικότητα Στεγνώματος", value="9 κιλά"),
            SpecItem(label="Τεχνολογία Στεγνώματος", value="Αντλίας θερμότητας"),
            SpecItem(label="Χρώμα", value="Λευκό"),
        ],
        spec_sections=[
            SpecSection(
                section="Ενεργειακά Χαρακτηριστικά",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="B")],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Πλυντήρια-Στεγνωτήρια",
        sub_category="Στεγνωτήρια Ρούχων",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "235370", derive_seo_keyword
    )

    assert fields["name"] == "LG RHX5009TWB – Στεγνωτήριο ρούχων 9kg B"
    assert fields["meta_title"] == "LG RHX5009TWB Στεγνωτήριο ρούχων 9kg B | eTranoulis"
    assert fields["seo_keyword"] == "lg-rhx5009twb-stegnotirio-rouchon-9kg-b"


def test_deterministic_fields_compact_voltage_differentiator_for_handheld_vacuums() -> (
    None
):
    source = SourceProductData(
        source_name="electronet",
        brand="Black&Decker",
        mpn="PV1820L-QW",
        name="Σκουπάκι Black & Decker Dustbuster Pivot PV1820L-QW 18 Volt",
        key_specs=[
            SpecItem(label="Τάση Volt", value="18,00"),
            SpecItem(label="Χρώμα", value="Ανθρακί"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκουπάκια",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "331566", derive_seo_keyword
    )

    assert fields["name"] == "Black&Decker PV1820L-QW – Σκουπάκι 18V Ανθρακί"
    assert (
        fields["meta_title"]
        == "Black&Decker PV1820L-QW Σκουπάκι 18V Ανθρακί | eTranoulis"
    )
    assert (
        fields["meta_description_draft"]
        == "Το Black&Decker PV1820L-QW είναι Σκουπάκι με 18V, Ανθρακί."
    )
    assert fields["seo_keyword"] == "black-decker-pv1820l-qw-skoupaki-18v-anthraki"


def test_resolve_name_rule_component_prefers_partial_spec_label_match_before_title_fallback() -> (
    None
):
    source = SourceProductData(
        source_name="electronet",
        brand="Black&Decker",
        mpn="PV1820L-QW",
        name="Σκουπάκι Black & Decker Dustbuster Pivot PV1820L-QW 18 Volt",
        key_specs=[SpecItem(label="Τάση Volt", value="18,00")],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκουπάκια",
    )

    resolved = resolve_name_rule_component(
        source,
        _build_preferred_spec_lookup(source),
        ["Τάση", "Volt", "V"],
        "Σκουπάκι",
        taxonomy,
    )

    assert resolved.source == "fuzzy_spec"
    assert resolved.matched_label == "ταση volt"
    assert resolved.value == "18V"


def test_resolve_name_rule_component_compacts_power_and_dimensions_from_partial_labels() -> (
    None
):
    source = SourceProductData(
        brand="Example",
        mpn="ABC123",
        name="Παράδειγμα προϊόντος",
        key_specs=[
            SpecItem(label="Ισχύς σε Watts", value="1200"),
            SpecItem(label="Πλάτος σε cm", value="60"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Συσκευές Κουζίνας",
        sub_category="Μπλέντερ",
    )
    spec_lookup = _build_preferred_spec_lookup(source)

    power = resolve_name_rule_component(
        source, spec_lookup, ["Ισχύς", "Ισχύς σε Watt", "Watt"], "Μπλέντερ", taxonomy
    )
    width = resolve_name_rule_component(
        source, spec_lookup, ["Πλάτος", "Πλάτος σε cm"], "Μπλέντερ", taxonomy
    )

    assert power.value == "1200W"
    assert width.value == "60cm"


def test_resolve_name_rule_component_does_not_fuzzy_match_generic_type_alias_to_unrelated_spec() -> (
    None
):
    source = SourceProductData(
        brand="Black&Decker",
        mpn="PV1820L-QW",
        name="Σκουπάκι Black & Decker Dustbuster Pivot PV1820L-QW 18 Volt",
        key_specs=[SpecItem(label="Τύπος Μπαταρίας", value="Λιθίου")],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκουπάκια",
    )

    resolved = resolve_name_rule_component(
        source,
        _build_preferred_spec_lookup(source),
        ["Τύπος", "Χειρός"],
        "Σκουπάκι",
        taxonomy,
    )

    assert resolved.value == ""


def test_skroutz_name_prefers_manufacturer_evidence_when_specs_conflict() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Bosch",
        mpn="KGN36NLEA",
        name="Bosch Ψυγειοκαταψύκτης KGN36NLEA",
        key_specs=[
            SpecItem(label="Σύστημα Ψύξης", value="Low Frost"),
            SpecItem(label="Συνολική Χωρητικότητα", value="290 lt"),
            SpecItem(label="Χρώμα", value="Λευκό"),
        ],
        spec_sections=[
            SpecSection(
                section="Διαστάσεις", items=[SpecItem(label="Πλάτος", value="60 cm")]
            ),
            SpecSection(
                section="Νέα Ενεργειακή Ετικέτα",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="F")],
            ),
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Τεχνικά στοιχεία",
                items=[
                    SpecItem(label="Σύστημα Ψύξης", value="Total No Frost"),
                    SpecItem(label="Συνολική Χωρητικότητα", value="305 lt"),
                    SpecItem(label="Χρώμα", value="Inox"),
                    SpecItem(label="Πλάτος", value="70 cm"),
                    SpecItem(label="Ενεργειακή Κλάση", value="E"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Ψυγεία & Καταψύκτες",
        sub_category="Ψυγειοκαταψύκτες",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "229957", derive_seo_keyword
    )

    assert "Total No Frost" in fields["name"]
    assert "305Lt" in fields["name"]
    assert fields["name"].endswith("E")
    assert "Low Frost" not in fields["name"]
    assert "290Lt" not in fields["name"]
    assert "Λευκό" not in fields["name"]
    assert "60cm" not in fields["name"]
    assert "Inox" not in fields["name"]
    assert "70cm" not in fields["name"]
    assert (
        fields["meta_title"]
        == "Bosch KGN36NLEA Ψυγειοκαταψύκτης Total No Frost 305Lt | eTranoulis"
    )
    assert (
        fields["seo_keyword"]
        == "bosch-kgn36nlea-psygeiokatapsyktis-total-no-frost-305lt-e"
    )


def test_tv_name_rule_uses_resolution_from_eukrineia_in_final_name() -> None:
    source = SourceProductData(
        brand="TCL",
        mpn="115C7K",
        name='TCL 115C7K Smart Τηλεόραση 115" Mini LED',
        key_specs=[
            SpecItem(label="Τεχνολογία Οθόνης", value="Mini LED"),
            SpecItem(label="Διαγώνιος", value="115 ''"),
            SpecItem(label="Ευκρίνεια", value="ULTRA HD ( 4K )"),
            SpecItem(label="Smart Platform", value="Google TV"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="50'' & άνω",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "142677", derive_seo_keyword
    )

    assert fields["name"] == 'TCL 115C7K – Τηλεόραση 115" 4K UHD Mini LED Google TV'


def test_tv_name_rule_prefers_logismiko_platform_over_boolean_hbbtv() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="TCL",
        mpn="115C7K",
        name='TCL Smart Τηλεόραση 115" 4K UHD Mini LED C7K HDR (2025) 115C7K',
        key_specs=[
            SpecItem(label="Διαγώνιος", value='115 "'),
            SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
            SpecItem(label="Τύπος Panel", value="Mini LED"),
            SpecItem(label="Local Dimming", value="Ναι"),
        ],
        spec_sections=[
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[
                    SpecItem(label="HbbTV", value="Ναι"),
                    SpecItem(label="VRR", value="Ναι"),
                ],
            ),
            SpecSection(
                section="Smart Δυνατότητες",
                items=[
                    SpecItem(label="Λογισμικό", value="Google TV"),
                    SpecItem(label="Smart Assistant", value="Google Assistant"),
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="50'' & άνω",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "000004", derive_seo_keyword
    )

    assert fields["name"] == 'TCL 115C7K – Τηλεόραση 115" 4K UHD Mini LED Google TV'
    assert "Ναι" not in fields["name"]


def test_apply_name_rule_dedupes_tv_resolution_and_prefers_concrete_platform_from_analysi_othonis() -> (
    None
):
    source = SourceProductData(
        brand="TCL",
        mpn="115C7K",
        name='TCL 115C7K Smart Τηλεόραση 115" Mini LED',
        key_specs=[
            SpecItem(label="Τεχνολογία Οθόνης", value="Mini LED"),
            SpecItem(label="Διαγώνιος Οθόνης", value='115 "'),
            SpecItem(label="Ανάλυση Οθόνης", value="8K UHD"),
            SpecItem(label="Ευκρίνεια", value="ULTRA HD ( 8K )"),
            SpecItem(label="Λειτουργικό Σύστημα", value="Smart TV"),
            SpecItem(label="Smart Platform", value="Google TV"),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="50'' & άνω",
    )
    rule = {
        "category_phrase": "Τηλεόραση",
        "differentiator_specs": [
            [["Τεχνολογία Οθόνης"]],
            [["Διαγώνιος Οθόνης"]],
            [["Ανάλυση Οθόνης"]],
            [["Ευκρίνεια"]],
            [["Λειτουργικό Σύστημα"]],
            [["Smart Platform"]],
        ],
        "max_differentiators": 6,
        "_matched_exact": True,
    }

    category_phrase, differentiators = apply_name_rule(
        rule, source, "TCL", "115C7K", taxonomy
    )

    assert category_phrase == "Τηλεόραση"
    assert differentiators == ["Mini LED", '115"', "8K UHD", "Google TV"]
    assert (
        compose_name("TCL", "115C7K", category_phrase, differentiators)
        == 'TCL 115C7K – Τηλεόραση Mini LED 115" 8K UHD Google TV'
    )
