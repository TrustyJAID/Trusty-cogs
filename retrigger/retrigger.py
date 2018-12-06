import discord
from redbot.core import commands, checks, Config
from redbot.core.data_manager import cog_data_path
from PIL import Image
from io import BytesIO
from copy import copy
from datetime import datetime
import aiohttp
import functools
import asyncio
import random
import string
import re
import os


class Trigger:
    """
        Trigger class to handle trigger objects
    """

    def __init__(self, name, regex, response_type, author, count, 
                 image=None, text=None, whitelist=[], blacklist=[], cooldown={}):
        self.name = name
        self.regex = regex
        self.response_type = response_type
        self.author = author
        self.count = count
        self.image = image
        self.text = text
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.cooldown = cooldown

    def _add_count(self, number:int):
        self.count += number

    def to_json(self) -> dict:
        return {"name":self.name,
                "regex":self.regex,
                "response_type":self.response_type,
                "author": self.author,
                "count": self.count,
                "image":self.image,
                "text":self.text,
                "whitelist":self.whitelist,
                "blacklist":self.blacklist,
                "cooldown":self.cooldown
                }

    @classmethod
    def from_json(cls, data:dict):
        if "cooldown" not in data:
            cooldown = {}
        else:
            cooldown = data["cooldown"]
        return cls(data["name"],
                   data["regex"],
                   data["response_type"],
                   data["author"],
                   data["count"],
                   data["image"],
                   data["text"],
                   data["whitelist"],
                   data["blacklist"],
                   cooldown)


class ReTrigger(getattr(commands, "Cog", object)):
    """
        Trigger bot events using regular expressions
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 964565433247)
        default_guild = {"trigger_list":{}, "allow_multiple":False}
        self.config.register_guild(**default_guild)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    async def local_perms(self, message):
        """Check the user is/isn't locally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True
        elif message.guild is None:
            return True
        guild_settings = self.bot.db.guild(message.guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()

        _ids = [r.id for r in message.author.roles if not r.is_default()]
        _ids.append(message.author.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, message):
        """Check the user is/isn't globally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True

        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return message.author.id in whitelist

        return message.author.id not in await self.bot.db.blacklist()

    async def channel_perms(self, trigger, channel):
        if trigger.whitelist:
            return channel.id in trigger.whitelist
        return channel.id not in trigger.blacklist

    async def check_ignored_channel(self, message):
        """https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/cogs/mod/mod.py#L1273"""
        channel = message.channel
        guild = channel.guild
        author = message.author
        mod = self.bot.get_cog("Mod")
        perms = channel.permissions_for(author)
        surpass_ignore = (
            isinstance(channel, discord.abc.PrivateChannel)
            or perms.manage_guild
            or await self.bot.is_owner(author)
            or await self.bot.is_admin(author)
        )
        if surpass_ignore:
            return True
        guild_ignored = await mod.settings.guild(guild).ignored()
        chann_ignored = await mod.settings.channel(channel).ignored()
        return not (guild_ignored or chann_ignored and not perms.manage_channels)

    async def check_trigger_exists(self, trigger, guild):
        if trigger in await self.config.guild(guild).trigger_list():
            return True
        else:
            return False

    async def make_guild_folder(self, directory):
        if not directory.is_dir():
            print("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def save_image_location(self, image_url, guild):
        seed = ''.join(random.sample(string.ascii_uppercase + string.digits, k=5))
        filename = image_url.split("/")[-1]
        filename = "{}-{}".format(seed, filename)
        directory = cog_data_path(self) /str(guild.id)
        cur_images = await self.config.guild(guild).images()
        file_path = str(cog_data_path(self)) + f"/{guild.id}/{filename}"
        await self.make_guild_folder(directory)
        async with self.session.get(image_url) as resp:
            test = await resp.read()
            with open(file_path, "wb") as f:
                f.write(test)
        return filename

    async def wait_for_image(self, ctx):
        await ctx.send("Upload an image for me to use! Type `exit` to cancel.")
        msg = None
        while msg is None:
            check = lambda m: m.author == ctx.message.author and m.attachments != []
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send("Image adding timed out.")
                break
            if "exit" in msg.content.lower():
                await ctx.send("Image adding cancelled.")
                break
        return msg
            
    def resize_image(self, size, image):
        length, width = (32, 32) # Start with the smallest size we want to upload
        im = Image.open(image)
        im.thumbnail((length*size, width*size), Image.ANTIALIAS)
        byte_array = BytesIO()
        im.save(byte_array, format="PNG")
        return discord.File(byte_array.getvalue(), filename="reeee.png")

    async def trigger_menu(self, ctx:commands.Context, post_list: list,
                         message: discord.Message=None,
                         page=0, timeout: int=30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        post = post_list[page]
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = discord.Embed(timestamp=ctx.message.created_at)
            em.colour = await self.bot.db.color()
            for trigger in post:
                blacklist = ", ".join(x for x in [f"<#{y}>" for y in trigger["blacklist"]])
                whitelist = ", ".join(x for x in [f"<#{y}>" for y in trigger["whitelist"]])
                info = ("__Author__: <@" + str(trigger["author"])+
                        ">\n__Count__: **" + str(trigger["count"]) +"**\n"+
                        "__Regex__: **" + trigger["regex"]+ "**\n"+
                        "__Response__: **" + trigger["response_type"] + "**\n"
                        )
                if blacklist:
                    info += "__Blacklist__: **" + blacklist + "**\n"
                if whitelist:
                    info += "__Whitelist__: **" + whitelist + "**\n"
                if trigger["cooldown"]:
                    time = trigger["cooldown"]["time"]
                    style = trigger["cooldown"]["style"]
                    info += "__Cooldown__: **{}s per {}**".format(time, style)

                em.add_field(name=trigger["name"], value=info[:1024])
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
            em.set_footer(text="Page {}/{}".format(page+1, len(post_list)))
        else:
            await ctx.send("I need embed_links permission to use this command.")
            return
        if len(post_list) == 1:
            # No need to offer multiple pages if they don't exist
            return await ctx.send(embed=em)
        
        if not message:
            message = await ctx.send(embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = lambda react, user:user == ctx.message.author and react.emoji in ["➡", "⬅", "❌"] and react.message.id == message.id
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
                return await self.trigger_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            elif react.emoji == "⬅":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("⬅", ctx.message.author)
                return await self.trigger_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            else:
                return await message.delete()

    async def check_trigger_cooldown(self, message, trigger):
        guild = message.guild
        trigger_list = await self.config.guild(guild).trigger_list()
        now = datetime.now().timestamp()
        if trigger.cooldown == {}:
            return False
        else:
            if trigger.cooldown["style"] in ["guild", "server"]:
                last = trigger.cooldown["last"]
                time = trigger.cooldown["time"]
                if (now - last) > time:
                    trigger.cooldown["last"] = now
                    trigger_list[trigger.name] = trigger.to_json()
                    await self.config.guild(guild).trigger_list.set(trigger_list)
                    return False
                else:
                    return True
            else:
                style = trigger.cooldown["style"]
                snowflake = getattr(message, style)
                if snowflake.id not in [x["id"] for x in trigger.cooldown["last"]]:
                    trigger.cooldown["last"].append({"id":snowflake.id, "last":now})
                    trigger_list[trigger.name] = trigger.to_json()
                    await self.config.guild(guild).trigger_list.set(trigger_list)
                    return False
                else:
                    entity_list = trigger.cooldown["last"]
                    for entity in entity_list:
                        if entity["id"] == snowflake.id:
                            last = entity["last"]
                            time = trigger.cooldown["time"]
                            if (now - last) > time:
                                trigger.cooldown["last"].remove({"id":snowflake.id, "last":last})
                                trigger.cooldown["last"].append({"id":snowflake.id, "last":now})
                                trigger_list[trigger.name] = trigger.to_json()
                                await self.config.guild(guild).trigger_list.set(trigger_list)
                                return False
                            else:
                                return True
    
    async def on_message(self, message):
        if message.guild is None:
            return
        if message.author.bot:
            return
        if not await self.local_perms(message):
            return
        if not await self.global_perms(message):
            return
        if not await self.check_ignored_channel(message):
            return
        msg = message.content
        guild = message.guild
        channel = message.channel
        prefix_list = await self.bot.command_prefix(self.bot, message)
        for prefix in prefix_list:
            if msg.startswith(prefix):
                # Don't run a trigger if it's the name of a command
                return
        trigger_list = await self.config.guild(guild).trigger_list()
        for triggers in trigger_list:
            trigger = Trigger.from_json(trigger_list[triggers])
            if not await self.channel_perms(trigger, channel):
                continue
            search = re.findall(trigger.regex, message.content)
            if search != []:
                if await self.check_trigger_cooldown(message, trigger):
                    return
                trigger._add_count(1)
                trigger_list[triggers] = trigger.to_json()
                await self.perform_trigger(message, trigger, search[0]) 
                await self.config.guild(guild).trigger_list.set(trigger_list)
                if not await self.config.guild(guild).allow_multiple():
                    return

    async def perform_trigger(self, message, trigger, find):
        own_permissions = message.channel.permissions_for(message.guild.me)
        guild = message.guild
        channel = message.channel
        author = message.author
        if trigger.response_type == "resize":
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            task = functools.partial(self.resize_image, size=len(find)-3, image=path)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                file = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
            return await message.channel.send(file=file)
        if trigger.response_type == "text" and own_permissions.send_messages:
            return await channel.send(trigger.text)
        if trigger.response_type == "react" and own_permissions.add_reactions:
            for emoji in trigger.text:
                await message.add_reaction(emoji)
            return
        if trigger.response_type == "ban" and own_permissions.ban_members:
            reason = "Trigger response: {}".format(trigger.name)
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally ban the bot owner 
                # or try to ban the guild owner
                return
            if guild.me.top_role > author.top_role:
                await author.ban(reason=reason, delete_message_days=0)
            return
        if trigger.response_type == "kick" and own_permissions.kick_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally kick the bot owner 
                # or try to kick the guild owner
                return
            reason = "Trigger response: {}".format(trigger.name)
            if guild.me.top_role > author.top_role:
                await author.kick(reason=reason)
            return
        if trigger.response_type == "image" and own_permissions.attach_files:
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            file = discord.File(path)
            return await channel.send(trigger.text, file=file)
        if trigger.response_type == "command":
            msg = copy(message)
            prefix_list = await self.bot.command_prefix(self.bot, message)
            msg.content = prefix_list[0] + trigger.text
            self.bot.dispatch("message", msg)
            return
        if trigger.response_type == "delete":
            await message.delete()
            return
        if trigger.response_type == "add_role":
            role = guild.get_role(trigger.text)
            try:
                await author.add_roles(role, reason="Said the magic words")
            except Exception as e:
                print(e)
            return
        if trigger.response_type == "remove_role":
            role = guild.get_role(trigger.text)
            try:
                await author.remove_roles(role, reason="Said the magic words")
            except Exception as e:
                print(e)
            return


    async def remove_trigger(self, guild, trigger_name):
        trigger_list = await self.config.guild(guild).trigger_list()
        for triggers in trigger_list:
            trigger = Trigger.from_json(trigger_list[triggers])
            if trigger.name == trigger_name:
                if trigger.image is not None:
                    path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(e)
                del trigger_list[triggers]
                await self.config.guild(guild).trigger_list.set(trigger_list)
                return True
        return False

    async def get_trigger(self, guild, name):
        trigger = None
        index = None
        trigger_list = await self.config.guild(guild).trigger_list()
        if name in trigger_list:
            trigger = Trigger.from_json(trigger_list[name])
        return trigger

    @commands.group()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def retrigger(self, ctx):
        """
            Setup automatic triggers based on regular expressions

            https://regexr.com/ is a good place to test regex
        """
        pass

    @retrigger.command()
    async def allowmultiple(self, ctx):
        """
            Toggle multiple triggers to respond at once
        """
        if await self.config.guild(ctx.guild).allow_multiple():
            await self.config.guild(ctx.guild).allow_multiple.set(False)
            await ctx.send("Multiple responses disabled, only the first trigger will happen.")
            return
        else:
            await self.config.guild(ctx.guild).allow_multiple.set(True)
            await ctx.send("Multiple responses enabled, all triggers will occur.")
            return

    @retrigger.group()
    async def blacklist(self, ctx):
        """
            Set blacklist options for retrigger
        """
        pass

    @retrigger.group()
    async def whitelist(self, ctx):
        """
            Set whitelist options for retrigger
        """
        pass

    @retrigger.command()
    async def cooldown(self, ctx, name:str, time:int, style="guild"):
        """
            Set cooldown options for retrigger

            `name` is the name of the trigger
            `time` is a time in seconds until the trigger will run again
            `style` must be either `guild`, `server`, `channel`, `user`, or `member`
        """
        trigger = await self.get_trigger(ctx.guild, name)
        if trigger is None:
            await ctx.send("Trigger `{}` doesn't exist.".format(name))
            return
        if style not in ["guild", "server", "channel", "user", "member"]:
            await ctx.send("Style must be either `guild`, `server`, `channel`, `user`, or `member`.")
            return
        msg = "Cooldown of {}s per {} set for Trigger {}.".format(time, style, name)
        if style in ["user", "member"]:
            style = "author"
        if style in ["guild", "server"]:
            cooldown = {"time":time, "style":style, "last": 0}
        else:
            cooldown = {"time":time, "style":style, "last": []}
        if time <= 0:
            cooldown = {}
            msg = "Cooldown for Trigger {} reset.".format(name)
        trigger_list = await self.config.guild(ctx.guild).trigger_list()
        trigger.cooldown = cooldown
        trigger_list[name] = trigger.to_json()
        await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
        await ctx.send(msg)

    @whitelist.command(name="add")
    async def whitelist_add(self, ctx, name:str, channel:discord.TextChannel=None):
        """
            Add channel to trigger's whitelist

            `name` is the name of the trigger
            `channel` is the channel where the trigger will only work defaults to current channel
        """
        if channel is None:
            channel = ctx.message.channel
        trigger = await self.get_trigger(ctx.guild, name)
        if trigger is None:
            await ctx.send("Trigger `{}` doesn't exist.".format(name))
            return
        if channel.id not in trigger.whitelist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.whitelist.append(channel.id)
            trigger_list[name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            await ctx.send("{} added to Trigger {}'s whitelist.".format(channel.mention, name))
            return
        else:
            await ctx.send("{} is already in Trigger {}'s whitelist.".format(channel.mention, name))
            return
        

    @whitelist.command(name="remove", aliases=["rem", "del"])
    async def whitelist_remove(self, ctx, name:str, channel:discord.TextChannel=None):
        """
            Remove channel from trigger's whitelist

            `name` is the name of the trigger
            `channel` is the channel where the trigger will only work defaults to current channel
        """
        if channel is None:
            channel = ctx.message.channel
        
        trigger = await self.get_trigger(ctx.guild, name)
        if trigger is None:
            await ctx.send("Trigger `{}` doesn't exist.".format(name))
            return
        if channel.id in trigger.whitelist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.whitelist.remove(channel.id)
            trigger_list[name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            await ctx.send("{} removed from Trigger {}'s whitelist.".format(channel.mention, name))
        else:
            await ctx.send("{} is not in Trigger {}'s whitelist.".format(channel.mention, name))
        

    @blacklist.command(name="add")
    async def blacklist_add(self, ctx, name:str, channel:discord.TextChannel=None):
        """
            Add channel to trigger's blacklist

            `name` is the name of the trigger
            `channel` is the channel where the trigger will only work defaults to current channel
        """
        if channel is None:
            channel = ctx.message.channel
        trigger = await self.get_trigger(ctx.guild, name)
        if trigger is None:
            await ctx.send("Trigger `{}` doesn't exist.".format(name))
            return
        if channel.id not in trigger.blacklist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.blacklist.append(channel.id)
            trigger_list[name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            await ctx.send("{} added to Trigger {}'s whitelist.".format(channel.mention, name))
        else:
            await ctx.send("{} is already in Trigger {}'s whitelist.".format(channel.mention, name))


    @blacklist.command(name="remove", aliases=["rem", "del"])
    async def blacklist_remove(self, ctx, name:str, channel:discord.TextChannel=None):
        """
            Remove channel from trigger's blacklist

            `name` is the name of the trigger
            `channel` is the channel where the trigger will only work defaults to current channel
        """
        if channel is None:
            channel = ctx.message.channel
        trigger = await self.get_trigger(ctx.guild, name)
        if trigger is None:
            await ctx.send("Trigger `{}` doesn't exist.".format(name))
            return
        if channel.id in trigger.blacklist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.blacklist.remove(channel.id)
            trigger_list[name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            await ctx.send("{} removed from Trigger {}'s blacklist.".format(channel.mention, name))
        else:
            await ctx.send("{} is not in Trigger {}'s blacklist.".format(channel.mention, name))


    @retrigger.command()
    async def list(self, ctx):
        """
            List all triggers currently on the server
        """
        trigger_dict = await self.config.guild(ctx.guild).trigger_list()
        trigger_list = [trigger_dict[name] for name in trigger_dict]
        if trigger_list == []:
            await ctx.send("There are no triggers setup on this server.")
            return
        post_list = [trigger_list[i:i + 10] for i in range(0, len(trigger_list), 10)]
        await self.trigger_menu(ctx, post_list)

    @retrigger.command(aliases=["del", "rem", "delete"])
    async def remove(self, ctx, name):
        """
            Remove a specified trigger

            `name` is the name of the trigger
        """
        if await self.remove_trigger(ctx.guild, name):
            await ctx.send("Trigger `{}` removed.".format(name))
        else:
            await ctx.send("Trigger `{}` doesn't exist.".format(name))


    @retrigger.command()
    async def text(self, ctx, name:str, regex:str, *, text:str):
        """
            Add a text response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` response of the trigger
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "text", author, 0, None, text)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    async def image(self, ctx, name:str, regex:str, image_url:str=None):
        """
            Add an image/file response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if msg is None:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, regex, "image", author, 0, filename, None)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    async def imagetext(self, ctx, name:str, regex:str, text:str, image_url:str=None):
        """
            Add an image/file response with text trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` the triggered text response
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if msg is None:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, regex, "image", author, 0, filename, text)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    async def resize(self, ctx, name:str, regex:str, image_url:str=None):
        """
            Add an image to resize in response to a trigger
            this will attempt to resize the image based on length of matching regex

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if msg is None:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, regex, "resize", author, 0, filename, None)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(self, ctx, name:str, regex:str):
        """
            Add a trigger to ban users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get banned by accident

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "ban", author, 0, None, None)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    @checks.mod_or_permissions(kick_members=True)
    async def kick(self, ctx, name:str, regex:str):
        """
            Add a trigger to kick users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get kicked by accident

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "kick", author, 0, None, None)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    async def react(self, ctx, name:str, regex:str, *, emojis:str):
        """
            Add a reaction trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `emojis` the emojis to react with when triggered separated by spaces
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        good_emojis = []
        for emoji in emojis.split(" "):
            if "<" in emoji and ">" in emoji:
                emoji = emoji[1:-1]
            try:
                await ctx.message.add_reaction(emoji)
                good_emojis.append(emoji)
            except Exception as e:
                print(e)
        if good_emojis == []:
            await ctx.send("None of the emojis supplied will work!")
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "react", author, 0, None, good_emojis)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    async def command(self, ctx, name:str, regex:str, *, command:str):
        """
            Add a command trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `command` the command that will be triggered, do add [p] prefix
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send("{} doesn't seem to be an available command.".format(command))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "command", author, 0, None, command)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command(aliases=["deletemsg"])
    async def filter(self, ctx, name:str, regex:str):
        """
            Add a trigger to delete a message

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "delete", author, 0, None, None)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(self, ctx, name:str, regex:str, role:discord.Role):
        """
            Add a trigger to add a role

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `role` the role applied when the regex pattern matches
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        if role >= ctx.me.top_role:
            await ctx.send("I can't assign roles higher than my own.")
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "add_role", author, 0, None, role.id)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))

    @retrigger.command()
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(self, ctx, name:str, regex:str, role:discord.Role):
        """
            Add a trigger to remove a role

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `role` the role applied when the regex pattern matches
            See https://regexr.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if await self.check_trigger_exists(name, ctx.guild):
            await ctx.send("{} is already a trigger name")
            return
        try:
            search = re.findall(regex, ctx.message.content)
        except Exception as e:
            await ctx.send("There is something wrong with that regex pattern: {}".format(e))
            return
        if role >= ctx.me.top_role:
            await ctx.send("I can't remove roles higher than my own.")
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, "remove_role", author, 0, None, role.id)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send("Trigger `{}` set.".format(name))


    def __unload(self):
        self.bot.loop.create_task(self.session.close())
