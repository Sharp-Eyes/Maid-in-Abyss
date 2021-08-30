from collections.abc import Mapping as _Mapping
import re as _re
from os import walk


def deep_update(D, U, *, update_None = True, update_falsy = True):
    """Update nested dict D with keys and values from nested dict U.
    Much like Python's built-in :method:`update`, this is done in-place.
    However, unlike :method:`update`, the result is also returned."""

    if not update_falsy:
        print("falsy")
        def predicate(v): return bool(v)
    elif not update_None:
        print("noney")
        def predicate(v): return v is not None
    else:
        print("basic")
        def predicate(_): return True



    if isinstance(D, _Mapping) and isinstance(U, _Mapping):
        for k,v in U.items():

            print(v, predicate(v))
            if predicate(v):
                D[k] = deep_update(D.get(k), v, update_None=update_None, update_falsy=update_falsy)
        return D
    return U


# Extension management

from .classes import Paths

def search_all_extensions():
    for dirpath, dirnames, filenames in walk(Paths.cogs):
        for file in filenames:
            filename, ext = file.rsplit(".", 1)
            if ext != "py": continue

            ext_path = dirpath.split(Paths.root, 1)[1].replace("/", ".")
            yield f"{ext_path}.{filename}"


def search_loaded_extensions(bot, pattern):
    """Search for loaded extensions that match a given pattern"""
    
    extensions = bot.extensions
    matches = []

    for extension in extensions:
        # Match e.g. "cogs.administrative.exts" and "exts", but not e.g. "gs.administrative.exts", "xts"
        pat = r"(^|.+\.)" + pattern
        match = _re.match(pat, extension)
        if match:
            matches.append(match.group(0))

    return matches


# JSON helpers

import json as _json

def deep_update_json(path, U, *, update_None = True, update_falsy = True):
    """Deep-updates a json file with a (nested) dict U. See :func:`deep_update` for
    further explanation of function parameters. Returns the data of the json file
    after the update.
    """

    with open(path, "r+") as file:
        data = _json.load(file)
        deep_update(data, U, update_None=update_None, update_falsy=update_falsy)

        file.seek(0)
        _json.dump(data, file)
        file.truncate()

    return data