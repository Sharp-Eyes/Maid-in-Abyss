from __future__ import annotations

import re
from dataclasses import dataclass

from typing import TypeVar, Callable, Iterable, Any


@dataclass
class Paths:
    root = ".\\master\\"
    secret = root + "private.json"
    guild_data = root + "guild_data.json"
    user_data = root + "user_data.json"
    cogs = root + 'cogs\\'
    events = root + 'events.json'


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


class sortedlist:

    def __init__(self, key=None, *args: _FT):
        if args:
            self.data = [i for i in args[0]] if isinstance(args[0], Iterable) else list(args)
        else:
            self.data: list[_FT] = []
        self.key = key

    def __repr__(self) -> str:
        return "sortedlist(" + ", ".join(str(i) for i in self.data) + ")"

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, i) -> _FT:
        return self.data[i]

    def _insert(self, i, item: _FT) -> sortedlist[_FT]:
        self.data.insert(i, item)
        return self

    def _cmp(self, L, M, U=None):
        if not self.key:
            return L < M and (M <= U if U is not None else True)
        k = self.key
        return k(L) < k(M) and (k(M) <= k(U) if U is not None else True)

    def insert(self, item: _FT) -> sortedlist[_FT]:
        # Binary search
        L = 0
        U = len(self) - 1

        if not self.data:
            self.data.append(item)
            return self

        if self._cmp(self.data[U], item):
            self.data.append(item)
            return self
        if self._cmp(item, self.data[L]):
            return self._insert(0, item)

        while True:
            M = (U + L) // 2
            print(self.data, L, M, U)

            if self._cmp(self.data[M], item, self.data[M + 1]):
                return self._insert(M + 1, item)

            if self._cmp(self.data[M], item):
                L = M + 1
            else:
                U = M - 1

            if U < L:
                print("wat")


class Codeblock:

    def __init__(self, content: str, *, lang: str = None):
        if lang is not None:
            self.content = content
            self.lang = lang
            return

        match = re.fullmatch(r"```(.*)\n(.+)(?:\n)```", content, re.M | re.DOTALL)
        self.content, self.lang = match.groups() if match else (content, "")

    def __str__(self):
        return f"```{self.lang}\n{self.content}```"

    def __repr__(self):
        return str(self)

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)
