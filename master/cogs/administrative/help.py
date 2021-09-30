from typing import Optional

import disnake
from disnake.ext import commands
from disnake import ApplicationCommandInteraction as Interaction

import re
# import inspect

from main import DEFAULT_PREFIX
from utils.classes import Codeblock

import logging
logger = logging.getLogger("Help")


class Help_Cog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def append_command_doc_to_embed(self, command: commands.Command, embed: disnake.Embed):

        if not command.description:
            return embed.add_field(
                name="Description:",
                value=command.brief or "This command appears to not yet have a description."
            )

        def _eliminate_match_and_create_field(match: re.Match):
            # (?P<x>...) matches are returned in ~.groupdict() as {x: ...} instead of the usual
            # ~.groups() tuple. This can be used to quickly generate an embed field, which requires
            # 'name' and 'value' params
            embed.add_field(
                **match.groupdict(),
                inline=bool(match[2])  # 2nd match stores field flags <n_>, atm only 'i' for inline
            )

        # pattern substring that denotes how a name field should/can look, including flags
        name_flag = r"<n([i]?)>"

        remainder: str = re.sub(
            fr"({name_flag}(?P<name>.*?)<v>(?P<value>.*?))(?={name_flag}|\Z)",
            _eliminate_match_and_create_field,
            command.description,
            flags=re.M | re.S
        )

        if remainder and not remainder.isspace():
            # More than whitespace remains after eliminating fields ->
            # some data wasn't found, probably unintentional
            logger.warning(
                f"Docstr for command '{command.qualified_name}' has remaining "
                f"content after processing: '{remainder}'. "
            )

        return embed

    def get_command_signature(self, command: str) -> tuple[commands.Command, str]:

        cmd = self.bot.get_command(command)
        if cmd:
            return cmd, cmd.signature

        # slash_cmd: CogSubcommandObject = nested_get(self.slash.subcommands, command.split())
        # if not slash_cmd:
        #     raise commands.CommandNotFound(command)

        # faux_cmd = commands.command(name=slash_cmd.name)(slash_cmd.func)
        # return faux_cmd, faux_cmd.signature[6:]

    def construct_help_embed(self, prefix: str, command: str):
        cmd_fmt = "{prefix}{name} {sig}"

        cmd, signature = self.get_command_signature(command)
        cmd_names = [cmd.qualified_name, *cmd.aliases]

        title = f"Command help:\n> {cmd.qualified_name}"
        description = (
            "**Aliases**:"
            + Codeblock(" | ".join(cmd_names), lang="md")
            + "**Usage**:"
            + Codeblock(cmd_fmt.format(prefix=prefix, name=cmd.qualified_name, sig=signature))
            + "Note: `<arg>` is a mandatory argument and `[arg]` is optional. `...` indicates "
            "multiple values are allowed."
        )

        embed = disnake.Embed(
            title=title,
            description=description
        )
        self.append_command_doc_to_embed(cmd, embed)

        return embed

    # @cog_ext.cog_slash(
    #     name="help",
    #     description="Get help with a specified command, "
    #                 "or general information if you don't specify one.",
    #     guild_ids=[701039771157397526],
    #     options=[
    #         create_option(
    #             name="command",
    #             description="The command you seek help with. "
    #                         "Leave blank for a generic help interface.",
    #             option_type=3,
    #             required=False
    #         )
    #     ]
    # )

    # @commands.slash_command(name="help")
    async def so_cool(self, inter: Interaction, *, command: str = ""):
        # Create a fake message so that we can determine prefix
        msg = disnake.PartialMessage(channel=inter.channel, id=inter.command_id)
        prefixes = await self.bot.get_prefix(msg)
        prefix = prefixes[2] if len(prefixes) > 2 else DEFAULT_PREFIX[0]

        if command:
            embed = self.construct_help_embed(prefix, command)
            self.bot.dispatch("embed_dispatch", inter, embed, hidden=True)


def setup(bot: commands.Bot):
    bot.add_cog(Help_Cog(bot))
