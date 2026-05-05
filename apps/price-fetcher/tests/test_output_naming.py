import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.io.paths import resolve_price_output_paths


def test_price_output_names_strip_fetch_suffix_before_writing_final_artifacts() -> None:
    output_dir = Path("output")
    paths = resolve_price_output_paths(
        Path("export_2026-04-02(1)_skroutz_enriched.csv"),
        output_dir,
    )

    assert paths.priced_enriched_csv == output_dir / "export_2026-04-02(1)_skroutz_enriched_with_new_price.csv"
    assert paths.price_only_csv == output_dir / "export_2026-04-02(1)_price_only.csv"
    assert paths.summary_json == output_dir / "export_2026-04-02(1)_pricing_summary.json"


def test_price_output_names_strip_bestprice_fetch_suffix_before_writing_final_artifacts() -> None:
    output_dir = Path("output")
    paths = resolve_price_output_paths(
        Path("export_2026-04-02(1)_bestprice_enriched.csv"),
        output_dir,
    )

    assert paths.priced_enriched_csv == output_dir / "export_2026-04-02(1)_bestprice_enriched_with_new_price.csv"
    assert paths.price_only_csv == output_dir / "export_2026-04-02(1)_price_only.csv"
    assert paths.summary_json == output_dir / "export_2026-04-02(1)_pricing_summary.json"
