import discord
import random
from redbot.core import commands

class Mock(getattr(commands, "Cog", object)):
    """mock a user as spongebob"""

    def __init__(self, bot):
        self.bot = bot

    def cap_change(self, message):
        result = ""
        for char in message:
            value = random.choice([True, False])
            if value:
                result += char.upper()
            else:
                result += char.lower()
        return result

    @commands.command(pass_context=True)
    async def mock(self, ctx, *, msg=""):
        """
            Mock a user with the spongebob meme

            `msg` can be either custom message or message ID
            if no `msg` is provided the command will use the last message in chat before the command
        """
        channel = ctx.message.channel
        result = ""
        user = ctx.message.author
        if msg:
            if msg.isdigit():
                async for message in channel.history(limit=100):
                    if str(message.id) == msg:
                        msg = message
                        break
        else:
            async for message in channel.history(limit=2):
                msg = message
        result = self.cap_change(msg.content) if hasattr(msg, "content") else self.cap_change(msg)
        author = msg.author if hasattr(msg, "author") else ctx.message.author
        time = msg.created_at if hasattr(msg, "created_at") else ctx.message.created_at
        embed = discord.Embed(description=result, timestamp=time)
        embed.colour = author.colour if hasattr(author, "colour") else discord.Colour.default()
        embed.set_author(name=author.display_name, icon_url=author.avatar_url)
        embed.set_thumbnail(url="https://i.imgur.com/upItEiG.jpg")
        embed.set_footer(text="{} mocked {}".format(
                         ctx.message.author.display_name, author.display_name), icon_url=ctx.message.author.avatar_url)
        if hasattr(msg, "attachments") and msg.attachments != []:
            embed.set_image(url=msg.attachments[0].url)
        if not channel.permissions_for(ctx.me).embed_links:
            if author != user:
                await ctx.send(result + " - " + author.mention)
            else:
                await ctx.send(result)
        else:
            await ctx.send(embed=embed)
            if author != user:
                await ctx.send("- " + author.mention)
