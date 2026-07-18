"""
Symlink allowlist: serving through symlinks that leave the content tree.

``K0SNGIN_LINKS`` names a JSON file of string key -> string value pairs
describing the site's intended symlinks — the same file the ansible link
playbook owns (``~/web/ansible/links.json``): keys are where the links live,
values are the directories they point at. Paths are explicit: absolute, or
``~user`` form (expanded with ``os.path.expanduser``). A value that is still
relative after expansion invalidates the file — there is no implicit "whose
home?" resolution.

k0sNgin only consumes the *values*: a request may resolve outside
``K0SNGIN_TOP_LEVEL`` iff its real path lands under one of the resolved
targets. ``Path.resolve()`` follows every link in a chain, so a nested
symlink inside an allowed target that points elsewhere resolves outside
every allowed root and is refused — no separate escape audit is needed.
"""

import json
import os
import pathlib

from .path import TOP_LEVEL_DIR


def load_link_targets(links_file) -> list:
    """Resolved allowed target roots from a links JSON file.

    The file must contain a JSON object of string -> string pairs; anything
    else — missing file, invalid JSON, a non-string value — disables the
    allowlist (with a warning) rather than taking the site down.
    """
    if not links_file:
        return []
    try:
        with open(links_file) as f:
            links = json.load(f)
    except (OSError, ValueError) as e:
        print(f"K0SNGIN_LINKS: cannot read {links_file}: {e}")  # TODO: log this
        return []
    if not isinstance(links, dict) or not all(
            isinstance(value, str) for value in links.values()):
        print(f"K0SNGIN_LINKS: {links_file} must be a JSON object of"
              " string key-value pairs; ignoring it")  # TODO: log this
        return []
    targets = []
    for value in links.values():
        target = pathlib.Path(os.path.expanduser(value))
        if not target.is_absolute():
            print(f"K0SNGIN_LINKS: value {value!r} is not absolute"
                  " (use an absolute path or ~user form);"
                  f" ignoring {links_file}")  # TODO: log this
            return []
        targets.append(target.resolve())
    return targets


ALLOWED_LINK_TARGETS = load_link_targets(os.environ.get("K0SNGIN_LINKS"))


def is_allowed(resolved_path: pathlib.Path) -> bool:
    """True if a fully-resolved path is inside the content tree or inside an
    allowed link target."""
    for root in (TOP_LEVEL_DIR, *ALLOWED_LINK_TARGETS):
        try:
            resolved_path.relative_to(root)
            return True
        except ValueError:
            continue
    return False
