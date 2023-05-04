from typing import List

from redbot.core import commands


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
