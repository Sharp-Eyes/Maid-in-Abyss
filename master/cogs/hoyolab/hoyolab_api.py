# TODO: Move models to separate file
# TODO: Move db initialization to bot level

from __future__ import annotations

import disnake
from disnake.ext import commands

from disnake import ApplicationCommandInteraction as Interaction
from disnake.ext.commands import Param
from disnake.ext.tasks import loop

import motor.motor_asyncio as motor
from dotenv import load_dotenv
from os import getenv

from datetime import time
from inspect import isclass
from collections import defaultdict

from typing import ClassVar, Optional, Literal
from pydantic import BaseModel, root_validator, ValidationError, Field
from bson.objectid import ObjectId
from pymongo.results import UpdateResult, InsertOneResult

from utils.overrides import AsyncInitMixin, FullReloadCog, CustomBot
from utils.classes import Codeblock

from .__hoyolab import Hoyolab_API
from .__hoyolab.exceptions import AlreadySigned, FirstSign, GenshinAPIError

import logging
logger = logging.getLogger("Hoyolab_API")

load_dotenv()
user, pw, db_default = getenv("MONGO_USER"), getenv("MONGO_PASS"), getenv("MONGO_DB")
DB_URI = (
    f"mongodb+srv://{user}:{pw}@maid-in-abyss.kdpxk.mongodb.net/{db_default}"
    "?retryWrites=true&w=majority"
)

db = motor.AsyncIOMotorClient(DB_URI)

CHECKIN_FAIL_MSG = (
    "{}, something went awry in trying to claim your daily login rewards. "
    "Please see your DMs for further information. I apologize for the inconvenience!"
)

HOYOLAB_CLAIM_RESET = time.fromisoformat("16:00:02")


class ClassVarPropagatingModel(BaseModel):

    @root_validator(pre=True, allow_reuse=True)
    def propagate(cls, values):
        for field in cls.__fields__.values():
            field_type = field.type_
            if not (isclass(field_type) and issubclass(field_type, BaseModel)):
                continue

            for class_var in cls.__class_vars__:
                if class_var not in cls.__dict__:
                    raise AttributeError(
                        f"ClassVar {class_var} has not yet been defined, "
                        "and thus cannot be propagated."
                    )
                if class_var in field_type.__class_vars__:
                    setattr(field_type, class_var, getattr(cls, class_var))
        return values


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


ValidGame = Literal["Honkai Impact", "Genshin Impact"]


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
        GenshinAPIError:
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

        except GenshinAPIError as e:
            # Unknown error occurred during claiming.
            # TODO: improve/expand on error catching
            logger.error(e)
            raise e


class HoyolabNotificationModel(BaseModel):
    # TODO: Deprecate

    honkai_impact: Optional[int] = Field(alias="Honkai Impact")
    genshin_impact: Optional[int] = Field(alias="Genshin Impact")

    def __getitem__(self, k: str) -> int:
        # Map all fields' names and aliases to their respective values
        for field in self.__fields__.values():
            if k in (field.name, field.alias):
                return getattr(self, k)
        raise KeyError(k)


class HoyolabDataModel(ClassVarPropagatingModel):

    API: ClassVar[Hoyolab_API]

    accounts: list[HoyolabAccountModel]
    notifications: HoyolabNotificationModel  # TODO: Deprecate

    def add_new_account(
        self,
        cookies: CookieModel,
        game: ValidGame
    ):
        """Add a new account with the provided cookies and bind it to the provided game."""
        new_account = HoyolabAccountModel(games=[game], cookies=cookies)
        self.accounts.append(new_account)


class DiscordUserDataModel(ClassVarPropagatingModel):

    class Config:
        arbitrary_types_allowed = True

    API: ClassVar[Hoyolab_API]

    db_id: Optional[ObjectId] = Field(alias="_id")
    discord_id: int
    hoyolab: HoyolabDataModel

    async def commit(self):
        """Commit any changes made to the user by pushing to the database."""
        result: UpdateResult = await db.discord.users.update_one(
            {"_id": self.db_id},
            {"$set": self.dict(exclude={"db_id"})}
        )
        logger.log(
            1,
            f"Updated DB <db.discord.users>; {result.modified_count} entries modified "
            f"with id {self.db_id}."
        )

    @classmethod
    async def create_new(cls, discord_id: int, hoyolab_data: HoyolabDataModel):
        """Create a new entry of user data, add it to the database, and set the database key."""
        new = cls(discord_id=discord_id, hoyolab=hoyolab_data)
        result: InsertOneResult = await db.discord.users.insert_one(
            new.dict(exclude={"db_id"})
        )
        logger.log(
            1, f"Inserted to DB <db.discord.users>; added entry with id {result.inserted_id}"
        )

        new.db_id = result.inserted_id
        return new


# wat

class UserSigninResult:
    """Simplifies parsing and handling sign-in result embed creation."""

    base_embed = disnake.Embed(
        title="Sign-in Results:",
        description="\u200b"
    )

    def __init__(self, *, suppressed: tuple[GenshinAPIError]):
        self.results: defaultdict[str, list[str]] = defaultdict(list)
        self.suppressed = suppressed

    def add_user_account_result(
        self,
        account: HoyolabAccountModel,
        game: ValidGame,
        result: Optional[GenshinAPIError]
    ) -> None:
        """Add a sign-in result for the user. For param result, pass the error
        returned by the claim function in case it failed, otherwise pass None
        to indicate a successful claim.
        """

        if isinstance(result, self.suppressed):
            return

        # TODO: Expand error handler
        if not result:
            emoji = "<:check_mark:904873627437125673>"
            message = "Success!"

        elif isinstance(result, FirstSign):
            emoji = "<:cross_mark:904873627466477678>"
            message = "Failed! You must first claim manually at least once."

        elif isinstance(result, AlreadySigned):
            emoji = "<:cross_mark:904873627466477678>"
            message = "Failed! Your rewards appear to have already been claimed."

        else:
            emoji = "<:cross_mark:904873627466477678>"
            message = "Failed! Something unexpected happened."

        self.results[account.name].append(f"{emoji} {game}:\n{message}")

    @property
    def embed(self) -> disnake.Embed:

        embed = self.base_embed.copy()
        for account_name, messages in self.results.items():
            embed.add_field(
                name=account_name,
                value="\n".join(messages)
            )
        return embed


# cog

class HoyolabApiCog(AsyncInitMixin, FullReloadCog):

    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.API = Hoyolab_API(bot.session)
        DiscordUserDataModel.API = self.API

        print("finished init")

    async def __async_init__(self):
        print("started async_init")
        self.user_cache: list[DiscordUserDataModel] = []
        async for user in db.discord.users.find():
            try:
                self.user_cache.append(DiscordUserDataModel(**user))
            except ValidationError:
                logger.warn(
                    f"Caching model from database failed for user with id {user['discord_id']}"
                )

        self.emoji = {
            "CHECK": self.bot.get_emoji(904873627437125673),
            "CROSS": self.bot.get_emoji(904873627466477678)
        }

        self.hoyo_signin_auto.start()

    @commands.command(name="getcache")
    async def getcache(self, ctx: commands.Context, user: disnake.User = None):
        if not user:
            return await ctx.send(f"{str(self.user_cache)[:1995]}...")

        for user_data in self.user_cache:
            if user_data.discord_id == user.id:
                break
        return await ctx.send(user_data)

    @commands.command(name="try")
    async def trycache(self, ctx: commands.Context):
        return await ctx.send(
            f"{self.user_cache[0].API}, {self.user_cache[0].hoyolab.API}"
        )

    @commands.slash_command(name="hoyolab", guild_ids=[701039771157397526, 511630315039490076])
    async def hoyo_main(self, inter: Interaction):
        pass

    @hoyo_main.sub_command_group(name="auth")
    async def hoyo_auth(self, inter: Interaction):
        pass

    @hoyo_auth.sub_command(name="set")
    async def hoyo_auth_set_cookies(
        self,
        inter: Interaction,
        name: str = Param(desc="How you want your account to be displayed."),
        game: str = Param(choices=["Honkai Impact", "Genshin Impact"]),
        ltuid: str = Param(
            "", desc="If selected, please make sure to also use LTOKEN.",
        ),
        ltoken: str = Param(
            "", desc="If selected, please make sure to also use LTUID.",
        ),
        account_id: str = Param(
            "", desc="If selected, please make sure to also use COOKIE_TOKEN.",
        ),
        cookie_token: str = Param(
            "", desc="If selected, please make sure to also use ACCOUNT_ID.",
        )
    ):
        user = disnake.utils.get(
            self.user_cache, discord_id=inter.author.id
        )
        if not any([ltuid, ltoken, account_id, cookie_token]):
            # Assume we're just adding a game
            if user is None:
                return await inter.response.send_message(
                    f"{inter.author.mention}, you should first setup an account. "
                    "Please run this command again and specify your login cookies.",
                    ephemeral=True
                )

            account = disnake.utils.get(user.hoyolab.accounts, name=name)
            if account is None:
                return await inter.response.send_message(
                    f"{inter.author.message}, you do not appear to have an account with "
                    "that name. Please pick an existing option or create an account first.",
                    ephemeral=True
                )

            await self._do_account_game_update(inter, account, game)
            return await user.commit()

        try:
            new_cookies = CookieModel(
                ltuid=ltuid,
                ltoken=ltoken,
                account_id=account_id,
                cookie_token=cookie_token
            )
        except ValidationError as e:
            # TODO: Make pydantic error parser?
            return await inter.response.send_message(e.errors()[0]["msg"], ephemeral=True)

        # TODO: Validate cookies

        if user is None:
            new_user = await DiscordUserDataModel.create_new(
                discord_id=inter.author.id,
                hoyolab_data={"accounts": [{"name": name, "games": [game], "cookies": new_cookies}]}
            )
            self.user_cache.append(new_user)

            return await inter.response.send_message(
                f"Successfully added your account with {new_cookies} and bound it to {game}!",
                ephemeral=True
            )

        for account in user.hoyolab.accounts:
            matching_cookies = account.match_cookies(new_cookies)

            if all(matching_cookies):
                # All match; add new game for same cookies or return error message.
                await self._do_account_game_update(inter, account, game)
                break

            elif any(matching_cookies):
                # One or more matches; assume update existing account:
                account.update_cookies(new_cookies)
                await inter.response.send_message(
                    f"Successfully updated your cookies to {new_cookies}", ephemeral=True
                )
                break

        else:
            # The loop didn't break, no matching account to be updated; new account:
            user.hoyolab.add_new_account(new_cookies, game)
            await inter.response.send_message(
                f"Successfully added your account with {new_cookies} and bound it to {game}!",
                ephemeral=True
            )

        await user.commit()

    async def _do_account_game_update(
        self,
        inter: Interaction,
        account: HoyolabAccountModel,
        game: ValidGame
    ):
        try:
            account.update_games(game)
        except ValueError as e:
            return await inter.response.send_message(e, ephemeral=True)

        await inter.response.send_message(
            f"Successfully bound your cookies to {game}!", ephemeral=True
        )

    @hoyo_auth_set_cookies.autocomplete("name")
    async def hoyo_auth_name_autocomp(self, inter: Interaction, inp: str):
        for user_data in self.user_cache:
            if user_data.discord_id == inter.author.id:
                break

        autocomp = [inp or " "]
        for account in user_data.hoyolab.accounts:
            autocomp.append(account.name)

        return autocomp

    @hoyo_auth_set_cookies.autocomplete("ltuid")
    @hoyo_auth_set_cookies.autocomplete("ltoken")
    @hoyo_auth_set_cookies.autocomplete("account_id")
    @hoyo_auth_set_cookies.autocomplete("cookie_token")
    async def hoyo_auth_cookie_autocomp(self, inter: Interaction, inp: str):
        for user_data in self.user_cache:
            if user_data.discord_id == inter.author.id:
                break

        active_cookie = inter.data.focused_option.name
        autocomp = [inp or " "]
        for account in user_data.hoyolab.accounts:
            current = getattr(account.cookies, active_cookie)
            if current:
                autocomp.append(current)

        return autocomp

    @hoyo_main.sub_command(name="sign-in")
    async def hoyo_signin(self, inter: Interaction, accounts: str = None, games: str = None):
        await inter.response.defer(ephemeral=True)

        result = UserSigninResult()

        user = disnake.utils.get(self.user_cache, discord_id=inter.author.id)
        for account in user.hoyolab.accounts:
            if accounts and account.name not in accounts:
                continue

            for game in account.games:
                if games and game not in games:
                    continue

                try:
                    await account.hoyolab_signin(game, force=True)
                except GenshinAPIError as e:
                    author = inter.author
                    result.add_user_account_result(account, game, e)

                    if type(e) is GenshinAPIError:
                        await author.send(
                            "An unknown error occurred in claiming rewards for your account "
                            f"{account.name}`. Please try claiming your rewards manually using "
                            "`/hoyolab sign-in`. If this persists, please contact my master."
                        )

                else:
                    result.add_user_account_result(account, game, None)

        await user.commit()
        await inter.edit_original_message(embed=result.embed)

    @hoyo_signin.autocomplete("accounts")
    async def hoyo_claim_account_autocomp(self, inter: Interaction, inp: str):
        user = disnake.utils.get(self.user_cache, discord_id=inter.author.id)
        return [
            account.name
            for account in user.hoyolab.accounts
            if inp.lower() in account.name.lower()
        ]

    @hoyo_signin.autocomplete("games")
    async def hoyo_claim_game_autocomp(self, inter: Interaction, inp: str, *, account=None):
        if account:
            user = disnake.utils.get(self.user_cache, discord_id=inter.author.id)
            account = disnake.utils.get(user.hoyolab.accounts, name=account)
            games = {game.lower() for game in account.games}
        else:
            games = {"honkai impact", "genshin impact"}

        inp = inp.lower()
        *prev, curr = inp.rsplit(", ", 1)

        if curr.strip(",") in games:
            prev.append(curr.strip(","))
            curr = ""

        games.difference_update(prev)
        return [
            ", ".join([*[p.title() for p in prev], game.title()])
            for game in games
            if curr in game
        ]

    @loop(time=[HOYOLAB_CLAIM_RESET])
    async def hoyo_signin_auto(self):
        logger.log(1, "Claiming daily check-in rewards")

        for user in self.user_cache:
            result = UserSigninResult(suppressed=(AlreadySigned,))
            discord_user = await self.bot.getch_user(user.discord_id)
            if not discord_user:
                continue

            for account in user.hoyolab.accounts:
                for game in account.games:
                    try:
                        await account.hoyolab_signin(game)
                    except GenshinAPIError as e:
                        result.add_user_account_result(account, game, e)

                        if type(e) is GenshinAPIError:
                            await discord_user.send(
                                "An unknown error occurred in claiming rewards for your account "
                                f"{account.name}`. Please try claiming your rewards manually using "
                                "`/hoyolab sign-in`. If this persists, please contact my master."
                            )
                    else:
                        result.add_user_account_result(account, game, None)

            await user.commit()

            if result.results:
                await discord_user.send(embed=result.embed)


def setup(bot: commands.Bot):
    bot.add_cog(HoyolabApiCog(bot))
