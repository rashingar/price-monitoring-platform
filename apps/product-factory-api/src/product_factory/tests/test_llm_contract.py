from pathlib import Path

import pytest

from product_factory.intro_text_markup import summarize_intro_text_emphasis
from product_factory.llm_contract import (
    INTRO_MAX_WORDS,
    INTRO_MIN_WORDS,
    build_intro_text_context,
    build_seo_meta_context,
    count_plain_text_words,
    validate_intro_text_output,
    validate_seo_meta_output,
)
from product_factory.models import (
    CLIInput,
    ParsedProduct,
    SourceProductData,
    SpecItem,
    TaxonomyResolution,
)
from product_factory.repo_paths import REPO_ROOT


def build_intro(words: int = INTRO_MIN_WORDS) -> str:
    return " ".join(["Ξ»Ξ­ΞΎΞ·"] * words)


def test_build_intro_text_context_excludes_section_generation() -> None:
    context = build_intro_text_context(
        cli=CLIInput(model="233541", url="https://www.electronet.gr/example"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="LG",
                mpn="GSGV80PYLL",
                name="LG GSGV80PYLL – Ψυγείο Ντουλάπα 635Lt",
                hero_summary="Σύντομη σύνοψη για καθημερινή χρήση.",
                key_specs=[SpecItem(label="Χωρητικότητα", value="635Lt")],
                presentation_source_html="<section><h3>Τίτλος</h3><p>Κείμενο</p></section>",
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Ψυγεία & Καταψύκτες", sub_category="Ψυγεία Ντουλάπες"
        ),
        deterministic_product={
            "name": "LG GSGV80PYLL – Ψυγείο Ντουλάπα 635Lt",
            "brand": "LG",
            "mpn": "GSGV80PYLL",
            "category_phrase": "Ψυγείο Ντουλάπα",
            "name_differentiators": ["635Lt", "Total No Frost"],
        },
    )

    assert context["task"] == "intro_text"
    assert context["writer_rules"]["llm_owned_fields"] == ["intro_text"]
    assert context["writer_rules"]["plain_text_only"] is False
    assert (
        context["writer_rules"]["output_format"]
        == "single_greek_paragraph_with_limited_strong_html"
    )
    assert context["writer_rules"]["allowed_inline_html_tags"] == ["strong"]
    assert context["writer_rules"]["forbidden_outputs"] == [
        "json",
        "markdown",
        "bullets",
        "cta_language",
        "unsupported_html",
    ]
    assert (
        context["writer_rules"]["emphasis_policy"]["scope"] == "generic_all_categories"
    )
    assert (
        context["writer_rules"]["emphasis_policy"]["max_emphasized_word_ratio"] == 0.35
    )
    assert context["writer_rules"]["word_count_range"] == {"min": 60, "max": 180}
    assert "presentation_source_sections" not in context
    assert "sections" not in context


def test_build_seo_meta_context_includes_required_keyword_evidence() -> None:
    context = build_seo_meta_context(
        cli=CLIInput(model="233541", url="https://www.electronet.gr/example"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="LG",
                mpn="GSGV80PYLL",
                name="LG GSGV80PYLL – Ψυγείο Ντουλάπα 635Lt",
                hero_summary="Σύντομη σύνοψη για καθημερινή χρήση.",
                key_specs=[SpecItem(label="Χωρητικότητα", value="635Lt")],
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Ψυγεία & Καταψύκτες", sub_category="Ψυγεία Ντουλάπες"
        ),
        deterministic_product={
            "name": "LG GSGV80PYLL – Ψυγείο Ντουλάπα 635Lt",
            "brand": "LG",
            "mpn": "GSGV80PYLL",
            "category_phrase": "Ψυγείο Ντουλάπα",
            "meta_title": "LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt | eTranoulis",
            "meta_description_draft": "Το LG GSGV80PYLL είναι ψυγείο ντουλάπα με 635Lt.",
            "name_differentiators": ["635Lt", "Total No Frost"],
            "seo_keyword": "lg-gsgv80pyll-psygeio-ntoulapa-635lt",
        },
    )

    assert context["task"] == "seo_meta"
    assert context["writer_rules"]["llm_owned_fields"] == [
        "product.meta_description",
        "product.meta_keywords",
    ]
    assert context["writer_rules"]["required_keywords"] == ["LG", "GSGV80PYLL"]
    assert set(context["evidence"]) >= {
        "meta_description_draft",
        "hero_summary",
        "key_specs",
        "deterministic_differentiators",
    }
    assert (
        context["product"]["meta_title"]
        == "LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt | eTranoulis"
    )
    assert (
        context["evidence"]["meta_description_draft"]
        == "Το LG GSGV80PYLL είναι ψυγείο ντουλάπα με 635Lt."
    )
    assert "Write natural Greek" in context["writer_rules"]["meta_description_rule"]
    assert (
        "product.prose_subject" in context["writer_rules"]["meta_description_rule"]
    )
    assert (
        "product.copy_name plus product.category"
        not in context["writer_rules"]["meta_description_rule"]
    )
    assert (
        "Exactly one sentence" not in context["writer_rules"]["meta_description_rule"]
    )
    assert (
        "Smooth the Greek grammar"
        not in context["writer_rules"]["meta_description_rule"]
    )
    assert context["writer_rules"]["subject_field"] == "product.prose_subject"
    assert context["writer_rules"]["category_field"] == "product.category"
    assert context["writer_rules"]["output_schema"] == {
        "product": {
            "meta_description": "string",
            "meta_keywords": "string[]",
        }
    }
    assert "json_shape" in context["writer_rules"]["deterministic_validation"]


def test_build_intro_text_context_prefers_model_name_over_raw_mpn() -> None:
    context = build_intro_text_context(
        cli=CLIInput(model="414520", url="https://example.test/product"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="Ariete",
                mpn="00P414520AR0",
                name="Ariete XVapor Comfort 00P414520AR0 Steam Cleaner",
                hero_summary="Steam cleaner for home use.",
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Steam Cleaner", sub_category="Cleaning"
        ),
        deterministic_product={
            "name": "Ariete 00P414520AR0 Steam Cleaner",
            "brand": "Ariete",
            "mpn": "00P414520AR0",
            "category_phrase": "Steam Cleaner",
        },
    )

    assert context["product"]["model_name"] == "XVapor Comfort"
    assert context["product"]["copy_name"] == "Ariete XVapor Comfort"
    assert context["product"]["prose_subject"] == "Ariete XVapor Comfort"
    assert context["product"]["mpn"] == "00P414520AR0"
    assert context["product"]["preferred_identifier"] == "XVapor Comfort"
    assert context["product"]["category"] == "Steam Cleaner"


def test_build_seo_meta_context_requires_model_name_when_available() -> None:
    context = build_seo_meta_context(
        cli=CLIInput(model="414520", url="https://example.test/product"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="Ariete",
                mpn="00P414520AR0",
                name="Ariete XVapor Comfort 00P414520AR0 Steam Cleaner",
                hero_summary="Steam cleaner for home use.",
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Steam Cleaner", sub_category="Cleaning"
        ),
        deterministic_product={
            "name": "Ariete 00P414520AR0 Steam Cleaner",
            "brand": "Ariete",
            "mpn": "00P414520AR0",
            "category_phrase": "Steam Cleaner",
            "meta_description_draft": "The Ariete 00P414520AR0 is a Steam Cleaner.",
        },
    )

    assert context["product"]["model_name"] == "XVapor Comfort"
    assert context["product"]["copy_name"] == "Ariete XVapor Comfort"
    assert context["product"]["prose_subject"] == "Ariete XVapor Comfort"
    assert context["product"]["preferred_identifier"] == "XVapor Comfort"
    assert context["product"]["category"] == "Steam Cleaner"
    assert (
        context["evidence"]["meta_description_draft"]
        == "The Ariete XVapor Comfort is a Steam Cleaner."
    )
    assert context["writer_rules"]["required_keywords"] == ["Ariete", "XVapor Comfort"]
    assert context["writer_rules"]["subject_field"] == "product.prose_subject"


def test_build_intro_text_context_ignores_internal_skroutz_family_as_model_name() -> (
    None
):
    context = build_intro_text_context(
        cli=CLIInput(model="415376", url="https://www.skroutz.gr/s/example.html"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="Midea",
                mpn="AIRGRN-21HRFN8-I",
                name="Midea AIRGRN-21HRFN8-I - Κλιματιστικό 21000 BTU",
                skroutz_family="air_conditioner",
                hero_summary="Air Green με AI EcoMaster.",
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Κλιματιστικό", sub_category="Τοίχου"
        ),
        deterministic_product={
            "name": "Midea AIRGRN-21HRFN8-I - Κλιματιστικό 21000 BTU",
            "brand": "Midea",
            "mpn": "AIRGRN-21HRFN8-I",
            "category_phrase": "Κλιματιστικό",
        },
    )

    assert context["product"]["model_name"] == ""
    assert context["product"]["preferred_identifier"] == "AIRGRN-21HRFN8-I"
    assert context["product"]["copy_name"] == "Midea AIRGRN-21HRFN8-I"
    assert context["product"]["prose_subject"] == "Midea AIRGRN-21HRFN8-I"
    assert context["product"]["category"] == "Κλιματιστικό"


def test_build_intro_text_context_keeps_ac_copy_name_category_free() -> None:
    context = build_intro_text_context(
        cli=CLIInput(model="409965", url="https://example.test/ac"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="Inventor",
                mpn="L4VI32-09/L4VO32-09",
                name="Inventor L4VI32-09/L4VO32-09 - Κλιματιστικό 9000 BTU",
                hero_summary="Κλιματιστικό τοίχου 9000 BTU.",
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Κλιματιστικό", sub_category="Τοίχου"
        ),
        deterministic_product={
            "name": "Inventor L4VI32-09/L4VO32-09 - Κλιματιστικό 9000 BTU",
            "brand": "Inventor",
            "mpn": "L4VI32-09/L4VO32-09",
            "category_phrase": "Κλιματιστικό",
        },
    )

    assert context["product"]["copy_name"] == "Inventor L4VI32-09/L4VO32-09"
    assert context["product"]["prose_subject"] == "Inventor L4VI32-09/L4VO32-09"
    assert context["product"]["category"] == "Κλιματιστικό"
    assert "Κλιματιστικό" not in context["product"]["prose_subject"]
    assert not context["product"]["copy_name"].endswith("Κλιματιστικό")
    assert context["writer_rules"]["subject_field"] == "product.prose_subject"
    assert context["writer_rules"]["category_field"] == "product.category"


def test_build_seo_meta_context_keeps_generic_copy_name_category_free() -> None:
    context = build_seo_meta_context(
        cli=CLIInput(model="233541", url="https://example.test/fridge"),
        parsed=ParsedProduct(
            source=SourceProductData(
                brand="LG",
                mpn="GSGV80PYLL",
                name="LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt",
                hero_summary="Ψυγείο ντουλάπα για καθημερινή χρήση.",
            )
        ),
        taxonomy=TaxonomyResolution(
            leaf_category="Ψυγείο Ντουλάπα", sub_category="Ψυγεία Ντουλάπες"
        ),
        deterministic_product={
            "name": "LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt",
            "brand": "LG",
            "mpn": "GSGV80PYLL",
            "category_phrase": "Ψυγείο Ντουλάπα",
            "meta_description_draft": "Το LG GSGV80PYLL είναι Ψυγείο Ντουλάπα.",
        },
    )

    assert context["product"]["copy_name"] == "LG GSGV80PYLL"
    assert context["product"]["prose_subject"] == "LG GSGV80PYLL"
    assert context["product"]["category"] == "Ψυγείο Ντουλάπα"
    assert "Ψυγείο Ντουλάπα" not in context["product"]["prose_subject"]
    assert not context["product"]["copy_name"].endswith("Ψυγείο Ντουλάπα")


def test_validate_intro_text_output_accepts_plain_text_only() -> None:
    normalized, errors = validate_intro_text_output(
        " ".join(["λέξη"] * INTRO_MIN_WORDS)
    )

    assert errors == []
    assert normalized.startswith("λέξη")


def test_validate_intro_text_output_accepts_updated_word_count_boundaries() -> None:
    assert INTRO_MIN_WORDS == 60
    assert INTRO_MAX_WORDS == 180

    _, min_errors = validate_intro_text_output(" ".join(["λέξη"] * 60))
    _, max_errors = validate_intro_text_output(" ".join(["λέξη"] * 180))

    assert min_errors == []
    assert max_errors == []


def test_validate_intro_text_output_rejects_updated_word_count_boundaries() -> None:
    _, min_errors = validate_intro_text_output(" ".join(["λέξη"] * 59))
    _, max_errors = validate_intro_text_output(" ".join(["λέξη"] * 181))

    assert "llm_intro_text_word_count_invalid" in min_errors
    assert "llm_intro_text_word_count_invalid" in max_errors


def test_validate_intro_text_output_accepts_safe_strong_emphasis() -> None:
    intro = (
        "<strong>Acme AX100</strong> είναι <strong>φορητός υπολογιστής</strong> για καθημερινή χρήση "
        "με σταθερή περιγραφή που βασίζεται σε επιβεβαιωμένα στοιχεία. Διαθέτει <strong>16GB RAM</strong> "
        "και αποθηκευτικό χώρο που αναφέρεται στο πλαίσιο, ώστε ο αναγνώστης να εντοπίζει γρήγορα τα "
        "βασικά σημεία χωρίς υπερβολές. Η σύντομη παρουσίαση κρατά ουδέτερο ύφος, αποφεύγει υποσχέσεις "
        "που δεν τεκμηριώνονται και συνδέει τον τύπο προϊόντος με τα κύρια χαρακτηριστικά που βοηθούν "
        "στην αξιολόγηση. Το κείμενο παραμένει ενιαία παράγραφος, χωρίς λίστες, προτροπές αγοράς ή "
        "πρόσθετους ισχυρισμούς πέρα από τα διαθέσιμα δεδομένα και διατηρεί καθαρή ροή για εύκολη ανάγνωση."
    )

    normalized, errors = validate_intro_text_output(intro)

    assert errors == []
    assert "<strong>Acme AX100</strong>" in normalized
    assert (
        count_plain_text_words(normalized)
        == summarize_intro_text_emphasis(normalized)["visible_word_count"]
    )


def test_intro_word_count_ignores_strong_tags() -> None:
    intro = "<strong>Μία δύο</strong> τρία τέσσερα πέντε"

    assert count_plain_text_words(intro) == 5


def test_validate_intro_text_output_rejects_short_intro() -> None:
    _, errors = validate_intro_text_output(" ".join(["λέξη"] * (INTRO_MIN_WORDS - 1)))

    assert "llm_intro_text_word_count_invalid" in errors


def test_validate_intro_text_output_rejects_html() -> None:
    _, errors = validate_intro_text_output(
        "<p>λέξη</p> " + " ".join(["λέξη"] * (INTRO_MIN_WORDS - 1))
    )

    assert "llm_intro_text_html_invalid" in errors


@pytest.mark.parametrize(
    "intro",
    [
        "<script>alert(1)</script> " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "<span>λέξη</span> " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        '<strong class="x">λέξη</strong> ' + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "<strong>λέξη " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "<strong></strong> " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "**λέξη** " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "[λέξη](https://example.test) " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "![λέξη](https://example.test/image.jpg) "
        + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "# Τίτλος " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
        "- λέξη " + " ".join(["λέξη"] * INTRO_MIN_WORDS),
    ],
)
def test_validate_intro_text_output_rejects_invalid_emphasis_markup(intro: str) -> None:
    _, errors = validate_intro_text_output(intro, intro_word_min=1, intro_word_max=200)

    assert "llm_intro_text_emphasis_invalid" in errors


def test_validate_intro_text_output_rejects_overused_emphasis() -> None:
    bold_words = " ".join(["λέξη"] * 40)
    plain_words = " ".join(["λέξη"] * 60)

    _, errors = validate_intro_text_output(
        f"<strong>{bold_words}</strong> {plain_words}"
    )

    assert "llm_intro_text_emphasis_overused" in errors


def test_validate_intro_text_output_uses_configured_emphasis_ratio() -> None:
    bold_words = " ".join(["λέξη"] * 40)
    plain_words = " ".join(["λέξη"] * 60)

    _, errors = validate_intro_text_output(
        f"<strong>{bold_words}</strong> {plain_words}",
        intro_max_emphasized_word_ratio=0.45,
    )

    assert errors == []


def test_validate_intro_text_output_allows_many_short_emphasis_spans_under_ratio_limit() -> (
    None
):
    emphasized = " ".join(["<strong>word</strong>"] * 11)
    plain_words = " ".join(["word"] * 75)

    _, errors = validate_intro_text_output(f"{emphasized} {plain_words}")

    assert errors == []


def test_intro_emphasis_missing_is_diagnostic_not_validation_error() -> None:
    intro = " ".join(["λέξη"] * INTRO_MIN_WORDS)

    _, errors = validate_intro_text_output(intro)
    diagnostics = summarize_intro_text_emphasis(intro)

    assert errors == []
    assert diagnostics["emphasis_warning_codes"] == ["llm_intro_text_emphasis_missing"]


def test_validate_intro_text_output_rejects_long_intro() -> None:
    _, errors = validate_intro_text_output(" ".join(["λέξη"] * (INTRO_MAX_WORDS + 1)))

    assert "llm_intro_text_word_count_invalid" in errors


def test_validate_intro_text_output_rejects_encoding_corruption() -> None:
    _, errors = validate_intro_text_output(" ".join(["Καλημέρα???"] * INTRO_MIN_WORDS))

    assert "llm_intro_text_encoding_invalid" in errors


def test_validate_seo_meta_output_accepts_product_meta_only_shape() -> None:
    normalized, errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": "Το LG GSGV80PYLL είναι ψυγείο ντουλάπα με πρακτική καθημερινή χρήση.",
                "meta_keywords": ["LG", "GSGV80PYLL", "Ψυγείο Ντουλάπα"],
            }
        }
    )

    assert errors == []
    assert normalized["product"]["meta_keywords"] == [
        "LG",
        "GSGV80PYLL",
        "Ψυγείο Ντουλάπα",
    ]


def test_validate_seo_meta_output_accepts_two_sentence_meta_description() -> None:
    normalized, errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": (
                    "Το TCL 115C7K είναι τηλεόραση Mini LED 115 ιντσών με 4K Ultra HD ανάλυση και Google TV. "
                    "Προσφέρει verified χαρακτηριστικά εικόνας και συνδεσιμότητας από τα διαθέσιμα στοιχεία."
                ),
                "meta_keywords": ["TCL", "115C7K", "Τηλεόραση"],
            }
        }
    )

    assert errors == []
    assert normalized["product"]["meta_description"].count(".") >= 2


def test_validate_seo_meta_output_rejects_legacy_presentation_shape() -> None:
    _, errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": "ok",
                "meta_keywords": ["LG"],
            },
            "presentation": {
                "intro_html": build_intro(),
            },
        }
    )

    assert "llm_seo_meta_root_shape_invalid" in errors


def test_validate_seo_meta_output_rejects_overlong_description() -> None:
    _, errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": f"{'Valid description text ' * 20}.",
                "meta_keywords": ["LG", "Example"],
            }
        },
        meta_description_max_chars=120,
    )

    assert "llm_seo_meta_description_too_long" in errors


def test_validate_seo_meta_output_rejects_incomplete_description() -> None:
    _, errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": "Valid description text that stops after a connector and",
                "meta_keywords": ["LG", "Example"],
            }
        }
    )

    assert "llm_seo_meta_description_incomplete" in errors


def test_validate_seo_meta_output_rejects_encoding_corruption() -> None:
    _, errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": "Κακή περιγραφή???",
                "meta_keywords": ["LG", "MH6535GDS"],
            }
        }
    )

    assert "llm_seo_meta_description_encoding_invalid" in errors


def test_seo_meta_prompt_source_uses_repo_root_relative_path_and_updated_guidance() -> (
    None
):
    prompt_path = REPO_ROOT / "resources" / "prompts" / "seo_meta_prompt.txt"
    prompt = Path(prompt_path).read_text(encoding="utf-8")
    lowered = prompt.casefold()

    assert prompt_path.is_file()
    assert "exactly one sentence" not in lowered
    assert "verified facts" in lowered
    assert "product.prose_subject" in prompt
    assert "product.copy_name" not in prompt
    assert "preferred_identifier" in prompt
    assert "return json only" in lowered


def test_intro_text_prompt_source_uses_updated_word_count_range() -> None:
    prompt_path = REPO_ROOT / "resources" / "prompts" / "intro_text_prompt.txt"
    prompt = Path(prompt_path).read_text(encoding="utf-8")

    assert prompt_path.is_file()
    assert "60-180 words" in prompt
    assert "80" + "-180" not in prompt
    assert "product.prose_subject" in prompt


def test_authoring_prompts_prefer_prose_subject_over_copy_name() -> None:
    prompt_paths = [
        REPO_ROOT / "resources" / "prompts" / "intro_text_prompt.txt",
        REPO_ROOT / "resources" / "prompts" / "seo_meta_prompt.txt",
    ]

    for prompt_path in prompt_paths:
        prompt = Path(prompt_path).read_text(encoding="utf-8")

        assert "product.prose_subject" in prompt
        assert "product.copy_name" not in prompt
        assert "brand + preferred_identifier + category" not in prompt
