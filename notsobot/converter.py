import discord
import re

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

IMAGE_LINKS = re.compile(r"(http[s]?:\/\/[^\"\']*\.(?:png|jpg|jpeg|gif|png|svg))")
EMOJI_REGEX = re.compile(r"<a?:[a-zA-Z0-9\_]+:([0-9]+)>$")


class ImageFinder(Converter):
    """
        This is a class to convert notsobots image searching capabilities
        into a more general converter class
    """

    async def convert(self, ctx, argument):
        message = ctx.message
        channel = ctx.message.channel
        attachments = ctx.message.attachments
        mentions = ctx.message.mentions
        match = IMAGE_LINKS.match(argument)
        emoji = EMOJI_REGEX.match(argument)
        urls = []
        if match:
            urls.append(match.group(1))
        if emoji:
            ext = "gif" if argument.startswith("<a") else "png"
            url = "https://cdn.discordapp.com/emojis/{id}.{ext}?v=1".format(
                id=emoji.group(1), ext=ext
            )
            urls.append(url)
        if mentions:
            for user in mentions:
                if user.is_avatar_animated():
                    urls.append(user.avatar_url_as(format="gif"))
                else:
                    urls.append(user.avatar_url_as(format="png"))
        if attachments:
            for attachment in attachments:
                urls.append(attachment.url)

        if not urls:
            raise BadArgument("No images provided.")
        return urls

    async def search_for_images(self, ctx):
        urls = []
        async for message in ctx.channel.history(limit=10):
            if message.attachments:
                for attachment in message.attachments:
                    urls.append(attachment.url)
            match = IMAGE_LINKS.match(message.content)
            if match:
                urls.append(match.group(1))
        if not urls:
            raise BadArgument("No Images found in recent history.")
        return urls
