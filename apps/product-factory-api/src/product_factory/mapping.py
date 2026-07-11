from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .category_filters import (
    CategoryFilterResolution,
    canonical_taxonomy_path,
    find_filter_category,
    load_category_filter_review_payload,
    load_category_filter_review_values,
    load_filter_map,
    resolve_category_filter_values,
)
from .characteristics_pipeline import build_characteristics_for_product
from .deterministic_fields import build_deterministic_product_fields
from .html_builders import (
    build_description_html,
    build_description_html_from_intro_and_sections,
    build_description_html_from_llm,
    build_deterministic_cta,
)
from .models import (
    CLIInput,
    ParsedProduct,
    SchemaMatchResult,
    SourceProductData,
    TaxonomyResolution,
)
from .normalize import normalize_for_match, normalize_whitespace, slugify_greek_for_seo
from .seo_identity import lock_seo_keyword
from .utils import as_decimal_string, build_additional_image_value


def derive_seo_keyword(name: str, model: str) -> str:
    if not name or not model:
        return ""
    slug = slugify_greek_for_seo(name)
    if not slug:
        return ""
    if model not in slug and not re.search(r"\d", slug):
        slug = f"{slug}-{model}"
    return slug


def serialize_meta_keywords(value: list[str] | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        keyword = str(item).strip()
        if not keyword:
            continue
        lowered = keyword.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(keyword)
    return ", ".join(out)


def normalize_meta_keywords(
    value: list[str] | str | None,
    *,
    brand: str = "",
    mpn: str = "",
) -> list[str]:
    raw_values: list[str]
    if value is None:
        raw_values = []
    elif isinstance(value, str):
        raw_values = [item.strip() for item in value.split(",") if item.strip()]
    else:
        raw_values = [str(item).strip() for item in value if str(item).strip()]

    normalized_brand = normalize_whitespace(brand)
    normalized_mpn = normalize_whitespace(mpn)
    ordered_candidates = [item for item in [normalized_brand, normalized_mpn] if item]
    ordered_candidates.extend(raw_values)

    out: list[str] = []
    seen: set[str] = set()
    for item in ordered_candidates:
        keyword = normalize_whitespace(item)
        if not keyword:
            continue
        variant_key = _meta_keyword_variant_key(keyword)
        if variant_key in seen:
            continue
        seen.add(variant_key)
        out.append(keyword)
    return out


def build_row(
    cli: CLIInput,
    parsed: ParsedProduct,
    taxonomy: TaxonomyResolution,
    schema_match: SchemaMatchResult,
    downloaded_image_count: int | None = None,
    besco_filenames_by_section: dict[int, str] | None = None,
    llm_product: dict[str, Any] | None = None,
    llm_intro_text: str | None = None,
    deterministic_presentation_sections: list[dict[str, Any]] | None = None,
    llm_presentation: dict[str, Any] | None = None,
    source_raw_html: str | None = None,
    characteristics_raw_html: str | None = None,
    characteristics_source: SourceProductData | None = None,
    model_root: Path | None = None,
    filter_map: dict[str, Any] | None = None,
    category_filter_resolver: Callable[..., CategoryFilterResolution] | None = None,
    published_seo_keyword: str = "",
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    source = parsed.source
    characteristics_source = characteristics_source or source
    cta_label = _cta_label_for_taxonomy(taxonomy)
    cta_text = _cta_text_for_taxonomy(taxonomy)
    deterministic = build_deterministic_product_fields(
        source=source,
        taxonomy=taxonomy,
        model=cli.model,
        seo_keyword_builder=derive_seo_keyword,
    )
    seo_keyword_candidate = str(
        deterministic.get("seo_keyword_candidate", deterministic.get("seo_keyword", ""))
        or ""
    )
    seo_keyword, seo_keyword_locked = lock_seo_keyword(
        seo_keyword_candidate, published_seo_keyword
    )
    deterministic["seo_keyword_candidate"] = seo_keyword_candidate
    deterministic["published_seo_keyword"] = normalize_whitespace(published_seo_keyword)
    deterministic["seo_keyword_locked"] = seo_keyword_locked
    deterministic["seo_keyword"] = seo_keyword
    if isinstance(deterministic.get("seo_identity"), dict):
        deterministic["seo_identity"] = {
            **deterministic["seo_identity"],
            "seo_keyword_candidate": seo_keyword_candidate,
            "published_seo_keyword": normalize_whitespace(published_seo_keyword),
            "seo_keyword_locked": seo_keyword_locked,
        }
    canonical_name = str(deterministic["name"])
    meta_title = str(deterministic["meta_title"])
    canonical_mpn = str(deterministic["mpn"])
    manufacturer = str(deterministic["manufacturer"])
    seo_keyword = str(deterministic["seo_keyword"])

    raw_meta_keywords = llm_product.get("meta_keywords") if llm_product else ""
    ac_profile = isinstance(deterministic.get("seo_identity"), dict) and (
        deterministic["seo_identity"].get("family") == "air_conditioner"
    )
    normalized_meta_keywords = (
        []
        if ac_profile and not raw_meta_keywords
        else normalize_meta_keywords(
            raw_meta_keywords,
            brand=str(deterministic["brand"]),
            mpn=canonical_mpn,
        )
    )

    if llm_presentation:
        description_html, desc_warnings = build_description_html_from_llm(
            product_name=canonical_name,
            model=cli.model,
            cta_url=taxonomy.cta_url,
            cta_label=cta_label,
            intro_html=str(llm_presentation.get("intro_html", "")),
            cta_text=cta_text,
            sections=list(llm_presentation.get("sections", [])),
            besco_filenames_by_section=besco_filenames_by_section,
        )
    elif llm_intro_text is not None or deterministic_presentation_sections is not None:
        description_html, desc_warnings = (
            build_description_html_from_intro_and_sections(
                product_name=canonical_name,
                model=cli.model,
                cta_url=taxonomy.cta_url,
                cta_text=cta_text,
                intro_text=str(llm_intro_text or ""),
                sections=list(deterministic_presentation_sections or []),
                besco_filenames_by_section=besco_filenames_by_section,
                presentation_source_html=source.presentation_source_html,
                presentation_source_text=source.presentation_source_text,
                base_url=source.canonical_url or source.url,
            )
        )
    else:
        description_html, desc_warnings = build_description_html(
            product_name=canonical_name,
            hero_summary=source.hero_summary,
            presentation_source_html=source.presentation_source_html,
            presentation_source_text=source.presentation_source_text,
            model=cli.model,
            sections_requested=max(int(cli.sections), 0),
            cta_url=taxonomy.cta_url,
            cta_label=cta_label,
            besco_filenames_by_section=besco_filenames_by_section,
            base_url=source.canonical_url or source.url,
        )
    warnings.extend(desc_warnings)
    characteristics_html, characteristics_diagnostics, characteristics_warnings = (
        build_characteristics_for_product(
            source=characteristics_source,
            taxonomy=taxonomy,
            schema_match=schema_match,
            raw_html=characteristics_raw_html or source_raw_html,
        )
    )
    warnings.extend(characteristics_warnings)

    final_price = cli.price
    try:
        cli_price_is_zero = float(str(cli.price)) == 0.0
    except ValueError:
        cli_price_is_zero = str(cli.price).strip() in {"", "0"}
    if cli_price_is_zero:
        final_price = 0

    category_value = ""
    if taxonomy.parent_category and taxonomy.leaf_category:
        from .taxonomy import TaxonomyResolver

        category_value = TaxonomyResolver().serialize_category(
            taxonomy, cli.boxnow, source=source
        )

    image_count_for_csv = cli.photos
    if downloaded_image_count is not None and downloaded_image_count > 0:
        image_count_for_csv = downloaded_image_count
        if downloaded_image_count < cli.photos:
            warnings.append("csv_image_count_capped_to_downloaded_gallery")

    row = {
        "model": cli.model,
        "mpn": canonical_mpn,
        "name": canonical_name,
        "description": description_html,
        "characteristics": characteristics_html,
        "category": category_value,
        "image": f"catalog/01_main/{cli.model}/{cli.model}-1.jpg",
        "additional_image": build_additional_image_value(
            cli.model, image_count_for_csv
        ),
        "manufacturer": manufacturer,
        "price": as_decimal_string(final_price),
        "quantity": "0",
        "minimum": "1",
        "subtract": "1",
        "stock_status": "Έως 30 ημέρες",
        "status": "0",
        "meta_keyword": serialize_meta_keywords(normalized_meta_keywords),
        "meta_title": meta_title,
        "meta_description": (
            str(llm_product.get("meta_description", "")).strip() if llm_product else ""
        ),
        "seo_keyword": seo_keyword,
        "product_url": (
            f"https://www.etranoulis.gr/{seo_keyword}" if seo_keyword else ""
        ),
        "related_product": "",
        "bestprice_status": str(cli.bestprice_status),
        "skroutz_status": str(cli.skroutz_status),
        "boxnow": str(cli.boxnow),
    }

    category_filter_resolution = _resolve_category_filters_for_row(
        row=row,
        source=source,
        taxonomy=taxonomy,
        model_root=model_root,
        filter_map=filter_map,
        category_filter_resolver=category_filter_resolver,
    )
    warnings.extend(category_filter_resolution.warnings)

    normalized = {
        "input": cli.to_dict(),
        "source": source.to_dict(),
        "characteristics_source": (
            characteristics_source.to_dict()
            if characteristics_source is not source
            else None
        ),
        "taxonomy": taxonomy.to_dict(),
        "schema_match": schema_match.to_dict(),
        "deterministic_product": deterministic,
        "characteristics_diagnostics": characteristics_diagnostics,
        "downloaded_gallery_count": downloaded_image_count or 0,
        "downloaded_besco_count": len(besco_filenames_by_section or {}),
        "llm_product": {
            **(llm_product or {}),
            "meta_keywords": normalized_meta_keywords,
        },
        "llm_intro_text": str(llm_intro_text or ""),
        "deterministic_presentation_sections": deterministic_presentation_sections
        or [],
        "llm_presentation": llm_presentation or {},
        "category_filters": category_filter_resolution.to_dict(),
        "csv_row": row,
    }
    return row, normalized, warnings


def _cta_label_for_taxonomy(taxonomy: TaxonomyResolution) -> str:
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Τηλεοράσεις"
    ):
        return taxonomy.leaf_category
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Κλιματιστικά"
    ):
        return taxonomy.leaf_category
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Φούρνοι Μικροκυμάτων"
    ):
        return taxonomy.leaf_category
    return taxonomy.sub_category or taxonomy.leaf_category


def _cta_text_for_taxonomy(taxonomy: TaxonomyResolution) -> str:
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Τηλεοράσεις"
    ):
        return build_deterministic_cta("fem", taxonomy.leaf_category)
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Κλιματιστικά"
    ):
        return build_deterministic_cta("neut", taxonomy.leaf_category)
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Φούρνοι Μικροκυμάτων"
    ):
        return "Δείτε περισσότερους Φούρνους Μικροκυμάτων εδώ"
    if normalize_for_match(taxonomy.leaf_category) == normalize_for_match(
        "Ανεμιστήρες"
    ):
        if normalize_for_match(taxonomy.sub_category) == normalize_for_match(
            "Ορθοστάτης"
        ):
            return "Δείτε περισσότερους Ανεμιστήρες Ορθοστάτες εδώ"
        if normalize_for_match(taxonomy.sub_category) == normalize_for_match("Οροφής"):
            return "Δείτε περισσότερους Ανεμιστήρες Οροφής εδώ"
    return build_deterministic_cta(taxonomy.gender, taxonomy.plural_label)


def _resolve_category_filters_for_row(
    *,
    row: dict[str, Any],
    source: Any,
    taxonomy: TaxonomyResolution,
    model_root: Path | None,
    filter_map: dict[str, Any] | None,
    category_filter_resolver: Callable[..., CategoryFilterResolution] | None,
) -> CategoryFilterResolution:
    taxonomy_path = canonical_taxonomy_path(taxonomy)
    if not taxonomy.category_id and not taxonomy_path:
        return CategoryFilterResolution(
            category_id="",
            taxonomy_path="",
            filter_category_found=False,
        )
    filter_map_payload = filter_map if filter_map is not None else load_filter_map()
    filter_category = find_filter_category(
        filter_map_payload,
        category_id=taxonomy.category_id,
        taxonomy_path=taxonomy_path,
    )
    if not filter_category:
        return CategoryFilterResolution(
            category_id=taxonomy.category_id,
            taxonomy_path=taxonomy_path,
            filter_category_found=False,
            warnings=["category_filter_map_entry_not_found"],
        )

    review_values: dict[str, str] = {}
    review_warnings: list[str] = []
    if model_root is not None:
        review_payload = load_category_filter_review_payload(model_root)
        if review_payload:
            if review_payload.get("load_error"):
                review_warnings.append("category_filter_review_load_failed")
            else:
                review_values = load_category_filter_review_values(model_root)
                if review_payload.get("approved") is not True:
                    review_warnings.append("category_filter_review_not_approved")

    resolver = category_filter_resolver or resolve_category_filter_values
    resolution = resolver(
        source=source,
        taxonomy=taxonomy,
        filter_category=filter_category,
        review_values=review_values,
    )
    resolution.warnings = [*review_warnings, *resolution.warnings]
    for group in resolution.groups:
        if group.emitted and group.resolved_value:
            row[f"filter_group:{group.group_name}"] = group.resolved_value
    return resolution


def _meta_keyword_variant_key(keyword: str) -> str:
    normalized = normalize_for_match(keyword)
    if not normalized:
        return ""
    tokens = []
    for token in normalized.split():
        singular = _singularize_token(token)
        tokens.append(singular or token)
    return " ".join(tokens)


def _singularize_token(token: str) -> str:
    if len(token) <= 3:
        return token
    # Align common Greek neuter singular/plural pairs such as
    # "ψυγείο" / "ψυγεία" onto the same comparison stem.
    if token.endswith("εια") and len(token) > 5:
        return token[:-1]
    if token.endswith("ειο") and len(token) > 5:
        return token[:-1]
    endings = ["ους", "ες", "οι", "ια", "ος", "ας", "ης", "α", "ο", "η", "ς", "s"]
    for ending in endings:
        if token.endswith(ending) and len(token) > len(ending) + 2:
            return token[: -len(ending)]
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    return token
