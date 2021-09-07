from discord.ext import commands

class ExtensionNotFound(commands.BadArgument):
    """Exception provided when the queried cog could not be found.
    Intended to be raised by a converter, instead of :class:`commands.ExtensionNotFound`,
    to make error handling easier.
    """

    def __init__(self, argument):
        self.argument = argument
        super().__init__(f'Extension "{argument}" not found.')