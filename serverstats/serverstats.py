import asyncio
import datetime
import logging
from copy import copy
from io import BytesIO
from typing import Dict, List, Literal, Optional, Tuple, Union, cast

import aiohttp
import discord
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import (
    bold,
    box,
    escape,
    humanize_number,
    humanize_timedelta,
    pagify,
)
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

from .converters import ChannelConverter, FuzzyMember, GuildConverter, MultiGuildConverter
from .menus import BaseMenu, AvatarPages, GuildPages, ListPages

_ = Translator("ServerStats", __file__)
log = logging.getLogger("red.trusty-cogs.ServerStats")


@cog_i18n(_)
class ServerStats(commands.Cog):
    """
    Gather useful information about servers the bot is in
    A lot of commands are bot owner only
    """

    __author__ = ["TrustyJAID", "Preda"]
    __version__ = "1.5.4"

    def __init__(self, bot):
        self.bot: Red = bot
        default_global: dict = {"join_channel": None}
        default_guild: dict = {"last_checked": 0, "members": {}, "total": 0, "channels": {}}
        self.config: Config = Config.get_conf(self, 54853421465543, force_registration=True)
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)

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

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def avatar(self, ctx: commands.Context, *, members: Optional[FuzzyMember]):
        """
        Display a users avatar in chat
        """
        if members is None:
            members = [ctx.author]

        await BaseMenu(
            source=AvatarPages(members=members),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
        ).start(ctx=ctx)

    @commands.Cog.listener()
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
            num=humanize_number(len(self.bot.guilds)),
            users=humanize_number(len(self.bot.users)),
            since=guild.created_at.strftime("%d %b %Y %H:%M:%S"),
            passed=passed,
        )
        try:
            em = await self.guild_embed(guild)
            em.description = created_at
            await channel.send(embed=em)
        except Exception:
            log.error(f"Error creating guild embed for new guild ID {guild.id}", exc_info=True)

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
            for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
                if abs(num) < 1000.0:
                    return "{0:.1f}{1}".format(num, unit)
                num /= 1000.0
            return "{0:.1f}{1}".format(num, "YB")

        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _("Created on {date}. That's over {num} days ago!").format(
            date=bold(guild.created_at.strftime("%d %b %Y %H:%M")),
            num=bold(humanize_number(passed)),
        )
        total_users = humanize_number(guild.member_count)
        try:
            joined_at = guild.me.joined_at
        except AttributeError:
            joined_at = datetime.datetime.utcnow()
        bot_joined = joined_at.strftime("%d %b %Y %H:%M:%S")
        since_joined = (datetime.datetime.utcnow() - joined_at).days
        joined_on = _(
            "**{bot_name}** joined this server on **{bot_join}**.\n"
            "That's over **{since_join}** days ago!"
        ).format(bot_name=self.bot.user.name, bot_join=bot_joined, since_join=since_joined)
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
            except Exception as error:
                print(error)
                continue
            else:
                member_msg += f"{emoji} {bold(humanize_number(num))} " + (
                    "\n" if count % 2 == 0 else ""
                )
            count += 1

        text_channels = len(guild.text_channels)
        nsfw_channels = len([c for c in guild.text_channels if c.is_nsfw()])
        voice_channels = len(guild.voice_channels)

        vc_regions = {
            "vip-us-east": _("__VIP__ US East ") + "\U0001F1FA\U0001F1F8",
            "vip-us-west": _("__VIP__ US West ") + "\U0001F1FA\U0001F1F8",
            "vip-amsterdam": _("__VIP__ Amsterdam ") + "\U0001F1F3\U0001F1F1",
            "eu-west": _("EU West ") + "\U0001F1EA\U0001F1FA",
            "eu-central": _("EU Central ") + "\U0001F1EA\U0001F1FA",
            "europe": _("Europe ") + "\U0001F1EA\U0001F1FA",
            "london": _("London ") + "\U0001F1EC\U0001F1E7",
            "frankfurt": _("Frankfurt ") + "\U0001F1E9\U0001F1EA",
            "amsterdam": _("Amsterdam ") + "\U0001F1F3\U0001F1F1",
            "us-west": _("US West ") + "\U0001F1FA\U0001F1F8",
            "us-east": _("US East ") + "\U0001F1FA\U0001F1F8",
            "us-south": _("US South ") + "\U0001F1FA\U0001F1F8",
            "us-central": _("US Central ") + "\U0001F1FA\U0001F1F8",
            "singapore": _("Singapore ") + "\U0001F1F8\U0001F1EC",
            "sydney": _("Sydney ") + "\U0001F1E6\U0001F1FA",
            "brazil": _("Brazil ") + "\U0001F1E7\U0001F1F7",
            "hongkong": _("Hong Kong ") + "\U0001F1ED\U0001F1F0",
            "russia": _("Russia ") + "\U0001F1F7\U0001F1FA",
            "japan": _("Japan ") + "\U0001F1EF\U0001F1F5",
            "southafrica": _("South Africa ") + "\U0001F1FF\U0001F1E6",
            "india": _("India ") + "\U0001F1EE\U0001F1F3",
            "south-korea": _("South Korea ") + "\U0001f1f0\U0001f1f7",
        }  # Unicode is needed because bold() is escaping emojis for some reason in this case.
        verif = {
            "none": _("0 - None"),
            "low": _("1 - Low"),
            "medium": _("2 - Medium"),
            "high": _("3 - High"),
            "extreme": _("4 - Extreme"),
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
            f"✅ {name}" for feature, name in features.items() if feature in guild.features
        ]

        em = discord.Embed(
            description=(f"{guild.description}\n\n" if guild.description else "")
            + f"{created_at}\n{joined_on}",
            colour=colour,
        )
        em.set_author(
            name=guild.name,
            icon_url="https://cdn.discordapp.com/emojis/457879292152381443.png"
            if "VERIFIED" in guild.features
            else "https://cdn.discordapp.com/emojis/508929941610430464.png"
            if "PARTNERED" in guild.features
            else discord.Embed.Empty,
            url=guild.icon_url
            if guild.icon_url
            else "https://cdn.discordapp.com/embed/avatars/1.png",
        )
        em.set_thumbnail(
            url=guild.icon_url
            if guild.icon_url
            else "https://cdn.discordapp.com/embed/avatars/1.png"
        )
        em.add_field(name=_("Members:"), value=member_msg)
        em.add_field(
            name=_("Channels:"),
            value=_(
                "\N{SPEECH BALLOON} Text: {text}\n{nsfw}"
                "\N{SPEAKER WITH THREE SOUND WAVES} Voice: {voice}"
            ).format(
                text=bold(humanize_number(text_channels)),
                nsfw=_("\N{NO ONE UNDER EIGHTEEN SYMBOL} Nsfw: {}\n").format(
                    bold(humanize_number(nsfw_channels))
                )
                if nsfw_channels
                else "",
                voice=bold(humanize_number(voice_channels)),
            ),
        )
        owner = guild.owner if guild.owner else await self.bot.get_or_fetch_user(guild.owner_id)
        em.add_field(
            name=_("Utility:"),
            value=_(
                "Owner: {owner_mention}\n{owner}\nRegion: {region}\nVerif. level: {verif}\nServer ID: {id}{shard}"
            ).format(
                owner_mention=bold(str(owner.mention)),
                owner=bold(str(owner)),
                region=f"**{vc_regions.get(str(guild.region)) or str(guild.region)}**",
                verif=bold(verif[str(guild.verification_level)]),
                id=bold(str(guild.id)),
                shard=shard,
            ),
            inline=False,
        )
        em.add_field(
            name=_("Misc:"),
            value=_(
                "AFK channel: {afk_chan}\nAFK timeout: {afk_timeout}\nCustom emojis: {emojis}\nRoles: {roles}"
            ).format(
                afk_chan=bold(str(guild.afk_channel)) if guild.afk_channel else bold(_("Not set")),
                afk_timeout=bold(humanize_timedelta(seconds=guild.afk_timeout)),
                emojis=bold(humanize_number(len(guild.emojis))),
                roles=bold(humanize_number(len(guild.roles))),
            ),
            inline=False,
        )
        if guild_features_list:
            em.add_field(name=_("Server features:"), value="\n".join(guild_features_list))
        if guild.premium_tier != 0:
            nitro_boost = _(
                "Tier {boostlevel} with {nitroboosters} boosters\n"
                "File size limit: {filelimit}\n"
                "Emoji limit: {emojis_limit}\n"
                "VCs max bitrate: {bitrate}"
            ).format(
                boostlevel=bold(str(guild.premium_tier)),
                nitroboosters=bold(humanize_number(guild.premium_subscription_count)),
                filelimit=bold(_size(guild.filesize_limit)),
                emojis_limit=bold(str(guild.emoji_limit)),
                bitrate=bold(_bitsize(guild.bitrate_limit)),
            )
            em.add_field(name=_("Nitro Boost:"), value=nitro_boost)
        if guild.splash:
            em.set_image(url=guild.splash_url_as(format="png"))
        return em

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
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
            num=humanize_number(len(self.bot.guilds)),
            users=humanize_number(len(self.bot.users)),
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
    async def emoji(
        self, ctx: commands.Context, emoji: Union[discord.Emoji, discord.PartialEmoji, str]
    ) -> None:
        """
        Post a large size emojis in chat
        """
        await ctx.channel.trigger_typing()
        if type(emoji) in [discord.PartialEmoji, discord.Emoji]:
            d_emoji = cast(discord.Emoji, emoji)
            ext = "gif" if d_emoji.animated else "png"
            url = "https://cdn.discordapp.com/emojis/{id}.{ext}?v=1".format(id=d_emoji.id, ext=ext)
            filename = "{name}.{ext}".format(name=d_emoji.name, ext=ext)
        else:
            try:
                """https://github.com/glasnt/emojificate/blob/master/emojificate/filter.py"""
                cdn_fmt = "https://twemoji.maxcdn.com/2/72x72/{codepoint:x}.png"
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

    @commands.command()
    async def botstats(self, ctx: commands.Context) -> None:
        """Display stats about the bot"""
        async with ctx.typing():
            servers = len(ctx.bot.guilds)
            passed = (datetime.datetime.utcnow() - ctx.me.created_at).days
            since = ctx.me.created_at.strftime("%d %b %Y %H:%M")
            msg = _(
                "{bot} is on {servers} servers serving {members} members!\n"
                "{bot} was created on **{since}**.\n"
                "That's over **{passed}** days ago!"
            ).format(
                bot=ctx.me.mention,
                servers=servers,
                members=len(self.bot.users),
                since=since,
                passed=passed,
            )
            em = discord.Embed(
                description=msg, colour=await ctx.embed_colour(), timestamp=ctx.message.created_at
            )
            if ctx.guild:
                em.set_author(
                    name=f"{ctx.me} {f'~ {ctx.me.nick}' if ctx.me.nick else ''}",
                    icon_url=ctx.me.avatar_url,
                )
            else:
                em.set_author(
                    name=f"{ctx.me}",
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
    async def topic(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, topic: str = ""
    ) -> None:
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
    async def channeledit(self, ctx: commands.Context) -> None:
        """Modify channel options"""
        pass

    @channeledit.command(name="name")
    @checks.mod_or_permissions(manage_channels=True)
    @checks.bot_has_permissions(manage_channels=True)
    async def channel_name(
        self, ctx: commands.Context, channel: Optional[ChannelConverter], *, name: str
    ) -> None:
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
    async def channel_position(
        self, ctx: commands.Context, channel: Optional[ChannelConverter], position: int
    ) -> None:
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
    async def channel_sync(
        self, ctx: commands.Context, channel: Optional[ChannelConverter], toggle: bool
    ) -> None:
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
    async def channel_nsfw(
        self, ctx: commands.Context, toggle: bool, channel: discord.TextChannel = None
    ) -> None:
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
    async def channel_topic(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, topic: str
    ) -> None:
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
    async def channel_bitrate(
        self, ctx: commands.Context, channel: discord.VoiceChannel, bitrate: int
    ) -> None:
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
    async def channel_userlimit(
        self, ctx: commands.Context, channel: discord.VoiceChannel, limit: int
    ) -> None:
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
    async def list(self, ctx: commands.Context, days: int, role: discord.Role = None) -> None:
        """
        List the users who have not talked in x days
        """
        if days < 1:
            return await ctx.send(_("You must provide a value of more than 0 days."))
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
        if msg_list != []:
            await BaseMenu(
                source=ListPages(pages=msg_list),
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=60,
                cog=self,
                page_start=0,
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

        `days` is the number of days since last seen talking on the server
        `role` is the specified role you would like to kick defaults to everyone
        `reinvite` True/False whether to try to send the user a message before kicking
        """
        if days < 1:
            return await ctx.send(_("You must provide a value of more than 0 days."))
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
            await self.bot.wait_for("reaction_add", check=pred, timeout=60)
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
    async def add(self, ctx: commands.Context, days: int, *new_roles: discord.Role) -> None:
        """
        Give roles to users who haven't spoken in x days

        `days` is the number of days since last seen talking on the server
        `new_roles` The new roles to apply to a user who is inactive
        """
        if days < 1:
            return await ctx.send(_("You must provide a value of more than 0 days."))
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
            await self.bot.wait_for("reaction_add", check=pred, timeout=60)
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
    async def remove(self, ctx: commands.Context, days: int, *removed_roles: discord.Role) -> None:
        """
        Remove roles from users who haven't spoken in x days

        `days` is the number of days since last seen talking on the server
        `role` is the specified role you would like to remove roles defaults to everyone
        `removed_roles` the roles to remove from inactive users
        """
        if days < 1:
            return await ctx.send(_("You must provide a value of more than 0 days."))
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
            await self.bot.wait_for("reaction_add", check=pred, timeout=60)
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
        await self.config.join_channel.set(None)
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

    @commands.command()
    async def whois(
        self, ctx: commands.Context, *, user_id: Union[int, discord.Member, discord.User]
    ) -> None:
        """
        Display servers a user shares with the bot

        `member` can be a user ID or mention
        """
        if not user_id:
            return await ctx.send(_("You need to supply a user ID for this to work properly."))
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
        embed = discord.Embed()
        since_created = (ctx.message.created_at - member.created_at).days
        user_created = member.created_at.strftime("%d %b %Y %H:%M")
        created_on = _("Joined Discord on {}\n({} days ago)").format(user_created, since_created)
        embed.description = created_on
        embed.set_thumbnail(url=member.avatar_url)
        embed.colour = await ctx.embed_colour()
        embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
        if await self.bot.is_owner(ctx.author):
            guild_list = [
                m
                async for m in AsyncIter(self.bot.get_all_members(), steps=500)
                if m.id == member.id
            ]
        else:
            guild_list = [
                m
                async for m in AsyncIter(self.bot.get_all_members(), steps=500)
                if m.id == member.id and ctx.author in m.guild.members
            ]

        if guild_list != []:
            msg = f"**{member}** ({member.id}) " + _("is on:\n\n")
            embed_list = ""
            for m in guild_list:
                # m = guild.get_member(member.id)
                is_owner = ""
                nick = ""
                if m.id == m.guild.owner_id:
                    is_owner = "\N{CROWN}"
                if m.nick:
                    nick = f"`{m.nick}` in"
                msg += f"{is_owner}{nick} __{m.guild.name}__ ({m.guild.id})\n\n"
                embed_list += f"{is_owner}{nick} __{m.guild.name}__ ({m.guild.id})\n\n"
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

    @commands.command(hidden=True)
    @checks.is_owner()
    async def topservers(self, ctx: commands.Context) -> None:
        """
        Lists servers by number of users and shows number of users
        """
        guilds = sorted(list(self.bot.guilds), key=lambda s: s.member_count, reverse=True)
        msg = ""
        msg_list = []
        count = 0
        for _, server in enumerate(guilds):
            if count == 10:
                msg_list.append(msg)
                msg = ""
                count = 0
            msg += f"{escape(server.name, mass_mentions=True, formatting=True)}: `{humanize_number(server.member_count)}`\n"
            count += 1
        msg_list.append(msg)
        await BaseMenu(
            source=ListPages(pages=msg_list),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def newservers(self, ctx: commands.Context) -> None:
        """
        Lists servers by when the bot was added to the server
        """
        guilds = sorted(list(self.bot.guilds), key=lambda s: s.me.joined_at)
        msg = ""
        msg_list = []
        count = 0
        for _, server in enumerate(guilds):
            if count == 10:
                msg_list.append(msg)
                msg = ""
                count = 0
            msg += f"{escape(server.name, mass_mentions=True, formatting=True)}: `{humanize_number(server.member_count)}`\n"
            count += 1
        msg_list.append(msg)
        await BaseMenu(
            source=ListPages(pages=msg_list),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def guildedit(self, ctx: commands.Context) -> None:
        """Edit various guild settings"""
        pass

    @guildedit.command(name="name")
    async def guild_name(self, ctx: commands.Context, *, name: str):
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
    async def verifivation_level(self, ctx: commands.Context, *, level: str) -> None:
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
    async def system_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
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
    async def afk_channel(
        self, ctx: commands.Context, channel: discord.VoiceChannel = None
    ) -> None:
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
    async def afk_timeout(self, ctx: commands.Context, timeout: int) -> None:
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
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def topmembers(
        self, ctx: commands.Context, number: int = 10, guild: GuildConverter = None
    ) -> None:
        """
        Lists top members on the server by join date

        `number` optional[int] number of members to display at a time maximum of 50
        `guild` can be either the server ID or name
        """
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
        await BaseMenu(
            source=ListPages(pages=msg_list),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @commands.command()
    @checks.is_owner()
    async def listchannels(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
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

    @staticmethod
    async def confirm_leave_guild(ctx: commands.Context, guild) -> None:
        await ctx.send(
            _("Are you sure you want me to leave {guild}? (reply yes or no)").format(guild=guild.name)
        )
        pred = MessagePredicate.yes_or_no(ctx)
        await ctx.bot.wait_for("message", check=pred)
        if pred.result is True:
            try:
                await ctx.send(_("Leaving {guild}.").format(guild=guild.name))
                await guild.leave()
            except Exception:
                log.error(
                    _("I couldn't leave {guild} ({g_id}).").format(
                        guild=guild.name, g_id=guild.id
                    ),
                    exc_info=True,
                )
                await ctx.send(_("I couldn't leave {guild}.").format(guild=guild.name))
        else:
            await ctx.send(_("Okay, not leaving {guild}.").format(guild=guild.name))

    @staticmethod
    async def get_guild_invite(guild: discord.Guild, max_age: int = 86400) -> None:
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
    async def getguild(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
        """
        Display info about servers the bot is on

        `guild_name` can be either the server ID or partial name
        """
        if not ctx.guild and not await ctx.bot.is_owner(ctx.author):
            return await ctx.send(_("This command is not available in DM."))
        guilds = [ctx.guild]
        page = 0
        if await ctx.bot.is_owner(ctx.author):
            page = ctx.bot.guilds.index(ctx.guild)
            guilds = ctx.bot.guilds
            if guild:
                page = ctx.bot.guilds.index(guild)

        await BaseMenu(
            source=GuildPages(guilds=guilds),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=page,
        ).start(ctx=ctx)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    @checks.admin()
    async def getguilds(self, ctx: commands.Context, *, guilds: MultiGuildConverter) -> None:
        """
        Display info about multiple servers

        `guild_name` can be either the server ID or partial name
        """
        page = 0
        if not guilds:
            guilds = ctx.bot.guilds
            page = ctx.bot.guilds.index(ctx.guild)
        await BaseMenu(
            source=GuildPages(guilds=guilds),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=page,
        ).start(ctx=ctx)

    @commands.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def nummembers(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
        """
        Display number of users on a server

        `guild_name` can be either the server ID or partial name
        """
        if not guild:
            guild = ctx.guild
        await ctx.send(
            "{} has {} members.".format(guild.name, humanize_number(guild.member_count))
        )

    @commands.guild_only()
    @commands.command(aliases=["rolestats"])
    @checks.mod_or_permissions(manage_messages=True)
    async def getroles(self, ctx: commands.Context, *, guild: GuildConverter = None) -> None:
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
        await BaseMenu(
            source=ListPages(pages=msg_list),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

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
    async def get_reactions(self, ctx: commands.Context, message: discord.Message) -> None:
        """
        Gets a list of all reactions from specified message and displays the user ID,
        Username, and Discriminator and the emoji name.
        """
        new_msg = ""
        for reaction in message.reactions:
            async for user in reaction.users():
                if isinstance(reaction.emoji, discord.PartialEmoji):
                    new_msg += "{} {}#{} {}\n".format(
                        user.id, user.name, user.discriminator, reaction.emoji.name
                    )
                else:
                    new_msg += "{} {}#{} {}\n".format(
                        user.id, user.name, user.discriminator, reaction.emoji
                    )
        temp_pages = []
        pages = []
        for page in pagify(new_msg, shorten_by=20):
            temp_pages.append(box(page, "py"))
        max_i = len(temp_pages)
        i = 1
        for page in temp_pages:
            pages.append(f"`Page {i}/{max_i}`\n" + page)
            i += 1
        await BaseMenu(
            source=ListPages(pages=pages),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
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
                    log.debug(check_after)
                    async for message in channel.history(
                        limit=None, after=check_after, oldest_first=False
                    ):
                        if not set_new_last_read:
                            log.debug(f"Setting last_checked to {message.id}")
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
            log.debug(_ret)
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

    @commands.command(name="serverstats")
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

        warning_msg = await ctx.send(
            _(
                "This can take a long time to gather all information for the first time! Are you sure you want to continue?"
            )
        )
        pred = ReactionPredicate.yes_or_no(warning_msg, ctx.author)
        start_adding_reactions(warning_msg, ReactionPredicate.YES_OR_NO_EMOJIS)

        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
        if not pred.result:
            return await ctx.send(_("Alright I will not gather data."))
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

            most_messages_user_id = sorted_members[0][0]
            most_messages_user_num = sorted_members[0][1]
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
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
            em.description = f"{new_msg}{''.join(i for i in channel_messages)}"

            em.add_field(name=_("Top Members"), value="".join(i for i in member_messages))
        await ctx.send(embed=em)

    @commands.command(name="channelstats")
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
        warning_msg = await ctx.send(
            _(
                "This can take a long time to gather all information for the first time! Are you sure you want to continue?"
            )
        )
        pred = ReactionPredicate.yes_or_no(warning_msg, ctx.author)
        start_adding_reactions(warning_msg, ReactionPredicate.YES_OR_NO_EMOJIS)

        try:
            await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(_("I guess not."), delete_after=30)
            return
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
            log.info(channel_data)
            for member_id, value in sorted_members[:5]:
                member_messages.append(f"<@!{member_id}>: {bold(humanize_number(value))}\n")
            most_messages_user_id = sorted_members[0][0]
            most_messages_user_num = sorted_members[0][1]
            maybe_guild = f"<@!{most_messages_user_id}>: {bold(humanize_number(int(most_messages_user_num)))}\n"
            new_msg = (
                _("**Most posts in <#{}>**\nTotal Messages: ").format(channel.id)
                + bold(humanize_number(int(channel_data["channels"][str(channel.id)]["total"])))
                + _("\nMost posts by {}\n".format(maybe_guild))
            )

            em = discord.Embed(colour=await self.bot.get_embed_colour(ctx))
            em.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
            em.description = f"{new_msg}"

            em.add_field(name=_("Top Members"), value="".join(i for i in member_messages))
        await ctx.send(embed=em)

    @commands.guild_only()
    @commands.command(aliases=["serveremojis"])
    @commands.bot_has_permissions(embed_links=True)
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
        if len(emoji_embeds) == 0:
            await ctx.send(_("There are no emojis on {guild}.").format(guild=guild.name))
        else:
            await BaseMenu(
                source=ListPages(pages=emoji_embeds),
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=60,
                cog=self,
                page_start=0,
            ).start(ctx=ctx)
