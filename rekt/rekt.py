import discord
from redbot.core import commands
from redbot.core import checks
from random import choice

rektlist = [
            "☑ Rekt",
            "☑ Tyrannosaurus Rekt",
            "☑ sudo apt-get Rekt",
            "☑ e=mRekt²",
            "☑ Rekt and Morty",
            "☑ Really Rekt",
            "☑ Cash4Rekt.com",
            "☑ Grapes of Rekt",
            "☑ Ship Rekt",
            "☑ Rektavoir Dogs",
            "☑ Raiders of the Rekt Ark ",
            "☑ Indiana Jones and the Temple of Rekt",
            "☑ Rekt markes the spot",
            "☑ Caught rekt handed",
            "☑ The Rekt Side Story",
            "☑ Singin' In The Rekt",
            "☑ Painting The Roses Rekt",
            "☑ Rekt Van Winkle",
            "☑ Parks and Rekt",
            "☑ Lord of the Rekts: The Reking of the King",
            "☑ Star Trekt",
            "☑ The Rekt Prince of Bel-Air",
            "☑ A Game of Rekt",
            "☑ Rektflix",
            "☑ Rekt it like it's hot",
            "☑ RektBox 360",
            "☑ The Rekt-men",
            "☑ School Of Rekt",
            "☑ I am Fire, I am Rekt",
            "☑ Rekt and Roll",
            "☑ Professor Rekt",
            "☑ Catcher in the Rekt",
            "☑ Rekt-22",
            "☑ Harry Potter: The Half-Rekt Prince",
            "☑ Great Rektspectations",
            "☑ Paper Scissors Rekt",
            "☑ RektCraft",
            "☑ Grand Rekt Auto V",
            "☑ Call of Rekt: Modern Reking 2",
            "☑ Legend Of Zelda: Ocarina of Rekt",
            "☑ Rekt It Ralph",
            "☑ Left 4 Rekt",
            "☑ www.rekkit.com",
            "☑ Pokemon: Fire Rekt",
            "☑ The Shawshank Rektemption",
            "☑ The Rektfather",
            "☑ The Rekt Knight",
            "☑ Fiddler on the Rekt",
            "☑ The Rekt Files",
            "☑ The Good, the Bad, and The Rekt",
            "☑ Forrekt Gump",
            "☑ The Silence of the Rekts",
            "☑ The Green Rekt",
            "☑ Gladirekt",
            "☑ Spirekted Away",
            "☑ Terminator 2: Rektment Day",
            "☑ The Rekt Knight Rises",
            "☑ The Rekt King",
            "☑ REKT-E",
            "☑ Citizen Rekt",
            "☑ Requiem for a Rekt",
            "☑ REKT TO REKT ass to ass",
            "☑ Star Wars: Episode VI - Return of the Rekt",
            "☑ Braverekt",
            "☑ Batrekt Begins",
            "☑ 2001: A Rekt Odyssey",
            "☑ The Wolf of Rekt Street",
            "☑ Rekt's Labyrinth",
            "☑ 12 Years a Rekt",
            "☑ Gravirekt",
            "☑ Finding Rekt",
            "☑ The Arekters",
            "☑ There Will Be Rekt",
            "☑ Christopher Rektellston",
            "☑ Hachi: A Rekt Tale",
            "☑ The Rekt Ultimatum",
            "☑ Shrekt",
            "☑ Rektal Exam",
            "☑ Rektium for a Dream",
            "☑ www.Trekt.tv",
            "☑ Erektile Dysfunction",
            "☑ Jesus, stepping out the grave: 'Get ressurekt'"
            ]


class Rekt(getattr(commands, "Cog", object)):
    """
        Post embed with random rekt messages
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def rekt(self, ctx):
        """Post embed with random rekt messages"""
        user = ctx.message.author.id
        rektemoji = ["\u2611", "\U0001F1F7", "\U0001F1EA", "\U0001F1F0", "\U0001F1F9"]
        embed = discord.Embed(colour=discord.Colour.blue())
        embed.add_field(name="NOT REKT", value="⬜ Not Rekt", inline=True)
        message = "\n".join(choice(rektlist) for line in range(10))
        if message != "":
            embed.add_field(name="REKT", value=message, inline=True)
        embed.set_author(name="Are you REKT?")
        msg = await ctx.send(embed=embed)
        for emoji in rektemoji:
            await msg.add_reaction(emoji=emoji)
