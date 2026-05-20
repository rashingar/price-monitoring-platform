from __future__ import annotations

import json
import re
from typing import Any

from ecommerce.source_capture.types import ResponseCandidate, ScoredCandidate

ANALYTICS_MARKERS = (
    "analytics",
    "gtm",
    "collect",
    "hotjar",
    "facebook",
    "doubleclick",
    "beacon",
    "zendesk",
    "zdassets",
    "sentry",
    "maps.googleapis.com",
)
PROMOTION_MARKERS = ("placements", "featured_cross_sell", "cross_sell", "sponsored")
STATIC_EXTENSIONS = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".ico",
)
PRICE_RE = re.compile(
    r"(price|amount|final_price|current_price|τιμ|€|eur)", re.IGNORECASE
)
SELLER_RE = re.compile(
    r"(seller|shop|store|merchant|καταστημα|κατάστημα|πωλητ)", re.IGNORECASE
)
AVAILABILITY_RE = re.compile(
    r"(availability|available|stock|διαθεσιμ|απόθεμα|αποθεμα)", re.IGNORECASE
)
SHIPPING_RE = re.compile(
    r"(shipping|delivery|courier|pickup|παραδοση|παράδοση|μεταφορ)", re.IGNORECASE
)
OFFERS_ENDPOINT_RE = re.compile(
    r"(product|offer|offers|offering|offerings|shop|shops|seller|sku)", re.IGNORECASE
)
BLOCKED_RE = re.compile(
    r"(just a moment|cloudflare|cf-chl|challenge-platform)", re.IGNORECASE
)


def score_response_candidate(candidate: ResponseCandidate) -> ScoredCandidate:
    body_text = _body_text(candidate)
    url = candidate.url.lower()
    content_type = candidate.content_type.lower()
    score = 0
    reasons: list[str] = []

    if _looks_json(candidate, body_text, content_type):
        score += 3
        reasons.append("+3 json")
    if PRICE_RE.search(body_text):
        score += 3
        reasons.append("+3 price fields")
    if SELLER_RE.search(body_text):
        score += 3
        reasons.append("+3 seller/shop fields")
    if AVAILABILITY_RE.search(body_text):
        score += 2
        reasons.append("+2 availability fields")
    if SHIPPING_RE.search(body_text):
        score += 2
        reasons.append("+2 shipping fields")
    if candidate.occurred_after_trigger or candidate.trigger_action:
        score += 2
        reasons.append("+2 after trigger")
    if OFFERS_ENDPOINT_RE.search(url):
        score += 1
        reasons.append("+1 product/offers endpoint")
    if "service_filtered_offerings" in url:
        score += 4
        reasons.append("+4 skroutz offerings endpoint")
    if "filter_products" in url:
        score += 4
        reasons.append("+4 skroutz filter products endpoint")
    if candidate.status is not None and candidate.status >= 400:
        score -= 2
        reasons.append("-2 error status")
    if BLOCKED_RE.search(body_text):
        score -= 4
        reasons.append("-4 blocked/challenge payload")
    if len(body_text) < 80:
        score -= 3
        reasons.append("-3 tiny payload")
    if any(marker in url for marker in ANALYTICS_MARKERS):
        score -= 5
        reasons.append("-5 analytics endpoint")
    if any(marker in url for marker in PROMOTION_MARKERS):
        score -= 4
        reasons.append("-4 promotion endpoint")
    if url.endswith(STATIC_EXTENSIONS):
        score -= 5
        reasons.append("-5 static asset")
    return ScoredCandidate(candidate=candidate, score=score, reasons=tuple(reasons))


def best_response_candidate(
    candidates: list[ResponseCandidate],
) -> ScoredCandidate | None:
    if not candidates:
        return None
    return ranked_response_candidates(candidates)[0]


def ranked_response_candidates(
    candidates: list[ResponseCandidate],
) -> list[ScoredCandidate]:
    return sorted(
        (score_response_candidate(candidate) for candidate in candidates),
        key=lambda item: item.score,
        reverse=True,
    )


def _looks_json(
    candidate: ResponseCandidate, body_text: str, content_type: str
) -> bool:
    if candidate.body_json is not None:
        return True
    if "json" in content_type:
        return True
    try:
        json.loads(body_text)
    except (TypeError, ValueError):
        return False
    return True


def _body_text(candidate: ResponseCandidate) -> str:
    if candidate.body_text:
        return candidate.body_text
    if candidate.body_json is not None:
        try:
            return json.dumps(candidate.body_json, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(candidate.body_json)
    return ""
