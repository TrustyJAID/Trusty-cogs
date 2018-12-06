from typing import Tuple
from redbot.core import commands

import discord

class TweetEntry:
    def __init__(self, twitter_id: int, twitter_name: str, 
                 channel: list, last_tweet: int, replies:bool=False):
        super().__init__()
        self.twitter_id = twitter_id
        self.twitter_name = twitter_name
        self.channel = channel
        self.last_tweet = last_tweet
        self.replies = replies

    def to_json(self) -> dict:
        return {
            "twitter_id": self.twitter_id,
            "twitter_name": self.twitter_name,
            "channel": self.channel,
            "last_tweet": self.last_tweet,
            "replies": self.replies
        }

    @classmethod
    def from_json(cls, data: dict):
        return cls(data["twitter_id"], data["twitter_name"],
                  data["channel"], data["last_tweet"], data["replies"])
