from .exceptions import *
from .api import Genshin_API

import discord
#from discord.ext import commands
import json

from typing import Union

from utils.helpers import Paths, nested_get, deep_update_json


import logging
logger = logging.getLogger("GAPI")


class Genshin_API_Claimer(Genshin_API):

    def __init__(self):
        pass

    # Helper functions

    def read_guild_data(self) -> dict:
        with open(Paths.guild_data) as guild_file:
            return json.load(guild_file)


    def read_user_data(self) -> dict:
        with open(Paths.user_data) as user_file:
            return json.load(user_file)


    def get_guild_notif_channel(self, guild_id) -> int:
        """Get the channel ID to which the current guild sends its gapi notifications."""

        guild_data = self.read_guild_data()
        return nested_get(guild_data, str(guild_id), "Genshin_Impact", "gapi_notification_channel")


    def get_user_notif_guilds(self, user_id) -> list[int]:
        """Get a list of guild IDs to which a user is subscribed."""

        user_data = self.read_user_data()
        return nested_get(user_data, str(user_id), "Genshin_Impact", "gapi_notification_guilds", ret=[])


    def get_user_cookies(self, user_id: Union[int, str], individual_user_data: dict = None) -> dict[str, str]:
        """Get the cookies of the user with the given ID. Returns none if this user was not found.
        If not provided with individual_user_data, it will read user_data.json instead.

        Parameters:
        -----------
        user_id: Union[:class:`int`, :class:`str`]
            the Discord UID of the target user.
        individual_user_data: :class:`dict`
            the user data of *one* individual user, as obtained from user_data.json.
        """
        
        if individual_user_data is None:
            individual_user_data = self.read_user_data().get(str(user_id), {})
        return nested_get(individual_user_data, "Genshin_Impact", "auth_cookies")


    # Claim logic

    async def claim_daily_reward(
        self, *,
        user: Union[discord.Member, discord.User],

        individual_data: dict,
    ) -> bool:
        """Claim Hoyolab daily rewards for a user by making the proper API calls.
        
        Parameters:
        -----------
        user: :class:`discord.Member`
            The user whose rewards we are attempting to claim.
        individual_data: :class:`dict`
            A dict that holds the user's user_data. This is derived from user_data.json, by selecting a single top-level entry (user).

        Returns:
        --------
        bool
            True: Claiming succeeded.

        Raises:
        -------
        FirstSign:
            The user that tried to claim their daily rewards has not yet completed their initial manual claim.
        AlreadySigned:
            The user has already claimed today.
        """

        # Technically we can get the auth_cookies from only the user object, but for auto-login that would mean:
        #  1) read user_data.json, loop over each user_id and their data (contains auth_cookies),
        #  2) construct a discord.User from the user_id,
        #  3) enter the discord.User into this function,
        #  4) read user_data.json again and use the discord.User object to get the correct auth_cookies.
        # This means we'd have to open the same json twice, which seems a bit dumb. I'd rather just pass in the cookies, as that would mean only reading the json once in either case.

        def update_latest_claim(today):
            claim_data = {str(user.id): {"Genshin_Impact": {"latest_claim": today}}}
            deep_update_json(Paths.user_data, claim_data)

        # Check whether the user has set their auth cookies
        auth_cookies = self.get_user_cookies(user.id)
        if not auth_cookies:
            raise CookieError("{0.mention}, you do not appear to have set your authorization cookies. Please enter them through `/gwiki auth`.")

        # Check claim status
        latest_claim = nested_get(individual_data, "Genshin_Impact", "latest_claim")
        if latest_claim == self.get_API_date():
            # latest cached claim was today, thus we exit without making any API calls.
            raise AlreadySigned("{0.mention}, you appear to have already claimed your daily rewards today.")

        try:
            await self.daily_claim_status(cookies=auth_cookies)

        except GenshinAPIError as e:
            logger.log(1, f"Auto-login failed for user {user.id}: {e}")
            
            if isinstance(e, FirstSign):
                raise e
            
            if isinstance(e, AlreadySigned):
                # Since the user already signed in but the cached date does not match, we can update the cached date to today
                # to save on any further API calls.
                update_latest_claim(self.get_API_date())
                raise e
        
        # Try claiming
        try:
            await self.daily_claim_exec(cookies=auth_cookies)
            update_latest_claim(self.get_API_date())
            return True

        except GenshinAPIError as e:
            logger.log(2, f"Auto-login failed for user {user.id}: {e}")
            raise e