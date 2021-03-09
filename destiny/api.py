import asyncio
import json
import logging
import functools
from base64 import b64encode
from datetime import datetime
from typing import List, Optional
from pathlib import Path

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n, get_locale
from redbot.core.utils.predicates import MessagePredicate

from .errors import (
    Destiny2APICooldown,
    Destiny2APIError,
    Destiny2InvalidParameters,
    Destiny2MissingAPITokens,
    Destiny2MissingManifest,
    Destiny2RefreshTokenError,
)

DEV_BOTS = [552261846951002112]
# If you want parsing the manifest data to be easier add your
# bots ID to this list otherwise this should help performance
# on bots that are just running the cog like normal

DESTINY1_BASE_URL = "https://www.bungie.net/d1/Platform/Destiny/"
BASE_URL = "https://www.bungie.net/Platform"
IMAGE_URL = "https://www.bungie.net"
AUTH_URL = "https://www.bungie.net/en/oauth/authorize"
TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
BUNGIE_MEMBERSHIP_TYPES = {
    0: "None",
    1: "Xbox",
    2: "Playstation",
    3: "Steam",
    4: "Blizzard",
    5: "Stadia",
    10: "Demon",
    254: "BungieNext",
}


_ = Translator("Destiny", __file__)
log = logging.getLogger("red.trusty-cogs.Destiny")


@cog_i18n(_)
class DestinyAPI:
    config: Config
    bot: Red
    throttle: float

    def __init__(self, *args):
        self.config: Config
        self.bot: Red
        self.throttle: float

    async def request_url(
        self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None
    ) -> dict:
        """
        Helper to make requests from formed headers and params elsewhere
        and apply rate limiting to prevent issues
        """
        time_now = datetime.now().timestamp()
        if self.throttle > time_now:
            raise Destiny2APICooldown(str(self.throttle - time_now))
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                # log.info(resp.url)
                # log.info(headers)
                if resp.status == 200:
                    data = await resp.json()
                    self.throttle = data["ThrottleSeconds"] + time_now
                    if data["ErrorCode"] == 1 and "Response" in data:
                        # fp = cog_data_path(self) / "data.json"
                        # await JsonIO(fp)._threadsafe_save_json(data["Response"])
                        return data["Response"]
                    else:
                        if "message" in data:
                            log.error(data["message"])
                        else:
                            log.error("Incorrect response data")
                        log.debug(url)
                        raise Destiny2InvalidParameters(data)
                else:
                    log.error("Could not connect to the API")
                    raise Destiny2APIError

    async def post_url(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        body: Optional[dict] = None,
    ) -> dict:
        """
        Helper to make requests from formed headers and params elsewhere
        and apply rate limiting to prevent issues
        """
        time_now = datetime.now().timestamp()
        if self.throttle > time_now:
            raise Destiny2APICooldown(str(self.throttle - time_now))
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, headers=headers, json=body) as resp:
                # log.info(resp.url)
                # log.info(headers)
                if resp.status == 200:
                    data = await resp.json()
                    self.throttle = data["ThrottleSeconds"] + time_now
                    if data["ErrorCode"] == 1 and "Response" in data:
                        # fp = cog_data_path(self) / "data.json"
                        # await JsonIO(fp)._threadsafe_save_json(data["Response"])
                        return data["Response"]
                    else:
                        if "message" in data:
                            log.error(data["message"])
                        else:
                            log.error("Incorrect response data")
                        raise Destiny2InvalidParameters(data["Message"])
                else:
                    data = await resp.json()
                    log.error("Could not connect to the API %s" % data)
                    raise Destiny2APIError(data.get("Message", "Unknown error."))

    async def get_access_token(self, code: str) -> dict:
        """
        Called once the OAuth flow is complete and acquires an access token
        """
        client_id = await self.config.api_token.client_id()
        client_secret = await self.config.api_token.client_secret()
        tokens = b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("utf8")
        header = {
            "Authorization": "Basic {0}".format(tokens),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = f"grant_type=authorization_code&code={code}"
        async with aiohttp.ClientSession() as session:
            async with session.post(TOKEN_URL, data=data, headers=header) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "error" in data:
                        raise Destiny2InvalidParameters(data["error_description"])
                    else:
                        return data
                else:
                    raise Destiny2InvalidParameters(_("That token is invalid."))

    async def get_refresh_token(self, user: discord.User) -> dict:
        """
        Generate a refresh token if the token is expired
        """
        client_id = await self.config.api_token.client_id()
        client_secret = await self.config.api_token.client_secret()
        tokens = b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("utf8")
        header = {
            "Authorization": "Basic {0}".format(tokens),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        refresh_token = await self.config.user(user).oauth.refresh_token()
        data = f"grant_type=refresh_token&refresh_token={refresh_token}"
        async with aiohttp.ClientSession() as session:
            async with session.post(TOKEN_URL, data=data, headers=header) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "error" in data:
                        raise Destiny2InvalidParameters(data["error_description"])
                    else:
                        return data
                else:
                    await self.config.user(user).oauth.clear()
                    raise Destiny2RefreshTokenError(_("The refresh token is invalid."))

    async def get_o_auth(self, ctx: commands.Context) -> Optional[dict]:
        """
        This sets up the OAuth flow for logging into the API
        """
        client_id = await self.config.api_token.client_id()
        if not client_id:
            raise Destiny2MissingAPITokens(
                _("The bot owner needs to provide some API tokens first.")
            )
        url = AUTH_URL + f"?client_id={client_id}&response_type=code"
        msg = _(
            "Go to the following url authorize "
            "this application and provide "
            "everything after `?code=` shown in the URL.\n"
        )
        try:
            await ctx.author.send(msg + url)
        except discord.errors.Forbidden:
            await ctx.send(msg + url)
        try:
            msg = await ctx.bot.wait_for(
                "message", check=lambda m: m.author == ctx.message.author, timeout=60
            )
        except asyncio.TimeoutError:
            return None
        if msg.content != "exit":
            return await self.get_access_token(msg.content)
        return None

    async def build_headers(self, user: discord.User = None) -> dict:
        """
        Build the headers for each API call from a discord User
        if present, if a function doesn't require OAuth it won't pass
        the user object
        """
        if not await self.config.api_token.api_key():
            raise Destiny2MissingAPITokens("The Bot owner needs to set an API Key first.")
        header = {
            "X-API-Key": await self.config.api_token.api_key(),
            "Content-Type": "application/x-www-form-urlencoded",
            "cache-control": "no-cache",
        }
        if not user:
            return header
        try:
            await self.check_expired_token(user)
        except Destiny2RefreshTokenError as e:
            log.error(e, exc_info=True)
            raise
        access_token = await self.config.user(user).oauth.access_token()
        token_type = await self.config.user(user).oauth.token_type()
        header["Authorization"] = "{} {}".format(token_type, access_token)
        return header

    async def get_user_profile(self, user: discord.User) -> dict:
        headers = await self.build_headers(user)
        return await self.request_url(
            BASE_URL + "/User/GetMembershipsForCurrentUser/", headers=headers
        )

    async def check_expired_token(self, user: discord.User):
        """
        Sending the expired token results in an HTTP error stating invalid credentials
        We need to keep track of when the token actually expires and check when used
        Good place to check is when building the Authorization headers
        """
        now = datetime.now().timestamp()
        user_oauth = await self.config.user(user).oauth()
        if "refresh_expires_at" not in user_oauth:
            try:
                refresh = await self.get_refresh_token(user)
            except Destiny2InvalidParameters:
                raise Destiny2RefreshTokenError
            refresh["refresh_expires_at"] = now + refresh["refresh_expires_in"]
            await self.config.user(user).oauth.set(refresh)
            return
        if "expires_at" not in user_oauth:
            try:
                refresh = await self.get_refresh_token(user)
            except Destiny2InvalidParameters:
                raise Destiny2RefreshTokenError
            refresh["expires_at"] = now + refresh["expires_in"]
            await self.config.user(user).oauth.set(refresh)
            return
        if user_oauth["refresh_expires_at"] < now:
            await self.config.user(user).clear()
            # We know we have to refresh the oauth after a certain time
            # So we'll clear the scope so the user can supply it again
            raise Destiny2RefreshTokenError
        if user_oauth["expires_at"] < now:
            try:
                refresh = await self.get_refresh_token(user)
            except Destiny2InvalidParameters:
                raise Destiny2RefreshTokenError
            refresh["expires_at"] = now + refresh["expires_in"]
            refresh["refresh_expires_at"] = now + refresh["refresh_expires_in"]
            await self.config.user(user).oauth.set(refresh)
            return

    async def get_characters(self, user: discord.User) -> dict:
        """
        This pulls the data for each character from the API given a user object
        """
        try:
            headers = await self.build_headers(user)
        except Exception as e:
            log.error(e, exc_info=True)
            raise Destiny2RefreshTokenError
        params = {"components": "100,103,104,200,202,204,205,300,302,304,307,800,900,1000,1100"}
        platform = await self.config.user(user).account.membershipType()
        user_id = await self.config.user(user).account.membershipId()
        url = BASE_URL + f"/Destiny2/{platform}/Profile/{user_id}/"
        return await self.request_url(url, params=params, headers=headers)

    def get_entities(self, entity: str, d1: bool = False) -> dict:
        """
        This loads the entity from the saved manifest
        """
        if d1:
            path = cog_data_path(self) / f"d1/{entity}.json"
        else:
            path = cog_data_path(self) / f"{entity}.json"
        with path.open(encoding="utf-8", mode="r") as f:
            data = json.load(f)
        return data

    async def get_definition(self, entity: str, entity_hash: list, d1: bool = False) -> dict:
        """
        This will attempt to get a definition from the manifest
        if the manifest is missing it will try and pull the data
        from the API
        """
        items = {}
        try:
            # the below is to prevent blocking reading the large
            # ~130mb manifest files and save on API calls
            task = functools.partial(self.get_entities, entity=entity, d1=d1)
            task = self.bot.loop.run_in_executor(None, task)
            data = await asyncio.wait_for(task, timeout=60)
        except Exception:
            log.info(_("No manifest found, getting response from API."))
            return await self.get_definition_from_api(entity.replace("Lite", ""), entity_hash)
        for item in entity_hash:
            try:
                items[str(item)] = data[str(item)]
                # items.append(data[str(item)])
            except KeyError:
                pass
        return items
        # return data[entity][entity_hash]

    async def get_definition_from_api(
        self, entity: str, entity_hash: list, d1: bool = False
    ) -> dict:
        """
        This will acquire definition data from the API when the manifest is missing
        """
        try:
            headers = await self.build_headers()
        except Exception:
            raise Destiny2APIError
        items = {}
        for hashes in entity_hash:
            url = f"{BASE_URL}/Destiny2/Manifest/{entity}/{hashes}/"
            data = await self.request_url(url, headers=headers)
            items[str(hashes)] = data
            # items.append(data)
        return items

    async def search_definition(self, entity: str, entity_hash: str, d1: bool = False) -> dict:
        """
        This is a helper to search clean names for a given definition of data
        """
        try:
            # the below is to prevent blocking reading the large
            # ~130mb manifest files and save on API calls
            task = functools.partial(self.get_entities, entity=entity)
            task = self.bot.loop.run_in_executor(None, task)
            data: dict = await asyncio.wait_for(task, timeout=60)
        except Exception:
            err_msg = _("This command requires the Manifest to be downloaded to work.")
            raise Destiny2MissingManifest(err_msg)
        items = {}
        for hash_key, data in data.items():
            if str(entity_hash) == hash_key:
                items[str(hash_key)] = data
                # items.append(data)
            display_properties = data["displayProperties"]
            if str(entity_hash).lower() in display_properties["name"].lower():
                if data.get("itemType", 0) == 20:
                    # We generally don't care about dummy items in the lookup
                    continue
                # items.append(data)
                items[str(data["hash"])] = data
        return items

    async def get_vendor(self, user: discord.User, character: str, vendor: str) -> dict:
        """
        This gets the inventory of a specified Vendor
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        params = {"components": "304,400,401,402"}
        platform = await self.config.user(user).account.membershipType()
        user_id = await self.config.user(user).account.membershipId()
        url = f"{BASE_URL}/Destiny2/{platform}/Profile/{user_id}/Character/{character}/Vendors/{vendor}/"
        return await self.request_url(url, params=params, headers=headers)

    async def get_clan_members(self, user: discord.User, clan_id: str) -> dict:
        """
        Get the list of all clan members
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        url = f"{BASE_URL}/GroupV2/{clan_id}/Members/"
        return await self.request_url(url, headers=headers)

    async def get_bnet_user(self, user: discord.User, membership_id: str) -> dict:
        """
        Get a Destiny users linked profiles
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        url = f"{BASE_URL}/User/GetCredentialTypesForTargetAccount/{membership_id}/"
        return await self.request_url(url, headers=headers)

    async def get_clan_pending(self, user: discord.User, clan_id: str) -> dict:
        """
        Get the list of pending clan members
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        url = f"{BASE_URL}/GroupV2/{clan_id}/Members/Pending"
        return await self.request_url(url, headers=headers)

    async def approve_clan_pending(
        self,
        user: discord.User,
        clan_id: str,
        membership_type: int,
        membership_id: str,
        member_data: dict,
    ) -> dict:
        """
        Approve a clan member into the clan
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        url = f"{BASE_URL}/GroupV2/{clan_id}/Members/Approve/{membership_type}/{membership_id}/"
        return await self.post_url(url, headers=headers, body=member_data)

    async def get_clan_info(self, user: discord.User, clan_id: str) -> dict:
        """
        Get the list of pending clan members
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        url = f"{BASE_URL}/GroupV2/{clan_id}/"
        return await self.request_url(url, headers=headers)

    async def get_activity_history(self, user: discord.User, character: str, mode: str) -> dict:
        """
        This retrieves the activity history for a user's character

        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        params = {"count": 5, "mode": mode}
        platform = await self.config.user(user).account.membershipType()
        user_id = await self.config.user(user).account.membershipId()
        url = f"{BASE_URL}/Destiny2/{platform}/Account/{user_id}/Character/{character}/Stats/Activities/"
        return await self.request_url(url, params=params, headers=headers)

    async def get_historical_stats(
        self,
        user: discord.User,
        character: str,
        mode: str,
        period: int = 2,
        dayend: Optional[str] = None,
        daystart: Optional[str] = None,
    ) -> dict:
        """
        Setup access to historical data
        requires a user object, character hash, and mode type

        can accept period between Daily, AllTime, and Activity
        Can also accept a YYYY-MM-DD formatted string for daystart and dayend
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        params = {"mode": mode, "periodType": period, "groups": "1,2,3,101,102,103"}
        # Set these up incase we want to use them later
        if dayend:
            params["dayend"] = dayend
        if daystart:
            params["daystart"] = daystart
        platform = await self.config.user(user).account.membershipType()
        user_id = await self.config.user(user).account.membershipId()
        url = f"{BASE_URL}/Destiny2/{platform}/Account/{user_id}/Character/{character}/Stats/"
        return await self.request_url(url, params=params, headers=headers)

    async def get_historical_stats_account(self, user: discord.User) -> dict:
        """
        This works the same as get_historical_stats but gets
        stats for all characters merged together

        This does not provide Gambit stats though
        """
        try:
            headers = await self.build_headers(user)
        except Exception:
            raise Destiny2RefreshTokenError
        params = {"groups": "1,2,3,101,102,103"}
        platform = await self.config.user(user).account.membershipType()
        user_id = await self.config.user(user).account.membershipId()
        url = f"{BASE_URL}/Destiny2/{platform}/Account/{user_id}/Stats/"
        return await self.request_url(url, params=params, headers=headers)

    async def has_oauth(self, ctx: commands.Context, user: discord.Member = None) -> bool:
        """
        Basic checks to see if the user has OAuth setup
        if not or the OAuth keys are expired this will call the refresh
        """
        if user:
            if not (
                await self.config.user(user).oauth() or await self.config.user(user).account()
            ):
                # bypass OAuth procedure since the user has not authorized it
                return await ctx.send(
                    _("That user has not provided an OAuth scope to view destiny data.")
                )
            else:
                return True
        if not await self.config.user(ctx.author).oauth():
            now = datetime.now().timestamp()
            try:
                data = await self.get_o_auth(ctx)
                if not data:
                    return False
            except Destiny2InvalidParameters as e:
                try:
                    await ctx.author.send(str(e))
                except discord.errors.Forbidden:
                    await ctx.send(str(e))
                return False
            except Destiny2MissingAPITokens:
                # await ctx.send(str(e))
                return True  # Some magic so we can still keep it all under one top level command
            data["expires_at"] = now + data["expires_in"]
            data["refresh_expires_at"] = now + data["refresh_expires_in"]
            await self.config.user(ctx.author).oauth.set(data)
            try:
                await ctx.author.send(_("Credentials saved."))
            except discord.errors.Forbidden:
                await ctx.send(_("Credentials saved."))
        if not await self.config.user(ctx.author).account():
            data = await self.get_user_profile(ctx.author)
            platform = ""
            if len(data["destinyMemberships"]) > 1:
                datas, platform = await self.pick_account(ctx, data)
                if not datas:
                    return False
                name = datas["displayName"]
                await self.config.user(ctx.author).account.set(datas)
            else:
                name = data["destinyMemberships"][0]["displayName"]
                platform = BUNGIE_MEMBERSHIP_TYPES[data["destinyMemberships"][0]["membershipType"]]
                await self.config.user(ctx.author).account.set(data["destinyMemberships"][0])
            await ctx.send(
                _("Account set to {name} {platform}").format(name=name, platform=platform)
            )
        if await self.config.user(ctx.author).account.membershipType() == 4:
            data = await self.get_user_profile(ctx.author)
            datas, platform = await self.pick_account(ctx, data)
            name = datas["displayName"]
            await self.config.user(ctx.author).account.set(datas)
            await ctx.send(
                _("Account set to {name} {platform}").format(name=name, platform=platform)
            )
        return True

    async def pick_account(self, ctx: commands.Context, profile: dict) -> tuple:
        """
        Have the user pick which account they want to pull data
        from if they have multiple accounts across platforms
        """
        msg = _(
            "There are multiple destiny memberships "
            "available, which one would you like to use?\n"
        )
        count = 1
        for memberships in profile["destinyMemberships"]:
            platform = BUNGIE_MEMBERSHIP_TYPES[memberships["membershipType"]]
            account_name = memberships["displayName"]
            msg += f"**{count}. {account_name} {platform}**\n"
            count += 1
            if memberships.get("crossSaveOverride", 0) == memberships["membershipType"]:
                membership = memberships
                membership_name = _("Crossave")
        if membership:
            return (membership, membership_name)
        try:
            await ctx.author.send(msg)
            pred = MessagePredicate.valid_int(user=ctx.author)
        except discord.errors.Forbidden:
            await ctx.send(msg)
            pred = MessagePredicate.valid_int(ctx)
        try:
            msg = await ctx.bot.wait_for("message", check=pred, timeout=60)
        except asyncio.TimeoutError:
            return None, None

        membership = profile["destinyMemberships"][int(pred.result) - 1]
        membership_name = BUNGIE_MEMBERSHIP_TYPES[profile["destinyMemberships"]["membershipType"]]
        return (membership, membership_name)

    async def save(self, data: dict, loc: str = "sample.json"):
        if self.bot.user.id not in DEV_BOTS:
            return
        base_path = Path(__file__).parent
        path = base_path / loc
        with path.open(encoding="utf-8", mode="w") as f:
            json.dump(data, f, indent=4, sort_keys=False, separators=(",", " : "))

    async def get_manifest(self, d1: bool = False) -> None:
        """
        Checks if the manifest is up to date and downloads if it's not
        """
        try:
            headers = await self.build_headers()
        except Destiny2MissingAPITokens:
            return
        if d1:
            manifest_data = await self.request_url(
                f"{DESTINY1_BASE_URL}/Manifest/", headers=headers
            )
            locale = get_locale()
            if locale in manifest_data:
                manifest = manifest_data["mobileWorldContentPaths"][locale]
            elif locale[:-3] in manifest_data:
                manifest = manifest_data["mobileWorldContentPaths"][locale[:-3]]
            else:
                manifest = manifest_data["mobileWorldContentPaths"]["en"]
        else:
            manifest_data = await self.request_url(
                f"{BASE_URL}/Destiny2/Manifest/", headers=headers
            )
            locale = get_locale()
            if locale in manifest_data:
                manifest = manifest_data["jsonWorldContentPaths"][locale]
            elif locale[:-3] in manifest_data:
                manifest = manifest_data["jsonWorldContentPaths"][locale[:-3]]
            else:
                manifest = manifest_data["jsonWorldContentPaths"]["en"]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://bungie.net/{manifest}", headers=headers, timeout=None
            ) as resp:
                if d1:
                    await self.download_d1_manifest(resp)
                else:
                    response_data = await resp.text()
                    data = json.loads(response_data)
                    for key, value in data.items():
                        path = cog_data_path(self) / f"{key}.json"
                        with path.open(encoding="utf-8", mode="w") as f:
                            if self.bot.user.id in DEV_BOTS:
                                json.dump(
                                    value,
                                    f,
                                    indent=4,
                                    sort_keys=False,
                                    separators=(",", " : "),
                                )
                            else:
                                json.dump(value, f)
                    await self.config.manifest_version.set(manifest_data["version"])
        return manifest_data["version"]

    async def download_d1_manifest(self, resp):
        data = await resp.read()
        directory = cog_data_path(self) / "d1/"
        if not directory.is_dir():
            log.debug("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)
        path = directory / "d1_manifest.zip"
        with path.open(mode="wb") as f:
            f.write(data)
        import zipfile
        import sqlite3
        import ctypes

        db_name = None
        with zipfile.ZipFile(str(path), "r") as zip_ref:
            zip_ref.extractall(str(cog_data_path(self) / "d1/"))
            db_name = zip_ref.namelist()

        conn = sqlite3.connect(directory / db_name[0])
        conn.row_factory = sqlite3.Row
        db = conn.cursor()
        rows = db.execute(
            """
        SELECT * from sqlite_master WHERE type='table'
        """
        ).fetchall()
        # conn.commit()
        # conn.close()
        # log.debug(rows)
        for row in rows:
            json_data = {}
            name = dict(row)["name"]
            data = db.execute(
                """
            SELECT * from {name}
            """.format(
                    name=name
                )
            ).fetchall()
            for _id, datas in data:
                # log.debug(datas)
                try:
                    hash_id = ctypes.c_uint32(_id).value
                except TypeError:
                    hash_id = _id
                json_data[str(hash_id)] = json.loads(datas)
            # log.debug(dict(row))
            path = cog_data_path(self) / f"d1/{name}.json"
            with path.open(encoding="utf-8", mode="w") as f:
                if self.bot.user.id in DEV_BOTS:
                    json.dump(
                        json_data,
                        f,
                        indent=4,
                        sort_keys=False,
                        separators=(",", " : "),
                    )
                else:
                    json.dump(value, f)
        conn.close()

    async def get_char_colour(self, embed: discord.Embed, character):
        r = character["emblemColor"]["red"]
        g = character["emblemColor"]["green"]
        b = character["emblemColor"]["blue"]
        embed.colour = discord.Colour.from_rgb(r, g, b)
        return embed
