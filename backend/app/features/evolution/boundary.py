"""The generated-product boundary that C's implementer may patch, proposed for A's review.

Patch paths are logical `product/` paths. Each one maps to one tracked SourceTable v1 file.
Only the three static UI files are patchable. The adapter, runtime image, fixed checks,
evaluator and manifest stay outside the boundary, so a patch cannot change what is checked.
"""

import hashlib

from backend.app.features.integration.product.handoff import MANIFEST, ROOT, ProductHandoff

PRODUCT_BOUNDARY = {
    "product/ui/app.js": "frontend/src/features/integration/product/app.js",
    "product/ui/index.html": "frontend/src/features/integration/product/index.html",
    "product/ui/style.css": "frontend/src/features/integration/product/style.css",
}
PATCHABLE_PATHS = frozenset(PRODUCT_BOUNDARY)


class BoundaryDrift(RuntimeError):
    """The tracked v1 files no longer match the frozen manifest."""


def frozen_v1_sources() -> dict[str, str]:
    """Read v1 boundary files only when their bytes match A's frozen fingerprints."""
    handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
    sources = {}
    for logical, tracked in PRODUCT_BOUNDARY.items():
        data = (ROOT / tracked).read_bytes()
        if hashlib.sha256(data).hexdigest() != handoff.implementation_hashes.get(tracked):
            raise BoundaryDrift(f"{tracked} differs from the frozen v1 manifest.")
        sources[logical] = data.decode()
    return sources
