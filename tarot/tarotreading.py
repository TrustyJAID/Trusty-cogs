from __future__ import annotations

import random
import re
from enum import Enum
from typing import List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.utils.views import SimpleMenu

from .tarot_cards import card_list as tarot_cards

log = getLogger("red.trusty-cogs.tarot")


def get_colour() -> discord.Colour:
    # Thanks Sinbad
    return discord.Color.from_hsv(random.random(), 1.0, 0.8)


class TarotMeaning(Enum):
    past = 0
    present = 1
    future = 2
    potential = 3
    reason = 4

    def __str__(self) -> str:
        return self.name.title()


class TarotSuit(Enum):
    trump = 0  # Represents the major arcana
    swords = 1
    spades = 1
    cups = 2
    hearts = 2
    pentacles = 3
    diamonds = 3
    disks = 3
    coins = 3
    wands = 4
    rods = 4
    clubs = 4
    batons = 4

    def __str__(self):
        return self.emoji + " | ".join(i.title() for i in self.aliases)

    @staticmethod
    def re():
        return re.compile(r"|".join(k for k in TarotSuit.__members__.keys()), flags=re.I)

    @property
    def offset(self):
        return self.value * 16

    @property
    def aliases(self) -> List[str]:
        ret = []
        for alias, value in TarotSuit.__members__.items():
            if value is self:
                ret.append(alias)
        return ret

    @classmethod
    def from_name(cls, name: str) -> TarotSuit:
        for alias, value in cls.__members__.items():
            if alias.lower() == name:
                return value
        return cls(0)

    @property
    def emoji(self) -> str:
        return {
            TarotSuit.trump: "\N{PLAYING CARD BLACK JOKER}",
            TarotSuit.wands: "\N{BLACK CLUB SUIT}\N{VARIATION SELECTOR-16}",
            TarotSuit.swords: "\N{BLACK SPADE SUIT}\N{VARIATION SELECTOR-16}",
            TarotSuit.cups: "\N{BLACK HEART SUIT}\N{VARIATION SELECTOR-16}",
            TarotSuit.pentacles: "\N{BLACK DIAMOND SUIT}\N{VARIATION SELECTOR-16}",
        }[self]


class TarotRank(Enum):
    trump = 0
    ace = 1
    two = 2
    three = 3
    four = 4
    five = 5
    six = 6
    seven = 7
    eight = 8
    nine = 9
    ten = 10
    page = 11
    jack = 11
    knave = 11
    knight = 12
    queen = 13
    king = 14

    def __str__(self):
        return " | ".join(i.title() for i in self.aliases)

    @staticmethod
    def re():
        return re.compile(
            r"|".join(rf"{k}|{v.value}" for k, v in TarotRank.__members__.items()), flags=re.I
        )

    @property
    def aliases(self) -> List[str]:
        ret = []
        for alias, value in TarotRank.__members__.items():
            if value is self:
                ret.append(alias)
        return ret

    @classmethod
    def from_name(cls, name: str) -> TarotRank:
        for alias, value in cls.__members__.items():
            if alias.lower() == name or str(value.value) == name:
                return value
        return cls(0)


class Arcana(Enum):
    minor = 0
    major = 1

    def __str__(self):
        return f"{self.name.title()} Arcana"

    @classmethod
    def from_name(cls, name: str) -> Arcana:
        for alias, value in cls.__members__.items():
            if alias.lower() == name:
                return value
        return cls(0)


class MajorArcana(Enum):
    fool = 0
    magician = 1
    high_priestess = 2
    empress = 3
    emperor = 4
    heirophant = 5
    lovers = 6
    chariot = 7
    strength = 8
    hermit = 9
    wheel_of_fortune = 10
    justice = 11
    hanged_man = 12
    death = 13
    temperance = 14
    devil = 15
    tower = 16
    star = 17
    moon = 18
    sun = 19
    judgement = 20
    world = 21

    def __str__(self):
        return self.name.replace("_", " ").title()

    @staticmethod
    def re():
        return re.compile(r"|".join(str(v) for v in MajorArcana.__members__.values()), flags=re.I)

    @classmethod
    def from_name(cls, name: str) -> MajorArcana:
        for alias, value in cls.__members__.items():
            if alias.lower() == name:
                return value
        return MajorArcana.fool


class TarotCard:
    def __init__(
        self,
        id: int,
        card_meaning: str,
        card_url: str,
        card_img: str,
        rank: Union[MajorArcana, TarotRank],
        suit: TarotSuit,
        arcana: Arcana,
    ):
        self.id: int = id
        self.card_meaning: str = card_meaning
        self.card_url: str = card_url
        self.card_img: str = card_img
        self.rank = rank
        self.suit = suit
        self.arcana = arcana

    @property
    def emoji(self):
        if self.arcana is not Arcana.major:
            return chr(0x1F090 + self.rank.value + self.suit.offset)
        return chr(0x1F0E0 + self.rank.value)

    @property
    def card_name(self):
        if self.arcana is Arcana.minor:
            return f"{self.rank} of {self.suit}"
        return f"{self.rank} {self.suit.emoji}"

    @staticmethod
    def re():
        return re.compile(
            rf"(?P<rank>{TarotRank.re().pattern})\s(of)?\s?(?P<suit>{TarotSuit.re().pattern})|(?P<arcana>{MajorArcana.re().pattern})",
            flags=re.I,
        )

    def get_card_img(self, deck: Optional[str]):
        if deck is None:
            return self.card_img
        url = "https://gfx.tarot.com/images/site/decks/{deck}/full_size/{card_number}.jpg"
        card_number = 0
        offsets = {
            TarotSuit.wands: 0,
            TarotSuit.cups: 1,
            TarotSuit.swords: 2,
            TarotSuit.pentacles: 3,
        }
        if self.arcana is Arcana.major:
            card_number = self.rank.value
        else:
            card_number = 21 + self.rank.value + offsets[self.suit] * 14
        return url.format(deck=deck, card_number=card_number)

    @classmethod
    def from_json(cls, id: int, data: dict) -> TarotCard:
        arcana = Arcana.from_name(data["arcana"])
        if arcana is Arcana.major:
            rank = MajorArcana.from_name(data["rank"])
        else:
            rank = TarotRank.from_name(data["rank"])
        suit = TarotSuit.from_name(data["suit"])
        return cls(
            id=id,
            card_meaning=data["card_meaning"],
            card_url=data["card_url"],
            card_img=data["card_img"],
            rank=rank,
            suit=suit,
            arcana=arcana,
        )

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Optional[TarotCard]:
        match = TarotCard.re().match(argument)
        log.debug(match)
        if match and not argument.isdigit():
            suit_str = match.group("suit")
            rank_str = match.group("rank")
            suit = None
            rank = None
            if suit_str:
                suit = TarotSuit.from_name(suit_str)
            if rank_str:
                rank = TarotRank.from_name(rank_str)
            arcana = match.group("arcana")
            for _id, card in tarot_cards.items():
                if arcana and arcana.lower() == card["card_name"].lower():
                    return TarotCard.from_json(id=int(_id), data=card)
                elif suit and rank:
                    if suit.name == card["suit"] and rank.name == card["rank"]:
                        return TarotCard.from_json(id=int(_id), data=card)
        else:
            try:
                card = tarot_cards[str(argument)]
                return TarotCard.from_json(id=int(argument), data=card)
            except KeyError:
                raise commands.BadArgument(f"`{argument}` is not an available Tarot card.")
        return None

    def embed(self, deck: Optional[str] = None):
        return (
            discord.Embed(
                title=self.card_name,
                description=self.card_meaning,
                colour=get_colour(),
                url=self.card_url,
            )
            .set_image(url=self.get_card_img(deck))
            .add_field(name="Arcana", value=str(self.arcana))
        )


class TarotReading(commands.Cog):
    """
    Post information about tarot cards and readings
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.3.0"

    def __init__(self, bot):
        self.bot = bot
        super().__init__()
        self.tarot_cards = {
            num: TarotCard.from_json(id=int(num), data=data) for num, data in tarot_cards.items()
        }
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_guild(deck=None)
        self.config.register_global(deck=None)

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

    async def get_deck(self, ctx: commands.Context) -> str:
        if ctx.guild:
            deck = await self.config.guild(ctx.guild).deck()
            if deck:
                return deck
        return await self.config.deck()

    @commands.hybrid_group()
    async def tarot(self, ctx: commands.Context) -> None:
        """Receive a tarot reading"""
        pass

    @tarot.group(name="set", with_app_command=False)
    async def tarot_set(self, ctx: commands.Context) -> None:
        """Set commands for tarot"""
        pass

    @tarot_set.command(name="deck")
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def _set_deck(self, ctx: commands.Context, deck_name: Optional[str] = None) -> None:
        """
        Set which deck to use from https://www.tarot.com/tarot/decks

        `deck_name` must be the name in the URL for the deck you want to use.
        If not provided will revert to the default to the Rider–Waite Tarot Deck.
        """
        if deck_name is None:
            await self.config.guild(ctx.guild).deck.clear()
        else:
            await self.config.guild(ctx.guild).deck.set(deck_name)
        card = random.choice(list(self.tarot_cards.values()))
        em = card.embed(deck_name)
        await ctx.send(
            "Set this server's tarot deck to {deck_name}.".format(
                deck_name=deck_name or "Rider–Waite"
            ),
            embed=em,
        )

    @tarot_set.command(name="globaldeck")
    @commands.is_owner()
    async def _set_global_deck(
        self, ctx: commands.Context, deck_name: Optional[str] = None
    ) -> None:
        """
        Set which deck to use from https://www.tarot.com/tarot/decks

        This sets it for every server the bot is in by default. Servers
        can specify their own deck to use via `[p]tarot set deck`

        `deck_name` must be the name in the URL for the deck you want to use.
        If not provided will revert to the default to the Rider–Waite Tarot Deck.
        """
        if deck_name is None:
            await self.config.deck.clear()
        else:
            await self.config.deck.set(deck_name)
        card = random.choice(list(self.tarot_cards.values()))
        em = card.embed(deck_name)
        await ctx.send(
            "Set the global tarot deck to {deck_name}.".format(
                deck_name=deck_name or "Rider–Waite"
            ),
            embed=em,
        )

    async def tarot_reading(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User], cards: List[int]
    ):
        embed = discord.Embed(
            title="Tarot reading for {}".format(user.display_name),
            colour=get_colour(),
            url=self.tarot_cards[str(cards[-1])].card_url,
        )
        deck = await self.get_deck(ctx)
        embed.set_thumbnail(url=self.tarot_cards[str(cards[-1])].get_card_img(deck))
        embed.timestamp = ctx.message.created_at
        embed.set_author(name=user.name, icon_url=user.display_avatar)
        for meaning in TarotMeaning:
            try:
                card_id = cards[meaning.value]
                card = self.tarot_cards[str(card_id)]
            except IndexError:
                # incase this gets passed an incorrect number of cards
                continue
            embed.add_field(
                name="{meaning}: {name}".format(meaning=str(meaning), name=card.card_name),
                value=f"__{card.arcana}__\n{card.card_meaning}",
            )
        embeds = []
        for card_number in cards:
            card = self.tarot_cards[str(card_number)]
            em = embed.copy()
            em.set_image(url=card.get_card_img(deck))
            embeds.append(em)
        await ctx.send(embeds=embeds)

    @tarot.command(name="life")
    async def _life(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Unique reading based on your discord user ID. Doesn't change.

        `[user]` Optional user who you want to see a life tarot reading for.
        If no user is provided this will run for the user who is running the command.
        """
        member = user or ctx.message.author
        state = random.getstate()
        random.seed(int(member.id))
        cards = []
        cards = random.sample((range(1, 78)), 5)
        random.setstate(state)
        await self.tarot_reading(ctx, member, cards)

    @tarot.command(name="reading")
    async def _reading(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Unique reading as of this very moment.

        `[user]` Optional user you want to view a tarot reading for.
        If no user is provided this will run for the user who is running the command.
        """
        member = user or ctx.message.author
        cards = []
        cards = random.sample((range(1, 78)), 5)
        await self.tarot_reading(ctx, member, cards)

    @tarot.command(name="card")
    async def _card(self, ctx: commands.Context, *, tarot_card: Optional[TarotCard]) -> None:
        """
        Random card or choose a card based on number or name.

        `[tarot_card]` Is the full name of any tarot card or a number corresponding to specific cards.
        If this doesn't match any cards number or name then a random one will be displayed instead.
        """
        user = ctx.message.author
        # msg = message.content
        card = None

        if tarot_card is None:
            card = self.tarot_cards[str(random.randint(1, 78))]

        else:
            card = tarot_card

        cards = []
        deck = await self.get_deck(ctx)
        for c in self.tarot_cards.values():
            embed = c.embed(deck)
            embed.timestamp = ctx.message.created_at
            embed.set_author(name=user.name, icon_url=user.display_avatar)
            cards.append(embed)
        menu = SimpleMenu(cards, page_start=card.id - 1, use_select_menu=True)
        options = [
            discord.SelectOption(label=c.card_name, description=str(c.id), value=str(c.id - 1))
            for c in self.tarot_cards.values()
        ]
        menu.select_options = options
        await menu.start(ctx)

    @_card.autocomplete("tarot_card")
    async def tarot_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        for _id, card in self.tarot_cards.items():
            choices.append(discord.app_commands.Choice(name=card.card_name, value=_id))
        return [c for c in choices if current.lower() in c.name.lower()][:25]
