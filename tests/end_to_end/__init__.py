import glob
import os


def glob_exists(*pos, strict=True, n=1):
    globexpr = os.path.join(*pos)
    file_list = glob.glob(globexpr)
    if strict and len(file_list) == n:
        return file_list[0] if len(file_list) == 1 else file_list
    elif not strict and len(file_list) > 0:
        return file_list
    else:
        print(globexpr)
        print(file_list)
        return False


DATA_PREFIX = os.path.join(os.path.dirname(__file__), 'data')


def data(*path):
    return os.path.join(DATA_PREFIX, *path)
