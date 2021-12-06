from typing import Optional
import disnake
from disnake.ext import commands
from disnake import MessageInteraction, ApplicationCommandInteraction as Interaction
from disnake.ui import View, Select, Button, button
from disnake import SelectOption, ButtonStyle

from models.guilds import ViewModel
from utils.bot import CustomBot


class CoopSelect(Select):
    role_names: tuple[str]
    game: str

    def __init__(self, guild: disnake.Guild, *, row: int = None, custom_id: str = None):
        self.roles: set[disnake.Role] = set()
        for role in guild.roles:
            if role.name in self.role_names:
                self.roles.add(role)
                if len(self.roles) == len(self.role_names):
                    break

        options = [
            SelectOption(label=role_name)
            for role_name in self.role_names
        ]

        super().__init__(
            placeholder=f"Please pick the {self.game} coop roles that apply to you.",
            min_values=0,
            max_values=len(options),
            options=options,
            row=row,
            custom_id=custom_id
        )

    async def callback(self, inter: MessageInteraction):
        await inter.response.defer()
        selected_roles = {
            role
            for role in self.roles
            if role.name in self.values
        }

        author: disnake.Member = inter.author
        author_roles = set(author.roles)
        add_roles = selected_roles.difference(author_roles)
        remove_roles = self.roles.intersection(author_roles).difference(selected_roles)

        await author.remove_roles(*remove_roles)
        await author.add_roles(*add_roles)

        return await inter.send(
            "Captain, you now have the following roles:\n"
            + ", ".join(role.mention for role in sorted(selected_roles))
            + self.changelog(add_roles, remove_roles),
            ephemeral=True
        )

    @classmethod
    def changelog(
        cls,
        added: set[disnake.Role] = {},
        removed: set[disnake.Role] = {},
    ) -> str:
        return (
            "```diff\nChanges:\n"
            + "\n".join(f"+ {role.name}" for role in sorted(added))
            + ("\n" if added else "")
            + "\n".join(f"- {role.name}" for role in sorted(removed))
            + "```"
        )


class HonkaiSelect(CoopSelect):
    role_names = (
        "Captain Level 1-60",
        "Captain Level 61-80",
        "Captain Level 81-88"
    )
    game = "Honkai Impact"


class GenshinSelect(CoopSelect):
    role_names = tuple(f"World Level {i}" for i in range(9))
    game = "Genshin Impact"


class CoopRemoveButton(Button):

    def __init__(
        self,
        label: str,
        custom_id: str,
        row: Optional[int] = None
    ):
        super().__init__(
            label=label,
            style=ButtonStyle.red,
            row=row,
            custom_id=custom_id
        )

    async def remove_roles(
        self, member: disnake.Member, role_names: list[str]
    ) -> str:
        to_remove = {
            role
            for role in member.roles
            if role.name in role_names
        }
        await member.remove_roles(*to_remove)
        return CoopSelect.changelog(removed=to_remove)


class HonkaiRemoveButton(CoopRemoveButton):

    def __init__(self, row: Optional[int] = None):
        super().__init__("Remove all | Honkai", "HonkaiX", row=row)

    async def callback(self, inter: MessageInteraction):
        await inter.response.defer()
        changelog = await self.remove_roles(inter.author, HonkaiSelect.role_names)
        await inter.send(
            f"Successfully removed all Honkai Impact coop roles:\n{changelog}",
            ephemeral=True
        )


class GenshinRemoveButton(CoopRemoveButton):

    def __init__(self, row: Optional[int] = None):
        super().__init__("Remove all | Genshin", "GenshinX", row=row)

    async def callback(self, inter: MessageInteraction):
        await inter.response.defer()
        changelog = await self.remove_roles(inter.author, GenshinSelect.role_names)
        await inter.send(
            f"Successfully removed all Genshin Impact coop roles:\n{changelog}",
            ephemeral=True
        )


class CoopView(View):
    def __init__(self, guild: disnake.Guild, games: list[str]):
        super().__init__(timeout=None)
        self.guild = guild
        honkai = "Honkai Impact" in games
        genshin = "Genshin Impact" in games
        if honkai:
            self.add_item(HonkaiSelect(guild, custom_id="HonkaiSelect"))
        if genshin:
            self.add_item(GenshinSelect(guild, custom_id="GenshinSelect"))
        if honkai:
            self.add_item(HonkaiRemoveButton())
        if genshin:
            self.add_item(GenshinRemoveButton())

    # @button(label="Remove all | Honkai", style=ButtonStyle.red, row=2, custom_id="HonkaiX")
    # async def remove_all_honkai(self, button: disnake.Button, inter: MessageInteraction):
    #     await inter.response.defer()
    #     remove_roles = {
    #         role
    #         for role in inter.author.roles
    #         if role.name in HonkaiSelect.role_names
    #     }
    #     await inter.author.remove_roles(*remove_roles)
    #     await inter.send(
    #         "Successfully removed all Honkai Impact coop roles:\n"
    #         + CoopSelect.changelog(removed=remove_roles),
    #         ephemeral=True
    #     )

    # @button(label="Remove all | Genshin", style=ButtonStyle.red, row=2, custom_id="GenshinX")
    # async def remove_all_genshin(self, button: disnake.Button, inter: MessageInteraction):
    #     await inter.response.defer()
    #     remove_roles = {
    #         role
    #         for role in inter.author.roles
    #         if role.name in GenshinSelect.role_names
    #     }
    #     await inter.author.remove_roles(*remove_roles)
    #     await inter.send(
    #         "Successfully removed all Genshin Impact coop roles:\n"
    #         + CoopSelect.changelog(removed=remove_roles),
    #         ephemeral=True
    #     )


class CoopCog(commands.Cog):

    def __init__(self, bot: CustomBot):
        self.bot = bot

    @commands.slash_command(guild_ids=[701039771157397526, 555270199402823682])
    async def cooptest(self, inter: Interaction):
        await inter.send("hi", view=CoopView(inter.guild))

    async def cog_load(self):
        async for view_data in self.bot.db.find(ViewModel, ViewModel.type == "coop"):
            guild = await self.bot.getch_guild(view_data.guild_id)
            self.bot.add_view(
                CoopView(guild, view_data.data["games"]),
                message_id=view_data.id
            )

            print(f"registered coop view with id {view_data.id}")

    @commands.command()
    async def epiccheck(self, ctx: commands.Context):
        await ctx.send(self.bot.persistent_views)

    async def setup_coop_roles(
        self,
        guild: disnake.Guild,
        roles: set[str]
    ) -> None:
        """Adds a list of coop roles by name, disregarding any roles that already exist."""
        existing_role_names = {role.name for role in guild.roles}
        for role_name in roles - existing_role_names:
            await guild.create_role(name=role_name, mentionable=True)

    async def teardown_coop_roles(self, guild: disnake.Guild) -> None:
        """Removes all coop roles that are currently in the specified guild."""
        to_delete = HonkaiSelect.role_names + GenshinSelect.role_names
        for role in guild.roles:
            if role.name in to_delete:
                await role.delete()

    async def setup_coop(
        self,
        channel: disnake.TextChannel,
        games: list[str]
    ) -> None:
        """Set up coop roles and a selector in the given channel."""
        if "Honkai Impact" in games:
            await self.setup_coop_roles(
                channel.guild,
                set(HonkaiSelect.role_names)
            )

        if "Genshin Impact" in games:
            await self.setup_coop_roles(
                channel.guild,
                set(GenshinSelect.role_names)
            )

        embed = disnake.Embed(
            title="Coop role selector",
            description=(
                "Use the selector panels under this message to quickly set/remove "
                "utility roles that make it easier to organize coop. Please note "
                "that you can select a singular role or any combination of roles.\n"
                "If you wish to completely remove all roles, please click the "
                "corresponding button(s) underneath the selector(s)."
            ),
            color=channel.guild.me.top_role.color
        )
        message = await channel.send(
            embed=embed, view=CoopView(channel.guild, games)
        )
        view_data = ViewModel(
            id=message.id,
            type="coop",
            channel_id=channel.id,
            guild_id=channel.guild.id,
            data={"games": games}
        )
        existing = await self.bot.db.find_one(
            ViewModel,
            ViewModel.guild_id == channel.guild.id,
            ViewModel.type == "coop"
        )
        if existing:
            await self.bot.db.delete(existing)
            try:
                await channel.get_partial_message(existing.id).delete()
            except disnake.HTTPException:
                pass
        await self.bot.db.save(view_data)

    async def teardown_coop(self, guild: disnake.Guild) -> None:
        """Remove coop roles and the coop selector from the specified guild."""
        view_data = await self.bot.db.find_one(
            ViewModel,
            ViewModel.guild_id == guild.id,
            ViewModel.type == "coop"
        )
        channel = self.bot.get_channel(view_data.channel_id)
        try:
            await channel.get_partial_message(view_data.id).delete()
        except disnake.HTTPException:
            pass
        await self.teardown_coop_roles(guild)
        await self.bot.db.delete(view_data)

    @commands.Cog.listener("on_coop_setup")
    async def setup_coop_remote(
        self,
        channel: disnake.TextChannel,
        games: list[str],
        progress_message: disnake.Message
    ):
        await self.setup_coop(channel, games)

        embed = progress_message.embeds[0]
        embed.title = "Coop setup | Success!"
        embed.description = (
            f"Successfully set up coop roles for {' and '.join(games)}!\n"
            f"Successfully set up the role selector in {channel.mention}!"
        )
        await progress_message.edit(embed=embed)

    @commands.Cog.listener("on_coop_teardown")
    async def teardown_coop_remote(
        self,
        guild: disnake.Guild,
        progress_message: disnake.Message
    ):
        await self.teardown_coop(guild)

        embed = progress_message.embeds[0]
        embed.title = "Coop teardown | Success!"
        embed.description = "Successfully removed all Coop functionality."
        await progress_message.edit(embed=embed)


def setup(bot: CustomBot):
    bot.add_cog(CoopCog(bot))
