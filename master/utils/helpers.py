import pkgutil
import disnake
from disnake.ext import commands

import os
import re
import sys
from collections.abc import Mapping
from itertools import groupby
from typing import Any, Generator, Iterator, Optional

MAIN_DIR: str = os.path.dirname(sys.modules["__main__"].__file__)  # type: ignore

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
        def predicate(v):
            return True

    if isinstance(D, Mapping) and isinstance(U, Mapping):
        for k, v in U.items():
            if predicate(v):
                D[k] = deep_update(D[k], v, update_None=update_None, update_falsy=update_falsy)
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
    return member.top_role.color if member else disnake.Colour.default()


# def search_all_extensions(
#     *,
#     blacklisted_dirs: str = DEFAULT_EXT_DIR_BLACKLIST,
#     blacklisted_files: str = DEFAULT_EXT_FILE_BLACKLIST,
# ):
#     """Search for all modules (.py files) in the cogs folder, with optional (regex) blacklists
#     for folder and file names.

#     Parameters
#     ----------
#     blacklisted_dirs: :class:`str`
#         a regex pattern that should match all directory names that are to be ignored.
#         By default, ignores all folders starting with "__".
#     blacklisted_files: :class:`str`
#         a regex pattern that should match all file names that are to be ignored.
#         By default, ignores all files starting with "__".
#     """

#     for dirpath, _, filenames in walk(os.path.join(MAIN_DIR, "cogs")):
#         cur_dir = dirpath.rsplit("\\", 1)[1]
#         if re.match(blacklisted_dirs, cur_dir):
#             continue

#         for file in filenames:
#             filename, ext = file.rsplit(".", 1)
#             if ext != "py":
#                 continue
#             if re.match(blacklisted_files, filename):
#                 continue

#             ext_path = os.path.relpath(dirpath, MAIN_DIR).replace(os.path.sep, ".")
#             yield f"{ext_path}.{filename}"


def walk_modules(path: str, start: str = os.curdir) -> Iterator[str]:
    """Recursively walk through all subdirectories of the provided path, and return
    all importable modules for cog loading.
    
    Prerequisite: cog folders are namespace packages, i.e. they don't have an `__init__.py`.
    Any actual packages (i.e. folders with `__init__.py`) will be yielded as if they were cogs.

    Parameters
    ----------
    path: :class:`str`
        The path to search for modules, along with its subdirectories.
    start: :class:`str`
        The folder from which to start the relative filenames. Useful if the bot is not ran from
        the cwd but e.g. one directory up.

    Yields
    ------
    :class:`str`
        The name of the found module. (usable in `load_extension`)
    """
    _start = os.path.join(start, path)
    for dirpath, dirs, _ in os.walk(_start, topdown=True):
        prefix = os.path.relpath(dirpath, start=start).replace(os.sep, ".")

        for module in pkgutil.iter_modules([dirpath]):
            if module.ispkg:
                dirs.remove(module.name)
            
            yield prefix + "." + module.name


def get_role_by_name(name: str, guild: disnake.Guild) -> Optional[disnake.Role]:
    for role in guild.roles:
        if role.name.lower() == name.lower():
            return role
    return None


def fuzzy(
    text: str,
    collection: list[str],
    *,
    strict: bool = False,
    n: int = 25
) -> Generator[tuple[int, str], None, None]:
    """Fuzzy match a string in a collection of possible strings"""
    sep = "" if strict else ".*?"
    pat = sep.join(re.escape(i) for i in text)
    pattern = re.compile(pat, flags=re.IGNORECASE)

    suggestions: list[tuple[int, int, str]] = []
    for item in collection:
        r = pattern.search(item)
        if r:
            suggestions.append((len(r.group()), r.start(), item))

    return ((score, string) for score, _, string in sorted(suggestions)[:n])


def fuzzy_match(
    text: str,
    collection: list[str],
    *,
    strict: bool = False,
    n: int = 25
) -> list[str]:
    return [string for _, string in fuzzy(text, collection, strict=strict, n=n)]


def fuzzy_scored(
    text: str,
    collection: list[str],
    *,
    strict: bool = False,
    n: int = 25
) -> list[tuple[int, str]]:
    return list(fuzzy(text, collection, strict=strict, n=n))