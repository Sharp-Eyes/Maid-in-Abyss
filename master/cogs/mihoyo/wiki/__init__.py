from .wiki import WikiCog
from utils.bot import CustomBot

def setup(bot: CustomBot):
    bot.add_cog(WikiCog(bot))
