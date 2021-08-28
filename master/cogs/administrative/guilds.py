import discord
from discord.ext import commands
import json

from main import DATA_PATH, DEFAULT_PREFIX
from utils.helpers import deep_update


class Guild_Cog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @commands.group(
        name = "prefix",
        brief = "Change the prefix to which I respond for the current guild."
        # description = TODO
    )
    async def base_prefix(self, ctx: commands.Context):
        print(ctx.invoked_subcommand)

        


    @base_prefix.command(
        name = "set"
    )
    async def set_prefix(self, ctx: commands.Context, *prefixes):

        guild: discord.Guild = ctx.guild
        # DMs
        if not guild: return await ctx.send("This command can only be used inside a guild.")

        with open(DATA_PATH, "r+") as file:
            data = json.load(file)
            new = {str(guild.id): {"prefix": prefixes}}
            deep_update(data, new)

            file.seek(0)
            json.dump(data, file)
            file.truncate()

        pfx_str = ", ".join(f"`{p}`" for p in prefixes)
        await ctx.send(f"I will now register commands in this guild with prefix(es): {pfx_str}.")
        



    @base_prefix.command(
        name = "get"
    )
    async def get_prefix(self, ctx: commands.Context):

        guild: discord.Guild = ctx.guild

        with open(DATA_PATH, "r") as file:
            data = json.load(file)
            guild_data = data.get(str(guild.id), dict())
            prefixes = guild_data.get("prefix", DEFAULT_PREFIX)

            pfx_str = ", ".join(f"`{p}`" for p in prefixes)
            await ctx.send(f"I currently respond to the following prefixes: {pfx_str}.")




def setup(bot: commands.Bot):
    bot.add_cog(Guild_Cog(bot))