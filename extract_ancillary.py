# Extract Sentinel-2 / Landsat metadata and MERRA2 ancillary data
# without running the full adjacency-effect correction.
#
# Outputs (written next to the satellite product):
#   tmart_atm_info_<basename>.txt  -- atmosphere info for use with atm_info_file=
#   tmart_ancillary_<basename>.csv -- key metadata + ancillary values in CSV format
#
# Credentials are read from a .env file in the same directory as this script:
#   EARTHDATA_USERNAME=your_username
#   EARTHDATA_PASSWORD=your_password
#
# Usage:
#   python extract_ancillary.py <file>
#   python extract_ancillary.py <file> --atm_info_file <existing_txt>
#   python extract_ancillary.py <file> --username <u> --password <p>  # overrides .env

import argparse
import os
import sys
import tmart


def _load_env():
    """Load variables from a .env file next to this script into os.environ."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            value = value.strip().strip("'\"")
            os.environ.setdefault(key.strip(), value)


def _get_image_quality(file, sensor):
    """Extract cloud cover and image quality indicators from satellite product metadata."""
    import os, glob
    from xml.dom import minidom

    result = {
        'cloud_cover': '',
        'NODATA_PIXEL_PERCENTAGE': '',
        'AOT_RETRIEVAL_ACCURACY': '',
        'HIGH_PROBA_CLOUDS_PERCENTAGE': '',
        'THIN_CIRRUS_PERCENTAGE': '',
        'CLOUD_SHADOW_PERCENTAGE': '',
        'WATER_PERCENTAGE': '',
    }

    try:
        if sensor in ('S2A', 'S2B', 'S2C'):
            for root, dirs, files in os.walk(file):
                for fname in files:
                    if fname in ('MTD_MSIL2A.xml', 'MTD_MSIL1C.xml'):
                        xml = minidom.parse(os.path.join(root, fname))
                        def _val(tag):
                            nodes = xml.getElementsByTagName(tag)
                            return float(nodes[0].firstChild.nodeValue) if nodes else ''
                        result['cloud_cover'] = _val('Cloud_Coverage_Assessment')
                        result['NODATA_PIXEL_PERCENTAGE'] = _val('NODATA_PIXEL_PERCENTAGE')
                        result['AOT_RETRIEVAL_ACCURACY'] = _val('AOT_RETRIEVAL_ACCURACY')
                        result['HIGH_PROBA_CLOUDS_PERCENTAGE'] = _val('HIGH_PROBA_CLOUDS_PERCENTAGE')
                        result['THIN_CIRRUS_PERCENTAGE'] = _val('THIN_CIRRUS_PERCENTAGE')
                        result['CLOUD_SHADOW_PERCENTAGE'] = _val('CLOUD_SHADOW_PERCENTAGE')
                        result['WATER_PERCENTAGE'] = _val('WATER_PERCENTAGE')
                        return result
        elif sensor in ('L8', 'L9'):
            mtl_files = glob.glob(os.path.join(file, '*MTL.txt'))
            if mtl_files:
                with open(mtl_files[0]) as f:
                    for line in f:
                        parts = line.split('=')
                        if len(parts) == 2 and parts[0].strip() == 'CLOUD_COVER':
                            result['cloud_cover'] = float(parts[1].strip())
                            return result
    except Exception as e:
        print(f'  Warning: could not extract image quality: {e}')
    return result


def extract(file, username=None, password=None, atm_info_file=None):
    """Extract metadata and MERRA2 ancillary data for a Sentinel-2 or Landsat product.

    Arguments:
        file          -- Path to the satellite product (.SAFE folder/zip for S2;
                         folder for L8/L9).
        username      -- EarthData username (required unless atm_info_file is given).
        password      -- EarthData password (required unless atm_info_file is given).
        atm_info_file -- Path to an existing tmart_atm_info_*.txt to skip download.

    Returns dict with keys: metadata, anci
    """
    import os

    # Resolve input path and type
    file, file_is_dir = tmart.AEC.identify_input(file)
    if not file_is_dir:
        sys.exit('This script only supports S2/L8/L9 directory products, not ACOLITE L1R.')

    basename = os.path.basename(file).split('.')[0]

    # Read config (water-detection thresholds etc.)
    config = tmart.AEC.read_config(mask_SWIR_threshold=None)

    # Identify sensor and extract metadata
    print('\nReading image files:')
    print(file)
    sensor = tmart.AEC.identify_sensor(file)

    if sensor in ('S2A', 'S2B', 'S2C'):
        metadata = tmart.AEC.read_metadata_S2(file, config, sensor)
    elif sensor in ('L8', 'L9'):
        metadata = tmart.AEC.read_metadata_Landsat(file, config, sensor)
    else:
        sys.exit('Unrecognized sensor: ' + str(sensor))

    metadata['sensor'] = sensor
    metadata.update(_get_image_quality(file, sensor))

    print('\nMetadata:')
    for k, v in metadata.items():
        print(f'  {k}: {v}')

    # Download / read MERRA2 ancillary data
    anci = tmart.AEC.get_ancillary(metadata, username, password,
                                   atm_info_file=atm_info_file)

    print('\nAncillary data:')
    for k, v in anci.items():
        print(f'  {k}: {v}')

    return {'metadata': metadata, 'anci': anci}


def _make_row(basename, metadata, anci):
    time_str = metadata.get('time', '')
    year  = time_str[:4]  if time_str else ''
    month = time_str[5:7] if time_str else ''

    row = {'basename': basename, 'year': year, 'month': month}
    for k in ['MGRS_tile', 'sensor', 'lat', 'lon', 'time', 'cloud_cover',
              'NODATA_PIXEL_PERCENTAGE', 'AOT_RETRIEVAL_ACCURACY',
              'HIGH_PROBA_CLOUDS_PERCENTAGE', 'THIN_CIRRUS_PERCENTAGE',
              'CLOUD_SHADOW_PERCENTAGE', 'WATER_PERCENTAGE',
              'sza', 'saa', 'vza', 'vaa']:
        row[k] = metadata.get(k, '')
    row.update(anci)
    return row


def _append_csv(csv_path, row):
    import csv, os
    file_exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def _append_atm_txt(txt_path, basename, anci):
    with open(txt_path, 'a') as f:
        f.write(f'\n# {basename}\n')
        f.write("Ratio of maritime aerosol in maritime/continental mixture: {}\n".format(anci['r_maritime']))
        f.write("Aerosol angstrom exponent: {}\n".format(anci['Angstrom_exp']))
        f.write("Aerosol single scattering albedo: {}\n".format(anci['SSA']))
        f.write("AOT550: {}\n".format(anci['AOT_MERRA2']))
        f.write("Total column ozone: {} DU\n".format(anci['ozone']))
        f.write("Total precipitable water vapour: {} kg m-2\n".format(anci['water_vapour']))


if __name__ == '__main__':
    import glob

    _load_env()

    parser = argparse.ArgumentParser(
        description='Extract Sentinel-2/Landsat metadata and MERRA2 ancillary data.')
    parser.add_argument('pattern', help='Path or glob pattern to satellite product(s) '
                        '(e.g. /data/S2B_*_T18TYR_*.SAFE.zip)')
    parser.add_argument('--username', default=None, help='EarthData username (overrides .env)')
    parser.add_argument('--password', default=None, help='EarthData password (overrides .env)')
    parser.add_argument('--atm_info_file', default=None,
                        help='Path to existing tmart_atm_info_*.txt (skips download)')
    parser.add_argument('--out', default=None,
                        help='Output file stem (default: tmart_ancillary in cwd)')
    args = parser.parse_args()

    username = args.username or os.environ.get('EARTHDATA_USERNAME')
    password = args.password or os.environ.get('EARTHDATA_PASSWORD')

    files = sorted(glob.glob(args.pattern))
    if not files:
        sys.exit(f'No files matched: {args.pattern}')

    out_dir = os.getcwd()
    stem = args.out if args.out else os.path.join(out_dir, 'tmart_ancillary')
    csv_path = stem + '.csv'
    txt_path = stem + '.txt'

    # Remove existing output files so we start fresh
    for p in (csv_path, txt_path):
        if os.path.exists(p):
            os.remove(p)

    print(f'Found {len(files)} file(s) matching pattern.')
    errors = []
    for f in files:
        print(f'\n{"="*60}')
        print(f'Processing: {f}')
        print('='*60)
        try:
            result = extract(file=f, username=username, password=password,
                             atm_info_file=args.atm_info_file)
            basename = os.path.basename(f).split('.')[0]
            row = _make_row(basename, result['metadata'], result['anci'])
            _append_csv(csv_path, row)
            _append_atm_txt(txt_path, basename, result['anci'])
        except (SystemExit, Exception) as e:
            print(f'Skipped {f}: {e}')
            errors.append((f, str(e)))

    print(f'\nWrote ancillary CSV to: {csv_path}')
    print(f'Wrote atmosphere info to: {txt_path}')

    if errors:
        print(f'\n{len(errors)} file(s) failed:')
        for f, msg in errors:
            print(f'  {f}: {msg}')
    else:
        print(f'\nAll {len(files)} file(s) processed successfully.')
