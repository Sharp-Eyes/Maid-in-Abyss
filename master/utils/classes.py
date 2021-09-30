from __future__ import annotations

import re
from dataclasses import dataclass

from typing import TypeVar, Callable


@dataclass
class Paths:
    root = ".\\master\\"
    secret = root + "private.json"
    guild_data = root + "guild_data.json"
    user_data = root + "user_data.json"
    cogs = root + 'cogs\\'


# Custom classes


_FT = TypeVar("_FT")


class defaultlist(list[_FT]):
    """List that automatically appends a new entry when indexed out of range.
    This is done by calling :func:`default_factory`.

    Parameters:
    -----------
    default_factory: :func:
        The function that is called when appending a new list entry. The return
        of this function will then populate that new list entry.
    """

    def __init__(self, default_factory: Callable[[], _FT] | None):
        assert callable(default_factory)
        self.default_factory = default_factory

    def __getitem__(self, i) -> _FT:
        try:
            return super().__getitem__(i)
        except IndexError:
            n = self.default_factory()
            self.append(n)
            return n


class Codeblock(str):

    def __init__(self, content: str, *, lang: str = None):
        if lang is not None:
            self.content = content
            self.lang = lang
            return

        match = re.fullmatch(r"```(.*)\n(.+)(?:\n)```", content, re.M | re.DOTALL)
        self.content, self.lang = match.groups() if match else (content, "")

    def __str__(self):
        return f"```{self.lang}\n{self.content}```"
