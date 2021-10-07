from __future__ import annotations
from dataclasses import dataclass

import disnake

from datetime import datetime
from typing_extensions import TypeAlias
from dateutil.relativedelta import relativedelta
from pytz import UTC
import re

from collections import defaultdict
from typing import Optional, Literal
from functools import total_ordering

from utils.helpers import create_time_markdown

__all__ = (
    "EventEntry",
    "Event"
)


@total_ordering
class EventEntry:

    def __init__(
        self,
        i: int,
        data: Optional[dict] = None,
        reference: Optional[datetime] = None,
        **kwargs
    ):

        self.i = i
        if {"state", "priority", "notification", "datetime"}.issubset(kwargs):
            self.state: Optional[str] = kwargs.get("state")
            self.priority: int = kwargs.get("priority", 0)
            self.notification: Optional[str] = kwargs.get("notification")
            self.datetime: datetime[UTC] = kwargs.get("datetime")
            return

        self.state = data.pop("state", None)
        self.priority = data.pop("priority", 0)
        self.notification = data.pop("notification", None)

        processed = self._preprocess(data)
        self.datetime = self._parse_date(reference, processed)

    def _preprocess(self, data: dict) -> tuple[str, str, dict]:
        if "time" in data:
            # time: hh:mm:ss -> hour: hh, minute: mm, second: ss
            data.update(zip(
                ["hour", "minute", "second"],
                data.pop("time").split(":")
            ))

        return defaultdict(lambda: 0, ((k, int(v)) for k, v in data.items()))

    def _parse_date(self, reference, parameters) -> datetime:
        if "weekday" in parameters:
            parameters["days"] -= 7 * (reference.weekday() > parameters["weekday"])
        if "microsecond" not in parameters:
            parameters["microsecond"] = 0

        return reference + relativedelta(**parameters)

    def __gt__(self, other):
        if isinstance(other, EventEntry):
            return self.datetime > other.datetime
        elif isinstance(other, datetime):
            return self.datetime > other
        else:
            raise TypeError(
                f"Comparison not supported between instances of {type(self)} and {type(other)}"
            )

    def shift(self, **params) -> EventEntry:
        self.datetime += relativedelta(**params)
        return self

    def __repr__(self):
        name = self.__class__.__name__
        return f"<{name}: {self.datetime.isoformat()}, {self.state}, {self.notification}>"

    def format(self) -> str:
        return self.notification

    def copy(self):
        return EventEntry(
            self.i,
            state=self.state,
            priority=self.priority,
            notification=self.notification,
            datetime=self.datetime
        )


class Event:

    def __init__(self, data: dict):
        self.icon: Optional[int] = data.get("icon")
        self.type: Literal["interrupted", "uninterrupted"] = data["type"]
        self.shorthands: Optional[dict] = data.get("shorthands")

        self.repeating: bool = data.get("repeating", False)
        if self.repeating:
            self.repetition_type = self._determine_repetition(data)

        ref = datetime.now(UTC)
        self._entries = [
            EventEntry(i, entry.copy(), ref)
            for i, entry in enumerate(data["entries"])
        ]

    def _determine_repetition(self, data: dict) -> Literal["weekly", "monthly"]:
        # Assumes that the data in each event entry field is consistent,
        # i.e. no weekdays in one field, and month days in the next.

        # Add more behaviours if necessary.
        first_entry = data["entries"][0]
        if "weekday" in first_entry:
            return "weekly"
        if "day" in first_entry:
            return "monthly"

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self.__getitem__(j) for j in range(i.start or 0, i.stop or 0, i.step or 1)]

        n = len(self._entries)
        if 0 <= i < n:
            return self._entries[i]

        if not self.repeating:
            raise IndexError(
                "Non-repeating events must be indexed within bounds of self._events"
            )

        cycles_ahead, entries_ahead = divmod(i, n)
        wrapped_entry = self._entries[entries_ahead].copy()
        if self.repetition_type == "weekly":
            wrapped_entry.datetime += relativedelta(weeks=cycles_ahead)
        elif self.repetition_type == "monthly":
            wrapped_entry.datetime += relativedelta(months=cycles_ahead)
        wrapped_entry.i = i
        return wrapped_entry

    def __len__(self):
        return len(self._entries)

    def _find_lookaheads(self, entry: EventEntry) -> list[int]:
        lookaheads = []

        def logic(match: re.Match):
            lookahead, sub = match.groupdict().values()
            if lookahead:
                return lookaheads.append(int(lookahead))
            find(self.shorthands[sub])

        def find(string):
            re.sub(r"\{(?P<lookahead>.+)\}|<(?P<sub>.+)>", logic, string)

        find(entry.notification)
        return lookaheads

    def _shift_events(self, n: int) -> list[EventEntry]:
        shift = {
            "monthly": {"months": 1},
            "weekly": {"weeks": 1}
        }[self.repetition_type]

        amended = [entry.shift(**shift) for entry in self._entries[:n]]
        self._entries = self._entries[n:] + amended
        return amended

    def get_next(self) -> Optional[EventEntry]:
        now = datetime.now(UTC)
        bounds = zip(self._entries[:-1], self._entries[1:])

        lower, upper = next(bounds)
        if now <= lower:
            return lower
        if lower < now <= upper:
            return upper
        for lower, upper in bounds:
            if lower < now <= upper:
                return upper

        if not self.repeating:
            return None

        # Not between any values, thus between the last of the current period
        # and the first of the next period.  Check for lookaheads in the first
        # entry, and shift all the necessary event dates over.
        to_shift = max(self._find_lookaheads(self._entries[0])) + 1

        shifted = self._shift_events(to_shift)
        return shifted[0]

    def find_next(
        self,
        target_state: str,
        *,
        start: Optional[EventEntry | int] = None
    ) -> Optional[EventEntry]:

        if not start:
            nxt = self.get_next()
            if nxt is None:
                return

            start = nxt.i

        elif isinstance(start, EventEntry):
            start = start.i

        # Wrap around if repeating
        stop = len(self) - 1 + len(self) * self.repeating

        # Start at start+1 so we don't match the starting value itself
        for entry in self[start + 1:stop]:
            print(entry)
            if entry.state == target_state:
                return entry
        return None

    def find_prior(
        self,
        target_state: str,
        *,
        start: Optional[int | EventEntry] = None
    ) -> Optional[EventEntry]:

        if not start:
            nxt = self.get_next()
            if nxt is None:
                return

            start = nxt.i

        elif isinstance(start, EventEntry):
            start = start.i

        # wrap around if repeating
        stop = -len(self) * self.repeating

        for entry in reversed(self[stop:start]):
            if entry.state == target_state:
                return entry
        return None

    def _sort_priorities(self, entry: EventEntry) -> EventEntry:
        nxt = self[entry.i + 1]
        return entry if entry.priority >= nxt.priority else nxt

    def format_lookahead(self, entry: EventEntry, lookahead: int) -> str:
        dt = self._entries[entry.i + lookahead].datetime
        return create_time_markdown(dt, "R")

    def to_str(self, entry: int | EventEntry, *, ignore_priority: bool = False) -> str:

        if ignore_priority is False:
            entry = self._sort_priorities(entry)

        if isinstance(entry, int):
            entry = self._entries[entry]

        def logic(match: re.Match) -> str:
            lookahead, sub = match.groupdict().values()
            if lookahead:
                return self.format_lookahead(entry, int(lookahead))
            if sub:
                return parse(self.shorthands[sub])

        def parse(string) -> str:
            return re.sub(r"\{(?P<lookahead>.+)\}|<(?P<sub>.+)>", logic, string)

        return parse(entry.notification)
