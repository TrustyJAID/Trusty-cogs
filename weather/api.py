from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Union

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import i18n
from redbot.core.utils.chat_formatting import humanize_list

_ = i18n.Translator("Weather", __file__)

log = getLogger("red.Trusty-cogs.weather")


HEADERS = {"User-Agent": "Trusty-cogs Weather cog for Red-DiscordBot"}

WIND_DIRECTION = {
    0: "N",
    1: "N/NE",
    2: "NE",
    3: "E/NE",
    4: "E",
    5: "E/SE",
    6: "SE",
    7: "S/SE",
    8: "S",
    9: "S/SW",
    10: "SW",
    11: "W/SW",
    12: "W",
    13: "W/NW",
    14: "NW",
    15: "N/NW",
    16: "N",
}

MOONS = {
    0: "\N{NEW MOON SYMBOL}",
    1: "\N{WAXING CRESCENT MOON SYMBOL}",
    2: "\N{FIRST QUARTER MOON SYMBOL}",
    3: "\N{WAXING GIBBOUS MOON SYMBOL}",
    4: "\N{FULL MOON SYMBOL}\N{VARIATION SELECTOR-16}",
    5: "\N{WANING GIBBOUS MOON SYMBOL}",
    6: "\N{LAST QUARTER MOON SYMBOL}",
    7: "\N{WANING CRESCENT MOON SYMBOL}",
}

WEATHER_EMOJIS = {
    200: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # thunderstorm with light rain
    201: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # thunderstorm with rain
    202: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # thunderstorm with heavy rain
    210: "\N{CLOUD WITH LIGHTNING}\N{VARIATION SELECTOR-16}",  # light thunderstorm
    211: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # thunderstorm
    212: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # heavy thunderstorm
    221: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # ragged thunderstorm
    230: "\N{CLOUD WITH LIGHTNING}\N{VARIATION SELECTOR-16}",  # thunderstorm with light drizzle
    231: "\N{CLOUD WITH LIGHTNING}\N{VARIATION SELECTOR-16}",  # thunderstorm with drizzle
    232: "\N{THUNDER CLOUD AND RAIN}\N{VARIATION SELECTOR-16}",  # thunderstorm with heavy drizzle
    300: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # light intensity drizzle
    301: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # drizzle
    302: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # heavy intensity drizzle
    310: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # light intensity drizzle rain
    311: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # drizzle rain
    312: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # heavy intensity drizzle rain
    313: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # shower rain and drizzle
    314: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # heavy shower rain and drizzle
    321: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # shower drizzle
    500: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # light rain
    501: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # moderate rain
    502: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # heavy intensity rain
    503: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # very heavy rain
    504: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # extreme rain
    511: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # freezing rain
    520: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # light intensity shower rain
    521: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # shower rain
    522: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # heavy intensity shower rain
    531: "\N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16}",  # ragged shower rain
    600: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # light snow
    601: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Snow
    602: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Heavy snow
    611: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Sleet
    612: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Light shower sleet
    613: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Shower sleet
    615: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Light rain and snow
    616: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Rain and snow
    620: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Light shower snow
    621: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Shower snow
    622: "\N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16}",  # Heavy shower snow
    701: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Mist    mist
    711: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Smoke   Smoke
    721: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Haze    Haze
    731: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Dust    sand/ dust whirls
    741: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Fog fog
    751: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Sand    sand
    761: "\N{FOG}\N{VARIATION SELECTOR-16}",  # Dust    dust
    762: "\N{VOLCANO}",  # Ash volcanic ash
    771: "\N{CLOUD WITH TORNADO}\N{VARIATION SELECTOR-16}",  # Squall  squalls
    781: "\N{CLOUD WITH TORNADO}\N{VARIATION SELECTOR-16}",  # Tornado tornado
    800: "\N{BLACK SUN WITH RAYS}\N{VARIATION SELECTOR-16}",
    801: "\N{WHITE SUN WITH SMALL CLOUD}\N{VARIATION SELECTOR-16}",  # Clouds  few clouds: 11-25%
    802: "\N{SUN BEHIND CLOUD}",  # Clouds  scattered clouds: 25-50%
    803: "\N{WHITE SUN BEHIND CLOUD}\N{VARIATION SELECTOR-16}",  # Clouds  broken clouds: 51-84%
    804: "\N{CLOUD}\N{VARIATION SELECTOR-16}",  # Clouds  overcast clouds: 85-100%
}

CLOUD_RANGES = {
    0: range(0, 11),
    1: range(11, 26),
    2: range(26, 51),
    3: range(51, 85),
    4: range(85, 101),
}


def get_cloud_num(cloudiness: int) -> int:
    for key, value in CLOUD_RANGES.items():
        if cloudiness in value:
            return 800 + key
    return 800


class APIError(Exception):
    pass


@dataclass
class Unit:
    code: List[str]
    speed: str
    temp: str


class Units(Enum):
    standard = "standard"
    metric = "metric"
    imperial = "imperial"

    def __str__(self):
        return self.name

    def get(self) -> Unit:
        if self.name == "metric":
            return Unit(code=["m", "c"], speed="m/s", temp=" °C")
        if self.name == "imperial":
            return Unit(code=["i", "f"], speed="mph", temp=" °F")
        return Unit(code=["k", "s"], speed="m/s", temp=" K")


class Coords(NamedTuple):
    lon: float
    lat: float

    def __str__(self):
        coords = f"[{self.lat:.2f}, {self.lon:.2f}]({self.url})"
        return coords

    @property
    def url(self):
        return f"https://www.google.com/maps/search/?api=1&query={self.lat}%2C{self.lon}"


@dataclass
class WeatherType:
    id: int
    main: str
    description: str
    icon: str

    @property
    def icon_url(self):
        return f"http://openweathermap.org/img/wn/{self.icon}@4x.png"

    @property
    def emoji(self) -> str:
        return WEATHER_EMOJIS.get(self.id, "")


@dataclass
class Precipitation:
    h1: Optional[int]
    h3: Optional[int]

    def __str__(self):
        strings = []
        if self.h1:
            strings.append(f"1h {self.h1} mm")
        if self.h3:
            strings.append(f"3h {self.h3} mm")
        return "-".join(strings)


@dataclass
class Geocoding:
    def __init__(self, **kwargs):
        self.name: Optional[str] = kwargs.get("name")
        self.lat: Optional[float] = kwargs.get("lat")
        self.lon: Optional[float] = kwargs.get("lon")
        self.country: Optional[str] = kwargs.get("country")
        self.local_names: Optional[Dict[str, str]] = kwargs.get("local_names")
        self.state: Optional[str] = kwargs.get("state")
        self.zipcode: Optional[str] = kwargs.get("zipcode")

    @property
    def location(self):
        if self.state:
            return f"{self.name}, {self.state}, {self.country}"
        return f"{self.name}, {self.country}"

    @classmethod
    def from_json(cls, data: dict) -> Geocoding:
        return cls(**data)

    @classmethod
    async def get(
        cls,
        appid: str,
        search: str,
        limit: int,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> List[Geocoding]:
        url = "http://api.openweathermap.org/geo/1.0/direct"
        params = {
            "q": search,
            "appid": appid,
            "limit": limit,
        }
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        else:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        if "cod" in data and data["cod"] != "200":
            raise APIError(data["message"])
        return [cls.from_json(i) for i in data]

    @classmethod
    async def get_zip(
        cls,
        appid: str,
        zipcode: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Geocoding:
        url = "http://api.openweathermap.org/geo/1.0/zip"
        params = {
            "zip": zipcode,
            "appid": appid,
        }
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        else:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        log.debug("Zipcode get data: %s", data)
        if "cod" in data and data["cod"] != "200":
            raise APIError(data["message"])

        return cls.from_json(data)

    @classmethod
    async def reverse(
        cls,
        appid: str,
        lat: float,
        lon: float,
        limit: int,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> List[Geocoding]:
        url = "http://api.openweathermap.org/geo/1.0/reverse"
        params = {
            "lat": str(lat),
            "lon": str(lon),
            "appid": appid,
            "limit": limit,
        }
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        else:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        if "cod" in data and data["cod"] != "200":
            raise APIError(data["message"])
        return [cls.from_json(i) for i in data]


@dataclass
class Temperature:
    def __init__(self, **kwargs):
        self.units: Units = kwargs.get("units", Units.standard)
        self.day: Optional[float] = kwargs.get("day")
        self.night: Optional[float] = kwargs.get("night")
        self.eve: Optional[float] = kwargs.get("eve")
        self.morn: Optional[float] = kwargs.get("morn")
        self.min: Optional[float] = kwargs.get("min")
        self.max: Optional[float] = kwargs.get("max")

    def __str__(self):
        if self.min and self.max:
            return f"{self.min}-{self.max} {self.units.get().temp}"
        return f"{self.max} {self.units.get().temp}"

    @classmethod
    def from_data(cls, data: Union[dict, float], units: Units):
        if isinstance(data, dict):
            return cls(**data, units=units)
        return cls(max=data, units=units)


@dataclass
class CurrentWeather:
    def __init__(self, **kwargs):
        self.dt: Optional[int] = kwargs.get("dt")
        self.temp: Optional[float] = kwargs.get("temp")
        self.feels_like: Optional[float] = kwargs.get("feels_like")
        self.pressure: Optional[int] = kwargs.get("pressure")
        self.humidity: Optional[int] = kwargs.get("humidity")
        self.dew_point: Optional[float] = kwargs.get("dew_point")
        self.uvi: Optional[float] = kwargs.get("uvi")
        self.clouds: Optional[int] = kwargs.get("clouds")
        self.wind_speed: Optional[float] = kwargs.get("wind_speed")
        self.wind_deg: Optional[int] = kwargs.get("wind_deg")
        self.weather: List[WeatherType] = kwargs.get("weather", [])
        self.units: Units = kwargs.get("units", Units.standard)
        self.visibility: Optional[int] = kwargs.get("visibility")
        self.sunrise: Optional[int] = kwargs.get("sunrise")
        self.sunset: Optional[int] = kwargs.get("sunset")
        self.wind_gust: Optional[float] = kwargs.get("wind_gust")
        self.rain: Optional[Union[Precipitation, float]] = kwargs.get("rain")
        self.snow: Optional[Union[Precipitation, float]] = kwargs.get("snow")

    def __str__(self):
        sunrise_ts = f"<t:{self.sunrise}:t>" if self.sunrise else _("No Data")
        sunset_ts = f"<t:{self.sunset}:t>" if self.sunset else _("No Data")
        windspeed = str(self.wind_speed) + " " + self.units.get().speed
        wind_gust = ""
        cloudiness_emoji = WEATHER_EMOJIS[get_cloud_num(self.clouds or 0)]
        if self.wind_gust:
            wind_gust = (
                _("  - \N{WIND BLOWING FACE}\N{VARIATION SELECTOR-16} **Wind Gusts**: ")
                + f"{self.wind_gust} {self.units.get().speed}\n"
            )
        ret = _(
            "- {weather_emoji} **Weather**: {weather}\n"
            "- \N{FACE WITH COLD SWEAT} **Humidity**: {humidity}%\n"
            "- \N{DASH SYMBOL} **Wind Speed**: {wind_speed} {direction}\n{wind_gust}"
            "- \N{THERMOMETER} **Temperature**: {temp}\n"
            "- {cloudiness_emoji} **Cloudiness**: {clouds}%\n"
            "- \N{SUNRISE OVER MOUNTAINS} **Sunrise**: {sunrise_ts}\n"
            "- \N{SUNSET OVER BUILDINGS} **Sunset**: {sunset_ts}\n"
            "- \N{BLACK SUN WITH RAYS}\N{VARIATION SELECTOR-16} **UV Index**: {uvi}\n"
            "- \N{BALLOON} **Atmospheric Pressure**: {pressure} hPa\n"
        ).format(
            weather_emoji="".join(i.emoji for i in self.weather),
            weather=humanize_list([i.description for i in self.weather]),
            humidity=self.humidity,
            wind_speed=windspeed,
            wind_gust=wind_gust,
            direction=self.wind_dir,
            temp=self.temp,
            cloudiness_emoji=cloudiness_emoji,
            clouds=self.clouds,
            sunrise_ts=sunrise_ts,
            sunset_ts=sunset_ts,
            uvi=self.uvi,
            pressure=self.pressure,
        )
        if self.visibility:
            ret += _("- \N{EYEGLASSES} **Visibility**: {visibility} m\n").format(
                visibility=self.visibility
            )
        if self.rain:
            ret += _("- \N{CLOUD WITH RAIN}\N{VARIATION SELECTOR-16} **Rain**: {rain}\n").format(
                rain=str(self.rain)
            )
        if self.snow:
            ret += _("- \N{CLOUD WITH SNOW}\N{VARIATION SELECTOR-16} **Snow**: {snow}\n").format(
                snow=str(self.snow)
            )
        return ret

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.dt)

    @property
    def wind_dir(self) -> str:
        index = int(self.wind_deg // 22.5)
        return WIND_DIRECTION[index]

    @classmethod
    def from_json(cls, data: dict, units: Units) -> CurrentWeather:
        rain = data.pop("rain", None)
        if rain and isinstance(rain, dict):
            rain = Precipitation(h1=rain.pop("1h", None), h3=rain.pop("3h", None))
        snow = data.pop("snow", None)
        if snow and isinstance(snow, dict):
            snow = Precipitation(h1=snow.pop("1h", None), h3=snow.pop("3h", None))
        temp = Temperature.from_data(data.pop("temp"), units)
        return cls(
            weather=[WeatherType(**i) for i in data.pop("weather", [])],
            temp=temp,
            rain=rain,
            snow=snow,
            units=units,
            **data,
        )


@dataclass
class MinutelyWeather:
    dt: int
    precipitation: float

    @classmethod
    def from_json(cls, data: dict) -> MinutelyWeather:
        return cls(**data)


@dataclass
class HourlyWeather(CurrentWeather):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pop: Optional[int] = kwargs.get("pop")


@dataclass
class DailyWeather(CurrentWeather):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pop: Optional[float] = kwargs.get("pop")
        self.sunrise: Optional[int] = kwargs.get("sunrise")
        self.sunset: Optional[int] = kwargs.get("sunset")
        self.moonrise: Optional[int] = kwargs.get("moonrise")
        self.moonset: Optional[int] = kwargs.get("moonset")
        self.moon_phase: Optional[float] = kwargs.get("moon_phase")
        self.summary: Optional[str] = kwargs.get("summary")

    def __str__(self):
        ret = super().__str__()
        if self.summary:
            ret = f"{self.summary}\n{ret}"
        moon = MOONS[int(self.moon_phase // 0.125)]
        ret += _("Moon Phase: {moon}").format(moon=moon)
        return ret


@dataclass
class Alert:
    def __init__(self, **kwargs):
        self.sender_name: str = kwargs.get("sender_name", "")
        self.event: str = kwargs.get("event", "")
        self.start: int = kwargs.get("start", 0)
        self.end: int = kwargs.get("end", 0)
        self.description: str = kwargs.get("description", "")
        self.tags: List[str] = kwargs.get("tags", [])

    def __str__(self):
        return "\N{WARNING SIGN}\N{VARIATION SELECTOR-16} {0.event}: <t:{0.start}> - <t:{0.end}>".format(
            self
        )

    @classmethod
    def from_json(cls, data: dict) -> Alert:
        return cls(**data)


@dataclass
class OneCall:
    def __init__(self, **kwargs):
        self.lat: float = kwargs.get("lat")
        self.lon: float = kwargs.get("lon")
        self.timezone: str = kwargs.get("timezone")
        self.timezone_offset: int = kwargs.get("timezone_offset")
        self.current: CurrentWeather = kwargs.get("current")
        self.minutely: List[MinutelyWeather] = kwargs.get("minutely", [])
        self.hourly: List[HourlyWeather] = kwargs.get("hourly", [])
        self.daily: List[DailyWeather] = kwargs.get("daily", [])
        self.alerts: List[Alert] = kwargs.get("alerts", [])
        self.units: Units = kwargs.get("units", Units.standard)
        self.name: str = kwargs.get("name", "")
        self.state: Optional[str] = kwargs.get("state", "")
        self.country: str = kwargs.get("country", "")

    @property
    def coords(self) -> Coords:
        return Coords(lat=self.lat, lon=self.lon)

    @classmethod
    def from_json(
        cls, data: dict, units: Units, name: str, state: Optional[str], country: str
    ) -> OneCall:
        return cls(
            current=CurrentWeather.from_json(data.pop("current"), units),
            minutely=[MinutelyWeather.from_json(i) for i in data.pop("minutely", [])],
            hourly=[HourlyWeather.from_json(i, units) for i in data.pop("hourly", [])],
            daily=[DailyWeather.from_json(i, units) for i in data.pop("daily", [])],
            alerts=[Alert.from_json(i) for i in data.pop("alerts", [])],
            **data,
            units=units,
            name=name,
            state=state,
            country=country,
        )

    @classmethod
    async def search(
        cls,
        appid: str,
        search: str,
        units: Optional[Units] = None,
        lang: Optional[str] = None,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> OneCall:
        geo = await Geocoding.get(appid, search, 1, session=session)
        if not geo:
            raise APIError(_("No locations found matching `{search}`.").format(search=search))
        return await cls.get(
            appid=appid,
            lat=geo[0].lat,
            lon=geo[0].lon,
            units=units,
            lang=lang,
            name=geo[0].name,
            state=geo[0].state,
            country=geo[0].country,
            session=session,
        )

    @classmethod
    async def zipcode(
        cls,
        appid: str,
        zipcode: str,
        units: Optional[Units] = None,
        lang: Optional[str] = None,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> OneCall:
        geo = await Geocoding.get_zip(appid, zipcode, session=session)
        return await cls.get(
            appid=appid,
            lat=geo.lat,
            lon=geo.lon,
            units=units,
            lang=lang,
            name=geo.name,
            country=geo.country,
            session=session,
        )

    @classmethod
    async def lat_lon(
        cls,
        appid: str,
        lat: float,
        lon: float,
        units: Optional[Units] = None,
        lang: Optional[str] = None,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> OneCall:
        return await cls.get(
            appid=appid, lat=lat, lon=lon, units=units, lang=lang, session=session
        )

    @classmethod
    async def get(
        cls,
        appid: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        units: Optional[Units] = None,
        lang: Optional[str] = None,
        name: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        api_version: str = "2.5",
    ) -> OneCall:
        url = f"https://api.openweathermap.org/data/{api_version}/onecall"
        params = {"appid": appid, "exclude": "minutely"}
        if lang:
            try:
                params["lang"] = lang.split("_")[0]
            except IndexError:
                params["lang"] = lang
        if lat and lon:
            params["lat"] = str(lat)
            params["lon"] = str(lon)
        if units is None:
            units = Units("metric")  # default to metric units instead of kelvin
            params["units"] = units.name
        else:
            params["units"] = units.name
        if name is None or country is None or state is None:
            geo = await Geocoding.reverse(appid=appid, lat=lat, lon=lon, limit=1, session=session)
            name = geo[0].name
            country = geo[0].country
            state = geo[0].state

        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        else:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        log.verbose("OneCall get data: %s", data)
        if "cod" in data and data["cod"] != "200":
            raise APIError(data["message"])
        return cls.from_json(data, units, name, state, country)

    def text(
        self, include_forecast: Optional[bool] = None, include_hourly: Optional[bool] = None
    ) -> str:
        if self.state:
            location = f"{self.name}, {self.state}, {self.country}"
        else:
            location = f"{self.name}, {self.country}"
        msg = _("Weather for {location}").format(location=location) + "\n"
        if not include_forecast and not include_hourly:
            if self.daily and self.daily[0].summary:
                msg += self.daily[0].summary + "\n"
            msg += _("Current Weather") + f" (<t:{self.current.dt}:R>)\n{self.current}\n"
        elif include_forecast:
            for day in self.daily[:3]:
                msg += f"<t:{day.dt}:D>\n{day}\n"
        if include_hourly:
            for hour in self.hourly[:3]:
                msg += f"<t:{hour.dt}:t> (<t:{hour.dt}:R>)\n{hour}\n"
        alerts = "\n".join(str(a) for a in self.alerts)
        if alerts:
            msg += alerts + "\n"
        msg += _("-# Powered by <https://openweathermap.org>")
        return msg

    def embed(
        self, include_forecast: Optional[bool] = None, include_hourly: Optional[bool] = None
    ) -> discord.Embed:
        icon_url = self.current.weather[0].icon_url
        if self.state:
            location = f"{self.name}, {self.state}, {self.country}"
        else:
            location = f"{self.name}, {self.country}"

        hue = 0.4 - (self.current.uvi / 10.0) * 0.4
        # https://stackoverflow.com/questions/340209/generate-colors-between-red-and-green-for-a-power-meter
        colour = discord.Colour.from_hsv(hue, 0.9, 0.9)
        embed = discord.Embed(colour=colour, timestamp=self.current.datetime)
        embed.set_thumbnail(url=icon_url)
        embed.set_author(
            name=_("Weather for {location}").format(location=location),
            url=self.coords.url,
            icon_url=icon_url,
        )
        if not include_forecast and not include_hourly:
            if self.daily and self.daily[0].summary:
                embed.description = self.daily[0].summary
            embed.add_field(
                name=_("Current Weather") + f" (<t:{self.current.dt}:R>)",
                value=str(self.current),
                inline=False,
            )
        elif include_forecast:
            for day in self.daily[:5]:
                embed.add_field(name=f"<t:{day.dt}:D>", value=str(day), inline=False)
        if include_hourly:
            for hour in self.hourly[:5]:
                embed.add_field(
                    name=f"<t:{hour.dt}:t> (<t:{hour.dt}:R>)", value=str(hour), inline=False
                )

        embed.set_footer(text=_("Powered by https://openweathermap.org"))
        alerts = "\n".join(str(a) for a in self.alerts)
        if alerts:
            embed.description = alerts
        return embed
