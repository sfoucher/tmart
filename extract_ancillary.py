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

    print('\nMetadata:')
    for k, v in metadata.items():
        print(f'  {k}: {v}')

    # Download / read MERRA2 ancillary data
    anci = tmart.AEC.get_ancillary(metadata, username, password,
                                   atm_info_file=atm_info_file)

    print('\nAncillary data:')
    for k, v in anci.items():
        print(f'  {k}: {v}')

    out_dir = os.getcwd()

    # Write atm info file
    tmart.AEC.write_atm_info(out_dir, basename, anci, AOT=anci['AOT_MERRA2'])
    print(f'\nWrote atmosphere info to: {out_dir}/tmart_atm_info_{basename}.txt')

    # Write CSV with scalar metadata + ancillary fields
    csv_path = _write_csv(out_dir, basename, metadata, anci)
    print(f'Wrote ancillary CSV to:    {csv_path}')

    return {'metadata': metadata, 'anci': anci}


def _write_csv(out_dir, basename, metadata, anci):
    import csv, os

    csv_path = os.path.join(out_dir, f'tmart_ancillary_{basename}.csv')

    time_str = metadata.get('time', '')
    year  = time_str[:4]  if time_str else ''
    month = time_str[5:7] if time_str else ''

    row = {'year': year, 'month': month}

    # Scalar metadata fields to include (in order)
    for k in ['MGRS_tile', 'sensor', 'lat', 'lon', 'time',
              'sza', 'saa', 'vza', 'vaa']:
        row[k] = metadata.get(k, '')

    # All ancillary fields are scalar
    row.update(anci)

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)

    return csv_path


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
    args = parser.parse_args()

    username = args.username or os.environ.get('EARTHDATA_USERNAME')
    password = args.password or os.environ.get('EARTHDATA_PASSWORD')

    files = sorted(glob.glob(args.pattern))
    if not files:
        sys.exit(f'No files matched: {args.pattern}')

    print(f'Found {len(files)} file(s) matching pattern.')
    errors = []
    for f in files:
        print(f'\n{"="*60}')
        print(f'Processing: {f}')
        print('='*60)
        try:
            extract(file=f, username=username, password=password,
                    atm_info_file=args.atm_info_file)
        except SystemExit as e:
            print(f'Skipped {f}: {e}')
            errors.append((f, str(e)))

    if errors:
        print(f'\n{len(errors)} file(s) failed:')
        for f, msg in errors:
            print(f'  {f}: {msg}')
    else:
        print(f'\nAll {len(files)} file(s) processed successfully.')
