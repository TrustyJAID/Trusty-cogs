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
from multiprocessing.pool import TimeoutError

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
        self.re_pool

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

    async def is_mod_or_admin(self, member: discord.Member):
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
        if mod is None:
            return True
        guild_ignored = await mod.settings.guild(guild).ignored()
        chann_ignored = await mod.settings.channel(channel).ignored()
        return not (guild_ignored or chann_ignored and not perms.manage_channels)

    async def make_guild_folder(self, directory):
        if not directory.is_dir():
            log.info("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def save_image_location(self, image_url, guild):
        seed = "".join(random.sample(string.ascii_uppercase + string.digits, k=5))
        filename = image_url.split("/")[-1]
        filename = "{}-{}".format(seed, filename)
        directory = cog_data_path(self) / str(guild.id)
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
        length, width = (16, 16)  # Start with the smallest size we want to upload
        with Image.open(image) as im:
            if size <= 0:
                size = 1
            im.thumbnail((length * size, width * size), Image.ANTIALIAS)
            byte_array = BytesIO()
            im.save(byte_array, format="PNG")
            return discord.File(byte_array.getvalue(), filename="resize.png")

    async def trigger_menu(
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
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            msg = _("I need embed_links permission to use this command.")
            await ctx.send(msg)
            return
        em = discord.Embed(timestamp=ctx.message.created_at)
        em.colour = await self.get_colour(ctx.guild)
        for trigger in post:
            blacklist = [
                await ChannelUserRole().convert(ctx, str(y)) for y in trigger["blacklist"]
            ]
            blacklist = ", ".join(x.mention for x in blacklist)
            whitelist = [
                await ChannelUserRole().convert(ctx, str(y)) for y in trigger["whitelist"]
            ]
            whitelist = ", ".join(x.mention for x in whitelist)
            responses = ", ".join(r for r in trigger["response_type"])
            info = (
                _("__Name__:")
                + "** "
                + trigger["name"]
                + "**\n"
                + _("__Author__: ")
                + "<@"
                + str(trigger["author"])
                + ">\n"
                + _("__Count__: ")
                + "**"
                + str(trigger["count"])
                + "**\n"
                + _("__Response__: ")
                + "**"
                + responses
                + "**\n"
            )
            if "text" in trigger["response_type"]:
                if trigger["multi_payload"]:
                    response = "\n".join(t[1] for t in trigger["multi_payload"] if t[0] == "text")
                else:
                    response = trigger["text"]
                info += _("__Text__: ") + "**{response}**\n".format(response=response)
            if "dm" in trigger["response_type"]:
                if trigger["multi_payload"]:
                    response = "\n".join(t[1] for t in trigger["multi_payload"] if t[0] == "dm")
                else:
                    response = trigger["text"]
                info += _("__DM__: ") + "**{response}**\n".format(response=response)
            if "command" in trigger["response_type"]:
                if trigger["multi_payload"]:
                    response = "\n".join(
                        t[1] for t in trigger["multi_payload"] if t[0] == "command"
                    )
                else:
                    response = trigger["text"]
                info += _("__Command__: ") + "**{response}**\n".format(response=response)
            if "react" in trigger["response_type"]:
                if trigger["multi_payload"]:
                    response = [
                        r for t in trigger["multi_payload"] for r in t[1:] if t[0] == "react"
                    ]
                else:
                    response = trigger["text"]
                server_emojis = "".join(f"<{e}>" for e in response if len(e) > 5)
                unicode_emojis = "".join(e for e in response if len(e) < 5)
                info += _("__Emojis__: ") + server_emojis + unicode_emojis + "\n"
            if "add_role" in trigger["response_type"]:
                if trigger["multi_payload"]:
                    response = [
                        r for t in trigger["multi_payload"] for r in t[1:] if t[0] == "add_role"
                    ]
                else:
                    response = trigger["text"]
                roles = [ctx.guild.get_role(r).mention for r in response]
                info += _("__Roles Added__: ") + humanize_list(roles) + "\n"
            if "remove_role" in trigger["response_type"]:
                if trigger["multi_payload"]:
                    response = [
                        r for t in trigger["multi_payload"] for r in t[1:] if t[0] == "remove_role"
                    ]
                else:
                    response = trigger["text"]
                roles = [ctx.guild.get_role(r).mention for r in response]
                info += _("__Roles Removed__: ") + humanize_list(roles) + "\n"
            if whitelist:
                info += _("__Whitelist__: ") + whitelist + "\n"
            if trigger["cooldown"]:
                time = trigger["cooldown"]["time"]
                style = trigger["cooldown"]["style"]
                info += _("__Cooldown__: ") + "**{}s per {}**".format(time, style)
            length_of_info = len(info)
            if len(post) > 1:
                diff = 1000 - length_of_info
                info += _("__Regex__: ") + "```bf\n" + trigger["regex"][:diff] + "```\n"
            else:
                diff = 2000 - length_of_info
                info += _("__Regex__: ") + "```bf\n" + trigger["regex"][:diff] + "```\n"
            if blacklist:
                info += _("__Blacklist__: ") + blacklist + "\n"

            if len(post) > 1:
                em.add_field(name=trigger["name"], value=info[:1024])
            else:
                em.description = info[:2048]
        em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
        em.set_footer(text=_("Page ") + "{}/{}".format(page + 1, len(post_list)))
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
                return await self.trigger_menu(
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
                return await self.trigger_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
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
                    trigger.cooldown["last"].append({"id": snowflake.id, "last": now})
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
                                trigger.cooldown["last"].remove({"id": snowflake.id, "last": last})
                                trigger.cooldown["last"].append({"id": snowflake.id, "last": now})
                                trigger_list[trigger.name] = trigger.to_json()
                                await self.config.guild(guild).trigger_list.set(trigger_list)
                                return False
                            else:
                                return True

    async def check_is_command(self, message):
        """Checks if the message is a bot command"""
        prefix_list = await self.bot.command_prefix(self.bot, message)
        msg = message.content
        is_command = False
        for prefix in prefix_list:
            if msg.startswith(prefix):
                # Don't run a trigger if it's the name of a command
                command_text = msg.replace(prefix, "").split(" ")[0]
                command = self.bot.get_command(command_text)
                if command:
                    is_command = True
        return is_command

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
            log.debug(_("I don't have permission to read channel history"))
            return
        except Exception as e:
            log.info("Could not find channel or message", exc_info=True)
            # If we can't find the channel ignore it
            return
        await self.check_triggers(message)

    async def check_triggers(self, message):
        msg = message.content
        guild = message.guild
        channel = message.channel
        author = message.author

        trigger_list = await self.config.guild(guild).trigger_list()
        if not trigger_list:
            return
        local_perms = not await self.local_perms(message)
        global_perms = not await self.global_perms(message)
        ignored_channel = not await self.check_ignored_channel(message)
        channel_perms = channel.permissions_for(author)
        is_command = await self.check_is_command(message)
        is_mod = await self.is_mod_or_admin(author)

        autoimmune = getattr(self.bot, "is_automod_immune", None)
        auto_mod = ["delete", "kick", "ban", "add_role", "remove_role"]

        for triggers in trigger_list:
            # log.debug(triggers)
            trigger = Trigger.from_json(trigger_list[triggers])
            allowed_trigger = await self.check_bw_list(trigger, message)
            is_auto_mod = trigger.response_type in auto_mod
            if not allowed_trigger:
                continue
            if allowed_trigger and (is_auto_mod and is_mod):
                continue

            if await self.check_trigger_cooldown(message, trigger):
                continue
            if any(t for t in trigger.response_type if t in auto_mod):
                if await autoimmune(message):
                    print_msg = _(
                        "ReTrigger: {author} is immune " "from automated actions "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
            if "delete" in trigger.response_type:
                if channel_perms.manage_messages or is_mod:
                    print_msg = _(
                        "ReTrigger: Delete is ignored because {author} "
                        "has manage messages permission "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
            elif "kick" in trigger.response_type:
                if channel_perms.kick_members or is_mod:
                    print_msg = _(
                        "ReTrigger: Kick is ignored because " "{author} has kick permissions "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
            elif "ban" in trigger.response_type:
                if channel_perms.ban_members or is_mod:
                    print_msg = _(
                        "ReTrigger: Ban is ignored because {author} " "has ban permissions "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
            elif any(t for t in trigger.response_type if t in ["add_role", "remove_role"]):
                if channel_perms.manage_roles or is_mod:
                    print_msg = _(
                        "ReTrigger: role change is ignored because {author} "
                        "has mange roles permissions "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
            else:
                if any([local_perms, global_perms, ignored_channel]):
                    print_msg = _(
                        "ReTrigger: Channel is ignored or " "{author} is blacklisted "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
                if is_command:
                    continue
            try:
                process = self.re_pool.apply_async(trigger.regex.findall, (message.content,))
                task = functools.partial(process.get, timeout=10)
                task = self.bot.loop.run_in_executor(None, task)
                search = await asyncio.wait_for(task, timeout=10)
            except (TimeoutError, asyncio.TimeoutError) as e:
                error_msg = (
                    "ReTrigger took too long to find matches "
                    f"{guild.name} ({guild.id}) "
                    f"Offending regex {trigger.regex} Name: {trigger.name}"
                )
                log.error(error_msg, exc_info=True)
                return  # we certainly don't want to be performing multiple triggers if this happens
            except Exception as e:
                log.error(
                    f"{trigger.name} {trigger.regex} in {guild.name} {guild.id}", exc_info=True
                )
                continue
            if search != []:
                trigger._add_count(1)
                trigger_list[triggers] = trigger.to_json()
                await self.perform_trigger(message, trigger, search[0])
                await self.config.guild(guild).trigger_list.set(trigger_list)
                # if not await self.config.guild(guild).allow_multiple():
                return

    async def perform_trigger(self, message, trigger, find):
        own_permissions = message.channel.permissions_for(message.guild.me)
        guild = message.guild
        channel = message.channel
        author = message.author
        reason = _("Trigger response: {trigger}").format(trigger=trigger.name)
        error_in = _("Retrigger encountered an error in ")
        if "resize" in trigger.response_type and own_permissions.attach_files:
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            task = functools.partial(self.resize_image, size=len(find) - 3, image=path)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                file = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                pass
            try:
                await channel.send(file=file)
            except Exception as e:
                log.error(error_in + guild.name, exc_info=True)
        if "text" in trigger.response_type and own_permissions.send_messages:
            if trigger.multi_payload:
                response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "text")
            else:
                response = trigger.text
            response = await self.convert_parms(message, response)
            try:
                await channel.send(response)
            except Exception as e:
                log.error(error_in + guild.name, exc_info=True)
        if "dm" in trigger.response_type:
            if trigger.multi_payload:
                response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "dm")
            else:
                response = trigger.text
            response = await self.convert_parms(message, response)
            try:
                await author.send(response)
            except Exception as e:
                log.error(error_in + str(author), exc_info=True)
        if "react" in trigger.response_type and own_permissions.add_reactions:
            if trigger.multi_payload:
                response = [r for t in trigger.multi_payload for r in t[1:] if t[0] == "react"]
            else:
                response = trigger.text
            for emoji in response:
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    log.error(error_in + guild.name, exc_info=True)
        if "ban" in trigger.response_type and own_permissions.ban_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally ban the bot owner
                # or try to ban the guild owner
                return
            if guild.me.top_role > author.top_role:
                try:
                    await author.ban(reason=reason, delete_message_days=0)
                except Exception as e:
                    log.error(error_in + guild.name, exc_info=True)
        if "kick" in trigger.response_type and own_permissions.kick_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally kick the bot owner
                # or try to kick the guild owner
                return
            if guild.me.top_role > author.top_role:
                try:
                    await author.kick(reason=reason)
                except Exception as e:
                    log.error(error_in + guild.name, exc_info=True)
        if "image" in trigger.response_type and own_permissions.attach_files:
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            file = discord.File(path)
            response = trigger.text
            if response:
                response = await self.convert_parms(message, response)
            try:
                await channel.send(trigger.text, file=file)
            except Exception as e:
                log.error(error_in + guild.name, exc_info=True)
        if "command" in trigger.response_type:
            if trigger.multi_payload:
                response = [t[1] for t in trigger.multi_payload if t[0] == "command"]
                for command in response:
                    command = await self.convert_parms(message, command)
                    msg = copy(message)
                    prefix_list = await self.bot.command_prefix(self.bot, message)
                    msg.content = prefix_list[0] + response
                    self.bot.dispatch("message", msg)
            else:
                msg = copy(message)
                command = await self.convert_parms(message, trigger.text)
                prefix_list = await self.bot.command_prefix(self.bot, message)
                msg.content = prefix_list[0] + command
                self.bot.dispatch("message", msg)
        if "add_role" in trigger.response_type and own_permissions.manage_roles:
            if trigger.multi_payload:
                response = [r for t in trigger.multi_payload for r in t[1:] if t[0] == "add_role"]
            else:
                response = trigger.text
            for roles in response:
                role = guild.get_role(roles)
                try:
                    await author.add_roles(role, reason=reason)
                except Exception as e:
                    log.error(error_in + guild.name, exc_info=True)
        if "remove_role" in trigger.response_type and own_permissions.manage_roles:
            if trigger.multi_payload:
                response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "remove_role"
                ]
            else:
                response = trigger.text
            for roles in response:
                role = guild.get_role(roles)
                try:
                    await author.remove_roles(role, reason=reason)
                except Exception as e:
                    log.error(error_in + guild.name, exc_info=True)
        if "delete" in trigger.response_type and own_permissions.manage_messages:
            log.debug("Performing delete trigger")
            await self.delete_modlog_action(message, trigger)
            try:
                await message.delete()
            except Exception as e:
                log.error(error_in + guild.name, exc_info=True)

        if "mock" in trigger.response_type:
            if trigger.multi_payload:
                response = [t[1] for t in trigger.multi_payload if t[0] == "mock"]
                for command in response:
                    command = await self.convert_parms(message, command)
                    msg = copy(message)
                    mocker = guild.get_member(trigger.author)
                    if not mocker:
                        return
                    msg.author = mocker
                    prefix_list = await self.bot.command_prefix(self.bot, message)
                    msg.content = prefix_list[0] + command
                    self.bot.dispatch("message", msg)
            else:
                msg = copy(message)
                mocker = guild.get_member(trigger.author)
                command = await self.convert_parms(message, trigger.text)
                if not mocker:
                    return  # We'll exit early if the author isn't on the server anymore
                msg.author = mocker
                prefix_list = await self.bot.command_prefix(self.bot, message)
                msg.content = prefix_list[0] + command
                self.bot.dispatch("message", msg)

    async def convert_parms(self, message, raw_response) -> str:
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/customcom/customcom.py
        ctx = await self.bot.get_context(message)
        cc_args = (*ctx.args, *ctx.kwargs.values())
        results = re.findall(r"{([^}]+)\}", raw_response)
        for result in results:
            param = self.transform_parameter(result, ctx.message)
            raw_response = raw_response.replace("{" + result + "}", param)
        results = re.findall(r"{((\d+)[^.}]*(\.[^:}]+)?[^}]*)\}", raw_response)
        if results:
            low = min(int(result[1]) for result in results)
            for result in results:
                index = int(result[1]) - low
                arg = self.transform_arg(result[0], result[2], cc_args[index])
                raw_response = raw_response.replace("{" + result[0] + "}", arg)
        return raw_response
        # await ctx.send(raw_response)

    @staticmethod
    def transform_arg(result, attr, obj) -> str:
        attr = attr[1:]  # strip initial dot
        if not attr:
            return str(obj)
        raw_result = "{" + result + "}"
        # forbid private members and nested attr lookups
        if attr.startswith("_") or "." in attr:
            return raw_result
        return str(getattr(obj, attr, raw_result))

    @staticmethod
    def transform_parameter(result, message) -> str:
        """
        For security reasons only specific objects are allowed
        Internals are ignored
        """
        raw_result = "{" + result + "}"
        objects = {
            "message": message,
            "author": message.author,
            "channel": message.channel,
            "guild": message.guild,
            "server": message.guild,
        }
        if result in objects:
            return str(objects[result])
        try:
            first, second = result.split(".")
        except ValueError:
            return raw_result
        if first in objects and not second.startswith("_"):
            first = objects[first]
        else:
            return raw_result
        return str(getattr(first, second, raw_result))

    async def delete_modlog_action(self, message, trigger):
        modlogs = await self.config.guild(message.guild).modlog()
        guild = message.guild
        author = message.author
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
            infomessage = (
                _("A message from ") + str(author) + _(" was deleted in ") + message.channel.name
            )
            embed = discord.Embed(
                description=message.content,
                colour=discord.Colour.dark_red(),
                timestamp=datetime.now(),
            )
            embed.add_field(name=_("Channel"), value=message.channel.mention)
            embed.add_field(name=_("Trigger Name"), value=trigger.name)
            finds = re.findall(trigger.regex, message.content)
            embed.add_field(name=_("Found Triggers"), value=str(finds))
            if message.attachments:
                files = ", ".join(a.filename for a in message.attachments)
                embed.add_field(name=_("Attachments"), value=files)
            embed.set_footer(text=_("User ID: ") + str(message.author.id))
            embed.set_author(
                name=str(author) + _(" - Deleted Message"), icon_url=author.avatar_url
            )
            try:
                if modlog_channel.permissions_for(guild.me).embed_links:
                    await modlog_channel.send(embed=embed)
                else:
                    await modlog_channel.send(infomessage)
            except:
                pass

    async def remove_trigger(self, guild, trigger_name):
        trigger_list = await self.config.guild(guild).trigger_list()
        for triggers in trigger_list:
            # trigger = Trigger.from_json(trigger_list[triggers])
            if triggers == trigger_name:
                if trigger_list[triggers]["image"] is not None:
                    image = trigger_list[triggers]["image"]
                    path = str(cog_data_path(self)) + f"/{guild.id}/{image}"
                    try:
                        os.remove(path)
                    except Exception as e:
                        msg = _("Error deleting saved image in {guild}").format(guild=guild.id)
                        log.error(msg, exc_info=True)
                del trigger_list[triggers]
                await self.config.guild(guild).trigger_list.set(trigger_list)
                return True
        return False
