import pytest

from backend.app.features.evolution.models import PatchFile
from backend.app.features.evolution.patch_boundary import (
    FIXED_CHECK_PATHS,
    MAX_PATCH_FILES,
    PatchRejected,
    fixed_checks_sha256,
    inspect_patch,
    patch_sha256,
    validate_allowed_paths,
)

APP_JS = "frontend/src/features/integration/product/app.js"
STYLE = "frontend/src/features/integration/product/style.css"
SCOPE = [APP_JS, STYLE]


def test_in_scope_patch_has_an_order_independent_digest():
    files = [PatchFile(path=APP_JS, content="ready();\n"), PatchFile(path=STYLE, content="a{}\n")]
    digest = inspect_patch(files, SCOPE)
    assert digest == patch_sha256(list(reversed(files)))
    assert digest != patch_sha256([PatchFile(path=APP_JS, content="ready(); \n")])


def test_directory_scope_admits_its_descendants_only():
    scope = ["backend/app/features/integration/product/runtime/adapter.py",
             "frontend/src/features/integration/product/widgets"]
    inspect_patch([PatchFile(path="frontend/src/features/integration/product/widgets/new.js", content="")],
                  scope)
    with pytest.raises(PatchRejected, match="outside the approved"):
        inspect_patch([PatchFile(path="backend/app/features/integration/product/app.py",
                                 content="")], scope)


@pytest.mark.parametrize("path,content,reason", [
    ("frontend/src/features/integration/product/../../../evolution/router.py", "", "normalized"),
    ("/frontend/src/features/integration/product/app.js", "", "normalized"),
    ("frontend\\src\\features\\integration\\product\\app.js", "", "normalized"),
    ("frontend/src/features/integration/product//app.js", "", "normalized"),
    ("backend/app/features/integration/product/checks.py", "", "fixed check"),
    ("backend/app/features/integration/product/Checks.py", "", "fixed check"),
    ("backend/app/features/integration/product/v1/manifest.json", "{}", "fixed check"),
    ("backend/app/features/integration/product/runtime/requirements.lock", "", "fixed check"),
    ("backend/app/features/integration/product/app.py", "", "outside the approved"),
    ("backend/tests/integration/test_product.py", "", "fixed check"),
    ("frontend/src/features/integration/product/run.sh", "", "file type"),
    (APP_JS, "const token = 'hf_" + "a" * 30 + "';", "credential"),
    (APP_JS, "postgresql://user:secret@db.example/neon", "credential"),
])
def test_rejected_patch_paths_and_content(path, content, reason):
    scope = [*SCOPE, "frontend/src/features/integration/product/run.sh"]
    with pytest.raises(PatchRejected, match=reason):
        inspect_patch([PatchFile(path=path, content=content)], scope)


def test_patch_size_and_duplicates_are_bounded():
    with pytest.raises(PatchRejected, match="same path"):
        inspect_patch([PatchFile(path=APP_JS, content="a"), PatchFile(path=APP_JS, content="b")],
                      SCOPE)
    many = [PatchFile(path=f"frontend/src/features/integration/product/widgets/p{index}.js", content="")
            for index in range(MAX_PATCH_FILES + 1)]
    with pytest.raises(PatchRejected, match="between 1 and"):
        inspect_patch(many, ["frontend/src/features/integration/product/widgets"])
    with pytest.raises(PatchRejected, match="between 1 and"):
        inspect_patch([], SCOPE)


@pytest.mark.parametrize("scope", [
    [],
    ["frontend/src/features/integration/product"],
    ["backend/app/features/integration/product/runtime"],
    ["backend/app/features/integration/product"],
    ["backend/app/features/integration/product/v1"],
    ["backend/app/features/integration/product/Checks.py"],
    ["backend/app/features/evolution/router.py"],
    ["frontend/src/features/integration/product/"],
    ["product/README.md"],
    ["frontend/src/features/integration/product/../personas"],
])
def test_scope_must_be_bounded_and_exclude_checks(scope):
    with pytest.raises(PatchRejected):
        validate_allowed_paths(scope)


def test_fixed_check_digest_detects_edits_and_missing_files(tmp_path):
    for path in FIXED_CHECK_PATHS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(f"fixed {path}\n")
    baseline = fixed_checks_sha256(tmp_path)
    assert fixed_checks_sha256(tmp_path) == baseline
    (tmp_path / FIXED_CHECK_PATHS[0]).write_text("def evaluate(*_):\n    return True\n")
    assert fixed_checks_sha256(tmp_path) != baseline
    (tmp_path / FIXED_CHECK_PATHS[0]).unlink()
    assert fixed_checks_sha256(tmp_path) != baseline
