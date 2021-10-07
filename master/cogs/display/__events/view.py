from typing import Optional
from .event import Event

from disnake.ui import button, Button, View
from disnake import MessageInteraction
from disnake.ext.commands import Bot


def create_event_view(
    bot: Bot,
    view_name: str,
    events: dict[str, Event],
    *,
    timeout: Optional[int] = 180
):
    dict_ = {}
    for event_name, event in events.items():
        event_name = event_name.replace(" ", "_")

        dict_[event_name] = create_event_button(bot, event_name, event)

    new = type(
        view_name,
        (View,),
        dict_
    )
    return new(timeout=timeout)


def create_event_button(bot: Bot, name: str, event: Event):

    async def new_button(self, button: Button, inter: MessageInteraction):
        member = inter.author
        guild = inter.guild
        for role in guild.roles:
            if role.name.lower() == name.replace("_", " "):
                break
        else:
            return

        if role in member.roles:
            await member.remove_roles(role)
            opt = "out"
        else:
            await member.add_roles(role)
            opt = "in"

        await inter.response.send_message(
            f"I have successfully opted you {opt} for {name} notifications!",
            ephemeral=True
        )

    icon = bot.get_emoji(event.icon)
    new_button.__name__ = name

    return button(
        custom_id=f"event {name}",
        emoji=icon
    )(new_button)
