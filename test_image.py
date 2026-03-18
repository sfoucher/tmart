import tmart
from importlib.metadata import version

file = '/content/tmart/data/S2B_MSIL1C_20250715T153819_N0511_R011_T18TYR_20250715T191325.SAFE.zip'
username = 'sfoucher'
password = 'o$E#*78CHrpz'
print('T-Mart version: ' + str(version('tmart')))

# T-Mart uses multiprocessing, which needs to be wrapped in 'if __name__ == "__main__":' for Windows users
if __name__ == "__main__":
    tmart.AEC.run(file, username, password, overwrite=False)