import asyncio
import os
from copy import copy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Dict, List, Literal, Optional, Tuple, Union

import aiohttp
import discord
import psutil
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    bold,
    box,
    escape,
    humanize_list,
    humanize_number,
    humanize_timedelta,
    pagify,
)

from .converters import GuildConverter, MultiGuildConverter, PermissionConverter
from .menus import (
    AvatarPages,
    BaseView,
    ConfirmView,
    GuildPages,
    ListPages,
    TopMemberPages,
)

_ = Translator("ServerStats", __file__)
log = getLogger("red.trusty-cogs.ServerStats")


@cog_i18n(_)
class ServerStats(commands.GroupCog):
    """
    Gather useful information about servers the bot is in
    A lot of commands are bot owner only
    """

    __author__ = ["TrustyJAID", "Preda"]
    __version__ = "1.8.0"

    def __init__(self, bot):
        self.bot: Red = bot
        default_global: dict = {"join_channel": None}
        default_guild: dict = {"last_checked": 0, "members": {}, "total": 0, "channels": {}}
        self.config: Config = Config.get_conf(self, 54853421465543, force_registration=True)
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.process = psutil.Process()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

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
            save = False
            if str(user_id) in data["members"]:
                del data["members"][str(user_id)]
                save = True
            for channel_id, chan_data in data["channels"].items():
                if str(user_id) in chan_data["members"]:
                    del chan_data["members"][str(user_id)]
                    save = True
            if save:
                await self.config.guild_from_id(guild_id).set(data)

    @commands.hybrid_command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def avatar(
        self, ctx: commands.Context, *, member: Optional[Union[discord.Member, discord.User]]
    ):
        """
        Display a users avatar in chat
        """
        if member is None:
            members = [ctx.author]
        else:
            members = [member]

        await BaseView(
            source=AvatarPages(members=members),
            cog=self,
        ).start(ctx=ctx)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Build and send a message containing serverinfo when the bot joins a new server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        passed = f"<t:{int(guild.created_at.timestamp())}:R>"

        created_at = _(
            "{bot} has joined a server!\n "
            "That's **{num}** servers now!\n"
            "That's a total of **{users}** users !\n"
            "Server created on **{since}**. "
            "That's over **{passed}**!"
        ).format(
            bot=channel.guild.me.mention,
            num=humanize_number(len(self.bot.guilds)),
            users=humanize_number(len(self.bot.users)),
            since=f"<t:{int(guild.created_at.timestamp())}:D>",
            passed=passed,
        )
        try:
            em = await self.guild_embed(guild)
            em.description = created_at
            await channel.send(embed=em)
        except Exception:
            log.error("Error creating guild embed for new guild ID %s", guild.id, exc_info=True)

    async def guild_embed(self, guild: discord.Guild) -> discord.Embed:
        """
        Builds the guild embed information used throughout the cog
        """

        def _size(num):
            for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
                if abs(num) < 1024.0:
                    return "{0:.1f}{1}".format(num, unit)
                num /= 1024.0
            return "{0:.1f}{1}".format(num, "YB")

        def _bitsize(num):
            for unit in ["bps", "kbps", "Mbps", "Gbps", "Tbps", "Pbps", "Ebps", "Zbps"]:
                if abs(num) < 1000.0:
                    return "{0:.1f}{1}".format(num, unit)
                num /= 1000.0
            return "{0:.1f} {1}".format(num, "Ybps")

        created_at = _("Created on {date}. That's over {num}!").format(
            date=bold(f"<t:{int(guild.created_at.timestamp())}:D>"),
            num=bold(f"<t:{int(guild.created_at.timestamp())}:R>"),
        )
        total_users = humanize_number(guild.member_count or len(guild.members))
        try:
            joined_at = guild.me.joined_at
        except AttributeError:
            joined_at = None
        if joined_at is None:
            joined_at = datetime.now(timezone.utc)
        bot_joined = discord.utils.format_dt(
            joined_at, "D"
        )  # f"<t:{int(joined_at.timestamp())}:D>"
        since_joined = discord.utils.format_dt(
            joined_at, "R"
        )  # f"<t:{int(joined_at.timestamp())}:R>"
        joined_on = _(
            "**{bot_name}** joined this server on **{bot_join}**.\n"
            "That's over **{since_join}**!"
        ).format(bot_name=self.bot.user.mention, bot_join=bot_joined, since_join=since_joined)

        shard = (
            _("\nShard ID: **{shard_id}/{shard_count}**").format(
                shard_id=humanize_number(guild.shard_id + 1),
                shard_count=humanize_number(self.bot.shard_count),
            )
            if self.bot.shard_count > 1
            else ""
        )
        colour = guild.roles[-1].colour

        online_stats = {
            _("Humans: "): lambda x: not x.bot,
            _(" • Bots: "): lambda x: x.bot,
            "\N{LARGE GREEN CIRCLE}": lambda x: x.status is discord.Status.online,
            "\N{LARGE ORANGE CIRCLE}": lambda x: x.status is discord.Status.idle,
            "\N{LARGE RED CIRCLE}": lambda x: x.status is discord.Status.do_not_disturb,
            "\N{MEDIUM WHITE CIRCLE}": lambda x: x.status is discord.Status.offline,
            "\N{LARGE PURPLE CIRCLE}": lambda x: (
                x.activity is not None and x.activity.type is discord.ActivityType.streaming
            ),
        }
        member_msg = _("Total Users: {}\n").format(bold(total_users))
        count = 1
        for emoji, value in online_stats.items():
            try:
                num = len([m for m in guild.members if value(m)])
            except Exception:
                log.error("Error determining number of users")
                continue
            else:
                member_msg += f"{emoji} {bold(humanize_number(num))} " + (
                    "\n" if count % 2 == 0 else ""
                )
            count += 1

        text_channels = len(guild.text_channels)
        nsfw_channels = len([c for c in guild.text_channels if c.is_nsfw()])
        voice_channels = len(guild.voice_channels)
        verif = {
            "none": _("0 - None"),
            "low": _("1 - Low"),
            "medium": _("2 - Medium"),
            "high": _("3 - High"),
            "extreme": _("4 - Extreme"),
            "highest": _("4 - Highest"),
        }

        features = {
            "ANIMATED_ICON": _("Animated Icon"),
            "BANNER": _("Banner Image"),
            "COMMERCE": _("Commerce"),
            "COMMUNITY": _("Community"),
            "DISCOVERABLE": _("Server Discovery"),
            "FEATURABLE": _("Featurable"),
            "INVITE_SPLASH": _("Splash Invite"),
            "MEMBER_LIST_DISABLED": _("Member list disabled"),
            "MEMBER_VERIFICATION_GATE_ENABLED": _("Membership Screening enabled"),
            "MORE_EMOJI": _("More Emojis"),
            "NEWS": _("News Channels"),
            "PARTNERED": _("Partnered"),
            "PREVIEW_ENABLED": _("Preview enabled"),
            "PUBLIC_DISABLED": _("Public disabled"),
            "VANITY_URL": _("Vanity URL"),
            "VERIFIED": _("Verified"),
            "VIP_REGIONS": _("VIP Voice Servers"),
            "WELCOME_SCREEN_ENABLED": _("Welcome Screen enabled"),
        }
        guild_features_list = [
            f"- {name}" for feature, name in features.items() if feature in guild.features
        ]

        em = discord.Embed(
            description=(f"> {bold(guild.description)}\n\n" if guild.description else "")
            + f"{created_at}\n{joined_on}",
            colour=colour,
        )
        author_icon = None
        if "VERIFIED" in guild.features:
            author_icon = "https://cdn.discordapp.com/emojis/457879292152381443.png"
        if "PARTNERED" in guild.features:
            author_icon = (
                "https://cdn.discordapp.com/badge-icons/3f9748e53446a137a052f3454e2de41e.png"
            )
        guild_icon = "https://cdn.discordapp.com/embed/avatars/5.png"
        if guild.icon:
            guild_icon = guild.icon
        em.set_author(
            name=guild.name,
            icon_url=author_icon,
            url=guild_icon,
        )
        em.set_thumbnail(url=guild.icon)
        owner = guild.owner if guild.owner else await self.bot.get_or_fetch_user(guild.owner_id)
        em.add_field(
            name=_("Utility:"),
            value=_(
                "Owner: {owner_mention}\n{owner}\nVerif. level: {verif}\nServer ID: {id}{shard}"
            ).format(
                owner_mention=bold(str(owner.mention)),
                owner=bold(str(owner)),
                verif=bold(verif[str(guild.verification_level)]),
                id=bold(str(guild.id)),
                shard=shard,
            ),
            inline=False,
        )
        em.add_field(name=_("Members:"), value=member_msg)
        em.add_field(
            name=_("Channels:"),
            value=_(
                "\N{SPEECH BALLOON} Text: {text}\n{nsfw}"
                "\N{NEWSPAPER} Forums: {forum}\n\N{SPOOL OF THREAD} Threads: {threads}\n"
                "\N{SPEAKER WITH THREE SOUND WAVES} Voice: {voice}\n"
                "\N{MICROPHONE} Stage: {stage}"
            ).format(
                text=bold(humanize_number(text_channels)),
                forum=bold(humanize_number(len(guild.forums))),
                threads=bold(humanize_number(len(guild.threads))),
                nsfw=_("\N{NO ONE UNDER EIGHTEEN SYMBOL} Nsfw: {}\n").format(
                    bold(humanize_number(nsfw_channels))
                )
                if nsfw_channels
                else "",
                voice=bold(humanize_number(voice_channels)),
                stage=bold(humanize_number(len(guild.stage_channels))),
            ),
        )

        em.add_field(
            name=_("Misc:"),
            value=_("AFK channel: {afk_chan}\nAFK timeout: {afk_timeout}\nRoles: {roles}").format(
                afk_chan=bold(str(guild.afk_channel)) if guild.afk_channel else bold(_("Not set")),
                afk_timeout=bold(humanize_timedelta(seconds=guild.afk_timeout)),
                roles=bold(humanize_number(len(guild.roles))),
            ),
        )
        nitro_boost = _(
            "Tier {boostlevel} with {nitroboosters} boosters\n"
            "File size limit: {filelimit}\n"
            "Emoji limit: {emojis_limit}\n"
            "Sticker limit: {sticker_limit}\n"
            "VCs max bitrate: {bitrate}"
        ).format(
            boostlevel=bold(str(guild.premium_tier)),
            nitroboosters=bold(humanize_number(guild.premium_subscription_count)),
            filelimit=bold(_size(guild.filesize_limit)),
            emojis_limit=bold(f"{len(guild.emojis)}/{guild.emoji_limit}"),
            sticker_limit=bold(f"{len(guild.stickers)}/{guild.sticker_limit}"),
            bitrate=bold(_bitsize(guild.bitrate_limit)),
        )
        em.add_field(name=_("Nitro Boost:"), value=nitro_boost)
        if guild_features_list:
            em.add_field(name=_("Server features:"), value="\n".join(guild_features_list))
        if guild.vanity_url:
            # you can only have a vanity URL in expected public servers
            em.add_field(name=_("Vanity URL:"), value=guild.vanity_url, inline=False)

        if guild.splash:
            em.set_image(url=guild.splash.url)
        return em

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Build and send a message containing serverinfo when the bot leaves a server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        passed = f"<t:{int(guild.created_at.timestamp())}:R>"
        created_at = _(
            "{bot} has left a server!\n "
            "That's **{num}** servers now!\n"
            "That's a total of **{users}** users !\n"
            "Server created on **{since}**. "
            "That's over **{passed}**!"
        ).format(
            bot=channel.guild.me.mention,
            num=humanize_number(len(self.bot.guilds)),
            users=humanize_number(len(self.bot.users)),
            since=f"<t:{int(guild.created_at.timestamp())}:D>",
            passed=passed,
        )
        try:
            em = await self.guild_embed(guild)
            em.description = created_at
            await channel.send(embed=em)
        except Exception:
            log.error("Error creating guild embed for old guild ID %s", guild.id, exc_info=True)

    @commands.hybrid_command()
    async def emoji(self, ctx: commands.Context, emoji: str) -> None:
        """
        Post a large size emojis in chat
        """
        await ctx.channel.typing()
        d_emoji = discord.PartialEmoji.from_str(emoji)
        if d_emoji.is_custom_emoji():
            ext = "gif" if d_emoji.animated else "png"
            url = "https://cdn.discordapp.com/emojis/{id}.{ext}?v=1".format(id=d_emoji.id, ext=ext)
            filename = "{name}.{ext}".format(name=d_emoji.name, ext=ext)
        else:
            try:
                """https://github.com/glasnt/emojificate/blob/master/emojificate/filter.py"""
                cdn_fmt = (
                    "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{codepoint:x}.png"
                )
                url = cdn_fmt.format(codepoint=ord(str(emoji)))
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

    @commands.hybrid_command(aliases=["bs"])
    async def botstats(self, ctx: commands.Context) -> None:
        """Display stats about the bot"""
        async with ctx.typing():
            servers = humanize_number(len(ctx.bot.guilds))
            members = humanize_number(len(self.bot.users))
            passed = discord.utils.format_dt(ctx.me.created_at, "R")
            since = discord.utils.format_dt(ctx.me.created_at, "D")
            uptime = discord.utils.format_dt(self.bot.uptime, "R")
            up_since = discord.utils.format_dt(self.bot.uptime, "D")
            msg = _(
                "{bot} is on {servers} servers serving {members} members!\n"
                "{bot} was created on **{since}**.\n"
                "That's over **{passed}**!\nI have been up since {up_since} ({uptime}).\n"
            ).format(
                bot=ctx.me.mention,
                servers=servers,
                members=members,
                since=since,
                passed=passed,
                uptime=uptime,
                up_since=up_since,
            )
            em = discord.Embed(colour=await ctx.embed_colour(), timestamp=ctx.message.created_at)
            # https://github.com/Rapptz/RoboDanny/blob/f859a326d74e919b1b3042b0114a258cd6a531f4/cogs/stats.py#L716-L798
            # The following code is inspired by RoboDanny linked above modified for Red-DiscordBot
            description = [msg]
            all_tasks = asyncio.all_tasks(loop=self.bot.loop)
            event_tasks = [t for t in all_tasks if "Client._run_event" in repr(t) and not t.done()]

            cogs_directory = [str(p) for p in await ctx.bot._cog_mgr.user_defined_paths()]
            cogs_directory.insert(0, str(await ctx.bot._cog_mgr.install_path()))
            cogs_directory.insert(0, str(ctx.bot._cog_mgr.CORE_PATH))

            tasks_directory = os.path.join("discord", "ext", "tasks", "__init__.py")
            inner_tasks = [
                t
                for t in all_tasks
                if any([p in repr(t) for p in cogs_directory]) or tasks_directory in repr(t)
            ]

            bad_inner_tasks = [
                hex(id(t)) for t in inner_tasks if t.done() and t._exception is not None
            ]
            bad_inner_tasks_str = humanize_list(bad_inner_tasks)
            total_warnings = len(bad_inner_tasks)
            em.add_field(
                name="Inner Tasks",
                value=f'Total: {len(inner_tasks)}\nFailed: {bad_inner_tasks_str or "None"}',
            )
            em.add_field(name="Events Waiting", value=f"Total: {len(event_tasks)}")

            memory_usage = self.process.memory_full_info().uss / 1024**2
            cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
            em.add_field(name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU")

            global_rate_limit = not self.bot.http._global_over.is_set()
            description.append(f"Global Rate Limit: {global_rate_limit}")
            em.set_footer(text=f"{total_warnings} warning(s)")
            if ctx.guild:
                em.set_author(
                    name=f"{ctx.me} {f'~ {ctx.me.nick}' if ctx.me.nick else ''}",
                    icon_url=ctx.me.avatar,
                )
            else:
                em.set_author(
                    name=f"{ctx.me}",
                    icon_url=ctx.me.avatar,
                )
            em.description = "\n".join(description)
            em.set_thumbnail(url=ctx.me.avatar)
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(embed=em)
        else:
            await ctx.send("\n".join(description)[:2000])

    @commands.hybrid_group()
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channeledit(self, ctx: commands.Context) -> None:
        """Modify channel options"""
        pass

    @channeledit.command(name="name")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_name(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel],
        *,
        name: str,
    ) -> None:
        """Edit a channels name"""
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
        await channel.edit(
            name=name[:100], reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(name="position")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_position(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel],
        position: int,
    ) -> None:
        """Edit a channels position"""
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
        try:
            await channel.edit(
                position=position, reason=_("Requested by {author}").format(author=ctx.author)
            )
        except Exception:
            log.exception("Error editing channel position on %s", channel)
            return
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(name="sync")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_sync(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel],
        toggle: bool,
    ) -> None:
        """Set whether or not to sync permissions with the channels Category"""
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
        await channel.edit(
            sync_permissions=toggle, reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(name="nsfw")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_nsfw(
        self, ctx: commands.Context, toggle: bool, channel: discord.TextChannel = None
    ) -> None:
        """Set whether or not a channel is NSFW"""
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
        await channel.edit(
            nsfw=toggle, reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(name="topic")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_topic(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, topic: str
    ) -> None:
        """Edit a channels topic"""
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
        await channel.edit(
            topic=topic[:1024], reason=_("Requested by {author}").format(author=ctx.author)
        )
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(name="bitrate")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_bitrate(
        self, ctx: commands.Context, channel: discord.VoiceChannel, bitrate: int
    ) -> None:
        """Edit a voice channels bitrate

        - `<channel>` The voice channel you want to change.
        - `<bitrate>` The new bitrate between 8000 and 96000.
        """
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
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
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(name="userlimit")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_userlimit(
        self, ctx: commands.Context, channel: discord.VoiceChannel, limit: int
    ) -> None:
        """Edit a voice channels user limit

        - `<channel>` The voice channel you want to change the limit on.
        - `<limit>` The limt on number of users between 0 and 99.
        """
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(
                _('I require the "Manage Channels" permission to execute that command.')
            )
            return
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
        await ctx.tick(message=_("Command complete."))

    @channeledit.command(
        name="permissions", aliases=["perms", "permission"], with_app_command=False
    )
    @checks.mod_or_permissions(manage_permissions=True)
    @checks.bot_has_permissions(manage_permissions=True)
    async def edit_channel_perms(
        self,
        ctx: commands.Context,
        permission: PermissionConverter,
        channel: Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel],
        true_or_false: Optional[bool],
        *roles_or_users: Union[discord.Member, discord.Role, str],
    ) -> None:
        """
        Edit channel read permissions for designated role

        `[channel]` The channel you would like to edit. If no channel is provided
        the channel this command is run in will be used.
        `[true_or_false]` `True` or `False` to set the permission level. If this is not
        provided `None` will be used instead which signifies the default state of the permission.
        `[roles_or_users...]` the roles or users you want to edit this setting for.

        `<permission>` Must be one of the following:
         - create_instant_invite
         - manage_channels
         - add_reactions
         - priority_speaker
         - stream
         - read_messages
         - send_messages
         - send_tts_messages
         - manage_messages
         - embed_links
         - attach_files
         - read_message_history
         - mention_everyone
         - external_emojis
         - connect
         - speak
         - mute_members
         - deafen_members
         - move_members
         - use_voice_activation
         - manage_roles
         - manage_webhooks
         - use_application_commands
         - request_to_speak
         - manage_threads
         - create_public_threads
         - create_private_threads
         - external_stickers
         - send_messages_in_threads
         - use_soundboard
        """
        if channel is None:
            channel = ctx.channel
        if (
            not channel.permissions_for(ctx.author).manage_permissions
            or not channel.permissions_for(ctx.author).manage_channels
        ):
            await ctx.send(
                _("You do not have the correct permissions to edit {channel}.").format(
                    channel=channel.mention
                )
            )
            return
        if (
            not channel.permissions_for(ctx.me).manage_permissions
            or not channel.permissions_for(ctx.author).manage_channels
        ):
            await ctx.send(
                _("I do not have the correct permissions to edit {channel}.").format(
                    channel=channel.mention
                )
            )
            return
        targets = list(roles_or_users)
        for r in roles_or_users:
            if isinstance(r, str):
                if r == "everyone":
                    targets.remove(r)
                    targets.append(ctx.guild.default_role)
                else:
                    targets.remove(r)
        if not targets:
            await ctx.send(
                _("You need to provide a role or user you want to edit permissions for")
            )
            return
        overs = channel.overwrites
        for target in targets:
            if target in overs:
                overs[target].update(**{permission: true_or_false})

            else:
                perm = discord.PermissionOverwrite(**{permission: true_or_false})
                overs[target] = perm
        try:
            await channel.edit(overwrites=overs)
            await ctx.send(
                _(
                    "The following roles or users have had `{perm}` "
                    "in {channel} set to `{perm_level}`:\n{roles_or_users}"
                ).format(
                    perm=permission,
                    channel=channel.mention,
                    perm_level=true_or_false,
                    roles_or_users=humanize_list([i.mention for i in targets]),
                )
            )
        except Exception:
            log.exception(f"Error editing permissions in channel {channel.name}")
            await ctx.send(_("There was an issue editing permissions on that channel."))

    async def ask_for_invite(self, ctx: commands.Context) -> Optional[str]:
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
            await ctx.send(_("I Guess not."))
            return None
        if "exit" in msg.content:
            return None
        else:
            return msg.content

    async def get_members_since(
        self,
        ctx: commands.Context,
        days: int,
        role: Union[discord.Role, Tuple[discord.Role], None],
    ) -> List[discord.Member]:
        now = datetime.now(timezone.utc)
        after = now - timedelta(days=days)
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
    @commands.guild_only()
    @checks.bot_has_permissions(add_reactions=True)
    async def pruneroles(self, ctx: commands.Context) -> None:
        """
        Perform various actions on users who haven't spoken in x days

        Note: This will only check if a user has talked in the past x days whereas
        discords built in Prune checks online status
        """
        pass

    @pruneroles.command()
    @commands.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def list(self, ctx: commands.Context, days: int, role: discord.Role = None) -> None:
        """
        List the users who have not talked in x days.

        - `<days>` The days you want to search for.
        - `[role]` The role you want to check.
        """
        if days < 1:
            await ctx.send(_("You must provide a value of more than 0 days."))
            return
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
                    estimate = await ctx.guild.estimate_pruned_members(
                        days=days if days < 30 else 30
                    )
                    em.add_field(name=_("Discord Estimate"), value=str(estimate))
                em.description = "\n".join(m.mention for m in page)
                em.set_author(name=f"{ctx.guild.name}", icon_url=ctx.guild.icon)
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
        if msg_list != []:
            await BaseView(
                source=ListPages(pages=msg_list),
                cog=self,
            ).start(ctx=ctx)
        else:
            await ctx.send(_("No one was found to be inactive in this time."))

    @pruneroles.command()
    @checks.mod_or_permissions(kick_members=True)
    @checks.bot_has_permissions(kick_members=True, add_reactions=True)
    async def kick(
        self, ctx: commands.Context, days: int, role: discord.Role = None, reinvite: bool = True
    ) -> None:
        """
        Kick users from the server who have been inactive for x days

        - `<days>` is the number of days since last seen talking on the server
        - `[role]` is the specified role you would like to kick defaults to everyone
        - `[reinvite=True]` True/False whether to try to send the user a message before kicking
        """
        if days < 1:
            await ctx.send(_("You must provide a value of more than 0 days."))
            return
        if role is not None and role >= ctx.me.top_role:
            msg = _("That role is higher than my role so I cannot kick those members.")
            await ctx.send(msg)
            return
        member_list = await self.get_members_since(ctx, days, role)
        send_msg = _(
            "{num} estimated users to give the role. Would you like to reassign their roles now?"
        ).format(num=str(len(member_list)))
        pred = ConfirmView(ctx.author)
        pred.message = await ctx.send(send_msg, view=pred)
        await pred.wait()
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
            await ctx.send(_("I guess not."))
            return
        await ctx.send(_("Done."))

    @pruneroles.command()
    @checks.mod_or_permissions(manage_roles=True)
    @checks.bot_has_permissions(manage_roles=True, add_reactions=True)
    async def add(self, ctx: commands.Context, days: int, *new_roles: discord.Role) -> None:
        """
        Give roles to users who haven't spoken in x days

        - `<days>` is the number of days since last seen talking on the server
        - `[new_roles...]` The new roles to apply to a user who is inactive
        """
        if days < 1:
            await ctx.send(_("You must provide a value of more than 0 days."))
            return
        if any([r >= ctx.me.top_role for r in new_roles]):
            msg = _(
                "At least one of those roles is higher than my "
                "role so I cannot add those roles."
            )
            await ctx.send(msg)
            return
        member_list = await self.get_members_since(ctx, days, None)
        send_msg = _(
            "{num} estimated users to give the role. Would you like to reassign their roles now?"
        ).format(num=str(len(member_list)))
        pred = ConfirmView(ctx.author)
        pred.message = await ctx.send(send_msg, view=pred)
        await pred.wait()
        if pred.result is True:
            for member in member_list:
                # roles = list(set(member.roles + list(new_roles)))
                try:
                    await member.add_roles(*new_roles, reason=_("Given role due to inactivity."))
                except discord.Forbidden:
                    log.debug("Could not find member %s, have they left the guild?", member)
                except Exception:
                    log.debug(
                        "Error editing %s roles for activity, have they left the guild?", member
                    )
        else:
            await ctx.send(_("I guess not."))
            return
        await ctx.send(_("Done."))

    @pruneroles.command()
    @checks.mod_or_permissions(manage_roles=True)
    @checks.bot_has_permissions(manage_roles=True, add_reactions=True)
    async def remove(self, ctx: commands.Context, days: int, *removed_roles: discord.Role) -> None:
        """
        Remove roles from users who haven't spoken in x days.

        - `<days>` is the number of days since last seen talking on the server.
        - `[removed_roles...]` the roles to remove from inactive users.
        """
        if days < 1:
            await ctx.send(_("You must provide a value of more than 0 days."))
            return
        if any([r >= ctx.me.top_role for r in removed_roles]):
            msg = _(
                "At least one of those roles is higher than my "
                "role so I cannot remove those roles."
            )
            await ctx.send(msg)
            return
        member_list = await self.get_members_since(ctx, days, removed_roles)
        send_msg = _(
            "{num} estimated users to give the role. Would you like to reassign their roles now?"
        ).format(num=str(len(member_list)))
        pred = ConfirmView(ctx.author)
        pred.message = await ctx.send(send_msg, view=pred)
        await pred.wait()
        if pred.result is True:
            for member in member_list:
                try:
                    await member.remove_roles(
                        *removed_roles, reason=_("Roles removed due to inactivity.")
                    )
                except discord.Forbidden:
                    log.debug("Could not find member %s, have they left the guild?", member)
                except Exception:
                    log.exception(
                        "Error editing %s roles for activity, have they left the guild?", member
                    )
        else:
            await ctx.send(_("I guess not."))
            return
        await ctx.send(_("Done."))

    @commands.command()
    @checks.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def setguildjoin(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
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
    async def removeguildjoin(self, ctx: commands.Context) -> None:
        """
        Stop bots join/leave server messages
        """
        await self.config.join_channel.clear()
        await ctx.send(_("No longer posting joined or left servers."))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def checkcheater(self, ctx: commands.Context, user_id: int) -> None:
        """
        Checks for possible cheaters abusing the global bank and server powers
        """
        is_cheater = False
        msg = ""
        for guild in self.bot.guilds:
            if guild.owner.id == user_id:
                is_cheater = True
                msg += guild.owner.mention + _(" is guild owner of ") + guild.name + "\n"
        if is_cheater:
            for page in pagify(msg):
                await ctx.maybe_send_embed(page)
        if not is_cheater:
            await ctx.send(_("Not a cheater"))

    async def make_whois_embed(self, ctx: commands.Context, member: discord.User):
        embed = discord.Embed()
        since_created = discord.utils.format_dt(member.created_at, "R")
        user_created = discord.utils.format_dt(member.created_at, "D")
        public_flags = ""
        robot = "\N{ROBOT FACE}" if member.bot else ""
        if version_info >= VersionInfo.from_str("3.4.0"):
            public_flags = "\n".join(
                bold(i.replace("_", " ").title()) for i, v in member.public_flags if v
            )
        created_on = (
            "Joined Discord on {user_created} ({since_created})\n"
            "{public_flags}\nUser ID:\n{user_id}"
        ).format(
            user_created=user_created,
            since_created=since_created,
            public_flags=public_flags,
            user_id=box(str(member.id)),
        )
        embed.description = created_on
        embed.set_thumbnail(url=member.display_avatar)
        embed.colour = await ctx.embed_colour()
        embed.set_author(name=f"{member} {robot}", icon_url=member.display_avatar)
        return embed

    @commands.hybrid_command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def whois(self, ctx: commands.Context, *, user_id: discord.User) -> None:
        """
        Display servers a user shares with the bot

        - `<user_id>` The user you want to search for, ID's are preferred but some name lookup works.
         - Note: This will only show shared servers between you and the bot.
        """
        async with ctx.typing():
            if not user_id:
                await ctx.send(_("You need to supply a user ID for this to work properly."))
                return
            if isinstance(user_id, int):
                try:
                    member = await self.bot.fetch_user(user_id)
                except AttributeError:
                    member = await self.bot.get_user_info(user_id)
                except discord.errors.NotFound:
                    await ctx.send(str(user_id) + _(" doesn't seem to be a discord user."))
                    return
            else:
                member = user_id

            if await self.bot.is_owner(ctx.author):
                if member.id == ctx.me.id:
                    guild_list = ctx.bot.guilds
                else:
                    guild_list = member.mutual_guilds
            else:
                if member.id == ctx.me.id:
                    guild_list = ctx.author.mutual_guilds
                else:
                    search = set(member.mutual_guilds)
                    author = set(ctx.author.mutual_guilds)
                    guild_list = list(author.intersection(search))

            embed_list = []
            robot = "\N{ROBOT FACE}" if member.bot else ""
            base_embed = await self.make_whois_embed(ctx, member)
            if guild_list != []:
                url = "https://discord.com/channels/{guild_id}"
                msg = f"**{member}** ({member.id}) {robot}" + _("is on:\n\n")
                embed_msg = ""
                for guild in guild_list:
                    m = guild.get_member(member.id)
                    # m = guild.get_member(member.id)
                    guild_join = ""
                    guild_url = url.format(guild_id=m.guild.id)
                    if m.joined_at:
                        ts = int(m.joined_at.timestamp())
                        guild_join = f"Joined the server <t:{ts}:R>"
                    is_owner = ""
                    nick = ""
                    if m.id == m.guild.owner_id:
                        is_owner = "\N{CROWN}"
                    if m.nick:
                        nick = f"`{m.nick}` in"
                    msg += f"{is_owner}{nick} __[{m.guild.name}]({guild_url})__ {guild_join}\n\n"
                    embed_msg += (
                        f"{is_owner}{nick} __[{m.guild.name}]({guild_url})__ {guild_join}\n\n"
                    )
                if ctx.channel.permissions_for(ctx.me).embed_links:
                    for number, em in enumerate(
                        pagify(embed_msg, ["\n"], page_length=1024), start=1
                    ):
                        embed = base_embed.copy()
                        embed.add_field(name=_("Shared Servers"), value=em)
                        embed.set_footer(
                            text=_("Page {number}/{total}").format(
                                number=number, total=len(embed_list)
                            )
                        )
                        embed_list.append(embed)
                else:
                    for page in pagify(msg, ["\n"]):
                        embed_list.append(page)
            else:
                if ctx.channel.permissions_for(ctx.me).embed_links:
                    embed_list.append(base_embed)
                else:
                    msg = f"**{member}** ({member.id}) " + _("is not in any shared servers!")
                    embed_list.append(msg)
            await BaseView(
                source=ListPages(pages=embed_list),
                cog=self,
            ).start(ctx=ctx)

    @commands.command(hidden=True)
    @checks.is_owner()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def topservers(self, ctx: commands.Context) -> None:
        """
        Lists servers by number of users and shows number of users
        """
        guilds = sorted(list(self.bot.guilds), key=lambda s: s.member_count, reverse=True)
        msg = ""
        for server in guilds:
            ts = int(server.me.joined_at.timestamp())
            msg += (
                f"{escape(server.name, mass_mentions=True, formatting=True)}: "
                f"`{humanize_number(server.member_count)}` Joined <t:{ts}:R>\n"
            )
        msg_list = []
        for page in pagify(msg, delims=["\n"], page_length=1000):
            msg_list.append(
                discord.Embed(
                    colour=await self.bot.get_embed_colour(ctx.channel), description=page
                )
            )
        await BaseView(
            source=ListPages(pages=msg_list),
            cog=self,
        ).start(ctx=ctx)

    @commands.command(hidden=True)
    @checks.is_owner()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def newservers(self, ctx: commands.Context) -> None:
        """
        Lists servers by when the bot was added to the server
        """
        guilds = sorted(list(self.bot.guilds), key=lambda s: s.me.joined_at, reverse=True)
        msg = ""
        msg_list = []
        for server in guilds:
            ts = int(server.me.joined_at.timestamp())
            msg += (
                f"{escape(server.name, mass_mentions=True, formatting=True)}: "
                f"`{humanize_number(server.member_count)}` Joined <t:{ts}:R>\n"
            )
        for page in pagify(msg, delims=["\n"], page_length=1000):
            msg_list.append(
                discord.Embed(
                    colour=await self.bot.get_embed_colour(ctx.channel), description=page
                )
            )
        await BaseView(
            source=ListPages(pages=msg_list),
            cog=self,
        ).start(ctx=ctx)

    @commands.hybrid_group()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def guildedit(self, ctx: commands.Context) -> None:
        """Edit various guild settings"""
        pass

    @guildedit.command(name="name")
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def guild_name(self, ctx: commands.Context, *, name: str):
        """
        Change the server name

        - `<name>` The new name of the server.
        """
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(name=name, reason=reason)
        except Exception:
            log.exception("Could not edit guild name")
            return await ctx.send(_("I could not edit the servers name."))
        await ctx.send(_("Server name set to {name}.").format(name=name))

    @guildedit.command(name="verificationlevel", aliases=["verification"])
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def verifivation_level(self, ctx: commands.Context, *, level: str) -> None:
        """
        Modify the guilds verification level

        - `<level>` must be one of:
         - `none`
         - `low`
         - `medium`
         - `table flip`
         - `high`
         - `double table flip`
         - `extreme`
        """

        levels = {
            "none": discord.VerificationLevel.none,
            "low": discord.VerificationLevel.low,
            "medium": discord.VerificationLevel.medium,
            "high": discord.VerificationLevel.high,
            "table flip": discord.VerificationLevel.high,
            "highest": discord.VerificationLevel.highest,
            "extreme": discord.VerificationLevel.highest,
            "double table flip": discord.VerificationLevel.highest,
        }
        reason = _("Requested by {author}").format(author=ctx.author)
        if level.lower() not in levels:
            await ctx.send(_("`{}` is not a proper verification level.").format(level))
            return
        try:
            await ctx.guild.edit(verification_level=levels[level], reason=reason)
        except Exception:
            log.exception("Could not edit guild verification level")
            await ctx.send(_("I could not edit the servers verification level."))
            return
        await ctx.send(_("Server verification level set to {level}").format(level=level))

    @guildedit.command(name="systemchannel", aliases=["welcomechannel"])
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def system_channel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """
        Change the system channel

        This is the default discord welcome channel.
        - `[channel]` The channel you want to set as the system channel.
         - If not provided will be set to `None`.
        """
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(system_channel=channel, reason=reason)
        except Exception:
            log.exception("Could not edit guild systemchannel")
            return await ctx.send(_("I could not edit the servers systemchannel."))
        channel_name = getattr(channel, "mention", "None")
        await ctx.send(_("Server systemchannel set to {channel}").format(channel=channel_name))

    @guildedit.command(name="afkchannel")
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def afk_channel(
        self, ctx: commands.Context, channel: Optional[discord.VoiceChannel] = None
    ) -> None:
        """
        Change the servers AFK voice channel

        - `[channel]` The channel you want to set as the system channel.
         - If not provided will be set to `None`.
        """
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(afk_channel=channel, reason=reason)
        except Exception:
            log.exception("Could not edit guild afk channel")
            return await ctx.send(_("I could not edit the servers afk channel."))
        channel_name = getattr(channel, "mention", "None")
        await ctx.send(_("Server afk channel set to {channel}").format(channel=channel_name))

    @guildedit.command(name="afktimeout")
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def afk_timeout(self, ctx: commands.Context, timeout: int) -> None:
        """
        Change the servers AFK timeout

        - `<timeout>` must be a value of 60, 300, 900, 1800, or 3600.
        """
        if timeout not in [60, 300, 900, 1800, 3600]:
            await ctx.send(_("`timeout` must be a value of 60, 300, 900, 1800, or 3600."))
            return
        reason = _("Requested by {author}").format(author=ctx.author)
        try:
            await ctx.guild.edit(afk_timeout=timeout, reason=reason)
        except Exception:
            log.exception("Could not edit guild afk timeout")
            await ctx.send(_("I could not edit the servers afk timeout."))
            return
        await ctx.send(_("Server AFK timeout set to {timeout} seconds.").format(timeout=timeout))

    @commands.hybrid_command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def topmembers(
        self,
        ctx: commands.Context,
        include_bots: Optional[bool] = None,
        guild: GuildConverter = None,
    ) -> None:
        """
        Lists top members on the server by join date

        - `[include_bots]` whether or not to display bots or members. By default this will show everyone.
        - `[guild]` can be either the server ID or name.
         - Note: You must share the guild with the bot for this to work.
        """
        if not guild:
            guild = ctx.guild
        members = guild.members
        async with ctx.typing():
            if include_bots is False:
                members = [i for i in guild.members if not i.bot]
            if include_bots is True:
                members = [i for i in guild.members if i.bot]

            def joined(member: discord.Member):
                return getattr(member, "joined_at", None) or datetime.datetime.now(timezone.utc)

            member_list = sorted(members, key=joined)
        if not member_list:
            await ctx.send(_("I could not list members based on your criteria."))
            return
        await BaseView(
            source=TopMemberPages(pages=member_list, include_bots=include_bots),
            cog=self,
        ).start(ctx=ctx)

    @commands.command()
    @checks.is_owner()
    async def listchannels(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
        """
        Lists channels and their position and ID for a server

        - `[guild]` can be either the guild ID or name.
         - Note: You must share the guild with the bot for this to work.
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
        pages = []
        for page in pagify(msg, ["\n"]):
            if await ctx.embed_requested():
                pages.append(
                    discord.Embed(
                        title=_("Channels in {guild}").format(guild=guild.name), description=page
                    )
                )
            else:
                pages.append(page)
        await BaseView(
            source=ListPages(pages),
            cog=self,
        ).start(ctx=ctx)

    @staticmethod
    async def confirm_leave_guild(ctx: commands.Context, guild) -> None:
        pred = ConfirmView(ctx.author)
        pred.message = await ctx.send(
            _("Are you sure you want me to leave {guild}? (reply yes or no)").format(
                guild=guild.name
            ),
            view=pred,
        )
        await pred.wait()
        if pred.result is True:
            try:
                await ctx.send(_("Leaving {guild}.").format(guild=guild.name))
                await guild.leave()
            except Exception:
                log.error(
                    "I couldn't leave %s (%s).",
                    guild.name,
                    guild.id,
                    exc_info=True,
                )
                await ctx.send(_("I couldn't leave {guild}.").format(guild=guild.name))
        else:
            await ctx.send(_("Okay, not leaving {guild}.").format(guild=guild.name))

    @staticmethod
    async def get_guild_invite(
        guild: discord.Guild, max_age: int = 86400
    ) -> Optional[discord.Invite]:
        """Handles the reinvite logic for getting an invite
        to send the newly unbanned user
        :returns: :class:`Invite`

        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L771
        """
        my_perms: discord.Permissions = guild.me.guild_permissions
        if my_perms.manage_guild or my_perms.administrator:
            if "VANITY_URL" in guild.features:
                # guild has a vanity url so use it as the one to send
                try:
                    return await guild.vanity_invite()
                except discord.errors.Forbidden:
                    invites = []
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
                guild.text_channels,
                map(lambda x: x.permissions_for(guild.me), guild.text_channels),
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

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def getguild(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
        """
        Display info about servers the bot is on

        - `[guild]` can be either the guild ID or name.
         - Note: You must share the guild with the bot for this to work.
        """
        async with ctx.typing():
            if not ctx.guild and not await ctx.bot.is_owner(ctx.author):
                return await ctx.send(_("This command is not available in DM."))
            guilds = [ctx.guild]
            page = 0
            if await ctx.bot.is_owner(ctx.author):
                if ctx.guild:
                    page = ctx.bot.guilds.index(ctx.guild)
                guilds = ctx.bot.guilds
                if guild:
                    page = ctx.bot.guilds.index(guild)

        await BaseView(
            source=GuildPages(guilds=guilds),
            cog=self,
            page_start=page,
            ctx=ctx,
        ).start(ctx=ctx)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @checks.admin()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def getguilds(self, ctx: commands.Context, *, guilds: MultiGuildConverter) -> None:
        """
        Display info about multiple servers

        - `[guilds]` can be multiple either the guild ID or name.
         - Note: You must share the guild with the bot for this to work.
        """
        async with ctx.typing():
            page = 0
            if not guilds:
                guilds = ctx.bot.guilds
                page = ctx.bot.guilds.index(ctx.guild)
        await BaseView(
            source=GuildPages(guilds=guilds),
            cog=self,
            page_start=page,
        ).start(ctx=ctx)

    @commands.hybrid_command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def nummembers(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
        """
        Display number of users on a server

        - `[guild]` can be either the guild ID or name.
         - Note: You must share the guild with the bot for this to work.
        """
        if not guild:
            guild = ctx.guild
        await ctx.send(
            "{} has {} members.".format(guild.name, humanize_number(guild.member_count))
        )

    @commands.guild_only()
    @commands.hybrid_command(aliases=["rolestats"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def getroles(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
        """
        Displays all roles their ID and number of members in order of
        hierarchy

        - `[guild]` can be either the guild ID or name.
         - Note: You must share the guild with the bot for this to work.
        """
        if not guild:
            guild = ctx.guild
        msg = ""
        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if ctx.channel.permissions_for(ctx.me).embed_links and guild is ctx.guild:
                msg += f"- {role.position}\\. `{role.id}` {role.mention}: {len(role.members)}\n"
            else:
                msg += f"- {role.position}\\. `{role.id}` {role.name}: {len(role.members)}\n"
        msg_list = []
        for page in pagify(msg, ["\n"]):
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed()
                embed.description = page
                embed.set_author(name=f"{guild.name} " + _("Roles"), icon_url=guild.icon)
                msg_list.append(embed)
            else:
                msg_list.append(page)
        await BaseView(
            source=ListPages(pages=msg_list),
            cog=self,
        ).start(ctx=ctx)

    async def check_highest(self, data):
        highest = 0
        users = 0
        for user, value in data.items():
            if value > highest:
                highest = value
                users = user
        return highest, users

    @commands.hybrid_command(name="getreactions", aliases=["getreaction"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def get_reactions(self, ctx: commands.Context, message: discord.Message) -> None:
        """
        Gets a list of all reactions from specified message and displays the user ID,
        Username, and Discriminator and the emoji name.
        """
        async with ctx.typing():
            new_msg = ""
            for reaction in message.reactions:
                async for user in reaction.users():
                    if isinstance(reaction.emoji, discord.PartialEmoji):
                        new_msg += f"{user.id} {str(user)} {reaction.emoji}\n"
                    else:
                        new_msg += f"{user.id} {str(user)} {reaction.emoji}\n"
            temp_pages = []
            pages = []
            for page in pagify(new_msg, shorten_by=20):
                temp_pages.append(box(page, "py"))
            max_i = len(temp_pages)
            i = 1
            for page in temp_pages:
                pages.append(f"`Page {i}/{max_i}`\n" + page)
                i += 1
        await BaseView(
            source=ListPages(pages=pages),
            cog=self,
        ).start(ctx=ctx)

    async def get_server_stats(
        self, guild: discord.Guild
    ) -> Dict[str, Union[str, Dict[str, int]]]:
        """
        This is a very expensive function but handles only pulling new
        data into config since the last time the command has been run.
        """

        # to_return: Dict[str, Union[int, Dict[int, int]]] = {
        # "last_checked": 0,
        # "members": {m.id: 0 for m in guild.members},
        # "total_posts": 0,
        # "channels": {},
        # } This is the data schema for saved data
        # It's all formatted easily for end user data request and deletion
        # to_return = await self.config.guild(guild).all()
        async with self.config.guild(guild).all() as to_return:
            for channel in guild.text_channels:
                my_perms = channel.permissions_for(guild.me)
                set_new_last_read = False

                if str(channel.id) not in to_return["channels"]:
                    to_return["channels"][str(channel.id)] = {}
                    to_return["channels"][str(channel.id)]["members"] = {}
                    to_return["channels"][str(channel.id)]["total"] = 0
                    to_return["channels"][str(channel.id)]["last_checked"] = 0
                    check_after = None
                else:
                    check_after = discord.Object(
                        id=to_return["channels"][str(channel.id)]["last_checked"]
                    )
                if not my_perms.read_message_history or not my_perms.read_messages:
                    continue
                try:
                    log.verbose("get_server_stats check_after: %s", check_after)
                    async for message in channel.history(
                        limit=None, after=check_after, oldest_first=False
                    ):
                        if not set_new_last_read:
                            log.debug("Setting last_checked to %s", message.id)
                            to_return["channels"][str(channel.id)]["last_checked"] = message.id
                            set_new_last_read = True
                        author = message.author
                        if author.discriminator == "0000" and author.bot:
                            continue
                        if str(author.id) not in to_return["members"]:
                            to_return["members"][str(author.id)] = 0
                        if str(author.id) not in to_return["channels"][str(channel.id)]["members"]:
                            to_return["channels"][str(channel.id)]["members"][str(author.id)] = 0
                        to_return["channels"][str(channel.id)]["members"][str(author.id)] += 1
                        to_return["channels"][str(channel.id)]["total"] += 1
                        to_return["members"][str(author.id)] += 1
                        to_return["total"] += 1

                except (AttributeError, discord.Forbidden):
                    log.debug("the heck", exc_info=True)
                    pass
            _ret = copy(to_return)
            # copy the data to prevent context manager from removing the reference
            log.verbose("get_server_stats _ret: %s", _ret)
        return _ret

    async def get_channel_stats(self, channel: discord.TextChannel) -> dict:
        """
        This is another expensive function but handles only pulling
        new data into config since the last time the command has been run.
        """
        guild = channel.guild
        async with self.config.guild(guild).all() as to_return:
            my_perms = channel.permissions_for(guild.me)
            set_new_last_read = False
            if channel.id not in to_return["channels"]:
                to_return["channels"][str(channel.id)] = {}
                to_return["channels"][str(channel.id)]["members"] = {}
                to_return["channels"][str(channel.id)]["total"] = 0
                to_return["channels"][str(channel.id)]["last_checked"] = 0
                check_after = None
            else:
                check_after = to_return["channels"][str(channel.id)]["last_checked"]
            if not my_perms.read_message_history or not my_perms.read_messages:
                return {}  # we shouldn't have even reached this far before
            try:
                async for message in channel.history(
                    limit=None, after=check_after, oldest_first=False
                ):
                    if not set_new_last_read:
                        to_return["channels"][str(channel.id)]["last_checked"] = message.id
                        set_new_last_read = True
                    author = message.author
                    if author.discriminator == "0000" and author.bot:
                        continue
                    if str(author.id) not in to_return["members"]:
                        to_return["members"][str(author.id)] = 0
                    if str(author.id) not in to_return["channels"][str(channel.id)]["members"]:
                        to_return["channels"][str(channel.id)]["members"][str(author.id)] = 0
                    to_return["channels"][str(channel.id)]["members"][str(author.id)] += 1
                    to_return["channels"][str(channel.id)]["total"] += 1
                    to_return["members"][str(author.id)] += 1
                    to_return["total"] += 1
                    # we still want to update the guild totals if we happened to  pull a specific channel
            except (AttributeError, discord.Forbidden):
                pass
            _ret = copy(to_return)
        return _ret

    @commands.hybrid_command(name="serverstats")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    @commands.guild_only()
    async def server_stats(
        self,
        ctx: commands.Context,
    ) -> None:
        """
        Gets total messages on the server and displays each channel
        separately as well as the user who has posted the most in each channel

        Note: This is a very slow function and may take some time to complete
        """

        warning_msg = _(
            "This can take a long time to gather all information for the first time! Are you sure you want to continue?"
        )
        pred = ConfirmView(ctx.author)
        # To anyone looking, this is intentionally red.
        # Testing this command in Red's #testing channel with over 2 million
        # messages took the bot nearly 2 days and still did not finish collecting
        # all the data. Therefore, I really don't want people doing this
        # if they're not prepared for it.
        pred.confirm_button.style = discord.ButtonStyle.red
        pred.message = await ctx.send(warning_msg, view=pred)
        await pred.wait()
        if not pred.result:
            await ctx.send(_("Alright I will not gather data."))
            return
        async with ctx.channel.typing():
            guild_data = await self.get_server_stats(ctx.guild)
            channel_messages = []
            member_messages = []

            sorted_chans = sorted(
                guild_data["channels"].items(), key=lambda x: x[1]["total"], reverse=True
            )
            sorted_members = sorted(
                guild_data["members"].items(), key=lambda x: x[1], reverse=True
            )
            for member_id, value in sorted_members[:5]:
                member_messages.append(f"<@!{member_id}>: {bold(humanize_number(value))}\n")

            try:
                most_messages_user_id = sorted_members[0][0]
            except IndexError:
                most_messages_user_id = None
            try:
                most_messages_user_num = sorted_members[0][1]
            except IndexError:
                most_messages_user_num = 0
            new_msg = (
                _("**Most posts on the server**\nTotal Messages: ")
                + bold(humanize_number(guild_data["total"]))
                + _("\nMost posts by ")
                + f"<@!{most_messages_user_id}> {bold(humanize_number(most_messages_user_num))}\n\n"
            )

            for channel_id, value in sorted_chans[:5]:
                sorted_members = sorted(
                    guild_data["channels"][channel_id]["members"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                most_messages_user_id = sorted_members[0][0]
                most_messages_user_num = sorted_members[0][1]
                maybe_guild = f"<@!{most_messages_user_id}>: {bold(humanize_number(int(most_messages_user_num)))}\n"
                channel_messages.append(
                    _("**Most posts in <#{}>**\nTotal Messages: ").format(channel_id)
                    + bold(humanize_number(int(value["total"])))
                    + _("\nMost posts by {}\n".format(maybe_guild))
                )
            em = discord.Embed(colour=await self.bot.get_embed_colour(ctx))
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon if ctx.guild.icon else None)
            em.description = f"{new_msg}{''.join(i for i in channel_messages)}"

            em.add_field(name=_("Top Members"), value="".join(i for i in member_messages))
        await ctx.send(embed=em)

    @commands.hybrid_command(name="channelstats")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def channel_stats(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = None,
    ) -> None:
        """
        Gets total messages in a specific channel as well as the user who
        has posted the most in that channel

        `limit` must be a number of messages to check, defaults to all messages
        Note: This can be a very slow function and may take some time to complete
        """
        warning_msg = _(
            "This can take a long time to gather all information for the first time! Are you sure you want to continue?"
        )
        pred = ConfirmView(ctx.author)
        # To anyone looking, this is intentionally red.
        # Testing this command in Red's #testing channel with over 2 million
        # messages took the bot nearly 2 days and still did not finish collecting
        # all the data. Therefore, I really don't want people doing this
        # if they're not prepared for it.
        pred.confirm_button.style = discord.ButtonStyle.red
        pred.message = await ctx.send(warning_msg, view=pred)
        await pred.wait()
        if not pred.result:
            return await ctx.send(_("Alright I will not gather data."))
        if not channel:
            channel = ctx.channel
        async with ctx.channel.typing():
            channel_data = await self.get_channel_stats(channel)
            member_messages = []
            sorted_members = sorted(
                channel_data["channels"][str(channel.id)]["members"].items(),
                key=lambda x: x[1],
                reverse=True,
            )
            for member_id, value in sorted_members[:5]:
                member_messages.append(f"<@!{member_id}>: {bold(humanize_number(value))}\n")
            try:
                most_messages_user_id = sorted_members[0][0]
            except IndexError:
                most_messages_user_id = None
            try:
                most_messages_user_num = sorted_members[0][1]
            except IndexError:
                most_messages_user_num = 0
            maybe_guild = f"<@!{most_messages_user_id}>: {bold(humanize_number(int(most_messages_user_num)))}\n"
            new_msg = (
                _("**Most posts in <#{}>**\nTotal Messages: ").format(channel.id)
                + bold(humanize_number(int(channel_data["channels"][str(channel.id)]["total"])))
                + _("\nMost posts by {}\n".format(maybe_guild))
            )

            em = discord.Embed(colour=await self.bot.get_embed_colour(ctx))
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
            em.description = f"{new_msg}"

            em.add_field(name=_("Top Members"), value="".join(i for i in member_messages))
        await ctx.send(embed=em)

    @commands.guild_only()
    @commands.hybrid_command(aliases=["serveremojis"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def guildemojis(
        self,
        ctx: commands.Context,
        id_emojis: Optional[bool] = False,
        *,
        guild: GuildConverter = None,
    ) -> None:
        """
        Display all server emojis in a menu that can be scrolled through

        `id_emojis` return the id of emojis. Default to False, set True
         if you want to see emojis ID's.
        - `[guild]` can be either the guild ID or name.
         - Note: You must share the guild with the bot for this to work.
        """
        if not guild:
            guild = ctx.guild
        msg = ""
        embed = discord.Embed(timestamp=ctx.message.created_at)
        embed.set_author(name=guild.name, icon_url=guild.icon)
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
            em.set_author(name=guild.name + _(" Emojis"), icon_url=guild.icon)
            regular = []
            msg = ""
            for emoji in page:
                msg += emoji
            em.description = msg
            em.set_footer(text="Page {} of {}".format(count, len(x)))
            count += 1
            emoji_embeds.append(em)
        if len(emoji_embeds) == 0:
            await ctx.send(_("There are no emojis on {guild}.").format(guild=guild.name))
        else:
            await BaseView(
                source=ListPages(pages=emoji_embeds),
                cog=self,
            ).start(ctx=ctx)
