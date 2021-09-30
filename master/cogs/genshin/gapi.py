# Credits for api reverse-engineering go to TheSadru.
# See https://github.com/thesadru/genshinstats/ for their work.


from .__gapi import (
    GUILDS,
    CheckIn_Mixin, CDKey_Mixin,
    get_guild_notif_channel, get_user_notif_guilds, validate_cdkey_cookies,
    read_user_data, get_user_cookies
)
from .__gapi.exceptions import CookieError, GenshinAPIError, FirstSign, AlreadySigned

import disnake
from disnake.ext import commands
from disnake.ext.commands import Param
from disnake import ApplicationCommandInteraction as Interaction

from utils.helpers import deep_update_json, create_interaction_identifier
from utils.classes import Paths, Codeblock
from utils.overrides import FullReloadCog

import logging
logger = logging.getLogger("GAPI")


class Gapi_Auth_Autocomp:
    cache = dict()

    @staticmethod
    def cookie_or_input(current_cookie: str, inp: str) -> str:
        print(current_cookie, inp)
        if not current_cookie:
            return inp
        if current_cookie.startswith(inp):
            return current_cookie
        return inp

    @classmethod
    async def run(cls, inter: Interaction, inp: str) -> list[str]:

        current = inter.data.focused_option.name.replace("-", "_")
        identifier = create_interaction_identifier(inter)
        cookies = cls.cache.get(identifier)
        if cookies:
            return [cls.cookie_or_input(cookies[current], inp)]

        try:
            cookies = get_user_cookies(user_id=inter.author.id)
        except CookieError:
            cookies = {}

        cls.cache[identifier] = cookies
        return [cls.cookie_or_input(cookies[current], inp)]


class GenshinAPI_Cog(CheckIn_Mixin, CDKey_Mixin, FullReloadCog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gapi_claim_daily.start()
        # bot.sess

    def cog_unload(self):
        if self.gapi_claim_daily.is_running:
            self.gapi_claim_daily.cancel()

    @commands.slash_command(name="gapi", guild_ids=GUILDS)
    async def gapi_slash(self, _):
        "Anything Genshin-API related."
        pass

    @gapi_slash.sub_command_group(name="subscriptions")
    async def gapi_subs(self, _):
        "Manage in which servers you want to be notified of anything Hoyolab-related."
        pass

    @gapi_subs.sub_command(name="add")
    async def gapi_subscribe(self, inter: Interaction):
        """Receive automatic Hoyolab notifications in this guild instead of DMs."""

        response = inter.response
        guild_id = inter.guild_id
        author_id = inter.author.id

        channel = get_guild_notif_channel(guild_id)
        guilds = get_user_notif_guilds(author_id)
        if not channel:
            return await response.send_message(
                f"**{inter.guild.name}** does not appear to have a notification channel set up. "
                "Please contact an administrator if you would like to see one set up.",
                ephemeral=True
            )

        if inter.guild_id in guilds:
            return await response.send_message(
                "It appears you are already subscribed to receive notifications in this guild.",
                ephemeral=True
            )

        new_guilds = [*guilds, guild_id]
        new_data = {str(author_id): {"Genshin_Impact": {"gapi_notification_guilds": new_guilds}}}
        deep_update_json(Paths.user_data, new_data)

        return await response.send_message(
            "You have been successfully signed up to receive notifications in this guild!~ "
            "You now receive notifications in the following guilds:\n"
            + ", ".join(f"**{g}**" for g in new_guilds),
            ephemeral=True
        )

    @gapi_subs.sub_command(name="remove")
    async def gapi_unsubscribe(self, inter: Interaction):
        """Unsubscribe from notifications in this guild.
        With no subscriptions, you will be notified in DMs.
        """

        response = inter.response
        author_id = inter.author.id
        guild_id = inter.guild_id

        guilds = get_user_notif_guilds(author_id)

        try:
            guilds.remove(guild_id)
            s = "You will no longer receive notifications in this guild!"
            if guilds:
                s += (
                    " You now receive notifications in the following guilds:\n"
                    + ", ".join(f"**{g}**" for g in guilds)
                )
            else:
                s += (
                    " Since you are now no longer subscribed to any guilds,"
                    " you will now be notified in DMs instead."
                )
            await response.send_message(s, ephemeral=True)
        except (ValueError, AttributeError):
            await response.send_message(
                "It appears you were not subscribed to this guild to begin with. "
                "Did you perhaps mean to use `/gapi subscriptions add`?",
                ephemeral=True
            )

        new_data = {str(author_id): {"Genshin_Impact": {"gapi_notification_guilds": guilds}}}
        deep_update_json(Paths.user_data, new_data)

    @gapi_subs.sub_command(name="view")
    async def gapi_view_subscriptions(self, inter: Interaction):
        "See which guilds you are currently set to receive notifications in, if any."

        response = inter.response
        author_id = inter.author.id

        guilds = get_user_notif_guilds(author_id)

        if guilds:
            return await response.send_message(
                "You are currently set to receive notifications in the following guilds:\n"
                + ", ".join(f"**{g}**" for g in guilds),
                ephemeral=True
            )
        await response.send_message(
            "You are currently not subscribed to any guilds. You will be notified in DMs instead.",
            ephemeral=True
        )

    @gapi_slash.sub_command(name="redeem")
    async def gapi_redeem(
        self,
        inter: Interaction,
        cdkey: str = Param(desc="The redeem code/cdkey you wish to redeem.")
    ):
        response = inter.response
        author_id = inter.author.id

        cookies = self.get_user_cookies(user_id=author_id)
        if not validate_cdkey_cookies(cookies):
            return await response.send_message(
                "To be able to redeem rewards for redeem codes/cdkeys, your `account_id` and "
                "`cookie_token` authorization cookies must be set. Regrettably, since it seems "
                "you have not set these, I am unable to redeem your rewards. Please check your "
                "cookies with `/gapi auth view` and amend the issue with `/gapi auth set`."
            )
        response = await self.redeem_cdkey(cookies=cookies, cdkey=cdkey)

    @gapi_slash.sub_command_group(name="auth")
    async def gapi_auth(self, inter: Interaction):
        pass

    @gapi_auth.sub_command(name="view")
    async def gapi_view_cookies(self, inter: Interaction):
        """View the authorization data I currently have stored for your account."""

        author = inter.author
        cookies = get_user_cookies(user_id=author.id)

        await inter.response.send_message(
            "The following cookies are stored for your account:\n"
            + ", ".join(f"{k}: {v}" for k, v in cookies.items()),
            ephemeral=True
        )

    @gapi_auth.sub_command(name="set")
    async def gapi_set_cookies(
        self,
        inter: Interaction,
        ltuid: str = Param(
            "", desc="If selected, please make sure to also use LTOKEN.",
            autocomp=Gapi_Auth_Autocomp.run
        ),
        ltoken: str = Param(
            "", desc="If selected, please make sure to also use LTUID.",
            autocomp=Gapi_Auth_Autocomp.run
        ),
        account_id: str = Param(
            "", desc="If selected, please make sure to also use COOKIE_TOKEN.",
            autocomp=Gapi_Auth_Autocomp.run
        ),
        cookie_token: str = Param(
            "", desc="If selected, please make sure to also use ACCOUNT_ID.",
            autocomp=Gapi_Auth_Autocomp.run
        )
    ):
        """Enter your Hoyolab authentication tokens.
        Accepts: LTUID & LTOKEN and/or ACCOUNT_ID & COOKIE_TOKEN.
        """
        # Remove the current interaction from cache
        identifier = create_interaction_identifier(inter)
        Gapi_Auth_Autocomp.cache.pop(identifier)

        response = inter.response
        view = Gapi_Auth_Confirmation()
        author_id = inter.author.id

        cookies = dict(
            ltuid=ltuid,
            ltoken=ltoken,
            account_id=account_id,
            cookie_token=cookie_token
        )
        cookie_str = Codeblock(
            "\n".join(f"{k:>12}: {v}"for k, v in cookies.items()),
            lang="yaml"
        )

        try:
            accounts = await self.get_game_accounts(cookies=cookies)
        except CookieError:
            return await response.send_message(
                "Regrettably, I could not find an account bound to the cookies you entered:\n"
                + cookie_str
                + "\nPlease double-check your authorization cookies and try again."
            )

        acc_str = ";\n".join(
            "- {nickname}, with UID {game_uid}, at AR {level}".format(**acc)
            for acc in accounts
        )

        await response.send_message(
            f"I found the following account(s):\n{acc_str}.\n\n"
            "Are you sure you wish to register these cookies?",
            view=view,
            ephemeral=True,
        )

        await view.wait()
        if view.value:
            new_data = {str(author_id): {"Genshin_Impact": {"auth_cookies": cookies}}}
            deep_update_json(Paths.user_data, new_data, update_falsy=False)

            await inter.edit_original_message(
                content="I have successfully set the following data:" + cookie_str
                + "By default, you will be notified in DMs. If this is not desired, you can sign "
                "up to be messaged in a guild instead, assuming that guild has set up a "
                "notifications channel. Please see `/gapi subscribe` for further information.",
                view=None
            )
        else:
            await inter.edit_original_message(
                content="Aborted the registration process. "
                        "Please feel free to try again if anything went wrong.",
                view=None
            )

    @gapi_slash.sub_command(name="claim")
    async def gapi_claim(self, inter: Interaction):
        "Claim your daily login rewards. Will only work after authorizing with /gapi auth."

        response = inter.response
        author = inter.author

        individual_data = read_user_data().get(str(author.id), {})
        try:
            await self.do_checkin_for(
                user=author,
                individual_data=individual_data
            )
        except GenshinAPIError as e:

            # Custom behavior in guilds vs DMs
            if inter.guild:
                await response.send_message(
                    self.__str__checkin_fail.format(author.mention),
                    ephemeral=True
                )

            # Left these here just in case we need unique behaviour for certain exceptions
            if isinstance(e, FirstSign):
                return await author.send(str(e).format(author))

            if isinstance(e, AlreadySigned):
                return await author.send(str(e).format(author))

        return await response.send_message(
            self.__str__checkin_success.format(author.mention),
            ephemeral=True
        )


class Gapi_Auth_Confirmation(disnake.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @disnake.ui.button(label="Confirm", style=disnake.ButtonStyle.green)
    async def confirm(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.value = True
        self.stop()

    @disnake.ui.button(label="Cancel", style=disnake.ButtonStyle.red)
    async def cancel(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.value = False
        self.stop()


def setup(bot: commands.Bot):
    bot.add_cog(GenshinAPI_Cog(bot))
