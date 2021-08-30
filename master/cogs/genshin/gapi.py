# Credits for api reverse-engineering go to TheSadru.
# See https://github.com/thesadru/genshinstats/ for their work.

import json
from typing import Union
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




def generate_ds_token(salt: str = DS_SALT) -> str:
    """Creates a new ds token for authentication."""
    t = int(datetime.datetime.utcnow().toordinal())  # current seconds
    r = ''.join(random.choice(list(string.ascii_letters), 6))  # 6 random chars
    h = hashlib.md5(f"salt={salt}&t={t}&r={r}".encode()).hexdigest()  # hash and get hex
    return f'{t},{r},{h}'



class Genshin_API:
    """Class that organizes a couple helper functions for API calls"""

    async def fetch_endpoint(self, endpoint_url, *, request_type="get", cookies = None, **params):

        HEADERS.update(ds = generate_ds_token())

        async with aiohttp.ClientSession() as session:
            request: Union[session.get, session.post] = getattr(session, request_type)
            async with request(endpoint_url, headers=HEADERS, cookies=cookies, json=params) as response:
                r = await response.read()
                print("!> ",r)
                response_data = json.loads(r)

        print(r)
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
        #self.gapi_claim_daily.start()


    @cog_ext.cog_subcommand(
        base="gapi",
        name="auth",
        guild_ids=[701039771157397526],
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
        ])
    async def bigtest(self, ctx: SlashContext, ltuid="", ltoken="", account_id="", cookie_token=""):

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

        # TODO: properly output cookies
        return await ctx.send(f"I have successfully set the following data:\n{ltuid=}, {ltoken=}, {account_id=}, {cookie_token=}", hidden=True)





    @commands.group(
        name = "genshin_api",
        aliases = ["gapi"]
    )
    async def gapi_main(self, _):
        pass


    @gapi_main.command(
        name = "claim"
    )
    async def gapi_claim(self, ctx: commands.Context):

        NotAuthed = CommandError(f"{ctx.author.mention}, it appears you have not yet authorized me to claim your daily rewards. Please see `/gapi howto` and `/gapi auth`.")

        with open(Paths.user_data) as user_file:
            user_data = json.load(user_file)
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

    

    @tasks.loop(time=[DAILY_CLAIM_TIME])
    async def gapi_claim_daily(self):
        succeeded = []
        users = [1,2]

        g: discord.Guild = self.bot.get_guild(701039771157397526)
        c: discord.TextChannel = g.get_channel(701039771614576693)

        for user in users:
            try:
                await self.daily_claim_status()
            except CommandError as e:
                await c.send(e)
                continue

            try:
                resp = await self.daily_claim_exec()
            except CommandError as e:
                await c.send(e)
                continue

            if resp: succeeded.append(user)

        if succeeded:
            await c.send(f"{succeeded}, I have successfully claimed your daily login rewards from Hoyolab! Please claim your rewards in-game.")

    @gapi_claim_daily.before_loop
    async def gapi_claim_daily_setup(self):
        pass
        #await self.gapi_claim_daily()



def setup(bot: commands.Cog):

    cog = Genshin_API_Cog(bot)
    bot.add_cog(cog)
    return cog