from random import choice, randint
import discord
import asyncio

import datetime
import aiohttp
import re
import itertools
from io import BytesIO
from redbot.core import commands
from redbot.core import checks, bank, Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from discord.ext.commands.converter import IDConverter
from discord.ext.commands.converter import _get_from_guilds
from discord.ext.commands.errors import BadArgument
from typing import Union, Optional


_ = Translator("ServerStats", __file__)


class FuzzyMember(IDConverter):
    """
    This will accept user ID's, mentions, and perform a fuzzy search for 
    members within the guild and return a list of member objects
    matching partial names

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """

    async def convert(self, ctx, argument):
        bot = ctx.bot
        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]+)>$", argument)
        guild = ctx.guild
        result = []
        if match is None:
            # Not a mention
            if guild:
                for m in guild.members:
                    if argument.lower() in m.display_name.lower():
                        # display_name so we can get the nick of the user first
                        # without being NoneType and then check username if that matches
                        # what we're expecting
                        result.append(m)
                        continue
                    if argument.lower() in m.name.lower():
                        result.append(m)
                        continue
        else:
            user_id = int(match.group(1))
            if guild:
                result.append(guild.get_member(user_id))
            else:
                result.append(_get_from_guilds(bot, "get_member", user_id))

        if result is None:
            raise BadArgument('Member "{}" not found'.format(argument))

        return result


class GuildConverter(IDConverter):
    """
    This is a guild converter for fuzzy guild names which is used throughout
    this cog to search for guilds by part of their name and will also
    accept guild ID's

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """

    async def convert(self, ctx, argument):
        bot = ctx.bot
        match = self._get_id_match(argument)
        result = None
        if ctx.author.id != ctx.bot.owner_id:
            # Don't need to be snooping other guilds unless we're
            # the bot owner
            return
        if match is None:
            # Not a mention
            for g in bot.guilds:
                if argument.lower() in g.name.lower():
                    # display_name so we can get the nick of the user first
                    # without being NoneType and then check username if that matches
                    # what we're expecting
                    result = g
        else:
            guild_id = int(match.group(1))
            result = bot.get_guild(guild_id)

        if result is None:
            raise BadArgument('Guild "{}" not found'.format(argument))

        return result


@cog_i18n(_)
class ServerStats(getattr(commands, "Cog", object)):
    """
        Gather useful information about servers the bot is in
        A lot of commands are bot owner only
    """

    def __init__(self, bot):
        self.bot = bot
        default_global = {"join_channel": None}
        self.config = Config.get_conf(self, 54853421465543)
        self.config.register_global(**default_global)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def avatar(self, ctx, *members: Optional[FuzzyMember]):
        """
            Display a users avatar in chat
        """

        embed_list = []
        if not members:
            members = [[ctx.author]]
        for member in list(itertools.chain.from_iterable(members)):

            em = discord.Embed(title=_("**Avatar**"), colour=member.colour)
            if member.is_avatar_animated():
                url = member.avatar_url_as(format="gif")
            if not member.is_avatar_animated():
                url = member.avatar_url_as(static_format="png")
            em.set_image(url=url)
            em.set_author(
                name="{}#{}".format(member.name, member.discriminator), icon_url=url, url=url
            )
            embed_list.append(em)
        if not embed_list:
            await ctx.send(_("That user does not appear to exist on this server."))
            return
        if len(embed_list) > 1:
            await menu(ctx, embed_list, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embed_list[0])

    async def on_guild_join(self, guild):
        """Build and send a message containing serverinfo when the bot joins a new server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        em = await self.guild_embed(guild)
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _(
            "{bot} has joined a server!\n "
            "That's {num} servers now! \n"
            "Server created {since}. "
            "That's over {passed} days ago!"
        ).format(
            bot=channel.guild.me.mention,
            num=len(self.bot.guilds),
            since=guild.created_at.strftime("%d %b %Y %H:%M"),
            passed=passed,
        )
        em.description = created_at
        await channel.send(embed=em)

    async def guild_embed(self, guild):
        """
            Builds the guild embed information used throughout the cog
        """
        online = len(
            [
                m.status
                for m in guild.members
                if m.status == discord.Status.online or m.status == discord.Status.idle
            ]
        )
        total_users = len(guild.members)
        text_channels = len([x for x in guild.text_channels])
        voice_channels = len([x for x in guild.voice_channels])
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _("Server created {since}. " "That's over {passed} days ago!").format(
            since=guild.created_at.strftime("%d %b %Y %H:%M"), passed=passed
        )

        colour = guild.roles[-1].colour

        em = discord.Embed(description=created_at, colour=colour, timestamp=guild.created_at)
        em.add_field(name=_("Region"), value=str(guild.region))
        em.add_field(name=_("Users"), value="{}/{}".format(online, total_users))
        em.add_field(name=_("Text Channels"), value=text_channels)
        em.add_field(name=_("Voice Channels"), value=voice_channels)
        em.add_field(name=_("Roles"), value=len(guild.roles))
        em.add_field(
            name=_("Owner"), value="{} | {}".format(str(guild.owner), guild.owner.mention)
        )
        if guild.features:
            em.add_field(
                name=_("Guild Features"), value=", ".join(feature for feature in guild.features)
            )
        em.set_footer(text=_("Guild ID: ") + "{}".format(guild.id))
        em.set_author(name=guild.name, icon_url=guild.icon_url_as(format="png"))
        em.set_thumbnail(url=guild.icon_url_as(format="png"))
        return em

    async def on_guild_remove(self, guild):
        """Build and send a message containing serverinfo when the bot leaves a server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        em = await self.guild_embed(guild)
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _(
            "{bot} has left a server!\n "
            "That's {num} servers now! \n"
            "Server created {since}. "
            "That's over {passed} days ago!"
        ).format(
            bot=channel.guild.me.mention,
            num=len(self.bot.guilds),
            since=guild.created_at.strftime("%d %b %Y %H:%M"),
            passed=passed,
        )
        em.description = created_at

        await channel.send(embed=em)

    @commands.command()
    async def emoji(self, ctx, emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        """
            Post a large size emojis in chat
        """
        await ctx.channel.trigger_typing()
        if type(emoji) in [discord.emoji.PartialEmoji, discord.Emoji]:
            ext = "gif" if emoji.animated else "png"
            url = "https://cdn.discordapp.com/emojis/{id}.{ext}?v=1".format(id=emoji.id, ext=ext)
            filename = "{name}.{ext}".format(name=emoji.name, ext=ext)
        else:
            """https://github.com/glasnt/emojificate/blob/master/emojificate/filter.py"""
            cdn_fmt = "https://twemoji.maxcdn.com/2/72x72/{codepoint:x}.png"
            url = cdn_fmt.format(codepoint=ord(emoji))
            filename = "emoji.png"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    image = BytesIO(await resp.read())
        except:
            await ctx.send(_("That doesn't appear to be a valid emoji"))
            return
        file = discord.File(image, filename=filename)
        await ctx.send(file=file)

    @commands.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def topic(self, ctx, channel: Optional[discord.TextChannel], *, topic: str = ""):
        """
            Sets a specified channels topic
            
            `channel` is optional and if not supplied will use the current channel
            Note: The maximum number of characters is 1024
        """
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(ctx.author).manage_messages:
            return
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
        await channel.edit(topic=topic[:1024])
        await ctx.tick()

    async def ask_for_invite(self, ctx):
        """
            Ask the user to provide an invite link
            if reinvite is True
        """
        check = lambda m: m.author == ctx.message.author
        msg_send = _(
            "Please provide a reinvite link/message.\n" "Type `exit` for no invite link/message."
        )
        invite_check = await ctx.send(msg_send)
        try:
            msg = await ctx.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await msg.edit(content=_("I Guess not."))
            return None
        if "exit" in msg.content:
            return None
        else:
            return msg.content

    async def get_members_since(self, ctx, days: int, role: discord.Role):
        now = datetime.datetime.utcnow()
        after = now - datetime.timedelta(days=days)
        if role is None:
            member_list = [m for m in ctx.guild.members if m.top_role < ctx.me.top_role]
        else:
            member_list = [m for m in role.members if m.top_role < ctx.me.top_role]
        user_list = []
        for channel in ctx.guild.text_channels:
            if not channel.permissions_for(ctx.me).read_message_history:
                continue
            async for message in channel.history(limit=None, after=after):
                if message.author in member_list:
                    member_list.remove(message.author)
        return member_list

    @commands.group()
    @checks.bot_has_permissions(add_reactions=True)
    async def pruneroles(self, ctx):
        """
            Perform various actions on users who haven't spoken in x days

            Note: This will only check if a user has talked in the past x days whereas 
            discords built in Prune checks online status
        """
        pass

    @pruneroles.command()
    async def list(self, ctx, days: int, role: discord.Role = None):
        """
            List the users who have not talked in x days
        """
        member_list = await self.get_members_since(ctx, days, role)
        x = [member_list[i : i + 10] for i in range(0, len(member_list), 10)]
        msg_list = []
        count = 1
        for page in x:
            if ctx.channel.permissions_for(ctx.me).embed_links:
                em = discord.Embed(colour=await ctx.embed_colour())
                if role:
                    em.add_field(name=_("Role"), value=role.mention)
                else:
                    estimate = await ctx.guild.estimate_pruned_members(days=days)
                    em.add_field(name=_("Discord Estimate"), value=str(estimate))
                em.description = "\n".join(m.mention for m in page)
                em.set_author(name=f"{ctx.guild.name}", icon_url=ctx.guild.icon_url)
                em.title = _("Estimated members to be pruned ") + str(len(member_list))
                em.set_footer(text="Page {} of {}".format(count, len(x)))
                count += 1
                msg_list.append(em)
            else:

                if not role:
                    estimate = await ctx.guild.estimate_pruned_members(days=days)
                    role_msg = _("Discord Estimate: {estimate}").format(estimate=estimate)
                else:
                    role_msg = _("Role: {role.name}").format(role=role)
                members = "\n".join(str(m) for m in page)
                msg = _(
                    "Estimated members to be pruned {num_members}\n" "{role}\n{members}\n"
                ).format(num_members=len(member_list), role=role_msg, members=members)

                msg += "Page {} of {}".format(count, len(x))
                count += 1
                msg_list.append(msg)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @pruneroles.command()
    @checks.mod_or_permissions(kick_members=True)
    @checks.bot_has_permissions(kick_members=True, add_reactions=True)
    async def kick(self, ctx, days: int, role: discord.Role = None, reinvite: bool = True):
        """
            Kick users from the server who have been inactive for x days
            
            `days` is the number of days since last seen talking on the server
            `role` is the specified role you would like to kick defaults to everyone
            `reinvite` True/False whether to try to send the user a message before kicking
        """
        if role is not None and role >= ctx.me.top_role:
            msg = _("That role is higher than my " "role so I cannot kick those members.")
            await ctx.send(msg)
            return
        member_list = await self.get_members_since(ctx, days, role)
        send_msg = str(len(member_list)) + _(
            " estimated users to kick. " "Would you like to kick them?"
        )
        msg = await ctx.send(send_msg)
        check = lambda r, u: u == ctx.message.author and r.emoji in ["✅", "❌"]
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if reaction.emoji == "✅":
            link = await self.ask_for_invite(ctx)
            no_invite = []
            for member in member_list:
                if link:
                    try:
                        await member.send(link)
                    except:
                        no_invite.append(member.id)
                await member.kick(reason=_("Kicked due to inactivity."))
            if link and len(no_invite) > 0:
                msg = str(len(no_invite)) + _(" users could not be DM'd an invite link")
                await ctx.send(msg)
        else:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        await ctx.send(_("Done."))

    @pruneroles.command()
    @checks.mod_or_permissions(manage_roles=True)
    @checks.bot_has_permissions(manage_roles=True, add_reactions=True)
    async def add(self, ctx, days: int, *new_roles: discord.Role):
        """
            Give roles to users who haven't spoken in x days
            
            `days` is the number of days since last seen talking on the server
            `new_roles` The new roles to apply to a user who is inactive
        """
        if any([r >= ctx.me.top_role for r in new_roles]):
            msg = _(
                "At least one of those roles is higher than my "
                "role so I cannot add those roles."
            )
            await ctx.send(msg)
            return
        member_list = await self.get_members_since(ctx, days, None)
        send_msg = str(len(member_list)) + _(
            " estimated users to give the role. " "Would you like to reassign their roles now?"
        )
        msg = await ctx.send(send_msg)
        check = lambda r, u: u == ctx.message.author and r.emoji in ["✅", "❌"]
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if reaction.emoji == "✅":
            for member in member_list:
                roles = list(set(member.roles + list(new_roles)))
                await member.edit(roles=roles, reason=_("Given role due to inactivity."))
        else:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        await ctx.send(_("Done."))

    @pruneroles.command()
    @checks.mod_or_permissions(manage_roles=True)
    @checks.bot_has_permissions(manage_roles=True, add_reactions=True)
    async def remove(self, ctx, days: int, *removed_roles: discord.Role):
        """
            Remove roles from users who haven't spoken in x days
            
            `days` is the number of days since last seen talking on the server
            `role` is the specified role you would like to remove roles defaults to everyone
            `removed_roles` the roles to remove from inactive users
        """
        if any([r >= ctx.me.top_role for r in removed_roles]):
            msg = _(
                "At least one of those roles is higher than my "
                "role so I cannot remove those roles."
            )
            await ctx.send(msg)
            return
        member_list = await self.get_members_since(ctx, days, None)
        send_msg = str(len(member_list)) + _(
            " estimated users to remove their roles. "
            "Would you like to reassign their roles now?"
        )
        msg = await ctx.send(send_msg)
        check = lambda r, u: u == ctx.message.author and r.emoji in ["✅", "❌"]
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if reaction.emoji == "✅":
            for member in member_list:
                if member.id != 261320113444225025:
                    continue
                roles = list(set(member.roles) - set(removed_roles))
                await member.edit(roles=roles, reason=_("Roles removed due to inactivity."))
        else:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        await ctx.send(_("Done."))

    @commands.command()
    @checks.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def setguildjoin(self, ctx, channel: discord.TextChannel = None):
        """
            Set a channel to see new servers the bot is joining
        """
        if channel is None:
            channel = ctx.message.channel
        await self.config.join_channel.set(channel.id)
        msg = _("Posting new servers and left servers in ") + channel.mention
        await ctx.send(msg)

    @commands.command()
    @checks.is_owner()
    async def removeguildjoin(self, ctx):
        """
            Stop bots join/leave server messages
        """
        await self.config.join_channel.set(None)
        await ctx.send(_("No longer posting joined or left servers."))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def checkcheater(self, ctx, user_id: int):
        """
            Checks for possible cheaters abusing the global bank and server powers
        """
        is_cheater = False
        for guild in self.bot.guilds:
            print(guild.owner.id)
            if guild.owner.id == user_id:
                is_cheater = True
                msg = guild.owner.mention + _(" is guild owner of ") + guild.name
                await ctx.send(msg)
        if not is_cheater:
            await ctx.send(_("Not a cheater"))

    @commands.command(hidden=True)
    async def whois(self, ctx, member: Union[int, discord.User]):
        """
            Display servers a user shares with the bot

            `member` can be a user ID or mention
        """
        if type(member) == int:
            try:
                member = await self.bot.get_user_info(member)
            except discord.errors.NotFound:
                await ctx.send(str(member) + _(" doesn't seem to be a discord user."))
                return
        if await self.bot.is_owner(ctx.author):
            guild_list = []
            for guild in self.bot.guilds:
                members = [member.id for member in guild.members]
                if member.id in members:
                    guild_list.append(guild)
            if guild_list != []:
                msg = "{} ({}) ".format(member, member.id) + _("is on:\n")
                for guild in guild_list:
                    msg += "{} ({})\n".format(guild.name, guild.id)
                for page in pagify(msg, ["\n"]):
                    await ctx.send(page)
            else:
                msg = f"{member} ({member.id}) " + _("is not in any shared servers!")
                await ctx.send(msg)
        else:
            guild_list = []
            for guild in self.bot.guilds:
                members = [member.id for member in guild.members]
                if member.id in members and ctx.author.id in members:
                    guild_list.append(guild)
            if guild_list != []:
                msg = "{} ({}) ".format(member, member.id) + _("is on:\n")
                for guild in guild_list:
                    msg += "{} ({})\n".format(guild.name, guild.id)
                for page in pagify(msg, ["\n"]):
                    await ctx.send(page)
            else:
                msg = f"{member} ({member.id}) " + _("is not in any shared servers!")
                await ctx.send(msg)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def topservers(self, ctx):
        """
            Lists servers by number of users and shows number of users
        """
        owner = ctx.author
        guilds = sorted(list(self.bot.guilds), key=lambda s: len(s.members), reverse=True)
        msg = ""
        for i, server in enumerate(guilds):
            msg += "{}: {}\n".format(server.name, len(server.members))

        for page in pagify(msg, ["\n"]):
            await ctx.send(page)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def newservers(self, ctx):
        """
            Lists servers by when the bot was added to the server
        """
        owner = ctx.author
        guilds = sorted(list(self.bot.guilds), key=lambda s: s.me.joined_at)
        msg = ""
        for i, server in enumerate(guilds):
            msg += "{}: {} ({})\n".format(i, server.name, server.id)

        for page in pagify(msg, ["\n"]):
            await ctx.send(page)

    @commands.command()
    @checks.mod_or_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, time: int = 0, channel: discord.TextChannel = None):
        """
            Set a channels slowmode setting

            `time` must be a number between 0 and 120
            `channel` is the channel you want to set slowmode on defaults to current channel
        """
        if channel is None:
            channel = ctx.channel
        if time < 0 or time > 120:
            await ctx.send(_("You can only set a number between 0 and 120"))
            return
        await channel.edit(slowmode_delay=time)
        msg = _("Slowmode set to `{time}` in {channel}").format(time=time, channel=channel.mention)
        await ctx.send(msg)

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def guildedit(self, ctx):
        """Edit various guild settings"""
        pass

    @guildedit.command(name="name")
    async def guild_name(self, ctx, *, name:str):
        """
        Change the server name
        """
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(name=name, reason=reason)
        except Exception as e:
            print(e)
            pass

    @guildedit.command(name="verificationlevel", aliases=["verification"])
    async def verifivation_level(self, ctx, *, level:str):
        """
            Modify the guilds verification level

            `level` must be one of:
            `none`, `low`, `medium`, `table flip`(`high`), or `double table flip`(`extreme`) 
        """

        levels = {
            "none":discord.VerificationLevel.none,
            "low":discord.VerificationLevel.low,
            "medium":discord.VerificationLevel.medium,
            "high":discord.VerificationLevel.high,
            "table flip":discord.VerificationLevel.high,
            "extreme":discord.VerificationLevel.extreme,
            "double table flip":discord.VerificationLevel.extreme
        }
        reason = _("Requested by {author}").format(author=ctx.author)
        if level.lower() not in levels:
            await ctx.send(_("`{}` is not a proper verification level.").format(level))
            return
        try:
            await ctx.guild.edit(verification_level=levels[level], reason=reason)
        except Exception as e:
            print(e)
            pass

    @guildedit.command(name="systemchannel", aliases=["welcomechannel"])
    async def system_channel(self, ctx, channel:discord.TextChannel=None):
        """
        Change the system channel

        This is the default discord welcome channel.
        """
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(system_channel=channel, reason=reason)
        except Exception as e:
            print(e)
            pass

    @guildedit.command(name="afkchannel")
    async def afk_channel(self, ctx, channel:discord.VoiceChannel=None):
        """
        Change the servers AFK voice channel

        Defaults to no AFK channel.
        """
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(afk_channel=channel, reason=reason)
        except Exception as e:
            print(e)
            pass

    @guildedit.command(name="afktimeout")
    async def afk_timeout(self, ctx, timeout:int):
        """
        Change the servers AFK timeout

        `timeout` must be a value of 60, 300, 900, 1800, or 3600.
        """
        if timeout not in [60, 300, 900, 1800, 3600]:
            await ctx.send(_("`timeout` must be a value of 60, 300, 900, 1800, or 3600."))
            return
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(afk_timeout=timeout, reason=reason)
        except Exception as e:
            print(e)
            pass

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def topmembers(self, ctx, number: Optional[int] = 10, guild: GuildConverter = None):
        """
            Lists top members on the server by join date

            `number` optional[int] number of members to display at a time maximum of 50
            `guild` can be either the server ID or name
        """
        guild = ctx.guild
        if not guild:
            guild = ctx.guild
        if number > 50:
            number = 50
        if number < 10:
            number = 10
        member_list = sorted(guild.members, key=lambda m: m.joined_at)
        is_embed = ctx.channel.permissions_for(ctx.me).embed_links
        x = [member_list[i : i + number] for i in range(0, len(member_list), number)]
        msg_list = []
        for page in x:
            header_msg = (
                "__**" + _("First ") + str(number) + _(" members of ") + f"{guild.name}**__\n"
            )
            msg = ""
            for member in page:
                if is_embed:
                    msg += f"{member_list.index(member)+1}. {member.mention}\n"

                else:
                    msg += f"{member_list.index(member)+1}. {member.name}\n"
            if is_embed:
                embed = discord.Embed(description=msg)
                embed.set_author(name=guild.name + _(" first members"), icon_url=guild.icon_url)
                msg_list.append(embed)

            else:
                msg_list.append(header_msg + msg)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @commands.command()
    @checks.is_owner()
    async def listchannels(self, ctx, *, guild: GuildConverter = None):
        """
            Lists channels and their position and ID for a server

            `guild` can be either the server ID or name
        """

        if not guild:
            guild = ctx.guild
        channels = {}
        msg = "__**{}({})**__\n".format(guild.name, guild.id)
        for category in guild.by_category():
            if category[0] is not None:
                word = _("Position")
                msg += "{0} ({1}): {2} {3}\n".format(
                    category[0].mention, category[0].id, word, category[0].position
                )
            for channel in category[1]:
                word = _("Position")
                msg += "{0} ({1}): {2} {3}\n".format(
                    channel.mention, channel.id, word, channel.position
                )
        for page in pagify(msg, ["\n"]):
            await ctx.send(page)

    async def guild_menu(
        self, ctx, post_list: list, message: discord.Message = None, page=0, timeout: int = 30
    ):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""

        guild = post_list[page]
        em = await self.guild_embed(guild)

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
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
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
                return await self.guild_menu(
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
                return await self.guild_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            else:
                return await message.delete()

    @commands.command()
    @checks.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def getguild(self, ctx, *, guild: GuildConverter = None):
        """
            Display info about servers the bot is on

            `guild_name` can be either the server ID or partial name
        """
        page = 0
        if guild:
            page = ctx.bot.guilds.index(guild)
        await self.guild_menu(ctx, ctx.bot.guilds, None, page)

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def nummembers(self, ctx, *, guild: GuildConverter = None):
        """
            Display number of users on a server

            `guild_name` can be either the server ID or partial name
        """
        if not guild:
            guild = ctx.guild
        await ctx.send("{} has {} members.".format(guild.name, len(guild.members)))

    @commands.command(aliases=["rolestats"])
    @checks.mod_or_permissions(manage_messages=True)
    async def getroles(self, ctx, *, guild: GuildConverter = None):
        """
            Displays all roles their ID and number of members in order of
            hierarchy

            `guild_name` can be either the server ID or partial name
        """
        if not guild:
            guild = ctx.guild
        msg = ""
        for role in sorted(guild.roles, reverse=True):
            if ctx.channel.permissions_for(ctx.me).embed_links and guild is ctx.guild:
                msg += f"{role.mention} ({role.id}): {len(role.members)}\n"
            else:
                msg += f"{role.name} ({role.id}): {len(role.members)}\n"
        msg_list = []
        for page in pagify(msg, ["\n"]):
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed()
                embed.description = page
                embed.set_author(name=guild.name + _("Roles"), icon_url=guild.icon_url)
                msg_list.append(embed)
            else:
                msg_list.append(page)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    async def check_highest(self, data):
        highest = 0
        users = 0
        for user, value in data.items():
            if value > highest:
                highest = value
                users = user
        return highest, users

    @commands.command(name="getreactions", aliases=["getreaction"])
    @checks.mod_or_permissions(manage_messages=True)
    async def get_reactions(self, ctx, message_id: int, channel: discord.TextChannel = None):
        """
            Gets a list of all reactions from specified message and displays the user ID,
            Username, and Discriminator and the emoji name.
        """
        if channel is None:
            channel = ctx.message.channel
        msg = await channel.get_message(message_id)
        new_msg = ""
        for reaction in msg.reactions:
            async for user in reaction.users():
                if type(reaction.emoji) is not str:
                    new_msg += "{} {}#{} {}\n".format(
                        user.id, user.name, user.discriminator, reaction.emoji.name
                    )
                else:
                    new_msg += "{} {}#{} {}\n".format(
                        user.id, user.name, user.discriminator, reaction.emoji
                    )
        for page in pagify(new_msg, shorten_by=20):
            await ctx.send("```py\n{}\n```".format(page))

    @commands.command(aliases=["serverstats"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(embed_links=True)
    async def server_stats(
        self, ctx, limit: Optional[int] = None, *, guild: GuildConverter = None
    ):
        """
            Gets total messages on the server and displays each channel 
            separately as well as the user who has posted the most in each channel

            `limit` must be a number of messages to check, defaults to all messages
            Note: This is a very slow function and may take some time to complete
        """
        if not guild:
            guild = ctx.guild
        channel = ctx.message.channel
        total_msgs = 0
        msg = ""
        total_contribution = {m: 0 for m in guild.members}
        if limit is None or limit > 1000:
            warning_msg = await ctx.send(_("This might take a while!"))
        else:
            warning_msg = None
        async with ctx.channel.typing():
            for chn in guild.channels:
                channel_msgs = 0
                try:
                    channel_contribution = {m: 0 for m in chn.members}
                    async for message in chn.history(limit=limit):
                        author = message.author
                        if author.discriminator == "0000" and author.bot:
                            continue
                        channel_msgs += 1
                        total_msgs += 1
                        if author not in total_contribution:
                            total_contribution[author] = 0
                        if author not in channel_contribution:
                            channel_contribution[author] = 0
                        channel_contribution[author] += 1
                        total_contribution[author] += 1
                    highest, user = await self.check_highest(channel_contribution)
                    if guild is ctx.guild:
                        msg += (
                            f"{chn.mention}: "
                            + ("Total Messages:")
                            + f"**{channel_msgs}** "
                            + _("most posts by ")
                            + f"{user.mention} **{highest}**\n"
                        )
                    else:
                        msg += (
                            f"{chn.mention}: "
                            + ("Total Messages:")
                            + f"**{channel_msgs}** "
                            + _("most posts by ")
                            + f"{user} **{highest}**\n"
                        )
                except discord.errors.Forbidden:
                    pass
                except AttributeError:
                    pass
            highest, user = await self.check_highest(total_contribution)
            if guild is ctx.guild:
                new_msg = (
                    f"__{guild.name}__: "
                    + _("Total Messages:")
                    + f"**{total_msgs}** "
                    + _("Most posts by ")
                    + f"{user.mention} **{highest}**\n{msg}"
                )
            else:
                new_msg = (
                    f"__{guild.name}__: "
                    + _("Total Messages:")
                    + f"**{total_msgs}** "
                    + _("Most posts by ")
                    + f"{user} **{highest}**\n{msg}"
                )

            x = sorted(total_contribution.items(), key=lambda x: x[1], reverse=True)
            x = [x[i : i + 10] for i in range(0, len(x), 10)]
            msg_list = []
            for page in x:
                em = discord.Embed(colour=await ctx.embed_colour())
                em.title = _("Most posts on the server")
                em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
                pg_count = 0
                for chn_page in pagify(new_msg, ["\n"], page_length=1024):
                    if pg_count == 0:
                        em.description = chn_page
                    else:
                        em.add_field(name=_("Most posts (continued)"), value=chn_page)
                    pg_count += 1
                if guild is ctx.guild:
                    members = "\n".join(f"{k.mention}: {v}" for k, v in page)
                    em.add_field(name=_("Members List"), value=members)
                else:
                    members = "\n".join(f"{k}: {v}" for k, v in page)
                    em.add_field(name=_("Members List"), value=members)
                msg_list.append(em)
            if warning_msg:
                await warning_msg.delete()
            await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @commands.command(aliases=["channelstats"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def channel_stats(
        self, ctx, limit: Optional[int] = None, channel: discord.TextChannel = None
    ):
        """
            Gets total messages in a specific channel as well as the user who
            has posted the most in that channel

            `limit` must be a number of messages to check, defaults to all messages
            Note: This can be a very slow function and may take some time to complete
        """
        if not channel:
            channel = ctx.channel
        total_msgs = 0
        msg = ""
        warning_msg = None
        if limit is None or limit > 1000:
            warning_msg = await ctx.send(_("This might take a while!"))
        else:
            warning_msg = None
        async with ctx.channel.typing():
            channel_msgs = 0
            channel_contribution = {}
            try:
                async for message in channel.history(limit=limit):
                    author = message.author
                    channel_msgs += 1
                    total_msgs += 1
                    if author not in channel_contribution:
                        channel_contribution[author] = 1
                    else:
                        channel_contribution[author] += 1
                highest, user = await self.check_highest(channel_contribution)
                msg += (
                    f"{channel.mention}: "
                    + ("Total Messages:")
                    + f"**{channel_msgs}** "
                    + _("most posts by ")
                    + f"{user.mention} **{highest}**\n"
                )
            except discord.errors.Forbidden:
                pass
            except AttributeError:
                pass
        # User get_user_info incase the top posts is by someone no longer
        # in the guild
        x = sorted(channel_contribution.items(), key=lambda x: x[1], reverse=True)
        x = [x[i : i + 10] for i in range(0, len(x), 10)]
        msg_list = []
        for page in x:
            em = discord.Embed(colour=await ctx.embed_colour())
            em.title = _("Most posts in {channel.name}").format(channel=channel)
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
            em.description = msg + "\n".join(f"{k.mention}: {v}" for k, v in page)
            msg_list.append(em)
        if warning_msg:
            await warning_msg.delete()
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @commands.command(aliases=["serveremojis"])
    @commands.bot_has_permissions(embed_links=True)
    async def guildemojis(self, ctx, *, guild: GuildConverter = None):
        """
            Display all server emojis in a menu that can be scrolled through

            `guild_name` can be either the server ID or partial name
        """
        if not guild:
            guild = ctx.guild
        msg = ""
        embed = discord.Embed(timestamp=ctx.message.created_at)
        embed.set_author(name=guild.name, icon_url=guild.icon_url)
        regular = []
        for emoji in guild.emojis:
            regular.append(f"{emoji} = `:{emoji.name}:`\n")
        if regular != "":
            embed.description = regular
        x = [regular[i : i + 10] for i in range(0, len(regular), 10)]
        emoji_embeds = []
        count = 1
        for page in x:
            em = discord.Embed(timestamp=ctx.message.created_at)
            em.set_author(name=guild.name + _(" Emojis"), icon_url=guild.icon_url)
            regular = []
            msg = ""
            for emoji in page:
                msg += emoji
            em.description = msg
            em.set_footer(text="Page {} of {}".format(count, len(x)))
            count += 1
            emoji_embeds.append(em)

        await menu(ctx, emoji_embeds, DEFAULT_CONTROLS)
