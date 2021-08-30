import sys
import traceback
import json

import discord
from discord.ext import commands
from discord_slash import SlashCommand

from utils.helpers import search_all_extensions
from utils.classes import Paths


# Type aliases
ExtensionError = commands.errors.ExtensionError


DEFAULT_PREFIX = ["."]


with open(Paths.secret) as secret_file:
    secret = json.load(secret_file)
    token = secret["token"]

intents = discord.Intents.default()
intents.members = True


def get_prefix(bot: commands.Bot, msg: discord.Message):
    """Return a message handler the correct prefix if in a guild or the default if in DMs."""

    handle = commands.when_mentioned_or
    guild: discord.Guild = msg.guild

    # DM:
    if not guild: return handle(DEFAULT_PREFIX)(bot, msg)

    # Guild:
    with open(Paths.guild_data) as data_file:
        guild_data = json.load(data_file)

    data = guild_data.get(str(guild.id), dict())
    prefixes = data.get("prefix", DEFAULT_PREFIX)
    return handle(*prefixes)(bot, msg)



if __name__ == "__main__":
    bot = commands.Bot(                 #Custom_Bot
        command_prefix=get_prefix,
        intents = intents
    )
    slash = SlashCommand(bot, sync_commands=True, sync_on_cog_reload=True) # Declares slash commands through the client.

    @bot.event
    async def on_ready():
        print(f"\n\nLogged in as {bot.user.name} | Dpy version {discord.__version__}")
        
        # Load or reload extensions, whichever is appropriate
        if not bot.extensions:
            method = bot.load_extension
        else:
            method = bot.reload_extension

        exceptions = 0
        for extension in search_all_extensions():
            try:
                method(extension)
                print(f"> Successfully loaded extension {extension}!")
                
            except (ExtensionError, Exception) as e:
                exceptions += 1
                print(f"> Failed to load extension {extension}: {e}.", file=sys.stderr)
                traceback.print_exc()

        print(f"\n> Encountered {exceptions} exceptions in loading cogs.")
        await slash.sync_all_commands()
            


    bot.run(token, reconnect=True)

