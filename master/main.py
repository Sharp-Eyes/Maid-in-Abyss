from os import walk
import sys
import traceback
import json

import discord
from discord.ext import commands



ExtensionError = commands.errors.ExtensionError


ROOT = "./master/"
SECRET_PATH = ROOT + "private.json"
DATA_PATH = ROOT + "guild_data.json"
COG_PATH = ROOT + 'cogs/'

DEFAULT_PREFIX = ["."]


with open(SECRET_PATH) as secret_file:
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
    with open(DATA_PATH) as data_file:
        guild_data = json.load(data_file)

    data = guild_data.get(str(guild.id), dict())
    prefixes = data.get("prefix", DEFAULT_PREFIX)
    return handle(*prefixes)(bot, msg)


def load_extensions(bot: commands.Bot, to_do = "load"):

    exceptions = 0
    meth = {
        "reload": bot.reload_extension,
        "load": bot.load_extension
    }[to_do]

    for dirpath, dirnames, filenames in walk(COG_PATH):
        for file in filenames:
            filename, ext = file.rsplit(".", 1)
            if ext != "py": continue

            try:
                ext_path = dirpath.split(ROOT, 1)[1].replace("/", ".")
                meth(f"{ext_path}.{filename}")
                print(f"> Successfully {to_do}ed extension {filename}!")
                
            except ExtensionError:
                exceptions += 1
                print(f"> Failed to {to_do} extension {filename}.", file=sys.stderr)
                traceback.print_exc()

    print(f"> {exceptions} exceptions occurred while {to_do}ing cogs.")
            


if __name__ == "__main__":
    bot = commands.Bot(
        command_prefix=get_prefix,
        intents = intents
    )


    @bot.event
    async def on_ready():
        print(f"\n\nLogged in as {bot.user.name} | Dpy version {discord.__version__}")
        
        # First load:
        if not bot.extensions:
            load_extensions(bot)
        else:
            load_extensions(bot, "reload")


    bot.run(token, reconnect=True)

