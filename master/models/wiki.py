from __future__ import annotations

from disnake.embeds import Embed
from disnake.utils import escape_markdown

import regex
import urllib
from collections import Counter
from functools import reduce
from operator import itemgetter
from enum import Enum, EnumMeta
from pydantic import (
    BaseModel, Field, validator, root_validator, PrivateAttr, ValidationError
)
from typing import Any, Optional, Callable
import wikitextparser as wtp

try:
    from cfuzzyset import cFuzzySet as FuzzySet
except ImportError:
    from fuzzyset import FuzzySet

BASE_WIKI_URL = "https://honkaiimpact3.fandom.com/"
BASE_IMG_URL = "https://static.wikia.nocookie.net/honkaiimpact3_gamepedia_en/images/"


class EmojiMeta(EnumMeta):  # TODO: Move
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


class Emoji(Enum, metaclass=EmojiMeta):  # TODO: Move
    """All the emoji stored in the bot, may be moved to mongodb soon:tm:"""

    def __str__(self):
        return self.value

    STAR = "<:icon_rarity_star:641631459865526302>"

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

    STIGMATA_GENERIC = "<:Stigmata_Generic:914200965136138241>"
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

    T = 0xff9279
    M = 0x9daafe
    B = 0xb2c964


class ValidCategory(Enum):
    STIGMA1 = 'Category:1-star Stigmata'
    STIGMA2 = 'Category:2-star Stigmata'
    STIGMA3 = 'Category:3-star Stigmata'
    STIGMA4 = 'Category:4-star Stigmata'
    STIGMA5 = 'Category:5-star Stigmata'

    MECH = 'Category:MECH-type Battlesuits'
    PSY = 'Category:PSY-type Battlesuits'
    BIO = 'Category:BIO-type Battlesuits'
    IMG = 'Category:IMG-type Battlesuits'
    QUA = 'Category:QUA-type Battlesuits'

    WEAPON1 = 'Category:1-Star Weapons'
    WEAPON2 = 'Category:2-Star Weapons'
    WEAPON3 = 'Category:3-Star Weapons'
    WEAPON4 = 'Category:4-Star Weapons'
    WEAPON5 = 'Category:5-Star Weapons'

    LANCE = 'Category:Lances'
    PISTOL = 'Category:Pistols'
    GAUNTLET = 'Category:Gauntlets'
    KATANA = 'Category:Katanas'
    CROSS = 'Category:Crosses'
    BOW = 'Category:Bows'
    CANNON = 'Category:Cannons'
    SCYTHE = 'Category:Scythes'
    GREATSWORD = 'Category:Greatswords'


# API response handlers

def strip_suffix_from_title(title: str) -> str:
    return regex.match(r"(.+?)(?=$| ?[\(/].*)", title)[0]


class QueryPage(BaseModel):

    title: str
    pageid_: set[str] = Field(alias="pageid")
    categories: set[ValidCategory] = Field(alias="categories")
    aliases: set[str] = Field(alias="redirects", default_factory=set)

    _fuzzy: FuzzySet = PrivateAttr(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fuzzy = FuzzySet([self.title, *self.aliases])

    @validator("title", pre=True, allow_reuse=True)
    def strip_suffixes(cls, title: str):
        return strip_suffix_from_title(title)

    @validator("pageid_", pre=True, allow_reuse=True)
    def ensure_pageid_set(cls, pageid_: Any):
        if isinstance(pageid_, set):
            return pageid_
        elif isinstance(pageid_, (str, int)):
            return {pageid_}
        else:
            return set(pageid_)

    @validator("categories", pre=True, allow_reuse=True)
    def extract_category(cls, categories: dict[str, str]):
        return {category["title"] for category in categories}

    @validator("aliases", pre=True, allow_reuse=True)
    def extract_redirect(cls, redirects: dict[str], values):
        title = values["title"]
        return [
            redirect["title"]
            for redirect in redirects
            if redirect["title"] not in title
        ]

    @property
    def pageid(self) -> str:
        return "|".join(self.pageid_)

    def update(self, other: QueryPage) -> None:
        if self.title != other.title:
            raise KeyError("Cannot merge two pages with different titles.")
        self.pageid_.update(other.pageid_)
        self.categories.update(other.categories)
        self.aliases.update(other.aliases)
        for alias in other.aliases:
            self._fuzzy.add(alias)


class QueryResponse(BaseModel):

    pages: dict[str, QueryPage] = Field(alias="query")

    @validator("pages", pre=True, allow_reuse=True)
    def unpack_query(cls, query: dict[str, dict[str, dict]]):
        pages: dict[str, QueryPage] = {}
        for page in query["pages"].values():
            try:
                qp = QueryPage(**page)
                if pages.setdefault(qp.title, qp) is not qp:
                    pages[qp.title].update(qp)
            except ValidationError:
                pass

        return pages

    def __len__(self) -> int:
        return len(self.pages)

    def get(self, k: str) -> QueryPage | None:
        k = k.lower()
        for page_name, page in self.pages.items():
            if k == page_name.lower() or any(k == alias.lower() for alias in page.aliases):
                return page

    def update(self, other: QueryResponse | QueryPage) -> None:
        if isinstance(other, QueryPage):
            page = self.pages[other.title]
            if not page:
                self.pages[other.title] = other
            else:
                page.update(other)

        elif isinstance(other, QueryResponse):
            for other_name, other_page in other.pages.items():
                page = self.pages.get(other_name)
                if page is None:
                    self.pages[other_name] = other_page
                else:
                    page.update(other_page)

    def fuzzy(self, query: str, n: int = 20):
        matches = []
        for name, page in self.pages.items():

            match = page._fuzzy.get(query)
            if match:
                best_score, best_name = max(match)
                val = name if best_name == name else f"{name} ({best_name})"

                alias_pair = (best_score, name, val)
                matches.append(alias_pair)

        return {
            match_descriptor: page_name
            for _, page_name, match_descriptor in
            sorted(matches)[:-n:-1]
        }


class WikiText(wtp._wikitext.WikiText):
    """Custom extension to wikitextparser's WikiText class such that it
    supports pydantic model validation.
    """

    @classmethod
    def __get_validators__(cls):
        yield cls._validate

    @classmethod
    def _validate(cls, value):
        if isinstance(value, wtp._wikitext.WikiText):
            return value
        elif isinstance(value, str):
            return wtp.parse(value)
        raise TypeError("WikiText input must be either str or WikiText.")


class Wikilink:
    """Class that represents a simple hyperlink to the wiki."""
    emoji: Emoji

    def __init__(self, name):
        self.name = name
        self.link = f"{BASE_WIKI_URL}{urlify(name)}"

    def __eq__(self, other: Wikilink):
        if not isinstance(other, Wikilink):
            raise TypeError("equality for WikiLinks is only supported for other WikiLinks.")

        return self.name == other.name

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


class ContentPage(BaseModel):
    """Class that represents the content of any page on the wiki.

    Page data is requested as wikitext through the api, parsed using
    wikitextparser, and then disassembled into a dict `data`.
    """

    pageid: int
    title: str
    wikitext: WikiText
    data: Optional[dict[str, str]]

    @root_validator(pre=True, allow_reuse=True)
    def extract_wikitext(cls, values):
        values["wikitext"] = values["revisions"][0]["slots"]["main"]["*"]
        return values

    @validator("data", always=True, allow_reuse=True)
    def wikitext_to_dict(cls, _, values):
        wikitext: WikiText = values["wikitext"]
        return {
            argument.name.strip(): argument.value.strip()
            for template in wikitext.templates
            for argument in template.arguments
            if not template.ancestors()  # Avoid nested arguments
        }


class ContentResponseModel(BaseModel):
    """Class that represents the entire response of an API call.

    This class is made in such a way that, if needed, multiple class
    instances can be losslessly combined. This is mainly used in
    situations where the request is too large and the wiki responds
    with `continue` parameters.
    """

    pages: list[ContentPage]

    @root_validator(pre=True, allow_reuse=True)
    def unpack_pages(cls, values: dict[str, dict[str]]):
        return {"pages": [
            ContentPage(**page)
            for page in values["query"]["pages"].values()
        ]}

    def update(self, other: ContentResponseModel) -> None:
        self.pages.append(other.pages)

    def get(self, **kwargs: str) -> ContentPage:
        for page in self.pages:
            if all(getattr(page, k, page.data.get(k)) == v for k, v in kwargs.items()):
                return page

    def get_all(self, **kwargs: str) -> list[ContentPage]:
        return [
            page
            for page in self.pages
            if all(getattr(page, k, page.data.get(k)) == v for k, v in kwargs.items())
        ]

    def find(self, predicate: Callable[[ContentPage], bool]) -> ContentPage:
        for page in self.pages:
            if predicate(page):
                return page

    def find_all(self, predicate: Callable[[ContentPage], bool]) -> list[ContentPage]:
        return [page for page in self.pages if predicate(page)]

    def highest_rarity_by_name(self, name: str) -> ContentPage:

        def predicate(page: ContentPage) -> int:
            title = page.data.get("name")
            if not title:
                return 0
            name_match = strip_suffix_from_title(title).lower() == name.lower()
            rarity = page.data.get("rarity", 0)
            return int(name_match and rarity)

        page = max(self.pages, key=predicate)
        if not predicate(page):
            raise KeyError(f"No page with name '{name}'.")
        return page


# Generic

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
        "br": "\n",
        "increase": "**{0}**",
        "color-blue": "**{0}**"
    }[result["t"]]
    return todo.format(result["m"])


def eliminate_tags(field: str):
    return regex.sub(
        r"(?P<t>''')(?P<m>.*?)'''"                                  # '''|x|''' -> **|x|**
        r"|<(?P<t>br).*?>(?P<m>\n? ?)"                              # <br> or <br>\n -> \n
        r"|<span class=\"(?P<t>[\w-]+)\">\s?(?P<m>.*?)\s?</span>",  # <span class=|x|>|y|</span>
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


class GenericWikiModel(ExtraPropagator):

    @root_validator(pre=True, allow_reuse=True)
    def parse_arguments(cls, values: dict[str, str]):
        for k, v in values.copy().items():
            field = cls.__fields__.get(k)
            if field:
                if field.type_ is Emoji:
                    try:
                        values[k] = Emoji[v]
                    except AttributeError:
                        pass
                    continue
            elif k not in cls.__annotations__:
                continue

            if isinstance(v, str):
                values[k] = cls._fix_string(v)

        return values

    @root_validator(allow_reuse=True)
    def post_string_parse(cls, values: dict[str: Any]):
        for k, v in values.items():
            field = cls.__fields__.get(k)
            if field.field_info.extra.get("parse_post") is True:
                values[k] = cls._fix_string(v)

        return values

    @staticmethod
    def _fix_string(s: str) -> str:
        return reduce(
            lambda x, f: f(x),
            (escape_markdown, resolve_wikilinks, eliminate_tags),
            s
        )

    def to_embed(self) -> list[Embed]:
        ...


# Battlesuits

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


class BattlesuitModel(GenericWikiModel):
    # selectable field: will appear in dropdown under message(s)

    # Information
    type: Emoji
    rank: Emoji
    battlesuit: Optional[Wikilink]
    character: Wikilink = Field(emoji=Emoji["VALKYRIE_GENERIC"])
    profile: str
    core_strengths: Optional[list[Emoji]] = Field(default_factory=list)
    augment: Optional[Wikilink] = Field(selectable=True)
    obtain: str

    # Recommendations
    formations: list[Formation] = Field(selectable=True)
    recommendations: list[Recommendation] = Field(selectable=True)

    def __init__(self, content: ContentResponseModel):
        # an API query for a battlesuit should only ever return one page
        super().__init__(**content.pages[0].data)

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

    @validator("core_strengths", pre=True, allow_reuse=True)
    def parse_core_strengths(cls, value):
        cores = regex.findall(
            "|".join(Emoji.__sortkeys__), value, regex.I)
        return [Emoji[core] for core in cores]

    def to_embed(self) -> list[Embed]:
        header_embed = Embed(
            description=self.profile + " " + "\u2800" * 42,
            color=Colours[self.type.name].value
        ).set_thumbnail(
            url=image_link(f"{(self.battlesuit or self.augment).name}_(Avatar)")
        ).set_author(
            name=f"{(self.battlesuit or self.augment).name} (link)",
            url=(self.battlesuit or self.augment).link,
            icon_url=image_link(f"Valkyrie_{self.rank.name}")
        )

        info_embed = Embed(
            color=Colours[self.type.name].value
        ).add_field(
            name="About:",
            value=(' '.join(str(p) for p in self.core_strengths)
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


# Stigmata

class StigSlot(Enum):

    Top = "T"
    Middle = "M"
    Bottom = "B"


class StigmataModel(GenericWikiModel):

    set: Wikilink = Field(alias="name")
    rarity: int
    slot: StigSlot
    effect: str = Field(slot_dependent=True, parse_post=True)
    HP: int = Field(slot_dependent=True)
    ATK: int = Field(slot_dependent=True)
    DEF: int = Field(slot_dependent=True)
    CRT: int = Field(slot_dependent=True)

    @root_validator(pre=True, allow_reuse=True)
    def unpack_stats(cls, values):
        stig_slot: str = values["slot"].upper()

        data = {}
        for field in cls.__fields__.values():
            field_name = field.alias
            slot_dependent = field.field_info.extra.get("slot_dependent")
            data[field_name] = values[stig_slot + field_name if slot_dependent else field_name]

        return data

    def to_embed(self, *, show_rarity: bool = True) -> Embed:
        desc = (f"Rarity: {self.rarity * Emoji.STAR.value}\n" if show_rarity else "") + self.effect
        stats = ",\u2003".join(
            f"**{name}**: {stat}"
            for name, stat in (
                ("HP", self.HP),
                ("ATK", self.ATK),
                ("DEF", self.DEF),
                ("CRT", self.CRT)
            )
            if stat
        )

        return Embed(
            description=f"{desc}\n\n{stats}",
            colour=Colours[self.slot.value].value
        ).set_author(
            name=f"{self.set.name} ({self.slot.value})",
            url=self.set.link,
            icon_url=image_link(f"Stigmata_{self.slot.name}")
        ).set_thumbnail(
            url=image_link(f"{self.set.name}_({self.slot.value})_(Icon)")
        )


class SetBonusModel(GenericWikiModel):

    name: str
    effect: str


class StigmataSetModel(GenericWikiModel):

    T: Optional[StigmataModel]
    M: Optional[StigmataModel]
    B: Optional[StigmataModel]
    rarity: Optional[int]
    set: Optional[Wikilink]
    set_2: Optional[SetBonusModel]
    set_3: Optional[SetBonusModel]

    def __init__(self, stigs: dict[str, str], content: ContentResponseModel):
        super().__init__(stigs=stigs, content=content)

    @root_validator(pre=True, allow_reuse=True)
    def unpack_stigmata(cls, values):
        stigs: dict[str, str] = values["stigs"]
        response_obj: ContentResponseModel = values["content"]

        # Unpack and parse stig data
        for slot, stig in stigs.items():
            stig_data = response_obj.highest_rarity_by_name(stig).data
            values[slot.upper()] = StigmataModel(slot=slot, **stig_data)

        # Determine if any set bonuses apply, if so, propagate them from stigmata data
        for stig, count in Counter(stigs.values()).items():
            count = int(count)
            if count < 2:
                continue
            stig_data = response_obj.highest_rarity_by_name(stig).data
            values["rarity"] = stig_data["rarity"]
            values["set"] = stig_data["name"]
            values["set_2"] = {"name": stig_data["2set"], "effect": stig_data["2effect"]}
            if count == 3:
                values["set_3"] = {"name": stig_data["3set"], "effect": stig_data["3effect"]}
            break

        return values

    def get_set_bonus(self, *, show_rarity=True) -> Optional[Embed]:
        if not self.set:
            return None

        set_embed = Embed(
            description=f"Rarity: {self.rarity * Emoji.STAR.value}" if show_rarity else Embed.Empty
        ).set_author(
            name=f"{self.set.name} set:",
            url=self.set.link,
            icon_url=image_link("Item Type (Stigmata)")
        ).add_field(
            name=f"{self.set_2.name} (2-set):",
            value=self.set_2.effect
        )

        if self.set_3:
            set_embed.add_field(
                name=f"{self.set_3.name} (3-set):",
                value=self.set_3.effect
            )

        return set_embed

    def to_embed(self) -> list[Embed]:
        show_rarity = self.T.set == self.M.set == self.B.set

        set_embed = self.get_set_bonus(show_rarity=show_rarity)
        embeds = [
            stig.to_embed(show_rarity=not show_rarity)
            for stig in (self.T, self.M, self.B)
            if stig
        ]
        if set_embed:
            embeds.append(set_embed)

        return embeds
