# Credits for api reverse-engineering go to TheSadru.
# See https://github.com/thesadru/genshinstats/ for their work.

import json
from typing import Union
import discord
from discord.ext import commands, tasks

import asyncio
import aiohttp

import datetime
from discord.ext.commands.errors import CommandError
from numpy import random
import string, hashlib


# Type aliases
CS = aiohttp.ClientSession


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

COOKIES = {
    "ltoken": "uEecA6eaelVrOoPwiVmLf880jeQlXB7srhtniGi1",
    "ltuid": "17334943"
}



def generate_ds_token(salt: str = DS_SALT) -> str:
    """Creates a new ds token for authentication."""
    t = int(datetime.datetime.utcnow().toordinal())  # current seconds
    r = ''.join(random.choice(list(string.ascii_letters), 6))  # 6 random chars
    h = hashlib.md5(f"salt={salt}&t={t}&r={r}".encode()).hexdigest()  # hash and get hex
    return f'{t},{r},{h}'



class Genshin_API:
    """Class that organizes a couple helper functions for API calls"""

    async def fetch_endpoint(self, endpoint_url, method = "get", **params):

        print("~~~~", endpoint_url)
        HEADERS.update(ds = generate_ds_token())

        async with aiohttp.ClientSession() as session:
            request: Union[CS.get, CS.post] = getattr(session, method)
            async with request(url = endpoint_url, headers = HEADERS, cookies = COOKIES, json=params) as response:
                r = await response.read()
                print("!> ",r)
                response_data = json.loads(r)

        print(r)

        # if response_data["retcode"] != 0: raise CommandError(response_data["message"])
        return response_data["data"]

    
    async def daily_claim_status(self):
        params = dict(act_id = OS_ACT_ID)
        response = await self.fetch_endpoint(OS_URL + "info", **params)

        if response["first_bind"]: raise CommandError("You must manually claim daily rewards on Hoyolab at least once.")          # TODO: custom exception here
        if response["is_sign"]: raise CommandError("It appears you have already signed in today")

        return response

    async def daily_claim_exec(self):
        """Sign into Hoyolab to claim daily rewards."""

        params = dict(lang = "en-us", act_id = OS_ACT_ID)
        response = await self.fetch_endpoint(OS_URL + "sign", "post", **params)

        return response



class Genshin_API_Cog(commands.Cog, Genshin_API):


    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gapi_claim_daily.start()



    @commands.command(
        name = "test"
    )
    async def testreq(self, ctx):

        resp = await self.fetch_endpoint("https://api-os-takumi.mihoyo.com/binding/api/getUserGameRolesByCookie")
        await ctx.send(resp)

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
        try:
            await self.daily_claim_status()
        except CommandError as e:
            return await ctx.send(e)

        try:
            await self.daily_claim_exec()
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

        await self.gapi_claim_daily()


def setup(bot):
    bot.add_cog(Genshin_API_Cog(bot))