from typing import Tuple, Union
import discord
from discord.ext import commands

from os import walk
import re
import traceback

from discord.ext.commands.errors import ExtensionError

from utils.helpers import search_loaded_extensions, search_all_extensions



class Extension_Manager(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot



    @commands.command(
        name = "load"
    )
    async def load_extension(self, ctx: commands.Context, ext_name: str):

        for extension in search_all_extensions():
            # Match e.g. "cogs.administrative.exts" and "exts", but not e.g. "gs.administrative.exts", "xts"
            pat = r"(^|.+\.)" + ext_name
            match = re.match(pat, extension)
            if not match: continue

            try:
                self.bot.load_extension(extension)
                await ctx.send(f"Successfully loaded extension {ext_name}!")
            
            except ExtensionError as e:
                await ctx.send(f"Failed to load extension {ext_name}: `{e}`.")
                traceback.print_exc()
            
            finally:
                return

        await ctx.send(f"Could not find an extension by the name of {ext_name}.")


    def reload_or_unload_extension(self, method: Union[commands.Bot.load_extension, commands.Bot.unload_extension], *extension_names: list[str]) -> bool:

        extension = None
        for extension in search_loaded_extensions(self.bot, *extension_names):
            try:
                method(extension)
                yield True

            except ExtensionError as e:
                traceback.print_exc()
                yield False

        if extension is None: yield None



    @commands.command(
        name = "reload"
    )
    async def reload_extension(self, ctx: commands.Context, *ext_names: str):

        method = self.bot.reload_extension
        r = [[], []]    # Result, fails in r[0], success in r[1] (True/False are treated as ints 1/0 when indexing)
        for i, result in enumerate(self.reload_or_unload_extension(method, *ext_names)):
            name = ext_names[i]

            # Not found:
            if result is None:
                await ctx.send(f"Could not find an extension by the name of {name}")
                continue

            # Found:
            r[result].append(name)

        if r[0]:
            await ctx.send("Failed to reload extension(s): " + ", ".join(r[0]))
        if r[1]:
            await ctx.send("Successfully reloaded extension(s): " + ", ".join(r[1]))




    @commands.command(
        name = "unload"
    )
    async def unload_extension(self, ctx: commands.Context, *ext_names: str):

        method = self.bot.unload_extension
        r = [[], []]    # Result, fails in r[0], success in r[1] (True/False are treated as ints 1/0 when indexing)
        for i, result in enumerate(self.reload_or_unload_extension(method, *ext_names)):
            name = ext_names[i]

            # Not found:
            if result is None:
                await ctx.send(f"Could not find an extension by the name of {name}")
                continue

            # Found:
            r[result].append(name)

        if r[0]:
            await ctx.send("Failed to unload extension(s): " + ", ".join(r[0]))
        if r[1]:
            await ctx.send("Successfully unloaded extension(s): " + ", ".join(r[1]))

        



def setup(bot: commands.Bot):
    bot.add_cog(Extension_Manager(bot))