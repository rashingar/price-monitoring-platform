from __future__ import annotations

from tools.schema_registry.refresh_template_coverage import (
    ExpectedCategory,
    ObservedTemplate,
    assess_template_coverage,
    build_markdown_table,
)


def _expected_category(
    *,
    label: str,
    parent_category: str,
    leaf_category: str,
    sub_category: str | None,
    category_path: str,
) -> ExpectedCategory:
    return ExpectedCategory(
        key=category_path,
        label=label,
        parent_category=parent_category,
        leaf_category=leaf_category,
        sub_category=sub_category,
        category_path=category_path,
        cta_url=f"https://example.test/{category_path.casefold().replace(' > ', '/')}",
    )


def _observed_template(
    *,
    template_id: str,
    template_file: str,
    category_path: str,
    template_status: str = "active",
    examples: tuple[str, ...] = (),
) -> ObservedTemplate:
    return ObservedTemplate(
        template_id=template_id,
        template_file=template_file,
        category_path=category_path,
        template_status=template_status,
        examples=examples,
    )


def test_refresh_template_coverage_marks_statuses_and_is_deterministic() -> None:
    expected = [
        _expected_category(
            label="Κατηγορία Α",
            parent_category="P1",
            leaf_category="L1",
            sub_category=None,
            category_path="P1 > L1 > -",
        ),
        _expected_category(
            label="Κατηγορία Β",
            parent_category="P1",
            leaf_category="L2",
            sub_category=None,
            category_path="P1 > L2 > -",
        ),
        _expected_category(
            label="Κατηγορία Γ",
            parent_category="P1",
            leaf_category="L3",
            sub_category=None,
            category_path="P1 > L3 > -",
        ),
    ]
    observed = [
        _observed_template(
            template_id="active",
            template_file="active.json",
            category_path="P1 > L1 > -",
            examples=("https://example.test/product-a",),
        ),
        _observed_template(
            template_id="manual",
            template_file="manual.json",
            category_path="P1 > L2 > -",
            template_status="manual_only",
        ),
    ]

    first = assess_template_coverage(expected, observed)
    second = assess_template_coverage(expected, observed)

    assert first == second
    assert [row["CTA Leaf Category"] for row in first] == ["Κατηγορία Α", "Κατηγορία Β", "Κατηγορία Γ"]
    assert [row["Status"] for row in first] == ["OK", "NEEDS_MANUAL", "MISSING"]


def test_refresh_template_coverage_marks_duplicate_category_ownership_as_review() -> None:
    expected = [
        _expected_category(
            label="Κατηγορία Α",
            parent_category="P1",
            leaf_category="L1",
            sub_category=None,
            category_path="P1 > L1 > -",
        ),
    ]
    observed = [
        _observed_template(
            template_id="active_a",
            template_file="active_a.json",
            category_path="P1 > L1 > -",
            examples=("https://example.test/product-a",),
        ),
        _observed_template(
            template_id="active_b",
            template_file="active_b.json",
            category_path="P1 > L1 > -",
            examples=("https://example.test/product-b",),
        ),
    ]

    rows = assess_template_coverage(expected, observed)

    assert rows == [
        {
            "CTA Leaf Category": "Κατηγορία Α",
            "File": "active_a.json<br>active_b.json",
            "Status": "REVIEW",
            "Electronet Examples": "https://example.test/product-a<br>https://example.test/product-b",
            "_sort_path": "P1 > L1 > -",
        }
    ]


def test_refresh_template_coverage_keeps_unique_labels_compact() -> None:
    expected = [
        _expected_category(
            label="Smartphones",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Smartphones",
            sub_category=None,
            category_path="ΤΗΛΕΦΩΝΙΑ > Smartphones > -",
        ),
        _expected_category(
            label="Tablets",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Tablets",
            sub_category=None,
            category_path="ΤΗΛΕΦΩΝΙΑ > Tablets > -",
        ),
    ]

    rows = assess_template_coverage(expected, [])

    assert [row["CTA Leaf Category"] for row in rows] == ["Smartphones", "Tablets"]


def test_refresh_template_coverage_disambiguates_branch_collisions_deterministically() -> None:
    expected = [
        _expected_category(
            label="Android",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Smartphones",
            sub_category="Android",
            category_path="ΤΗΛΕΦΩΝΙΑ > Smartphones > Android",
        ),
        _expected_category(
            label="iOS",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Smartphones",
            sub_category="iOS",
            category_path="ΤΗΛΕΦΩΝΙΑ > Smartphones > iOS",
        ),
        _expected_category(
            label="Android",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Tablets",
            sub_category="Android",
            category_path="ΤΗΛΕΦΩΝΙΑ > Tablets > Android",
        ),
        _expected_category(
            label="iOS",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Tablets",
            sub_category="iOS",
            category_path="ΤΗΛΕΦΩΝΙΑ > Tablets > iOS",
        ),
    ]
    observed = [
        _observed_template(
            template_id="android_phone",
            template_file="android_phone.json",
            category_path="ΤΗΛΕΦΩΝΙΑ > Smartphones > Android",
            examples=("https://example.test/android-phone-1",),
        ),
        _observed_template(
            template_id="ios_tablet",
            template_file="ios_tablet.json",
            category_path="ΤΗΛΕΦΩΝΙΑ > Tablets > iOS",
            examples=("https://example.test/ios-tablet-1",),
        ),
    ]

    first = assess_template_coverage(expected, observed)
    second = assess_template_coverage(expected, observed)

    assert first == second
    assert [row["CTA Leaf Category"] for row in first] == [
        "Android [ΤΗΛΕΦΩΝΙΑ > Smartphones]",
        "iOS [ΤΗΛΕΦΩΝΙΑ > Smartphones]",
        "Android [ΤΗΛΕΦΩΝΙΑ > Tablets]",
        "iOS [ΤΗΛΕΦΩΝΙΑ > Tablets]",
    ]
    assert build_markdown_table(first) == build_markdown_table(second)


def test_refresh_template_coverage_does_not_expand_non_colliding_rows_when_some_labels_collide() -> None:
    expected = [
        _expected_category(
            label="Android",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Smartphones",
            sub_category="Android",
            category_path="ΤΗΛΕΦΩΝΙΑ > Smartphones > Android",
        ),
        _expected_category(
            label="Android",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Tablets",
            sub_category="Android",
            category_path="ΤΗΛΕΦΩΝΙΑ > Tablets > Android",
        ),
        _expected_category(
            label="Windows",
            parent_category="ΤΗΛΕΦΩΝΙΑ",
            leaf_category="Tablets",
            sub_category="Windows",
            category_path="ΤΗΛΕΦΩΝΙΑ > Tablets > Windows",
        ),
    ]

    rows = assess_template_coverage(expected, [])

    assert [row["CTA Leaf Category"] for row in rows] == [
        "Android [ΤΗΛΕΦΩΝΙΑ > Smartphones]",
        "Android [ΤΗΛΕΦΩΝΙΑ > Tablets]",
        "Windows",
    ]
