import discord
import random
from redbot.core import commands
from typing import Union, Optional


class Mock(commands.Cog):
    """mock a user as spongebob"""

    __author__ = ["TrustyJAID"]
    __version__ = "1.0.7"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context):
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

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
        channel: Optional[discord.TextChannel] = None,
        *,
        msg: Optional[Union[discord.Member, int, str]] = None
    ) -> None:
        """
            Mock a user with the spongebob meme

            `channel` Optional channel to retrieve messages from and post the mock message
            `msg` Optional either member, message ID, or string
            if no `msg` is provided the command will use the last message in channel before the command
            is `msg` is a member it will look through the past 10 messages in
            the `channel` and put them all together
        """
        if not channel:
            send_channel = ctx.channel
        else:
            send_channel = channel
        result = ""
        mocker = ctx.message.author
        if type(msg) is int:
            try:
                search_msg = await ctx.channel.fetch_message(msg)
            except AttributeError:
                search_msg = await ctx.channel.get_message(msg)
            except discord.errors.NotFound:
                return
            except discord.errors.Forbidden:
                return
            result = await self.cap_change(search_msg.content)
            if result == "" and len(search_msg.embeds) != 0:
                if search_msg.embeds[0].description != discord.Embed.Empty:
                    result = await self.cap_change(search_msg.embeds[0].description)
            author = search_msg.author
        elif type(msg) is str:
            result = await self.cap_change(str(msg))
            author = ctx.message.author
        elif type(msg) is discord.Member:
            total_msg = ""
            async for message in send_channel.history(limit=10):
                if message.author == msg:
                    total_msg += message.content + "\n"
            result = await self.cap_change(total_msg)
            author = msg
        else:
            async for message in send_channel.history(limit=2):
                search_msg = message
            author = search_msg.author
            result = await self.cap_change(search_msg.content)
            if result == "" and len(search_msg.embeds) != 0:
                if search_msg.embeds[0].description != discord.Embed.Empty:
                    result = await self.cap_change(search_msg.embeds[0].description)
        time = ctx.message.created_at
        embed = discord.Embed(description=result, timestamp=time)
        embed.colour = getattr(author, "colour", discord.Colour.default())
        embed.set_author(name=author.display_name, icon_url=author.avatar_url)
        embed.set_thumbnail(url="https://i.imgur.com/upItEiG.jpg")
        embed.set_footer(
            text="{} mocked {}".format(ctx.message.author.display_name, author.display_name),
            icon_url=ctx.message.author.avatar_url,
        )
        if hasattr(msg, "attachments") and search_msg.attachments != []:
            embed.set_image(url=search_msg.attachments[0].url)
        if not send_channel.permissions_for(ctx.me).embed_links:
            if author != mocker:
                await send_channel.send(result + " - " + author.mention)
            else:
                await send_channel.send(result)
        else:
            await send_channel.send(embed=embed)
            if author != mocker:
                await send_channel.send("- " + author.mention)
