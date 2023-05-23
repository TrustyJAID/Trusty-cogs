from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Tuple

import aiohttp
from red_commons.logging import getLogger

BASE_URL = "https://{ip}/clip/v2/"

log = getLogger("red.trusty-cogs.hue")


class HueError(Exception):
    def __init__(self, data: dict):
        self.type = data.get("type", 0)
        self.address: str = data.get("address", "")
        self.description: str = data.get("description", "")


class Bridge:
    def __init__(self, ip: str):
        self.ip = ip


class Service(NamedTuple):
    rid: str
    rtype: str


@dataclass
class ProductData:
    model_id: str
    manufacturer_name: str
    product_name: str
    product_archetype: str
    certified: bool
    software_version: str
    hardware_platform_type: str

    @classmethod
    def from_json(cls, data: dict) -> ProductData:
        return cls(
            model_id=data["model_id"],
            manufacturer_name=data["manufacturer_name"],
            product_name=data["product_name"],
            product_archetype=data["product_archetype"],
            certified=data["certified"],
            software_version=data["software_version"],
            hardware_platform_type=data["hardware_platform_type"],
        )


@dataclass
class MetaData:
    name: str
    archetype: str

    @classmethod
    def from_json(cls, data: dict) -> MetaData:
        return cls(name=data["name"], archetype=data["archetype"])


@dataclass
class Device:
    id: str
    id_v1: str
    product_data: ProductData
    metadata: MetaData
    identify: dict
    services: List[Service]
    type: str
    _client: Client

    @classmethod
    def from_json(cls, data: dict, client: Client) -> Device:
        return cls(
            id=data["id"],
            id_v1=data["id_v1"],
            product_data=ProductData.from_json(data["product_data"]),
            metadata=MetaData.from_json(data["metadata"]),
            identify=data.get("identify", {}),
            services=[Service(**i) for i in data["services"]],
            type=data["type"],
            _client=client,
        )


class Owner(NamedTuple):
    rid: str
    rtype: str


@dataclass
class On:
    on: bool

    @classmethod
    def from_json(cls, data: dict) -> On:
        return cls(on=data["on"])

    def to_json(self):
        return {"on": self.on}


@dataclass
class Dimming:
    brightness: float
    min_dim_level: float

    def to_json(self):
        return {
            "brightness": max(min(100.0, self.brightness), self.min_dim_level),
        }

    def set_brightness(self, brightness: float) -> float:
        self.brightness = max(min(100.0, brightness), self.min_dim_level)
        return self.brightness


@dataclass
class MirekSchema:
    mirek_minimum: int
    mirek_maximum: int

    def to_json(self):
        return {
            "mirek_maximum": self.mirek_maximum,
            "mirek_minimum": self.mirek_minimum,
        }


@dataclass
class ColourTemp:
    mirek: int
    mirek_valid: bool
    mirek_schema: MirekSchema

    @classmethod
    def from_json(cls, data: dict) -> ColourTemp:
        return cls(
            mirek=data["mirek"] or data["mirek_schema"]["mirek_minimum"],
            mirek_valid=data["mirek_valid"],
            mirek_schema=MirekSchema(**data["mirek_schema"]),
        )

    def validate(self, new_value: int) -> int:
        return max(
            min(self.mirek_schema.mirek_maximum, new_value), self.mirek_schema.mirek_minimum
        )

    def to_json(self):
        return {
            "mirek": self.validate(self.mirek),
        }

    def set_kelvin(self, temperature: int) -> int:
        self.mirek = self.validate(int(1000000 / temperature))
        return int(1000000 / self.mirek)

    def set(self, mirek: int) -> int:
        self.mirek = self.validate(mirek)
        return self.mirek


@dataclass
class XYColour:
    x: float
    y: float

    def to_json(self):
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_rgb(cls, red: float, green: float, blue: float) -> XYColour:
        X = 0.4124 * red + 0.3576 * green + 0.1805 * blue
        Y = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        Z = 0.0193 * red + 0.1192 * green + 0.9505 * blue
        try:
            x = X / (X + Y + Z)
            y = Y / (X + Y + Z)
        except ZeroDivisionError:
            x = 1.0
            y = 1.0
        return cls(x=max(min(1.0, x), 0.0), y=max(min(1.0, y), 0.0))

    @classmethod
    def from_hex(cls, hex_code: str) -> XYColour:
        hex_code = hex_code.replace("#", "")
        r, g, b = tuple(int(hex_code[i : i + 2], 16) for i in (0, 2, 4))
        return cls.from_rgb(r, g, b)

    def set(self, x: float, y: float) -> XYColour:
        self.x = max(min(1.0, x), 0.0)
        self.y = max(min(1.0, y), 0.0)
        return self

    def set_random(self):
        return self.set(random.random(), random.random())


@dataclass
class ColourGamut:
    red: XYColour
    green: XYColour
    blue: XYColour

    @classmethod
    def from_json(cls, data: dict) -> ColourGamut:
        return cls(
            red=XYColour(**data["red"]),
            green=XYColour(**data["green"]),
            blue=XYColour(**data["blue"]),
        )

    def to_json(self):
        return {
            "red": self.red.to_json(),
            "green": self.green.to_json(),
            "blue": self.blue.to_json(),
        }


@dataclass
class Colour:
    xy: XYColour
    gamut: ColourGamut
    gamut_type: str

    @classmethod
    def from_json(cls, data: dict) -> Colour:
        return cls(
            xy=XYColour(**data["xy"]),
            gamut=ColourGamut.from_json(data["gamut"]),
            gamut_type=data["gamut_type"],
        )

    def to_json(self):
        return {
            "xy": self.xy.to_json(),
        }

    def set(self, x: float, y: float) -> XYColour:
        return self.xy.set(x, y)

    def set_rgb(self, red: float, green: float, blue: float) -> XYColour:
        self.xy = XYColour.from_rgb(red, green, blue)
        return self.xy

    def set_hex(self, hex_code: str) -> XYColour:
        self.xy = XYColour.from_hex(hex_code)
        return self.xy

    def set_random(self):
        return self.xy.set_random()


@dataclass
class Dynamics:
    status: str
    status_values: List[str]
    speed: float
    speed_valid: bool

    @classmethod
    def from_json(cls, data: dict) -> Dynamics:
        return cls(
            status=data["status"],
            status_values=data["status_values"],
            speed=data["speed"],
            speed_valid=data["speed_valid"],
        )


@dataclass
class Alert:
    action_values: List[str]


@dataclass
class Light:
    id: str
    id_v1: str
    owner: Owner
    metadata: MetaData
    _on: On
    dimming: Dimming
    dimming_delta: dict
    colour_temperature: ColourTemp
    colour_temperature_delta: dict
    colour: Colour
    dynamics: Dynamics
    _alert: Alert
    signaling: dict
    mode: str
    type: str
    _client: Client

    @property
    def name(self):
        return self.metadata.name

    @property
    def url(self):
        return BASE_URL.format(ip=self._client.ip) + f"resource/light/{self.id}"

    @property
    def on(self):
        return self._on.on

    async def __aenter__(self):
        pass

    async def __aexit__(self, *args):
        await self.edit()

    @classmethod
    def from_json(cls, data: dict, client: Client) -> Light:
        return cls(
            id=data["id"],
            id_v1=data["id_v1"],
            owner=Owner(**data["owner"]),
            metadata=MetaData.from_json(data["metadata"]),
            _on=On(**data["on"]),
            dimming=Dimming(**data["dimming"]),
            dimming_delta=data["dimming_delta"],
            colour_temperature=ColourTemp.from_json(data["color_temperature"]),
            colour_temperature_delta=data["color_temperature_delta"],
            colour=Colour.from_json(data["color"]),
            dynamics=Dynamics.from_json(data["dynamics"]),
            _alert=Alert(**data["alert"]),
            signaling=data.get("signalning", {}),
            mode=data["mode"],
            type=data["type"],
            _client=client,
        )

    def to_json(self) -> dict:
        return {
            "dimming": self.dimming.to_json(),
            "on": self._on.to_json(),
            "color": self.colour.to_json(),
            "color_temperature": self.colour_temperature.to_json(),
        }

    def set_xy(self, x: float, y: float) -> XYColour:
        """Set the light x,y colour values

        Note: This function, along with all the 'set' methods do not
        perform the change but rather need an awaited call to edit them.
        Consider using `async with light:` instead or remember to do
        `await light.edit()` when done making changes.
        """
        return self.colour.set(x, y)

    def set_rgb(self, red: float, green: float, blue: float) -> XYColour:
        return self.colour.set_rgb(red, green, blue)

    def set_hex(self, hex_code: str) -> XYColour:
        return self.colour.set_hex(hex_code)

    def set_brightness(self, brightness: float) -> float:
        """Set the light brightness and return the new brightness value

        Note: This function, along with all the 'set' methods do not
        perform the change but rather need an awaited call to edit them.
        Consider using `async with light:` instead or remember to do
        `await light.edit()` when done making changes.
        """
        return self.dimming.set_brightness(brightness)

    def set_colour_temperature(self, mirek: int) -> int:
        return self.colour_temperature.set(mirek)

    def set_colour_temperature_k(self, temperature: int) -> int:
        return self.colour_temperature.set_kelvin(temperature)

    def set_random_colour(self):
        return self.colour.set_random()

    async def edit(self):
        body = self.to_json()
        log.verbose("Light - edit - body: $s", body)
        return await self._client.request("PUT", self.url, body=body)

    async def flash(
        self, xy_1: Tuple[float, ...], xy_2: Tuple[float, ...], number: int, freq: float
    ):
        old_colour = self.colour.to_json()
        on = self.on
        if not self.on:
            await self.switch()
        old_brightness = self.dimming.to_json()
        for i in range(number):
            async with self:
                self.set_xy(xy_1[0], xy_1[1])
                self.set_brightness(100.0)
            await asyncio.sleep(freq)
            async with self:
                self.set_xy(xy_2[0], xy_2[1])
            await asyncio.sleep(freq)
        async with self:
            self.set_xy(old_colour["xy"]["x"], old_colour["xy"]["y"])
            self._on.on = on
            self.set_brightness(old_brightness["brightness"])

    async def switch(self):
        """Switch the light state from on to off"""
        self._on.on = not self.on
        return await self.edit()

    async def turn_on(self):
        self._on.on = True
        return await self.edit()

    async def turn_off(self):
        self._on.on = False
        return await self.edit()

    async def alert(self):
        return await self._client.request("PUT", self.url, body={"alert": {"action": "breathe"}})

    async def edit_temperature(self, mirek: int):
        self.set_colour_temperature(mirek)
        return await self.edit()

    async def edit_temperature_k(self, temperature: int):
        self.set_colour_temperature_k(temperature)
        return await self.edit()

    async def edit_brightness(self, brightness: float):
        self.set_brightness(brightness)
        return await self.edit()

    async def edit_colour(self, new_colour: XYColour):
        self.colour.xy = new_colour
        return await self.edit()

    async def edit_colour_rgb(self, red: float, green: float, blue: float):
        new_colour = XYColour.from_rgb(red, green, blue)
        return await self.edit_colour(new_colour)

    async def edit_colour_hex(self, hex_code: str):
        new_colour = XYColour.from_hex(hex_code)
        return await self.edit_colour(new_colour)

    async def edit_xy(self, x: float, y: float):
        self.set_xy(x, y)
        return await self.edit()


class Client:
    def __init__(self, ip: str, username: Optional[str] = None, clientkey: Optional[str] = None):
        self.ip = ip
        self.session: aiohttp.ClientSession = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False)
        )
        self.username = username
        self.clientkey = clientkey
        if self.username and self.clientkey:
            self.session.headers["hue-application-key"] = self.username
        self.name = "TrustyCogs#hue-cog"
        self._devices: Dict[str, Device] = {}
        self._lights: Dict[str, Light] = {}

    def __repr__(self):
        return f"<Hue Client {self.ip=}>"

    async def close(self):
        if not self.session.closed:
            await self.session.close()

    @property
    def authed(self) -> bool:
        return self.clientkey is not None

    async def request(
        self,
        method: str,
        url: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        async with self.session.request(method, url, json=body, params=params) as resp:
            data = await resp.json()
            log.verbose("Light - request - data: $s", data)
            if "errors" in data:
                for error in data["errors"]:
                    log.verbose("Client, error description: %s", error["description"])
        return data

    async def auth(self):
        data = await self.request(
            "POST",
            f"https://{self.ip}/api",
            body={"devicetype": self.name, "generateclientkey": True},
        )
        for resp in data:
            if "success" in resp:
                self.username = resp["success"]["username"]
                self.clientkey = resp["success"]["clientkey"]
                self.session.headers["hue-application-key"] = self.username
                return resp
            if "error" in resp:
                raise HueError(resp["error"])
        return data

    @property
    def devices(self) -> List[Device]:
        return list(self._devices.values())

    @property
    def lights(self) -> List[Light]:
        return list(self._lights.values())

    async def get_light_named(self, name: str) -> Optional[Light]:
        if not self.lights:
            await self.get_lights()
        for light in self.lights:
            if name.lower() in light.name.lower():
                return light
        return None

    async def get_lights(self):
        data = await self.request("GET", BASE_URL.format(ip=self.ip) + "resource/light")
        for light in data["data"]:
            self._lights[light["id"]] = Light.from_json(light, self)
        return self.lights

    async def get_devices(self) -> List[Device]:
        data = await self.request("GET", BASE_URL.format(ip=self.ip) + "resource/device")
        for d in data["data"]:
            self._devices[d["id"]] = Device.from_json(d, self)
        return self.devices
