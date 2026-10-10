"""A's approved product boundary for implementer patches. Inspection runs before any write.

A patch is a list of whole-file replacements. It may change SourceTable implementation files that
an approved improvement names. It may never change the fixed checks, the frozen v1 record or the
pinned runtime environment, so an implementer cannot weaken what decides its own success.
"""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from backend.app.features.evolution.models import PatchFile

# The SourceTable implementation that a reviewed v2 may change. Boundary changes need A's review.
PRODUCT_ROOTS = (
    "backend/app/features/integration/product",
    "frontend/src/features/integration/product",
)
# Files that decide regression success or record v1. Their digest must not change in a patch.
FIXED_CHECK_PATHS = (
    "backend/app/features/integration/product/checks.py",
    "backend/app/features/integration/product/freeze.py",
    "backend/app/features/integration/product/handoff.py",
    "backend/app/features/integration/product/v1/manifest.json",
    "backend/app/features/integration/proof/independent.py",
    "backend/tests/integration/test_product.py",
    "backend/app/features/evolution/product_ui_check.py",
)
# The frozen v1 directory, pinned dependencies and image. None is a bounded improvement.
PROTECTED_PATHS = (
    *FIXED_CHECK_PATHS,
    "backend/app/features/integration/product/v1",
    "backend/app/features/integration/product/runtime/Dockerfile",
    "backend/app/features/integration/product/runtime/requirements.lock",
)
PATCHABLE_SUFFIXES = (".py", ".js", ".css", ".html")
MAX_PATCH_FILES = 8
MAX_FILE_BYTES = 200_000
SECRET_PATTERN = re.compile(
    r"hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|postgres(?:ql)?://[^\s:/@]+:[^\s@]+@"
)


class PatchRejected(ValueError):
    """The patch or its approved scope leaves A's boundary. Nothing was written."""


def _is_protected(path: str) -> bool:
    # Case-insensitive file systems would let Checks.py overwrite checks.py.
    folded = PurePosixPath(path.casefold())
    return any(folded.is_relative_to(item.casefold()) for item in PROTECTED_PATHS)


def _require_normal(path: str) -> None:
    pure = PurePosixPath(path)
    if ("\\" in path or pure.is_absolute() or str(pure) != path
            or any(part in {"", ".", ".."} for part in pure.parts)):
        raise PatchRejected(f"Path {path!r} is not a normalized relative path.")


def validate_allowed_paths(allowed_paths: list[str]) -> None:
    """Each scope is a product file or directory, never the whole product or a fixed check."""
    if not allowed_paths:
        raise PatchRejected("An approved improvement must name at least one product path.")
    for scope in allowed_paths:
        _require_normal(scope)
        if scope in PRODUCT_ROOTS or not any(PurePosixPath(scope).is_relative_to(root)
                                             for root in PRODUCT_ROOTS):
            raise PatchRejected(f"Scope {scope!r} is not a bounded path inside the product.")
        if _is_protected(scope) or any(PurePosixPath(item.casefold()).is_relative_to(
                scope.casefold()) for item in PROTECTED_PATHS):
            raise PatchRejected(f"Scope {scope!r} contains fixed checks or the pinned runtime.")


def patch_sha256(files: list[PatchFile]) -> str:
    canonical = json.dumps(sorted([item.path, item.content] for item in files),
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def inspect_patch(files: list[PatchFile], allowed_paths: list[str]) -> str:
    """Reject the whole patch on the first violation. Return its digest when it is in scope."""
    validate_allowed_paths(allowed_paths)
    if not files or len(files) > MAX_PATCH_FILES:
        raise PatchRejected(f"A patch must change between 1 and {MAX_PATCH_FILES} files.")
    paths = [item.path for item in files]
    if len(set(paths)) != len(paths):
        raise PatchRejected("A patch cannot list the same path twice.")
    for item in files:
        _require_normal(item.path)
        if _is_protected(item.path):
            raise PatchRejected(f"{item.path} is a fixed check, the v1 record or a pinned runtime file.")
        if not any(PurePosixPath(item.path).is_relative_to(scope) for scope in allowed_paths):
            raise PatchRejected(f"{item.path} is outside the approved improvement scope.")
        if not item.path.endswith(PATCHABLE_SUFFIXES):
            raise PatchRejected(f"{item.path} is not a patchable source file type.")
        if len(item.content.encode()) > MAX_FILE_BYTES:
            raise PatchRejected(f"{item.path} exceeds {MAX_FILE_BYTES} bytes.")
        if SECRET_PATTERN.search(item.content):
            raise PatchRejected(f"{item.path} contains a credential-like value.")
    return patch_sha256(files)


def fixed_checks_sha256(root: Path) -> str:
    """Digest of the fixed checks in one tree. A missing file counts as a change."""
    digest = hashlib.sha256()
    for path in FIXED_CHECK_PATHS:
        target = root / path
        digest.update(path.encode() + b"\0")
        digest.update(target.read_bytes() if target.is_file() else b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()
