"""Generic approved prototype UI boundary. A validated catalog is required before reads."""
from backend.app.features.integration.handoff import ROOT, ExecutionError, verified_handoff

PRODUCT_BOUNDARY = {f'product/ui/{name}': f'product/ui/{name}' for name in ('app.js', 'index.html', 'style.css')}
PATCHABLE_PATHS = frozenset(PRODUCT_BOUNDARY)


class BoundaryDrift(RuntimeError):
    pass


def frozen_v1_sources():
    try:
        handoff = verified_handoff()
        if not PRODUCT_BOUNDARY.keys() <= handoff.implementation_hashes.keys():
            raise ExecutionError('PROTOTYPE_BOUNDARY_NOT_FROZEN')
        return {logical: (ROOT / tracked).read_text() for logical, tracked in PRODUCT_BOUNDARY.items()}
    except (ExecutionError, OSError):
        raise BoundaryDrift('A selected, validated prototype with a frozen UI boundary is required.') from None
