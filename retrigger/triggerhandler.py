import discord
import logging
import re
from redbot.core import commands, Config, modlog
from datetime import datetime
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_list
from PIL import Image
from io import BytesIO
from copy import copy
import os
import aiohttp
import functools
import asyncio
import random
import string
from multiprocessing import Pool, TimeoutError

from .converters import *


log = logging.getLogger("red.ReTrigger")
_ = Translator("ReTrigger", __file__)


class TriggerHandler:
    """
        Handles all processing of triggers
    """

    def __init__(self, *args):
        self.config: Config
        self.bot: Red

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
            log.info("Creating guild folder")
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
        with Image.open(image) as im:
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
        await self.check_triggers(message)

    async def on_raw_message_edit(self, payload):
        if "content" not in payload.data:
            return
        if "guild_id" not in payload.data:
            return
        if "bot" in payload.data["author"]:
            return
        try:
            channel = self.bot.get_channel(int(payload.data["channel_id"]))
            message = await channel.get_message(int(payload.data["id"]))
        except discord.errors.Forbidden:
            log.info("Could not find channel or message")
            return
        except Exception as e:
            log.info("Could not find channel or message", exc_info=True)
            # If we can't find the channel ignore it
            return
        await self.check_triggers(message)

    async def check_triggers(self, message):
        local_perms = not await self.local_perms(message)
        global_perms =  not await self.global_perms(message)
        ignored_channel = not await self.check_ignored_channel(message)

        msg = message.content
        guild = message.guild
        channel = message.channel
        author = message.author

        channel_perms = channel.permissions_for(author)
        is_command = await self.check_is_command(message)
        is_mod = await self.is_mod_or_admin(author)
        trigger_list = await self.config.guild(guild).trigger_list()
        autoimmune = getattr(self.bot, "is_automod_immune", None)
        auto_mod = ["delete", "kick", "ban", "add_role", "remove_role"]
        
        for triggers in trigger_list:
            trigger = Trigger.from_json(trigger_list[triggers])
            allowed_trigger = await self.check_bw_list(trigger, message)
            is_auto_mod = trigger.response_type in auto_mod
            if not allowed_trigger:
                continue
            if allowed_trigger and (is_auto_mod and is_mod):
                continue

            try:
                pool = Pool(processes=1)
                process = pool.apply_async(re.findall, (trigger.regex, message.content))
                task = functools.partial(process.get, timeout=10)
                task = self.bot.loop.run_in_executor(None, task)
                search = await asyncio.wait_for(task, timeout=10)
                pool.close()
            except (TimeoutError, asyncio.TimeoutError) as e:
                pool.close()
                error_msg = ("ReTrigger took too long to find matches "
                             f"{guild.name} ({guild.id}) "
                             f"Offending regex {trigger.regex} Name: {trigger.name}")
                log.error(error_msg, exc_info=True)
                return # we certainly don't want to be performing multiple triggers if this happens

            if search != []:
                if await self.check_trigger_cooldown(message, trigger):
                    return
                if trigger.response_type in auto_mod:
                    if await autoimmune(message):
                        print_msg = _("ReTrigger: {author} is immune "
                                      "from automated actions ").format(author=author)
                        log.info(print_msg + trigger.name)
                        return
                if trigger.response_type == "delete":
                    if channel_perms.manage_messages or is_mod:
                        print_msg = _("ReTrigger: Delete is ignored because {author} "
                                      "has manage messages permission ").format(author=author)
                        log.info(print_msg+ trigger.name)
                        return
                elif trigger.response_type == "kick":
                    if channel_perms.kick_members or is_mod:
                        print_msg = _("ReTrigger: Kick is ignored because "
                                      "{author} has kick permissions ").format(author=author)
                        log.info(print_msg+ str(message.author))
                        return
                elif trigger.response_type == "ban":
                    if channel_perms.ban_members or is_mod:
                        print_msg = _("ReTrigger: Ban is ignored because {author} "
                                      "has ban permissions ").format(author=author)
                        log.info(print_msg+ str(message.author))
                        return
                elif trigger.response_type in ["add_role", "remove_role"]:
                    if channel_perms.manage_roles or is_mod:
                        print_msg = _("ReTrigger: role change is ignored because {author} "
                                      "has mange roles permissions ").format(author=author)
                        log.info(print_msg+ str(message.author))
                else:
                    if any([local_perms, global_perms, ignored_channel]):
                        print_msg = _("ReTrigger: Channel is ignored or"
                                      "{author} is blacklisted ").format(author=author)
                        log.info(print_msg+ str(message.author))
                        return
                    if is_command:
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
                        msg = (f"Error deleting saved image in {guild.id}")
                        log.error(msg, exc_info=True)
                del trigger_list[triggers]
                await self.config.guild(guild).trigger_list.set(trigger_list)
                return True
        return False
