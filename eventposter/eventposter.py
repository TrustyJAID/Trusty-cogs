import asyncio
import logging
from typing import Literal, Optional, Union, Dict, Tuple

import discord
from discord.ext import tasks

from redbot import VersionInfo, version_info
from redbot.core import Config, VersionInfo, checks, commands, version_info
from redbot.core.utils.chat_formatting import pagify, humanize_timedelta, humanize_list
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from redbot.core.i18n import Translator, cog_i18n

from .event_obj import Event, ValidImage

log = logging.getLogger("red.trusty-cogs.EventPoster")

_ = Translator("EventPoster", __file__)

EVENT_EMOJIS = [
    "\N{WHITE HEAVY CHECK MARK}",
    "\N{NEGATIVE SQUARED CROSS MARK}",
    "\N{WHITE QUESTION MARK ORNAMENT}",
]


@cog_i18n(_)
class EventPoster(commands.Cog):
    """Create admin approved events/announcements"""

    __version__ = "2.0.3"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=144014746356678656)
        default_guild = {
            "approval_channel": None,
            "announcement_channel": None,
            "ping": "",
            "events": {},
            "custom_links": {},
            "default_max": None,
            "cleanup_seconds": None,
            "bypass_admin": False,
            "max_events": None,
            "required_roles": [],
        }
        default_user = {"player_class": ""}
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_user)
        self.event_cache: Dict[int, Dict[int, Event]] = {}
        self._ready: asyncio.Event = asyncio.Event()
        self.bot.loop.create_task(self.initialize())
        self.cleanup_old_events.start()

    def format_help_for_context(self, ctx: commands.Context):
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    def cog_unload(self):
        self.cleanup_old_events.cancel()

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if str(user_id) in data["events"]:
                if data["events"][str(user_id)]["message"] in self.event_cache[guild_id]:
                    event = data["events"][str(user_id)]["message"]
                    del self.event_cache[guild_id][event]
                del data["events"][str(user_id)]
                await self.config.guild_from_id(guild_id).events.set(data["events"])
        all_members = await self.config.all_members()
        for guild_id, members in all_members.items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()

    @tasks.loop(seconds=60)
    async def cleanup_old_events(self):
        for guild_id, events in self.event_cache.items():
            cleanup_seconds = await self.config.guild_from_id(guild_id).cleanup_seconds()
            to_remove = []
            if not cleanup_seconds:
                continue
            for message_id, event in events.items():
                if event.should_remove(cleanup_seconds):
                    to_remove.append(message_id)
                    log.debug(f"Removing {event} due to age.")
            for msg_id in to_remove:
                ctx = await events[msg_id].get_ctx(self.bot)
                if ctx:
                    await events[msg_id].edit(ctx, content=_("This event has ended."))

                async with self.config.guild_from_id(guild_id).events() as guild_events:
                    del guild_events[str(events[msg_id].hoster)]
                    log.debug("deleted from config")
                del events[msg_id]
                log.debug("deleted from cache")
        log.debug("Finished checking events to cleanup")

    @cleanup_old_events.before_loop
    async def before_cleanup_old_events(self):
        log.debug("Waiting for cog to finish setting up.")
        await self.bot.wait_until_red_ready()
        await self._ready.wait()
        # Finish loading all the events to memory first before checking

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        try:
            for guild_id in await self.config.all_guilds():
                if guild_id not in self.event_cache:
                    self.event_cache[guild_id] = {}
                data = await self.config.guild_from_id(int(guild_id)).events()
                seconds = await self.config.guild_from_id(int(guild_id)).cleanup_seconds()
                for user_id, event_data in data.items():
                    try:
                        event = Event.from_json(self.bot, event_data)
                    except (TypeError, KeyError, discord.errors.Forbidden):
                        log.exception("Error loading events")
                        continue
                    if event is None:
                        continue
                    if seconds is not None and event.should_remove(seconds):
                        continue
                    self.event_cache[guild_id][event.message] = event
        except Exception:
            log.exception("Error loading events")
        self._ready.set()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Checks for reactions to the event
        """
        if str(payload.emoji) not in EVENT_EMOJIS:
            # log.debug("Not a valid yes or no emoji")
            return
        if payload.guild_id not in self.event_cache:
            return
        if payload.message_id not in self.event_cache[payload.guild_id]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if user.bot:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        event = self.event_cache[payload.guild_id][payload.message_id]
        if str(payload.emoji) == "\N{WHITE HEAVY CHECK MARK}":
            await self.add_user_to_event(user, event)
        if str(payload.emoji) == "\N{WHITE QUESTION MARK ORNAMENT}":
            await self.add_user_to_maybe(user, event)
        if str(payload.emoji) == "\N{NEGATIVE SQUARED CROSS MARK}":
            if user.id == event.hoster:

                async with self.config.guild(guild).events() as events:
                    event = Event.from_json(self.bot, events[str(user.id)])
                    ctx = await event.get_ctx(self.bot)
                    if ctx:
                        await event.edit(ctx, content=_("This event has ended."))
                    del events[str(user.id)]
                    del self.event_cache[guild.id][event.message]
                return
            await self.remove_user_from_event(user, event)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Checks for reactions to the event
        """
        if str(payload.emoji) not in EVENT_EMOJIS:
            # log.debug("Not a valid yes or no emoji")
            return
        if payload.guild_id not in self.event_cache:
            return
        if payload.message_id not in self.event_cache[payload.guild_id]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if user.bot:
            return
        event = self.event_cache[payload.guild_id][payload.message_id]
        if str(payload.emoji) == "\N{WHITE HEAVY CHECK MARK}":
            if user.id == event.hoster:
                return
            if user.id not in event.maybe:
                await self.remove_user_from_event(user, event)
        if str(payload.emoji) == "\N{WHITE QUESTION MARK ORNAMENT}":
            if user.id == event.hoster:
                return
            if user.id not in event.members:
                await self.remove_user_from_event(user, event)

    async def add_user_to_event(self, user: discord.Member, event: Event) -> None:
        if user.id in event.members:
            return
        if event.max_slots and len(event.members) >= event.max_slots:
            return
        event.members.append(user.id)
        if user.id in event.maybe:
            event.maybe.remove(user.id)
        ctx = await event.get_ctx(self.bot)
        if not ctx:
            return
        em = await event.make_event_embed(ctx)
        await event.edit(ctx, embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster)] = event.to_json()
        self.event_cache[ctx.guild.id][event.message] = event
        return

    async def add_user_to_maybe(self, user: discord.Member, event: Event) -> None:
        if user.id in event.maybe:
            return
        event.maybe.append(user.id)
        if user.id in event.members:
            event.members.remove(user.id)
        ctx = await event.get_ctx(self.bot)
        if not ctx:
            return
        em = await event.make_event_embed(ctx)
        await event.edit(ctx, embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster)] = event.to_json()
        self.event_cache[ctx.guild.id][event.message] = event
        return

    async def remove_user_from_event(self, user: discord.Member, event: Event) -> None:

        ctx = await event.get_ctx(self.bot)
        if not ctx:
            return
        if user.id in event.members:
            event.members.remove(user.id)
            em = await event.make_event_embed(ctx)
            await event.edit(ctx, embed=em)
            async with self.config.guild(ctx.guild).events() as cur_events:
                cur_events[str(event.hoster)] = event.to_json()
            self.event_cache[ctx.guild.id][event.message] = event
        if user.id in event.maybe:
            event.maybe.remove(user.id)
            em = await event.make_event_embed(ctx)
            await event.edit(ctx, embed=em)
            async with self.config.guild(ctx.guild).events() as cur_events:
                cur_events[str(event.hoster)] = event.to_json()
            self.event_cache[ctx.guild.id][event.message] = event

    @commands.command(name="eventping", aliases=["eventmention"])
    @commands.guild_only()
    async def event_ping(
        self,
        ctx: commands.Context,
        include_maybe: Optional[bool] = True,
        *,
        message: Optional[str] = None,
    ) -> None:
        """
        Ping all the registered users for your event including optional message

        `[include_maybe=True]` either `true` or `false` to include people who registered as maybe.
        `[message]` Optional message to include with the ping.
        """
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event running with people to ping."))
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(ctx.author.id)])
        msg = event.mention(include_maybe) + ":\n" + message
        for page in pagify(msg):
            await ctx.send(page, allowed_mentions=discord.AllowedMentions(users=True))
            # include AllowedMentions here just incase someone has user mentions disabled
            # since this is intended to ping the users.

    async def check_requirements(self, ctx: commands.Context) -> bool:
        max_events = await self.config.guild(ctx.guild).max_events()
        if (
            max_events is not None
            and ctx.guild.id in self.event_cache
            and len(self.event_cache[ctx.guild.id]) >= max_events
        ):
            await ctx.send(
                _(
                    "The maximum number of events are already posted. Please wait until one finishes."
                )
            )
            return False
        required_roles = [
            ctx.guild.get_role(r) for r in await self.config.guild(ctx.guild).required_roles()
        ]
        allowed = True
        if required_roles:
            allowed = False
            for role in required_roles:
                if role is None:
                    continue
                if role in ctx.author.roles:
                    allowed = True
        if not allowed:
            await ctx.send(_("You do not have one of the required roles to create events."))
        return allowed

    @commands.command(name="event")
    @commands.guild_only()
    async def make_event(
        self,
        ctx: commands.Context,
        members: commands.Greedy[discord.Member],
        max_slots: Optional[int] = None,
        *,
        description: str,
    ) -> None:
        """
        Create an event

        `[members...]` Add members already in the event you want to host.
        `[max_slots=None]` Specify maximum number of Slots the event can have, default is no limit.
        `<description>` provide a description for the event you're hosting.
        With custom keyword links setup this will add an image to the events thumbnail
        after being approved by an admin.

        If a date or time is provided the timestamp in the event will try to display
        the correct time for everyone. For example `[p]event Deep Stone Crypt Sunday at 9PM MDT`
        will convert the "sunday at 9PM MDT" into a converted timestamp for everyone removing
        the need to know what MDT is in their own time.
        This also works for times relative to now, e.g. `[p]event Last Wish in 3 hours`
        will add the timestamp display in 3 hours from the time this message is posted.

        Note: If a timezone is provided it must be the correct timezone according to
        daylight savings time. For example PST time may sometimes be UTC+8 in which case
        PDT must be used instead.
        """
        if not await self.check_requirements(ctx):
            return
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) in await self.config.guild(ctx.guild).events():
            if not await self.check_clear_event(ctx):
                return
            else:
                to_del = 0
                for message_id, event in self.event_cache[ctx.guild.id].items():
                    if event.hoster == ctx.author.id:
                        await event.edit(ctx, content=_("This event has ended."))
                        to_del = event.message
                    async with self.config.guild(ctx.guild).events() as cur_events:
                        del cur_events[str(event.hoster)]
                try:
                    del self.event_cache[ctx.guild.id][to_del]
                except KeyError:
                    pass
        if ctx.author not in members:
            members.insert(0, ctx.author)
        member_list = [m.id for m in members]
        if not max_slots:

            max_slots = await self.config.guild(ctx.guild).default_max()
            # log.debug(f"using default {max_slots}")
        event = Event(
            hoster=ctx.author.id,
            members=list(member_list),
            event=description,
            max_slots=max_slots,
            guild=ctx.guild.id,
            channel=announcement_channel.id,
        )

        if await self.config.guild(ctx.guild).bypass_admin():
            return await self.post_event(ctx, event)

        em = await event.make_event_embed(ctx)
        await ctx.send(_("Please wait for an someone to approve your event request."))
        admin_msg = await approval_channel.send(embed=em)
        start_adding_reactions(admin_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(admin_msg)
        reaction, user = await ctx.bot.wait_for("reaction_add", check=pred)
        if pred.result:
            event.approver = user.id
            await self.post_event(ctx, event)
        else:
            msg = _("{author}, your event request was denied by an admin.").format(
                author=ctx.author.mention
            )
            if version_info >= VersionInfo.from_str("3.4.6"):
                await ctx.reply(msg)
            else:
                await ctx.send(msg)
            return

    async def post_event(self, ctx: commands.Context, event: Event):
        em = await event.make_event_embed(ctx)
        ping = await self.config.guild(ctx.guild).ping()
        sanitize = {}
        if version_info >= VersionInfo.from_str("3.4.0"):
            sanitize = {"allowed_mentions": discord.AllowedMentions(everyone=True, roles=True)}
        announcement_channel = ctx.guild.get_channel(event.channel)
        posted_message = await announcement_channel.send(ping, embed=em, **sanitize)
        event.message = posted_message.id
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster)] = event.to_json()
        if ctx.guild.id not in self.event_cache:
            self.event_cache[ctx.guild.id] = {}
        self.event_cache[ctx.guild.id][posted_message.id] = event
        try:
            start_adding_reactions(posted_message, EVENT_EMOJIS)
        except discord.errors.Forbidden:
            pass

    @commands.command(name="clearevent", aliases=["endevent"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def clear_event(self, ctx: commands.Context, clear: bool = False) -> None:
        """
        Delete a stored event so you can create more

        `[clear]` yes/no to clear your current running event.
        """
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have any events running."))
        elif not clear:
            event_data = await self.config.guild(ctx.guild).events()
            event = Event.from_json(self.bot, event_data[str(ctx.author.id)])
            if not event:
                async with self.config.guild(ctx.guild).events() as events:
                    # clear the broken event
                    del events[str(ctx.author.id)]
                    del self.event_cache[ctx.guild.id][event.message]
                return await ctx.send(_("You don't have any events running."))
            em = await event.make_event_embed(ctx)
            return await ctx.send(
                _(
                    "{author}, you're currently hosting. "
                    "Type `{prefix}clearevent yes` to clear it."
                ).format(author=ctx.author.display_name, prefix=ctx.clean_prefix),
                embed=em,
            )
        else:
            async with self.config.guild(ctx.guild).events() as events:
                event = Event.from_json(self.bot, events[str(ctx.author.id)])
                await event.edit(ctx, content=_("This event has ended."))
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            await ctx.tick()

    @commands.command(name="showevent")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def show_event(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Show current event being run by a member"""
        if member is None:
            member = ctx.author
        if str(member.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(
                _("{member} does not have any events running.").format(member=member)
            )
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(member.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            return await ctx.send(
                _("{member} is not currently hosting an event.").format(member=member.display_name)
            )
        em = await event.make_event_embed(ctx)
        await ctx.send(
            _(
                "{member} is currently hosting. " "Type `{prefix}clearevent yes` to clear it."
            ).format(member=member.display_name, prefix=ctx.clean_prefix),
            embed=em,
        )

    @commands.command(name="join")
    @commands.guild_only()
    async def join_event(
        self,
        ctx: commands.Context,
        hoster: discord.Member,
    ) -> None:
        """Join an event being hosted"""
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(
                _("{hoster} is not currently hosting any events.").format(
                    hoster=hoster.display_name
                )
            )
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(hoster.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            return await ctx.send(
                _("{hoster} is not currently hosting any events.").format(
                    hoster=hoster.display_name
                )
            )
        if ctx.author.id in event.members:
            return await ctx.send(_("You're already participating in this event!"))
        await self.add_user_to_event(ctx.author, event)
        await ctx.tick()

    @commands.command(name="leaveevent")
    @commands.guild_only()
    async def leave_event(self, ctx: commands.Context, hoster: discord.Member) -> None:
        """Leave an event being hosted"""
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(
                _("{hoster} is not currently hosting any events.").format(
                    hoster=hoster.display_name
                )
            )
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(hoster.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            return await ctx.send(
                _("{hoster} is not currently hosting any events.").format(
                    hoster=hoster.display_name
                )
            )
        if ctx.author.id not in event.members:
            return await ctx.send(_("You're not participating in this event!"))
        await self.remove_user_from_event(ctx.author, event)
        await ctx.tick()

    @commands.command(name="removefromevent")
    @commands.guild_only()
    async def remove_from_event(
        self, ctx: commands.Context, member: discord.Member, hoster: discord.Member = None
    ) -> None:
        """
        Remove a user from an event you're hosting

        `<member>` The member to remove from your event
        `<hoster>` mod/admin only to specify whos event to remove a user from.
        """
        if hoster and not await self.is_mod_or_admin(ctx.author):
            return await ctx.send(_("You cannot remove a member from someone elses event"))
        if hoster is None:
            hoster = ctx.author
        if member is hoster:
            return await ctx.send(_("You cannot remove the hoster from this event."))
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You are not currently hosting any events."))
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(ctx.author.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            return await ctx.send(_("That user is not currently hosting any events."))
        if member.id not in event.members:
            return await ctx.send(_("That member is not participating in that event!"))
        await self.remove_from_event(member, event)
        await ctx.tick()

    @commands.group(name="eventedit", aliases=["editevent"])
    @commands.guild_only()
    async def event_edit(self, ctx: commands.Context):
        """
        Edit various things in events
        """
        pass

    @event_edit.command()
    @commands.guild_only()
    async def title(self, ctx: commands.Context, *, new_description: str):
        """
        Edit the title of your event

        `<new_description>` The new description for your event
        """
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                event.event = new_description
                em = await event.make_event_embed(ctx)

                await event.edit(ctx, embed=em)
                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
                await ctx.tick()
                break

    async def get_channels(
        self, ctx: commands.Context
    ) -> Tuple[Optional[discord.TextChannel], Optional[discord.TextChannel]]:
        approval_channel = ctx.guild.get_channel(
            await self.config.guild(ctx.guild).approval_channel()
        )
        announcement_channel = ctx.guild.get_channel(
            await self.config.guild(ctx.guild).announcement_channel()
        )
        if not approval_channel and not await self.config.guild(ctx.guild).bypass_admin():
            await ctx.send(
                _(
                    "No admin channel has been setup on this server. "
                    "Use `{prefix}eventset approvalchannel` to add one."
                ).format(prefix=ctx.clean_prefix)
            )
            return None, None
        if not announcement_channel:
            await ctx.send(
                _(
                    "No announcement channel has been setup on this server. "
                    "Use `{prefix}eventset channel` to add one."
                ).format(prefix=ctx.clean_prefix)
            )
            return None, None
        return announcement_channel, approval_channel

    @event_edit.command()
    @commands.guild_only()
    async def slots(self, ctx: commands.Context, new_slots: Optional[int] = None):
        """
        Edit the number of slots available for your event

        `<new_slots>` The number of available slots for your events activity
        """
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                event.max_slots = new_slots
                em = await event.make_event_embed(ctx)

                await event.edit(ctx, embed=em)
                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
                await ctx.tick()
                break

    @event_edit.command()
    @commands.guild_only()
    async def remaining(self, ctx: commands.Context):
        """
        Show how long until your event will be automatically ended if available.
        """
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                seconds = await self.config.guild(ctx.guild).cleanup_seconds()
                if seconds is None:
                    return await ctx.send(
                        _("There is no automatic timeout of events in this server.")
                    )
                await ctx.send(
                    _("Your event has {time} remaining until it is ended automatically.").format(
                        time=event.remaining(seconds)
                    )
                )
                return

    @event_edit.group()
    @commands.guild_only()
    async def members(self, ctx: commands.Context):
        """Edit event members"""
        pass

    @members.command(name="add")
    @commands.guild_only()
    async def members_add(self, ctx: commands.Context, *new_members: discord.Member):
        """
        Add members to your event (hopefully not against their will)

        `[new_members...]` The members you want to add to your event
        """
        if not new_members:
            return await ctx.send_help()
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                for m in new_members:
                    await self.add_user_to_event(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
                await ctx.tick()
                break

    @members.command(name="remove", aliases=["rem"])
    @commands.guild_only()
    async def members_remove(self, ctx: commands.Context, *members: discord.Member):
        """
        Remove members from your event (hopefully not against their will)

        `[members...]` The members you want to add to your event
        """
        if not members:
            return await ctx.send_help()
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                for m in members:
                    if m.id in event.members or m.id in event.maybe:
                        await self.remove_user_from_event(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
                await ctx.tick()
                break

    @event_edit.group()
    @commands.guild_only()
    async def maybe(self, ctx: commands.Context):
        """Edit event members"""
        pass

    @maybe.command(name="add")
    @commands.guild_only()
    async def maybe_add(self, ctx: commands.Context, *new_members: discord.Member):
        """
        Add members to your events maybe list

        `[new_members...]` The members you want to add to your event
        """
        if not new_members:
            return await ctx.send_help()
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                for m in new_members:
                    if m.id not in event.members:
                        await self.add_user_to_maybe(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
                await ctx.tick()
                break

    @maybe.command(name="remove", aliases=["rem"])
    @commands.guild_only()
    async def maybe_remove(self, ctx: commands.Context, *members: discord.Member):
        """
        Remove members from your events maybe list

        `[members...]` The members you want to remove from your event
        """
        if not members:
            return await ctx.send_help()
        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(_("You don't have an event to edit right now."))
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if event.hoster == ctx.author.id:
                for m in members:
                    if m.id in event.members or m.id in event.maybe:
                        await self.remove_user_from_event(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
                await ctx.tick()
                break

    async def is_mod_or_admin(self, member: discord.Member) -> bool:
        guild = member.guild
        if member == guild.owner:
            return True
        if await self.bot.is_owner(member):
            return True
        if await self.bot.is_admin(member):
            return True
        if await self.bot.is_mod(member):
            return True
        return False

    async def check_clear_event(self, ctx: commands.Context) -> bool:
        msg = await ctx.send(_("You already have an event running, would you like to cancel it?"))
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=pred)
        return pred.result

    @commands.group(name="eventset")
    @commands.guild_only()
    async def event_settings(self, ctx: commands.Context) -> None:
        """Manage server specific settings for events"""
        pass

    @event_settings.command(name="settings")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def show_event_settings(self, ctx: commands.Context) -> None:
        """
        Show the current event settings.
        """
        data = await self.config.guild(ctx.guild).all()
        approval_channel = ctx.guild.get_channel(data["approval_channel"])
        announcement_channel = ctx.guild.get_channel(data["announcement_channel"])
        embed = discord.Embed(title=_("Event Settings for {guild}").format(guild=ctx.guild.name))
        msg = _(
            "__Approval Channel:__ {approval_channel}\n"
            "__Announcement Channel:__ {announcement_channel}\n"
            "__Mentioned Roles:__ {ping}\n"
        ).format(
            approval_channel=approval_channel.mention if approval_channel else approval_channel,
            announcement_channel=announcement_channel.mention
            if announcement_channel
            else announcement_channel,
            ping=data["ping"],
        )
        if data["default_max"]:
            msg += _("__Default Max Slots:__ {default_slots}\n").format(
                default_slots=data["default_max"]
            )
        if data["cleanup_seconds"] is not None:
            log.debug(data["cleanup_seconds"])
            msg += _("__Events End After:__ **{time}**\n").format(
                time=humanize_timedelta(seconds=data["cleanup_seconds"])
            )
        if data["bypass_admin"]:
            msg += _("__Skip Admin Approval:__ **{bypass_admin}**\n").format(
                bypass_admin=data["bypass_admin"]
            )
        if data["max_events"]:
            msg += _("__Maximum Events:__ **{max_events}**\n").format(max_events=data["max_events"])
        if data["required_roles"]:
            roles = [ctx.guild.get_role(r) for r in data["required_roles"]]
            msg += _("__Event Creator Roles:__ {roles}\n").format(
                roles=humanize_list([r.mention for r in roles])
            )
        embed.description = msg
        await ctx.send(embed=embed)

    @event_settings.command(name="remove", aliases=["rem"])
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def remove_event(
        self, ctx: commands.Context, *, hoster_or_message: Union[discord.Member, discord.Message]
    ):
        """
        Remove and end a current event.

        `<hoster_or_message>` The member who is hosting the event or the message the event is
        located at.

        If a message is used instead it must be either a `channelID-messageID` pair,
        a message jump link, or the message ID if the command is in the same channel
        as the event message itself.
        """
        if isinstance(hoster_or_message, discord.Member):
            if hoster_or_message and not await self.is_mod_or_admin(ctx.author):
                return await ctx.send(_("You cannot remove a member from someone elses event"))
            if str(hoster_or_message.id) not in await self.config.guild(ctx.guild).events():
                return await ctx.send(_("You are not currently hosting any events."))
            to_del = 0
            for message_id, event in self.event_cache[ctx.guild.id].items():
                if event.hoster == hoster_or_message.id:
                    await event.edit(ctx, content=_("This event has ended."))
                    to_del = event.message
                async with self.config.guild(ctx.guild).events() as cur_events:
                    del cur_events[str(event.hoster)]
            try:
                del self.event_cache[ctx.guild.id][to_del]
            except KeyError:
                pass
        else:
            try:
                event = self.event_cache[ctx.guild.id][hoster_or_message.id]
            except KeyError:
                return await ctx.send(_("I could not find an event under that message."))
            await event.edit(ctx, content=_("This event has ended."))
            async with self.config.guild(ctx.guild).events() as cur_events:
                del cur_events[str(event.hoster)]
            del self.event_cache[ctx.guild.id][event.message]
        await ctx.tick()

    @event_settings.command(name="playerclass")
    @commands.guild_only()
    async def set_default_player_class(
        self, ctx: commands.Context, *, player_class: str = ""
    ) -> None:
        """
        Set's the users default player class. If nothing is provided this will be rest.

        `[player_class]` Your desired playerclass for events. This is listed
        next to your name when you register for an event. If this is changed
        during an event you have signed up for if the event updates with new
        members or changes in any way the event will reflect this change.
        """
        await self.config.member(ctx.author).player_class.set(player_class)
        if player_class:
            await ctx.send(
                _("Your player class has been set to {player_class}").format(
                    player_class=player_class
                )
            )
        else:
            await ctx.send("Your player class has been reset.")
        if ctx.guild.id not in self.event_cache:
            return
        for message_id, event in self.event_cache[ctx.guild.id].items():
            if ctx.author.id in event.members:
                em = await event.make_event_embed(ctx)
                await event.edit(ctx, embed=em)

    @event_settings.command(name="defaultmax", aliases=["max"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_default_max_slots(
        self, ctx: commands.Context, max_slots: Optional[int] = None
    ) -> None:
        """
        Set's the servers default maximum slots

        `[max_slots]` The maximum number of slots allowed by default for events.
        """
        if max_slots is not None and max_slots <= 0:
            max_slots = None
        await self.config.guild(ctx.guild).default_max.set(max_slots)
        await ctx.send(
            _("Default maximum slots for events set to {max_slots} slots.").format(
                max_slots=max_slots
            )
        )

    @event_settings.command(name="channel")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """
        Set the Announcement channel for events

        `[channel]` The channel events will be sent to. Providing no input will
        clear the channel.

        If no channel is set events cannot be created.
        """
        if channel and not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send(_("I require `Embed Links` permission to use that channel."))
        save_channel = None
        reply = _("Announcement channel ")
        if channel:
            save_channel = channel.id
            reply += _("set to {chan}").format(chan=channel.mention)
            await self.config.guild(ctx.guild).announcement_channel.set(save_channel)
        else:
            reply += _("cleared.")
            await self.config.guild(ctx.guild).announcement_channel.clear()
        await ctx.send(reply)

    @event_settings.command(name="cleanup")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_cleanup_interval(
        self, ctx: commands.Context, *, time: Optional[commands.TimedeltaConverter] = None
    ) -> None:
        """
        Set the events cleanup interval.

        `[time]` How long events should be allowed to live before being
        automatically ended.

        Note: If there is a timestamp for the event, the cleanup interval
        will check since the timestamp. If not it will check time after the event
        has been posted. Timestamp can be seen from the events embed.
        """
        if time:
            await self.config.guild(ctx.guild).cleanup_seconds.set(int(time.total_seconds()))
            reply = _("I will cleanup events older than {time}.").format(
                time=humanize_timedelta(timedelta=time)
            )
        else:
            reply = _("I will not cleanup messages regardless of age.")
            await self.config.guild(ctx.guild).cleanup_seconds.clear()
        await ctx.send(reply)

    @event_settings.command(name="maxevents")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_max_events(
        self, ctx: commands.Context, number_of_events: Optional[int] = None
    ) -> None:
        """
        Set the maximum number of events the server can host.

        `[number_of_events]` The maximum number of events this server can have running
        at one time.

        Note: If this is set then the event author must cancel the event manually
        by either reacting to the x on the event itself or `[p]clearevent`. This
        can also be handled automatically with `[p]eventset cleanup` where events
        will last until the designated time after an event has started. Alternatively
        a mod or admin can cancel an event through `[p]eventset remove`
        """
        if number_of_events is not None and number_of_events <= 0:
            number_of_events = None
        if number_of_events:
            await self.config.guild(ctx.guild).max_events.set(int(number_of_events))
            reply = _("I will allow a maximum of {number} events.").format(number=number_of_events)
        else:
            reply = _("I will not restrict the maximum number of events.")
            await self.config.guild(ctx.guild).max_events.clear()
        await ctx.send(reply)

    @event_settings.command(name="bypass")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def bypass_admin_approval(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Set whether or not admin approval is required for events to be posted.

        `<true_or_false>` `True` or `False` whether or not to allow events
        to bypass admin approval.
        """
        if true_or_false:
            await self.config.guild(ctx.guild).bypass_admin.set(true_or_false)
            reply = _("I will post events without admin apprval first.")
        else:
            reply = _("I will not post events without admin apprval first.")
            await self.config.guild(ctx.guild).bypass_admin.clear()
        await ctx.send(reply)

    @event_settings.command(name="approvalchannel", aliases=["adminchannel"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_approval_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """
        Set the admin approval channel

        `[channel]` The channel you have restricted to people you trust to approve events.
        If no channel is provided this will be reset.

        Note: This is required unless bypass has been enabled.
        """
        if channel and not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send(_("I require `Embed Links` permission to use that channel."))
        if channel and not channel.permissions_for(ctx.me).add_reactions:
            return await ctx.send(_("I require `Add Reactions` permission to use that channel."))
        save_channel = None
        reply = _("Admin approval channel ")
        if channel:
            save_channel = channel.id
            reply += _("set to {chan}.").format(chan=channel.mention)
            await self.config.guild(ctx.guild).approval_channel.set(save_channel)
        else:
            await self.config.guild(ctx.guild).approval_channel.clear()
            reply += _("cleared.")

        await ctx.send(reply)

    @event_settings.command(name="roles", aliases=["role"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_required_roles(self, ctx: commands.Context, *roles: discord.Role) -> None:
        """
        Set the roles that are allowed to create roles

        `[roles...]` the role(s) that are allowed to create events. If not provided,
        there will be no restriction on who can create an event.
        """
        if roles:
            role_ids = [r.id for r in roles]
            role_names = humanize_list([r.name for r in roles])
            await self.config.guild(ctx.guild).required_roles.set(role_ids)
            await ctx.send(_("Roles allowed to create events: {roles}.").format(roles=role_names))
        else:
            await self.config.guild(ctx.guild).required_roles.clear()
            await ctx.send(_("Anyone will now be able to create an event."))

    @event_settings.command(name="links")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_custom_link(self, ctx: commands.Context, keyword: str, link: ValidImage) -> None:
        """
        Set the custom thumbnail for events

        `<keyword>` is the word that will be searched for in event titles.
        `<link>` needs to be an image link to be used for the thumbnail when the keyword
        is found in the event title.
        """
        async with self.config.guild(ctx.guild).custom_links() as custom_links:
            custom_links[keyword.lower()] = link
        await ctx.tick()

    @event_settings.command(name="viewlinks", aliases=["showlinks"])
    @checks.mod_or_permissions(manage_messages=True)
    @checks.bot_has_permissions(add_reactions=True)
    @commands.guild_only()
    async def view_links(self, ctx: commands.Context):
        """
        Show custom thumbnails available for events in this server
        """
        custom_links = await self.config.guild(ctx.guild).custom_links()
        embed_links = ctx.channel.permissions_for(ctx.me).embed_links
        msgs = []
        msg = ""
        for keyword, link in custom_links.items():
            if embed_links:
                msg += f"[{keyword}]({link})\n"
            else:
                msg += f"`{keyword}` - {link}"
        if embed_links:
            for page in pagify(msg):
                embed = discord.Embed(description=page)
                embed.title = _("{guild} Thumbnail Links").format(guild=ctx.guild.name)
                msgs.append(embed)
        else:
            for page in pagify(msg):
                msgs.append(page)
        await menu(ctx, msgs, DEFAULT_CONTROLS)

    @event_settings.command(name="ping", aliases=["mention"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_ping(self, ctx: commands.Context, *roles: Union[discord.Role, str]) -> None:
        """
        Set the ping to use when an event is announced

        `[roles...]` is a space separated list of roles to be pinged when an announcement
        is made. Use `here` or `everyone` if you want to ping that specific group of people.
        """
        role_mentions = [r.mention for r in roles if isinstance(r, discord.Role)]
        here = [f"@{r}" for r in roles if r in ["here", "everyone"]]
        msg = humanize_list(role_mentions + here)
        await self.config.guild(ctx.guild).ping.set(msg)
        await ctx.tick()
