import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.source_url_agent.matching import extract_mpn_evidence, extract_name_evidence
from pricefetcher.utils.text import build_product_search_queries


def test_raw_exact_match_is_accepted() -> None:
    evidence = extract_mpn_evidence(
        "SM-S921B",
        title="Samsung Galaxy S24 SM-S921B | Skroutz.gr",
        body_text="",
    )

    assert evidence is not None
    assert evidence.fragment == "SM-S921B"
    assert evidence.source == "title"


def test_whitespace_only_normalized_match_is_accepted() -> None:
    evidence = extract_mpn_evidence(
        "AB  123",
        title="Product title",
        body_text="The exact code is ab 123 and is available now.",
    )

    assert evidence is not None
    assert evidence.fragment == "ab 123"
    assert evidence.source == "body"


def test_broader_normalization_is_rejected() -> None:
    evidence = extract_mpn_evidence(
        "WH-1000XM5",
        title="Sony WH 1000XM5 | Skroutz.gr",
        body_text="",
    )

    assert evidence is None


def test_name_evidence_matches_greek_variant_words_against_english_row_name() -> None:
    evidence = extract_name_evidence(
        "Miele Guard M1 Standard Red",
        "Miele Guard M1 Standard Ηλεκτρική Σκούπα 890W με Σακούλα 4.5lt Κόκκινη | BestPrice.gr",
    )

    assert evidence is not None
    assert evidence.token_ratio >= 0.75
    assert "red" in evidence.matched_tokens


def test_build_product_search_queries_adds_a_clean_normalized_query() -> None:
    queries = build_product_search_queries(
        "Miele SNRF3 – Σκούπα Ηλεκτρική Boost CX1 125 Edition Lotus White (12433990)",
    )

    assert queries[0] == "Miele SNRF3 – Σκούπα Ηλεκτρική Boost CX1 125 Edition Lotus White (12433990)"
    assert "Miele boost cx1 125 edition lotus white" in queries
