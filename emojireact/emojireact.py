import re

import discord
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n

from .unicode_codes import UNICODE_EMOJI

_ = Translator("EmojiReactions", __file__)

EMOJI = re.compile(r"(<?(a)?:([0-9a-zA-Z]+):([0-9]+)?>?)")
UNICODE_RE = re.compile("|".join(rf"{re.escape(w)}" for w in UNICODE_EMOJI.keys()))


@cog_i18n(_)
class EmojiReactions(commands.Cog):
    """
    Automatically react to messages with emojis in them with the emoji
    """

    def __init__(self, bot):
        self.bot = bot
        default_guild = {"unicode": False, "guild": False, "random": False}
        self.config = Config.get_conf(self, 35677998656)
        self.config.register_guild(**default_guild)

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

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
                em.title = _("Emojireact settings for ") + guild.name
                if guild_emoji:
                    em.add_field(name=_("Server Emojis "), value=str(guild_emoji))
                if unicode_emoji:
                    em.add_field(name=_("Unicode Emojis "), value=str(unicode_emoji))
                if len(em.fields) > 0:
                    await ctx.send(embed=em)
            else:
                msg = _("Emojireact settings for ") + guild.name + "\n"
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
            msg = _("Okay, I will not react to messages " "containing unicode emojis!")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).unicode.set(True)
            msg = _("Okay, I will react to messages " "containing unicode emojis!")
            await ctx.send(msg)

    @emojireact.command(name="guild")
    async def _guild(self, ctx):
        """Toggle guild emoji reactions"""
        if await self.config.guild(ctx.guild).guild():
            await self.config.guild(ctx.guild).guild.set(False)
            msg = _("Okay, I will not react to messages " "containing server emojis!")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).guild.set(True)
            msg = _("Okay, I will react to messages " "containing server emojis!")
            await ctx.send(msg)

    @emojireact.command(name="all")
    async def _all(self, ctx):
        """Toggle all emoji reactions"""
        guild_emoji = await self.config.guild(ctx.guild).guild()
        unicode_emoji = await self.config.guild(ctx.guild).unicode()
        if guild_emoji or unicode_emoji:
            await self.config.guild(ctx.guild).guild.set(False)
            await self.config.guild(ctx.guild).unicode.set(False)
            msg = _("Okay, I will not react to messages " "containing all emojis!")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).guild.set(True)
            await self.config.guild(ctx.guild).unicode.set(True)
            msg = _("Okay, I will react to messages " "containing all emojis!")
            await ctx.send(msg)

    @commands.Cog.listener()
    async def on_message(self, message):
        channel = message.channel
        emoji_list = []
        if message.guild is None:
            return
        if not channel.permissions_for(message.guild.me).add_reactions:
            return
        if await self.config.guild(message.guild).guild():
            for match in EMOJI.finditer(message.content):
                if match.group(4):
                    emoji_list.append(f"{match.group(2)}:{match.group(3)}:{match.group(4)}")
                else:
                    emoji_list.append(discord.utils.get(self.bot.emojis, name=match.group(3)))
        if await self.config.guild(message.guild).unicode():
            for emoji in UNICODE_RE.findall(message.content):
                emoji_list.append(str(emoji))
        if emoji_list == []:
            return
        for emoji in emoji_list:
            try:
                await message.add_reaction(emoji)
            except discord.errors.Forbidden:
                return
            except discord.errors.HTTPException:
                continue
