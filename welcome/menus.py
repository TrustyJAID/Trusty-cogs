from __future__ import annotations

import re
from enum import Enum
from typing import Any, List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, escape
from redbot.vendored.discord.ext import menus

IMAGE_LINKS = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|png|webp))")


class EventType(Enum):
    greeting = 0
    goodbye = 1

    def get_name(self):
        return {EventType.greeting: _("greeting"), EventType.goodbye: _("goodbye")}.get(self)

    def __str__(self):
        return self.get_name()

    def key(self):
        return self.name.upper()


log = getLogger("red.Trusty-cogs.welcome")
_ = Translator("Welcome", __file__)


class WelcomePages(menus.ListPageSource):
    def __init__(self, pages: List[str]):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.select_options = []
        for count, page in enumerate(pages):
            self.select_options.append(discord.SelectOption(label=f"Page {count+1}", value=count))
        self.current_page = None
        self.current_selection = None

    def is_paginating(self):
        return True

    async def format_page(self, view: BaseMenu, page: str):
        self.current_page = view.current_page
        config = view.cog.config
        msgs = await config.guild(view.ctx.guild).get_raw(view.event_type.key())
        try:
            raw_text = msgs[self.current_page]
            view.enable_extra_buttons()
        except IndexError:
            raw_text = _("Deleted Greeting")
            view.disable_extra_buttons()
        self.current_selection = raw_text
        if view.show_preview:
            is_welcome = view.event_type is EventType.greeting
            grouped = await config.guild(view.ctx.guild).GROUPED()
            members = view.ctx.author if not grouped else [view.ctx.author, view.ctx.me]
            if await config.guild(view.ctx.guild).EMBED():
                return await view.cog.make_embed(members, view.ctx.guild, raw_text, is_welcome)
            else:
                return await view.cog.convert_parms(members, view.ctx.guild, raw_text, is_welcome)
        display_text = raw_text
        if view.show_raw:
            display_text = escape(display_text, formatting=True)
            display_text = re.sub(r"(<@?[!&#]?[0-9]{17,20}>)", r"\\\1", display_text)
        if view.ctx.channel.permissions_for(view.ctx.guild.me).embed_links:
            em = discord.Embed(
                title=_("{event_type} message {count}").format(
                    event_type=view.event_type.get_name().title(), count=view.current_page + 1
                ),
                description=display_text,
                colour=await view.cog.bot.get_embed_colour(view.ctx.channel),
            )
            em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
            return em
        return display_text


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        await self.view.message.delete()


class _NavigateButton(discord.ui.Button):
    # Borrowed from myself mainly
    # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/utils/views.py#L44
    def __init__(
        self, style: discord.ButtonStyle, emoji: Union[str, discord.PartialEmoji], direction: int
    ):
        super().__init__(style=style, emoji=emoji)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        if self.direction == 0:
            self.view.current_page = 0
        elif self.direction == self.view.source.get_max_pages():
            self.view.current_page = self.view.source.get_max_pages() - 1
        else:
            self.view.current_page += self.direction
        await self.view.show_checked_page(self.view.current_page, interaction)


class ToggleButton(discord.ui.Button):
    def __init__(self, attr_toggle: str, style: discord.ButtonStyle, label: str):
        super().__init__(style=style, label=label)
        self.attr_toggle = attr_toggle

    async def callback(self, interaction: discord.Interaction):
        current = getattr(self.view, self.attr_toggle)
        self.style = discord.ButtonStyle.blurple if not current else discord.ButtonStyle.grey
        setattr(self.view, self.attr_toggle, not current)
        await self.view.show_checked_page(self.view.current_page, interaction)


class WelcomeEditModal(discord.ui.Modal):
    def __init__(
        self, welcome_message: str, index: int, button: discord.ui.Button, event_type: EventType
    ):
        super().__init__(
            title=_("Edit {event_type} {count}").format(
                event_type=event_type.get_name(), count=index
            )
        )
        self.text = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            label=_("{style} text").format(style=event_type.get_name().title()),
            default=welcome_message,
            max_length=2000,
        )
        self.add_item(self.text)
        self.og_button = button
        self.index = index
        self.original_welcome = welcome_message
        self.event_type = event_type

    async def on_submit(self, interaction: discord.Interaction):
        edited_text = False
        guild = interaction.guild
        config = self.og_button.view.cog.config
        if self.original_welcome != self.text.value:
            self.original_welcome = self.text.value
            edited_text = True
            try:
                settings = await config.guild(guild).get_raw(self.event_type.key())
                settings[self.index] = self.text.value
                await config.guild(guild).set_raw(self.event_type.key(), value=settings)
            except IndexError:
                await interaction.response.send_message(
                    _("There was an error editing this {event_type} message.").format(
                        event_type=self.event_type.get_name()
                    )
                )

        if edited_text:
            await interaction.response.send_message(
                _("I have edited {style} {number}.").format(
                    style=self.event_type.get_name(), number=self.index + 1
                )
            )
        else:
            await interaction.response.send_message(_("None of the values have changed."))
        await self.og_button.view.show_checked_page(self.og_button.view.current_page, interaction)

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        owner_id = interaction.guild.owner.id
        if interaction.user.id not in (
            owner_id,
            *interaction.client.owner_ids,
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class EmbedEditModal(discord.ui.Modal):
    def __init__(self, embed_settings: dict, button: discord.ui.Button, event_type: EventType):
        super().__init__(title=_("Edit Embed Settings"))
        self.old_settings = embed_settings
        self.event_type = event_type
        self.embed_title = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=_("Embed Title"),
            default=embed_settings["title"],
            max_length=256,
            placeholder="The title of the embed",
            required=False,
        )
        self.embed_footer = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=_("Embed Footer"),
            default=embed_settings["footer"],
            max_length=256,
            placeholder="The footer of the embed",
            required=False,
        )
        self.embed_thumbnail = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=_("Embed Thumbnail"),
            default=embed_settings["thumbnail"],
            max_length=256,
            placeholder="guild, splash, avatar, or a custom url",
            required=False,
        )
        self.embed_image = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=_("Embed Image"),
            default=embed_settings["image"]
            if self.event_type is EventType.greeting
            else embed_settings["image_goodbye"],
            max_length=256,
            placeholder="guild, splash, avatar, or a custom url",
            required=False,
        )
        self.embed_icon_url = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=_("Embed Icon URL"),
            default=embed_settings["icon_url"],
            max_length=256,
            placeholder="guild, splash, avatar, or a custom url",
            required=False,
        )
        self.add_item(self.embed_title)
        self.add_item(self.embed_footer)
        self.add_item(self.embed_thumbnail)
        self.add_item(self.embed_image)
        self.add_item(self.embed_icon_url)
        self.og_button = button

    async def on_submit(self, interaction: discord.Interaction):
        items = {
            "title": self.embed_title,
            "footer": self.embed_footer,
            "thumbnail": self.embed_thumbnail,
            # "image": self.embed_image,
            "icon_url": self.embed_icon_url,
        }
        if self.event_type is EventType.greeting:
            items["image"] = self.embed_image
        else:
            items["image_goodbye"] = self.embed_image
        changes = set()
        config = self.og_button.view.cog.config
        invalid = set()
        for key, item in items.items():
            if self.old_settings[key] != item.value:
                if key in ("title", "footer"):
                    changes.add(key)
                    await config.guild(interaction.guild).EMBED_DATA.set_raw(key, value=item.value)
                else:
                    if item.value in ("guild", "splash", "avatar", ""):
                        set_to = item.value
                        if not item.value:
                            set_to = None
                        if set_to != self.old_settings[key]:
                            changes.add(key)
                            await config.guild(interaction.guild).EMBED_DATA.set_raw(
                                key, value=set_to
                            )
                    else:
                        search = IMAGE_LINKS.search(item.value)
                        if not search:
                            invalid.add(
                                _(
                                    "`{key}` must contain guild, splash, avatar, or a valid image URL."
                                ).format(key=key)
                            )

        if not changes:
            await interaction.response.send_message(
                _("None of the values have changed.\n") + "\n".join(f"- {i}" for i in invalid)
            )
        else:
            changes_str = "\n".join(f"- {i}" for i in changes)
            await interaction.response.send_message(
                _("I have edited the following embed settings:\n{changes}").format(
                    changes=changes_str
                )
            )
        await self.og_button.view.show_checked_page(self.og_button.view.current_page, interaction)

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        owner_id = interaction.guild.owner.id
        if interaction.user.id not in (
            owner_id,
            *interaction.client.owner_ids,
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class WelcomeEditButton(discord.ui.Button):
    def __init__(
        self,
        event_type: EventType,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{GEAR}\N{VARIATION SELECTOR-16}"
        self.label = _("Edit {event_type}").format(event_type=event_type.get_name().title())
        self.event_type = event_type

    async def callback(self, interaction: discord.Interaction):
        modal = WelcomeEditModal(
            self.view.source.current_selection,
            self.view.source.current_page,
            self,
            self.event_type,
        )
        await interaction.response.send_modal(modal)


class EmbedEditButton(discord.ui.Button):
    def __init__(
        self,
        event_type: EventType,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{GEAR}\N{VARIATION SELECTOR-16}"
        self.label = _("Edit Embed Settings")
        self.event_type = event_type

    async def callback(self, interaction: discord.Interaction):
        settings = await self.view.cog.config.guild(interaction.guild).EMBED_DATA()
        modal = EmbedEditModal(settings, self, self.event_type)
        await interaction.response.send_modal(modal)


class DeleteWelcomeButton(discord.ui.Button):
    def __init__(
        self,
        event_type: EventType,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.event_type = event_type
        super().__init__(
            style=style,
            row=row,
            label=_("Delete {event_type}").format(event_type=event_type.get_name().title()),
        )
        self.style = style
        self.emoji = "\N{PUT LITTER IN ITS PLACE SYMBOL}"

    async def keep_trigger(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=_("Okay this {event_type} will not be deleted.").format(
                event_type=self.event_type.get_name()
            ),
            view=None,
        )

    async def delete_trigger(self, interaction: discord.Interaction):
        config = self.view.cog.config
        guild = interaction.guild
        settings = await config.guild(guild).get_raw(self.event_type.key())
        settings.pop(self.view.source.current_page)
        await config.guild(guild).set_raw(self.event_type.key(), value=settings)
        await interaction.response.edit_message(
            content=_("This {event_type} has been deleted.").format(
                event_type=self.event_type.get_name()
            ),
            view=None,
        )
        self.view.disable_extra_buttons()
        await self.view.show_checked_page(self.view.current_page, interaction=None)

    async def callback(self, interaction: discord.Interaction):
        """Enables and disables triggers"""
        new_view = discord.ui.View()
        approve_button = discord.ui.Button(style=discord.ButtonStyle.green, label=_("Yes"))
        approve_button.callback = self.delete_trigger
        deny_button = discord.ui.Button(style=discord.ButtonStyle.red, label=_("No"))
        deny_button.callback = self.keep_trigger
        new_view.add_item(approve_button)
        new_view.add_item(deny_button)
        await interaction.response.send_message(
            _("Are you sure you want to delete {event_type} {name}?").format(
                event_type=self.event_type.get_name(), name=self.view.source.current_page + 1
            ),
            ephemeral=True,
            view=new_view,
        )
        if not interaction.response.is_done():
            await interaction.response.defer()


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        *,
        message: Optional[discord.Message] = None,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        raw: bool = False,
        event_type: EventType = EventType.greeting,
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
        self.event_type = event_type
        self.current_page = kwargs.get("page_start", 0)
        self.forward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=1,
        )
        self.backward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=-1,
        )
        self.first_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=0,
        )
        self.last_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=self.source.get_max_pages(),
        )
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.stop_button)
        self.add_item(self.first_button)
        self.add_item(self.backward_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_button)

        self.delete_after = delete_message_after
        self.clear_after = clear_reactions_after
        self.show_raw = raw
        self.raw_button = ToggleButton(
            "show_raw",
            discord.ButtonStyle.blurple if raw else discord.ButtonStyle.grey,
            _("Show Raw"),
        )
        self.add_item(self.raw_button)
        self.preview_button = ToggleButton(
            "show_preview",
            discord.ButtonStyle.grey,
            _("Show Preview"),
        )
        self.add_item(self.preview_button)
        self.edit_button = WelcomeEditButton(self.event_type, discord.ButtonStyle.grey, 2)
        self.edit_embed_button = EmbedEditButton(self.event_type, discord.ButtonStyle.grey, 2)
        self.add_item(self.edit_button)
        self.add_item(self.edit_embed_button)
        self.delete_button = DeleteWelcomeButton(self.event_type, discord.ButtonStyle.red, 2)
        self.add_item(self.delete_button)
        self.show_preview = False

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        if self.message is None:
            return
        if self.clear_after and not self.delete_after:
            await self.message.edit(view=None)
        elif self.delete_after:
            await self.message.delete()

    def disable_extra_buttons(self):
        self.raw_button.disabled = True
        self.preview_button.disabled = True
        self.edit_button.disabled = True
        self.edit_embed_button.disabled = True
        self.delete_button.disabled = True

    def enable_extra_buttons(self):
        self.raw_button.disabled = False
        self.preview_button.disabled = False
        self.edit_button.disabled = False
        self.edit_embed_button.disabled = False
        self.delete_button.disabled = False

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.bot = self.cog.bot
        # await self.source._prepare_once()
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self, page: int):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if self.event_type is EventType.greeting:
            mentions = await self.cog.config.guild(self.ctx.guild).MENTIONS()
        else:
            mentions = await self.cog.config.guild(self.ctx.guild).GOODBYE_MENTIONS()
        allowed_mentions = discord.AllowedMentions(**mentions)
        if isinstance(value, dict):
            value.update({"allowed_mentions": discord.AllowedMentions(**mentions)})
            return value
        elif isinstance(value, str):
            return {"content": value, "embeds": [], "allowed_mentions": allowed_mentions}
        elif isinstance(value, discord.Embed):
            return {"embeds": [value], "content": None, "allowed_mentions": allowed_mentions}

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

    async def show_page(self, page_number: int, interaction: Optional[discord.Interaction]):
        page = await self._source.get_page(page_number)
        self.current_page = self.source.pages.index(page)
        kwargs = await self._get_kwargs_from_page(page)

        if interaction is None or interaction.response.is_done():
            await self.message.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)
        # await self.message.edit(**kwargs)

    async def show_checked_page(
        self, page_number: int, interaction: Optional[discord.Interaction]
    ) -> None:
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
