# Massive props to thesadru for figuring out all the genshin api endpoints and
# helping me on my way to figure out the honkai endpoint. Code mostly adapted from
# https://github.com/thesadru/genshinstats; also check out
# https://github.com/thesadru/genshin.py

from __future__ import annotations

import disnake
from disnake import ApplicationCommandInteraction as Interaction
from disnake.ext import commands
from disnake.ext.commands import Param
from disnake.ext.tasks import loop

import logging
from collections import defaultdict
from datetime import time
from typing import Optional
from models.hoyolab import CookieModel, DiscordUserDataModel, HoyolabAccountModel
from pydantic import ValidationError
from utils.bot import CustomBot

from .__hoyolab_utils import Hoyolab_API, ValidGame
from .__hoyolab_utils.exceptions import AlreadySigned, FirstSign, HoyolabAPIError

logger = logging.getLogger("Hoyolab_API")


CHECKIN_FAIL_MSG = (
    "{}, something went awry in trying to claim your daily login rewards. "
    "Please see your DMs for further information. I apologize for the inconvenience!"
)

HOYOLAB_CLAIM_RESET = time.fromisoformat("16:00:02")


# display / possibly move to separate file if more display classes are needed


class UserSigninResult:
    """Simplifies parsing and handling sign-in result embed creation."""

    base_embed = disnake.Embed(title="Sign-in Results:", description="\u200b")

    def __init__(self, *, suppressed: tuple[HoyolabAPIError] = tuple()):
        self.results: defaultdict[str, list[str]] = defaultdict(list)
        self.suppressed = suppressed

    def add_user_account_result(
        self, account: HoyolabAccountModel, game: ValidGame, result: Optional[HoyolabAPIError]
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
            embed.add_field(name=account_name, value="\n".join(messages))
        return embed


# cog


class HoyolabApiCog(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot

    async def cog_load(self):

        await self.bot.wait_until_ready()
        self.API = Hoyolab_API(self.bot.session)
        DiscordUserDataModel.API = self.API
        DiscordUserDataModel.bot = self.bot

        self.user_cache: list[DiscordUserDataModel] = []
        async for user in self.bot._motor.discord.users.find():
            try:
                self.user_cache.append(DiscordUserDataModel(**user))
            except ValidationError:
                logger.warn(
                    f"Caching model from database failed for user with id {user['discord_id']}"
                )

        self.emoji = {
            "CHECK": self.bot.get_emoji(904873627437125673),
            "CROSS": self.bot.get_emoji(904873627466477678),
        }

        if not self.hoyo_signin_auto.is_running():
            self.hoyo_signin_auto.start()

    def cog_unload(self):
        if self.hoyo_signin_auto.is_running():
            self.hoyo_signin_auto.cancel()

    @commands.is_owner()
    @commands.command(name="getcache")
    async def getcache(self, ctx: commands.Context, user: disnake.User = None):
        if not user:
            return await ctx.send(f"{str(self.user_cache)[:1995]}...")

        for user_data in self.user_cache:
            if user_data.discord_id == user.id:
                break
        return await ctx.send(user_data)

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
            "",
            desc="If selected, please make sure to also use LTOKEN.",
        ),
        ltoken: str = Param(
            "",
            desc="If selected, please make sure to also use LTUID.",
        ),
        account_id: str = Param(
            "",
            desc="If selected, please make sure to also use COOKIE_TOKEN.",
        ),
        cookie_token: str = Param(
            "",
            desc="If selected, please make sure to also use ACCOUNT_ID.",
        ),
    ):
        user = disnake.utils.get(self.user_cache, discord_id=inter.author.id)
        inter.send
        if not any([ltuid, ltoken, account_id, cookie_token]):
            # Assume we're just adding a game
            if user is None:
                return await inter.response.send_message(
                    f"{inter.author.mention}, you should first setup an account. "
                    "Please run this command again and specify your login cookies.",
                    ephemeral=True,
                )

            account = disnake.utils.get(user.hoyolab.accounts, name=name)
            if account is None:
                return await inter.response.send_message(
                    f"{inter.author.message}, you do not appear to have an account with "
                    "that name. Please pick an existing option or create an account first.",
                    ephemeral=True,
                )

            await self._do_account_game_update(inter, account, game)
            return await user.commit()

        try:
            new_cookies = CookieModel(
                ltuid=ltuid, ltoken=ltoken, account_id=account_id, cookie_token=cookie_token
            )
        except ValidationError as e:
            # TODO: Make pydantic error parser?
            return await inter.response.send_message(e.errors()[0]["msg"], ephemeral=True)

        # TODO: Validate cookies

        if user is None:
            new_user = await DiscordUserDataModel.create_new(
                _id=inter.author.id,
                hoyolab_data={
                    "accounts": [{"name": name, "games": [game], "cookies": new_cookies}]
                },
            )
            self.user_cache.append(new_user)

            return await inter.response.send_message(
                f"Successfully added your account with {new_cookies} and bound it to {game}!",
                ephemeral=True,
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
                ephemeral=True,
            )

        await user.commit()

    async def _do_account_game_update(
        self, inter: Interaction, account: HoyolabAccountModel, game: ValidGame
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
                except HoyolabAPIError as e:
                    author = inter.author
                    result.add_user_account_result(account, game, e)

                    if type(e) is HoyolabAPIError:
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
            account.name for account in user.hoyolab.accounts if inp.lower() in account.name.lower()
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
            ", ".join([*[p.title() for p in prev], game.title()]) for game in games if curr in game
        ]

    @commands.command(name="force_autoclaim")
    async def force_autoclaim(self, ctx):
        # if not self.hoyo_signin_auto.is_running:
        await self.hoyo_signin_auto()

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
                    except HoyolabAPIError as e:
                        result.add_user_account_result(account, game, e)

                        if type(e) is HoyolabAPIError:
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
