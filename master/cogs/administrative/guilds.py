from __future__ import annotations
import inspect

import disnake
from disnake.channel import TextChannel
from disnake.ext import commands
from disnake.ext.commands import Param
from disnake import (
    ApplicationCommandInteraction as Interaction,
    MessageInteraction,
    ButtonStyle,
    SelectOption
)
from disnake.ui import View, Select, Button

from typing import Callable, Optional
from typing_extensions import Self
from enum import Enum

from utils.bot import CustomBot
from models import ViewModel


class SetupViewState(Enum):
    DEFAULT = "default"
    COOP = "coop"
    EVENT = "event"


class ReturnButton(Button):
    view: SetupView

    def __init__(
        self,
        *,
        custom_id_pfx: str,
        row: Optional[int] = None
    ):
        super().__init__(
            style=ButtonStyle.gray,
            label="Return to Setup",
            custom_id=custom_id_pfx + "_to_setup_return_btn",
            row=row,
            emoji="<:caution_mark:905440121464193085>"
        )

    async def callback(self, inter: MessageInteraction):
        await self.view.change_state(SetupViewState.DEFAULT)
        await inter.response.edit_message(
            embed=self.view.embed,
            view=self.view
        )


class ConditionalButton(Button):
    view: SetupView

    def __init__(
        self,
        label: str,
        *,
        style: ButtonStyle,
        emoji: str,
        custom_id: str,
        row: Optional[int] = None
    ):
        super().__init__(
            style=style,
            label=label,
            custom_id=custom_id,
            row=row,
            disabled=True,
            emoji=emoji
        )

    async def maybe_enable(self) -> None:
        """Enables the button if all conditions have been met"""
        raise NotImplementedError()

    async def callback(self, inter: MessageInteraction):
        raise NotImplementedError()


class CoopConfirmButton(ConditionalButton):

    def maybe_enable(self) -> None:
        """Enables the button if both a channel and games have been selected"""
        for item in self.view.children:
            id = item.custom_id
            if "selector" not in id:
                continue
            if id not in self.view.selections:
                self.disabled = True
                return

        self.disabled = False

    async def callback(self, inter: MessageInteraction):
        selections = self.view.selections
        await self.view.change_state(SetupViewState.DEFAULT)
        await inter.response.edit_message(
            embed=self.view.embed,
            view=self.view
        )
        embed = disnake.Embed(
            title="Coop setup | Pending...",
            description="Your changes have been noted, and should appear in the guild soon..."
        ).set_author(
            name=inter.author.display_name,
            icon_url=inter.author.display_avatar.url
        )
        confirmation_message = await inter.followup.send(embed=embed)

        self.view.bot.dispatch(
            "coop_setup",  # cogs.display.coop // CoopCog.setup_coop_remote
            channel=selections["coop_setup_channel_selector"],
            games=selections["coop_setup_game_selector"],
            progress_message=confirmation_message
        )


class CoopTeardownButton(ConditionalButton):
    view: SetupView

    def __init__(self, *, row: Optional[int] = None):
        super().__init__(
            label="Disable Coop Interface",
            style=ButtonStyle.red,
            custom_id="coop_setup_teardown_btn",
            emoji="<:cross_mark:904873627466477678>",
            row=row
        )

    async def maybe_enable(self) -> None:
        maybe_view = await self.view.bot.db.find_one(
            ViewModel,
            ViewModel.type == "coop",
            ViewModel.guild_id == self.view.guild.id
        )
        self.disabled = not maybe_view

    async def callback(self, inter: MessageInteraction):
        self.view.change_state(SetupViewState.DEFAULT)
        await inter.response.edit_message(embed=self.view.embed, view=self.view)
        embed = disnake.Embed(
            title="Coop teardown | Pending...",
            description="Your changes have been noted, and should appear in the guild soon..."
        ).set_author(
            name=inter.author.display_name,
            icon_url=inter.author.display_avatar.url
        )
        confirmation_message = await inter.followup.send(embed=embed)

        self.view.bot.dispatch(
            "coop_teardown",  # cogs.display.coop // CoopCog.teardown_coop_remote
            guild=self.view.guild,
            progress_message=confirmation_message
        )


class SetupPicker(Select):
    view: SetupView

    def __init__(
        self,
        *,
        row: Optional[int] = None
    ):
        options = [
            SelectOption(label=k, value=v)
            for k, v in (
                ("Coop Roles", "coop"),
                ("Events", "event"),
            )
        ]
        super().__init__(
            custom_id="guild_setup",
            placeholder="Select what to set up...",
            options=options,
            row=row
        )

    async def callback(self, inter: MessageInteraction):
        selected = SetupViewState(self.values[0])
        await self.view.change_state(selected)

        await inter.response.edit_message(
            embed=self.view.embed,
            view=self.view
        )


class SetupChannelPicker(Select):
    view: SetupView

    def __init__(
        self,
        guild: disnake.Guild,
        *,
        custom_id_pfx: str,
        row: Optional[int] = None,
    ):
        # TODO: add paginator; support up to 500 channels :/

        self.channels = [
            channel
            for channel in guild.channels
            if isinstance(channel, TextChannel)
            and channel.permissions_for(guild.me).send_messages
        ]
        super().__init__(
            custom_id=custom_id_pfx + "_channel_selector",
            placeholder="Select a channel...",
            options=[
                SelectOption(
                    label=channel.name,
                    description=channel.category.name if channel.category else ""
                )
                for channel in self.channels[:25]
            ],
            row=row
        )

    async def callback(self, inter: MessageInteraction):
        selected = disnake.utils.get(self.channels, name=self.values[0])
        self.view.selections[self.custom_id] = selected
        for option in self.options:
            if option.value in self.values:
                option.default = True

        await self.view.update_items()
        await inter.response.edit_message(view=self.view)


class SetupGamePicker(Select):
    view: SetupView

    def __init__(
        self,
        *,
        custom_id_pfx: str,
        row: Optional[int] = None,
    ):
        self.games = [
            "Honkai Impact",
            "Genshin Impact"
        ]
        super().__init__(
            custom_id=custom_id_pfx + "_game_selector",
            placeholder="Select coop games...",
            options=[
                SelectOption(label=game)
                for game in self.games
            ],
            max_values=len(self.games),
            row=row
        )

    async def callback(self, inter: MessageInteraction):
        self.view.selections[self.custom_id] = self.values
        for option in self.options:
            if option.value in self.values:
                option.default = True

        await self.view.update_items()
        await inter.response.edit_message(view=self.view)


class SetupView(View):
    state = disnake.utils.MISSING

    def __init__(
        self,
        guild: disnake.Guild,
        bot: CustomBot,
        state: SetupViewState = SetupViewState.DEFAULT
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.bot = bot
        self._selections = {}

        self.state = state
        state_modifier, self._embed = self.state_mapping[state]
        state_modifier(self)

    async def change_state(self, state: SetupViewState) -> SetupView:
        if state is self.state:
            print("wait a minute")
            return

        print(f"CHANGING STATE -> {state}")
        self._selections = {}
        self.clear_items()

        state_modifier, self._embed = self.state_mapping[state]
        state_modifier(self)

        current = await self.bot.db.find_one(
            ViewModel,
            ViewModel.guild_id == self.guild.id
        )
        current.data["state"] = state.value
        await self.bot.db.save(current)

        self.state = state
        await self.update_items()
        return self

    def to_default_state(self) -> None:
        self.add_item(SetupPicker(row=0))

    def to_coop_state(self) -> None:
        self.add_item(SetupChannelPicker(
            self.guild,
            custom_id_pfx="coop_setup",
            row=0,
        ))
        self.add_item(SetupGamePicker(
            custom_id_pfx="coop_setup",
            row=1,
        ))
        self.add_item(CoopConfirmButton(
            "Confirm Selections",
            style=ButtonStyle.green,
            custom_id="coop_setup_confirm_btn",
            emoji="<:check_mark:904873627437125673>",
            row=2,
        ))
        self.add_item(CoopTeardownButton(
            row=2,
        ))
        self.add_item(ReturnButton(
            custom_id_pfx="coop_setup",
            row=2,
        ))

    async def update_items(self):
        for item in self.children:
            if hasattr(item, "maybe_enable"):
                func = item.maybe_enable
                if inspect.iscoroutinefunction(func):
                    await func()
                else:
                    func()

    @property
    def selections(self):
        return self._selections

    @property
    def embed(self) -> disnake.Embed:
        return self._embed

    state_mapping: dict[
        SetupViewState, tuple[
            Callable[[Self], None],
            disnake.Embed
        ]
    ] = {
        SetupViewState.DEFAULT: (
            to_default_state,
            disnake.Embed(
                title="Maid-in-Abyss Setup | Main",
                description=(
                    "Right here, you can customize exactly what I can and cannot do in "
                    "this server. If you want to move this setup panel elsewhere, just "
                    "use `/setup` at the new destination. Please see the dropdown menu "
                    "below to find out what exactly you can customize. Most general "
                    "functionality can be enabled/disabled altogether or on a per-game "
                    "basis.\n(very much WIP, have mercy on me)"
                ),
            ),
        ),
        SetupViewState.COOP: (
            to_coop_state,
            disnake.Embed(
                title="Maid-in-Abyss Setup | Coop",
                description=(
                    "Set whether you want to enable my coop feature. This entails:\n\n"
                    "`1.` Select for which games you want to enable coop;\n"
                    "`2.` Select in which channel you want to place a role selector, if any.\n"
                    "`3.` Press the <:check_mark:904873627437125673>`Confirm Selections`"
                    " button to save your selections;\n"
                    "`4.` I will add the necessary coop roles for the games you selected "
                    " to the server;\n"
                    "`5.` I will send a selector panel for the games you selected in the "
                    " channel you selected."
                ),
            ),
        )
    }


class Guild_Cog(commands.Cog):

    def __init__(self, bot: CustomBot):
        self.bot = bot

    async def cog_load(self):
        async for view_data in self.bot.db.find(ViewModel, ViewModel.type == "setup"):
            guild = await self.bot.getch_guild(view_data.guild_id)
            self.bot.add_view(
                SetupView(guild, self.bot, SetupViewState(view_data.data["state"])),
                message_id=view_data.id
            )

            print(f"registered setup view with id {view_data.id}")

    @commands.slash_command(
        name="setup",
        guild_ids=[
            701039771157397526, 511630315039490076, 555270199402823682, 268046379085987840
        ]
    )
    @commands.has_permissions(manage_guild=True)
    async def setuptest(self, inter: Interaction):

        view = SetupView(inter.guild, self.bot)
        await inter.send(
            embed=view.embed,
            view=view
        )

        response = await inter.original_message()
        view_data = ViewModel(
            id=response.id,
            type="setup",
            channel_id=inter.channel_id,
            guild_id=inter.guild_id,
            data={"state": view.state.value}
        )
        existing = await self.bot.db.find_one(
            ViewModel,
            ViewModel.guild_id == inter.guild_id,
            ViewModel.type == "setup"
        )
        if existing:
            await self.bot.db.delete(existing)
            channel = self.bot.get_channel(existing.channel_id)
            try:
                await channel.get_partial_message(existing.id).delete()
            except disnake.HTTPException:
                pass
        await self.bot.db.save(view_data)

    @commands.command(name="loaded_views")
    async def get_loaded_views(self, ctx: commands.Context):
        await ctx.send(self.bot.persistent_views)


def setup(bot: commands.Bot):
    bot.add_cog(Guild_Cog(bot))
