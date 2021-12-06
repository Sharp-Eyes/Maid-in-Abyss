from disnake import ApplicationCommandInteraction as Interaction
from disnake.ext import commands

import traceback
from utils.bot import CustomBot


class Extension_Manager(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot

    @commands.slash_command(name="extensions", guild_ids=[701039771157397526])
    async def extensions_slash(self, inter):
        pass

    @extensions_slash.sub_command(name="reload")
    @commands.is_owner()
    async def reload_slash(self, inter: Interaction, extension: str, reload_submodules: bool):
        self.bot.reload_extension(extension, reload_submodules=reload_submodules)
        return await inter.send(f"Successfully reloaded extension `{extension}`", ephemeral=True)

    @extensions_slash.sub_command(name="load")
    @commands.is_owner()
    async def load_slash(
        self,
        inter: Interaction,
        extension: str,
    ):
        self.bot.load_extension(extension)
        return await inter.send(f"Successfully loaded extension `{extension}`", ephemeral=True)

    @extensions_slash.sub_command(name="unload")
    @commands.is_owner()
    async def unload_slash(
        self,
        inter: Interaction,
        extension: str,
    ):
        self.bot.unload_extension(extension)
        return await inter.send(f"Successfully unloaded extension `{extension}`", ephemeral=True)

    @reload_slash.autocomplete("extension")
    @load_slash.autocomplete("extension")
    @unload_slash.autocomplete("extension")
    async def ext_autocomp(self, inter: Interaction, inp: str):
        return [ext for ext in self.bot.extensions if inp.lower() in ext.lower()]

    @reload_slash.error
    @load_slash.error
    @unload_slash.error
    async def slash_ext_error(self, inter: Interaction, error):
        await inter.send(str(error), ephemeral=True)
        traceback.print_exc()


def setup(bot: commands.Bot):
    bot.add_cog(Extension_Manager(bot))
