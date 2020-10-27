import asyncio
from dataclasses import dataclass
from typing import List, Dict, Optional, Union


@dataclass
class FakePayload:
    """A fake payload object to utilize `_update_stars` method"""
    channel_id: int
    message_id: int
    user_id: int
    emoji: str


@dataclass
class StarboardMessage:
    """A class to hold message objects pertaining
    To starboarded messages including the original
    message ID, and the starboard message ID
    as well as a list of users who have added their "vote"
    """
    def __init__(self, **kwargs):
        self.original_message: int = kwargs.get("original_message")
        self.original_channel: int = kwargs.get("original_channel")
        self.new_message: Optional[int] = kwargs.get("new_message")
        self.new_channel: Optional[int] = kwargs.get("new_channel")
        self.author: int = kwargs.get("author")
        self.reactions: List[int] = kwargs.get("reactions")

    def to_json(self) -> dict:
        return {
            "original_message": self.original_message,
            "original_channel": self.original_channel,
            "new_message": self.new_message,
            "new_channel": self.new_channel,
            "author": self.author,
            "reactions": self.reactions,
        }

    @classmethod
    def from_json(cls, data: dict):
        reactions = []
        if "reactions" in data:
            reactions = data["reactions"]
        return cls(
            original_message=data["original_message"],
            original_channel=data["original_channel"],
            new_message=data["new_message"],
            new_channel=data["new_channel"],
            author=data["author"],
            reactions=reactions,
        )


@dataclass
class StarboardEntry:
    def __init__(self, **kwargs):

        super().__init__()
        self.name: str = kwargs.get("name")
        self.channel: int = kwargs.get("channel")
        self.emoji: str = kwargs.get("emoji")
        self.colour: str = kwargs.get("colour", "user")
        self.enabled: bool = kwargs.get("enabled", True)
        self.selfstar: bool = kwargs.get("selfstar", False)
        self.blacklist_role: List[int] = kwargs.get("blacklist_role", [])
        self.whitelist_role: List[int] = kwargs.get("whitelist_role", [])
        self.messages: List[StarboardMessage] = kwargs.get(
            "messages", []
        )
        self.blacklist_channel: List[int] = kwargs.get("blacklist_channel", [])
        self.whitelist_channel: List[int] = kwargs.get("whitelist_channel", [])
        self.threshold: int = kwargs.get("threshold", 1)
        self.autostar: bool = kwargs.get("autostar", False)
        self.lock: asyncio.Lock = asyncio.Lock()

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "channel": self.channel,
            "emoji": self.emoji,
            "colour": self.colour,
            "selfstar": self.selfstar,
            "blacklist_role": self.blacklist_role,
            "whitelist_role": self.whitelist_role,
            "messages": [m.to_json() for m in self.messages],
            "blacklist_channel": self.blacklist_channel,
            "whitelist_channel": self.whitelist_channel,
            "threshold": self.threshold,
            "autostar": self.autostar,
        }

    @classmethod
    def from_json(cls, data: dict):
        colour = "user"
        selfstar = False
        autostar = False
        if "autostar" in data:
            autostar = data["autostar"]
        if "selfstar" in data:
            selfstar = data["selfstar"]
        if "colour" in data:
            colour = data["colour"]
        messages = []
        if "messages" in data:
            messages = [StarboardMessage.from_json(m) for m in data["messages"]]
        return cls(
            name=data["name"],
            channel=data["channel"],
            emoji=data["emoji"],
            colour=colour,
            enabled=data["enabled"],
            selfstar=selfstar,
            blacklist_role=data["blacklist_role"],
            whitelist_role=data["whitelist_role"],
            messages=messages,
            blacklist_channel=data["blacklist_channel"],
            whitelist_channel=data["whitelist_channel"],
            threshold=data["threshold"],
            autostar=autostar,
        )
