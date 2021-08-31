from dataclasses import dataclass

@dataclass
class Paths:
    root = ".\\master\\"
    secret = root + "private.json"
    guild_data = root + "guild_data.json"
    user_data = root + "user_data.json"
    cogs = root + 'cogs\\'