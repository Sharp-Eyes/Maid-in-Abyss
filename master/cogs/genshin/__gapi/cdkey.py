from .api import Genshin_API
from .exceptions import CodeRedemptionError, IncorrectCodeError, AlreadyClaimed
from .user import get_user_cookies

import disnake
from disnake.ext import commands, tasks

import re
from typing import Any, Union
from collections import defaultdict, namedtuple
from bs4 import BeautifulSoup, FeatureNotFound
from functools import partial

from utils.overrides import CustomBot
from utils.helpers import parse_soup_text, nested_get, deep_update_json
from utils.classes import Paths

import logging
logger = logging.getLogger("GAPI")

__all__ = (
    "CDKey_Mixin",
    "validate_cdkey_cookies"
)

GWIKI_BASE_URL = "https://genshin-impact.fandom.com/wiki"
REDEEM_CODE_URL = "https://genshin-impact.fandom.com/wiki/Promotional_Codes"

CDKeyInfo = namedtuple("CDKeyInfo", ["code", "rewards", "start", "end"])


try:
    s = BeautifulSoup("", "lxml")
    PARSER = "lxml"
except FeatureNotFound as e:
    PARSER = ""


def validate_cdkey_cookies(cookies: dict[str, str]) -> bool:
    """Check whether `account_id` and `cookie_token` have been set,
    as redeem codes can only be claimed when these are set
    """
    return cookies["account_id"] and cookies["cookie_token"]


class CDKey_Mixin(Genshin_API):
    """A class that organizes helper functions for redeeming CDKey/Redeem Code
    rewards through the Genshin API. Contains methods to handle code redemption
    and a background task that webscrapes for new redeem codes.
    """
    bot: CustomBot

    async def do_redeem_for(
        self,
        user: Union[disnake.User, disnake.Member],
        *,
        individual_data: dict[str, Any],
        cdkey: str
    ):
        """Claim Hoyolab cdkey rewards for a user by making the proper API calls.

        Parameters:
        -----------
        user: :class:`discord.Member`
            The user whose rewards we are attempting to claim.
        individual_data: :class:`dict`
            A dict that holds the user's user_data. This is derived from user_data.json,
            by selecting a single top-level entry (user).
        cdkey:  str
            The CDKey to be redeemed.

        Returns:
        --------
        bool
            True: Claiming succeeded.

        Raises:
        -------
        IncorrectCodeError:
            The CDKey is not bound to any rewards
        AlreadyClaimed:
            The user has already claimed rewards for the entered CDKey.
        CookieError:
            Entered cookies are incorrect or COOKIE_TOKEN and ACCOUNT_ID cookies have
            not been set.
        CodeRedemptionError:
            A collection of other somewhat more miscellaneous errors. Includes:
            - The entered CDKey already expired,
            - No game account bound to entered cookies,
            - No bound game account above AR10
        """

        def update_claimed():
            data = {str(user.id): {"Genshin_Impact": {"cdkeys": [*redeemed_prior, cdkey]}}}
            deep_update_json(Paths.user_data, data)

        redeemed_prior = nested_get(individual_data, "Genshin_Impact", "cdkeys", [])
        if cdkey in redeemed_prior:
            raise AlreadyClaimed(
                "{0.mention}, you appear to have already redeemed this code. "
                "Please check the redeem code and try again."
            )

        cookies = get_user_cookies(user_data=individual_data)

        try:
            await self.redeem_cdkey(cookies=cookies, cdkey=cdkey)
            update_claimed()

        except AlreadyClaimed as e:
            update_claimed()
            raise e

    async def scrape_redeem_codes(self):
        async with self.bot.session.get(REDEEM_CODE_URL) as response:
            soup = BeautifulSoup(await response.read(), PARSER)

        get_text = partial(parse_soup_text, strip=True, sep=" ", href_prepend=GWIKI_BASE_URL)

        for row in soup.select("tbody > tr"):
            info_cell = row.select_one("td:last-of-type")
            if not (info_cell and "153,255,153" in info_cell["style"]):
                continue

            code_cell = row.select_one("td:first-of-type")
            if code_cell.select_one("[target]"):
                continue

            reward_cell = row.select_one("td:nth-of-type(3)")

            start, _, end, *_ = info_cell.children
            r = re.findall(r"[A-Z][a-z]+ \d{1,2}, \d{4}", start + end) + ["?"] * 2

            yield CDKeyInfo(
                get_text(code_cell),
                get_text(reward_cell),
                *r[:2]
            )

    @tasks.loop(hours=1)
    async def kekloop(self):

        succeeded = defaultdict(list[disnake.User])
        failed = defaultdict(list[disnake.User])

        async for cdkey_info in self.scrape_redeem_codes():
            pass
