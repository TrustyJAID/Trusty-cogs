import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import discord
from redbot.core import Config, VersionInfo, checks, commands, version_info
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.predicates import MessagePredicate

from .events import Events

default_greeting = "Welcome {0.name} to {1.name}!"
default_goodbye = "See you later {0.name}!"
default_bot_msg = "Hello {0.name}, fellow bot!"
default_settings = {
    "GREETING": [default_greeting],
    "ON": False,
    "LEAVE_ON": False,
    "LEAVE_CHANNEL": None,
    "GROUPED": False,
    "GOODBYE": [default_goodbye],
    "CHANNEL": None,
    "WHISPER": False,
    "BOTS_MSG": default_bot_msg,
    "BOTS_ROLE": None,
    "EMBED": False,
    "JOINED_TODAY": False,
    "MINIMUM_DAYS": 0,
    "DELETE_PREVIOUS_GREETING": False,
    "DELETE_AFTER_GREETING": None,
    "DELETE_PREVIOUS_GOODBYE": False,
    "DELETE_AFTER_GOODBYE": None,
    "LAST_GREETING": None,
    "FILTER_SETTING": None,
    "LAST_GOODBYE": None,
    "MENTIONS": {"users": True, "roles": False, "everyone": False},
    "GOODBYE_MENTIONS": {"users": True, "roles": False, "everyone": False},
    "EMBED_DATA": {
        "title": None,
        "colour": 0,
        "footer": None,
        "thumbnail": None,
        "image": None,
        "image_goodbye": None,
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

    __author__ = ["irdumb", "TrustyJAID"]
    __version__ = "2.4.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 144465786453, force_registration=True)
        self.config.register_guild(**default_settings)
        self.group_check = bot.loop.create_task(self.group_welcome())
        self.joined = {}
        self.today_count = {"now": datetime.utcnow()}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def group_welcome(self) -> None:
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            # log.debug("Checking for new welcomes")
            for guild_id, members in self.joined.items():
                if members:
                    await self.send_member_join(members, self.bot.get_guild(guild_id))
            self.joined = {}
            await asyncio.sleep(300)

    @commands.group()
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def welcomeset(self, ctx: commands.Context) -> None:
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
                "DELETE_PREVIOUS_GREETING": _("Previous greeting deleted "),
                "DELETE_PREVIOUS_GOODBYE": _("Previous goodbye deleted "),
                "DELETE_AFTER_GREETING": _("Greeting deleted after "),
                "DELETE_AFTER_GOODBYE": _("Goodbye deleted after "),
                "MINIMUM_DAYS": _("Minimum days old to welcome "),
                "WHISPER": _("Whisper "),
                "BOTS_MSG": _("Bots message "),
                "BOTS_ROLE": _("Bots role "),
                "EMBED": _("Embeds "),
            }
            msg = ""
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed(colour=await ctx.embed_colour())
                embed.set_author(name=_("Welcome settings for ") + guild.name)
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
                            msg += f"**{name}**:" + _(" None") + "\n"
                        continue
                    if attr == "BOTS_ROLE":
                        role = guild.get_role(guild_settings["BOTS_ROLE"])
                        if role is not None:
                            msg += f"**{name}**: {role.mention}\n"
                        else:
                            msg += f"**{name}**:" + _(" None") + "\n"
                        continue
                    else:
                        msg += f"**{name}**: {guild_settings[attr]}\n"
                embed.description = msg
                await ctx.send(embed=embed)

            else:
                msg = "```\n"
                for attr, name in setting_names.items():
                    msg += name + str(guild_settings[attr]) + "\n"
                msg += "```"
                await ctx.send(msg)

    @welcomeset.group(name="greeting", aliases=["welcome"])
    async def welcomeset_greeting(self, ctx: commands.Context) -> None:
        """
        Manage welcome messages
        """
        pass

    @welcomeset_greeting.command()
    @checks.mod_or_permissions(mention_everyone=True)
    @checks.bot_has_permissions(mention_everyone=True)
    async def allowedmentions(self, ctx: commands.Context, set_to: bool, *allowed) -> None:
        """
        Determine the bots allowed mentions for welcomes

        `<set_to>` What to set the allowed mentions to either `True` or `False`.
        `[allowed...]` must be either `everyone`, `users`, or `roles` and can include more than one.

        Note: This will only function on Red 3.4.0 or higher.
        """
        if not allowed:
            return await ctx.send(_("You must provide either `users`, `roles` or `everyone`."))
        for i in set(allowed):
            if i not in ["everyone", "users", "roles"]:
                return await ctx.send(_("You must provide either `users`, `roles` or `everyone`."))
        if (
            "everyone" in set(allowed)
            or "roles" in set(allowed)
            and not ctx.guild.me.guild_permissions.mention_everyone
        ):
            await ctx.send(
                _(
                    "I don't have mention everyone permissions so these settings may not work properly."
                )
            )
        async with self.config.guild(ctx.guild).MENTIONS() as mention_settings:
            for setting in set(allowed):
                mention_settings[setting] = set_to
        await ctx.send(
            _("Mention settings have been set to {set_to} for {settings}").format(
                set_to=str(set_to), settings=humanize_list(list(set(allowed)))
            )
        )

    @welcomeset_greeting.command(name="grouped")
    async def welcomeset_greeting_grouped(self, ctx: commands.Context, grouped: bool) -> None:
        """Set whether to group welcome messages"""
        await self.config.guild(ctx.guild).GROUPED.set(grouped)
        if grouped:
            await ctx.send(_("I will now group welcomes."))
        else:
            await ctx.send(_("I will no longer group welcomes."))

    @welcomeset_greeting.command(name="add")
    async def welcomeset_greeting_add(self, ctx: commands.Context, *, format_msg: str) -> None:
        """
        Adds a welcome message format for the guild to be chosen at random

        {0} is user
        {1} is guild
        {count} can be used to display number of users who have joined today.
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

    @welcomeset_greeting.command(name="del")
    async def welcomeset_greeting_del(self, ctx: commands.Context) -> None:
        """Removes a welcome message from the random message list"""
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).GREETING()
        msg = _("Choose a welcome message to delete:\n\n")
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))
        pred = MessagePredicate.valid_int(ctx)
        try:
            await self.bot.wait_for("message", check=pred, timeout=120)
        except asyncio.TimeoutError:
            return
        try:
            choice = guild_settings.pop(pred.result)
        except Exception:
            await ctx.send(_("That's not a number in the list :/"))
            return
        if not guild_settings:
            guild_settings = [default_greeting]
        await self.config.guild(guild).GREETING.set(guild_settings)
        await ctx.send(_("**This message was deleted:**\n") + str(choice))

    @welcomeset_greeting.command(name="list")
    async def welcomeset_greeting_list(self, ctx: commands.Context) -> None:
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
    async def welcomeset_greeting_toggle(self, ctx: commands.Context) -> None:
        """
        Turns on/off welcoming new users to the guild
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).ON()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now welcome new users to the guild."))
        else:
            await ctx.send(_("I will no longer welcome new users."))
        await self.config.guild(guild).ON.set(guild_settings)

    @welcomeset_greeting.command(name="deleteprevious")
    async def welcomeset_greeting_delete_previous(self, ctx: commands.Context) -> None:
        """
        Turns on/off deleting the previous welcome message when a user joins
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).DELETE_PREVIOUS_GREETING()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(
                _("I will now delete the previous welcome message when a new user joins.")
            )
        else:
            await ctx.send(
                _("I will stop deleting the previous welcome message when a new user joins.")
            )
        await self.config.guild(guild).DELETE_PREVIOUS_GREETING.set(guild_settings)

    @welcomeset_greeting.command(name="count")
    async def welcomeset_greeting_count(self, ctx: commands.Context) -> None:
        """
        Turns on/off showing how many users join each day.

        This resets 24 hours after the cog was loaded.
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).JOINED_TODAY()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now show how many people join the server each day."))
        else:
            await ctx.send(_("I will stop showing how many people join the server each day."))
        await self.config.guild(guild).JOINED_TODAY.set(guild_settings)

    @welcomeset_greeting.command(name="minimumage", aliases=["age"])
    async def welcomeset_greeting_minimum_days(self, ctx: commands.Context, days: int) -> None:
        """
        Set the minimum number of days a user account must be to show up in the welcome message

        `<days>` number of days old the account must be, set to 0 to not require this.
        """
        guild = ctx.message.guild
        if days < 0:
            days = 0
        await self.config.guild(guild).MINIMUM_DAYS.set(days)
        await ctx.send(
            _("I will now show users joining who are {days} days old.").format(days=days)
        )

    @welcomeset_greeting.command(name="filter")
    async def welcomeset_greeting_filter(
        self, ctx: commands.Context, replacement: Optional[str] = None
    ) -> None:
        """
        Set what to do when a username matches the bots filter.

        `[replacement]` replaces usernames that are found by cores filter with this word.

        If left blank, this will prevent welcome messages for usernames matching cores filter.

        """

        await self.config.guild(ctx.guild).FILTER_SETTING.set(replacement)
        has_filter = self.bot.get_cog("Filter")
        if replacement:
            await ctx.send(
                _(
                    "I will now replace usernames matching cores filter with `{replacement}`"
                ).format(replacement=replacement)
            )
            if not has_filter:
                await ctx.send(
                    _(
                        "Filter is not loaded, run `{prefix}load filter` and add "
                        "some words to filter for this to work"
                    ).format(prefix=ctx.clean_prefix)
                )
        else:
            await ctx.send(
                _("I will not post welcome messages for usernames that match cores filter.")
            )
            if not has_filter:
                await ctx.send(
                    _(
                        "Filter is not loaded, run `{prefix}load filter` and add "
                        "some words to filter for this to work"
                    ).format(prefix=ctx.clean_prefix)
                )

    @welcomeset_greeting.command(name="deleteafter")
    async def welcomeset_greeting_delete_after(
        self, ctx: commands.Context, delete_after: Optional[int] = None
    ) -> None:
        """
        Set the time after which a welcome message is deleted in seconds.

        Providing no input will set the bot to not delete after any time.
        """
        if delete_after:
            await ctx.send(
                _("I will now delete welcome messages after {time} seconds.").format(
                    time=delete_after
                )
            )
        else:
            await ctx.send(_("I will not delete welcome messages after a set time."))
        await self.config.guild(ctx.guild).DELETE_AFTER_GREETING.set(delete_after)

    @welcomeset_greeting.command(name="channel")
    async def welcomeset_greeting_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
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

    @welcomeset_greeting.command()
    async def test(self, ctx: commands.Context) -> None:
        """Test the welcome message deleted after 60 seconds"""
        await self.send_testing_msg(ctx)

    @welcomeset.group(name="goodbye", aliases=["leave"])
    async def welcomeset_goodbye(self, ctx: commands.Context) -> None:
        """
        Manage goodbye messages
        """
        pass

    @welcomeset_goodbye.command(name="allowedmentions")
    @checks.mod_or_permissions(mention_everyone=True)
    async def goodbye_allowedmentions(self, ctx: commands.Context, set_to: bool, *allowed) -> None:
        """
        Determine the bots allowed mentions for welcomes

        `<set_to>` What to set the allowed mentions to either `True` or `False`.
        `[allowed...]` must be either `everyone`, `users`, or `roles` and can include more than one.

        Note: This will only function on Red 3.4.0 or higher.
        """
        if not allowed:
            return await ctx.send(_("You must provide either `users`, `roles` or `everyone`."))
        for i in set(allowed):
            if i not in ["everyone", "users", "roles"]:
                return await ctx.send(_("You must provide either `users`, `roles` or `everyone`."))
        if (
            "everyone" in set(allowed)
            or "roles" in set(allowed)
            and not ctx.guild.me.guild_permissions.mention_everyone
        ):
            await ctx.send(
                _(
                    "I don't have mention everyone permissions so these settings may not work properly."
                )
            )
        async with self.config.guild(ctx.guild).GOODBYE_MENTIONS() as mention_settings:
            for setting in set(allowed):
                mention_settings[setting] = set_to
        await ctx.send(
            _("Mention settings have been set to {set_to} for {settings}").format(
                set_to=str(set_to), settings=humanize_list(list(set(allowed)))
            )
        )

    @welcomeset_goodbye.command(name="add")
    async def welcomeset_goodbye_add(self, ctx: commands.Context, *, format_msg: str) -> None:
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

    @welcomeset_goodbye.command(name="del")
    async def welcomeset_goodbye_del(self, ctx: commands.Context) -> None:
        """
        Removes a goodbye message from the random message list
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).GOODBYE()
        msg = _("Choose a goodbye message to delete:\n\n")
        for c, m in enumerate(guild_settings):
            msg += "  {}. {}\n".format(c, m)
        for page in pagify(msg, ["\n", " "], shorten_by=20):
            await ctx.send("```\n{}\n```".format(page))
        pred = MessagePredicate.valid_int(ctx)
        try:
            await self.bot.wait_for("message", check=pred, timeout=120)
        except asyncio.TimeoutError:
            return
        try:
            choice = guild_settings.pop(pred.result)
        except Exception:
            await ctx.send(_("That's not a number in the list :/"))
            return
        if not guild_settings:
            guild_settings = [default_goodbye]
        await self.config.guild(guild).GOODBYE.set(guild_settings)
        await ctx.send(_("**This message was deleted:**\n") + str(choice))

    @welcomeset_goodbye.command(name="list")
    async def welcomeset_goodbye_list(self, ctx: commands.Context) -> None:
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
    async def welcomeset_goodbye_toggle(self, ctx: commands.Context) -> None:
        """
        Turns on/off goodbying users who leave to the guild
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).LEAVE_ON()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now say goodbye when a member leaves the server."))
        else:
            await ctx.send(_("I will no longer say goodbye to members leaving the server."))
        await self.config.guild(guild).LEAVE_ON.set(guild_settings)

    @welcomeset_goodbye.command(name="channel")
    async def welcomeset_goodbye_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
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

    @welcomeset_goodbye.command(name="deleteprevious")
    async def welcomeset_goodbye_delete_previous(self, ctx: commands.Context) -> None:
        """
        Turns on/off deleting the previous welcome message when a user joins
        """
        guild = ctx.message.guild
        guild_settings = await self.config.guild(guild).DELETE_PREVIOUS_GOODBYE()
        guild_settings = not guild_settings
        if guild_settings:
            await ctx.send(_("I will now delete the previous goodbye message when user leaves."))
        else:
            await ctx.send(
                _("I will stop deleting the previous goodbye message when a user leaves.")
            )
        await self.config.guild(guild).DELETE_PREVIOUS_GOODBYE.set(guild_settings)

    @welcomeset_goodbye.command(name="deleteafter")
    async def welcomeset_goodbye_delete_after(
        self, ctx: commands.Context, delete_after: Optional[int] = None
    ) -> None:
        """
        Set the time after which a welcome message is deleted in seconds.

        Providing no input will set the bot to not delete after any time.
        """
        if delete_after:
            await ctx.send(
                _("I will now delete goodbye messages after {time} seconds.").format(
                    time=delete_after
                )
            )
        else:
            await ctx.send(_("I will not delete welcome messages after a set time."))
        await self.config.guild(ctx.guild).DELETE_AFTER_GOODBYE.set(delete_after)

    @welcomeset_goodbye.command(name="test")
    async def welcomeset_goodbye_test(self, ctx: commands.Context) -> None:
        """Test the goodbye message deleted after 60 seconds"""
        await self.send_testing_msg(ctx, leave=True)

    @welcomeset.group(name="bot")
    async def welcomeset_bot(self, ctx: commands.Context) -> None:
        """
        Special welcome for bots
        """
        pass

    @welcomeset_bot.command(name="test")
    async def welcomeset_bot_test(self, ctx: commands.Context) -> None:
        """Test the bot joining message"""
        await self.send_testing_msg(ctx, bot=True)

    @welcomeset_bot.command(name="msg")
    async def welcomeset_bot_msg(
        self, ctx: commands.Context, *, format_msg: Optional[str] = None
    ) -> None:
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

    # TODO: Check if have permissions
    @welcomeset_bot.command(name="role")
    async def welcomeset_bot_role(
        self, ctx: commands.Context, *, role: Optional[discord.Role] = None
    ) -> None:
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
    async def whisper(self, ctx: commands.Context, choice: Optional[str] = None) -> None:
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
    async def _embed(self, ctx: commands.Context) -> None:
        """
        Set various embed options
        """
        pass

    @_embed.command()
    async def toggle(self, ctx: commands.Context) -> None:
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

    @_embed.command(aliases=["color"])
    async def colour(self, ctx: commands.Context, colour: discord.Colour) -> None:
        """
        Set the embed colour

        This accepts hex codes and integer value colours
        """
        await self.config.guild(ctx.guild).EMBED_DATA.colour.set(colour.value)
        await ctx.tick()

    @_embed.command()
    async def title(self, ctx: commands.Context, *, title: str = "") -> None:
        """
        Set the embed title

        {0} is user
        {1} is guild
        {count} can be used to display number of users who have joined today.
        """
        await self.config.guild(ctx.guild).EMBED_DATA.title.set(title[:256])
        await ctx.tick()

    @_embed.command()
    async def footer(self, ctx: commands.Context, *, footer: str = "") -> None:
        """
        Set the embed footer

        {0} is user
        {1} is guild
        {count} can be used to display number of users who have joined today.
        """
        await self.config.guild(ctx.guild).EMBED_DATA.footer.set(footer[:256])
        await ctx.tick()

    @_embed.command()
    async def thumbnail(self, ctx: commands.Context, link: Optional[str] = None) -> None:
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
    async def icon(self, ctx: commands.Context, link: Optional[str] = None) -> None:
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

    @_embed.group(name="image")
    async def _image(self, ctx: commands.Context) -> None:
        """
        Set embed image options
        """
        pass

    @_image.command(name="greeting")
    async def image_greeting(self, ctx: commands.Context, link: Optional[str] = None) -> None:
        """
        Set the embed image link for greetings

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
            await ctx.send(_("Greeting image cleared."))

    @_image.command(name="goodbye")
    async def image_goodbye(self, ctx: commands.Context, link: Optional[str] = None) -> None:
        """
        Set the embed image link for goodbyes

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
                await self.config.guild(ctx.guild).EMBED_DATA.image_goodbye.set(
                    link_search.group(0)
                )
                await ctx.tick()
            elif link in ["author", "avatar"]:
                await self.config.guild(ctx.guild).EMBED_DATA.image_goodbye.set("avatar")
                await ctx.tick()
            elif link in ["server", "guild"]:
                await self.config.guild(ctx.guild).EMBED_DATA.image_goodbye.set("guild")
                await ctx.tick()
            elif link == "splash":
                await self.config.guild(ctx.guild).EMBED_DATA.image_goodbye.set("splash")
                await ctx.tick()
            else:
                await ctx.send(
                    _("That's not a valid option. You must provide a link, `avatar` or `server`.")
                )
        else:
            await self.config.guild(ctx.guild).EMBED_DATA.image_goodbye.set(None)
            await ctx.send(_("Goodbye image cleared."))

    @_embed.command()
    async def timestamp(self, ctx: commands.Context) -> None:
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
    async def author(self, ctx: commands.Context) -> None:
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
    async def mention(self, ctx: commands.Context) -> None:
        """
        Toggle mentioning the user when they join

        This will add a mention outside the embed so they actually get the mention.
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
