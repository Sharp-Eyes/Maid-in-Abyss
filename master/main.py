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


intents = disnake.Intents.default()
intents.members = True


def get_prefix(bot: CustomBot, msg: disnake.Message):
    """Return a message handler the correct prefix if in a guild or the default if in DMs."""

    # Custom prefixes don't matter anymore, shifting to /commands anyways
    return commands.when_mentioned_or(".")(bot, msg)


if __name__ == "__main__":
    bot = CustomBot(
        command_prefix=get_prefix,
        intents=intents,
    )
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
