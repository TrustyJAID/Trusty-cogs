import discord
import logging

from typing import Union, Optional

from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .converters import StarboardExists
from .events import StarboardEvents
from .message_entry import StarboardMessage
from .starboard_entry import StarboardEntry

_ = Translator("Starboard", __file__)
log = logging.getLogger("red.trusty-cogs.Starboard")


@cog_i18n(_)
class Starboard(StarboardEvents, commands.Cog):
    """
        Create a starboard to *pin* those special comments indefinitely
    """

    __version__ = "2.2.5"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        default_guild = {"starboards": {}}

        self.config = Config.get_conf(self, 356488795)
        self.config.register_guild(**default_guild)
        self.starboards = {}

    async def initialize(self) -> None:
        for guild_id in await self.config.all_guilds():
            self.starboards[guild_id] = {}
            all_data = await self.config.guild(discord.Object(id=guild_id)).starboards()
            for name, data in all_data.items():
                starboard = StarboardEntry.from_json(data)
                self.starboards[guild_id][name] = starboard

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

    @starboard.command(name="info")
    async def starboard_info(self, ctx: commands.Context) -> None:
        """
            Display info on starboards setup on the server.
        """
        guild = ctx.guild
        if await self.config.guild(guild).starboards():
            embeds = []
            texts = []
            channel_perms = ctx.channel.permissions_for(ctx.guild.me)
            for name, starboard in self.starboards[ctx.guild.id].items():
                embed, text = await self._build_starboard_info(ctx, starboard)
                embeds.append(embed)
                texts.append(text)
            if channel_perms.embed_links:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                await menu(ctx, texts, DEFAULT_CONTROLS)

    @starboard.command(name="create", aliases=["add"])
    async def setup_starboard(
        self,
        ctx: commands.Context,
        name: str,
        channel: discord.TextChannel = None,
        emoji: Union[discord.Emoji, str] = "⭐",
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
        starboard = StarboardEntry(name, channel.id, str(emoji))
        starboards[name] = starboard
        await self._save_starboards(guild)
        msg = _("Starboard set to {channel} with emoji {emoji}").format(
            channel=channel.mention, emoji=emoji
        )
        await ctx.send(msg)

    @starboard.command(name="cleanup")
    async def cleanup(self, ctx: commands.Context) -> None:
        """
            Cleanup stored deleted channels or roles in the blacklist/whitelist
        """
        guild = ctx.guild
        if guild.id not in self.starboards:
            await ctx.send(_("There are no Starboards setup on this server."))
            return
        roles = 0
        channels = 0
        boards = 0
        for name, starboard in self.starboards[guild.id].items():
            channel = guild.get_channel(starboard.channel)
            if channel is None:
                del self.starboards[guild.id][name]
                boards += 1
                continue
            if starboard.blacklist_channel:
                for c in starboard.blacklist_channel:
                    channel = guild.get_channel(c)
                    if channel is None:
                        self.starboards[guild.id][name].blacklist_channel.remove(c)
                        channels += 1
            if starboard.whitelist_channel:
                for c in starboard.whitelist_channel:
                    channel = guild.get_channel(c)
                    if channel is None:
                        self.starboards[guild.id][name].whitelist_channel.remove(c)
                        channels += 1
            if starboard.blacklist_role:
                for r in starboard.blacklist_role:
                    role = guild.get_role(r)
                    if role is None:
                        self.starboards[guild.id][name].blacklist_role.remove(r)
                        roles += 1
            if starboard.whitelist_role:
                for r in starboard.whitelist_role:
                    role = guild.get_role(r)
                    if role is None:
                        self.starboards[guild.id][name].whitelist_role.remove(r)
                        roles += 1
        await self._save_starboards(guild)
        msg = _(
            "Removed {channels} channels, {roles} roles and {boards} boards "
            "that no longer exist"
        ).format(channels=channels, roles=roles, boards=boards)
        await ctx.send(msg)

    @starboard.command(name="remove", aliases=["delete", "del"])
    async def remove_starboard(self, ctx: commands.Context, starboard: StarboardExists) -> None:
        """
            Remove a starboard from the server

            `<name>` is the name for the starboard and will be lowercase only
        """
        del self.starboards[ctx.guild.id][starboard.name]
        await self._save_starboards(ctx.guild)
        await ctx.send(_("Deleted starboard {name}").format(name=starboard.name))

    @commands.command()
    @commands.guild_only()
    async def star(
        self,
        ctx: commands.Context,
        starboard: StarboardExists,
        msg_id: int,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
            Manually star a message

            `<name>` is the name of the starboard you would like to add the message to
            `<msg_id>` is the message ID you want to star
            `[channel]` is the channel where that message is located
        """
        guild = ctx.guild
        if channel is None:
            channel = ctx.message.channel
        try:
            try:
                msg = await ctx.channel.fetch_message(msg_id)
            except AttributeError:
                msg = await channel.get_message(msg_id)  # type: ignore
        except discord.errors.NotFound:
            error_msg = _("That message doesn't appear to exist in the specified channel.")
            return await ctx.send(error_msg)
        except discord.errors.Forbidden:
            error_msg = _("I do not have permission to read this channels history.")
            return await ctx.send(error_msg)
        if not starboard.enabled:
            error_msg = _("Starboard {name} isn't enabled.").format(name=starboard.name)
            await ctx.send(error_msg)
            return
        if not await self._check_roles(starboard, ctx.message.author):
            error_msg = _(
                "One of your roles is blacklisted or you don't have the whitelisted role."
            )
            await ctx.send(error_msg)
            return
        if not await self._check_channel(starboard, channel):
            error_msg = _("This channel is either blacklisted or not in the whitelisted channels.")
            await ctx.send(error_msg)
            return
        count = 1
        star_channel = self.bot.get_channel(starboard.channel)
        for messages in [StarboardMessage.from_json(m) for m in starboard.messages]:
            same_msg = messages.original_message == msg.id
            same_channel = messages.original_channel == channel.id
            if same_msg and same_channel and messages.new_message:
                try:
                    msg_edit = await star_channel.get_message(messages.new_message)
                except AttributeError:
                    msg_edit = await star_channel.fetch_message(messages.new_message)
                count_msg = f"{starboard.emoji} **#{count}**"
                await msg_edit.edit(content=count_msg)
                return

        em = await self._build_embed(guild, msg, starboard)
        count_msg = f"{starboard.emoji} **#{count}**"
        post_msg = await star_channel.send(count_msg, embed=em)
        star_message = StarboardMessage(
            msg.id, channel.id, post_msg.id, star_channel.id, msg.author.id
        )
        if star_message not in self.starboards[ctx.guild.id][starboard.name].messages:
            self.starboards[ctx.guild.id][starboard.name].messages.append(star_message.to_json())
        await self._save_starboards(guild)

    @starboard.group()
    async def whitelist(self, ctx: commands.Context) -> None:
        """Add/Remove channels/roles from the whitelist"""
        pass

    @starboard.group()
    async def blacklist(self, ctx: commands.Context) -> None:
        """Add/Remove channels/roles from the blacklist"""
        pass

    @blacklist.command(name="add")
    async def blacklist_add(
        self,
        ctx: commands.Context,
        starboard: StarboardExists,
        channel_or_role: Union[discord.TextChannel, discord.Role],
    ) -> None:
        """
            Add a channel to the starboard blacklist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to add to the blacklist
        """
        guild = ctx.guild
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id in starboard.blacklist_channel:
                msg = _("{channel_or_role} is already blacklisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].blacklist_channel.append(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} blacklisted on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
        else:
            if channel_or_role.id in starboard.blacklist_role:
                msg = _("{channel_or_role} is already blacklisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].blacklist_role.append(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} blacklisted on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)

    @blacklist.command(name="remove")
    async def blacklist_remove(
        self,
        ctx: commands.Context,
        starboard: StarboardExists,
        channel_or_role: Union[discord.TextChannel, discord.Role],
    ) -> None:
        """
            Remove a channel to the starboard blacklist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to remove from the blacklist
        """
        guild = ctx.guild
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id not in starboard.blacklist_channel:
                msg = _("{channel_or_role} is not blacklisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].blacklist_channel.remove(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} removed from blacklist on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
        else:
            if channel_or_role.id not in starboard.blacklist_role:
                msg = _("{channel_or_role} is not blacklisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].blacklist_role.remove(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} removed from blacklist on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)

    @whitelist.command(name="add")
    async def whitelist_add(
        self,
        ctx: commands.Context,
        starboard: StarboardExists,
        channel_or_role: Union[discord.TextChannel, discord.Role],
    ) -> None:
        """
            Add a channel to the starboard whitelist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to add to the whitelist
        """
        guild = ctx.guild
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id in starboard.whitelist_channel:
                msg = _("{channel_or_role} is already whitelisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].whitelist_channel.append(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} whitelisted on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
        else:
            if channel_or_role.id in starboard.whitelist_role:
                msg = _("{channel_or_role} is already whitelisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].whitelist_role.append(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} whitelisted on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)

    @whitelist.command(name="remove")
    async def whitelist_remove(
        self,
        ctx: commands.Context,
        starboard: StarboardExists,
        channel_or_role: Union[discord.TextChannel, discord.Role],
    ) -> None:
        """
            Remove a channel to the starboard whitelist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to remove from the whitelist
        """
        guild = ctx.guild
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id not in starboard.whitelist_channel:
                msg = _("{channel_or_role} is not whitelisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].whitelist_channel.remove(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} removed from whitelist on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
        else:
            if channel_or_role.id not in starboard.whitelist_role:
                msg = _("{channel_or_role} is not whitelisted for starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)
                return
            else:
                self.starboards[ctx.guild.id][starboard.name].whitelist_role.remove(
                    channel_or_role.id
                )
                await self._save_starboards(guild)
                msg = _("{channel_or_role} removed from whitelist on starboard {name}").format(
                    channel_or_role=channel_or_role.name, name=starboard.name
                )
                await ctx.send(msg)

    @starboard.command(name="channel", aliases=["channels"])
    async def change_channel(
        self, ctx: commands.Context, starboard: StarboardExists, channel: discord.TextChannel
    ) -> None:
        """
            Change the channel that the starboard gets posted to

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to remove from the blacklist
        """
        guild = ctx.guild
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
    async def toggle_starboard(self, ctx: commands.Context, starboard: StarboardExists) -> None:
        """
            Toggle a starboard on/off

            `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        if starboard.enabled:
            msg = _("Starboard {name} disabled.").format(name=starboard.name)
        else:
            msg = _("Starboard {name} enabled.").format(name=starboard.name)
        self.starboards[ctx.guild.id][starboard.name].enabled = not starboard.enabled
        await self._save_starboards(guild)
        await ctx.send(msg)

    @starboard.command(name="selfstar")
    async def toggle_selfstar(self, ctx: commands.Context, starboard: StarboardExists) -> None:
        """
            Toggle whether or not a user can star their own post

            `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        if starboard.selfstar:
            msg = _("Selfstarring on starboard {name} disabled.").format(name=starboard.name)
        else:
            msg = _("Selfstarring on starboard {name} enabled.").format(name=starboard.name)
        self.starboards[ctx.guild.id][starboard.name].selfstar = not starboard.selfstar
        await self._save_starboards(guild)
        await ctx.send(msg)

    @starboard.command(name="colour", aliases=["color"])
    async def colour_starboard(
        self, ctx: commands.Context, starboard: StarboardExists, colour: Union[discord.Colour, str]
    ) -> None:
        """
            Change the default colour for a starboard

            `<name>` is the name of the starboard to toggle
            `<colour>` The colour to use for the starboard embed
            This can be a hexcode or integer for colour or `author/member/user` to use
            the original posters colour or `bot` to use the bots colour.
            Colour also accepts names from [discord.py](https://discordpy.readthedocs.io/en/latest/api.html#colour)
        """
        guild = ctx.guild
        if isinstance(colour, str):
            colour = colour.lower()
            if colour not in ["user", "member", "author", "bot"]:
                return await ctx.send(_("The provided colour option is not valid."))
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
        self, ctx: commands.Context, starboard: StarboardExists, emoji: Union[discord.Emoji, str]
    ) -> None:
        """
            Set the emoji for the starboard

            `<name>` is the name of the starboard to change the emoji for
            `<emoji>` must be an emoji on the server or a default emoji
        """
        guild = ctx.guild
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
        self, ctx: commands.Context, starboard: StarboardExists, threshold: int
    ) -> None:
        """
            Set the threshold before posting to the starboard

            `<name>` is the name of the starboard to change the threshold for
            `<threshold>` must be a number of reactions before a post gets
            moved to the starboard
        """
        guild = ctx.guild
        if threshold <= 0:
            threshold = 1
        self.starboards[ctx.guild.id][starboard.name].threshold = threshold
        await self._save_starboards(guild)
        msg = _("Threshold of {threshold} reactions set for {name}").format(
            threshold=threshold, name=starboard.name
        )
        await ctx.send(msg)
