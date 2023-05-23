from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

log = getLogger("red.trusty-cogs.starboard")


@dataclass
class FakePayload:
    """A fake payload object to utilize `_update_stars` method"""

    guild_id: int
    channel_id: int
    message_id: int
    user_id: int
    emoji: str
    event_type: str


@dataclass
class StarboardEntry:
    def __init__(self, **kwargs):
        super().__init__()
        self.name: str = kwargs.get("name", "starboard")
        self.guild: int = kwargs.get("guild", None)
        self.channel: int = kwargs.get("channel", 0)
        self.emoji: discord.PartialEmoji = discord.PartialEmoji.from_str(kwargs.get("emoji", "⭐"))
        self.colour: str = kwargs.get("colour", "user")
        self.enabled: bool = kwargs.get("enabled", True)
        self.selfstar: bool = kwargs.get("selfstar", False)
        self.blacklist: List[int] = kwargs.get("blacklist", [])
        self.whitelist: List[int] = kwargs.get("whitelist", [])
        self.messages: Dict[str, StarboardMessage] = kwargs.get("messages", {})
        self.starboarded_messages: Dict[str, str] = kwargs.get("starboarded_messages", {})
        self.threshold: int = kwargs.get("threshold", 1)
        self.autostar: bool = kwargs.get("autostar", False)
        self.starred_messages: int = kwargs.get("starred_messages", 0)
        self.stars_added: int = kwargs.get("stars_added", 0)
        self.lock: asyncio.Lock = asyncio.Lock()
        self.inherit: bool = kwargs.get("inherit", False)

    def __repr__(self) -> str:
        return (
            "<Starboard guild={0.guild} name={0.name} emoji={0.emoji} "
            "enabled={0.enabled} threshold={0.threshold}>"
        ).format(self)

    def check_roles(self, member: Union[discord.Member, discord.User]) -> bool:
        """
        Checks if the user is allowed to add to the starboard
        Allows bot owner to always add messages for testing
        disallows users from adding their own messages

        Parameters
        ----------
            member: Union[discord.Member, discord.User]
                The member object which added the reaction for this starboard.

        Returns
        -------
            bool
                Whether or not this member is allowed to utilize this starboard.
        """
        if not isinstance(member, discord.Member):
            # this will account for non-members reactions and still count
            # for the starboard count
            return True
        guild = member.guild
        whitelisted_roles = [
            guild.get_role(rid) for rid in self.whitelist if guild.get_role(rid) is not None
        ]
        blacklisted_roles = [
            guild.get_role(rid) for rid in self.blacklist if guild.get_role(rid) is not None
        ]
        if whitelisted_roles:
            # only count if the whitelist contains actual roles
            for role in whitelisted_roles:
                if role in member.roles:
                    return True
            return False
            # Since we'd normally return True
            # if there is a whitelist we want to ensure only whitelisted
            # roles can starboard something
        if blacklisted_roles:
            for role in blacklisted_roles:
                if role in member.roles:
                    return False

        return True

    def check_channel(self, bot: Red, channel: discord.TextChannel) -> bool:
        """
        Checks if the channel is allowed to track starboard
        messages

        Parameters
        ----------
            bot: Red
                The bot object
            channel: discord.TextChannel
                The channel we want to verify we're allowed to post in

        Returns
        -------
            bool
                Whether or not the channel we got a "star" in we're allowed
                to repost.
        """
        guild = bot.get_guild(self.guild)
        if guild is None:
            return False
        if not guild.get_channel_or_thread(self.channel):
            return False
        if channel is None:
            return False
        sb_channel = guild.get_channel_or_thread(self.channel)
        if sb_channel is None:
            return False
        if channel.is_nsfw() and not sb_channel.is_nsfw():
            return False
        whitelisted_channels = [
            guild.get_channel_or_thread(cid).id
            for cid in self.whitelist
            if guild.get_channel_or_thread(cid) is not None
        ]
        blacklisted_channels = [
            guild.get_channel_or_thread(cid).id
            for cid in self.blacklist
            if guild.get_channel_or_thread(cid) is not None
        ]
        if whitelisted_channels:
            if channel.id in whitelisted_channels:
                return True
            if channel.category_id and channel.category_id in whitelisted_channels:
                return True
            if self.inherit:
                if isinstance(channel, (discord.Thread, discord.ForumChannel)):
                    if channel.parent.id in whitelisted_channels:
                        return True
            return False
        if blacklisted_channels:
            if channel.id in blacklisted_channels:
                return False
            if channel.category_id and channel.category_id in blacklisted_channels:
                return False
            if self.inherit:
                if isinstance(channel, (discord.Thread, discord.ForumChannel)):
                    if channel.parent.id in blacklisted_channels:
                        return False
        return True

    async def to_json(self) -> dict:
        return {
            "name": self.name,
            "guild": self.guild,
            "enabled": self.enabled,
            "channel": self.channel,
            "emoji": str(self.emoji),
            "colour": self.colour,
            "selfstar": self.selfstar,
            "blacklist": self.blacklist,
            "whitelist": self.whitelist,
            "messages": {
                k: m.to_json() async for k, m in AsyncIter(self.messages.items(), steps=500)
            },
            "starboarded_messages": self.starboarded_messages,
            "threshold": self.threshold,
            "autostar": self.autostar,
            "starred_messages": self.starred_messages,
            "stars_added": self.stars_added,
            "inherit": self.inherit,
        }

    @classmethod
    async def from_json(cls, data: dict, guild_id: Optional[int]):
        messages = data.get("messages", {})
        guild = data.get("guild", guild_id)
        if guild is None and guild_id is not None:
            guild = guild_id
        starboarded_messages = data.get("starboarded_messages", {})
        if isinstance(messages, list):
            new_messages = {}
            async for message_data in AsyncIter(messages, steps=500):
                message_obj = StarboardMessage.from_json(message_data, guild)
                if not message_obj.guild:
                    message_obj.guild = guild
                key = f"{message_obj.original_channel}-{message_obj.original_message}"
                new_messages[key] = message_obj
            messages = new_messages
        else:
            new_messages = {}
            async for key, value in AsyncIter(messages.items()):
                msg = StarboardMessage.from_json(value, guild)
                new_messages[key] = msg
            messages = new_messages
        if not starboarded_messages:
            async for message_ids, obj in AsyncIter(messages.items()):
                key = f"{obj.new_channel}-{obj.new_message}"
                starboarded_messages[key] = f"{obj.original_channel}-{obj.original_message}"
        starred_messages = data.get("starred_messages", len(starboarded_messages))
        stars_added = data.get("stars_added", 0)
        if not stars_added:
            async for message_id, message in AsyncIter(messages.items(), steps=500):
                stars_added += len(message.reactions)
        blacklist = data.get("blacklist", [])
        whitelist = data.get("whitelist", [])
        if data.get("blacklist_channel") or data.get("blacklist_role"):
            log.debug("Converting blacklist")
            blacklist += data.get("blacklist_channel", [])
            blacklist += data.get("blacklist_role", [])
        if data.get("whitelist_channel") or data.get("whitelist_role"):
            log.debug("Converting whitelist")
            whitelist += data.get("whitelist_channel", [])
            whitelist += data.get("whitelist_role", [])
        inherit = data.get("inherit", False)
        return cls(
            name=data.get("name"),
            guild=guild,
            channel=data.get("channel"),
            emoji=data.get("emoji"),
            colour=data.get("colour", "user"),
            enabled=data.get("enabled"),
            selfstar=data.get("selfstar", False),
            blacklist=blacklist,
            whitelist=whitelist,
            messages=messages,
            threshold=data.get("threshold"),
            autostar=data.get("autostar", False),
            starboarded_messages=starboarded_messages,
            starred_messages=starred_messages,
            stars_added=stars_added,
            inherit=inherit,
        )


@dataclass
class StarboardMessage:
    """A class to hold message objects pertaining
    To starboarded messages including the original
    message ID, and the starboard message ID
    as well as a list of users who have added their "vote"
    """

    def __init__(self, **kwargs):
        self.guild: int = kwargs.get("guild", None)
        self.original_message: int = kwargs.get("original_message", 0)
        self.original_channel: int = kwargs.get("original_channel", 0)
        self.new_message: Optional[int] = kwargs.get("new_message")
        self.new_channel: Optional[int] = kwargs.get("new_channel")
        self.author: int = kwargs.get("author", 0)
        self.reactions: List[int] = kwargs.get("reactions", [])

    def __repr__(self) -> str:
        return (
            "<StarboardMessage author={0.author} guild={0.guild} count={1} "
            "original_channel={0.original_channel} original_message={0.original_message} "
            "new_channel={0.new_channel} new_message={0.new_message}>"
        ).format(self, len(self.reactions))

    async def delete(self, star_channel: discord.TextChannel) -> None:
        if self.new_message is None:
            return
        try:
            message_edit = star_channel.get_partial_message(self.new_message)
            self.new_message = None
            self.new_channel = None
            await message_edit.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden):
            return

    async def edit(self, star_channel: discord.TextChannel, content: str) -> None:
        if self.new_message is None:
            return
        try:
            message_edit = star_channel.get_partial_message(self.new_message)
            await message_edit.edit(content=content)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            return

    async def update_count(
        self, bot: Red, starboard: StarboardEntry, remove: Optional[int]
    ) -> None:
        """
        This function can pull the most accurate reaction info from a starboarded message
        However it takes at least 2 API calls which can be expensive. I am leaving
        This here for future potential needs but we should instead rely on our
        listener to keep track of reactions added/removed.

        Parameters
        ----------
            bot: Red
                The bot object used for bot.get_guild
            starbaord: StarboardEntry
                The starboard object which contains this message entry
            remove: Optional[int]
                This was used to represent a user who removed their reaction.

        Returns
        -------
            MessageEntry
                Returns itself although since this is handled in memory is not required.
        """
        guild = bot.get_guild(self.guild)
        # log.debug(f"{guild=} {self.guild=}")
        orig_channel = guild.get_channel_or_thread(self.original_channel)
        new_channel = guild.get_channel_or_thread(self.new_channel)
        orig_reaction = []
        if orig_channel:
            try:
                orig_msg = await orig_channel.fetch_message(self.original_message)
                orig_reaction = [
                    r for r in orig_msg.reactions if str(r.emoji) == str(starboard.emoji)
                ]
            except discord.HTTPException:
                pass
        new_reaction = []
        if new_channel:
            try:
                new_msg = await new_channel.fetch_message(self.new_message)
                new_reaction = [
                    r for r in new_msg.reactions if str(r.emoji) == str(starboard.emoji)
                ]
            except discord.HTTPException:
                pass
        reactions = orig_reaction + new_reaction
        for reaction in reactions:
            async for user in reaction.users():
                if not starboard.check_roles(user):
                    continue
                if not starboard.selfstar and user.id == orig_msg.author.id:
                    continue
                if user.id not in self.reactions and not user.bot:
                    self.reactions.append(user.id)
        if remove and remove in self.reactions:
            self.reactions.remove(remove)
        self.reactions = list(set(self.reactions))
        return self

    def to_json(self) -> Dict[str, Union[List[int], int, None]]:
        return {
            "guild": self.guild,
            "original_message": self.original_message,
            "original_channel": self.original_channel,
            "new_message": self.new_message,
            "new_channel": self.new_channel,
            "author": self.author,
            "reactions": self.reactions,
        }

    @classmethod
    def from_json(
        cls, data: Dict[str, Union[List[int], int, None]], guild_id: Optional[int]
    ) -> StarboardMessage:
        return cls(
            guild=data.get("guild", guild_id),
            original_message=data.get("original_message"),
            original_channel=data.get("original_channel"),
            new_message=data.get("new_message"),
            new_channel=data.get("new_channel"),
            author=data.get("author"),
            reactions=data.get("reactions", []),
        )
