from typing import Tuple

import discord
from redbot.core import commands


class Stamp:
    async def convert(self, ctx: commands.Context, argument: str) -> Tuple[int, int]:
        if len(argument) > 2:
            raise commands.BadArgument("Your stamp must be 2 characters max.")
        x, y = argument[0].upper(), argument[1]
        letters = {
            "B": 0,
            "I": 1,
            "N": 2,
            "G": 3,
            "O": 4,
        }
        return [int(letters[x]), int(y) - 1]
