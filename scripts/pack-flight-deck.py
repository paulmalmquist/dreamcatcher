"""Assemble a complete source upload using this checkout's lockfile and built SDK.

Run npm run build first. No installs, company connections, or container execution.
The resulting ZIP includes the exact SDK runtime, source JSX and dist/index.html
build instructions, not a pretend successful deployment.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from dreamcatcher.hosting import pack_source, unpack_source


def source_bundle():
    if not (ROOT / 'sdk/dist/index.js').exists():
        raise SystemExit('Run npm run build first to compile the SDK')
    sample = ROOT / 'examples/flight-deck'
    files = {str(p.relative_to(sample)): p.read_bytes() for p in sample.rglob('*') if p.is_file() and p.name != 'README.md'}
    for name in ('package.json', 'package-lock.json', 'frontend/package.json', 'sdk/package.json'):
        files[name] = (ROOT / name).read_bytes()
    for folder in ('sdk/dist', 'sdk/cli', 'sdk/contracts'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file():
                files[str(path.relative_to(ROOT))] = path.read_bytes()
    files['dreamcatcher.json'] = (ROOT / 'examples/apps/build-readiness/dreamcatcher.json').read_bytes()
    # The distributable embeds the same built SDK without any runtime npm install.
    files['server.mjs'] = (ROOT / 'sdk/templates/dashboard/server.mjs').read_text().replace("from '@dreamcatcher/sdk'", "from './sdk/dist/index.js'").encode()
    blob = pack_source(files)
    unpack_source(blob)  # The same source contract as the upload API.
    return blob


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    output = Path(parser.parse_args().output)
    with output.open('xb') as stream:
        stream.write(source_bundle())
    print(output)
