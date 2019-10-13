import discord
import logging
import aiohttp
import functools
import asyncio
import random
import string
import os
import re

from io import BytesIO
from copy import copy
from datetime import datetime
from typing import List, Union, Pattern, cast, Dict

from redbot.core.bot import Red
from redbot.core import commands, Config, modlog
from redbot.core.i18n import Translator
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_list, box, escape

from discord.ext.commands.errors import BadArgument

from multiprocessing import TimeoutError
from multiprocessing.pool import Pool

from .converters import Trigger, ChannelUserRole

try:
    from PIL import Image
    try:
        import pytesseract
        ALLOW_OCR = True
    except ImportError:
        ALLOW_OCR = False

    ALLOW_RESIZE = True
except ImportError:
    ALLOW_RESIZE = False
    ALLOW_OCR = False


log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

RE_CTX: Pattern = re.compile(r"{([^}]+)\}")
RE_POS: Pattern = re.compile(r"{((\d+)[^.}]*(\.[^:}]+)?[^}]*)\}")
LINK_REGEX: Pattern = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|mp3|mp4))")
IMAGE_REGEX: Pattern = re.compile(r"(?:(?:https?):\/\/)?[\w/\-?=%.]+\.[(?:png|jpg|jpeg)]+")

listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


class TriggerHandler:
    """
        Handles all processing of triggers
    """

    config: Config
    bot: Red
    re_pool: Pool
    triggers: Dict[int, List[Trigger]]
    ALLOW_RESIZE: bool = ALLOW_RESIZE
    ALLOW_OCR: bool = ALLOW_OCR

    def __init__(self, *args):
        self.config: Config
        self.bot: Red
        self.re_pool: Pool
        self.triggers: Dict[int, List[Trigger]]
        self.ALLOW_RESIZE = ALLOW_RESIZE
        self.ALLOW_OCR = ALLOW_OCR

    async def remove_trigger_from_cache(self, guild: discord.Guild, trigger: Trigger):
        try:
            for t in self.triggers[guild.id]:
                if t.name == trigger.name:
                    self.triggers[guild.id].remove(t)
        except ValueError:
            # it will get removed on the next reload of the cog
            log.info("Trigger can't be removed :blobthinking:")
            pass

    async def can_edit(self, author: discord.Member, trigger: Trigger):
        """Chekcs to see if the member is allowed to edit the trigger"""
        if trigger.author == author.id:
            return True
        if await self.bot.is_owner(author):
            return True
        if author is author.guild.owner and "mock" not in trigger.response_type:
            return True

    async def local_perms(self, message: discord.Message) -> bool:
        """Check the user is/isn't locally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True
        elif message.guild is None:
            return True
        if not getattr(message.author, "roles", None):
            return False
        guild_settings = self.bot.db.guild(message.guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()
        author: discord.Member = cast(discord.Member, message.author)
        _ids = [r.id for r in author.roles if not r.is_default()]
        _ids.append(message.author.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, message: discord.Message) -> bool:
        """Check the user is/isn't globally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True

        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return message.author.id in whitelist

        return message.author.id not in await self.bot.db.blacklist()

    async def check_bw_list(self, trigger: Trigger, message: discord.Message) -> bool:
        can_run = True
        author: discord.Member = cast(discord.Member, message.author)
        if trigger.whitelist:
            can_run = False
            if message.channel.id in trigger.whitelist:
                can_run = True
            if message.author.id in trigger.whitelist:
                can_run = True
            for role in author.roles:
                if role.is_default():
                    continue
                if role.id in trigger.whitelist:
                    can_run = True
            return can_run
        else:
            if message.channel.id in trigger.blacklist:
                can_run = False
            if message.author.id in trigger.blacklist:
                can_run = False
            for role in author.roles:
                if role.is_default():
                    continue
                if role.id in trigger.blacklist:
                    can_run = False
        return can_run

    async def is_mod_or_admin(self, member: discord.Member) -> bool:
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

    async def make_guild_folder(self, directory):
        if not directory.is_dir():
            log.info("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def save_image_location(self, image_url: str, guild: discord.Guild) -> str:
        good_image_url = LINK_REGEX.search(image_url)
        if not good_image_url:
            return None
        seed = "".join(random.sample(string.ascii_uppercase + string.digits, k=5))
        filename = good_image_url.group(1).split("/")[-1]
        filename = "{}-{}".format(seed, filename)
        directory = cog_data_path(self) / str(guild.id)
        file_path = str(cog_data_path(self)) + f"/{guild.id}/{filename}"
        await self.make_guild_folder(directory)
        async with aiohttp.ClientSession() as session:
            async with session.get(good_image_url.group(1)) as resp:
                test = await resp.read()
                with open(file_path, "wb") as f:
                    f.write(test)
        return filename

    async def wait_for_image(self, ctx: commands.Context) -> discord.Message:
        await ctx.send(_("Upload an image for me to use! Type `exit` to cancel."))
        msg = None
        while msg is None:

            def check(m):
                return m.author == ctx.author and (m.attachments or "exit" in m.content)

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send(_("Image adding timed out."))
                break
            if "exit" in msg.content.lower():
                await ctx.send(_("Image adding cancelled."))
                break
        return msg

    async def wait_for_multiple_images(self, ctx: commands.Context) -> List[str]:
        await ctx.send(_("Upload an image for me to use! Type `exit` to cancel."))
        files: list = []
        while True:

            def check(m):
                return m.author == ctx.author

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                return files
            if "exit" in msg.content.lower():
                return files
            else:
                link = LINK_REGEX.search(msg.content)
                for a in msg.attachments:
                    if a.size > 8 * 1000 * 1000:
                        continue
                    try:
                        files.append(await self.save_image_location(a.url, ctx.guild))
                        await msg.add_reaction("✅")
                    except Exception:
                        pass
                if link:
                    try:
                        files.append(await self.save_image_location(link.group(0), ctx.guild))
                        await msg.add_reaction("✅")
                    except Exception:
                        pass
        return files

    async def wait_for_multiple_responses(self, ctx: commands.Context):
        msg_text = _(
            "Please enter your desired phrase to be used for this trigger."
            "Type `exit` to stop adding responses."
        )
        await ctx.send(msg_text)
        responses: list = []
        while True:

            def check(m):
                return m.author == ctx.author

            try:
                message = await self.bot.wait_for("message", check=check, timeout=60)
                await message.add_reaction("✅")
            except asyncio.TimeoutError:
                return responses
            if message.content == "exit":
                return responses
            else:
                responses.append(message.content)

    def resize_image(self, size: int, image: str) -> discord.File:
        length, width = (16, 16)  # Start with the smallest size we want to upload
        with Image.open(image) as im:
            if size <= 0:
                size = 1
            im.thumbnail((length * size, width * size), Image.ANTIALIAS)
            byte_array = BytesIO()
            im.save(byte_array, format="PNG")
            byte_array.seek(0)
            return discord.File(byte_array, filename="resize.png")

    async def trigger_embed(
        self, ctx: commands.Context, trigger_list: List[dict]
    ) -> List[Union[discord.Embed, str]]:
        msg_list = []
        embeds = ctx.channel.permissions_for(ctx.me).embed_links
        page = 1
        for triggers in trigger_list:
            trigger = await Trigger.from_json(triggers)
            author = ctx.guild.get_member(trigger.author)
            if not author:
                try:
                    author = await self.bot.fetch_user(trigger.author)
                except AttributeError:
                    author = await self.bot.get_user_info(trigger.author)
            blacklist = []
            for y in trigger.blacklist:
                try:
                    blacklist.append(await ChannelUserRole().convert(ctx, str(y)))
                except BadArgument:
                    continue
            if embeds:
                blacklist_s = ", ".join(x.mention for x in blacklist)
            else:
                blacklist_s = ", ".join(x.name for x in blacklist)
            whitelist = []
            for y in trigger.whitelist:
                try:
                    whitelist.append(await ChannelUserRole().convert(ctx, str(y)))
                except BadArgument:
                    continue
            if embeds:
                whitelist_s = ", ".join(x.mention for x in whitelist)
            else:
                whitelist_s = ", ".join(x.name for x in whitelist)
            responses = ", ".join(r for r in trigger.response_type)
            info = _(
                "Name: **{name}** \n"
                "Author: {author}\n"
                "Count: **{count}**\n"
                "Response: **{response}**\n"
            )
            if embeds:
                info = info.format(
                    name=trigger.name,
                    author=author.mention,
                    count=trigger.count,
                    response=responses,
                )
            else:
                info = info.format(
                    name=trigger.name, author=author.name, count=trigger.count, response=responses
                )
            if trigger.ignore_commands:
                info += _("Ignore commands: **{ignore}**\n").format(ignore=trigger.ignore_commands)
            if "text" in trigger.response_type:
                if trigger.multi_payload:
                    response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "text")
                else:
                    response = trigger.text
                info += _("Text: ") + "**{response}**\n".format(response=response)
            if "dm" in trigger.response_type:
                if trigger.multi_payload:
                    response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "dm")
                else:
                    response = trigger.text
                info += _("DM: ") + "**{response}**\n".format(response=response)
            if "command" in trigger.response_type:
                if trigger.multi_payload:
                    response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "command")
                else:
                    response = trigger.text
                info += _("Command: ") + "**{response}**\n".format(response=response)
            if "react" in trigger.response_type:
                if trigger.multi_payload:
                    emoji_response = [
                        r for t in trigger.multi_payload for r in t[1:] if t[0] == "react"
                    ]
                else:
                    emoji_response = trigger.text
                server_emojis = "".join(f"<{e}>" for e in emoji_response if len(e) > 5)
                unicode_emojis = "".join(e for e in emoji_response if len(e) < 5)
                info += _("Emojis: ") + server_emojis + unicode_emojis + "\n"
            if "add_role" in trigger.response_type:
                if trigger.multi_payload:
                    role_response = [
                        r for t in trigger.multi_payload for r in t[1:] if t[0] == "add_role"
                    ]
                else:
                    role_response = trigger.text
                roles = [ctx.guild.get_role(r) for r in role_response]
                if embeds:
                    roles_list = [r.mention for r in roles if r is not None]
                else:
                    roles_list = [r.name for r in roles if r is not None]
                if roles_list:
                    info += _("Roles Added: ") + humanize_list(roles_list) + "\n"
                else:
                    info += _("Roles Added: Deleted Roles\n")
            if "remove_role" in trigger.response_type:
                if trigger.multi_payload:
                    role_response = [
                        r for t in trigger.multi_payload for r in t[1:] if t[0] == "remove_role"
                    ]
                else:
                    role_response = trigger.text
                roles = [ctx.guild.get_role(r) for r in role_response]
                if embeds:
                    roles_list = [r.mention for r in roles if r is not None]
                else:
                    roles_list = [r.name for r in roles if r is not None]
                if roles_list:
                    info += _("Roles Removed: ") + humanize_list(roles_list) + "\n"
                else:
                    info += _("Roles Added: Deleted Roles\n")
            if whitelist_s:
                info += _("Whitelist: ") + whitelist_s + "\n"
            if blacklist_s:
                info += _("Blacklist: ") + blacklist_s + "\n"
            if trigger.cooldown:
                time = trigger.cooldown["time"]
                style = trigger.cooldown["style"]
                info += _("Cooldown: ") + "**{}s per {}**\n".format(time, style)
            if trigger.ocr_search:
                info += _("OCR: **Enabled**\n")
            if trigger.ignore_edits:
                info += _("Ignoring edits: **Enabled**\n")
            info += _("Regex: ") + box(trigger.regex.pattern[: 2000 - len(info)], lang="bf")
            if embeds:
                em = discord.Embed(
                    timestamp=ctx.message.created_at,
                    colour=await ctx.embed_colour(),
                    description=info,
                    title=_("Triggers for {guild}").format(guild=ctx.guild.name),
                )
                em.set_author(name=author, icon_url=author.avatar_url)
                if trigger.created_at == 0:
                    em.set_footer(
                        text=_("Page {page}/{leng}").format(page=page, leng=len(trigger_list))
                    )
                else:
                    em.set_footer(
                        text=_("Page {page}/{leng} Created").format(
                            page=page, leng=len(trigger_list)
                        )
                    )
                    em.timestamp = discord.utils.snowflake_time(trigger.created_at)
                msg_list.append(em)
            else:
                msg_list.append(info)
            page += 1
        return msg_list

    async def check_trigger_cooldown(self, message: discord.Message, trigger: Trigger) -> bool:
        now = datetime.now().timestamp()
        if trigger.cooldown:
            if trigger.cooldown["style"] in ["guild", "server"]:
                last = trigger.cooldown["last"]
                time = trigger.cooldown["time"]
                if (now - last) > time:
                    trigger.cooldown["last"] = now
                    return False
                else:
                    return True
            else:
                style = trigger.cooldown["style"]
                snowflake = getattr(message, style)
                if snowflake.id not in [x["id"] for x in trigger.cooldown["last"]]:
                    trigger.cooldown["last"].append({"id": snowflake.id, "last": now})
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
                                return False
                            else:
                                return True
        return False

    async def check_is_command(self, message: discord.Message) -> bool:
        """Checks if the message is a bot command"""
        prefix_list = await self.bot.command_prefix(self.bot, message)
        msg = message.content
        is_command = False
        for prefix in prefix_list:
            if msg.startswith(prefix):
                # Don't run a trigger if it's the name of a command
                command_text = msg.replace(prefix, "").split(" ")[0]
                if not command_text:
                    continue
                command = self.bot.get_command(command_text)
                if command:
                    is_command = True
        return is_command

    @listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if message.author.bot:
            return
        await self.check_triggers(message, False)

    @listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if "content" not in payload.data:
            return
        if "guild_id" not in payload.data:
            return
        if "bot" in payload.data["author"]:
            return
        try:
            channel = self.bot.get_channel(int(payload.data["channel_id"]))
            try:
                message = await channel.fetch_message(int(payload.data["id"]))
            except AttributeError:
                message = await channel.get_message(int(payload.data["id"]))
        except discord.errors.Forbidden:
            log.debug(_("I don't have permission to read channel history"))
            return
        except Exception:
            log.info("Could not find channel or message", exc_info=True)
            # If we can't find the channel ignore it
            return
        if message.author.bot:
            # somehow we got a bot through the previous check :thonk:
            return
        await self.check_triggers(message, True)

    async def check_triggers(self, message: discord.Message, edit: bool):
        """
            This is where we iterate through the triggers and perform the
            search. This does all the permission checks and cooldown checks
            before actually running the regex to avoid possibly long regex
            operations.
        """
        guild: discord.Guild = cast(discord.Guild, message.guild)
        if guild.id not in self.triggers:
            return
        channel: discord.TextChannel = cast(discord.TextChannel, message.channel)
        author: discord.Member = cast(discord.Member, message.author)

        local_perms = not await self.local_perms(message)
        global_perms = not await self.global_perms(message)
        channel_perms = channel.permissions_for(author)
        is_command = await self.check_is_command(message)
        is_mod = await self.is_mod_or_admin(author)

        autoimmune = getattr(self.bot, "is_automod_immune", None)
        auto_mod = ["delete", "kick", "ban", "add_role", "remove_role"]
        # async with self.config.guild(guild).trigger_list() as trigger_list:
        for trigger in self.triggers[guild.id]:
            # log.debug(triggers)
            # try:
            # trigger = await Trigger.from_json(trigger_list[triggers])
            # except Exception:
            # continue
            if edit and trigger.ignore_edits:
                continue

            allowed_trigger = await self.check_bw_list(trigger, message)
            is_auto_mod = trigger.response_type in auto_mod
            if not allowed_trigger:
                continue
            if allowed_trigger and (is_auto_mod and is_mod):
                continue
            if is_command and trigger.ignore_commands:
                continue
            if any(t for t in trigger.response_type if t in auto_mod):
                if await autoimmune(message):
                    print_msg = _(
                        "ReTrigger: {author} is immune from automated actions "
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
                        "ReTrigger: Kick is ignored because {author} has kick permissions "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
            elif "ban" in trigger.response_type:
                if channel_perms.ban_members or is_mod:
                    print_msg = _(
                        "ReTrigger: Ban is ignored because {author} has ban permissions "
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
                if any([local_perms, global_perms]):
                    print_msg = _(
                        "ReTrigger: Channel is ignored or {author} is blacklisted "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
                if is_command:
                    continue
            content = message.content
            if trigger.ocr_search and ALLOW_OCR:
                for attachment in message.attachments:
                    temp = BytesIO()
                    await attachment.save(temp)
                    temp.seek(0)
                    content += pytesseract.image_to_string(Image.open(temp))
                good_image_url = IMAGE_REGEX.findall(message.content)
                for link in good_image_url:
                    temp = BytesIO()
                    async with aiohttp.ClientSession() as session:
                        async with session.get(link) as resp:
                            data = await resp.read()
                            temp.write(data)
                            temp.seek(0)
                    content += pytesseract.image_to_string(Image.open(temp))
            if "delete" in trigger.response_type and trigger.text:
                content = (
                    message.content + " " + " ".join(f.filename for f in message.attachments)
                )

            search = await self.safe_regex_search(guild, trigger, content)
            if not search[0]:
                self.triggers[guild.id].remove(trigger)
                return
            elif search[0] and search[1] != []:
                if await self.check_trigger_cooldown(message, trigger):
                    continue
                trigger.count += 1
                await self.perform_trigger(message, trigger, search[1])
                return

    async def safe_regex_search(self, guild: discord.Guild, trigger: Trigger, content: str):
        """
            Mostly safe regex search to prevent reDOS from user defined regex patterns

            This works by running the regex pattern inside a process pool defined at the
            cog level and then checking that process in the default executor to keep
            things asynchronous. If the process takes too long to complete we log a
            warning and remove the trigger from trying to run again.
        """
        if await self.config.guild(guild).bypass():
            log.debug(f"Bypassing safe regex in guild {guild.name} ({guild.id})")
            return (True, trigger.regex.findall(content))
        try:
            process = self.re_pool.apply_async(trigger.regex.findall, (content,))
            task = functools.partial(process.get, timeout=1)
            new_task = self.bot.loop.run_in_executor(None, task)
            search = await asyncio.wait_for(new_task, timeout=5)
        except TimeoutError:
            error_msg = (
                "ReTrigger: regex process took too long. Removing from memory "
                f"{guild.name} ({guild.id}) Author {trigger.author} "
                f"Offending regex `{trigger.regex.pattern}` Name: {trigger.name}"
            )
            log.warning(error_msg)
            return (False, [])
            # we certainly don't want to be performing multiple triggers if this happens
        except asyncio.TimeoutError:
            error_msg = (
                "ReTrigger: regex asyncio timed out."
                f"{guild.name} ({guild.id}) Author {trigger.author} "
                f"Offending regex `{trigger.regex.pattern}` Name: {trigger.name}"
            )
            log.warning(error_msg)
            return (False, [])
        except Exception:
            log.error(
                f"ReTrigger encountered an error {trigger.name} {trigger.regex} in {guild.name} {guild.id}",
                exc_info=True,
            )
            return (True, [])
        else:
            return (True, search)

    async def perform_trigger(self, message: discord.Message, trigger: Trigger, find: List[str]):

        guild: discord.Guild = cast(discord.Guild, message.guild)
        channel: discord.TextChannel = cast(discord.TextChannel, message.channel)
        author: discord.Member = cast(discord.Member, message.author)
        reason = _("Trigger response: {trigger}").format(trigger=trigger.name)
        own_permissions = channel.permissions_for(guild.me)

        error_in = _(
            "Retrigger encountered an error in {guild} with trigger {trigger} "
        ).format(guild=guild.name, trigger=trigger.name)
        if "resize" in trigger.response_type and own_permissions.attach_files and ALLOW_RESIZE:
            await channel.trigger_typing()
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            task = functools.partial(self.resize_image, size=len(find[0]) - 3, image=path)
            new_task = self.bot.loop.run_in_executor(None, task)
            try:
                file: discord.File = await asyncio.wait_for(new_task, timeout=60)
            except asyncio.TimeoutError:
                pass
            try:
                await channel.send(file=file)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "text" in trigger.response_type and own_permissions.send_messages:
            await channel.trigger_typing()
            if trigger.multi_payload:
                text_response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "text")
            else:
                text_response = str(trigger.text)
            response = await self.convert_parms(message, text_response, trigger.regex)
            try:
                await channel.send(response)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "randtext" in trigger.response_type and own_permissions.send_messages:
            await channel.trigger_typing()
            rand_text_response: str = random.choice(trigger.text)
            crand_text_response = await self.convert_parms(
                message, rand_text_response, trigger.regex
            )
            try:
                await channel.send(crand_text_response)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "dm" in trigger.response_type:
            if trigger.multi_payload:
                dm_response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "dm")
            else:
                dm_response = str(trigger.text)
            response = await self.convert_parms(message, dm_response, trigger.regex)
            try:
                await author.send(response)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "dmme" in trigger.response_type:
            if trigger.multi_payload:
                dm_response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "dmme")
            else:
                dm_response = str(trigger.text)
            response = await self.convert_parms(message, dm_response, trigger.regex)
            try:
                trigger_author = await self.bot.fetch_user(trigger.author)
            except AttributeError:
                trigger_author = await self.bot.get_user_info(trigger.author)
            except Exception:
                log.error(error_in, exc_info=True)
            try:
                await trigger_author.send(response)
            except discord.errors.Forbidden:
                await self.remove_trigger_from_cache(guild, trigger)
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "react" in trigger.response_type and own_permissions.add_reactions:
            if trigger.multi_payload:
                react_response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "react"
                ]
            else:
                react_response = trigger.text
            for emoji in react_response:
                try:
                    await message.add_reaction(emoji)
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    log.debug(error_in, exc_info=True)
                except Exception:
                    log.error(error_in, exc_info=True)
        if "ban" in trigger.response_type and own_permissions.ban_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally ban the bot owner
                # or try to ban the guild owner
                return
            if guild.me.top_role > author.top_role:
                try:
                    await author.ban(reason=reason, delete_message_days=0)
                    if await self.config.guild(guild).ban_logs():
                        await self.modlog_action(message, trigger, find, _("Banned"))
                except discord.errors.Forbidden:
                    log.debug(error_in, exc_info=True)
                except Exception:
                    log.error(error_in, exc_info=True)
        if "kick" in trigger.response_type and own_permissions.kick_members:
            if await self.bot.is_owner(author) or author == guild.owner:
                # Don't want to accidentally kick the bot owner
                # or try to kick the guild owner
                return
            if guild.me.top_role > author.top_role:
                try:
                    await author.kick(reason=reason)
                    if await self.config.guild(guild).kick_logs():
                        await self.modlog_action(message, trigger, find, _("Kicked"))
                except discord.errors.Forbidden:
                    log.debug(error_in, exc_info=True)
                except Exception:
                    log.error(error_in, exc_info=True)
        if "image" in trigger.response_type and own_permissions.attach_files:
            await channel.trigger_typing()
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            file = discord.File(path)
            image_text_response = trigger.text
            if image_text_response:
                image_text_response = await self.convert_parms(
                    message, image_text_response, trigger.regex
                )
            try:
                await channel.send(image_text_response, file=file)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "randimage" in trigger.response_type and own_permissions.attach_files:
            await channel.trigger_typing()
            image = random.choice(trigger.image)
            path = str(cog_data_path(self)) + f"/{guild.id}/{image}"
            file = discord.File(path)
            rimage_text_response = trigger.text
            if rimage_text_response:
                text_response = await self.convert_parms(message, response, trigger.regex)
            try:
                await channel.send(rimage_text_response, file=file)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)
        if "command" in trigger.response_type:
            if trigger.multi_payload:
                command_response = [t[1] for t in trigger.multi_payload if t[0] == "command"]
                for command in command_response:
                    command = await self.convert_parms(message, command, trigger.regex)
                    msg = copy(message)
                    prefix_list = await self.bot.command_prefix(self.bot, message)
                    msg.content = prefix_list[0] + command
                    self.bot.dispatch("message", msg)
            else:
                msg = copy(message)
                command = await self.convert_parms(message, str(trigger.text), trigger.regex)
                prefix_list = await self.bot.command_prefix(self.bot, message)
                msg.content = prefix_list[0] + command
                self.bot.dispatch("message", msg)
        if "add_role" in trigger.response_type and own_permissions.manage_roles:

            if trigger.multi_payload:
                add_response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "add_role"
                ]
            else:
                add_response = trigger.text
            for roles in add_response:
                add_role: discord.Role = cast(discord.Role, guild.get_role(roles))
                if not add_role:
                    continue
                try:
                    await author.add_roles(add_role, reason=reason)
                    if await self.config.guild(guild).add_role_logs():
                        await self.modlog_action(message, trigger, find, _("Added Role"))
                except discord.errors.Forbidden:
                    log.debug(error_in, exc_info=True)
                except Exception:
                    log.error(error_in, exc_info=True)
        if "remove_role" in trigger.response_type and own_permissions.manage_roles:

            if trigger.multi_payload:
                rem_response = [
                    r for t in trigger.multi_payload for r in t[1:] if t[0] == "remove_role"
                ]
            else:
                rem_response = trigger.text
            for roles in rem_response:
                rem_role: discord.Role = cast(discord.Role, guild.get_role(roles))
                if not rem_role:
                    continue
                try:
                    await author.remove_roles(rem_role, reason=reason)
                    if await self.config.guild(guild).remove_role_logs():
                        await self.modlog_action(message, trigger, find, _("Removed Role"))
                except discord.errors.Forbidden:
                    log.debug(error_in, exc_info=True)
                except Exception:
                    log.error(error_in, exc_info=True)
        if "delete" in trigger.response_type and own_permissions.manage_messages:
            log.debug("Performing delete trigger")
            try:
                await message.delete()
                if await self.config.guild(guild).filter_logs():
                    await self.modlog_action(message, trigger, find, _("Deleted Message"))
            except discord.errors.NotFound:
                log.debug(error_in, exc_info=True)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)

        if "mock" in trigger.response_type:
            if trigger.multi_payload:
                mock_response = [t[1] for t in trigger.multi_payload if t[0] == "mock"]
                for command in mock_response:
                    command = await self.convert_parms(message, command, trigger.regex)
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
                command = await self.convert_parms(message, str(trigger.text), trigger.regex)
                if not mocker:
                    return  # We'll exit early if the author isn't on the server anymore
                msg.author = mocker
                prefix_list = await self.bot.command_prefix(self.bot, message)
                msg.content = prefix_list[0] + command
                self.bot.dispatch("message", msg)

    async def convert_parms(
        self, message: discord.Message, raw_response: str, regex_replace: Pattern
    ) -> str:
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/customcom/customcom.py
        ctx = await self.bot.get_context(message)
        results = RE_CTX.findall(raw_response)
        for result in results:
            param = await self.transform_parameter(result, ctx.message)
            raw_response = raw_response.replace("{" + result + "}", param)
        results = RE_POS.findall(raw_response)
        if results:
            for result in results:
                search = regex_replace.search(message.content)
                if not search:
                    continue
                try:
                    arg = search.group(int(result[0]))
                    raw_response = raw_response.replace("{" + result[0] + "}", arg)
                except IndexError:
                    log.error("Regex pattern is too broad and no matched groups were found.")
                    continue
                except Exception:
                    log.error(
                        f"Retrigger Encountered an error converting parameters", exc_info=True
                    )
                    continue
        return raw_response
        # await ctx.send(raw_response)

    @staticmethod
    async def transform_parameter(result: str, message: discord.Message) -> str:
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

    async def modlog_action(
        self, message: discord.Message, trigger: Trigger, find: List[str], action: str
    ):
        modlogs = await self.config.guild(message.guild).modlog()
        guild: discord.Guild = cast(discord.Guild, message.guild)
        author: discord.Member = cast(discord.Member, message.author)
        channel: discord.TextChannel = cast(discord.TextChannel, message.channel)
        if modlogs:
            if modlogs == "default":
                # We'll get the default modlog channel setup
                # with modlogset
                try:
                    modlog_channel = await modlog.get_modlog_channel(guild)
                except Exception:
                    log.error("Error getting modlog channel", exc_info=True)
                    # Return early if no modlog channel exists
                    return
            else:
                modlog_channel = guild.get_channel(modlogs)
                if modlog_channel is None:
                    return
            infomessage = f"{author} - {action}\n"
            embed = discord.Embed(
                description=message.content,
                colour=discord.Colour.dark_red(),
                timestamp=datetime.now(),
            )
            found_regex = humanize_list(find)
            embed.add_field(name=_("Channel"), value=channel.mention)
            embed.add_field(name=_("Trigger Name"), value=trigger.name)
            if found_regex:
                embed.add_field(name=_("Found Triggers"), value=found_regex[:1024])
            embed.add_field(name=_("Trigger author"), value=f"<@{trigger.author}>")
            if message.attachments:
                files = ", ".join(a.filename for a in message.attachments)
                embed.add_field(name=_("Attachments"), value=files)
            embed.set_footer(text=_("User ID: ") + str(message.author.id))
            embed.set_author(name=infomessage, icon_url=author.avatar_url)
            try:
                if modlog_channel.permissions_for(guild.me).embed_links:
                    await modlog_channel.send(embed=embed)
                else:
                    infomessage += _(
                        "Channel: {channel}\n"
                        "Trigger Name: {trigger}\n"
                        "Trigger author: {t_author}\n"
                        "Found Triggers: {found_triggers}\n"
                    ).format(
                        channel=channel.mention,
                        trigger=trigger.name,
                        t_author=f"{trigger.author}",
                        found_triggers=humanize_list(find)[:1024],
                    )
                    msg = escape(
                        infomessage.replace("@&", ""), mass_mentions=True, formatting=True
                    )
                    await modlog_channel.send(msg)
            except Exception:
                log.error("Error posting modlog message", exc_info=True)
                pass

    async def remove_trigger(self, guild: discord.Guild, trigger_name: str) -> bool:
        """Returns true or false if the trigger was removed"""
        async with self.config.guild(guild).trigger_list() as trigger_list:
            for triggers in trigger_list:
                # trigger = Trigger.from_json(trigger_list[triggers])
                if triggers == trigger_name:
                    if trigger_list[triggers]["image"] is not None:
                        image = trigger_list[triggers]["image"]
                        if isinstance(image, list):
                            for i in image:
                                path = str(cog_data_path(self)) + f"/{guild.id}/{i}"
                                try:
                                    os.remove(path)
                                except Exception:
                                    msg = _("Error deleting saved image in {guild}").format(
                                        guild=guild.id
                                    )
                                    log.error(msg, exc_info=True)
                        else:
                            path = str(cog_data_path(self)) + f"/{guild.id}/{image}"
                            try:
                                os.remove(path)
                            except Exception:
                                msg = _("Error deleting saved image in {guild}").format(
                                    guild=guild.id
                                )
                                log.error(msg, exc_info=True)
                    del trigger_list[triggers]
                    return True
        return False
