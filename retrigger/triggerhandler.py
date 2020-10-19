import asyncio
import functools
import logging
import os
import random
import string
from copy import copy
from datetime import datetime
from io import BytesIO
from multiprocessing import TimeoutError
from multiprocessing.pool import Pool
from typing import Any, Dict, List, Literal, Pattern, Tuple, cast, Optional

import aiohttp
import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, commands, modlog
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape, humanize_list

from .converters import Trigger
from .message import ReTriggerMessage

try:
    from PIL import Image, ImageSequence

    try:
        import pytesseract

        ALLOW_OCR = True
    except ImportError:
        ALLOW_OCR = False

    ALLOW_RESIZE = True
except ImportError:
    ALLOW_RESIZE = False
    ALLOW_OCR = False


try:
    import regex as re
except ImportError:
    import re


log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

RE_CTX: Pattern = re.compile(r"{([^}]+)\}")
RE_POS: Pattern = re.compile(r"{((\d+)[^.}]*(\.[^:}]+)?[^}]*)\}")
LINK_REGEX: Pattern = re.compile(
    r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|mp3|mp4))", flags=re.I
)
IMAGE_REGEX: Pattern = re.compile(
    r"(?:(?:https?):\/\/)?[\w\/\-?=%.]+\.(?:png|jpg|jpeg)+", flags=re.I
)


class TriggerHandler:
    """
    Handles all processing of triggers
    """

    config: Config
    bot: Red
    re_pool: Pool
    triggers: Dict[int, List[Trigger]]
    trigger_timeout: int
    ALLOW_RESIZE: bool = ALLOW_RESIZE
    ALLOW_OCR: bool = ALLOW_OCR

    def __init__(self, *args):
        self.config: Config
        self.bot: Red
        self.re_pool: Pool
        self.triggers: Dict[int, List[Trigger]]
        self.trigger_timeout: int
        self.ALLOW_RESIZE = ALLOW_RESIZE
        self.ALLOW_OCR = ALLOW_OCR

    async def remove_trigger_from_cache(self, guild_id: int, trigger: Trigger) -> None:
        try:
            for t in self.triggers[guild_id]:
                if t.name == trigger.name:
                    self.triggers[guild_id].remove(t)
        except ValueError:
            # it will get removed on the next reload of the cog
            log.info("Trigger can't be removed :blobthinking:")
            pass

    async def can_edit(self, author: discord.Member, trigger: Trigger) -> bool:
        """Chekcs to see if the member is allowed to edit the trigger"""
        if trigger.author == author.id:
            return True
        if await self.bot.is_owner(author):
            return True
        if author is author.guild.owner and "mock" not in trigger.response_type:
            return True

    async def check_bw_list(self, trigger: Trigger, message: discord.Message) -> bool:
        can_run = True
        author: discord.Member = cast(discord.Member, message.author)
        channel: discord.TextChannel = cast(discord.TextChannel, message.channel)
        if trigger.whitelist:
            can_run = False
            if channel.id in trigger.whitelist:
                can_run = True
            if channel.category_id and channel.category_id in trigger.whitelist:
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
            if channel.id in trigger.blacklist:
                can_run = False
            if channel.category_id and channel.category_id in trigger.blacklist:
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

    async def make_guild_folder(self, directory) -> None:
        if not directory.is_dir():
            log.info("Creating guild folder")
            directory.mkdir(exist_ok=True, parents=True)

    async def save_image_location(self, image_url: str, guild: discord.Guild) -> Optional[str]:
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

    async def wait_for_image(self, ctx: commands.Context) -> Optional[discord.Message]:
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

    async def wait_for_multiple_responses(self, ctx: commands.Context) -> List[discord.Message]:
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

    def resize_gif(self, size: int, image: str) -> discord.File:
        img_list = []
        with Image.open(image) as im:
            if size <= 0:
                size = 1
            length, width = (16 * size, 16 * size)
            start_list = [frame.copy() for frame in ImageSequence.Iterator(im)]
            for frame in start_list:
                frame.thumbnail((length, width), Image.ANTIALIAS)
                img_list.append(frame)
        byte_array = BytesIO()
        img_list[0].save(
            byte_array, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0
        )
        byte_array.seek(0)
        return discord.File(byte_array, filename="resize.gif")

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if message.author.bot:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, message.guild):
                return
        if getattr(message, "retrigger", False):
            log.debug("A ReTrigger dispatched message, ignoring.")
            return
        await self.check_triggers(message, False)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if "content" not in payload.data:
            return
        if "guild_id" not in payload.data:
            return
        if "bot" in payload.data["author"]:
            return
        channel = self.bot.get_channel(int(payload.data["channel_id"]))
        try:
            message = await channel.fetch_message(int(payload.data["id"]))
        except (discord.errors.Forbidden, discord.errors.NotFound):
            log.debug(
                _("I don't have permission to read channel history or cannot find the message.")
            )
            return
        except Exception:
            log.info("Could not find channel or message", exc_info=True)
            # If we can't find the channel ignore it
            return
        if message.author.bot:
            # somehow we got a bot through the previous check :thonk:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, message.guild):
                return
        await self.check_triggers(message, True)

    async def check_triggers(self, message: discord.Message, edit: bool) -> None:
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
        author: Optional[discord.Member] = guild.get_member(message.author.id)
        if not author:
            return

        blocked = not await self.bot.allowed_by_whitelist_blacklist(author)
        channel_perms = channel.permissions_for(author)
        is_command = await self.check_is_command(message)
        is_mod = await self.is_mod_or_admin(author)

        autoimmune = getattr(self.bot, "is_automod_immune", None)
        auto_mod = ["delete", "kick", "ban", "add_role", "remove_role"]
        for trigger in self.triggers[guild.id]:
            if not trigger.enabled:
                continue
            if edit and trigger.ignore_edits:
                continue
            if trigger.chance:
                if random.randint(0, trigger.chance) != 0:
                    continue

            allowed_trigger = await self.check_bw_list(trigger, message)
            is_auto_mod = trigger.response_type in auto_mod
            if not allowed_trigger:
                continue
            if allowed_trigger and (is_auto_mod and is_mod):
                continue
            # log.debug(f"Checking trigger {trigger.name}")
            if is_command and not trigger.ignore_commands:
                continue

            if any(t for t in trigger.response_type if t in auto_mod):
                if await autoimmune(message):
                    print_msg = _("ReTrigger: {author} is immune from automated actions ").format(
                        author=author
                    )
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
                if blocked:
                    print_msg = _(
                        "ReTrigger: Channel is ignored or {author} is blacklisted "
                    ).format(author=author)
                    log.debug(print_msg + trigger.name)
                    continue
            content = message.content
            if trigger.read_filenames and message.attachments:
                content = message.content + " " + " ".join(f.filename for f in message.attachments)

            if trigger.ocr_search and ALLOW_OCR:
                content += await self.get_image_text(message)

            search = await self.safe_regex_search(guild, trigger, content)
            if not search[0]:
                trigger.enabled = False
                return
            elif search[0] and search[1] != []:
                if await self.check_trigger_cooldown(message, trigger):
                    continue
                trigger.count += 1
                await self.perform_trigger(message, trigger, search[1])
                return

    async def get_image_text(self, message: discord.Message) -> str:
        """
        This function is built to asynchronously search images for text using pytesseract

        It takes a discord message and searches for valid
        image links and all attachments on the message
        then runs them through pytesseract. All contents
        from pytesseract are returned as a string.
        """
        content = " "
        for attachment in message.attachments:
            temp = BytesIO()
            await attachment.save(temp)
            task = functools.partial(pytesseract.image_to_string, Image.open(temp))
            new_task = self.bot.loop.run_in_executor(None, task)
            try:
                content += await asyncio.wait_for(new_task, timeout=5)
            except asyncio.TimeoutError:
                pass
        good_image_url = IMAGE_REGEX.findall(message.content)
        for link in good_image_url:
            temp = BytesIO()
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    data = await resp.read()
                    temp.write(data)
                    temp.seek(0)
            task = functools.partial(pytesseract.image_to_string, Image.open(temp))
            new_task = self.bot.loop.run_in_executor(None, task)
            try:
                content += await asyncio.wait_for(new_task, timeout=5)
            except asyncio.TimeoutError:
                pass
        return content

    async def safe_regex_search(
        self, guild: discord.Guild, trigger: Trigger, content: str
    ) -> Tuple[bool, list]:
        """
        Mostly safe regex search to prevent reDOS from user defined regex patterns

        This works by running the regex pattern inside a process pool defined at the
        cog level and then checking that process in the default executor to keep
        things asynchronous. If the process takes too long to complete we log a
        warning and remove the trigger from trying to run again.
        """
        if await self.config.guild(guild).bypass():
            # log.debug(f"Bypassing safe regex in guild {guild.name} ({guild.id})")
            return (True, trigger.regex.findall(content))
        try:
            process = self.re_pool.apply_async(trigger.regex.findall, (content,))
            task = functools.partial(process.get, timeout=self.trigger_timeout)
            new_task = self.bot.loop.run_in_executor(None, task)
            search = await asyncio.wait_for(new_task, timeout=self.trigger_timeout + 5)
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

    async def perform_trigger(
        self, message: discord.Message, trigger: Trigger, find: List[str]
    ) -> None:

        guild: discord.Guild = cast(discord.Guild, message.guild)
        channel: discord.TextChannel = cast(discord.TextChannel, message.channel)
        author: discord.Member = cast(discord.Member, message.author)
        reason = _("Trigger response: {trigger}").format(trigger=trigger.name)
        own_permissions = channel.permissions_for(guild.me)

        error_in = _("Retrigger encountered an error in {guild} with trigger {trigger} ").format(
            guild=guild.name, trigger=trigger.name
        )
        if "resize" in trigger.response_type and own_permissions.attach_files and ALLOW_RESIZE:
            await channel.trigger_typing()
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            if path.lower().endswith(".gif"):
                task = functools.partial(self.resize_gif, size=len(find[0]) - 3, image=path)
            else:
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

        if "rename" in trigger.response_type and own_permissions.manage_nicknames:
            # rename above text so the mention shows the renamed user name
            if author == guild.owner:
                # Don't want to accidentally kick the bot owner
                # or try to kick the guild owner
                return
            if guild.me.top_role > author.top_role:
                if trigger.multi_payload:
                    text_response = "\n".join(
                        t[1] for t in trigger.multi_payload if t[0] == "rename"
                    )
                else:
                    text_response = str(trigger.text)
                response = await self.convert_parms(message, text_response, trigger, find)
                if response and not channel.permissions_for(author).mention_everyone:
                    response = escape(response, mass_mentions=True)
                try:
                    await author.edit(nick=response[:32], reason=reason)
                except discord.errors.Forbidden:
                    log.debug(error_in, exc_info=True)
                except Exception:
                    log.error(error_in, exc_info=True)

        if "publish" in trigger.response_type and own_permissions.manage_messages:
            if channel.is_news():
                try:
                    await message.publish()
                except Exception:
                    log.exception(error_in)

        if "text" in trigger.response_type and own_permissions.send_messages:
            await channel.trigger_typing()
            if trigger.multi_payload:
                text_response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "text")
            else:
                text_response = str(trigger.text)
            response = await self.convert_parms(message, text_response, trigger, find)
            if response and not channel.permissions_for(author).mention_everyone:
                response = escape(response, mass_mentions=True)
            try:
                await channel.send(response, delete_after=trigger.delete_after)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)

        if "randtext" in trigger.response_type and own_permissions.send_messages:
            await channel.trigger_typing()
            rand_text_response: str = random.choice(trigger.text)
            crand_text_response = await self.convert_parms(
                message, rand_text_response, trigger, find
            )
            if crand_text_response and not channel.permissions_for(author).mention_everyone:
                crand_text_response = escape(crand_text_response, mass_mentions=True)
            try:
                await channel.send(crand_text_response)
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
                    message, image_text_response, trigger, find
                )
            if image_text_response and not channel.permissions_for(author).mention_everyone:
                image_text_response = escape(image_text_response, mass_mentions=True)
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
                rimage_text_response = await self.convert_parms(
                    message, rimage_text_response, trigger, find
                )

            if rimage_text_response and not channel.permissions_for(author).mention_everyone:
                rimage_text_response = escape(rimage_text_response, mass_mentions=True)
            try:
                await channel.send(rimage_text_response, file=file)
            except discord.errors.Forbidden:
                log.debug(error_in, exc_info=True)
            except Exception:
                log.error(error_in, exc_info=True)

        if "dm" in trigger.response_type:
            if trigger.multi_payload:
                dm_response = "\n".join(t[1] for t in trigger.multi_payload if t[0] == "dm")
            else:
                dm_response = str(trigger.text)
            response = await self.convert_parms(message, dm_response, trigger, find)
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
            response = await self.convert_parms(message, dm_response, trigger, find)
            trigger_author = self.bot.get_user(trigger.author)
            if not trigger_author:
                try:
                    trigger_author = await self.bot.fetch_user(trigger.author)
                except Exception:
                    log.error(error_in, exc_info=True)
            try:
                await trigger_author.send(response)
            except discord.errors.Forbidden:
                trigger.enabled = False
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

        if "command" in trigger.response_type:
            if trigger.multi_payload:
                command_response = [t[1] for t in trigger.multi_payload if t[0] == "command"]
                for command in command_response:
                    command = await self.convert_parms(message, command, trigger, find)
                    msg = copy(message)
                    prefix_list = await self.bot.command_prefix(self.bot, message)
                    msg.content = prefix_list[0] + command
                    msg = ReTriggerMessage(message=msg)
                    self.bot.dispatch("message", msg)
            else:
                msg = copy(message)
                command = await self.convert_parms(message, str(trigger.text), trigger, find)
                prefix_list = await self.bot.command_prefix(self.bot, message)
                msg.content = prefix_list[0] + command
                msg = ReTriggerMessage(message=msg)
                self.bot.dispatch("message", msg)
        if "mock" in trigger.response_type:
            if trigger.multi_payload:
                mock_response = [t[1] for t in trigger.multi_payload if t[0] == "mock"]
                for command in mock_response:
                    command = await self.convert_parms(message, command, trigger, find)
                    msg = copy(message)
                    mocker = guild.get_member(trigger.author)
                    if not mocker:
                        return
                    msg.author = mocker
                    prefix_list = await self.bot.command_prefix(self.bot, message)
                    msg.content = prefix_list[0] + command
                    msg = ReTriggerMessage(message=msg)
                    self.bot.dispatch("message", msg)
            else:
                msg = copy(message)
                mocker = guild.get_member(trigger.author)
                command = await self.convert_parms(message, str(trigger.text), trigger, find)
                if not mocker:
                    return  # We'll exit early if the author isn't on the server anymore
                msg.author = mocker
                prefix_list = await self.bot.command_prefix(self.bot, message)
                msg.content = prefix_list[0] + command
                msg = ReTriggerMessage(message=msg)
                self.bot.dispatch("message", msg)

        if "delete" in trigger.response_type and own_permissions.manage_messages:
            # this should be last since we can accidentally delete the context when needed
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

    async def convert_parms(
        self, message: discord.Message, raw_response: str, trigger: Trigger, find: List[str]
    ) -> str:
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/customcom/customcom.py
        # ctx = await self.bot.get_context(message)
        results = RE_CTX.findall(raw_response)
        for result in results:
            param = await self.transform_parameter(result, message)
            raw_response = raw_response.replace("{" + result + "}", param)
        results = RE_POS.findall(raw_response)
        if results:
            for result in results:
                search = trigger.regex.search(message.content)
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
        raw_response = raw_response.replace("{count}", str(trigger.count))
        if hasattr(message.channel, "guild"):
            prefixes = await self.bot.get_prefix(message.channel)
            raw_response = raw_response.replace("{p}", prefixes[0])
            raw_response = raw_response.replace("{pp}", humanize_list(prefixes))
            raw_response = raw_response.replace("{nummatch}", str(len(find)))
            raw_response = raw_response.replace("{lenmatch}", str(len(max(find))))
            raw_response = raw_response.replace("{lenmessage}", str(len(message.content)))
        return raw_response
        # await ctx.send(raw_response)

    @staticmethod
    async def transform_parameter(result: str, message: discord.Message) -> str:
        """
        For security reasons only specific objects are allowed
        Internals are ignored
        """
        raw_result = "{" + result + "}"
        objects: Dict[str, Any] = {
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
    ) -> None:
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
                except RuntimeError:
                    log.debug("Error getting modlog channel", exc_info=True)
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

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            for trigger_name, trigger in data["trigger_list"].items():
                if trigger["author"] == user_id:
                    await self.remove_trigger(guild_id, trigger_name)
                    t = await Trigger.from_json(trigger)
                    await self.remove_trigger_from_cache(guild_id, t)

    async def remove_trigger(self, guild_id: int, trigger_name: str) -> bool:
        """Returns true or false if the trigger was removed"""
        async with self.config.guild_from_id(guild_id).trigger_list() as trigger_list:
            for triggers in trigger_list:
                # trigger = Trigger.from_json(trigger_list[triggers])
                if triggers == trigger_name:
                    if trigger_list[triggers]["image"] is not None:
                        image = trigger_list[triggers]["image"]
                        if isinstance(image, list):
                            for i in image:
                                path = str(cog_data_path(self)) + f"/{guild_id}/{i}"
                                try:
                                    os.remove(path)
                                except Exception:
                                    msg = _("Error deleting saved image in {guild}").format(
                                        guild=guild_id
                                    )
                                    log.error(msg, exc_info=True)
                        else:
                            path = str(cog_data_path(self)) + f"/{guild_id}/{image}"
                            try:
                                os.remove(path)
                            except Exception:
                                msg = _("Error deleting saved image in {guild}").format(
                                    guild=guild_id
                                )
                                log.error(msg, exc_info=True)
                    del trigger_list[triggers]
                    return True
        return False
