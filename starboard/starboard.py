import logging
import asyncio
from typing import Union, Dict, Optional
from datetime import timedelta

import discord
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify

from .converters import StarboardExists, RealEmoji
from .events import StarboardEvents
from .starboard_entry import StarboardEntry, FakePayload
from .menus import BaseMenu, StarboardPages

_ = Translator("Starboard", __file__)
log = logging.getLogger("red.trusty-cogs.Starboard")

TimeConverter = commands.converter.TimedeltaConverter(
    minimum=timedelta(days=7), allowed_units=["days", "weeks"], default_unit="days"
)


@cog_i18n(_)
class Starboard(StarboardEvents, commands.Cog):
    """
    Create a starboard to *pin* those special comments indefinitely
    """

    __version__ = "2.5.1"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 356488795)
        self.config.register_global(purge_time=None)
        self.config.register_guild(starboards={})
        self.starboards: Dict[int, Dict[str, StarboardEntry]] = {}
        self.init_task: asyncio.Task = self.bot.loop.create_task(self.initialize())
        self.ready = asyncio.Event()
        self.cleanup_loop: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        log.debug("Started building starboards cache from config.")
        for guild_id in await self.config.all_guilds():
            self.starboards[guild_id] = {}
            all_data = await self.config.guild_from_id(guild_id).starboards()
            for name, data in all_data.items():
                try:
                    starboard = await StarboardEntry.from_json(data, guild_id)
                except Exception:
                    log.exception("error converting starboard")
                self.starboards[guild_id][name] = starboard

        self.cleanup_loop = asyncio.create_task(self.cleanup_old_messages())
        self.ready.set()
        log.debug("Done building starboards cache from config.")

    def cog_unload(self) -> None:
        self.ready.clear()
        self.init_task.cancel()
        if self.cleanup_loop:
            self.cleanup_loop.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        return self.ready.is_set()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    @commands.group()
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def starboard(self, ctx: commands.Context) -> None:
        """
        Commands for managing the starboard
        """

    @starboard.command(name="purge")
    @commands.is_owner()
    async def purge_threshold(
        self, ctx: commands.Context, *, time: TimeConverter = timedelta(seconds=0)
    ) -> None:
        """
        Define how long to keep message ID's for every starboard

        `<time>` is the number of days or weeks you want to keep starboard messages for.

        e.g. `[p]starboard purge 2 weeks`
        """
        if time.total_seconds() < 1:
            await self.config.purge_time.clear()
            await ctx.send(_("I will now keep message ID's indefinitely."))
            return
        await self.config.purge_time.set(int(time.total_seconds()))
        await ctx.send(
            _(
                "I will now prun messages that are {time} "
                "old or more every 24 hours.\n"
                "This will take effect after the next reload."
            ).format(time=humanize_timedelta(timedelta=time))
        )

    @starboard.command(name="info")
    @commands.bot_has_permissions(read_message_history=True, embed_links=True)
    async def starboard_info(self, ctx: commands.Context) -> None:
        """
        Display info on starboards setup on the server.
        """
        guild = ctx.guild
        await ctx.trigger_typing()
        if guild.id in self.starboards:
            await BaseMenu(source=StarboardPages(list(self.starboards[guild.id].values()))).start(
                ctx=ctx
            )

    @starboard.command(name="create", aliases=["add"])
    async def setup_starboard(
        self,
        ctx: commands.Context,
        name: str,
        channel: Optional[discord.TextChannel] = None,
        emoji: RealEmoji = "⭐",
    ) -> None:
        """
        Create a starboard on this server

        `<name>` is the name for the starboard and will be lowercase only
        `[channel]` is the channel where posts will be made defaults to current channel
        `[emoji=⭐]` is the emoji that will be used to add to the starboard defaults to ⭐
        """
        guild = ctx.message.guild
        name = name.lower()
        if channel is None:
            channel = ctx.message.channel
        if type(emoji) == discord.Emoji:
            if emoji not in guild.emojis:
                await ctx.send(_("That emoji is not on this guild!"))
                return
        if not channel.permissions_for(guild.me).send_messages:
            send_perms = _("I don't have permission to post in ")

            await ctx.send(send_perms + channel.mention)
            return

        if not channel.permissions_for(guild.me).embed_links:
            embed_perms = _("I don't have permission to embed links in ")
            await ctx.send(embed_perms + channel.mention)
            return
        if guild.id not in self.starboards:
            self.starboards[guild.id] = {}
        starboards = self.starboards[guild.id]
        if name in starboards:
            await ctx.send(_("{name} starboard name is already being used").format(name=name))
            return
        starboard = StarboardEntry(name=name, channel=channel.id, emoji=str(emoji), guild=guild.id)
        self.starboards[guild.id][name] = starboard
        await self._save_starboards(guild)
        msg = _("Starboard set to {channel} with emoji {emoji}").format(
            channel=channel.mention, emoji=emoji
        )
        await ctx.send(msg)

    @starboard.command(name="cleanup")
    async def cleanup(self, ctx: commands.Context) -> None:
        """
        Cleanup stored deleted channels or roles in the blocklist/allowlist
        """
        guild = ctx.guild
        if guild.id not in self.starboards:
            await ctx.send(_("There are no Starboards setup on this server."))
            return
        channels = 0
        boards = 0
        for name, starboard in self.starboards[guild.id].items():
            channel = guild.get_channel(starboard.channel)
            if channel is None:
                del self.starboards[guild.id][name]
                boards += 1
                continue
            if starboard.blacklist:
                for c in starboard.blacklist:
                    channel = guild.get_channel(c)
                    role = guild.get_role(c)
                    if channel is None and role is None:
                        self.starboards[guild.id][name].blacklist.remove(c)
                        channels += 1
            if starboard.whitelist:
                for c in starboard.whitelist:
                    channel = guild.get_channel(c)
                    role = guild.get_role(c)
                    if channel is None and role is None:
                        self.starboards[guild.id][name].whitelist.remove(c)
                        channels += 1
        await self._save_starboards(guild)
        msg = _(
            "Removed {channels} channels and roles, and {boards} boards " "that no longer exist"
        ).format(channels=channels, boards=boards)
        await ctx.send(msg)

    @starboard.command(name="remove", aliases=["delete", "del"])
    async def remove_starboard(
        self, ctx: commands.Context, starboard: Optional[StarboardExists]
    ) -> None:
        """
        Remove a starboard from the server

        `<name>` is the name for the starboard and will be lowercase only
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        del self.starboards[ctx.guild.id][starboard.name]
        await self._save_starboards(ctx.guild)
        await ctx.send(_("Deleted starboard {name}").format(name=starboard.name))

    @commands.command()
    @commands.guild_only()
    async def star(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        message: discord.Message,
    ) -> None:
        """
        Manually star a message

        `<name>` is the name of the starboard you would like to add the message to
        `<message>` is the message ID, `channel_id-message_id`, or a message link
        of the message you want to star
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if message.guild and message.guild.id != guild.id:
            await ctx.send(_("I cannot star messages from another server."))
            return
        if not starboard.enabled:
            error_msg = _("Starboard {name} isn't enabled.").format(name=starboard.name)
            await ctx.send(error_msg)
            return
        if not starboard.check_roles(ctx.message.author):
            error_msg = _(
                "One of your roles is blocked on {starboard} "
                "or you don't have a role that is allowed."
            ).format(starboard=starboard.name)
            await ctx.send(error_msg)
            return
        if not starboard.check_channel(self.bot, message.channel):
            error_msg = _(
                "That messages channel is either blocked, not "
                "in the allowlist, or designated NSFW while the "
                "{starboard} channel is not designated as NSFW."
            ).format(starboard=starboard.name)
            await ctx.send(error_msg)
            return
        fake_payload = FakePayload(
            guild_id=guild.id,
            message_id=message.id,
            channel_id=message.channel.id,
            user_id=ctx.author.id,
            emoji=starboard.emoji,
            event_type="REACTION_ADD",
        )
        await self._update_stars(fake_payload)

    @commands.command()
    @commands.guild_only()
    async def unstar(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        message: discord.Message,
    ) -> None:
        """
        Manually unstar a message

        `<name>` is the name of the starboard you would like to add the message to
        `<message>` is the message ID, `channe_id-message_id`, or a message link
        of the message you want to unstar
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if message.guild and message.guild.id != guild.id:
            await ctx.send(_("I cannot star messages from another server."))
            return
        if not starboard.enabled:
            error_msg = _("Starboard {name} isn't enabled.").format(name=starboard.name)
            await ctx.send(error_msg)
            return
        if not starboard.check_roles(ctx.message.author):
            error_msg = _(
                "One of your roles is blocked on {starboard} "
                "or you don't have a role that is allowed."
            ).format(starboard=starboard.name)
            await ctx.send(error_msg)
            return
        if not starboard.check_channel(self.bot, message.channel):
            error_msg = _(
                "That messages channel is either blocked, not "
                "in the allowlist, or designated NSFW while the "
                "{starboard} channel is not designated as NSFW."
            ).format(starboard=starboard.name)
            await ctx.send(error_msg)
            return
        fake_payload = FakePayload(
            guild_id=guild.id,
            message_id=message.id,
            channel_id=message.channel.id,
            user_id=ctx.author.id,
            emoji=starboard.emoji,
            event_type="REACTION_REMOVE",
        )
        await self._update_stars(fake_payload)

    @starboard.group(name="allowlist", aliases=["whitelist"])
    async def whitelist(self, ctx: commands.Context) -> None:
        """Add/Remove channels/roles from the allowlist"""
        pass

    @starboard.group(name="blocklist", aliases=["blacklist"])
    async def blacklist(self, ctx: commands.Context) -> None:
        """Add/Remove channels/roles from the blocklist"""
        pass

    @blacklist.command(name="add")
    async def blacklist_add(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        channel_or_role: Union[discord.TextChannel, discord.CategoryChannel, discord.Role],
    ) -> None:
        """
        Add a channel to the starboard blocklist

        `<name>` is the name of the starboard to adjust
        `<channel_or_role>` is the channel or role you would like to add to the blocklist
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if channel_or_role.id in starboard.blacklist:
            msg = _("{channel_or_role} is already blocked for starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)
            return
        else:
            self.starboards[ctx.guild.id][starboard.name].blacklist.append(channel_or_role.id)
            await self._save_starboards(guild)
            msg = _("{channel_or_role} blocked on starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)

    @blacklist.command(name="remove")
    async def blacklist_remove(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        channel_or_role: Union[discord.TextChannel, discord.CategoryChannel, discord.Role],
    ) -> None:
        """
        Remove a channel to the starboard blocklist

        `<name>` is the name of the starboard to adjust
        `<channel_or_role>` is the channel or role you would like to remove from the blocklist
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if channel_or_role.id not in starboard.blacklist:
            msg = _("{channel_or_role} is not on the blocklist for starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)
            return
        else:
            self.starboards[ctx.guild.id][starboard.name].blacklist.remove(channel_or_role.id)
            await self._save_starboards(guild)
            msg = _("{channel_or_role} removed from the blocklist on starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)

    @whitelist.command(name="add")
    async def whitelist_add(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        channel_or_role: Union[discord.TextChannel, discord.CategoryChannel, discord.Role],
    ) -> None:
        """
        Add a channel to the starboard allowlist

        `<name>` is the name of the starboard to adjust
        `<channel_or_role>` is the channel or role you would like to add to the allowlist
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]

        if channel_or_role.id in starboard.whitelist:
            msg = _("{channel_or_role} is already allowed for starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)
            return
        else:
            self.starboards[ctx.guild.id][starboard.name].whitelist.append(channel_or_role.id)
            await self._save_starboards(guild)
            msg = _("{channel_or_role} allowed on starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)
            if isinstance(channel_or_role, discord.TextChannel):
                star_channel = ctx.guild.get_channel(starboard.channel)
                if channel_or_role.is_nsfw() and not star_channel.is_nsfw():
                    await ctx.send(
                        _(
                            "The channel you have provided is designated "
                            "as NSFW but your starboard channel is not. "
                            "They will both need to be set the same "
                            "in order for this to work properly."
                        )
                    )

    @whitelist.command(name="remove")
    async def whitelist_remove(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        channel_or_role: Union[discord.TextChannel, discord.CategoryChannel, discord.Role],
    ) -> None:
        """
        Remove a channel to the starboard allowlist

        `<name>` is the name of the starboard to adjust
        `<channel_or_role>` is the channel or role you would like to remove from the allowlist
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if channel_or_role.id not in starboard.whitelist:
            msg = _("{channel_or_role} is not on the allowlist for starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)
            return
        else:
            self.starboards[ctx.guild.id][starboard.name].whitelist.remove(channel_or_role.id)
            await self._save_starboards(guild)
            msg = _("{channel_or_role} removed from the allowlist on starboard {name}").format(
                channel_or_role=channel_or_role.name, name=starboard.name
            )
            await ctx.send(msg)

    @starboard.command(name="channel", aliases=["channels"])
    async def change_channel(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        channel: discord.TextChannel,
    ) -> None:
        """
        Change the channel that the starboard gets posted to

        `<name>` is the name of the starboard to adjust
        `<channel>` The channel of the starboard.
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if not channel.permissions_for(guild.me).send_messages:
            send_perms = _("I don't have permission to post in ")
            await ctx.send(send_perms + channel.mention)
            return

        if not channel.permissions_for(guild.me).embed_links:
            embed_perms = _("I don't have permission to embed links in ")
            await ctx.send(embed_perms + channel.mention)
            return
        if channel.id == starboard.channel:
            msg = _("Starboard {name} is already posting in {channel}").format(
                name=starboard.name, channel=channel.mention
            )
            await ctx.send(msg)
            return
        self.starboards[ctx.guild.id][starboard.name].channel = channel.id
        await self._save_starboards(guild)
        msg = _("Starboard {name} set to post in {channel}").format(
            name=starboard.name, channel=channel.mention
        )
        await ctx.send(msg)

    @starboard.command(name="toggle")
    async def toggle_starboard(
        self, ctx: commands.Context, starboard: Optional[StarboardExists]
    ) -> None:
        """
        Toggle a starboard on/off

        `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if starboard.enabled:
            msg = _("Starboard {name} disabled.").format(name=starboard.name)
        else:
            msg = _("Starboard {name} enabled.").format(name=starboard.name)
        self.starboards[ctx.guild.id][starboard.name].enabled = not starboard.enabled
        await self._save_starboards(guild)
        await ctx.send(msg)

    @starboard.command(name="selfstar")
    async def toggle_selfstar(
        self, ctx: commands.Context, starboard: Optional[StarboardExists]
    ) -> None:
        """
        Toggle whether or not a user can star their own post

        `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if starboard.selfstar:
            msg = _("Selfstarring on starboard {name} disabled.").format(name=starboard.name)
        else:
            msg = _("Selfstarring on starboard {name} enabled.").format(name=starboard.name)
        self.starboards[ctx.guild.id][starboard.name].selfstar = not starboard.selfstar
        await self._save_starboards(guild)
        await ctx.send(msg)

    @starboard.command(name="autostar")
    async def toggle_autostar(
        self, ctx: commands.Context, starboard: Optional[StarboardExists]
    ) -> None:
        """
        Toggle whether or not the bot will add the emoji automatically to the starboard message.

        `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if starboard.autostar:
            msg = _("Autostarring on starboard {name} disabled.").format(name=starboard.name)
        else:
            msg = _("Autostarring on starboard {name} enabled.").format(name=starboard.name)
        self.starboards[ctx.guild.id][starboard.name].autostar = not starboard.autostar
        await self._save_starboards(guild)
        await ctx.send(msg)

    @starboard.command(name="colour", aliases=["color"])
    async def colour_starboard(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        colour: Union[discord.Colour, str],
    ) -> None:
        """
        Change the default colour for a starboard

        `<name>` is the name of the starboard to toggle
        `<colour>` The colour to use for the starboard embed
        This can be a hexcode or integer for colour or `author/member/user` to use
        the original posters colour or `bot` to use the bots colour.
        Colour also accepts names from
        [discord.py](https://discordpy.readthedocs.io/en/latest/api.html#colour)
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if isinstance(colour, str):
            colour = colour.lower()
            if colour not in ["user", "member", "author", "bot"]:
                await ctx.send(_("The provided colour option is not valid."))
                return
            else:
                starboard.colour = colour
        else:
            self.starboards[ctx.guild.id][starboard.name].colour = colour.value
        await self._save_starboards(guild)
        msg = _("Starboard `{name}` colour set to `{colour}`.").format(
            name=starboard.name, colour=starboard.colour
        )
        await ctx.send(msg)

    @starboard.command(name="emoji")
    async def set_emoji(
        self,
        ctx: commands.Context,
        starboard: Optional[StarboardExists],
        emoji: RealEmoji,
    ) -> None:
        """
        Set the emoji for the starboard

        `<name>` is the name of the starboard to change the emoji for
        `<emoji>` must be an emoji on the server or a default emoji
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if type(emoji) == discord.Emoji:
            if emoji not in guild.emojis:
                await ctx.send(_("That emoji is not on this guild!"))
                return
        self.starboards[ctx.guild.id][starboard.name].emoji = str(emoji)
        await self._save_starboards(guild)
        msg = _("{emoji} set for starboard {name}").format(emoji=emoji, name=starboard.name)
        await ctx.send(msg)

    @starboard.command(name="threshold")
    async def set_threshold(
        self, ctx: commands.Context, starboard: Optional[StarboardExists], threshold: int
    ) -> None:
        """
        Set the threshold before posting to the starboard

        `<name>` is the name of the starboard to change the threshold for
        `<threshold>` must be a number of reactions before a post gets
        moved to the starboard
        """
        guild = ctx.guild
        if not starboard:
            if guild.id not in self.starboards:
                await ctx.send(_("There are no starboards setup on this server!"))
                return
            if len(self.starboards[guild.id]) > 1:
                await ctx.send(
                    _(
                        "There's more than one starboard setup in this server. "
                        "Please provide a name for the starboard you wish to use."
                    )
                )
                return
            starboard = list(self.starboards[guild.id].values())[0]
        if threshold <= 0:
            threshold = 1
        self.starboards[ctx.guild.id][starboard.name].threshold = threshold
        await self._save_starboards(guild)
        msg = _("Threshold of {threshold} reactions set for {name}").format(
            threshold=threshold, name=starboard.name
        )
        await ctx.send(msg)
