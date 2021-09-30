from disnake.ext import commands
import json

from main import DEFAULT_PREFIX
from utils.helpers import deep_update
from utils.classes import Paths

DEFAULT_PFX_STR = ", ".join(DEFAULT_PREFIX)
DEFAULT_PFX_STR_STYLIZED = ", ".join(f"`{p}`" for p in DEFAULT_PREFIX)


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
            + {', '.join(f'`{p}<command>`' for p in DEFAULT_PREFIX)}
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


def setup(bot: commands.Bot):
    bot.add_cog(Guild_Cog(bot))
