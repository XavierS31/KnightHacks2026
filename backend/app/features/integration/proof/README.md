# Independent source probes

These checks run the two pinned repositories independently. They are not an adapter, generated product, or persona trial. Neither probe calls HF.

From the repository root, with Docker running:

```sh
docker build --tag repofusion-a-independent:20261010 backend/app/features/integration/proof
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 1 --memory 256m --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=16m repofusion-a-independent:20261010 pdf
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 1 --memory 256m --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=16m repofusion-a-independent:20261010 schema
```

Build context includes only this probe directory. It does not include `.env` or a host checkout. Run as UID 65534, offline, with no host mounts. The checked probes completed in under one second each; a future execution wrapper still needs a hard wall-clock timeout.

`pdf` creates a known one-page ruled PDF in memory, checks exact extracted rows and nine cells, and checks rejection of invalid PDF bytes. `schema` validates a separate known CSV, then checks rejection of an invalid integer. Frictionless uses relative scratch paths to satisfy its source-path safety rules.

The image pins both source archive commits but its base tag and transitive dependencies can change on rebuild. Capture the image ID and `pip freeze` alongside probe stdout; lock these before freezing product v1. Preserve upstream license notices when distributing the sources. Dependency-wide license review remains open.

Results and limitations: [candidate research](../../../../../docs/research/developer-a-candidates-2026-10-10.md).
