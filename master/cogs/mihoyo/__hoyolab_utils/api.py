from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import string
from typing import Literal, Union
import aiohttp
import pytz
from numpy import random

from .exceptions import AlreadySigned, FirstSign, UnintelligibleResponseError, validate_API_response

logger = logging.getLogger("GAPI")


__all__ = (
    "get_API_datetime",
    "get_API_date",
    "Hoyolab_API",
    "ValidGame",
)

DS_SALT = "6cqshh5dhw73bzxn20oexa9k516chk7s"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/58.0.3029.110 Safari/537.36"
)
HEADERS = {
    # required headers
    "x-rpc-app_version": "1.5.0",  # overseas api uses 1.x.x, chinese api uses 2.x.x
    "x-rpc-client_type": "4",
    "x-rpc-language": "en-us",
    # authentication headers
    "ds": "",
    # recommended headers
    "user-agent": USER_AGENT,
}

DAILY_SIGNIN_URL = {
    "Honkai Impact": "https://api-os-takumi.mihoyo.com/event/mani/",
    "Genshin Impact": "https://hk4e-api-os.mihoyo.com/event/sol/",
}
ACT_ID = {"Honkai Impact": "e202110291205111", "Genshin Impact": "e202102251931481"}

ValidRequestType = Union[aiohttp.ClientSession.get, aiohttp.ClientSession.post]
ValidGame = Literal["Honkai Impact", "Genshin Impact"]


def generate_ds_token(salt: str = DS_SALT) -> str:
    """Create a new ds token for authentication."""
    t = int(datetime.datetime.utcnow().toordinal())  # current seconds
    r = "".join(random.choice(list(string.ascii_letters), 6))  # 6 random chars
    h = hashlib.md5(f"salt={salt}&t={t}&r={r}".encode()).hexdigest()  # hash and get hex
    return f"{t},{r},{h}"


def get_API_datetime() -> datetime.datetime:
    """Get the current time as a datetime object attuned with HoYoLAB server time.
    (tz: Asia/Shanghai)
    """
    return datetime.datetime.now(pytz.timezone("Asia/Shanghai"))


def get_API_date() -> str:
    """Get the current date in yyyy-mm-dd, as is returned by the HoYoLAB API,
    attuned with HoYoLAB server time (tz: Asia/Shanghai).
    """
    return get_API_datetime().strftime("%Y-%m-%d")


class Hoyolab_API:
    """A class that organizes helper functions for HoYoLAB API calls."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    @property
    def date(self):
        """the current date in yyyy-mm-dd, as is returned by the HoYoLAB API,
        attuned with HoYoLAB server time (tz: Asia/Shanghai).
        """
        API_datetime = datetime.datetime.now(pytz.timezone("Asia/Shanghai"))
        return API_datetime.strftime("%Y-%m-%d")

    async def fetch_endpoint(
        self, endpoint_url: str, *, request_type: str = "get", cookies: dict = None, **params
    ) -> dict:
        """Make an API call to the given endpoint url with provided authorization cookies.
        API calls can be either POST or GET, dependent on the endpoint. Can be provided with
        optional parameters `params`, which will be passed as JSON in POST-requests.
        Returns the response JSON content in a dict.

        Parameters:
        -----------
        endpoint_url: :class:`str`
            The URL of the endpoint to which the API call is to be made.
        request_type: :class:`str`
            The type of request that is to be made to the API endpoint. Can be:\n
                `"get"` -> :method:`aiohttp.ClientSession.get`\n
                `"post"` -> :method:`aiohttp.ClientSession.post`
        cookies: :class:`dict`
            A dict that contains the user's authorization cookies.
        params:
            Any additional keyword arguments are passed as JSON parameters in the request.
            Mainly used to provide data in POST requests.
        """

        headers = HEADERS.copy()
        headers["ds"] = generate_ds_token()

        request: ValidRequestType = getattr(self.session, request_type)
        async with request(endpoint_url, headers=headers, cookies=cookies, json=params) as response:

            try:
                response_data: dict = await response.json()
                logger.log(1, response_data)
            except Exception as e:
                # TODO: figure out which exception to intercept here (for non-json output)
                response_data: str = await response.read()
                raise UnintelligibleResponseError(response_data)

        if response_data["retcode"] != 0:
            validate_API_response(response_data)

        return response_data["data"]

    async def get_game_accounts(cls, *, cookies) -> dict:
        """Get the game accounts of the user with the provided cookies."""
        data = await cls.fetch_endpoint(
            "https://api-os-takumi.mihoyo.com/binding/api/getUserGameRolesByCookie", cookies=cookies
        )
        return data["list"]

    async def daily_claim_status(cls, game, *, cookies: dict[str, str]):
        """Check whether the user whose authorization cookies were provided can claim
        their daily rewards.
        """
        params = {"act_id": ACT_ID[game]}
        response = await cls.fetch_endpoint(
            DAILY_SIGNIN_URL[game] + "info", cookies=cookies, **params
        )

        if response["first_bind"]:
            raise FirstSign(
                "Unfortunately, I was unable to claim your Hoyolab daily login rewards. "
                "It seems that you have not yet claimed the login rewards manually at "
                "least once. Due to API limitations, it appears this is necessary.\n"
                "Please claim your daily login rewards manually at "
                "https://webstatic-sea.mihoyo.com/ys/event/signin-sea/."
            )
        if response["is_sign"]:
            raise AlreadySigned("{0.mention}, it appears you have already signed in today")

        return response

    async def daily_claim_exec(cls, game, *, cookies: dict[str, str]):
        """Sign into Hoyolab to claim daily rewards."""

        params = {"lang": "en-us", "act_id": ACT_ID[game]}
        response = await cls.fetch_endpoint(
            DAILY_SIGNIN_URL[game] + "sign", request_type="post", cookies=cookies, **params
        )

        return response

    async def redeem_cdkey(cls, *, cookies, cdkey):
        accs = [
            account
            for account in await cls.get_game_accounts(cookies=cookies)
            if account["level"] >= 10
        ]
        const_params = {"cdkey": cdkey, "game_biz": "hk4e_global", "lang": "en"}
        filtered_cookies = {k: v for k, v in cookies.items() if k in ["account_id", "cookie_token"]}

        for i, acc in enumerate(accs):
            if i:
                await asyncio.sleep(5)  # Ratelimit
            await cls.fetch_endpoint(
                "https://hk4e-api-os.mihoyo.com/common/apicdkey/api/webExchangeCdkey",
                cookies=filtered_cookies,
                uid=acc["game_uid"],
                region=acc["region"],
                **const_params,
            )
