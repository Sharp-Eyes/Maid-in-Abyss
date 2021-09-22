from dataclasses import dataclass

@dataclass
class Paths:
    root = ".\\master\\"
    secret = root + "private.json"
    guild_data = root + "guild_data.json"
    user_data = root + "user_data.json"
    cogs = root + 'cogs\\'


# Typehint aides

from discord.ext.commands import Bot
from discord_slash import SlashCommand

class Slashbot(Bot):
    """As :module:`discord_slash` monkey-patches commands.Bot with its own functionality
    from :class:`~.SlashCommand`, a normal :class:`commands.Bot` is not aware of this
    added functionality, and is thus not properly type-hinted. This class can be used
    instead, and should solely be used for typehinting.
    """
    slash = SlashCommand