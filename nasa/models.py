from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from math import hypot, sqrt
from typing import Dict, List, NamedTuple, Optional, Union

import aiohttp
import discord
import skyfield
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number
from skyfield.api import load
from skyfield.toposlib import wgs84

_ = Translator("NASA", __file__)

log = getLogger("red.trusty-cogs.NASACog")

HEADERS = {"User-Agent": "Trusty-cogs NASA cog for Red-DiscordBot"}


class APIError(Exception):
    pass


class QueryConverter(discord.ext.commands.FlagConverter, case_insensitive=True):
    @property
    def parameters(self) -> Dict[str, str]:
        return {k: v for k, v in self if v is not None}

    @property
    def params(self) -> Dict[str, str]:
        return self.parameters


class DateFinder(discord.app_commands.Transformer):
    """
    Converter for `YYYY-MM-DD` date formats
    """

    DATE_RE = re.compile(
        r"((19|20)\d\d)[- \/.](0[1-9]|1[012]|[1-9])[- \/.](0[1-9]|[12][0-9]|3[01]|[1-9])"
    )

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> str:
        find = cls.DATE_RE.search(argument)
        if find:
            date_str = f"{find.group(1)}-{find.group(3)}-{find.group(4)}"
            return date_str
        else:
            raise commands.BadArgument("The value provided is not `YYYY-MM-DD` formatted.")

    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> str:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, value)


class NASAapodAPI(QueryConverter):
    date: Optional[str] = discord.ext.commands.flag(
        name="date", default=None, description="YYYY-MM-DD The date of the APOD image to retrieve"
    )
    start_date: Optional[str] = discord.ext.commands.flag(
        name="start_date",
        default=None,
        description="YYYY-MM-DD The start of a date range. Cannot be used with date.",
        converter=DateFinder,
    )
    end_date: Optional[str] = discord.ext.commands.flag(
        name="end_date",
        default=None,
        description="YYYY-MM-DD The end of the date range, when used with start_date.",
        converter=DateFinder,
    )
    count: Optional[int] = discord.ext.commands.flag(
        name="count",
        default=None,
        description="If this is specified then count randomly chosen images will be returned.",
    )


class MarsRovers(QueryConverter):
    sol: Optional[int] = discord.ext.commands.flag(
        name="sol", default=0, description="sol (ranges from 0 to max found in endpoint)"
    )
    camera: Optional[str] = discord.ext.commands.flag(
        name="camera",
        default=None,
        description="FHAZ, RHAZ, MAST, CHEMCAM, MAHLI, MARDI, NAVCAM, PANCAM, or MINITES",
    )
    page: Optional[int] = discord.ext.commands.flag(
        name="page", default=1, description="25 items per page returned"
    )
    earth_date: Optional[str] = discord.ext.commands.flag(
        name="earth_date",
        default=None,
        description="YYYY-MM-DD corresponding date on earth for the given sol",
        converter=DateFinder,
    )


class NASAEarthAsset(QueryConverter):
    lat: float = discord.ext.commands.flag(name="lat", description="Latitude")
    lon: float = discord.ext.commands.flag(
        name="lon",
        description="Longitude",
    )
    date: str = discord.ext.commands.flag(
        name="date",
        description="YYYY-MM-DD beginning of 30 day date range that will be used to look for closest image to that date",
        converter=DateFinder,
    )
    dim: Optional[float] = discord.ext.commands.flag(
        name="dim",
        default=None,
        description="width and height of image in degrees",
    )


class NASANearEarthObjectAPI(QueryConverter):
    start_date: Optional[str] = discord.ext.commands.flag(
        name="start_date",
        default=None,
        description="YYYY-MM-DD Starting date for asteroid search",
        converter=DateFinder,
    )
    end_date: Optional[str] = discord.ext.commands.flag(
        name="end_date",
        default=None,
        description="YYYY-MM-DD Ending date for asteroid search",
        converter=DateFinder,
    )


class NASAImagesAPI(QueryConverter):
    q: Optional[str] = discord.ext.commands.flag(
        name="q",
        aliases=["query"],
        default=None,
        description="Free text search terms to compare to all indexed metadata.",
    )
    center: Optional[str] = discord.ext.commands.flag(
        name="center",
        aliases=["c"],
        default=None,
        description="NASA center which published the media.",
    )
    description: Optional[str] = discord.ext.commands.flag(
        name="description",
        default=None,
        description="Terms to search for in “Description” fields",
    )
    description_508: Optional[str] = discord.ext.commands.flag(
        name="description_508",
        aliases=["508"],
        default=None,
        description="Terms to search for in “508 Description” fields.",
    )
    keywords: Optional[str] = discord.ext.commands.flag(
        name="keywords",
        default=None,
        description="Terms to search for in “Keywords” fields. Separate multiple values with commas.",
    )
    location: Optional[str] = discord.ext.commands.flag(
        name="location",
        default=None,
        description="Terms to search for in “Location” fields.",
    )
    media_type: Optional[str] = discord.ext.commands.flag(
        name="media_type",
        aliases=["media"],
        default=None,
        description="Media types to restrict the search to. Available types: [“image”, “audio”]. Separate multiple values with commas.",
    )
    nasa_id: Optional[str] = discord.ext.commands.flag(
        name="nasa_id",
        aliases=["id"],
        default=None,
        description="The media asset’s NASA ID.",
    )
    page: Optional[str] = discord.ext.commands.flag(
        name="page",
        default=None,
        description=" Page number, starting at 1, of results to get.",
    )
    photographer: Optional[str] = discord.ext.commands.flag(
        name="photographer",
        default=None,
        description="The primary photographer’s name.",
    )
    secondary_creator: Optional[str] = discord.ext.commands.flag(
        name="secondary_creator",
        default=None,
        description="A secondary photographer/videographer’s name.",
    )
    title: Optional[str] = discord.ext.commands.flag(
        name="title",
        default=None,
        description="Terms to search for in “Title” fields.",
    )
    year_start: Optional[str] = discord.ext.commands.flag(
        name="year_start",
        aliases=["start"],
        default=None,
        description="The start year for results. Format: YYYY.",
    )
    year_end: Optional[str] = discord.ext.commands.flag(
        name="year_end",
        aliases=["end"],
        default=None,
        description="The end year for results. Format: YYYY.",
    )


@dataclass
class TLEMember:
    id: str
    type: str
    satelliteId: int
    name: str
    date: str
    line1: str
    line2: str

    @property
    def datetime(self):
        return datetime.strptime(self.date, "%Y-%m-%dT%H:%M:%S%z")

    @classmethod
    def from_json(cls, data: dict) -> TLEMember:
        return cls(id=data.pop("@id"), type=data.pop("@type"), **data)

    def embed(self) -> discord.Embed:
        lat = self.latitude()
        lon = self.longitude()
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat}%2C{lon}"
        coords = f"[Latitude: {lat:.2f} Longitude: {lon:.2f}]({maps_url})"
        description = (
            f"Satellite ID: {self.satelliteId}\n"
            f"Position: {coords}\nElevation: {self.elevation():.2f} km\n"
            f"Velocity: {self.velocity():.2f} km/s"
        )
        em = discord.Embed(title=self.name, description=description, timestamp=self.datetime)
        em.add_field(name="Line 1", value=self.line1, inline=False)
        em.add_field(name="Line 2", value=self.line2, inline=False)
        return em

    def velocity(self):
        return hypot(*list(self.satellite.at(load.timescale().now()).velocity.km_per_s))

    def distance(self):
        return self.satellite.at(load.timescale().now()).distance

    def location(self):
        return wgs84.geographic_position_of(self.satellite.at(load.timescale().now()))

    def latitude(self):
        return self.location().latitude.degrees

    def longitude(self):
        return self.location().longitude.degrees

    def elevation(self):
        return self.location().elevation.km

    @property
    def satellite(self) -> skyfield.EarthSatellite:
        ts = load.timescale()
        return skyfield.api.EarthSatellite(self.line1, self.line2, self.name, ts)


@dataclass
class TLEParameters:
    search: str
    sort: str
    sort_dir: str
    page: int
    page_size: int

    @classmethod
    def from_json(cls, data: dict) -> TLEParameters:
        return cls(sort_dir=data.pop("sort-dir"), page_size=data.pop("page-size"), **data)


@dataclass
class TLEView:
    id: str
    type: str
    first: str
    last: str
    next: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> TLEView:
        return cls(id=data.pop("@id"), type=data.pop("@type"), **data)


@dataclass
class NASATLEFeed:
    context: str
    id: str
    type: str
    totalItems: int
    member: List[TLEMember]
    parameters: TLEParameters
    view: TLEView

    @classmethod
    def from_json(cls, data: dict) -> NASATLEFeed:
        return cls(
            context=data.pop("@context"),
            id=data.pop("@id"),
            type=data.pop("@type"),
            totalItems=data["totalItems"],
            member=[TLEMember.from_json(i) for i in data["member"]],
            parameters=TLEParameters.from_json(data["parameters"]),
            view=TLEView.from_json(data["view"]),
        )

    @classmethod
    async def get(
        cls, params: Dict[str, str] = {}, session: Optional[aiohttp.ClientSession] = None
    ) -> NASATLEFeed:
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(
                    "http://tle.ivanstanojevic.me/api/tle", params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                    else:
                        raise APIError(
                            "There was an error in that request. Response code {code}".format(
                                code=resp.status
                            )
                        )
        else:
            async with session.get("http://tle.ivanstanojevic.me/api/tle", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    raise APIError(
                        "There was an error in that request. Response code {code}".format(
                            code=resp.status
                        )
                    )
        return cls.from_json(data)

    async def next(self, session: Optional[aiohttp.ClientSession] = None) -> NASATLEFeed:
        if self.view.next:
            return await self.get(session=session)
        else:
            raise APIError("There was an error in that request.")

    @classmethod
    async def search(
        cls, query: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None
    ) -> NASATLEFeed:
        params = {}
        if query:
            params["search"] = query
        return await cls.get(params, session=session)


class InsightData(NamedTuple):
    av: float
    ct: int
    mn: float
    mx: float


class WindDirection(NamedTuple):
    compass_degrees: float
    compass_point: str
    compass_right: float
    compass_up: float
    ct: int


@dataclass
class Validity:
    sol_hours_with_data: List[int]
    valid: bool


@dataclass
class InsightWD:
    compass_pts: Dict[str, WindDirection]
    most_common: Optional[WindDirection] = None

    @classmethod
    def from_json(cls, data: dict) -> InsightWD:
        wd = WindDirection(**data.pop("most_common")) if data["most_common"] else None
        compass_pts = {key: WindDirection(**data[key]) for key in data}
        return cls(most_common=wd, compass_pts=compass_pts)


@dataclass
class SolData:
    atmospheric_temp: Optional[InsightData]
    horizontal_windspeed: Optional[InsightData]
    pressure: Optional[InsightData]
    wind_direction: Optional[InsightWD]
    First_UTC: str
    Last_UTC: str
    Season: str

    @property
    def first_utc(self) -> datetime:
        return datetime.strptime(self.First_UTC, "%Y-%m-%dT%H:%M:%SZ")

    @property
    def last_utc(self) -> datetime:
        return datetime.strptime(self.Last_UTC, "%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_json(cls, data: dict) -> SolData:
        at = InsightData(**data["AT"]) if data.get("AT") else None
        hws = InsightData(**data["HWS"]) if data.get("HWS") else None
        pre = InsightData(**data["PRE"]) if data.get("PRE") else None
        wd = InsightWD.from_json(data["WD"]) if data.get("WD") else None
        return cls(
            atmospheric_temp=at,
            horizontal_windspeed=hws,
            pressure=pre,
            wind_direction=wd,
            First_UTC=data["First_UTC"],
            Last_UTC=data["Last_UTC"],
            Season=data["Season"],
        )


@dataclass
class SolValidity:
    atmospheric_temp: Validity
    horizontal_windspeed: Validity
    pressure: Validity
    wind_direction: Validity

    @classmethod
    def from_json(cls, data: dict) -> SolValidity:
        return cls(
            atmospheric_temp=Validity(**data["AT"]),
            horizontal_windspeed=Validity(**data["HWS"]),
            pressure=Validity(**data["PRE"]),
            wind_direction=Validity(**data["WD"]),
        )


@dataclass
class MarsInsightValidity:
    sol_hours_required: int
    sols_checked: List[str]
    sols: Dict[str, SolValidity]

    @classmethod
    def from_json(cls, data: dict) -> MarsInsightValidity:
        return cls(
            sol_hours_required=data["sol_hours_required"],
            sols_checked=data["sols_checked"],
            sols={key: SolValidity.from_json(data[key]) for key in data["sols_checked"]},
        )


@dataclass
class MarsInsightFeed:
    sol_keys: List[str]
    validity_checks: MarsInsightValidity
    sols: Dict[str, SolData]

    @classmethod
    def from_json(cls, data: dict) -> MarsInsightFeed:
        return cls(
            sol_keys=data["sol_keys"],
            validity_checks=MarsInsightValidity.from_json(data["validity_checks"]),
            sols={key: SolData.from_json(data[key]) for key in data["sol_keys"]},
        )

    @classmethod
    async def get(
        cls, api_key: str = "DEMO_KEY", session: Optional[aiohttp.ClientSession] = None
    ) -> MarsInsightFeed:
        url = f"https://api.nasa.gov/insight_weather/?api_key={api_key}&feedtype=json&ver=1.0"
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
        else:
            async with session.get(url) as resp:
                data = await resp.json()
        return cls.from_json(data)


class EstimatedDiameter(NamedTuple):
    estimated_diameter_min: float
    estimated_diameter_max: float

    def __str__(self):
        return f"min: {self.estimated_diameter_min:.2f} max: {self.estimated_diameter_max:.2f}"


@dataclass
class EstimatedDiameterData:
    kilometers: EstimatedDiameter
    meters: EstimatedDiameter
    miles: EstimatedDiameter
    feet: EstimatedDiameter

    @classmethod
    def from_json(cls, data: dict) -> EstimatedDiameterData:
        return cls(
            kilometers=EstimatedDiameter(**data["kilometers"]),
            meters=EstimatedDiameter(**data["meters"]),
            miles=EstimatedDiameter(**data["miles"]),
            feet=EstimatedDiameter(**data["feet"]),
        )


class RelativeVelocity(NamedTuple):
    kilometers_per_second: float
    kilometers_per_hour: float
    miles_per_hour: float

    @classmethod
    def from_json(cls, data: dict) -> RelativeVelocity:
        return cls(
            kilometers_per_second=float(data["kilometers_per_second"]),
            kilometers_per_hour=float(data["kilometers_per_hour"]),
            miles_per_hour=float(data["miles_per_hour"]),
        )


class MissDistance(NamedTuple):
    astronomical: float
    lunar: float
    kilometers: float
    miles: float

    @classmethod
    def from_json(cls, data: dict) -> MissDistance:
        return cls(
            astronomical=float(data["astronomical"]),
            lunar=float(data["lunar"]),
            kilometers=float(data["kilometers"]),
            miles=float(data["miles"]),
        )


@dataclass
class CloseApproachData:
    close_approach_date: str
    close_approach_date_full: str
    epoch_date_close_approach: int
    relative_velocity: RelativeVelocity
    miss_distance: MissDistance
    orbiting_body: str

    @classmethod
    def from_json(cls, data: dict) -> CloseApproachData:
        return cls(
            relative_velocity=RelativeVelocity.from_json(data.pop("relative_velocity")),
            miss_distance=MissDistance.from_json(data.pop("miss_distance")),
            **data,
        )

    def __str__(self):
        ts = discord.utils.format_dt(self.datetime)
        return (
            f"Time: {ts}\nOrbiting: {self.orbiting_body}\n"
            "__Relative Velocity__\n"
            f"{self.relative_velocity.kilometers_per_second:.2f} Km/s\n"
            f"{self.relative_velocity.kilometers_per_hour:.2f} Km/h\n"
            f"{self.relative_velocity.miles_per_hour:.2f} Mph\n"
            "__Miss Distance__\n"
            f"{self.miss_distance.astronomical:.2f} AU\n"
            f"{self.miss_distance.lunar:.2f} LD\n"
            f"{self.miss_distance.kilometers:.2f} km\n"
            f"{self.miss_distance.miles:.2f} miles\n"
        )

    @property
    def timestamp(self):
        return self.epoch_date_close_approach / 1000

    @property
    def datetime(self):
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class NearEarthObject:
    links: Dict[str, str]
    id: str
    neo_reference_id: str
    name: str
    nasa_jpl_url: str
    absolute_magnitude_h: float
    estimated_diameter: EstimatedDiameterData
    is_potentially_hazardous_asteroid: bool
    close_approach_data: List[CloseApproachData]
    is_sentry_object: bool

    @classmethod
    def from_json(cls, data: dict) -> NearEarthObject:
        return cls(
            estimated_diameter=EstimatedDiameterData.from_json(data.pop("estimated_diameter")),
            close_approach_data=[
                CloseApproachData.from_json(i) for i in data.pop("close_approach_data", [])
            ],
            **data,
        )

    def embed(self):
        em = discord.Embed(title=self.name)
        diameter = (
            f"Km: {self.estimated_diameter.kilometers}\n m: {self.estimated_diameter.meters}\n"
            f"mi: {self.estimated_diameter.miles}\n feet: {self.estimated_diameter.feet}\n"
        )
        em.add_field(name="Estimated Diameter", value=diameter)
        for approach in self.close_approach_data:
            em.add_field(name="Close Approach data", value=str(approach))
        return em


@dataclass
class NEOFeed:
    links: Dict[str, str]
    element_count: int
    near_earth_objects: List[NearEarthObject]

    @classmethod
    def from_json(cls, data: dict) -> NEOFeed:
        neos = data.pop("near_earth_objects", {})
        near_earth_objects = [
            NearEarthObject.from_json(neo) for day in neos.values() for neo in day
        ]
        return cls(
            near_earth_objects=sorted(
                near_earth_objects, key=lambda x: x.close_approach_data[0].timestamp
            ),
            **data,
        )

    @classmethod
    async def get(
        cls,
        api_key: str = "DEMO_KEY",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> NEOFeed:
        params = {"api_key": api_key}
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y-%m-%d")
        url = "https://api.nasa.gov/neo/rest/v1/feed"
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        else:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        return cls.from_json(data)


@dataclass
class ManifestPhoto:
    sol: int
    earth_date: str
    total_photos: int
    cameras: List[str]


@dataclass
class PhotoManifest:
    name: str
    landing_date: str
    launch_date: str
    status: str
    max_sol: int
    max_date: str
    total_photos: int
    photos: List[ManifestPhoto]

    @classmethod
    def from_json(cls, data: dict) -> PhotoManifest:
        return cls(photos=[ManifestPhoto(**p) for p in data.pop("photos")], **data)


@dataclass
class Camera:
    id: int
    name: str
    rover_id: int
    full_name: str


@dataclass
class Rover:
    id: int
    name: str
    landing_date: str
    launch_date: str
    status: str


@dataclass
class RoverPhoto:
    id: int
    sol: int
    camera: Camera
    img_src: str
    earth_date: str
    rover: Rover

    @classmethod
    def from_json(cls, data: dict) -> RoverPhoto:
        return cls(camera=Camera(**data.pop("camera")), rover=Rover(**data.pop("rover")), **data)

    def embed(self):
        title = f"{self.camera.full_name} on {self.rover.name}"
        description = f"Sol: {self.sol}\nEarth Date: {self.earth_date}"
        em = discord.Embed(title=title, description=description)
        em.set_image(url=self.img_src)
        return em


class Category(NamedTuple):
    id: str
    title: str


class Source(NamedTuple):
    id: str
    url: str


@dataclass
class Geometry:
    magnitudeValue: Optional[float]
    magnitudeUnit: Optional[str]
    date: datetime
    type: str
    coordinates: List[float]

    @classmethod
    def from_json(cls, data: dict) -> Geometry:
        return cls(
            magnitudeValue=data["magnitudeValue"],
            magnitudeUnit=data["magnitudeUnit"],
            date=datetime.strptime(data["date"], "%Y-%m-%dT%H:%M:%SZ"),
            type=data["type"],
            coordinates=data["coordinates"],
        )


@dataclass
class Event:
    id: str
    title: str
    description: Optional[str]
    link: str
    closed: Optional[str]
    categories: List[Category]
    sources: List[Source]
    geometry: List[Geometry]

    @classmethod
    def from_json(cls, data: dict) -> Event:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            link=data["link"],
            closed=data["closed"],
            categories=[Category(**i) for i in data["categories"]],
            sources=[Source(**i) for i in data["sources"]],
            geometry=[Geometry.from_json(i) for i in data["geometry"]],
        )

    @property
    def image_url(self):
        lon = self.geometry[-1].coordinates[0]
        lat = self.geometry[-1].coordinates[1]
        date = self.geometry[-1].date
        row = int((90 - lat) * (2**3) / 288)
        col = int((180 + lon) * (2**3) / 288)
        date_str = date.strftime("%Y-%m-%d")
        return f"https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date_str}/250m/3/{row}/{col}.jpg"

    def embed(self):
        em = discord.Embed(title=self.title, description=self.description)
        em.set_image(url=self.image_url)
        coordinates = self.geometry[-1].coordinates
        lat = coordinates[1]
        lon = coordinates[0]
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat}%2C{lon}"
        coords = f"[Latitude: {lat}\nLongitude: {lon}]({maps_url})"
        em.add_field(name="Coordinates", value=coords)
        value = ""
        for geometry in reversed(self.geometry):
            if len(value) >= 512:
                break
            if geometry.magnitudeValue is None:
                continue
            timestamp = discord.utils.format_dt(geometry.date)
            value += f"{geometry.magnitudeValue} {geometry.magnitudeUnit} - {timestamp}\n"
        if value:
            em.add_field(name="Data", value=value)
        sources = ""
        for source in self.sources:
            sources += f"[{source.id}]({source.url})\n"
        if sources:
            em.add_field(name="Sources", value=sources)
        return em


class CentroidCoords(NamedTuple):
    lat: float
    lon: float

    def __str__(self):
        return f"{self.lat=} {self.lon=}"


class XYZPoint(NamedTuple):
    x: float
    y: float
    z: float

    def __str__(self):
        return f"{self.x=} {self.y=} {self.z=}"

    @property
    def distance(self):
        return sqrt(self.x**2 + self.y**2 + self.z**2)


class Quaternion(NamedTuple):
    q0: float
    q1: float
    q2: float
    q3: float

    def __str__(self):
        return f"{self.q0=} {self.q1=} {self.q2=} {self.q3=}"


@dataclass
class Coords:
    centroid_coordinates: CentroidCoords
    dscovr_j2000_position: XYZPoint
    lunar_j2000_position: XYZPoint
    sun_j2000_position: XYZPoint
    attitude_quaternions: Quaternion

    @classmethod
    def from_json(cls, data: dict) -> Coords:
        return cls(
            centroid_coordinates=CentroidCoords(**data.pop("centroid_coordinates")),
            dscovr_j2000_position=XYZPoint(**data.pop("dscovr_j2000_position")),
            lunar_j2000_position=XYZPoint(**data.pop("lunar_j2000_position")),
            sun_j2000_position=XYZPoint(**data.pop("sun_j2000_position")),
            attitude_quaternions=Quaternion(**data.pop("attitude_quaternions")),
        )


@dataclass
class EPICData:
    identifier: str
    caption: str
    image: str
    version: str
    centroid_coordinates: CentroidCoords
    dscovr_j2000_position: XYZPoint
    lunar_j2000_position: XYZPoint
    sun_j2000_position: XYZPoint
    attitude_quaternions: Quaternion
    date: datetime
    coords: Coords

    @classmethod
    def from_json(cls, data: dict) -> EPICData:
        date = datetime.strptime(data.pop("date"), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        coords = Coords.from_json(data.pop("coords"))
        return cls(date=date, coords=coords, **data)

    @property
    def natural_url(self):
        url_date = self.date.strftime("%Y/%m/%d")
        return f"https://epic.gsfc.nasa.gov/archive/natural/{url_date}/png/{self.image}.png"

    @property
    def enhanced_url(self):
        url_date = self.date.strftime("%Y/%m/%d")
        return f"https://epic.gsfc.nasa.gov/archive/enhanced/{url_date}/png/{self.image}.png"

    def get_distance(self, distance: float) -> str:
        return f"{humanize_number(int(distance))} km ({humanize_number(int(distance*0.621371))} Miles)"

    def embed(self, enhanced: bool = False) -> discord.Embed:
        url = self.natural_url if not enhanced else self.enhanced_url
        description = (
            f"{self.caption}\n\n"
            f"Distance from Earth: {self.get_distance(self.coords.dscovr_j2000_position.distance)}\n"
            f"Distance from Sun: {self.get_distance(self.coords.sun_j2000_position.distance)}\n"
            f"Distance from Moon: {self.get_distance(self.coords.lunar_j2000_position.distance)}\n"
        )

        em = discord.Embed(title=self.identifier, description=description, url=url)
        em.set_image(url=url)
        return em


@dataclass
class Resource:
    dataset: str
    planet: str


@dataclass
class Asset:
    date: datetime
    id: str
    resource: Resource
    service_version: str
    url: str

    @classmethod
    def from_json(cls, data: dict) -> Asset:
        date = datetime.strptime(data.pop("date"), "%Y-%m-%dT%H:%M:%S.%f").replace(
            tzinfo=timezone.utc
        )
        resource = Resource(**data.pop("resource"))
        return cls(date=date, resource=resource, **data)


@dataclass
class NASAAstronomyPictureOfTheDay:
    date: datetime
    explanation: str
    media_type: str
    service_version: str
    title: str
    url: str
    hdurl: Optional[str] = None
    copyright: Optional[str] = None
    thumbnail_url: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> NASAAstronomyPictureOfTheDay:
        date = datetime.fromisoformat(data.pop("date"))
        return cls(date=date, **data)

    @classmethod
    async def from_url(
        cls,
        url: str,
        api_key: str = "DEMO_KEY",
        params: dict = {},
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Union[NASAAstronomyPictureOfTheDay, List[NASAAstronomyPictureOfTheDay]]:
        params.update({"api_key": api_key, "thumbs": "True"})
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        else:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        if isinstance(data, list):
            return [cls.from_json(i) for i in data]
        return cls.from_json(data)

    @classmethod
    async def get(
        cls,
        api_key: str = "DEMO_KEY",
        date: Optional[datetime] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        count: Optional[int] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Union[NASAAstronomyPictureOfTheDay, List[NASAAstronomyPictureOfTheDay]]:
        params = {}
        if date:
            params["date"] = date.strftime("%Y-%m-%d")
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y-%m-%d")
        if count:
            params["count"] = count
        return await cls.from_url(
            "https://api.nasa.gov/planetary/apod", api_key, params=params, session=session
        )

    @classmethod
    async def today(
        cls,
        api_key: str = "DEMO_KEY",
        session: Optional[aiohttp.ClientSession] = None,
    ) -> NASAAstronomyPictureOfTheDay:
        return await cls.get(api_key, session=session)  # type: ignore

    def embed(self) -> discord.Embed:
        em = discord.Embed(
            title=self.title, description=self.explanation, timestamp=self.date, url=self.url
        )
        em.set_image(url=self.url)
        if self.thumbnail_url:
            em.set_thumbnail(url=self.thumbnail_url)
        if self.copyright:
            em.add_field(name="Copyright (c)", value=self.copyright)
        if self.hdurl:
            em.add_field(name="HD URL", value=f"[Click here]({self.hdurl})")
        return em


@dataclass
class Links:
    href: str
    rel: str
    prompt: Optional[str] = None
    render: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> Links:
        return cls(**data)


@dataclass
class Data:
    date_created: datetime

    @classmethod
    def from_json(cls, data: dict):
        date = datetime.strptime(data.pop("date_created"), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        ret = cls(date_created=date)
        for key, value in data.items():
            setattr(ret, key, value)
        return ret


@dataclass
class Items:
    data: List[Data]
    href: str
    links: List[Links]

    @classmethod
    def from_json(cls, data: dict) -> Items:
        return cls(
            href=data.pop("href"),
            data=[Data.from_json(i) for i in data.pop("data", [])],
            links=[Links.from_json(i) for i in data.pop("links", [])],
        )


@dataclass
class Collection:
    href: str
    items: List[Items]
    links: List[Links]
    metadata: dict
    version: str

    @classmethod
    def from_json(cls, data: dict) -> Collection:
        data = data.get("collection", {})
        return cls(
            items=[Items.from_json(i) for i in data.pop("items", [])],
            links=[Links.from_json(i) for i in data.pop("links", [])],
            **data,
        )

    @classmethod
    async def from_params(
        cls, params: Dict[str, str] = {}, session: Optional[aiohttp.ClientSession] = None
    ) -> Collection:
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(
                    "https://images-api.nasa.gov/search", params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                    else:
                        raise APIError(
                            "There was an error in that request. Response code {code}".format(
                                code=resp.status
                            )
                        )
        else:
            async with session.get("https://images-api.nasa.gov/search", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    raise APIError(
                        "There was an error in that request. Response code {code}".format(
                            code=resp.status
                        )
                    )
        return cls.from_json(data)

    @classmethod
    async def get(
        cls,
        q: Optional[str] = None,
        center: Optional[str] = None,
        description: Optional[str] = None,
        description_508: Optional[str] = None,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        media_type: Optional[str] = None,
        nasa_id: Optional[str] = None,
        page: Optional[str] = None,
        photographer: Optional[str] = None,
        secondary_creator: Optional[str] = None,
        title: Optional[str] = None,
        year_start: Optional[str] = None,
        year_end: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Collection:
        params = {
            "q": q,
            "center": center,
            "description": description,
            "description_508": description_508,
            "keywords": keywords,
            "location": location,
            "media_type": media_type,
            "nasa_id": nasa_id,
            "page": page,
            "photographer": photographer,
            "secondary_creator": secondary_creator,
            "title": title,
            "year_start": year_start,
            "year_end": year_end,
        }
        return await cls.from_params(
            params={k: v for k, v in params.items() if v is not None}, session=session
        )
