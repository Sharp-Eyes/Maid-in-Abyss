# Credits for api reverse-engineering go to TheSadru.
# See https://github.com/thesadru/genshinstats/ for their work.

# TODO: cancel task on disconnect if possible

from .__gapi import Genshin_API_Claimer
from .__gapi.exceptions import *

import discord
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

import json

from numpy import array
from typing import DefaultDict

import datetime

from utils.helpers import deep_update_json, nested_get
from utils.classes import Paths


import logging
logger = logging.getLogger("GAPI")


# Predetermine guilds for local slash commands

with open(Paths.guild_data) as guild_file:
    guild_data: dict = json.load(guild_file)
    guilds = [
        int(guild_id)
        for guild_id, data in guild_data.items()
        if nested_get(data, "Genshin_Impact", "gapi_notification_channel")
    ]

DAILY_CLAIM_TIME = datetime.time.fromisoformat("16:00:02")  # UTC


class Genshin_API_Cog(commands.Cog, Genshin_API_Claimer):


    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gapi_claim_daily.start()

    # Notification subscription management

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
            "\n\nBy default, you will be notified in DMs. If this is not desired, you can sign up to be messaged in a guild instead, "
            "assuming that guild has set up a notification channel. Please see `/gapi subscribe` for further information.",
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
            guilds.remove(ctx.guild_id)
            s = "You will no longer receive notifications in this guild!"
            if guilds:
                s += " You now receive notifications in the following guilds:\n" + ", ".join(f"**{g}**" for g in guilds)
            else:
                s += " Since you are now no longer subscribed to any guilds, you will now be notified in DMs instead."
            await ctx.send(s, hidden = True)
        except (ValueError, AttributeError):
            await ctx.send(
                "It appears you were not subscribed to this guild to begin with. Did you perhaps mean to use `/gapi subscriptions add`?",
                hidden=True
            )

        new_data = {str(ctx.author_id): {"Genshin_Impact": {"gapi_notification_guilds": guilds}}}
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


    # Basic functionality for which idk how to employ slash commands yet.

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


    # Claim slashcommand

    __str__claim_success = "{}, I have successfully claimed your daily login rewards from Hoyolab! Don't forget to collect them in-game!"
    __str__claim_fail = "{}, something went awry in trying to claim your daily login rewards. Please see your DMs for further information. I apologize for the inconvenience!"

    @cog_ext.cog_subcommand(
        base="gapi",
        name="claim",
        description="Claim your daily login rewards. Will only work after authorizing with /gapi auth.",
        guild_ids=guilds
    )
    async def gapi_claim(self, ctx: SlashContext):
        individual_data = self.read_user_data().get(str(ctx.author_id), {})
        user = ctx.author

        try:
            await self.claim_daily_reward(
                user=user,
                individual_data=individual_data
            )
        except GenshinAPIError as e:

             # Custom behavior in guilds vs DMs
            if ctx.guild:
                await ctx.send(
                    "An unexpected error occurred in trying to claim your rewards. Please see our DMs for further information.",
                    hidden=True
                )

            # Left these here just in case we need unique behaviour for certain exceptions
            if isinstance(e, FirstSign):
                return await user.send(str(e).format(user))
            
            if isinstance(e, AlreadySigned):
                return await user.send(str(e).format(user))

        return await ctx.send(self.__str__claim_success.format(user.mention), hidden=True)


    # Autoclaim

    @tasks.loop(time=[DAILY_CLAIM_TIME])
    async def gapi_claim_daily(self):
        logger.log(1, "claiming daily stuffs")

        user_data = self.read_user_data()
        succeeded = DefaultDict(list[discord.User])
        failed = DefaultDict(list[discord.User])


        for user_id, data in user_data.items():
            user: discord.User = self.bot.get_user(int(user_id))
            guilds = self.get_user_notif_guilds(user_id)

            try:
                await self.claim_daily_reward(
                    user=user,
                    individual_data=data
                )
                for guild in guilds:
                    succeeded[guild].append(user)
        
            except GenshinAPIError as e:
                for guild in guilds:
                    failed[guild].append(user)
                
                if isinstance(e, FirstSign):
                    return await user.send(str(e).format(user))
                
                if isinstance(e, AlreadySigned):
                    # Don't want to ping a user that already checked in with daily check-in, just to minimize spam
                    return


        for guild_id, users in succeeded.items():
            channel_id = self.get_guild_notif_channel(guild_id)
            channel: discord.TextChannel = self.bot.get_channel(channel_id)
            user_str = ", ".join(u.mention for u in users)

            await channel.send(self.__str__claim_success.format(user_str))

        for guild_id, users in failed.items():
            channel_id = self.get_guild_notif_channel(guild_id)
            channel: discord.TextChannel = self.bot.get_channel(channel_id)
            user_str = ", ".join(u.mention for u in users)

            await channel.send(self.__str__claim_fail.format(user_str))
            

    @gapi_claim_daily.before_loop
    async def gapi_claim_daily_setup(self):

        # Try to claim before daily reset on cog load in case we missed a day
        if datetime.datetime.utcnow().time() < DAILY_CLAIM_TIME:
           await self.gapi_claim_daily()
        pass

    def cog_unload(self):
        self.gapi_claim_daily.cancel()



def setup(bot: commands.Bot):
    bot.add_cog(Genshin_API_Cog(bot))