import asyncio
from random import choice as randchoice

import aiohttp
import discord
from redbot.core import Config, checks, commands

numbs = {"next": "➡", "back": "⬅", "exit": "❌"}


class Halo(commands.Cog):
    """
    Display Halo 5 and Halo Wars 2 stats and information
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        default_global = {"api_token": {"token": "", "language": "en"}}
        self.config = Config.get_conf(self, 35689771456)
        self.config.register_global(**default_global)

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def request_url(self, url, params=None):
        header_data = await self.config.api_token()
        header = {
            "Ocp-Apim-Subscription-Key": header_data["token"],
            "Accept-Language": header_data["language"],
        }
        async with self.session.get(url, params=params, headers=header) as resp:
            return await resp.json()

    @commands.group(name="halo5")
    @checks.admin_or_permissions(manage_guild=True)
    async def _halo5(self, ctx):
        """Get information from Halo 5"""
        pass

    @commands.group(name="halowars")
    @checks.admin_or_permissions(manage_guild=True)
    async def _halowars(self, ctx):
        """Get information from Halo Wars 2"""
        pass

    def random_colour(self):
        return int("".join([randchoice("0123456789ABCDEF") for x in range(6)]), 16)

    async def halo5_playlist_menu(
        self, ctx, post_list: list, message: discord.Message = None, page=0, timeout: int = 30
    ):
        """menu control logic for this taken from
        https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        s = post_list[page]
        created_at = ctx.message.created_at
        desc = "Created at: {}".format(created_at)
        em = discord.Embed(
            title=s["name"],
            description=s["description"],
            colour=discord.Colour(value=self.random_colour()),
            timestamp=created_at,
        )
        em.add_field(name="Gamemode", value=s["gameMode"])
        em.add_field(name="Ranked", value=str(s["isRanked"]))
        if s["imageUrl"] is not None:
            em.set_image(url=s["imageUrl"])
        if not message:
            message = await ctx.send(embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = lambda react, user: user == ctx.message.author and react.emoji in ["➡", "⬅", "❌"]
        try:
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.remove_reaction("⬅", self.bot.user)
            await message.remove_reaction("❌", self.bot.user)
            await message.remove_reaction("➡", self.bot.user)
            return None
        else:
            reacts = {v: k for k, v in numbs.items()}
            react = reacts[react.emoji]
            if react == "next":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                return await self.halo5_playlist_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            elif react == "back":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                return await self.halo5_playlist_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            else:
                return await message.delete()

    @_halo5.command(name="playlist")
    async def halo5_playlist(self, ctx, active=True):
        """Gathers data about active Halo 5 playlists"""
        data = await self.request_url("https://www.haloapi.com/metadata/h5/metadata/playlists")
        list_active = []
        for playlist in data:
            if playlist["isActive"]:
                list_active.append(playlist)
        await self.halo5_playlist_menu(ctx, list_active)

    async def halowars_playlist_menu(
        self, ctx, post_list: list, message: discord.Message = None, page=0, timeout: int = 30
    ):
        """menu control logic for this taken from
        https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        s = post_list[page]
        created_at = ctx.message.created_at
        desc = "Created at: {}".format(created_at)
        em = discord.Embed(
            title=s["View"]["Title"],
            # description=s["description"],
            colour=discord.Colour(value=self.random_colour()),
            timestamp=created_at,
        )
        # em.add_field(name="Gamemode", value=s["gameMode"])
        # em.add_field(name="Ranked", value=str(s["isRanked"]))
        # if s["HW2Playlist"][] is not None:
        em.set_image(url=s["View"]["HW2Playlist"]["Image"]["View"]["Media"]["MediaUrl"])
        if not message:
            message = await ctx.send(embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = lambda react, user: user == ctx.message.author and react.emoji in ["➡", "⬅", "❌"]
        try:
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.remove_reaction("⬅", self.bot.user)
            await message.remove_reaction("❌", self.bot.user)
            await message.remove_reaction("➡", self.bot.user)
            return None
        else:
            reacts = {v: k for k, v in numbs.items()}
            react = reacts[react.emoji]
            if react == "next":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                return await self.halowars_playlist_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            elif react == "back":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                return await self.halowars_playlist_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            else:
                return await message.delete()

    async def get_halo5_rank_data(self, designation_id, tier_id):
        rank_data = await self.request_url(
            "https://www.haloapi.com/metadata/h5/metadata/csr-designations"
        )
        designation = [x for x in rank_data if x["id"] == str(designation_id)]
        image_url = [x["iconImageUrl"] for x in designation[0]["tiers"] if x["id"] == str(tier_id)]
        return designation[0]["name"], image_url

    @_halo5.command(name="rank")
    async def Halo5_rank(self, ctx, *, gamertag):
        """Gather playter rank information from Halo 5"""
        colours = {
            "Unranked": "7f7f7f",
            "Bronze": "c27c0e",
            "Silver": "cccccc",
            "Gold": "xf1c40f",
            "Platinum": "e5e5e5",
            "Diamond": "ffffff",
            "Onyx": "000000",
            "Champion": "71368a",
        }
        player_data = await self.request_url(
            "https://www.haloapi.com/stats/h5/servicerecords/arena?", {"players": gamertag}
        )
        tier = player_data["Results"][0]["Result"]["ArenaStats"]["HighestCsrAttained"]["Tier"]
        designation = player_data["Results"][0]["Result"]["ArenaStats"]["HighestCsrAttained"][
            "DesignationId"
        ]
        designation_name, image_url = await self.get_halo5_rank_data(designation, tier)
        embed = discord.Embed(
            title=gamertag,
            description=designation_name,
            colour=discord.Colour(value=int(colours[designation_name], 16)),
            timestamp=ctx.message.created_at,
        )
        embed.add_field(name="Designation", value=str(designation), inline=True)
        embed.add_field(name="Tier", value=str(tier), inline=True)
        embed.set_thumbnail(url=image_url[0])
        await ctx.send(embed=embed)

    @_halowars.command(name="playlist")
    async def halowars_playlist(self, ctx, active=True):
        """Gathers data about active Halo 5 playlists"""
        data = await self.request_url("https://www.haloapi.com/metadata/hw2/playlists")
        list_active = []
        for playlist in data["ContentItems"]:
            # print(playlist)
            if not playlist["View"]["HW2Playlist"]["Hide"]:
                list_active.append(playlist)
        await self.halowars_playlist_menu(ctx, list_active)

    @commands.group(name="haloset")
    @checks.is_owner()
    async def _haloset(self, ctx):
        """Command for setting required access information for the API.
        To get this info, visit https://developer.haloapi.com and create a new application."""
        pass

    @_haloset.command()
    async def tokens(self, ctx, subscription_key, language="en"):
        """Set the tokens and language for requests from the API"""
        await self.config.api_token.token.set(subscription_key)
        await self.config.api_token.language.set(language)
        await ctx.send("Halo API credentials set!")

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    __unload = cog_unload
