import random
from random import choice, sample
from typing import Optional

import discord
from redbot.core import commands

from . import tarot_cards


class TarotReading(commands.Cog):
    """
    Post information about tarot cards and readings
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.tarot_cards = tarot_cards.card_list

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

    def get_colour(self) -> int:
        colour = "".join([choice("0123456789ABCDEF") for x in range(6)])
        return int(colour, 16)

    @commands.group()
    async def tarot(self, ctx: commands.Context) -> None:
        """Receive a tarot reading"""
        pass

    @tarot.command(name="life")
    async def _life(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """Unique reading based on your discord user ID. Doesn't change."""
        card_meaning = ["Past", "Present", "Future", "Potential", "Reason"]
        if user is None:
            user = ctx.message.author
        userseed = user.id

        random.seed(int(userseed))
        cards = []
        cards = sample((range(1, 78)), 5)

        embed = discord.Embed(
            title="Tarot reading for {}".format(user.display_name),
            colour=discord.Colour(value=self.get_colour()),
        )
        embed.set_thumbnail(url=self.tarot_cards[str(cards[-1])]["card_img"])
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        number = 0
        for card in cards:
            embed.add_field(
                name="{0}: {1}".format(
                    card_meaning[number], self.tarot_cards[str(card)]["card_name"]
                ),
                value=self.tarot_cards[str(card)]["card_meaning"],
            )
            number += 1
        await ctx.send(embed=embed)

    @tarot.command(name="reading")
    async def _reading(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """Unique reading as of this very moment."""
        card_meaning = ["Past", "Present", "Future", "Potential", "Reason"]
        if user is None:
            user = ctx.message.author

        cards = []
        cards = sample((range(1, 78)), 5)

        embed = discord.Embed(
            title="Tarot reading for {}".format(user.display_name),
            colour=discord.Colour(value=self.get_colour()),
        )
        embed.set_thumbnail(url=self.tarot_cards[str(cards[-1])]["card_img"])
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        number = 0
        for card in cards:
            embed.add_field(
                name="{0}: {1}".format(
                    card_meaning[number], self.tarot_cards[str(card)]["card_name"]
                ),
                value=self.tarot_cards[str(card)]["card_meaning"],
            )
            number += 1
        await ctx.send(embed=embed)

    @tarot.command(name="card")
    async def _card(self, ctx: commands.Context, *, msg: Optional[str] = None) -> None:
        """Random card or choose a card based on number or name."""
        user = ctx.message.author
        # msg = message.content
        card = None

        if msg is None:
            card = self.tarot_cards[str(random.randint(1, 78))]

        elif msg.isdigit() and int(msg) > 0 and int(msg) < 79:
            card = self.tarot_cards[str(msg)]

        elif not msg.isdigit():
            for cards in self.tarot_cards:
                if msg.lower() in self.tarot_cards[cards]["card_name"].lower():
                    card = self.tarot_cards[cards]
            if card is None:
                await ctx.send("That card does not exist!")
                return

        embed = discord.Embed(
            title=card["card_name"],
            description=card["card_meaning"],
            colour=discord.Colour(value=self.get_colour()),
            url=card["card_url"],
        )
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        embed.set_image(url=card["card_img"])
        await ctx.send(embed=embed)
