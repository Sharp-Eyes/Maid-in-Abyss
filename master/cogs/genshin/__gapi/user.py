from .exceptions import CookieError

import json
from typing import Union

from utils.classes import Paths
from utils.helpers import nested_get


__all__ = (
    "read_guild_data",
    "read_user_data",
    "get_guild_notif_channel",
    "get_user_notif_guilds",
    "get_user_cookies",
)

ID = Union[int, str]


def read_guild_data() -> dict:
    with open(Paths.guild_data) as guild_file:
        return json.load(guild_file)


def read_user_data() -> dict:
    with open(Paths.user_data) as user_file:
        return json.load(user_file)


def get_guild_notif_channel(guild_id: ID) -> int:
    """Get the channel ID to which the current guild sends its gapi notifications."""

    guild_data = read_guild_data()
    return nested_get(guild_data, str(guild_id), "Genshin_Impact", "gapi_notification_channel")


def get_user_notif_guilds(user_id: ID) -> list[int]:
    """Get a list of guild IDs to which a user is subscribed."""

    user_data = read_user_data()
    return nested_get(user_data, str(user_id), "Genshin_Impact", "gapi_notification_guilds", ret=[])


def get_user_cookies(*, user_id: Union[int, str] = None, user_data: dict = None) -> dict[str, str]:
    """Get the cookies of the user with the given ID. Returns none if this user was not found.
    If not provided with individual_user_data, it will read user_data.json instead.

    Parameters:
    -----------
    user_id: Union[:class:`int`, :class:`str`]
        the Discord UID of the target user.
    user_data: :class:`dict`
        the user data of *one* individual user, as obtained from user_data.json.
    """
    if not bool(user_id) ^ bool(user_data):
        raise ValueError("One and only one of 'user_id' and 'user_data' should be set.")

    if user_data is None:
        user_data = read_user_data().get(str(user_id), {})

    cookies = nested_get(user_data, "Genshin_Impact", "auth_cookies")
    if not cookies:
        raise CookieError(
            "{0.mention}, you seem to not have provided your authorization cookies. "
            "Please see `/gapi auth` if this is in error."
        )

    return cookies


def check_user_cookies(cookies: dict):
    pass
