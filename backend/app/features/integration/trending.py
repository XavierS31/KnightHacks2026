"""A bounded snapshot of GitHub Trending, separate from star-sorted search."""
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from backend.app.features.integration.discovery import GitHubDiscovery, discovery_error
from backend.app.features.integration.sources import GitHubSources
from backend.app.shared.contracts import Evidence


class TrendingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_article = False
        self.in_heading = False
        self.names = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'article' and 'Box-row' in attributes.get('class', '').split():
            self.in_article = True
        if self.in_article and tag == 'h2':
            self.in_heading = True
        if self.in_article and self.in_heading and tag == 'a':
            match = re.fullmatch(r'/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/?', attributes.get('href', ''))
            if match and match[1].lower() not in {name.lower() for name in self.names}:
                self.names.append(match[1])

    def handle_endtag(self, tag):
        if tag == 'h2':
            self.in_heading = False
        if tag == 'article':
            self.in_article = self.in_heading = False


async def trending_snapshot(request, token='', transport=None):
    language = quote(request.trending_language, safe='')
    url = 'https://github.com/trending' + (f'/{language}' if language else '')
    # The GitHub API bearer token must never be sent to the HTML client.
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport) as client:
            async with client.stream('GET', url, params={'since': request.trending_period}) as response:
                if response.status_code in {403, 429}:
                    raise discovery_error(429, 'TRENDING_RATE_LIMIT', 'GitHub Trending refused the request.', True)
                if response.status_code != 200:
                    raise discovery_error(502, 'TRENDING_UNAVAILABLE', 'GitHub Trending is unavailable.', True)
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 1_000_000:
                        raise discovery_error(502, 'TRENDING_TOO_LARGE', 'Trending page exceeds the response limit.')
                    chunks.append(chunk)
                html = b''.join(chunks).decode('utf-8')
                reference = str(response.request.url)
    except httpx.RequestError as exc:
        raise discovery_error(502, 'TRENDING_UNAVAILABLE', 'GitHub Trending is unavailable.', True) from exc
    except UnicodeDecodeError:
        raise discovery_error(502, 'TRENDING_INVALID_RESPONSE', 'GitHub Trending returned unsupported text.') from None
    parser = TrendingParser()
    parser.feed(html)
    if not parser.names:
        raise discovery_error(502, 'TRENDING_INVALID_RESPONSE', 'No verifiable repository rows found; the page may be empty or changed.')
    collected = datetime.now(UTC)
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    repositories = []
    async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=False,
                                 transport=transport) as client:
        for rank, name in enumerate(parser.names[:request.limit], start=1):
            metadata, metadata_url = await GitHubSources()._json(client, f'/repos/{name}')
            try:
                if metadata.get('fork') is not False or metadata.get('archived') is not False:
                    continue
                if metadata['full_name'].lower() != name.lower():
                    raise ValueError('Repository mismatch')
                repo = GitHubDiscovery._repository(metadata, metadata_url, collected)
                repo = repo.model_copy(update={'discovery_mode': 'trending', 'evidence': [
                    Evidence(source='GitHub Trending snapshot', reference=reference,
                             collected_at=collected, kind='source',
                             note=f'{request.trending_period} snapshot rank {rank}; not a total-stars ranking.'),
                    Evidence(source='GitHub repository API', reference=metadata_url,
                             collected_at=collected, kind='source',
                             note='Repository metadata only; commits/interfaces/execution are unvalidated.'),
                ]})
                repositories.append(repo)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise discovery_error(502, 'TRENDING_INVALID_METADATA', 'Trending repository metadata could not be verified.') from exc
    return repositories, len(parser.names), collected, False
