import logging
import re
from datetime import datetime, timedelta, timezone
from random import choice as rand_choice
from typing import List, Optional, Pattern, Union, cast

import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.utils.common_filters import filter_mass_mentions

RE_CTX: Pattern = re.compile(r"{([^}]+)\}")
RE_POS: Pattern = re.compile(r"{((\d+)[^.}]*(\.[^:}]+)?[^}]*)\}")
_ = Translator("Welcome", __file__)
log = logging.getLogger("red.trusty-cogs.Welcome")


@cog_i18n(_)
class Events:
    def __init__(self):
        self.bot: Red
        self.config: Config
        self.joined: dict
        self.today_count: dict

    @staticmethod
    def transform_arg(result: str, attr: str, obj: Union[discord.Guild, discord.Member]) -> str:
        attr = attr[1:]  # strip initial dot
        if not attr:
            return str(obj)
        raw_result = "{" + result + "}"
        # forbid private members and nested attr lookups
        if attr.startswith("_") or "." in attr:
            return raw_result
        return str(getattr(obj, attr, raw_result))

    async def convert_parms(
        self,
        member: Union[discord.Member, List[discord.Member]],
        guild: discord.Guild,
        msg: str,
        is_welcome: bool,
    ) -> str:
        results = RE_POS.findall(msg)
        raw_response = msg
        user_count = self.today_count[guild.id] if guild.id in self.today_count else 1
        raw_response = raw_response.replace("{count}", str(user_count))
        has_filter = self.bot.get_cog("Filter")
        filter_setting = await self.config.guild(guild).FILTER_SETTING()
        if filter_setting is None:
            filter_setting = "[Redacted]"
        if isinstance(member, list):
            username = humanize_list(member)
        else:
            username = str(member)
        for result in results:
            if int(result[1]) == 1:
                param = self.transform_arg(result[0], result[2], guild)
            elif int(result[1]) == 0:
                if isinstance(member, discord.Member):
                    param = self.transform_arg(result[0], result[2], member)
                else:
                    params = []
                    for m in member:
                        params.append(self.transform_arg(result[0], result[2], m))
                    if len(params) > 1:
                        param = humanize_list(params)
                    else:
                        param = params[0]
            raw_response = raw_response.replace("{" + result[0] + "}", param)
        if has_filter:
            bad_name = await has_filter.filter_hits(username, guild)
            if bad_name:
                for word in bad_name:
                    raw_response = re.sub(rf"(?i){word}", filter_setting, raw_response)
                    if isinstance(member, list):
                        raw_response = re.sub(
                            "|".join(m.mention for m in member), filter_setting, raw_response
                        )
                    else:
                        raw_response = re.sub(
                            rf"(?i){member.mention}", filter_setting, raw_response
                        )
        if await self.config.guild(guild).JOINED_TODAY() and is_welcome:
            raw_response = _("{raw_response}\n\n{count} users joined today!").format(
                raw_response=raw_response, count=user_count
            )
        return raw_response

    async def make_embed(
        self,
        member: Union[discord.Member, List[discord.Member]],
        guild: discord.Guild,
        msg: str,
        is_welcome: bool,
    ) -> discord.Embed:
        EMBED_DATA = await self.config.guild(guild).EMBED_DATA()
        converted_msg = await self.convert_parms(member, guild, msg, is_welcome)
        has_filter = self.bot.get_cog("Filter")
        username = str(member)
        if has_filter:
            bad_words = await has_filter.filter_hits(username, guild)
            if bad_words:
                for word in bad_words:
                    username = username.replace(word, "[Redacted]")
        em = discord.Embed(description=converted_msg)
        if EMBED_DATA["colour"]:
            em.colour = EMBED_DATA["colour"]
        if EMBED_DATA["title"]:
            em.title = await self.convert_parms(member, guild, EMBED_DATA["title"], False)
        if EMBED_DATA["footer"]:
            em.set_footer(
                text=await self.convert_parms(member, guild, EMBED_DATA["footer"], False)
            )
        if EMBED_DATA["thumbnail"]:
            url = EMBED_DATA["thumbnail"]
            if url == "guild":
                url = str(guild.icon.url)
            elif url == "splash":
                url = str(guild.splash_url)
            elif url == "avatar" and isinstance(member, discord.Member):
                url = str(member.avatar.url)
            em.set_thumbnail(url=url)
        if EMBED_DATA["image"] or EMBED_DATA["image_goodbye"]:
            url = ""
            if EMBED_DATA["image"] and is_welcome:
                url = EMBED_DATA["image"]
            if EMBED_DATA["image_goodbye"] and not is_welcome:
                url = EMBED_DATA["image_goodbye"]
            if url == "guild":
                url = str(guild.icon.url)
            elif url == "splash":
                url = str(guild.splash_url)
            elif url == "avatar" and isinstance(member, discord.Member):
                url = str(member.avatar.url)
            em.set_image(url=url)
        if EMBED_DATA["icon_url"]:
            url = EMBED_DATA["icon_url"]
            if url == "guild":
                url = str(guild.icon.url)
            elif url == "splash":
                url = str(guild.splash_url)
            elif url == "avatar" and isinstance(member, discord.Member):
                url = str(member.avatar.url)
            em.set_author(name=username, icon_url=url)
        if EMBED_DATA["timestamp"]:
            em.timestamp = datetime.now(timezone.utc)
        if EMBED_DATA["author"] and isinstance(member, discord.Member):
            em.set_author(name=username, icon_url=str(member.avatar.url))
        return em

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if not await self.config.guild(guild).ON():
            return
        if guild is None:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if member.bot:
            return await self.bot_welcome(member, guild)
        td = timedelta(days=await self.config.guild(guild).MINIMUM_DAYS())
        if (datetime.now(timezone.utc) - member.created_at) <= td:
            log.info(_("Member joined with an account newer than required days."))
            return
        has_filter = self.bot.get_cog("Filter")
        filter_setting = await self.config.guild(guild).FILTER_SETTING()
        if has_filter and filter_setting is None:
            if await has_filter.filter_hits(member.name, guild):
                log.info(_("Member joined with a bad username."))
                return

        if datetime.now(timezone.utc).date() > self.today_count["now"].date():
            self.today_count = {"now": datetime.now(timezone.utc)}
            # reset the daily count when a user joins the following day or when the cog is reloaded

        if guild.id not in self.today_count:
            self.today_count[guild.id] = 1
        else:
            self.today_count[guild.id] += 1

        if await self.config.guild(guild).GROUPED():
            if guild.id not in self.joined:
                self.joined[guild.id] = []
            log.debug("member joined")
            if member not in self.joined[guild.id]:
                return self.joined[guild.id].append(member)
        await self.send_member_join(member, guild)

    async def bot_welcome(self, member: discord.Member, guild: discord.Guild):
        bot_welcome = await self.config.guild(guild).BOTS_MSG()
        bot_role = await self.config.guild(guild).BOTS_ROLE()
        msg = bot_welcome or rand_choice(await self.config.guild(guild).GREETING())
        channel = await self.get_welcome_channel(member, guild)
        is_embed = await self.config.guild(guild).EMBED()
        if version_info >= VersionInfo.from_str("3.4.0"):
            mentions = await self.config.guild(guild).MENTIONS()
            sanitize = {"allowed_mentions": discord.AllowedMentions(**mentions)}
        else:
            sanitize = {}

        if bot_role:
            try:
                role = cast(discord.abc.Snowflake, guild.get_role(bot_role))
                await member.add_roles(role, reason=_("Automatic Bot Role"))
            except Exception:
                log.error(
                    _("welcome.py: unable to add  a role. ") + f"{bot_role} {member}",
                    exc_info=True,
                )
            else:
                log.debug(
                    _("welcome.py: added ") + str(role) + _(" role to ") + _("bot, ") + str(member)
                )
        if bot_welcome:
            # finally, welcome them
            if not channel:
                return
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, msg, False)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    await channel.send(member.mention, embed=em, **sanitize)
                else:
                    await channel.send(embed=em)
            else:
                await channel.send(
                    await self.convert_parms(member, guild, bot_welcome, False), **sanitize
                )

    async def get_welcome_channel(
        self, member: Union[discord.Member, List[discord.Member]], guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        # grab the welcome channel
        # guild_settings = await self.config.guild(guild).guild_settings()
        c_id = await self.config.guild(guild).CHANNEL()
        channel = cast(discord.TextChannel, guild.get_channel(c_id))
        only_whisper = await self.config.guild(guild).WHISPER() is True
        if channel is None:  # complain even if only whisper
            if not only_whisper:
                log.info(
                    _("welcome.py: Channel not found. It was most likely deleted. User joined: ")
                    + str(member)
                )
                return None
            else:
                # We will not complain here since some people only want the bot to whisper at times
                return None
        # we can stop here

        if not channel.permissions_for(guild.me).send_messages:
            log.info(_("Permissions Error. User that joined: ") + "{0}".format(member))
            log.info(
                _("Bot doesn't have permissions to send messages to ")
                + "{0.name}'s #{1.name} channel".format(guild, channel)
            )
            return None
        return channel

    async def send_member_join(
        self, member: Union[discord.Member, List[discord.Member]], guild: discord.Guild
    ) -> None:
        only_whisper = await self.config.guild(guild).WHISPER() is True
        channel = await self.get_welcome_channel(member, guild)
        msg = rand_choice(await self.config.guild(guild).GREETING())
        is_embed = await self.config.guild(guild).EMBED()
        delete_after = await self.config.guild(guild).DELETE_AFTER_GREETING()
        save_msg = None
        if version_info >= VersionInfo.from_str("3.4.0"):
            mentions = await self.config.guild(guild).MENTIONS()
            sanitize = {"allowed_mentions": discord.AllowedMentions(**mentions)}
        else:
            sanitize = {}

        if await self.config.guild(guild).DELETE_PREVIOUS_GREETING():
            old_id = await self.config.guild(guild).LAST_GREETING()
            if channel is not None and old_id is not None:
                old_msg = None
                try:
                    old_msg = await channel.fetch_message(old_id)
                except discord.errors.NotFound:
                    pass
                except discord.errors.Forbidden:
                    await self.config.guild(guild).DELETE_PREVIOUS_GREETING.set(False)
                if old_msg:
                    await old_msg.delete()
        # whisper the user if needed
        if not await self.config.guild(guild).GROUPED():
            if await self.config.guild(guild).WHISPER():
                try:
                    if is_embed:
                        em = await self.make_embed(member, guild, msg, True)
                        if await self.config.guild(guild).EMBED_DATA.mention():
                            await member.send(member.mention, embed=em)  # type: ignore
                        else:
                            await member.send(embed=em)  # type: ignore
                    else:
                        await member.send(await self.convert_parms(member, guild, msg, False))  # type: ignore
                except discord.errors.Forbidden:
                    log.info(
                        _(
                            "welcome.py: unable to whisper a user. Probably "
                            "doesn't want to be PM'd"
                        )
                        + str(member)
                    )
                except Exception:
                    log.error("error sending member join message", exc_info=True)
        if only_whisper:
            return
        if not channel:
            return
        if is_embed and channel.permissions_for(guild.me).embed_links:
            em = await self.make_embed(member, guild, msg, True)
            if await self.config.guild(guild).EMBED_DATA.mention():
                if await self.config.guild(guild).GROUPED():
                    members = cast(List[discord.Member], member)
                    save_msg = await channel.send(
                        humanize_list([m.mention for m in members]),
                        embed=em,
                        delete_after=delete_after,
                        **sanitize,
                    )
                else:
                    member = cast(discord.Member, member)
                    save_msg = await channel.send(
                        str(member.mention),
                        embed=em,
                        delete_after=delete_after,
                        **sanitize,
                    )
            else:
                save_msg = await channel.send(
                    embed=em,
                    delete_after=delete_after,
                    **sanitize,
                )
        else:
            save_msg = await channel.send(
                await self.convert_parms(member, guild, msg, True),
                delete_after=delete_after,
                **sanitize,
            )
        if save_msg is not None:
            await self.config.guild(guild).LAST_GREETING.set(save_msg.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        if guild is None:
            return

        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if await self.config.guild(guild).GROUPED():
            if guild.id not in self.joined:
                self.joined[guild.id] = []
            if member in self.joined[guild.id]:
                self.joined[guild.id].remove(member)

        if not await self.config.guild(guild).LEAVE_ON():
            return

        bot_welcome = member.bot and await self.config.guild(guild).BOTS_MSG()
        msg = bot_welcome or rand_choice(await self.config.guild(guild).GOODBYE())
        is_embed = await self.config.guild(guild).EMBED()
        delete_after = await self.config.guild(guild).DELETE_AFTER_GOODBYE()
        save_msg = None
        if version_info >= VersionInfo.from_str("3.4.0"):
            mentions = await self.config.guild(guild).GOODBYE_MENTIONS()
            sanitize = {"allowed_mentions": discord.AllowedMentions(**mentions)}
        else:
            sanitize = {}

        # grab the welcome channel
        # guild_settings = await self.config.guild(guild).guild_settings()
        channel = self.bot.get_channel(await self.config.guild(guild).LEAVE_CHANNEL())
        if channel is None:  # complain even if only whisper
            log.info(
                _("welcome.py: Channel not found in {guild}. It was most likely deleted.").format(
                    guild=guild
                )
            )
            return
        # we can stop here
        if await self.config.guild(guild).DELETE_PREVIOUS_GOODBYE():
            old_id = await self.config.guild(guild).LAST_GOODBYE()
            if channel is not None and old_id is not None:
                old_msg = None
                try:
                    old_msg = await channel.fetch_message(old_id)
                except discord.errors.NotFound:
                    log.debug("Message not found for deletion.")
                    pass
                except discord.errors.Forbidden:
                    await self.config.guild(guild).DELETE_PREVIOUS_GOODBYE.set(False)
                if old_msg:
                    await old_msg.delete()

        if not channel.permissions_for(guild.me).send_messages:
            log.info(_("Permissions Error in {guild}"))
            return
        elif not member.bot:
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, msg, False)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    save_msg = await channel.send(
                        member.mention, embed=em, delete_after=delete_after, **sanitize
                    )
                else:
                    save_msg = await channel.send(embed=em, delete_after=delete_after)
            else:
                save_msg = await channel.send(
                    await self.convert_parms(member, guild, msg, False),
                    delete_after=delete_after,
                    **sanitize,
                )
        if save_msg is not None:
            await self.config.guild(guild).LAST_GOODBYE.set(save_msg.id)

    async def send_testing_msg(
        self, ctx: commands.Context, bot: bool = False, msg: str = None, leave: bool = False
    ) -> None:
        # log.info(leave)
        default_greeting = "Welcome {0.name} to {1.name}!"
        default_goodbye = "See you later {0.name}!"
        default_bot_msg = "Hello {0.name}, fellow bot!"
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).get_raw()
        # log.info(guild_settings)
        if version_info >= VersionInfo.from_str("3.4.0"):
            mentions = await self.config.guild(guild).MENTIONS()
            sanitize = {"allowed_mentions": discord.AllowedMentions(**mentions)}
        else:
            sanitize = {}
        channel = guild.get_channel(guild_settings["CHANNEL"])
        if leave:
            channel = guild.get_channel(guild_settings["LEAVE_CHANNEL"])
        rand_msg = msg or rand_choice(guild_settings["GREETING"])
        if leave:
            rand_msg = msg or rand_choice(guild_settings["GOODBYE"])
        if bot:
            rand_msg = guild_settings["BOTS_MSG"]
        if rand_msg is None and msg is None:
            rand_msg = default_greeting
        if rand_msg is None and bot:
            rand_msg = default_bot_msg
        if rand_msg is None and leave:
            rand_msg = default_goodbye
        is_welcome = not leave
        is_embed = guild_settings["EMBED"]
        member = ctx.message.author
        whisper_settings = guild_settings["WHISPER"]
        if channel is None and whisper_settings not in ["BOTH", True]:
            msg = _("I can't find the specified channel. It might have been deleted.")
            await ctx.send(msg)
            return
        if channel is None:
            await ctx.send(_("`Sending a testing message to ") + "` DM", **sanitize)
        else:
            await ctx.send(
                _("`Sending a testing message to ") + "`{0.mention}".format(channel), **sanitize
            )
        if not bot and guild_settings["WHISPER"]:
            if is_embed:
                em = await self.make_embed(member, guild, rand_msg, is_welcome)
                await ctx.author.send(embed=em, delete_after=60)
            else:
                await ctx.author.send(
                    await self.convert_parms(member, guild, rand_msg, is_welcome),
                    delete_after=60,
                    **sanitize,
                )
            if guild_settings["WHISPER"] != "BOTH":
                return
        if bot or whisper_settings is not True:
            if not channel:
                return
            if guild_settings["GROUPED"]:
                member = [ctx.author, ctx.me]
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, rand_msg, is_welcome)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    if guild_settings["GROUPED"]:
                        await channel.send(
                            humanize_list([m.mention for m in member]), embed=em, delete_after=60
                        )
                    else:
                        await channel.send(member.mention, embed=em, delete_after=60, **sanitize)
                else:
                    await channel.send(embed=em, delete_after=60, **sanitize)
            else:
                await channel.send(
                    await self.convert_parms(member, guild, rand_msg, is_welcome),
                    delete_after=60,
                    **sanitize,
                )
