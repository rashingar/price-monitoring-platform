from __future__ import annotations

import pytest

from tools.opencart_config import compute_opencart_target_identity


def test_target_identity_is_canonical_and_sensitive_to_profile() -> None:
    first = compute_opencart_target_identity(
        store_base="HTTPS://Store.Example:443/shop/",
        admin_path="/private-admin/index.php",
        profile="SEO migration partial update",
    )
    equivalent = compute_opencart_target_identity(
        store_base="https://store.example/shop",
        admin_path="private-admin/index.php",
        profile="SEO migration partial update",
    )
    different_profile = compute_opencart_target_identity(
        store_base="https://store.example/shop",
        admin_path="private-admin/index.php",
        profile="SEO migration partial update v2",
    )

    assert first == equivalent
    assert first.startswith("opencart-target:sha256:")
    assert len(first.removeprefix("opencart-target:sha256:")) == 64
    assert different_profile != first
    assert "private-admin" not in first
    assert "SEO migration" not in first


@pytest.mark.parametrize(
    "store_base",
    [
        "https://operator:secret@store.example",
        "https://store.example?token=value",
        "https://store.example#admin",
        "file:///srv/store",
    ],
)
def test_target_identity_rejects_ambiguous_or_secret_bearing_urls(
    store_base: str,
) -> None:
    with pytest.raises(ValueError):
        compute_opencart_target_identity(
            store_base=store_base,
            admin_path="admin/index.php",
            profile="migration-profile",
        )
