import logging

import discord

from random import choice as rand_choice
from datetime import datetime

from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import pagify
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Welcome", __file__)
log = logging.getLogger("red.Welcome")


@cog_i18n(_)
class Events:
    def __init__(self):
        self.bot: Red
        self.config: config

    async def make_embed(self, member: discord.Member, guild: discord.Guild, msg: str):
        EMBED_DATA = await self.config.guild(guild).EMBED_DATA()
        em = discord.Embed(description=msg.format(member, member.guild))
        em.set_thumbnail(url=member.avatar_url_as(format="png"))
        if EMBED_DATA["colour"]:
            em.colour = EMBED_DATA["colour"]
        if EMBED_DATA["title"]:
            em.title = EMBED_DATA["title"].format(member, member.guild)
        if EMBED_DATA["footer"]:
            em.set_footer(text=EMBED_DATA["footer"].format(member, member.guild))
        if EMBED_DATA["thumbnail"]:
            url = EMBED_DATA["thumbnail"]
            if url == "guild":
                url = guild.icon_url
            elif url == "avatar":
                url = member.avatar_url
            elif url == "splash":
                url = guild.splash_url
            em.set_thumbnail(url=url)
        if EMBED_DATA["image"]:
            url = EMBED_DATA["image"]
            if url == "guild":
                url = guild.icon_url
            elif url == "avatar":
                url = member.avatar_url
            elif url == "splash":
                url = guild.splash_url
            em.set_image(url=url)
        if EMBED_DATA["icon_url"]:
            url = EMBED_DATA["icon_url"]
            if url == "guild":
                url = guild.icon_url
            elif url == "avatar":
                url = member.avatar_url
            elif url == "splash":
                url = guild.splash_url
            em.set_author(name=str(member), icon_url=url)
        if EMBED_DATA["timestamp"]:
            em.timestamp = datetime.utcnow()
        if EMBED_DATA["author"]:
            em.set_author(name=str(member), icon_url=member.avatar_url)
        return em

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if not await self.config.guild(guild).ON():
            return
        if guild is None:
            return

        only_whisper = await self.config.guild(guild).WHISPER() is True
        bot_welcome = member.bot and await self.config.guild(guild).BOTS_MSG()
        bot_role = member.bot and await self.config.guild(guild).BOTS_ROLE()
        msg = bot_welcome or rand_choice(await self.config.guild(guild).GREETING())
        is_embed = await self.config.guild(guild).EMBED()

        # whisper the user if needed
        if not member.bot and await self.config.guild(guild).WHISPER():
            try:
                if is_embed:
                    em = await self.make_embed(member, guild, msg)
                    if await self.config.guild(guild).EMBED_DATA.mention():
                        await member.send(member.mention, embed=em)
                    else:
                        await member.send(embed=em)
                else:
                    await member.send(msg.format(member, guild))
            except:
                log.info(
                    _("welcome.py: unable to whisper a user. Probably " "doesn't want to be PM'd")
                    + str(member)
                )
        # grab the welcome channel
        # guild_settings = await self.config.guild(guild).guild_settings()
        channel = self.bot.get_channel(await self.config.guild(guild).CHANNEL())
        if channel is None:  # complain even if only whisper
            log.info(
                _("welcome.py: Channel not found. It was most " "likely deleted. User joined: ")
                + member.name
            )
            return
        # we can stop here

        if not self.speak_permissions(guild, channel.id):
            log.info(_("Permissions Error. User that joined: ") + "{0.name}".format(member))
            log.info(
                _("Bot doesn't have permissions to send messages to ")
                + "{0.name}'s #{1.name} channel".format(guild, channel)
            )
            return
        # try to add role if needed
        if bot_role:
            try:
                role = guild.get_role(bot_role)
                await member.add_roles(role)
            except Exception as e:
                log.info(e)
                log.info(_("welcome.py: unable to add  a role. ") + str(bot_role) + str(member))
            else:
                log.info(
                    _("welcome.py: added ") + str(role) + _(" role to ") + _("bot, ") + str(member)
                )

        if only_whisper and not bot_welcome:
            return
        if bot_welcome:
            # finally, welcome them
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, msg)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    await channel.send(member.mention, embed=em)
                else:
                    await channel.send(embed=em)
            else:
                await channel.send(bot_welcome.format(member, guild))
        elif not member.bot:
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, msg)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    await channel.send(member.mention, embed=em)
                else:
                    await channel.send(embed=em)
            else:
                await channel.send(msg.format(member, guild))

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        if not await self.config.guild(guild).LEAVE_ON():
            return
        if guild is None:
            return

        only_whisper = await self.config.guild(guild).WHISPER() is True
        bot_welcome = member.bot and await self.config.guild(guild).BOTS_MSG()
        bot_role = member.bot and await self.config.guild(guild).BOTS_ROLE()
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
                await channel.send(msg.format(member, guild))

    def get_welcome_channel(self, guild, guild_settings):
        try:
            return guild.get_channel(guild_settings)
        except:
            return None

    def speak_permissions(self, guild, guild_settings):
        channel = self.get_welcome_channel(guild, guild_settings)
        if channel is None:
            return False
        return guild.me.permissions_in(channel)

    async def send_testing_msg(self, ctx, bot=False, msg=None, leave=False):
        log.info(leave)
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).get_raw()
        log.info(guild_settings)
        channel = guild.get_channel(guild_settings["CHANNEL"])
        if leave:
            channel = guild.get_channel(guild_settings["LEAVE_CHANNEL"])
        if channel is None:
            return
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
                await ctx.author.send(rand_msg.format(member, guild), delete_after=60)
        if bot or whisper_settings is not True:
            if is_embed and channel.permissions_for(guild.me).embed_links:
                em = await self.make_embed(member, guild, rand_msg)
                if await self.config.guild(guild).EMBED_DATA.mention():
                    await channel.send(member.mention, embed=em, delete_after=60)
                else:
                    await channel.send(embed=em, delete_after=60)
            else:
                await channel.send(rand_msg.format(member, guild), delete_after=60)
