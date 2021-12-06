from typing import Any, Dict, List, Optional
from odmantic import Field, Model

__all__ = ("ViewModel", "GuildModel")


class ViewModel(Model):
    class Config:
        collection = "views"

    id: int = Field(primary_field=True)
    type: str
    guild_id: Optional[int]
    channel_id: Optional[int]
    data: Dict[str, Any]


class GuildModel(Model):
    class Config:
        collection = "guilds"

    id: int = Field(primary_field=True)
    prefix: Optional[List[str]]
