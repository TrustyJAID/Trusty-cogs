from __future__ import annotations

from typing import Literal, Optional

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import Config, checks, commands, i18n
from redbot.core.utils.views import SetApiView

from .api import HEADERS, APIError, Geocoding, Units
from .menus import BaseMenu, WeatherPages

_ = i18n.Translator("Weather", __file__)

log = getLogger("red.Trusty-cogs.weather")


@i18n.cog_i18n(_)
class Weather(commands.Cog):
    """Get weather data from https://openweathermap.org"""

    __author__ = ["TrustyJAID"]
    __version__ = "1.5.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 138475464)
        self.config.register_global(units=None, api_version="2.5")
        self.config.register_guild(units=None)
        self.config.register_user(units=None)
        self.session = aiohttp.ClientSession(headers=HEADERS)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_unload(self):
        await self.session.close()

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        await self.config.user_from_id(user_id).clear()

    async def get_units(self, ctx: commands.Context) -> Units:
        bot_units = await self.config.units()
        guild_units = None
        if ctx.guild:
            guild_units = await self.config.guild(ctx.guild).units()
        user_units = await self.config.user(ctx.author).units()
        units = Units("metric")
        if bot_units:
            units = Units(bot_units)
        if guild_units:
            units = Units(guild_units)
        if user_units:
            units = Units(user_units)
        return units

    async def get_lang(self, ctx: commands.Context) -> Optional[str]:
        if not ctx.interaction:
            locale = await i18n.get_locale_from_guild(self.bot, ctx.guild)
            if locale:
                return locale.replace("-", "_")
            return None
        lang = str(ctx.interaction.locale)
        return lang.replace("-", "_")

    async def get_appid(self, ctx: commands.Context) -> Optional[str]:
        tokens = await self.bot.get_shared_api_tokens("openweathermap")
        appid = tokens.get("api_key")
        if appid is None:
            await ctx.send(
                _(
                    "The bot owner needs to set an api key. See `{prefix}weather set creds`."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        return appid

    @commands.hybrid_group(name="weather", aliases=["we"], fallback="location")
    @discord.app_commands.describe(
        search="city, state, country code format",
        forecast="Whether or not to include the 5 day forecast information",
        units="The units to display, standard is kelvin",
    )
    async def weather(
        self,
        ctx: commands.Context,
        forecast: Optional[bool],
        units: Optional[Units],
        *,
        search: str,
    ) -> None:
        """
        Display weather in a given location

        `search` must take the form of `city, state, Country Code`
        example: `[p]weather New York, New York, US`
        """
        async with ctx.typing():
            appid = await self.get_appid(ctx)
            if appid is None:
                return
            if not units:
                units = await self.get_units(ctx)
            lang = await self.get_lang(ctx)
            try:
                resp = await Geocoding.get(appid, search, limit=5, session=self.session)
            except APIError as e:
                await ctx.send(_("Error Retrieving Location: {error}").format(error=e))
                return
            if not resp:
                await ctx.send(_("No locations found matching `{search}`.").format(search=search))
                return
        api_version = await self.config.api_version()
        await BaseMenu(
            appid=appid,
            source=WeatherPages(resp, units, lang, forecast, api_version=api_version),
            session=self.session,
        ).start(ctx=ctx)

    @weather.command(name="zip")
    @discord.app_commands.describe(
        zipcode="zip/postal code, country code format",
        forecast="Whether or not to include the 5 day forecast information",
        units="The units to display, standard is kelvin",
    )
    async def weather_by_zip(
        self,
        ctx: commands.Context,
        forecast: Optional[bool],
        units: Optional[Units],
        *,
        zipcode: str,
    ) -> None:
        """
        Display weather in a given location

        `zipcode` must be a valid ZIP code or `ZIP code, Country Code` (assumes US otherwise)
        example: `[p]weather zip 20500`
        """
        async with ctx.typing():
            appid = await self.get_appid(ctx)
            if appid is None:
                return
            if not units:
                units = await self.get_units(ctx)
            lang = await self.get_lang(ctx)
            try:
                resp = await Geocoding.get_zip(appid=appid, zipcode=zipcode, session=self.session)
            except APIError as e:
                await ctx.send(_("Error Retrieving Location: {error}").format(error=e))
                return
        api_version = await self.config.api_version()
        await BaseMenu(
            appid=appid,
            source=WeatherPages([resp], units, lang, forecast, api_version=api_version),
            session=self.session,
        ).start(ctx=ctx)

    @weather.command(name="coords", aliases=["co", "coordinates"])
    @discord.app_commands.describe(
        lat="The latitude",
        lon="The longitude",
        forecast="Whether or not to include the 5 day forecast information",
        units="The units to display, standard is kelvin",
    )
    async def weather_by_coordinates(
        self,
        ctx: commands.Context,
        forecast: Optional[bool],
        units: Optional[Units],
        lat: float,
        lon: float,
    ) -> None:
        """
        Display weather in a given location

        `lat` and `lon` specify a precise point on Earth using the
        geographic coordinates specified by latitude (north-south) and longitude (east-west).
        example: `[p]weather coordinates 35 139`
        """
        async with ctx.typing():
            appid = await self.get_appid(ctx)
            if appid is None:
                return
            if not units:
                units = await self.get_units(ctx)
            lang = await self.get_lang(ctx)
            try:
                resp = await Geocoding.reverse(
                    appid, lat=lat, lon=lon, limit=5, session=self.session
                )
            except APIError as e:
                await ctx.send(_("Error Retrieving Location: {error}").format(error=e))
                return
            if not resp:
                await ctx.send(
                    _("No locations found matching `{lat}, {lon}`.").format(lat=lat, lon=lon)
                )
                return
        api_version = await self.config.api_version()
        await BaseMenu(
            appid=appid,
            source=WeatherPages(resp, units, lang, forecast, api_version=api_version),
            session=self.session,
        ).start(ctx=ctx)

    @weather.group(name="set")
    async def weather_set(self, ctx: commands.Context) -> None:
        """Set user or guild default units"""
        pass

    @weather_set.command(name="guild", aliases=["server"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_guild(self, ctx: commands.Context, units: Units) -> None:
        """
        Sets the guild default weather units

        `units` must be one of imperial, metric, or standard (kelvin)
        """
        guild = ctx.message.guild
        await self.config.guild(guild).units.set(units.name)
        await ctx.send(_("Server's default units set to `{units}`").format(units=units.name))

    @weather_set.command(name="bot")
    @checks.mod_or_permissions(manage_messages=True)
    async def set_bot(self, ctx: commands.Context, units: Units) -> None:
        """
        Sets the bots default weather units

        `units` must be one of imperial, metric, or standard (kelvin)
        """
        await self.config.units.set(units.name)
        await ctx.send(_("Bots default units set to {units}").format(units=units.name))

    @weather_set.command(name="user")
    async def set_user(self, ctx: commands.Context, units: Units) -> None:
        """
        Sets the user default weather units

        `units` must be one of imperial, metric, or standard (kelvin)
        Note: User settings override guild settings.
        """
        author = ctx.message.author
        await self.config.user(author).units.set(units.name)
        await ctx.send(
            _("{author} default units set to `{units}`").format(
                author=author.display_name, units=units.name
            )
        )

    @weather_set.command(name="version", with_app_command=False)
    @commands.is_owner()
    async def set_api_version(self, ctx: commands.Context, version: Optional[str] = None):
        """
        Customise the API version used by the cog.

        This is mainly to setup using the new OneCall 3.0 version but that requires
        a valid credit card setup on the account even for the free tier.
        By default we will try to use the 2.5 OneCall API which has historically
        only required the basic free tier account for an API token.
        """
        if version is None:
            await self.config.api_version.clear()
            await ctx.send(_("I will attempt to use the `2.5` OneCall API."))
            return
        await self.config.api_version.set(version)
        await ctx.send(
            _("I will attempt to use the `{version}` OneCall API.").format(version=version)
        )

    @weather_set.command(name="creds", with_app_command=False)
    @commands.is_owner()
    async def weather_creds(self, ctx: commands.Context):
        """
        How to setup the weather cog credentials

        1. go to https://openweathermap.org
        2. Create an account.
        3. go to https://home.openweathermap.org/api_keys
        4. Enter an API key name and click Generate
        5. Copy the key and run `[p]set api openweathermap api_key YOUR_API_KEY_HERE`
        6. go to https://home.openweathermap.org/subscriptions and Subscribe to One Call by Call
        """
        msg = _(
            "1. go to https://openweathermap.org\n"
            "2. Create an account.\n"
            "3. go to https://home.openweathermap.org/api_keys\n"
            "4. Enter an API key name and click Generate\n"
            "5. Copy the key and run `{prefix}set api openweathermap api_key YOUR_API_KEY_HERE`\n"
            "6. go to https://home.openweathermap.org/subscriptions and Subscribe to One Call by Call\n"
        ).format(prefix=ctx.clean_prefix)
        keys = {"api_key": ""}
        view = SetApiView("openweathermap", keys)
        if await ctx.embed_requested():
            em = discord.Embed(description=msg)
            await ctx.send(embed=em, view=view)
        else:
            await ctx.send(msg, view=view)
