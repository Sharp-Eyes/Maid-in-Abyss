import disnake
from disnake.ext import commands

from typing import Union

from utils.helpers import get_bot_color

Embed = disnake.Embed


class Embed_Manager(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_embed_dispatch(
        self,
        ctx_or_response: Union[commands.Context, disnake.InteractionResponse],
        embed: Embed,
        **kwargs
    ):
        if isinstance(ctx_or_response, commands.Context):
            send = ctx_or_response.send
            guild = ctx_or_response.guild
        else:
            send = ctx_or_response.send_message
            guild = ctx_or_response._parent.guild

        if embed.color is Embed.Empty:
            color = get_bot_color(self.bot, guild)
            setattr(embed, "colour", color)
        await send(embed=embed, **kwargs)


def setup(bot):
    bot.add_cog(Embed_Manager(bot))
