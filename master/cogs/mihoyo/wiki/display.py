import disnake

import re
import typing as t
import urllib
import wikitextparser as wtp

from .models import BASE_WIKI_URL, Battlesuit, Colours, Emoji, SetBonus, Stigma, StigmataSet

# STRING PARSERS


def urlify(s: str):
    """Convert a string value to a value more likely to be recognized by
    the HI3 wiki. Meant to be used to convert names to urls
    """
    return urllib.parse.quote(s.replace(" ", "_"))


def image_link(name: str) -> str:
    """Tries to create an image url by name, linking to the HI3 wiki."""
    return f"{BASE_WIKI_URL}/Special:Redirect/file/{urlify(name)}.png"


def wiki_link(name: str) -> str:
    """Tries to create a page url linking to an HI3 wiki page."""
    return f"{BASE_WIKI_URL}{urlify(name)}"


def discord_link(display: str, link: str = None, from_display=True):
    """Formats a link into markdown syntax for use in discord embeds."""
    if link is None and from_display is True:
        link = wiki_link(display)
    return f"[{display}]({link})"


TAG_MAPPING = {
    "inc": "**",
    "increase": "**",
    "color-blue": "**",
    "color-orange": "**",
    "br": "\n",
}

TEMPLATE_MAPPING = {"star": "\N{BLACK STAR}"}


def parse_wiki_str(string: str) -> str:
    """Parse a string with MediaWiki markup and HTML tags to Markdown recognized by discord."""

    repl: t.Optional[str]

    def replace(lst: list[t.Optional[str]], begin: int, end: int, repl: str = None) -> None:
        lst[begin:end] = [repl] + [None] * (end - begin - 1)

    wt = wtp.parse(string)
    list_str: list[t.Optional[str]] = list(string)

    for em in wt.get_bolds_and_italics():
        span_l, span_h = em.span
        match_l, match_h = em._match.span(1)
        repl = "**" if isinstance(em, wtp.Bold) else "_"
        replace(list_str, span_l, span_l + match_l, repl)
        replace(list_str, span_l + match_h, span_h, repl)

    for tag in wt.get_tags():
        span_l, span_h = tag.span
        match_l, match_h = tag._match.span("contents")
        if match_l != -1:  # not a self-closing tag
            repl = TAG_MAPPING.get(tag.attrs["class"])
            replace(list_str, span_l, span_l + match_l, repl)
            replace(list_str, span_l + match_h, span_h, repl)
        else:  # remove the whole self-closing tag
            replace(list_str, span_l, span_h, TAG_MAPPING.get(tag.name))

    for wikilink in wt.wikilinks:
        span_l, span_h = wikilink.span
        if wikilink.wikilinks:
            # TODO: figure out if this is relevant
            replace(list_str, span_l, span_h, "<placeholder1>")  # image
        else:
            match_l, match_h = wikilink._match.span(4)  # text span
            if match_l != -1:
                # TODO: Figure out if this is relevant
                replace(list_str, span_l, span_l + match_l, "<placeholder2>")
                replace(list_str, span_l + match_h, span_h)
            else:
                # Page link
                replace(list_str, span_l, span_h, discord_link(wikilink.target))

    for template in wt.templates:
        span_l, span_h = template.span
        if not template.templates:
            replace(list_str, span_l, span_h, TEMPLATE_MAPPING.get(template.name))

    return "".join(c for c in list_str if c is not None)


# - BATTLESUITS


def battlesuit_description(battlesuit: Battlesuit) -> str:
    """Used as fallback for battlesuits without a description. Appears to be the case for augments."""
    return f"{discord_link(battlesuit.character)} battlesuit." + (
        f"\n{discord_link('Augment Core')} upgrade of {discord_link(battlesuit.augment)}"
        if battlesuit.augment
        else ""
    )


def battlesuit_header_embed(battlesuit: Battlesuit) -> disnake.Embed:
    desc = (
        parse_wiki_str(battlesuit.profile)
        if battlesuit.profile
        else battlesuit_description(battlesuit)
    )
    return (
        disnake.Embed(
            description=f"{desc} {chr(10240) * 42}",  # blank line of wide invis chars to widen embed
            color=Colours[battlesuit.type.name],
        )
        .set_author(
            name=f"{battlesuit.name} (link)",
            url=wiki_link(battlesuit.name),
            icon_url=image_link(f"Valkyrie_{battlesuit.rank.name}"),
        )
        .set_thumbnail(url=image_link(f"{battlesuit.name}_(Avatar)"))
    )


def battlesuit_info_embed(battlesuit: Battlesuit) -> disnake.Embed:
    info_embed = disnake.Embed(color=Colours[battlesuit.type.name]).add_field(
        name="About:",
        value=(
            " ".join(battlesuit.core_strengths)
            + f"\nType: {battlesuit.type} {battlesuit.type.name}"
            + f"\nValkyrie: {Emoji.VALKYRIE_GENERIC} {discord_link(battlesuit.character)}"
            + (
                f"\nAugment (of): {Emoji.VALKYRIE_GENERIC} {discord_link(battlesuit.augment)}"
                if battlesuit.augment
                else ""
            )
        ),
        inline=False,
    )
    for recommendation in battlesuit.recommendations:
        info_embed.add_field(
            name=f"{recommendation.type.title()}:",
            value=(
                f"{Emoji.EQUIPMENT_GENERIC} {discord_link(recommendation.weapon.name)}\n"
                f"{Emoji.STIG_TOP} {discord_link(recommendation.T.name)}\n"
                f"{Emoji.STIG_MID} {discord_link(recommendation.M.name)}\n"
                f"{Emoji.STIG_BOT} {discord_link(recommendation.B.name)}"
            ),
        )

    return info_embed


def prettify_battlesuit(battlesuit: Battlesuit) -> list[disnake.Embed]:
    return [battlesuit_header_embed(battlesuit), battlesuit_info_embed(battlesuit)]


# - STIGMATA


def make_stigma_description(stigma: Stigma, show_rarity: bool = False):
    """Generate the description for a single `Stigma`."""
    desc = (f"Rarity: {stigma.rarity * Emoji.STAR}\n" if show_rarity else "") + stigma.effect

    stats = ",\u2003".join(
        f"**{name}**: {stat}"
        for name, stat in (
            ("HP", stigma.hp),
            ("ATK", stigma.attack),
            ("DEF", stigma.defense),
            ("CRT", stigma.crit),
        )
        if stat
    )
    return f"{parse_wiki_str(desc)}\n\n{stats}"


def make_stigma_embed(stigma: Stigma, show_rarity: bool) -> disnake.Embed:
    """Generate a display embed for a single `Stigma`."""
    return (
        disnake.Embed(
            title=stigma.effect_name,
            description=make_stigma_description(stigma, show_rarity),
            color=Colours[stigma.slot.name],
        )
        .set_author(
            name=stigma.name,
            url=wiki_link(stigma.set_name),
            icon_url=image_link(f"Stigmata_{stigma.slot.name.title()}"),
        )
        .set_thumbnail(url=image_link(f"{stigma.set_name} ({stigma.slot}) (Icon)"))
    )


def make_set_bonus_embed(set_bonuses: t.Sequence[SetBonus], set_rarity: int) -> disnake.Embed:
    """Generate a display embed for a `StigmataSet`'s set bonuses."""
    set_embed = disnake.Embed(description=f"Rarity: {Emoji.STAR * set_rarity}")
    for set_bonus in set_bonuses:
        set_embed.add_field(
            name=set_bonus.name, value=parse_wiki_str(set_bonus.effect), inline=True
        )
    return set_embed


def prettify_stigmata(stigmata_set: StigmataSet) -> list[disnake.Embed]:
    """Generate display embeds for a `StigmataSet`."""
    set_stigmata, set_bonuses = stigmata_set.main_set_with_bonuses

    embeds = [make_stigma_embed(stig, stig not in set_stigmata) for stig in stigmata_set.stigmata]

    if set_bonuses and set_stigmata:
        embeds.append(make_set_bonus_embed(set_bonuses, set_stigmata[0].rarity))

    return embeds
