import disnake
from disnake.ext import commands

import os
import re
import sys
from collections.abc import Mapping
from itertools import groupby
from os import walk
from typing import Any, Optional

MAIN_DIR = os.path.dirname(sys.modules["__main__"].__file__)

DEFAULT_EXT_DIR_BLACKLIST = r"__.*"
DEFAULT_EXT_FILE_BLACKLIST = r"__.*"


def all_equal(iterable):
    "Returns True if all the elements are equal to each other"
    g = groupby(iterable)
    return next(g, True) and not next(g, False)


def deep_update(D: dict, U: dict, *, update_None: bool = True, update_falsy: bool = True) -> dict:
    """Update nested dict D with keys and values from nested dict U.
    Much like Python's built-in :method:`update`, this is done in-place.
    However, unlike :method:`update`, the result is also returned.

    Parameters
    ----------
    D: :class:`dict`
        the :class:`dict` that is to be updated.
    U: :class:`dict`
        the :class:`dict` that is used to update `D`.
    update_None: :class:`bool`
        whether or not None values in U should overwrite non-None values in D.
    update_falsy: :class:`bool`
        whether or not falsy values (values that equate to False in `bool(v)`)
        should overwrite non-falsy values in D.
    """

    if not update_falsy:

        def predicate(v):
            return bool(v)

    elif not update_None:

        def predicate(v):
            return v is not None

    else:

        def predicate(_):
            return True

    if isinstance(D, Mapping) and isinstance(U, Mapping):
        for k, v in U.items():
            if predicate(v):
                D[k] = deep_update(D.get(k), v, update_None=update_None, update_falsy=update_falsy)
        return D
    return U


def nested_get(d: dict, *keys: list, ret: Any = None) -> Any:
    """Get data from a nested dict by supplying a list of keys.
    Returns :param:`ret` if nothing could be found.
    """
    if not isinstance(d, dict):
        return ret
    if len(keys) > 1:
        return nested_get(d.get(keys[0], {}), *keys[1:], ret=ret)
    return d.get(keys[0], ret)


def get_bot_color(bot: commands.Bot, guild: disnake.Guild) -> disnake.Colour:
    member = guild.get_member(bot.user.id)
    return member.top_role.color


def search_all_extensions(
    *,
    blacklisted_dirs: str = DEFAULT_EXT_DIR_BLACKLIST,
    blacklisted_files: str = DEFAULT_EXT_FILE_BLACKLIST,
):
    """Search for all modules (.py files) in the cogs folder, with optional (regex) blacklists
    for folder and file names.

    Parameters
    ----------
    blacklisted_dirs: :class:`str`
        a regex pattern that should match all directory names that are to be ignored.
        By default, ignores all folders starting with "__".
    blacklisted_files: :class:`str`
        a regex pattern that should match all file names that are to be ignored.
        By default, ignores all files starting with "__".
    """

    for dirpath, _, filenames in walk(os.path.join(MAIN_DIR, "cogs")):
        cur_dir = dirpath.rsplit("\\", 1)[1]
        if re.match(blacklisted_dirs, cur_dir):
            continue

        for file in filenames:
            filename, ext = file.rsplit(".", 1)
            if ext != "py":
                continue
            if re.match(blacklisted_files, filename):
                continue

            ext_path = os.path.relpath(dirpath, MAIN_DIR).replace(os.path.sep, ".")
            yield f"{ext_path}.{filename}"


def get_role_by_name(name: str, guild: disnake.Guild) -> Optional[disnake.Role]:
    for role in guild.roles:
        if role.name.lower() == name.lower():
            return role
    return None
