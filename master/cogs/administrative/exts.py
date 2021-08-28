import discord
from discord.ext import commands

from os import walk
import re
import traceback

from discord.ext.commands.errors import ExtensionError

from main import ROOT, COG_PATH


ExtensionError = commands.errors.ExtensionError


class Extension_Manager(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    def search_loaded_extensions(self, pattern):
        """Search for loaded extensions that match a given pattern"""
        
        extensions = self.bot.extensions
        matches = []

        for extension in extensions:
            # Match e.g. "cogs.administrative.exts" and "exts", but not e.g. "gs.administrative.exts", "xts"
            match = re.match(r"(^|.+\.)" + pattern, extension)
            if match:
                matches.append(match.group(0))

        return matches


    @commands.command(
        name = "load"
    )
    async def load_extension(self, ctx: commands.Context, ext_name: str):

        for dirpath, dirnames, filenames in walk(COG_PATH):
            for file in filenames:
                filename, ext = file.rsplit(".", 1)
                if ext != "py": continue
                if filename != ext_name: continue

                ext_path = dirpath.split(ROOT, 1)[1].replace("/", ".")
                try:
                    self.bot.load_extension(f"{ext_path}.{filename}")
                    await ctx.send(f"Successfully loaded extension {ext_name}!")
                
                except ExtensionError as e:
                    await ctx.send(f"Failed to load extension {ext_name}: `{e}`.")
                    traceback.print_exc()
                
                finally:
                    return

        await ctx.send(f"Could not find an extension by the name of {ext_name}.")


    @commands.command(
        name = "reload"
    )
    async def reload_extension(self, ctx: commands.Context, ext_name: str):

        exts = self.search_loaded_extensions(ext_name)
        if not exts: return await ctx.send(f"Could not find an extension by the name of {ext_name}.")

        for ext in exts:
            try:
                self.bot.reload_extension(ext)
                await ctx.send(f"Successfully reloaded extension {ext_name}!")

            except ExtensionError as e:
                await ctx.send(f"Failed to reload extension {ext_name}: `{e}`.")
                traceback.print_exc()


    @commands.command(
        name = "unload"
    )
    async def unload_extension(self, ctx: commands.Context, ext_name: str):

        exts = self.search_loaded_extensions(ext_name)
        if not exts: return await ctx.send(f"Could not find an extension by the name of {ext_name}.")

        for ext in exts:
            try:
                self.bot.unload_extension(ext)
                await ctx.send(f"Successfully unloaded extension {ext_name}!")

            except ExtensionError as e:
                await ctx.send(f"Failed to unload extension {ext_name}: `{e}`.")
                traceback.print_exc()

        



def setup(bot: commands.Bot):
    bot.add_cog(Extension_Manager(bot))