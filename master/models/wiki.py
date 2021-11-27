from __future__ import annotations
from disnake.embeds import Embed

import regex
import urllib
from functools import reduce
from operator import getitem, itemgetter
from enum import Enum, EnumMeta
from pydantic import BaseModel, Field, validator, root_validator, PrivateAttr
from pydantic.fields import ModelField
from typing import Any, Optional

from utils.overrides import FuncEmbed, EmptyEmbed


BASE_WIKI_URL = "https://honkaiimpact3.fandom.com/"
BASE_IMG_URL = "https://static.wikia.nocookie.net/honkaiimpact3_gamepedia_en/images/"


class EmojiMeta(EnumMeta):
    """Makes it so the Emoji enum is indexed by name when called instead of
    by value, as is the case with default Enums. There's probably a better
    way of doing this.
    """

    def __getitem__(self, name: str) -> Any:
        name = name.replace(" ", "_").upper()
        return super().__getattribute__(name)

    def __init__(self, name, bases, namespace) -> None:
        super().__init__(name, bases, namespace)
        self.__sortkeys__ = sorted(
            (e.name.replace("_", " ") for e in self),
            key=len,
            reverse=True
        )


class Emoji(Enum, metaclass=EmojiMeta):
    """All the emoji stored in the bot, may be moved to mongodb soon:tm:"""

    def __str__(self):
        return self.value

    BIO = "<:Type_BIO:643900338864259072>"
    PSY = "<:Type_PSY:643900338683772939>"
    MECH = "<:Type_MECH:643900338868453417>"
    QUA = "<:Type_QUA:643900338943819777>"
    IMG = "<:Type_IMG:909205004269813773>"

    B = "<:Rank_B:643906316716474379>"
    A = "<:Rank_A:643906316317884447>"
    S = "<:Rank_S:643906316422742047>"
    SS = "<:Rank_SS:643906317362266113>"
    SSS = "<:Rank_SSS:643906317781696552>"

    STIG_TOP = "<:Stig_T:640937795761733652>"
    STIG_MID = "<:Stig_M:640937795665395734>"
    STIG_BOT = "<:Stig_B:640937795103227909>"
    EQUIPMENT_GENERIC = "<:Equipment_Generic:642086143571132420>"
    VALKYRIE_GENERIC = "<:Valkyrie_Generic:909813519103430697>"

    ICE_DMG = "<:Ice_DMG:911355738008453151>"
    FIRE_DMG = "<:Fire_DMG:911355738042007572>"
    LIGHTNING_DMG = "<:Lightning_DMG:911355737832304650>"
    PHYSICAL = "<:Physical:911355737819725875>"

    BURST = "<:Burst:911356972044009532>"
    TIME_MASTERY = "<:Time_Mastery:911355737878462544>"
    GATHER = "<:Gather:911355737819725844>"
    HEAL = "<:Heal:911355737907822592>"
    FAST_ATK = "<:Fast_ATK:911355737756807281>"
    HEAVY_ATK = "<:Heavy_ATK:911355737861681183>"

    FREEZE = "<:Freeze:911355838394929236>"
    IGNITE = "<:Ignite:911355738083954739>"
    BLEED = "<:Bleed:911355737886847026>"
    WEAKEN = "<:Weaken:911355738100748338>"
    IMPAIR = "<:Impair:911355737903603792>"
    STUN = "<:Stun:911355838491402250>"
    PARALYZE = "<:Paralyze:911357753115672576>"


class Colours(Enum):
    BIO = 0xffb833
    PSY = 0xfe46cf
    MECH = 0x2fe0ff
    QUA = 0x9b78fe
    IMG = 0xf1d799


# Display

class Wikilink:
    emoji: Emoji

    def __init__(self, name):
        self.name = name
        self.link = f"{BASE_WIKI_URL}{urlify(name)}"

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise TypeError("string required")
        return cls(v)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    def __repr__(self):
        return f"Wikilink({self.name})"

    def __str__(self):
        return self.format()

    def format(self):
        if hasattr(self, "emoji"):
            return f"{self.emoji} {wiki_link(self.name)}"
        else:
            return wiki_link(self.name)


# Generic

def maybe_format(value):
    if hasattr(value, "format"):
        return value.format()
    if not (isinstance(value, bool) or value is ...):
        return str(value)
    return value


def urlify(s: str):
    """Convert a string value to a value more likely to be recognized by
    the HI3 wiki. Meant to be used to convert names to urls
    """
    return urllib.parse.quote(s.replace(" ", "_"))


def image_link(name: str):
    """Tries to get an image url by name from the HI3 wiki."""
    return f"{BASE_WIKI_URL}/Special:Redirect/file/{urlify(name)}.png"


def wiki_link(name: str):
    return f"[{name}]({BASE_WIKI_URL}{urlify(name)})"


def resolve_wikilinks(field: str):
    return regex.sub(
        r"(\[\[(.*?)\]\])",
        lambda m: wiki_link(m[2]),
        field
    )


def convert_tag(match) -> str:
    result = match.groupdict()
    todo = {
        "'''": "**{0}**",
        "br": "\n"
    }[result["t"]]
    return todo.format(result["m"])


def eliminate_tags(field: str):
    return regex.sub(
        r"(?P<t>''')(?P<m>.*?)'''|<(?P<t>br).*?>(?P<m>\n? ?)",
        convert_tag,
        field,
        0,
        regex.S
    )


class PrimaryAttribute(Enum):
    DMG_ICE = "Ice DMG"
    DMG_FIRE = "Fire DMG"
    DMG_LIGHTNING = "Lightning DMG"
    DMG_PHYS = "Physical"

    BURST = "Burst"
    TIMEFRAC = "Time Mastery"
    GATHER = "Gather"

    FREEZE = "Freeze"


class ExtraPropagator(BaseModel):
    """Propagates values set in Field extras to the field value, if that
    value supports the attribute. For example:
    ```
    class SupportsEmoji:
        emoji: Emoji

        def __init__(self, message):
            self.message = message

    class MyModel(ExtraPropagator):
        a: SupportsEmoji = Field(emoji="whoa")
        b: SupportsEmoji = Field(emoji="epic")

    m = MyModel(a="wow", b="amazing")
    m.a.emoji, m.b.emoji
    >>> ("whoa", "epic")
    ```
    Requires some caution such that unwanted propagations do not occur.
    """

    @root_validator(allow_reuse=True)
    def propagate_extras(cls, values):
        for k, v in values.items():
            field = cls.__fields__[k]
            if not hasattr(field.type_, "__annotations__"):
                continue
            extras = field.field_info.extra
            for extra_k, extra_v in extras.items():
                if extra_k in field.type_.__annotations__:
                    setattr(v, extra_k, extra_v)
        return values


class Recommendation(ExtraPropagator):

    stage: str
    weapon: Wikilink = Field(emoji=Emoji["EQUIPMENT_GENERIC"])
    top: Wikilink = Field(emoji=Emoji["STIG_TOP"])
    mid: Wikilink = Field(emoji=Emoji["STIG_MID"])
    bot: Wikilink = Field(emoji=Emoji["STIG_BOT"])

    def format(self):
        return {
            "inline": True,
            "name": f"{self.stage} Equipment:",
            "value": (
                f"{self.weapon}\n"
                f"{self.top}\n{self.mid}\n{self.bot}"
            )
        }


class Formation(ExtraPropagator):

    valk: Wikilink = Field(emoji=Emoji["VALKYRIE_GENERIC"])
    reason: str

    def __str__(self):
        return self.format()

    def format(self):
        return f"{self.valk}: {self.reason}"


class GenericWikiModel(ExtraPropagator):

    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)

    @root_validator(pre=True, allow_reuse=True)
    def parse_arguments(cls, values: dict[str, str]):
        for k, v in values.copy().items():
            field = cls.__fields__.get(k)
            if not field:
                continue
            if field.type_ is Emoji:
                try:
                    values[k] = Emoji[v]
                except AttributeError:
                    pass
                continue

            values[k] = reduce(
                lambda x, f: f(x),
                [resolve_wikilinks, eliminate_tags],
                v
            )

        return values

    def to_embed(self) -> list[Embed]:
        ...


# Characters

class CharacterModel(GenericWikiModel):
    # selectable field: will appear in dropdown under message(s)

    # Information
    type: Emoji
    rank: Emoji
    battlesuit: Optional[Wikilink]
    character: Wikilink = Field(emoji=Emoji["VALKYRIE_GENERIC"])
    features: str
    primary: Optional[list[Emoji]] = Field(default_factory=list)
    augment: Optional[Wikilink] = Field(selectable=True)
    obtain: str

    # Recommendations
    formations: list[Formation] = Field(selectable=True)
    recommendations: list[Recommendation] = Field(selectable=True)

    @root_validator(pre=True, allow_reuse=True)
    def parse_arguments(cls, values: dict[str, str]):

        cls.parse_recommendations(values)
        cls.parse_formations(values)
        return values

    @classmethod
    def parse_recommendations(cls, values) -> None:
        for stage in ("beginner", "economic", "advanced"):
            keys = (f"{stage}Weapon", f"{stage}Top", f"{stage}Middle", f"{stage}Bottom")
            w, t, m, b = itemgetter(*keys)(values)
            values.setdefault("recommendations", list()).append(Recommendation(
                weapon=w,
                top=t, mid=m, bot=b,
                stage=stage.title()
            ))

    @classmethod
    def parse_formations(cls, values) -> None:
        for i in (1, 2):
            keys = (f"formation{i}", f"reason{i}")
            f, r = itemgetter(*keys)(values)
            values.setdefault("formations", list()).append(Formation(
                valk=f, reason=eliminate_tags(r)
            ))

    @validator("primary", pre=True, allow_reuse=True)
    def parse_primaries(cls, value):
        primaries = regex.findall(
            "|".join(Emoji.__sortkeys__), value, regex.I)
        return [Emoji[primary] for primary in primaries]

    def to_embed(self) -> list[Embed]:
        header_embed = Embed(
            description=self.features + " " + "\u2800" * 42,
            color=Colours[self.type.name].value
        ).set_thumbnail(
            url=image_link(f"{(self.battlesuit or self.augment).name}_(Icon)")
        ).set_author(
            name=f"{(self.battlesuit or self.augment).name} (link)",
            url=(self.battlesuit or self.augment).link,
            icon_url=image_link(f"Valkyrie_{self.rank.name}")
        )

        info_embed = Embed(
            color=Colours[self.type.name].value
        ).add_field(
            name="About:",
            value=(' '.join(str(p) for p in self.primary)
                   + f"\n{self.character}\nType: {self.type}\nAugment: {self.augment}"),
            inline=True
        ).add_field(
            name="Obtain:",
            value=f"{self.obtain}",
            inline=True
        ).add_field(
            name="Formations:",
            value="\n".join(f.format() for f in self.formations),
            inline=False
        )
        reduce(
            lambda e, f: Embed.add_field(e, **f.format()),
            self.recommendations,
            info_embed
        )

        return [header_embed, info_embed]
