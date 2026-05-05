from __future__ import annotations

import argparse
from urllib.parse import urlparse

from .models import CLIInput
from .source_detection import validate_url_scope

FAIL_MESSAGE = "Generation failed, provide 6-digit model"


def validate_input(args: argparse.Namespace) -> CLIInput:
    model = str(args.model).strip()
    if not model.isdigit() or len(model) != 6:
        raise ValueError(FAIL_MESSAGE)
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Input URL must be an Electronet or Skroutz product URL")
    source, scope_ok, _scope_reason = validate_url_scope(args.url)
    if not scope_ok:
        raise ValueError("Input URL must be an Electronet product URL or a Skroutz product URL")
    return CLIInput(
        model=model,
        url=args.url.strip(),
        photos=max(int(args.photos), 1),
        sections=max(int(args.sections), 0),
        skroutz_status=int(args.skroutz_status),
        boxnow=int(args.boxnow),
        price=args.price,
        out=args.out,
    )
