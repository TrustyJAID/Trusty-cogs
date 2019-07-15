import discord
import asyncio
import datetime
import aiohttp
import itertools
import logging

from io import BytesIO
from redbot.core import commands
from redbot.core import checks, Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions
from typing import Union, Optional, List, Tuple

from .converters import FuzzyMember, GuildConverter, ChannelConverter


_ = Translator("ServerStats", __file__)
log = logging.getLogger("red.trusty-cogs.ServerStats")
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class ServerStats(commands.Cog):
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
    async def avatar(self, ctx, *members: FuzzyMember):
        """
            Display a users avatar in chat
        """
        embed_list = []
        if members == ([None],):
            return await ctx.send(_("No one with that name appears to be on this server."))
        if not members:
            members = ([ctx.author],)
        for member in list(itertools.chain.from_iterable(members)):

            em = discord.Embed(title=_("**Avatar**"), colour=member.colour)
            if member.is_avatar_animated():
                url = member.avatar_url_as(format="gif")
            if not member.is_avatar_animated():
                url = member.avatar_url_as(static_format="png")
            em.set_image(url=url)
            try:
                em.set_author(
                    name=f"{member} {f'~ {member.nick}' if member.nick else ''}", icon_url=url, url=url
                )
            except AttributeError:
                em.set_author(
                    name=f"{member}", icon_url=url, url=url
                )
            embed_list.append(em)
        if not embed_list:
            await ctx.send(_("That user does not appear to exist on this server."))
            return
        if len(embed_list) > 1:
            await menu(ctx, embed_list, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embed_list[0])

    @listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Build and send a message containing serverinfo when the bot joins a new server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _(
            "{bot} has joined a server!\n "
            "That's **{num}** servers now!\n"
            "That's a total of **{users}** users !\n"
            "Server created on **{since}**. "
            "That's over **{passed}** days ago!"
        ).format(
            bot=channel.guild.me.mention,
            num=len(self.bot.guilds),
            users=sum(len(s.members) for s in self.bot.guilds),
            since=guild.created_at.strftime("%d %b %Y %H:%M:%S"),
            passed=passed,
        )
        try:
            em = await self.guild_embed(guild)
            em.description = created_at
            await channel.send(embed=em)
        except Exception:
            log.error(f"Error creating guild embed for new guild ID {guild.id}", exc_info=True)

    async def guild_embed(self, guild):
        """
            Builds the guild embed information used throughout the cog
        """

        def check_feature(feature):
            return "\N{WHITE HEAVY CHECK MARK}" if feature in guild.features else "\N{CROSS MARK}"

        verif = {0: "0 - None", 1: "1 - Low", 2: "2 - Medium", 3: "3 - Hard", 4: "4 - Extreme"}

        region = {
            "vip-us-east": _("__VIP__ US East") + " :flag_us:",
            "vip-us-west": _("__VIP__ US West") + " :flag_us:",
            "vip-amsterdam": _("__VIP__ Amsterdam") + " :flag_nl:",
            "eu-west": _("EU West") + " :flag_eu:",
            "eu-central": _("EU Central") + " :flag_eu:",
            "london": _("London") + " :flag_gb:",
            "frankfurt": _("Frankfurt") + " :flag_de:",
            "amsterdam": _("Amsterdam") + " :flag_nl:",
            "us-west": _("US West") + " :flag_us:",
            "us-east": _("US East") + " :flag_us:",
            "us-south": _("US South") + " :flag_us:",
            "us-central": _("US Central") + " :flag_us:",
            "singapore": _("Singapore") + " :flag_sg:",
            "sydney": _("Sydney") + " :flag_au:",
            "brazil": _("Brazil") + " :flag_br:",
            "hongkong": _("Hong Kong") + " :flag_hk:",
            "russia": _("Russia") + " :flag_ru:",
            "japan": _("Japan") + " :flag_jp:",
            "southafrica": _("South Africa") + " :flag_za:",
            "india": _("India") + " :flag_in:",
        }

        format_kwargs = {
            "vip": check_feature("VIP_REGIONS"),
            "van": check_feature("VANITY_URL"),
            "splash": check_feature("INVITE_SPLASH"),
            "m_emojis": check_feature("MORE_EMOJI"),
            "verify": check_feature("VERIFIED"),
        }
        online_stats = {
            _("Humans: "): lambda x: not x.bot,
            _(" • Bots: "): lambda x: x.bot,
            "📗": lambda x: x.status == discord.Status.online,
            "📙": lambda x: x.status == discord.Status.idle,
            "📕": lambda x: x.status == discord.Status.idle,
            "📓": lambda x: x.status == discord.Status.offline,
            "🎥": lambda x: x.activity == discord.Streaming,
            "📱": lambda x: x.is_on_mobile(),
        }
        member_msg = _("Total Users: **{total}**\n").format(total=len(guild.members))
        count = 1
        for k, v in online_stats.items():

            try:
                num = len([m for m in guild.members if v(m)])
            except Exception as e:
                print(e)
                continue
            else:
                member_msg += f"{k} **{num}** " + ("\n" if count % 2 == 0 else "")
            count += 1
        text_channels = len([x for x in guild.text_channels])
        voice_channels = len([x for x in guild.voice_channels])
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _("Created on **{since}**. " "That's over **{passed}** days ago!").format(
            since=guild.created_at.strftime("%d %b %Y %H:%M"), passed=passed
        )
        try:
            joined_at = guild.me.joined_at
        except AttributeError:
            joined_at = datetime.datetime.utcnow()

        bot_joined = joined_at.strftime("%d %b %Y %H:%M:%S")
        since_joined = (datetime.datetime.utcnow() - joined_at).days

        joined_on = _(
            "**{bot_name}** joined this server on **{bot_join}**."
            " That's over **{since_join}** days ago!"
        ).format(bot_name=self.bot.user.name, bot_join=bot_joined, since_join=since_joined)

        colour = guild.roles[-1].colour

        em = discord.Embed(description=f"{created_at}\n{joined_on}", colour=colour)
        em.add_field(name=_("Members :"), value=member_msg)
        em.add_field(
            name=_("Channels :"),
            value=_("💬 Text : **{text}**\n🔊 Voice : **{voice}**").format(
                text=text_channels, voice=voice_channels
            ),
        )
        try:
            verification_level = verif[int(guild.verification_level)]
        except TypeError:
            verification_level = str(guild.verification_level)
        em.add_field(
            name=_("Utility :"),
            value=_(
                "Owner : {owner.mention}\n**{owner}**\nRegion : **{region}**\n"
                "Verif. level : **{verif}**\nServer ID : **{id}**"
            ).format(
                owner=guild.owner,
                region=str(guild.region) if guild.region not in region else region[str(guild.region)],
                verif=verification_level,
                id=guild.id,
            ),
        )
        em.add_field(
            name=_("Misc :"),
            value=_(
                "AFK channel : **{afk_chan}**\nAFK Timeout : **{afk_timeout}sec**\n"
                "Custom emojis : **{emojis}**\nRoles : **{roles}**"
            ).format(
                afk_chan=guild.afk_channel,
                afk_timeout=guild.afk_timeout,
                emojis=len(guild.emojis),
                roles=len(guild.roles),
            ),
        )
        if guild.features:
            em.add_field(
                name=_("Special features :"),
                value=_(
                    "{vip} VIP Regions\n{van} Vanity URL\n{splash} Splash Invite\n"
                    "{m_emojis} More Emojis\n{verify} Verified"
                ).format(**format_kwargs),
            )
        if "VERIFIED" in guild.features:
            em.set_author(
                name=guild.name,
                icon_url="https://cdn.discordapp.com/emojis/457879292152381443.png",
            )
        if guild.icon_url:
            em.set_author(name=guild.name, url=guild.icon_url)
            em.set_thumbnail(url=guild.icon_url)
        else:
            em.set_author(
                name=guild.name,
                url="https://cdn.discordapp.com/attachments/494975386334134273/529843761635786754/Discord-Logo-Black.png",
            )
            em.set_thumbnail(
                url="https://cdn.discordapp.com/attachments/494975386334134273/529843761635786754/Discord-Logo-Black.png"
            )
        return em

    @listener()
    async def on_guild_remove(self, guild):
        """Build and send a message containing serverinfo when the bot leaves a server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _(
            "{bot} has left a server!\n "
            "That's **{num}** servers now!\n"
            "That's a total of **{users}** users !\n"
            "Server created on **{since}**. "
            "That's over **{passed}** days ago!"
        ).format(
            bot=channel.guild.me.mention,
            num=len(self.bot.guilds),
            users=sum(len(s.members) for s in self.bot.guilds),
            since=guild.created_at.strftime("%d %b %Y %H:%M"),
            passed=passed,
        )
        try:
            em = await self.guild_embed(guild)
            em.description = created_at
            await channel.send(embed=em)
        except Exception:
            log.error(f"Error creating guild embed for old guild ID {guild.id}", exc_info=True)

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
            try:
                """https://github.com/glasnt/emojificate/blob/master/emojificate/filter.py"""
                cdn_fmt = "https://twemoji.maxcdn.com/2/72x72/{codepoint:x}.png"
                url = cdn_fmt.format(codepoint=ord(emoji))
                filename = "emoji.png"
            except TypeError:
                await ctx.send(_("That doesn't appear to be a valid emoji"))
                return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    image = BytesIO(await resp.read())
        except Exception:
            await ctx.send(_("That doesn't appear to be a valid emoji"))
            return
        file = discord.File(image, filename=filename)
        await ctx.send(file=file)

    @commands.command()
    async def botstats(self, ctx):
        """Display stats about the bot"""
        servers = len(ctx.bot.guilds)
        members = set()
        passed = (datetime.datetime.utcnow() - ctx.me.created_at).days
        since = ctx.me.created_at.strftime("%d %b %Y %H:%M")
        for g in ctx.bot.guilds:
            count = 0
            for m in g.members:
                members.add(m.id)
                count += 1
            if not count % 10:
                await asyncio.sleep(0.1)
        msg = _(
            "{bot} is on {servers} servers serving {members} members!\n"
            "{bot} was created on **{since}**.\n"
            "That's over **{passed}** days ago!"
        ).format(
            bot=ctx.me.mention, servers=servers, members=len(members), since=since, passed=passed
        )
        em = discord.Embed(
            description=msg, colour=await ctx.embed_colour(), timestamp=ctx.message.created_at
        )
        em.set_author(
            name=f"{ctx.me} {f'~ {ctx.me.nick}' if ctx.me.nick else ''}",
            icon_url=ctx.me.avatar_url,
        )
        em.set_thumbnail(url=ctx.me.avatar_url)
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(embed=em)
        else:
            await ctx.send(msg)

    @commands.command()
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
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
        await channel.edit(
            topic=topic[:1024], reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick()

    @commands.group()
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channeledit(self, ctx):
        """Modify channel options"""
        pass

    @channeledit.command(name="name")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_name(self, ctx, channel: Optional[ChannelConverter], *, name: str):
        """Edit a channels name"""
        if not channel:
            channel = ctx.channel
        await channel.edit(
            name=name[:100], reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick()

    @channeledit.command(name="position")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_position(self, ctx, channel: Optional[ChannelConverter], position: int):
        """Edit a channels position"""
        if not channel:
            channel = ctx.channel
        try:
            await channel.edit(
                position=position, reason=_("Requested by {author}").format(author=ctx.author)
            )
        except Exception as e:
            print(e)
            return
        await ctx.tick()

    @channeledit.command(name="sync")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_sync(self, ctx, channel: Optional[ChannelConverter], toggle: bool):
        """Set whether or not to sync permissions with the channels Category"""
        if not channel:
            channel = ctx.channel
        await channel.edit(
            sync_permissions=toggle, reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick()

    @channeledit.command(name="nsfw")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_nsfw(self, ctx, toggle: bool, channel: discord.TextChannel = None):
        """Set whether or not a channel is NSFW"""
        if not channel:
            channel = ctx.channel
        await channel.edit(
            nsfw=toggle, reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick()

    @channeledit.command(name="topic")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_topic(self, ctx, channel: Optional[discord.TextChannel], *, topic: str):
        """Edit a channels topic"""
        if not channel:
            channel = ctx.channel
        await channel.edit(
            topic=topic[:1024], reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick()

    @channeledit.command(name="bitrate")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_bitrate(self, ctx, channel: discord.VoiceChannel, bitrate: int):
        """Edit a voice channels bitrate"""
        try:
            await channel.edit(
                bitrate=bitrate, reason=_("Requested by {author}").format(author=ctx.author)
            )
        except Exception:
            await ctx.send(
                _(
                    "`{bitrate}` is either too high or too low please "
                    "provide a number between 8000 and 96000."
                ).format(bitrate=bitrate)
            )
            return
        await ctx.tick()

    @channeledit.command(name="userlimit")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_userlimit(self, ctx, channel: discord.VoiceChannel, limit: int):
        """Edit a voice channels user limit"""
        try:
            await channel.edit(
                user_limit=limit, reason=_("Requested by {author}").format(author=ctx.author)
            )
        except Exception:
            await ctx.send(
                _(
                    "`{limit}` is either too high or too low please "
                    "provide a number between 0 and 99."
                ).format(limit=limit)
            )
            return
        await ctx.tick()

    async def ask_for_invite(self, ctx):
        """
            Ask the user to provide an invite link
            if reinvite is True
        """
        msg_send = _(
            "Please provide a reinvite link/message.\n" "Type `exit` for no invite link/message."
        )
        await ctx.send(msg_send)
        try:
            msg = await ctx.bot.wait_for(
                "message", check=lambda m: m.author == ctx.message.author, timeout=30
            )
        except asyncio.TimeoutError:
            await msg.edit(content=_("I Guess not."))
            return None
        if "exit" in msg.content:
            return None
        else:
            return msg.content

    async def get_members_since(
        self, ctx, days: int, role: Union[discord.Role, Tuple[discord.Role], None]
    ):
        now = datetime.datetime.utcnow()
        after = now - datetime.timedelta(days=days)
        member_list = []
        if role:
            if not isinstance(role, discord.Role):
                for r in role:
                    for m in r.members:
                        if m.top_role < ctx.me.top_role:
                            member_list.append(m)
            else:
                member_list = [m for m in role.members if m.top_role < ctx.me.top_role]
        else:
            member_list = [m for m in ctx.guild.members if m.top_role < ctx.me.top_role]
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
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if pred.result is True:
            link = await self.ask_for_invite(ctx)
            no_invite = []
            for member in member_list:
                if link:
                    try:
                        await member.send(link)
                    except Exception:
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
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if pred.result is True:
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
        member_list = await self.get_members_since(ctx, days, removed_roles)
        send_msg = str(len(member_list)) + _(
            " estimated users to remove their roles. "
            "Would you like to reassign their roles now?"
        )
        msg = await ctx.send(send_msg)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if pred.result is True:
            for member in member_list:
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
    async def whois(self, ctx, *, member: Union[int, discord.Member, discord.User, None] = None):
        """
            Display servers a user shares with the bot

            `member` can be a user ID or mention
        """
        if not member:
            return await ctx.send(_("You need to supply a user ID for this to work properly."))
        if type(member) is int:
            try:
                member = await self.bot.get_user_info(member)
            except AttributeError:
                member = await self.bot.fetch_user(member)
            except discord.errors.NotFound:
                await ctx.send(str(member) + _(" doesn't seem to be a discord user."))
                return
        embed = discord.Embed()
        since_created = (ctx.message.created_at - member.created_at).days
        user_created = member.created_at.strftime("%d %b %Y %H:%M")
        created_on = _("Joined Discord on {}\n({} days ago)").format(user_created, since_created)
        embed.description = created_on
        embed.set_thumbnail(url=member.avatar_url)
        embed.colour = await ctx.embed_colour()
        embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
        if await self.bot.is_owner(ctx.author):
            guild_list = []
            for guild in self.bot.guilds:
                members = [member.id for member in guild.members]
                if member.id in members:
                    guild_list.append(guild)
            if guild_list != []:
                msg = f"**{member}** ({member.id}) " + _("is on:\n\n")
                embed_list = ""
                for guild in guild_list:
                    m = guild.get_member(member.id)
                    msg += f"{m.nick if m.nick else ''} in __{guild.name}__ ({guild.id})\n"
                    embed_list += f"{m.nick if m.nick else ''} in __{guild.name}__ ({guild.id})\n"
                if ctx.channel.permissions_for(ctx.me).embed_links:
                    for page in pagify(embed_list, ["\n"], shorten_by=1000):
                        embed.add_field(name=_("Shared Servers"), value=page)
                    await ctx.send(embed=embed)
                else:
                    for page in pagify(msg, ["\n"], shorten_by=1000):
                        await ctx.send(page)
            else:
                if ctx.channel.permissions_for(ctx.me).embed_links:
                    await ctx.send(embed=embed)
                else:
                    msg = f"**{member}** ({member.id}) " + _("is not in any shared servers!")
                    await ctx.send(msg)
        else:
            guild_list = []
            for guild in self.bot.guilds:
                members = [member.id for member in guild.members]
                if member.id in members and ctx.author.id in members:
                    guild_list.append(guild)
            if guild_list != []:
                msg = f"**{member}** ({member.id}) " + _("is on:\n\n")
                embed_list = ""
                for guild in guild_list:
                    msg += f"__{guild.name}__ ({guild.id})\n"
                    embed_list += f"__{guild.name}__ ({guild.id})\n"
                if ctx.channel.permissions_for(ctx.me).embed_links:
                    for page in pagify(embed_list, ["\n"], shorten_by=1000):
                        embed.add_field(name=_("Shared Servers"), value=page)
                    await ctx.send(embed=embed)
                else:
                    for page in pagify(msg, ["\n"], shorten_by=1000):
                        await ctx.send(page)
            else:
                msg = f"**{member}** ({member.id}) " + _("is not in any shared servers!")
                await ctx.send(msg)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def topservers(self, ctx):
        """
            Lists servers by number of users and shows number of users
        """
        guilds = sorted(list(self.bot.guilds), key=lambda s: len(s.members), reverse=True)
        msg = ""
        msg_list = []
        count = 0
        for i, server in enumerate(guilds):
            if count == 10:
                msg_list.append(msg)
                msg = ""
                count = 0
                await asyncio.sleep(0.1)
            msg += f"{server.name}: {len(server.members)}\n"
            count += 1
        msg_list.append(msg)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def newservers(self, ctx):
        """
            Lists servers by when the bot was added to the server
        """
        guilds = sorted(list(self.bot.guilds), key=lambda s: s.me.joined_at)
        msg = ""
        msg_list = []
        count = 0
        for i, server in enumerate(guilds):
            if count == 10:
                msg_list.append(msg)
                msg = ""
                count = 0
                await asyncio.sleep(0.1)
            msg += f"{server.name}: {len(server.members)}\n"
            count += 1
        msg_list.append(msg)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def guildedit(self, ctx):
        """Edit various guild settings"""
        pass

    @guildedit.command(name="name")
    async def guild_name(self, ctx, *, name: str):
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
    async def verifivation_level(self, ctx, *, level: str):
        """
            Modify the guilds verification level

            `level` must be one of:
            `none`, `low`, `medium`, `table flip`(`high`), or `double table flip`(`extreme`)
        """

        levels = {
            "none": discord.VerificationLevel.none,
            "low": discord.VerificationLevel.low,
            "medium": discord.VerificationLevel.medium,
            "high": discord.VerificationLevel.high,
            "table flip": discord.VerificationLevel.high,
            "extreme": discord.VerificationLevel.extreme,
            "double table flip": discord.VerificationLevel.extreme,
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
    async def system_channel(self, ctx, channel: discord.TextChannel = None):
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
    async def afk_channel(self, ctx, channel: discord.VoiceChannel = None):
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
    async def afk_timeout(self, ctx, timeout: int):
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

        def joined(member: discord.Member):
            return getattr(member, "joined_at", datetime.datetime.utcnow())

        member_list = sorted(guild.members, key=joined)
        is_embed = ctx.channel.permissions_for(ctx.me).embed_links
        x = []
        for i in range(0, len(member_list), number):
            x.append(member_list[i : i + number])
            await asyncio.sleep(0.2)

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
            await asyncio.sleep(0.1)
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
        self,
        ctx,
        post_list: List[discord.Guild],
        message: discord.Message = None,
        page=0,
        timeout: int = 30,
    ):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        guild = post_list[page]
        em = await self.guild_embed(guild)
        emojis = ["➡", "⬅", "❌", "\N{OUTBOX TRAY}", "\N{INBOX TRAY}"]
        if not message:
            message = await ctx.send(embed=em)
            start_adding_reactions(message, emojis)
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = (
            lambda react, user: user == ctx.message.author
            and react.emoji in ["➡", "⬅", "❌", "\N{OUTBOX TRAY}", "\N{INBOX TRAY}"]
            and react.message.id == message.id
        )
        try:
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            for e in emojis:
                try:
                    await message.remove_reaction(e, ctx.me)
                except Exception:
                    pass
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
            elif react.emoji == "\N{OUTBOX TRAY}":
                try:
                    await self.confirm_leave_guild(ctx, guild)
                except:
                    pass
            elif react.emoji == "\N{INBOX TRAY}":
                invite = await self.get_guild_invite(guild)
                if invite:
                    await ctx.send(str(invite))
                else:
                    await ctx.send(
                        _("I cannot find or create an invite for `{guild}`").format(
                            guild=guild.name
                        )
                    )
            else:
                return await message.delete()

    @staticmethod
    async def confirm_leave_guild(ctx, guild):
        await ctx.send(
            _("Are you sure you want to leave {guild}? (reply yes or no)").format(guild=guild.name)
        )
        pred = MessagePredicate.yes_or_no(ctx)
        await ctx.bot.wait_for("message", check=pred)
        if pred.result is True:
            try:
                await ctx.send(_("Leaving {guild}.").format(guild=guild.name))
                await guild.leave()
            except Exception:
                await ctx.send(_("I couldn't leave {guild}.").format(guild=guild.name))
        else:
            await ctx.send(_("Okay, not leaving {guild}.").format(guild=guild.name))

    @staticmethod
    async def get_guild_invite(guild: discord.Guild, max_age: int = 86400):
        """Handles the reinvite logic for getting an invite
        to send the newly unbanned user
        :returns: :class:`Invite`

        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L771
        """
        my_perms: discord.Permissions = guild.me.guild_permissions
        if my_perms.manage_guild or my_perms.administrator:
            if "VANITY_URL" in guild.features:
                # guild has a vanity url so use it as the one to send
                return await guild.vanity_invite()
            invites = await guild.invites()
        else:
            invites = []
        for inv in invites:  # Loop through the invites for the guild
            if not (inv.max_uses or inv.max_age or inv.temporary):
                # Invite is for the guild's default channel,
                # has unlimited uses, doesn't expire, and
                # doesn't grant temporary membership
                # (i.e. they won't be kicked on disconnect)
                return inv
        else:  # No existing invite found that is valid
            channels_and_perms = zip(
                guild.text_channels, map(guild.me.permissions_in, guild.text_channels)
            )
            channel = next(
                (channel for channel, perms in channels_and_perms if perms.create_instant_invite),
                None,
            )
            if channel is None:
                return
            try:
                # Create invite that expires after max_age
                return await channel.create_invite(max_age=max_age)
            except discord.HTTPException:
                return

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def getguild(self, ctx, *, guild: GuildConverter = None):
        """
            Display info about servers the bot is on

            `guild_name` can be either the server ID or partial name
        """
        if guild or await ctx.bot.is_owner(ctx.author):
            if not ctx.guild:
                page = 1
            else:
                page = ctx.bot.guilds.index(guild) if guild else ctx.bot.guilds.index(ctx.guild)
            await self.guild_menu(ctx, ctx.bot.guilds, None, page)
        else:
            if ctx.guild:
                await ctx.send(embed=await self.guild_embed(ctx.guild))

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
        try:
            msg = await channel.get_message(message_id)
        except AttributeError:
            msg = await channel.fetch_message(message_id)
        except discord.errors.Forbidden:
            return
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

    @commands.command(name="serverstats")
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
                if guild is ctx.guild:
                    members = "\n".join(f"{k.mention}: {v}" for k, v in page)
                else:
                    members = "\n".join(f"{k}: {v}" for k, v in page)
                total = len(members)
                em = discord.Embed(colour=await ctx.embed_colour())
                em.title = _("Most posts on the server")
                em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
                pg_count = 0
                for chn_page in pagify(new_msg, ["\n"], page_length=1000):
                    if total + len(chn_page) >= 5000:
                        break
                    if pg_count == 0:
                        em.description = chn_page
                    else:
                        em.add_field(name=_("Most posts (continued)"), value=chn_page)
                    pg_count += 1
                    total += len(chn_page)

                em.add_field(name=_("Members List"), value=members)
                msg_list.append(em)
            if warning_msg:
                await warning_msg.delete()
            await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @commands.command(name="channelstats")
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
            channel_contribution: dict = {}
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
    async def guildemojis(
        self, ctx, id_emojis: Optional[bool] = False, *, guild: GuildConverter = None
    ):
        """
            Display all server emojis in a menu that can be scrolled through

            `id_emojis` return the id of emojis. Default to False, set True
             if you want to see emojis ID's.
            `guild_name` can be either the server ID or partial name
        """
        if not guild:
            guild = ctx.guild
        msg = ""
        embed = discord.Embed(timestamp=ctx.message.created_at)
        embed.set_author(name=guild.name, icon_url=guild.icon_url)
        regular = []
        for emoji in guild.emojis:
            if id_emojis:
                regular.append(
                    (
                        f"{emoji} = `:{emoji.name}:` "
                        f"`<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>`\n"
                    )
                )
            else:
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
