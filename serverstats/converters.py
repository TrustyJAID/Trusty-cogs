import logging
import re
from typing import List, Union

import discord
from unidecode import unidecode

from rapidfuzz import process
from discord.ext.commands.converter import IDConverter, _get_from_guilds
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.i18n import Translator

_ = Translator("ServerStats", __file__)
log = logging.getLogger("red.trusty-cogs.ServerStats")


class FuzzyMember(IDConverter):
    """
    This will accept user ID's, mentions, and perform a fuzzy search for
    members within the guild and return a list of member objects
    matching partial names

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: commands.Context, argument: str) -> List[discord.Member]:
        bot = ctx.bot
        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]+)>$", argument)
        guild = ctx.guild
        result = []
        if match is None:
            # Not a mention
            if guild:
                for m in process.extract(
                    argument,
                    {m: unidecode(m.name) for m in guild.members},
                    limit=None,
                    score_cutoff=75,
                ):
                    result.append(m[2])
                for m in process.extract(
                    argument,
                    {m: unidecode(m.nick) for m in guild.members if m.nick and m not in result},
                    limit=None,
                    score_cutoff=75,
                ):
                    result.append(m[2])
        else:
            user_id = int(match.group(1))
            if guild:
                result.append(guild.get_member(user_id))
            else:
                result.append(_get_from_guilds(bot, "get_member", user_id))

        if not result or result == [None]:
            raise BadArgument('Member "{}" not found'.format(argument))

        return result


class GuildConverter(IDConverter):
    """
    This is a guild converter for fuzzy guild names which is used throughout
    this cog to search for guilds by part of their name and will also
    accept guild ID's

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Guild:
        bot = ctx.bot
        match = self._get_id_match(argument)
        result = None
        if not await bot.is_owner(ctx.author):
            # Don't need to be snooping other guilds unless we're
            # the bot owner
            raise BadArgument(_("That option is only available for the bot owner."))
        if match is None:
            # Not a mention
            for g in process.extractOne(argument, {g: unidecode(g.name) for g in bot.guilds}):
                result = g
        else:
            guild_id = int(match.group(1))
            result = bot.get_guild(guild_id)

        if result is None:
            raise BadArgument('Guild "{}" not found'.format(argument))

        return result


class MultiGuildConverter(IDConverter):
    """
    This is a guild converter for fuzzy guild names which is used throughout
    this cog to search for guilds by part of their name and will also
    accept guild ID's

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: commands.Context, argument: str) -> List[discord.Guild]:
        bot = ctx.bot
        match = self._get_id_match(argument)
        result = []
        if not await bot.is_owner(ctx.author):
            # Don't need to be snooping other guilds unless we're
            # the bot owner
            raise BadArgument(_("That option is only available for the bot owner."))
        if not match:
            # Not a mention
            for g in process.extract(
                argument, {g: unidecode(g.name) for g in bot.guilds}, limit=None, score_cutoff=75
            ):
                result.append(g[2])
        else:
            guild_id = int(match.group(1))
            guild = bot.get_guild(guild_id)
            if not guild:
                raise BadArgument('Guild "{}" not found'.format(argument))
            result.append(guild)

        if not result:
            raise BadArgument('Guild "{}" not found'.format(argument))

        return result


class ChannelConverter(IDConverter):
    """
    This is to convert ID's from a category, voice, or text channel via ID's or names
    """

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.TextChannel, discord.CategoryChannel, discord.VoiceChannel]:
        match = self._get_id_match(argument) or re.match(r"<#([0-9]+)>$", argument)
        result = None
        guild = ctx.guild

        if match is None:
            # not a mention
            result = discord.utils.get(guild.channels, name=argument)

        else:
            channel_id = int(match.group(1))
            result = guild.get_channel(channel_id)

        if not result:
            raise BadArgument(f"Channel `{argument}` not found")
        return result
