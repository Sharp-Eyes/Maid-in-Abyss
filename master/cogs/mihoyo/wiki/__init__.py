from .wiki import WikiCog# , # setup
from utils.bot import CustomBot

def setup(bot: CustomBot):
    bot.add_cog(WikiCog(bot))
