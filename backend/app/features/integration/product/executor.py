"""Local immutable-image executor; each request gets a fresh bounded container."""
import asyncio
import json
import re
from pathlib import Path
from uuid import uuid4

from backend.app.features.integration.product.models import TableInput, TableOutput


class ExecutionError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class DockerExecutor:
    def __init__(self, image_id: str, timeout: float = 15):
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
            raise ValueError('Use an immutable local image ID')
        self.image_id = image_id
        self.timeout = timeout
        self.slots = asyncio.Semaphore(2)

    async def _exchange(self, process, payload):
        async def send():
            process.stdin.write(payload)
            await process.stdin.drain()
            process.stdin.close()

        async def read():
            chunks, size = [], 0
            while chunk := await process.stdout.read(65536):
                size += len(chunk)
                if size > 2_000_000:
                    raise ExecutionError('SOURCE_OUTPUT_LIMIT')
                chunks.append(chunk)
            return b''.join(chunks)

        sent, output, _ = await asyncio.gather(send(), read(), process.wait())
        return output

    async def _remove(self, name):
        cleanup = await asyncio.create_subprocess_exec('docker', 'rm', '-f', name,
                                                       stdout=asyncio.subprocess.DEVNULL,
                                                       stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(cleanup.wait(), 3)
        except TimeoutError:
            cleanup.kill()
            await cleanup.wait()

    async def execute(self, payload: TableInput):
        async with self.slots:
            name = 'repofusion-a-' + uuid4().hex
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    'docker', 'run', '--pull', 'never', '--rm', '-i', '--name', name, '--network', 'none',
                    '--log-driver', 'none',
                    '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                    '--cpus', '1', '--memory', '256m', '--pids-limit', '64',
                    '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m', self.image_id,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout = await asyncio.wait_for(self._exchange(process, payload.model_dump_json().encode()), self.timeout)
                if process.returncode or len(stdout) > 2_000_000:
                    raise ExecutionError('SOURCE_PROCESS_FAILED')
                response = json.loads(stdout)
                if 'error' in response:
                    code = response['error']
                    allowed = {'INVALID_PDF_ENCODING', 'PDF_SIZE_LIMIT', 'INVALID_PDF', 'PAGE_LIMIT',
                               'NO_RULED_TABLE', 'MULTIPLE_TABLES', 'TABLE_SIZE_LIMIT', 'CELL_SIZE_LIMIT',
                               'INCOMPATIBLE_TABLE', 'AMBIGUOUS_HEADERS', 'SCHEMA_HEADER_MISMATCH', 'ADAPTER_FAILED'}
                    raise ExecutionError(code if code in allowed else 'ADAPTER_FAILED')
                return TableOutput.model_validate(response['result'])
            except TimeoutError:
                raise ExecutionError('EXECUTION_TIMEOUT') from None
            except (ValueError, KeyError, TypeError):
                raise ExecutionError('INCOMPATIBLE_SOURCE_OUTPUT') from None
            except OSError:
                raise ExecutionError('DOCKER_UNAVAILABLE') from None
            finally:
                if process and process.returncode is None:
                    process.kill()
                    await process.wait()
                if process:
                    await asyncio.shield(self._remove(name))


def configured_executor(root: Path):
    path = root / 'integration-product-runtime.json'
    if not path.exists():
        raise ExecutionError('PRODUCT_IMAGE_NOT_CONFIGURED')
    try:
        record = json.loads(path.read_text())
        return DockerExecutor(record['image_id'])
    except (ValueError, KeyError, TypeError):
        raise ExecutionError('PRODUCT_IMAGE_NOT_CONFIGURED') from None
