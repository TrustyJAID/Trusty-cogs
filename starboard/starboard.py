from typing import Union

import discord

from .message_entry import StarboardMessage
from .starboard_entry import StarboardEntry
from .errors import StarboardError, NoStarboardError
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Starboard", __file__)
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class Starboard(commands.Cog):
    """
        Create a starboard to *pin* those special comments
    """
    __version__ = "2.1.2"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        default_guild = {"starboards": {}}

        self.config = Config.get_conf(self, 356488795)
        self.config.register_guild(**default_guild)
        self.message_list = []

    @commands.group()
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def starboard(self, ctx):
        """Commands for managing the starboard"""
        if ctx.invoked_subcommand is None:
            guild = ctx.guild
            if await self.config.guild(guild).starboards():
                embed = discord.Embed(colour=await self.get_colour(guild))
                embed.title = _("Starboard settings for ") + guild.name
                text_msg = ""
                s_boards = await self.config.guild(guild).starboards()
                channel_perms = ctx.channel.permissions_for(ctx.guild.me)
                for s in s_boards:
                    channel = guild.get_channel(s_boards[s]["channel"])
                    s_channel = channel.mention if channel else "deleted_channel"
                    msg = _("Name: ") + s_boards[s]["name"] + "\n"
                    msg += _("Enabled: ") + str(s_boards[s]["enabled"]) + "\n"
                    msg += _("Emoji: ") + str(s_boards[s]["emoji"]) + "\n"
                    msg += _("Channel: ") + s_channel + "\n"
                    msg += _("Threshold: ") + str(s_boards[s]["threshold"]) + "\n"
                    if s_boards[s]["blacklist_channel"]:
                        channels = [guild.get_channel(c) for c in s_boards[s]["blacklist_channel"]]
                        chans = ", ".join(c.mention for c in channels if c is not None)
                        msg += _("Blacklisted Channels: ") + chans + "\n"
                    if s_boards[s]["whitelist_channel"]:
                        channels = [guild.get_channel(c) for c in s_boards[s]["whitelist_channel"]]
                        chans = ", ".join(c.mention for c in channels if c is not None)
                        msg += _("Whitelisted Channels: ") + chans + "\n"
                    if s_boards[s]["blacklist_role"]:
                        roles = [guild.get_role(c) for c in s_boards[s]["blacklist_role"]]
                        if channel_perms.embed_links:
                            chans = ", ".join(r.mention for r in roles if r is not None)
                        else:
                            chans = ", ".join(r.name for r in roles if r is not None)
                        msg += _("Blacklisted roles: ") + chans + "\n"
                    if s_boards[s]["whitelist_role"]:
                        roles = [guild.get_role(c) for c in s_boards[s]["whitelist_role"]]
                        if channel_perms.embed_links:
                            chans = ", ".join(r.mention for r in roles)
                        else:
                            chans = ", ".join(r.name for r in roles)
                        msg += _("Whitelisted Roles: ") + chans + "\n"
                    embed.add_field(name=_("Starboard ") + s, value=msg)
                    text_msg += _("Starboard ") + s + "\n" + msg + "\n"
                if channel_perms.embed_links:
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(msg)

    @starboard.command(name="create", aliases=["add"])
    async def setup_starboard(
        self,
        ctx: commands.Context,
        name: str,
        channel: discord.TextChannel = None,
        emoji: Union[discord.Emoji, str] = "⭐",
    ):
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
        starboards = await self.config.guild(guild).starboards()
        if name in starboards:
            await ctx.send(name + _(" starboard name is already being used"))
            return
        starboard = StarboardEntry(name, channel.id, str(emoji))
        starboards[name] = starboard.to_json()
        await self.config.guild(guild).starboards.set(starboards)
        msg = _("Starboard set to ") + channel.mention + _(" with emoji ") + str(emoji)
        await ctx.send(msg)

    @starboard.command(name="cleanup")
    async def cleanup(self, ctx):
        """
            Cleanup stored deleted channels or roles in the blacklist/whitelist
        """
        guild = ctx.guild
        s_boards = await self.config.guild(guild).starboards()
        if not s_boards:
            await ctx.send(_("There are no Starboards setup on this server."))
            return
        if s_boards:
            roles = 0
            channels = 0
            boards = 0
            for s in await self.config.guild(guild).starboards():
                channel = guild.get_channel(s_boards[s]["channel"])
                if channel is None:
                    del s_boards[s]
                    boards += 1
                    continue
                if s_boards[s]["blacklist_channel"]:
                    for c in s_boards[s]["blacklist_channel"]:
                        channel = guild.get_channel(c)
                        if channel is None:
                            s_boards[s]["blacklist_channel"].remove(c)
                            channels += 1
                if s_boards[s]["whitelist_channel"]:
                    for c in s_boards[s]["whitelist_channel"]:
                        channel = guild.get_channel(c)
                        if channel is None:
                            s_boards[s]["whitelist_channel"].remove(c)
                            channels += 1
                if s_boards[s]["blacklist_role"]:
                    for r in s_boards[s]["blacklist_role"]:
                        role = guild.get_role(r)
                        if role is None:
                            s_boards[s]["blacklist_role"].remove(r)
                            roles += 1
                if s_boards[s]["whitelist_role"]:
                    for r in s_boards[s]["whitelist_role"]:
                        role = guild.get_role(r)
                        if role is None:
                            s_boards[s]["whitelist_role"].remove(r)
                            roles += 1
            await self.config.guild(guild).starboards.set(s_boards)
        msg = _(
            "Removed {channels} channels, {roles} roles and {boards} boards "
            "that no longer exist"
        ).format(channels=channels, roles=roles, boards=boards)
        await ctx.send(msg)

    @starboard.command(name="update", hidden=True)
    @checks.is_owner()
    async def update_starboard(self, ctx):
        """
            This is to update all previous starboards
            to the new starboard storage method keeping as many
            settings as possible
            This works for all guilds
        """
        data = await self.config.all_guilds()
        error_msg = ""
        for guild_id in data:
            try:
                guild = self.bot.get_guild(guild_id)
                await self.config.guild(guild).clear()
                emoji = data[guild_id]["emoji"]
                channel = data[guild_id]["channel"]
                enabled = data[guild_id]["enabled"]
                threshold = data[guild_id]["threshold"]
                channel_blacklist = data[guild_id]["ignore"]
                starboard = StarboardEntry(
                    "starboard",
                    channel,
                    emoji,
                    enabled,
                    [],
                    [],
                    [],
                    channel_blacklist,
                    [],
                    threshold,
                )
                new_data = {"starboards": {"starboard": starboard.to_json()}}
                await self.config.guild(guild).set(new_data)
            except Exception as e:
                error_msg += (
                    _("Server ") + str(guild_id) + _(" had an error converting ") + str(e) + "\n"
                )
                pass
        if error_msg:
            errors = _("The following servers had errors\n") + error_msg
            await ctx.send(errors)
        await ctx.send(_("Starboards should all be updated."))

    @starboard.command(name="remove", aliases=["delete", "del"])
    async def remove_starboard(self, ctx: commands.Context, name: str):
        """
            Remove a starboard from the server

            `<name>` is the name for the starboard and will be lowercase only
        """
        guild = ctx.message.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(name + _(" Doesn't appear to be a starboard on this server."))
            return
        starboards = await self.config.guild(guild).starboards()
        del starboards[starboard.name]
        await self.config.guild(guild).starboards.set(starboards)
        await ctx.send(_("Deleted starboard ") + name)

    @commands.command()
    @commands.guild_only()
    async def star(self, ctx, name: str, msg_id: int, channel: discord.TextChannel = None):
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
                msg = await channel.get_message(msg_id)
            except AttributeError:
                msg = await ctx.channel.fetch_message(msg_id)
        except discord.errors.NotFound:
            error_msg = _("That message doesn't appear to exist in the specified channel.")
            return await ctx.send(error_msg)
        except discord.errors.Forbidden:
            error_msg = _("I do not have permission to read this channels history.")
            return await ctx.send(error_msg)
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            return
        if not starboard.enabled:
            error_msg = _("Starboard {name} isn't enabled.").format(name=starboard.name)
            await ctx.send(error_msg)
            return
        if not await self.check_roles(starboard, ctx.message.author):
            error_msg = _(
                "One of your roles is blacklisted or you don't have the whitelisted role."
            )
            await ctx.send(error_msg)
            return
        if not await self.check_channel(starboard, channel):
            error_msg = _(
                "This channel is either blacklisted or not in the whitelisted channels."
            )
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

        em = await self.build_embed(guild, msg, starboard)
        count_msg = f"{starboard.emoji} **#{count}**"
        post_msg = await star_channel.send(count_msg, embed=em)
        star_message = StarboardMessage(
            msg.id, channel.id, post_msg.id, star_channel.id, msg.author.id
        )
        await self.save_starboard_messages(guild, star_message, starboard)

    @starboard.group()
    async def whitelist(self, ctx):
        """Add/Remove channels/roles from the whitelist"""
        pass

    @starboard.group()
    async def blacklist(self, ctx):
        """Add/Remove channels/roles from the blacklist"""
        pass

    @blacklist.command(name="add")
    async def blacklist_add(
        self, ctx, name: str, channel_or_role: Union[discord.TextChannel, discord.Role]
    ):
        """
            Add a channel to the starboard blacklist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to add to the blacklist
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id in starboard.blacklist_channel:
                msg = channel_or_role.name + _(" is already blacklisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.blacklist_channel.append(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" blacklisted on starboard ") + name
                await ctx.send(msg)
        else:
            if channel_or_role.id in starboard.blacklist_role:
                msg = channel_or_role.name + _(" is already blacklisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.blacklist_role.append(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" blacklisted on starboard ") + name
                await ctx.send(msg)

    @blacklist.command(name="remove")
    async def blacklist_remove(
        self, ctx, name: str, channel_or_role: Union[discord.TextChannel, discord.Role]
    ):
        """
            Remove a channel to the starboard blacklist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to remove from the blacklist
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id not in starboard.blacklist_channel:
                msg = channel_or_role.name + _(" is not blacklisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.blacklist_channel.remove(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" removed from blacklist on starboard ") + name
                await ctx.send(msg)
        else:
            if channel_or_role.id not in starboard.blacklist_role:
                msg = channel_or_role.name + _(" is not blacklisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.blacklist_role.remove(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" removed from blacklist on starboard ") + name
                await ctx.send(msg)

    @whitelist.command(name="add")
    async def whitelist_add(
        self, ctx, name: str, channel_or_role: Union[discord.TextChannel, discord.Role]
    ):
        """
            Add a channel to the starboard whitelist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to add to the whitelist
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id in starboard.whitelist_channel:
                msg = channel_or_role.name + _(" is already whitelisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.whitelist_channel.append(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" whitelisted on starboard ") + name
                await ctx.send(msg)
        else:
            if channel_or_role.id in starboard.whitelist_role:
                msg = channel_or_role.name + _(" is already whitelisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.whitelist_role.append(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" whitelisted on starboard ") + name
                await ctx.send(msg)

    @whitelist.command(name="remove")
    async def whitelist_remove(
        self, ctx, name: str, channel_or_role: Union[discord.TextChannel, discord.Role]
    ):
        """
            Remove a channel to the starboard whitelist

            `<name>` is the name of the starboard to adjust
            `<channel_or_role>` is the channel or role you would like to remove from the whitelist
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if type(channel_or_role) is discord.TextChannel:
            if channel_or_role.id not in starboard.whitelist_channel:
                msg = channel_or_role.name + _(" is not whitelisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.whitelist_channel.remove(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" removed from whitelist on starboard ") + name
                await ctx.send(msg)
        else:
            if channel_or_role.id not in starboard.whitelist_role:
                msg = channel_or_role.name + _(" is not whitelisted for starboard ") + name
                await ctx.send(msg)
                return
            else:
                starboard.whitelist_role.remove(channel_or_role.id)
                await self.save_starboard(guild, starboard)
                msg = channel_or_role.name + _(" removed from whitelist on starboard ") + name
                await ctx.send(msg)

    @starboard.command(name="channel", aliases=["channels"])
    async def change_channel(self, ctx, name: str, channel: discord.TextChannel):
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
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if channel.id == starboard.channel:
            msg = _("Starboard ") + name + _(" is already posting in ") + channel.mention
            await ctx.send(msg)
            return
        starboard.channel = channel.id
        await self.save_starboard(guild, starboard)
        msg = _("Starboard ") + name + _(" set to post in ") + channel.mention
        await ctx.send(msg)

    @starboard.command(name="toggle")
    async def toggle_starboard(self, ctx, name: str):
        """
            Toggle a starboard on/off

            `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if starboard.enabled:
            msg = _("Starboard ") + name + _(" disabled.")
        else:
            msg = _("Starboard ") + name + _(" enabled.")
        starboard.enabled = not starboard.enabled
        await self.save_starboard(guild, starboard)
        await ctx.send(msg)

    @starboard.command(name="selfstar")
    async def toggle_selfstar(self, ctx, name: str):
        """
            Toggle whether or not a user can star their own post

            `<name>` is the name of the starboard to toggle
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if starboard.selfstar:
            msg = _("Selfstarring on starboard {name} disabled.").format(name=starboard.name)
        else:
            msg = _("Selfstarring on starboard {name} enabled.").format(name=starboard.name)
        starboard.selfstar = not starboard.selfstar
        await self.save_starboard(guild, starboard)
        await ctx.send(msg)

    @starboard.command(name="colour", aliases=["color"])
    async def colour_starboard(self, ctx, name: str, colour: Union[discord.Colour, str]):
        """
            Change the default colour for a starboard

            `<name>` is the name of the starboard to toggle
            `<colour>` The colour to use for the starboard embed
            This can be a hexcode or integer for colour or `author/member/user` to use
            the original posters colour or `bot` to use the bots colour.
            Colour also accepts names from [discord.py](https://discordpy.readthedocs.io/en/rewrite/api.html#discord.Colour)
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if isinstance(colour, str):
            colour = colour.lower()
            if colour not in ["user", "member", "author", "bot"]:
                return await ctx.send(_("The provided colour option is not valid."))
            else:
                starboard.colour = colour
        else:
            starboard.colour = colour.value
        await self.save_starboard(guild, starboard)
        msg = _("Starboard `{name}` colour set to `{colour}`.").format(
            name=starboard.name,
            colour=starboard.colour
        )
        await ctx.send(msg)

    @starboard.command(name="emoji")
    async def set_emoji(self, ctx, name: str, emoji: Union[discord.Emoji, str]):
        """
            Set the emoji for the starboard

            `<name>` is the name of the starboard to change the emoji for
            `<emoji>` must be an emoji on the server or a default emoji
        """
        guild = ctx.guild
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        if type(emoji) == discord.Emoji:
            if emoji not in guild.emojis:
                await ctx.send(_("That emoji is not on this guild!"))
                return
        starboard.emoji = str(emoji)
        await self.save_starboard(guild, starboard)
        msg = str(emoji) + _(" set for starboard ") + name
        await ctx.send(msg)

    @starboard.command(name="threshold")
    async def set_threshold(self, ctx, name: str, threshold: int):
        """
            Set the threshold before posting to the starboard

            `<name>` is the name of the starboard to change the threshold for
            `<threshold>` must be a number of reactions before a post gets
            moved to the starboard
        """
        guild = ctx.guild
        if threshold <= 0:
            threshold = 1
        try:
            starboard = await self.get_starboard_from_name(guild, name)
        except NoStarboardError:
            await ctx.send(_("There is no starboard named ") + name)
            return
        starboard.threshold = threshold
        await self.save_starboard(guild, starboard)
        msg = _("Threshold of ") + str(threshold) + _(" reactions set for ") + name
        await ctx.send(msg)

    async def check_roles(self, starboard, member):
        """Checks if the user is allowed to add to the starboard
           Allows bot owner to always add messages for testing
           disallows users from adding their own messages"""
        user_roles = set([role.id for role in member.roles])
        if starboard.whitelist_role:
            for role in starboard.whitelist_role:
                if role in user_roles:
                    return True
        elif starboard.blacklist_role:
            for role in starboard.blacklist_role:
                if role in user_roles:
                    return False
        else:
            return True

    async def check_channel(self, starboard, channel):
        """CHecks if the channel is allowed to track starboard
        messages"""
        if starboard.whitelist_channel:
            return channel.id in starboard.whitelist_channel
        else:
            return channel.id not in starboard.blacklist_channel

    async def get_starboard_from_name(self, guild: discord.Guild, name: str):
        starboards = await self.config.guild(guild).starboards()
        try:
            starboard = StarboardEntry.from_json(starboards.get(name.lower()))
        except Exception as e:
            print(e)
            raise NoStarboardError
        else:
            return starboard

    async def get_colour(self, guild):
        if await self.bot.db.guild(guild).use_bot_color():
            return guild.me.colour
        else:
            return await self.bot.db.color()

    async def get_starboard_from_emoji(self, guild: discord.Guild, emoji: str):
        starboards = await self.config.guild(guild).starboards()
        for name, s_board in starboards.items():
            if s_board["emoji"] == str(emoji):
                return StarboardEntry.from_json(s_board)
        raise NoStarboardError

    async def save_starboard(self, guild, starboard):
        async with self.config.guild(guild).starboards() as boards:
            boards[starboard.name] = starboard.to_json()

    async def build_embed(self, guild, msg, starboard):
        channel = msg.channel
        author = msg.author
        if msg.embeds != []:
            em = msg.embeds[0]
            if msg.content != "":
                if em.description != discord.Embed.Empty:
                    em.description = "{}\n\n{}".format(msg.content, em.description)[:2048]
                else:
                    em.description = msg.content
                if not author.bot:
                    em.set_author(
                        name=author.display_name, url=msg.jump_url, icon_url=author.avatar_url
                    )
        else:
            em = discord.Embed(timestamp=msg.created_at)
            if starboard.colour in ["user", "member", "author"]:
                em.color = author.colour
            elif starboard.colour == "bot":
                em.color = await self.get_colour(guild)
            else:
                em.color = discord.Colour(starboard.colour)
            em.description = msg.content
            em.set_author(name=author.display_name, url=msg.jump_url, icon_url=author.avatar_url)
            if msg.attachments != []:
                em.set_image(url=msg.attachments[0].url)
        em.timestamp = msg.created_at
        if em.description:
            em.description = em.description + f"\n\n[Click Here to view context]({msg.jump_url})"
        else:
            em.description = f"\n\n[Click Here to view context]({msg.jump_url})"
        em.set_footer(text="{} | {}".format(channel.guild.name, channel.name))
        return em

    async def save_starboard_messages(self, guild, star_message, starboard):
        starboards = await self.config.guild(guild).starboards()
        if star_message.to_json() in starboard.messages:
            return
        else:
            for m in starboard.messages:
                msgs = StarboardMessage.from_json(m)
                same_msg = msgs.original_message == star_message.original_message
                same_channel = msgs.original_channel == star_message.original_channel
                if same_msg and same_channel:
                    starboard.messages.remove(m)
        del starboards[starboard.name]
        starboard.messages.append(star_message.to_json())
        starboards[starboard.name] = starboard.to_json()
        await self.config.guild(guild).starboards.set(starboards)

    async def get_count(self, message_entry, emoji):
        orig_channel = self.bot.get_channel(message_entry.original_channel)
        new_channel = self.bot.get_channel(message_entry.new_channel)
        try:
            orig_msg = await orig_channel.get_message(message_entry.original_message)
        except AttributeError:
            orig_msg = await orig_channel.fetch_message(message_entry.original_message)
        orig_reaction = [r for r in orig_msg.reactions if str(r.emoji) == str(emoji)]
        try:
            try:
                new_msg = await new_channel.get_message(message_entry.new_message)
            except AttributeError:
                new_msg = await new_channel.fetch_message(message_entry.new_message)
            new_reaction = [r for r in new_msg.reactions if str(r.emoji) == str(emoji)]
            reactions = orig_reaction + new_reaction
        except discord.errors.NotFound:
            reactions = orig_reaction
        unique_users = []
        for reaction in reactions:
            async for user in reaction.users():
                if user.id not in unique_users:
                    unique_users.append(user.id)
        return len(unique_users)

    async def is_mod_or_admin(self, member: discord.Member):
        guild = member.guild
        if member == guild.owner:
            return True
        if await self.bot.is_owner(member):
            return True
        if await self.bot.is_admin(member):
            return True
        if await self.bot.is_mod(member):
            return True
        return False

    @listener()
    async def on_raw_reaction_add(self, payload):
        await self._update_stars(payload)

    @listener()
    async def on_raw_reaction_remove(self, payload):
        await self._update_stars(payload)

    @listener()
    async def on_raw_reaction_clear(self, payload):
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except AttributeError:
            # DMChannels don't have guilds
            return
        try:
            try:
                msg = await channel.fetch_message(id=payload.message_id)
            except AttributeError:
                msg = await channel.get_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            return
        starboards = await self.config.guild(guild).starboards()
        for name, s_board in starboards.items():
            starboard = StarboardEntry.from_json(s_board)
            star_channel = self.bot.get_channel(starboard.channel)
            await self._loop_messages(payload, starboard, star_channel, msg)

    async def _update_stars(self, payload):
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except AttributeError:
            # DMChannels don't have guilds
            return
        try:
            try:
                msg = await channel.fetch_message(id=payload.message_id)
            except AttributeError:
                msg = await channel.get_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            return
        member = guild.get_member(payload.user_id)
        if not await self.config.guild(guild).starboards() or member.bot:
            return
        try:
            starboard = await self.get_starboard_from_emoji(guild, str(payload.emoji))
        except NoStarboardError:
            return
        if not starboard.enabled:
            return
        if not await self.check_roles(starboard, member):
            return
        if not await self.check_channel(starboard, channel):
            return

        if starboard.emoji == str(payload.emoji):
            star_channel = self.bot.get_channel(starboard.channel)
            if member.id == msg.author.id and not starboard.selfstar:
                # allow mods, admins and owner to automatically star messages
                return
            if await self._loop_messages(payload, starboard, star_channel, msg):
                return
            try:
                reaction = [r for r in msg.reactions if str(r.emoji) == str(payload.emoji)][0]
                count = reaction.count
            except IndexError:
                count = 0
            self.message_list.append((guild.id, payload.message_id))
            if count < starboard.threshold:
                star_message = StarboardMessage(msg.id, channel.id, None, None, msg.author.id)

                await self.save_starboard_messages(guild, star_message, starboard)
                self.message_list.remove((guild.id, payload.message_id))
                return

            em = await self.build_embed(guild, msg, starboard)
            count_msg = "{} **#{}**".format(payload.emoji, count)
            post_msg = await star_channel.send(count_msg, embed=em)
            star_message = StarboardMessage(
                msg.id, channel.id, post_msg.id, star_channel.id, msg.author.id
            )
            await self.save_starboard_messages(guild, star_message, starboard)
            self.message_list.remove((guild.id, payload.message_id))

    async def _loop_messages(self, payload, starboard, star_channel, msg):
        guild = star_channel.guild
        for messages in (StarboardMessage.from_json(m) for m in starboard.messages):
            same_msg = messages.original_message == msg.id
            same_channel = messages.original_channel == payload.channel_id
            starboard_msg = messages.new_message == msg.id
            starboard_channel = messages.new_channel == payload.channel_id

            if not messages.new_message or not messages.new_channel:
                continue
            if (guild.id, msg.id) in self.message_list:
                # This is to help prevent double posting starboard messages
                return True
            if (same_msg and same_channel) or (starboard_msg and starboard_channel):
                count = await self.get_count(messages, starboard.emoji)
                try:
                    msg_edit = await star_channel.get_message(messages.new_message)
                except AttributeError:
                    msg_edit = await star_channel.fetch_message(messages.new_message)
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    # starboard message may have been deleted
                    return True
                if count < starboard.threshold:
                    self.message_list.append((guild.id, payload.message_id))
                    star_message = StarboardMessage(
                        msg.id, payload.channel_id, None, None, msg.author.id
                    )

                    await self.save_starboard_messages(guild, star_message, starboard)
                    self.message_list.remove((guild.id, payload.message_id))
                    await msg_edit.delete()
                    return True
                count_msg = f"{starboard.emoji} **#{count}**"
                await msg_edit.edit(content=count_msg)
                return True
        return False
