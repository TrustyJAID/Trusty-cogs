from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, Optional

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import bounded_gather

from .menus import (
    BaseMenu,
    EPICPages,
    MarsRoverManifest,
    MarsRoverPhotos,
    NASAapod,
    NASAEventPages,
    NASAImagesCollection,
)
from .models import (
    Asset,
    Collection,
    EPICData,
    Event,
    MarsRovers,
    NASAapodAPI,
    NASAAstronomyPictureOfTheDay,
    NASAEarthAsset,
    NASAImagesAPI,
    PhotoManifest,
    RoverPhoto,
)

if TYPE_CHECKING:
    from redbot.core.bot import Red

_ = Translator("NASA", __file__)

log = logging.getLogger("red.trusty-cogs.NASACog")


class APIError(Exception):
    pass


@cog_i18n(_)
class NASACog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Trusty-cogs NASA cog for Red-DiscordBot"}
        )
        self._last_rate_limit_remaining = 1000
        self._last_rate_limit_limit = None
        self.config = Config.get_conf(self, 218773382617890828, force_registration=True)
        self.config.register_channel(guild_id=None, apod=False)
        self.config.register_global(last_apod=None)
        self.apod_loop.start()

    async def cog_unload(self):
        await self.session.close()

    @tasks.loop(seconds=3600)
    async def apod_loop(self):
        parameters = {"thumbs": "True"}
        try:
            data = await self.request("https://api.nasa.gov/planetary/apod", parameters=parameters)
        except APIError:
            log.exception("Error in Astronomy Photo of the Day loop")
            return
        try:
            apod = NASAAstronomyPictureOfTheDay.from_json(data)
        except KeyError:
            if "msg" in data:
                log.exception(f"Error in Astronomy Photo of the Day loop {data['msg']}")
            else:
                log.exception("Error in Astronomy Photo of the Day loop")
            return
        try:
            embed = await NASAapod([]).format_page(None, apod)
        except Exception:
            log.exception("error building embed")
            return
        if apod.url == await self.config.last_apod():
            return
        await self.config.last_apod.set(apod.url)
        all_channels = await self.config.all_channels()
        tasks = []
        for channel_id, data in all_channels.items():
            if not data["apod"]:
                continue
            if not data["guild_id"]:
                continue
            guild = self.bot.get_guild(data["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel_or_thread(channel_id)
            if not channel:
                await self.config.channel_from_id(channel_id).clear()
                continue
            tasks.append(channel.send(embed=embed))
        await bounded_gather(*tasks, return_exceptions=True)

    @apod_loop.before_loop
    async def before_apod_loop(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_group(name="nasa")
    async def nasa(self, ctx: commands.Context):
        """Commands for interacting with NASA's API"""
        pass

    @nasa.command(name="apodchannel", with_app_command=False)
    @commands.mod_or_permissions(manage_channels=True)
    async def automatic_apod(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Toggle a channel for NASA's Astronomy Photo of the Day
        """
        if channel is None:
            channel = ctx.channel
        await self.config.channel(channel).guild_id.set(channel.guild.id)
        if await self.config.channel(channel).apod():
            await self.config.channel.clear()
            await ctx.send(
                _("I will no longer post NASA's Astronomy Photo of the Day in {channel}.").format(
                    channel=channel.mention
                )
            )
        else:
            await self.config.channel(channel).apod.set(True)
            await ctx.send(
                _("Posting NASA's Astronomy Photo of the Day in {channel}.").format(
                    channel=channel.mention
                )
            )

    @nasa.command(name="apod")
    async def nasa_apod(self, ctx: commands.Context, *, query: NASAapodAPI):
        """NASA's Astronomy Picture of the day"""
        async with ctx.typing():
            parameters = query.parameters
            parameters["thumbs"] = "True"
            try:
                data = await self.request(
                    "https://api.nasa.gov/planetary/apod", parameters=parameters
                )
            except APIError as e:
                await ctx.send(e)
                return
            pods = []
            if isinstance(data, list):
                for i in data:
                    try:
                        pods.append(NASAAstronomyPictureOfTheDay.from_json(i))
                    except KeyError:
                        if "msg" in data:
                            await ctx.send(data["msg"])
                            return
            else:
                try:
                    pods.append(NASAAstronomyPictureOfTheDay.from_json(data))
                except KeyError:
                    if "msg" in data:
                        await ctx.send(data["msg"])
                        return
        await BaseMenu(source=NASAapod(pods)).start(ctx=ctx)

    @nasa.command(name="eonet")
    async def nasa_eonet(self, ctx: commands.Context):
        """
        Natural events from EONET.
        """
        async with ctx.typing():
            try:
                data = await self.request("https://eonet.gsfc.nasa.gov/api/v3/events")
            except APIError as e:
                await ctx.send(e)
                return
            events = [Event.from_json(e) for e in data["events"]]
        await BaseMenu(source=NASAEventPages(events)).start(ctx=ctx)

    @nasa.group(name="marsrover", aliases=["rover"])
    async def mars_rovers(self, ctx: commands.Context):
        """Pull images from Mars Rovers Curiosity, Opportunity, and Spirit"""
        pass

    @mars_rovers.command(name="manifest")
    async def mars_rover_manifest(
        self, ctx: commands.Context, rover_name: Literal["curiosity", "spirit", "opportunity"]
    ):
        """Get mission manifest information for a specified Mars Rover"""
        async with ctx.typing():
            url = f"https://api.nasa.gov/mars-photos/api/v1/manifests/{rover_name}"
            try:
                data = await self.request(url)
            except APIError as e:
                await ctx.send(e)
                return
            manifest = PhotoManifest.from_json(data["photo_manifest"])
        await BaseMenu(source=MarsRoverManifest(manifest)).start(ctx=ctx)

    @mars_rovers.command(name="curiosity")
    async def mars_curiosity(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Curiosity

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos. Must be one of
        FHAZ, RHAZ, MAST, CHEMCAM, MAHLI, MARDI, or NAVCAM
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.
        """
        async with ctx.typing():
            url = "https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/photos"
            try:
                data = await self.request(url, parameters=query.parameters)
            except APIError as e:
                await ctx.send(e)
                return
            photos = [RoverPhoto.from_json(p) for p in data["photos"]]
            if not photos:
                await ctx.send(_("No images could be found for the provided parameters."))
                return
        await BaseMenu(source=MarsRoverPhotos(photos)).start(ctx=ctx)

    @mars_rovers.command(name="opportunity")
    async def mars_opportunity(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Opportunity

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos. Must be one of
        FHAZ, RHAZ, NAVCAM, PANCAM, or MINITES
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.
        """
        async with ctx.typing():
            url = "https://api.nasa.gov/mars-photos/api/v1/rovers/opportunity/photos"
            try:
                data = await self.request(url, parameters=query.parameters)
            except APIError as e:
                await ctx.send(e)
                return
            photos = [RoverPhoto.from_json(p) for p in data["photos"]]
            if not photos:
                await ctx.send(_("No images could be found for the provided parameters."))
                return
        await BaseMenu(source=MarsRoverPhotos(photos)).start(ctx=ctx)

    @mars_rovers.command(name="spirit")
    async def mars_spirit(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Spirit

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos. Must be one of
        FHAZ, RHAZ, NAVCAM, PANCAM, or MINITES
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.
        """
        async with ctx.typing():
            url = "https://api.nasa.gov/mars-photos/api/v1/rovers/spirit/photos"
            try:
                data = await self.request(url, parameters=query.parameters)
            except APIError as e:
                await ctx.send(e)
                return
            photos = [RoverPhoto.from_json(p) for p in data["photos"]]
            if not photos:
                await ctx.send(_("No images could be found for the provided parameters."))
                return
        await BaseMenu(source=MarsRoverPhotos(photos)).start(ctx=ctx)

    @nasa.group(name="epic")
    async def nasa_epic(self, ctx: commands.Context):
        """Images from DSCOVR's Earth Polychromatic Imaging Camera"""
        pass

    @nasa_epic.command(name="natural")
    async def nasa_epic_natural(self, ctx: commands.Context):
        """Natural photos from DSCOVR's Earth Polychromatic Imaging Camera"""
        async with ctx.typing():
            try:
                data = await self.request("https://api.nasa.gov/EPIC/api/natural/images")
            except APIError as e:
                await ctx.send(e)
                return
            pages = [EPICData.from_json(i) for i in data]
        await BaseMenu(source=EPICPages(pages)).start(ctx=ctx)

    @nasa_epic.command(name="enhanced")
    async def nasa_epic_enhanced(self, ctx: commands.Context):
        """Enhanced photos from DSCOVR's Earth Polychromatic Imaging Camera"""
        async with ctx.typing():
            try:
                data = await self.request("https://api.nasa.gov/EPIC/api/enhanced/images")
            except APIError as e:
                await ctx.send(e)
                return
            pages = [EPICData.from_json(i) for i in data]
        await BaseMenu(source=EPICPages(pages, enhanced=True)).start(ctx=ctx)

    @nasa.command(name="images")
    async def nasa_images_and_videos(self, ctx: commands.Context, *, query: NASAImagesAPI):
        """
        Search through NASA's images and videos

        `<query>` supports all available parameters from the API.
        https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf

        e.g. `[p]nasa images q: apollo 11 year_end: 1970` for all images associated with Apollo 11
        until 1970.
        """
        async with ctx.typing():
            try:
                data = await self.request(
                    "https://images-api.nasa.gov/search", query.parameters, include_api_key=False
                )
            except APIError as e:
                await ctx.send(e)
                return
            collection = Collection.from_json(data)
            # log.info(collection)
        if not collection.items:
            await ctx.send(_("Nothing could be found matching those parameters."))
            return
        await BaseMenu(source=NASAImagesCollection(collection), cog=self).start(ctx=ctx)

    @nasa.command(name="earth")
    async def nasa_earth_image(self, ctx: commands.Context, *, query: NASAEarthAsset):
        """
        Images of Earth from satelite

        Required parameters:
            `lat:` The Latitude.
            `lon:` The Longitude.
            `date:` YYYY-MM-DD formate of the date range to search for.
        Optional parameters:
            `dim:` Width and height in degrees.

        e.g. `[p]nasa earth lat: 29.78 lon: 95.33 date: 2018-01-01 dim: 0.10`
        """
        async with ctx.typing():
            try:
                data = await self.request(
                    "https://api.nasa.gov/planetary/earth/assets", query.parameters
                )
            except APIError as e:
                await ctx.send(e)
                return
            earth = Asset.from_json(data)
            em = discord.Embed(title=f"{earth.resource.dataset} {earth.resource.planet}")
            em.set_image(url=earth.url)
        await ctx.send(embed=em)

    async def request(self, url: str, parameters: dict = {}, include_api_key: bool = True) -> dict:

        if include_api_key:
            tokens = await self.bot.get_shared_api_tokens("nasa")
            parameters["api_key"] = tokens.get("api_key", "DEMO_KEY")
        async with self.session.get(url, params=parameters) as resp:
            self._last_rate_limit_remaining = int(resp.headers.get("X-RateLimit-Remaining", 1000))
            self._last_rate_limit_limit = resp.headers.get("X-RateLimit-Limit", None)
            if resp.status == 200:
                data = await resp.json()
                log.info(resp.url)
            else:
                raise APIError(
                    f"There was an error with the API: Error Code {resp.status}\n"
                    f"Rate Limit: {self._last_rate_limit_limit}\n"
                    f"Remaining: {self._last_rate_limit_remaining}"
                )
        return data
