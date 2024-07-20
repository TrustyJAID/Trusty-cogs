from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Pattern, Union

import aiohttp
import discord
import unidecode
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import commands

IMAGE_LINKS: Pattern = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?P<extension>png|jpg|jpeg|gif)"
    r"(?P<extras>\?(?:ex=(?P<expires>\w+)&)(?:is=(?P<issued>\w+)&)(?:hm=(?P<token>\w+)&))?)",  # Discord CDN info
    flags=re.I,
)
TENOR_REGEX: Pattern[str] = re.compile(
    r"https:\/\/tenor\.com\/view\/(?P<image_slug>[a-zA-Z0-9-]+-(?P<image_id>\d+))"
)
EMOJI_REGEX: Pattern = re.compile(r"(<(?P<animated>a)?:[a-zA-Z0-9\_]+:([0-9]+)>)")
MENTION_REGEX: Pattern = re.compile(r"<@!?([0-9]+)>")
ID_REGEX: Pattern = re.compile(r"[0-9]{17,}")

VALID_CONTENT_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/gif")

log = getLogger("red.trusty-cogs.NotSoBot")


class TenorError(Exception):
    pass


@dataclass
class TenorMedia:
    url: str
    duration: int
    preview: str
    dims: List[int]
    size: int

    @classmethod
    def from_json(cls, data: dict) -> TenorMedia:
        known_data_keys = ["url", "duration", "preview", "dims", "size"]
        known_data = {k: data.pop(k) for k in known_data_keys}
        return cls(**known_data)


@dataclass
class TenorPost:
    id: str
    title: str
    media_formats: Dict[str, TenorMedia]
    created: float
    content_description: str
    itemurl: str
    url: str
    tags: List[str]
    flags: List[str]
    hasaudio: bool

    @classmethod
    def from_json(cls, data: dict) -> TenorPost:
        media = {k: TenorMedia.from_json(v) for k, v in data.pop("media_formats", {}).items()}
        known_data_keys = [
            "id",
            "title",
            "created",
            "content_description",
            "itemurl",
            "url",
            "tags",
            "flags",
            "hasaudio",
        ]
        known_data = {k: data.pop(k) for k in known_data_keys}
        return cls(**known_data, media_formats=media)


class TenorAPI:
    def __init__(self, token: str, client: str):
        self._token = token
        self._client = client
        self.session = aiohttp.ClientSession(base_url="https://tenor.googleapis.com")

    async def posts(self, ids: List[str]):
        params = {"key": self._token, "ids": ",".join(i for i in ids), "client_key": self._client}
        async with self.session.get("/v2/posts", params=params) as resp:
            data = await resp.json()
            if "error" in data:
                raise TenorError(data)
        return [TenorPost.from_json(i) for i in data.get("results", [])]


class ImageFinder(Converter):
    """
    This is a class to convert notsobots image searching capabilities
    into a more general converter class
    """

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> List[Union[discord.Asset, str]]:
        attachments = ctx.message.attachments
        mentions = MENTION_REGEX.finditer(argument)
        matches = IMAGE_LINKS.finditer(argument)
        emojis = EMOJI_REGEX.finditer(argument)
        ids = ID_REGEX.finditer(argument)
        tenor_matches = TENOR_REGEX.finditer(argument)
        urls = []
        if tenor_matches:
            api = ctx.cog.tenor
            if api:
                tenor_matches = [m.group("image_id") for m in tenor_matches]
                try:
                    posts = await api.posts(tenor_matches)
                    for post in posts:
                        if "gif" in post.media_formats:
                            urls.append(post.media_formats["gif"].url)
                except TenorError as e:
                    log.error("Error getting tenor image information. %s", e)

        if matches:
            for match in matches:
                urls.append(match.group(1))
        if emojis:
            for emoji in emojis:
                partial_emoji = discord.PartialEmoji.from_str(emoji.group(1))
                if partial_emoji.is_custom_emoji():
                    urls.append(partial_emoji.url)
        if mentions:
            for mention in mentions:
                if ctx.guild:
                    user = ctx.guild.get_member(int(mention.group(1)))
                else:
                    user = ctx.bot.get_user(int(mention.group(1)))
                if user is None:
                    continue
                if user.display_avatar.is_animated():
                    urls.append(user.display_avatar.replace(format="gif").url)
                else:
                    urls.append(user.display_avatar.replace(format="png").url)
        if not urls and ids:
            for possible_id in ids:
                if ctx.guild:
                    user = ctx.guild.get_member(int(possible_id.group(1)))
                else:
                    user = ctx.bot.get_user(int(possible_id.group(1)))
                if user:
                    if user.display_avatar.is_animated():
                        urls.append(user.display_avatar.replace(format="gif").url)
                    else:
                        urls.append(user.display_avatar.replace(format="png").url)
        if attachments:
            for attachment in attachments:
                if attachment.content_type not in VALID_CONTENT_TYPES:
                    continue
                urls.append(attachment.url)
        if not urls:
            if ctx.guild:
                user = await commands.MemberConverter().convert(ctx, argument)
                if user.display_avatar.is_animated():
                    urls.append(user.display_avatar.replace(format="gif").url)
                else:
                    urls.append(user.display_avatar.replace(format="png").url)

        if not urls:
            raise BadArgument("No images provided.")
        return urls

    @staticmethod
    async def search_for_images(
        ctx: commands.Context,
    ) -> List[Union[discord.Asset, discord.Attachment, str]]:
        urls = []
        if not ctx.channel.permissions_for(ctx.me).read_message_history:
            raise BadArgument("I require read message history perms to find images.")
        async for message in ctx.channel.history(limit=10):
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.content_type not in VALID_CONTENT_TYPES:
                        continue
                    urls.append(attachment)
            match = IMAGE_LINKS.match(message.content)
            if match:
                urls.append(match.group(1))
            tenor = TENOR_REGEX.match(message.content)
            if tenor:
                api = ctx.cog.tenor
                if api:
                    try:
                        posts = await api.posts([tenor.group("image_id")])
                        for post in posts:
                            if "gif" in post.media_formats:
                                urls.append(post.media_formats["gif"].url)
                    except TenorError as e:
                        log.error("Error getting tenor image information. %s", e)
        if not urls:
            raise BadArgument("No Images found in recent history.")
        return urls
