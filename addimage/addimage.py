from random import choice, randint
import random
import aiohttp
import discord
import asyncio
from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
from redbot.core.data_manager import cog_data_path
from pathlib import Path
import os
import string
from redbot.core.i18n import Translator

_ = Translator("Alias", __file__)

class AddImage(getattr(commands, "Cog", object)):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        temp_folder = cog_data_path(self) /"global"
        temp_folder.mkdir(exist_ok=True, parents=True)
        default_global = {"images":[]}
        default_guild = {"images":[]}
        self.config = Config.get_conf(self, 16446735546)
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)

    async def first_word(self, msg):
        return msg.split(" ")[0].lower()

    async def get_prefix(self, message: discord.Message) -> str:
        """
        From Redbot Alias Cog
        Tries to determine what prefix is used in a message object.
            Looks to identify from longest prefix to smallest.
            Will raise ValueError if no prefix is found.
        :param message: Message object
        :return:
        """
        content = message.content
        prefix_list = await self.bot.command_prefix(self.bot, message)
        prefixes = sorted(prefix_list,
                          key=lambda pfx: len(pfx),
                          reverse=True)
        for p in prefixes:
            if content.startswith(p):
                return p
        raise ValueError(_("No prefix found."))

    async def part_of_existing_command(self, alias):
        '''Command or alias'''
        command = self.bot.get_command(alias)
        return command is not None


    async def make_guild_folder(self, directory):
        if not directory.is_dir():
            print("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def get_image(self, alias, guild=None)-> dict:
        if guild is None:
            list_images = await self.config.images()
            for image in await self.config.images():
                if image["command_name"].lower() == alias.lower():
                    return image
        else:
            list_images = await self.config.guild(guild).images()
            for image in await self.config.guild(guild).images():
                # print(image)
                if image["command_name"].lower() == alias.lower():
                    return image

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


    async def on_message(self, message):
        if len(message.content) < 2 or message.guild is None:
            return

        msg = message.content
        guild = message.guild
        channel = message.channel
        try:
            prefix = await self.get_prefix(message)
        except ValueError:
            return
        alias = await self.first_word(msg[len(prefix):])
        if not await self.local_perms(message):
            return
        if not await self.global_perms(message):
            return
        if not await self.check_ignored_channel(message):
            return

        if alias in [x["command_name"] for x in await self.config.images()]:
            if channel.permissions_for(channel.guild.me).attach_files:
                await channel.trigger_typing()
                image = await self.get_image(alias)
                list_images = await self.config.images()
                list_images.remove(image)
                image["count"] += 1
                list_images.append(image)
                await self.config.images.set(list_images)
                file = discord.File(image["file_loc"])
                await channel.send(file=file)

        elif alias in [x["command_name"] for x in await self.config.guild(guild).images()]:
            if channel.permissions_for(channel.guild.me).attach_files:
                await channel.trigger_typing()
                image = await self.get_image(alias, guild)
                guild_images = await self.config.guild(guild).images()
                guild_images.remove(image)
                image["count"] += 1
                guild_images.append(image)
                await self.config.guild(guild).images.set(guild_images)
                file = discord.File(image["file_loc"])
                await channel.send(file=file)

    async def check_command_exists(self, command, guild):
        if command in [x["command_name"] for x in await self.config.guild(guild).images()]:
            return True
        elif await self.part_of_existing_command(command):
            return True
        elif command in [x["command_name"] for x in await self.config.images()]:
            return True
        else:
            return False

    async def image_menu(self, ctx:commands.Context, post_list: list,
                         message: discord.Message=None,
                         page=0, timeout: int=30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        post = post_list[page]
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = discord.Embed(timestamp=ctx.message.created_at)
            for image in post:
                info = "__Author__: <@{}>\n__Count__: **{}**".format(image["author"], image["count"])
                em.add_field(name=image["command_name"], value=info)
            em.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.avatar_url)
            em.set_footer(text="Page {}/{}".format(page+1, len(post_list)))
        else:
            await ctx.send("I need embed_links permission to use this command.")
            return
        if len(post_list) == 1:
            # No need to offer multiple pages if they don't exist
            await ctx.send(embed=em)
            return
        
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
            await message.remove_reaction("⬅", ctx.guild.me)
            await message.remove_reaction("❌", ctx.guild.me)
            await message.remove_reaction("➡", ctx.guild.me)
            return None
        else:
            if react.emoji == "➡":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                try:
                    await message.remove_reaction("➡", ctx.message.author)
                except:
                    pass
                return await self.image_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            elif react.emoji == "⬅":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                try:
                    await message.remove_reaction("⬅", ctx.message.author)
                except:
                    pass
                return await self.image_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            else:
                return await message.delete()

    @commands.group()
    @commands.guild_only()
    async def addimage(self, ctx):
        """
            Add an image for the bot to directly upload
        """
        pass

    @addimage.command(name="list")
    async def listimages(self, ctx, image_loc="guild", server_id:int=None):
        """List images added to bot"""
        msg = ""
        if image_loc in ["global"]:
            image_list = await self.config.images()
        elif image_loc in ["guild", "server"]:
            if server_id is None:
                guild = ctx.message.guild
            else:
                guild = self.bot.get_guild(server_id)
            image_list = await self.config.guild(guild).images()       
        
        if image_list == []:
            await ctx.send("{} does not have any images saved!".format(self.bot.user.display_name))
            return
        post_list = [image_list[i:i + 25] for i in range(0, len(image_list), 25)]
        await self.image_menu(ctx, post_list)
        

    @addimage.command()
    async def clear_list(self, ctx):
        await self.config.images.set([])
        await self.config.guild(ctx.guild).images.set([])

    @addimage.command(name="delete", aliases=["remove", "rem", "del"])
    async def remimage(self, ctx, cmd):
        """Remove a selected images"""
        author = ctx.message.author
        guild = ctx.message.guild
        channel = ctx.message.channel
        cmd = cmd.lower()
        if cmd not in [x["command_name"] for x in await self.config.guild(guild).images()]:
            await ctx.send("{} is not an image for this guild!".format(cmd))
            return

        await channel.trigger_typing()
        all_imgs = await self.config.guild(guild).images()
        image = await self.get_image(cmd, guild)
        all_imgs.remove(image)
        try:
            os.remove(image.file_loc)
        except:
            pass
        await self.config.guild(guild).images.set(all_imgs)
        await ctx.send("{} has been deleted from this guild!".format(cmd))
       

    @checks.is_owner()
    @addimage.command(hidden=True, name="deleteglobal", aliases=["dg", "delglobal"])
    async def rem_image_global(self, ctx, cmd):
        """Remove a selected images"""
        author = ctx.message.author
        guild = ctx.message.guild
        channel = ctx.message.channel
        cmd = cmd.lower()
        if cmd not in [x["command_name"] for x in await self.config.images()]:
            await ctx.send("{} is not a global image!".format(cmd))
            return

        await channel.trigger_typing()
        all_imgs = await self.config.images()
        image = await self.get_image(cmd)
        all_imgs.remove(image)
        try:
            os.remove(image.file_loc)
        except:
            pass
        await self.config.images.set(all_imgs)
        await ctx.send("{} has been deleted globally!".format(cmd))

    async def save_image_location(self, msg, cmd, guild=None):
        seed = ''.join(random.sample(string.ascii_uppercase + string.digits, k=5))
        filename = "{}-{}".format(seed, msg.attachments[0].filename)
        if guild is not None:
            directory = cog_data_path(self) /str(guild.id)
            cur_images = await self.config.guild(guild).images()
        else:
            directory = cog_data_path(self) /"global"
            cur_images = await self.config.images()
        await self.make_guild_folder(directory)
        cmd = cmd.lower()
        
        file_path = "{}/{}".format(str(directory), filename)

        new_entry = {"command_name": cmd,
                    "count": 0,
                    "file_loc": file_path,
                    "author": msg.author.id}

        cur_images.append(new_entry)
        async with self.session.get(msg.attachments[0].url) as resp:
            test = await resp.read()
            with open(file_path, "wb") as f:
                f.write(test)
        if guild is not None:
            await self.config.guild(guild).images.set(cur_images)
        else:
            await self.config.images.set(cur_images)

    async def wait_for_image(self, ctx):
        msg = None
        while msg is None:
            check = lambda m: m.author == ctx.message.author and m.attachments != []
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send("Image adding timed out.")
                break
            if msg.content.lower().strip() == "exit":
                await ctx.send("Image adding cancelled.")
                break
        return msg

    @addimage.command(pass_context=True, name="add")
    async def add_image_guild(self, ctx, cmd):
        """Add an image to direct upload."""
        author = ctx.message.author
        guild = ctx.message.guild
        channel = ctx.message.channel
        if cmd.lower() == "global":
            await ctx.send("global is not a valid command name! Try something else.")
            return
        if await self.check_command_exists(cmd, guild):
            await ctx.send("{} is already in the list, try another!".format(cmd))
            return
        else:
            await ctx.send("{} added as the command!".format(cmd))
        if ctx.message.attachments == []:
            await ctx.send("Upload an image for me to use! Type `exit` to cancel.")
            msg = await self.wait_for_image(ctx)
            if msg is None:
                return
            await self.save_image_location(msg, cmd, guild)
            await ctx.send("{} has been added to my files!".format(cmd))
        else:
            await self.save_image_location(ctx.message, cmd, guild)
        

    @checks.is_owner()
    @addimage.command(hidden=True, pass_context=True, name="addglobal")
    async def add_image_global(self, ctx, cmd):
        """Add an image to direct upload."""
        author = ctx.message.author
        guild = ctx.message.guild
        channel = ctx.message.channel
        msg = ctx.message
        if cmd.lower() == "global":
            await ctx.send("global is not a valid command name! Try something else.")
            return
        if await self.check_command_exists(cmd, guild):
            await ctx.send("{} is already in the list, try another!".format(cmd))
            return
        else:
            await ctx.send("{} added as the command!".format(cmd))
        if ctx.message.attachments == []:
            await ctx.send("Upload an image for me to use! Type `exit` to cancel.")
            msg = await self.wait_for_image(ctx)
            if msg is None:
                return
            await self.save_image_location(msg, cmd)
            await ctx.send("{} has been added to my files!".format(cmd))
        else:
            await self.save_image_location(ctx.message, cmd)

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
