import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_list

from .game import CAHGame, CardSet

log = logging.getLogger("red.trusty-cogs.cah")


class CardSetTransformer(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> CardSet:
        card_sets = ctx.bot.get_cog("CardsAgainstHumanity").card_sets
        white_cards = []
        black_cards = []
        official = False
        log.info(f"{argument} card set searching")
        if argument.lower() == "official":
            official = True
            for cardset in card_sets.values():
                if not cardset.official:
                    continue
                white_cards.extend(cardset.white)
                black_cards.extend(cardset.black)
            return CardSet(
                name="Official", white=white_cards, black=black_cards, official=official
            )
        elif argument.lower() == "all":
            for cardset in card_sets.values():
                white_cards.extend(cardset.white)
                black_cards.extend(cardset.black)
            return CardSet(name="all", white=white_cards, black=black_cards, official=official)
        elif argument.lower() in card_sets:
            return card_sets[argument.lower()]
        elif "|" in argument:
            for possible_set in argument.split("|"):
                if possible_set.lower() in card_sets:
                    white_cards.extend(card_sets[possible_set.lower()].white)
                    black_cards.extend(card_sets[possible_set.lower()].black)
            return CardSet(name=argument, white=white_cards, black=black_cards, official=official)
        if not white_cards and not black_cards:
            log.info("No car set match found")
            raise commands.BadArgument(
                "No card set matching `{argument}` was found.".format(argument=argument)
            )
        return CardSet(name=argument, white=white_cards, black=black_cards, official=official)

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> CardSet:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        card_sets = interaction.client.get_cog("CardsAgainstHumanity").card_sets
        supplied_sets = []
        new_sets = ""
        for sup in current.split("|"):
            if sup in card_sets:
                supplied_sets.append(sup)
            else:
                new_sets = sup
        choices = [
            discord.app_commands.Choice(name="all", value="all"),
            discord.app_commands.Choice(name="official", value="official"),
        ]
        divider = "|" if supplied_sets else ""
        choices.extend(
            discord.app_commands.Choice(
                name=f"{'|'.join(supplied_sets)}{divider}{s}"[:100],
                value=f"{'|'.join(supplied_sets)}{divider}{s}"[:100],
            )
            for s in card_sets
        )
        return [c for c in choices if current.lower() in c.name.lower()][:25]


class CardsAgainstHumanity(commands.Cog):

    __version__ = "1.0.1"
    __author__ = ["TrustyJAID", "crhallberg", "Cards Against Humanity®️"]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_global(card_sets=[])
        self.card_sets: Dict[str, CardSet] = {}
        self.running_games: Dict[int, CAHGame] = {}

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def download_data(self, url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as infile:
                return await infile.read()

    async def get_font_file(self, path: Path):
        url = "https://github.com/adampash/Lifehacker.me/blob/master/fonts/HelveticaNeue-Bold.ttf?raw=true"
        with path.open("wb") as outfile:
            outfile.write(await self.download_data(url))

    async def get_card_sets(self) -> List[dict]:
        url = "https://raw.githubusercontent.com/crhallberg/json-against-humanity/latest/cah-all-full.json"
        data = json.loads(await self.download_data(url))
        await self.config.card_sets.set(data)
        return data

    async def get_black_card(self, path: Path):
        url = "https://i.imgur.com/OrM8UcC.png"
        with path.open("wb") as outfile:
            outfile.write(await self.download_data(url))

    async def get_white_card(self, path: Path):
        url = "https://i.imgur.com/mlkVIxg.png"
        with path.open("wb") as outfile:
            outfile.write(await self.download_data(url))

    async def cog_load(self):
        # sets_path = cog_data_path(self) / "cards.json"
        font_path = cog_data_path(self) / "HelveticaNeue-Bold.ttf"
        white_path = cog_data_path(self) / "white.png"
        black_path = cog_data_path(self) / "black.png"
        if not os.path.isfile(font_path):
            await self.get_font_file(font_path)
        if not os.path.isfile(white_path):
            await self.get_white_card(white_path)
        if not os.path.isfile(black_path):
            await self.get_black_card(black_path)
        if await self.config.card_sets():
            for cardset in await self.config.card_sets():
                c_set = CardSet.from_json(cardset)
                self.card_sets[c_set.name.lower()] = c_set
        else:
            card_sets = await self.get_card_sets()
            for cardset in card_sets:
                c_set = CardSet.from_json(cardset)
                self.card_sets[c_set.name.lower()] = c_set

    @commands.hybrid_group(name="cah")
    async def cah(self, ctx: commands.Context):
        """Cards Against Humanity®️ commands

        Cards Against Humanity®️ is licened under Creative Commons BY-NC-SA 4.0
        https://creativecommons.org/licenses/by-nc-sa/4.0/
        """
        pass

    @cah.command(name="list")
    async def list_sets(self, ctx: commands.Context):
        """List all the available set names."""
        msg = humanize_list([s.name for s in self.card_sets.values() if s.official])
        await ctx.maybe_send_embed(msg)

    @cah.command(name="start")
    @commands.max_concurrency(1, commands.BucketType.channel)
    @discord.app_commands.describe(
        rounds="The number of rounds you want to play.",
        card_set="The card set(s) you want to use separated by |.",
    )
    async def start_cah(
        self,
        ctx: commands.Context,
        rounds: Optional[int] = 10,
        *,
        card_set: Optional[CardSetTransformer],
    ):
        """
        Start a game of Cards Against Humanity®️

        `[rounds=10]` The number of rounds you wish to play.
        `[card_set]` The name of the card set(s) you want to use.
        By default all official cards are used but you can customize this
        by `|` separating card sets.
        e.g. `[p]cah start 10 CAH Base Set|2012 Holiday Pack`
        """
        cards = card_set
        if card_set is None:
            white_cards = []
            black_cards = []
            for cardset in self.card_sets.values():
                if not cardset.official:
                    continue
                white_cards.extend(cardset.white)
                black_cards.extend(cardset.black)
            cards = CardSet(name="Official", white=white_cards, black=black_cards, official=True)

        game = CAHGame(ctx, cards, rounds or 10)
        self.running_games[ctx.channel.id] = game
        await game.start()
        # del self.running_games[ctx.channel.id]
