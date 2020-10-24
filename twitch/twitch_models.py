from dataclasses import dataclass

import discord


@dataclass(init=False)
class TwitchProfile:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.login = kwargs.get("login")
        self.display_name = kwargs.get("display_name")
        self.acc_type = kwargs.get("acc_type")
        self.broadcaster_type = kwargs.get("broadcaster_type")
        self.description = kwargs.get("description")
        self.profile_image_url = kwargs.get("profile_image_url")
        self.offline_image_url = kwargs.get("offline_image_url")
        self.view_count = kwargs.get("view_count")

    @classmethod
    def from_json(cls, data: dict):
        data = data["data"][0]
        return cls(**data)

    def make_user_embed(self) -> discord.Embed:
        # makes the embed for a twitch profile
        em = discord.Embed(colour=int("6441A4", 16))
        em.description = self.description
        url = "https://twitch.tv/{}".format(self.login)
        em.set_author(name=self.display_name, url=url, icon_url=self.profile_image_url)
        em.set_image(url=self.offline_image_url)
        em.set_thumbnail(url=self.profile_image_url)
        footer_text = "{} Viewer count".format(self.view_count)
        em.set_footer(text=footer_text, icon_url=self.profile_image_url)
        return em


@dataclass(init=False)
class TwitchFollower:
    def __init__(self, **kwargs):
        self.from_id = kwargs.get("from_id")
        self.to_id = kwargs.get("to_id")
        self.followed_at = kwargs.get("followed_at")

    @classmethod
    def from_json(cls, data: dict):
        return cls(**data)
