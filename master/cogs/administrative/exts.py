import disnake
from disnake.ext import commands
from disnake.ext.commands.errors import BadArgument

import traceback

from utils.converters import ExtensionConverter


class Extension_Manager(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        channel: disnake.TextChannel = ctx.channel
        permissions = channel.permissions_for(ctx.author)
        return permissions.administrator

    __success_str = "Successfully {}ed extension(s) {}."

    @staticmethod
    def __make_ext_str(extensions):
        return ", ".join(f"`{ext}`" for ext in extensions)

    @staticmethod
    def __handle_extensions(method, extensions):
        for ext in extensions:
            if isinstance(ext, BadArgument):
                raise ext
            method(ext)

    @commands.command(
        name="load"
    )
    async def load_exts(
        self,
        ctx: commands.Context,
        extensions: commands.Greedy[ExtensionConverter(loaded=False)]
    ):
        self.__handle_extensions(
            self.bot.load_extension,
            extensions
        )
        await ctx.send(self.__success_str.format(
            "load",
            self.__make_ext_str(extensions)
        ))

    @commands.command(
        name="unload"
    )
    async def unload_exts(
        self,
        ctx: commands.Context,
        extensions: commands.Greedy[ExtensionConverter(unloaded=False)]
    ):
        self.__handle_extensions(
            self.bot.unload_extension,
            extensions
        )
        await ctx.send(self.__success_str.format(
            "unload",
            self.__make_ext_str(extensions)
        ))

    @commands.command(
        name="reload"
    )
    async def reload_exts(
        self,
        ctx: commands.Context,
        extensions: commands.Greedy[ExtensionConverter(unloaded=False)]
    ):

        for cog in self.bot.cogs.values():
            if cog.__module__ not in extensions: continue  # noqa: E701
            if not hasattr(cog, "_prep_reload"): continue  # noqa: E701
            cog._prep_reload()

        self.__handle_extensions(
            self.bot.reload_extension,
            extensions
        )
        await ctx.send(self.__success_str.format(
            "reload",
            self.__make_ext_str(extensions)
        ))

    @load_exts.error
    @unload_exts.error
    @reload_exts.error
    async def ext_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)
        traceback.print_exc()


def setup(bot: commands.Bot):
    bot.add_cog(Extension_Manager(bot))
