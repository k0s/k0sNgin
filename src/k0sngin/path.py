import os
import pathlib

# Get the top-level directory from environment or use CWD
TOP_LEVEL_DIR = pathlib.Path(os.environ.get("K0SNGIN_TOP_LEVEL", os.getcwd())).resolve()

def is_subpath(path: str, base: str) -> bool:
    """Check if a path is a subpath of a base path"""
    return os.path.commonpath([path, base]) == base
