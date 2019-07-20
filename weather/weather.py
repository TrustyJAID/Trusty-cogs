import discord
import datetime
import aiohttp
from urllib.parse import urlencode

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Weather", __file__)


class UnitConverter(Converter):
    async def convert(self, ctx, argument):
        new_units = None
        if argument.lower() in ["f", "imperial", "mph"]:
            new_units = "imperial"
        elif argument.lower() in ["c", "metric", "kph"]:
            new_units = "metric"
        elif argument.lower() in ["k", "kelvin"]:
            new_units = "kelvin"
        elif argument.lower() in ["clear", "none"]:
            new_units = None
        else:
            raise BadArgument(_("`{units}` is not a vaild option!").format(units=argument))
        return new_units


@cog_i18n(_)
class Weather(commands.Cog):
    """Get weather data from https://openweathermap.org"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 138475464)
        default = {"units": None}
        self.config.register_global(**default)
        self.config.register_guild(**default)
        self.config.register_user(**default)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.unit = {
            "imperial": {"code": ["i", "f"], "speed": "mph", "temp": " °F"},
            "metric": {"code": ["m", "c"], "speed": "km/h", "temp": " °C"},
            "kelvin": {"code": ["k", "s"], "speed": "km/h", "temp": " K"},
        }

    @commands.group(name="weather", aliases=["we"], invoke_without_command=True)
    @commands.bot_has_permissions(embed_links=True)
    async def weather(self, ctx, *, location: str):
        """
            Display weather in a given location

            `location` must take the form of `city, Country Code`
            example: `[p]weather New York,US`
        """
        await ctx.trigger_typing()
        await self.get_weather(ctx, location=location)

    @weather.command(name="zip")
    @commands.bot_has_permissions(embed_links=True)
    async def weather_by_zip(self, ctx, *, zipcode: int):
        """
            Display weather in a given location

            `zipcode` must be a valid ZIP code or `ZIP code, Country Code` (assumes US otherwise)
            example: `[p]weather zip 20500`
        """
        await ctx.trigger_typing()
        await self.get_weather(ctx, zipcode=zipcode)

    @weather.command(name="cityid")
    @commands.bot_has_permissions(embed_links=True)
    async def weather_by_cityid(self, ctx, *, cityid: int):
        """
            Display weather in a given location

            `cityid` must be a valid openweathermap city ID
            (get list here: <https://bulk.openweathermap.org/sample/city.list.json.gz>)
            example: `[p]weather cityid 2172797`
        """
        await ctx.trigger_typing()
        await self.get_weather(ctx, cityid=cityid)

    @weather.command(name="co", aliases=["coords", "coordinates"])
    @commands.bot_has_permissions(embed_links=True)
    async def weather_by_coordinates(self, ctx, lat: float, lon: float):
        """
            Display weather in a given location

            `lat` and `lon` specify a precise point on Earth using the
            geographic coordinates specified by latitude (north-south) and longitude (east-west).
            example: `[p]weather coordinates 35 139`
        """
        await ctx.trigger_typing()
        await self.get_weather(ctx, lat=lat, lon=lon)

    @commands.group(name="weatherset")
    async def weather_set(self, ctx):
        """Set user or guild default units"""
        pass

    @weather_set.command(name="guild", aliases=["server"])
    @checks.mod_or_permissions(manage_messages=True)
    async def set_guild(self, ctx, units: UnitConverter):
        """
            Sets the guild default weather units

            `units` must be one of imperial, metric, or kelvin
        """
        guild = ctx.message.guild
        await self.config.guild(guild).units.set(units)
        await ctx.send(_("Server's default units set to `{units}`").format(units=str(units)))

    @weather_set.command(name="bot")
    @checks.mod_or_permissions(manage_messages=True)
    async def set_bot(self, ctx, units: UnitConverter):
        """
            Sets the bots default weather units

            `units` must be one of imperial, metric, or kelvin
        """
        await self.config.units.set(units)
        await ctx.send(_("Bots default units set to {units}").format(units=str(units)))

    @weather_set.command(name="user")
    async def set_user(self, ctx, units: UnitConverter):
        """
            Sets the user default weather units

            `units` must be one of imperial, metric, or kelvin
            Note: User settings override guild settings.
        """
        author = ctx.message.author
        await self.config.user(author).units.set(units)
        await ctx.send(
            _("{author} default units set to `{units}`").format(
                author=author.display_name, units=str(units)
            )
        )

    async def get_weather(
        self, ctx, *, location=None, zipcode=None, cityid=None, lat=None, lon=None
    ):
        guild = ctx.message.guild
        author = ctx.message.author
        bot_units = await self.config.units()
        guild_units = None
        if guild:
            guild_units = await self.config.guild(guild).units()
        user_units = await self.config.user(author).units()
        units = "imperial"
        if bot_units:
            units = bot_units
        if guild_units:
            units = guild_units
        if user_units:
            units = user_units
        params = {"appid": "88660f6af079866a3ef50f491082c386", "units": units}
        if units == "kelvin":
            params["units"] = "metric"
        if zipcode:
            params["zip"] = zipcode
        elif cityid:
            params["id"] = cityid
        elif lon and lat:
            params["lat"] = lat
            params["lon"] = lon
        else:
            params["q"] = location
        url = "https://api.openweathermap.org/data/2.5/weather?{0}".format(urlencode(params))
        async with self.session.get(url) as resp:
            data = await resp.json()
        try:
            if data["message"] == "city not found":
                await ctx.send("City not found.")
                return
        except Exception:
            pass
        currenttemp = data["main"]["temp"]
        mintemp = data["main"]["temp_min"]
        maxtemp = data["main"]["temp_max"]
        city = data["name"]
        try:
            country = data["sys"]["country"]
        except KeyError:
            country = ""
        lat, lon = data["coord"]["lat"], data["coord"]["lon"]
        condition = ", ".join(info["main"] for info in data["weather"])
        windspeed = str(data["wind"]["speed"]) + " " + self.unit[units]["speed"]
        if units == "kelvin":
            currenttemp = abs(currenttemp - 273.15)
            mintemp = abs(maxtemp - 273.15)
            maxtemp = abs(maxtemp - 273.15)
        sunrise = datetime.datetime.utcfromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M")
        sunset = datetime.datetime.utcfromtimestamp(data["sys"]["sunset"]).strftime("%H:%M")
        embed = discord.Embed(colour=discord.Colour.blue())
        if len(city) and len(country):
            embed.add_field(name=_("🌍 **Location**"), value="{0}, {1}".format(city, country))
        else:
            embed.add_field(
                name=_("\N{EARTH GLOBE AMERICAS} **Location**"), value=_("*Unavailable*")
            )
        embed.add_field(
            name=_("\N{STRAIGHT RULER} **Lat,Long**"), value="{0}, {1}".format(lat, lon)
        )
        embed.add_field(name=_("\N{CLOUD} **Condition**"), value=condition)
        embed.add_field(
            name=_("\N{FACE WITH COLD SWEAT} **Humidity**"), value=data["main"]["humidity"]
        )
        embed.add_field(name=_("\N{DASH SYMBOL} **Wind Speed**"), value="{0}".format(windspeed))
        embed.add_field(
            name=_("\N{THERMOMETER} **Temperature**"),
            value="{0:.2f}{1}".format(currenttemp, self.unit[units]["temp"]),
        )
        embed.add_field(
            name=_("\N{HIGH BRIGHTNESS SYMBOL} **Min - Max**"),
            value="{0:.2f}{1} to {2:.2f}{3}".format(
                mintemp, self.unit[units]["temp"], maxtemp, self.unit[units]["temp"]
            ),
        )
        embed.add_field(name=_("\N{SUNRISE OVER MOUNTAINS} **Sunrise (UTC)**"), value=sunrise)
        embed.add_field(name=_("\N{SUNSET OVER BUILDINGS} **Sunset (UTC)**"), value=sunset)
        embed.set_footer(text=_("Powered by https://openweathermap.org"))
        await ctx.send(embed=embed)

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    __unload = cog_unload
