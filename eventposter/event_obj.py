import re
from typing import List, Optional, Tuple, cast

import discord
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

IMAGE_LINKS = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|png))", flags=re.I)


class Event:
    hoster: discord.Member
    members: List[Tuple[discord.Member, str]]
    event: str
    max_slots: Optional[int]
    approver: Optional[discord.Member]
    message: Optional[discord.Message]
    channel: Optional[discord.TextChannel]
    maybe: Optional[List[discord.Member]]

    def __init__(self, **kwargs):
        self.hoster = kwargs.get("hoster")
        self.members = kwargs.get("members")
        self.event = kwargs.get("event")
        self.max_slots = kwargs.get("max_slots")
        self.approver = kwargs.get("approver")
        self.message = kwargs.get("message")
        self.channel = kwargs.get("channel")
        self.maybe = kwargs.get("maybe", [])

    def __str__(self):
        """used for debugging event information"""
        return f"{self.hoster}\n{self.members}\n{self.event}\n{self.max_slots}\n{self.maybe}"

    @classmethod
    async def from_json(cls, data: dict, guild: discord.Guild):
        channel = cast(discord.TextChannel, guild.get_channel(data["channel"]))
        message = None
        if not channel:
            return None
        try:
            message = await channel.fetch_message(data["message"])  # type: ignore
        except Exception:
            # Return None if we can't find the original events
            return None
        hoster = guild.get_member(data["hoster"])
        if not hoster:
            return None
        members = []
        for m in data["members"]:
            if isinstance(m, tuple) or isinstance(m, list):
                mem = guild.get_member(m[0])
                p_class = m[1]
            else:
                mem = guild.get_member(m)
                p_class = None
            if not mem:
                continue
            members.append((mem, p_class))

        max_slots = None
        if "max_slots" in data:
            max_slots = data["max_slots"]
        maybe = []
        if "maybe" in data:
            for m in data["maybe"]:
                mem = guild.get_member(m)
                if not mem:
                    continue
                maybe.append(mem)
        return cls(
            hoster=hoster,
            members=members,
            event=data["event"],
            max_slots=max_slots,
            approver=guild.get_member(data["approver"]),
            message=message,
            channel=channel,
            maybe=maybe,
        )

    def to_json(self):
        return {
            "hoster": self.hoster.id,
            "members": [(m.id, p_class) for m, p_class in self.members],
            "event": self.event,
            "max_slots": self.max_slots,
            "approver": self.approver.id if self.approver else None,
            "message": self.message.id if self.message else None,
            "channel": self.channel.id if self.channel else None,
            "maybe": [m.id for m in self.maybe],
        }


class ValidImage(Converter):
    async def convert(self, ctx, argument):
        search = IMAGE_LINKS.search(argument)
        if not search:
            raise BadArgument("That's not a valid image link.")
        else:
            return argument
