import asyncio
from typing import Dict, Literal, Optional, Tuple

import discord
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta, pagify
from redbot.core.utils.views import SimpleMenu

from .event_obj import ApproveView, ConfirmView, Event, ValidImage, WrongView

log = getLogger("red.trusty-cogs.EventPoster")

_ = Translator("EventPoster", __file__)

EVENT_EMOJIS = [
    "\N{WHITE HEAVY CHECK MARK}",
    "\N{NEGATIVE SQUARED CROSS MARK}",
    "\N{WHITE QUESTION MARK ORNAMENT}",
]


@cog_i18n(_)
class EventPoster(commands.Cog):
    """Create admin approved events/announcements"""

    __version__ = "2.1.4"
    __author__ = "TrustyJAID"
    __flavor__ = "Admins are sleep deprived :)"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=144014746356678656)
        default_guild = {
            "approval_channel": None,
            "announcement_channel": None,
            "ping": "",
            "events": {},
            "custom_links": {},
            "large_links": {},
            "default_max": None,
            "cleanup_seconds": None,
            "bypass_admin": False,
            "max_events": None,
            "required_roles": [],
            "playerclass_options": {},
            "make_thread": False,
            "enable_slash": False,
        }
        default_user = {"player_class": ""}
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_user)
        self.event_cache: Dict[int, Dict[int, Event]] = {}
        self._ready: asyncio.Event = asyncio.Event()
        self.cleanup_old_events.start()
        self.waiting_approval = {}

    def format_help_for_context(self, ctx: commands.Context):
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_unload(self):
        self.cleanup_old_events.cancel()
        for guild_id, events in self.event_cache.items():
            for user_id, event in events.items():
                event.stop()

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
                await self.config.guild_from_id(int(guild_id)).events.set(data["events"])
        all_members = await self.config.all_members()
        for guild_id, members in all_members.items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()

    @tasks.loop(seconds=60)
    async def cleanup_old_events(self):
        for guild_id, events in self.event_cache.items():
            cleanup_seconds = await self.config.guild_from_id(int(guild_id)).cleanup_seconds()
            to_remove = []
            if not cleanup_seconds:
                continue
            for message_id, event in events.items():
                if event.should_remove(cleanup_seconds):
                    to_remove.append(message_id)
                    # log.debug(f"Removing {event} due to age.")
            for msg_id in to_remove:
                ctx = await events[msg_id].get_ctx(self.bot)
                if ctx:
                    await events[msg_id].end_event()

                async with self.config.guild_from_id(int(guild_id)).events() as guild_events:
                    del guild_events[str(events[msg_id].hoster)]
                    # log.debug("deleted from config")
                del events[msg_id]
                # log.debug("deleted from cache")
        # log.debug("Finished checking events to cleanup")

    @cleanup_old_events.before_loop
    async def before_cleanup_old_events(self):
        log.debug("Waiting for cog to finish setting up.")
        await self.bot.wait_until_red_ready()
        await self._ready.wait()
        # Finish loading all the events to memory first before checking

    async def cog_load(self) -> None:
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
                    event.cog = self
                    self.event_cache[guild_id][event.message] = event
                    self.bot.add_view(event)
        except Exception:
            log.exception("Error loading events")
        self._ready.set()

    async def add_user_to_event(self, user: discord.Member, event: Event) -> None:
        if user.id in event.members:
            return
        if event.max_slots and len(event.members) >= event.max_slots:
            return
        event.members.append(user.id)
        if user.id in event.maybe:
            event.maybe.remove(user.id)
        event.check_join_enabled()
        await event.update_event()
        if event.thread:
            guild = self.bot.get_guild(event.guild)
            if not guild:
                return
            thread = guild.get_thread(event.thread)
            if not thread:
                return
            try:
                await thread.add_user(user)
            except Exception:
                pass
        return

    async def add_user_to_maybe(self, user: discord.Member, event: Event) -> None:
        if user.id in event.maybe:
            return
        event.maybe.append(user.id)
        if user.id in event.members:
            event.members.remove(user.id)
        event.check_join_enabled()
        await event.update_event()
        if event.thread:
            guild = self.bot.get_guild(event.guild)
            if not guild:
                return
            thread = guild.get_thread(event.thread)
            if not thread:
                return
            try:
                await thread.add_user(user)
            except Exception:
                pass
        return

    async def remove_user_from_event(self, user: discord.Member, event: Event) -> None:
        ctx = await event.get_ctx(self.bot)
        if not ctx:
            return
        if user.id in event.members:
            event.members.remove(user.id)
        if user.id in event.maybe:
            event.maybe.remove(user.id)
        event.check_join_enabled()
        await event.update_event()
        if event.thread:
            guild = self.bot.get_guild(event.guild)
            if not guild:
                return
            thread = guild.get_thread(event.thread)
            if not thread:
                return
            try:
                await thread.remove_user(user)
            except Exception:
                pass

    async def check_requirements(self, ctx: commands.Context) -> bool:
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        max_events = await self.config.guild(ctx.guild).max_events()
        if (
            max_events is not None
            and ctx.guild.id in self.event_cache
            and len(self.event_cache[ctx.guild.id]) >= max_events
        ):
            msg = _(
                "The maximum number of events are already posted. Please wait until one finishes."
            )
            if is_slash:
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return False
        required_roles = [
            ctx.guild.get_role(r)
            for r in await self.config.guild(ctx.guild).required_roles()
            if ctx.guild.get_role(r) is not None
        ]
        allowed = True
        if required_roles:
            allowed = False
            for role in required_roles:
                if role is None:
                    continue
                if role in author.roles:
                    allowed = True
        if not allowed:
            msg = _("You do not have one of the required roles to create events.")
            await ctx.send(msg)
        return allowed

    @commands.hybrid_group(name="event")
    @commands.guild_only()
    async def event_commands(self, ctx: commands.Context):
        """All event related commands."""
        pass

    @event_commands.command(name="ping", aliases=["mention"])
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
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            msg = _("You don't have an event running with people to ping.")
            await ctx.send(msg)
            return
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(ctx.author.id)])
        msg = event.mention(include_maybe) + ":\n"
        if message is not None:
            msg += message
        for page in pagify(msg):
            await ctx.send(page, allowed_mentions=discord.AllowedMentions(users=True))
            # include AllowedMentions here just incase someone has user mentions disabled
            # since this is intended to ping the users.

    @event_commands.command(name="make")
    @commands.guild_only()
    async def make_event(
        self,
        ctx: commands.Context,
        members: commands.Greedy[discord.Member] = None,
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
        if not isinstance(members, list):
            members = [members]
        if not await self.check_requirements(ctx):
            return

        announcement_channel, approval_channel = await self.get_channels(ctx)
        if not announcement_channel:
            return
        if str(ctx.author.id) in await self.config.guild(ctx.guild).events():
            if not await self.check_clear_event(ctx):
                return
            else:
                event = None
                for message_id, events in self.event_cache[ctx.guild.id].items():
                    if events.hoster == ctx.author.id:
                        event = events
                if event is not None:
                    await event.end_event()
        if ctx.author not in members:
            members.insert(0, ctx.author)
        member_list = [m.id for m in members if m is not None]
        if not max_slots:
            max_slots = await self.config.guild(ctx.guild).default_max()
            # log.debug(f"using default {max_slots}")
        select_options = await self.config.guild(ctx.guild).playerclass_options()
        event = Event(
            bot=self.bot,
            hoster=ctx.author.id,
            members=list(member_list),
            event=description,
            max_slots=max_slots,
            guild=ctx.guild.id,
            channel=announcement_channel.id,
            select_options=select_options,
            cog=self,
        )

        if await self.config.guild(ctx.guild).bypass_admin():
            msg = _("Creating your event.")
            await ctx.send(msg)
            return await self.post_event(ctx, event)

        view = ApproveView(self, ctx)
        wrongview = WrongView()

        em = await event.make_event_embed(ctx)
        msg = _(
            "Please wait for someone to approve your event request. "
            "In the mean time here's how your event will look. "
        )
        wrongview.message = await ctx.send(msg, embed=em, view=wrongview)
        admin_msg = await approval_channel.send(embed=em, view=view)
        self.waiting_approval[admin_msg.id] = {"event": event, "ctx": ctx, "wrongview": wrongview}
        await wrongview.wait()
        if not wrongview.approved:
            del self.waiting_approval[admin_msg.id]
            try:
                await admin_msg.delete()
            except Exception:
                pass

    async def post_event(self, ctx: commands.Context, event: Event):
        em = await event.make_event_embed(ctx)
        ping = await self.config.guild(ctx.guild).ping()
        sanitize = {}
        if version_info >= VersionInfo.from_str("3.4.0"):
            sanitize = {"allowed_mentions": discord.AllowedMentions(everyone=True, roles=True)}
        announcement_channel = ctx.guild.get_channel(event.channel)
        posted_message = await announcement_channel.send(ping, embed=em, view=event, **sanitize)
        if await self.config.guild(ctx.guild).make_thread():
            try:
                thread = await posted_message.create_thread(name=event.event[:100])
                made_thread = True
            except Exception:
                made_thread = False
            if made_thread:
                event.thread = thread.id
                for m in event.members:
                    try:
                        await thread.add_user(ctx.guild.get_member(m))
                    except Exception:
                        log.exception("Error adding members to new thread.")
        setattr(event, "message", posted_message.id)
        # event.message = posted_message.id
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster)] = event.to_json()
        if ctx.guild.id not in self.event_cache:
            self.event_cache[ctx.guild.id] = {}
        self.event_cache[ctx.guild.id][posted_message.id] = event
        # try:
        # start_adding_reactions(posted_message, EVENT_EMOJIS)
        # except discord.errors.Forbidden:
        # pass

    @event_commands.command(name="clear", aliases=["end"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def clear_event(self, ctx: commands.Context, clear: bool = False) -> None:
        """
        Delete a stored event so you can create more

        `[clear]` yes/no to clear your current running event.
        """
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            msg = _("You don't have any events running.")
            await ctx.send(msg)
            return
        if not clear:
            event_data = await self.config.guild(ctx.guild).events()
            event = Event.from_json(self.bot, event_data[str(ctx.author.id)])
            if not event:
                async with self.config.guild(ctx.guild).events() as events:
                    # clear the broken event
                    del events[str(ctx.author.id)]
                    del self.event_cache[ctx.guild.id][event.message]
                msg = _("You don't have any events running.")
                await ctx.send(msg)
                return
            em = await event.make_event_embed(ctx)
            msg = _(
                "{author}, you're currently hosting. "
                "Type `{prefix}event clear yes` to clear it."
            ).format(author=ctx.author.display_name, prefix=ctx.clean_prefix)
            await ctx.send(
                msg,
                embed=em,
            )
            return
        else:
            event_data = await self.config.guild(ctx.guild).events()
            event = Event.from_json(self.bot, event_data[str(ctx.author.id)])
            await event.end_event()
            msg = _("Your event has been cleared.")
            await ctx.send(msg)

    @event_commands.command(name="show")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def show_event(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Show current event being run by a member"""
        if member is None:
            member = ctx.author
        if str(member.id) not in await self.config.guild(ctx.guild).events():
            msg = _("{member} does not have any events running.").format(
                member=member.display_name
            )
            await ctx.send(msg)
            return
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(member.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            msg = _("{member} is not currently hosting an event.").format(
                member=member.display_name
            )
            await ctx.send(msg)
            return
        em = await event.make_event_embed(ctx)
        msg = _(
            "{member} is currently hosting. Type `{prefix}event set remove @hoster` to clear it."
        ).format(member=member.display_name, prefix=ctx.clean_prefix)
        await ctx.send(
            msg,
            embed=em,
        )

    @event_commands.command(name="join")
    @commands.guild_only()
    async def join_event(
        self,
        ctx: commands.Context,
        hoster: discord.Member,
    ) -> None:
        """Join an event being hosted"""

        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            msg = _("{hoster} is not currently hosting any events.").format(
                hoster=hoster.display_name
            )
            await ctx.send(msg)
            return
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(hoster.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            msg = _("{hoster} is not currently hosting any events.").format(
                hoster=hoster.display_name
            )
            await ctx.send(msg)
            return
        if ctx.author.id in event.members:
            msg = _("You're already participating in this event!")
            await ctx.send(msg)
            return
        await self.add_user_to_event(ctx.author, event)
        msg = _("Adding you to {hoster}'s event.").format(hoster=hoster)
        await ctx.send(msg)

    @event_commands.command(name="leave")
    @commands.guild_only()
    async def leave_event(self, ctx: commands.Context, hoster: discord.Member) -> None:
        """Leave an event being hosted"""

        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            msg = _("{hoster} is not currently hosting any events.").format(
                hoster=hoster.display_name
            )
            await ctx.send(msg)
            return
        event_data = await self.config.guild(ctx.guild).events()
        event = Event.from_json(self.bot, event_data[str(hoster.id)])
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message]
            msg = _("{hoster} is not currently hosting any events.").format(
                hoster=hoster.display_name
            )
            await ctx.send(msg)
            return
        if ctx.author.id not in event.members:
            msg = _("You're not participating in this event!")
            await ctx.send(msg)
            return
        await self.remove_user_from_event(ctx.author, event)
        msg = _("Removing you from {hoster}'s event.").format(hoster=hoster)
        await ctx.send(msg)

    @event_commands.group(name="edit")
    @commands.guild_only()
    async def event_edit(self, ctx: commands.Context):
        """
        Edit various things in events
        """

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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                event.event = new_description
                await event.update_event()
        msg = _("Editing your event title to: {new_title}").format(new_title=new_description)
        await ctx.send(msg)

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
            msg = _(
                "No admin channel has been setup on this server. "
                "Use `{prefix}event set approvalchannel` to add one."
            ).format(prefix=ctx.clean_prefix)
            await ctx.send(msg)
            return None, None
        if not announcement_channel:
            msg = _(
                "No announcement channel has been setup on this server. "
                "Use `{prefix}event set channel` to add one."
            ).format(prefix=ctx.clean_prefix)
            await ctx.send(msg)
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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                event.max_slots = new_slots
                await event.update_event()
        msg = _("Editing your events max slots to: {new_slots}").format(new_slots=new_slots)
        await ctx.send(msg)

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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                seconds = await self.config.guild(ctx.guild).cleanup_seconds()
                if seconds is None:
                    msg = _("There is no automatic timeout of events in this server.")
                    await ctx.send(msg)
                    return
                msg = _("Your event has {time} remaining until it is ended automatically.").format(
                    time=event.remaining(seconds)
                )
                await ctx.send(msg)
                return

    @event_edit.command(name="memberadd")
    @commands.guild_only()
    async def members_add(
        self, ctx: commands.Context, new_members: commands.Greedy[discord.Member]
    ):
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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                for m in new_members:
                    await self.add_user_to_event(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
        msg = _("Added {members} to your event.").format(members=humanize_list(new_members))
        await ctx.send(msg)

    @event_edit.command(name="memberremove", aliases=["memberrem"])
    @commands.guild_only()
    async def members_remove(
        self, ctx: commands.Context, members: commands.Greedy[discord.Member]
    ):
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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                for m in members:
                    if m.id in event.members or m.id in event.maybe:
                        await self.remove_user_from_event(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
        msg = _("Removed {members} from your event.").format(members=humanize_list(members))
        await ctx.send(msg)

    @event_edit.command(name="maybeadd")
    @commands.guild_only()
    async def maybe_add(self, ctx: commands.Context, new_members: commands.Greedy[discord.Member]):
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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                for m in new_members:
                    if m.id not in event.members:
                        await self.add_user_to_maybe(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
        msg = _("Added {members} to maybe on your event.").format(
            members=humanize_list(new_members)
        )
        await ctx.send(msg)

    @event_edit.command(name="mayberemove", aliases=["mayberem"])
    @commands.guild_only()
    async def maybe_remove(self, ctx: commands.Context, members: commands.Greedy[discord.Member]):
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
            msg = _("You don't have an event to edit right now.")
            await ctx.send(msg)
            return
        for event in self.event_cache[ctx.guild.id].values():
            if event.hoster == ctx.author.id:
                for m in members:
                    if m.id in event.members or m.id in event.maybe:
                        await self.remove_user_from_event(m, event)

                async with self.config.guild(ctx.guild).events() as cur_events:
                    cur_events[str(event.hoster)] = event.to_json()
                self.event_cache[ctx.guild.id][event.message] = event
        msg = _("Removed {members} from maybe on your event.").format(
            members=humanize_list(members)
        )
        await ctx.send(msg)

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
        new_view = ConfirmView(ctx)
        msg = _("You already have an event running, would you like to cancel it?")
        await ctx.send(msg, view=new_view)
        await new_view.wait()
        return new_view.approved

    @event_commands.group(name="set")
    @commands.guild_only()
    async def event_settings(self, ctx: commands.Context) -> None:
        """Manage server specific settings for events"""

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
            log.trace("show_event_settings cleanup_seconds: %s", data["cleanup_seconds"])
            msg += _("__Events End After:__ **{time}**\n").format(
                time=humanize_timedelta(seconds=data["cleanup_seconds"])
            )
        if data["bypass_admin"]:
            msg += _("__Skip Admin Approval:__ **{bypass_admin}**\n").format(
                bypass_admin=data["bypass_admin"]
            )
        if data["max_events"]:
            msg += _("__Maximum Events:__ **{max_events}**\n").format(
                max_events=data["max_events"]
            )
        if data["required_roles"]:
            roles = [ctx.guild.get_role(r) for r in data["required_roles"]]
            msg += _("__Event Creator Roles:__ {roles}\n").format(
                roles=humanize_list([r.mention for r in roles if r is not None])
            )
        embed.description = msg
        await ctx.send(embed=embed)

    @event_settings.command(name="addplayerclass")
    async def add_guild_playerclass(
        self,
        ctx: commands.Context,
        emoji: Optional[str] = None,
        *,
        player_class: str,
    ):
        """
        Add a playerclass choice for users to pick from on this server.

        `[emoji]` Can be any emoji and is used on the drop down selector to
        help distinguish the classes.
        `<player_class>` The name of the player class you want to have
        as a server option.

        Note: There is a maximum of 25 classes you can add. The class name
        can also only be a maximum of 100 characters.
        """

        if len(player_class) > 100:
            msg = _("Player classes can be a maximum of 100 characters.")
            await ctx.send(msg)
            return
        async with self.config.guild(ctx.guild).playerclass_options() as options:
            if len(options) >= 25:
                msg = _(
                    "You can have a maximum of 25 player classes to select from."
                    "Delete some first before trying to add more."
                )
                await ctx.send(msg)
                return
            if player_class not in options:
                if emoji is not None:
                    emoji = discord.PartialEmoji.from_str(emoji)
                    if emoji.is_custom_emoji() and emoji.animated:
                        emoji = f"a:{emoji.name}:{emoji.id}"
                    elif emoji.is_custom_emoji() and not emoji.animated:
                        emoji = f"{emoji.name}:{emoji.id}"
                    else:
                        emoji = str(emoji)
                options[player_class] = emoji
        msg = _("{player_class} has been added as an available option.").format(
            player_class=player_class
        )
        await ctx.send(msg)

    @event_settings.command(name="removeplayerclass")
    async def remove_guild_playerclass(self, ctx: commands.Context, *, player_class: str):
        """
        Remove a playerclass choice for users to pick from on this server.

        `<player_class>` The name of the playerclass you want to remove.
        """

        success_msg = _("{player_class} has been removed as an available option.").format(
            player_class=player_class
        )
        fail_msg = _("{player_class} is not currently available as an option.").format(
            player_class=player_class
        )
        async with self.config.guild(ctx.guild).playerclass_options() as options:
            if player_class in options:
                del options[player_class]
                await ctx.send(success_msg)
            else:
                await ctx.send(fail_msg)

    @event_settings.command(name="listplayerclass")
    async def list_guild_playerclass(self, ctx: commands.Context):
        """
        List the playerclass choices in this server.
        """

        player_classes = await self.config.guild(ctx.guild).playerclass_options()
        player_classes = humanize_list(list(player_classes.keys()))
        msg = _("{guild} Available Playerclasses: **{player_classes}**").format(
            guild=ctx.guild.name, player_classes=player_classes
        )
        await ctx.send(msg)

    @event_settings.command(name="remove", aliases=["rem"])
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def remove_event(
        self,
        ctx: commands.Context,
        *,
        hoster: discord.Member,
    ):
        """
        Remove and end a current event.

        `<hoster>` The member who is hosting the event.
        """

        if hoster and not await self.is_mod_or_admin(ctx.author):
            msg = _("You cannot remove someone elses event")
            await ctx.send(msg)
            return
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            msg = _("That user is not currently hosting any events.")
            await ctx.send(msg)
            return
        event = None
        for events in self.event_cache[ctx.guild.id].values():
            if events.hoster == hoster.id:
                event = events
                break
        if event is not None:
            await event.end_event()
        await ctx.send(
            _("Ending {hoster}'s event.").format(hoster=hoster.mention),
            allowed_mentions=discord.AllowedMentions(users=False),
        )

    @event_settings.command(name="class")
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
        msg = _("Your player class has been set to {player_class}").format(
            player_class=player_class
        )
        if player_class:
            await ctx.send(msg)
        else:
            msg = _("Your player class has been reset.")
            await ctx.send(msg)
        if ctx.guild.id not in self.event_cache:
            return
        for event in self.event_cache[ctx.guild.id].values():
            if ctx.author.id in event.members:
                await event.update_event()

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
        msg = _("Default maximum slots for events set to {max_slots} slots.").format(
            max_slots=max_slots
        )
        await ctx.send(msg)

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

        if channel and not channel.permissions_for(ctx.guild.me).embed_links:
            msg = _("I require `Embed Links` permission to use that channel.")
            await ctx.send(msg)
            return
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

    # @event_settings.command(name="maxevents")
    # @checks.mod_or_permissions(manage_messages=True)
    # @commands.guild_only()
    async def set_max_events(
        self, ctx: commands.Context, number_of_events: Optional[int] = None
    ) -> None:
        """
        Set the maximum number of events the server can host.

        `[number_of_events]` The maximum number of events this server can have running
        at one time.

        Note: If this is set then the event author must cancel the event manually
        by either reacting to the x on the event itself or `[p]event clear yes`. This
        can also be handled automatically with `[p]event set cleanup` where events
        will last until the designated time after an event has started. Alternatively
        a mod or admin can cancel an event through `[p]event set remove`
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

    @event_settings.command(name="thread")
    @checks.mod_or_permissions(manage_messages=True, manage_threads=True)
    @commands.guild_only()
    async def make_thread(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Set whether or not to turn the announcement message into a thread
        for people to join and discuss in.

        `<true_or_false>` `True` or `False` whether or not to allow events
        to bypass admin approval.
        """

        if true_or_false:
            await self.config.guild(ctx.guild).make_thread.set(true_or_false)
            reply = _("I will create events with a thread for discussion.")
        else:
            reply = _("I will not create events with a thread for discussion.")
            await self.config.guild(ctx.guild).make_thread.clear()
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
            msg = _("I require `Embed Links` permission to use that channel.")
            await ctx.send(msg)
            return
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
    async def set_required_roles(self, ctx: commands.Context, role: discord.Role) -> None:
        """
        Set the roles that are allowed to create events

        `[roles...]` the role(s) that are allowed to create events. If not provided,
        there will be no restriction on who can create an event.
        """
        roles = [role]

        if roles:
            role_ids = [r.id for r in roles]
            role_names = humanize_list([r.name for r in roles])
            await self.config.guild(ctx.guild).required_roles.set(role_ids)
            reply = _("Roles allowed to create events: {roles}.").format(roles=role_names)
        else:
            await self.config.guild(ctx.guild).required_roles.clear()
            reply = _("Anyone will now be able to create an event.")
        await ctx.send(reply)

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
        reply = _("An image with the keyword {keyword} has been added.").format(keyword=keyword)
        await ctx.send(reply)

    @event_settings.command(name="largelinks")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_custom_large_link(
        self, ctx: commands.Context, keyword: str, link: ValidImage
    ) -> None:
        """
        Set the custom embed image for events

        `<keyword>` is the word that will be searched for in event titles.
        `<link>` needs to be an image link to be used for the thumbnail when the keyword
        is found in the event title.
        """
        async with self.config.guild(ctx.guild).large_links() as custom_links:
            custom_links[keyword.lower()] = link
        await ctx.tick()

    @event_settings.command(name="viewlinks", aliases=["showlinks"])
    @checks.mod_or_permissions(manage_messages=True)
    @checks.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def view_links(self, ctx: commands.Context):
        """
        Show custom thumbnails available for events in this server
        """
        custom_links = await self.config.guild(ctx.guild).custom_links()
        msgs = []
        for keyword, link in custom_links.items():
            em = discord.Embed(title=keyword)
            em.set_image(url=link)
            msgs.append(em)
        await SimpleMenu(msgs, use_select_menu=True).start(ctx)

    @event_settings.command(name="viewlargelinks", aliases=["showlargelinks"])
    @checks.mod_or_permissions(manage_messages=True)
    @checks.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def view_large_links(self, ctx: commands.Context):
        """
        Show custom images available for events in this server
        """
        custom_links = await self.config.guild(ctx.guild).large_links()
        msgs = []
        for keyword, link in custom_links.items():
            em = discord.Embed(title=keyword)
            em.set_image(url=link)
            msgs.append(em)
        await SimpleMenu(msgs, use_select_menu=True).start(ctx)

    @event_settings.command(
        name="ping", aliases=["mention"], usage="[everyone=False] [here=False] [roles...]"
    )
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_ping(
        self,
        ctx: commands.Context,
        everyone: Optional[bool] = False,
        here: Optional[bool] = False,
        roles: commands.Greedy[discord.Role] = (),
    ) -> None:
        """
        Set the ping to use when an event is announced

        `[everyone=False]` True or False, whether to include everyone ping.
        `[here=False]` True or False, whether to include here ping.
        `[role...]` Is the role(s) you want to add to the list of pinged roles when
        an event is created.

        If you want to ping here but not everyone you would do something like:
         - `[p]event set ping false true`

        If you just want to set a few roles you can do:
         - `[p]event set ping @role1 @role2`
        """
        role_mentions = [r.mention for r in roles if r is not None]
        if here:
            role_mentions.insert(0, "@here")
        if everyone:
            role_mentions.insert(0, "@everyone")
        pings = humanize_list(role_mentions)
        await self.config.guild(ctx.guild).ping.set(pings)
        reply = _("The following pings have been registered:\n {pings}").format(pings=pings)
        await ctx.send(
            reply,
            allowed_mentions=discord.AllowedMentions(roles=False, everyone=False),
        )
