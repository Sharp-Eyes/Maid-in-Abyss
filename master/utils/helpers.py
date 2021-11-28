import datetime
from typing import Any, Optional, Union

import disnake
from disnake.ext import commands

from collections.abc import Mapping
import re
from os import walk
import json
from bs4 import BeautifulSoup, NavigableString
from functools import partial
from itertools import groupby


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


def create_interaction_identifier(inter: disnake.ApplicationCommandInteraction) -> str:
    """Create a unique identifier for an interaction."""
    return "{0.data.name}{0.author.id}{0.guild.id}".format(inter)


def create_time_markdown(time: Union[int, datetime.datetime], format: str) -> str:
    if isinstance(time, datetime.datetime):
        time = int(time.timestamp())
    spec = {
        "short datetime": "f",
        "long datetime": "F",
        "short date": "d",
        "long date": "D",
        "short time": "t",
        "long time": "T",
        "relative time": "R"
    }
    if format not in spec.values():
        format = spec.get(format.lower())
        if not format:
            raise KeyError(
                f"format {format} doesn't exist. Try any of "
                + "; ".join(f"{k}, {v}" for k, v in spec.items())
            )
    return f"<t:{time}:{format}>"


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
        By default, ignores all folders starting with "__".
    blacklisted_files: :class:`str`
        a regex pattern that should match all file names that are to be ignored.
        By default, ignores all files starting with "__".
    """

    for dirpath, _, filenames in walk(Paths.cogs):
        cur_dir = dirpath.rsplit("\\", 1)[1]
        if re.match(blacklisted_dirs, cur_dir):
            continue

        for file in filenames:
            filename, ext = file.rsplit(".", 1)
            if ext != "py":
                continue
            if re.match(blacklisted_files, filename):
                continue

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


def get_role_by_name(name: str, guild: disnake.Guild) -> Optional[disnake.Role]:
    for role in guild.roles:
        if role.name.lower() == name.lower():
            return role
    return None


# JSON helpers

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
        data = json.load(file)     # Read file (advances pointer)
        deep_update(data, U, update_None=update_None, update_falsy=update_falsy)

        file.seek(0)                # Return pointer to beginning of file
        json.dump(data, file)      # Start overwriting at pointer (beginning)
        file.truncate()             # Cut off any remaining contents

    return data


# BS4 helpers
def parse_soup_text(
    soup: BeautifulSoup,
    *,
    href_prepend: str = "",
    strip: bool = True,
    split: bool = False,
    sep: str = " ",
    ignore: list[str] = list()
):
    result = [[]]
    get_text = partial(soup.get_text, strip=strip, separator=sep)

    def on_a(a: BeautifulSoup):
        # Possibly add <img> tag handling
        t = get_text(a)
        if not t:
            return
        h = href_prepend + a['href']
        result[-1].append(f"[{t}]({h})")

    def on_b(b: BeautifulSoup):
        t = get_text(b)
        if not t:
            return
        result[-1].append(f"*{t}*")

    def on_br(br: BeautifulSoup):
        if result:
            result.extend([["\n"], []])

    state = {
        "a": on_a,
        "b": on_b,
        "br": on_br
    }

    def recurse(soup: BeautifulSoup):

        if isinstance(soup, NavigableString):
            t = get_text(soup)
            if t:
                result[-1].append(t)
            return

        for child in soup.children:
            etype = child.name
            if etype in ignore:
                continue

            todo = state.get(etype)
            if not todo:
                recurse(child)
                continue

            todo(child)

    recurse(soup)

    return "".join(sep.join(r) for r in result)
