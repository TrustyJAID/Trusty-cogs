from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import sqrt
from typing import List, NamedTuple, Optional

import discord
from redbot.core.i18n import Translator

_ = Translator("NASA", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")


class NASAapodAPI(discord.ext.commands.FlagConverter, case_insensitive=True):
    date: Optional[str] = discord.ext.commands.flag(
        name="date", default=None, description="YYYY-MM-DD The date of the APOD image to retrieve"
    )
    start_date: Optional[str] = discord.ext.commands.flag(
        name="start_date",
        default=None,
        description="YYYY-MM-DD The start of a date range. Cannot be used with date.",
    )
    end_date: Optional[str] = discord.ext.commands.flag(
        name="end_date",
        default=None,
        description="YYYY-MM-DD The end of the date range, when used with start_date.",
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
        description="corresponding date on earth for the given sol",
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
    )
    dim: Optional[float] = discord.ext.commands.flag(
        name="dim",
        default=None,
        description="width and height of image in degrees",
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
