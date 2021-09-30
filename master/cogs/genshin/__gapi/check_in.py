from .api import Genshin_API, get_API_date
from .exceptions import GenshinAPIError, AlreadySigned, FirstSign
from .user import get_user_cookies, read_user_data, get_user_notif_guilds, get_guild_notif_channel

import disnake
from disnake.ext import tasks
from disnake.ext.commands import Bot

import datetime
from typing import Union
from collections import defaultdict

from utils.helpers import Paths, nested_get, deep_update_json


import logging
logger = logging.getLogger("GAPI")


__all__ = ["CheckIn_Mixin"]


DAILY_CLAIM_TIME = datetime.time.fromisoformat("16:00:02")  # UTC


class CheckIn_Mixin(Genshin_API):
    """A mixin class that contains everything necessary to set up HoYoLAB daily check-in routines.
    Contains a method for 'manual' checkin and a :class:`discord.ext.tasks.Task` for auto-claiming.
    """
    bot: Bot
    __str__checkin_success = (
        "{}, I have successfully claimed your daily login rewards from Hoyolab! "
        "Don't forget to collect them in-game!"
    )
    __str__checkin_fail = (
        "{}, something went awry in trying to claim your daily login rewards. "
        "Please see your DMs for further information. I apologize for the inconvenience!"
    )

    async def do_checkin_for(
        self, *,
        user: Union[disnake.Member, disnake.User],
        individual_data: dict,
    ) -> bool:
        """Claim Hoyolab daily rewards for a user by making the proper API calls.

        Parameters:
        -----------
        user: :class:`discord.Member`
            The user whose rewards we are attempting to claim.
        individual_data: :class:`dict`
            A dict that holds the user's user_data. This is derived from user_data.json,
            by selecting a single top-level entry (user).

        Returns:
        --------
        bool
            True: Claiming succeeded.

        Raises:
        -------
        FirstSign:
            The user that tried to claim their daily rewards has not yet completed their
            initial manual claim.
        AlreadySigned:
            The user has already claimed today.
        """

        def update_latest_claim(today):
            claim_data = {str(user.id): {"Genshin_Impact": {"latest_claim": today}}}
            deep_update_json(Paths.user_data, claim_data)

        # Check whether the user has set their auth cookies
        auth_cookies = get_user_cookies(user_id=user.id)

        # Check claim status
        latest_claim = nested_get(individual_data, "Genshin_Impact", "latest_claim")
        if latest_claim == get_API_date():
            # latest cached claim was today, thus we exit without making any API calls.
            logger.log(
                1,
                f"Auto-claim failed for user {user.name}#{user.discriminator}: "
                "rewards already claimed (Cache)."
            )
            raise AlreadySigned(
                "{0.mention}, you appear to have already claimed your daily rewards today."
            )

        try:
            await self.daily_claim_status(cookies=auth_cookies)

        except GenshinAPIError as e:

            if isinstance(e, FirstSign):
                logger.log(
                    1,
                    f"Auto-claim failed for user {user.name}#{user.discriminator}: "
                    "not yet manually claimed (API)."
                )
                raise e

            if isinstance(e, AlreadySigned):
                logger.log(
                    1,
                    f"Auto-claim failed for user {user.name}#{user.discriminator}: "
                    "rewards already claimed (API)."
                )
                # Since the user already signed in but the cached date does not match, we can
                # update the cached date to today to save on any further API calls.
                update_latest_claim(get_API_date())
                raise e

        # Try claiming
        try:
            await self.daily_claim_exec(cookies=auth_cookies)
            update_latest_claim(get_API_date())
            return True

        except GenshinAPIError as e:
            logger.log(2, f"Auto-login failed for user {user.id}: {e}")
            raise e

    # Auto check-in

    @tasks.loop(time=[DAILY_CLAIM_TIME], reconnect=False)
    async def gapi_claim_daily(self):
        logger.log(1, "claiming daily stuffs")

        user_data = read_user_data()
        succeeded = defaultdict(list[disnake.User])
        failed = defaultdict(list[disnake.User])

        for user_id, data in user_data.items():
            user = self.bot.get_user(int(user_id))
            guilds = get_user_notif_guilds(user_id)

            try:
                await self.do_checkin_for(
                    user=user,
                    individual_data=data
                )
                if not guilds:
                    await user.send(self.__str__checkin_success.format(user.name))
                for guild in guilds:
                    succeeded[guild].append(user)

            except GenshinAPIError as e:

                if isinstance(e, FirstSign):
                    await user.send(str(e).format(user))
                    for guild in guilds:
                        failed[guild].append(user)
                    continue

                if isinstance(e, AlreadySigned):
                    # Don't want to ping a user that already checked in manually, to minimize spam
                    continue

        for guild_id, users in succeeded.items():
            channel_id = get_guild_notif_channel(guild_id)
            channel: disnake.TextChannel = self.bot.get_channel(channel_id)
            user_str = ", ".join(u.mention for u in users)

            await channel.send(self.__str__checkin_success.format(user_str))

        for guild_id, users in failed.items():
            channel_id = get_guild_notif_channel(guild_id)
            channel: disnake.TextChannel = self.bot.get_channel(channel_id)
            user_str = ", ".join(u.mention for u in users)

            await channel.send(self.__str__checkin_fail.format(user_str))

    @gapi_claim_daily.before_loop
    async def gapi_claim_daily_setup(self):

        # Try to claim before daily reset on cog load in case we missed a day
        if datetime.datetime.utcnow().time() < DAILY_CLAIM_TIME:
            await self.gapi_claim_daily()
