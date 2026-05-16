from __future__ import annotations

from ecommerce.source_capture.types import VendorDefinition


VENDOR_DEFINITIONS: tuple[VendorDefinition, ...] = (
    VendorDefinition(
        slug="electronet",
        name="Electronet",
        base_url="https://www.electronet.gr",
        vendor_type="direct_vendor",
        active=True,
        supports_direct_product_url=True,
        supports_search=False,
        supports_xhr_capture=False,
        domains=("electronet.gr", "www.electronet.gr"),
    ),
    VendorDefinition(
        slug="skroutz",
        name="Skroutz",
        base_url="https://www.skroutz.gr",
        vendor_type="marketplace_or_aggregator",
        active=True,
        supports_direct_product_url=True,
        supports_search=True,
        supports_xhr_capture=False,
        domains=("skroutz.gr", "www.skroutz.gr"),
    ),
    VendorDefinition(
        slug="bestprice",
        name="BestPrice",
        base_url="https://www.bestprice.gr",
        vendor_type="marketplace_or_aggregator",
        active=True,
        supports_direct_product_url=True,
        supports_search=True,
        supports_xhr_capture=False,
        domains=("bestprice.gr", "www.bestprice.gr"),
    ),
    VendorDefinition(
        slug="plaisio",
        name="Plaisio",
        base_url="https://www.plaisio.gr",
        vendor_type="direct_vendor",
        active=False,
        supports_direct_product_url=True,
        supports_search=False,
        supports_xhr_capture=False,
        domains=("plaisio.gr", "www.plaisio.gr"),
    ),
    VendorDefinition(
        slug="public",
        name="Public",
        base_url="https://www.public.gr",
        vendor_type="direct_vendor",
        active=False,
        supports_direct_product_url=True,
        supports_search=False,
        supports_xhr_capture=False,
        domains=("public.gr", "www.public.gr"),
    ),
    VendorDefinition(
        slug="kotsovolos",
        name="Kotsovolos",
        base_url="https://www.kotsovolos.gr",
        vendor_type="direct_vendor",
        active=False,
        supports_direct_product_url=True,
        supports_search=False,
        supports_xhr_capture=False,
        domains=("kotsovolos.gr", "www.kotsovolos.gr"),
    ),
)

VENDORS_BY_SLUG = {vendor.slug: vendor for vendor in VENDOR_DEFINITIONS}
VENDOR_SLUG_BY_DOMAIN = {domain: vendor.slug for vendor in VENDOR_DEFINITIONS for domain in vendor.domains}
