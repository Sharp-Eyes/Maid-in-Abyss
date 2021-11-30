from __future__ import annotations

from pydantic import BaseModel, Field, root_validator
from typing import Optional, ClassVar
from collections import defaultdict
from pymongo.results import UpdateResult, InsertOneResult

from utils.classes import Codeblock
from utils.overrides import PropagatingModel
from utils.bot import CustomBot
from cogs.mihoyo.__hoyolab_utils import Hoyolab_API, ValidGame
from cogs.mihoyo.__hoyolab_utils.exceptions import (
    AlreadySigned, FirstSign, HoyolabAPIError
)

import logging
logger = logging.getLogger("Hoyolab_API")


class CookieModel(BaseModel):

    class Config:
        extra = "forbid"

    ltuid: Optional[str]
    ltoken: Optional[str]
    account_id: Optional[str]
    cookie_token: Optional[str]

    @root_validator(allow_reuse=True)
    def check_proper_pairs(cls, values):
        # False if both (un)defined, True if one defined and one undefined.
        pair1 = bool(values["ltuid"]) ^ bool(values["ltoken"])
        pair2 = bool(values["account_id"]) ^ bool(values["cookie_token"])

        if (not any(values.values())) or pair1 or pair2:
            # Raise if all missing or any wrong pair
            raise ValueError(
                "Please define one or both pairs of cookies `ltuid` & `ltoken` and/or "
                "`account_id` & `cookie_token`."
            )

        return values

    def __str__(self):
        return str(Codeblock(
            "\n".join(f"{k:>12}: {v}" for k, v in self.dict().items()),
            lang="yaml"
        ))


class HoyolabAccountModel(BaseModel):
    """Not per se related to actual hoyolab accounts; just my implementation of them."""

    API: ClassVar[Hoyolab_API]

    name: str
    games: list[ValidGame]
    latest_claim: Optional[defaultdict[ValidGame, str]] = defaultdict(str)
    cookies: CookieModel

    def update_games(
        self,
        game: ValidGame
    ):
        """Add a new game to an existing Hoyolab account. With this, the same login cookies
        will be used for all games bound to the account.
        """
        if game in self.games:
            raise ValueError(
                "You appear to have already bound the account with cookies "
                f"{self.cookies} to {game}."
            )

        self.games.append(game)

    def update_cookies(
        self,
        cookies: CookieModel
    ):
        """Update the account's cookies. Actually mostly useless as accounts are validated,
        and two different accounts will most likely never have overlapping tokens.
        """
        self.cookies = cookies

    def match_cookies(
        self,
        other: HoyolabAccountModel | CookieModel
    ) -> tuple[bool, bool, bool, bool]:
        """For two hoyolab accounts, check if the cookies match. Returns a tuple with
        four bools, denoting whether each set of cookies matches. This is guaranteed to
        be in the following order: `ltuid`, `ltoken`, `account_id`, `cookie_token`.
        """
        if isinstance(other, HoyolabAccountModel):
            other_cookies = other.cookies
        elif isinstance(other, CookieModel):
            other_cookies = other
        else:
            raise TypeError("other must be of type HoyolabAccountModel or CookieModel.")
        return tuple(
            own_cookie == other_cookie
            for own_cookie, other_cookie in zip(
                self.cookies.dict().values(),
                other_cookies.dict().values()
            )
        )

    async def hoyolab_signin(self, game: ValidGame, *, force: bool = False):
        """Claim Hoyolab daily rewards for a user by making the proper API calls.

        Parameters:
        -----------
        game: Literal["Honkai Impact", "Genshin Impact"]
            The game for which rewards are to be claimed.
        account: :class:`HoyolabAccountModel`
            The Hoyolab account for which rewards are to be claimed.

        Raises:
        -------
        FirstSign:
            The user that tried to claim their daily rewards has not yet completed their
            initial manual claim.
        AlreadySigned:
            The user has already claimed today.
        HoyolabAPIError:
            An unhandled exception occurred.
        """

        # Check claim status
        if not force and self.latest_claim[game] == self.API.date:
            # latest cached claim was today, thus we exit without making any API calls.
            raise AlreadySigned(
                "{0.mention}, you appear to have already claimed your daily rewards today."
            )

        try:
            await self.API.daily_claim_status(game, cookies=self.cookies)

        except FirstSign:
            raise

        except AlreadySigned:
            # Since the user already signed in but the cached date does not match, we can
            # update the cached date to today to save on any further API calls.
            self.latest_claim[game] = self.API.date
            raise

        # Try claiming
        try:
            await self.API.daily_claim_exec(game, cookies=self.cookies)
            self.latest_claim[game] = self.API.date

        except HoyolabAPIError as e:
            # Unknown error occurred during claiming.
            # TODO: improve/expand on error catching
            logger.error(e)
            raise e


class HoyolabDataModel(PropagatingModel):

    API: ClassVar[Hoyolab_API]

    accounts: list[HoyolabAccountModel]

    def add_new_account(
        self,
        cookies: CookieModel,
        game: ValidGame
    ):
        """Add a new account with the provided cookies and bind it to the provided game."""
        new_account = HoyolabAccountModel(games=[game], cookies=cookies)
        self.accounts.append(new_account)


class DiscordUserDataModel(PropagatingModel):

    class Config:
        arbitrary_types_allowed = True

    API: ClassVar[Hoyolab_API]
    bot: ClassVar[CustomBot]

    discord_id: int = Field(alias="_id")
    hoyolab: HoyolabDataModel

    async def commit(self):
        """Commit any changes made to the user by pushing to the database."""
        result: UpdateResult = await self.bot.db.discord.users.update_one(
            {"_id": self.discord_id},
            {"$set": self.dict(by_alias=True)}
        )
        logger.log(
            1,
            f"Updated DB <db.discord.users>; {result.modified_count} entries modified "
            f"with id {self.discord_id}."
        )

    @classmethod
    async def create_new(cls, _id: int, hoyolab_data: HoyolabDataModel):
        """Create a new entry of user data, add it to the database, and set the database key."""
        new = cls(_id=_id, hoyolab=hoyolab_data)
        result: InsertOneResult = await cls.bot.db.discord.users.insert_one(
            new.dict(by_alias=True)
        )
        logger.log(
            1, f"Inserted to DB <db.discord.users>; added entry with id {result.inserted_id}"
        )

        return new
