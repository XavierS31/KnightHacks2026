"""Shared fixed-host GitHub reads: bounded cache, request budget and quota circuit breaker."""
import hashlib
import json
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from time import time

import httpx
from fastapi import HTTPException

MAX_RESPONSE_BYTES = 2_000_000


@dataclass
class RequestBudget:
    limit: int = 90
    used: int = 0


request_budget = ContextVar('github_request_budget', default=None)
_cache = OrderedDict()
_cooldowns = OrderedDict()


def scope(client):
    # A digest separates credential scopes without storing credentials in records or cache keys.
    return hashlib.sha256(client.headers.get('authorization', '').encode()).hexdigest()


def rate_failure(response):
    headers = response.headers
    limited = response.status_code == 429 or headers.get('x-ratelimit-remaining') == '0' or 'retry-after' in headers
    if response.status_code == 403 and not limited:
        try:
            limited = 'rate limit' in response.json().get('message', '').lower()
        except (ValueError, AttributeError):
            pass
    if not limited:
        return HTTPException(403, detail={'code': 'GITHUB_FORBIDDEN', 'message': 'GitHub denied access; check repository permissions.', 'retryable': False})
    try:
        delay = max(1, int(headers.get('retry-after', '0')))
        reset = int(headers.get('x-ratelimit-reset', '0'))
        retry_at = max(time() + delay, reset) if headers.get('x-ratelimit-remaining') == '0' else time() + max(delay, 60)
    except ValueError:
        retry_at = time() + 60
    detail = {'code': 'GITHUB_RATE_LIMIT', 'message': 'GitHub quota exhausted; no automatic retry. Retry after the reported reset.',
              'retryable': True, 'retry_at': int(retry_at), 'resource': headers.get('x-ratelimit-resource', 'unknown'),
              'remaining': headers.get('x-ratelimit-remaining', 'unknown')}
    return HTTPException(429, detail=detail)


async def github_json(client, path, params=None, missing_ok=False):
    url = httpx.URL('https://api.github.com' + path, params=params)
    auth = scope(client)
    # Mock transports are isolated from production and other fixtures.
    transport = client._transport if isinstance(client._transport, httpx.MockTransport) else 0
    key = (auth, transport, str(url))
    cached = _cache.get(key)
    now = time()
    if cached and now - cached[0] < (3600 if params and params.get('ref') else 300):
        _cache.move_to_end(key)
        return json.loads(cached[2]), str(url)
    resource = 'search' if path.startswith('/search/') else 'core'
    cooldown = _cooldowns.get((auth, transport, resource))
    if cooldown and cooldown['retry_at'] > now:
        raise HTTPException(429, detail=cooldown.copy())
    budget = request_budget.get()
    if budget:
        if budget.used >= budget.limit:
            raise HTTPException(429, detail={'code': 'GITHUB_REQUEST_BUDGET', 'message': 'Study API request limit reached; no retry.', 'retryable': False})
        budget.used += 1
    headers = {'If-None-Match': cached[1]} if cached and cached[1] else {}
    try:
        async with client.stream('GET', url, headers=headers) as response:
            if response.status_code in {403, 429}:
                # Read only a bounded error body, so permission errors can be distinguished.
                error_body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    error_body.extend(chunk)
                    if len(error_body) > 8192:
                        break
                response._content = bytes(error_body[:8192])
                exc = rate_failure(response)
                if exc.status_code == 429:
                    _cooldowns[(auth, transport, resource)] = exc.detail
                    while len(_cooldowns) > 64:
                        _cooldowns.popitem(last=False)
                raise exc
            if response.status_code == 401:
                raise HTTPException(502, detail={'code': 'GITHUB_AUTH_FAILED', 'message': 'Check server-side GitHub authentication.', 'retryable': False})
            if response.status_code == 404 and missing_ok:
                return None, str(url)
            if response.status_code == 304 and cached:
                raw = cached[2]
            elif response.status_code == 200:
                chunks, size = [], 0
                async for chunk in response.aiter_bytes(chunk_size=16384):
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise HTTPException(502, detail={'code': 'GITHUB_SOURCE_TOO_LARGE', 'message': 'Response exceeds bounded extraction limit.', 'retryable': False})
                    chunks.append(chunk)
                raw = b''.join(chunks)
            else:
                raise HTTPException(502, detail={'code': 'GITHUB_SOURCE_FAILED', 'message': 'GitHub read failed.', 'retryable': False})
            payload = json.loads(raw)
            _cache[key] = (now, response.headers.get('etag', cached[1] if cached else None), raw)
            while len(_cache) > 64 or sum(len(item[2]) for item in _cache.values()) > 8_000_000:
                _cache.popitem(last=False)
            return payload, str(url)
    except httpx.RequestError:
        raise HTTPException(502, detail={'code': 'GITHUB_UNAVAILABLE', 'message': 'GitHub read unavailable.', 'retryable': True}) from None
    except ValueError:
        raise HTTPException(502, detail={'code': 'GITHUB_INVALID_RESPONSE', 'message': 'Malformed GitHub data.', 'retryable': False}) from None
