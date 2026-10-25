#!/usr/bin/env python3
"""Normalize generated flat illustrations into the approved palette and RGBA framing.
Requires Pillow and NumPy. Inspect every result: palette normalization is not an art-quality check.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageOps

# Source color anchors were measured from the accepted model calibration.
# Multiple source shades intentionally map to one exact style color.
ANCHORS = [
    ('fdfbe2', 'fffdf4'), ('aa3633', 'e95b38'), ('e56e41', 'e95b38'),
    ('084140', '203e43'), ('133032', '203e43'),
    ('608880', '639e95'), ('8baa9e', '639e95'),
    ('a9b7a5', 'c9d1c6'), ('a0b9aa', 'd7ddce'), ('becab8', 'd7ddce'),
    ('e8bb4b', 'efc64a'), ('bb932b', 'efc64a'),
]


def rgb(value):
    value = value.lstrip('#')
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def normalize(source, destination, overrides):
    im = Image.open(source).convert('RGB').filter(ImageFilter.MedianFilter(3))
    pixels = np.asarray(im, dtype=np.float32)
    corners = np.concatenate([pixels[:24, :24].reshape(-1, 3), pixels[:24, -24:].reshape(-1, 3),
                              pixels[-24:, :24].reshape(-1, 3), pixels[-24:, -24:].reshape(-1, 3)])
    background = np.median(corners, axis=0)
    pairs = ANCHORS + [(entry['source'], entry['target']) for entry in overrides]
    centers = np.array([background, *[rgb(a) for a, _ in pairs]], dtype=np.float32)
    targets = np.array([[237, 240, 232], *[rgb(b) for _, b in pairs]], dtype=np.uint8)
    labels = np.empty(pixels.shape[:2], dtype=np.uint8)
    # Process in strips so larger future images do not allocate a huge distance tensor.
    for start in range(0, pixels.shape[0], 64):
        delta = pixels[start:start + 64, :, None, :] - centers
        labels[start:start + 64] = (delta * delta).sum(-1).argmin(-1)
    # A generated backdrop may drift slightly across the canvas. Remove only its
    # border-connected color region, preserving similar colors enclosed in the object.
    distance = np.linalg.norm(pixels - background, axis=-1)
    border = np.concatenate([distance[:8].ravel(), distance[-8:].ravel(),
                             distance[:, :8].ravel(), distance[:, -8:].ravel()])
    tolerance = min(35, max(10, float(np.percentile(border, 99)) + 5))
    candidate = Image.fromarray((distance <= tolerance).astype(np.uint8) * 255)
    candidate = ImageOps.expand(candidate, border=1, fill=255)
    ImageDraw.floodfill(candidate, (0, 0), 128)
    labels[np.asarray(candidate)[1:-1, 1:-1] == 128] = 0
    # Discard model-made gray cast shadows and rebuild one consistent short shadow.
    shadow_indices = np.flatnonzero((targets == [201, 209, 198]).all(axis=1))
    foreground = (labels != 0) & ~np.isin(labels, shadow_indices)
    rgba = np.dstack([targets[labels], foreground.astype(np.uint8) * 255])
    image = Image.fromarray(rgba)
    bbox = image.getchannel('A').getbbox()
    if not bbox or bbox[0] < 3 or bbox[1] < 3 or bbox[2] > im.width - 3 or bbox[3] > im.height - 3:
        raise ValueError(f'{source.name}: background/framing needs manual review')
    crop = image.crop(bbox)
    crop.thumbnail((384, 384), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (512, 512))
    canvas.alpha_composite(crop, ((512 - crop.width) // 2, (512 - crop.height) // 2))
    shadow_alpha = Image.new('L', (512, 512))
    shadow_alpha.paste(canvas.getchannel('A'), (2, 4))
    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(1.2)).point(lambda a: round(a * .18))
    shadow = Image.new('RGBA', (512, 512), (32, 62, 67, 0))
    shadow.putalpha(shadow_alpha)
    shadow.alpha_composite(canvas)
    canvas = shadow
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, optimize=True)
    return {'file': destination.name, 'sourceBounds': bbox, 'contentSize': crop.size,
            'backgroundSample': [round(float(v), 1) for v in background]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1] / 'assets/raster/catalog.json')
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', nargs='+')
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    ids = {asset['id'] for asset in catalog['assets']}
    if args.only and set(args.only) - ids:
        parser.error('Unknown asset IDs')
    for asset in catalog['assets']:
        if args.only and asset['id'] not in args.only:
            continue
        result = normalize(args.raw / (asset['id'] + '.raw.png'), args.out / asset['file'], asset.get('paletteSamples', []))
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
