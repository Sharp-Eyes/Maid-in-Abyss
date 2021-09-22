import datetime, pytz
from typing import Union
import aiohttp
import string, hashlib

from numpy import random

from .exceptions import *


import logging
logger = logging.getLogger("GAPI")


# Constants
OS_URL = "https://hk4e-api-os.mihoyo.com/event/sol/"
OS_ACT_ID = "e202102251931481"

BASE_URL = "https://bbs-api-os.hoyolab.com/"
DS_SALT = "6cqshh5dhw73bzxn20oexa9k516chk7s"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"

HEADERS = {
    # required headers
    "x-rpc-app_version": "1.5.0",  # overseas api uses 1.x.x, chinese api uses 2.x.x
    "x-rpc-client_type": "4",
    "x-rpc-language": "en-us",
    # authentication headers
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

    
    def get_API_datetime(self):
        return datetime.datetime.now(pytz.timezone("Asia/Shanghai"))
        
    def get_API_date(self):
        return self.get_API_datetime().strftime("%Y-%m-%d")


    async def fetch_endpoint(self, endpoint_url, *, request_type="get", cookies = None, **params):
        """Make an API call to the given endpoint url with provided authorization cookies.
        API calls can be either POST or GET, dependent on the endpoint. Can be provided with optional
        parameters `params`, which will be passed as JSON in POST-requests.
        """
        headers = HEADERS.copy()
        headers["ds"] = self.generate_ds_token()

        async with aiohttp.ClientSession() as session:
            request: Union[session.get, session.post] = getattr(session, request_type)
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


    async def daily_claim_status(self, cookies):
        params = dict(act_id = OS_ACT_ID)
        response = await self.fetch_endpoint(
            OS_URL + "info",
            cookies=cookies,
            **params
        )

        if response["first_bind"]: raise FirstSign(
            "Unfortunately, I was unable to claim your Hoyolab daily login rewards. "
            "It seems that you have not yet claimed the login rewards manually at "
            "least once. Due to API limitations, it appears this is necessary.\n"
            "Please claim your daily login rewards manually at https://webstatic-sea.mihoyo.com/ys/event/signin-sea/."
        )
        if response["is_sign"]: raise AlreadySigned("{0.mention}, it appears you have already signed in today")

        return response


    async def daily_claim_exec(self, cookies):
        """Sign into Hoyolab to claim daily rewards."""

        params = dict(lang = "en-us", act_id = OS_ACT_ID)
        response = await self.fetch_endpoint(
            OS_URL + "sign",
            request_type="post",
            cookies=cookies,
            **params
        )

        return response