import discord
from redbot.core import commands, Config, checks
from .unicode_codes import UNICODE_EMOJI

class EmojiReactions(getattr(commands, "Cog", object)):
    """
        Automatically react to messages with emojis in them with the emoji
    """
    
    def __init__(self, bot):
        self.bot = bot
        default_guild = {"unicode": False, "guild":False, "random":False}
        self.config = Config.get_conf(self, 35677998656)
        self.config.register_guild(**default_guild)

    @commands.group()
    @checks.admin_or_permissions(manage_messages=True)
    async def emojireact(self, ctx):
        """
            Automatically react to messages with emojis in them with the emoji
        """
        if ctx.invoked_subcommand is None:          
            try:
                guild = ctx.message.guild
                em = discord.Embed(title="Emojireact settings for {}".format(guild.name), colour=discord.Colour.blue())
                em.add_field(name="Server", value=str(await self.config.guild(guild).guild()))
                em.add_field(name="Unicode", value=str(await self.config.guild(guild).unicode()))
                await ctx.send(embed=em)
            except:
                pass


    @emojireact.command(name="unicode")
    async def _unicode(self, ctx):
        """Toggle unicode emoji reactions"""
        if await self.config.guild(ctx.guild).unicode():
            await self.config.guild(ctx.guild).unicode.set(False)
            await ctx.send("Okay, I will not react to messages containing unicode emojis!")
        else:
            await self.config.guild(ctx.guild).unicode.set(True)
            await ctx.send("Okay, I will react to messages containing unicode emojis!")

    @emojireact.command(name="guild")
    async def _guild(self, ctx):
        """Toggle guild emoji reactions"""
        if await self.config.guild(ctx.guild).guild():
            await self.config.guild(ctx.guild).guild.set(False)
            await ctx.send("Okay, I will not react to messages containing server emojis!")
        else:
            await self.config.guild(ctx.guild).guild.set(True)
            await ctx.send("Okay, I will react to messages containing server emojis!")

    @emojireact.command(name="all")
    async def _all(self, ctx):
        """Toggle all emoji reactions"""
        if await self.config.guild(ctx.guild).guild() or await self.config.guild(ctx.guild).unicode():
            await self.config.guild(ctx.guild).guild.set(False)
            await self.config.guild(ctx.guild).unicode.set(False)
            await ctx.send("Okay, I will not react to messages containing all emojis!")
        else:
            await self.config.guild(ctx.guild).guild.set(True)
            await self.config.guild(ctx.guild).unicode.set(True)
            await ctx.send("Okay, I will react to messages containing all emojis!")

    async def on_message(self, message):
        channel = message.channel
        emoji_list = []
        if message.guild is None:
            return
        for word in message.content.split(" "):
            if word.startswith("<:") and word.endswith(">") and await self.config.guild(message.guild).guild():
                emoji_list.append(word.rpartition(">")[0].partition("<")[2])
            if word in UNICODE_EMOJI and await self.config.guild(message.guild).unicode():
                emoji_list.append(word)
        if emoji_list == []:
            return
        for emoji in emoji_list:
            try:
                await message.add_reaction(emoji)
            except:
                pass
