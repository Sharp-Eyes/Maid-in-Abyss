# TODO: Massive cleanup - separate stuff into different classes,
#       refactor messy methods, and so on.
#       Possibly also refactor Event/EventEntry a bit.
#
#       split into:
#           - display
#           - ?
#
# TODO: Add documentation.
#       Most methods are rather vague as-is.

from __future__ import annotations

from .__events import Event, EventEntry, create_event_view

import disnake
from disnake.ext import commands, tasks

import json
from datetime import datetime
from pytz import UTC
from collections import defaultdict
from typing import Generator

from utils.helpers import create_time_markdown, deep_update_json
from utils.classes import Paths, sortedlist
from utils.overrides import FullReloadCog, AsyncInitMixin


from dataclasses import dataclass  # noqa
from typing import Optional

@dataclass        # noqa
class Destination:
    channel: Optional[disnake.TextChannel]
    honkai_status: Optional[disnake.Message]
    genshin_status: Optional[disnake.Message]


class EventManager_Cog(AsyncInitMixin, FullReloadCog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.events: defaultdict[str, dict[str, Event]] = defaultdict(dict)
        self.populate_events()
        self.views = {
            game_name: create_event_view(bot, game_name, event_data, timeout=None)
            for game_name, event_data in self.events.items()
        }

        self.roles: defaultdict[str, dict[str, disnake.Role]] = defaultdict(dict)

        self.update_update_order()
        self.update_and_start_loop()

    async def init(self):
        await self.send_or_update_embeds()

    def populate_events(self) -> None:
        with open(Paths.events) as event_file:
            data = json.load(event_file)

        for game, game_events in data.items():
            for event_name, event_data in game_events.items():
                self.events[game][event_name] = Event(event_data)

        print(self.events)

    def _create_duration(self, L: datetime | EventEntry, U: datetime | EventEntry) -> str:
        if isinstance(L, EventEntry):
            L = L.datetime
        if isinstance(U, EventEntry):
            U = U.datetime

        return f"{create_time_markdown(L, 'F')} ~ {create_time_markdown(U, 'F')}"

    def parse_finished_event(self, event: Event) -> str:
        pass  # TODO: implement

    def _parse_interrupted_event(self, event: Event) -> tuple[str, str]:
        # sourcery skip: class-extract-method
        nxt = event.get_next()

        if not nxt:
            # Assume event is over
            return self.parse_finished_event(event)

        state = nxt.state
        if state == "start":
            end = event.find_next("stop", start=nxt.i)
            run_time = self._create_duration(nxt, end)

        elif state == "stop":
            start = event.find_prior("start", start=nxt.i)
            run_time = self._create_duration(start, nxt)

        elif state is None:
            stop = event.find_next("stop", start=nxt.i)
            start = event.find_prior("start", start=stop.i)
            run_time = self._create_duration(start, stop)

        else:
            print(f"This ain't supposed to happen: {state=}")

        state_message = event.to_str(nxt)
        return run_time, state_message

    def _parse_uninterrupted_event(self, event: Event) -> tuple[str, str]:
        nxt = event.get_next()

        if not nxt:
            # Assume event is over
            return self.parse_finished_event(event)

        state = nxt.state
        if state == "reset":
            stop = event.find_prior("reset", start=nxt.i)
            run_time = self._create_duration(nxt, stop)

        elif state is None:
            stop = event.find_next("reset", start=nxt.i)
            start = event.find_prior("reset", start=stop.i)
            run_time = self._create_duration(start, stop)

        state_message = event.to_str(event[nxt.i - 1])
        return run_time, state_message

    def parse_event(self, event: str | Event) -> tuple[str, str]:

        if isinstance(event, str):
            event = self.events[event]

        if event.type == "interrupted":
            parse = self._parse_interrupted_event
        elif event.type == "uninterrupted":
            parse = self._parse_uninterrupted_event

        return parse(event)

    def construct_event_embeds(self) -> Generator[tuple[str, disnake.Embed], None, None]:
        for game, event_data in self.events.items():
            embed = disnake.Embed(
                title=f"**{game.title()}** events:",
                description=(
                    "Times are listed in your device's local timezone.\n"
                    "(Ways to add) more coming soon!"
                )
            )

            for event_name, event in event_data.items():
                run_time, state_message = self.parse_event(event)
                icon = self.bot.get_emoji(event.icon) or ""
                print(f"{event.icon=}, {icon=}")
                embed.add_field(
                    name=f"{icon} {event_name.title()}",
                    value=f"{run_time}\n - {state_message}"
                )

                yield game, embed

    def update_update_order(self) -> None:
        """Updates `self.update_order` with today's notifications.
        Should be run once a day and at startup/reload.
        """
        order = sortedlist(lambda o: o[0].datetime)
        for _, event_data in self.events.items():
            for _, event in event_data.items():
                nxt = event.get_next()
                if not (nxt and nxt.notification):
                    continue
                # Can't queue events for tomorrow due to tasks limitation
                if nxt.datetime.date != datetime.now(UTC).date:
                    continue
                order.insert((nxt, event))

        self.update_order = order

    def get_destinations(self) -> Generator[Destination, None, None]:
        with open(Paths.guild_data) as guild_file:
            guild_data = json.load(guild_file)

        for data in guild_data.values():
            dest_info = data.get("status channel")
            if not dest_info:
                continue

            channel = self.bot.get_channel(dest_info.get("id", 0))
            if not channel:
                continue

            honkai_id = dest_info.get("honkai impact")
            if self.views["honkai impact"] not in self.bot.persistent_views:
                self.bot.add_view(self.views["honkai impact"], message_id=honkai_id)

            genshin_id = dest_info.get("genshin impact")
            if self.views["genshin impact"] not in self.bot.persistent_views:
                self.bot.add_view(self.views["genshin impact"], message_id=genshin_id)

            honkai_status = channel.get_partial_message(honkai_id) if honkai_id else None
            genshin_status = channel.get_partial_message(genshin_id) if genshin_id else None
            yield Destination(channel, honkai_status, genshin_status)

    async def send_or_update_embeds(self):
        embeds = dict(self.construct_event_embeds())
        print(embeds)

        for destination in self.get_destinations():
            if destination.honkai_status:
                await destination.honkai_status.edit(
                    embed=embeds["honkai impact"],
                    view=self.views["honkai impact"]
                )
            else:
                msg = await destination.channel.send(
                    embed=embeds["honkai impact"],
                    view=self.views["honkai impact"]
                )
                new_data = {
                    str(destination.channel.guild.id): {
                        "status channel": {
                            "honkai impact": msg.id
                        }
                    }
                }
                deep_update_json(Paths.guild_data, new_data)

            if destination.genshin_status:
                await destination.genshin_status.edit(
                    embed=embeds["genshin impact"],
                    view=self.views["genshin impact"]
                )
            else:
                msg = await destination.channel.send(
                    embed=embeds["genshin impact"],
                    view=self.views["genshin impact"]
                )
                new_data = {
                    str(destination.channel.guild.id): {
                        "status channel": {
                            "genshin impact": msg.id
                        }
                    }
                }
                deep_update_json(Paths.guild_data, new_data)

    async def send_notification(self):
        pass

    def update_and_start_loop(self) -> None:
        time = [entry.datetime.timetz() for entry, _ in self.update_order]
        restart = datetime.now(UTC).replace(
            hour=23, minute=59, second=59, microsecond=999999
        ).time()
        time.append(restart)

        self.event_update_loop.change_interval(time=time)
        print("starting")
        self.event_update_loop.start()

    @tasks.loop(reconnect=False)
    async def event_update_loop(self):

        # Close loop if we enter the next day
        if datetime.now(UTC).date() != self._update_order[0][0].date():
            self.update_update_order()
            self.event_update_loop.cancel()
            return

        update = next(self.update_iter)
        await self.send_or_update_embeds()

    @event_update_loop.before_loop
    async def event_loop_startup(self):
        print("coolios")
        # Determine which events will actually be handled by the loop
        i = None
        for i, (entry, _) in enumerate(self.update_order, -1):
            print(i, entry)
            if entry.datetime >= datetime.now(UTC):
                break

        if i is None:
            return
        if self.update_order:
            self.update_iter = iter(self.update_order[i:])

    @event_update_loop.after_loop
    async def event_loop_cleanup(self):
        self.update_and_start_loop()


def setup(bot):
    bot.add_cog(EventManager_Cog(bot))
