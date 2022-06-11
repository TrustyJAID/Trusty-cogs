from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from typing import Dict, List, NamedTuple, Optional, Union

import aiohttp
import discord
from redbot.core import commands
from redbot.core.i18n import Translator

_ = Translator("NASA", __file__)

log = logging.getLogger("red.trusty-cogs.NASACog")

HEADERS = {"User-Agent": "Trusty-cogs NASA cog for Red-DiscordBot"}


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


class NASAapodAPI(discord.ext.commands.FlagConverter, case_insensitive=True):
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

    @property
    def parameters(self):
        return {k: v for k, v in self if v is not None}


class MarsRovers(discord.ext.commands.FlagConverter, case_insensitive=True):
    sol: Optional[int] = discord.ext.commands.flag(
        name="sol", default=None, description="sol (ranges from 0 to max found in endpoint)"
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

    @property
    def parameters(self):
        return {k: v for k, v in self if v is not None}


class NASAEarthAsset(discord.ext.commands.FlagConverter, case_insensitive=True):
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

    @property
    def parameters(self):
        return {k: v for k, v in self if v is not None}


class NASANearEarthObjectAPI(discord.ext.commands.FlagConverter, case_insensitive=True):
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

    @property
    def parameters(self):
        return {k: v for k, v in self if v is not None}


class NASAImagesAPI(discord.ext.commands.FlagConverter, case_insensitive=True):
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

    @property
    def parameters(self):
        return {k: v for k, v in self if v is not None}


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
    def first_utc(self):
        return datetime.strptime(self.First_UTC, "%Y-%m-%dT%H:%M:%SZ")

    @property
    def last_utc(self):
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
        row = int((90 - lat) * (2 ** 3) / 288)
        col = int((180 + lon) * (2 ** 3) / 288)
        date_str = date.strftime("%Y-%m-%d")
        return f"https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date_str}/250m/3/{row}/{col}.jpg"


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
        return sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


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
