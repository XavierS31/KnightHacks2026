import { execFileSync } from 'node:child_process'
import { readFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const temp = mkdtempSync(join(tmpdir(), 'repofusion-contracts-'))
try {
  const target = join(temp, 'types.ts')
  execFileSync(process.execPath, ['node_modules/openapi-typescript/bin/cli.js', '../shared/openapi.json', '-o', target], { stdio: 'inherit' })
  if (readFileSync(target, 'utf8') !== readFileSync('src/shared/api-types.ts', 'utf8')) {
    throw new Error('Generated TypeScript drift: run npm run generate:api')
  }
  console.log('Generated TypeScript contracts match OpenAPI.')
} finally {
  rmSync(temp, { recursive: true, force: true })
}
