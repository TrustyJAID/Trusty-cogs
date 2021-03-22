import re
import logging
import pytz

from dateutil import parser
from dateutil.tz import gettz
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, cast

from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, pagify, humanize_timedelta
from redbot.core.i18n import Translator, cog_i18n

import discord
from discord.utils import snowflake_time
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

log = logging.getLogger("red.trusty-cogs.EventPoster")

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


class Event:
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

    def __init__(self, **kwargs):
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

    def __repr__(self):
        return "<Event description={0.event} hoster={0.hoster} start={0.start}>".format(self)

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
            future = (
                self.start + timedelta(seconds=seconds)
            ).timestamp()
            log.debug(f"{humanize_timedelta(seconds = future-now)}")
            return now > future
        else:
            future = (
                snowflake_time(self.message).replace(tzinfo=timezone.utc)
                + timedelta(seconds=seconds)
            ).timestamp()
            log.debug(f"{humanize_timedelta(seconds = future-now)}")
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
            future = (
                self.start + timedelta(seconds=seconds)
            ).timestamp()
            diff = future-now
            log.debug(f"Set time {future=} {now=} {diff=}")
            return humanize_timedelta(seconds=future - now)
        else:
            future = (
                snowflake_time(self.message).replace(tzinfo=timezone.utc)
                + timedelta(seconds=seconds)
            ).timestamp()
            diff = future-now
            log.debug(f"Message Time {future=} {now=} {diff=}")
            return humanize_timedelta(seconds=future - now)

    async def get_ctx(self, bot: Red) -> Optional[commands.Context]:
        """
        Returns the context object for the events message

        This can't be used to invoke another command but
        it is useful to get a basis for an events final posted message.
        """
        guild = bot.get_guild(self.guild)
        if not guild:
            return None
        chan = guild.get_channel(self.channel)
        if not chan:
            return None
        try:
            msg = await chan.fetch_message(self.message)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            return None
        return await bot.get_context(msg)

    async def edit(self, context: commands.Context, **kwargs) -> None:
        ctx = await self.get_ctx(context.bot)
        if not ctx:
            return
        await ctx.message.edit(**kwargs)

    def mention(self, include_maybe: bool):
        members = self.members
        if include_maybe:
            members += self.maybe
        return humanize_list([f"<@!{m}>" for m in members])

    async def make_event_embed(self, ctx: commands.Context) -> discord.Embed:
        hoster = ctx.guild.get_member(self.hoster)
        em = discord.Embed()
        em.set_author(
            name=_("{hoster} is hosting").format(hoster=hoster), icon_url=hoster.avatar_url
        )
        try:
            prefixes = await ctx.bot.get_valid_prefixes(ctx.guild)
            prefix = prefixes[0]
        except AttributeError:
            prefixes = await ctx.bot.get_prefix(ctx.message)
            prefix = prefixes[0]
        max_slots_msg = ""
        if self.max_slots:
            slots = self.max_slots - len(self.members)
            if slots < 0:
                slots = 0
            max_slots_msg = _("**{slots} slots available.**").format(slots=slots)

        em.description = _(
            "**{description}**\n\nTo join this event type "
            "`{prefix}join {hoster}` or react to this message with "
            "\N{WHITE HEAVY CHECK MARK}\n\n{max_slots_msg} "
        ).format(
            description=self.event[:1024],
            prefix=prefix,
            hoster=hoster,
            max_slots_msg=max_slots_msg,
        )
        player_list = ""
        config = ctx.bot.get_cog("EventPoster").config
        for i, member in enumerate(self.members):
            player_class = ""
            has_player_class = await config.member_from_ids(ctx.guild.id, member).player_class()
            mem = ctx.guild.get_member(member)
            if has_player_class:
                player_class = f" - {has_player_class}"
            player_list += _("**Slot {slot_num}**\n{member}{player_class}\n").format(
                slot_num=i + 1, member=mem.mention, player_class=player_class
            )
        for page in pagify(player_list, page_length=1024):
            em.add_field(name=_("Attendees"), value=page)
        if self.maybe and len(em.fields) < 25:
            maybe = [f"<@!{m}>" for m in self.maybe]
            em.add_field(name=_("Maybe"), value=humanize_list(maybe))
        if self.approver:
            approver = ctx.guild.get_member(self.approver)
            em.set_footer(
                text=_("Approved by {approver}").format(approver=approver),
                icon_url=approver.avatar_url,
            )
        start = await self.start_time()
        if start is not None:
            em.timestamp = start
        config = Config.get_conf(None, identifier=144014746356678656, cog_name="EventPoster")
        thumbnails = await config.guild(ctx.guild).custom_links()
        for name, link in thumbnails.items():
            if name.lower() in self.event.lower():
                em.set_thumbnail(url=link)
        return em

    @classmethod
    def from_json(cls, bot: Red, data: dict):
        members = data.get("members", [])
        new_members = []
        for m in members:
            if isinstance(m, tuple) or isinstance(m, list):
                log.debug(f"Converting to new members list in {data.get('channel')}")
                new_members.append(m[0])
            else:
                new_members.append(m)
        start = data.get("start")
        if start:
            start = datetime.fromtimestamp(start, tz=timezone.utc)
        guild = data.get("guild")
        if not guild:
            chan = bot.get_channel(data.get("channel"))
            guild = chan.guild.id
        return cls(
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
        }


class ValidImage(Converter):
    async def convert(self, ctx, argument):
        search = IMAGE_LINKS.search(argument)
        if not search:
            raise BadArgument(_("That's not a valid image link."))
        else:
            return argument
