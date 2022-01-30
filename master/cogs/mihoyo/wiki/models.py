# TODO: add new weapon models when the wiki updates them
# TODO: deprecate models/wiki.py when the wiki finishes updating

from __future__ import annotations

import re
from enum import Enum, IntEnum
from functools import cached_property, partial
import typing as t
import wikitextparser as wtp
from pydantic import BaseModel, Field, ValidationError, root_validator, validator

BASE_WIKI_URL = "https://honkaiimpact3.fandom.com/"
BASE_IMG_URL = "https://static.wikia.nocookie.net/honkaiimpact3_gamepedia_en/images/"
BASE_API_URL = "https://honkaiimpact3.fandom.com/api.php?"


# ENUMS


class Emoji(str, Enum):
    """All the emoji stored in the bot, may be moved to mongodb soon:tm:"""

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

    PASSIVE = "<:Passive:914596917961445416>"
    ACTIVE = "<:Active:914594001565413378>"

    @classmethod
    def __get_validators__(cls):
        yield lambda value: cls[value.upper().replace(" ", "_")]


class Colours(IntEnum):
    BIO = 0xFFB833
    PSY = 0xFE46CF
    MECH = 0x2FE0FF
    QUA = 0x9B78FE
    IMG = 0xF1D799

    TOP = 0xFF9279
    MIDDLE = 0x9DAAFE
    BOTTOM = 0xB2C964


class ValidCategory(str, Enum):
    STIGMA1 = "Category:1-star Stigmata"
    STIGMA2 = "Category:2-star Stigmata"
    STIGMA3 = "Category:3-star Stigmata"
    STIGMA4 = "Category:4-star Stigmata"
    STIGMA5 = "Category:5-star Stigmata"

    MECH = "Category:MECH-type Battlesuits"
    PSY = "Category:PSY-type Battlesuits"
    BIO = "Category:BIO-type Battlesuits"
    IMG = "Category:IMG-type Battlesuits"
    QUA = "Category:QUA-type Battlesuits"

    WEAPON1 = "Category:1-Star Weapons"
    WEAPON2 = "Category:2-Star Weapons"
    WEAPON3 = "Category:3-Star Weapons"
    WEAPON4 = "Category:4-Star Weapons"
    WEAPON5 = "Category:5-Star Weapons"

    LANCE = "Category:Lances"
    PISTOL = "Category:Pistols"
    GAUNTLET = "Category:Gauntlets"
    KATANA = "Category:Katanas"
    CROSS = "Category:Crosses"
    BOW = "Category:Bows"
    CANNON = "Category:Cannons"
    SCYTHE = "Category:Scythes"
    GREATSWORD = "Category:Greatswords"


class StigmaSlot(str, Enum):
    TOP = "T"
    MIDDLE = "M"
    BOTTOM = "B"


# WIKI RESPONSE PARSERS


def wikitext_to_dict(wikitext: WikiText) -> dict[str, str]:
    return {
        argument.name.strip(): argument.value.strip()
        for template in wikitext.templates
        for argument in template.arguments
        if not template.ancestors()  # Avoid nested arguments
    }


SelfT = t.TypeVar("SelfT")


class ResponseModel(t.Protocol):
    def update(self: SelfT, other: SelfT) -> None:
        ...


ResponseModelT = t.TypeVar("ResponseModelT", bound=ResponseModel)


class QueryPage(BaseModel):

    title: str
    pageid_: set[str] = Field(alias="pageid")
    categories: set[ValidCategory] = Field(alias="categories")
    aliases: set[str] = Field(alias="redirects", default_factory=set)

    @validator("title", pre=True, allow_reuse=True)
    def _strip_suffixes(cls, title: str):
        match = re.match(r"(.+?)(?=$| ?[\(/].*)", title)
        return match[0] if match else title

    @validator("pageid_", pre=True, allow_reuse=True)
    def _ensure_pageid_set(cls, pageid_: t.Any):
        if isinstance(pageid_, set):
            return pageid_
        elif isinstance(pageid_, (str, int)):
            return {pageid_}
        else:
            return set(pageid_)

    @validator("categories", pre=True, allow_reuse=True)
    def _extract_category(cls, categories: list[dict[str, str]]):
        return {category["title"] for category in categories}

    @validator("aliases", pre=True, allow_reuse=True)
    def _extract_redirect(cls, redirects: list[dict[str, str]], values: dict[str, t.Any]):
        pat = r"[\s:\-']|\([TMB\d]\)|\(stigmata\)|/\d-star"
        subber: partial[str] = partial(re.sub, pat, "", flags=re.I)
        simplified_title = subber(values["title"]).lower()

        def predicate(alias: str) -> bool:
            return simplified_title == subber(alias).lower()

        return [title for redirect in redirects if not predicate(title := redirect["title"])]

    @property
    def pageid(self) -> str:
        return "|".join(self.pageid_)

    @property
    def all_names(self) -> list[str]:
        return [self.title, *self.aliases]

    def update(self, other: QueryPage) -> None:
        if self.title != other.title:
            raise KeyError("Cannot merge two pages with different titles.")
        self.pageid_.update(other.pageid_)
        self.categories.update(other.categories)
        self.aliases.update(other.aliases)


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
        return None

    def update(self, other: QueryResponse | QueryPage) -> None:
        if isinstance(other, QueryPage):
            page = self.pages.get(other.title)
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


class ContentPage(BaseModel):
    """Class that represents the content of any page on the wiki.

    Page data is requested as wikitext through the api, parsed using
    wikitextparser, and then disassembled into a dict `data`.
    """

    pageid: int
    title: str
    wikitext: WikiText
    data: dict[str, str] = Field(default_factory=dict)

    @root_validator(pre=True, allow_reuse=True)
    def _extract_wikitext(cls, values):
        values["wikitext"] = values["revisions"][0]["slots"]["main"]["*"]
        return values

    @validator("data", always=True, allow_reuse=True)
    def _wikitext_to_dict(cls, _, values):
        wikitext: WikiText = values["wikitext"]
        return wikitext_to_dict(wikitext)


class ContentResponse(BaseModel):
    """Class that represents the entire response of an API call.

    This class is made in such a way that, if needed, multiple class
    instances can be losslessly combined. This is mainly relevant in
    situations where the request is too large and the wiki responds
    with `continue` parameters.
    """

    pages: list[ContentPage] = Field(default_factory=list)

    @root_validator(pre=True, allow_reuse=True)
    def _unpack_pages(cls, values: dict[str, dict[str, t.Any]]):
        return {"pages": [ContentPage(**page) for page in values["query"]["pages"].values()]}

    def update(self, other: ContentResponse) -> None:
        self.pages.extend(other.pages)

    def get(self, **kwargs: str) -> t.Optional[ContentPage]:
        for page in self.pages:
            if all(getattr(page, k, page.data.get(k)) == v for k, v in kwargs.items()):
                return page
        return None

    def get_all(self, **kwargs: str) -> list[ContentPage]:
        return [
            page
            for page in self.pages
            if all(getattr(page, k, page.data.get(k)) == v for k, v in kwargs.items())
        ]

    def find(self, predicate: t.Callable[[ContentPage], bool]) -> t.Optional[ContentPage]:
        for page in self.pages:
            if predicate(page):
                return page
        return None

    def find_all(self, predicate: t.Callable[[ContentPage], bool]) -> list[ContentPage]:
        return [page for page in self.pages if predicate(page)]


# CONTENT MODELS


class WikiBase(BaseModel):
    class Config:
        allow_mutation = False
        frozen = True
        keep_untouched = (cached_property,)


# - BATTLESUITS


class Equipment(BaseModel):
    """Represents a piece of equipment, equipped on a Battlesuit."""

    name: str
    rarity: int


class Recommendation(BaseModel):
    """Represents an equipment recommendation for a battlesuit, including a
    weapon, and T, M, and B stigmata; not necessarily of the same set.
    """

    type: str
    weapon: Equipment
    T: Equipment
    M: Equipment
    B: Equipment
    offensive_ability: str
    functionality: str
    compatibility: str


class Battlesuit(BaseModel):  # TODO: Add skills when finished on wiki
    """Represents a battlesuit with all data on the wiki."""

    type: Emoji
    rank: Emoji
    name: str = Field(alias="battlesuit")
    character: str
    profile: str = Field("", alias="profile")  # Undefined for augments fsr
    core_strengths: list[Emoji]
    augment: t.Optional[str]
    recommendations: list[Recommendation]

    @validator("core_strengths", pre=True, allow_reuse=True)
    def _parse_core_strengths(cls, value: str):
        return value.split(", ") if value else []

    @root_validator(pre=True, allow_reuse=True)
    def _pack_recommendations(cls, values: dict[str, t.Any]):
        values["recommendations"] = recommendations = []
        for category, pretty_name in (
            ("BBSrec", "recommended"),
            ("BBSau", "auxiliary"),
            ("BBSun", "universal"),
            ("BBStr", "transitional"),
        ):
            cat_data = values.get(category)
            if not cat_data:
                continue
            wikitext = wtp.parse(cat_data)
            templates = iter(wikitext.templates)
            results = {
                "weapon": dict(
                    zip(["name", "rarity"], [arg.value for arg in next(templates).arguments])
                )
            }

            for template in templates:
                slot = template.get_arg("slot")
                results[slot.value.strip()] = dict(
                    zip(["name", "_", "rarity"], [arg.value for arg in template.arguments])
                )

            for score_type in ("offensive_ability", "functionality", "compatibility"):
                results[score_type] = values[f"{category}_{score_type}"]

            recommendations.append(Recommendation(**results, type=pretty_name))
        return values


# - STIGMATA


class SetBonus(BaseModel, frozen=True, allow_mutation=False):
    """Represents a set bonus for a stigmata set."""

    name: str
    effect: str
    number: int


SetBonusT = t.Union[
    tuple[SetBonus, SetBonus],  # 3-set
    tuple[SetBonus],  # 2-set
    tuple[()],  # no set bonus
]


class Stigma(WikiBase):
    """Represents a singular Stigma. Also contains information about its set."""

    class Config:
        allow_mutation = False
        frozen = True

    name: str = Field(alias="slot_name")
    hp: int = Field(alias="HP")
    attack: int = Field(alias="ATK")
    defense: int = Field(alias="DEF")
    crit: int = Field(alias="CRT")
    effect_name: str = Field(alias="effectName")
    effect: str

    # Set info
    slot: StigmaSlot
    set_name: str = Field(alias="name")
    set_name_2p: t.Optional[str] = Field(alias="setEffect2pName")
    set_effect_2p: t.Optional[str] = Field(alias="setEffect2p")
    set_name_3p: t.Optional[str] = Field(alias="setEffect3pName")
    set_effect_3p: t.Optional[str] = Field(alias="setEffect3p")
    rarity: int
    obtain: dict[str, bool]

    @root_validator(pre=True, allow_reuse=True)
    def _pack_obtain(cls, values: dict[str, t.Any]):
        base = "obtain"  # all fields that contain source data start with 'obtain'
        values[base] = {k.removeprefix(base): v for k, v in values.items() if base in k}
        return values

    @root_validator(pre=True, allow_reuse=True)
    def _unpack_stig_data(cls, values: dict[str, t.Any]):
        slot = values["slot"]  # used to remove slot prefixes from stat/effect fields
        values = {k.removeprefix(f"slot{slot}_"): v for k, v in values.items()}
        values["slot_name"] = (
            values.get(f"set{slot}") or values.get(f"slot{slot}") or values["name"]
        )
        return values

    @property
    def set_2p(self) -> t.Optional[SetBonus]:
        """The Stigma's set's 2-set effect. `None` if the set consists of a singular Stigma."""
        if self.set_name_2p and self.set_effect_2p:
            return SetBonus(name=self.set_name_2p, effect=self.set_effect_2p, number=3)
        return None

    @property
    def set_3p(self) -> t.Optional[SetBonus]:
        """The Stigma's set's 3-set effect. `None` if the set is not a 3-piece set."""
        if self.set_name_3p and self.set_effect_3p:
            return SetBonus(name=self.set_name_3p, effect=self.set_effect_3p, number=3)
        return None

    @property
    def set_bonuses(self) -> SetBonusT:
        """The Stigma's set's set bonuses. Returns a tuple with zero, one or two `SetBonus`es,
        according to how many pieces are in the set.
        """
        return tuple(bonus for bonus in (self.set_2p, self.set_3p) if bonus)  # type: ignore


StigmataSetT = t.Union[
    tuple[Stigma, Stigma, Stigma],
    tuple[Stigma, Stigma],
    tuple[Stigma],
]


class StigmataSet(WikiBase):
    """Represents a set of `Stigma`ta. This has full support for mixed sets.

    Any set operations take into account the number of stigmata of a given set
    that are actually present in the `StigmataSet`.
    """

    stigmata: StigmataSetT  # one, two or three stigmata

    @root_validator(pre=True, allow_reuse=True)
    def _validate_stigs(cls, values: dict[str, t.Any]):
        stigmata: t.Optional[t.Sequence[Stigma]] = values.get("stigmata")
        if stigmata:
            if not all(isinstance(stig, Stigma) for stig in stigmata):
                raise TypeError("All stigmata must be of type `Stigmata`")
        else:
            # Assume we're parsing a set from raw data
            values["stigmata"] = stigmata = tuple(
                Stigma(slot=slot, **values) for slot in StigmaSlot if f"slot{slot}" in values
            )

        # validate that we have at most one of each slot
        if len({stig.slot for stig in stigmata}) != len(stigmata):
            raise ValueError("A set cannot have multiple stigmata share a slot")
        return values

    # TODO: Maybe delete T, M, B; as they aren't used internally?
    #       They also conflict with 6-piece sets but idk what to do about those yet.
    @property
    def T(self) -> t.Optional[Stigma]:
        """The `Stigma` in the Top slot. `None` if there is none."""
        for stig in self.stigmata:
            if stig.slot is StigmaSlot.TOP:
                return stig
        return None

    @property
    def M(self) -> t.Optional[Stigma]:
        """The `Stigma` in the Middle slot. `None` if there is none."""
        for stig in self.stigmata:
            if stig.slot is StigmaSlot.MIDDLE:
                return stig
        return None

    @property
    def B(self) -> t.Optional[Stigma]:
        """The `Stigma` in the Bottom slot. `None` if there is none."""
        for stig in self.stigmata:
            if stig.slot is StigmaSlot.BOTTOM:
                return stig
        return None

    @cached_property
    def main_set_with_bonuses(
        self,
    ) -> t.Union[tuple[StigmataSetT, SetBonusT], tuple[tuple[()], tuple[()]]]:
        """The main set that contributes to the `StigmataSet` set-bonus, and the set-bonuses
        provided by the set.

        - In case of a full set, this returns the full set with 3-piece and 2-piece bonuses;
        - In case of a 2:1 mixed set, this returns the 2-set with 2-piece set bonus;
        - In case of a 1:1:1 mixed set, this returns two empty tuples, as there is no set bonus;
        - In case of a 2-piece non-mixed set, this returns the set with its 2-piece set bonus;
        - In all other cases, this returns two empty tuples.
        """
        counts: dict[SetBonusT, list[Stigma]] = {}
        for stig in self.stigmata:
            set_bonuses = stig.set_bonuses
            if not set_bonuses:
                continue
            counts.setdefault(set_bonuses, []).append(stig)

        if not counts or len(counts) == len(self.stigmata):
            return ((), ())

        bonuses, stigs = max(counts.items(), key=lambda pair: len(pair[1]))
        return tuple(stigs), bonuses[: len(stigs) - 1]  # type: ignore

    @property
    def set_bonuses(self) -> t.Optional[SetBonusT]:
        """The set bonuses triggered by the `Stigma`ta in this `StigmaSet`,
        `None` if no set bonuses are active.
        """
        _, set_bonuses = self.main_set_with_bonuses
        return set_bonuses or None

    @property
    def main_set(self) -> t.Optional[StigmataSetT]:
        """The `Stigma`ta in this set that contribute to this `StigmaSet`'s set bonus,
        `None` if no set bonuses are active.
        """
        stigmata, _ = self.main_set_with_bonuses
        return stigmata or None

    @property
    def name(self) -> t.Optional[str]:
        """The name of the set that contribute to this `StigmaSet`'s set bonus,
        `None` if no set bonuses are active.
        """
        return stigset[0].name if (stigset := self.main_set) else None
