import os


def create_dirs(path: str) -> None:
    """Create all parent directories for a given path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
