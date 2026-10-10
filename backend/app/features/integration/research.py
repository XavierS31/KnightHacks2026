"""Explicit local research CLI; real evidence files stay under ignored artifacts/."""
import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from backend.app.features.integration.proposals import Extraction, IntegrationInference
from backend.app.features.integration.sources import SourceDocument, SourceSnapshot
from backend.app.shared.inference import InferenceError
from backend.app.shared.settings import Settings


def prepare_snapshots(root):
    existing = root / 'research-snapshots.json'
    if existing.exists():
        # A retained interpretation refers to this exact snapshot identity.
        return [SourceSnapshot.model_validate(item) for item in json.loads(existing.read_text())]
    records = json.loads((root / 'candidate-readmes.json').read_text())
    licenses = {record['name']: record for record in json.loads(
        (root / 'candidate-license-evidence.json').read_text())}
    snapshots = []
    for record in records:
        documents = []
        for kind, item in [('readme', record), ('license', licenses.get(record['name']))]:
            if not item or item.get('result', {}).get('isError'):
                continue
            data = item['result']['structuredContent']
            text = data.get('content')
            if not isinstance(text, str):
                continue
            path = item.get('path', 'LICENSE' if kind == 'license' else 'README.md')
            documents.append(SourceDocument(
                kind=kind, reference=f"https://github.com/{record['name']}/blob/{record['commit_sha']}/{path}",
                request_reference=f"https://api.github.com/repos/{record['name']}/contents/{path}?ref={record['commit_sha']}",
                collected_at=datetime.fromtimestamp((root / ('candidate-readmes.json' if kind == 'readme'
                                                              else 'candidate-license-evidence.json')).stat().st_mtime, UTC),
                path=path, blob_sha=data.get('sha'), text=text,
                content_sha256=hashlib.sha256(text.encode()).hexdigest(), truncated=True,
            ))
        snapshots.append(SourceSnapshot(
            id=uuid5(NAMESPACE_URL, f"https://github.com/{record['name'].lower()}/commit/{record['commit_sha']}"),
            repository_id=uuid5(NAMESPACE_URL, f"https://github.com/{record['name'].lower()}"),
            full_name=record['name'], commit_sha=record['commit_sha'],
            commit_reference=f"https://github.com/{record['name']}/commit/{record['commit_sha']}",
            collected_at=datetime.now(UTC), status='partial', license_spdx=None, documents=documents,
            failures=[] if any(doc.kind == 'readme' for doc in documents) else ['README unavailable'],
            limitations=['Manually collected through the connected GitHub tools at a git ls-remote HEAD commit.',
                         'Connector returned bounded line excerpts, not complete file bytes; SHA-256 hashes the captured excerpt.',
                         'Blob SHA is supplied by GitHub; full-file integrity was not independently checked here.',
                         'Document collection time is the evidence-file capture time, not an exact per-request timestamp.',
                         'Issue collection, SPDX classification and license approval remain open.',
                         'Local research artifacts are not Neon persistence or completed integrations.'],
        ))
    (root / 'research-snapshots.json').write_text(json.dumps([s.model_dump(mode='json') for s in snapshots], indent=2))
    return snapshots


async def extract_candidates(root, live):
    if not live:
        raise SystemExit('Pass --live only for an authorized inference run.')
    settings = Settings().model_copy(update={'app_mode': 'live'})
    service = IntegrationInference(settings)
    snapshots = prepare_snapshots(root)
    path = root / 'candidate-extractions.json'
    results = json.loads(path.read_text()) if path.exists() else []
    completed = {item['extraction']['full_name'] for item in results if item.get('extraction')}
    try:
        for snapshot in snapshots:
            if snapshot.full_name in completed:
                continue
            try:
                extraction = await service.extract(snapshot)
                results.append({'name': snapshot.full_name, 'status': 'completed',
                                'extraction': extraction.model_dump(mode='json')})
                print(f'{snapshot.full_name}: cited extraction completed', flush=True)
            except InferenceError as exc:
                results.append({'name': snapshot.full_name, 'status': 'failed', 'code': exc.code})
                print(f'{snapshot.full_name}: {exc.code}', flush=True)
                if exc.code in {'INTEGRATION_BUDGET_EXHAUSTED', 'INFERENCE_NOT_CONFIGURED'}:
                    break
            path.write_text(json.dumps(results, indent=2))
    finally:
        path.write_text(json.dumps(results, indent=2))
        await service.close()


async def propose_pairs(root, live):
    if not live:
        raise SystemExit('Pass --live only for an authorized inference run.')
    extractions = {item['name']: Extraction.model_validate(item['extraction'])
                   for item in json.loads((root / 'candidate-extractions.json').read_text())
                   if item.get('extraction')}
    # Hypotheses for independent research, never automatic selection.
    pairs = [('microsoft/markitdown', 'collective/icalendar'),
             ('adbar/trafilatura', 'simonw/datasette'),
             ('networkx/networkx', 'vega/altair'),
             ('simonw/sqlite-utils', 'frictionlessdata/frictionless-py')]
    service = IntegrationInference(Settings().model_copy(update={'app_mode': 'live'}))
    path = root / 'candidate-proposals.json'
    outputs = json.loads(path.read_text()) if path.exists() else []
    try:
        for pair in pairs:
            if any(item.get('pair') == list(pair) and item.get('preview') for item in outputs):
                continue
            if not all(name in extractions for name in pair):
                outputs.append({'pair': pair, 'status': 'blocked', 'code': 'MISSING_EXTRACTION'})
                continue
            try:
                result = await service.propose([extractions[name] for name in pair])
                outputs.append({'pair': pair, 'status': 'completed', 'preview': result.model_dump(mode='json')})
                print(f'{pair}: proposal hypothesis completed', flush=True)
            except InferenceError as exc:
                outputs.append({'pair': pair, 'status': 'failed', 'code': exc.code})
                print(f'{pair}: {exc.code}', flush=True)
            path.write_text(json.dumps(outputs, indent=2))
    finally:
        path.write_text(json.dumps(outputs, indent=2))
        await service.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['prepare', 'extract', 'propose'])
    parser.add_argument('--live', action='store_true')
    arguments = parser.parse_args()
    root = Settings().artifact_root
    if arguments.operation == 'prepare':
        print(f'Prepared {len(prepare_snapshots(root))} source snapshots; no inference.')
    else:
        asyncio.run((extract_candidates if arguments.operation == 'extract' else propose_pairs)(root, arguments.live))


if __name__ == '__main__':
    main()
