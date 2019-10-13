import re
import asyncio
import logging

import discord

from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import pagify
from redbot.core.i18n import Translator, cog_i18n

from .events import Events

default_greeting = "Welcome {0.name} to {1.name}!"
default_goodbye = "See you later {0.name}!"
default_settings = {
    "GREETING": [default_greeting],
    "ON": False,
    "LEAVE_ON": False,
    "LEAVE_CHANNEL": None,
    "GROUPED": False,
    "GOODBYE": [default_goodbye],
    "CHANNEL": None,
    "WHISPER": False,
    "BOTS_MSG": None,
    "BOTS_ROLE": None,
    "EMBED": False,
    "EMBED_DATA": {
        "title": None,
        "colour": 0,
        "footer": None,
        "thumbnail": None,
        "image": None,
        "icon_url": None,
        "author": True,
        "timestamp": True,
        "mention": False,
    },
}

IMAGE_LINKS = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|png))")

_ = Translator("Welcome", __file__)
log = logging.getLogger("red.trusty-cogs.Welcome")


@cog_i18n(_)
class Welcome(Events, commands.Cog):
    """Welcomes new members and goodbye those who leave to the guild
     in the default channel rewritten for V3 from
     https://github.com/irdumbs/Dumb-Cogs/blob/master/welcome/welcome.py"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 144465786453, force_registration=True)
        self.config.register_guild(**default_settings)
        self.group_check = bot.loop.create_task(self.group_welcome())
        self.joined = {}

    async def group_welcome(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            log.debug("Checking for new welcomes")
            for guild_id, members in self.joined.items():
                await self.send_member_join(members, self.bot.get_guild(guild_id))
            self.joined = {}
            await asyncio.sleep(300)

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
                "GOODBYE": _("Random Goodbye "),
                "GROUPED": _("Grouped welcomes "),
                "ON": _("Welcomes On "),
                "CHANNEL": _("Channel "),
                "LEAVE_ON": _("Goodbyes On "),
                "LEAVE_CHANNEL": _("Leaving Channel "),
                "WHISPER": _("Whisper "),
                "BOTS_MSG": _("Bots message "),
                "BOTS_ROLE": _("Bots role "),
                "EMBED": _("Embeds "),
            }
            msg = ""
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed(colour=await ctx.embed_colour())
                embed.set_author(
                    name=_("Welcome settings for ") + guild.name
                )
                # embed.description = "\n".join(g for g in guild_settings["GREETING"])
                for attr, name in setting_names.items():
                    if attr in ["GREETING", "GOODBYE"]:
                        embed.add_field(
                            name=name,
                            value="\n".join(g for g in guild_settings[attr])[:1024],
                            inline=False,
                        )
                        continue
                    if attr in ["CHANNEL", "LEAVE_CHANNEL"]:
                        chan = guild.get_channel(guild_settings[attr])
                        if chan is not None:
                            msg += f"**{name}**: {chan.mention}\n"
                        else:
                            msg += f"**{name}**:" + _("None") + "\n"
                        continue
                    if attr == "BOTS_ROLE":
                        role = guild.get_role(guild_settings["BOTS_ROLE"])
                        if role is not None:
                            msg += f"**{name}**:  {role.mention}\n"
                        else:
                            msg += f"**{name}**:" + _("None") + "\n"
                        continue
                    else:
                        msg += f"**{name}**:  {guild_settings[attr]}\n"
                embed.description = msg
                await ctx.send(embed=embed)

            else:
                msg = "```\n"
                for attr, name in setting_names.items():
                    msg += name + str(guild_settings[attr]) + "\n"
                msg += "```"
                await ctx.send(msg)

    @welcomeset.group(name="greeting", aliases=["welcome"])
    async def welcomeset_greeting(self, ctx):
        """
            Manage welcome messages
        """
        pass

    @welcomeset_greeting.command(name="grouped")
    async def welcomeset_greeting_grouped(self, ctx, grouped: bool):
        """Set whether to group welcome messages"""
        await self.config.guild(ctx.guild).GROUPED.set(grouped)
        await self.send_testing_msg(ctx)

    @welcomeset_greeting.command(name="add")
    async def welcomeset_greeting_add(self, ctx, *, format_msg):
        """
        Adds a welcome message format for the guild to be chosen at random

        {0} is user
        {1} is guild
        Default is set to:
            Welcome {0.name} to {1.name}!

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

    @welcomeset_greeting.command(name="del")
    async def welcomeset_greeting_del(self, ctx):
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

    @welcomeset_greeting.command(name="list")
    async def welcomeset_greeting_list(self, ctx):
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

    @welcomeset_greeting.command(name="toggle")
    async def welcomeset_greeting_toggle(self, ctx):
        """
            Turns on/off welcoming new users to the guild
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).ON()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now welcome new users to the guild."))
            await self.send_testing_msg(ctx)
        else:
            await ctx.send(_("I will no longer welcome new users."))
        await self.config.guild(guild).ON.set(guild_settings)

    @welcomeset_greeting.command(name="channel")
    async def welcomeset_greeting_channel(self, ctx, channel: discord.TextChannel):
        """
        Sets the channel to send the welcome message

        If channel isn"t specified, the guild's default channel will be used
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).CHANNEL()
        if channel is None:
            channel = ctx.message.channel
        if not channel.permissions_for(ctx.me).send_messages:
            msg = _("I do not have permissions to send messages to {channel}").format(
                channel=channel.mention
            )
            await ctx.send(msg)
            return
        guild_settings = channel.id
        await self.config.guild(guild).CHANNEL.set(guild_settings)
        msg = _("I will now send welcome messages to {channel}").format(channel=channel.mention)
        await channel.send(msg)
        await self.send_testing_msg(ctx)

    @welcomeset_greeting.command()
    async def test(self, ctx):
        """Test the welcome message deleted after 60 seconds"""
        await self.send_testing_msg(ctx)

    @welcomeset.group(name="goodbye", aliases=["leave"])
    async def welcomeset_goodbye(self, ctx):
        """
            Manage goodbye messages
        """
        pass

    @welcomeset_goodbye.command(name="add")
    async def welcomeset_goodbye_add(self, ctx, *, format_msg):
        """
        Adds a goodbye message format for the guild to be chosen at random

        {0} is user
        {1} is guild
        Default is set to:
            See you later {0.name}!

        Example formats:
            {0.mention}.. well, bye.
            {1.name} has lost a member. {0.name}#{0.discriminator} - {0.id}
            Someone has quit the server! Who is it?! D:
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).GOODBYE()
        guild_settings.append(format_msg)
        await self.config.guild(guild).GOODBYE.set(guild_settings)
        await ctx.send(_("Goodbye message added for the guild."))
        await self.send_testing_msg(ctx, msg=format_msg, leave=True)

    @welcomeset_goodbye.command(name="del")
    async def welcomeset_goodbye_del(self, ctx):
        """
        Removes a goodbye message from the random message list
        """
        guild = ctx.message.guild
        author = ctx.message.author
        guild_settings = await self.config.guild(guild).GOODBYE()
        msg = _("Choose a goodbye message to delete:\n\n")
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

    @welcomeset_goodbye.command(name="list")
    async def welcomeset_goodbye_list(self, ctx):
        """
            Lists the goodbye messages of this guild
        """
        guild = ctx.message.guild
        msg = _("Goodbye messages:\n\n")
        guild_settings = await self.config.guild(guild).GOODBYE()
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))

    @welcomeset_goodbye.command(name="toggle")
    async def welcomeset_goodbye_toggle(self, ctx):
        """
            Turns on/off goodbying users who leave to the guild
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).LEAVE_ON()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now say goodbye when a member leaves the server."))
            await self.send_testing_msg(ctx, leave=True)
        else:
            await ctx.send(_("I will no longer say goodbye to members leaving the server."))
        await self.config.guild(guild).LEAVE_ON.set(guild_settings)

    @welcomeset_goodbye.command(name="channel")
    async def welcomeset_goodbye_channel(self, ctx, channel: discord.TextChannel):
        """
        Sets the channel to send the goodbye message
        """
        guild = ctx.message.guild
        if not channel.permissions_for(ctx.me).send_messages:
            msg = _("I do not have permissions to send messages to {channel}").format(
                channel=channel.mention
            )
            await ctx.send(msg)
            return
        await self.config.guild(guild).LEAVE_CHANNEL.set(channel.id)
        msg = _("I will now send goodbye messages to {channel}").format(channel=channel.mention)
        await ctx.send(msg)
        await self.send_testing_msg(ctx, leave=True)

    @welcomeset_goodbye.command(name="test")
    async def welcomeset_goodbye_test(self, ctx):
        """Test the goodbye message deleted after 60 seconds"""
        await self.send_testing_msg(ctx, leave=True)

    @welcomeset.group(name="bot")
    async def welcomeset_bot(self, ctx):
        """
            Special welcome for bots
        """
        pass

    @welcomeset_bot.command(name="test")
    async def welcomeset_bot_test(self, ctx):
        """Test the bot joining message"""
        await self.send_testing_msg(ctx, bot=True)

    @welcomeset_bot.command(name="msg")
    async def welcomeset_bot_msg(self, ctx, *, format_msg=None):
        """Set the welcome msg for bots.

        Leave blank to reset to regular user welcome"""
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).BOTS_MSG()
        guild_settings = format_msg
        await self.config.guild(guild).BOTS_MSG.set(guild_settings)
        if format_msg is None:
            msg = _("Bot message reset. Bots will now be welcomed as regular users.")
            await ctx.send(msg)
        else:
            await ctx.send(_("Bot welcome message set for the guild."))
            await self.send_testing_msg(ctx, bot=True, msg=format_msg)

    # TODO: Check if have permissions
    @welcomeset_bot.command(name="role")
    async def welcomeset_bot_role(self, ctx, *, role: discord.Role = None):
        """
        Set the role to put bots in when they join.

        Leave blank to not give them a role.
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).BOTS_ROLE()
        guild_settings = role.id if role is not None else role
        if role is not None and role >= guild.me.top_role:
            return await ctx.send(_("I cannot assign roles higher than my own."))
        await self.config.guild(guild).BOTS_ROLE.set(guild_settings)
        if role:
            msg = _("Bots that join this guild will be given ") + role.name
        else:
            msg = _("Bots that join this guild will not be given a role.")
        await ctx.send(msg)

    @welcomeset.command()
    async def whisper(self, ctx, choice: str = None):
        """Sets whether or not a DM is sent to the new user

        Options:
            off - turns off DMs to users
            only - only send a DM to the user, don"t send a welcome to the channel
            both - send a message to both the user and the channel

        If Option isn't specified, toggles between "off" and "only"
        DMs will not be sent to bots"""
        options = {"off": False, "only": True, "both": "BOTH"}
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).WHISPER()
        if choice is None:
            guild_settings = not guild_settings
        elif choice.lower() not in options:
            await ctx.send(_("You must select either `off`, `only`, or `both`."))
            return
        else:
            guild_settings = options[choice.lower()]
        await self.config.guild(guild).WHISPER.set(guild_settings)
        if not guild_settings:
            await ctx.send(_("I will no longer send DMs to new users"))
        elif guild_settings == "BOTH":
            channel = guild.get_channel(await self.config.guild(guild).CHANNEL())
            msg = _(
                "I will now send welcome messages to {channel} as well as to the new user in a DM"
            ).format(channel=channel)
            await ctx.send(msg)
        else:
            msg = _("I will now only send welcome messages to the new user as a DM")
            await ctx.send(msg)
        await self.send_testing_msg(ctx)

    @welcomeset.group(name="embed")
    async def _embed(self, ctx):
        """
        Set various embed options
        """
        pass

    @_embed.command()
    async def toggle(self, ctx):
        """
        Toggle embed messages
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).EMBED()
        await self.config.guild(guild).EMBED.set(not guild_settings)
        if guild_settings:
            verb = _("off")
        else:
            verb = _("on")
        await ctx.send(_("Welcome embeds turned {verb}").format(verb=verb))
        await self.send_testing_msg(ctx)

    @_embed.command(aliases=["color"])
    async def colour(self, ctx, colour: discord.Colour):
        """
        Set the embed colour

        This accepts hex codes and integer value colours
        """
        await self.config.guild(ctx.guild).EMBED_DATA.colour.set(colour.value)
        await ctx.tick()

    @_embed.command()
    async def title(self, ctx, *, title: str = ""):
        """
        Set the embed title
        """
        await self.config.guild(ctx.guild).EMBED_DATA.title.set(title[:256])
        await ctx.tick()

    @_embed.command()
    async def footer(self, ctx, *, footer: str = ""):
        """
        Set the embed footer
        """
        await self.config.guild(ctx.guild).EMBED_DATA.footer.set(footer[:256])
        await ctx.tick()

    @_embed.command()
    async def thumbnail(self, ctx, link: str = None):
        """
        Set the embed thumbnail image

        `[link]` must be a valid image link
        You may also specify:
         `member`, `user` or `avatar` to use the members avatar
        `server` or `guild` to use the servers icon
        `splash` to use the servers splash image if available
        if nothing is provided the defaults are used.
        """
        if link is not None:
            link_search = IMAGE_LINKS.search(link)
            if link_search:
                await self.config.guild(ctx.guild).EMBED_DATA.thumbnail.set(link_search.group(0))
                await ctx.tick()
            elif link in ["member", "user", "avatar"]:
                await self.config.guild(ctx.guild).EMBED_DATA.thumbnail.set("avatar")
                await ctx.tick()
            elif link in ["server", "guild"]:
                await self.config.guild(ctx.guild).EMBED_DATA.thumbnail.set("guild")
                await ctx.tick()
            elif link == "splash":
                await self.config.guild(ctx.guild).EMBED_DATA.thumbnail.set("splash")
                await ctx.tick()
            else:
                await ctx.send(
                    _("That's not a valid option. You must provide a link, `avatar` or `server`.")
                )
        else:
            await self.config.guild(ctx.guild).EMBED_DATA.thumbnail.set(None)
            await ctx.send(_("Thumbnail cleared."))

    @_embed.command()
    async def icon(self, ctx, link: str = None):
        """
        Set the embed icon image

        `[link]` must be a valid image link
        You may also specify:
         `member`, `user` or `avatar` to use the members avatar
        `server` or `guild` to use the servers icon
        `splash` to use the servers splash image if available
        if nothing is provided the defaults are used.
        """
        if link is not None:
            link_search = IMAGE_LINKS.search(link)
            if link_search:
                await self.config.guild(ctx.guild).EMBED_DATA.icon_url.set(link_search.group(0))
                await ctx.tick()
            elif link in ["author", "avatar"]:
                await self.config.guild(ctx.guild).EMBED_DATA.icon_url.set("avatar")
                await ctx.tick()
            elif link in ["server", "guild"]:
                await self.config.guild(ctx.guild).EMBED_DATA.icon_url.set("guild")
                await ctx.tick()
            elif link == "splash":
                await self.config.guild(ctx.guild).EMBED_DATA.icon_url.set("splash")
                await ctx.tick()
            else:
                await ctx.send(
                    _("That's not a valid option. You must provide a link, `avatar` or `server`.")
                )
        else:
            await self.config.guild(ctx.guild).EMBED_DATA.icon_url.set(None)
            await ctx.send(_("Icon cleared."))

    @_embed.command()
    async def image(self, ctx, link: str = None):
        """
        Set the embed image link

        `[link]` must be a valid image link
        You may also specify:
         `member`, `user` or `avatar` to use the members avatar
        `server` or `guild` to use the servers icon
        `splash` to use the servers splash image if available
        if nothing is provided the defaults are used.
        """
        if link is not None:
            link_search = IMAGE_LINKS.search(link)
            if link_search:
                await self.config.guild(ctx.guild).EMBED_DATA.image.set(link_search.group(0))
                await ctx.tick()
            elif link in ["author", "avatar"]:
                await self.config.guild(ctx.guild).EMBED_DATA.image.set("avatar")
                await ctx.tick()
            elif link in ["server", "guild"]:
                await self.config.guild(ctx.guild).EMBED_DATA.image.set("guild")
                await ctx.tick()
            elif link == "splash":
                await self.config.guild(ctx.guild).EMBED_DATA.image.set("splash")
                await ctx.tick()
            else:
                await ctx.send(
                    _("That's not a valid option. You must provide a link, `avatar` or `server`.")
                )
        else:
            await self.config.guild(ctx.guild).EMBED_DATA.image.set(None)
            await ctx.send(_("Image cleared."))

    @_embed.command()
    async def timestamp(self, ctx):
        """
        Toggle the timestamp in embeds
        """
        cur_setting = await self.config.guild(ctx.guild).EMBED_DATA.timestamp()
        await self.config.guild(ctx.guild).EMBED_DATA.timestamp.set(not cur_setting)
        if cur_setting:
            verb = _("off")
        else:
            verb = _("on")
        await ctx.send(_("Timestamps turned {verb}").format(verb=verb))

    @_embed.command()
    async def author(self, ctx):
        """
        Toggle the author field being filled in the embed

        Note: This will override the icon image if it is set
        """
        cur_setting = await self.config.guild(ctx.guild).EMBED_DATA.author()
        await self.config.guild(ctx.guild).EMBED_DATA.author.set(not cur_setting)
        if cur_setting:
            verb = _("off")
        else:
            verb = _("on")
        await ctx.send(_("Author field turned {verb}").format(verb=verb))

    @_embed.command()
    async def mention(self, ctx):
        """
        Toggle mentioning the user when they join
        """
        cur_setting = await self.config.guild(ctx.guild).EMBED_DATA.mention()
        await self.config.guild(ctx.guild).EMBED_DATA.mention.set(not cur_setting)
        if cur_setting:
            verb = _("off")
        else:
            verb = _("on")
        await ctx.send(_("Mentioning the user turned {verb}").format(verb=verb))

    def cog_unload(self):
        self.group_check.cancel()

    __unload = cog_unload