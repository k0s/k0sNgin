import os

def is_subpath(path: str, base: str) -> bool:
    """Check if a path is a subpath of a base path"""
    return os.path.commonpath([path, base]) == base
