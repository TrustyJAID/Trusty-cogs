import discord
import aiohttp
import asyncio
import json
import os
from datetime import datetime
from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.utils.chat_formatting import pagify, box
from random import choice as randchoice

numbs = {
    "next": "➡",
    "back": "⬅",
    "exit": "❌"
}
class Anime(getattr(commands, "Cog", object)):

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.url = "https://anilist.co/api/"
        self.config = Config.get_conf(self, 15863754656)
        default_global = {"last_check":0, "airing":[], "api":{'client_id': '', 'client_secret': '', "access_token":{}}}
        default_guild = {"enabled":False, "channel":None}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        # self.airing = dataIO.load_json("data/anilist/airing.json")
        self.loop = bot.loop.create_task(self.check_airing_start())

    @commands.group()
    async def anime(self, ctx):
        """Various anime related commands"""
        pass

    @anime.command()
    @checks.is_owner()
    async def reset(self, ctx):
        airing = await self.config.airing()
        new_airing = []
        for anime in airing:
            try:
                if anime["episodes"] != []:
                    new_airing.append(anime)
            except KeyError:
                pass
        await self.config.airing.set(new_airing)

    async def check_airing_start(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Anime"):
            await self.check_last_posted()
            # print("hello")
            time_now = datetime.utcnow()
            anime_list = await self.config.airing()
            for anime in anime_list:
                # print(anime["title_english"])
                if "episodes" not in anime:
                    continue
                if anime["adult"]:
                    continue
                for episode, time in anime["episodes"].items():
                    time_start = datetime.utcfromtimestamp(time)
                    # print(time_start.timestamp())
                    if time_start < time_now:
                        await self.post_anime_announcement(anime, episode, time_start)
            # await self.config.last_check.set(time_now.timestamp())
            await self.remove_posted_shows()
            # dataIO.save_json("data/anilist/settings.json", self.settings)
            await asyncio.sleep(60)
            # print("Checking anime")

    @anime.command(pass_context=True)
    async def airing(self, ctx):
        animes=""
        for anime in await self.config.airing():
            animes += "{},".format(anime["title_english"])
        for page in pagify(animes, [","]):
            await ctx.send(page)

    async def remove_posted_shows(self):
        time_now = datetime.utcnow()
        to_delete = {}
        airing_list = await self.config.airing()
        for anime in airing_list:
            if "episodes" not in anime:
                continue
            for episode, time in anime["episodes"].items():
                time_start = datetime.utcfromtimestamp(time)
                if time_start < time_now:
                    print("it gets here")
                    try:
                        to_delete[anime["id"]] = episode
                    except Exception as e:
                        print(e)
        for show_id, episode in to_delete.items():
            try:
                anime = [show for show in await self.config.airing() if show["id"] == show_id][0]
                del airing_list[airing_list.index(anime)]["episodes"][episode]
            except Exception as e:
                print(e)
        await self.config.airing.set(airing_list)

    async def check_last_posted(self):
        time = await self.config.last_check()
        if time is None:
            time = 0
        last_time = datetime.fromtimestamp(time)
        time_now = datetime.utcnow()
        if last_time.day != time_now.day:
            await self.get_currently_airing()
        return

    async def post_anime_announcement(self, anime, episode, time_start):
        title = "{} | {}".format(anime["title_english"], anime["title_japanese"])
        url = "https://anilist.co/anime/{}/".format(anime["id"])
        print(url)
        em = discord.Embed(colour=discord.Colour(value=self.random_colour()))
        desc = "Episode {} of {} starting!".format(episode, anime["title_english"])
        em.description = desc
        em.set_image(url=anime["image_url_lge"])
        em.set_author(name=title, url=url, icon_url=anime["image_url_sml"])
        em.set_footer(text="Start Date ")
        em.timestamp = time_start
        for guild in await self.config.all_guilds():
            guild = self.bot.get_guild(id=guild)
            if not await self.config.guild(guild).enabled() and await self.config.guild(guild).channel() is None:
                continue
            channel_id = await self.config.guild(guild).channel()
            channel = self.bot.get_channel(id=channel_id)
            await channel.send(embed=em)
        return


    async def check_auth(self):
        time_now = datetime.utcnow()
        params = {"client_id": await self.config.api.client_id(), "client_secret": await self.config.api.client_secret()}
        params["grant_type"] = "client_credentials"
        print(params)
        if await self.config.api.access_token() == {} or "error" in await self.config.api.access_token():
            async with self.session.post(self.url + "auth/access_token", params=params) as resp:
                data = await resp.json()
            print(data)
            await self.config.api.access_token.set(data)
        elif time_now > datetime.utcfromtimestamp(await self.config.api.access_token.expires()):
            async with self.session.post(self.url + "auth/access_token", params=params) as resp:
                data = await resp.json()
            print("new token saved")
            await self.config.api.access_token.set(data)
        header = {"access_token": await self.config.api.access_token.access_token()}
        return header

    def random_colour(self):
        return int(''.join([randchoice('0123456789ABCDEF')for x in range(6)]), 16)

    async def search_menu(self, ctx, post_list: list,
                         message: discord.Message=None,
                         page=0, timeout: int=30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        s = post_list[page]
        title = "{} | {}".format(s["title_english"], s["title_japanese"])
        url = "https://anilist.co/anime/{}/".format(s["id"])
        created_at = s["start_date"]
        created_at = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S+09:00") # "2006-07-03T00:00:00+09:00"
        
        em = discord.Embed( colour=discord.Colour(value=self.random_colour()))
        if s["description"] is not None:
            desc = s["description"].replace("<br>", "\n")
            desc = desc.replace("<em>", "*")
            desc = desc.replace("</em>", "*")
            em.description = desc
        em.set_thumbnail(url=s["image_url_lge"])
        em.set_author(name=title, url=url, icon_url=s["image_url_sml"])
        em.set_footer(text="Start Date ")
        em.timestamp = created_at
        if not message:
            message = await ctx.send(embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = lambda react, user:user == ctx.message.author and react.emoji in ["➡", "⬅", "❌"]
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
                try:
                    await message.remove_reaction("➡", ctx.message.author)
                except:
                    pass
                return await self.search_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            elif react == "back":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                try:
                    await message.remove_reaction("⬅", ctx.message.author)
                except:
                    pass
                return await self.search_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            else:
                return await message.delete()



    @anime.command(pass_context=True)
    async def search(self, ctx, *, search):
        header = await self.check_auth()
        async with self.session.get(self.url + "anime/search/{}".format(search), params=header) as resp:
            print(str(resp.url))
            data = await resp.json()
        if "error" not in data:
            await self.search_menu(ctx, data)
        else:
            await ctx.send("{} was not found or credentials were not set!".format(search))

    @commands.command(hidden=True)
    async def forceairing(self, ctx):
        await self.get_currently_airing()
        await ctx.send("Done.")

    async def get_currently_airing(self):
        header1 = await self.check_auth()
        header2 = header1
        header2["status"] = "Currently Airing"
        header2["full_page"] = "true"
        time_now = datetime.utcnow()
        anime_list = []
        async with self.session.get(self.url + "browse/anime", params=header2) as resp:
            # print(str(resp.url))
            data = await resp.json()
        for anime in data:
            if not anime["adult"]:
                # print(anime["title_english"])
                episode_data = {}
                async with self.session.get(self.url + "anime/{}/airing".format(anime["id"]), params=header1) as resp:
                    ani_data = await resp.json()
                try:
                    for ep, time in ani_data.items():
                        if datetime.utcfromtimestamp(time) > time_now:
                            episode_data[ep] = time
                except Exception as e:
                    print(e)
                    pass
            if episode_data != {}:
                data[data.index(anime)]["episodes"] = episode_data
        await self.config.airing.set(data)
        await self.config.last_check.set(datetime.utcnow().timestamp())
        # dataIO.save_json("data/anilist/airing.json", self.airing)

    @anime.command(hidden=True, pass_context=True)
    async def test(self, ctx, *, search=None):
        header1 = await self.check_auth()
        header2 = header1
        header2["status"] = "currently airing"
        header2["full_page"] = True
        time_now = datetime.utcnow()
        anime_list = []
        async with self.session.get(self.url + "browse/anime", params=header2) as resp:
            print(str(resp.url))
            data = await resp.json()
        for anime in data:
            if not anime["adult"]:
                episode_data = {}
                async with self.session.get(self.url + "anime/{}/airing".format(anime["id"]), params=header1) as resp:
                    ani_data = await resp.json()
                    # print(anime["title_english"])
                # anime_list.append(ani_data)
                # print(ani_data)
            # if episode_data != {}:
            data[data.index(anime)]["episodes"] = ani_data
        dataIO.save_json("data/anilist/sample.json", data)

    @commands.group(pass_context=True, name="animeset")
    @checks.admin_or_permissions(manage_channels=True)
    async def animeset(self, ctx):
        """Setup a channel for anime airing announcements"""
        pass

    

    @animeset.command(pass_context=True, name="channel")
    async def add_channel(self, ctx, channel:discord.TextChannel=None):
        """Set the channel for anime announcements"""
        if channel is None:
            channel = ctx.message.channel
        guild = channel.guild

        if channel.id == await self.config.guild(guild).channel():
            await ctx.send("I am already posting anime announcement updates in {}".format(channel.mention))
            return
        else:
            await self.config.guild(guild).channel.set(channel.id)
            await self.config.guild(guild).enabled.set(True)
        await ctx.send("I will post anime episode announcements in {}".format(channel.mention))

    @animeset.command(pass_context=True, name="delete")
    async def del_channel(self, ctx, channel:discord.TextChannel=None):
        """Set the channel for anime announcements"""
        if channel is None:
            channel = ctx.message.channel
        guild = channel.guild
        if channel.id != await self.config.guild(guild).channel():
            await ctx.send("I am not posting anime announcement updates in {}".format(channel.mention))
            return
        else:
            await self.config.guild(guild).channel.set(None)
            await self.config.guild(guild).enabled.set(False)
        await ctx.send("I will stop posting anime episode announcements in {}".format(channel.mention))

    @commands.group(pass_context=True, name='aniset')
    @checks.is_owner()
    async def _aniset(self, ctx):
        """Command for setting required access information for the API.
        To get this info, visit https://anilist.co/home log in, go to your profile
        select Developer and create new Client, set the name and provide your client_id
        and client secret with `[p]aniset creds client_id client_secret`"""
        pass

    @_aniset.command(name='creds')
    @checks.is_owner()
    async def set_creds(self, ctx, client_id:str, client_secret:str):
        """Sets the access credentials. See [p]help aniset for instructions on getting these"""
        # self.settings["api"]["client_id"] = client_id
        # self.settings["api"]["client_secret"] = client_secret
        await self.config.api.client_id.set(client_id)
        await self.config.api.client_secret.set(client_secret)
        # dataIO.save_json("data/anilist/settings.json", self.settings)
        await ctx.send('Set the access credentials!')

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
        self.loop.cancel()
