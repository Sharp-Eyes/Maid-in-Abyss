from discord.ext import commands
import re

from discord.ext.commands.errors import BadArgument

from .exceptions import ExtensionNotFound
from .helpers import search_all_extensions

Converter = commands.Converter



class ExtensionConverter(Converter[str]):
    """Converts to a :class:`str` representing an extension, e.g. 'cogs.administrative.help'.
    Takes optional parameters `loaded` and `unloaded` to specify which extensions should be checked.
    
    Parameters:
    -----------
    loaded: :class:`bool`
        Declares whether or not loaded cogs are to be searched for the provided conversion argument.
    unloaded: :class:`bool`
        Declares whether or not unloaded cogs are to be searched for the provided conversion argument.
    
    at least one of these must be True.

    raise_unexpected: :class:`bool`
        Declares whether or not to raise an exception when an unexpected result is found.
        e.g. on encountering a loaded extension while `loaded == False`
"""

    def __init__(self, *, loaded=True, unloaded=True, raise_unexpected=True):
        if not (loaded or unloaded):
            raise Exception("At least one of 'loaded' and 'unloaded' must be True.")
        
        self.loaded = loaded
        self.unloaded = unloaded
        self.raise_unexpected = raise_unexpected

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        bot: commands.Bot = ctx.bot
        extensions = bot.extensions

        # First check if the extension is already loaded:
        pat = r"(^|.+\.)" + argument
        for extension in extensions:
            if re.match(pat, extension):
                if self.loaded:
                    return extension
                if self.raise_unexpected:
                    return BadArgument(f"Extension {argument} is already loaded.")

        # Next see if it's among loadable extensions:
        for extension in search_all_extensions():
            if extension in extensions: continue
            if re.match(pat, extension):
                if self.unloaded:
                    return extension
                if self.raise_unexpected:
                    return BadArgument(f"Extension {argument} is not currently loaded.")

        # Nothing matched:
        return ExtensionNotFound(argument)
        

commands.clean_content