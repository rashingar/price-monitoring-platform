#!/usr/bin/env python3
"""CLI tool to compare pipeline output against a reference catalog CSV.

Usage:
    python tools/catalog_diff.py --catalog-csv catalog_2026_plus.csv \
        --candidate-dir products/ --output diff_report.json
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path


def levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein distance between two strings."""
    if len(a) < len(b):
        return levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def keyword_overlap(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity of word sets from two strings."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def extract_cta_text(html: str) -> str:
    """Extract CTA text from description HTML.

    Looks for an anchor tag with border-radius: 12px in its style and
    returns the inner text.
    """
    match = re.search(r'border-radius:\s*12px[^>]*>([^<]+)</a>', html or "")
    return match.group(1).strip() if match else ""


def read_catalog_csv(path: str) -> dict[str, dict]:
    """Read the catalog CSV and return a dict keyed by model."""
    products: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row.get("model", "").strip()
            if model:
                products[model] = row
    return products


def read_candidate_csvs(directory: str) -> dict[str, dict]:
    """Read all CSV files from the candidate directory.

    Each CSV is expected to be a single-row file with headers.
    """
    products: dict[str, dict] = {}
    dir_path = Path(directory)
    for csv_file in sorted(dir_path.glob("*.csv")):
        with open(csv_file, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                model = row.get("model", "").strip()
                if model:
                    products[model] = row
    return products


def compare_field_exact(catalog_val: str, candidate_val: str) -> dict:
    """Compare two field values for exact match."""
    status = "exact" if catalog_val == candidate_val else "different"
    return {
        "catalog": catalog_val,
        "candidate": candidate_val,
        "status": status,
    }


def compare_name(catalog_val: str, candidate_val: str) -> dict:
    """Compare name fields with Levenshtein distance."""
    dist = levenshtein(catalog_val, candidate_val)
    if dist == 0:
        status = "exact"
    elif dist <= 10:
        status = "close"
    else:
        status = "different"
    return {
        "catalog": catalog_val,
        "candidate": candidate_val,
        "status": status,
        "distance": dist,
    }


def compare_meta_description(catalog_val: str, candidate_val: str) -> dict:
    """Compare meta_description with keyword overlap."""
    overlap = keyword_overlap(catalog_val, candidate_val)
    if catalog_val == candidate_val:
        status = "exact"
    elif overlap >= 0.5:
        status = "close"
    else:
        status = "different"
    return {
        "catalog": catalog_val,
        "candidate": candidate_val,
        "status": status,
        "keyword_overlap": round(overlap, 4),
    }


def build_report(
    catalog: dict[str, dict], candidates: dict[str, dict]
) -> dict:
    """Build the full diff report."""
    catalog_models = set(catalog.keys())
    candidate_models = set(candidates.keys())
    matched_models = sorted(catalog_models & candidate_models)
    catalog_only = sorted(catalog_models - candidate_models)
    candidate_only = sorted(candidate_models - catalog_models)

    # Initialize field stats
    field_stats: dict[str, dict[str, int]] = {
        "name": {"exact_match": 0, "close_match": 0, "different": 0},
        "meta_description": {"exact_match": 0, "close_match": 0, "different": 0},
        "category": {"exact_match": 0, "different": 0},
        "meta_title": {"exact_match": 0, "different": 0},
        "seo_keyword": {"exact_match": 0, "different": 0},
        "cta_text": {"exact_match": 0, "different": 0},
    }

    products = []

    for model in matched_models:
        cat_row = catalog[model]
        cand_row = candidates[model]

        fields: dict[str, dict] = {}

        # name
        name_result = compare_name(
            cat_row.get("name", ""), cand_row.get("name", "")
        )
        fields["name"] = name_result
        if name_result["status"] == "exact":
            field_stats["name"]["exact_match"] += 1
        elif name_result["status"] == "close":
            field_stats["name"]["close_match"] += 1
        else:
            field_stats["name"]["different"] += 1

        # meta_description
        meta_result = compare_meta_description(
            cat_row.get("meta_description", ""),
            cand_row.get("meta_description", ""),
        )
        fields["meta_description"] = meta_result
        if meta_result["status"] == "exact":
            field_stats["meta_description"]["exact_match"] += 1
        elif meta_result["status"] == "close":
            field_stats["meta_description"]["close_match"] += 1
        else:
            field_stats["meta_description"]["different"] += 1

        # category
        cat_result = compare_field_exact(
            cat_row.get("category", ""), cand_row.get("category", "")
        )
        fields["category"] = cat_result
        field_stats["category"][
            "exact_match" if cat_result["status"] == "exact" else "different"
        ] += 1

        # meta_title
        mt_result = compare_field_exact(
            cat_row.get("meta_title", ""), cand_row.get("meta_title", "")
        )
        fields["meta_title"] = mt_result
        field_stats["meta_title"][
            "exact_match" if mt_result["status"] == "exact" else "different"
        ] += 1

        # seo_keyword
        seo_result = compare_field_exact(
            cat_row.get("seo_keyword", ""), cand_row.get("seo_keyword", "")
        )
        fields["seo_keyword"] = seo_result
        field_stats["seo_keyword"][
            "exact_match" if seo_result["status"] == "exact" else "different"
        ] += 1

        # cta_text (extracted from description HTML)
        cat_cta = extract_cta_text(cat_row.get("description", ""))
        cand_cta = extract_cta_text(cand_row.get("description", ""))
        cta_result = compare_field_exact(cat_cta, cand_cta)
        fields["cta_text"] = cta_result
        field_stats["cta_text"][
            "exact_match" if cta_result["status"] == "exact" else "different"
        ] += 1

        products.append({"model": model, "fields": fields})

    report = {
        "summary": {
            "catalog_total": len(catalog),
            "candidate_total": len(candidates),
            "matched": len(matched_models),
            "catalog_only": catalog_only,
            "candidate_only": candidate_only,
        },
        "field_stats": field_stats,
        "products": products,
    }
    return report


def print_summary(report: dict) -> None:
    """Print a human-readable summary to stdout."""
    s = report["summary"]
    print(f"Catalog products:   {s['catalog_total']}")
    print(f"Candidate products: {s['candidate_total']}")
    print(f"Matched:            {s['matched']}")
    print(f"Catalog-only:       {len(s['catalog_only'])}")
    print(f"Candidate-only:     {len(s['candidate_only'])}")
    print()
    print("Field comparison stats:")
    print(f"  {'Field':<20} {'Exact':>6} {'Close':>6} {'Diff':>6}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}")
    for field, stats in report["field_stats"].items():
        exact = stats.get("exact_match", 0)
        close = stats.get("close_match", "-")
        diff = stats.get("different", 0)
        print(f"  {field:<20} {exact:>6} {str(close):>6} {diff:>6}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare pipeline output against a reference catalog CSV."
    )
    parser.add_argument(
        "--catalog-csv",
        required=True,
        help="Path to the reference catalog CSV file.",
    )
    parser.add_argument(
        "--candidate-dir",
        required=True,
        help="Directory containing candidate single-row CSV files.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output JSON diff report.",
    )
    args = parser.parse_args()

    catalog_path = args.catalog_csv
    candidate_dir = args.candidate_dir
    output_path = args.output

    if not os.path.isfile(catalog_path):
        print(f"Error: catalog CSV not found: {catalog_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(candidate_dir):
        print(
            f"Error: candidate directory not found: {candidate_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    catalog = read_catalog_csv(catalog_path)
    candidates = read_candidate_csvs(candidate_dir)

    report = build_report(catalog, candidates)

    print_summary(report)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
