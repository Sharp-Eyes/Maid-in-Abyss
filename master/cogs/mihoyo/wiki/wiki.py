from __future__ import annotations

from disnake import ApplicationCommandInteraction as Interaction
from disnake.ext import commands

import typing as t
from models.wiki import WeaponModel  # TODO: Remove when wiki updates
from utils.bot import CustomBot
from utils.helpers import fuzzy_scored

from .display import prettify_battlesuit, prettify_stigmata
from .models import (
    Battlesuit,
    ContentResponse,
    QueryResponse,
    ResponseModelT,
    StigmataSet,
    ValidCategory,
)

BASE_WIKI_URL = "https://honkaiimpact3.fandom.com/"
BASE_API_URL = "https://honkaiimpact3.fandom.com/api.php?"


# Cog


class WikiCog(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.wiki_cache: QueryResponse

    async def cog_load(self):
        await self.bot.wait_until_first_connect()  # ensure we have a session
        print("loading")
        await self.populate_wiki_cache()
        print("dunzo'd")

    async def API_request(
        self,
        params: dict[str, str],
        response_model: t.Type[ResponseModelT],
    ) -> ResponseModelT:
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
            "gcmlimit": "max",
        }

        for i, cat in enumerate(["Category:Stigmata", "Category:Battlesuits", "Category:Weapons"]):
            _params = params.copy()
            _params.update(gcmtitle=cat)

            if not i:
                result = await self.API_request(_params, QueryResponse)
            else:
                result.update(await self.API_request(_params, QueryResponse))

        self.wiki_cache = result

    @commands.command(name="reloadwikicache")
    async def _reloadwikicache(self, ctx):
        await self.populate_wiki_cache()
        print("reloaded wiki cache")

    @commands.slash_command(
        name="wiki",
        guild_ids=[701039771157397526, 511630315039490076, 555270199402823682, 268046379085987840],
    )
    async def wiki(self, inter: Interaction, query: str):
        await inter.response.defer()

        page = self.wiki_cache.get(query)
        if not page:
            # mobile users can send without picking an autocomplete option
            corrected: dict[str, str] = self.wiki_query_autocomp(None, query)
            corrected_name = next(iter(corrected.values()))
            page = self.wiki_cache.get(corrected_name)  # assume top result

        if not page:
            raise KeyError(f"No page could be found by the name of {corrected_name}.")

        page_params = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "pageids": page.pageid,
            "rvprop": "content",
            "rvslots": "main",
        }
        content = await self.API_request(page_params, ContentResponse)

        if page.categories.intersection(
            {
                ValidCategory.PSY,
                ValidCategory.BIO,
                ValidCategory.MECH,
                ValidCategory.QUA,
                ValidCategory.IMG,
            }
        ):
            battlesuit = Battlesuit(**content.pages[0].data)
            embeds = prettify_battlesuit(battlesuit)

        elif page.categories.intersection(
            {
                ValidCategory.STIGMA1,
                ValidCategory.STIGMA2,
                ValidCategory.STIGMA3,
                ValidCategory.STIGMA4,
                ValidCategory.STIGMA5,
            }
        ):
            stigmata_set = StigmataSet(**content.pages[0].data)
            embeds = prettify_stigmata(stigmata_set)

        elif page.categories.intersection(
            {
                ValidCategory.PISTOL,
                ValidCategory.KATANA,
                ValidCategory.CANNON,
                ValidCategory.GREATSWORD,
                ValidCategory.CROSS,
                ValidCategory.GAUNTLET,
                ValidCategory.SCYTHE,
                ValidCategory.LANCE,
                ValidCategory.BOW,
            }
        ):
            # Old implementation(ish) as weapon pages haven't been updated yet
            # TODO: replace with new implementation when they get updated, delete old wiki model file
            content_page = max(content.pages, key=lambda page: int(page.data.get("rarity", 0)))
            wiki_result = WeaponModel(**content_page.data)
            embeds = wiki_result.to_embed()

        else:
            await inter.edit_original_message(
                content="It appears this type of query hasn't been implemented yet. "
                "Please check back soon:tm:. For now, have this "
                f"[link]({BASE_WIKI_URL}?curid={page.pageid})."
            )
            return

        await inter.edit_original_message(embeds=embeds)

    @wiki.autocomplete("query")
    async def wiki_query_autocomp(self, inter: Interaction, inp: str):

        def visualize_match(title: str, match: str) -> str:
            return title if title == match else f"{title} ({match})"

        fuzzy_result: list[tuple[int, str, str]] = []
        pages = self.wiki_cache.pages.copy()
        for strict in (True, False):
            for page_name, page in pages.items():
                page_best_match = fuzzy_scored(inp, page.all_names, strict=strict, n=1)
                if page_best_match:
                    fuzzy_result.append(page_best_match[0] + (page_name,))

            if len(fuzzy_result) >= 20 or not strict:
                break

            for _, _, title in fuzzy_result:
                pages.pop(title)

        return {
            visualize_match(title, match): title
            for _, match, title in sorted(fuzzy_result)[:20]
        }
