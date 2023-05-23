from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

import aiohttp
import discord
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import bounded_gather
from redbot.core.utils.views import SetApiView

from .menus import (
    BaseMenu,
    EPICPages,
    MarsRoverManifest,
    MarsRoverPhotos,
    NASAapod,
    NASAEventPages,
    NASAImagesCollection,
    NEOFeedPages,
    TLEPages,
)
from .models import (
    HEADERS,
    APIError,
    Asset,
    Collection,
    EPICData,
    Event,
    MarsRovers,
    NASAapodAPI,
    NASAAstronomyPictureOfTheDay,
    NASAEarthAsset,
    NASAImagesAPI,
    NASANearEarthObjectAPI,
    NASATLEFeed,
    NEOFeed,
    PhotoManifest,
    RoverPhoto,
)

if TYPE_CHECKING:
    from redbot.core.bot import Red

_ = Translator("NASA", __file__)

log = getLogger("red.trusty-cogs.NASACog")


@cog_i18n(_)
class NASACog(commands.Cog):
    __author__ = ["TrustyJAID"]
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession(headers=HEADERS)
        self._last_rate_limit_remaining = 1000
        self._last_rate_limit_limit = None
        self.config = Config.get_conf(self, 218773382617890828, force_registration=True)
        self.config.register_channel(guild_id=None, apod=False)
        self.config.register_global(last_apod=None)
        self.apod_loop.start()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        # Nothing to delete
        return

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
            embed = apod.embed()
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
            if not channel.permissions_for(guild.me).embed_links:
                await self.config.channel(channel).clear()
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

    @nasa.command(name="creds", with_app_command=False)
    @commands.is_owner()
    async def set_nasa_api(self, ctx: commands.Context):
        """Instructions to set the your NASA API Key"""
        message = _(
            "1. Go to https://api.nasa.gov.\n"
            '2. Fill out the form to Generate and API Key".\n'
            "3. Copy your API key into:\n"
            "`{prefix}set api nasa api_key YOUR_API_KEY_HERE`"
        ).format(prefix=ctx.prefix)
        keys = {"api_key": ""}
        view = SetApiView("nasa", keys)
        if await ctx.embed_requested():
            em = discord.Embed(description=message)
            await ctx.send(embed=em, view=view)
            # await ctx.send(embed=em)
        else:
            await ctx.send(message, view=view)
            # await ctx.send(message)

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
        if not channel.permissions_for(ctx.me).embed_links:
            await ctx.send(
                _(
                    "I require embed links permission in {channel} to post the photo of the day."
                ).format(channel=channel.mention)
            )
            return
        if await self.config.channel(channel).apod():
            await self.config.channel.clear()
            await ctx.send(
                _("I will no longer post NASA's Astronomy Photo of the Day in {channel}.").format(
                    channel=channel.mention
                )
            )
        else:
            await self.config.channel(channel).guild_id.set(channel.guild.id)
            await self.config.channel(channel).apod.set(True)
            await ctx.send(
                _("Posting NASA's Astronomy Photo of the Day in {channel}.").format(
                    channel=channel.mention
                )
            )
            tokens = await self.bot.get_shared_api_tokens("nasa")
            api_key = tokens.get("api_key", "DEMO_KEY")
            apod = await NASAAstronomyPictureOfTheDay.today(api_key, session=self.session)
            await channel.send(embed=apod.embed())

    @nasa.command(name="apod")
    @commands.bot_has_permissions(embed_links=True)
    async def nasa_apod(self, ctx: commands.Context, *, query: NASAapodAPI):
        """
        NASA's Astronomy Picture of the day

        `count:` Pull a random number of Photo's of the day in a menu
        `date:` Pick a specific date's photo `YYYY-MM-DD`
        `start_date:` The start date to pull Photos of the day from `YYYY-MM-DD`
        `end_date:` The end date to pull photos of the day from `YYYY-MM-DD`

        e.g. `[p]nasa apod date: 2022-06-11` to get the Astronomy Photo of the Day
        for June 11th, 2022.
        """
        async with ctx.typing():
            params = query.parameters
            if params.get("count", None) and any(
                params.get(k) for k in ["start_date", "end_date", "date"]
            ):
                await ctx.send(_("You cannot include count and any date parameters."))
                return
            if params.get("start_date", None) and params.get("date", None):
                await ctx.send(_("You cannot include date and start_date parameters."))
                return
            params["thumbs"] = "True"
            try:
                data = await self.request("https://api.nasa.gov/planetary/apod", parameters=params)
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
    @commands.bot_has_permissions(embed_links=True)
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

    @nasa.group(name="mars")
    async def mars(self, ctx: commands.Context):
        """Pull images from Mars Rovers Curiosity, Opportunity, Perseverance, and Spirit"""
        pass

    @nasa.command(name="neo")
    @commands.bot_has_permissions(embed_links=True)
    async def nasa_neo(self, ctx: commands.Context, *, query: NASANearEarthObjectAPI):
        """
        Get Near Earth Object information from NASA
        """
        async with ctx.typing():
            url = "https://api.nasa.gov/neo/rest/v1/feed"
            try:
                data = await self.request(url, parameters=query.parameters)
            except APIError as e:
                await ctx.send(e)
                return
            feed = NEOFeed.from_json(data)
        await BaseMenu(source=NEOFeedPages(feed)).start(ctx=ctx)

    @mars.command(name="rovermanifest")
    @commands.bot_has_permissions(embed_links=True)
    async def mars_rover_manifest(
        self,
        ctx: commands.Context,
        rover_name: Literal["curiosity", "spirit", "opportunity", "perseverance"],
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

    @mars.command(name="perseverance")
    @commands.bot_has_permissions(embed_links=True)
    async def mars_perseverance(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Perseverance

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos.
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.

        see `[p]nasa mars rovermanifest perseverence`
        """
        async with ctx.typing():
            url = "https://api.nasa.gov/mars-photos/api/v1/rovers/perseverance/photos"
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

    @mars.command(name="curiosity")
    @commands.bot_has_permissions(embed_links=True)
    async def mars_curiosity(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Curiosity

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos.
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.

        see `[p]nasa mars rovermanifest curiosity`
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

    @mars.command(name="opportunity")
    @commands.bot_has_permissions(embed_links=True)
    async def mars_opportunity(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Opportunity

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos.
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.

        see `[p]nasa mars rovermanifest opportunity`
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

    @mars.command(name="spirit")
    @commands.bot_has_permissions(embed_links=True)
    async def mars_spirit(self, ctx: commands.Context, *, query: MarsRovers):
        """
        Images from Mars Rover Spirit

        `sol:` The sol date of when the images were taken
        `camera:` The camera used to take the photos.
        `page:` The page number of the images to lookup. Each page holds up to
        25 images.
        `earth_date:` The equivalent earth date for the sol to lookup.

        see `[p]nasa mars rovermanifest spirit`
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
    @commands.bot_has_permissions(embed_links=True)
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
    @commands.bot_has_permissions(embed_links=True)
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
    @commands.bot_has_permissions(embed_links=True)
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
                collection = await Collection.from_params(query.parameters, session=self.session)
            except APIError as e:
                await ctx.send(e)
                return
            # log.info(collection)
        if not collection.items:
            await ctx.send(_("Nothing could be found matching those parameters."))
            return
        await BaseMenu(source=NASAImagesCollection(collection), cog=self).start(ctx=ctx)

    @nasa.command(name="earth")
    @commands.bot_has_permissions(embed_links=True)
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

    @nasa.command(name="tle")
    @commands.bot_has_permissions(embed_links=True)
    async def nasa_tle(self, ctx: commands.Context, *, search: Optional[str] = None):
        """Search through TLE data for various satelites"""
        async with ctx.typing():
            try:
                feed = await NASATLEFeed.search(search, session=self.session)
            except APIError as e:
                await ctx.send(e)
                return
        if not feed.member:
            await ctx.send(_("No satellites could be found with that search term."))
            return
        await BaseMenu(source=TLEPages(feed)).start(ctx=ctx)

    async def request(self, url: str, parameters: dict = {}, include_api_key: bool = True) -> dict:
        if include_api_key:
            tokens = await self.bot.get_shared_api_tokens("nasa")
            parameters["api_key"] = tokens.get("api_key", "DEMO_KEY")
        async with self.session.get(url, params=parameters) as resp:
            self._last_rate_limit_remaining = int(resp.headers.get("X-RateLimit-Remaining", 1000))
            self._last_rate_limit_limit = resp.headers.get("X-RateLimit-Limit", None)
            if resp.status == 200:
                data = await resp.json()
                log.verbose("Response URL: %s", resp.url)
            else:
                raise APIError(
                    f"There was an error with the API: Error Code {resp.status}\n"
                    f"Rate Limit: {self._last_rate_limit_limit}\n"
                    f"Remaining: {self._last_rate_limit_remaining}"
                )
        return data
