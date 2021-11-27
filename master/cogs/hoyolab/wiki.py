from __future__ import annotations

import disnake
from disnake.ext import commands
from disnake import ApplicationCommandInteraction as Interaction

import aiohttp
import re
from pydantic import BaseModel, validator, ValidationError, Field, PrivateAttr
from typing import Any, Type, TypeVar, Callable
from fuzzyset import FuzzySet
from enum import Enum, EnumMeta
from itertools import product
import wikitextparser as wtp
from traceback import print_exc

from utils.bot import FullReloadCog
from utils.overrides import CustomBot
from models.wiki import CharacterModel


BASE_WIKI_URL = "https://honkaiimpact3.fandom.com/"
BASE_API_URL = "https://honkaiimpact3.fandom.com/api.php?"


ResponseModel = TypeVar("ResponseModel")


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


# Models

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
    def strip_rarity(cls, title: str):
        return re.match(r"(.+?)(?=$| ?[\(/].*)", title)[0]

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


# Cog

class WikiCog(FullReloadCog):

    def __init__(self, bot: CustomBot):
        self.bot = bot
        bot.get_guild

    async def cog_load(self):
        await self.bot.wait_until_ready()
        print("loading")
        await self.populate_wiki_cache()

        print("dunzo'd")

    async def populate_wiki_cache(self) -> None:
        params = {
            "action": "query",
            "format": "json",
            "prop": "categories|redirects",
            "generator": "categorymembers",
            "cllimit": "max",
            "clcategories": "|".join(cat.value for cat in ValidCategory),
            "rdprop": "title",
            "rdlimit": "max",
            "gcmtitle": "Category:Stigmata",
            "gcmlimit": "max",
        }

        for i, cat in enumerate(["Category:Stigmata", "Category:Battlesuits", "Category:Weapons"]):
            _params = params.copy()
            _params.update(gcmtitle=cat)
            if not i:
                result = await self.API_request(_params, QueryResponse)
            else:
                result.update(await self.API_request(_params, QueryResponse))

        self.bot.wiki_cache = result

    async def API_request(
        self,
        params: dict[str, str],
        response_model: Type[ResponseModel] | Callable[..., ResponseModel]
    ) -> ResponseModel:
        async with self.bot.session.get(BASE_API_URL, params=params) as resp:
            data = await resp.json()
        result = response_model(**data)

        while "continue" in data:
            _params = params.copy()
            _params.update(data["continue"])

            async with self.bot.session.get(BASE_API_URL, params=_params) as resp:
                data = await resp.json()
            result.update(response_model(**data))

        return result

    @commands.command(name="reloadwikicache")
    async def _reloadwikicache(self, ctx):
        await self.populate_wiki_cache()
        print("reloaded wiki cache")

    @commands.slash_command(name="wiki", guild_ids=[701039771157397526, 511630315039490076])
    async def wiki(self, inter: Interaction, query: str):
        await inter.response.defer()
        page: QueryPage = self.bot.wiki_cache.pages[query]

        page_params = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "pageids": page.pageid,
            "rvprop": "content",
            "rvslots": "main"
        }
        data = await self.API_request(page_params, dict)

        if page.categories.intersection({
            ValidCategory.PSY, ValidCategory.BIO, ValidCategory.MECH,
            ValidCategory.QUA, ValidCategory.IMG
        }):
            wikitext = wtp.parse(
                data["query"]["pages"][str(page.pageid)]["revisions"][0]["slots"]["main"]["*"]
            )
            longest_template = sorted(wikitext.templates, key=len)[-1]
            parsed_kwargs = dict(
                map(lambda x: (x.name.strip(), x.value.strip()), longest_template.arguments)
            )
            try:
                char = CharacterModel(**parsed_kwargs)
            except Exception:
                await inter.edit_original_message(
                    content="Unfortunately, something went wrong trying to parse the data "
                            "from the wiki. Please contact the developer."
                )
                print_exc()
                return

            await inter.edit_original_message(embeds=char.to_embed())
            return

        await inter.edit_original_message(
            content="It appears this type of query hasn't been implemented yet. "
                    "Please check back soon:tm:. For now, have this "
                    f"[link]({BASE_WIKI_URL}?curid={page.pageid})."
        )

    @wiki.autocomplete("query")
    async def wiki_query_autocomp(self, inter: Interaction, inp: str):
        # TODO: Match by longest substring first; fuzzy only if no results are found.
        return self.bot.wiki_cache.fuzzy(inp)


def setup(bot: CustomBot):
    bot.add_cog(WikiCog(bot))
