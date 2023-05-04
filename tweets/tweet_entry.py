from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Union


@dataclass
class TweetEntry:
    def __init__(self, **kwargs):
        super().__init__()
        self.twitter_id = kwargs.get("twitter_id", 0)
        self.twitter_name = kwargs.get("twitter_name", "")
        self.channels = kwargs.get("channels", {})
        self.last_tweet = kwargs.get("last_tweet", 0)

    def __repr__(self) -> str:
        return "<TweetEntry twitter_name={0.twitter_name} twitter_id={0.twitter_id}>".format(self)

    def to_json(self) -> Dict[str, Union[Dict[str, Union[bool, int]], int, str]]:
        return {
            "twitter_id": self.twitter_id,
            "twitter_name": self.twitter_name,
            "channels": {k: v.to_json() for k, v in self.channels.items()},
            "last_tweet": self.last_tweet,
        }

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> TweetEntry:
        channel = data.get("channel", {})
        channels = data.get("channels", {})
        if isinstance(channel, list):
            for channel_id in data.get("channel", []):
                channels[str(channel_id)] = {
                    "guild": None,
                    "channel": channel_id,
                    "replies": data.get("replies", False),
                    "retweets": data.get("retweets", True),
                    "embeds": True,
                }
        channel_obj = {}
        for channel_ids, chan_data in channels.items():
            chan_data["channel"] = int(channel_ids)
            channel_obj[channel_ids] = ChannelData.from_json(chan_data)
        return cls(
            twitter_id=data.get("twitter_id"),
            twitter_name=data.get("twitter_name"),
            channels=channel_obj,
            last_tweet=data.get("last_tweet"),
        )


@dataclass
class ChannelData:
    def __init__(self, **kwargs):
        self.guild = kwargs.get("guild")
        self.channel = kwargs.get("channel")
        self.replies = kwargs.get("replies", False)
        self.retweets = kwargs.get("retweets", True)
        self.embeds = kwargs.get("embeds", True)

    def __str__(self) -> str:
        return (
            f"Replies: {self.replies} - ReTweets: {self.retweets} - Custom Embeds: {self.embeds}"
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "guild": self.guild,
            "channel": self.channel,
            "replies": self.replies,
            "retweets": self.retweets,
            "embeds": self.embeds,
        }

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> ChannelData:
        return cls(
            guild=data.get("guild"),
            channel=data.get("channel"),
            replies=data.get("replies", False),
            retweets=data.get("retweets", True),
            embeds=data.get("embeds", True),
        )
