# TODO: Move cog loading outside of on_ready, maybe disable cog reloading on dc, too.

import disnake
from disnake.ext import commands

import logging
import os
import sys
import traceback
from dotenv import load_dotenv
from utils.bot import CustomBot
from utils.helpers import walk_modules

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


if __name__ == "__main__":
    bot = CustomBot(
        command_prefix=commands.when_mentioned_or("."),
        intents=intents,
        help_command=None
    )
    bot.load_extension("jishaku")
    exceptions = 0
    for module in walk_modules("cogs", start="master"):
        if "__" in module:  # TODO: delete dunder modules
            continue
        try:
            bot.load_extension(module)
            print(f"> Successfully loaded extension {module}!")

        except (ExtensionError, Exception) as e:
            exceptions += 1
            print(f"> Failed to load extension {module}: {e}.", file=sys.stderr)
            traceback.print_exc()

    print(f"\n> Encountered {exceptions} exceptions in loading cogs.\n")

    bot.run(token, reconnect=True)
