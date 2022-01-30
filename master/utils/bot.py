from __future__ import annotations

import disnake
from disnake.ext import commands
from disnake.ext.commands import ExtensionNotLoaded
from disnake.ext.commands.common_bot_base import _is_submodule

import functools
import logging
import os
import sys
from types import ModuleType
from typing import Any, Callable, Optional, Union
import aiohttp
import db_models
from beanie import init_beanie
from dotenv import load_dotenv
from motor import motor_asyncio as motor

from .reload import reload_child_modules

reload_logger = logging.getLogger("reload")
reload_logger.setLevel(logging.DEBUG)


__all__ = ["CustomBot"]


load_dotenv()
user, pw, db_default = os.getenv("MONGO_USER"), os.getenv("MONGO_PASS"), os.getenv("MONGO_DB")
DB_URI = (
    f"mongodb+srv://{user}:{pw}@maid-in-abyss.kdpxk.mongodb.net/{db_default}"
    "?retryWrites=true&w=majority"
)


# CUSTOM BOT


class CustomBot(commands.Bot):
    def __init__(
        self,
        command_prefix: Optional[Union[str, list[str], Callable]] = None,
        description: str = None,
        **options: Any,
    ):
        self._motor = motor.AsyncIOMotorClient(DB_URI)
        super().__init__(command_prefix=command_prefix, description=description, **options)

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        await init_beanie(database=self._motor.discord, document_models=db_models.all())
        self.dispatch("db_connected")  # maybe temporary, maybe not
        await super().start(token, reconnect=reconnect)

    async def close(self):
        await super().close()

    @functools.cached_property
    def session(self) -> aiohttp.ClientSession:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=self.http.connector,
        )
        session._request = functools.partial(session._request, proxy=self.http.proxy)  # type: ignore
        return session

    # literally just a copy-paste from dpy, except for the `reload_submodules`` check w/ call
    def reload_extension(
        self, name: str, *, package: Optional[str] = None, reload_submodules: bool = False
    ) -> None:
        """Atomically reloads an extension.

        This replaces the extension with the same extension, only refreshed. This is
        equivalent to a :meth:`unload_extension` followed by a :meth:`load_extension`
        except done in an atomic way. That is, if an operation fails mid-reload then
        the bot will roll-back to the prior working state.

        Parameters
        ------------
        name: :class:`str`
            The extension name to reload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when reloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7
        reload_submodules: :class:`bool`
            Whether to reload the submodules loaded in the cog's module. For example,
            when set to `True`, reloading an extension `foo` that imports `bar` will
            also reload module `bar`. This makes it so that any changes made to bar.py
            will propagate to foo.py when foo.py is reloaded.

        Raises
        -------
        ExtensionNotLoaded
            The extension was not loaded.
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension setup function had an execution error.
        """

        name = self._resolve_name(name, package)
        lib: ModuleType = self._CommonBotBase__extensions.get(name)  # why is this mangled :/
        if lib is None:
            raise ExtensionNotLoaded(name)

        if reload_submodules:
            reload_child_modules(lib)
            # TODO: redo `init_beanie` when db models are reloaded

        # get the previous module states from sys modules
        modules = {
            name: module
            for name, module in sys.modules.items()
            if _is_submodule(lib.__name__, name)
        }

        try:
            # Unload and then load the module...
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, name)
            self.load_extension(name)
        except Exception:
            # if the load failed, the remnants should have been
            # cleaned from the load_extension function call
            # so let's load it from our old compiled library.
            lib.setup(self)  # type: ignore
            self._CommonBotBase__extensions[name] = lib

            # revert sys.modules back to normal and raise back to caller
            sys.modules.update(modules)
            raise

    # this is probably useless but :)
    async def getch_guild(self, id: int, /) -> disnake.Guild:
        return self.get_guild(id) or await self.fetch_guild(id)

    async def as_member(self, guild: disnake.Guild) -> Optional[disnake.Member]:
        return disnake.utils.get(guild.members, id=self.user.id)
