import asyncio
import functools
import multiprocessing as mp
import os
import random
import string
from copy import copy
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, cast

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import commands, modlog
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape, humanize_list

from .abc import ReTriggerMixin
from .converters import Trigger, TriggerResponse
from .message import ReTriggerMessage

try:
    import pytesseract

    ALLOW_OCR = True
except ImportError:
    ALLOW_OCR = False

try:
    from PIL import Image, ImageSequence

    ALLOW_RESIZE = True
except ImportError:
    ALLOW_RESIZE = False
    ALLOW_OCR = False


try:
    import regex as re
except ImportError:
    import re


log = getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

RE_CTX: re.Pattern = re.compile(r"{([^}]+)\}")
RE_POS: re.Pattern = re.compile(r"{((\d+)[^.}]*(\.[^:}]+)?[^}]*)\}")
LINK_REGEX: re.Pattern = re.compile(
    r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|mp3|mp4|webp))", flags=re.I
)
IMAGE_REGEX: re.Pattern = re.compile(
    r"(?:(?:https?):\/\/)?[\w\/\-?=%.]+\.(?:png|jpg|jpeg|webp)+", flags=re.I
)


class TriggerHandler(ReTriggerMixin):
    """
    Handles all processing of triggers
    """

    async def remove_trigger_from_cache(self, guild_id: int, trigger: Trigger) -> None:
        try:
            del self.triggers[guild_id][trigger.name]
        except KeyError:
            # it will get removed on the next reload of the cog
            log.info("Trigger can't be removed :blobthinking:")

    async def can_edit(self, author: discord.Member, trigger: Trigger) -> bool:
        """Chekcs to see if the member is allowed to edit the trigger"""
        if trigger.author == author.id:
            return True
        if await self.bot.is_owner(author):
            return True
        if author is author.guild.owner and TriggerResponse.mock not in trigger.response_type:
            return True
        return False

    async def can_enable_or_disable(self, author: discord.Member, trigger: Trigger) -> bool:
        if TriggerResponse.mock in trigger.response_type:
            # explicitly disallow anyone but the trigger author to
            # enable or disable mocked command triggers
            return await self.can_edit(author, trigger)
        if await self.can_edit(author, trigger):
            # Allow all who previously could edit to also still do this
            return True
        # finally if they could not previously edit compare permissions
        # to see if they have all required permissions from the triggers
        # response types
        return author.guild_permissions >= trigger.get_permissions()

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
                break
            if "exit" in msg.content.lower():
                break
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

    async def check_is_command(self, message: discord.Message) -> bool:
        """Checks if the message is a bot command"""
        prefix_list = await self.bot.get_valid_prefixes(message.guild)
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
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        if getattr(message, "retrigger", False):
            log.trace("A ReTrigger dispatched message, ignoring.")
            return
        await self.check_triggers(message, False)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if "content" not in payload.data and "embeds" not in payload.data:
            return
        if "guild_id" not in payload.data:
            return
        guild = self.bot.get_guild(int(payload.data["guild_id"]))
        if not guild:
            return
        if guild.id not in self.triggers:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if not any(t.check_edits for t in self.triggers[guild.id].values()):
            # log.debug(f"No triggers in {guild=} have check_edits enabled")
            return
        if "bot" in payload.data.get("author", {}):
            return
        channel = guild.get_channel(int(payload.data["channel_id"]))
        if payload.cached_message is not None:
            message = payload.cached_message
        else:
            message = discord.Message(state=channel._state, channel=channel, data=payload.data)
        if message.author.bot:
            # somehow we got a bot through the previous check :thonk:
            return
        await self.check_triggers(message, True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if await self.bot.cog_disabled_in_guild(self, thread.guild):
            return
        if thread.guild.id not in self.triggers:
            return
        if not thread.permissions_for(thread.guild.me).manage_threads:
            return
        try:
            await self.check_triggers_thread(thread)
        except Exception:
            log.exception("Error checking thread title")

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        if await self.bot.cog_disabled_in_guild(self, before.guild):
            return
        if before.guild.id not in self.triggers:
            return
        if not before.permissions_for(before.guild.me).manage_threads:
            return
        if before.name != after.name:
            try:
                await self.check_triggers_thread(after, edit=True)
            except Exception:
                log.exception("Error checking thread title change")

    async def check_triggers_thread(self, thread: discord.Thread, *, edit: bool = False):
        guild = thread.guild
        for trigger in self.triggers[guild.id].values():
            if not trigger.enabled:
                continue
            if TriggerResponse.delete not in trigger.response_type:
                continue
            if not trigger.read_thread_title:
                continue
            if edit and not trigger.check_edits:
                continue
            allowed_trigger = await trigger.check_bw_list(author=thread.owner, channel=thread)
            is_auto_mod = any(r.is_automod for r in trigger.response_type)
            is_mod = False
            if thread.owner is not None:
                is_mod = await self.is_mod_or_admin(thread.owner)
            if not allowed_trigger:
                log.debug(
                    "ReTrigger: %r is immune from allowlist/blocklist %r", thread.owner, trigger
                )
                continue
            if allowed_trigger and (is_auto_mod and is_mod):
                log.debug(
                    "ReTrigger: %r is immune from automated actions %r", thread.owner, trigger
                )
                continue

            search = await self.safe_regex_search(guild, trigger, thread.name)
            if not search[0]:
                trigger.enabled = False
                return
            elif search[0] and search[1] != []:
                trigger.count += 1
                log.debug(
                    "ReTrigger: thread from %r triggered for deletion with %r",
                    thread.owner,
                    trigger,
                )
                try:
                    log.debug("Deleting thread %r", thread)
                    await thread.delete()
                    if await self.config.guild(guild).filter_logs():
                        await self.modlog_action(thread, trigger, search[1], _("Deleted Thread"))
                except discord.errors.NotFound:
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except discord.errors.Forbidden:
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                return

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
        for trigger in self.triggers[guild.id].values():
            if not trigger.enabled:
                continue
            if edit and not trigger.check_edits:
                continue
            if trigger.chance:
                if random.randint(0, trigger.chance) != 0:
                    continue
            if trigger.nsfw and not channel.is_nsfw():
                continue

            allowed_trigger = await trigger.check_bw_list(author=author, channel=channel)
            is_auto_mod = any(r.is_automod for r in trigger.response_type)
            if not allowed_trigger:
                log.debug("ReTrigger: %r is immune from allowlist/blocklist %r", author, trigger)
                continue
            if allowed_trigger and (is_auto_mod and is_mod):
                log.debug("ReTrigger: %r is immune from automated actions %r", author, trigger)
                continue
            # log.debug(f"Checking trigger {trigger.name}")
            if is_command and not trigger.ignore_commands:
                log.debug(
                    "ReTrigger: %r is ignored because they used a command %r", author, trigger
                )
                continue

            if any(r.is_automod for r in trigger.response_type):
                if await self.bot.is_automod_immune(message):
                    log.debug("ReTrigger: %r is immune from automated actions %r", author, trigger)
                    continue
            if TriggerResponse.delete in trigger.response_type:
                if channel_perms.manage_messages or is_mod:
                    log.debug(
                        "ReTrigger: Delete is ignored because %r has manage messages permission %r",
                        author,
                        trigger,
                    )
                    continue
            elif TriggerResponse.kick in trigger.response_type:
                if channel_perms.kick_members or is_mod:
                    log.debug(
                        "ReTrigger: Kick is ignored because %r has kick permissions %r",
                        author,
                        trigger,
                    )
                    continue
            elif TriggerResponse.ban in trigger.response_type:
                if channel_perms.ban_members or is_mod:
                    log.debug(
                        "ReTrigger: Ban is ignored because %r has ban permissions %r",
                        author,
                        trigger,
                    )
                    continue
            elif any(r.is_role_change for r in trigger.response_type):
                if channel_perms.manage_roles or is_mod:
                    log.debug(
                        "ReTrigger: role change is ignored because %r has mange roles permissions %r",
                        author,
                        trigger,
                    )
            else:
                if blocked:
                    log.debug(
                        "ReTrigger: Channel is ignored or %r is blacklisted %r",
                        author,
                        trigger,
                    )
                    continue

            content = ""
            content += message.content
            if trigger.read_filenames and message.attachments:
                content += " " + " ".join(f.filename for f in message.attachments)

            if trigger.ocr_search and ALLOW_OCR:
                content += await self.get_image_text(message)
            if trigger.read_embeds and len(message.embeds) > 0:
                content += "\n".join(
                    self.convert_embed_to_string(embed, index)
                    for index, embed in enumerate(message.embeds)
                )
            if trigger.regex is None:
                log.debug(
                    "ReTrigger: Trigger %r must have invalid regex.",
                    trigger,
                )
                trigger.disable()
                continue
            # log.debug("content = %s message.content = %s", content, message.content)
            search = await self.safe_regex_search(guild, trigger, content)
            if not search[0]:
                trigger.enabled = False
                return
            elif search[0] and search[1] != []:
                if await trigger.check_cooldown(message):
                    continue
                trigger.count += 1
                log.debug("ReTrigger: message from %r triggered %r", author, trigger)
                await self.perform_trigger(message, trigger, search[1])
                return

    @staticmethod
    def convert_embed_to_string(embed: discord.Embed, embed_index: int = 0) -> str:
        embed_dict = embed.to_dict()
        flattened_embed_dict = {}
        field_blacklist = ["type", "color", "proxy_url", "height", "width", "proxy_icon_url"]
        for field, value in embed_dict.items():
            if field in field_blacklist:
                continue
            if isinstance(value, dict):
                for subfield in value:
                    if subfield in field_blacklist:
                        continue
                    flattened_embed_dict[f"{field.lower()}-{subfield.lower()}"] = value[subfield]
            elif isinstance(value, list):
                for field_index, embedfields in enumerate(value):
                    emfield_name = embedfields["name"].lower()
                    flattened_embed_dict[
                        f"{field.lower()}-{field_index}-{emfield_name}"
                    ] = embedfields["value"]
            else:
                flattened_embed_dict[field.lower()] = value
        return "\n".join(
            f"embed-{embed_index}-{field}: {value}"
            for field, value in flattened_embed_dict.items()
        )

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
            loop = asyncio.get_running_loop()
            new_task = loop.run_in_executor(None, task)
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
            loop = asyncio.get_running_loop()
            new_task = loop.run_in_executor(None, task)
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
            loop = asyncio.get_running_loop()
            new_task = loop.run_in_executor(None, task)
            search = await asyncio.wait_for(new_task, timeout=self.trigger_timeout + 5)
        except mp.TimeoutError:
            error_msg = (
                "ReTrigger: regex process took too long. Removing from memory "
                "%s (%s) Author %s "
                "Offending regex `%s` Name: %s"
            )
            log.warning(
                error_msg,
                guild.name,
                guild.id,
                trigger.author,
                trigger.regex.pattern,
                trigger.name,
            )
            return (False, [])
            # we certainly don't want to be performing multiple triggers if this happens
        except asyncio.TimeoutError:
            error_msg = (
                "ReTrigger: regex asyncio timed out."
                "%s (%s) Author %s "
                "Offending regex `%s` Name: %s"
            )
            log.warning(
                error_msg,
                guild.name,
                guild.id,
                trigger.author,
                trigger.regex.pattern,
                trigger.name,
            )
            return (False, [])
        except ValueError:
            return (False, [])
        except Exception:
            log.error(
                "ReTrigger encountered an error %s %s in %s %s",
                trigger.name,
                trigger.regex,
                guild.name,
                guild.id,
                exc_info=True,
            )
            return (True, [])
        else:
            return (True, search)

    async def perform_trigger(
        self, message: discord.Message, trigger: Trigger, find: List[str]
    ) -> None:
        guild: discord.Guild = cast(discord.Guild, message.guild)
        channel = message.channel
        author: discord.Member = cast(discord.Member, message.author)
        reason = _("Trigger response: {trigger}").format(trigger=trigger.name)
        own_permissions = channel.permissions_for(guild.me)
        # is_thread_message = getattr(message, "is_thread", False)
        if isinstance(channel, discord.TextChannel):
            # currently only text channels are capable of creating threads from
            # a message being sent. Forum Chanels can't have sent messages by
            # design and therefore we can't automatically make a thread in them.
            if (
                trigger.thread.public is not None
                and own_permissions.send_messages_in_threads
                and trigger.thread.name
            ):
                thread_name = await self.convert_parms(message, trigger.thread.name, trigger, find)
                if trigger.thread.public is True and own_permissions.create_public_threads:
                    channel = await channel.create_thread(
                        name=thread_name[:100], message=message, reason=reason
                    )
                elif trigger.thread.public is False and own_permissions.create_private_threads:
                    channel = await channel.create_thread(
                        name=thread_name[:100], invitable=trigger.thread.invitable, reason=reason
                    )
                    if trigger.thread.invitable or (
                        trigger.thread.invitable is False and own_permissions.manage_messages
                    ):
                        try:
                            await channel.add_user(author)
                        except Exception:
                            log.exception(
                                "ReTrigger encountered an error adding a user to a private thread."
                            )
        if (
            TriggerResponse.resize in trigger.response_type
            and own_permissions.attach_files
            and ALLOW_RESIZE
        ):
            await channel.typing()
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            if path.lower().endswith(".gif"):
                task = functools.partial(self.resize_gif, size=len(find[0]) - 3, image=path)
            else:
                task = functools.partial(self.resize_image, size=len(find[0]) - 3, image=path)
            loop = asyncio.get_running_loop()
            new_task = loop.run_in_executor(None, task)
            try:
                file: discord.File = await asyncio.wait_for(new_task, timeout=60)
            except asyncio.TimeoutError:
                pass
            try:
                await channel.send(file=file)
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.rename in trigger.response_type and own_permissions.manage_nicknames:
            # rename above text so the mention shows the renamed user name
            if author == guild.owner:
                # Don't want to accidentally kick the bot owner
                # or try to kick the guild owner
                return
            if guild.me.top_role > author.top_role:
                if trigger.multi_payload:
                    text_response = "\n".join(
                        str(t.response)
                        for t in trigger.multi_payload
                        if t.action is TriggerResponse.rename
                    )
                else:
                    text_response = str(trigger.text)
                response = await self.convert_parms(message, text_response, trigger, find)
                if response and not channel.permissions_for(author).mention_everyone:
                    response = escape(response, mass_mentions=True)
                try:
                    await author.edit(nick=response[:32], reason=reason)
                except discord.errors.Forbidden:
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )

        if TriggerResponse.publish in trigger.response_type and own_permissions.manage_messages:
            if channel.is_news():
                try:
                    await message.publish()
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )

        if TriggerResponse.text in trigger.response_type and own_permissions.send_messages:
            await channel.typing()
            if trigger.multi_payload:
                text_response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.text
                )
            else:
                text_response = str(trigger.text)
            response = await self.convert_parms(message, text_response, trigger, find)
            if response and not channel.permissions_for(author).mention_everyone:
                response = escape(response, mass_mentions=True)
            kwargs = {}
            if trigger.reply:
                kwargs["reference"] = message
            try:
                await channel.send(
                    response,
                    tts=trigger.tts,
                    delete_after=trigger.delete_after,
                    allowed_mentions=trigger.allowed_mentions(),
                    **kwargs,
                )
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.randtext in trigger.response_type and own_permissions.send_messages:
            await channel.typing()
            rand_text_response: str = random.choice(trigger.text)
            crand_text_response = await self.convert_parms(
                message, rand_text_response, trigger, find
            )
            if crand_text_response and not channel.permissions_for(author).mention_everyone:
                crand_text_response = escape(crand_text_response, mass_mentions=True)
            kwargs = {}
            if trigger.reply:
                kwargs["reference"] = message
            try:
                await channel.send(
                    crand_text_response,
                    tts=trigger.tts,
                    delete_after=trigger.delete_after,
                    allowed_mentions=trigger.allowed_mentions(),
                    **kwargs,
                )
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.image in trigger.response_type and own_permissions.attach_files:
            await channel.typing()
            path = str(cog_data_path(self)) + f"/{guild.id}/{trigger.image}"
            file = discord.File(path)
            image_text_response = trigger.text
            if image_text_response:
                image_text_response = await self.convert_parms(
                    message, image_text_response, trigger, find
                )
            if image_text_response and not channel.permissions_for(author).mention_everyone:
                image_text_response = escape(image_text_response, mass_mentions=True)
            kwargs = {}
            if trigger.reply:
                kwargs["reference"] = message
            try:
                await channel.send(
                    image_text_response,
                    tts=trigger.tts,
                    file=file,
                    delete_after=trigger.delete_after,
                    allowed_mentions=trigger.allowed_mentions(),
                    **kwargs,
                )
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.randimage in trigger.response_type and own_permissions.attach_files:
            await channel.typing()
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
            kwargs = {}
            if trigger.reply:
                kwargs["reference"] = message
            try:
                await channel.send(
                    rimage_text_response,
                    tts=trigger.tts,
                    file=file,
                    delete_after=trigger.delete_after,
                    allowed_mentions=trigger.allowed_mentions(),
                    **kwargs,
                )
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.dm in trigger.response_type:
            if trigger.multi_payload:
                dm_response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.dm
                )
            else:
                dm_response = str(trigger.text)
            response = await self.convert_parms(message, dm_response, trigger, find)
            try:
                await author.send(response, allowed_mentions=trigger.allowed_mentions())
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.dmme in trigger.response_type:
            if trigger.multi_payload:
                dm_response = "\n".join(
                    str(t.response)
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.dmme
                )
            else:
                dm_response = str(trigger.text)
            response = await self.convert_parms(message, dm_response, trigger, find)
            trigger_author = self.bot.get_user(trigger.author)
            if not trigger_author:
                try:
                    trigger_author = await self.bot.fetch_user(trigger.author)
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
            try:
                await trigger_author.send(response, allowed_mentions=trigger.allowed_mentions())
            except discord.errors.Forbidden:
                trigger.enabled = False
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

        if TriggerResponse.react in trigger.response_type and own_permissions.add_reactions:
            for emoji in trigger.reactions:
                try:
                    await message.add_reaction(emoji)
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )

        if TriggerResponse.add_role in trigger.response_type and own_permissions.manage_roles:
            for roles in trigger.add_roles:
                add_role: discord.Role = cast(discord.Role, guild.get_role(roles))
                if not add_role:
                    continue
                try:
                    await author.add_roles(add_role, reason=reason)
                    if await self.config.guild(guild).add_role_logs():
                        await self.modlog_action(message, trigger, find, _("Added Role"))
                except discord.errors.Forbidden:
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )

        if TriggerResponse.remove_role in trigger.response_type and own_permissions.manage_roles:
            for roles in trigger.remove_roles:
                rem_role: discord.Role = cast(discord.Role, guild.get_role(roles))
                if not rem_role:
                    continue
                try:
                    await author.remove_roles(rem_role, reason=reason)
                    if await self.config.guild(guild).remove_role_logs():
                        await self.modlog_action(message, trigger, find, _("Removed Role"))
                except discord.errors.Forbidden:
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )

        if TriggerResponse.kick in trigger.response_type and own_permissions.kick_members:
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
                    log.debug(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )
                except Exception:
                    log.exception(
                        "Retrigger encountered an error in %r with trigger %r", guild, trigger
                    )

        if TriggerResponse.ban in trigger.response_type and own_permissions.ban_members:
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
                    log.debug("Discord forbidden error when banning %s", author, exc_info=True)
                except Exception:
                    log.error("Exception when banning %s", author, exc_info=True)

        if TriggerResponse.command in trigger.response_type:
            if trigger.multi_payload:
                command_response = [
                    t.response
                    for t in trigger.multi_payload
                    if t.action is TriggerResponse.command
                ]
                for command in command_response:
                    command = await self.convert_parms(message, command, trigger, find)
                    msg = copy(message)
                    prefix_list = await self.bot.get_valid_prefixes(message.guild)
                    msg.content = prefix_list[0] + command
                    msg = ReTriggerMessage(message=msg)
                    self.bot.dispatch("message", msg)
            else:
                msg = copy(message)
                command = await self.convert_parms(message, str(trigger.text), trigger, find)
                prefix_list = await self.bot.get_valid_prefixes(message.guild)
                msg.content = prefix_list[0] + command
                msg = ReTriggerMessage(message=msg)
                self.bot.dispatch("message", msg)
        if TriggerResponse.mock in trigger.response_type:
            if trigger.multi_payload:
                mock_response = [
                    t.response for t in trigger.multi_payload if t.action is TriggerResponse.mock
                ]
                for command in mock_response:
                    command = await self.convert_parms(message, command, trigger, find)
                    msg = copy(message)
                    mocker = guild.get_member(trigger.author)
                    if not mocker:
                        return
                    msg.author = mocker
                    prefix_list = await self.bot.get_valid_prefixes(message.guild)
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
                prefix_list = await self.bot.get_valid_prefixes(message.guild)
                msg.content = prefix_list[0] + command
                msg = ReTriggerMessage(message=msg)
                self.bot.dispatch("message", msg)

        if TriggerResponse.delete in trigger.response_type and own_permissions.manage_messages:
            # this should be last since we can accidentally delete the context when needed
            log.debug("Performing delete trigger")
            try:
                await message.delete()
                if await self.config.guild(guild).filter_logs():
                    await self.modlog_action(message, trigger, find, _("Deleted Message"))
            except discord.errors.NotFound:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except discord.errors.Forbidden:
                log.debug("Retrigger encountered an error in %r with trigger %r", guild, trigger)
            except Exception:
                log.exception(
                    "Retrigger encountered an error in %r with trigger %r", guild, trigger
                )

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
                content = message.content
                if trigger.read_filenames and message.attachments:
                    content = (
                        message.content + " " + " ".join(f.filename for f in message.attachments)
                    )
                search = trigger.regex.search(content)
                if not search:
                    continue
                try:
                    arg = search.group(int(result[0]))
                    raw_response = raw_response.replace("{" + result[0] + "}", arg)
                except IndexError:
                    log.error("Regex pattern is too broad and no matched groups were found.")
                    continue
                except Exception:
                    log.exception("Retrigger encountered an error with trigger %r", trigger)
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
        if message.attachments:
            objects["attachment"] = message.attachments[0]
            # we can only reasonably support one attachment at a time
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
        self,
        message_or_thread: Union[discord.Message, discord.Thread],
        trigger: Trigger,
        find: List[str],
        action: str,
    ) -> None:
        guild: discord.Guild = cast(discord.Guild, message_or_thread.guild)
        if isinstance(message_or_thread, discord.Message):
            author = message_or_thread.author
            content = message_or_thread.content
            attachments = message_or_thread.attachments
            channel: discord.TextChannel = cast(discord.TextChannel, message_or_thread.channel)
        else:
            author = message_or_thread.owner
            content = message_or_thread.name
            attachments = []
            channel: discord.TextChannel = cast(discord.TextChannel, message_or_thread.parent)

        modlogs = await self.config.guild(guild).modlog()
        # author: discord.Member = cast(discord.Member, author)
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
                description=content,
                colour=discord.Colour.dark_red(),
                timestamp=datetime.now(tz=timezone.utc),
            )
            found_regex = humanize_list(find)
            embed.add_field(name=_("Channel"), value=channel.mention)
            embed.add_field(name=_("Trigger Name"), value=trigger.name)
            if found_regex:
                embed.add_field(name=_("Found Triggers"), value=found_regex[:1024])
            embed.add_field(name=_("Trigger author"), value=f"<@{trigger.author}>")
            if attachments:
                files = ", ".join(a.filename for a in attachments)
                embed.add_field(name=_("Attachments"), value=files)
            embed.set_footer(text=_("User ID: ") + str(author.id))
            embed.set_author(name=infomessage, icon_url=author.display_avatar)
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

    async def remove_trigger(self, guild_id: int, trigger_name: str) -> bool:
        """Returns true or false if the trigger was removed"""
        async with self.config.guild_from_id(int(guild_id)).trigger_list() as trigger_list:
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
                                    log.error(
                                        "Error deleting saved image in %s", guild_id, exc_info=True
                                    )
                        else:
                            path = str(cog_data_path(self)) + f"/{guild_id}/{image}"
                            try:
                                os.remove(path)
                            except Exception:
                                log.error(
                                    "Error deleting saved image in %s", guild_id, exc_info=True
                                )
                    del trigger_list[triggers]
                    del self.triggers[guild_id][trigger_name]
                    return True
        return False
