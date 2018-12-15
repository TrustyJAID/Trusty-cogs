import discord
from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
from .unicode_codes import UNICODE_EMOJI

_ = Translator("EmojiReactions", __file__)


@cog_i18n(_)
class EmojiReactions(getattr(commands, "Cog", object)):
    """
        Automatically react to messages with emojis in them with the emoji
    """
    
    def __init__(self, bot):
        self.bot = bot
        default_guild = {"unicode": False, 
                         "guild":False, 
                         "random":False}
        self.config = Config.get_conf(self, 35677998656)
        self.config.register_guild(**default_guild)

    @commands.group()
    @checks.admin_or_permissions(manage_messages=True)
    async def emojireact(self, ctx):
        """
            Automatically react to messages with emojis in them with the emoji
        """
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            guild_emoji = await self.config.guild(guild).guild()
            unicode_emoji = await self.config.guild(guild).unicode()          
            if ctx.channel.permissions_for(ctx.me).embed_links:
                em = discord.Embed(colour=discord.Colour.blue())
                em.title=_("Emojireact settings for ")+ guild.name
                if guild_emoji:
                    em.add_field(name=_("Server Emojis "), value=str(guild_emoji))
                if unicode_emoji:
                    em.add_field(name=_("Unicode Emojis "), value=str(unicode_emoji))
                if len(em.fields) > 0:
                    await ctx.send(embed=em)
            else:
                msg = _("Emojireact settings for ")+ guild.name + "\n"
                if guild_emoji:
                    msg += _("Server Emojis ") + str(guild_emoji) + "\n"
                if unicode_emoji:
                    msg += _("Unicode Emojis ") + str(unicode_emoji) + "\n"
                await ctx.send(msg)

    @emojireact.command(name="unicode")
    async def _unicode(self, ctx):
        """Toggle unicode emoji reactions"""
        if await self.config.guild(ctx.guild).unicode():
            await self.config.guild(ctx.guild).unicode.set(False)
            msg = _("Okay, I will not react to messages "
                   "containing unicode emojis!")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).unicode.set(True)
            msg = _("Okay, I will react to messages "
                    "containing unicode emojis!")
            await ctx.send(msg)

    @emojireact.command(name="guild")
    async def _guild(self, ctx):
        """Toggle guild emoji reactions"""
        if await self.config.guild(ctx.guild).guild():
            await self.config.guild(ctx.guild).guild.set(False)
            msg = _("Okay, I will not react to messages "
                  "containing server emojis!")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).guild.set(True)
            msg = _("Okay, I will react to messages "
                    "containing server emojis!")
            await ctx.send(msg)

    @emojireact.command(name="all")
    async def _all(self, ctx):
        """Toggle all emoji reactions"""
        guild_emoji = await self.config.guild(ctx.guild).guild()
        unicode_emoji = await self.config.guild(ctx.guild).unicode()
        if guild_emoji or unicode_emoji:
            await self.config.guild(ctx.guild).guild.set(False)
            await self.config.guild(ctx.guild).unicode.set(False)
            msg = _("Okay, I will not react to messages "
                    "containing all emojis!")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).guild.set(True)
            await self.config.guild(ctx.guild).unicode.set(True)
            msg = _("Okay, I will react to messages "
                    "containing all emojis!")
            await ctx.send(msg)

    async def on_message(self, message):
        channel = message.channel
        emoji_list = []
        if message.guild is None:
            return
        guild_emoji = await self.config.guild(message.guild).guild()
        unicode_emoji = await self.config.guild(message.guild).unicode()
        for word in message.content.split(" "):
            if word.startswith("<:") and word.endswith(">") and guild_emoji:
                emoji_list.append(word.rpartition(">")[0].partition("<")[2])
            if word in UNICODE_EMOJI and unicode_emoji:
                emoji_list.append(word)
        if emoji_list == []:
            return
        for emoji in emoji_list:
            try:
                await message.add_reaction(emoji)
            except:
                pass
