import re
import random
from random import choice, sample
from typing import Optional
from dataclasses import dataclass

import discord
from redbot.core import commands

from . import tarot_cards


@dataclass
class TarotCard:
    id: int
    card_meaning: str
    card_name: str
    card_url: str
    card_img: str


TAROT_CARDS = {num: TarotCard(id=num, **data) for num, data in tarot_cards.card_list.items()}
TAROT_RE = re.compile(r"|".join(t.card_name for _id, t in TAROT_CARDS.items()), flags=re.I)


class TarotConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Optional[TarotCard]:
        if find := TAROT_RE.match(argument):
            card_name = find.group(0)
            for card in TAROT_CARDS.values():
                if card_name.lower() == card.card_name.lower():
                    return card
        else:
            try:
                return TAROT_CARDS[str(argument)]
            except KeyError:
                raise commands.BadArgument("`{argument}` is not an available Tarot card.")
        return None


class TarotReading(commands.Cog):
    """
    Post information about tarot cards and readings
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.1.1"

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

    def get_colour(self) -> int:
        colour = "".join([choice("0123456789ABCDEF") for x in range(6)])
        return int(colour, 16)

    @commands.group()
    async def tarot(self, ctx: commands.Context) -> None:
        """Receive a tarot reading"""
        pass

    @tarot.command(name="life")
    async def _life(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Unique reading based on your discord user ID. Doesn't change.

        `[user]` Optional user who you want to see a life tarot reading for.
        If no user is provided this will run for the user who is running the command.
        """
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
        embed.set_thumbnail(url=TAROT_CARDS[str(cards[-1])].card_img)
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        number = 0
        for card in cards:
            embed.add_field(
                name="{0}: {1}".format(card_meaning[number], TAROT_CARDS[str(card)].card_name),
                value=TAROT_CARDS[str(card)].card_meaning,
            )
            number += 1
        await ctx.send(embed=embed)

    @tarot.command(name="reading")
    async def _reading(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Unique reading as of this very moment.

        `[user]` Optional user you want to view a tarot reading for.
        If no user is provided this will run for the user who is running the command.
        """
        card_meaning = ["Past", "Present", "Future", "Potential", "Reason"]
        if user is None:
            user = ctx.message.author

        cards = []
        cards = sample((range(1, 78)), 5)

        embed = discord.Embed(
            title="Tarot reading for {}".format(user.display_name),
            colour=discord.Colour(value=self.get_colour()),
        )
        embed.set_thumbnail(url=TAROT_CARDS[str(cards[-1])].card_img)
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        number = 0
        for card in cards:
            embed.add_field(
                name="{0}: {1}".format(card_meaning[number], TAROT_CARDS[str(card)].card_name),
                value=TAROT_CARDS[str(card)].card_meaning,
            )
            number += 1
        await ctx.send(embed=embed)

    @tarot.command(name="card")
    async def _card(
        self, ctx: commands.Context, *, tarot_card: Optional[TarotConverter] = None
    ) -> None:
        """
        Random card or choose a card based on number or name.

        `[tarot_card]` Is the full name of any tarot card or a number corresponding to specific cards.
        If this doesn't match any cards number or name then a random one will be displayed instead.
        """
        user = ctx.message.author
        # msg = message.content
        card = None

        if tarot_card is None:
            card = TAROT_CARDS[str(random.randint(1, 78))]

        else:
            card = tarot_card

        embed = discord.Embed(
            title=card.card_name,
            description=card.card_meaning,
            colour=discord.Colour(value=self.get_colour()),
            url=card.card_url,
        )
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.avatar_url)
        embed.set_image(url=card.card_img)
        await ctx.send(embed=embed)
