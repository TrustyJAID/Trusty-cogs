from __future__ import annotations

from enum import Enum
from io import BytesIO
from typing import List, Optional, Tuple, Union

import discord
from PIL import Image
from redbot.core import commands


class LawVsChaos(Enum):
    lawful = 0
    neutral = 1
    chaotic = 2

    def __str__(self) -> str:
        return self.name.title()

    @property
    def short(self) -> str:
        return self.name[0]

    @classmethod
    def from_name(cls, name: str) -> LawVsChaos:
        for i in cls:
            if i.name == name.lower():
                return i
        raise ValueError


class GoodVsEvil(Enum):
    good = 0
    neutral = 1
    evil = 2

    def __str__(self) -> str:
        return self.name.title()

    @property
    def short(self) -> str:
        return self.name[0]

    @classmethod
    def from_name(cls, name: str) -> GoodVsEvil:
        for i in cls:
            if i.name == name.lower():
                return i
        raise ValueError


class Alignment:
    def __init__(self, law: LawVsChaos, good: GoodVsEvil):
        self.lawful = law
        self.good = good

    @property
    def idx(self) -> Tuple[int, int]:
        return (self.lawful.value, self.good.value)

    @property
    def short(self) -> str:
        return f"{self.lawful.short}{self.good.short}"

    def __str__(self) -> str:
        return f"{self.lawful} {self.good}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Alignment):
            return False
        return self.lawful is other.lawful and self.good is other.good

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    @classmethod
    def from_name(cls, name: str) -> Alignment:
        lawful, good = name.split("_")
        return cls(LawVsChaos.from_name(lawful), GoodVsEvil.from_name(good))


class Stamp:
    async def convert(self, ctx: commands.Context, argument: str) -> List[int]:
        if len(argument) > 2:
            raise commands.BadArgument("Your stamp must be 2 characters max.")
        y = int(argument[1]) - 1
        bingo = await ctx.cog.config.guild(ctx.guild).bingo()
        try:
            x = bingo.index(argument[0].upper())
        except ValueError:
            raise commands.BadArgument(
                f"`{argument[0].upper()}` is not a valid letter in {bingo}."
            )

        return [x, y]


class AlignmentFlags(discord.ext.commands.FlagConverter, case_insensitive=True):
    lawful_good: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="lawful_good",
        aliases=["lg", "lawfulgood"],
        default=None,
        description="Who or what is Lawful Good?",
    )
    lawful_neutral: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="lawful_neutral",
        aliases=["ln", "lawfulneutral"],
        default=None,
        description="Who or what is Lawful Neutral?",
    )
    lawful_evil: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="lawful_evil",
        aliases=["le", "lawfulevil"],
        default=None,
        description="Who or what is Lawful Evil?",
    )
    neutral_good: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="neutral_good",
        aliases=["ng", "neutralgood"],
        default=None,
        description="Who or what is Neutral Good?",
    )
    neutral_neutral: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="neutral_neutral",
        aliases=["nn", "neutralneutral"],
        default=None,
        description="Who or what is Neutral Neutral?",
    )
    neutral_evil: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="neutral_evil",
        aliases=["ne", "neutralevil"],
        default=None,
        description="Who or what is Neutral Evil?",
    )
    chaotic_good: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="chaotic_good",
        aliases=["cg", "chaoticgood"],
        default=None,
        description="Who or what is Chaotic Good?",
    )
    chaotic_neutral: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="chaotic_neutral",
        aliases=["cn", "chaoticneutral"],
        default=None,
        description="Who or what is Chaotic Neutral?",
    )
    chaotic_evil: Optional[Union[discord.Member, str]] = discord.ext.commands.flag(
        name="chaotic_evil",
        aliases=["ce", "chaoticevil"],
        default=None,
        description="Who or what is Chaotic Evil?",
    )

    async def to_table(self):
        table = {}
        for alignment in self:
            align = Alignment.from_name(alignment[0])
            table[align.short] = {"text": None, "image": None, "user_id": None}
            if alignment[1] is None:
                continue

            if isinstance(alignment[1], discord.Member):
                b = BytesIO()
                await alignment[1].display_avatar.save(b)
                image = Image.open(b).convert("RGBA")
                table[align.short]["text"] = alignment[1].display_name
                table[align.short]["image"] = image
                table[align.short]["user_id"] = alignment[1].id
            else:
                table[align.short]["text"] = str(alignment[1])

        return table
