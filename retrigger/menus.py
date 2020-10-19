from __future__ import annotations

import logging
from typing import Any, List, Optional

import discord
from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate
from redbot.vendored.discord.ext import menus

from .converters import ChannelUserRole, Trigger

log = logging.getLogger("red.Trusty-cogs.retrigger")
_ = Translator("ReTrigger", __file__)


class ExplainReTriggerPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)
        self.pages = pages

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        if menu.ctx.channel.permissions_for(menu.ctx.me).embed_links:
            em = discord.Embed(
                description=page, colour=await menu.ctx.bot.get_embed_colour(menu.ctx)
            )
            em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class ReTriggerPages(menus.ListPageSource):
    def __init__(self, triggers: List[Trigger], guild: discord.Guild):
        super().__init__(triggers, per_page=1)
        self.active_triggers = triggers
        self.selection = None
        self.guild = guild

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, trigger: Trigger):
        self.selection = trigger
        msg_list = []
        embeds = menu.ctx.channel.permissions_for(menu.ctx.me).embed_links
        good = "\N{WHITE HEAVY CHECK MARK}"
        bad = "\N{NEGATIVE SQUARED CROSS MARK}"
        # trigger = await Trigger.from_json(triggers)
        author = self.guild.get_member(trigger.author)
        if not author:
            try:
                author = await menu.ctx.bot.fetch_user(trigger.author)
            except Exception:
                author = discord.Object(id=trigger.author)
                author.name = _("Unknown or Deleted User")
                author.mention = _("Unknown or Deleted User")
                author.avatar_url = "https://cdn.discordapp.com/embed/avatars/1.png"
        blacklist = []
        for y in trigger.blacklist:
            try:
                blacklist.append(await ChannelUserRole().convert(menu.ctx, str(y)))
            except BadArgument:
                continue
        if embeds:
            blacklist_s = ", ".join(x.mention for x in blacklist)
        else:
            blacklist_s = ", ".join(x.name for x in blacklist)
        whitelist = []
        for y in trigger.whitelist:
            try:
                whitelist.append(await ChannelUserRole().convert(menu.ctx, str(y)))
            except BadArgument:
                continue
        if embeds:
            whitelist_s = ", ".join(x.mention for x in whitelist)
        else:
            whitelist_s = ", ".join(x.name for x in whitelist)
        if trigger.response_type:
            responses = humanize_list(trigger.response_type)
        else:
            responses = _("This trigger has no actions and should be removed.")

        info = _(
            "__Name__: **{name}** \n"
            "__Active__: **{enabled}**\n"
            "__Author__: {author}\n"
            "__Count__: **{count}**\n"
            "__Response__: **{response}**\n"
        )
        if embeds:
            info = info.format(
                name=trigger.name,
                enabled=good if trigger.enabled else bad,
                author=author.mention,
                count=trigger.count,
                response=responses,
            )
        else:
            info = info.format(
                name=trigger.name,
                enabled=good if trigger.enabled else bad,
                author=author.name,
                count=trigger.count,
                response=responses,
            )
        text_response = ""
        if trigger.ignore_commands:
            info += _("Ignore commands: **{ignore}**\n").format(ignore=trigger.ignore_commands)
        if "text" in trigger.response_type:
            if trigger.multi_payload:
                text_response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "text")
            else:
                text_response = trigger.text
            if len(text_response) < 200:
                info += _("__Text__: ") + "**{response}**\n".format(response=text_response)
        if "rename" in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "text")
            else:
                response = trigger.text
            info += _("__Rename__: ") + "**{response}**\n".format(response=response)
        if "dm" in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "dm")
            else:
                response = trigger.text
            info += _("__DM__: ") + "**{response}**\n".format(response=response)
        if "command" in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "command")
            else:
                response = trigger.text
            info += _("__Command__: ") + "**{response}**\n".format(response=response)
        if "react" in trigger.response_type:
            if trigger.multi_payload:
                emoji_response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "react"
                ]
            else:
                emoji_response = trigger.text
            server_emojis = "".join(f"<{e}>" for e in emoji_response if len(e) > 5)
            unicode_emojis = "".join(e for e in emoji_response if len(e) < 5)
            info += _("__Emojis__: ") + server_emojis + unicode_emojis + "\n"
        if "add_role" in trigger.response_type:
            if trigger.multi_payload:
                role_response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "add_role"
                ]
            else:
                role_response = trigger.text
            roles = [menu.ctx.guild.get_role(r) for r in role_response]
            if embeds:
                roles_list = [r.mention for r in roles if r is not None]
            else:
                roles_list = [r.name for r in roles if r is not None]
            if roles_list:
                info += _("__Roles Added__: ") + humanize_list(roles_list) + "\n"
            else:
                info += _("Roles Added: Deleted Roles\n")
        if "remove_role" in trigger.response_type:
            if trigger.multi_payload:
                role_response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "remove_role"
                ]
            else:
                role_response = trigger.text
            roles = [menu.ctx.guild.get_role(r) for r in role_response]
            if embeds:
                roles_list = [r.mention for r in roles if r is not None]
            else:
                roles_list = [r.name for r in roles if r is not None]
            if roles_list:
                info += _("__Roles Removed__: ") + humanize_list(roles_list) + "\n"
            else:
                info += _("__Roles Added__: Deleted Roles\n")
        if whitelist_s:
            info += _("__Allowlist__: ") + whitelist_s + "\n"
        if blacklist_s:
            info += _("__Blocklist__: ") + blacklist_s + "\n"
        if trigger.cooldown:
            time = trigger.cooldown["time"]
            style = trigger.cooldown["style"]
            info += _("Cooldown: ") + "**{}s per {}**\n".format(time, style)
        if trigger.ocr_search:
            info += _("OCR: **Enabled**\n")
        if trigger.ignore_edits:
            info += _("Ignoring edits: **Enabled**\n")
        if trigger.delete_after:
            info += _("Message deleted after: {time} seconds.\n").format(time=trigger.delete_after)
        if trigger.read_filenames:
            info += _("Read filenames: **Enabled**\n")
        if trigger.chance:
            info += _("__Chance__: **1 in {number}**\n").format(number=trigger.chance)
        if embeds:
            # info += _("__Regex__: ") + box(trigger.regex.pattern, lang="bf")
            em = discord.Embed(
                timestamp=menu.ctx.message.created_at,
                colour=await menu.ctx.embed_colour(),
                title=_("Triggers for {guild}").format(guild=self.guild.name),
            )
            em.set_author(name=author, icon_url=author.avatar_url)
            if trigger.created_at == 0:
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            else:
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()} Created")
                em.timestamp = discord.utils.snowflake_time(trigger.created_at)

            first = True
            for pages in pagify(info, page_length=1024):
                if first:
                    em.description = pages
                    first = False
                else:
                    em.add_field(name=_("Trigger info continued"), value=pages)
            if len(text_response) >= 200:
                use_box = False
                for page in pagify(text_response, page_length=1000):
                    if page.startswith("```"):
                        use_box = True
                    if use_box:
                        em.add_field(name=_("__Text__"), value=box(page.replace("```", ""), lang="text"))
                    else:
                        em.add_field(name=_("__Text__"), value=page)
            for page in pagify(trigger.regex.pattern, page_length=1000):
                em.add_field(name=_("__Regex__"), value=box(page, lang="bf"))
            msg_list.append(em)
        else:
            info += _("Regex: ") + box(trigger.regex.pattern[: 2000 - len(info)], lang="bf")
        if embeds:
            return em
        else:
            return info
        # return await make_embed_from_submission(menu.ctx.channel, self._subreddit, submission)


class ReTriggerMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.page_start = page_start

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self._author_id):
            return False
        return payload.emoji in self.buttons

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
        skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
        skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        await self.message.delete()

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}"
    )
    async def toggle_trigger(self, payload: discord.RawReactionActionEvent) -> None:
        """Enables and disables triggers"""
        member = self.ctx.guild.get_member(payload.user_id)
        if await self.cog.can_edit(member, self.source.selection):
            self.source.selection.toggle()
            await self.show_checked_page(self.current_page)

    @menus.button("\N{NEGATIVE SQUARED CROSS MARK}")
    async def stop_trigger(self, payload: discord.RawReactionActionEvent) -> None:
        """Enables and disables triggers"""
        member = self.ctx.guild.get_member(payload.user_id)
        if await self.cog.can_edit(member, self.source.selection):
            self.source.selection.disable()
            await self.show_checked_page(self.current_page)

    @menus.button("\N{WHITE HEAVY CHECK MARK}")
    async def enable_trigger(self, payload: discord.RawReactionActionEvent) -> None:
        """Enables and disables triggers"""
        member = self.ctx.guild.get_member(payload.user_id)
        if await self.cog.can_edit(member, self.source.selection):
            self.source.selection.enable()
            await self.show_checked_page(self.current_page)

    @menus.button("\N{PUT LITTER IN ITS PLACE SYMBOL}")
    async def delete_trigger(self, payload: discord.RawReactionActionEvent) -> None:
        """Enables and disables triggers"""
        member = self.ctx.guild.get_member(payload.user_id)
        if await self.cog.can_edit(member, self.source.selection):
            msg = await self.ctx.send(
                _("Are you sure you want to delete trigger {name}?").format(
                    name=self.source.selection.name
                )
            )
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, self.ctx.author)
            await self.ctx.bot.wait_for("reaction_add", check=pred)
            if pred.result:
                await msg.delete()
                self.source.selection.disable()
                done = await self.cog.remove_trigger(payload.guild_id, self.source.selection.name)
                if done:
                    page = await self._source.get_page(self.current_page)
                    kwargs = await self._get_kwargs_from_page(page)
                    await self.message.edit(
                        content=_("This trigger has been deleted."), embed=kwargs["embed"]
                    )
                    for t in self.cog.triggers[self.ctx.guild.id]:
                        if t.name == self.source.selection.name:
                            self.cog.triggers[self.ctx.guild.id].remove(t)


class BaseMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.page_start = page_start

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.current_page = self.page_start
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self._author_id):
            return False
        return payload.emoji in self.buttons

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
        skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
        skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        await self.message.delete()
