from typing import Any

import disnake
from disnake.ext import commands

from collections.abc import Mapping
import re
from os import walk


DEFAULT_EXT_DIR_BLACKLIST = r"__.*"
DEFAULT_EXT_FILE_BLACKLIST = r"__.*"


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


def nested_get(d: dict, *keys: list, ret: Any = None):
    """Get data from a nested dict by supplying a list of keys.
    Returns :param:`ret` if nothing could be found.
    """
    if len(keys) > 1:
        return nested_get(d.get(keys[0], {}), *keys[1:], ret=ret)
    return d.get(keys[0], ret)


def get_bot_color(bot: commands.Bot, guild: disnake.Guild):
    member = guild.get_member(bot.user.id)
    return member.top_role.color


def create_interaction_identifier(inter: disnake.ApplicationCommandInteraction):
    """Create a unique identifier for an interaction."""
    return "{0.data.name}{0.author.id}{0.guild.id}".format(inter)


# Extension management
from .classes import Paths


def search_all_extensions(
    *,
    blacklisted_dirs: str = DEFAULT_EXT_DIR_BLACKLIST,
    blacklisted_files: str = DEFAULT_EXT_FILE_BLACKLIST
):
    """Search for all modules (.py files) in the cogs folder, with optional (regex) blacklists
    for folder and file names.

    Parameters
    ----------
    blacklisted_dirs: :class:`str`
        a regex pattern that should match all directory names that are to be ignored.
    blacklisted_files: :class:`str`
        a regex pattern that should match all file names that are to be ignored.
    """

    for dirpath, _, filenames in walk(Paths.cogs):
        cur_dir = dirpath.rsplit("\\", 1)[1]
        if re.match(blacklisted_dirs, cur_dir): continue

        for file in filenames:
            filename, ext = file.rsplit(".", 1)
            if ext != "py": continue
            if re.match(blacklisted_files, filename): continue

            ext_path = dirpath.split(Paths.root, 1)[1].replace("\\", ".")
            yield f"{ext_path}.{filename}"


def custom_modules_from_globals(glb: dict) -> set:
    """Returns a set of all modules loaded in globals that are defined in cogs or utils."""

    pat = r"cogs\..*|utils\..*"
    return {
        module_name
        for v in glb.values()
        if hasattr(v, "__module__") and re.match(
            pat,
            module_name := v.__module__
        )
    }


# JSON helpers
import json as _json


def deep_update_json(
    path: str,
    U: dict,
    *,
    update_None: bool = True,
    update_falsy: bool = True
) -> dict:
    """Deep-updates a json file with a (nested) dict U. See :func:`deep_update` for
    further explanation of function parameters. Returns the data of the json file
    after the update.

    Parameters:
    -----------
    path: :class:`str`
        the path to the json file that is to be updated.
    U: :class:`dict`
        the dict used to update the dict obtained from the json file. Equivalent to\
        :param:`U` in :func:`deep_update`.
    update_None: :class:`bool`
        whether or not None values in U should overwrite non-None values in D.
    update_falsy: :class:`bool`
        whether or not falsy values (values that equate to False in `bool(v)`)
        should overwrite non-falsy values in D.
    """

    with open(path, "r+") as file:
        data = _json.load(file)     # Read file (advances pointer)
        deep_update(data, U, update_None=update_None, update_falsy=update_falsy)

        file.seek(0)                # Return pointer to beginning of file
        _json.dump(data, file)      # Start overwriting at pointer (beginning)
        file.truncate()             # Cut off any remaining contents

    return data
