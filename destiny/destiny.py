import discord
import logging
import asyncio

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .errors import *
from .api import DestinyAPI


BASE_URL = "https://www.bungie.net/Platform"
IMAGE_URL = "https://www.bungie.net"
AUTH_URL = "https://www.bungie.net/en/oauth/authorize"
TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
_ = Translator("Destiny", __file__)
log = logging.getLogger("red.Destiny")


@cog_i18n(_)
class Destiny(DestinyAPI, commands.Cog):
    """
        Get information from the Destiny 2 API
    """

    __version__ = "1.0.0"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        default_global = {
            "api_token": {"api_key": "", "client_id": "", "client_secret": ""},
            "manifest_version": "",
        }
        default_user = {"oauth": {}, "account": {}}
        self.config = Config.get_conf(self, 35689771456)
        self.config.register_global(**default_global, force_registration=True)
        self.config.register_user(**default_user, force_registration=True)
        self.throttle: float = 0
        # self.manifest_download_start = bot.loop.create_task(self.get_manifest())

    @commands.group()
    async def destiny(self, ctx):
        """Get information from the Destiny 2 API"""
        pass

    @destiny.group(aliases=["s"])
    async def search(self, ctx: commands.Context):
        """
            Search for a destiny item, vendor, record, etc.
        """
        pass

    @search.command(aliases=["item"])
    @commands.bot_has_permissions(embed_links=True)
    async def items(self, ctx: commands.Context, *, search: str):
        """
            Search for a specific item in Destiny 2
        """
        try:
            items = await self.search_definition("DestinyInventoryItemDefinition", search)
        except Destiny2MissingManifest as e:
            await ctx.send(e)
            return
        if not items:
            await ctx.send(_("`{search}` could not be found.").format(search=search))
            return
        embeds = []
        log.debug(items[0])
        for item in items:
            if not (item["equippable"]):
                continue
            embed = discord.Embed()
            embed.description = item["displayProperties"]["description"]
            embed.title = item["itemTypeAndTierDisplayName"]
            name = item["displayProperties"]["name"]
            icon_url = IMAGE_URL + item["displayProperties"]["icon"]
            embed.set_author(name=name, icon_url=icon_url)
            embed.set_thumbnail(url=icon_url)
            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def user(self, ctx: commands.Context):
        """
            Display a menu of your basic characters info
        """
        if not await self.has_oauth(ctx):
            return
        try:
            chars = await self.get_characters(ctx.author)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            info = ""
            race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
            gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
            char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
            info += "{race} {gender} {char_class} ".format(
                race=race[0]["displayProperties"]["name"],
                gender=gender[0]["displayProperties"]["name"],
                char_class=char_class[0]["displayProperties"]["name"],
            )
            titles = ""
            if "titleRecordHash" in char:
                # TODO: Add fetch for Destiny.Definitions.Records.DestinyRecordDefinition
                char_title = await self.get_definition(
                    "DestinyRecordDefinition", [char["titleRecordHash"]]
                )
                title_info = "**{title_name}**\n{title_desc}\n"
                for t in char_title:
                    try:
                        title_name = t["titleInfo"]["titlesByGenderHash"][str(char["genderHash"])]
                        title_desc = t["displayProperties"]["description"]
                        titles += title_info.format(title_name=title_name, title_desc=title_desc)
                    except:
                        pass
            embed = discord.Embed(title=info)
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
            if "emblemPath" in char:
                embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
            items = chars["characterEquipment"]["data"][char_id]["items"]
            # log.debug(data)
            level = char["baseCharacterLevel"]
            light = char["light"]
            level_str = _("Level: **{level}**  \nLight: **{light}**").format(
                level=level, light=light
            )
            embed.description = level_str
            embed = await self.get_char_colour(embed, char)
            if titles:
                embed.add_field(name=_("Titles"), value=titles)
            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command(aliases=["xûr"])
    @commands.bot_has_permissions(embed_links=True)
    async def xur(self, ctx: commands.Context):
        """
            Display a menu of Xûr's current wares
        """
        if not await self.has_oauth(ctx):
            return
        try:
            chars = await self.get_characters(ctx.author)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)
            try:
                xur = await self.get_vendor(ctx.author, char_id, "2190858386")
            except Destiny2APIError:
                log.error("I can't seem to see Xûr at the moment")
                await ctx.send(_("Come back on the weekend when Xûr is around."))
                return
            break
        items = [v["itemHash"] for k, v in xur["sales"]["data"].items()]
        data = await self.get_definition("DestinyInventoryItemDefinition", items)
        embeds = []
        for item in data:
            if not (item["equippable"]):
                continue
            embed = discord.Embed()
            embed.description = item["displayProperties"]["description"]
            embed.title = item["itemTypeAndTierDisplayName"]
            name = item["displayProperties"]["name"]
            icon_url = IMAGE_URL + item["displayProperties"]["icon"]
            embed.set_author(name=name, icon_url=icon_url)
            embed.set_thumbnail(url=icon_url)
            embeds.append(embed)

        # await ctx.tick()
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def eververse(self, ctx: commands.Context):
        """
            Display items available on the eververse right now
        """
        if not await self.has_oauth(ctx):
            return
        try:
            chars = await self.get_characters(ctx.author)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            log.debug(char_id)
            try:
                eververse = await self.get_vendor(ctx.author, char_id, "3361454721")
            except Destiny2APIError as e:
                log.error("I can't seem to see the eververse at the moment", exc_info=True)
                await ctx.send(_("I can't access the eververse at the moment."))
                return
            break
        items = [v["itemHash"] for k, v in eververse["sales"]["data"].items()]
        data = await self.get_definition("DestinyInventoryItemDefinition", items)
        embeds = []
        for item in data:
            if not (item["equippable"]):
                continue
            embed = discord.Embed()
            embed.description = item["displayProperties"]["description"]
            embed.title = item["itemTypeAndTierDisplayName"]
            name = item["displayProperties"]["name"]
            icon_url = IMAGE_URL + item["displayProperties"]["icon"]
            embed.set_author(name=name, icon_url=icon_url)
            embed.set_thumbnail(url=icon_url)
            embeds.append(embed)

        # await ctx.tick()
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def loadout(self, ctx: commands.Context):
        """
            Display a menu of each characters equipped weapons and their info
        """
        if not await self.has_oauth(ctx):
            return
        try:
            chars = await self.get_characters(ctx.author)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)
            info = ""
            race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
            gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
            char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
            info += "{race} {gender} {char_class} ".format(
                race=race[0]["displayProperties"]["name"],
                gender=gender[0]["displayProperties"]["name"],
                char_class=char_class[0]["displayProperties"]["name"],
            )
            titles = ""
            if "titleRecordHash" in char:
                # TODO: Add fetch for Destiny.Definitions.Records.DestinyRecordDefinition
                char_title = await self.get_definition(
                    "DestinyRecordDefinition", [char["titleRecordHash"]]
                )
                title_info = "**{title_name}**\n{title_desc}\n"
                for t in char_title:
                    title_name = t["titleInfo"]["titlesByGenderHash"][char["genderHash"]]
                    title_desc = t["displayProperties"]["description"]
                    titles += title_info.format(title_name=title_name, title_desc=title_desc)
                log.debug("User has a title")
                pass
            embed = discord.Embed(title=info)
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
            if "emblemPath" in char:
                embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
            if titles:
                embed.add_field(name=_("Titles"), value=titles)
            char_items = chars["characterEquipment"]["data"][char_id]["items"]
            item_list = [i["itemHash"] for i in char_items]
            # log.debug(item_list)
            items = await self.get_definition("DestinyInventoryItemDefinition", item_list)
            # log.debug(items)
            for data in items:
                # log.debug(data)
                for item in char_items:
                    # log.debug(item)
                    if data["hash"] == item["itemHash"]:
                        instance_id = item["itemInstanceId"]
                item_instance = chars["itemComponents"]["instances"]["data"][instance_id]
                if not item_instance["isEquipped"]:
                    continue

                if not (data["equippable"] and data["itemType"] == 3):
                    continue
                name = data["displayProperties"]["name"]
                desc = data["displayProperties"]["description"]
                item_type = data["itemTypeAndTierDisplayName"]
                try:
                    light = item_instance["primaryStat"]["value"]
                except KeyError:
                    light = ""
                perk_list = chars["itemComponents"]["perks"]["data"][instance_id]["perks"]
                perk_hashes = [p["perkHash"] for p in perk_list]
                perk_data = await self.get_definition("DestinySandboxPerkDefinition", perk_hashes)
                perks = ""
                for perk in perk_data:
                    properties = perk["displayProperties"]
                    if "name" in properties and "description" in properties:
                        perks += "**{0}** - {1}\n".format(
                            properties["name"], properties["description"]
                        )

                value = f"**{light}** {item_type}\n{desc}\n{perks}"
                embed.add_field(name=name, value=value)
            # log.debug(data)
            level = char["baseCharacterLevel"]
            light = char["light"]
            level_str = _("Level: **{level}**  \nLight: **{light}**").format(
                level=level, light=light
            )
            embed.description = level_str
            embed = await self.get_char_colour(embed, char)

            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @checks.is_owner()
    @commands.bot_has_permissions(add_reactions=True)
    async def manifest(self, ctx):
        """
            See the current manifest version and optionally re-download it
        """
        version = await self.config.manifest_version()
        if not version:
            version = "Not Downloaded"
        await ctx.send(_("Current manifest version is {version}").format(version=version))
        while True:
            msg = await ctx.send(_("Would you like to re-download the manifest?"))
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            check = lambda r, u: u == ctx.author and str(r.emoji) in ["✅", "❌"]
            try:
                react, user = await self.bot.wait_for("reaction_add", check=check, timeout=15)
            except asyncio.TimeoutError:
                await msg.delete()
                break
            if str(react.emoji) == "✅":
                try:
                    await self.get_manifest()
                except:
                    await ctx.send(_("There was an issue downloading the manifest."))
                await msg.delete()
                await ctx.tick()
                break
            else:
                await msg.delete()
                break

    @destiny.command()
    @checks.is_owner()
    async def token(self, ctx, api_key: str, client_id: str, client_secret: str):
        """
        Set the API tokens for Destiny 2's API

        Required information is found at:
        https://www.bungie.net/en/Application 
        select create a new application
        choose **Confidential** OAuth Client type
        Select the scope you would like the bot to have access to
        Set the redirect URL to https://localhost/
        NOTE: It is strongly recommended to use this command in DM
        """
        await self.config.api_token.api_key.set(api_key)
        await self.config.api_token.client_id.set(client_id)
        await self.config.api_token.client_secret.set(client_secret)
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        await ctx.send("Destiny 2 API credentials set!")
        # msg = await ctx.send(_("Downloading Manifest..."))
        # async with ctx.typing():
            # await self.get_manifest()
            # await ctx.send(_("Done."))
