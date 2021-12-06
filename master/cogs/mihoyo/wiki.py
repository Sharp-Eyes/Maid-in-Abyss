from __future__ import annotations

from disnake import ApplicationCommandInteraction as Interaction
from disnake.ext import commands

from typing import Callable, Type, TypeVar
from models.wiki import QueryPage  # TODO: remove
from models.wiki import (
    BattlesuitModel,
    ContentResponseModel,
    QueryResponse,
    StigmataSetModel,
    ValidCategory,
    WeaponModel,
)
from utils.bot import CustomBot

BASE_WIKI_URL = "https://honkaiimpact3.fandom.com/"
BASE_API_URL = "https://honkaiimpact3.fandom.com/api.php?"


ResponseModel = TypeVar("ResponseModel")


# Cog


class WikiCog(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot

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
        response_model: Type[ResponseModel] | Callable[..., ResponseModel],
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

    @commands.slash_command(
        name="wiki",
        guild_ids=[701039771157397526, 511630315039490076, 555270199402823682, 268046379085987840],
    )
    async def wiki(self, inter: Interaction, query: str):
        await inter.response.defer()
        page: QueryPage = self.bot.wiki_cache.get(query)

        page_params = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "pageids": page.pageid,
            "rvprop": "content",
            "rvslots": "main",
        }
        content = await self.API_request(page_params, ContentResponseModel)

        if page.categories.intersection(
            {
                ValidCategory.PSY,
                ValidCategory.BIO,
                ValidCategory.MECH,
                ValidCategory.QUA,
                ValidCategory.IMG,
            }
        ):
            wiki_result = BattlesuitModel(content=content)

        elif page.categories.intersection(
            {
                ValidCategory.STIGMA1,
                ValidCategory.STIGMA2,
                ValidCategory.STIGMA3,
                ValidCategory.STIGMA4,
                ValidCategory.STIGMA5,
            }
        ):
            wiki_result = StigmataSetModel(
                stigs=dict.fromkeys(("T", "M", "B"), page.title), content=content
            )

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
            data = content.highest_rarity_by_name(page.title).data
            wiki_result = WeaponModel(**data)

        else:
            await inter.edit_original_message(
                content="It appears this type of query hasn't been implemented yet. "
                "Please check back soon:tm:. For now, have this "
                f"[link]({BASE_WIKI_URL}?curid={page.pageid})."
            )
            return

        await inter.edit_original_message(embeds=wiki_result.to_embed())

    @wiki.autocomplete("query")
    async def wiki_query_autocomp(self, inter: Interaction, inp: str):
        # TODO: Match by longest substring first; fuzzy only if no results are found.
        return self.bot.wiki_cache.fuzzy(inp)


def setup(bot: CustomBot):
    bot.add_cog(WikiCog(bot))
