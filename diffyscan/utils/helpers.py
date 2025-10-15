import os
from shutil import rmtree


def remove_directory(directory: str) -> None:
    """
    Remove a directory and all its contents.

    Args:
        directory: Path to the directory to remove
    """
    if os.path.isdir(directory):
        rmtree(directory)


def create_dirs(path: str) -> None:
    """
    Create all parent directories for a given path.

    Args:
        path: File path for which to create parent directories
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
