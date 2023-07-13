from __future__ import annotations

from typing import Any, List, Optional, Union

import discord
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, pagify
from redbot.vendored.discord.ext import menus

from .abc import ReTriggerMixin
from .converters import ChannelUserRole, MultiResponse, Trigger, TriggerResponse

try:
    import regex as re
except ImportError:
    import re

log = getLogger("red.Trusty-cogs.retrigger")
_ = Translator("ReTrigger", __file__)


class ExplainReTriggerPages(menus.ListPageSource):
    def __init__(self, pages: List[str]):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.select_options = []
        for count, page in enumerate(pages):
            self.select_options.append(discord.SelectOption(label=f"Page {count+1}", value=count))

    def is_paginating(self):
        return True

    async def format_page(self, view: discord.ui.View, page: str):
        if view.ctx.channel.permissions_for(view.ctx.guild.me).embed_links:
            em = discord.Embed(
                description=page, colour=await view.cog.bot.get_embed_colour(view.ctx.channel)
            )
            em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class ReTriggerPages(menus.ListPageSource):
    def __init__(self, triggers: List[Trigger], guild: discord.Guild):
        super().__init__(triggers, per_page=1)
        self.active_triggers = triggers
        self.selection: Trigger
        self.guild = guild
        self.enabled = False
        self.select_options = []
        for count, trigger in enumerate(triggers):
            self.select_options.append(
                discord.SelectOption(label=trigger.name[:25], value=str(count))
            )

    def is_paginating(self):
        return True

    async def format_page(self, view: ReTriggerMenu, trigger: Trigger):
        self.selection = trigger
        msg_list = []
        embeds = view.ctx.channel.permissions_for(view.ctx.guild.me).embed_links
        good = "\N{WHITE HEAVY CHECK MARK}"
        bad = "\N{NEGATIVE SQUARED CROSS MARK}"
        # trigger = await Trigger.from_json(triggers)
        self.enabled = trigger.enabled
        author = self.guild.get_member(trigger.author)
        if not author:
            try:
                author = await view.cog.bot.fetch_user(trigger.author)
            except Exception:
                author = discord.Object(id=trigger.author)
                author.name = _("Unknown or Deleted User")
                author.mention = _("Unknown or Deleted User")
                author.display_avatar = "https://cdn.discordapp.com/embed/avatars/1.png"
        blacklist = []
        for y in trigger.blacklist:
            try:
                blacklist.append(await ChannelUserRole().convert(view.ctx, str(y)))
            except BadArgument:
                continue
        blacklist_s = ", ".join(x.mention for x in blacklist)
        whitelist = []
        for y in trigger.whitelist:
            try:
                whitelist.append(await ChannelUserRole().convert(view.ctx, str(y)))
            except BadArgument:
                continue
        whitelist_s = ", ".join(x.mention for x in whitelist)
        if trigger.response_type:
            responses = humanize_list(list({t.name for t in trigger.response_type}))
        else:
            responses = _("This trigger has no actions and should be removed.")

        info = _(
            "__Name__: **{name}** \n"
            "__Active__: **{enabled}**\n"
            "__Author__: {author}\n"
            "__Count__: **{count}**\n"
            "__Created__: **{created}**\n"
            "__Response__: **{response}**\n"
            "__NSFW__: **{nsfw}**\n"
            "__Thread__: {thread}\n"
        )
        info = info.format(
            name=trigger.name,
            enabled=good if trigger.enabled else bad,
            author=author.mention,
            created=discord.utils.format_dt(trigger.created_at, style="R"),
            count=trigger.count,
            response=responses,
            nsfw=trigger.nsfw,
            thread=trigger.thread.format_str(),
        )
        text_response: str = ""
        if trigger.ignore_commands:
            info += _("__Ignore commands__: **{ignore}**\n").format(ignore=trigger.ignore_commands)
        if TriggerResponse.text in trigger.response_type:
            if trigger.multi_payload:
                text_response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.text
                )
            else:
                text_response = trigger.text
            if len(text_response) < 200:
                info += _("__Text__: ") + "**{response}**\n".format(response=text_response)
        if trigger.reply is not None:
            info += _("__Replies with Notification__:") + "**{response}**\n".format(
                response=trigger.reply
            )
        if TriggerResponse.rename in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.rename
                )
            else:
                response = trigger.text
            info += _("__Rename__: ") + "**{response}**\n".format(response=response)
        if TriggerResponse.dm in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.dm
                )
            else:
                response = trigger.text
            info += _("__DM__: ") + "**{response}**\n".format(response=response)
        if TriggerResponse.dmme in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.dmme
                )
            else:
                response = trigger.text
            info += _("__Self DM__: ") + "**{response}**\n".format(response=response)
        if TriggerResponse.command in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.command
                )
            else:
                response = trigger.text
            info += _("__Command__: ") + "**{response}**\n".format(response=response)
        if TriggerResponse.react in trigger.response_type:
            server_emojis = "".join(str(e) for e in trigger.reactions)
            info += _("__Emojis__: ") + server_emojis + "\n"
        if TriggerResponse.add_role in trigger.response_type:
            roles = [view.ctx.guild.get_role(r) for r in trigger.add_roles]
            roles_list = [r.mention for r in roles if r is not None]
            if roles_list:
                info += _("__Roles Added__: ") + humanize_list(roles_list) + "\n"
            else:
                info += _("Roles Added: Deleted Roles\n")
        if TriggerResponse.remove_role in trigger.response_type:
            roles = [view.ctx.guild.get_role(r) for r in trigger.remove_roles]
            roles_list = [r.mention for r in roles if r is not None]
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
            info += _("__Cooldown__: ") + "**{}s per {}**\n".format(time, style)
        if trigger.ocr_search:
            info += _("__OCR__: **Enabled**\n")
        if trigger.check_edits:
            info += _("__Checking edits__: **Enabled**\n")
        if trigger.delete_after:
            info += _("__Message deleted after__: {time} seconds.\n").format(
                time=trigger.delete_after
            )
        if trigger.read_filenames:
            info += _("__Read filenames__: **Enabled**\n")
        if trigger.read_thread_title:
            info += _("__Read Thread Titles__: **Enabled**\n")
        if trigger.tts:
            info += _("__TTS__: **Enabled**\n")
        if trigger.chance:
            info += _("__Chance__: **1 in {number}**\n").format(number=trigger.chance)
        if TriggerResponse.text in trigger.response_type:
            info += _("__Mentions__:\n")
            info += _("- Users: **{user_mention}**\n").format(user_mention=trigger.user_mention)
            info += _("- Roles: **{role_mention}**\n").format(role_mention=trigger.role_mention)
            info += _("- Everyone: **{everyone_mention}**\n").format(
                everyone_mention=trigger.everyone_mention
            )
        if last_modified_str := trigger.last_modified_str(view.ctx):
            info += last_modified_str
        if trigger.regex:
            pattern_error = ""
            pattern = trigger.regex.pattern
        else:
            try:
                trigger.compile()
                pattern = trigger.regex.pattern
                pattern_error = ""
            except Exception as e:
                pattern_error = str(e)
                pattern = trigger._raw_regex
        if trigger.read_embeds:
            info += _("__Read Embeds__: **Enabled**\n")
        if embeds:
            # info += _("__Regex__: ") + box(trigger.regex.pattern, lang="bf")
            em = discord.Embed(
                colour=await view.cog.bot.get_embed_colour(view.ctx.channel),
                title=_("Triggers for {guild}").format(guild=self.guild.name),
            )
            em.set_author(name=author, icon_url=author.display_avatar)
            if trigger.created_at == 0:
                em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
            else:
                em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()} Created")
                em.timestamp = trigger.created_at

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
                        em.add_field(
                            name=_("__Text__"), value=box(page.replace("```", ""), lang="text")
                        )
                    else:
                        em.add_field(name=_("__Text__"), value=page)
            for page in pagify(pattern, page_length=1000):
                em.add_field(name=_("__Regex__"), value=box(page, lang="re"))
            if pattern_error:
                em.add_field(name=_("__Error__"), value=pattern_error)
            msg_list.append(em)
        else:
            info += _("Regex: ") + box(pattern[: 2000 - len(info)], lang="re")
        if embeds:
            return em
        else:
            return info
        # return await make_embed_from_submission(view.ctx.channel, self._subreddit, submission)


class ReTriggerSelectOption(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption], placeholder: str):
        self.view: ReTriggerMenu
        super().__init__(min_values=1, max_values=1, options=options, placeholder=placeholder)

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        await self.view.show_checked_page(index, interaction)


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: Union[ReTriggerMenu, BaseMenu]
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
        self.view: Union[ReTriggerMenu, BaseMenu]
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
        self.view: Union[ReTriggerMenu, BaseMenu]
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
        self.view: Union[ReTriggerMenu, BaseMenu]
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
        self.view: Union[ReTriggerMenu, BaseMenu]
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class ToggleTriggerButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: ReTriggerMenu
        super().__init__(style=style, row=row)
        self.style = discord.ButtonStyle.red
        self.emoji = "\N{NEGATIVE SQUARED CROSS MARK}"
        self.label = _("Disable Trigger")

    def modify(self):
        self.style = (
            discord.ButtonStyle.red if self.view.source.enabled else discord.ButtonStyle.green
        )
        self.emoji = (
            "\N{NEGATIVE SQUARED CROSS MARK}"
            if self.view.source.enabled
            else "\N{WHITE HEAVY CHECK MARK}"
        )
        self.label = _("Disable Trigger") if self.view.source.enabled else _("Enable Trigger")

    async def callback(self, interaction: discord.Interaction):
        """Enables and disables triggers"""
        member = interaction.user
        trigger = self.view.source.selection
        guild = self.view.source.guild
        if await self.view.cog.can_enable_or_disable(member, self.view.source.selection):
            trigger.toggle()
            trigger._last_modified_by = member.id
            trigger._last_modified_at = interaction.id
            trigger._last_modified = _("enabled") if trigger.enabled else _("disabled")
            async with self.view.cog.config.guild(guild).trigger_list() as trigger_list:
                trigger_list[trigger.name] = await trigger.to_json()
            await self.view.show_checked_page(self.view.current_page, interaction)
        else:
            await interaction.response.send_message(
                _("You are not authorized to enable or disable this trigger."), ephemeral=True
            )


class ReTriggerEditModal(discord.ui.Modal):
    def __init__(self, trigger: Trigger, button: discord.ui.Button):
        super().__init__(title=f"{trigger.name[:45]}")
        self.text = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, label="Response", default=trigger.text
        )
        self.regex = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, label="Regex", default=trigger._raw_regex
        )
        self.add_item(self.regex)
        reply_options = [
            discord.SelectOption(label=_("Reply with ping"), value="True"),
            discord.SelectOption(label=_("Reply without ping"), value="False"),
            discord.SelectOption(label=_("Don't reply"), value="None"),
        ]
        self.replies = discord.ui.Select(
            max_values=1, min_values=0, placeholder="Replies", options=reply_options
        )
        self.multi_inputs = {}
        text_inputs = ["text", "dm", "dmme", "command", "mock"]
        if not trigger.multi_payload:
            for response_type in trigger.response_type:
                if response_type.value in text_inputs:
                    self.add_item(self.text)
                    break
        else:
            for response_type in trigger.response_type:
                if response_type.name not in text_inputs:
                    continue
                self.multi_inputs[response_type] = discord.ui.TextInput(
                    style=discord.TextStyle.short,
                    label=response_type.name,
                    default="".join(
                        str(i.response) for i in trigger.multi_payload if i.action is response_type
                    ),
                )
            for ti in self.multi_inputs.values():
                try:
                    self.add_item(ti)
                except ValueError:
                    # I really hope there aren't any triggers with this many text responses
                    log.error(
                        "ReTrigger attempted to send a modal edit with more text inputs than expected."
                    )
                    pass

        # if TriggerResponse.text in trigger.response_type:
        # self.add_item(self.replies)
        self.og_button = button
        self.trigger = trigger

    async def handle_multi(self, interaction: discord.Interaction):
        log.debug(self.multi_inputs)
        msg = _("Editing Trigger {trigger}:\n").format(trigger=self.trigger.name)
        guild = interaction.guild
        any_edits = False
        changed_values = []
        if self.trigger._raw_regex != self.regex.value:
            try:
                re.compile(self.regex.value)
            except Exception as e:
                await interaction.response.send_message(
                    _("The provided regex pattern is not valid: {e}").format(e=e), ephemeral=True
                )
                return
            self.trigger._raw_regex = self.regex.value
            self.trigger.compile()
            # we've already checked if the regex was valid
            any_edits = True
            msg += _("- Regex\n")
            changed_values.append("regex")
        for response_type, ti in self.multi_inputs.items():
            old = [i for i in self.trigger.multi_payload if i.action is response_type]
            old_str = "".join(str(i.response) for i in old)
            if ti.value is None:
                continue
            if old_str != ti.value:
                any_edits = True
                log.debug(
                    "Modifying %s on trigger %r old_str=%s new_str=%s",
                    response_type.name,
                    self.trigger,
                    old_str,
                    ti.value,
                )
                for old_payload in old:
                    try:
                        self.trigger.multi_payload.remove(old_payload)
                    except IndexError:
                        log.error("Error removing multi payload option.")
                self.trigger.multi_payload.append(MultiResponse(response_type, ti.value))
                changed_values.append(response_type.name)
                msg += _("- {response_type}").format(response_type=response_type.name)
        if any_edits:
            await interaction.response.send_message(msg)
            self.trigger._last_modified_by = interaction.user.id
            self.trigger._last_modified_at = interaction.id
            self.trigger._last_modified = humanize_list(changed_values)
            async with self.og_button.view.cog.config.guild(guild).trigger_list() as trigger_list:
                trigger_list[self.trigger.name] = await self.trigger.to_json()
        else:
            await interaction.response.send_message(_("None of the values have changed."))
        await self.og_button.view.show_checked_page(self.og_button.view.current_page, interaction)

    async def on_submit(self, interaction: discord.Interaction):
        edited_text = False
        edited_regex = False
        edited_replies = False
        if self.trigger.multi_payload:
            return await self.handle_multi(interaction)
        msg = _("Editing Trigger {trigger}:\n").format(trigger=self.trigger.name)
        guild = interaction.guild
        changed_values = []
        if self.trigger.text != self.text.value:
            self.trigger.text = self.text.value
            edited_text = True
            changed_values.append("text")
            msg += _("Text: `{text}`\n").format(text=self.text.value)
        if self.trigger._raw_regex != self.regex.value:
            try:
                re.compile(self.regex.value)
            except Exception as e:
                await interaction.response.send_message(
                    _("The provided regex pattern is not valid: {e}").format(e=e), ephemeral=True
                )
                return
            self.trigger._raw_regex = self.regex.value
            self.trigger.compile()
            # we've already checked if the regex was valid
            edited_regex = True
            changed_values.append("regex")
            msg += _("Regex: `{regex}`\n").format(regex=self.regex.value)
        if self.replies.values:
            if self.replies.values[0] == "True":
                self.trigger.reply = True
            elif self.replies.values[0] == "False":
                self.trigger.reply = False
            else:
                self.trigger.reply = None
            edited_replies = True
            changed_values.append("replies")
            msg += _("Replies: `{replies}`\n").format(replies=self.replies.values[0])
        if edited_text or edited_regex or edited_replies:
            await interaction.response.send_message(msg)
            self.trigger._last_modified_by = interaction.user.id
            self.trigger._last_modified_at = interaction.id
            self.trigger._last_modified = humanize_list(changed_values)
            async with self.og_button.view.cog.config.guild(guild).trigger_list() as trigger_list:
                trigger_list[self.trigger.name] = await self.trigger.to_json()
        else:
            await interaction.response.send_message(_("None of the values have changed."))
        await self.og_button.view.show_checked_page(self.og_button.view.current_page, interaction)

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        owner_id = interaction.guild.owner.id
        if interaction.user.id not in (
            self.trigger.author,
            owner_id,
            *interaction.client.owner_ids,
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class ReTriggerEditButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: ReTriggerMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{GEAR}\N{VARIATION SELECTOR-16}"
        self.label = _("Edit Trigger")

    async def callback(self, interaction: discord.Interaction):
        trigger = self.view.source.selection
        cog = interaction.client.get_cog("ReTrigger")
        if not await cog.can_edit(interaction.user, trigger):
            await interaction.response.send_message(
                _("You are not authorized to edit this trigger."), ephemeral=True
            )
            return
        modal = ReTriggerEditModal(trigger, self)
        await interaction.response.send_modal(modal)


class DeleteTriggerButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: ReTriggerMenu
        super().__init__(style=style, row=row, label=_("Delete Trigger"))
        self.style = style
        self.emoji = "\N{PUT LITTER IN ITS PLACE SYMBOL}"

    async def keep_trigger(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=_("Okay this trigger will not be deleted."), view=None
        )

    async def delete_trigger(self, interaction: discord.Interaction):
        self.view.source.selection.disable()
        done = await self.view.cog.remove_trigger(
            interaction.guild_id, self.view.source.selection.name
        )
        if done:
            # page = await self.view._source.get_page(self.current_page)
            # kwargs = await self.view._get_kwargs_from_page(page)
            await interaction.response.edit_message(
                content=_("This trigger has been deleted."), view=None
            )
            await self.view.show_page(self.view.current_page, interaction=None)

    async def callback(self, interaction: discord.Interaction):
        """Enables and disables triggers"""
        member = interaction.user
        if (
            await self.view.cog.can_edit(member, self.view.source.selection)
            or member.guild_permissions.administrator
        ):
            new_view = discord.ui.View()
            approve_button = discord.ui.Button(style=discord.ButtonStyle.green, label=_("Yes"))
            approve_button.callback = self.delete_trigger
            deny_button = discord.ui.Button(style=discord.ButtonStyle.red, label=_("No"))
            deny_button.callback = self.keep_trigger
            new_view.add_item(approve_button)
            new_view.add_item(deny_button)
            await interaction.response.send_message(
                _("Are you sure you want to delete trigger {name}?").format(
                    name=self.view.source.selection.name
                ),
                ephemeral=True,
                view=new_view,
            )
        else:
            await interaction.response.send_message(
                _("You are not authorized to delete this trigger."), ephemeral=True
            )
            return


class ReTriggerMenu(discord.ui.View):
    def __init__(
        self,
        source: ReTriggerPages,
        cog: ReTriggerMixin,
        page_start: int = 0,
        timeout: int = 180,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.cog = cog
        self.page_start = page_start
        self.ctx = None
        self.message = None
        self._source = source
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.edit_button = ReTriggerEditButton(discord.ButtonStyle.primary, 1)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.delete_button = DeleteTriggerButton(discord.ButtonStyle.red, 1)
        self.toggle_button = ToggleTriggerButton(discord.ButtonStyle.grey, 1)
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.toggle_button)
        self.add_item(self.delete_button)
        self.add_item(self.edit_button)
        self.current_page = page_start
        self.select_view: ReTriggerSelectOption
        self.author = None

    @property
    def source(self) -> ReTriggerPages:
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx)

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.author = ctx.author
        if self.ctx is None:
            self.ctx = ctx

        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        self.toggle_button.modify()
        if len(self.source.active_triggers) < 2:
            self.forward_button.disabled = True
            self.back_button.disabled = True
            self.first_item.disabled = True
            self.last_item.disabled = True
        else:
            options = self.source.select_options[:25]
            if len(self.source.select_options) > 25 and self.current_page > 12:
                options = self.source.select_options[
                    self.current_page - 12 : self.current_page + 13
                ]
            self.select_view = ReTriggerSelectOption(
                options=options, placeholder=_("Pick a Trigger")
            )
            self.add_item(self.select_view)
        self.message = await ctx.send(
            **kwargs, allowed_mentions=discord.AllowedMentions(users=False, roles=False), view=self
        )
        return self.message

    async def _update_buttons(self):
        trigger = self.source.selection
        guild = self.source.guild
        if trigger.name not in self.cog.triggers[guild.id]:
            self.delete_button.disabled = True
            self.edit_button.disabled = True
            self.toggle_button.disabled = True
        else:
            self.delete_button.disabled = False
            self.edit_button.disabled = False
            self.toggle_button.disabled = False

    async def _get_kwargs_from_page(self, page: int):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        await self._update_buttons()
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embeds": None}
        elif isinstance(value, discord.Embed):
            return {"embeds": [value], "content": None}

    async def show_page(self, page_number: int, interaction: Optional[discord.Interaction]):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self.toggle_button.modify()
        if len(self.source.active_triggers) < 2:
            self.forward_button.disabled = True
            self.back_button.disabled = True
            self.first_item.disabled = True
            self.last_item.disabled = True
        else:
            self.remove_item(self.select_view)
            options = self.source.select_options[:25]
            if len(self.source.select_options) > 25 and page_number > 12:
                options = self.source.select_options[page_number - 12 : page_number + 13]
            self.select_view = ReTriggerSelectOption(
                options=options, placeholder=_("Pick a Trigger")
            )
            self.add_item(self.select_view)
        # await self.message.edit(**kwargs, view=self)
        if interaction is None:
            await self.message.edit(**kwargs, view=self)
            return
        if interaction.response.is_done() and self.message is not None:
            await interaction.followup.edit_message(self.message.id, **kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

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
        if self.author and interaction.user.id not in (
            self.author.id,
            *interaction.client.owner_ids,
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


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
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.select_view = ReTriggerSelectOption(
            options=self.source.select_options, placeholder=_("Pick a page")
        )
        self.add_item(self.select_view)

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

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
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
