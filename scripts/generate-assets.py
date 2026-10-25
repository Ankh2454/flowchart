#!/usr/bin/env python3
"""Generate a catalog through the explicitly selected local image-job API.
Raw PNGs and resumable job receipts go to --out; no production assets are overwritten.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def api(base, path, payload=None):
    request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'} if payload else {},
                      method='POST' if payload else 'GET')
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-base', required=True, help='Explicit API origin, e.g. http://127.0.0.1:8120')
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1] / 'assets/raster/catalog.json')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', nargs='+', help='Generate only these asset IDs')
    parser.add_argument('--timeout', type=float, default=600, help='Seconds to wait per job; receipts allow resuming')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    base = args.api_base.rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment:
        parser.error('--api-base must be an HTTP(S) API origin')
    catalog = json.loads(args.catalog.read_text())
    ids = {asset['id'] for asset in catalog['assets']}
    if args.only and set(args.only) - ids:
        parser.error('Unknown asset IDs: ' + ', '.join(sorted(set(args.only) - ids)))
    assets = [asset for asset in catalog['assets'] if not args.only or asset['id'] in args.only]
    args.out.mkdir(parents=True, exist_ok=True)
    for index, asset in enumerate(assets, 1):
        name = asset['id']
        if not re.fullmatch(r'[a-z0-9-]+', name):
            raise ValueError('Unsafe asset ID')
        payload = {'kind': 'image', 'prompt': asset['prompt'], 'seed': asset['seed'], **catalog['generation']}
        receipt_path = args.out / (name + '.job.json')
        raw_path = args.out / (name + '.raw.png')
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt['payload'] != payload or receipt['apiBase'] != base:
                raise ValueError(f'{name}: request changed; use a fresh --out directory')
            job_id = receipt['jobId']
            if raw_path.exists():
                print(f'[{index}/{len(assets)}] {name}: raw image already saved', flush=True)
                continue
        else:
            if raw_path.exists():
                raise ValueError(f'{raw_path} exists without a job receipt')
            job = api(base, '/v1/jobs', payload)
            job_id = job['id']
            receipt = {'apiBase': base, 'jobId': job_id, 'payload': payload}
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        if not re.fullmatch(r'[0-9a-f]{32}', job_id):
            raise ValueError('Invalid job identifier')
        print(f'[{index}/{len(assets)}] {name}: waiting for {job_id}', flush=True)
        deadline = time.monotonic() + args.timeout
        while True:
            job = api(base, '/v1/jobs/' + job_id)
            status = job['status']
            if status == 'succeeded':
                break
            if status not in ('queued', 'running'):
                raise RuntimeError(f'{name}: {status}: {job.get("error")}')
            if time.monotonic() >= deadline:
                raise TimeoutError(f'{name}: job still {status}; rerun the same command to resume without resubmitting')
            time.sleep(2)
        with urlopen(base + '/v1/jobs/' + job_id + '/file', timeout=30) as response:
            data = response.read()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError(f'{name}: API did not return PNG data')
        raw_path.write_bytes(data)
        receipt['result'] = {key: job.get(key) for key in ('status', 'created_at', 'finished_at')}
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        print(f'[{index}/{len(assets)}] {name}: saved {len(data):,} bytes', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
