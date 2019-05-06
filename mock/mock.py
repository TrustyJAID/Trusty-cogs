import discord
import random
from redbot.core import commands
from typing import Union, Optional


class Mock(commands.Cog):
    """mock a user as spongebob"""

    def __init__(self, bot):
        self.bot = bot

    async def cap_change(self, message: str):
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
        ctx,
        channel: Optional[discord.TextChannel] = None,
        *,
        msg: Optional[Union[discord.Member, int, str]] = None
    ):
        """
            Mock a user with the spongebob meme

            `channel` Optional channel to retrieve messages from and post the mock message
            `msg` Optional either member, message ID, or string
            if no `msg` is provided the command will use the last message in channel before the command
            is `msg` is a member it will look through the past 10 messages in
            the `channel` and put them all together
        """
        if not channel:
            channel = ctx.channel
        result = ""
        mocker = ctx.message.author
        if type(msg) is int:
            try:
                msg = await ctx.channel.get_message(msg)
            except AttributeError:
                msg = await ctx.channel.fetch_message(msg)
            except discord.errors.Forbidden:
                return
        elif msg is None:
            async for message in channel.history(limit=2):
                msg = message
            author = msg.author
        if type(msg) is discord.Message:
            result = await self.cap_change(msg.content)
            if result == "" and len(msg.embeds) != 0:
                if msg.embeds[0].description != discord.Embed.Empty:
                    result = await self.cap_change(msg.embeds[0].description)
            author = msg.author
        elif type(msg) is discord.Member:
            total_msg = ""
            async for message in channel.history(limit=10):
                if message.author == msg:
                    total_msg += message.content + "\n"
            result = await self.cap_change(total_msg)
            author = msg
        else:
            result = await self.cap_change(msg)
            author = ctx.message.author
        time = ctx.message.created_at
        embed = discord.Embed(description=result, timestamp=time)
        embed.colour = author.colour if hasattr(author, "colour") else discord.Colour.default()
        embed.set_author(name=author.display_name, icon_url=author.avatar_url)
        embed.set_thumbnail(url="https://i.imgur.com/upItEiG.jpg")
        embed.set_footer(
            text="{} mocked {}".format(ctx.message.author.display_name, author.display_name),
            icon_url=ctx.message.author.avatar_url,
        )
        if hasattr(msg, "attachments") and msg.attachments != []:
            embed.set_image(url=msg.attachments[0].url)
        if not channel.permissions_for(ctx.me).embed_links:
            if author != mocker:
                await channel.send(result + " - " + author.mention)
            else:
                await channel.send(result)
        else:
            await channel.send(embed=embed)
            if author != mocker:
                await channel.send("- " + author.mention)
