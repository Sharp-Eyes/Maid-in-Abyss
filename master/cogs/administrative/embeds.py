import discord
from discord.ext import commands
from discord_slash import SlashContext

from typing import Union

from utils.helpers import get_bot_color

Embed = discord.Embed

class Embed_Manager(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_embed_dispatch(self, ctx: Union[commands.Context, SlashContext], embed: Embed, **kwargs):
        if embed.color is Embed.Empty:
            color = get_bot_color(self.bot, ctx.guild)
            setattr(embed, "colour", color)
        await ctx.send(embed=embed, **kwargs)




def setup(bot):
    bot.add_cog(Embed_Manager(bot))