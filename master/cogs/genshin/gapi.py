# Credits for api reverse-engineering go to TheSadru.
# See https://github.com/thesadru/genshinstats/ for their work.

import json
from typing import DefaultDict, Union
import discord
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

import aiohttp
from numpy import array, random

import datetime
from discord.ext.commands.errors import CommandError
import string, hashlib

from utils.helpers import deep_update_json
from utils.classes import Paths

from logging import Logger


logger = Logger("GAPI")


# Predetermine guilds for local slash commands

with open(Paths.guild_data) as guild_file:
    guild_data: dict = json.load(guild_file)
    guilds = [
        int(guild_id)
        for guild_id, data in guild_data.items()
        if data.get("Genshin_Impact", {}).get("gapi_notification_channel")
    ]


# Constants
BASE_URL = "https://bbs-api-os.hoyolab.com/"
DS_SALT = "6cqshh5dhw73bzxn20oexa9k516chk7s"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"

OS_URL = "https://hk4e-api-os.mihoyo.com/event/sol/"
OS_ACT_ID = "e202102251931481"
DAILY_CLAIM_TIME = datetime.time.fromisoformat("18:00:02").replace(tzinfo = datetime.timezone.utc)

HEADERS = {
    # required headers
    "x-rpc-app_version": "1.5.0",  # overseas api uses 1.x.x, chinese api uses 2.x.x
    "x-rpc-client_type": "4",
    "x-rpc-language": "en-us",
    # authentications headers
    "ds": "",
    # recommended headers
    "user-agent": USER_AGENT
}




class Genshin_API:
    """Class that organizes a couple helper functions for API calls"""


    def generate_ds_token(salt: str = DS_SALT) -> str:
        """Creates a new ds token for authentication."""
        t = int(datetime.datetime.utcnow().toordinal())  # current seconds
        r = ''.join(random.choice(list(string.ascii_letters), 6))  # 6 random chars
        h = hashlib.md5(f"salt={salt}&t={t}&r={r}".encode()).hexdigest()  # hash and get hex
        return f'{t},{r},{h}'


    async def fetch_endpoint(self, endpoint_url, *, request_type="get", cookies = None, **params):

        HEADERS.update(ds = self.generate_ds_token())

        async with aiohttp.ClientSession() as session:
            request: Union[session.get, session.post] = getattr(session, request_type)
            async with request(endpoint_url, headers=HEADERS, cookies=cookies, json=params) as response:
                r = await response.read()
                print("!> ",r)
                response_data = json.loads(r)

        # if response_data["retcode"] != 0: raise CommandError(response_data["message"])
        return response_data["data"]

    
    async def daily_claim_status(self, cookies):
        params = dict(act_id = OS_ACT_ID)
        response = await self.fetch_endpoint(OS_URL + "info", cookies=cookies, **params)

        if response["first_bind"]: raise CommandError("You must manually claim daily rewards on Hoyolab at least once.")          # TODO: custom exception here
        if response["is_sign"]: raise CommandError("It appears you have already signed in today")

        return response

    async def daily_claim_exec(self, cookies):
        """Sign into Hoyolab to claim daily rewards."""

        params = dict(lang = "en-us", act_id = OS_ACT_ID)
        response = await self.fetch_endpoint(OS_URL + "sign", request_type="post", cookies=cookies, **params)

        return response





class Genshin_API_Cog(commands.Cog, Genshin_API):


    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.gapi_claim_daily.start()



    def read_guild_data(self) -> dict:
        with open(Paths.guild_data) as guild_file:
            return json.load(guild_file)

    def read_user_data(self) -> dict:
        with open(Paths.user_data) as user_file:
            return json.load(user_file)

    def get_guild_notif_channel(self, guild_id) -> int:
        """Return the channel ID to which the current guild sends its gapi notifications"""
        guild_data = self.read_guild_data()
        return guild_data.get(str(guild_id), {}).get("Genshin_Impact", {}).get("gapi_notification_channel")


    def get_user_notif_guilds(self, user_id) -> list[int]:
        """Return a list of guild IDs to which a user is subscribed"""
        user_data = self.read_user_data()
        return user_data.get(str(user_id), {}).get("Genshin_Impact", {}).get("gapi_notification_guilds", [])




    @cog_ext.cog_subcommand(
        base="gapi",
        name="auth",
        guild_ids=guilds,
        description="Enter your Hoyolab authentication tokens. Accepts: LTUID & LTOKEN and/or ACCOUNT_ID & COOKIE_TOKEN.",
        options=[
            create_option(
                name="ltuid",
                description="If selected, please make sure to also use LTOKEN.",
                option_type=3,
                required=False
            ),
            create_option(
                name="ltoken",
                description="If selected, please make sure to also use LTUID.",
                option_type=3,
                required=False
            ),
            create_option(
                name="account_id",
                description="If selected, please make sure to also use COOKIE_TOKEN.",
                option_type=3,
                required=False
            ),
            create_option(
                name="cookie_token",
                description="If selected, please make sure to also use ACCOUNT_ID.",
                option_type=3,
                required=False
            )
        ]
    )
    async def gapi_auth(self, ctx: SlashContext, ltuid="", ltoken="", account_id="", cookie_token=""):

        v = array([ltuid, ltoken, account_id, cookie_token], dtype=str)     # Array of all argument values
        b = v != ""                                                         # Array converted to bool (non-empty str is True, empty str is False)

        if sum(b) < 2:  # Less than 2 entered: wrong by definition
            return await ctx.send("Please supply _at least one_ pair of `ltuid & ltoken` and `account_id & cookie_token`.", hidden=True)

        if sum(b[::2] ^ b[1::2]):   # at least 2 entered, but not correct pairs
            return await ctx.send("Please supply at least one _pair_ of `ltuid & ltoken` and `account_id & cookie_token`.", hidden=True)

        d = dict(zip(["ltuid", "ltoken", "account_id", "cookie_token"], v))

        new_data = {str(ctx.author_id): {"Genshin_Impact": {"auth_cookies": d}}}
        complete_data = deep_update_json(Paths.user_data, new_data, update_falsy = False)
        cookies = complete_data[str(ctx.author_id)]["Genshin_Impact"]["auth_cookies"]

        return await ctx.send(
            "I have successfully set the following data:\n" +
            ", ".join(f"{k}: `{v}`"for k,v in cookies.items()) +
            "\n\nBy default, you will be notified in DMs. If this is not desirable, you can sign up to be messaged in a guild instead, "
            "assuming that guild has setup a notification channel. Please see `/gapi subscribe` for more.",
            hidden=True
        )


    @cog_ext.cog_subcommand(
        base="gapi",
        subcommand_group="subscriptions",
        name="add",
        subcommand_group_description="Manage in which servers you want to be notified of anything Hoyolab-related.",
        description="Receive automatic Hoyolab notifications in this guild instead of DMs.",
        guild_ids=guilds,
    )
    async def gapi_subscribe(self, ctx: SlashContext):

        channel = self.get_guild_notif_channel(ctx.guild_id)
        guilds = self.get_user_notif_guilds(ctx.author_id)
        print("g", guilds)
        if not channel:
            return await ctx.send(
                f"**{ctx.guild.name}** does not appear to have a notification channel set up. Please contact an "
                "administrator if you would like to see one set up.",
                hidden=True
            )
        if ctx.guild_id in guilds:
            return await ctx.send(
                "It appears you are already subscribed to receive notifications in this guild.",
                hidden=True
            )
        
        new_guilds = [*guilds, ctx.guild_id]
        new_data = {str(ctx.author_id): {"Genshin_Impact": {"gapi_notification_guilds": new_guilds}}}
        deep_update_json(Paths.user_data, new_data)
        return await ctx.send(
            "You have been successfully signed up to receive notifications in this guild!~ "
            "You now receive notifications in the following guilds:\n" +
            ", ".join(f"**{g}**" for g in new_guilds),
            hidden=True
        )


    @cog_ext.cog_subcommand(
        base="gapi",
        subcommand_group="subscriptions",
        name="remove",
        subcommand_group_description="Manage in which servers you want to be notified of anything Hoyolab-related.",
        description="Unsubscribe from notifications in this guild. Without any subscription, you will be notified in DMs.",
        guild_ids=guilds,
    )
    async def gapi_unsubscribe(self, ctx: SlashContext):

        guilds = self.get_user_notif_guilds(ctx.author_id)
        
        try:
            new_guilds = guilds.remove(ctx.guild_id)
            s = "You will no longer receive notifications in this guild!"
            if new_guilds:
                s += " You now receive notifications in the following guilds:\n" + ", ".join(f"**{g}**" for g in new_guilds)
            else:
                s += " Since you are now no longer subscribed to any guilds, you will now be notified in DMs instead."
            await ctx.send(s, hidden = True)
        except (ValueError, AttributeError):
            await ctx.send(
                "It appears you were not subscribed to this guild to begin with. Did you perhaps mean to use `/gapi subscriptions add`?",
                hidden=True
            )

        new_data = {str(ctx.author_id): {"Genshin_Impact": {"gapi_notification_guilds": new_guilds}}}
        deep_update_json(Paths.user_data, new_data)


    @cog_ext.cog_subcommand(
        base="gapi",
        subcommand_group="subscriptions",
        name="view",
        subcommand_group_description="Manage in which servers you want to be notified of anything Hoyolab-related.",
        description="See which guilds you are currently set to receive notifications in, if any.",
        guild_ids=guilds,
    )
    async def gapi_view_subscriptions(self, ctx: SlashContext):

        guilds = self.get_user_notif_guilds(ctx.author_id)
        
        if guilds:
            return await ctx.send(
                "You are currently set to receive notifications in the following guilds:\n" +
                ", ".join(f"**{g}**" for g in guilds),
                hidden = True
            )
        await ctx.send(
            "You are currently not subscribed to any guilds. You will be notified in DMs instead.",
            hidden=True
        )



    @commands.group(
        name = "genshin_api",
        aliases = ["gapi"]
    )
    async def gapi_main(self, _):
        pass


    @gapi_main.command(
        name = "set_notification_channel"
    )
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 1800, commands.BucketType.guild)
    async def gapi_notif(self, ctx: commands.Context, channel: discord.TextChannel):

        new_data = {str(ctx.guild.id): {"Genshin_Impact": {"gapi_notification_channel": channel.id}}}
        deep_update_json(Paths.guild_data, new_data)
        await ctx.send(f"Successfully set **{ctx.guild.name}**'s notification channel for everything Hoyolab-related to {channel.mention}.")

        # Hack until I figure out how to individually reload slash commands
        # For now, they're reloaded by reloading the cog. This command is then pasted over the reloaded cog's version of this command to keep its cooldown.
        # May introduce a memory leak... who knows -- should be fixed sometime anyways
        #
        # TODO: reload only the slash commands instead of the entire module.

        self.bot.reload_extension(self.__module__)
        new_cog: Genshin_API_Cog = self.bot.get_cog(self.qualified_name)
        new_cog.gapi_notif = self.gapi_notif



    @gapi_main.command(
        name = "claim"
    )
    async def gapi_claim(self, ctx: commands.Context):

        NotAuthed = CommandError(f"{ctx.author.mention}, it appears you have not yet authorized me to claim your daily rewards. Please see `/gapi howto` and `/gapi auth`.")

        user_data = self.read_user_data()
        current_user_data = user_data.get(str(ctx.author.id))
        if not current_user_data: raise NotAuthed
        
        cookies = current_user_data["Genshin_Impact"].get("auth_cookies")
        if not cookies: raise NotAuthed


        # TODO: abstract error handling away to a centralized error handler
        try:
            await self.daily_claim_status(cookies)
        except CommandError as e:
            return await ctx.send(e)

        try:
            await self.daily_claim_exec(cookies)
        except CommandError as e:
            return await ctx.send(e)

        await ctx.send(f"{ctx.author.mention}, I have successfully claimed your daily login rewards from Hoyolab! Please claim your rewards in-game.")


    # Autoclaim

    __str__already_claimed = "{0.mention}, it appears your rewards have already been claimed today. Don't forget to collect them in-game!"
    __str__claim_success = "{0}, I have successfully claimed your daily login rewards from Hoyolab! Don't forget to collect them in-game!"
    __str__claim_fail = "{0}, something went awry in trying to claim your daily login rewards. Please see your DMs for further information. I apologize for the inconvenience!"

    @tasks.loop(time=[DAILY_CLAIM_TIME])
    async def gapi_claim_daily(self):
        print("claiming daily stuffs")

        user_data = self.read_user_data()
        succeeded = DefaultDict(list)
        failed = DefaultDict(list)

        for user_id, data in user_data.items():

            guilds = self.get_user_notif_guilds(user_id)
            user_id = int(user_id)

            cookies = data.get("Genshin_Impact", {}).get("auth_cookies")
            if not any(cookies.values()):
                continue

            user: discord.User = self.bot.get_user(user_id)

            # Check claim status
            try:
                await self.daily_claim_status(cookies=cookies)
            except CommandError as e:

                if not guilds:
                    await user.send(self.__str__already_claimed.format(user))
                    continue

                for guild in guilds:
                    failed[guild].append(user)
                continue
            
            # Try claiming
            try:
                await self.daily_claim_exec(cookies=cookies)
                
                if not guilds:
                    await user.send(self.__str__claim_success.format(user.mention))
                    continue
                
                for guild in guilds:
                    succeeded[guild].append(user)

            except CommandError as e:
                logger.warning(f"Daily claiming failed for user {user.id}: {e}")
                
                if not guilds:
                    await user.send(self.__str__claim_fail.format(user.mention))
                    continue

                for guild in guilds:
                    failed[guild].append(user)
                continue

        for guild_id, users in succeeded.items():
            channel_id = self.get_guild_notif_channel(guild_id)
            channel = self.bot.get_channel(channel_id)
            user_str = ", ".join(u.mention for u in users)

            await channel.send(self.__str__claim_success.format(user_str))

        for guild_id, users in failed.items():
            channel_id = self.get_guild_notif_channel(guild_id)
            channel = self.bot.get_channel(channel_id)
            user_str = ", ".join(u.mention for u in users)

            await channel.send(self.__str__claim_fail.format(user_str))
            

    @gapi_claim_daily.before_loop
    async def gapi_claim_daily_setup(self):

        # Try to claim before daily reset on cog load in case we missed a day
        if datetime.datetime.utcnow().time < DAILY_CLAIM_TIME:
            await self.gapi_claim_daily()



def setup(bot: commands.Bot):
    bot.add_cog(Genshin_API_Cog(bot))