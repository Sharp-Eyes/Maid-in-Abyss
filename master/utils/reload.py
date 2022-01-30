import importlib.util
import logging
import os
import typing as t
import sys
from dataclasses import dataclass, field
from types import ModuleType

__all__ = [
    "MAIN_DIR",
    "is_custom_module",
    "walk_module_imports",
    "linearize_imports",
]

logger = logging.getLogger("reload")
logger.setLevel(logging.DEBUG)

# Directory from which the bot is run, used to determine whether a module should be reloaded or not
MAIN_DIR: str = os.path.dirname(sys.modules["__main__"].__file__)  # type: ignore


def is_custom_module(module: ModuleType) -> bool:
    """Check whether the passed module is a 'custom module'.

    This is done by checking whether the module is in a subdirectory of the main directory.

    Parameters
    ----------
    module: :class:`ModuleType`:
        The module that is to be checked.

    Returns
    -------
    :class:`bool`:
        Whether or not the module is a custom module.
    """
    if not (module_file := getattr(module, "__file__", None)):
        return False  # C-based modules don't have __file__
    if module.__name__ in ["utils.bot", "utils.reload"]:
        return False  # necessary so that reloading doesn't break itself, as both files are 'custom'
    return MAIN_DIR == os.path.commonpath([MAIN_DIR, os.path.dirname(module_file)])


@dataclass
class ModuleData:
    """Represents a module and its 'child' imports.

    Attributes
    ----------
    depth: :class:`int`
        The maximum relative depth at which the module is imported.
        This is necessary to pre-sort the child modules for the C3-linearization algorithm.
    module: :class:`ModuleType`
        The module that is to be reloaded.
    children: set[:class:`str`]
        A set that holds the names of all modules imported by this module.
    """

    depth: int
    module: ModuleType
    children: set[str] = field(default_factory=set)


def walk_module_imports(module: ModuleType, depth: int = 0) -> dict[str, ModuleData]:
    """Determine all custom module imports for a provided module, then recursively
    do the same for all 'child' imports.

    Parameters
    ----------
    module: :class:`ModuleType`
        The module that is to be reloaded.

    Returns
    -------
    dict[:class:`str`, :class:`ModuleData`]:
        A mapping of a module's name to a dataclass including the module object and its imports.
    """
    children: set[str] = set()
    for obj in module.__dict__.values():

        if not hasattr(obj, "__module__"):
            if isinstance(obj, ModuleType) and is_custom_module(obj):
                children.add(obj.__name__)  # Directly encountered a custom module
            continue  # Not a module, nor contains a reference to a module

        # Non-module with reference to module
        obj_module_name: str = obj.__module__
        if obj_module_name == module.__name__:
            continue  # We don't want to register a module as its own child

        obj_module = sys.modules[obj_module_name]
        if is_custom_module(obj_module):
            children.add(obj_module_name)

    modules = {module.__name__: ModuleData(depth, module, children)}
    for child in children:
        modules.update(walk_module_imports(sys.modules[child], depth=depth + 1))

    return modules


def merge(*sequences: t.MutableSequence[str]) -> list[str]:
    """Merges any number of sequences according to the C3 linearization algorithm.

    Parameters
    -----------
    *sequences: MutableSequence[:class:`str`]:
        Any number of mutable sequences that are to be merged into one.

    Returns
    -------
    list[:class:`str`]:
        A list created by merging `sequences`. Contains all unique items in `sequences`,
        ordered according to the C3 linearization algorithm.
    """
    res: list[str] = []
    while True:
        nonempty_seqs = [seq for seq in sequences if seq]
        if not nonempty_seqs:
            return res

        for candidate, *_ in nonempty_seqs:  # find merge candidates among sequence heads
            logger.debug("[MRO MERGE] Checking candidate %s against %s", candidate, nonempty_seqs)
            if not any(candidate in tail for _, *tail in nonempty_seqs):
                if candidate == "utils.helpers":
                    print(">>>", candidate, res, nonempty_seqs)
                break  # candidate only appears in heads, therefore is valid
        else:
            raise Exception("Inconsistent hierarchy")  # Circular imports and other shenanigans

        res.append(candidate)
        for seq in nonempty_seqs:  # remove candidate from heads
            if seq[0] == candidate:
                del seq[0]


def linearize_imports(
    modules: dict[str, ModuleData], parent_name: str, _visited: set[str] = None
) -> list[str]:
    """Compute the import precedence list according to the C3 linearization algorithm.

    Parameters
    ----------
    modules: dict[:class:`str`, :class:`ModuleData`]:
        A mapping of a module's name to a dataclass including the module object and its imports,
        as returned by `walk_module_imports`.
    parent_name: :class:`str`:
        The name of the parent module from which to start building the import hierarchy.

    Returns
    -------
    list[:class:`str`]:
        A list of imports in (reverse) hierarchical order, much like a class MRO. Reloading the
        modules in this list from back to front will ensure no imports happen out of order.
    """
    if _visited is None:
        _visited = set()
    _visited.add(parent_name)

    children = {child: modules[child] for child in modules[parent_name].children}
    return merge(  # https://en.wikipedia.org/wiki/C3_linearization
        [parent_name],
        *[
            linearize_imports(modules, child, _visited)
            for child in children
            if child not in _visited  # skip already calculated MROs
        ],
        sorted(children, key=lambda name: children[name].depth),
    )


def reload_child_modules(module: ModuleType) -> bool:
    """Atomically and recursively reload all child modules of a given module.

    For the target module, this checks all imports; then each of those imports' imports, and so on.
    The reloading will be ordered in such a way that all module dependencies are properly resolved.
    If reloading any module fails, the old state of ALL encountered modules will be returned to
    their state before reloading, such that no unexpected behaviour arises even if reloading fails.

    Parameters
    ----------
    module: :class:`ModuleType`:
        The module that is to be reloaded.

    Returns
    -------
    :class:`bool`:
        Whether or not reloading succeeded.
    """
    import_mapping = walk_module_imports(module)
    import_hierarchy = linearize_imports(import_mapping, module.__name__)

    for module_name in import_hierarchy[:0:-1]:
        spec = importlib.util.find_spec(module_name)
        if not spec:
            raise ModuleNotFoundError(module_name)
        lib = importlib.util.module_from_spec(spec)
        try:
            sys.modules[module_name] = lib
            spec.loader.exec_module(lib)  # type: ignore  # we want this to raise if it fails anyways
        except Exception:  # revert reloads
            sys.modules.update((name, data.module) for name, data in import_mapping.items())
            return False

    return True
