from random import choice
from typing import List

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Rekt", __file__)

rektlist: List[str] = [
    _("☑ Rekt"),
    _("☑ Tyrannosaurus Rekt"),
    _("☑ sudo apt-get Rekt"),
    _("☑ e=mRekt²"),
    _("☑ Rekt and Morty"),
    _("☑ Really Rekt"),
    _("☑ Cash4Rekt.com"),
    _("☑ Grapes of Rekt"),
    _("☑ Ship Rekt"),
    _("☑ Rektavoir Dogs"),
    _("☑ Raiders of the Rekt Ark _("),
    _("☑ Indiana Jones and the Temple of Rekt"),
    _("☑ Rekt markes the spot"),
    _("☑ Caught rekt handed"),
    _("☑ The Rekt Side Story"),
    _("☑ Singin' In The Rekt"),
    _("☑ Painting The Roses Rekt"),
    _("☑ Rekt Van Winkle"),
    _("☑ Parks and Rekt"),
    _("☑ Lord of the Rekts: The Reking of the King"),
    _("☑ Star Trekt"),
    _("☑ The Rekt Prince of Bel-Air"),
    _("☑ A Game of Rekt"),
    _("☑ Rektflix"),
    _("☑ Rekt it like it's hot"),
    _("☑ RektBox 360"),
    _("☑ The Rekt-men"),
    _("☑ School Of Rekt"),
    _("☑ I am Fire, I am Rekt"),
    _("☑ Rekt and Roll"),
    _("☑ Professor Rekt"),
    _("☑ Catcher in the Rekt"),
    _("☑ Rekt-22"),
    _("☑ Harry Potter: The Half-Rekt Prince"),
    _("☑ Great Rektspectations"),
    _("☑ Paper Scissors Rekt"),
    _("☑ RektCraft"),
    _("☑ Grand Rekt Auto V"),
    _("☑ Call of Rekt: Modern Reking 2"),
    _("☑ Legend Of Zelda: Ocarina of Rekt"),
    _("☑ Rekt It Ralph"),
    _("☑ Left 4 Rekt"),
    _("☑ www.rekkit.com"),
    _("☑ Pokemon: Fire Rekt"),
    _("☑ The Shawshank Rektemption"),
    _("☑ The Rektfather"),
    _("☑ The Rekt Knight"),
    _("☑ Fiddler on the Rekt"),
    _("☑ The Rekt Files"),
    _("☑ The Good, the Bad, and The Rekt"),
    _("☑ Forrekt Gump"),
    _("☑ The Silence of the Rekts"),
    _("☑ The Green Rekt"),
    _("☑ Gladirekt"),
    _("☑ Spirekted Away"),
    _("☑ Terminator 2: Rektment Day"),
    _("☑ The Rekt Knight Rises"),
    _("☑ The Rekt King"),
    _("☑ REKT-E"),
    _("☑ Citizen Rekt"),
    _("☑ Requiem for a Rekt"),
    _("☑ REKT TO REKT ass to ass"),
    _("☑ Star Wars: Episode VI - Return of the Rekt"),
    _("☑ Braverekt"),
    _("☑ Batrekt Begins"),
    _("☑ 2001: A Rekt Odyssey"),
    _("☑ The Wolf of Rekt Street"),
    _("☑ Rekt's Labyrinth"),
    _("☑ 12 Years a Rekt"),
    _("☑ Gravirekt"),
    _("☑ Finding Rekt"),
    _("☑ The Arekters"),
    _("☑ There Will Be Rekt"),
    _("☑ Christopher Rektellston"),
    _("☑ Hachi: A Rekt Tale"),
    _("☑ The Rekt Ultimatum"),
    _("☑ Shrekt"),
    _("☑ Rektal Exam"),
    _("☑ Rektium for a Dream"),
    _("☑ www.Trekt.tv"),
    _("☑ Erektile Dysfunction"),
    _("☑ Jesus, stepping out the grave: 'Get ressurekt'"),
]


@cog_i18n(_)
class Rekt(commands.Cog):
    """
    Post embed with random rekt messages
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
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

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def rekt(self, ctx: commands.Context):
        """Post embed with random rekt messages"""
        rektemoji = ["\u2611", "\U0001F1F7", "\U0001F1EA", "\U0001F1F0", "\U0001F1F9"]
        embed = discord.Embed(colour=discord.Colour.blue())
        embed.add_field(name=_("NOT REKT"), value=_("⬜ Not Rekt"), inline=True)
        message = "\n".join(choice(rektlist) for line in range(10))
        if message != "":
            embed.add_field(name=_("REKT"), value=message, inline=True)
        embed.set_author(name=_("Are you REKT?"))
        msg = await ctx.send(embed=embed)
        for emoji in rektemoji:
            await msg.add_reaction(emoji)
