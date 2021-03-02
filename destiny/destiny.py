import asyncio
import datetime
import logging
import json
import functools
from pathlib import Path
from typing import List, Literal, Optional
from copy import copy

import discord
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify, humanize_timedelta
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .api import DestinyAPI
from .converter import DestinyActivity, StatsPage, SearchInfo
from .errors import Destiny2APIError, Destiny2MissingManifest

DEV_BOTS = [552261846951002112]
# If you want parsing the manifest data to be easier add your
# bots ID to this list otherwise this should help performance
# on bots that are just running the cog like normal

BASE_URL = "https://www.bungie.net/Platform"
IMAGE_URL = "https://www.bungie.net"
AUTH_URL = "https://www.bungie.net/en/oauth/authorize"
TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
_ = Translator("Destiny", __file__)
log = logging.getLogger("red.trusty-cogs.Destiny")


@cog_i18n(_)
class Destiny(DestinyAPI, commands.Cog):
    """
    Get information from the Destiny 2 API
    """

    __version__ = "1.4.0"
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
        Method for finding a user's data inside the cog and deleting it.
        """
        await self.config.user_from_id(user_id).clear()

    @staticmethod
    def humanize_timedelta(
        *, timedelta: Optional[datetime.timedelta] = None, seconds: Optional[int] = None
    ) -> str:
        """
        Get a human timedelta representation

        Only here until available in Core Red from PR
        https://github.com/Cog-Creators/Red-DiscordBot/pull/2412
        """

        try:
            obj = seconds or timedelta.total_seconds()
        except AttributeError:
            raise ValueError("You must provide either a timedelta or a number of seconds")

        seconds = int(obj)
        periods = [
            (_("year"), _("years"), 60 * 60 * 24 * 365),
            (_("month"), _("months"), 60 * 60 * 24 * 30),
            (_("day"), _("days"), 60 * 60 * 24),
            (_("hour"), _("hours"), 60 * 60),
            (_("minute"), _("minutes"), 60),
            (_("second"), _("seconds"), 1),
        ]

        strings = []
        for period_name, plural_period_name, period_seconds in periods:
            if seconds >= period_seconds:
                period_value, seconds = divmod(seconds, period_seconds)
                if period_value == 0:
                    continue
                unit = plural_period_name if period_value > 1 else period_name
                strings.append(f"{period_value} {unit}")

        return ", ".join(strings)

    @commands.group()
    async def destiny(self, ctx: commands.Context) -> None:
        """Get information from the Destiny 2 API"""
        pass

    @destiny.command()
    async def forgetme(self, ctx: commands.Context) -> None:
        """
        Remove your authorization to the destiny API on the bot
        """
        await self.red_delete_data_for_user(requester="user", user_id=ctx.author.id)
        await ctx.send(_("Your authorization has been reset."))

    @destiny.group(aliases=["s"])
    async def search(self, ctx: commands.Context) -> None:
        """
        Search for a destiny item, vendor, record, etc.
        """
        pass

    async def get_weapon_possible_perks(self, weapon: dict) -> dict:
        perks = {}
        slot_counter = 1
        count = 2
        for socket in weapon["sockets"]["socketEntries"]:
            if socket["singleInitialItemHash"] in [
                4248210736,
                2323986101,
                0,
                2285418970,
                1282012138,
                2993594586,
            ]:
                continue
            if socket["socketTypeHash"] in [2218962841, 1282012138, 1456031260]:
                continue
            if "randomizedPlugSetHash" in socket:
                pool = (
                    await self.get_definition(
                        "DestinyPlugSetDefinition", [socket["randomizedPlugSetHash"]]
                    )
                )[0]
                pool_perks = [v["plugItemHash"] for v in pool["reusablePlugItems"]]
                all_perks = await self.get_definition("DestinyInventoryItemDefinition", pool_perks)
                try:
                    key_hash = all_perks[0]["itemCategoryHashes"][0]
                    key_data = await self.get_definition("DestinyItemCategoryDefinition", [key_hash])
                    key = key_data[0]["displayProperties"]["name"]
                    if key in perks:
                        key = f"{key} {count}"
                        count += 1
                except IndexError:
                    key = _("Perk {count}").format(count=slot_counter)
                perks[key] = "\n".join(
                    [p["displayProperties"]["name"] for p in all_perks]
                )
                slot_counter += 1
                continue
            if "reusablePlugSetHash" in socket:
                pool = (
                    await self.get_definition(
                        "DestinyPlugSetDefinition", [socket["reusablePlugSetHash"]]
                    )
                )[0]
                pool_perks = [v["plugItemHash"] for v in pool["reusablePlugItems"]]
                all_perks = await self.get_definition("DestinyInventoryItemDefinition", pool_perks)
                try:
                    key_hash = all_perks[0]["itemCategoryHashes"][0]
                    key_data = await self.get_definition("DestinyItemCategoryDefinition", [key_hash])
                    key = key_data[0]["displayProperties"]["name"]
                    if key in perks:
                        key = f"{key} {count}"
                        count += 1
                except IndexError:
                    key = _("Perk {count}").format(count=slot_counter)
                perks[key] = "\n".join(
                    [p["displayProperties"]["name"] for p in all_perks]
                )
                slot_counter += 1
                continue
            perk_hash = socket["singleInitialItemHash"]
            perk = (await self.get_definition("DestinyInventoryItemDefinition", [perk_hash]))[0]
            try:
                key_hash = all_perks[0]["itemCategoryHashes"][0]
                key_data = await self.get_definition("DestinyItemCategoryDefinition", [key_hash])
                key = key_data[0]["displayProperties"]["name"]
                if key in perks:
                    key = f"{key} {count}"
                    count += 1
            except IndexError:
                key = _("Perk {count}").format(count=slot_counter)
            perks[key] = perk["displayProperties"]["name"]
            slot_counter += 1
        return perks

    @search.command(aliases=["item"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.max_concurrency(1, commands.BucketType.default)
    async def items(
        self, ctx: commands.Context, details_or_lore: Optional[SearchInfo] = None, *, search: str
    ) -> None:
        """
        Search for a specific item in Destiny 2

        `[details_or_lore]` signify what information to display for the item
        by default this command will show all available perks on weapons
        using `details`, `true`, or `stats` will show the weapons stat bars
        using `lore` here will instead display the weapons lore card instead if it exists.
        """
        show_lore = True if details_or_lore is False else False
        if search.startswith("lore "):
            search = search.replace("lore ", "")
        async with ctx.typing():
            try:
                items = await self.search_definition("DestinyInventoryItemDefinition", search)
            except Destiny2MissingManifest as e:
                await ctx.send(e)
                return
            if not items:
                await ctx.send(_("`{search}` could not be found.").format(search=search))
                return
            embeds = []
            # log.debug(items[0])
            for item in items:
                if not (item["equippable"]):
                    continue
                embed = discord.Embed()
                description = item["flavorText"] + "\n\n"
                damage_type = ""
                try:
                    damage_data = (
                        await self.get_definition(
                            "DestinyDamageTypeDefinition", [item["defaultDamageTypeHash"]]
                        )
                    )[0]
                    damage_type = damage_data["displayProperties"]["name"]
                except KeyError:
                    pass
                if item["itemType"] in [3] and not show_lore:

                    stats_str = ""
                    rpm = ""
                    recoil = ""
                    magazine = ""
                    for stat_hash, value in item["stats"]["stats"].items():
                        if stat_hash in ["1935470627", "1480404414", "1885944937"]:
                            continue

                        stat_info = (
                            await self.get_definition("DestinyStatDefinition", [stat_hash])
                        )[0]
                        stat_name = stat_info["displayProperties"]["name"]
                        if not stat_name:
                            continue
                        prog = "█" * int(value["value"] / 10)
                        empty = "░" * int((100 - value["value"]) / 10)
                        bar = f"{prog}{empty}"
                        if stat_hash == "4284893193":
                            rpm = f"{stat_name}: **{value['value']}**\n"
                            continue
                        if stat_hash == "3871231066":
                            recoil = f"{stat_name}: **{value['value']}**\n"
                            continue
                        if stat_hash == "2715839340":
                            magazine = f"{stat_name}: **{value['value']}**\n"
                            continue
                        if details_or_lore:
                            stats_str += f"{stat_name}: **{value['value']}** \n{bar}\n"
                    stats_str += rpm + recoil + magazine
                    description += stats_str
                    embed.description = description
                    perks = await self.get_weapon_possible_perks(item)
                    for key, value in perks.items():
                        embed.add_field(name=key, value=value[:1024])
                if "loreHash" in item and (show_lore or item["itemType"] in [2]):
                    lore = await self.get_definition("DestinyLoreDefinition", [item["loreHash"]])
                    description += _("Lore: \n\n") + lore[0]["displayProperties"]["description"]
                if len(description) > 2048:
                    count = 0
                    for page in pagify(description, page_length=1024):
                        if count == 0:
                            embed.description = page
                        else:
                            embed.add_field(name=_("Lore Continued"), value=page)
                        count += 1
                else:
                    embed.description = description
                embed.title = damage_type + " " + item["itemTypeAndTierDisplayName"]
                name = item["displayProperties"]["name"]
                icon_url = IMAGE_URL + item["displayProperties"]["icon"]
                embed.set_author(name=name, icon_url=icon_url)
                embed.set_thumbnail(url=icon_url)
                if item.get("screenshot", False):
                    embed.set_image(url=IMAGE_URL + item["screenshot"])
                embeds.append(embed)
        self.bot.loop.create_task(menu(ctx, embeds, DEFAULT_CONTROLS))
        # I only have this in a task to allow multple uses of the command
        # after the hard processing is done, once the embeds are created
        # I want to exit the concurrency preventer here

    async def check_gilded_title(self, chars: dict, title: dict) -> bool:
        """
        Checks a players records for a completed gilded title
        """
        gilding_hash = title["titleInfo"].get("gildingTrackingRecordHash", None)
        records = chars["profileRecords"]["data"]["records"]
        if str(gilding_hash) in records:
            for objective in records[str(gilding_hash)]["objectives"]:
                if objective["complete"]:
                    return True
        return False

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def user(self, ctx: commands.Context, user: discord.Member = None) -> None:
        """
        Display a menu of your basic character's info
        `[user]` A member on the server who has setup their account on this bot.
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx, user):
                return
            if not user:
                user = ctx.author
            try:
                chars = await self.get_characters(user)
                # await self.save(chars, "character.json")
            except Destiny2APIError as e:
                log.error(e, exc_info=True)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return
            embeds = []

            for char_id, char in chars["characters"]["data"].items():
                info = ""
                race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
                gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
                char_class = await self.get_definition(
                    "DestinyClassDefinition", [char["classHash"]]
                )
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
                            gilded = ""
                            if await self.check_gilded_title(chars, t):
                                gilded = _("Gilded ")
                            title_name = (
                                f"{gilded}"
                                + t["titleInfo"]["titlesByGenderHash"][str(char["genderHash"])]
                            )
                            title_desc = t["displayProperties"]["description"]
                            titles += title_info.format(
                                title_name=title_name, title_desc=title_desc
                            )
                        except KeyError:
                            pass
                embed = discord.Embed(title=info)
                embed.set_author(name=user.display_name, icon_url=user.avatar_url)
                if "emblemPath" in char:
                    embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
                if titles:
                    # embed.add_field(name=_("Titles"), value=titles)
                    embed.set_author(
                        name=f"{user.display_name} ({title_name})", icon_url=user.avatar_url
                    )
                # log.debug(data)
                stats_str = ""
                time_played = humanize_timedelta(seconds=int(char["minutesPlayedTotal"]) * 60)
                for stat_hash, value in char["stats"].items():
                    stat_info = (await self.get_definition("DestinyStatDefinition", [stat_hash]))[
                        0
                    ]
                    stat_name = stat_info["displayProperties"]["name"]
                    prog = "█" * int(value / 10)
                    empty = "░" * int((100 - value) / 10)
                    bar = f"{prog}{empty}"
                    if stat_hash == "1935470627":
                        bar = ""
                    stats_str += f"{stat_name}: **{value}** \n{bar}\n"
                stats_str += _("Time Played Total: **{time}**").format(time=time_played)
                embed.description = stats_str
                embed = await self.get_char_colour(embed, char)
                if titles:
                    embed.add_field(name=_("Titles"), value=titles)
                embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @search.command()
    @commands.bot_has_permissions(embed_links=True)
    async def lore(self, ctx: commands.Context, entry: str = None) -> None:
        """
        Find Destiny Lore
        """
        try:
            # the below is to prevent blocking reading the large
            # ~130mb manifest files and save on API calls
            task = functools.partial(self.get_entities, entity="DestinyLoreDefinition")
            task = self.bot.loop.run_in_executor(None, task)
            data: dict = await asyncio.wait_for(task, timeout=60)
        except Exception:
            return await ctx.send(_("The manifest needs to be downloaded for this to work."))
        lore = []
        for entry_hash, entries in data.items():
            em = discord.Embed(title=entries["displayProperties"]["name"])
            description = entries["displayProperties"]["description"]
            if len(description) < 2048:
                em.description = entries["displayProperties"]["description"]
            elif len(description) > 2048 and len(description) < 6000:
                em.description = description[:2048]
                new_desc = description[:2048]
                parts = [new_desc[i : i + 1024] for i in range(0, len(new_desc), 1024)]
                for i in parts:
                    em.add_field(name=_("Continued"), value=i)

            if entries["displayProperties"]["hasIcon"]:
                icon = entries["displayProperties"]["icon"]
                em.set_thumbnail(url=f"{IMAGE_URL}{icon}")
            lore.append(em)
        if entry:
            for t in lore:
                if entry.lower() in str(t.title).lower():
                    print(t.title)
                    lore.insert(0, lore.pop(lore.index(t)))
        await menu(ctx, lore, DEFAULT_CONTROLS)

    async def save(self, data: dict, loc: str = "sample.json"):
        if self.bot.user.id not in DEV_BOTS:
            return
        base_path = Path(__file__).parent
        path = base_path / loc
        with path.open(encoding="utf-8", mode="w") as f:
            json.dump(data, f, indent=4, sort_keys=False, separators=(",", " : "))

    @destiny.command(aliases=["xûr"])
    @commands.bot_has_permissions(embed_links=True)
    async def xur(self, ctx: commands.Context, full: bool = False) -> None:
        """
        Display a menu of Xûr's current wares

        `[full=False]` Show perk definition on Xûr's current wares
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx):
                return
            try:
                chars = await self.get_characters(ctx.author)
                # await self.save(chars, "characters.json")
            except Destiny2APIError:
                # log.debug(e)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return
            for char_id, char in chars["characters"]["data"].items():
                # log.debug(char)
                try:
                    xur = await self.get_vendor(ctx.author, char_id, "2190858386")
                    xur_def = await self.get_definition("DestinyVendorDefinition", ["2190858386"])
                except Destiny2APIError:
                    log.error("I can't seem to see Xûr at the moment")
                    today = datetime.datetime.utcnow()
                    friday = today.replace(hour=17, minute=0, second=0) + datetime.timedelta(
                        (4 - today.weekday()) % 7
                    )
                    next_xur = self.humanize_timedelta(timedelta=(friday - today))
                    await ctx.send(
                        _("Xûr's not around, come back in {next_xur}.").format(next_xur=next_xur)
                    )
                    return
                break
            items = [v["itemHash"] for k, v in xur["sales"]["data"].items()]
            embeds = []
            data = await self.get_definition("DestinyInventoryItemDefinition", items)
            embed = discord.Embed(
                colour=discord.Colour.red(),
                description=xur_def[0]["displayProperties"]["description"],
            )
            embed.set_thumbnail(
                url=IMAGE_URL + xur_def[0]["displayProperties"]["largeTransparentIcon"]
            )
            embed.set_author(name="Xûr's current wares")
            location = xur_def[0]["locations"][0]["destinationHash"]
            log.debug(await self.get_definition("DestinyDestinationDefinition", [location]))
            for index, item_base in xur["sales"]["data"].items():
                item = (
                    await self.get_definition(
                        "DestinyInventoryItemDefinition", [item_base["itemHash"]]
                    )
                )[0]
                if not (item["equippable"]):
                    continue
                perk_hashes = [
                    str(p["singleInitialItemHash"]) for p in item["sockets"]["socketEntries"]
                ]
                perk_data = await self.get_definition(
                    "DestinyInventoryItemDefinition", perk_hashes
                )
                perks = ""
                item_embed = discord.Embed(title=item["displayProperties"]["name"])
                item_embed.set_thumbnail(url=IMAGE_URL + item["displayProperties"]["icon"])
                item_embed.set_image(url=IMAGE_URL + item["screenshot"])
                for perk in perk_data:
                    properties = perk["displayProperties"]
                    if "Common" in perk["itemTypeAndTierDisplayName"]:
                        continue
                    if (
                        properties["name"] == "Empty Mod Socket"
                        or properties["name"] == "Default Ornament"
                        or properties["name"] == "Change Energy Type"
                        or properties["name"] == "Empty Catalyst Socket"
                    ):
                        continue
                    if "name" in properties and "description" in properties:
                        if not properties["name"]:
                            continue
                        await self.save(perk, properties["name"] + ".json")
                        if full:
                            perks += "**{0}** - {1}\n".format(
                                properties["name"], properties["description"]
                            )
                        else:
                            perks += "- **{0}**\n".format(properties["name"])
                stats_str = ""
                if "armor" in item["equippingBlock"]["uniqueLabel"]:
                    total = 0
                    for stat_hash, stat_data in xur["itemComponents"]["stats"]["data"][index][
                        "stats"
                    ].items():
                        stat_info = (
                            await self.get_definition("DestinyStatDefinition", [stat_hash])
                        )[0]
                        stat_name = stat_info["displayProperties"]["name"]
                        stat_value = stat_data["value"]
                        prog = "█" * int(stat_value / 6)
                        empty = "░" * int((42 - stat_value) / 6)
                        bar = f"{prog}{empty}"
                        stats_str += f"{stat_name}: \n{bar} **{stat_value}**\n"
                        total += stat_value
                    stats_str += _("Total: **{total}**").format(total=total)

                msg = (
                    item["itemTypeAndTierDisplayName"]
                    + "\n"
                    + (item["displayProperties"]["description"] + "\n" if full else "")
                    + perks
                    + stats_str
                )
                item_embed.description = msg
                embed.insert_field_at(
                    0, name="**__" + item["displayProperties"]["name"] + "__**\n", value=msg
                )
                embeds.insert(0, item_embed)
            embeds.insert(0, embed)
            # await ctx.send(embed=embed)
            # await ctx.tick()
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def eververse(self, ctx: commands.Context) -> None:
        """
        Display items currently available on the Eververse
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx):
                return
            try:
                chars = await self.get_characters(ctx.author)
            except Destiny2APIError:
                # log.debug(e)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return
            embeds: List[discord.Embed] = []
            for char_id, char in chars["characters"]["data"].items():
                log.debug(char_id)
                try:
                    eververse = await self.get_vendor(ctx.author, char_id, "3361454721")
                except Destiny2APIError:
                    log.error("I can't seem to see the eververse at the moment", exc_info=True)
                    await ctx.send(_("I can't access the eververse at the moment."))
                    return
                break
            items = [v["itemHash"] for k, v in eververse["sales"]["data"].items()]
            data = await self.get_definition("DestinyInventoryItemDefinition", items)
            embeds = []
            for item in data:
                if item["itemType"] in [25, 20, 9]:
                    continue
                embed = discord.Embed()
                embed.description = item["displayProperties"]["description"]
                embed.title = item["itemTypeAndTierDisplayName"]
                name = item["displayProperties"]["name"]
                icon_url = IMAGE_URL + item["displayProperties"]["icon"]
                embed.set_author(name=name, icon_url=icon_url)
                embed.set_thumbnail(url=icon_url)
                if "screenshot" in item:
                    embed.set_image(url=IMAGE_URL + item["screenshot"])
                embeds.append(embed)

        # await ctx.tick()
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def spider(self, ctx: commands.Context) -> None:
        """
        Display Spiders wares
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx):
                return
            try:
                chars = await self.get_characters(ctx.author)
            except Destiny2APIError:
                # log.debug(e)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return
            for char_id, char in chars["characters"]["data"].items():
                log.debug(char_id)
                try:
                    spider = await self.get_vendor(ctx.author, char_id, "863940356")
                    spider_def = (
                        await self.get_definition("DestinyVendorDefinition", ["863940356"])
                    )[0]
                except Destiny2APIError:
                    log.error("I can't seem to see the Spider at the moment", exc_info=True)
                    await ctx.send(_("I can't access the Spider at the moment."))
                    return
                break
            await self.save(spider, "spider.json")
            embed = discord.Embed(description=spider_def["displayProperties"]["description"])
            embed.set_thumbnail(
                url=IMAGE_URL + spider_def["displayProperties"]["largeTransparentIcon"]
            )
            embed.set_author(
                name=spider_def["displayProperties"]["name"]
                + ", "
                + spider_def["displayProperties"]["subtitle"]
            )
            for key, data in spider["sales"]["data"].items():
                item_hash = data["itemHash"]

                item = (
                    await self.get_definition("DestinyInventoryItemLiteDefinition", [item_hash])
                )[0]
                if item["itemType"] in [0, 26]:
                    continue
                try:
                    costs = data["costs"][0]
                    cost = (
                        await self.get_definition(
                            "DestinyInventoryItemLiteDefinition", [costs["itemHash"]]
                        )
                    )[0]
                    cost_str = str(costs["quantity"]) + " " + cost["displayProperties"]["name"]
                except IndexError:
                    cost_str = "None"
                embed.add_field(name=item["displayProperties"]["name"], value=cost_str)

                await asyncio.sleep(0)
        await ctx.send(embed=embed)

    @destiny.command(aliases=["banshee-44"])
    @commands.bot_has_permissions(embed_links=True)
    async def banshee(self, ctx: commands.Context) -> None:
        """
        Display Banshee-44's wares
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx):
                return
            try:
                chars = await self.get_characters(ctx.author)
            except Destiny2APIError:
                # log.debug(e)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return

            for char_id, char in chars["characters"]["data"].items():
                log.debug(char_id)
                try:
                    spider = await self.get_vendor(ctx.author, char_id, "672118013")
                    spider_def = (
                        await self.get_definition("DestinyVendorDefinition", ["672118013"])
                    )[0]
                except Destiny2APIError:
                    log.error(
                        "I can't seem to see the Banshee-44's wares at the moment", exc_info=True
                    )
                    await ctx.send(_("I can't access the Banshee-44 at the moment."))
                    return
                break
            await self.save(spider, "spider.json")
            embed = discord.Embed(description=spider_def["displayProperties"]["description"])
            embed.set_thumbnail(
                url=IMAGE_URL + spider_def["displayProperties"]["largeTransparentIcon"]
            )
            embed.set_author(
                name=spider_def["displayProperties"]["name"]
                + ", "
                + spider_def["displayProperties"]["subtitle"]
            )
            for key, data in spider["sales"]["data"].items():
                item_hash = data["itemHash"]

                item = (
                    await self.get_definition("DestinyInventoryItemLiteDefinition", [item_hash])
                )[0]
                if item["itemType"] in [0]:
                    continue
                try:
                    costs = data["costs"][0]
                    cost = (
                        await self.get_definition(
                            "DestinyInventoryItemLiteDefinition", [costs["itemHash"]]
                        )
                    )[0]
                    cost_str = str(costs["quantity"]) + " " + cost["displayProperties"]["name"]
                except IndexError:
                    cost_str = "None"

                embed.add_field(name=item["displayProperties"]["name"], value=cost_str)

                await asyncio.sleep(0)
        await ctx.send(embed=embed)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def loadout(
        self, ctx: commands.Context, full: Optional[bool] = False, user: discord.Member = None
    ) -> None:
        """
        Display a menu of each character's equipped weapons and their info

        `[full=False]` Display full information about weapons equipped.
        `[user]` A member on the server who has setup their account on this bot.
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx, user):
                return
            if not user:
                user = ctx.author
            try:
                chars = await self.get_characters(user)
            except Destiny2APIError:
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
                char_class = await self.get_definition(
                    "DestinyClassDefinition", [char["classHash"]]
                )
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
                            gilded = ""
                            if await self.check_gilded_title(chars, t):
                                gilded = _("Gilded ")
                            title_name = (
                                f"{gilded}"
                                + t["titleInfo"]["titlesByGenderHash"][str(char["genderHash"])]
                            )
                            title_name = t["titleInfo"]["titlesByGenderHash"][
                                str(char["genderHash"])
                            ]
                            title_desc = t["displayProperties"]["description"]
                            titles += title_info.format(
                                title_name=title_name, title_desc=title_desc
                            )
                        except KeyError:
                            pass
                    log.debug("User has a title")
                    pass
                embed = discord.Embed(title=info)
                embed.set_author(name=user.display_name, icon_url=user.avatar_url)
                if "emblemPath" in char:
                    embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
                if titles:
                    # embed.add_field(name=_("Titles"), value=titles)
                    embed.set_author(
                        name=f"{user.display_name} ({title_name})", icon_url=user.avatar_url
                    )
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
                    perk_data = await self.get_definition(
                        "DestinySandboxPerkDefinition", perk_hashes
                    )
                    perks = ""
                    for perk in perk_data:
                        properties = perk["displayProperties"]
                        if "name" in properties and "description" in properties:
                            if full:
                                perks += "**{0}** - {1}\n".format(
                                    properties["name"], properties["description"]
                                )
                            else:
                                perks += "- **{0}**\n".format(properties["name"])

                    value = f"**{light}** {item_type}\n{perks}"
                    embed.add_field(name=name, value=value, inline=True)
                # log.debug(data)
                stats_str = ""
                for stat_hash, value in char["stats"].items():
                    stat_info = (await self.get_definition("DestinyStatDefinition", [stat_hash]))[
                        0
                    ]
                    stat_name = stat_info["displayProperties"]["name"]
                    prog = "█" * int(value / 10)
                    empty = "░" * int((100 - value) / 10)
                    bar = f"{prog}{empty}"
                    if stat_hash == "1935470627":
                        bar = ""
                    stats_str += f"{stat_name}: **{value}** \n{bar}\n"
                embed.description = stats_str
                embed = await self.get_char_colour(embed, char)

                embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def gambit(self, ctx: commands.Context) -> None:
        """
        Display a menu of each characters gambit stats
        """
        await ctx.invoke(self.stats, "allPvECompetitive")

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def pvp(self, ctx: commands.Context) -> None:
        """
        Display a menu of each character's pvp stats
        """
        await ctx.invoke(self.stats, "allPvP")

    @destiny.command(aliases=["raids"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def raid(self, ctx: commands.Context) -> None:
        """
        Display a menu for each character's RAID stats
        """
        await ctx.invoke(self.stats, "raid")

    @destiny.command(aliases=["qp"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def quickplay(self, ctx: commands.Context) -> None:
        """
        Display a menu of past quickplay matches
        """
        await ctx.invoke(self.history, 70)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def history(self, ctx: commands.Context, activity: DestinyActivity) -> None:
        """
        Display a menu of each character's last 5 activities

        `<activity>` The activity type to display stats on available types include:
        all, story, strike, raid, allpvp, patrol, allpve, control, clash,
        crimsondoubles, nightfall, heroicnightfall, allstrikes, ironbanner, allmayhem,
        supremacy, privatematchesall, survival, countdown, trialsofthenine, social,
        trialscountdown, trialssurvival, ironbannercontrol, ironbannerclash,
        ironbannersupremacy, scorednightfall, scoredheroicnightfall, rumble, alldoubles,
        doubles, privatematchesclash, privatematchescontrol, privatematchessupremacy,
        privatematchescountdown, privatematchessurvival, privatematchesmayhem,
        privatematchesrumble, heroicadventure, showdown, lockdown, scorched,
        scorchedteam, gambit, allpvecompetitive, breakthrough, blackarmoryrun,
        salvage, ironbannersalvage, pvpcompetitive, pvpquickplay, clashquickplay,
        clashcompetitive, controlquickplay, controlcompetitive, gambitprime,
        reckoning, menagerie, vexoffensive, nightmarehunt, elimination, momentum,
        dungeon, sundial, trialsofosiris
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx):
                return
            user = ctx.author
            try:
                chars = await self.get_characters(user)
            except Destiny2APIError:
                # log.debug(e)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return
            RAID = {
                "assists": _("Assists"),
                "kills": _("Kills"),
                "deaths": _("Deaths"),
                "opponentsDefeated": _("Opponents Defeated"),
                "efficiency": _("Efficiency"),
                "killsDeathsRatio": _("KDR"),
                "killsDeathsAssists": _("KDA"),
                "score": _("Score"),
                "activityDurationSeconds": _("Duration"),
                "playerCount": _("Player Count"),
                "teamScore": _("Team Score"),
                "completed": _("Completed"),
            }
            embeds = []
            for char_id, char in chars["characters"]["data"].items():
                # log.debug(char)
                char_info = ""
                race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
                gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
                char_class = await self.get_definition(
                    "DestinyClassDefinition", [char["classHash"]]
                )
                char_info += "{user} - {race} {gender} {char_class} ".format(
                    user=user.display_name,
                    race=race[0]["displayProperties"]["name"],
                    gender=gender[0]["displayProperties"]["name"],
                    char_class=char_class[0]["displayProperties"]["name"],
                )
                try:
                    data = await self.get_activity_history(user, char_id, activity)
                except Exception:
                    log.error(
                        _(
                            "Something went wrong I couldn't get info on character {char_id} for activity {activity}"
                        ).format(char_id=char_id, activity=activity)
                    )
                    continue
                if not data:
                    continue

                for activities in data["activities"]:
                    activity_hash = str(activities["activityDetails"]["directorActivityHash"])
                    activity_data = await self.get_definition(
                        "DestinyActivityDefinition", [activity_hash]
                    )
                    activity_data = activity_data[0]
                    embed = discord.Embed(
                        title=activity_data["displayProperties"]["name"],
                        description=activity_data["displayProperties"]["description"],
                    )

                    date = datetime.datetime.strptime(activities["period"], "%Y-%m-%dT%H:%M:%SZ")
                    embed.timestamp = date
                    if activity_data["displayProperties"]["hasIcon"]:
                        embed.set_thumbnail(
                            url=IMAGE_URL + activity_data["displayProperties"]["icon"]
                        )
                    elif (
                        activity_data["pgcrImage"] != "/img/misc/missing_icon_d2.png"
                        and "emblemPath" in char
                    ):
                        embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
                    embed.set_author(name=char_info, icon_url=user.avatar_url)
                    for attr, name in RAID.items():
                        if activities["values"][attr]["basic"]["value"] < 0:
                            continue
                        embed.add_field(
                            name=name,
                            value=str(activities["values"][attr]["basic"]["displayValue"]),
                        )
                    embed = await self.get_char_colour(embed, char)

                    embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @staticmethod
    async def get_extra_attrs(stat_type: str, attrs: dict) -> dict:
        """Helper function to receive the total attributes we care about"""
        EXTRA_ATTRS = {}
        if stat_type == "allPvECompetitive":
            EXTRA_ATTRS = {
                "winLossRatio": _("Win Loss Ratio"),
                "invasions": _("Invasions"),
                "invasionKills": _("Invasion Kills"),
                "invasionDeaths": _("Invasion Deaths"),
                "invaderDeaths": _("Invader Deaths"),
                "invaderKills": _("Invader Kills"),
                "primevalKills": _("Primeval Kills"),
                "blockerKills": _("Blocker Kills"),
                "mobKills": _("Mob Kills"),
                "highValueKills": _("High Value Targets Killed"),
                "motesPickedUp": _("Motes Picked Up"),
                "motesDeposited": _("Motes Deposited"),
                "motesDenied": _("Motes Denied"),
                "motesLost": _("Motes Lost"),
            }
        if stat_type == "allPvP":
            EXTRA_ATTRS = {"winLossRatio": _("Win Loss Ratio")}
        for k, v in EXTRA_ATTRS.items():
            attrs[k] = v
        return attrs

    async def build_character_stats(
        self, user: discord.Member, chars: dict, stat_type: str
    ) -> List[discord.Embed]:

        embeds: List[discord.Embed] = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)

            try:
                data = await self.get_historical_stats(user, char_id, 0)
            except Exception:
                log.error(
                    _("Something went wrong I couldn't get info on character {char_id}").format(
                        char_id=char_id
                    )
                )
                continue
            if not data:
                continue
            try:
                if stat_type != "allPvECompetitive":
                    embed = await self.build_stat_embed_char_basic(user, char, data, stat_type)
                    embeds.append(embed)
                else:
                    data = data[stat_type]["allTime"]
                    embed = await self.build_stat_embed_char_gambit(user, char, data, stat_type)
                    embeds.append(embed)
            except Exception:
                log.error(
                    f"User {user.id} had an issue generating stats for character {char_id}",
                    exc_info=True,
                )
                continue
        return embeds

    async def build_stat_embed_char_basic(
        self, user: discord.Member, char: dict, data: dict, stat_type: str
    ) -> discord.Embed:
        char_info = ""
        race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
        gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
        char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
        char_info += "{user} - {race} {gender} {char_class} ".format(
            user=user.display_name,
            race=race[0]["displayProperties"]["name"],
            gender=gender[0]["displayProperties"]["name"],
            char_class=char_class[0]["displayProperties"]["name"],
        )
        ATTRS = {
            "opponentsDefeated": _("Opponents Defeated"),
            "efficiency": _("Efficiency"),
            "bestSingleGameKills": _("Best Single Game Kills"),
            "bestSingleGameScore": _("Best Single Game Score"),
            "precisionKills": _("Precision Kills"),
            "longestKillSpree": _("Longest Killing Spree"),
            "longestSingleLife": _("Longest Single Life"),
            "totalActivityDurationSeconds": _("Total time playing"),
            "averageLifespan": _("Average Life Span"),
            "weaponBestType": _("Best Weapon Type"),
        }
        embed = discord.Embed(title=stat_type.title())
        embed.set_author(name=char_info, icon_url=user.avatar_url)
        kills = data[stat_type]["allTime"]["kills"]["basic"]["displayValue"]
        deaths = data[stat_type]["allTime"]["deaths"]["basic"]["displayValue"]
        assists = data[stat_type]["allTime"]["assists"]["basic"]["displayValue"]
        kda = f"{kills} | {deaths} | {assists}"
        embed.add_field(name=_("Kills | Deaths | Assists"), value=kda)
        if "emblemPath" in char:
            embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
        for stat, values in data[stat_type]["allTime"].items():

            if values["basic"]["value"] < 0 or stat not in ATTRS:
                continue
            embed.add_field(name=ATTRS[stat], value=str(values["basic"]["displayValue"]))
        if "killsDeathsRatio" in data[stat_type] and "killsDeathsAssists" in data[stat_type]:
            kdr = data[stat_type]["killsDeathsRatio"]
            kda = data[stat_type]["killsDeathsAssists"]
            if kdr or kda:
                embed.add_field(name=_("KDR/KDA"), value=f"{kdr}/{kda}")
        if (
            "resurrectionsPerformed" in data[stat_type]
            and "resurrectionsReceived" in data[stat_type]
        ):
            res = data[stat_type]["resurrectionsPerformed"]
            resur = data[stat_type]["resurrectionsReceived"]
            if res or resur:
                embed.add_field(name=_("Resurrections/Received"), value=f"{res}/{resur}")
        return await self.get_char_colour(embed, char)

    async def build_stat_embed_char_gambit(
        self, user: discord.Member, char: dict, data: dict, stat_type: str
    ) -> discord.Embed:
        char_info = ""
        race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
        gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
        char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
        char_info += "{user} - {race} {gender} {char_class} ".format(
            user=user.display_name,
            race=race[0]["displayProperties"]["name"],
            gender=gender[0]["displayProperties"]["name"],
            char_class=char_class[0]["displayProperties"]["name"],
        )
        ATTRS = {
            "opponentsDefeated": _("Opponents Defeated"),
            "efficiency": _("Efficiency"),
            "bestSingleGameKills": _("Best Single Game Kills"),
            "bestSingleGameScore": _("Best Single Game Score"),
            "precisionKills": _("Precision Kills"),
            "longestKillSpree": _("Longest Killing Spree"),
            "longestSingleLife": _("Longest Single Life"),
            "totalActivityDurationSeconds": _("Total time playing"),
            "averageLifespan": _("Average Life Span"),
            "weaponBestType": _("Best Weapon Type"),
            "winLossRatio": _("Win Loss Ratio"),
        }
        embed = discord.Embed(title="Gambit")
        embed.set_author(name=char_info, icon_url=user.avatar_url)
        kills = data["kills"]["basic"]["displayValue"]
        deaths = data["deaths"]["basic"]["displayValue"]
        assists = data["assists"]["basic"]["displayValue"]
        kda = f"{kills} | {deaths} | {assists}"
        embed.add_field(name=_("Kills | Deaths | Assists"), value=kda)
        small_blocker = data["smallBlockersSent"]["basic"]["displayValue"]
        med_blocker = data["mediumBlockersSent"]["basic"]["displayValue"]
        large_blocker = data["largeBlockersSent"]["basic"]["displayValue"]
        blockers = f"S {small_blocker}, M {med_blocker}, L {large_blocker}"
        embed.add_field(name=_("Blockers"), value=blockers)
        invasions = _("Invasions: {invasions}").format(
            invasions=data["invasions"]["basic"]["displayValue"]
        )
        invasion_kills = _("Kills: {kills}\nDeaths: {deaths}").format(
            kills=data["invasionKills"]["basic"]["displayValue"],
            deaths=data["invasionDeaths"]["basic"]["displayValue"],
        )
        embed.add_field(name=invasions, value=invasion_kills)
        invaders = _("Killed: {killed}\nKilled By: {by}").format(
            killed=data["invaderKills"]["basic"]["displayValue"],
            by=data["invaderDeaths"]["basic"]["displayValue"],
        )
        embed.add_field(name=_("Invaders"), value=invaders)
        motes_dep = data["motesDeposited"]["basic"]["value"]
        try:
            lost = 1 - (motes_dep / data["motesPickedUp"]["basic"]["value"])
            motes_lost = "{:.2%}".format(lost)
        except ZeroDivisionError:
            motes_lost = "0%"
        motes = _("{motes:,} ({lost} Lost)").format(motes=motes_dep, lost=motes_lost)
        embed.add_field(name=_("Motes Deposited"), value=motes)
        motes_denied = data["motesDenied"]["basic"]["value"]
        embed.add_field(name=_("Motes Denied"), value="{:,}".format(motes_denied))
        mob_kills = data["mobKills"]["basic"]["value"]
        primeval_kills = data["primevalKills"]["basic"]["value"]
        high_kills = data["highValueKills"]["basic"]["value"]
        kills_msg = _("Primevals: {prime:,}\nHigh Value Targets: {high:,}\nMobs: {mobs:,}").format(
            prime=primeval_kills, high=high_kills, mobs=mob_kills
        )
        embed.add_field(name=_("Kill Stats"), value=kills_msg)
        if "killsDeathsRatio" in data and "killsDeathsAssists" in data:
            kdr = data["killsDeathsRatio"]["basic"]["displayValue"]
            kda = data["killsDeathsAssists"]["basic"]["displayValue"]
            if kdr or kda:
                embed.add_field(name=_("KDR/KDA"), value=f"{kdr}/{kda}")
        if "resurrectionsPerformed" in data and "resurrectionsReceived" in data:
            res = data["resurrectionsPerformed"]["basic"]["displayValue"]
            resur = data["resurrectionsReceived"]["basic"]["displayValue"]
            if res or resur:
                embed.add_field(name=_("Resurrections/Received"), value=f"{res}/{resur}")
        if "emblemPath" in char:
            embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
        for stat, values in data.items():

            if values["basic"]["value"] < 0 or stat not in ATTRS:
                continue
            embed.add_field(name=ATTRS[stat], value=str(values["basic"]["displayValue"]))

        return await self.get_char_colour(embed, char)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def stats(self, ctx: commands.Context, stat_type: StatsPage, all: bool = True) -> None:
        """
        Display each character's stats for a specific activity
        `<activity>` The type of stats to display, available options are:
        `raid`, `pvp`, `pve`, patrol, story, gambit, and strikes
        """
        async with ctx.typing():
            if not await self.has_oauth(ctx):
                return
            user = ctx.author
            try:
                chars = await self.get_characters(user)
            except Destiny2APIError:
                # log.debug(e)
                msg = _("I can't seem to find your Destiny profile.")
                await ctx.send(msg)
                return
            # base stats should be available for all stat types
            embeds = await self.build_character_stats(user, chars, stat_type)

            if not embeds:
                return await ctx.send(
                    _("No stats could be found for that activity and character.")
                )
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @checks.is_owner()
    @commands.bot_has_permissions(add_reactions=True)
    async def manifest(self, ctx: commands.Context, d1: bool = False) -> None:
        """
        See the current manifest version and optionally re-download it
        """
        if not d1:
            version = await self.config.manifest_version()
            if not version:
                version = "Not Downloaded"
            await ctx.send(_("Current manifest version is {version}").format(version=version))
            await ctx.trigger_typing()
            msg = await ctx.send(_("Would you like to re-download the manifest?"))
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                react, user = await self.bot.wait_for("reaction_add", check=pred, timeout=15)
            except asyncio.TimeoutError:
                await msg.delete()
            if pred.result:
                try:
                    version = await self.get_manifest()
                except Exception:
                    return await ctx.send(_("There was an issue downloading the manifest."))
                await msg.delete()
                await ctx.send(f"Manifest {version} was downloaded.")
            else:
                await msg.delete()
        else:
            try:
                version = await self.get_manifest(d1)
            except Exception:
                log.exception("Error getting D1 manifest")
                return await ctx.send(_("There was an issue downloading the manifest."))

    @destiny.command()
    @checks.is_owner()
    async def token(
        self, ctx: commands.Context, api_key: str, client_id: str, client_secret: str
    ) -> None:
        """
        Set the API tokens for Destiny 2's API

        Required information is found at:
        https://www.bungie.net/en/Application
        select **Create New App**
        Choose **Confidential** OAuth Client type
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
