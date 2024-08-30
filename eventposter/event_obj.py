import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

import discord
import pytz
from dateutil import parser
from dateutil.tz import gettz
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from discord.utils import snowflake_time
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta, pagify

log = getLogger("red.trusty-cogs.EventPoster")

_ = Translator("EventPoster", __file__)

IMAGE_LINKS = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|png))", flags=re.I)

# the following regex is slightly modified from Red
# it's changed to be slightly more strict on matching with finditer
# this is to prevent "empty" matches when parsing the full reason
# This is also designed more to allow time interval at the beginning or the end of the mute
# to account for those times when you think of adding time *after* already typing out the reason
# https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/commands/converter.py#L55
TIME_RE_STRING = r"|".join(
    [
        r"((?P<weeks>\d+?)\s?(weeks?|w))",
        r"((?P<days>\d+?)\s?(days?|d))",
        r"((?P<hours>\d+?)\s?(hours?|hrs|hr?))",
        r"((?P<minutes>\d+?)\s?(minutes?|mins?|m(?!o)))",  # prevent matching "months"
        r"((?P<seconds>\d+?)\s?(seconds?|secs?|s))",
    ]
)
TIME_RE = re.compile(TIME_RE_STRING, re.I)


class WrongView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.approved = True
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if self.message is not None:
            await self.message.edit(view=None)

    @discord.ui.button(label=_("This looks wrong"), style=discord.ButtonStyle.red)
    async def end_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        self.approved = False
        if self.message is not None:
            await self.message.edit(view=None)
        await interaction.response.send_message(
            _("This event has been cancelled. Feel free to try again.")
        )


class ApproveButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.green, label=label)

    async def callback(self, interaction: discord.Interaction):
        self.view.approved = True
        self.view.stop()
        await self.view.ctx.message.edit(view=None)
        await interaction.response.defer()


class DenyButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.red, label=label)

    async def callback(self, interaction: discord.Interaction):
        self.view.approved = False
        self.view.stop()
        await interaction.response.defer()


class ApproveView(discord.ui.View):
    def __init__(self, cog: commands.Cog, ctx: commands.Context):
        super().__init__(timeout=None)
        self.approved = False
        self.ctx = ctx
        self.cog = cog

    @discord.ui.button(label=_("Approve"), style=discord.ButtonStyle.green)
    async def approve_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message.id not in self.cog.waiting_approval:
            await interaction.response.defer()
            return
        self.stop()
        await interaction.response.defer()
        event = self.cog.waiting_approval[interaction.message.id]["event"]
        ctx = self.cog.waiting_approval[interaction.message.id]["ctx"]
        self.cog.waiting_approval[interaction.message.id]["wrongview"].stop()
        event.approver = interaction.user.id
        try:
            await self.cog.post_event(ctx, event)
        except Exception:
            log.exception("Error posting event")
        args = {
            "content": _("{user} has approved this event.").format(user=interaction.user.mention),
            "allowed_mentions": discord.AllowedMentions(users=False),
        }
        await interaction.followup.send(**args)
        await interaction.message.edit(view=None)

    @discord.ui.button(label=_("Deny"), style=discord.ButtonStyle.red)
    async def deny_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message.id not in self.cog.waiting_approval:
            await interaction.response.defer()
            return
        self.stop()
        await interaction.response.defer()
        ctx = self.cog.waiting_approval[interaction.message.id]["ctx"]
        ctx = self.cog.waiting_approval[interaction.message.id]["ctx"]
        msg = _("{author}, your event request was denied by an admin.").format(
            author=ctx.author.mention
        )
        await ctx.reply(msg)
        args = {
            "content": _("{user} has denied this event.").format(user=interaction.user.mention),
            "allowed_mentions": discord.AllowedMentions(users=False),
        }
        if interaction.response.is_done():
            await interaction.followup.send(**args)
        else:
            await interaction.response.send_message(**args)
        await interaction.message.edit(view=None)


class ConfirmView(discord.ui.View):
    def __init__(self, ctx: Union[commands.Context, discord.Interaction]):
        super().__init__()
        self.approved = False
        self.ctx = ctx

    @discord.ui.button(label=_("Yes"), style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.approved = True
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.button(label=_("No"), style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.approved = False
        self.stop()
        await interaction.response.edit_message(view=None)

    async def interaction_check(self, interaction: discord.Interaction):
        if isinstance(self.ctx, discord.Interaction):
            if interaction.user.id != self.ctx.user.id:
                return False
        else:
            if interaction.user.id != self.ctx.author.id:
                return False
        return True


class TimeZones:
    def __init__(self):
        self.zones = {}
        self._last_updated = 0

    def get_zones(self):
        delta = datetime.now() - datetime.fromtimestamp(self._last_updated)
        if not self.zones or delta > timedelta(days=1):
            # only generate a new list of timezones daily
            # This should save some processing time while still
            # giving flexibility based on timezones available
            self.gen_tzinfos()
            return self.zones
        else:
            return self.zones

    def gen_tzinfos(self):
        self._last_updated = datetime.now().timestamp()
        self.zones = {}
        # reset so we don't end up with two timezones present at once daily
        for zone in pytz.common_timezones:
            try:
                tzdate = pytz.timezone(zone).localize(datetime.utcnow(), is_dst=None)
            except pytz.NonExistentTimeError:
                # This catches times that don't exist due to Daylight savings time
                pass
            else:
                tzinfo = gettz(zone)
                self.zones[tzdate.tzname()] = tzinfo
                # store the timezone info into a dict to be returned
                # for the parser to understand common timezone short names


TIMEZONES = TimeZones()


class JoinEventButton(discord.ui.Button):
    def __init__(self, custom_id: str):
        super().__init__(
            style=discord.ButtonStyle.green, label=_("Join Event"), custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        """Join this event"""
        if interaction.user.id in self.view.members:
            await interaction.response.send_message(
                _("You have already registered for this event."), ephemeral=True
            )
            return
        if self.view.max_slots and len(self.view.members) >= self.view.max_slots:
            await interaction.response.send_message(
                _("This event is at the maximum number of members."), ephemeral=True
            )
            return
        if interaction.user.id in self.view.maybe:
            self.view.maybe.remove(interaction.user.id)
        if self.view.thread:
            try:
                thread = interaction.guild.get_thread(self.view.thread)
                if not thread.archived:
                    await thread.add_user(interaction.user)
            except Exception:
                log.exception("Error adding user to event thread")
        self.view.members.append(interaction.user.id)
        self.view.check_join_enabled()
        await self.view.update_event()
        if not interaction.response.is_done():
            await interaction.response.defer()


class LeaveEventButton(discord.ui.Button):
    def __init__(self, custom_id: str):
        super().__init__(
            style=discord.ButtonStyle.red, label=_("Leave Event"), custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        """Leave this event"""
        if interaction.user.id == self.view.hoster:
            new_view = ConfirmView(interaction)
            await interaction.response.send_message(
                content=_("Are you sure you want to end your event?"),
                ephemeral=True,
                view=new_view,
            )
            await new_view.wait()
            if new_view.approved:
                await self.view.end_event()
                await interaction.followup.send(_("Your event has now ended."), ephemeral=True)
            else:
                await interaction.followup.send(_("I will not end this event."), ephemeral=True)
            return
        if interaction.user.id not in self.view.members + self.view.maybe:
            await interaction.response.send_message(
                _("You are not registered for this event."), ephemeral=True
            )
            return
        if self.view.thread:
            try:
                thread = interaction.guild.get_thread(self.view.thread)
                if not thread.archived:
                    await thread.remove_user(interaction.user)
            except Exception:
                log.debug("Error removing user from event thread")
        if interaction.user.id in self.view.members:
            self.view.members.remove(interaction.user.id)
        if interaction.user.id in self.view.maybe:
            self.view.maybe.remove(interaction.user.id)
        self.view.check_join_enabled()

        await self.view.update_event()
        if not interaction.response.is_done():
            await interaction.response.defer()


class PlayerClassSelect(discord.ui.Select):
    def __init__(self, custom_id: str, options: Dict[str, str], placeholder: Optional[str]):
        super().__init__(
            custom_id=custom_id,
            min_values=1,
            max_values=1,
            placeholder=placeholder,
        )
        for option, emoji in options.items():
            self.add_option(label=option, emoji=discord.PartialEmoji.from_str(emoji))

    async def callback(self, interaction: discord.Interaction):
        await self.view.cog.config.member(interaction.user).player_class.set(self.values[0])
        if interaction.user.id in self.view.members:
            self.view.check_join_enabled()
            await self.view.update_event()
            await interaction.response.send_message(
                _("Changing your class to {player_class}.").format(player_class=self.values[0]),
                ephemeral=True,
            )
            return
        if self.view.max_slots and len(self.view.members) >= self.view.max_slots:
            await interaction.response.send_message(
                _("This event is at the maximum number of members."), ephemeral=True
            )
            return
        if interaction.user.id in self.view.maybe:
            self.view.maybe.remove(interaction.user.id)
        if interaction.user.id not in self.view.members:
            self.view.members.append(interaction.user.id)
            if self.view.thread:
                try:
                    thread = interaction.guild.get_thread(self.view.thread)
                    if not thread.archived:
                        await thread.add_user(interaction.user)
                except Exception:
                    log.exception("Error adding user to event thread")
        await self.view.update_event()
        if not interaction.response.is_done():
            await interaction.response.defer()


class MaybeJoinEventButton(discord.ui.Button):
    def __init__(self, custom_id: str):
        super().__init__(
            style=discord.ButtonStyle.grey, label=_("Maybe Join Event"), custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        """Maybe Join this event"""
        if interaction.user.id == self.view.hoster:
            await interaction.response.send_message(
                _("You are hosting this event, you cannot join the maybe queue!"), ephemeral=True
            )
            return
        if interaction.user.id in self.view.members:
            self.view.members.remove(interaction.user.id)
            self.view.check_join_enabled()
        if interaction.user.id in self.view.maybe:
            self.view.maybe.remove(interaction.user.id)
            if self.view.thread:
                try:
                    thread = interaction.guild.get_thread(self.view.thread)
                    await thread.remove_user(interaction.user)
                except Exception:
                    log.exception("Error remove user to event thread")
        else:
            self.view.maybe.append(interaction.user.id)
            if self.view.thread:
                try:
                    thread = interaction.guild.get_thread(self.view.thread)
                    await thread.add_user(interaction.user)
                except Exception:
                    log.exception("Error adding user to event thread")

        await self.view.update_event()
        if not interaction.response.is_done():
            await interaction.response.defer()


class Event(discord.ui.View):
    bot: Red
    hoster: int
    members: List[int]
    event: str
    max_slots: Optional[int]
    approver: Optional[int]
    message: Optional[int]
    channel: Optional[int]
    guild: int
    maybe: List[int]
    start: Optional[datetime]
    thread: Optional[int]

    def __init__(self, **kwargs):
        self.bot = kwargs.get("bot")
        self.hoster = kwargs.get("hoster")
        self.members = kwargs.get("members")
        self.event = kwargs.get("event")
        self.max_slots = kwargs.get("max_slots")
        self.approver = kwargs.get("approver")
        self.message = kwargs.get("message")
        self.channel = kwargs.get("channel")
        self.guild = kwargs.get("guild")
        self.maybe = kwargs.get("maybe", [])
        self.start = kwargs.get("start", None)
        self.select_options = kwargs.get("select_options", {})
        self.thread = kwargs.get("thread")
        self.cog = kwargs.get("cog")
        super().__init__(timeout=None)
        self.join_button = JoinEventButton(custom_id=f"join-{self.hoster}")
        self.leave_button = LeaveEventButton(custom_id=f"leave-{self.hoster}")
        self.maybe_button = MaybeJoinEventButton(custom_id=f"maybejoin-{self.hoster}")
        self.add_item(self.join_button)
        self.add_item(self.maybe_button)
        self.add_item(self.leave_button)
        self.select_view = None
        log.trace("Event select_options: %s", self.select_options)
        if self.select_options:
            self.select_view = PlayerClassSelect(
                custom_id=f"playerclass-{self.hoster}",
                options=self.select_options,
                placeholder=_("Pick a class to join this event"),
            )
            self.add_item(self.select_view)

    def __repr__(self):
        return "<Event description={0.event} hoster={0.hoster} start={0.start}>".format(self)

    def check_join_enabled(self):
        if self.max_slots and len(self.members) >= self.max_slots:
            self.join_button.disabled = True
            self.select_view.disabled = True
            log.trace("Setting Join Button to %s", self.join_button.disabled)
        if self.max_slots and len(self.members) < self.max_slots:
            self.join_button.disabled = False
            self.select_view.disabled = False
            log.debug("Setting Join Button to %s", self.join_button.disabled)

    async def interaction_check(self, interaction: discord.Interaction):
        """
        The interaction pre-check incase I ever need it

        Right now there are no restrictions on joining events
        """
        return True

    async def start_time(self) -> Optional[datetime]:
        date = None
        if self.start is None:
            # assume it's a timedelta first
            # if it's not a timedelta we can try searching for a date
            time_data = {}
            for time in TIME_RE.finditer(self.event):
                for k, v in time.groupdict().items():
                    if v:
                        time_data[k] = int(v)
            if time_data:
                date = datetime.now(timezone.utc) + timedelta(**time_data)
            else:
                try:
                    date, tokens = parser.parse(
                        self.event, fuzzy_with_tokens=True, tzinfos=TIMEZONES.get_zones()
                    )
                    if date and "tomorrow" in self.event.lower():
                        date += timedelta(days=1)
                    date.replace(tzinfo=timezone.utc)
                except Exception:
                    log.debug("Error parsing datetime.")
            if date:
                log.debug("setting start date")
                self.start = date
                return date
            else:
                return None
        else:
            return self.start

    def should_remove(self, seconds: int) -> bool:
        """
        Returns True if we should end the event
        Returns False if the event should stay open
        """
        now = datetime.now(timezone.utc).timestamp()
        if self.message is None:
            # If we don't even have a message linked to this event delete it
            # although in practice this should never happen
            return True
        if self.start:
            future = (self.start + timedelta(seconds=seconds)).timestamp()
            log.verbose("should_remove self.start %s", humanize_timedelta(seconds=future - now))
            return now > future
        else:
            future = (
                snowflake_time(self.message).replace(tzinfo=timezone.utc)
                + timedelta(seconds=seconds)
            ).timestamp()
            log.verbose("should_remove else %s", humanize_timedelta(seconds=future - now))
            return now > future

    def remaining(self, seconds: int) -> str:
        """
        Returns the time remaining on an event
        """
        now = datetime.now(timezone.utc).timestamp()
        if self.message is None:
            # If we don't even have a message linked to this event delete it
            # although in practice this should never happen
            return _("0 seconds")
        if self.start:
            future = (self.start + timedelta(seconds=seconds)).timestamp()
            diff = future - now
            log.debug("Set time self.start future=%s now=%s diff=%s", future, now, diff)
            return humanize_timedelta(seconds=future - now)
        else:
            future = (
                snowflake_time(self.message).replace(tzinfo=timezone.utc)
                + timedelta(seconds=seconds)
            ).timestamp()
            diff = future - now
            log.debug("Message Time ellse future=%s now=%s diff=%s", future, now, diff)
            return humanize_timedelta(seconds=future - now)

    async def update_event(self):
        ctx = await self.get_ctx(self.bot)
        em = await self.make_event_embed(ctx)
        await self.edit(embed=em)
        if self.thread is not None:
            guild = self.bot.get_guild(self.guild)
            thread = guild.get_thread(self.thread)
            if thread.name != self.event[:100]:
                await thread.edit(name=self.event[:100])
        config = self.bot.get_cog("EventPoster").config
        async with config.guild_from_id(int(self.guild)).events() as cur_events:
            cur_events[str(self.hoster)] = self.to_json()
        self.bot.get_cog("EventPoster").event_cache[self.guild][self.message] = self

    async def end_event(self):
        config = self.bot.get_cog("EventPoster").config
        async with config.guild_from_id(int(self.guild)).events() as events:
            # event = Event.from_json(self.bot, events[str(user.id)])
            ctx = await self.get_ctx(self.bot)
            if ctx:
                await self.edit(content=_("This event has ended."), view=None)
            del events[str(self.hoster)]
            del self.bot.get_cog("EventPoster").event_cache[self.guild][self.message]
        if self.thread:
            guild = self.bot.get_guild(int(self.guild))
            if not guild:
                return
            thread = guild.get_thread(self.thread)
            if not thread:
                return
            try:
                await thread.edit(archived=True)
            except Exception:
                pass

    async def get_ctx(self, bot: Red) -> Optional[commands.Context]:
        """
        Returns the context object for the events message

        This can't be used to invoke another command but
        it is useful to get a basis for an events final posted message.
        """
        guild = self.bot.get_guild(self.guild)
        if not guild:
            return None
        chan = guild.get_channel(self.channel)
        if not chan:
            return None
        try:
            msg = await chan.fetch_message(self.message)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            return None
        return await self.bot.get_context(msg)

    async def edit(self, **kwargs) -> None:
        ctx = await self.get_ctx(self.bot)
        view = kwargs.pop("view", self)
        if not ctx:
            return
        await ctx.message.edit(**kwargs, view=view)

    def mention(self, include_maybe: bool):
        members = self.members
        if include_maybe:
            members += self.maybe
        return humanize_list([f"<@!{m}>" for m in members])

    async def make_event_embed(self, ctx: Optional[commands.Context] = None) -> discord.Embed:
        if ctx is None:
            ctx = await self.get_ctx(self.bot)
        hoster = ctx.guild.get_member(self.hoster)
        em = discord.Embed()
        em.set_author(
            name=_("{hoster} is hosting").format(hoster=hoster), icon_url=hoster.display_avatar
        )
        try:
            prefixes = await self.bot.get_valid_prefixes(ctx.guild)
            prefix = prefixes[0]
        except AttributeError:
            prefixes = await self.bot.get_prefix(ctx.message)
            prefix = prefixes[0]
        max_slots_msg = ""
        if self.max_slots:
            slots = self.max_slots - len(self.members)
            if slots < 0:
                slots = 0
            max_slots_msg = _("**{slots} slots available.**").format(slots=slots)
        cog = ctx.bot.get_cog("EventPoster")
        command_name = cog.join_event.qualified_name
        em.description = _(
            "**{description}**\n\nTo join this event type "
            "`{prefix}{command_name} {hoster}` or press the Join Event button below.\n\n"
            "**{max_slots_msg}**"
        ).format(
            description=self.event[:1024],
            command_name=command_name,
            prefix=prefix,
            hoster=hoster,
            max_slots_msg=max_slots_msg,
        )
        player_list = ""
        config = Config.get_conf(None, identifier=144014746356678656, cog_name="EventPoster")
        to_rem = []
        for i, member in enumerate(self.members):
            player_class = ""
            has_player_class = await config.member_from_ids(ctx.guild.id, member).player_class()
            mem = ctx.guild.get_member(member)
            if mem is None:
                to_rem.append(member)
                continue
            if has_player_class:
                player_class = f" - {has_player_class}"
            player_list += _("**Slot {slot_num}**\n{member}{player_class}\n").format(
                slot_num=i + 1, member=mem.mention, player_class=player_class
            )
        for removed_member in to_rem:
            if removed_member in self.members:
                self.members.remove(removed_member)
        for page in pagify(player_list, page_length=1024):
            em.add_field(name=_("Attendees"), value=page)
        if self.maybe and len(em.fields) < 25:
            maybe = []
            to_rem = []
            for m in self.maybe:
                mem = ctx.guild.get_member(m)
                if mem is None:
                    to_rem.append(m)
                    continue
                maybe.append(mem.mention)
            for m_id in to_rem:
                if m_id in self.maybe:
                    self.maybe.remove(m_id)
            em.add_field(name=_("Maybe"), value=humanize_list(maybe))
        if self.approver:
            approver = ctx.guild.get_member(self.approver)
            em.set_footer(
                text=_("Approved by {approver}").format(approver=approver),
                icon_url=approver.display_avatar,
            )
        start = await self.start_time()
        if start is not None:
            em.timestamp = start

        thumbnail = await self.get_thumbnail(ctx)
        if thumbnail:
            em.set_thumbnail(url=thumbnail)
        image = await self.get_image(ctx)
        if image:
            em.set_image(url=image)
        return em

    def get_config(self):
        return Config.get_conf(None, identifier=144014746356678656, cog_name="EventPoster")

    async def get_thumbnail(self, ctx: Optional[commands.Context]) -> Optional[str]:
        if ctx is None:
            ctx = await self.get_ctx(self.bot)
        config = self.get_config()
        thumbnails = await config.guild(ctx.guild).custom_links()
        for name, link in thumbnails.items():
            if re.search(rf"(?i)\b{name}\b", self.event):
                return link
        return None

    async def get_image(self, ctx: Optional[commands.Context]) -> Optional[str]:
        if ctx is None:
            ctx = await self.get_ctx(self.bot)
        config = self.get_config()
        large_links = await config.guild(ctx.guild).large_links()
        for name, link in large_links.items():
            if re.search(rf"(?i)\b{name}\b", self.event):
                return link
        return None

    @classmethod
    def from_json(cls, bot: Red, data: dict):
        members = data.get("members", [])
        new_members = []
        for m in members:
            if isinstance(m, tuple) or isinstance(m, list):
                log.debug("Converting to new members list in %s", data.get("channel"))
                new_members.append(m[0])
            else:
                new_members.append(m)
        start = data.get("start")
        if start:
            start = datetime.fromtimestamp(start, tz=timezone.utc)
        guild = data.get("guild")
        if not guild:
            chan = bot.get_channel(data.get("channel"))
            if chan:
                guild = chan.guild.id
        return cls(
            bot=bot,
            hoster=data.get("hoster"),
            members=new_members,
            event=data.get("event"),
            max_slots=data.get("max_slots"),
            approver=data.get("approver"),
            message=data.get("message"),
            guild=guild,
            channel=data.get("channel"),
            maybe=data.get("maybe"),
            start=start,
            select_options=data.get("select_options"),
            thread=data.get("thread", None),
        )

    def to_json(self):
        return {
            "hoster": self.hoster,
            "members": self.members,
            "event": self.event,
            "max_slots": self.max_slots,
            "approver": self.approver,
            "message": self.message,
            "channel": self.channel,
            "guild": self.guild,
            "maybe": self.maybe,
            "start": int(self.start.timestamp()) if self.start is not None else None,
            "select_options": self.select_options,
            "thread": self.thread,
        }


class ValidImage(Converter):
    async def convert(self, ctx, argument):
        search = IMAGE_LINKS.search(argument)
        if not search:
            raise BadArgument(_("That's not a valid image link."))
        else:
            return argument
