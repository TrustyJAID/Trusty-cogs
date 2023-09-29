import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Union, cast

import discord
from discord.utils import snowflake_time
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_timedelta

from .starboard_entry import FakePayload, StarboardEntry, StarboardMessage

_ = Translator("Starboard", __file__)
log = getLogger("red.trusty-cogs.Starboard")


@cog_i18n(_)
class StarboardEvents:
    bot: Red
    config: Config
    starboards: Dict[int, Dict[str, StarboardEntry]]
    ready: asyncio.Event

    async def _build_embed(
        self, guild: discord.Guild, message: discord.Message, starboard: StarboardEntry
    ) -> List[discord.Embed]:
        channel = cast(discord.TextChannel, message.channel)
        author = message.author
        embeds = []
        if message.embeds:
            embeds = message.embeds
            for em in embeds:
                if em.type in ["image", "gifv"]:
                    if em.thumbnail:
                        em.set_image(url=em.thumbnail.url)
                        em.set_thumbnail(url=None)

                if em.description is not None:
                    em.description = "{}\n\n{}".format(message.system_content, em.description)[
                        :4096
                    ]
                else:
                    em.description = message.system_content
                # if not author.bot:
                em.set_author(
                    name=author.display_name,
                    url=message.jump_url,
                    icon_url=author.display_avatar,
                )
                if starboard.colour in ["user", "member", "author"]:
                    em.color = author.colour
                elif starboard.colour == "bot":
                    em.color = await self.bot.get_embed_colour(channel)
                else:
                    em.color = discord.Colour(starboard.colour)
                if msg_ref := getattr(message, "reference", None):
                    ref_msg = getattr(msg_ref, "resolved", None)
                    if ref_msg is not None:
                        try:
                            ref_text = ref_msg.system_content
                            ref_link = f"\n\n{ref_msg.jump_url}"
                            if len(ref_text + ref_link) > 1024:
                                ref_text = (
                                    ref_text[: len(ref_link) - 1] + "\N{HORIZONTAL ELLIPSIS}"
                                )
                            ref_text += ref_link
                            em.add_field(
                                name=_("Replying to {author}").format(
                                    author=ref_msg.author.display_name
                                ),
                                value=ref_text,
                            )
                        except Exception:
                            pass
                em.timestamp = message.created_at
                jump_link = f"\n\n{message.jump_url}"
                if em.description:
                    with_context = f"{em.description}{jump_link}"
                    if len(with_context) > 4096:
                        em.add_field(name=_("Context"), value=jump_link)
                    else:
                        em.description = with_context
                else:
                    em.description = jump_link
                em.set_footer(text=f"{channel.guild.name} | {channel.name}")
        else:
            em = discord.Embed(timestamp=message.created_at, url=message.jump_url)
            if starboard.colour in ["user", "member", "author"]:
                em.color = author.colour
            elif starboard.colour == "bot":
                em.color = await self.bot.get_embed_colour(channel)
            else:
                em.color = discord.Colour(starboard.colour)
            em.description = message.system_content
            em.set_author(
                name=author.display_name, url=message.jump_url, icon_url=author.display_avatar
            )
            if msg_ref := getattr(message, "reference", None):
                ref_msg = getattr(msg_ref, "resolved", None)
                if ref_msg is not None:
                    try:
                        ref_text = ref_msg.system_content
                        ref_link = f"\n\n{ref_msg.jump_url}"
                        if len(ref_text + ref_link) > 1024:
                            ref_text = ref_text[: len(ref_link) - 1] + "\N{HORIZONTAL ELLIPSIS}"
                        ref_text += ref_link
                        em.add_field(
                            name=_("Replying to {author}").format(
                                author=ref_msg.author.display_name
                            ),
                            value=ref_text,
                        )
                    except Exception:
                        pass
            em.timestamp = message.created_at
            jump_link = f"\n\n{message.jump_url}"
            if em.description:
                with_context = f"{em.description}{jump_link}"
                if len(with_context) > 2048:
                    em.add_field(name=_("Context"), value=jump_link)
                else:
                    em.description = with_context
            else:
                em.description = jump_link
            em.set_footer(text=f"{channel.guild.name} | {channel.name}")
            if message.attachments:
                for attachment in message.attachments:
                    new_em = em.copy()
                    spoiler = attachment.is_spoiler()
                    if spoiler:
                        new_em.add_field(
                            name="Attachment",
                            value=f"||[{attachment.filename}]({attachment.url})||",
                        )
                    elif not attachment.filename.lower().endswith(
                        ("png", "jpeg", "jpg", "gif", "webp")
                    ):
                        new_em.add_field(
                            name="Attachment", value=f"[{attachment.filename}]({attachment.url})"
                        )
                    else:
                        new_em.set_image(url=attachment.url)
                    embeds.append(new_em)
            else:
                embeds.append(em)
        return embeds

    async def _save_starboards(self, guild: discord.Guild) -> None:
        async with self.config.guild(guild).starboards() as starboards:
            for name, starboard in self.starboards[guild.id].items():
                starboards[name] = await starboard.to_json()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self.ready.wait()
        await self._update_stars(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self.ready.wait()
        await self._update_stars(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionActionEvent) -> None:
        await self.ready.wait()
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.id not in self.starboards:
            return
        # starboards = await self.config.guild(guild).starboards()
        for starboard in self.starboards[guild.id].values():
            # starboard = StarboardEntry.from_json(s_board)
            star_channel = guild.get_channel_or_thread(starboard.channel)
            if not star_channel:
                continue
            async with starboard.lock:
                await self._loop_messages(payload, starboard, star_channel)

    async def is_bot_or_server_owner(self, member: discord.Member) -> bool:
        guild = member.guild
        if not guild:
            return False
        if guild.owner_id == member.id:
            return True
        return await self.bot.is_owner(member)

    async def _update_stars(
        self, payload: Union[discord.RawReactionActionEvent, FakePayload]
    ) -> None:
        """
        This handles updating the starboard with a new message
        based on the reactions added.
        This covers all reaction event types
        """
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if guild.me.is_timed_out():
            return
        channel = guild.get_channel_or_thread(payload.channel_id)

        if guild.id not in self.starboards:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        member = guild.get_member(payload.user_id)
        if member and member.bot:
            return
        starboard = None
        msg = guild._state._get_message(payload.message_id)
        # I know I am not supposed to use these private methods but I want to avoid
        # lookups if I can while ensuring historical lookups
        for starboard in self.starboards[guild.id].values():
            if starboard.emoji == payload.emoji:
                if not starboard.enabled:
                    continue
                allowed_roles = starboard.check_roles(member)
                allowed_channel = starboard.check_channel(self.bot, channel)
                if any((not allowed_roles, not allowed_channel)):
                    log.debug("User or channel not in allowlist")
                    continue

                star_channel = guild.get_channel(starboard.channel)
                if star_channel is None:
                    continue
                if (
                    not star_channel.permissions_for(guild.me).send_messages
                    or not star_channel.permissions_for(guild.me).embed_links
                ):
                    continue

                async with starboard.lock:
                    star_message = await self._loop_messages(payload, starboard, star_channel)
                    if star_message is True:
                        continue
                    if msg is None:
                        try:
                            msg = await channel.fetch_message(payload.message_id)
                        except (discord.errors.NotFound, discord.Forbidden):
                            continue
                    if star_message is False:
                        if getattr(payload, "event_type", None) == "REACTION_REMOVE":
                            # Return early so we don't create a new starboard message
                            # when the first time we're seeing the message is on a
                            # reaction remove event
                            continue

                        reactions = [payload.user_id]
                        if payload.user_id == msg.author.id:
                            if not starboard.selfstar:
                                reactions.remove(payload.user_id)
                        star_message = StarboardMessage(
                            guild=guild.id,
                            original_message=payload.message_id,
                            original_channel=payload.channel_id,
                            new_message=None,
                            new_channel=None,
                            author=msg.author.id,
                            reactions=reactions,
                        )
                    starboard.stars_added += 1
                    key = f"{payload.channel_id}-{payload.message_id}"
                    # await star_message.update_count(self.bot, starboard, remove)
                    count = len(star_message.reactions)
                    # log.debug(f"First time {count=} {starboard.threshold=}")
                    if count < starboard.threshold:
                        if key not in starboard.messages:
                            self.starboards[guild.id][starboard.name].messages[key] = star_message
                        await self._save_starboards(guild)
                        continue
                    if not starboard.selfstar and msg.author.id == payload.user_id:
                        log.debug("Is a selfstar so let's return")
                        # this is here to prevent 1 threshold selfstars
                        continue
                    embeds = await self._build_embed(guild, msg, starboard)
                    count_msg = "{emoji} **#{count}**".format(emoji=payload.emoji, count=count)
                    post_msg = await star_channel.send(count_msg, embeds=embeds)
                    if starboard.autostar:
                        try:
                            await post_msg.add_reaction(starboard.emoji)
                        except Exception:
                            log.exception("Error adding autostar.")
                    if key not in starboard.messages:
                        self.starboards[guild.id][starboard.name].messages[key] = star_message
                    star_message.new_message = post_msg.id
                    star_message.new_channel = star_channel.id
                    starboard.starred_messages += 1
                    index_key = f"{star_channel.id}-{post_msg.id}"
                    self.starboards[guild.id][starboard.name].messages[key] = star_message
                    self.starboards[guild.id][starboard.name].starboarded_messages[index_key] = key
                    await self._save_starboards(guild)

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ) -> None:
        """
        Method for finding users data inside the cog and deleting it.
        """
        for guild_id, starboards in self.starboards.items():
            for starboard, entry in starboards.items():
                for message_ids, message in entry.messages.items():
                    if message.author == user_id:
                        index_key = f"{message.new_channel}-{message.new_message}"
                        try:
                            del self.starboards[guild_id][starboard].messages[message_ids]
                            del self.starboards[guild_id][starboard].starboarded_messages[
                                index_key
                            ]
                        except Exception:
                            pass
            async with self.config.guild_from_id(guild_id).starboards() as starboards:
                for name, starboard in self.starboards[guild_id].items():
                    starboards[name] = await starboard.to_json()

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
            to_purge = datetime.now(timezone.utc) - purge
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
                        to_rem_index = []
                        try:
                            async for message_ids, message in AsyncIter(
                                starboard.messages.items(), steps=500
                            ):
                                if message.new_message:
                                    if snowflake_time(message.new_message) < to_purge:
                                        to_rem.append(message_ids)
                                        index_key = f"{message.new_channel}-{message.new_message}"
                                        to_rem_index.append(index_key)
                                else:
                                    if snowflake_time(message.original_message) < to_purge:
                                        to_rem.append(message_ids)
                            for m in to_rem:
                                log.verbose("Removing %s", m)
                                del starboard.messages[m]
                                total_pruned += 1
                            for m in to_rem_index:
                                del starboard.starboarded_messages[m]
                            if len(to_rem) > 0:
                                log.info(
                                    "Starboard pruned %s messages that are "
                                    "%s old from "
                                    "%s (%s)",
                                    len(to_rem),
                                    humanize_timedelta(timedelta=purge),
                                    guild.name,
                                    guild.id,
                                )
                        except Exception:
                            log.exception("Error trying to clenaup old starboard messages.")
                await self._save_starboards(guild)
            if total_pruned:
                log.info(
                    "Starboard has pruned %s messages and ignored %s guilds.",
                    total_pruned,
                    guilds_ignored,
                )
            # Sleep 1 day but also run on cog reload
            await asyncio.sleep(60 * 60 * 24)

    async def _loop_messages(
        self,
        payload: Union[discord.RawReactionActionEvent, FakePayload],
        starboard: StarboardEntry,
        star_channel: discord.TextChannel,
        is_clear: bool = False,
    ) -> Union[StarboardMessage, bool]:
        """
        This handles finding if we have already saved a message internally

        Parameters
        ----------
            paylod: Union[discord.RawReactionActionEvent, FakePayload]
                Represents the raw reaction payload for the starred message
            starboard: StarboardEntry
                The starboard which matched the reaction emoji.
            star_channel: discord.TextChannel
                The channel which we want to send starboard messages into.
            is_clear: bool
                Whether or not the reaction event was for clearing all emojis.

        Returns
        -------
            Union[StarboardMessage, bool]
                StarboardMessage object if we have already saved this message
                but have not posted the new message yet.

                True if we have found the starboard object and no further action is
                required.

                False if we want to post the new starboard message.

        """
        try:
            guild = star_channel.guild
        except AttributeError:
            return False
        key = f"{payload.channel_id}-{payload.message_id}"
        if key in starboard.messages:
            # the starred message was an original starboard message
            starboard_msg = starboard.messages[key]
        elif key in starboard.starboarded_messages:
            # the starred message was the starboarded message
            key = starboard.starboarded_messages[key]
            starboard_msg = starboard.messages[key]
            pass
        else:
            return False

        # await starboard_msg.update_count(self.bot, starboard, remove)
        if not starboard.selfstar and payload.user_id == starboard_msg.author:
            return True

        if getattr(payload, "event_type", None) == "REACTION_ADD":
            if (user_id := getattr(payload, "user_id", 0)) not in starboard_msg.reactions:
                starboard_msg.reactions.append(user_id)
                log.verbose("Adding user (%s) in _loop_messages", user_id)
                starboard.stars_added += 1
        else:
            if (user_id := getattr(payload, "user_id", 0)) in starboard_msg.reactions:
                starboard_msg.reactions.remove(user_id)
                log.verbose("Removing user (%s) in _loop_messages", user_id)
                starboard.stars_added -= 1

        if not starboard_msg.new_message or not starboard_msg.new_channel:
            return starboard_msg
        count = len(starboard_msg.reactions)
        log.debug("Existing count=%s starboard.threshold=%s", count, starboard.threshold)
        if count < starboard.threshold:
            try:
                index_key = f"{starboard_msg.new_channel}-{starboard_msg.new_message}"
                del starboard.starboarded_messages[index_key]
                log.debug("Removed old message from index")
            except KeyError:
                pass
            await starboard_msg.delete(star_channel)
            starboard.starred_messages -= 1
            await self._save_starboards(guild)
            return True
        log.debug("Editing starboard")
        count_message = f"{starboard.emoji} **#{count}**"
        asyncio.create_task(starboard_msg.edit(star_channel, count_message))
        # create a task because otherwise we could wait up to an hour to open the lock.
        # This is thanks to announcement channels and published messages.
        return True
