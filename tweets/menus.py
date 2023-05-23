from __future__ import annotations

import asyncio
from typing import Any, List, Optional

import discord
import tweepy
from red_commons.logging import getLogger

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.vendored.discord.ext import menus

from .tweets_api import EXPANSIONS, MEDIA_FIELDS, TWEET_FIELDS, USER_FIELDS

log = getLogger("red.Trusty-cogs.tweets")
_ = Translator("Tweets", __file__)


class NoTweets(Exception):
    pass


class TweetListPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        em = page
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class TweetPages(menus.PageSource):
    def __init__(self, **kwargs):
        self._page: int = 1
        self._index: int = 0
        self._cache: List[tweepy.Tweet] = []
        self._checks: int = 0
        self._last_page: int = 0
        self._api: tweepy.asynchronous.AsyncClient = kwargs.get("api")
        self._username: str = kwargs.get("username")
        self._last_searched: str = ""
        self._user = None
        self._next_page_token: Optional[str] = None
        self._previous_page_token: Optional[str] = None
        self._includes = None
        self._meta = None
        self._errors = None
        self._data = None

    @property
    def index(self) -> int:
        return self._index

    @property
    def last_page(self) -> int:
        return self._last_page

    async def get_page(
        self, page_number, *, skip_next: bool = False, skip_prev: bool = False
    ) -> dict:
        # log.info(f"Cache size is {len(self._cache)}")

        if page_number < self.last_page:
            page = await self.prev()
        if page_number > self.last_page:
            page = await self.next()
        if page_number == self.last_page and self._cache:
            page = self._cache[page_number]
        if skip_next:
            page = await self.next(True)
        if skip_prev:
            page = await self.prev(True)
        if not self._cache:
            raise NoTweets()
        # log.info(page)
        self._last_page = page_number
        return page

    async def next(self, skip: bool = False) -> dict:
        """
        Returns the next element from the list

        If all elements have been traversed attempt to pull new data

        If no new data can be found within a reasonable number of calls stop
        """
        self._index += 1
        if self._index > (len(self._cache) - 1) or skip:
            try:
                await self._next_batch(_next=True)
            except Exception:
                # log.debug("Error getting schedule")
                raise
            self._index = 0
        # log.info(f"getting next data {len(self._cache)}")
        return self._cache[self.index]

    async def prev(self, skip: bool = False) -> dict:
        """
        Returns the previous element from the list

        If all elements have been traversed pull new data

        If no new data can be found within a reasonable number of calls stop
        (this one is expected to have more time between calls)
        I wonder if I should traverse weekly instead of daily :blobthink:
        """
        self._index -= 1
        if self._index < 0 or skip:
            # Grab new list from previous day
            try:
                new_data = await self._next_batch(_prev=True)
                self._index = len(new_data) - 1
            except Exception:
                # log.debug("Error getting schedule")
                self._index = 0
                raise
        return self._cache[self.index]

    async def prepare(self) -> None:
        try:
            await self._next_batch()
        except Exception:
            pass

    def is_paginating(self) -> bool:
        return True

    async def _get_twitter_statuses(
        self,
        pagination_token: Optional[str] = None,
    ) -> List[tweepy.Status]:
        msg_list = []
        if self._user is None:
            log.info("Getting user ID for %s", self._username)
            resp = await self._api.get_user(username=self._username)
            self._user = resp.data
            log.info("_get_twitter_statuses user: %s", self._user)
        try:
            log.info("Getting tweets for %s", self._user.id)
            kwargs = {
                "id": self._user.id,
                "tweet_fields": TWEET_FIELDS,
                "user_fields": USER_FIELDS,
                "media_fields": MEDIA_FIELDS,
                "expansions": EXPANSIONS,
            }
            if pagination_token is not None:
                kwargs["pagination_token"] = pagination_token
            resp = await self._api.get_users_tweets(**kwargs)
            self._next_page_token = resp.meta.get("next_token", None)
            self._previous_page_token = resp.meta.get("previous_token", None)
            self._includes = resp.includes
            self._meta = resp.meta
            self._errors = resp.errors
            self._data = resp.data
            msg_list = resp.data

        except tweepy.TweepError:
            log.exception("Error pulling tweets")
            raise
        except Exception:
            log.exception("Some other error is happening")

        return msg_list

    async def _next_batch(
        self,
        *,
        _next: bool = False,
        _prev: bool = False,
    ) -> List[tweepy.Status]:
        """
        Actually grab the list of games.
        """
        # compare_date = datetime.utcnow().strftime("%Y-%m-%d")
        log.debug("Pulling tweets into the cache")
        token = None
        if _next:
            token = self._next_page_token
        elif _prev:
            token = self._previous_page_token
        try:
            msg_list = await self._get_twitter_statuses(pagination_token=token)
            # log.debug(next(self._listing))
        except asyncio.TimeoutError:
            log.error("Timeout error pulling tweet statuses")
        except tweepy.TweepError:
            log.error("Error pulling twitter info")

        self._cache = msg_list
        # return the games as a form of metadata about how the cache is changing
        return msg_list

    async def format_page(self, menu: menus.MenuPages, tweet: tweepy.Tweet):
        resp = tweepy.Response(
            data=tweet, includes=self._includes, errors=self._errors, meta=self._meta
        )
        return await menu.cog.build_tweet_embed(resp)

    def _get_reply(self, ids: List[int]) -> tweepy.Status:
        return self._api.lookup_statuses(ids)


class TweetStreamView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        self.cog = cog
        super().__init__(timeout=None)
        self.add_item(LikeButton())
        self.add_item(ReTweetButton())
        self.add_item(ReplyButton())


class LikeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            custom_id="Trusty-cogs-tweets-likebutton",
            style=discord.ButtonStyle.grey,
            emoji="\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.view.cog.authorize_user(interaction=interaction):
            return
        api = await self.view.cog.authenticate(interaction.user)
        tweet_id = interaction.message.content.split("/")[-1]
        await api.like(tweet_id, user_auth=False)
        await interaction.response.send_message(_("You liked the tweet!"), ephemeral=True)


class ReTweetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            custom_id="Trusty-cogs-tweets-retweetbutton",
            style=discord.ButtonStyle.grey,
            emoji="\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.view.cog.authorize_user(interaction=interaction):
            return
        api = await self.view.cog.authenticate(interaction.user)
        tweet_id = interaction.message.content.split("/")[-1]
        await api.retweet(tweet_id, user_auth=False)
        await interaction.response.send_message(_("You retweeted the tweet!"), ephemeral=True)


class ReplyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            custom_id="Trusty-cogs-tweets-replybutton",
            style=discord.ButtonStyle.grey,
            emoji="\N{SPEECH BALLOON}",
        )

    async def callback(self, interaction: discord.Interaction):
        tweet_id = interaction.message.content.split("/")[-1]
        modal = ReplyModal(view=self.view, tweet_id=tweet_id)
        await interaction.response.send_modal(modal)


class ReplyModal(discord.ui.Modal):
    def __init__(self, view: discord.ui.View, tweet_id: int):
        super().__init__(title=_("Reply to tweet"))
        self.view = view
        self.tweet_id = tweet_id
        self.reply = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            label=_("Reply"),
            placeholder=_("Add another Tweet"),
            max_length=280,
            min_length=1,
        )
        self.add_item(self.reply)
        reply_options = [
            discord.SelectOption(label=_("Following"), value="following"),
            discord.SelectOption(label=_("Everyone"), value="None"),
        ]
        self.reply_settings = discord.ui.Select(
            max_values=1, min_values=0, placeholder=_("Reply settings"), options=reply_options
        )
        # self.add_item(self.reply_settings)

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.view.cog.authorize_user(interaction=interaction):
            return
        api = await self.view.cog.authenticate(interaction.user)
        reply_setting = None
        # if self.reply_settings.values[0] != "None":
        # reply_setting = self.reply_settings.values[0]
        await api.create_tweet(
            text=self.reply.value,
            in_reply_to_tweet_id=self.tweet_id,
            reply_settings=reply_setting,
            user_auth=False,
        )
        await interaction.response.send_message(_("Tweet sent!"))


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
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page + 1, interaction=interaction)


class BackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page - 1, interaction=interaction)


class LastItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction=interaction)


class FirstItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction=interaction)


class SkipForwardkButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, skip_next=True, interaction=interaction)


class SkipBackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, skip_prev=True, interaction=interaction)


class TweetsMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
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
        self.page_start = page_start
        self.ctx = None
        self.message = None
        self._source = source
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = SkipBackButton(discord.ButtonStyle.grey, 0)
        self.last_item = SkipForwardkButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.like_button = LikeButton()
        self.retweet_button = ReTweetButton()
        self.reply_button = ReplyButton()
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.like_button)
        self.add_item(self.retweet_button)
        self.add_item(self.reply_button)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ):
        log.exception(error)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        await self._source.prepare()
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
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
        self.current_page = self.page_start
        try:
            page = await self._source.get_page(self.page_start)
        except NoTweets:
            log.exception("No tweets found")
            await ctx.send(_("No twitter account with that username could be found."))
            return
        kwargs = await self._get_kwargs_from_page(page)
        nsfw = kwargs.pop("nsfw", False)
        if ctx.guild is not None:
            if nsfw and not ctx.channel.is_nsfw():
                return await ctx.send(
                    _("This tweet is labeled as NSFW and this is not a NSFW channel."), view=self
                )
        return await ctx.send(**kwargs, view=self)

    async def show_page(
        self,
        page_number: int,
        *,
        skip_next: bool = False,
        skip_prev: bool = False,
        interaction: discord.Interaction,
    ) -> None:
        if skip_next or skip_prev:
            await interaction.response.defer()
        try:
            page = await self._source.get_page(
                page_number, skip_next=skip_next, skip_prev=skip_prev
            )
        except NoTweets:
            msg = _("No twitter information could be found for {username}.").format(
                username=self.source._username
            )
            await self.message.edit(content=msg, embed=None)
            return
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        kwargs["view"] = self
        nsfw = kwargs.pop("nsfw", False)
        if self.ctx.guild is not None:
            if nsfw and not self.ctx.channel.is_nsfw():
                kwargs["content"] = _(
                    "This tweet is labeled as NSFW and this is not a NSFW channel."
                )
                kwargs["embeds"] = []
        if interaction.response.is_done():
            if self.message is not None:
                await self.message.edit(**kwargs)
            else:
                await interaction.edit_original_response(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        try:
            await self.show_page(page_number, interaction=interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self._source = source
        self.ctx: commands.Context = None
        self.message: discord.Message = None
        self.page_start = page_start
        self.current_page = page_start
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

    @property
    def source(self):
        return self._source

    async def start(self, ctx: commands.Context):
        await self.source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs, view=self)

    async def send_initial_message(self, ctx: commands.Context) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        return await ctx.send(**kwargs, view=self)

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
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
