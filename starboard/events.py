import discord
import logging

from typing import List, cast, Dict, Union, Literal

from redbot import version_info, VersionInfo
from redbot.core.bot import Red
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n

from .message_entry import StarboardMessage
from .starboard_entry import StarboardEntry

_ = Translator("Starboard", __file__)
log = logging.getLogger("red.trusty-cogs.Starboard")


@cog_i18n(_)
class StarboardEvents:
    bot: Red
    config: Config
    starboards: Dict[int, StarboardEntry]

    def __init__(self, bot):
        self.bot: Red
        self.config: Config
        self.starboards: Dict[int, StarboardEntry]

    async def _build_starboard_info(self, ctx: commands.Context, starboard: StarboardEntry):
        channel_perms = ctx.channel.permissions_for(ctx.guild.me)
        embed = discord.Embed(colour=await self._get_colour(ctx.channel))
        embed.title = _("Starboard settings for {guild}").format(guild=ctx.guild.name)
        text_msg = ""
        channel = ctx.guild.get_channel(starboard.channel)
        s_channel = channel.mention if channel else "deleted_channel"
        msg = _("Name: {name}\n").format(name=starboard.name)
        msg += _("Enabled: {enabled}\n").format(enabled=starboard.enabled)
        msg += _("Emoji: {emoji}\n").format(emoji=starboard.emoji)
        msg += _("Channel: {channel}\n").format(channel=s_channel)
        msg += _("Threshold: {threshold}\n").format(threshold=starboard.threshold)
        if starboard.blacklist_channel:
            channels = [ctx.guild.get_channel(c) for c in starboard.blacklist_channel]
            chans = ", ".join(c.mention for c in channels if c is not None)
            msg += _("Blacklisted Channels: {chans}\n").format(chans=chans)
        if starboard.whitelist_channel:
            channels = [ctx.guild.get_channel(c) for c in starboard.whitelist_channel]
            chans = ", ".join(c.mention for c in channels if c is not None)
            msg += _("Whitelisted Channels: {chans}\n").format(chans=chans)
        if starboard.blacklist_role:
            roles = [ctx.guild.get_role(c) for c in starboard.blacklist_role]
            if channel_perms.embed_links:
                chans = ", ".join(r.mention for r in roles if r is not None)
            else:
                chans = ", ".join(r.name for r in roles if r is not None)
            msg += _("Blacklisted roles: {chans}\n").format(chans=chans)
        if starboard.whitelist_role:
            roles = [ctx.guild.get_role(c) for c in starboard.whitelist_role]
            if channel_perms.embed_links:
                chans = ", ".join(r.mention for r in roles)
            else:
                chans = ", ".join(r.name for r in roles)
            msg += _("Whitelisted Roles: {chans}\n").format(chans=chans)
        embed.add_field(name=_("Starboard {name}").format(name=starboard.name), value=msg)
        text_msg += _("{msg} Starboard {name}\n").format(msg=msg, name=starboard.name)
        return (embed, text_msg)

    async def _check_roles(
        self, starboard: StarboardEntry, member: Union[discord.Member, discord.User]
    ) -> bool:
        """Checks if the user is allowed to add to the starboard
        Allows bot owner to always add messages for testing
        disallows users from adding their own messages"""
        if isinstance(member, discord.User):
            return True
        user_roles = set([role.id for role in member.roles])
        if starboard.whitelist_role:
            for role in starboard.whitelist_role:
                if role in user_roles:
                    return True
            return False
            # Since we'd normally return True
            # if there is a whitelist we want to ensure only whitelisted
            # roles can starboard something
        elif starboard.blacklist_role:
            for role in starboard.blacklist_role:
                if role in user_roles:
                    return False

        return True

    async def _check_channel(
        self, starboard: StarboardEntry, channel: discord.TextChannel
    ) -> bool:
        """CHecks if the channel is allowed to track starboard
        messages"""
        if starboard.whitelist_channel:
            return channel.id in starboard.whitelist_channel
        else:
            return channel.id not in starboard.blacklist_channel

    async def _get_colour(self, channel: discord.TextChannel) -> discord.Colour:
        try:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()
        except AttributeError:
            return await self.bot.get_embed_colour(channel)

    async def _build_embed(
        self, guild: discord.Guild, message: discord.Message, starboard: StarboardEntry
    ) -> discord.Embed:
        channel = cast(discord.TextChannel, message.channel)
        author = message.author
        if message.embeds:
            em = message.embeds[0]
            if message.system_content:
                if em.description != discord.Embed.Empty:
                    em.description = "{}\n\n{}".format(message.system_content, em.description)[
                        :2048
                    ]
                else:
                    em.description = message.system_content
                if not author.bot:
                    em.set_author(
                        name=author.display_name,
                        url=message.jump_url,
                        icon_url=str(author.avatar_url),
                    )
        else:
            em = discord.Embed(timestamp=message.created_at)
            if starboard.colour in ["user", "member", "author"]:
                em.color = author.colour
            elif starboard.colour == "bot":
                em.color = await self._get_colour(channel)
            else:
                em.color = discord.Colour(starboard.colour)
            em.description = message.system_content
            em.set_author(
                name=author.display_name, url=message.jump_url, icon_url=str(author.avatar_url)
            )
            if message.attachments != []:
                em.set_image(url=message.attachments[0].url)
        em.timestamp = message.created_at
        jump_link = _("\n\n[Click Here to view context]({link})").format(link=message.jump_url)
        if em.description:
            em.description = f"{em.description}{jump_link}"
        else:
            em.description = jump_link
        em.set_footer(text=f"{channel.guild.name} | {channel.name}")
        return em

    async def _save_starboards(self, guild: discord.Guild) -> None:
        await self.config.guild(guild).starboards.set(
            {n: s.to_json() for n, s in self.starboards[guild.id].items()}
        )

    async def _get_count(self, message_entry: StarboardMessage, starboard: StarboardEntry) -> int:
        orig_channel = self.bot.get_channel(message_entry.original_channel)
        new_channel = self.bot.get_channel(message_entry.new_channel)
        try:
            orig_msg = await orig_channel.fetch_message(message_entry.original_message)
        except discord.errors.Forbidden:
            return 0
        orig_reaction = [r for r in orig_msg.reactions if str(r.emoji) == str(starboard.emoji)]
        try:
            try:
                new_msg = await new_channel.fetch_message(message_entry.new_message)
            except discord.errors.Forbidden:
                return 0
            new_reaction = [r for r in new_msg.reactions if str(r.emoji) == str(starboard.emoji)]
            reactions = orig_reaction + new_reaction
        except discord.errors.NotFound:
            reactions = orig_reaction
        unique_users: List[int] = []
        for reaction in reactions:
            async for user in reaction.users():
                if not await self._check_roles(starboard, user):
                    continue
                if not starboard.selfstar and user.id == orig_msg.author.id:
                    continue
                if user.id not in unique_users and not user.bot:
                    unique_users.append(user.id)
        return len(unique_users)

    async def is_mod_or_admin(self, member: discord.Member) -> bool:
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._update_stars(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._update_stars(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionActionEvent) -> None:
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except AttributeError:
            # DMChannels don't have guilds
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        try:
            msg = await channel.fetch_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            return
        if guild.id not in self.starboards:
            return
        # starboards = await self.config.guild(guild).starboards()
        for name, starboard in self.starboards[guild.id].items():
            # starboard = StarboardEntry.from_json(s_board)
            star_channel = self.bot.get_channel(starboard.channel)
            if not star_channel:
                continue
            await self._loop_messages(payload, starboard, star_channel, msg)

    async def _update_stars(self, payload: discord.RawReactionActionEvent) -> None:
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except AttributeError:
            # DMChannels don't have guilds
            return
        if guild.id not in self.starboards:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        try:
            msg = await channel.fetch_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            return
        member = guild.get_member(payload.user_id)
        if member and member.bot:
            return
        starboard = None
        for name, s_board in self.starboards[guild.id].items():
            if s_board.emoji == str(payload.emoji):
                starboard = s_board
        if not starboard:
            return
        if not starboard.enabled:
            return
        if not await self._check_roles(starboard, member):
            return
        if not await self._check_channel(starboard, channel):
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

            star_message = StarboardMessage(msg.id, channel.id, None, None, msg.author.id)
            if count < starboard.threshold:
                if star_message.to_json() not in starboard.messages:
                    self.starboards[guild.id][starboard.name].messages.append(
                        star_message.to_json()
                    )
                await self._save_starboards(guild)
                return

            em = await self._build_embed(guild, msg, starboard)
            count_msg = "{} **#{}**".format(payload.emoji, count)
            post_msg = await star_channel.send(count_msg, embed=em)
            if starboard.autostar:
                try:
                    await post_msg.add_reaction(starboard.emoji)
                except Exception:
                    log.exception("Error adding autostar.")
            if star_message.to_json() not in starboard.messages:
                self.starboards[guild.id][starboard.name].messages.append(star_message.to_json())
            star_message = StarboardMessage(
                msg.id, channel.id, post_msg.id, star_channel.id, msg.author.id
            )
            self.starboards[guild.id][starboard.name].messages.append(star_message.to_json())
            await self._save_starboards(guild)

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        for guild_id, starboards in self.starboards.items():
            for starboard, entry in starboards.items():
                for message in entry.messages:
                    if message["author"] == user_id:
                        self.starboards[guild_id][starboard].messages.remove(message)
            await self.config.guild_from_id(guild_id).starboards.set(self.starboard[guild_id])

    async def _loop_messages(
        self,
        payload: discord.RawReactionActionEvent,
        starboard: StarboardEntry,
        star_channel: discord.TextChannel,
        message: discord.Message,
    ):
        try:
            guild = star_channel.guild
        except AttributeError:
            return
        for messages in (StarboardMessage.from_json(m) for m in starboard.messages):
            same_message = messages.original_message == message.id
            same_channel = messages.original_channel == payload.channel_id
            starboard_message = messages.new_message == message.id
            starboard_channel = messages.new_channel == payload.channel_id

            if not messages.new_message or not messages.new_channel:
                continue
            if (same_message and same_channel) or (starboard_message and starboard_channel):
                count = await self._get_count(messages, starboard)
                try:
                    message_edit = await star_channel.fetch_message(messages.new_message)  # type: ignore
                    # This is for backwards compatibility for older Red
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    # starboard message may have been deleted
                    return True
                if count < starboard.threshold:
                    star_message = StarboardMessage(
                        message.id, payload.channel_id, None, None, message.author.id
                    )
                    if messages.to_json() in starboard.messages:
                        starboard.messages.remove(messages.to_json())
                    starboard.messages.append(star_message.to_json())

                    await self._save_starboards(guild)

                    await message_edit.delete()
                    return True
                count_message = f"{starboard.emoji} **#{count}**"
                await message_edit.edit(content=count_message)
                return True
        return False
