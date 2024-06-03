import os
from shutil import rmtree


def remove_directory(directory: str):
    if os.path.isdir(directory):
        rmtree(directory)


def create_dirs(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
