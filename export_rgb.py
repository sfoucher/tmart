# Export Sentinel-2 RGB colour composite as a Cloud Optimised GeoTIFF (COG).
#
# Bands: B04 (Red), B03 (Green), B02 (Blue) at native 10 m resolution.
# Processing:
#   reflectance = DN * mult + add   (scaling factors from product metadata)
#   clip to [0, 0.3]
#   stretch to [0, 255] uint8        (0.3 → 255)
#
# Usage:
#   python export_rgb.py <file_or_pattern>
#   python export_rgb.py '/data/S2B_*_T18TYR_*.SAFE.zip'
#   python export_rgb.py '/data/S2B_*_T18TYR_*.SAFE.zip' --out /output/folder

import argparse
import glob
import os
import sys

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy


MAX_REFLECTANCE = 0.3   # clip ceiling before 8-bit stretch


def export_rgb(file, out_dir=None, max_reflectance=MAX_REFLECTANCE):
    """Export a single Sentinel-2 product as a COG RGB GeoTIFF.

    Arguments:
        file    -- Path to .SAFE folder or .SAFE.zip.
        out_dir -- Directory for output file (default: cwd).

    Returns the path to the written COG.
    """
    import tmart

    if out_dir is None:
        out_dir = os.getcwd()

    # Resolve path (unzip if needed)
    file, file_is_dir = tmart.AEC.identify_input(file)
    if not file_is_dir:
        sys.exit('Only S2 .SAFE products are supported (not ACOLITE L1R).')

    sensor = tmart.AEC.identify_sensor(file)
    if sensor not in ('S2A', 'S2B', 'S2C'):
        sys.exit(f'Expected Sentinel-2, got: {sensor}')

    config  = tmart.AEC.read_config(mask_SWIR_threshold=None)
    metadata = tmart.AEC.read_metadata_S2(file, config, sensor)

    basename = os.path.basename(file).split('.')[0]
    out_path = os.path.join(out_dir, f'{basename}_RGB.tif')

    rgb_bands = [('B04', 'Red'), ('B03', 'Green'), ('B02', 'Blue')]
    arrays, profile = [], None

    for band_key, label in rgb_bands:
        jp2_path = metadata[band_key]
        mult     = metadata[f'{band_key}_mult']
        add      = metadata[f'{band_key}_add']

        print(f'  Reading {label} ({band_key}): {os.path.basename(jp2_path)}')

        with rasterio.open(jp2_path) as src:
            if profile is None:
                profile = src.profile.copy()
            dn = src.read(1).astype(np.float32)

        # DN → reflectance → clip → uint8
        refl = dn * mult + add
        refl = np.clip(refl, 0.0, max_reflectance)
        uint8 = (refl / max_reflectance * 255).astype(np.uint8)
        arrays.append(uint8)

    # Write temp GeoTIFF with overviews, then copy to COG
    tmp_path = out_path + '.tmp.tif'
    profile.update(
        driver='GTiff',
        dtype='uint8',
        count=3,
        compress='deflate',
        tiled=True,
        blockxsize=512,
        blockysize=512,
        photometric='RGB',
    )
    # Remove jp2-specific keys that rasterio may have carried over
    for key in ('REVERSIBLE', 'QUALITY'):
        profile.pop(key, None)

    print(f'\nWriting temporary GeoTIFF and building overviews...')
    with rasterio.open(tmp_path, 'w', **profile) as dst:
        for i, arr in enumerate(arrays, start=1):
            dst.write(arr, i)
        dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
        dst.update_tags(ns='rio_overview', resampling='average')

    print(f'Converting to COG: {out_path}')
    rio_copy(tmp_path, out_path, driver='GTiff',
             copy_src_overviews=True, compress='deflate',
             tiled=True, blockxsize=512, blockysize=512)
    os.remove(tmp_path)

    print(f'Done: {out_path}')
    return out_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Export Sentinel-2 RGB COG GeoTIFF.')
    parser.add_argument('pattern', help='Path or glob pattern to .SAFE or .SAFE.zip product(s)')
    parser.add_argument('--out', default=None,
                        help='Output directory (default: current working directory)')
    parser.add_argument('--max-reflectance', type=float, default=MAX_REFLECTANCE,
                        help=f'Reflectance clip ceiling before 8-bit stretch (default: {MAX_REFLECTANCE})')
    args = parser.parse_args()

    files = sorted(glob.glob(args.pattern))
    if not files:
        sys.exit(f'No files matched: {args.pattern}')

    out_dir = args.out or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    print(f'Found {len(files)} file(s).')
    errors = []
    for f in files:
        print(f'\n{"="*60}')
        print(f'Processing: {f}')
        print('='*60)
        try:
            export_rgb(f, out_dir=out_dir, max_reflectance=args.max_reflectance)
        except (SystemExit, Exception) as e:
            print(f'Skipped {f}: {e}')
            errors.append((f, str(e)))

    if errors:
        print(f'\n{len(errors)} file(s) failed:')
        for f, msg in errors:
            print(f'  {f}: {msg}')
    else:
        print(f'\nAll {len(files)} file(s) processed successfully.')
