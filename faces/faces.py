import discord
from random import choice
import random
from redbot.core import commands
from . import faceslist

class Faces(getattr(commands, "Cog", object)):
    """
        Generate fun/random unicode faces courtesy of the CIA files
    """

    def __init__(self, bot):
        self.bot = bot
        self.faces = faceslist.faces
    
    @commands.command(pass_context=True, aliases=["japaneseface"])
    async def face(self, ctx, number=None):
        """Japanese Faces at random courtesy of the CIA"""
        if number is None:
            await ctx.send(choice(self.faces))
            return
        if "<@" in str(number):
            random.seed(number.strip("<@!>"))
            userface = self.faces[random.randint(0, len(self.faces))]
            await ctx.send(userface)
            return
        if number.isdigit():
            if int(number) <= len(self.faces):
                await ctx.send(self.faces[int(number)-1])
                return
            else:
                await ctx.send("That number is too large, pick less than {}!"
                                   .format(len(self.faces)))
                return
        if not number.isdigit() and "<@!" not in number:
            await ctx.send(self.faces[len(number)])
