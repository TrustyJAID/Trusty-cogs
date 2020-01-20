import discord
import asyncio
import aiohttp
import time
import logging

from typing import Tuple, Optional, List

from redbot.core.bot import Red
from redbot.core import Config, commands
from .twitch_profile import TwitchProfile
from .twitch_follower import TwitchFollower
from .errors import TwitchError


log = logging.getLogger("red.Trusty-cogs.Twitch")

BASE_URL = "https://api.twitch.tv/helix"


class TwitchAPI:
    """
        Get twitch user information and post when a user gets new followers
    """

    config: Config
    bot: Red
    rate_limit_resets: set
    rate_limit_remaining: int

    def __init__(self, bot):
        self.config: Config
        self.bot: Red
        self.rate_limit_resets: set = set()
        self.rate_limit_remaining: int = 0

    #####################################################################################
    # Logic for accessing twitch API with rate limit checks                             #
    # https://github.com/tsifrer/python-twitch-client/blob/master/twitch/helix/base.py  #
    #####################################################################################

    async def _get_api_tokens(self):
        try:
            keys = await self.bot.get_shared_api_tokens("twitch")
        except AttributeError:
            keys = await self.bot.db.api_tokens.get_raw("twitch", default={})
        return keys

    async def get_header(self) -> dict:
        keys = await self._get_api_tokens()
        header = {"Client-ID": keys["client_id"]}
        access_token = await self.config.access_token()
        if access_token != {}:
            # Return bearer token if availavble for more access
            header["Authorization"] = "Bearer {}".format(access_token["access_token"])
        return header

    async def wait_for_rate_limit_reset(self) -> None:
        """Check rate limits in response header and ensure we're following them
        https://github.com/tsifrer/python-twitch-client/blob/master/twitch/helix/base.py
        """
        if self.rate_limit_remaining == 0:
            current_time = int(time.time())
            self.rate_limit_resets = set(x for x in self.rate_limit_resets if x > current_time)

            if len(self.rate_limit_resets) > 0:
                reset_time = list(self.rate_limit_resets)[0]
                # Calculate wait time and add 0.1s to the wait time to allow Twitch to reset
                # their counter
                wait_time = reset_time - current_time + 0.1
                await asyncio.sleep(wait_time)

    async def oauth_check(self) -> None:
        url = "https://id.twitch.tv/oauth2/token"
        keys = await self._get_api_tokens()
        if "client_secret" not in keys:
            # Can't get the app access token without the client secret being set
            return
        client_id = keys["client_id"]
        client_secret = keys["client_secret"]
        access_token = await self.config.access_token()
        if access_token == {}:
            # Attempts to acquire an app access token
            params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "analytics:read:extensions analytics:read:games bits:read clips:edit user:edit user:edit:broadcast",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as resp:
                    access_token = await resp.json()
            await self.config.access_token.set(access_token)
        else:
            if "access_token" not in access_token:
                # Tries to re-aquire access token if set one is incorrect
                await self.config.access_token.set({})
                return await self.oauth_check()
            header = {"Authorization": "OAuth {}".format(access_token["access_token"])}
            url = "https://id.twitch.tv/oauth2/validate"
            async with aiohttp.ClientSession() as session:
                resp = await session.get(url, headers=header)
            if resp.status == 200:
                # Validates the access token before use
                return
            else:
                await self.config.access_token.set({})
                return await self.oauth_check()

    async def get_response(self, url: str) -> dict:
        """Get responses from twitch after checking rate limits"""
        await self.oauth_check()
        header = await self.get_header()
        await self.wait_for_rate_limit_reset()
        async with aiohttp.ClientSession() as session:
            resp = await session.get(url, headers=header)
        remaining = resp.headers.get("Ratelimit-Remaining")
        if remaining:
            self.rate_limit_remaining = int(remaining)
        reset = resp.headers.get("Ratelimit-Reset")
        if reset:
            self.rate_limit_resets.add(int(reset))

        if resp.status == 429:
            return await self.get_response(url)

        return await resp.json()

    #####################################################################################

    async def make_user_embed(self, profile: TwitchProfile) -> discord.Embed:
        # makes the embed for a twitch profile
        em = discord.Embed(colour=int("6441A4", 16))
        em.description = profile.description
        url = "https://twitch.tv/{}".format(profile.login)
        em.set_author(
            name="{}".format(profile.display_name), url=url, icon_url=profile.profile_image_url
        )
        em.set_image(url=profile.offline_image_url)
        em.set_thumbnail(url=profile.profile_image_url)
        footer_text = "{} Viewer count".format(profile.view_count)
        em.set_footer(text=footer_text, icon_url=profile.profile_image_url)
        return em

    async def make_follow_embed(self, profile: TwitchProfile, total_followers: int):
        # makes the embed for a twitch profile
        em = discord.Embed(colour=int("6441A4", 16))
        url = "https://twitch.tv/{}".format(profile.login)
        em.description = "[{}]({}) has just followed!".format(profile.display_name, url)
        em.set_author(
            name="{} has just followed!".format(profile.display_name),
            url=url,
            icon_url=profile.profile_image_url,
        )
        # em.set_image(url=profile.offline_image_url)
        em.set_thumbnail(url=profile.profile_image_url)
        footer_text = "{} followers".format(total_followers)
        em.set_footer(text=footer_text, icon_url=profile.profile_image_url)
        return em

    async def get_all_followers(self, user_id: str) -> Tuple[list, dict]:
        # Get's all of a users current followers
        url = "{}/users/follows?to_id={}&first=100".format(BASE_URL, user_id)
        data = await self.get_response(url)
        follows = [x["from_id"] for x in data["data"]]
        total = data["total"]
        print("{} of {}".format(len(follows), total))
        count = 0
        while len(follows) < total:
            count += 1
            cursor = data["pagination"]["cursor"]
            data = await self.get_response(url + "&after=" + cursor)
            for user in data["data"]:
                if user["from_id"] not in follows:
                    follows.append(user["from_id"])
            print("{} of {}".format(len(follows), total))
            if count == (int(total / 100) + (total % 100 > 0)):
                # Break the loop if we've gone over the total we could theoretically get
                break
        return follows, total

    async def get_profile_from_name(self, twitch_name: str) -> TwitchProfile:
        url = "{}/users?login={}".format(BASE_URL, twitch_name)
        return TwitchProfile.from_json(await self.get_response(url))

    async def get_profile_from_id(self, twitch_id: str) -> TwitchProfile:
        url = "{}/users?id={}".format(BASE_URL, twitch_id)
        return TwitchProfile.from_json(await self.get_response(url))

    async def get_new_followers(self, user_id: str) -> Tuple[List[TwitchProfile], int]:
        # Gets the last 100 followers from twitch
        url = "{}/users/follows?to_id={}&first=100".format(BASE_URL, user_id)
        data = await self.get_response(url)
        follows = [TwitchFollower.from_json(x) for x in data["data"]]
        total = data["total"]
        return follows, total

    async def maybe_get_twitch_profile(
        self, ctx: commands.Context, twitch_name: str
    ) -> TwitchProfile:
        if twitch_name is not None:
            # Search for twitch login name
            try:
                profile = await self.get_profile_from_name(twitch_name)
            except Exception as e:
                print(e)
                raise TwitchError("{} is not a valid Twitch username".format(twitch_name))
        else:
            # User has set their twitch ID on the bot
            twitch_id = await self.config.user(ctx.author).id()
            if twitch_id == "":
                raise TwitchError("You must set a twitch ID")
            else:
                profile = await self.get_profile_from_id(twitch_id)
        return profile

    async def check_account_added(
        self, account_list: list, profile: TwitchProfile
    ) -> Optional[dict]:
        # Checks if the account is in the config and returns only that one
        account_return = None
        for account in account_list:
            if account["id"] == profile.id:
                account_return = account
        return account_return

    async def check_for_new_followers(self) -> None:
        # Checks twitch every minute for new followers
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Twitch"):
            check_accounts = await self.config.twitch_accounts()
            for account in check_accounts:
                followers, total = await self.get_new_followers(account["id"])
                for follow in reversed(followers):
                    if follow.from_id not in account["followers"]:
                        try:
                            profile = await self.get_profile_from_id(follow.from_id)
                        except Exception:
                            log.error(
                                f"Error getting twitch profile {follow.from_id}", exc_info=True
                            )
                        log.info(
                            "{} Followed! You have {} followers now.".format(profile.login, total)
                        )
                        em = await self.make_follow_embed(profile, total)
                        for channel_id in account["channels"]:
                            channel = self.bot.get_channel(id=channel_id)
                            if channel and channel.permissions_for(channel.guild.me).embed_links:
                                await channel.send(embed=em)
                        check_accounts.remove(account)
                        account["followers"].append(follow.from_id)
                        check_accounts.append(account)
                        await self.config.twitch_accounts.set(check_accounts)

            await asyncio.sleep(60)
