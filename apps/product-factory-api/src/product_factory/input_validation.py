from __future__ import annotations

import argparse
from urllib.parse import urlparse

from .models import CLIInput
from .product_identity import normalize_manual_mpn
from .source_detection import SUPPORTED_URL_MESSAGE, validate_url_scope
from .status_fields import (
    DEFAULT_BESTPRICE_STATUS,
    DEFAULT_BOXNOW_STATUS,
    DEFAULT_SKR_OUTZ_STATUS,
    status_or_default,
)

FAIL_MESSAGE = "Generation failed, provide 6-digit model"


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
    raw_manual_mpn = str(getattr(args, "manual_mpn", "") or "").strip()
    manual_mpn = normalize_manual_mpn(raw_manual_mpn, internal_model=model) or None
    gallery_url = str(getattr(args, "gallery_url", "") or "").strip() or None
    if gallery_url is not None:
        parsed_gallery_url = urlparse(gallery_url)
        if parsed_gallery_url.scheme not in {"http", "https"}:
            raise ValueError(SUPPORTED_URL_MESSAGE)
        _gallery_source, gallery_scope_ok, _gallery_scope_reason = validate_url_scope(
            gallery_url
        )
        if not gallery_scope_ok:
            raise ValueError(SUPPORTED_URL_MESSAGE)
    characteristics_url = (
        str(getattr(args, "characteristics_url", "") or "").strip() or None
    )
    if characteristics_url is not None:
        parsed_characteristics_url = urlparse(characteristics_url)
        if parsed_characteristics_url.scheme not in {"http", "https"}:
            raise ValueError(SUPPORTED_URL_MESSAGE)
        (
            _characteristics_source,
            characteristics_scope_ok,
            _characteristics_scope_reason,
        ) = validate_url_scope(characteristics_url)
        if not characteristics_scope_ok:
            raise ValueError(SUPPORTED_URL_MESSAGE)
    second_opencart_image_index = getattr(args, "second_opencart_image_index", None)
    if second_opencart_image_index in ("", None):
        second_opencart_image_index = None
    else:
        second_opencart_image_index = int(second_opencart_image_index)
        if second_opencart_image_index < 1:
            raise ValueError("second_opencart_image_index must be a positive integer")
    gallery_mode = str(getattr(args, "gallery_mode", "") or "").strip().lower() or None
    if gallery_mode is not None and gallery_mode != "all":
        raise ValueError("gallery_mode must be 'all' when provided")
    return CLIInput(
        model=model,
        url=args.url.strip(),
        photos=max(int(args.photos), 1),
        sections=max(int(args.sections), 0),
        bestprice_status=status_or_default(
            getattr(args, "bestprice_status", None),
            default=DEFAULT_BESTPRICE_STATUS,
            field_name="bestprice_status",
        ),
        skroutz_status=status_or_default(
            getattr(args, "skroutz_status", None),
            default=DEFAULT_SKR_OUTZ_STATUS,
            field_name="skroutz_status",
        ),
        boxnow=status_or_default(
            getattr(args, "boxnow", None),
            default=DEFAULT_BOXNOW_STATUS,
            field_name="boxnow",
        ),
        price=args.price,
        manual_mpn=manual_mpn,
        gallery_url=gallery_url,
        characteristics_url=characteristics_url,
        second_opencart_image_index=second_opencart_image_index,
        gallery_mode=gallery_mode,
        out=args.out,
    )
