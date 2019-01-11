import discord
from redbot.core import commands, checks, Config, modlog
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list
from discord.ext.commands.converter import Converter, IDConverter
from discord.ext.commands.errors import BadArgument
from PIL import Image
from io import BytesIO
from copy import copy
from datetime import datetime
from typing import Union
import aiohttp
import functools
import asyncio
import random
import string
import re
import os
import logging

log = logging.getLogger("red.ReTrigger")
_ = Translator("ReTrigger", __file__)


class Trigger:
    """
        Trigger class to handle trigger objects
    """

    def __init__(self, 
                 name:str, 
                 regex:str, 
                 response_type:str, 
                 author:int, 
                 count:int, 
                 image:str, 
                 text:str, 
                 whitelist:list, 
                 blacklist:list, 
                 cooldown:dict):
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

class TriggerExists(Converter):

    async def convert(self, ctx, argument):
        bot = ctx.bot
        guild = ctx.guild
        config = bot.get_cog("ReTrigger").config
        trigger_list = await config.guild(guild).trigger_list()
        result = None
        if argument in trigger_list:
            result = Trigger.from_json(trigger_list[argument])
        else:
            result = argument
        return result


class ValidRegex(Converter):
    """
    This will check to see if the provided regex pattern is valid

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """
    async def convert(self, ctx, argument):
        bot = ctx.bot
        try:
            re.compile(argument)
            result = argument
        except Exception as e:
            log.error("Retrigger conversion error", exc_info=True)
            err_msg = "`{arg}` is not a valid regex pattern. {e}".format(arg=argument, e=e)
            raise BadArgument(err_msg)
        return result

class ChannelUserRole(IDConverter):
    """
    This will check to see if the provided argument is a channel, user, or role

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """

    async def convert(self, ctx, argument):
        bot = ctx.bot
        guild = ctx.guild
        result = None
        id_match = self._get_id_match(argument)
        channel_match = re.match(r'<#([0-9]+)>$', argument)
        member_match = re.match(r'<@!?([0-9]+)>$', argument)
        role_match = re.match(r'<@&([0-9]+)>$', argument)
        for converter in ["channel", "role", "member"]:
            if converter == "channel":
                match = id_match or channel_match
                if match:
                    channel_id = match.group(1)
                    result = guild.get_channel(int(channel_id))
                else:
                    result = discord.utils.get(guild.text_channels, name=argument)
            if converter == "member":
                match = id_match or member_match
                if match:
                    member_id = match.group(1)
                    result = guild.get_member(int(member_id))
                else:
                    result = guild.get_member_named(argument)
            if converter == "role":
                match = id_match or role_match
                if match:
                    role_id = match.group(1)
                    result = guild.get_role(int(role_id))
                else:
                    result = discord.utils.get(guild._roles.values(), name=argument)
            if result:
                break
        if not result:
            msg = _("{arg} is not a valid channel, user or role.").format(arg=argument)
            raise BadArgument(msg)
        return result



@cog_i18n(_)
class ReTrigger(getattr(commands, "Cog", object)):
    """
        Trigger bot events using regular expressions
    """

    __author__ = "TrustyJAID"
    __version__ = "1.9.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 964565433247)
        default_guild = {"trigger_list":{}, 
                         "allow_multiple":False,
                         "modlog":"default"}
        self.config.register_guild(**default_guild)

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

    async def check_bw_list(self, trigger, message):
        can_run = True
        if await self.is_mod_or_admin(message.author):
            return True
        if trigger.whitelist:
            can_run = False
            if message.channel.id in trigger.whitelist:
                can_run = True
            if message.author.id in trigger.whitelist:
                can_run = True
            for role in message.author.roles:
                if role.id in trigger.whitelist:
                    can_run = True
            return can_run
        else:
            if message.channel.id in trigger.blacklist:
                can_run = False
            if message.author.id in trigger.blacklist:
                can_run = False
            for role in message.author.roles:
                if role.id in trigger.blacklist:
                    can_run = False
        return can_run

    async def is_mod_or_admin(self, member:discord.Member):
        guild = member.guild
        if member == guild.owner:
            return True
        if await self.bot.is_owner(member):
            return True
        if await self.bot.is_admin(member):
            return True
        if await self.bot.is_mod(member):
            return True
        return False

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


    async def make_guild_folder(self, directory):
        if not directory.is_dir():
            log.warn("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def save_image_location(self, image_url, guild):
        seed = ''.join(random.sample(string.ascii_uppercase + string.digits, k=5))
        filename = image_url.split("/")[-1]
        filename = "{}-{}".format(seed, filename)
        directory = cog_data_path(self) /str(guild.id)
        cur_images = await self.config.guild(guild).images()
        file_path = str(cog_data_path(self)) + f"/{guild.id}/{filename}"
        await self.make_guild_folder(directory)
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                test = await resp.read()
                with open(file_path, "wb") as f:
                    f.write(test)
        return filename

    async def wait_for_image(self, ctx):
        await ctx.send(_("Upload an image for me to use! Type `exit` to cancel."))
        msg = None
        while msg is None:
            check = lambda m: m.author == ctx.author and (m.attachments or "exit" in m.content)
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send(_("Image adding timed out."))
                break
            if "exit" in msg.content.lower():
                await ctx.send(_("Image adding cancelled."))
                break
        return msg

    async def get_colour(self, guild):
        if await self.bot.db.guild(guild).use_bot_color():
            return guild.me.colour
        else:
            return await self.bot.db.color()
            
    def resize_image(self, size, image):
        length, width = (16, 16) # Start with the smallest size we want to upload
        im = Image.open(image)
        if size <= 0:
            size = 1
        im.thumbnail((length*size, width*size), Image.ANTIALIAS)
        byte_array = BytesIO()
        im.save(byte_array, format="PNG")
        return discord.File(byte_array.getvalue(), filename="resize.png")

    async def trigger_menu(self, ctx:commands.Context, post_list: list,
                         message: discord.Message=None,
                         page=0, timeout: int=30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        post = post_list[page]
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = discord.Embed(timestamp=ctx.message.created_at)
            em.colour = await self.get_colour(ctx.guild)
            for trigger in post:
                blacklist = [await ChannelUserRole().convert(ctx, str(y)) for y in trigger["blacklist"]]
                blacklist = ", ".join(x.mention for x in blacklist)
                whitelist = [await ChannelUserRole().convert(ctx, str(y)) for y in trigger["whitelist"]]
                whitelist = ", ".join(x.mention for x in whitelist)
                info = (_("__Name__:") +"** "+ trigger["name"] + "**\n" +
                        _("__Author__: ") +"<@"+ str(trigger["author"])+ ">\n" +
                        _("__Count__: ")+ "**" + str(trigger["count"]) +"**\n" +
                        _("__Response__: ")+ "**" + trigger["response_type"] + "**\n"
                        )
                if trigger["response_type"] == "text":
                    info += _("__Text__: ") +"**"+ trigger["text"] + "**\n"
                if trigger["response_type"] == "dm":
                    info += _("__DM__: ") +"**"+ trigger["text"] + "**\n"
                if trigger["response_type"] == "command":
                    info += _("__Command__: ") +"**"+ trigger["text"] + "**\n"
                if trigger["response_type"] == "react":
                    server_emojis = "".join(f"<{e}>" for e in trigger["text"] if len(e) > 5)
                    unicode_emojis = "".join(e for e in trigger["text"] if len(e) < 5)
                    info += _("__Emojis__: ") + server_emojis + unicode_emojis + "\n"
                if trigger["response_type"] == "add_role":
                    roles = [ctx.guild.get_role(r).mention for r in trigger["text"]]
                    info += _("__Roles Added__: ") + humanize_list(roles) + "\n"
                if trigger["response_type"] == "remove_role":
                    roles = [ctx.guild.get_role(r).mention for r in trigger["text"]]
                    info += _("__Roles Removed__: ") + humanize_list(roles) + "\n"
                if whitelist:
                    info += _("__Whitelist__: ") + whitelist + "\n"
                if trigger["cooldown"]:
                    time = trigger["cooldown"]["time"]
                    style = trigger["cooldown"]["style"]
                    info += _("__Cooldown__: ")+"**{}s per {}**".format(time, style)
                length_of_info = len(info)
                if len(post) > 1:
                    diff = 1000 - length_of_info
                    info += _("__Regex__: ")+"```bf\n" + trigger["regex"][:diff]+ "```\n"
                else:
                    diff = 2000 - length_of_info
                    info += _("__Regex__: ")+"```bf\n" + trigger["regex"][:diff]+ "```\n"
                if blacklist:
                    info += _("__Blacklist__: ") + blacklist + "\n"
                
                if len(post) > 1:
                    em.add_field(name=trigger["name"], value=info[:1024])
                else:
                    em.description = info[:2048]
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
            em.set_footer(text=_("Page ")+"{}/{}".format(page+1, len(post_list)))
        else:
            msg = _("I need embed_links permission to use this command.")
            await ctx.send(msg)
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

    async def check_is_command(self, message):
        """Checks if the message is a bot command"""
        prefix_list = await self.bot.command_prefix(self.bot, message)
        msg = message.content
        for prefix in prefix_list:
            if msg.startswith(prefix):
                # Don't run a trigger if it's the name of a command
                command_text = msg.split(" ")[0].replace(prefix, "")
                try:
                    command = self.bot.get_command(command_text)
                except:
                    return True
                if command is not None:
                    return True
        return False
    
    async def on_message(self, message):
        if message.guild is None:
            return
        if message.author.bot:
            return
        local_perms = not await self.local_perms(message)
        global_perms =  not await self.global_perms(message)
        ignored_channel = not await self.check_ignored_channel(message)
        msg = message.content
        guild = message.guild
        channel = message.channel
        channel_perms = channel.permissions_for(message.author)
        is_command = await self.check_is_command(message)
        is_mod = await self.is_mod_or_admin(message.author)
        trigger_list = await self.config.guild(guild).trigger_list()
        autoimmune = getattr(self.bot, "is_automod_immune", None)
        for triggers in trigger_list:
            trigger = Trigger.from_json(trigger_list[triggers])
            if not await self.check_bw_list(trigger, message):
                continue
            search = re.findall(trigger.regex, message.content)
            if search != []:
                if await self.check_trigger_cooldown(message, trigger):
                    return
                if trigger.response_type in ["delete", 
                                             "kick", 
                                             "ban", 
                                             "add_role", 
                                             "remove_role"]:
                    if await autoimmune(message):
                        print_msg = _("ReTrigger: Author is immune "
                                      "from automated actions")
                        log.warn(print_msg)
                        return
                if trigger.response_type == "delete":
                    if channel_perms.manage_messages or is_mod:
                        print_msg = _("ReTrigger: Delete is ignored because "
                                      "user has manage messages permission")
                        log.warn(print_msg)
                        return
                elif trigger.response_type == "kick":
                    if channel_perms.kick_members or is_mod:
                        print_msg = _("ReTrigger: Kick is ignored "
                                      "because the user has kick permissions")
                        log.warn(print_msg)
                        return
                elif trigger.response_type == "ban":
                    if channel_perms.ban_members or is_mod:
                        print_msg = _("ReTrigger: Ban is ignored "
                                      "because the user has ban permissions")
                        log.warn(print_msg)
                        return
                elif trigger.response_type in ["add_role", "remove_role"]:
                    if channel_perms.manage_roles or is_mod:
                        print_msg = _("ReTrigger: role change is ignored "
                                      "because the user has mange roles permissions")
                        log.warn(print_msg)
                else:
                    if any([local_perms, global_perms, ignored_channel]):
                        print_msg = _("ReTrigger: Channel is "
                                      "ignored or user is blacklisted")
                        log.warn(print_msg)
                        return
                    if is_command:
                        return
                trigger._add_count(1)
                trigger_list[triggers] = trigger.to_json()
                await self.perform_trigger(message, trigger, search[0]) 
                await self.config.guild(guild).trigger_list.set(trigger_list)
                if not await self.config.guild(guild).allow_multiple():
                    return

    async def on_raw_message_edit(self, payload):
        if "content" not in payload.data:
            return
        if "guild_id" not in payload.data:
            return
        if "bot" in payload.data["author"]:
            return
        try:
            channel = self.bot.get_channel(int(payload.data["channel_id"]))
        except:
            # If we can't find the channel ignore it
            pass
        try:
            message = await channel.get_message(int(payload.data["id"]))
        except:
            # if we can't find the message ignore it
            pass
        try:
            local_perms = not await self.local_perms(message)
        except:
            return
        global_perms =  not await self.global_perms(message)
        ignored_channel = not await self.check_ignored_channel(message)
        guild = message.guild
        channel_perms = channel.permissions_for(message.author)
        is_command = await self.check_is_command(message)
        is_mod = await self.is_mod_or_admin(message.author)
        trigger_list = await self.config.guild(guild).trigger_list()
        for triggers in trigger_list:
            trigger = Trigger.from_json(trigger_list[triggers])
            if not await self.check_bw_list(trigger, message):
                continue
            search = re.findall(trigger.regex, message.content)
            if search != []:
                if await self.check_trigger_cooldown(message, trigger):
                    return
                if trigger.response_type in ["delete", 
                                             "kick", 
                                             "ban", 
                                             "add_role", 
                                             "remove_role"]:
                    if await autoimmune(message):
                        print_msg = _("ReTrigger: Author is immune "
                                      "from automated actions")
                        log.warn(print_msg)
                        return
                if trigger.response_type == "delete":
                    if channel.permissions_for(message.author).manage_messages:
                        print_msg = _("ReTrigger: Delete is ignored because "
                                      "user has manage messages permission")
                        log.warn(print_msg)
                        return
                elif trigger.response_type == "kick":
                    if channel_perms.kick_members or is_mod:
                        print_msg = _("ReTrigger: Kick is ignored "
                                      "because the user has kick permissions")
                        log.warn(print_msg)
                        return
                elif trigger.response_type == "ban":
                    if channel_perms.ban_members or is_mod:
                        print_msg = _("ReTrigger: Ban is ignored "
                                      "because the user has ban permissions")
                        log.warn(print_msg)
                        return
                elif trigger.response_type in ["add_role", "remove_role"]:
                    if channel_perms.manage_roles or is_mod:
                        print_msg = _("ReTrigger: role change is ignored "
                                      "because the user has mange roles permissions")
                        log.warn(print_msg)
                else:
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
        reason = _("Trigger response: ") + trigger.name
        if trigger.response_type == "resize":
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            task = functools.partial(self.resize_image, size=len(find)-3, image=path)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                file = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
            try:
                await message.channel.send(file=file)
            except Exception as e:
                log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "text" and own_permissions.send_messages:
            try:
                await channel.send(trigger.text)
            except Exception as e:
                log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "dm":
            try:
                await author.send(trigger.text)
            except Exception as e:
                log.error(_("Retrigger encountered an error in ")+ str(author), exc_info=True)
            return
        if trigger.response_type == "react" and own_permissions.add_reactions:
            for emoji in trigger.text:
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "ban" and own_permissions.ban_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally ban the bot owner 
                # or try to ban the guild owner
                return
            if guild.me.top_role > author.top_role:
                try:
                    await author.ban(reason=reason, delete_message_days=0)
                except Exception as e:
                    log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "kick" and own_permissions.kick_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally kick the bot owner 
                # or try to kick the guild owner
                return
            if guild.me.top_role > author.top_role:
                try:
                    await author.kick(reason=reason)
                except Exception as e:
                    log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "image" and own_permissions.attach_files:
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            file = discord.File(path)
            try:
                await channel.send(trigger.text, file=file)
            except Exception as e:
                log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "command":
            msg = copy(message)
            prefix_list = await self.bot.command_prefix(self.bot, message)
            msg.content = prefix_list[0] + trigger.text
            self.bot.dispatch("message", msg)
            return
        if trigger.response_type == "delete":
            try:
                await message.delete()
            except Exception as e:
                log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            modlogs = await self.config.guild(guild).modlog()
            if modlogs:
                if modlogs == "default":
                    # We'll get the default modlog channel setup
                    # with modlogset
                    try:
                        modlog_channel = await modlog.get_modlog_channel(guild)
                    except Exception as e:
                        log.error("Error getting modlog channel", exc_info=True)
                        # Return early if no modlog channel exists
                        return
                else:
                    modlog_channel = guild.get_channel(modlogs)
                    if modlog_channel is None:
                        return
                infomessage = (_("A message from ") + str(message.author) +
                               _(" was deleted in ")+
                               message.channel.name)
                embed = discord.Embed(description=message.content,
                                      colour=discord.Colour.dark_red(),
                                      timestamp=datetime.now())
                embed.add_field(name=_("Channel"), value=message.channel.mention)
                embed.add_field(name=_("Trigger Name"), value=trigger.name)
                finds = re.findall(trigger.regex, message.content)
                embed.add_field(name=_("Found Triggers"), value=str(finds))
                if message.attachments:
                    files = ", ".join(a.filename for a in message.attachments)
                    if len(message.attachments) > 1:
                        files = files[:-2]
                    embed.add_field(name=_("Attachments"), value=files)
                embed.set_footer(text=_("User ID: ")+ str(message.author.id))
                embed.set_author(name=str(author) + _(" - Deleted Message"), 
                                 icon_url=message.author.avatar_url)
                try:
                    if modlog_channel.permissions_for(guild.me).embed_links:
                        await modlog_channel.send(embed=embed)
                    else:
                        await modlog_channel.send(infomessage)
                except:
                    pass
                return
        if trigger.response_type == "add_role":
            for roles in trigger.text:
                role = guild.get_role(roles)
                try:
                    await author.add_roles(role, reason=reason)
                except Exception as e:
                    log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
            return
        if trigger.response_type == "remove_role":
            for roles in trigger.text:
                role = guild.get_role(roles)
                try:
                    await author.remove_roles(role, reason=reason)
                except Exception as e:
                    log.error(_("Retrigger encountered an error in ")+ guild.name, exc_info=True)
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
                        log.error("Error deleting saved image", exc_info=True)
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
    @commands.guild_only()
    async def retrigger(self, ctx):
        """
            Setup automatic triggers based on regular expressions

            https://regex101.com/ is a good place to test regex
        """
        pass

    @retrigger.command()
    @checks.mod_or_permissions(manage_guild=True)
    async def allowmultiple(self, ctx):
        """
            Toggle multiple triggers to respond at once
        """
        if await self.config.guild(ctx.guild).allow_multiple():
            await self.config.guild(ctx.guild).allow_multiple.set(False)
            msg = _("Multiple responses disabled, "
                   "only the first trigger will happen.")
            await ctx.send(msg)
            return
        else:
            await self.config.guild(ctx.guild).allow_multiple.set(True)
            msg = _("Multiple responses enabled, "
                    "all triggers will occur.")
            await ctx.send(msg)
            return

    @retrigger.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog(self, ctx, channel:Union[discord.TextChannel, str]):
        """
            Set the modlog channel for filtered words

            `channel` The channel you would like filtered word notifications to go
            Use `none` or `clear` to not show any modlogs
            User `default` to use the built in modlog channel
        """
        if type(channel) is str:
            if channel.lower() in ["none", "clear"]:
                channel = None
            elif channel.lower() in ["default"]:
                channel = "default"
            else:
                await ctx.send(_("Channel \"{channel}\" not found.").format(channel=channel))
                return
            await self.config.guild(ctx.guild).modlog.set(channel)
        else:
            await self.config.guild(ctx.guild).modlog.set(channel.id)
        await ctx.send(_("Modlog set to {channel}").format(channel=channel))

    @retrigger.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist(self, ctx):
        """
            Set blacklist options for retrigger
        """
        pass

    @retrigger.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist(self, ctx):
        """
            Set whitelist options for retrigger
        """
        pass

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def cooldown(self, ctx, trigger:TriggerExists, time:int, style="guild"):
        """
            Set cooldown options for retrigger

            `trigger` is the name of the trigger
            `time` is a time in seconds until the trigger will run again
            set a time of 0 or less to remove the cooldown
            `style` must be either `guild`, `server`, `channel`, `user`, or `member`
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if style not in ["guild", "server", "channel", "user", "member"]:
            msg = _("Style must be either `guild`, "
                    "`server`, `channel`, `user`, or `member`.")
            await ctx.send(msg)
            return
        msg = _("Cooldown of {time}s per {style} set for Trigger `{name}`.")
        if style in ["user", "member"]:
            style = "author"
        if style in ["guild", "server"]:
            cooldown = {"time":time, "style":style, "last": 0}
        else:
            cooldown = {"time":time, "style":style, "last": []}
        if time <= 0:
            cooldown = {}
            msg = _("Cooldown for Trigger `") + name + _("` reset.")
        trigger_list = await self.config.guild(ctx.guild).trigger_list()
        trigger.cooldown = cooldown
        trigger_list[name] = trigger.to_json()
        await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
        await ctx.send(msg.format(time=time, style=style, name=trigger.name))

    @whitelist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_add(self, ctx, trigger:TriggerExists, channel_user_role:ChannelUserRole):
        """
            Add channel to triggers whitelist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to whitelist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id not in trigger.whitelist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.whitelist.append(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} added `{list_type}` to its whitelist.")
        else:
            msg = _("Trigger `{name}` already has {list_type} whitelisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))
        

    @whitelist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_remove(self, ctx, trigger:TriggerExists, channel_user_role:ChannelUserRole):
        """
            Remove channel from triggers whitelist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to remove from the whitelist
        """        
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id in trigger.whitelist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.whitelist.remove(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} removed `{list_type}` from its whitelist.")
        else:
            msg = _("Trigger `{name}` does not have {list_type} whitelisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))
        

    @blacklist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_add(self, ctx, trigger:TriggerExists, channel_user_role:ChannelUserRole):
        """
            Add channel to triggers blacklist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to blacklist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id not in trigger.blacklist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.blacklist.append(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} added `{list_type}` to its blacklist.")
        else:
            msg = _("Trigger `{name}` already has {list_type} blacklisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))


    @blacklist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_remove(self, ctx, trigger:TriggerExists, channel_user_role:ChannelUserRole):
        """
            Remove channel from triggers blacklist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to remove from the blacklist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id in trigger.blacklist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.blacklist.remove(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} removed `{list_type}` from its blacklist.")
        else:
            msg = _("Trigger `{name}` does not have {list_type} blacklisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))


    @retrigger.command()
    async def list(self, ctx, trigger:TriggerExists=None):
        """
            List information about triggers

            `trigger` if supplied provides information about named trigger
        """
        if trigger:
            if type(trigger) is str:
                return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
            else:
                return await self.trigger_menu(ctx, [[trigger.to_json()]])
        trigger_dict = await self.config.guild(ctx.guild).trigger_list()
        trigger_list = [trigger_dict[name] for name in trigger_dict]
        if trigger_list == []:
            msg = _("There are no triggers setup on this server.")
            await ctx.send(msg)
            return
        post_list = [trigger_list[i:i + 10] for i in range(0, len(trigger_list), 10)]
        await self.trigger_menu(ctx, post_list)

    @retrigger.command(aliases=["del", "rem", "delete"])
    @checks.mod_or_permissions(manage_messages=True)
    async def remove(self, ctx, trigger:TriggerExists):
        """
            Remove a specified trigger

            `trigger` is the name of the trigger
        """
        if type(trigger) is Trigger:
            await self.remove_trigger(ctx.guild, trigger.name)
            await ctx.send(_("Trigger `")+trigger.name+_("` removed."))
        else:
            await ctx.send(_("Trigger `")+trigger+_("` doesn't exist."))


    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def text(self, ctx, name:TriggerExists, regex:ValidRegex, *, text:str):
        """
            Add a text response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` response of the trigger
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "text", 
                              author, 
                              0, 
                              None, 
                              text, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def dm(self, ctx, name:TriggerExists, regex:ValidRegex, *, text:str):
        """
            Add a dm response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` response of the trigger
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "dm", 
                              author, 
                              0, 
                              None, 
                              text, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def image(self, ctx, name:TriggerExists, regex:ValidRegex, image_url:str=None):
        """
            Add an image/file response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, 
                              regex, 
                              "image", 
                              author, 
                              0, 
                              filename, 
                              None, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def imagetext(self, ctx, name:TriggerExists, regex:ValidRegex, text:str, image_url:str=None):
        """
            Add an image/file response with text trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` the triggered text response
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, 
                              regex, 
                              "image", 
                              author, 
                              0, 
                              filename, 
                              text, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def resize(self, ctx, name:TriggerExists, regex:ValidRegex, image_url:str=None):
        """
            Add an image to resize in response to a trigger
            this will attempt to resize the image based on length of matching regex

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, 
                              regex, 
                              "resize", 
                              author, 
                              0, 
                              filename, 
                              None, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, name:TriggerExists, regex:str):
        """
            Add a trigger to ban users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get banned by accident

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "ban", 
                              author, 
                              0, 
                              None, 
                              None, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, name:TriggerExists, regex:str):
        """
            Add a trigger to kick users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get kicked by accident

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "kick", 
                              author, 
                              0, 
                              None, 
                              None, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def react(self, ctx, name:TriggerExists, regex:ValidRegex, *emojis:str):
        """
            Add a reaction trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `emojis` the emojis to react with when triggered separated by spaces
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        good_emojis = []
        for emoji in emojis:
            if "<" in emoji and ">" in emoji:
                emoji = emoji[1:-1]
            try:
                await ctx.message.add_reaction(emoji)
                good_emojis.append(emoji)
            except Exception as e:
                log.error("Could not react with emoji", exc_info=True)
        if good_emojis == []:
            await ctx.send(_("None of the emojis supplied will work!"))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "react", 
                              author, 
                              0, 
                              None, 
                              good_emojis, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def command(self, ctx, name:TriggerExists, regex:ValidRegex, *, command:str):
        """
            Add a command trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `command` the command that will be triggered, do add [p] prefix
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send(command + _(" doesn't seem to be an available command."))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "command", 
                              author, 
                              0, 
                              None, 
                              command, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["deletemsg"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def filter(self, ctx, name:TriggerExists, regex:str):
        """
            Add a trigger to delete a message

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "delete", 
                              author, 
                              0, 
                              None, 
                              None, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(self, ctx, name:TriggerExists, regex:ValidRegex, *roles:discord.Role):
        """
            Add a trigger to add a role

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `role` the role applied when the regex pattern matches
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        for role in roles:
            if role >= ctx.me.top_role:
                await ctx.send(_("I can't assign roles higher than my own."))
                return
        roles = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "add_role", 
                              author, 
                              0, 
                              None, 
                              roles, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(self, ctx, name:TriggerExists, regex:ValidRegex, *roles:discord.Role):
        """
            Add a trigger to remove a role

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `role` the role applied when the regex pattern matches
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        for role in roles:
            if role >= ctx.me.top_role:
                await ctx.send(_("I can't remove roles higher than my own."))
                return
        roles = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, 
                              regex, 
                              "remove_role", 
                              author, 
                              0, 
                              None, 
                              roles, 
                              [], 
                              [], 
                              {})
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))
