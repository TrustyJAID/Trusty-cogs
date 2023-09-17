import re
from typing import List, Union

import discord
from discord.ext.commands.converter import IDConverter
from discord.ext.commands.errors import BadArgument
from rapidfuzz import process
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from unidecode import unidecode

_ = Translator("ServerStats", __file__)
log = getLogger("red.trusty-cogs.ServerStats")


class GuildConverter(discord.app_commands.Transformer):
    """
    This is a guild converter for fuzzy guild names which is used throughout
    this cog to search for guilds by part of their name and will also
    accept guild ID's

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> discord.Guild:
        bot = ctx.bot
        result = None
        if not argument.isdigit():
            # Not a mention
            for g in process.extractOne(argument, {g: unidecode(g.name) for g in bot.guilds}):
                result = g
        else:
            guild_id = int(argument)
            result = bot.get_guild(guild_id)

        if result is None:
            raise BadArgument('Guild "{}" not found'.format(argument))
        if ctx.author not in result.members and not await bot.is_owner(ctx.author):
            raise BadArgument(_("That option is only available for the bot owner."))

        return result

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> discord.Guild:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        if await interaction.client.is_owner(interaction.user):
            choices = [
                discord.app_commands.Choice(name=g.name, value=str(g.id))
                for g in interaction.client.guilds
                if current.lower() in g.name.lower()
            ]
        else:
            choices = [
                discord.app_commands.Choice(name=g.name, value=str(g.id))
                for g in interaction.client.guilds
                if current.lower() in g.name.lower()
                and g.get_member(interaction.user.id) is not None
            ]
        return choices[:25]


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


class PermissionConverter(IDConverter):
    """
    This is to convert to specific permission names

    add_reactions
    attach_files
    change_nickname
    connect
    create_instant_invite
    deafen_members
    embed_links
    external_emojis
    manage_channels
    manage_messages
    manage_permissions
    manage_roles
    manage_webhooks
    mention_everyone
    move_members
    mute_members
    priority_speaker
    read_message_history
    read_messages
    send_messages
    send_tts_messages
    speak
    stream
    use_external_emojis
    use_slash_commands
    use_voice_activation
    value
    view_channel
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        valid_perms = dict(discord.Permissions.all_channel())
        error_string = "\n".join(f"- {i}" for i, v in valid_perms.items() if v)
        match = re.match(
            r"|".join(i for i, allowed in valid_perms.items() if allowed), argument, flags=re.I
        )
        if not match:
            raise BadArgument(
                f"Permission `{argument}` not found. Please pick from:\n{error_string}"
            )
        result = match.group(0)

        if not result:
            raise BadArgument(
                f"Permission `{argument}` not found. Please pick from:\n{error_string}"
            )
        return result
