from __future__ import annotations

from product_factory.services.authoring_lint import (
    lint_intro_text_output,
    lint_seo_meta_description,
)


PRODUCT = {
    "brand": "Inventor",
    "preferred_identifier": "L4VI32-09/L4VO32-09",
    "mpn": "L4VI32-09/L4VO32-09",
    "prose_subject": "Inventor L4VI32-09/L4VO32-09",
    "copy_name": "Inventor L4VI32-09/L4VO32-09",
    "category": "Κλιματιστικό",
}


def test_linter_detects_duplicated_category_phrase_in_intro_text() -> None:
    warnings = lint_intro_text_output(
        (
            "Το Inventor L4VI32-09/L4VO32-09 Κλιματιστικό είναι ένα "
            "κλιματιστικό για καθημερινή χρήση."
        ),
        PRODUCT,
    )

    assert "intro_text_duplicate_category_phrase" in {
        warning.code for warning in warnings
    }


def test_linter_detects_duplicated_prose_subject_model_phrase() -> None:
    warnings = lint_seo_meta_description(
        (
            "Το Inventor L4VI32-09/L4VO32-09 είναι κλιματιστικό και το "
            "Inventor L4VI32-09/L4VO32-09 διαθέτει λειτουργίες ψύξης."
        ),
        PRODUCT,
    )

    codes = {warning.code for warning in warnings}
    assert "authoring_duplicate_prose_subject" in codes
    assert "authoring_duplicate_identifier_phrase" in codes


def test_linter_allows_normal_greek_text_with_one_category_phrase() -> None:
    warnings = lint_intro_text_output(
        (
            "Το Inventor L4VI32-09/L4VO32-09 είναι κλιματιστικό για χώρους "
            "καθημερινής χρήσης, με σταθερή απόδοση και καθαρή λειτουργία."
        ),
        PRODUCT,
    )

    assert warnings == []
