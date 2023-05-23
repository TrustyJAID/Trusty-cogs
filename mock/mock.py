import random
from typing import Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands

log = getLogger("red.trusty-cogs.mock")


class Mock(commands.Cog):
    """mock a user as spongebob"""

    __author__ = ["TrustyJAID"]
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context):
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def cap_change(self, message: str) -> str:
        result = ""
        for char in message:
            value = random.choice([True, False])
            if value:
                result += char.upper()
            else:
                result += char.lower()
        return result

    @commands.command()
    async def mock(
        self,
        ctx: commands.Context,
        *,
        msg: Optional[Union[discord.Message, discord.Member, str]] = None,
    ) -> None:
        """
        Mock a user with the spongebob meme

        `[msg]` Optional either member, message ID, or string
        message ID can be channe_id-message-id formatted or a message link
        if no `msg` is provided the command will use the last message in channel before the command
        is `msg` is a member it will look through the past 10 messages in
        the `channel` and put them all together
        """
        if isinstance(msg, str):
            log.verbose("Mocking a given string")
            result = await self.cap_change(str(msg))
            result += f"\n\n[Mocking Message]({ctx.message.jump_url})"
            author = ctx.message.author
        elif isinstance(msg, discord.Member):
            log.verbose("Mocking a user")
            total_msg = ""
            async for message in ctx.channel.history(limit=10):
                if message.author == msg:
                    total_msg += message.content + "\n"
            result = await self.cap_change(total_msg)
            author = msg
        elif isinstance(msg, discord.Message):
            log.verbose("Mocking a message")
            result = await self.cap_change(msg.content)
            result += f"\n\n[Mocking Message]({msg.jump_url})"
            author = msg.author
            search_msg = msg
        else:
            log.verbose("Mocking last message in chat")
            async for message in ctx.channel.history(limit=2):
                search_msg = message
            author = search_msg.author
            result = await self.cap_change(search_msg.content)
            result += f"\n\n[Mocking Message]({search_msg.jump_url})"
            if result == "" and len(search_msg.embeds) != 0:
                if search_msg.embeds[0].description != discord.Embed.Empty:
                    result = await self.cap_change(search_msg.embeds[0].description)
        time = ctx.message.created_at
        embed = discord.Embed(description=result, timestamp=time)
        embed.colour = getattr(author, "colour", discord.Colour.default())
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        embed.set_thumbnail(url="https://i.imgur.com/upItEiG.jpg")
        embed.set_footer(
            text=f"{ctx.message.author.display_name} mocked {author.display_name}",
            icon_url=ctx.message.author.display_avatar.url,
        )
        if hasattr(msg, "attachments") and search_msg.attachments != []:
            embed.set_image(url=search_msg.attachments[0].url)
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            if author != ctx.message.author:
                await ctx.send(f"{result} - {author.mention}")
            else:
                await ctx.send(result)
        else:
            await ctx.channel.send(embed=embed)
            if author != ctx.message.author:
                await ctx.send(f"- {author.mention}")
