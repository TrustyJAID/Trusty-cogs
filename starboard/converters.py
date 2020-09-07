from .starboard_entry import StarboardEntry

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core.i18n import Translator
from redbot.core import commands

_ = Translator("Starboard", __file__)


class StarboardExists(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> StarboardEntry:
        cog = ctx.cog
        guild = ctx.guild
        if guild.id not in cog.starboards:
            raise BadArgument(_("There are no starboards setup on this server!"))
        try:
            starboard = cog.starboards[guild.id][argument.lower()]
        except KeyError:
            raise BadArgument(_("There is no starboard named {name}").format(name=argument))
        return starboard
