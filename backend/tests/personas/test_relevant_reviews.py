"""Invented HTTP records verify bounded intake, never establish real source evidence."""

import httpx
import pytest

from backend.app.features.personas.relevant_reviews import collect_public_issue
from backend.app.features.personas.review_corpus import ReviewSourceError


async def collect(handler, repository="jsvine/pdfplumber", number=311):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await collect_public_issue(
            repository, number, software_context="Invented test context",
            selection_context="Invented test selection", access_basis="Test-only access basis",
            client=client,
        )


def record(**overrides):
    return {
        "number": 311, "html_url": "https://github.com/jsvine/pdfplumber/issues/311",
        "created_at": "2020-11-12T10:00:00Z", "body": "Invented  report\nfor unit tests.",
        "user": {"login": "never-retained"}, **overrides,
    }


@pytest.mark.asyncio
async def test_fixed_endpoint_and_no_author_retention():
    def handler(request):
        assert str(request.url) == "https://api.github.com/repos/jsvine/pdfplumber/issues/311"
        assert "authorization" not in request.headers
        return httpx.Response(200, json=record())
    source = await collect(handler)
    assert source.source_text == "Invented report for unit tests."
    assert source.external_id == "jsvine/pdfplumber#311"
    assert "never-retained" not in source.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"number": True}, {"number": 312}, {"html_url": "https://evil.example/issues/311"},
    {"pull_request": {}}, {"body": None}, {"body": "  "},
    {"created_at": "not-a-date"}, {"created_at": "2020-11-12T10:00:00"},
])
async def test_reject_invalid_identity_body_and_time(changes):
    with pytest.raises(ReviewSourceError):
        await collect(lambda _: httpx.Response(200, json=record(**changes)))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 410, 302, 429, 500])
async def test_unavailable_and_http_failures_are_safe(status):
    with pytest.raises(ReviewSourceError) as failure:
        await collect(lambda _: httpx.Response(status, text="untrusted remote error"))
    assert "untrusted" not in str(failure.value)


@pytest.mark.asyncio
async def test_reject_oversized_response():
    with pytest.raises(ReviewSourceError, match="SOURCE_TOO_LARGE"):
        await collect(lambda _: httpx.Response(200, content=b"x" * 65537))


@pytest.mark.asyncio
@pytest.mark.parametrize("repository,number", [("other/repo", 1), ("../jsvine", 1),
                                                        ("jsvine/pdfplumber", True)])
async def test_invalid_source_never_sends(repository, number):
    def handler(_):
        pytest.fail("Invalid source caused network access")
    with pytest.raises(ReviewSourceError, match="INVALID_ISSUE_ID"):
        await collect(handler, repository, number)
