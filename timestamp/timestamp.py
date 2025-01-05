from datetime import datetime, timedelta
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo, available_timezones

import discord
from babel.dates import format_time, get_timezone_location, get_timezone_name
from discord.utils import format_dt, snowflake_time
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import commands, i18n
from redbot.core.commands.converter import RelativedeltaConverter
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import box, humanize_timedelta, pagify
from redbot.core.utils.views import SimpleMenu

TIMESTAMP_STYLES = ["R", "D", "d", "T", "t", "F", "f"]

RELATIVE_CONVERTER = RelativedeltaConverter(
    allowed_units=["years", "months", "weeks", "days", "hours", "minutes", "seconds"]
)

_ = i18n.Translator("Timestamp", __file__)

log = getLogger("red.trusty-cogs.timestamp")


class TimezoneConverter(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> ZoneInfo:
        if "/" in argument:
            try:
                return ZoneInfo(argument)
            except Exception:
                raise commands.BadArgument(_("That is not a valid timezone."))
        locale = i18n.get_babel_locale()
        now = datetime.now()
        cog = ctx.bot.get_cog("Timestamp")
        at = cog.at
        for zone in at:
            tnow = now.astimezone(ZoneInfo(zone))
            try:
                name = get_timezone_name(tnow, locale=locale)
                short = get_timezone_name(tnow, width="short", locale=locale)
                tz = f"{short} {name} ({zone})"
            except LookupError:
                continue
            if len(argument) <= 3 and argument.lower() == short.lower():
                return ZoneInfo(zone)
            elif argument.lower() in tz.lower():
                return ZoneInfo(zone)
        raise commands.BadArgument(_("That is not a valid timezone."))

    async def transform(self, interaction: discord.Interaction, argument: str) -> ZoneInfo:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        g_locale = await i18n.get_locale_from_guild(interaction.client, interaction.guild)
        locale = i18n.get_babel_locale(g_locale)
        choices = []
        now = datetime.now()
        cog = interaction.client.get_cog("Timestamp")
        at = cog.at
        for zone in at:
            tnow = now.astimezone(ZoneInfo(zone))
            zone_name = zone
            try:
                name = get_timezone_name(tnow, locale=locale)
                short = get_timezone_name(tnow, width="short", locale=locale)
                ts_now = format_time(tnow, format="short", locale=locale)
                zone_name = f"{short} {name} ({zone}) {ts_now}"
            except Exception:
                pass
            if current.lower() in zone_name.lower():
                choices.append(discord.app_commands.Choice(name=zone_name, value=zone))
        return choices[:25]


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
    timezone: Optional[ZoneInfo] = commands.flag(
        name="timezone",
        aliases=["tz"],
        default=None,
        description="The base timezone referenced.",
        converter=TimezoneConverter,
    )

    def datetime(self, tzinfo: ZoneInfo) -> datetime:
        now = datetime.now(tz=self.timezone or tzinfo)
        return datetime(
            year=self.year or now.year,
            month=self.month or now.month,
            day=self.day or now.day,
            hour=self.hour or now.hour,
            minute=self.minute,
            second=self.second,
            tzinfo=tzinfo,
        )


class Timestamp(commands.Cog):
    """
    A discord timestamp creator cog.
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.3.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_user(timezone=None)
        self._repo = ""
        self._commit = ""
        self.at = available_timezones()
        # cache these since it opens a lot of files

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

    async def cog_load(self):
        if version_info > VersionInfo.from_str("3.5.9"):
            self.discord_timestamp.app_command.allowed_contexts = (
                discord.app_commands.installs.AppCommandContext(
                    guild=True, dm_channel=True, private_channel=True
                )
            )
            self.discord_timestamp.app_command.allowed_installs = (
                discord.app_commands.installs.AppInstallationType(guild=True, user=True)
            )

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
        locale = i18n.get_babel_locale()
        now = datetime.now().astimezone(zone)
        zone_name = zone.key
        short = zone.tzname(now)
        location = None
        try:
            zone_name = get_timezone_name(now, locale=locale)
            short = get_timezone_name(now, width="short", locale=locale)
            location = get_timezone_location(now, locale=locale)
        except LookupError:
            log.error("Error parsing timezone %s", zone.key)
        include = {"key": zone.key, "name": zone_name, "short": short}
        translate = {
            "key": _("Key"),
            "name": _("Name"),
            "short": _("Short"),
            "offset": _("UTC Offset"),
            "location": _("Location"),
            "now": _("Time Now"),
        }
        utcoffset = zone.utcoffset(now) or timedelta(seconds=0)

        # because humanize_timedelta doesn't handle negative timedeltas
        if utcoffset < timedelta(seconds=0):
            include["offset"] = f"`-{humanize_timedelta(seconds=-utcoffset.total_seconds())}`"
        elif utcoffset == timedelta(seconds=0):
            include["offset"] = "`+0`"
        else:
            include["offset"] = f"`+{humanize_timedelta(timedelta=utcoffset)}`"
        if utcoffset is not None:
            ts_now = format_time(now, format="short", locale=locale)
            include["now"] = ts_now
        if location is not None:
            include["location"] = location
        msg = ""
        for key, value in include.items():
            name = translate[key]
            if key == "key":
                msg += f"- {value}\n"
                continue
            msg += f" - {name}: {value}\n"

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
                self.at,
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
                        title=_("Available Timezones"),
                        colour=await ctx.bot.get_embed_colour(ctx),
                    )
                    em.add_field(name=" ", value=tzs[0])
                    if len(tzs) > 1:
                        em.add_field(name=" ", value=tzs[1])
                    if len(tzs) > 2:
                        em.add_field(name=" ", value=tzs[2])
                    em.set_footer(
                        text=_("Page {current}/{total}").format(current=i, total=len(pages))
                    )
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
        timezone_name = timezone.key
        await ctx.send(
            _("I have set your timezone to `{timezone_name}`.\n{zone_info}").format(
                timezone_name=timezone_name, zone_info=zone_info
            )
        )

    async def send_all_styles(self, ctx: commands.Context, new_time: datetime, *, msg: str = ""):
        msg += f"ISO\n{box(new_time.isoformat())}"
        for i in TIMESTAMP_STYLES:
            ts = format_dt(new_time, i)
            msg += f"{ts}\n{box(ts)}"
        await ctx.maybe_send_embed(msg)

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
                zone = time.timezone or ZoneInfo(usertz)
            else:
                command = f"`{ctx.clean_prefix}{self.set_timezone.qualified_name}`"
                msg += _("You haven't set your timezone yet. See {command} to set it.").format(
                    command=command
                )
            try:
                locale = i18n.get_babel_locale()
                new_time = time.datetime(tzinfo=zone).astimezone(ZoneInfo("UTC"))
                from_tz = get_timezone_name(time.datetime(tzinfo=zone), locale=locale)
                short_from_tz = get_timezone_name(
                    time.datetime(tzinfo=zone), width="short", locale=locale
                )
                to_tz = get_timezone_name(new_time, locale=locale)
                short_to_tz = get_timezone_name(new_time, width="short", locale=locale)
            except ValueError as e:
                await ctx.send(e)
                return
        await self.send_all_styles(
            ctx, new_time, msg=f"{msg}\n{from_tz} ({short_from_tz}) to {to_tz} ({short_to_tz})\n"
        )

    @discord_timestamp.command(name="relative", aliases=["r"])
    @discord.app_commands.describe(relative_time="The time relative to now. e.g. in 2 hours.")
    async def relative_timestamp(
        self, ctx: commands.Context, *, relative_time: RELATIVE_CONVERTER
    ):
        """
        Produce a timestamp relative to right now.

        Accepts: `years`, `months`, `weeks`, `days`, `hours`, `minutes`, and `seconds`.

        Example:
            `[p]ts r 2 hours`
            Will produce a timestamp 2 hours from the time the command was run.

        """
        await ctx.typing()
        new_time = ctx.message.created_at + relative_time
        td = humanize_timedelta(timedelta=new_time - ctx.message.created_at)
        # convert back to a timedelta from the relativedelta and humanize
        await self.send_all_styles(ctx, new_time, msg=f"{td}\n")

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
        await ctx.typing()
        new_time = snowflake_time(snowflake)
        await self.send_all_styles(ctx, new_time, msg=f"Discord ID `{snowflake}`\n")
