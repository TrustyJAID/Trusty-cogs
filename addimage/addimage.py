import random
import aiohttp
import discord
import asyncio
from redbot.core import commands, checks, Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
import os
import string
from redbot.core.i18n import Translator, cog_i18n


_ = Translator("AddImage", __file__)
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class AddImage(commands.Cog):
    """
        Add images the bot can upload
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        temp_folder = cog_data_path(self) / "global"
        temp_folder.mkdir(exist_ok=True, parents=True)
        default_global = {"images": []}
        default_guild = {"images": []}
        self.config = Config.get_conf(self, 16446735546)
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)

    async def initialize(self):
        guilds = await self.config.all_guilds()
        for guild_id, data in guilds.items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            for image in data["images"]:
                image["file_loc"] = image["file_loc"].split("/")[-1]
            await self.config.guild(guild).set(data)

        async with self.config.images() as images:
            for image in images:
                image["file_loc"] = image["file_loc"].split("/")[-1]

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
        prefixes = sorted(prefix_list, key=lambda pfx: len(pfx), reverse=True)
        for p in prefixes:
            if content.startswith(p):
                return p
        raise ValueError(_("No prefix found."))

    async def part_of_existing_command(self, alias):
        """Command or alias"""
        command = self.bot.get_command(alias)
        return command is not None

    async def make_guild_folder(self, directory):
        if not directory.is_dir():
            print("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def get_image(self, alias, guild=None) -> dict:
        if guild is None:
            for image in await self.config.images():
                if image["command_name"].lower() == alias.lower():
                    return image
        else:
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
        """
        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/cogs/mod/mod.py#L1273
        """
        channel = message.channel
        guild = channel.guild
        author = message.author
        mod = self.bot.get_cog("Mod")
        if mod is None:
            return True
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

    @listener()
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
        if message.author.bot:
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
                async with self.config.images() as list_images:
                    list_images.remove(image)
                    image["count"] += 1
                    list_images.append(image)
                path = str(cog_data_path(self)) + "/global/" + image["file_loc"]
                file = discord.File(path)
                try:
                    await channel.send(files=[file])
                except discord.errors.Forbidden:
                    pass

        elif alias in [x["command_name"] for x in await self.config.guild(guild).images()]:
            if channel.permissions_for(channel.guild.me).attach_files:
                await channel.trigger_typing()
                image = await self.get_image(alias, guild)
                async with self.config.guild(guild).images() as guild_images:
                    guild_images.remove(image)
                    image["count"] += 1
                    guild_images.append(image)
                path = str(cog_data_path(self)) + f"/{guild.id}/" + image["file_loc"]
                file = discord.File(path)
                try:
                    await channel.send(files=[file])
                except discord.errors.Forbidden:
                    pass

    async def check_command_exists(self, command, guild):
        if command in [x["command_name"] for x in await self.config.guild(guild).images()]:
            return True
        elif await self.part_of_existing_command(command):
            return True
        elif command in [x["command_name"] for x in await self.config.images()]:
            return True
        else:
            return False

    @commands.group()
    @commands.guild_only()
    async def addimage(self, ctx):
        """
            Add an image for the bot to directly upload
        """
        pass

    @addimage.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def listimages(self, ctx, image_loc="guild", server_id: discord.Guild = None):
        """
            List images added to bot
        """
        if image_loc in ["global"]:
            image_list = await self.config.images()
        elif image_loc in ["guild", "server"]:
            if server_id is None:
                guild = ctx.message.guild
            else:
                guild = self.bot.get_guild(server_id)
            image_list = await self.config.guild(guild).images()

        if image_list == []:
            await ctx.send(_("I does not have any images saved!"))
            return
        post_list = [image_list[i: i + 25] for i in range(0, len(image_list), 25)]
        images = []
        for post in post_list:
            em = discord.Embed(timestamp=ctx.message.created_at)
            for image in post:
                info = (
                    _("__Author__: ")
                    + "<@{}>\n".format(image["author"])
                    + _("__Count__: ")
                    + "**{}**".format(image["count"])
                )
                em.add_field(name=image["command_name"], value=info)
            em.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.avatar_url)
            em.set_footer(
                text=_("Page ") + "{}/{}".format(post_list.index(post) + 1, len(post_list))
            )
            images.append(em)
        await menu(ctx, images, DEFAULT_CONTROLS)

    @addimage.command()
    @checks.is_owner()
    async def clear_global(self, ctx):
        """
            Clears the full set of images stored globally
        """
        await self.config.images.set([])
        directory = cog_data_path(self) / "global"
        for file in os.listdir(str(directory)):
            try:
                os.remove(str(directory / file))
            except Exception as e:
                print(e)

    @addimage.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def clear_images(self, ctx):
        """
            Clear all the images stored for the current server
        """
        await self.config.guild(ctx.guild).images.set([])
        directory = cog_data_path(self) / str(ctx.guild.id)
        for file in os.listdir(str(directory)):
            try:
                os.remove(str(directory / file))
            except Exception as e:
                print(e)

    @addimage.command(name="delete", aliases=["remove", "rem", "del"])
    @checks.mod_or_permissions(manage_channels=True)
    async def remimage(self, ctx, name: str):
        """
            Remove a selected images

            `name` the command name used to post the image
        """
        guild = ctx.message.guild
        channel = ctx.message.channel
        name = name.lower()
        if name not in [x["command_name"] for x in await self.config.guild(guild).images()]:
            await ctx.send(name + _(" is not an image for this guild!"))
            return

        await channel.trigger_typing()
        all_imgs = await self.config.guild(guild).images()
        image = await self.get_image(name, guild)
        all_imgs.remove(image)
        try:
            os.remove(image.file_loc)
        except Exception:
            pass
        await self.config.guild(guild).images.set(all_imgs)
        await ctx.send(name + _(" has been deleted from this guild!"))

    @checks.is_owner()
    @addimage.command(hidden=True, name="deleteglobal", aliases=["dg", "delglobal"])
    async def rem_image_global(self, ctx, name: str):
        """
            Remove a selected images

            `name` the command name used to post the image
        """
        channel = ctx.message.channel
        name = name.lower()
        if name not in [x["command_name"] for x in await self.config.images()]:
            await ctx.send(name + _(" is not a global image!"))
            return

        await channel.trigger_typing()
        all_imgs = await self.config.images()
        image = await self.get_image(name)
        all_imgs.remove(image)
        try:
            os.remove(image.file_loc)
        except Exception:
            pass
        await self.config.images.set(all_imgs)
        await ctx.send(name + _(" has been deleted globally!"))

    async def save_image_location(self, msg, name, guild=None):
        seed = "".join(random.sample(string.ascii_uppercase + string.digits, k=5))
        filename = "{}-{}".format(seed, msg.attachments[0].filename)
        if guild is not None:
            directory = cog_data_path(self) / str(guild.id)
            cur_images = await self.config.guild(guild).images()
        else:
            directory = cog_data_path(self) / "global"
            cur_images = await self.config.images()
        await self.make_guild_folder(directory)
        name = name.lower()

        file_path = "{}/{}".format(str(directory), filename)

        new_entry = {
            "command_name": name,
            "count": 0,
            "file_loc": filename,
            "author": msg.author.id,
        }

        cur_images.append(new_entry)
        await msg.attachments[0].save(file_path)
        if guild is not None:
            await self.config.guild(guild).images.set(cur_images)
        else:
            await self.config.images.set(cur_images)

    async def wait_for_image(self, ctx):
        msg = None
        while msg is None:
            def check(m: discord.Member):
                return m.author == ctx.author and (m.attachments or "exit" in m.content)
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send(_("Image adding timed out."))
                break
            if msg.content.lower().strip() == "exit":
                await ctx.send(_("Image adding cancelled."))
                break
        return msg

    @addimage.command(name="add")
    @checks.mod_or_permissions(manage_channels=True)
    @commands.bot_has_permissions(attach_files=True)
    async def add_image_guild(self, ctx, name: str):
        """
            Add an image to direct upload on this server

            `name` the command name used to post the image
        """
        guild = ctx.message.guild
        if name.lower() == "global":
            msg = _("global is not a valid command name! Try something else.")
            return await ctx.send(msg)
        if await self.check_command_exists(name, guild):
            msg = name + _(" is already in the list, try another!")
            return await ctx.send(msg)
        else:
            msg = name + _(" added as the command!")
            await ctx.send(msg)
        if ctx.message.attachments == []:
            msg = _("Upload an image for me to use! Type `exit` to cancel.")
            await ctx.send(msg)
            file_msg = await self.wait_for_image(ctx)
            if not file_msg or not file_msg.attachments:
                return
            await self.save_image_location(file_msg, name, guild)
            await ctx.send(name + _(" has been added to my files!"))
        else:
            await self.save_image_location(ctx.message, name, guild)

    @checks.is_owner()
    @addimage.command(hidden=True, name="addglobal")
    async def add_image_global(self, ctx, name: str):
        """
            Add an image to direct upload globally

            `name` the command name used to post the image
        """
        guild = ctx.message.guild
        msg = ctx.message
        if name.lower() == "global":
            msg = _("global is not a valid command name! Try something else.")
            return await ctx.send(msg)
        if await self.check_command_exists(name, guild):
            msg = name + _(" is already in the list, try another!")
            return await ctx.send(msg)
        else:
            msg = name + _(" added as the command!")
            await ctx.send(msg)
        if ctx.message.attachments == []:
            msg = _("Upload an image for me to use! Type `exit` to cancel.")
            await ctx.send(msg)
            file_msg = await self.wait_for_image(ctx)
            if not file_msg or not file_msg.attachments:
                return
            await self.save_image_location(file_msg, name)
            await ctx.send(name + _(" has been added to my files!"))
        else:
            await self.save_image_location(ctx.message, name)

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    __unload = cog_unload