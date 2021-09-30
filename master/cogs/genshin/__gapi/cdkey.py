from .api import Genshin_API

from disnake.ext import commands


import logging
logger = logging.getLogger("GAPI")


__all__ = (
    "CDKey_Mixin",
    "validate_cdkey_cookies"
)


def validate_cdkey_cookies(cookies: dict[str, str]):
    """Check whether `account_id` and `cookie_token` have been set,
    as redeem codes can only be claimed when these are set
    """
    return cookies["account_id"] and cookies["cookie_token"]


class CDKey_Mixin(Genshin_API):
    """A class that organizes helper functions for redeeming CDKey/Redeem Code
    rewards through the Genshin API. Contains methods to handle code redemption
    and a background task that webscrapes for new redeem codes.
    """
    bot: commands.Bot
