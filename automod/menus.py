from __future__ import annotations

from typing import Any, List, Optional

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta, inline
from redbot.vendored.discord.ext import menus

log = getLogger("red.trusty-cogs.automod")
_ = Translator("This string isn't used for anything", __file__)


class AutoModRulePages(menus.ListPageSource):
    def __init__(self, pages: List[discord.AutoModRule], *, guild: discord.Guild):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.current_item: discord.AutoModRule = None
        self.guild = guild

    async def delete(self, view: BaseMenu, author: discord.Member) -> None:
        try:
            await self.current_item.delete(reason=f"Deleted by {author}")
        except Exception:
            return

    async def toggle(self, view: BaseMenu, author: discord.Member) -> bool:
        try:
            self.current_itme = await self.current_item.edit(
                enabled=not self.current_item.enabled, reason=f"Toggled by {author}"
            )
        except Exception:
            return False
        return True

    async def format_page(self, view: discord.ui.View, page: discord.AutoModRule):
        # fetch the most recently edited version since we can toggle it through this
        # menu and our cached ones may be out of date
        self.current_item = page = await self.guild.fetch_automod_rule(page.id)
        title = (
            f"\N{WHITE HEAVY CHECK MARK} {page.name}"
            if page.enabled
            else f"\N{CROSS MARK} {page.name}"
        )
        em = discord.Embed(
            title=title, colour=await view.cog.bot.get_embed_colour(view.ctx.channel)
        )
        em.set_author(name=f"AutoMod Rules for {page.guild.name}", icon_url=page.guild.icon)
        trigger = page.trigger
        trigger_type_str = trigger.type.name.replace("_", " ").title()
        description = f"Type: {trigger_type_str}\n"
        if trigger.mention_limit:
            description += f"Mention Limit: {trigger.mention_limit}\n"
        if trigger.presets:
            description += "Discord Preset Triggers:\n"
            description += (
                "\n".join(f" - {k}" for k, v in dict(trigger.presets).items() if v) + "\n"
            )
        trigger_keys = (
            "allow_list",
            "keyword_filter",
            "regex_patterns",
        )
        for key in trigger_keys:
            if triggers := getattr(trigger, key, None):
                key_name = key.replace("_", " ").title()
                description += f"- {key_name}:\n"
                description += "\n".join(f" - {inline(t)}" for t in triggers) + "\n"
        em.description = description[:4096]

        # em.add_field(name="Enabled", value=str(page.enabled))
        actions_str = ""
        for action in page.actions:
            if action.type is discord.AutoModRuleActionType.block_message:
                actions_str += "- Block Message\n"
                if action.custom_message:
                    actions_str += f"- Send this Message to the user:\n - {action.custom_message}"
            elif action.type is discord.AutoModRuleActionType.timeout:
                actions_str += f"- Timeout for {humanize_timedelta(timedelta=action.duration)}\n"
            else:
                actions_str += f"- Send alert to <#{action.channel_id}>\n"
        em.add_field(name="Actions", value=actions_str, inline=False)
        em.add_field(
            name="Creator",
            value=page.creator.mention if page.creator else inline(str(page.creator_id)),
        )
        if page.exempt_roles:
            em.add_field(
                name="Exempt Roles",
                value="\n".join(f"- {r.mention}" for r in page.exempt_roles),
            )
        if page.exempt_channels:
            em.add_field(
                name="Exempt Channels",
                value="\n".join(f"- {c.mention}" for c in page.exempt_channels),
            )
        em.add_field(name="ID", value=inline(str(page.id)))
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class AutoModActionsPages(menus.ListPageSource):
    def __init__(self, pages: List[dict], *, guild: discord.Guild):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.current_item: dict = None
        self.guild = guild

    async def delete(self, view: BaseMenu, author: discord.User) -> None:
        name = self.current_item.get("name", None)
        async with view.cog.config.guild(self.guild).actions() as actions:
            if name in actions:
                del actions[name]

    async def format_page(self, view: discord.ui.View, page: dict):
        self.current_item = page
        guild = page["guild"]
        name = page["name"]
        em = discord.Embed(
            title=name, colour=await view.cog.bot.get_embed_colour(view.ctx.channel)
        )
        ret = ""
        for k, v in page.items():
            if v is None or k in ("guild", "name"):
                continue
            ret += f"- {k}: {v}\n"
        em.description = ret
        em.set_author(name=f"AutoMod Actions for {guild.name}", icon_url=guild.icon)
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class AutoModTriggersPages(menus.ListPageSource):
    def __init__(self, pages: List[dict], *, guild: discord.Guild):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.current_item: dict = None
        self.guild: discord.Guild = guild

    async def delete(self, view: BaseMenu, author: discord.User) -> None:
        name = self.current_item.get("name", None)
        async with view.cog.config.guild(self.guild).triggers() as triggers:
            if name in triggers:
                del triggers[name]

    async def format_page(self, view: discord.ui.View, page: dict):
        self.current_item = page
        guild = page["guild"]
        self.guild = guild
        name = page["name"]
        em = discord.Embed(
            title=name, colour=await view.cog.bot.get_embed_colour(view.ctx.channel)
        )
        ret = ""
        for k, v in page.items():
            if v is None or k in ("guild", "name"):
                continue
            if k == "presets":
                presets = dict(discord.AutoModPresets._from_value(value=v)).items()
                v = "\n".join(f" - {x}" for x, y in presets if y)
                name = "Discord Presets"
                ret += f"- {name}:\n{v}\n"
                continue
            name = k.replace("_", " ").title()
            v = "\n".join(f" - {inline(x)}" for x in v)
            ret += f"- {name}:\n{v}\n"
        em.description = ret
        em.set_author(name=f"AutoMod Triggers for {guild.name}", icon_url=guild.icon)
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: BaseMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        await self.view.message.delete()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: BaseMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page + 1, interaction)


class BackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: BaseMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page - 1, interaction)


class LastItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: BaseMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction)


class FirstItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: BaseMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class ToggleRuleButton(discord.ui.Button):
    def __init__(
        self,
        row: int,
    ):
        self.view: BaseMenu
        super().__init__(style=discord.ButtonStyle.secondary, row=row)

    def modify(self):
        item: discord.AutoModRule = self.view.source.current_item
        self.emoji = (
            "\N{NEGATIVE SQUARED CROSS MARK}" if item.enabled else "\N{WHITE HEAVY CHECK MARK}"
        )
        self.label = _("Disable Rule") if item.enabled else _("Enable Rule")

    async def callback(self, interaction: discord.Interaction):
        """Enables and disables triggers"""
        member = interaction.user
        await self.view.source.toggle(self.view, member)
        self.modify()
        await self.view.show_page(self.view.current_page, interaction)


class DeleteButton(discord.ui.Button):
    def __init__(
        self,
        row: int,
    ):
        self.view: BaseMenu
        super().__init__(label=_("Delete"), style=discord.ButtonStyle.red, row=row)

    async def callback(self, interaction: discord.Interaction):
        """Enables and disables triggers"""
        member = interaction.user
        await self.view.source.delete(self.view, member)
        await interaction.response.edit_message(content="This item has been deleted.", view=None)


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.cog = cog
        self.bot = None
        self.message = message
        self._source = source
        self.ctx = None
        self.current_page = kwargs.get("page_start", 0)
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.toggle_button: Optional[ToggleRuleButton] = None
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.delete_button = DeleteButton(1)
        self.add_item(self.delete_button)
        if isinstance(source, AutoModRulePages):
            self.toggle_button = ToggleRuleButton(1)
            self.add_item(self.toggle_button)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.bot = self.cog.bot
        # await self.source._prepare_once()
        self.message = await self.send_initial_message(ctx)

    def check_paginating(self):
        if not self.source.is_paginating():
            self.forward_button.disabled = True
            self.back_button.disabled = True
            self.first_item.disabled = True
            self.last_item.disabled = True
        else:
            self.forward_button.disabled = False
            self.back_button.disabled = False
            self.first_item.disabled = False
            self.last_item.disabled = False

    async def _get_kwargs_from_page(self, page):
        self.check_paginating()
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if self.toggle_button is not None:
            self.toggle_button.modify()
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.author = ctx.author
        if self.ctx is None:
            self.ctx = ctx
        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await ctx.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = self.source.pages.index(page)
        kwargs = await self._get_kwargs_from_page(page)
        if interaction.response.is_done():
            await interaction.followup.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)
        # await self.message.edit(**kwargs)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.user.id not in (
            *interaction.client.owner_ids,
            self.author.id,
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class ConfirmView(discord.ui.View):
    """
    This is just a copy of my version from Red to be removed later possibly
    https://github.com/Cog-Creators/Red-DiscordBot/pull/6176
    """

    def __init__(
        self,
        author: Optional[discord.abc.User] = None,
        *,
        timeout: float = 180.0,
        disable_buttons: bool = False,
    ):
        if timeout is None:
            raise TypeError("This view should not be used as a persistent view.")
        super().__init__(timeout=timeout)
        self.result: Optional[bool] = None
        self.author: Optional[discord.abc.User] = author
        self.message: Optional[discord.Message] = None
        self.disable_buttons = disable_buttons

    async def on_timeout(self):
        if self.message is None:
            # we can't do anything here if message is none
            return

        if self.disable_buttons:
            self.confirm_button.disabled = True
            self.dismiss_button.disabled = True
            await self.message.edit(view=self)
        else:
            await self.message.edit(view=None)

    @discord.ui.button(label=_("Yes"), style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        # respond to the interaction so the user does not see "interaction failed".
        await interaction.response.defer()
        # call `on_timeout` explicitly here since it's not called when `stop()` is called.
        await self.on_timeout()

    @discord.ui.button(label=_("No"), style=discord.ButtonStyle.secondary)
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        # respond to the interaction so the user does not see "interaction failed".
        await interaction.response.defer()
        # call `on_timeout` explicitly here since it's not called when `stop()` is called.
        await self.on_timeout()

    async def interaction_check(self, interaction: discord.Interaction):
        if self.message is None:
            self.message = interaction.message
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
