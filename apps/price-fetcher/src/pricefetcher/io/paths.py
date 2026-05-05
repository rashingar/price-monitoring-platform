"""Output-path resolution and runtime config loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_CSV_ENCODING = "utf-8-sig"
DEFAULT_RUNTIME_CONFIG_PATH = Path("config/runtime.json")


@dataclass(frozen=True)
class RuntimeConfig:
    output_dir: str = DEFAULT_OUTPUT_DIR
    csv_encoding: str = DEFAULT_CSV_ENCODING


@dataclass(frozen=True)
class PriceOutputPaths:
    priced_enriched_csv: Path
    price_only_csv: Path
    summary_json: Path


def load_runtime_config(config_path: Path = DEFAULT_RUNTIME_CONFIG_PATH) -> RuntimeConfig:
    if not config_path.exists():
        return RuntimeConfig()

    with config_path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)

    return RuntimeConfig(
        output_dir=str(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
        csv_encoding=str(payload.get("csv_encoding", DEFAULT_CSV_ENCODING)),
    )


def resolve_output_dir(cli_output_dir: str | None, runtime_config: RuntimeConfig) -> Path:
    selected = cli_output_dir or runtime_config.output_dir or DEFAULT_OUTPUT_DIR
    return Path(selected)


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_price_output_paths(input_path: Path, output_dir: Path) -> PriceOutputPaths:
    input_stem = input_path.stem
    base_name = _resolve_price_base_name(input_stem)
    return PriceOutputPaths(
        priced_enriched_csv=output_dir / f"{input_stem}_with_new_price.csv",
        price_only_csv=output_dir / f"{base_name}_price_only.csv",
        summary_json=output_dir / f"{base_name}_pricing_summary.json",
    )


def _resolve_price_base_name(input_stem: str) -> str:
    for suffix in ("_skroutz_enriched", "_bestprice_enriched"):
        if input_stem.endswith(suffix):
            return input_stem[: -len(suffix)]
    return input_stem
