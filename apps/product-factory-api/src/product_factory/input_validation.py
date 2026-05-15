from __future__ import annotations

import argparse
from urllib.parse import urlparse

from .models import CLIInput
from .source_detection import validate_url_scope

FAIL_MESSAGE = "Generation failed, provide 6-digit model"
SUPPORTED_URL_MESSAGE = "Input URL must be an Electronet, Skroutz, or BestPrice product URL"


def validate_input(args: argparse.Namespace) -> CLIInput:
    model = str(args.model).strip()
    if not model.isdigit() or len(model) != 6:
        raise ValueError(FAIL_MESSAGE)
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(SUPPORTED_URL_MESSAGE)
    source, scope_ok, _scope_reason = validate_url_scope(args.url)
    if not scope_ok:
        raise ValueError(SUPPORTED_URL_MESSAGE)
    gallery_url = str(getattr(args, "gallery_url", "") or "").strip() or None
    if gallery_url is not None:
        parsed_gallery_url = urlparse(gallery_url)
        if parsed_gallery_url.scheme not in {"http", "https"}:
            raise ValueError(SUPPORTED_URL_MESSAGE)
        _gallery_source, gallery_scope_ok, _gallery_scope_reason = validate_url_scope(gallery_url)
        if not gallery_scope_ok:
            raise ValueError(SUPPORTED_URL_MESSAGE)
    characteristics_url = str(getattr(args, "characteristics_url", "") or "").strip() or None
    if characteristics_url is not None:
        parsed_characteristics_url = urlparse(characteristics_url)
        if parsed_characteristics_url.scheme not in {"http", "https"}:
            raise ValueError(SUPPORTED_URL_MESSAGE)
        _characteristics_source, characteristics_scope_ok, _characteristics_scope_reason = validate_url_scope(
            characteristics_url
        )
        if not characteristics_scope_ok:
            raise ValueError(SUPPORTED_URL_MESSAGE)
    second_opencart_image_index = getattr(args, "second_opencart_image_index", None)
    if second_opencart_image_index in ("", None):
        second_opencart_image_index = None
    else:
        second_opencart_image_index = int(second_opencart_image_index)
        if second_opencart_image_index < 1:
            raise ValueError("second_opencart_image_index must be a positive integer")
    return CLIInput(
        model=model,
        url=args.url.strip(),
        photos=max(int(args.photos), 1),
        sections=max(int(args.sections), 0),
        skroutz_status=int(args.skroutz_status),
        boxnow=int(args.boxnow),
        price=args.price,
        gallery_url=gallery_url,
        characteristics_url=characteristics_url,
        second_opencart_image_index=second_opencart_image_index,
        out=args.out,
    )
