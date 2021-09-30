import sys
import traceback
import json

import disnake
from disnake.ext import commands
from disnake.ext.tasks import Loop
# from discord_slash import SlashCommand

from utils.helpers import search_all_extensions
from utils.classes import Paths
from utils.overrides import CustomBot

import logging
logging.basicConfig(level=logging.NOTSET)

dpy_logger = logging.getLogger("disnake")
dpy_logger.setLevel(logging.ERROR)

# ds_logger = logging.getLogger("discord_slash")
# ds_logger.setLevel(logging.WARN)

# Type aliases
ExtensionError = commands.errors.ExtensionError


DEFAULT_PREFIX = ["."]


with open(Paths.secret) as secret_file:
    secret = json.load(secret_file)
    token = secret["token"]

intents = disnake.Intents.default()
intents.members = True


def get_prefix(bot: CustomBot, msg: disnake.Message):
    """Return a message handler the correct prefix if in a guild or the default if in DMs."""

    handle = commands.when_mentioned_or
    guild = msg.guild

    # DM:
    if not guild:
        return handle(*DEFAULT_PREFIX)(bot, msg)

    # Guild:
    with open(Paths.guild_data) as data_file:
        guild_data = json.load(data_file)

    data = guild_data.get(str(guild.id), dict())
    prefixes = data.get("prefix", DEFAULT_PREFIX)
    return handle(*prefixes)(bot, msg)


if __name__ == "__main__":
    bot = CustomBot(
        command_prefix=get_prefix,
        intents=intents,
    )

    @bot.event
    async def on_ready():
        print(f"\n\nLogged in as {bot.user.name} | disnake version {disnake.__version__}")

        # Load or reload extensions, whichever is appropriate
        method = bot.load_extension if not bot.extensions else bot.reload_extension
        exceptions = 0
        for extension in search_all_extensions():
            try:
                method(extension)
                print(f"> Successfully loaded extension {extension}!")

            except (ExtensionError, Exception) as e:
                exceptions += 1
                print(f"> Failed to load extension {extension}: {e}.", file=sys.stderr)
                traceback.print_exc()

        await bot._sync_application_commands()

        print(f"\n> Encountered {exceptions} exceptions in loading cogs.\n")

    # @bot.event
    # async def on_disconnect():
    #     cogs: dict[str, commands.Cog] = bot.cogs.copy()
    #     for cog in cogs.values():
    #         for item in cog.__dict__.values():
    #             if not isinstance(item, Loop): continue
    #             if item.is_running:
    #                 item.cancel()
    #                 print(f"Cancelling task <{item.__name__}>")

    bot.run(token, reconnect=True)
