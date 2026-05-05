import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.core.price_workflow import run_price


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def test_price_pipeline_reproduces_lg_like_price_only_fixture(tmp_path: Path) -> None:
    enriched_csv = tmp_path / "LG-TVs_export_2026-04-02_skroutz_enriched.csv"
    output_dir = tmp_path / "output"
    enriched_csv.write_text(
        "model,mpn,name,price,status,skroutz_price,skroutz_url,match_status,observed_at,error_reason,price_relation,price_delta,matched_mpn\n"
        "140342,32LQ63006LA,LG TV 32,269,1,178.99,https://www.skroutz.gr/s/34338327/Product.html,matched,2026-04-07 12:00:00,,higher,90.01,32LQ63006LA\n"
        "142774,OLED65B56LA,LG TV 65,1200,1,1200.00,https://www.skroutz.gr/s/60811496/Product.html,matched,2026-04-07 12:00:01,,equal,0.00,OLED65B56LA\n"
        "999999,NOTFOUND,LG TV Missing,450,0,,,not_found,2026-04-07 12:00:02,no valid product result found,,,\n",
        encoding="utf-8-sig",
    )

    result = run_price(
        enriched_csv,
        PROJECT_ROOT / "config" / "pricing" / "default_rule.json",
        output_dir_override=str(output_dir),
    )

    priced_rows = _read_csv(result.output_paths.priced_enriched_csv)
    assert [row["new_price"] for row in priced_rows] == ["178", "1199", ""]

    price_only_rows = _read_csv(result.output_paths.price_only_csv)
    assert [row["price"] for row in price_only_rows] == ["178", "1199", "450"]

    summary = _read_json(result.output_paths.summary_json)
    assert summary["source"] == "skroutz"
    assert summary["priced_rows"] == 2
    assert summary["blank_new_price_rows"] == 1


def test_bestprice_store_positioning_pipeline_keeps_or_repositions_live_store_prices(tmp_path: Path) -> None:
    enriched_csv = tmp_path / "miele_bestprice_enriched.csv"
    output_dir = tmp_path / "output"
    enriched_csv.write_text(
        "model,mpn,price,bestprice_price,bestprice_url,match_status,observed_at,error_reason,price_relation,price_delta,matched_mpn,bestprice_best_store,bestprice_best_store_price,bestprice_next_store,bestprice_next_store_price\n"
        "339772,SOUL5,399.00,397.00,https://www.bestprice.gr/item/1/product-a.html,matched,2026-04-22 12:00:00,,higher,2.00,SOUL5,eTranoulis,397.00,Competitor A,397.20\n"
        "339774,SOUL5,560.00,578.00,https://www.bestprice.gr/item/2/product-b.html,matched,2026-04-22 12:00:01,,lower,-18.00,SOUL5,eTranoulis,578.00,Competitor B,580.00\n"
        "339775,SOUL5,510.00,498.00,https://www.bestprice.gr/item/3/product-c.html,matched,2026-04-22 12:00:02,,higher,12.00,SOUL5,Competitor C,498.00,Competitor D,505.00\n",
        encoding="utf-8-sig",
    )

    rule_config = tmp_path / "bestprice_etranoulis.json"
    rule_config.write_text(
        json.dumps(
            {
                "name": "bestprice_etranoulis",
                "rule_family": "bestprice_store_positioning",
                "rounding_mode": "keep_2dp",
                "parameters": {
                    "own_store": "eTranoulis",
                    "target_gap": "0.10",
                    "min_gap": "0.10",
                    "max_gap": "1.00",
                },
            }
        ),
        encoding="utf-8-sig",
    )

    result = run_price(
        enriched_csv,
        rule_config,
        output_dir_override=str(output_dir),
    )

    priced_rows = _read_csv(result.output_paths.priced_enriched_csv)
    assert [row["new_price"] for row in priced_rows] == ["397.00", "579.90", "497.90"]
    assert [row["bestprice_best_store"] for row in priced_rows] == ["eTranoulis", "eTranoulis", "Competitor C"]

    price_only_rows = _read_csv(result.output_paths.price_only_csv)
    assert [row["price"] for row in price_only_rows] == ["397.00", "579.90", "497.90"]
