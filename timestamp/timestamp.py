import re
from datetime import datetime, timedelta
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo, available_timezones

import discord
from babel.dates import format_time
from discord.ext.commands.converter import Converter
from discord.utils import format_dt, snowflake_time
from redbot.core import commands, i18n
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify
from redbot.core.utils.views import SimpleMenu

TIMESTAMP_STYLES = ["R", "D", "d", "T", "t", "F", "f"]

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
TIME_SPLIT = re.compile(r"t(?:ime)?=")


class MuteTime(Converter):
    """
    This will parse my defined multi response pattern and provide usable formats
    to be used in multiple reponses
    """

    async def convert(self, ctx: commands.Context, argument: str) -> timedelta:
        time_split = TIME_SPLIT.split(argument)
        if time_split:
            maybe_time = time_split[-1]
        else:
            maybe_time = argument

        time_data = {}
        for time in TIME_RE.finditer(maybe_time):
            argument = argument.replace(time[0], "")
            for k, v in time.groupdict().items():
                if v:
                    time_data[k] = int(v)
        if not time_data:
            raise commands.BadArgument("You need to provide proper relative time info.")
        return timedelta(**time_data)


class AbsoluteTimeFlags(commands.FlagConverter, case_insensitive=True):
    year: int = commands.flag(
        name="year",
        default=0,
        description="The year. Defaults to the current year.",
    )
    month: commands.Range[int, 1, 12] = commands.flag(
        name="month",
        default=0,
        description="The month. Defaults to the current month.",
    )
    day: commands.Range[int, 1, 31] = commands.flag(
        name="day",
        aliases=["d"],
        default=0,
        description="The day. Defaults to the current day.",
    )
    hour: commands.Range[int, 0, 24] = commands.flag(
        name="hour",
        aliases=["hours", "h"],
        default=0,
        description="The hour. Defaults to the current hour.",
    )
    minute: commands.Range[int, 0, 60] = commands.flag(
        name="minute",
        aliases=["minutes", "m"],
        default=0,
        description="The minute. Defaults to 0.",
    )
    second: commands.Range[int, 0, 60] = commands.flag(
        name="second",
        aliases=["seconds", "s"],
        default=0,
        description="The second. Defaults to 0.",
    )

    def datetime(self, tzinfo: ZoneInfo) -> datetime:
        now = datetime.now(tz=tzinfo)
        return datetime(
            year=self.year or now.year,
            month=self.month or now.month,
            day=self.day or now.day,
            hour=self.hour or now.hour,
            minute=self.minute,
            second=self.second,
            tzinfo=tzinfo,
        )


class TimezoneConverter(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> ZoneInfo:
        try:
            return ZoneInfo(argument)
        except Exception:
            raise commands.BadArgument("That is not a valid timezone.")

    async def transform(self, interaction: discord.Interaction, argument: str) -> ZoneInfo:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        choices = [
            discord.app_commands.Choice(name=i, value=i)
            for i in available_timezones()
            if current.lower() in i.lower()
        ]
        return choices[:25]


class Timestamp(commands.Cog):
    """
    A discord timestamp creator cog.
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.1.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_user(timezone=None)
        self._repo = ""
        self._commit = ""

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\n- Cog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"- Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        await self.config.user_from_id(user_id).clear()

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._get_commit()

    async def _get_commit(self):
        if self._repo:
            return
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "timestamp":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    @commands.hybrid_group(name="timestamp", aliases=["ts"])
    async def discord_timestamp(self, ctx: commands.Context):
        """Make your very own discord timestamp!"""
        pass

    def get_timezone_info(self, zone: ZoneInfo) -> str:
        now = datetime.now()
        msg = f"- `{zone.key}`\n - Abbreviation: {zone.tzname(now)}\n"
        utcoffset = zone.utcoffset(now) or timedelta(seconds=0)
        locale = i18n.get_babel_locale()
        # because humanize_timedelta doesn't handle negative timedeltas
        if utcoffset < timedelta(seconds=0):
            msg += f" - UTC Offset: `-{humanize_timedelta(seconds=-utcoffset.total_seconds())}`\n"
        elif utcoffset == timedelta(seconds=0):
            msg += " - UTC Offset: `+0`\n"
        else:
            msg += f" - UTC Offset: `+{humanize_timedelta(timedelta=utcoffset)}`\n"
        if utcoffset is not None:
            tnow = now.astimezone(zone)
            ts_now = format_time(tnow, format="short", locale=locale)
            msg += f" - Time Now: {ts_now}\n"
        return msg

    @staticmethod
    def _chunks(lst: list, n: int):
        # https://stackoverflow.com/a/312464/4438492
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    @discord_timestamp.group(name="timezone", aliases=["tz"], fallback="view")
    async def timezone_commands(
        self,
        ctx: commands.Context,
        timezone: Optional[discord.app_commands.Transform[ZoneInfo, TimezoneConverter]] = None,
    ):
        """
        Timezone related commands
        """
        if timezone is None:
            msg = ""
            now = ctx.message.created_at
            for i in sorted(
                available_timezones(),
                key=lambda x: ZoneInfo(x).utcoffset(now),
            ):
                z = ZoneInfo(i)
                msg += self.get_timezone_info(z) + "\n"

            msgs = []
            pages = list(pagify(msg, page_length=500, delims=["\n\n", "\n"], priority=True))
            if await ctx.embed_requested():
                pages = list(self._chunks(pages, 3))
                for i, tzs in enumerate(pages, start=1):
                    em = discord.Embed(
                        # description=tzs,
                        title="Available Timezones",
                        colour=await ctx.bot.get_embed_colour(ctx),
                    )
                    em.add_field(name=" ", value=tzs[0])
                    if len(tzs) > 1:
                        em.add_field(name=" ", value=tzs[1])
                    if len(tzs) > 2:
                        em.add_field(name=" ", value=tzs[2])
                    em.set_footer(text=f"Page {i}/{len(pages)}")
                    msgs.append(em)
            else:
                msgs = pages
            await SimpleMenu(msgs, use_select_menu=True).start(ctx)
            return
        else:
            await ctx.send(self.get_timezone_info(timezone))

    @timezone_commands.command(name="set")
    async def set_timezone(
        self,
        ctx: commands.Context,
        timezone: discord.app_commands.Transform[ZoneInfo, TimezoneConverter],
    ):
        """
        Set your timezone for conversions

        To see the available timezones use the command:
        - `[p]timestamp timezone`

        Choose the timezone closest to your actual location for best results.
        Timezone names like PST, PT, MDT, MST, etc. are abbreviations and don't
        represent the full daylight saving time calculation. Whereas
        a timezone like `America/Pacific` Will automatically adjust
        for timezones in your location. Unless, of course, you always
        follow a timezone like MST.
        """
        await self.config.user(ctx.author).timezone.set(timezone.key)
        zone_info = self.get_timezone_info(timezone)
        await ctx.send(f"I have set your timezone to `{timezone.key}`.\n{zone_info}")

    @discord_timestamp.command(name="absolute", aliases=["a"])
    async def absolute_timestamp(self, ctx: commands.Context, *, time: AbsoluteTimeFlags):
        """
        Produce an absolute timestamp.

        See `[p]timestamp timezone` to set your timezone so this is accurate for you.
        Usage:
        - `year:` The year you want the timestamp to be for. Defaults to current year if not provided.
        - `month:` The month you want the timestamp to be for. Defaults to current month if not provided.
        - `day:` The day you want the timestamp to be for. Defaults to current day if not provided.
        - `hour:` The hour you want the timestamp to be for. Defaults to current hour if not provided.
        - `minute:` The minute you want the timestamp to be for. Defaults to 0 if not provided.
        - `second:` The second you want the timestamp to be for. Defaults to 0 if not provided.
        Example:
            `[p]ts a year: 2023 month: 7 day: 11 hour: 12`
            Will produce <t:1689076800:F> with no timezone set.
        """
        async with ctx.typing():
            zone = ZoneInfo("UTC")
            msg = ""
            if usertz := await self.config.user(ctx.author).timezone():
                zone = ZoneInfo(usertz)
            else:
                msg += (
                    "You haven't set your timezone yet. "
                    f"See `{ctx.clean_prefix}{self.set_timezone.qualified_name}` to set it.\n"
                )
            try:
                new_time = time.datetime(tzinfo=zone).astimezone(ZoneInfo("UTC"))
            except ValueError as e:
                await ctx.send(e)
                return

            for i in TIMESTAMP_STYLES:
                ts = format_dt(new_time, i)
                msg += f"`{ts}` - {ts}\n"
        await ctx.send(msg)

    @discord_timestamp.command(name="relative", aliases=["r"])
    @discord.app_commands.describe(relative_time="The time relative to now. e.g. in 2 hours.")
    async def relative_timestamp(self, ctx: commands.Context, *, relative_time: MuteTime):
        """
        Produce a timestamp relative to right now.

        Example:
            `[p]ts r in 2 hours`
            Will produce a timestamp 2 hours from the time the command was run.

        """
        async with ctx.typing():
            msg = ""
            for i in TIMESTAMP_STYLES:
                ts = format_dt(ctx.message.created_at + relative_time, i)
                msg += f"`{ts}` - {ts}\n"
        await ctx.send(msg)

    @discord_timestamp.command(name="snowflake", aliases=["s"])
    @discord.app_commands.describe(
        snowflake="A discord ID. e.g. channel ID, user ID, or server ID show their creation date."
    )
    async def snowflake_timestamp(self, ctx: commands.Context, snowflake: int):
        """
        Produce a snowflake's timestamp

        Snowflakes are discord ID's and contain the time of creation within them.
        This command can expose that as discord timestamps.

        Example:
            `[p]ts s 218773382617890828`
            Will produce <t:1472230039:F>.
        """
        async with ctx.typing():
            now = snowflake_time(snowflake)
            msg = ""
            for i in TIMESTAMP_STYLES:
                ts = format_dt(now, i)
                msg += f"`{ts}` - {ts}\n"
        await ctx.send(msg)
