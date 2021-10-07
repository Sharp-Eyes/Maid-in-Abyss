import disnake
from disnake.channel import TextChannel
from disnake.ext import commands
from disnake.ext.commands import Param
from disnake import ApplicationCommandInteraction as Interaction

from typing import Literal
import json
from datetime import datetime
from pytz import UTC

from main import DEFAULT_PREFIX
from utils.helpers import deep_update, deep_update_json
from utils.classes import Paths

DEFAULT_PFX_STR = ", ".join(DEFAULT_PREFIX)
DEFAULT_PFX_STR_STYLIZED = ", ".join(f"`{p}`" for p in DEFAULT_PREFIX)

GUILDS = [701039771157397526, 511630315039490076]

with open(Paths.guild_data) as guild_file:
    gdata = json.load(guild_file)


class Guild_Cog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(
        name="prefix",
        brief="Change the prefix to which I respond for the current guild."
        # description = TODO
    )
    async def prefix_base(self, ctx: commands.Context):
        print(ctx.invoked_subcommand)

    @prefix_base.command(
        name="set",
        description=(
            "<n>Description:"
            "<v>Change the prefix(es) to which I respond. This can be almost anything, "
            "though I recommend not using any quotation marks, as they may produce "
            "invalid results.\nLeave `[prefixes]` blank to return me to my default "
            f"prefix(es): {DEFAULT_PFX_STR_STYLIZED}. This may be handy when you provide me with "
            "disfunctional prefixes. Finally, know that I will always respond to being "
            "@mentioned."
            "<n>Examples:"
            "<v>```ini\n[1] <p>prefix set . maid.\n[2] <p>prefix set .\n"
            "[3] <p>prefix set```"
            "`[1]` makes me respond to both `.<command>` and `maid.<command>`;\n"
            "`[2]` makes me respond only to `.<command>`;\n"
            "`[3]` makes me respond to my default prefix(es): "
            + ', '.join(f'`{p}<command>`' for p in DEFAULT_PREFIX)
            + "."
        )
    )
    async def prefix_set(self, ctx: commands.Context, *prefixes):

        if not prefixes:
            return await self.prefix_set(ctx, *DEFAULT_PREFIX)

        guild = ctx.guild
        # DMs
        if not guild:
            return await ctx.send("This command can only be used inside a guild.")

        with open(Paths.guild_data, "r+") as file:
            data = json.load(file)
            new = {str(guild.id): {"prefix": prefixes}}
            deep_update(data, new)

            file.seek(0)
            json.dump(data, file)
            file.truncate()

        pfx_str = ", ".join(f"`{p}`" for p in prefixes)
        await ctx.send(f"I will now register commands in this guild with prefix(es): {pfx_str}.")

    @prefix_base.command(
        name="get"
    )
    async def prefix_get(self, ctx: commands.Context):

        guild = ctx.guild

        with open(Paths.guild_data, "r") as file:
            data = json.load(file)
            guild_data = data.get(str(guild.id), dict())
            prefixes = guild_data.get("prefix", DEFAULT_PREFIX)

            pfx_str = ", ".join(f"`{p}`" for p in prefixes)
            await ctx.send(f"I currently respond to the following prefixes: {pfx_str}.")

    @commands.command(name="age")
    async def _age(self, ctx, guild: disnake.Guild):
        dt = guild.created_at
        now = datetime.now(UTC)
        diff = int((now - dt).total_seconds())
        mins, secs = divmod(diff, 60)
        hours, mins = divmod(mins, 60)
        days, hours = divmod(hours, 24)
        years, days = divmod(days, 365)
        dt_str = dt.strftime("%A, %e %b %Y, %T")
        await ctx.send(
            f"Server {guild.name} was created on {dt_str}.\nIt has been live for {years} years, "
            f"{days} days, {hours} hours, {mins} minutes, and {secs} seconds."
        )

    @commands.slash_command(
        name="notifications",
        guild_ids=GUILDS
    )
    @commands.has_permissions(administrator=True)
    async def notif_main(
        self,
        inter: Interaction,
        action: Literal["set", "view", "stop"] = Param(
            desc="Whether to view notification channels, or add/remove notifications in a channel."
        ),
        channel: TextChannel = Param(
            "",
            desc="The channel to view/modify. Leave blank when viewing to view all.",
        ),
        type: Literal["genshin api", "status"] = Param(
            "",
            desc="The type of channel you wish to view/modify. "
            "Leave blank when viewing to view all.",
        )
    ):
        """Change which notifications to receive, and where to receive them."""
        await inter.response.send_message(f"{action=}, {channel=}, {type=}")

        if type == "status":
            new_data = {str(inter.guild_id): {"status channel": {"id": channel.id}}}
            deep_update_json(Paths.guild_data, new_data)


def setup(bot: commands.Bot):
    bot.add_cog(Guild_Cog(bot))
