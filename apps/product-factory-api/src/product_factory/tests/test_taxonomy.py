from product_factory.models import SourceProductData, TaxonomyResolution
from product_factory.models import SpecItem, SpecSection
from product_factory.taxonomy import TaxonomyResolver


def test_taxonomy_serialization() -> None:
    resolver = TaxonomyResolver()
    resolution = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκούπες Stick",
    )
    assert resolver.serialize_category(resolution, 0) == (
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκούπισμα:::"
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκούπισμα///Σκούπες Stick"
    )
    assert resolver.serialize_category(resolution, 1).endswith(":::Μικροσυσκευές")


def test_tv_category_serialization_includes_size_tech_and_manufacturer_subcategories() -> (
    None
):
    resolver = TaxonomyResolver()
    resolution = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="50'' & άνω",
    )
    source = SourceProductData(
        brand="TCL",
        name='TCL 60" OLED 4K UHD TV',
        key_specs=[
            SpecItem(label="Διαγώνιος Οθόνης ( Ίντσες )", value="60"),
            SpecItem(label="Τεχνολογία Οθόνης", value="OLED"),
            SpecItem(label="Ανάλυση Οθόνης", value="Ultra HD ( 4K )"),
        ],
    )

    assert resolver.serialize_category(resolution, source=source).split(":::") == [
        "ΕΙΚΟΝΑ & ΗΧΟΣ",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///50'' & άνω",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///OLED TV",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///4K UHD",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///TCL",
    ]


def test_taxonomy_resolution_prefers_breadcrumb_match() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=["Αρχική", "Εξοπλισμός Σπιτιού", "Σκούπισμα", "Σκούπες Stick"],
        url="https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/example",
        name="Σκούπα Stick Rowenta X-Force",
        key_specs=[],
        spec_sections=[],
    )
    assert resolution.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert resolution.leaf_category == "Σκούπισμα"
    assert resolution.sub_category == "Σκούπες Stick"
    assert candidates[0]["confidence"] >= candidates[-1]["confidence"]


def test_taxonomy_resolution_maps_koptiria_ravdomplenter_to_exact_subcategory() -> None:
    resolver = TaxonomyResolver()
    resolution, _ = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Εξοπλισμός Σπιτιού",
            "Συσκευές Κουζίνας",
            "Κοπτήρια - Ραβδομπλέντερ",
        ],
        url="https://www.electronet.gr/exoplismos-spitioy/syskeyes-koyzinas/koptiria-rabdomplenter/example",
        name="Πολυκόπτης Tefal Fresh Express DN853B Γκρι",
        key_specs=[],
        spec_sections=[],
    )

    assert resolution.sub_category == "Κοπτήρια-Ράβδοι"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakos-eksoplismos/syskeues-kouzinas/kopthria-ravdoi"
    )


def test_taxonomy_resolution_maps_electronet_womens_care_brushes_to_personal_care() -> (
    None
):
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Εξοπλισμός Σπιτιού",
            "Γυναικεία Φροντίδα",
            "Βούρτσες - Ψαλίδια",
        ],
        url="https://www.electronet.gr/exoplismos-spitioy/gynaikeia-frontida/boyrtses-psalidia/boyrtsa-mallion-philips-bha71000",
        name="Βούρτσα Μαλλιών Philips BHA710/00",
        key_specs=[],
        spec_sections=[],
    )

    assert resolution.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert resolution.leaf_category == "Προσωπική Φροντίδα"
    assert resolution.sub_category == "Βούρτσες-Ψαλίδια-ισιωτικά"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakos-eksoplismos/proswpikh-frontida/vourtses-psalidia"
    )
    assert candidates[0]["sub_category"] == "Βούρτσες-Ψαλίδια-ισιωτικά"


def test_taxonomy_resolution_prefers_dryer_subcategory_for_singular_product_name() -> (
    None
):
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Οικιακές Συσκευές",
            "Πλυντήρια - Στεγνωτήρια",
            "Στεγνωτήρια",
        ],
        url="https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/stegnotiria/stegnotirio-royhon-lg-rhx5009twb-9-kg-b",
        name="Στεγνωτήριο ρούχων LG RHX5009TWB 9 kg B",
        key_specs=[],
        spec_sections=[],
    )

    assert resolution.sub_category == "Στεγνωτήρια Ρούχων"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakes-syskeues/plynthria-stegnwthria/stegnwthria-rouxwn"
    )
    assert candidates[0]["sub_category"] == "Στεγνωτήρια Ρούχων"


def test_taxonomy_resolution_prefers_television_size_bucket_for_50_inches() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=["Αρχική", "Εικόνα - Ήχος", "Τηλεοράσεις", "Όλες οι Τηλεοράσεις"],
        url="https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-samsung-qe50qn80f-50-smart-4k-mini-led-ai",
        name="TV Samsung QE50QN80F 50'' Smart 4K Mini LED AI",
        key_specs=[SpecItem(label="Διαγώνιος Οθόνης ( Ίντσες )", value="50")],
        spec_sections=[
            SpecSection(
                section="Εικόνα - Ήχος",
                items=[SpecItem(label="Διαγώνιος Οθόνης ( Ίντσες )", value="50")],
            )
        ],
    )

    assert resolution.parent_category == "ΕΙΚΟΝΑ & ΗΧΟΣ"
    assert resolution.leaf_category == "Τηλεοράσεις"
    assert resolution.sub_category == "33''-50''"
    assert resolution.cta_url == "https://www.etranoulis.gr/eikona-hxos/thleoraseis"
    assert resolution.plural_label == "Τηλεοράσεις"
    assert "television_size_bucket" in resolution.reason
    assert candidates[0]["sub_category"] == "33''-50''"
    assert (
        candidates[0]["cta_url"] == "https://www.etranoulis.gr/eikona-hxos/thleoraseis"
    )


def test_taxonomy_resolution_accepts_bestprice_stand_fan_url_evidence() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=["Ξ‘ΟΟ‡ΞΉΞΊΞ®"],
        url="https://www.bestprice.gr/item/2156488534/taurus-greco-16cr-anemistiras-dapedou-orthostatis-40cm-40w.html",
        name="Taurus Greco 16cr anemistiras dapedou orthostatis 40cm 40W",
        key_specs=[
            {"label": "manufacturer", "value": "Taurus"},
            {"label": "diameter", "value": "40cm"},
            {"label": "power", "value": "40W"},
        ],
        spec_sections=[],
    )

    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/klimatismos-thermansi/anemisthres/orthostatis"
    )
    assert resolution.taxonomy_path
    assert "fan_subcategory_url" in resolution.reason
    assert candidates[0]["cta_url"].endswith("/orthostatis")


def test_taxonomy_resolution_accepts_bestprice_pan_url_evidence() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=["home"],
        url="https://www.bestprice.gr/item/2164069513/bra-tigani-anoxeidoto-antikollitiko-24cm-a771202.html",
        name="BRA tigani anoxeidoto antikollitiko 24cm A771202",
        key_specs=[
            {"label": "manufacturer", "value": "BRA"},
            {"label": "size", "value": "24cm"},
            {"label": "type", "value": "tigani"},
        ],
        spec_sections=[],
    )

    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakos-eksoplismos/skeuh-mageirikhs/thgania"
    )
    assert resolution.taxonomy_path
    assert "cookware_pan_url" in resolution.reason
    assert candidates[0]["cta_url"].endswith("/thgania")


def test_taxonomy_resolution_accepts_bestprice_espresso_capsule_evidence() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=["home"],
        url="https://www.bestprice.gr/item/2153980520/delonghi-inissia-en80-cw-kafetiera-espresso-gia-kapsoules-nespresso-19bar.html",
        name="DeLonghi Inissia EN80.CW Kafetiera Espresso gia Kapsoules Nespresso 19bar",
        key_specs=[
            {"label": "manufacturer", "value": "DeLonghi"},
            {"label": "capsule type", "value": "Nespresso"},
            {"label": "pump pressure", "value": "19bar"},
        ],
        spec_sections=[],
    )

    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakos-eksoplismos/kafes-rofhmata-xhmoi/kafetieres-espresso"
    )
    assert resolution.taxonomy_path
    assert "coffee_espresso_evidence" in resolution.reason
    assert candidates[0]["sub_category"] == "Καφετιέρες Espresso"


def test_taxonomy_resolution_prefers_microwave_without_grill_url_and_base_cta() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Οικιακές Συσκευές",
            "Φούρνοι Μικροκυμάτων",
            "Φούρνοι Μικροκυμάτων Χωρίς Grill",
        ],
        url="https://www.electronet.gr/oikiakes-syskeyes/foyrnoi-mikrokymaton/foyrnoi-mikrokymaton-horis-grill/foyrnos-mikrokymaton-midea-mm20cf2esl",
        name="Φούρνος Μικροκυμάτων Midea MM20CF2ESL",
        key_specs=[SpecItem(label="Χωρητικότητα Φούρνου σε Λίτρα", value="20")],
        spec_sections=[
            SpecSection(
                section="Επισκόπηση Προϊόντος",
                items=[SpecItem(label="Χωρητικότητα Φούρνου σε Λίτρα", value="20")],
            )
        ],
    )

    assert resolution.leaf_category == "Φούρνοι Μικροκυμάτων"
    assert resolution.sub_category == "Χωρίς Grill"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakes-syskeues/fournoi-mikrokymatwn"
    )
    assert resolution.plural_label == "Φούρνους Μικροκυμάτων"
    assert "electronet_microwave_without_grill_url" in resolution.reason
    assert candidates[0]["sub_category"] == "Χωρίς Grill"
    assert (
        candidates[0]["cta_url"]
        == "https://www.etranoulis.gr/oikiakes-syskeues/fournoi-mikrokymatwn"
    )


def test_taxonomy_resolution_prefers_microwave_with_grill_url_and_base_cta() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Οικιακές Συσκευές",
            "Φούρνοι Μικροκυμάτων",
            "Φούρνοι Μικροκυμάτων Με Grill",
        ],
        url="https://www.electronet.gr/oikiakes-syskeyes/foyrnoi-mikrokymaton/foyrnoi-mikrokymaton-me-grill/foyrnos-mikrokymaton-midea-example",
        name="Φούρνος Μικροκυμάτων Midea Example με Grill",
        key_specs=[SpecItem(label="Χωρητικότητα Φούρνου σε Λίτρα", value="20")],
        spec_sections=[
            SpecSection(
                section="Επισκόπηση Προϊόντος",
                items=[SpecItem(label="Χωρητικότητα Φούρνου σε Λίτρα", value="20")],
            )
        ],
    )

    assert resolution.leaf_category == "Φούρνοι Μικροκυμάτων"
    assert resolution.sub_category == "Με Grill"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakes-syskeues/fournoi-mikrokymatwn"
    )
    assert resolution.plural_label == "Φούρνους Μικροκυμάτων"
    assert "electronet_microwave_with_grill_url" in resolution.reason
    assert candidates[0]["sub_category"] == "Με Grill"
    assert (
        candidates[0]["cta_url"]
        == "https://www.etranoulis.gr/oikiakes-syskeues/fournoi-mikrokymatwn"
    )


def test_taxonomy_resolution_prefers_hifi_for_electronet_mini_hifi_url() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=["Home", "Audio Home Systems", "Mini Hifi"],
        url="https://www.electronet.gr/eikona-ihos/audio-home-systems/mini-hifi/ihosystima-micro-panasonic-sc-pm700eg-s",
        name="Micro HiFi Panasonic SC-PM700EG-S",
        key_specs=[],
        spec_sections=[],
    )

    assert resolution.leaf_category == "Audio Systems"
    assert resolution.sub_category == "Hifi"
    assert (
        resolution.cta_url == "https://www.etranoulis.gr/eikona-hxos/audio-systems/hifi"
    )
    assert "electronet_mini_hifi_url" in resolution.reason
    assert candidates[0]["sub_category"] == "Hifi"


def test_taxonomy_resolution_maps_electronet_frapieres_combined_breadcrumb() -> None:
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Εξοπλισμός Σπιτιού",
            "Καφές - Χυμοί - Ροφήματα",
            "Φραπιέρες - Ηλεκτρικά Μπρίκια",
        ],
        url="https://www.electronet.gr/exoplismos-spitioy/kafes-hymoi-rofimata/frapieres-ilektrika-mprikia/frapiera-rohnson-mod-r-4437-mpez",
        name="Φραπιέρα Rohnson MOD R-4437 Μπεζ",
        key_specs=[],
        spec_sections=[],
    )

    assert resolution.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert resolution.leaf_category == "Καφές-Ροφήματα-Χυμοί"
    assert resolution.sub_category == "Φραπιέρες"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/oikiakos-eksoplismos/kafes-rofhmata-xhmoi/frapieres"
    )
    assert "electronet_frapieres_url" in resolution.reason
    assert candidates[0]["sub_category"] == "Φραπιέρες"


def test_taxonomy_resolution_maps_electronet_combined_air_conditioner_wall_breadcrumb() -> (
    None
):
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "Αρχική",
            "Κλιματισμός - Θέρμανση",
            "Κλιματιστικά",
            "Κλιματιστικά Τοίχου",
        ],
        url="https://www.electronet.gr/klimatismos-thermansi/klimatistika/klimatistika-toihoy/ac-inventor-neo-plus-npvi-24wfinpvo24-24000btu",
        name="A/C Inventor Neo Plus NPVI-24WFI/NPVO24 24000Btu",
        key_specs=[],
        spec_sections=[],
    )

    assert resolution.parent_category == "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ"
    assert resolution.leaf_category == "Κλιματιστικά"
    assert resolution.sub_category == "Τοίχου"
    assert (
        resolution.cta_url
        == "https://www.etranoulis.gr/klimatismos-thermansi/klimatistika/toixou"
    )
    assert "sub_breadcrumb" in resolution.reason
    assert candidates[0]["sub_category"] == "Τοίχου"

def test_taxonomy_resolution_prefers_wall_air_conditioner_over_accessories_for_unit_evidence() -> (
    None
):
    resolver = TaxonomyResolver()
    resolution, candidates = resolver.resolve(
        breadcrumbs=[
            "\u039a\u03bb\u03b9\u03bc\u03b1\u03c4\u03b9\u03c3\u03bc\u03cc\u03c2 & \u0397\u03bb\u03b9\u03b1\u03ba\u03ac",
            "\u039a\u03bb\u03b9\u03bc\u03b1\u03c4\u03b9\u03c3\u03bc\u03cc\u03c2",
            "\u039a\u03bb\u03b9\u03bc\u03b1\u03c4\u03b9\u03c3\u03c4\u03b9\u03ba\u03ac",
        ],
        url="https://www.apothema.gr/hisense-kf50xt00g-klimatistiko-inverter-18000-btu-301290p",
        name="Hisense KF50XT00G \u039a\u03bb\u03b9\u03bc\u03b1\u03c4\u03b9\u03c3\u03c4\u03b9\u03ba\u03cc Inverter 18000 BTU",
        key_specs=[
            {"label": "\u0391\u03c0\u03cc\u03b4\u03bf\u03c3\u03b7 (BTU)", "value": "18000 BTU"}
        ],
        spec_sections=[],
    )

    assert resolution.leaf_category == "\u039a\u03bb\u03b9\u03bc\u03b1\u03c4\u03b9\u03c3\u03c4\u03b9\u03ba\u03ac"
    assert resolution.sub_category == "\u03a4\u03bf\u03af\u03c7\u03bf\u03c5"
    assert "air_conditioner_unit_wall_evidence" in resolution.reason
    assert candidates[0]["sub_category"] == "\u03a4\u03bf\u03af\u03c7\u03bf\u03c5"
