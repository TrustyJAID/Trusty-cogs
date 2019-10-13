import re
import logging

import discord

from random import choice as rand_choice
from datetime import datetime
from typing import List, Union, Pattern

from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify, humanize_list
from redbot.core.i18n import Translator, cog_i18n


RE_CTX: Pattern = re.compile(r"{([^}]+)\}")
RE_POS: Pattern = re.compile(r"{((\d+)[^.}]*(\.[^:}]+)?[^}]*)\}")
_ = Translator("Welcome", __file__)
log = logging.getLogger("red.trusty-cogs.Welcome")
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class Events:
    def __init__(self):
        self.bot: Red
        self.config: Config
        self.joined: dict

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

    async def convert_parms(self, member, guild, msg):
        results = RE_POS.findall(msg)
        log.debug(results)
        raw_response = msg
        for result in results:
            log.debug(result)
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
            log.debug(param)
            raw_response = raw_response.replace("{" + result[0] + "}", param)
        return raw_response

    async def make_embed(
        self,
        member: Union[discord.Member, List[discord.Member]],
        guild: discord.Guild,
        msg: str,
    ):
        EMBED_DATA = await self.config.guild(guild).EMBED_DATA()
        converted_msg = await self.convert_parms(member, guild, msg)
        em = discord.Embed(description=converted_msg)
        if isinstance(member, discord.Member):
            em.set_thumbnail(url=member.avatar_url_as(format="png"))
        if EMBED_DATA["colour"]:
            em.colour = EMBED_DATA["colour"]
        if EMBED_DATA["title"]:
            em.title = await self.convert_parms(member, guild, EMBED_DATA["title"])
        if EMBED_DATA["footer"]:
            em.set_footer(text=await self.convert_parms(member, guild, EMBED_DATA["footer"]))
        if EMBED_DATA["thumbnail"]:
            url = EMBED_DATA["thumbnail"]
            if url == "guild":
                url = guild.icon_url
            elif url == "splash":
                url = guild.splash_url
            elif url == "avatar" and isinstance(member, discord.Member):
                url = member.avatar_url
            em.set_thumbnail(url=url)
        if EMBED_DATA["image"]:
            url = EMBED_DATA["image"]
            if url == "guild":
                url = guild.icon_url
            elif url == "splash":
                url = guild.splash_url
            elif url == "avatar" and isinstance(member, discord.Member):
                url = member.avatar_url
            em.set_image(url=url)
        if EMBED_DATA["icon_url"]:
            url = EMBED_DATA["icon_url"]
            if url == "guild":
                url = guild.icon_url
            elif url == "splash":
                url = guild.splash_url
            elif url == "avatar" and isinstance(member, discord.Member):
                url = member.avatar_url
            em.set_author(name=str(member), icon_url=url)
        if EMBED_DATA["timestamp"]:
            em.timestamp = datetime.utcnow()
        if EMBED_DATA["author"] and isinstance(member, discord.Member):
            em.set_author(name=str(member), icon_url=member.avatar_url)
        return em

    @listener()
    async def on_member_join(self, member):
        guild = member.guild
        if not await self.config.guild(guild).ON():
            return
        if guild is None:
            return
        if member.bot:
            return await self.bot_welcome(member, guild)
        if guild.id not in self.joined:
            self.joined[guild.id] = []
        if await self.config.guild(guild).GROUPED() and member not in self.joined[guild.id]:
            log.debug("member joined")
            return self.joined[guild.id].append(member)
        await self.send_member_join(member, guild)

    async def bot_welcome(self, member, guild):
        bot_welcome = await self.config.guild(guild).BOTS_MSG()
        bot_role = await self.config.guild(guild).BOTS_ROLE()
        msg = bot_welcome or rand_choice(await self.config.guild(guild).GREETING())
        channel = await self.get_welcome_channel(member, guild)
        is_embed = await self.config.guild(guild).EMBED()
        if bot_role:
            try:
                role = guild.get_role(bot_role)
                await member.add_roles(role)
            except Exception:
                log.error(
                    _("welcome.py: unable to add  a role. ") + f"{bot_role} {member}", exc_info=True
                )
            else:
                log.debug(
                    _("welcome.py: added ") + str(role) + _(" role to ") + _("bot, ") + str(member)
                )
        if bot_welcome:
            # finally, welcome them
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, msg)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    await channel.send(member.mention, embed=em)
                else:
                    await channel.send(embed=em)
            else:
                await channel.send(await self.convert_parms(member, guild, bot_welcome))

    async def get_welcome_channel(self, member, guild):
        # grab the welcome channel
        # guild_settings = await self.config.guild(guild).guild_settings()
        channel = guild.get_channel(await self.config.guild(guild).CHANNEL())
        only_whisper = await self.config.guild(guild).WHISPER() is True
        if channel is None:  # complain even if only whisper
            if not only_whisper:
                log.info(
                    _("welcome.py: Channel not found. It was most likely deleted. User joined: ")
                    + str(member)
                )
                return
            else:
                # We will not complain here since some people only want the bot to whisper at times
                return
        # we can stop here

        if not guild.me.permissions_in(channel).send_messages:
            log.info(_("Permissions Error. User that joined: ") + "{0}".format(member))
            log.info(
                _("Bot doesn't have permissions to send messages to ")
                + "{0.name}'s #{1.name} channel".format(guild, channel)
            )
            return
        return channel

    async def send_member_join(self, member, guild):
        only_whisper = await self.config.guild(guild).WHISPER() is True
        channel = await self.get_welcome_channel(member, guild)
        msg = rand_choice(await self.config.guild(guild).GREETING())
        is_embed = await self.config.guild(guild).EMBED()

        # whisper the user if needed
        if not await self.config.guild(guild).GROUPED():
            if await self.config.guild(guild).WHISPER():
                try:
                    if is_embed:
                        em = await self.make_embed(member, guild, msg)
                        if await self.config.guild(guild).EMBED_DATA.mention():
                            await member.send(member.mention, embed=em)
                        else:
                            await member.send(embed=em)
                    else:
                        await member.send(await self.convert_parms(member, guild, msg))
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
        if is_embed and channel.permissions_for(guild.me).embed_links:
            em = await self.make_embed(member, guild, msg)
            if await self.config.guild(guild).EMBED_DATA.mention():
                if await self.config.guild(guild).GROUPED():
                    await channel.send(
                        humanize_list([m.mention for m in member]), embed=em, delete_after=60
                    )
                else:
                    await channel.send(member.mention, embed=em)
            else:
                await channel.send(embed=em)
        else:
            await channel.send(await self.convert_parms(member, guild, msg))

    @listener()
    async def on_member_remove(self, member):
        guild = member.guild
        if not await self.config.guild(guild).LEAVE_ON():
            return
        if guild is None:
            return

        if guild.id not in self.joined:
            self.joined[guild.id] = []
        if await self.config.guild(guild).GROUPED() and member in self.joined[guild.id]:
            self.joined[guild.id].remove(member)
            return

        bot_welcome = member.bot and await self.config.guild(guild).BOTS_MSG()
        msg = bot_welcome or rand_choice(await self.config.guild(guild).GOODBYE())
        is_embed = await self.config.guild(guild).EMBED()

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

        if not channel.permissions_for(guild.me).send_messages:
            log.info(_("Permissions Error in {guild}"))
            return
        elif not member.bot:
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, msg)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    await channel.send(member.mention, embed=em)
                else:
                    await channel.send(embed=em)
            else:
                await channel.send(await self.convert_parms(member, guild, msg))

    def speak_permissions(self, guild, channel):
        if channel is None:
            return False
        return guild.me.permissions_in(channel)

    async def send_testing_msg(self, ctx, bot=False, msg=None, leave=False):
        # log.info(leave)
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).get_raw()
        # log.info(guild_settings)
        channel = guild.get_channel(guild_settings["CHANNEL"])
        if leave:
            channel = guild.get_channel(guild_settings["LEAVE_CHANNEL"])
        rand_msg = msg or rand_choice(guild_settings["GREETING"])
        if leave:
            rand_msg = msg or rand_choice(guild_settings["GOODBYE"])
        if bot:
            rand_msg = guild_settings["BOTS_MSG"]
        is_embed = guild_settings["EMBED"]
        member = ctx.message.author
        whisper_settings = guild_settings["WHISPER"]
        if channel is None and whisper_settings not in ["BOTH", True]:
            msg = _("I can't find the specified channel. It might have been deleted.")
            await ctx.send(msg)
            return
        if channel is None:
            await ctx.send(_("`Sending a testing message to ") + "` DM")
        else:
            await ctx.send(_("`Sending a testing message to ") + "`{0.mention}".format(channel))
        if not bot and guild_settings["WHISPER"]:
            if is_embed:
                em = await self.make_embed(member, guild, rand_msg)
                await ctx.author.send(embed=em, delete_after=60)
            else:
                await ctx.author.send(await self.convert_parms(member, guild, rand_msg), delete_after=60)
            if guild_settings["WHISPER"] != "BOTH":
                return
        if bot or whisper_settings is not True:
            if not channel:
                return
            if guild_settings["GROUPED"]:
                member = [ctx.author, ctx.me]
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, rand_msg)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    if guild_settings["GROUPED"]:
                        await channel.send(
                            humanize_list([m.mention for m in member]), embed=em, delete_after=60
                        )
                    else:
                        await channel.send(member.mention, embed=em, delete_after=60)
                else:
                    await channel.send(embed=em, delete_after=60)
            else:
                await channel.send(
                    await self.convert_parms(member, guild, rand_msg), delete_after=60
                )
