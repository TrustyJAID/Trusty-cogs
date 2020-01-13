import discord
import re

from typing import List, Tuple

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

IMAGE_LINKS = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|png))")


class Event:
    hoster: discord.Member
    members: List[discord.Member]
    event: str
    approver: discord.Member
    message: discord.Message
    channel: discord.TextChannel

    def __init__(
        self,
        hoster: discord.Member,
        members: List[Tuple[discord.Member, str]],
        event: str,
        approver: discord.Member = None,
        message: discord.Message = None,
        channel: discord.TextChannel = None
    ):
        self.hoster = hoster
        self.members = members
        self.event = event
        self.approver = approver
        self.message = message
        self.channel = channel

    @classmethod
    async def from_json(cls, data: dict, guild: discord.Guild):
        channel = guild.get_channel(data["channel"])
        message = None
        if not channel:
            return None
        try:
            message = await channel.get_message(data["message"])
        except AttributeError:
            message = await channel.fetch_message(data["message"])
        except Exception:
            # Return None if we can't find the original events
            return None
        return cls(
            guild.get_member(data["hoster"]),
            [(guild.get_member(m), p_class) for m, p_class in data["members"]],
            data["event"],
            guild.get_member(data["approver"]),
            message,
            channel
        )

    def to_json(self):
        return {
            "hoster": self.hoster.id,
            "members": [(m.id, p_class) for m, p_class in self.members],
            "event": self.event,
            "approver": self.approver.id if self.approver else None,
            "message": self.message.id if self.message else None,
            "channel": self.channel.id if self.channel else None
        }


class ValidImage(Converter):
    async def convert(self, ctx, argument):
        search = IMAGE_LINKS.search(argument)
        if not search:
            raise BadArgument("That's not a valid image link.")
        else:
            return argument
