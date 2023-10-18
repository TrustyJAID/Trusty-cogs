# Borrowed with permission from
# https://github.com/mikeshardmind/SinbadCogs/blob/v3/scheduler/message.py

from __future__ import annotations

import re
from typing import List, Union

import discord

EVERYONE_REGEX = re.compile(r"@here|@everyone")

# This entire below block is such an awful hack. Don't look at it too closely.


class ReTriggerMessage(discord.Message):
    """
    Subclassed discord message with neutered coroutines.

    Extremely butchered class for a specific use case.
    Be careful when using this in other use cases.
    """

    def __init__(self, *, message: discord.Message) -> None:
        # auto current time
        self.id = message.id
        # important properties for even being processed
        self.author = message.author
        self.channel = message.channel
        self.content = message.content
        self.guild = message.channel.guild  # type: ignore
        self.reference = message.reference
        # this is required to fix an issue with cooldown commands
        self._edited_timestamp = message.created_at
        # this attribute being in almost everything (and needing to be) is a pain
        self._state = self.guild._state  # type: ignore
        # sane values below, fresh messages which are commands should exhibit these.
        self.call = None
        self.type = discord.MessageType.default
        self.tts = False
        self.pinned = False
        # suport for attachments somehow later maybe?
        self.attachments: List[discord.Attachment] = message.attachments
        # support for embed search
        self.embeds = message.embeds
        # mentions
        self.mention_everyone = self.channel.permissions_for(
            self.author
        ).mention_everyone and bool(EVERYONE_REGEX.match(self.content))
        # pylint: disable=E1133
        # pylint improperly detects the inherited properties here as not being iterable
        # This should be fixed with typehint support added to upstream lib later
        self.mentions: List[Union[discord.User, discord.Member]] = list(
            filter(None, [self.guild.get_member(idx) for idx in self.raw_mentions])
        )
        self.channel_mentions: List[discord.TextChannel] = list(
            filter(
                None,
                [self.guild.get_channel(idx) for idx in self.raw_channel_mentions],  # type: ignore
            )
        )
        self.role_mentions: List[discord.Role] = list(
            filter(None, [self.guild.get_role(idx) for idx in self.raw_role_mentions])
        )
        self.webhook_id = None
        self.retrigger = True
