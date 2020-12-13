import logging
import asyncio
from typing import Dict, Literal, Union, cast, Optional
from datetime import datetime, timedelta

import discord
from discord.utils import snowflake_time
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter

from .starboard_entry import StarboardEntry, StarboardMessage, FakePayload

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
        self.starboards: Dict[int, Dict[str, StarboardEntry]]

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
            msg += _("Blocked Channels: {chans}\n").format(chans=chans)
        if starboard.whitelist_channel:
            channels = [ctx.guild.get_channel(c) for c in starboard.whitelist_channel]
            chans = ", ".join(c.mention for c in channels if c is not None)
            msg += _("Allowed Channels: {chans}\n").format(chans=chans)
        if starboard.blacklist_role:
            roles = [ctx.guild.get_role(c) for c in starboard.blacklist_role]
            if channel_perms.embed_links:
                chans = ", ".join(r.mention for r in roles if r is not None)
            else:
                chans = ", ".join(r.name for r in roles if r is not None)
            msg += _("Blocked roles: {chans}\n").format(chans=chans)
        if starboard.whitelist_role:
            roles = [ctx.guild.get_role(c) for c in starboard.whitelist_role]
            if channel_perms.embed_links:
                chans = ", ".join(r.mention for r in roles)
            else:
                chans = ", ".join(r.name for r in roles)
            msg += _("Allowed Roles: {chans}\n").format(chans=chans)
        embed.add_field(name=_("Starboard {name}").format(name=starboard.name), value=msg)
        text_msg += _("{msg} Starboard {name}\n").format(msg=msg, name=starboard.name)
        return (embed, text_msg)

    async def _check_roles(
        self, starboard: StarboardEntry, member: Union[discord.Member, discord.User]
    ) -> bool:
        """Checks if the user is allowed to add to the starboard
        Allows bot owner to always add messages for testing
        disallows users from adding their own messages"""
        if not isinstance(member, discord.Member):
            # this will account for non-members reactions and still count
            # for the starboard count
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
        if channel.is_nsfw() and not self.bot.get_channel(starboard.channel).is_nsfw():
            return False
        if starboard.whitelist_channel:
            if channel.id in starboard.whitelist_channel:
                return True
            if channel.category_id and channel.category_id in starboard.whitelist_channel:
                return True
            return False
        else:
            if channel.id in starboard.blacklist_channel:
                return False
            if channel.category_id and channel.category_id in starboard.blacklist_channel:
                return False
            return True

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

    async def _get_count(
        self, message_entry: StarboardMessage, starboard: StarboardEntry, remove: Optional[int]
    ) -> StarboardMessage:
        """This will update the unique user list for the starboard message object"""
        orig_channel = self.bot.get_channel(message_entry.original_channel)
        new_channel = self.bot.get_channel(message_entry.new_channel)
        orig_reaction = []
        if orig_channel:
            try:
                orig_msg = await orig_channel.fetch_message(message_entry.original_message)
                orig_reaction = [
                    r for r in orig_msg.reactions if str(r.emoji) == str(starboard.emoji)
                ]
            except discord.errors.Forbidden:
                pass
        new_reaction = []
        if new_channel:
            try:
                new_msg = await new_channel.fetch_message(message_entry.new_message)
                new_reaction = [
                    r for r in new_msg.reactions if str(r.emoji) == str(starboard.emoji)
                ]
            except discord.errors.Forbidden:
                pass

        reactions = orig_reaction + new_reaction
        for reaction in reactions:
            log.debug(reactions)
            async for user in reaction.users():
                if not await self._check_roles(starboard, user):
                    continue
                if not starboard.selfstar and user.id == orig_msg.author.id:
                    continue
                if user.id not in message_entry.reactions and not user.bot:
                    log.debug("Adding user")
                    message_entry.reactions.append(user.id)
        if remove and remove in message_entry.reactions:
            log.debug("Removing user")
            message_entry.reactions.remove(remove)
        message_entry.reactions = list(set(message_entry.reactions))
        log.debug(message_entry.reactions)
        return message_entry

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
        await self._update_stars(payload, remove=payload.user_id)

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
            async with starboard.lock:
                await self._loop_messages(payload, starboard, star_channel, msg, None)

    async def _update_stars(
        self,
        payload: Union[discord.RawReactionActionEvent, FakePayload],
        remove: Optional[int] = None,
    ) -> None:
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

        star_channel = guild.get_channel(starboard.channel)
        if not star_channel:
            return
        try:
            msg = await channel.fetch_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            return
        if member.id == msg.author.id and not starboard.selfstar:
            return
        async with starboard.lock:
            if await self._loop_messages(payload, starboard, star_channel, msg, remove):
                return

            star_message = StarboardMessage(
                original_message=msg.id,
                original_channel=channel.id,
                new_message=None,
                new_channel=None,
                author=msg.author.id,
                reactions=[payload.user_id],
            )
            await self._get_count(star_message, starboard, remove)
            count = len(star_message.reactions)
            if count < starboard.threshold:
                if star_message not in starboard.messages:
                    self.starboards[guild.id][starboard.name].messages.append(star_message)
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
            if star_message not in starboard.messages:
                self.starboards[guild.id][starboard.name].messages.append(star_message)
            star_message.new_message = post_msg.id
            star_message.new_channel = star_channel.id
            self.starboards[guild.id][starboard.name].messages.append(star_message)
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
                    if message.author == user_id:
                        self.starboards[guild_id][starboard].messages.remove(message)
            await self.config.guild_from_id(guild_id).starboards.set(
                {n: s.to_json() for n, s in self.starboards[guild_id].items()}
            )

    async def cleanup_old_messages(self) -> None:
        """This will periodically iterate through old messages
        and prune them based on age to help keep data relatively easy to work
        through
        """
        purge_time = await self.config.purge_time()

        if not purge_time:
            return
        purge = timedelta(seconds=purge_time)
        while True:
            total_pruned = 0
            guilds_ignored = 0
            to_purge = datetime.utcnow() - purge
            # Prune only the last 30 days worth of data
            for guild_id, starboards in self.starboards.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    guilds_ignored += 1
                    continue
                # log.debug(f"Cleaning starboard data for {guild.name} ({guild.id})")
                for name, starboard in starboards.items():
                    async with starboard.lock:
                        to_rem = []
                        try:
                            async for message in AsyncIter(starboard.messages, steps=500):
                                if message.new_message:
                                    if snowflake_time(message.new_message) < to_purge:
                                        to_rem.append(message)
                                else:
                                    if snowflake_time(message.original_message) < to_purge:
                                        to_rem.append(message)
                            for m in to_rem:
                                log.debug(f"Removing {m}")
                                starboard.messages.remove(m)
                                total_pruned += 1
                            if len(to_rem) > 0:
                                log.info(
                                    f"Starboard pruned {len(to_rem)} messages that are "
                                    f"30 days old from {guild.name} ({guild.id})"
                                )
                        except Exception:
                            log.exception("Error trying to clenaup old starboard messages.")
                await self._save_starboards(guild)
            if total_pruned:
                log.info(
                    f"Starboard has pruned {total_pruned} messages and ignored {guilds_ignored} guilds."
                )
            # Sleep 1 day but also run on cog reload
            await asyncio.sleep(60 * 60 * 24)

    async def _loop_messages(
        self,
        payload: Union[discord.RawReactionActionEvent, FakePayload],
        starboard: StarboardEntry,
        star_channel: discord.TextChannel,
        message: discord.Message,
        remove: Optional[int],
    ) -> bool:
        try:
            guild = star_channel.guild
        except AttributeError:
            return True
        async for messages in AsyncIter(starboard.messages, steps=500):
            same_message = messages.original_message == message.id
            same_channel = messages.original_channel == payload.channel_id
            starboard_message = messages.new_message == message.id
            starboard_channel = messages.new_channel == payload.channel_id

            if not messages.new_message or not messages.new_channel:
                continue
            if (same_message and same_channel) or (starboard_message and starboard_channel):
                await self._get_count(messages, starboard, remove)
                if remove is None:
                    if getattr(payload, "user_id", 0) not in messages.reactions:
                        log.debug("Adding user in _loop_messages")
                        messages.reactions.append(payload.user_id)
                count = len(messages.reactions)
                log.debug(messages.reactions)
                try:
                    message_edit = await star_channel.fetch_message(messages.new_message)
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    # starboard message may have been deleted
                    return True
                if count < starboard.threshold:
                    messages.new_message = None
                    messages.new_channel = None
                    await self._save_starboards(guild)
                    await message_edit.delete()
                    return True
                log.debug("Editing starboard")
                count_message = f"{starboard.emoji} **#{count}**"
                await message_edit.edit(content=count_message)
                return True
        return False
