# TODO: Move cog loading outside of on_ready, maybe disable cog reloading on dc, too.

import sys
import traceback
from dotenv import load_dotenv
import os

import disnake
from disnake.ext import commands

from utils.helpers import search_all_extensions
from utils.bot import CustomBot

import logging
logging.basicConfig(level=logging.NOTSET)

dpy_logger = logging.getLogger("disnake")
dpy_logger.setLevel(logging.ERROR)
reload_logger = logging.getLogger("reload")
reload_logger.setLevel(logging.ERROR)  # Disable 'nested reload' debug notifs (utils/overrides.py)

# Type aliases
ExtensionError = commands.errors.ExtensionError


load_dotenv()
token = os.getenv("TOKEN")


DEFAULT_PREFIX = ["."]

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
    # guild_data = bot["guilds"]
    prefixes = DEFAULT_PREFIX  # guild_data.get(str(guild.id), "prefix", default=DEFAULT_PREFIX)
    return handle(*prefixes)(bot, msg)


if __name__ == "__main__":
    bot = CustomBot(
        command_prefix=get_prefix,
        intents=intents,
    )

    # @bot.event
    # async def on_ready():
    # print(f"\n\nLogged in as {bot.user.name} | disnake version {disnake.__version__}")

    # Load or reload extensions, whichever is appropriate
    exceptions = 0
    for extension in search_all_extensions():
        try:
            bot.load_extension(extension)
            print(f"> Successfully loaded extension {extension}!")

        except (ExtensionError, Exception) as e:
            exceptions += 1
            print(f"> Failed to load extension {extension}: {e}.", file=sys.stderr)
            traceback.print_exc()

    print(f"\n> Encountered {exceptions} exceptions in loading cogs.\n")

    bot.run(token, reconnect=True)
