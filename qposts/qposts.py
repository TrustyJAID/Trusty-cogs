import discord
import aiohttp
import asyncio
import json
import os
from datetime import datetime
from redbot.core import commands
from redbot.core import Config
from redbot.core import checks
from redbot.core.data_manager import cog_data_path
from pathlib import Path
from bs4 import BeautifulSoup
try:
    import tweepy as tw
    twInstalled = True
except:
    twInstalled = False

numbs = {
    "next": "➡",
    "back": "⬅",
    "exit": "❌"
}
class QPosts(getattr(commands, "Cog", object)):
    """Gather Qanon updates from 8chan"""

    def __init__(self, bot):
        self.bot = bot
        default_data = {"twitter":{"access_secret" : "",
        "access_token" : "",
        "consumer_key" : "",
        "consumer_secret" : ""}, "boards":{}, "channels":[], "last_checked":0, "print":True}
        self.config = Config.get_conf(self, 112444567876)
        self.config.register_global(**default_data)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.url = "https://8ch.net"
        self.boards = ["greatawakening", "qresearch", "patriotsfight"]
        self.trips = ["!UW.yye1fxo", "!ITPb.qbhqo", "!xowAT4Z3VQ", "!4pRcUA0lBE", "!CbboFOtcZs", "!A6yxsPKia.", "!2jsTvXXmX", "!!mG7VJxZNCI"]
        self.loop = bot.loop.create_task(self.get_q_posts())


    async def authenticate(self):
        """Authenticate with Twitter's API"""
        try:
            auth = tw.OAuthHandler(await self.config.twitter.consumer_key(), await self.config.twitter.consumer_secret())
            auth.set_access_token(await self.config.twitter.access_token(), await self.config.twitter.access_secret())
            return tw.API(auth)
        except:
            return

    async def send_tweet(self, message: str, file=None):
        """Sends tweets as the bot owners account"""
        if not twInstalled:
            return
        try:
            api = await self.authenticate()
            if file is None:
                api.update_status(message)
            else:
                api.update_with_media(file, status=message)
        except:
            return

    @commands.command()
    async def reset_qpost(self, ctx):
        await self.config.last_checked.set(0)
        await ctx.send("Done.")

    @commands.command()
    async def dlq(self, ctx):
        board_posts = await self.config.boards()
        for board in self.boards:
            async with self.session.get("{}/{}/catalog.json".format(self.url, board)) as resp:
                data = await resp.json()
            Q_posts = []
            
            for page in data:
                for thread in page["threads"]:
                    if await self.config.print():
                        print(thread["no"])
                    async with self.session.get("{}/{}/res/{}.json".format(self.url, board,thread["no"])) as resp:
                        posts = await resp.json()
                    for post in posts["posts"]:
                        if "trip" in post:
                            if post["trip"] in self.trips:
                                Q_posts.append(post)
            board_posts[board] = Q_posts
        await self.config.boards.set(board_posts)

    @commands.command(pass_context=True, name="qrole")
    async def qrole(self, ctx):
        """Set your role to a team role"""
        guild = ctx.message.guild
        try:
            role = [role for role in guild.roles if role.name == "QPOSTS"][0]
            await ctx.message.author.add_roles(role)
            await ctx.send("Role applied.")
        except:
            return

    async def get_q_posts(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("QPosts"):
            board_posts = await self.config.boards()
            for board in self.boards:
                try:
                    async with self.session.get("{}/{}/catalog.json".format(self.url, board)) as resp:
                        data = await resp.json()
                except Exception as e:
                    print(f"error grabbing board catalog {board}: {e}")
                    continue
                Q_posts = []
                if board not in board_posts:
                    board_posts[board] = []
                for page in data:
                    for thread in page["threads"]:
                        # print(thread["no"])
                        thread_time = datetime.utcfromtimestamp(thread["last_modified"])
                        last_checked_time = datetime.fromtimestamp(await self.config.last_checked())
                        if thread_time >= last_checked_time:
                            try:
                                async with self.session.get("{}/{}/res/{}.json".format(self.url, board,thread["no"])) as resp:
                                    posts = await resp.json()
                            except:
                                print("error grabbing thread {} in board {}".format(thread["no"], board))
                                continue
                            for post in posts["posts"]:
                                if "trip" in post:
                                    if post["trip"] in self.trips:
                                        Q_posts.append(post)
                old_posts = [post_no["no"] for post_no in board_posts[board]]

                for post in Q_posts:
                    if post["no"] not in old_posts:
                        board_posts[board].append(post)
                        # dataIO.save_json("data/qposts/qposts.json", self.qposts)
                        await self.postq(post, "/{}/".format(board))
                    for old_post in board_posts[board]:
                        if old_post["no"] == post["no"] and old_post["com"] != post["com"]:
                            if "edit" not in board_posts:
                                board_posts["edit"] = {}
                            if board not in board_posts["edit"]:
                                board_posts["edit"][board] = []
                            board_posts["edit"][board].append(old_post)
                            board_posts[board].remove(old_post)
                            board_posts[board].append(post)
                            await self.postq(post, "/{}/ {}".format(board, "EDIT"))
            await self.config.boards.set(board_posts)
            if await self.config.print():
                print("checking Q...")
            cur_time = datetime.utcnow()
            await self.config.last_checked.set(cur_time.timestamp())
            await asyncio.sleep(60)

    async def get_quoted_post(self, qpost):
        html = qpost["com"]
        soup = BeautifulSoup(html, "html.parser")
        reference_post = []
        for a in soup.find_all("a", href=True):
            # print(a)
            try:
                url, post_id = a["href"].split("#")[0].replace("html", "json"), int(a["href"].split("#")[1])
            except:
                continue
            async with self.session.get(self.url + url) as resp:
                data = await resp.json()
            for post in data["posts"]:
                if post["no"] == post_id:
                    reference_post.append(post)
        return reference_post
            
    # @commands.command(pass_context=True)
    async def postq(self, qpost, board):
        name = qpost["name"] if "name" in qpost else "Anonymous"
        url = "{}/{}/res/{}.html#{}".format(self.url, board, qpost["resto"], qpost["no"])
        
        html = qpost["com"]
        soup = BeautifulSoup(html, "html.parser")
        ref_text = ""
        text = ""
        img_url = ""
        reference = await self.get_quoted_post(qpost)
        if qpost["com"] != "<p class=\"body-line empty \"></p>":
            for p in soup.find_all("p"):
                if p.get_text() is None:
                    text += "."
                else:
                    text += p.get_text() + "\n"
        if reference != []:
            for post in reference:
                # print(post)
                ref_html = post["com"]
                soup_ref = BeautifulSoup(ref_html, "html.parser")
                for p in soup_ref.find_all("p"):
                    if p.get_text() is None:
                        ref_text += "."
                    else:
                        ref_text += p.get_text() + "\n"
            if "tim" in reference[0] and "tim" not in qpost:
                file_id = reference[0]["tim"]
                file_ext = reference[0]["ext"]
                img_url = "https://media.8ch.net/file_store/{}{}".format(file_id, file_ext)
                await self.save_q_files(reference[0])
        if "tim" in qpost:
            file_id = qpost["tim"]
            file_ext = qpost["ext"]
            img_url = "https://media.8ch.net/file_store/{}{}".format(file_id, file_ext)
            await self.save_q_files(qpost)

        # print("here")
        em = discord.Embed(colour=discord.Colour.red())
        em.set_author(name=name + qpost["trip"], url=url)
        em.timestamp = datetime.utcfromtimestamp(qpost["time"])
        if text != "":
            if text.count("_") > 2 or text.count("~") > 2 or text.count("*") > 2:
                em.description = "```\n{}```".format(text[:1990])
            else:
                em.description = text[:1900]
        else:
            em.description = qpost["com"]

        if ref_text != "":
            if ref_text.count("_") > 2 or ref_text.count("~") > 2 or ref_text.count("*") > 2:
                em.add_field(name=str(post["no"]), value="```{}```".format(ref_text[:1000]))
            else:
                em.add_field(name=str(post["no"]), value=ref_text[:1000])
        if img_url != "":
            em.set_image(url=img_url)
            try:
                if await self.config.print():
                    print("sending tweet with image")
                tw_msg = "{}\n#QAnon\n{}".format(url, text)
                await self.send_tweet(tw_msg[:280], "data/qposts/files/{}{}".format(file_id, file_ext))
            except Exception as e:
                print(f"Error sending tweet with image: {e}")
                pass
        else:
            try:
                if await self.config.print():
                    print("sending tweet")
                tw_msg = "{}\n#QAnon\n{}".format(url, text)
                await self.send_tweet(tw_msg[:280])
            except Exception as e:
                print(f"Error sending tweet: {e}")
                pass
        em.set_footer(text=board)
        
        
        for channel_id in await self.config.channels():
            try:
                channel = self.bot.get_channel(id=channel_id)
            except Exception as e:
                print(f"Error getting the qchannel: {e}")
                continue
            if channel is None:
                continue
            guild = channel.guild
            if not channel.permissions_for(guild.me).send_messages:
                    continue
            if not channel.permissions_for(guild.me).embed_links:
                await channel.send(text[:1900])
            try:
                role = "".join(role.mention for role in guild.roles if role.name == "QPOSTS")
                if role != "":
                    await channel.send("{} <{}>".format(role, url), embed=em)
                else:
                    await channel.send("<{}>".format(url), embed=em)
            except Exception as e:
                print(f"Error posting Qpost in {channel_id}: {e}")
                


    async def q_menu(self, ctx, post_list: list, board,
                         message: discord.Message=None,
                         page=0, timeout: int=30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""

        qpost = post_list[page]
        em = discord.Embed(colour=discord.Colour.red())
        name = qpost["name"] if "name" in qpost else "Anonymous"
        url = "{}/{}/res/{}.html#{}".format(self.url, board, qpost["resto"], qpost["no"])
        em.set_author(name=name + qpost["trip"], url=url)
        em.timestamp = datetime.utcfromtimestamp(qpost["time"])
        html = qpost["com"]
        soup = BeautifulSoup(html, "html.parser")
        text = ""
        for p in soup.find_all("p"):
            if p.get_text() is None:
                text += "."
            else:
                text += p.get_text() + "\n"
        em.description = "```{}```".format(text[:1800])
        reference = await self.get_quoted_post(qpost)
        if reference != []:
            for post in reference:
                # print(post)
                ref_html = post["com"]
                soup_ref = BeautifulSoup(ref_html, "html.parser")
                ref_text = ""
                for p in soup_ref.find_all("p"):
                    if p.get_text() is None:
                        ref_text += "."
                    else:
                        ref_text += p.get_text() + "\n"
                em.add_field(name=str(post["no"]), value="```{}```".format(ref_text[:1000]))
            if "tim" in post and "tim" not in qpost:
                file_id = post["tim"]
                file_ext = post["ext"]
                img_url = "https://media.8ch.net/file_store/{}{}".format(file_id, file_ext)
                if file_ext in [".png", ".jpg", ".jpeg"]:
                    em.set_image(url=img_url)
        em.set_footer(text="/{}/".format(board))
        if "tim" in qpost:
            file_id = qpost["tim"]
            file_ext = qpost["ext"]
            img_url = "https://media.8ch.net/file_store/{}{}".format(file_id, file_ext)
            if file_ext in [".png", ".jpg", ".jpeg"]:
                em.set_image(url=img_url)
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
                return await self.q_menu(ctx, post_list, board, message=message,
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
                return await self.q_menu(ctx, post_list, board, message=message,
                                             page=next_page, timeout=timeout)
            else:
                return await message.delete()

    @commands.command(pass_context=True, aliases=["postq"])
    async def qpost(self, ctx, board="patriotsfight"):
        """Display latest qpost from specified board"""
        if board not in await self.config.boards():
            await ctx.send("{} is not an available board!")
            return
        qposts = await self.config.boards()
        qposts = list(reversed(qposts[board]))
        await self.q_menu(ctx, qposts, board)

    @commands.command()
    async def qprint(self, ctx):
        """Toggle printing to the console"""
        if await self.config.print():
            await self.config.print.set(False)
            await ctx.send("Printing off.")
        else:
            await self.config.print.set(True)
            await ctx.send("Printing on.")

    async def save_q_files(self, post):
        try:
            file_id = post["tim"]
            file_ext = post["ext"]
        
            file_path =  cog_data_path(self) /"files"
            file_path.mkdir(exist_ok=True, parents=True)
            url = "https://media.8ch.net/file_store/{}{}".format(file_id, file_ext)
            async with self.session.get(url) as resp:
                image = await resp.read()
            with open(str(file_path) + "/{}{}".format(file_id, file_ext), "wb") as out:
                out.write(image)
            if "extra_files" in post:
                for file in post["extra_files"]:
                    file_id = file["tim"]
                    file_ext = file["ext"]
                    url = "https://media.8ch.net/file_store/{}{}".format(file_id, file_ext)
                    async with self.session.get(url) as resp:
                        image = await resp.read()
                    with open(str(file_path) + "/{}{}".format(file_id, file_ext), "wb") as out:
                        out.write(image)
        except Exception as e:
            print(f"Error saving files: {e}")
            pass

    @commands.command(pass_context=True)
    async def qchannel(self, ctx, channel:discord.TextChannel=None):
        """Set the channel for live qposts"""
        if channel is None:
            channel = ctx.message.channel
        guild = ctx.message.guild
        cur_chans = await self.config.channels()
        if channel.id in cur_chans:
            await ctx.send("{} is already posting new Q posts!".format(channel.mention))
            return
        else:
            cur_chans.append(channel.id)
        await self.config.channels.set(cur_chans)
        await ctx.send("{} set for qposts!".format(channel.mention))

    @commands.command(pass_context=True)
    async def remqchannel(self, ctx, channel:discord.TextChannel=None):
        """Remove qpost updates from a channel"""
        if channel is None:
            channel = ctx.message.channel
        guild = ctx.message.guild
        cur_chans = await self.config.channels()
        if channel.id not in cur_chans:
            await ctx.send("{} is not posting new Q posts!".format(channel.mention))
            return
        else:
            cur_chans.remove(channel.id)
        await self.config.channels.set(cur_chans)
        await ctx.send("{} set for qposts!".format(channel.mention))

    @commands.command(name='qtwitterset')
    @checks.is_owner()
    async def set_creds(self, ctx, consumer_key: str, consumer_secret: str, access_token: str, access_secret: str):
        """Set automatic twitter updates alongside discord"""
        api = {'consumer_key': consumer_key, 'consumer_secret': consumer_secret,
            'access_token': access_token, 'access_secret': access_secret}
        await self.config.twitter.set(api)
        await ctx.send('Set the access credentials!')

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
        self.loop.cancel()

    __del__ = __unload
