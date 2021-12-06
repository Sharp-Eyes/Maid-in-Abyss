from __future__ import annotations

import disnake
from disnake.ext import commands
from disnake.ext.commands import ExtensionNotLoaded
from disnake.ext.commands.common_bot_base import _is_submodule

import importlib.util
import logging
import os
import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable, Mapping, Optional, Union
import aiohttp
from dotenv import load_dotenv
from motor import motor_asyncio as motor
from odmantic import AIOEngine

reload_logger = logging.getLogger("reload")
reload_logger.setLevel(logging.DEBUG)


__all__ = "CustomBot" "FullReloadCog"


load_dotenv()
user, pw, db_default = os.getenv("MONGO_USER"), os.getenv("MONGO_PASS"), os.getenv("MONGO_DB")
DB_URI = (
    f"mongodb+srv://{user}:{pw}@maid-in-abyss.kdpxk.mongodb.net/{db_default}"
    "?retryWrites=true&w=majority"
)
MAIN_DIR = os.path.dirname(sys.modules["__main__"].__file__)
START = object()


# Custom bot


def is_custom_module(module: ModuleType) -> bool:
    """Check whether the passed module is a 'custom module'. This is done by checking
    whether the module's directory is a subdirectory of where the main file is located.

    For sake of sanity, also prevents reloading _this_ module
    """
    if not hasattr(module, "__file__"):  # certain builtins such as sys don't have __file__
        return False
    if module.__name__ == __name__:
        return False
    module_dir = os.path.dirname(module.__file__)
    return MAIN_DIR == os.path.commonpath([MAIN_DIR, module_dir])


def check_for_init_parent(module: ModuleType) -> Optional[str]:
    """Check if the module is a child of a module with an __init__.py file.
    If so, add the parent module to the reload dict too. Otherwise, imports
    from the parent module (folder name) would not actually reflect the
    updated child modules.
    """
    path = os.path.dirname(module.__file__)
    files = os.listdir(path)
    if "__init__.py" in files:
        return os.path.relpath(path, "master").replace("\\", ".")


@dataclass
class ModuleStorage:
    """Represents how a module is stored to enable reloading of submodules.

    Attributes:
    -----------
    priority: :class:`int`
        Represents in what order the modules are reloaded. A larger priority
        (greater number) is reloaded first.
    module: Optional[:class:`ModuleType`]
        The module that is to be reloaded. Mainly used to store the old module
        state for atomic reloading. In case this is `None`, it can always be
        obtained later through `sys.modules`.
    module_imports: :class:`set`[:class:`str`]
        A set that holds all the names of items imported from that module. For
        example, if the module contains a line `from foo import bar, baz`,
        this set will contain `"bar"` and `"baz"`.
    """

    priority: int
    module: Optional[ModuleType] = None
    module_imports: set[str] = field(default_factory=set)


def update_module_storage(
    modules: Mapping[str, ModuleStorage],
    depth: int,
    module_name: str,
    module: Optional[ModuleType] = None,
    imported_item: Optional[str] = None,
):
    """Adds a module to storage or updates a module already in storage.

    If the passed `module_name` is not yet in `modules`, it is added.
    Otherwise, if the passed `depth` is lower than the currently stored
    `priority`, `priority` is set to `depth`, such that the module is
    always reloaded after its dependents are.
    """

    if module_name in modules:
        mod = modules[module_name]
        if depth < mod.priority:
            mod.priority = depth

    else:
        mod = ModuleStorage(depth, module)
        modules[module_name] = mod

    if imported_item:
        # fingers crossed there's no shadowing going on, otherwise this
        # may shadow 'the wrong way around'
        mod.module_imports.add(imported_item)

    return mod


def recursive_magic_fuckery(
    globals_: dict[str, Any],
    modules: Mapping[str, ModuleStorage] = START,
    depth: int = 0,
) -> Mapping[str, ModuleStorage]:
    """Recursively walk through all modules and objects in the provided `globals`
    dict. Registers and indexes each module referenced by the globals to optimize
    reload order, then recursively does the same for the globals of all found objects.
    """
    # TODO: rename

    if modules is START:
        modules = {}

    for obj_name, obj in globals_.items():

        if not hasattr(obj, "__module__"):
            if isinstance(obj, ModuleType) and is_custom_module(obj):
                # Directly encountered a custom module
                update_module_storage(modules, depth, obj_name, obj)

            # Not a module, nor contains a reference to a module
            continue

        # Non-module with reference to module
        obj_module_name: str = obj.__module__
        if obj_module_name == globals_["__name__"]:
            continue  # Reloading current module is handled by dpy afterwards

        obj_module = sys.modules[obj_module_name]
        if not is_custom_module(obj_module):
            continue

        update_module_storage(modules, depth, obj_module_name, obj_module, obj_name)

        parent_name = check_for_init_parent(obj_module)
        if parent_name:
            update_module_storage(modules, depth, parent_name)

        # Check for more imports inside the object's source module
        recursive_magic_fuckery(obj_module.__dict__, modules, depth=depth + 1)

    return modules


class CustomBot(commands.Bot):
    def __init__(
        self,
        command_prefix: Optional[Union[str, list[str], Callable]] = None,
        description: str = None,
        **options: Any,
    ):
        self._motor = motor.AsyncIOMotorClient(DB_URI)
        self.db = AIOEngine(self._motor, "discord")
        super().__init__(command_prefix=command_prefix, description=description, **options)

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        self.session = aiohttp.ClientSession()

        self.dispatch("db_connected")

        await super().start(token, reconnect=reconnect)

    async def close(self):
        await self.session.close()
        await self.db.close()
        return await super().close()

    def _reload_submodules(self, lib: ModuleType) -> None:
        """Atomically reloads all 'custom' submodules of a given module."""

        lib_globals = lib.__dict__
        module_storage = dict(
            sorted(recursive_magic_fuckery(lib_globals).items(), key=lambda pair: -pair[1].priority)
        )

        old: dict[str, ModuleType] = {}
        for module_name, module_data in module_storage.items():
            reload_logger.debug(
                f"Reloading items {module_data.module_imports} " f"from module {module_name}"
            )

            spec = importlib.util.find_spec(module_name)
            lib = importlib.util.module_from_spec(spec)
            old[module_name] = module_data.module or sys.modules[module_name]
            try:
                sys.modules[module_name] = lib
                spec.loader.exec_module(lib)
            except Exception:
                # Undo all previous module imports
                sys.modules.update(old)

                # Undo all `from module import x` imports
                for module_name in old:
                    module_data = module_storage[module_name]
                    for obj_name in module_data.module_imports:
                        lib_globals[obj_name] = getattr(old[module_name], obj_name)
                raise

            for obj_name in module_data.module_imports:
                lib_globals[obj_name] = getattr(sys.modules[module_name], obj_name)

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
        lib = self._CommonBotBase__extensions.get(name)  # why is this mangled :/
        if lib is None:
            raise ExtensionNotLoaded(name)

        if reload_submodules:
            self._reload_submodules(lib)

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

    async def getch_guild(self, id: int, /) -> disnake.Guild:
        return self.get_guild(id) or await self.fetch_guild(id)

    async def as_member(self, guild: disnake.Guild) -> Optional[disnake.Member]:
        return disnake.utils.get(guild.members, id=self.user.id)
