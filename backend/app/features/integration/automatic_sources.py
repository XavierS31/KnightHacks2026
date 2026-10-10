"""Automatically select bounded, commit-pinned docs; never execute repository code."""
import re
from urllib.parse import unquote

import httpx
from fastapi import HTTPException

from backend.app.features.integration.sources import GitHubSources, SourceRequest


def documentation_paths(snapshot):
    paths = []
    for doc in snapshot.documents:
        if doc.kind != "readme":
            continue
        for href in re.findall(r"\]\(([^\s)]+)", doc.text):
            href = unquote(href.split("#")[0]).removeprefix("./")
            if (re.fullmatch(r"[A-Za-z0-9_. /-]+", href or "")
                    and href.lower().endswith((".md", ".rst", ".txt"))
                    and not any(part in {"", ".", ".."} for part in href.split("/"))
                    and len(href) <= 200
                    and not re.search(r"license|contribut|security|changelog|readme", href, re.I)):
                if href not in paths:
                    paths.append(href)
    return sorted(paths, key=lambda path: not bool(re.search(r"usage|api|feature|develop|guide", path, re.I)))[:2]


class AutomaticSources(GitHubSources):
    async def research(self, repository, token="", transport=None):
        snapshot = await self.collect(repository, SourceRequest(issue_limit=0), token, transport)
        if any('GITHUB_RATE_LIMIT' in failure for failure in snapshot.failures):
            return snapshot
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        paths = documentation_paths(snapshot)
        async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=False,
                                     transport=transport) as client:
            # One root listing finds interface manifests and docs when README links are absent.
            try:
                entries, _ = await self._json(client, f"/repos/{snapshot.full_name}/contents", {"ref": snapshot.commit_sha})
                if isinstance(entries, list):
                    available = {item.get("name") for item in entries if isinstance(item, dict) and item.get("type") == "file"}
                    manifests = [name for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod") if name in available]
                    if not paths:
                        paths = [name for name in ("USAGE.md", "API.md", "docs.md") if name in available][:2]
                    if any(isinstance(item, dict) and item.get('type') == 'dir' and item.get('name') == 'docs' for item in entries):
                        docs, _ = await self._json(client, f"/repos/{snapshot.full_name}/contents/docs", {"ref": snapshot.commit_sha})
                        if isinstance(docs, list):
                            candidates = [f"docs/{item['name']}" for item in docs if isinstance(item, dict)
                                          and item.get('type') == 'file' and isinstance(item.get('name'), str)
                                          and re.fullmatch(r"[A-Za-z0-9_. -]+\.(md|rst|txt)", item['name'], re.I)]
                            def relevance(path):
                                return (3 * len(re.findall(r"developer|api|architecture|integration|runtime|format|feature|usage|contract", path, re.I))
                                        - 3 * len(re.findall(r"install|security|contribut|changelog|background.prompt", path, re.I)))
                            paths = sorted(set([*paths, *candidates]), key=lambda path: (-relevance(path), path))[:2]
                    if manifests:
                        paths.append(manifests[0])
            except HTTPException as exc:
                snapshot.failures.append(f"Automatic documentation index: {exc.detail['code']}")
                if exc.status_code == 429:
                    snapshot.status = 'partial'
                    return snapshot
            for path in paths[:3]:
                try:
                    data, reference = await self._json(client, f"/repos/{snapshot.full_name}/contents/{path}",
                                                       {"ref": snapshot.commit_sha}, missing_ok=True)
                    if data is not None:
                        snapshot.documents.append(self._document(data, snapshot.full_name, snapshot.commit_sha,
                                                                 "documentation", reference))
                    else:
                        snapshot.failures.append(f"Automatic document unavailable: {path}")
                except HTTPException as exc:
                    snapshot.failures.append(f"Automatic document {path}: {exc.detail['code']}")
                    if exc.status_code == 429:
                        break
                except (ValueError, TypeError, KeyError, AttributeError):
                    snapshot.failures.append(f"Automatic document {path}: invalid or oversized")
        snapshot.status = "partial" if snapshot.failures else "collected"
        snapshot.limitations.append("Automatic research reads at most two docs selected from local README links/docs index and one root manifest; issues and external documentation sites are not fetched.")
        return snapshot
