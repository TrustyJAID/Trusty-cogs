import asyncio
from datetime import datetime

import aiohttp
import discord
from redbot.core import Config, checks, commands

from .gabuser import GabUser

__version__ = "2.0.1"
__author__ = "TrustyJAID"

BASE_URL = "https://api.gab.com/v1.0/"


class GabaiError(Exception):
    pass


class NotFoundError(GabaiError):
    pass


class Gabai(commands.Cog):
    """
    Get information from gab.ai and display on discord
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 17864784635)
        default_global = {
            "api_token": {"client_id": "", "client_secret": "", "token": {}, "refresh_time": 0}
        }
        self.config.register_global(**default_global)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.rate_limit_remaining = 60
        self.rate_limit_time = 0

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    @commands.group()
    async def gab(self, ctx):
        """
        Add your gab tag to receive the role Anonymous
        """
        pass

    async def refresh_token(self):
        api_token = await self.config.api_toke()
        params = {
            "grant_type": "refresh_token",
            "refresh_token": api_token["token"]["refresh_token"],
            "client_id": api_token["client_id"],
            "client_secret": api_token["client_secret"],
            "scope": "read engage-user engage-post write-post notifications",
        }
        async with self.session.post("https://api.gab.com/oauth/token", json=params) as resp:
            token = await resp.json()
        await self.config.api_token.token.set(token)
        await self.config.api_token.refresh_time.set(
            token["expires_in"] + datetime.now().timestamp()
        )

    async def get_header(self):
        access_token = await self.config.api_token.token.access_token()
        return {"Authorization": "Bearer {}".format(access_token)}

    async def check_rate_limit(self):
        """Current rate limit is 60 calls per minute"""
        time_now = int(datetime.now().timestamp())
        if self.rate_limit_remaining == 60:
            self.rate_limit_time = int(datetime.now().timestamp())
            self.rate_limit_remaining -= 1
            return
        if self.rate_limit_remaining != 0:
            self.rate_limit_remaining -= 1
            return
        else:
            if time_now > (self.rate_limit_time + 60):
                self.rate_limit_remaining = 59
                self.rate_limit_time = time_now
            else:
                await asyncio.sleep(self.rate_limit_time + 60 - time_now)

    async def get_gab_response(self, url, params=None):
        await self.check_rate_limit()
        header = await self.get_header()
        async with self.session.get(BASE_URL + url, params=params, headers=header) as resp:
            response = await resp.json()
            if "status" in response:
                raise NotFoundError(response["message"])
            else:
                return response

    async def make_user_embed(self, user: GabUser):

        url = "https://gab.ai/{}".format(user.username)
        em = discord.Embed(description=user.bio[:1990], title=user.name, colour=int("4bd079", 16))
        em.set_author(name=user.username, url=url, icon_url=user.picture_url_full)
        em.set_thumbnail(url=user.picture_url_full)
        em.add_field(name="Followers", value=user.follower_count)
        em.add_field(name="Following", value=user.following_count)
        em.add_field(name="Score", value=user.score)
        acknowledgements = ""
        if user.is_pro:
            acknowledgements += "Pro, "
        if user.verified:
            acknowledgements += "Verified, "
        if user.is_donor:
            acknowledgements += "Donor, "
        if user.is_investor:
            acknowledgements += "Investor, "
        if acknowledgements != "":
            em.add_field(name="Acknowledgements", value=acknowledgements[:-2])
        # em.set_image(url=user.cover_url)
        return em

    async def make_post_embed(self, post: dict):
        username = post["actuser"]["username"]
        post_id = post["post"]["id"]
        url = "https://gab.ai/{}/posts/{}".format(username, post_id)
        timestamp = datetime.strptime(post["post"]["created_at"], "%Y-%m-%dT%H:%M:%S+00:00")
        attachment = post["post"]["attachment"]["type"]
        colour = int("4bd079", 16)
        likes = post["post"]["like_count"]
        replies = post["post"]["reply_count"]
        em = discord.Embed(description=post["post"]["body"], timestamp=timestamp, colour=colour)
        if attachment is not None:
            if attachment != "media":
                em.set_image(url=post["post"]["attachment"]["value"])
            else:
                em.set_image(url=post["post"]["attachment"]["value"][0]["url_full"])
        em.set_author(
            name=post["actuser"]["username"], url=url, icon_url=post["actuser"]["picture_url"]
        )
        em.set_footer(text="{} Likes | {} Replies | Created at".format(likes, replies))
        return em

    async def gab_menu(
        self,
        ctx: commands.Context,
        post_list: list,
        message: discord.Message = None,
        page=0,
        timeout: int = 30,
    ):
        """menu control logic for this taken from
        https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        post = post_list[page]
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = await self.make_post_embed(post)
        else:
            await ctx.send("I need embed_links permission to use this command.")
            return

        if not message:
            message = await ctx.send(embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = (
            lambda react, user: user == ctx.message.author
            and react.emoji in ["➡", "⬅", "❌"]
            and react.message.id == message.id
        )
        try:
            react, user = await ctx.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.remove_reaction("⬅", ctx.me)
            await message.remove_reaction("❌", ctx.me)
            await message.remove_reaction("➡", ctx.me)
            return None
        else:
            if react.emoji == "➡":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("➡", ctx.message.author)
                return await self.gab_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            elif react.emoji == "⬅":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("⬅", ctx.message.author)
                return await self.gab_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            else:
                return await message.delete()

    @gab.command()
    async def feed(self, ctx, username: str, before_date: str = None):
        """
        Gets a users feed from gab.ai before a specified date

        before_date must be in format DD-MM-YYYY
        """
        await ctx.trigger_typing()
        if before_date is None:
            before_date = datetime.now().strftime("%Y-%m-%dT%H:%M%S%z")
        else:
            before_date = datetime.strptime(before_date, "%d-%m-%Y").strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            )
        try:
            feed_info = await self.get_gab_response(
                f"users/{username}/feed/", {"before": before_date}
            )
        except NotFoundError as e:
            await ctx.send("{} {}".format(username, e))
            return
        await self.gab_menu(ctx, feed_info["data"])

    @gab.command()
    async def user(self, ctx, username: str):
        """
        Get user information from gab.ai
        """
        await ctx.trigger_typing()
        try:
            user_info = await self.get_gab_response(f"users/{username}")
        except NotFoundError as e:
            await ctx.send("{} {}".format(username, e))
            return
        user = GabUser.from_json(user_info)
        em = await self.make_user_embed(user)
        await ctx.send(embed=em)

    @gab.command()
    @checks.is_owner()
    async def token(self, ctx, client_id: str, client_secret: str):
        """
        Provide your client_id and client_secret

        1. go to https://gab.ai/settings/clients then Developer Apps
        2. Select Create app
        3. Fillout the form and set the redirect url to https://localhost
        4. Provide the client_id and client_secret
        5. The bot will provide a link and ask for the code
        6. post everything after `?code=` in discord
        """
        await self.config.api_token.client_id.set(client_id)
        await self.config.api_token.client_secret.set(client_secret)
        url = f"https://api.gab.com/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri=https://localhost&scope=%20read%20engage-user%20engage-post%20write-post%20notifications"
        await ctx.send(
            "Please go to the following url and provide the code supplied: {}".format(url)
        )
        check = lambda m: m.author.id == ctx.message.author.id
        code = await self.bot.wait_for("message", check=check)
        params = {
            "grant_type": "authorization_code",
            "code": code.content,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "https://localhost",
        }
        async with self.session.post("https://api.gab.com/oauth/token", json=params) as resp:
            token = await resp.json()
        if "error" in token:
            await ctx.send(token["message"] + "\n\nMaybe try again/")
            return
        await self.config.api_token.token.set(token)
        await self.config.api_token.refresh_time.set(
            token["expires_in"] + datetime.now().timestamp()
        )
        await ctx.send("API Tokens set!")

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
