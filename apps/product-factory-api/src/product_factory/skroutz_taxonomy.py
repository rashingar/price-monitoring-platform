from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from .normalize import normalize_for_match, normalize_whitespace

TV_SIZE_SMALL = "Έως 32''"
TV_SIZE_MEDIUM = "33''-50''"
TV_SIZE_LARGE = "50'' & άνω"

TV_INCH_RE = re.compile(r"(?<!\d)(\d{2,3})(?=\s*(?:\"|”|''|ιντσ|inch|in\b))", re.IGNORECASE)
TV_URL_INCH_RE = re.compile(r"-(\d{2,3})(?=-|$)")
WIDTH_RE = re.compile(r"(?<!\d)(\d{2})(?:[.,]\d+)?(?=\s*(?:cm|εκ|x))", re.IGNORECASE)


@dataclass(slots=True)
class SkroutzTaxonomyHint:
    parent_category: str = ""
    leaf_category: str = ""
    sub_category: str | None = None
    breadcrumbs: list[str] = field(default_factory=list)
    source_category: str = ""
    match_type: str = ""
    matched_rule_id: str = ""
    ambiguous: bool = False
    escalation_reason: str = ""
    tv_inches: int | None = None
    category_tag_text: str = ""
    category_tag_href: str = ""
    category_tag_slug: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_category_href_slug(href: str | None) -> str:
    raw = normalize_whitespace(href)
    if not raw:
        return ""
    path = normalize_whitespace(urlparse(raw).path)
    if not path:
        return ""
    slug = path.rstrip("/").split("/")[-1]
    if slug.endswith(".html"):
        slug = slug[:-5]
    return normalize_whitespace(slug.replace("-", " "))


def serialize_source_category(
    parent_category: str,
    leaf_category: str,
    source_segments: list[str] | None = None,
) -> str:
    parent = normalize_whitespace(parent_category)
    leaf = normalize_whitespace(leaf_category)
    if not parent or not leaf:
        return ""
    parts = [parent, f"{parent}///{leaf}"]
    for segment in source_segments or []:
        normalized = normalize_whitespace(segment)
        if normalized:
            parts.append(f"{parent}///{leaf}///{normalized}")
    return ":::".join(parts)


def build_breadcrumbs(parent_category: str, leaf_category: str, sub_category: str | None = None) -> list[str]:
    crumbs = ["Αρχική", normalize_whitespace(parent_category), normalize_whitespace(leaf_category)]
    if sub_category:
        crumbs.append(normalize_whitespace(sub_category))
    return [item for item in crumbs if item]


def classify_skroutz_taxonomy(
    *,
    category_tag_text: str,
    category_tag_href: str,
    title: str,
    url: str,
    brand: str = "",
    family_key: str | None = None,
) -> SkroutzTaxonomyHint | None:
    slug = normalize_category_href_slug(category_tag_href)
    tag_norm = normalize_for_match(category_tag_text)
    slug_norm = normalize_for_match(slug)
    title_norm = normalize_for_match(title)
    url_norm = normalize_for_match(urlparse(url).path)
    context = {
        "category_tag_text": normalize_whitespace(category_tag_text),
        "category_tag_href": normalize_whitespace(category_tag_href),
        "category_tag_slug": slug,
        "tag_norm": tag_norm,
        "slug_norm": slug_norm,
        "title": normalize_whitespace(title),
        "title_norm": title_norm,
        "url": normalize_whitespace(url),
        "url_norm": url_norm,
        "family_key": family_key or "",
    }

    if family_key == "television":
        return _classify_television(context)
    if family_key == "speaker":
        return _build_hint(
            context=context,
            parent="ΕΙΚΟΝΑ & ΗΧΟΣ",
            leaf="Audio Systems",
            sub="Ηχεία",
            matched_rule_id="audio:speaker",
        )
    if family_key == "dishwasher":
        return _classify_dishwasher(context)
    if family_key == "cooker":
        return _classify_cooker(context)
    if family_key == "microwave":
        return _classify_microwave(context)
    if family_key == "refrigeration":
        return _classify_refrigeration(context)
    if family_key == "laundry":
        return _classify_laundry(context)
    if family_key == "built_in_appliance":
        return _classify_built_in_appliance(context)
    if family_key == "hood":
        return _build_hint(
            context=context,
            parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            leaf="Απορροφητήρες",
            sub=None,
            matched_rule_id="hood:leaf_only",
        )
    if family_key == "home_appliance_accessory":
        return _build_hint(
            context=context,
            parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            leaf="Αξεσουάρ Οικιακών Συσκευών",
            sub=None,
            matched_rule_id="home_appliance_accessory:leaf_only",
        )
    if family_key == "heat_pump":
        return _build_hint(
            context=context,
            parent="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            leaf="Αντλίες Θερμότητας",
            sub=None,
            matched_rule_id="heat_pump:leaf_only",
        )
    if family_key == "air_conditioner":
        return _classify_air_conditioner(context)
    if family_key == "lpg_heater":
        return _build_hint(
            context=context,
            parent="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            leaf="Θερμαντικά",
            sub="Θερμαντικά Υγραερίου",
            matched_rule_id="heating:lpg",
        )
    if _has_any(context, "tileoras", "teleorasi", "tv", "television"):
        return _classify_television(context)
    if _has_any(context, "hxeia", "icheio", "ixeio", "speaker", "karaoke"):
        return _build_hint(
            context=context,
            parent="ΕΙΚΟΝΑ & ΗΧΟΣ",
            leaf="Audio Systems",
            sub="Ηχεία",
            matched_rule_id="audio:speaker",
        )
    if _has_any(context, "aporrofit"):
        return _build_hint(
            context=context,
            parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            leaf="Απορροφητήρες",
            sub=None,
            matched_rule_id="hood:leaf_only",
        )
    if _has_any(context, "axesouar", "aksesouar", "syndetiko"):
        return _build_hint(
            context=context,
            parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            leaf="Αξεσουάρ Οικιακών Συσκευών",
            sub=None,
            matched_rule_id="home_appliance_accessory:leaf_only",
        )
    if _has_any(context, "antlia thermotitas", "heat pump"):
        return _build_hint(
            context=context,
            parent="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            leaf="Αντλίες Θερμότητας",
            sub=None,
            matched_rule_id="heat_pump:leaf_only",
        )
    if _has_any(context, "klimatist", "κλιματισ", "air condition", "btu", "inverter"):
        return _classify_air_conditioner(context)
    if _has_any(context, "mikrokym", "μικροκυμα", "microwave"):
        return _classify_microwave(context)
    if _has_any(context, "ygraeri", "υγραερι", "soba"):
        return _build_hint(
            context=context,
            parent="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            leaf="Θερμαντικά",
            sub="Θερμαντικά Υγραερίου",
            matched_rule_id="heating:lpg",
        )
    return None


def _classify_television(context: dict[str, str]) -> SkroutzTaxonomyHint:
    inches = _parse_tv_inches(context["title"], context["url"])
    if inches is None:
        return _ambiguous_hint(context, "television:size_missing", tv_inches=None)
    if inches <= 32:
        canonical_sub = TV_SIZE_SMALL
    elif inches <= 50:
        canonical_sub = TV_SIZE_MEDIUM
    else:
        canonical_sub = TV_SIZE_LARGE

    source_segments: list[str] = [canonical_sub]
    if inches == 50 and canonical_sub != TV_SIZE_LARGE:
        source_segments.append(TV_SIZE_LARGE)

    match_type = "exact_category"
    if source_segments != [canonical_sub]:
        match_type = "descendant_fallback"

    hint = _build_hint(
        context=context,
        parent="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf="Τηλεοράσεις",
        sub=canonical_sub,
        matched_rule_id="television:size_bucket",
        source_segments=source_segments,
        match_type=match_type,
    )
    hint.tv_inches = inches
    return hint


def _classify_dishwasher(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "pagou", "πάγκ", "epitrapez", "επιτραπεζ"):
        return _build_hint(
            context=context,
            parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            leaf="Πλυντήρια Πιάτων",
            sub="Επιτραπέζια",
            matched_rule_id="dishwasher:tabletop",
        )

    width = _parse_width_bucket(context["title"], context["url"])
    if width == 45:
        sub = "45cm"
    elif width == 60:
        sub = "60cm"
    else:
        return _ambiguous_hint(context, "dishwasher:width_missing")

    return _build_hint(
        context=context,
        parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf="Πλυντήρια Πιάτων",
        sub=sub,
        matched_rule_id="dishwasher:width_bucket",
    )


def _classify_air_conditioner(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "forito", "portable", "φορητ"):
        sub = "Φορητά"
        rule_id = "air_conditioner:portable"
    elif _has_any(context, "ntoulap", "ντουλαπ"):
        sub = "Ντουλάπες"
        rule_id = "air_conditioner:cabinet"
    else:
        sub = "Τοίχου"
        rule_id = "air_conditioner:wall"
    return _build_hint(
        context=context,
        parent="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf="Κλιματιστικά",
        sub=sub,
        matched_rule_id=rule_id,
    )


def _classify_cooker(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "aeri", "gas", "ygraeri", "fysikou aeriou"):
        sub = "Κουζίνες Αερίου"
        rule_id = "cooker:gas"
    elif _has_any(context, "emagi", "εμαγι"):
        sub = "Κουζίνες Εμαγιέ"
        rule_id = "cooker:enamel"
    elif _has_any(context, "keram", "ceramic", "epagog", "κεραμ", "επαγωγ"):
        sub = "Κουζίνες Κεραμικές"
        rule_id = "cooker:ceramic"
    else:
        return _ambiguous_hint(context, "cooker:type_missing")

    return _build_hint(
        context=context,
        parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf="Κουζίνες",
        sub=sub,
        matched_rule_id=rule_id,
    )


def _classify_microwave(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "grill", "γκριλ"):
        sub = "Με Grill"
        rule_id = "microwave:with_grill"
    elif _has_any(context, "without grill", "χωρις grill", "χωρίς grill"):
        sub = "Χωρίς Grill"
        rule_id = "microwave:without_grill"
    else:
        sub = None
        rule_id = "microwave:leaf_only"

    return _build_hint(
        context=context,
        parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf="Φούρνοι Μικροκυμάτων",
        sub=sub,
        matched_rule_id=rule_id,
    )


def _classify_refrigeration(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "psygeiokatapsykt", "ψυγειοκαταψυκτ"):
        sub = "Ψυγειοκαταψύκτες"
        rule_id = "refrigeration:fridge_freezer"
    elif _has_any(context, "ntoulapa", "ντουλαπα", "side by side"):
        sub = "Ψυγεία Ντουλάπες"
        rule_id = "refrigeration:side_by_side"
    elif _has_any(context, "katapsykt", "καταψυκτ"):
        sub = "Καταψύκτες"
        rule_id = "refrigeration:freezer"
    elif _has_any(context, "psygei", "ψυγει"):
        sub = "Ψυγεία"
        rule_id = "refrigeration:fridge"
    else:
        return _ambiguous_hint(context, "refrigeration:type_missing")

    return _build_hint(
        context=context,
        parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf="Ψυγεία & Καταψύκτες",
        sub=sub,
        matched_rule_id=rule_id,
    )


def _classify_laundry(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "plyntirio stegnotirio", "washer dryer", "2 in1", "2in1"):
        sub = "Πλυντήρια Στεγνωτήρια 2 in1"
        rule_id = "laundry:washer_dryer"
    elif _has_any(context, "stegnotir", "στεγνωτηρ"):
        sub = "Στεγνωτήρια Ρούχων"
        rule_id = "laundry:dryer"
    elif _has_any(context, "plyntir", "πλυντηρ"):
        sub = "Πλυντήρια Ρούχων"
        rule_id = "laundry:washing_machine"
    else:
        return _ambiguous_hint(context, "laundry:type_missing")

    return _build_hint(
        context=context,
        parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf="Πλυντήρια-Στεγνωτήρια",
        sub=sub,
        matched_rule_id=rule_id,
    )


def _classify_built_in_appliance(context: dict[str, str]) -> SkroutzTaxonomyHint:
    if _has_any(context, "plyntiri", "πλυντηρι") and _has_any(context, "piat", "πιατ"):
        sub = "Πλυντήρια Πιάτων"
        rule_id = "built_in:dishwasher"
    elif _has_any(context, "plyntiri", "πλυντηρι"):
        sub = "Πλυντήρια Ρούχων"
        rule_id = "built_in:washing_machine"
    elif _has_any(context, "psygeiokatapsykt", "ψυγειοκαταψυκτ"):
        sub = "Ψυγεία"
        rule_id = "built_in:fridge_freezer"
    elif _has_any(context, "katapsykt", "καταψυκτ"):
        sub = "Καταψύκτες"
        rule_id = "built_in:freezer"
    elif _has_any(context, "psygei", "ψυγει"):
        sub = "Ψυγεία"
        rule_id = "built_in:fridge"
    elif _has_any(context, "mikrokym", "μικροκυμα", "microwave"):
        sub = "Μικροκυμάτων"
        rule_id = "built_in:microwave"
    elif _has_any(context, "estia", "εστια"):
        sub = "Εστίες"
        rule_id = "built_in:hob"
    elif _has_any(context, "fourn", "φουρν"):
        sub = "Φούρνοι"
        rule_id = "built_in:oven"
    else:
        return _ambiguous_hint(context, "built_in:type_missing")

    return _build_hint(
        context=context,
        parent="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf="Εντοιχιζόμενες Συσκευές",
        sub=sub,
        matched_rule_id=rule_id,
    )


def _build_hint(
    *,
    context: dict[str, str],
    parent: str,
    leaf: str,
    sub: str | None,
    matched_rule_id: str,
    source_segments: list[str] | None = None,
    match_type: str = "exact_category",
) -> SkroutzTaxonomyHint:
    source_items = list(source_segments if source_segments is not None else ([sub] if sub else []))
    return SkroutzTaxonomyHint(
        parent_category=parent,
        leaf_category=leaf,
        sub_category=sub,
        breadcrumbs=build_breadcrumbs(parent, leaf, sub),
        source_category=serialize_source_category(parent, leaf, source_items),
        match_type=match_type,
        matched_rule_id=matched_rule_id,
        ambiguous=False,
        escalation_reason="",
        category_tag_text=context["category_tag_text"],
        category_tag_href=context["category_tag_href"],
        category_tag_slug=context["category_tag_slug"],
    )


def _ambiguous_hint(
    context: dict[str, str],
    reason: str,
    *,
    tv_inches: int | None = None,
) -> SkroutzTaxonomyHint:
    return SkroutzTaxonomyHint(
        ambiguous=True,
        escalation_reason=reason,
        matched_rule_id=reason,
        tv_inches=tv_inches,
        category_tag_text=context["category_tag_text"],
        category_tag_href=context["category_tag_href"],
        category_tag_slug=context["category_tag_slug"],
    )


def _has_any(context: dict[str, str], *needles: str) -> bool:
    haystacks = [context["tag_norm"], context["slug_norm"], context["title_norm"], context["url_norm"]]
    normalized_needles = [normalize_for_match(needle) for needle in needles if normalize_for_match(needle)]
    for needle in normalized_needles:
        if any(needle in haystack for haystack in haystacks):
            return True
    return False


def _parse_tv_inches(title: str, url: str) -> int | None:
    match = TV_INCH_RE.search(normalize_whitespace(title))
    if match:
        return int(match.group(1))
    path = normalize_whitespace(urlparse(url).path)
    candidates = [int(value) for value in TV_URL_INCH_RE.findall(path) if len(value) in {2, 3}]
    for value in candidates:
        if 16 <= value <= 110:
            return value
    return None


def _parse_width_bucket(title: str, url: str) -> int | None:
    text = normalize_whitespace(f"{title} {urlparse(url).path}")
    values = [int(value) for value in WIDTH_RE.findall(text)]
    for value in values:
        if value <= 45:
            return 45
        if value >= 58:
            return 60
    return None
