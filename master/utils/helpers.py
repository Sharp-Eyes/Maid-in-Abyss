from collections.abc import Mapping as _Mapping



def deep_update(D, U):
    """Update nested dict D with keys and values from nested dict U.
    Much like Python's built-in :method:`update`, this is done in-place.
    However, unlike :method:`update`, the result is also returned."""

    if isinstance(D, _Mapping) and isinstance(U, _Mapping):
        for k,v in U.items():
            D[k] = deep_update(D.get(k), v)
        return D
    return U

