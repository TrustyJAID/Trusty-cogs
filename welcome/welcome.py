import discord
import datetime
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import pagify
from redbot.core.i18n import Translator, cog_i18n
from copy import deepcopy
import os
from random import choice as rand_choice
import asyncio

time_ = datetime.datetime.utcnow()

default_greeting = "Welcome {0.mention} to {1.name}!"
default_goodbye = "Goodbye {0.mention} 😦"
default_settings = {
    "GREETING": [default_greeting],
    "ON_GREETING": False,
    "CHANNEL_GREETING": None,
    "WHISPER_GREETING": False,
    "BOTS_MSG_GREETING": None,
    "BOTS_ROLE_GREETING": None,
    "EMBED_GREETING": True,
    "GOODBYE": [default_goodbye],
    "ON_GOODBYE": False,
    "CHANNEL_GOODBYE": None,
    "WHISPER_GOODBYE": False,
    "BOTS_MSG_GOODBYE": None,
    "EMBED_GOODBYE": True,
}
settings_path = "data/welcomeleave/settings.json"

_ = Translator("WelcomeLeaver", __file__)


@cog_i18n(_)
class WelcomeLeave(getattr(commands, "Cog", object)):
    """Welcomes and goodbye users to the guild.
    Rewritten from https://github.com/irdumbs/Dumb-Cogs/blob/master/welcome/welcome.py"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 144465786453)
        self.config.register_guild(**default_settings)

    @commands.group()
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def welcomeset(self, ctx):
        """Sets welcome module settings"""
        guild = ctx.message.guild
        if ctx.invoked_subcommand is None:
            guild_settings = await self.config.guild(guild).get_raw()
            setting_names = {
                "GREETING": _("Random Greeting "),
                "ON_GREETING": _("On "),
                "CHANNEL_GREETING": _("Channel "),
                "WHISPER_GREETING": _("Whisper "),
                "BOTS_MSG_GREETING": _("Bots message "),
                "BOTS_ROLE_GREETING": _("Bots role "),
                "EMBED_GREETING": _("Embeds "),
            }
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed(colour=await self.get_colour(guild))
                embed.set_author(
                    name=_("Welcome settings for ") + guild.name, icon_url=guild.icon_url
                )
                embed.description = "\n".join(g for g in guild_settings["GREETING"])
                for attr, name in setting_names.items():
                    if attr == "GREETING":
                        continue
                    if attr == "CHANNEL_GREETING":
                        chan = guild.get_channel(guild_settings["CHANNEL_GREETING"])
                        if chan is not None:
                            embed.add_field(name=name, value=chan.mention)
                        else:
                            embed.add_field(name=name, value=_("None"))
                        continue
                    if attr == "BOTS_ROLE_GREETING":
                        role = guild.get_role(guild_settings["BOTS_ROLE_GREETING"])
                        if role is not None:
                            embed.add_field(name=name, value=role.mention)
                        else:
                            embed.add_field(name=name, value=_("None"))
                        continue
                    else:
                        embed.add_field(name=name, value=guild_settings[attr])
                await ctx.send(embed=embed)

            else:
                msg = "```\n"
                for attr, name in setting_names.items():
                    msg += name + str(guild_settings[attr]) + "\n"
                msg += "```"
                await ctx.send(msg)

    @welcomeset.group(name="msg")
    async def welcomeset_msg(self, ctx):
        """
            Manage welcome messages
        """
        pass

    @welcomeset_msg.command(name="add")
    async def welcomeset_msg_add(self, ctx, *, format_msg):
        """
        Adds a welcome message format for the guild to be chosen at random

        {0} is user
        {1} is guild
        Default is set to:
            Welcome {0.mention} to {1.name}!

        Example formats:
            {0.mention}.. What are you doing here?
            {1.name} has a new member! {0.name}#{0.discriminator} - {0.id}
            Someone new joined! Who is it?! D: IS HE HERE TO HURT US?!
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).GREETING()
        guild_settings.append(format_msg)
        await self.config.guild(guild).GREETING.set(guild_settings)
        await ctx.send(_("Welcome message added for the guild."))
        await self.send_testing_msg(ctx, msg=format_msg)

    @welcomeset_msg.command(name="del")
    async def welcomeset_msg_del(self, ctx):
        """Removes a welcome message from the random message list
        """
        guild = ctx.message.guild
        author = ctx.message.author
        guild_settings = await self.config.guild(guild).GREETING()
        msg = _("Choose a welcome message to delete:\n\n")
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))
        check = (
            lambda message: message.author == ctx.message.author
            and message.channel == ctx.message.channel
        )
        try:
            answer = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return
        try:
            num = int(answer.content)
            choice = guild_settings.pop(num)
        except:
            await ctx.send(_("That's not a number in the list :/"))
            return
        if not guild_settings:
            guild_settings = [default_greeting]
        await self.config.guild(guild).GREETING.set(guild_settings)
        await ctx.send(_("**This message was deleted:**\n") + str(choice))

    @welcomeset_msg.command(name="list")
    async def welcomeset_msg_list(self, ctx):
        """
            Lists the welcome messages of this guild
        """
        guild = ctx.message.guild
        msg = _("Welcome messages:\n\n")
        guild_settings = await self.config.guild(guild).GREETING()
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))

    @welcomeset.command()
    async def toggle(self, ctx):
        """
            Turns on/off welcoming new users to the guild
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).ON_GREETING()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now welcome new users to the guild."))
            await self.send_testing_msg(ctx)
        else:
            await ctx.send(_("I will no longer welcome new users."))
        await self.config.guild(guild).ON_GREETING.set(guild_settings)

    @welcomeset.command()
    async def channel(self, ctx, channel: discord.TextChannel = None):
        """
        Sets the channel to send the welcome message

        If channel isn"t specified, the guild"s default channel will be used
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).CHANNEL_GREETING()
        if channel is None:
            channel = ctx.message.channel
        if not channel.permissions_for(ctx.me).send_messages:
            msg = _("I do not have permissions to send messages to ") + "{0.mention}".format(
                channel
            )
            await ctx.send(msg)
            return
        guild_settings = channel.id
        await self.config.guild(guild).CHANNEL_GREETING.set(guild_settings)
        channel = self.get_welcome_channel(guild, guild_settings)
        msg = _("I will now send welcome messages to ") + "{0.mention}".format(channel)
        await channel.send(msg)
        await self.send_testing_msg(ctx)

    @welcomeset.group(name="bot")
    async def welcomeset_bot(self, ctx):
        """
            Special welcome for bots
        """
        pass

    @welcomeset_bot.command(name="msg")
    async def welcomeset_bot_msg(self, ctx, *, format_msg=None):
        """Set the welcome msg for bots.

        Leave blank to reset to regular user welcome"""
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).BOTS_MSG_GREETING()
        guild_settings = format_msg
        await self.config.guild(guild).BOTS_MSG_GREETING.set(guild_settings)
        if format_msg is None:
            msg = _("Bot message reset. Bots will " "now be welcomed as regular users.")
            await ctx.send(msg)
        else:
            await ctx.send(_("Bot welcome message set for the guild."))
            await self.send_testing_msg(ctx, bot=True, msg=format_msg)

    # TODO: Check if have permissions
    @welcomeset_bot.command(name="role")
    async def welcomeset_bot_role(self, ctx, role: discord.Role = None):
        """
        Set the role to put bots in when they join.

        Leave blank to not give them a role.
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).BOTS_ROLE_GREETING()
        guild_settings = role.id if role else role
        await self.config.guild(guild).BOTS_ROLE_GREETING.set(guild_settings)
        msg = _("Bots that join this guild will be given ") + role.name
        await ctx.send(msg)

    @welcomeset.command()
    async def whisper(self, ctx, choice: str = None):
        """Sets whether or not a DM is sent to the new user

        Options:
            off - turns off DMs to users
            only - only send a DM to the user, don"t send a welcome to the channel
            both - send a message to both the user and the channel

        If Option isn"t specified, toggles between "off" and "only"
        DMs will not be sent to bots"""
        options = {"off": False, "only": True, "both": "BOTH"}
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).WHISPER_GREETING()
        if choice is None:
            guild_settings = not guild_settings
        elif choice.lower() not in options:
            await ctx.send_help()
            return
        else:
            guild_settings = options[choice.lower()]
        await self.config.guild(guild).WHISPER_GREETING.set(guild_settings)
        channel = self.get_welcome_channel(guild, guild_settings)
        if not guild_settings:
            await ctx.send(_("I will no longer send DMs to new users"))
        elif guild_settings == "BOTH":
            msg = (
                _("I will now send welcome ")
                + _("messages to ")
                + "{0.mention}".format(ctx.channel)
                + _(" as well as to the new user in a DM")
            )
            await ctx.send(msg)
        else:
            msg = _("I will now only send " "welcome messages to the new user " "as a DM")
            await ctx.send(msg)
        await self.send_testing_msg(ctx)

    @welcomeset.command()
    async def embed(self, ctx):
        """
        Turns on/off embed messages
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).BOTS_ROLE_GREETING()
        guild_settings = not guild_settings
        if guild_settings:
            await self.config.guild(guild).EMBED_GREETING.set(guild_settings)
            await ctx.send(_("I will now welcome new users to the guild in embeds."))
            await self.send_testing_msg(ctx)
        else:
            await self.config.guild(guild).EMBED_GREETING.set(guild_settings)
            await ctx.send("I will test without embedds.")
            await self.send_testing_msg(ctx)

    async def make_embed(self, member: discord.Member, msg: str):
        count = member.guild.member_count
        em = discord.Embed(
            description=msg.format(member, member.guild),
            timestamp=member.joined_at,
            color=self.bot.color,
        )
        em.set_author(name=member.name + "#" + member.discriminator, icon_url=member.avatar_url)
        em.set_thumbnail(url=member.avatar_url_as(format="png"))
        em.set_footer(text="↗️ Member count : {}".format(count))
        return em

    async def make_embed_whisper(self, member: discord.Member, msg: str):
        count = member.guild.member_count
        em = discord.Embed(
            description=msg.format(member, member.guild),
            timestamp=member.joined_at,
            color=self.bot.color,
        )
        em.set_author(name=member.name + "#" + member.discriminator, icon_url=member.avatar_url)
        em.set_thumbnail(url=member.guild.icon_url)
        em.set_footer(text="↗️ Member count : {}".format(count))
        return em

    async def get_colour(self, guild):
        if await self.bot.db.guild(guild).use_bot_color():
            return guild.me.colour
        else:
            return await self.bot.db.color()

    async def on_member_join(self, member):
        guild = member.guild
        if not await self.config.guild(guild).ON_GREETING():
            return
        if guild is None:
            return

        only_whisper = await self.config.guild(guild).WHISPER_GREETING() is True
        bot_welcome = member.bot and await self.config.guild(guild).BOTS_MSG_GREETING()
        bot_role = member.bot and await self.config.guild(guild).BOTS_ROLE_GREETING()
        msg = bot_welcome or rand_choice(await self.config.guild(guild).GREETING())
        is_embed = await self.config.guild(guild).EMBED_GREETING()

        # whisper the user if needed
        if not member.bot and await self.config.guild(guild).WHISPER_GREETING():
            try:
                if is_embed:
                    em = await self.make_embed_whisper(member, msg)
                    await member.send(embed=em)
                else:
                    await member.send(msg.format(member, guild))
            except:
                print(
                    _("welcome.py: unable to whisper a user. Probably " "doesn't want to be PM'd")
                    + str(member)
                )
        # grab the welcome channel
        # guild_settings = await self.config.guild(guild).guild_settings()
        channel = self.bot.get_channel(await self.config.guild(guild).CHANNEL_GREETING())
        if channel is None:  # complain even if only whisper
            print(
                _("welcome.py: Channel not found. It was most " "likely deleted. User joined: ")
                + member.name
            )
            return
        # we can stop here

        if not self.speak_permissions(guild, channel.id):
            print(_("Permissions Error. User that joined: ") + "{0.name}".format(member))
            print(
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
                print(e)
                print(_("welcome.py: unable to add  a role. ") + str(bot_role) + str(member))
            else:
                print(
                    _("welcome.py: added ") + str(role) + _(" role to ") + _("bot, ") + str(member)
                )

        if only_whisper and not bot_welcome:
            return
        if bot_welcome:
            # finally, welcome them
            if is_embed:
                em = await self.make_embed(member, bot_welcome)
                await channel.send(embed=em)
            else:
                await channel.send(bot_welcome.format(member, guild))
        elif not member.bot:
            if is_embed:
                em = await self.make_embed(member, msg)
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
        return guild.get_member(self.bot.user.id).permissions_in(channel).send_messages

    async def send_testing_msg(self, ctx, bot=False, msg=None):
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).guild_settings()
        # print(guild_settings)
        channel = self.get_welcome_channel(
            guild, await self.config.guild(guild).CHANNEL_GREETING()
        )
        rand_msg = msg or rand_choice(await self.config.guild(guild).GREETING())
        is_embed = await self.config.guild(guild).EMBED_GREETING()
        member = ctx.message.author
        whisper_settings = await self.config.guild(guild).WHISPER_GREETING()
        if channel is None and whisper_settings not in ["BOTH", True]:
            msg = _("I can't find the specified channel. " "It might have been deleted.")
            await ctx.send(msg)
            return
        if channel is None:
            await ctx.send(_("`Sending a testing message to ") + "` DM")
        else:
            await ctx.send(_("`Sending a testing message to ") + "`{0.mention}".format(channel))
        if self.speak_permissions(guild, await self.config.guild(guild).CHANNEL_GREETING()):
            msg = await self.config.guild(guild).BOTS_MSG_GREETING() if bot else rand_msg
            print(msg)
            if not bot and await self.config.guild(guild).WHISPER_GREETING():
                if is_embed:
                    em = await self.make_embed_whisper(member, msg)
                    await ctx.author.send(embed=em)
                else:
                    await ctx.author.send(msg.format(member, guild))
            if bot or whisper_settings is not True:
                if is_embed:
                    em = await self.make_embed(member, msg)
                    await channel.send(embed=em)
                else:
                    await channel.send(msg.format(member, guild))
        else:
            msg = _("I do not have permissions to send messages to ")
            if channel:
                msg += "{0.mention}".format(channel)
            else:
                return
            await ctx.send(msg)

    @commands.group()
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def leaverset(self, ctx):
        """Sets leaver module settings"""
        guild = ctx.message.guild
        if ctx.invoked_subcommand is None:
            guild_settings = await self.config.guild(guild).get_raw()
            setting_names = {
                "GOODBYE": _("Random Goodbye "),
                "ON_GOODBYE": _("On "),
                "CHANNEL_GOODBYE": _("Channel "),
                "WHISPER_GOODBYE": _("Whisper "),
                "BOTS_MSG_GOODBYE": _("Bots message "),
                "EMBED_GOODBYE": _("Embeds "),
            }
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed(colour=await self.get_colour_leaver(guild))
                embed.set_author(
                    name=_("Leaver settings for ") + guild.name, icon_url=guild.icon_url
                )
                embed.description = "\n".join(g for g in guild_settings["GOODBYE"])
                for attr, name in setting_names.items():
                    if attr == "GOODBYE":
                        continue
                    if attr == "CHANNEL_GOODBYE":
                        chan = guild.get_channel(guild_settings["CHANNEL_GOODBYE"])
                        if chan is not None:
                            embed.add_field(name=name, value=chan.mention)
                        else:
                            embed.add_field(name=name, value=_("None"))
                        continue
                    else:
                        embed.add_field(name=name, value=guild_settings[attr])
                await ctx.send(embed=embed)

            else:
                msg = "```\n"
                for attr, name in setting_names.items():
                    msg += name + str(guild_settings[attr]) + "\n"
                msg += "```"
                await ctx.send(msg)

    @leaverset.group(name="msg")
    async def leaverset_msg(self, ctx):
        """
            Manage leaver messages
        """
        pass

    @leaverset_msg.command(name="add")
    async def leaver_msg_add(self, ctx, *, format_msg):
        """
        Adds a leaver message format for the guild to be chosen at random

        {0} is user
        {1} is guild
        Default is set to:
            Goodbye {0.mention} 😦

        Example formats:
            {0.mention}.. What are you doing here?
            {1.name} has a new member! {0.name}#{0.discriminator} - {0.id}
            Someone new joined! Who is it?! D: IS HE HERE TO HURT US?!
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).GOODBYE()
        guild_settings.append(format_msg)
        await self.config.guild(guild).GOODBYE.set(guild_settings)
        await ctx.send(_("Leaver message added for the guild."))
        await self.send_testing_msg_leaver(ctx, msg=format_msg)

    @leaverset_msg.command(name="del")
    async def leaverset_msg_del(self, ctx):
        """Removes a leaver message from the random message list
        """
        guild = ctx.message.guild
        author = ctx.message.author
        guild_settings = await self.config.guild(guild).GOODBYE()
        msg = _("Choose a leaver message to delete:\n\n")
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))
        check = (
            lambda message: message.author == ctx.message.author
            and message.channel == ctx.message.channel
        )
        try:
            answer = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return
        try:
            num = int(answer.content)
            choice = guild_settings.pop(num)
        except:
            await ctx.send(_("That's not a number in the list :/"))
            return
        if not guild_settings:
            guild_settings = [default_goodbye]
        await self.config.guild(guild).GOODBYE.set(guild_settings)
        await ctx.send(_("**This message was deleted:**\n") + str(choice))

    @leaverset_msg.command(name="list")
    async def leaverset_msg_list(self, ctx):
        """
            Lists the leaver messages of this guild
        """
        guild = ctx.message.guild
        msg = _("Leaver messages:\n\n")
        guild_settings = await self.config.guild(guild).GOODBYE()
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))

    @leaverset.command(name="toggle")
    async def toggleleave(self, ctx):
        """
            Turns on/off goodbye users to the guild
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).ON_GOODBYE()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now goodbye new users to the guild."))
            await self.send_testing_msg_leaver(ctx)
        else:
            await ctx.send(_("I will no longer goodbye new users."))
        await self.config.guild(guild).ON_GOODBYE.set(guild_settings)

    @leaverset.command(name="channel")
    async def channelleave(self, ctx, channel: discord.TextChannel = None):
        """
        Sets the channel to send the leaver message

        If channel isn"t specified, the guild"s default channel will be used
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).CHANNEL_GOODBYE()
        if channel is None:
            channel = ctx.message.channel
        if not channel.permissions_for(ctx.me).send_messages:
            msg = _("I do not have permissions to send messages to ") + "{0.mention}".format(
                channel
            )
            await ctx.send(msg)
            return
        guild_settings = channel.id
        await self.config.guild(guild).CHANNEL_GOODBYE.set(guild_settings)
        channel = self.get_goodbye_channel_leaver(guild, guild_settings)
        msg = _("I will now send leaver messages to ") + "{0.mention}".format(channel)
        await channel.send(msg)
        await self.send_testing_msg_leaver(ctx)

    @leaverset.group(name="bot")
    async def leaverset_bot(self, ctx):
        """
            Special goodbye for bots
        """
        pass

    @leaverset_bot.command(name="msg")
    async def leaverset_bot_msg(self, ctx, *, format_msg=None):
        """Set the leaver msg for bots.

        Leave blank to reset to regular user leaver"""
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).BOTS_MSG_GOODBYE()
        guild_settings = format_msg
        await self.config.guild(guild).BOTS_MSG_GOODBYE.set(guild_settings)
        if format_msg is None:
            msg = _("Bot message reset. Bots will " "now be goodbye as regular users.")
            await ctx.send(msg)
        else:
            await ctx.send(_("Bot goodbye message set for the guild."))
            await self.send_testing_msg_leaver(ctx, bot=True, msg=format_msg)

    @leaverset.command(name="whisper")
    async def whisperleave(self, ctx, choice: str = None):
        """Sets whether or not a DM is sent to the leaver user

        Options:
            off - turns off DMs to users
            only - only send a DM to the user, don"t send a goodbye to the channel
            both - send a message to both the user and the channel

        If Option isn"t specified, toggles between "off" and "only"
        DMs will not be sent to bots"""
        options = {"off": False, "only": True, "both": "BOTH"}
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).WHISPER_GOODBYE()
        if choice is None:
            guild_settings = not guild_settings
        elif choice.lower() not in options:
            await ctx.send_help()
            return
        else:
            guild_settings = options[choice.lower()]
        await self.config.guild(guild).WHISPER_GOODBYE.set(guild_settings)
        channel = self.get_goodbye_channel_leaver(guild, guild_settings)
        if not guild_settings:
            await ctx.send(_("I will no longer send DMs to new users"))
        elif guild_settings == "BOTH":
            msg = (
                _("I will now send goodbye ")
                + _("messages to ")
                + "{0.mention}".format(ctx.channel)
                + _(" as well as to the new user in a DM")
            )
            await ctx.send(msg)
        else:
            msg = _("I will now only send " "goodbye messages to user " "as a DM")
            await ctx.send(msg)
        await self.send_testing_msg_leaver(ctx)

    @leaverset.command(name="embed")
    async def embedleave(self, ctx):
        """
        Turns on/off embed messages
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).EMBED_GOODBYE()
        guild_settings = not guild_settings
        if guild_settings:
            await self.config.guild(guild).EMBED_GOODBYE.set(guild_settings)
            await ctx.send(_("I will now goobye users to the guild in embeds."))
            await self.send_testing_msg_leaver(ctx)
        else:
            await self.config.guild(guild).EMBED_GOODBYE.set(guild_settings)
            await ctx.send("I will test without embedds.")
            await self.send_testing_msg_leaver(ctx)

    async def make_embed_leaver(self, member: discord.Member, msg: str):
        count = member.guild.member_count
        em = discord.Embed(
            description=msg.format(member, member.guild), timestamp=time_, color=self.bot.color
        )
        em.set_author(name=member.name + "#" + member.discriminator, icon_url=member.avatar_url)
        em.set_thumbnail(url=member.avatar_url_as(format="png"))
        em.set_footer(text="↘️ Member count : {}".format(count))
        return em

    async def make_embed_whisper_leaver(self, member: discord.Member, msg: str):
        count = member.guild.member_count
        em = discord.Embed(
            description=msg.format(member, member.guild), timestamp=time_, color=self.bot.color
        )
        em.set_author(name=member.name + "#" + member.discriminator, icon_url=member.avatar_url)
        em.set_thumbnail(url=member.guild.icon_url)
        em.set_footer(text="↘️ Member count : {}".format(count))
        return em

    async def get_colour_leaver(self, guild):
        if await self.bot.db.guild(guild).use_bot_color():
            return guild.me.colour
        else:
            return await self.bot.db.color()

    async def on_member_remove(self, member):
        guild = member.guild
        if not await self.config.guild(guild).ON_GOODBYE():
            return
        if guild is None:
            return

        only_whisper = await self.config.guild(guild).WHISPER_GOODBYE() is True
        bot_goodbye = member.bot and await self.config.guild(guild).BOTS_MSG_GOODBYE()
        msg = bot_goodbye or rand_choice(await self.config.guild(guild).GOODBYE())
        is_embed = await self.config.guild(guild).EMBED_GOODBYE()

        # whisper the user if needed
        if not member.bot and await self.config.guild(guild).WHISPER_GOODBYE():
            try:
                if is_embed:
                    em = await self.make_embed_whisper_leaver(member, msg)
                    await member.send(embed=em)
                else:
                    await member.send(msg.format(member, guild))
            except:
                print(
                    _("leaver.py: unable to whisper a user. Probably " "doesn't want to be PM'd")
                    + str(member)
                )
        # grab the leaver channel
        # guild_settings = await self.config.guild(guild).guild_settings()
        channel = self.bot.get_channel(await self.config.guild(guild).CHANNEL_GOODBYE())
        if channel is None:  # complain even if only whisper
            print(
                _("leaver.py: Channel not found. It was most " "likely deleted. User joined: ")
                + member.name
            )
            return
        # we can stop here

        if not self.speak_permissions_leaver(guild, channel.id):
            print(_("Permissions Error. User that joined: ") + "{0.name}".format(member))
            print(
                _("Bot doesn't have permissions to send messages to ")
                + "{0.name}'s #{1.name} channel".format(guild, channel)
            )
            return

        if only_whisper and not bot_goodbye:
            return
        if bot_goodbye:
            # finally, goodbye them
            if is_embed:
                em = await self.make_embed_leaver(member, bot_goodbye)
                await channel.send(embed=em)
            else:
                await channel.send(bot_goodbye.format(member, guild))
        elif not member.bot:
            if is_embed:
                em = await self.make_embed_leaver(member, msg)
                await channel.send(embed=em)
            else:
                await channel.send(msg.format(member, guild))

    def get_goodbye_channel_leaver(self, guild, guild_settings):
        try:
            return guild.get_channel(guild_settings)
        except:
            return None

    def speak_permissions_leaver(self, guild, guild_settings):
        channel = self.get_goodbye_channel_leaver(guild, guild_settings)
        if channel is None:
            return False
        return guild.get_member(self.bot.user.id).permissions_in(channel).send_messages

    async def send_testing_msg_leaver(self, ctx, bot=False, msg=None):
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).guild_settings()
        # print(guild_settings)
        channel = self.get_goodbye_channel_leaver(
            guild, await self.config.guild(guild).CHANNEL_GOODBYE()
        )
        rand_msg = msg or rand_choice(await self.config.guild(guild).GOODBYE())
        is_embed = await self.config.guild(guild).EMBED_GOODBYE()
        member = ctx.message.author
        whisper_settings = await self.config.guild(guild).WHISPER_GOODBYE()
        if channel is None and whisper_settings not in ["BOTH", True]:
            msg = _("I can't find the specified channel. " "It might have been deleted.")
            await ctx.send(msg)
            return
        if channel is None:
            await ctx.send(_("`Sending a testing message to ") + "` DM")
        else:
            await ctx.send(_("`Sending a testing message to ") + "`{0.mention}".format(channel))
        if self.speak_permissions_leaver(guild, await self.config.guild(guild).CHANNEL_GOODBYE()):
            msg = await self.config.guild(guild).BOTS_MSG_GOODBYE() if bot else rand_msg
            print(msg)
            if not bot and await self.config.guild(guild).WHISPER_GOODBYE():
                if is_embed:
                    em = await self.make_embed_whisper_leaver(member, msg)
                    await ctx.author.send(embed=em)
                else:
                    await ctx.author.send(msg.format(member, guild))
            if bot or whisper_settings is not True:
                if is_embed:
                    em = await self.make_embed_leaver(member, msg)
                    await channel.send(embed=em)
                else:
                    await channel.send(msg.format(member, guild))
        else:
            msg = _("I do not have permissions to send messages to ")
            if channel:
                msg += "{0.mention}".format(channel)
            else:
                return
            await ctx.send(msg)

    @commands.command(name="welcomeleavesettings")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_channels=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def welcomeleave_settings(self, ctx):
        """Show current settings of welcomeleave module"""
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).get_raw()
        setting_names_welcome = {
            "GREETING": _("Random Greeting "),
            "ON_GREETING": _("On "),
            "CHANNEL_GREETING": _("Channel "),
            "WHISPER_GREETING": _("Whisper "),
            "BOTS_MSG_GREETING": _("Bots message "),
            "BOTS_ROLE_GREETING": _("Bots role "),
            "EMBED_GREETING": _("Embeds "),
        }
        setting_names_goodbye = {
            "GOODBYE": _("Random Goodbye "),
            "ON_GOODBYE": _("On "),
            "CHANNEL_GOODBYE": _("Channel "),
            "WHISPER_GOODBYE": _("Whisper "),
            "BOTS_MSG_GOODBYE": _("Bots message "),
            "EMBED_GOODBYE": _("Embeds "),
        }
        if ctx.channel.permissions_for(ctx.me).embed_links:
            embed_welcome = discord.Embed(colour=await self.get_colour(guild))
            embed_welcome.set_author(
                name=_("Welcome settings for ") + guild.name, icon_url=guild.icon_url
            )
            embed_welcome.description = "\n".join(g for g in guild_settings["GREETING"])
            for attr, name in setting_names_welcome.items():
                if attr == "GREETING":
                    continue
                if attr == "CHANNEL_GREETING":
                    chan = guild.get_channel(guild_settings["CHANNEL_GREETING"])
                    if chan is not None:
                        embed_welcome.add_field(name=name, value=chan.mention)
                    else:
                        embed_welcome.add_field(name=name, value=_("None"))
                    continue
                if attr == "BOTS_ROLE_GREETING":
                    role = guild.get_role(guild_settings["BOTS_ROLE_GREETING"])
                    if role is not None:
                        embed_welcome.add_field(name=name, value=role.mention)
                    else:
                        embed_welcome.add_field(name=name, value=_("None"))
                    continue
                else:
                    embed_welcome.add_field(name=name, value=guild_settings[attr])
            embed_goodbye = discord.Embed(colour=await self.get_colour_leaver(guild))
            embed_goodbye.set_author(
                name=_("Leaver settings for ") + guild.name, icon_url=guild.icon_url
            )
            embed_goodbye.description = "\n".join(g for g in guild_settings["GOODBYE"])
            for attr, name in setting_names_goodbye.items():
                if attr == "GOODBYE":
                    continue
                if attr == "CHANNEL_GOODBYE":
                    chan = guild.get_channel(guild_settings["CHANNEL_GOODBYE"])
                    if chan is not None:
                        embed_goodbye.add_field(name=name, value=chan.mention)
                    else:
                        embed_goodbye.add_field(name=name, value=_("None"))
                    continue
                else:
                    embed_goodbye.add_field(name=name, value=guild_settings[attr])
            await ctx.send(embed=embed_welcome)
            await ctx.send(embed=embed_goodbye)

        else:
            msg_welcome = "```\n"
            for attr, name in setting_names_goodbye.items():
                msg_welcome += name + str(guild_settings[attr]) + "\n"
            msg_welcome += "```"
            msg_goodbye = "```\n"
            for attr, name in setting_names_goodbye.items():
                msg_goodbye += name + str(guild_settings[attr]) + "\n"
            msg_goodbye += "```"
            await ctx.send(msg_welcome)
            await ctx.send(msg_goodbye)
