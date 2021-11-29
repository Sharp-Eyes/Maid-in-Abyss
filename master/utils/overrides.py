from __future__ import annotations

from typing import TYPE_CHECKING
from inspect import isclass
from pydantic import BaseModel, root_validator

if TYPE_CHECKING:
    from pydantic.typing import MappingIntStrAny, AbstractSetIntStr, DictStrAny


class PropagatingModel(BaseModel):
    """Pydantic model that propagates:
    1. ClassVars defined in the parent model to all child-models that
        also have the ClassVar annotated.
    2. Fields defined in the parent model with Field(..., propagate=True)
        to all child models that have a field with the same name and type.
    """

    @root_validator(pre=True, allow_reuse=True)
    def propagate(cls, values):
        for field in cls.__fields__.values():
            field_type = field.type_
            if not (isclass(field_type) and issubclass(field_type, BaseModel)):
                continue

            # Propagate ClassVars
            for class_var in cls.__class_vars__:
                # Make sure the ClassVars are actually defined
                if class_var not in cls.__dict__:
                    raise AttributeError(
                        f"ClassVar {class_var} has not yet been defined, thus cannot be propagated."
                    )
                if class_var in field_type.__class_vars__:
                    # If the ClassVar is also annotated in a child model, propagate it
                    setattr(field_type, class_var, getattr(cls, class_var))

            # Propagate Fields with propagate=True
            for sub_field in field_type.__fields__.values():
                prop_field = cls.__fields__.get(sub_field.name)
                if not prop_field:
                    # Check for matching field names between current and child model
                    continue
                if prop_field.type_ is not sub_field.type_:
                    # Make sure types match
                    continue
                # Propagate field value to child model
                values[field.alias][prop_field.alias] = values[prop_field.alias]

        return values

    def dict(
        self,
        *,
        include: AbstractSetIntStr | MappingIntStrAny = None,
        exclude: AbstractSetIntStr | MappingIntStrAny = None,
        by_alias: bool = False,
        skip_defaults: bool = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> DictStrAny:
        hidden_fields = {
            attribute_name
            for attribute_name, model_field in self.__fields__.items()
            if model_field.field_info.extra.get("hidden") is True
        }
        if exclude is not None:
            exclude.update(hidden_fields)
        elif hidden_fields:
            exclude = hidden_fields

        return super().dict(
            include=include, exclude=exclude, by_alias=by_alias, skip_defaults=skip_defaults,
            exclude_unset=exclude_unset, exclude_defaults=exclude_defaults,
            exclude_none=exclude_none
        )
