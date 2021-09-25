import sys
import os
import importlib.util
import re

from typing import Any
from types import ModuleType
from collections import defaultdict

from discord.ext import commands
from utils.classes import defaultlist

class Full_Reload_Cog(commands.Cog):
    """A custom cog implementation that, when reloaded, ensures all the modules
    loaded by the cog's source module are reloaded as well. For example, a module
    `a.py` that imports `foo` and implements cog `Bar` will automatically reload
    module `foo` when cog `Bar` is reloaded with the reload command defined in
    `cogs.administrative.exts`.
    """

    def _prep_reload(self):

        # Pattern that only matches 'custom', self-made module names. Mostly used because we don't try to reload
        # modules like `re` or `discord`, as they won't be modified during runtime (or at all) anyways.
        pat = r"^cogs\..*$|^utils\..*$"

        # Since the passed self is always the calling class instance, calling `on_cog_reload` from a class that
        # subclasses `Full_Reload_Cog` will make self that instance, not an instance of `Full_Reload_Cog`. We can
        # use that to grab the globals of the module in which that class is defined.
        glb = sys.modules[self.__module__].__dict__

        def make_new():
            return defaultdict(set)
        modules = defaultlist(make_new)
        found_parents = set()

        def reload(module: ModuleType):
            """Re-run the module and paste the result lib over the current one.
            If this fails, the old lib is simply pasted back over the new one.
            """
            mod = module.__name__
            spec = importlib.util.find_spec(mod)
            lib = importlib.util.module_from_spec(spec)
            prev = sys.modules[mod]
            sys.modules[mod] = lib
            try:
                spec.loader.exec_module(lib)
            except Exception as e:
                sys.modules[mod] = prev
                raise e

        def check_for_init_parent(module: ModuleType):
            """Check if the module is a child of a module with an __init__.py file.
            If so, add the parent module to the reload dict too. Otherwise, imports
            from the parent module (folder name) would not actually reflect the
            updated child modules.
            """
            path = os.path.dirname(module.__file__)
            files = os.listdir(path)
            if "__init__.py" in files:
                return os.path.relpath(path, "master").replace("\\",".")
                
        
        def get_modules_rec(glb: dict[str, Any], depth: int = 0):
            """Recursively get all modules imported by a module, then all modules imported by
            those imported modules, and so forth. These fill out `modules` in order of the
            recursion depth they were encountered at. Furthermore, for each module, the items
            imported from that module are stored. This **will** contain duplicates.

            This will create a sort of dependency 'tree', e.g.:
            [
                __main__ imports mod A, mod B, cls c from mod C;
                A imports mod B, cls c from mod C // B imports mod C, mod D, cls e from mod E // C imports mod D
                B imports mod C, mod D, cls e from mod E // C imports mod D
                C imports mod D
            ]            
            """
            if depth > 50: return   # Arbitrary, much higher than needed; just here to prevent spiral imports to recurse for too long.
            for obj in glb.values():
                
                if not hasattr(obj, "__module__"):
                    if isinstance(obj, ModuleType) and re.match(pat, obj.__name__):
                        # Directly encountered a custom module
                        modules[depth][obj.__name__]

                    # Encountered something that is not a module nor contains a reference to a module, thus irrelevant.
                    continue

                # Encountered a non-module object that does contain a reference to a module
                # e.g. `Paths` from `from utils.classes import Paths`.
                obj_mod_name = obj.__module__
                if obj_mod_name == glb["__name__"]: continue     # The current module is reloaded by bot.reload_extension()
                if not re.match(pat, obj_mod_name): continue     

                modules[depth][obj_mod_name].add(obj)
                
                # Get the currently loaded module from its name
                obj_module = sys.modules[obj_mod_name]
                
                # If a module's contents can be imported through an __init__.py file, that init file must be reloaded as well.
                # Therefore, we have to check the directory of each module for __init__.py files.
                parent = check_for_init_parent(obj_module)
                if parent:
                    # If we find one at depth 0, we shift everything we found to depth 1 and prepend the parent at depth 0
                    if depth == 0:
                        depth += 1
                        modules.insert(0, make_new())
                        modules[0][parent]
                        found_parents.add(parent)

                    # Else we can just add it at depth-1. We make sure to only add the parent at the lowest possible depth,
                    # as reloading the parent should be done after all its children modules have been reloaded, and modules
                    # will be loaded from greatest depth to lowest (explained later).
                    elif parent not in found_parents:
                        modules[depth-1][parent]
                        found_parents.add(parent)

                get_modules_rec(obj_module.__dict__, depth=depth+1)

        # Construct 'dependency tree'
        get_modules_rec(glb)

        # Walk over tree from the back, ignoring any encountered duplicates (leaving the first one found in)
        # This makes sure that all the dependencies are 'in shortest order' and without duplicates; if we then
        # import the list in reversed order (same as this step), we are guaranteed to import all modules'
        # dependencies before we import the modules themselves. The previous example gets reduced to:
        # [
        #     __main__ imports mod A, mod B, cls c from mod C;
        #     A imports mod B, cls c from mod C
        #     B imports mod C, mod D, cls e from mod E
        #     C imports mod D
        # ]
        to_ignore = set()
        for mods in reversed(modules):
            mods: dict[str, set]    # typehint
            
            new = mods.keys() - to_ignore
            for mod in new:
                module = sys.modules[mod]
                reload(module)

                # overwrite everything that was imported from the module to the newly reloaded module's instances
                for o in mods[mod]:
                    # pretty much does what "from <mod> import <o>" does
                    glb[o.__name__] = getattr(sys.modules[mod], o.__name__)

            to_ignore.update(mods)
