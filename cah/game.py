from __future__ import annotations

import asyncio
import functools
import os
import random
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

import discord
from PIL import Image, ImageDraw, ImageFont
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import escape, humanize_list, pagify

log = getLogger("red.trusty-cogs.cah")


class CAHException(Exception):
    pass


class GameAlreadyRunning(CAHException):
    pass


class TooManyPlayers(CAHException):
    pass


class Card(NamedTuple):
    # https://crhallberg.com/cah/
    text: str
    pack: int
    set_name: str
    pick: Optional[int] = None

    def __str__(self):
        return self.text

    async def file(self, path: Path) -> Optional[discord.File]:
        try:
            img = await self.image(path)
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Error generating image")
            return None
        file = discord.File(img)

        return file

    @property
    def file_name(self) -> str:
        return NotImplemented

    @property
    def fill(self) -> Tuple[int, int, int, int]:
        return NotImplemented

    async def image(self, path: Path) -> BytesIO:
        loop = asyncio.get_running_loop()
        task = functools.partial(self._image, path=path)
        card = await loop.run_in_executor(None, task)
        temp = BytesIO()
        card.save(temp, format="webp")
        temp.name = "card.webp"
        temp.seek(0)
        return temp

    def _image(self, path: Path) -> Image.Image:
        with Image.open(path / self.file_name) as card:
            card = card.convert("RGBA")
        fill = self.fill
        font_size = 30 - 1 * (len(self.text) // 60)
        font_width = int((card.width - 50) / font_size) * 2
        font1 = ImageFont.truetype(str(path / "HelveticaNeue-Bold.ttf"), font_size)
        font2_size = 20 - 1 * (len(self.set_name) // 15)
        font2_width = int((card.width - 125) / font2_size) * 2
        font2 = ImageFont.truetype(str(path / "HelveticaNeue-Bold.ttf"), font2_size)
        font3 = ImageFont.truetype(str(path / "HelveticaNeue-Bold.ttf"), 15)
        # font1, font2, font3 = None, None, None

        draw = ImageDraw.Draw(card)
        margin = 25
        offset = 25
        set_offset = 490
        if isinstance(self, BlackCard):
            text = self.underscore
        else:
            text = self.text
        for line in textwrap.wrap(text, width=font_width):
            draw.text((margin, offset), line, fill=fill, font=font1)
            offset += font1.getbbox(line)[3] - font1.getbbox(line)[1]
        for line in textwrap.wrap(self.set_name, width=font2_width):
            draw.text((100, set_offset), line, fill=fill, font=font2)
            set_offset += font2.getbbox(line)[3] - font2.getbbox(line)[1]
        if self.pick:
            draw.text((35, 462), "Pick", fill=fill, font=font3)
            width_left, height_top, width_right, height_bottom = font3.getbbox("Pick")
            height_start = height_bottom - height_top
            width_start = width_right - width_left
            size = height_start + 4
            x, y = (40, 452)
            position = (
                x + width_start,
                y + height_start,
                x + width_start + size,
                y + height_start + size,
            )
            draw.ellipse(position, fill=fill)
            draw.text(
                (x + width_start + 4, y + height_start - 2),
                str(self.pick),
                fill=(0, 0, 0, 255),
                font=font3,
            )
        return card


class WhiteCard(Card):
    @property
    def file_name(self):
        return "white.png"

    @property
    def fill(self) -> Tuple[int, int, int, int]:
        return (0, 0, 0, 255)


class BlackCard(Card):
    @property
    def file_name(self):
        return "black.png"

    @property
    def fill(self) -> Tuple[int, int, int, int]:
        return (255, 255, 255, 255)

    def __str__(self):
        return escape(self.underscore, formatting=True)

    @property
    def underscore(self):
        return self.text.replace("_", "_____________")

    def format(self, white_cards: List[WhiteCard]):
        if "_" in self.text:
            count = 0
            new_str = []
            for char in self.text:
                if char == "_":
                    new_str.append(white_cards[count].text)
                    count += 1
                else:
                    new_str.append(char)
            return "".join(new_str)
        return ",".join(c.text for c in white_cards)


@dataclass
class CardSet:
    name: str
    white: List[WhiteCard]
    black: List[BlackCard]
    official: bool

    @classmethod
    def from_json(cls, data: dict) -> CardSet:
        return cls(
            white=[WhiteCard(**i, set_name=data["name"]) for i in data.pop("white", [])],
            black=[BlackCard(**i, set_name=data["name"]) for i in data.pop("black", [])],
            **data,
        )


class PlayerHand(discord.ui.Select):
    def __init__(self, player: Player):
        self.view: PlayerSelect
        cards_to_pick = player.game.round.black_card.pick
        super().__init__(
            placeholder="Pick your card(s)",
            min_values=cards_to_pick or 1,
            max_values=cards_to_pick or 1,
        )
        self.player = player
        self.cards = {str(i): card for i, card in enumerate(player.hand)}
        for i, card in self.cards.items():
            self.add_option(label=card.text[:80], value=i)

    async def file(self, path: Path, cards: List[WhiteCard]) -> Optional[discord.File]:
        try:
            img = await self.played_cards(path, cards)
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Error generating image")
            return None
        file = discord.File(img)

        return file

    async def played_cards(self, path: Path, cards: List[WhiteCard]) -> BytesIO:
        loop = asyncio.get_running_loop()
        task = functools.partial(self._played_cards, path=path, cards=cards)
        img = await loop.run_in_executor(None, task)
        temp = BytesIO()
        img.save(temp, format="webp")

        temp.name = "played_cards.webp"
        temp.seek(0)
        return temp

    def _played_cards(self, path: Path, cards: List[WhiteCard]) -> Image.Image:
        imgs = [card._image(path) for card in cards]
        template = Image.new("RGBA", (425 * len(cards), 576))
        for i, img in enumerate(imgs):
            template.paste(img, (i * 425, 0), img)
        return template

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = [self.cards[i] for i in self.values]
        for card in cards:
            self.player.hand.remove(card)
            self.player.game.discard_pile.add_white(card)
        self.player.game.draw_cards(self.player, len(cards))
        self.player.game.round.play_cards(self.player, cards)
        img = await self.file(self.player.game.path, cards)
        kwargs: dict = {"ephemeral": True}
        if img is not None:
            kwargs["file"] = img

        await interaction.followup.send(
            f"You played: {humanize_list([str(c) for c in cards])}", **kwargs
        )
        self.view.stop()
        await self.player.game.round.edit()


class PlayerSelect(discord.ui.View):
    def __init__(self, player: Player):
        super().__init__()
        self.player = player
        self._current_hand = PlayerHand(self.player)
        self.add_item(self._current_hand)
        self._never_have_i_ever = NeverHaveIEverButton()
        # self.add_item(self._never_have_i_ever)

    async def edit_hand(self, interaction: discord.Interaction):
        self.remove_item(self._current_hand)
        self._current_hand = PlayerHand(self.player)
        self.add_item(self._current_hand)
        new_image = await self.player.file(self.player.game.path)
        if new_image is not None:
            await interaction.edit_original_response(attachments=[new_image], view=self)
        else:
            msg = "Pick a card\n"
            for number, card in enumerate(self.player.hand):
                msg += f"- {card}\n"
            await interaction.edit_original_response(content=msg)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("Error in Player Hand")


class NeverHaveIEverButton(discord.ui.Button):
    def __init__(self):
        self.view: PlayerSelect
        super().__init__(label="Never Have I Ever", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        modal = NeverHaveIEver(self.view.player)
        await interaction.response.send_modal(modal)
        await modal.wait()
        await self.view.edit_hand(interaction)


class NeverHaveIEver(discord.ui.Modal):
    def __init__(self, player: Player):
        self.player = player
        super().__init__(title="Never Have I Ever")
        max_length = 2000 - (80 + len(humanize_list([c.text for c in self.player.hand])))
        self.explanation = discord.ui.TextInput(
            label="Explain why you don't understand these cards",
            style=discord.TextStyle.paragraph,
            placeholder="I am dumb person who doesn't understand that 'Bees?' is the funniest card in existence.",
            required=True,
            min_length=50,
            max_length=max_length,
        )
        self.cards = {i: card for i, card in enumerate(self.player.hand)}
        options = [discord.SelectOption(label=c.text, value=str(i)) for i, c in self.cards.items()]
        self.chosen_cards = discord.ui.Select(
            max_values=len(self.cards), min_values=1, placeholder="Your Cards", options=options
        )
        self.add_item(self.explanation)
        self.add_item(self.chosen_cards)

    async def file(self, path: Path, cards: List[WhiteCard]) -> Optional[discord.File]:
        try:
            img = await self.discarded_cards(path, cards)
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Error generating image")
            return None
        file = discord.File(img)

        return file

    async def discarded_cards(self, path: Path, cards: List[WhiteCard]) -> BytesIO:
        loop = asyncio.get_running_loop()
        task = functools.partial(self._discarded_cards, path=path, cards=cards)
        img = await loop.run_in_executor(None, task)
        temp = BytesIO()
        img.save(temp, format="webp")

        temp.name = "discarded_cards.webp"
        temp.seek(0)
        return temp

    def _discarded_cards(self, path: Path, cards: List[WhiteCard]) -> Image.Image:
        imgs = [card._image(path) for card in cards]
        height = 580 * min(1 + len(imgs) // 5, 2)
        width = 425 * max(min(5, len(imgs)), 1)
        template = Image.new("RGBA", (width, height))
        for i, img in enumerate(imgs):
            div = divmod(i, 5)
            x = 425 * div[1]
            template.paste(img, (x, (580 * (i // 5))), img)
        return template

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = [self.cards[int(i)] for i in self.chosen_cards.values]
        for card in cards:
            self.player.game.discard_pile.add_white(card)
            self.player.hand.remove(card)
        self.player.game.draw_cards(self.player, len(cards))
        msg = (
            f"{interaction.user.mention} Discarded the following cards, can you believe it?!\n"
            f"{humanize_list([c.text for c in cards])}\n"
            f"{self.explanation.value}"
        )
        img = await self.file(self.player.game.path, cards)
        if img is not None:
            await interaction.followup.send(msg, file=img)
        else:
            await interaction.followup.send(msg)


class Player:
    def __init__(self, user: discord.abc.User, game: CAHGame):
        super().__init__()
        self.user = user
        self.hand: List[WhiteCard] = []
        self.points: int = 0
        self._current_hand: Optional[PlayerHand] = None
        self.game = game

    async def file(self, path: Path) -> Optional[discord.File]:
        try:
            img = await self.make_hand(path)
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Error generating image")
            return None
        file = discord.File(img)

        return file

    async def make_hand(self, path: Path) -> BytesIO:
        loop = asyncio.get_running_loop()
        task = functools.partial(self._make_hand, path)
        img = await loop.run_in_executor(None, task)
        temp = BytesIO()
        img.save(temp, format="webp")

        temp.name = "hand.webp"
        temp.seek(0)
        return temp

    def _make_hand(self, path: Path) -> Image.Image:
        images = [c._image(path) for c in self.hand]
        template = Image.new("RGBA", size=(1800, 700))
        rotation = 9
        for i, img in enumerate(images):
            rotated_image = img.rotate(
                75 - (rotation * i),
                resample=Image.Resampling.BICUBIC,
                expand=True,
            )
            template.paste(rotated_image, (i * 150, 700 - rotated_image.height), rotated_image)
        return template

    @property
    def view(self):
        if not self.hand:
            self.game.draw_cards(self, 10)
        return PlayerSelect(self)

    @classmethod
    def join_game(cls, user: discord.abc.User, game: CAHGame):
        if len(game.white_cards) + len(game.discard_pile.white_cards) < 10:
            raise TooManyPlayers("Too many players and not enough cards")
        ret = cls(user, game)
        return ret

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("Error in Player Hand")


class JoinButton(discord.ui.Button):
    def __init__(self):
        self.view: Round
        super().__init__(label="Join Round", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if interaction.user.id == self.view.game.card_czar.id:
            await interaction.followup.send(
                "You are the Card Czar, you're not allowed to play a card.", ephemeral=True
            )
            return
        if interaction.user.id in self.view.game.players:
            player: Player = self.view.game.players[interaction.user.id]
        else:
            try:
                player: Player = Player.join_game(interaction.user, self.view.game)
            except TooManyPlayers:
                await interaction.followup.send(
                    "Sorry, there's too many players and not enough cards to let you join this game.",
                    ephemeral=True,
                )
                return
            self.view.game.players[interaction.user.id] = player
        view = player.view
        img = await player.file(self.view.game.path)
        if img is None:
            msg = "Pick a card\n"
            for number, card in enumerate(player.hand):
                msg += f"- {card}\n"
            await interaction.followup.send(msg, view=view, ephemeral=True)
        else:
            await interaction.followup.send("Pick a card", file=img, view=view, ephemeral=True)


class StopButton(discord.ui.Button):
    def __init__(self):
        self.view: Round
        super().__init__(label="Stop", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        if (
            interaction.user.id == self.view.game.user_start.id
            or await interaction.client.is_owner(interaction.user)
        ):
            self.view.game.stop()
            self.view.stop()
            await interaction.response.send_message("Stopping game")
            return
        await interaction.response.send_message(
            "You're not allowed to stop this game.", ephemeral=True
        )


class EndRoundButton(discord.ui.Button):
    def __init__(self):
        self.view: Round
        super().__init__(label="End Round", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        if await interaction.client.is_owner(interaction.user):
            self.view.stop()
            await interaction.response.send_message("Stopping Round")
            return
        if interaction.user.id == self.view.game.card_czar.id:
            self.view.stop()
            await interaction.response.send_message("Stopping Round")
            return
        await interaction.response.send_message(
            "You're not allowed to end this round.", ephemeral=True
        )


class DiscardPile:
    def __init__(self):
        self.white_cards: List[WhiteCard] = []
        self.black_cards: List[BlackCard] = []

    def add_white(self, card: WhiteCard):
        self.white_cards.append(card)

    def add_black(self, card: BlackCard):
        self.black_cards.append(card)


class WinnerSelect(discord.ui.Select):
    def __init__(self, cards: Dict[int, List[WhiteCard]]):
        self.view: Winner
        super().__init__(placeholder="Pick Winner")
        self.cards = cards
        for i, player in enumerate(self.cards.items()):
            label = f"{i+1}. {','.join(card.text for card in player[1])}"[:80]
            self.add_option(label=label, value=f"{player[0]}")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = self.cards.get(int(self.values[0]), [])
        winner = interaction.guild.get_member(int(self.values[0]))
        if winner is not None:
            self.view.game.card_czar = winner
            member_str = winner.mention
        else:
            member_str = "Unknown Member"
        img = await self.view.file(self.view.game.path, cards)
        kwargs: dict = {"allowed_mentions": discord.AllowedMentions(users=False)}
        if img is not None:
            kwargs["file"] = img
        await interaction.followup.send(
            f"# {member_str} won with the card(s): {self.view.game.round.black_card.format(cards)}",
            **kwargs,
        )
        self.view.game.players[int(self.values[0])].points += 1
        self.view.picked_winner = True
        self.view.stop()


class Winner(discord.ui.View):
    def __init__(self, game: CAHGame, cards: Dict[int, List[WhiteCard]]):
        self.game: CAHGame = game
        self.cards = cards
        super().__init__(timeout=30)
        self.select = WinnerSelect(self.cards)
        self.add_item(self.select)
        self.picked_winner = False

    async def file(self, path: Path, cards: List[WhiteCard]) -> Optional[discord.File]:
        try:
            img = await self.winning_cards(path, cards)
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Error generating image")
            return None
        file = discord.File(img)

        return file

    async def winning_cards(self, path: Path, cards: List[WhiteCard]) -> BytesIO:
        loop = asyncio.get_running_loop()
        task = functools.partial(self._winning_cards, path=path, cards=cards)
        img = await loop.run_in_executor(None, task)
        temp = BytesIO()
        img.save(temp, format="webp")

        temp.name = "Winner.webp"
        temp.seek(0)
        return temp

    def _winning_cards(self, path: Path, cards: List[WhiteCard]) -> Image.Image:
        imgs = [card._image(path) for card in cards]
        template = Image.new("RGBA", (425 * len(cards), 576))
        for i, img in enumerate(imgs):
            template.paste(img, (i * 425, 0), img)
        return template

    async def on_timeout(self):
        if not self.picked_winner:
            choice = random.choice(list(self.cards.keys()))
            member = self.game.ctx.guild.get_member(int(choice))
            if member is not None:
                self.game.card_czar = member
                member_str = member.mention
            else:
                member_str = "Unknown Member"
            self.game.players[int(choice)].points += 1
            cards = self.cards[choice]
            img = await self.file(self.game.path, cards)
            winner_str = (
                f"# {member_str} won with the card(s): {self.game.round.black_card.format(cards)}"
            )
            await self.game.ctx.send(
                f"Rando Cardrissian has picked a winner for you.\n{winner_str}",
                allowed_mentions=discord.AllowedMentions(users=False),
                file=img,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("Error in Winner")

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.card_czar.id:
            await interaction.response.send_message(
                "You're not allowed to vote for the winner.", ephemeral=True
            )
            return False
        return True


class Round(discord.ui.View):
    def __init__(
        self, game: CAHGame, black_card: BlackCard, end_time: datetime, round_number: int
    ):
        timeout = end_time.timestamp() - datetime.now().timestamp()
        super().__init__(timeout=timeout)
        self.black_card: BlackCard = black_card
        self.game = game
        self.end_time = end_time
        self.round_number = round_number
        self.played_cards: Dict[int, List[WhiteCard]] = {}
        self.join_button: JoinButton = JoinButton()
        self.stop_button: StopButton = StopButton()
        self.stop_round: EndRoundButton = EndRoundButton()
        self.add_item(self.join_button)
        self.add_item(self.stop_button)
        self.add_item(self.stop_round)
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if self.message is not None:
            await self.message.edit(view=None)

    @property
    def timestamp(self):
        return discord.utils.format_dt(self.end_time, "R")

    def play_cards(self, player: Player, cards: List[WhiteCard]):
        self.played_cards[player.user.id] = cards

    def __str__(self):
        players = (
            f"Number of Players: {len(self.played_cards)}" if len(self.played_cards) > 0 else ""
        )
        return (
            f"# Round: {self.round_number+1}\n"
            f"Card Czar: {self.game._card_czar.mention}\n"
            f"> ## {self.black_card}\n\n"
            f"{self.timestamp}\n"
        ) + players

    async def start(self, ctx: commands.Context):
        img = await self.black_card.file(self.game.path)
        self.message = await ctx.send(
            str(self),
            file=img,
            allowed_mentions=discord.AllowedMentions(users=False),
            view=self,
        )

    async def edit(self):
        if self.message is not None:
            await self.message.edit(
                content=str(self),
                allowed_mentions=discord.AllowedMentions(users=False),
            )

    def stop(self) -> None:
        super().stop()
        if self.message is not None:
            loop = asyncio.get_running_loop()
            loop.create_task(self.message.edit(view=None))
        if self.game._wait_task is not None:
            self.game._wait_task.cancel()
        self.game._round_wait.set()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("Error in Round")

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id in self.played_cards and not await interaction.client.is_owner(
            interaction.user
        ):
            await interaction.response.send_message(
                "You've already played this round.", ephemeral=True
            )
            return False
        return True


class CAHGame:
    def __init__(
        self,
        ctx: commands.Context,
        card_set: CardSet,
        number_of_rounds: int = 10,
    ):
        self.number_of_rounds = number_of_rounds
        self.user_start = ctx.author
        self.ctx = ctx
        self.players: Dict[int, Player] = {}
        self.discard_pile: DiscardPile = DiscardPile()
        self.id = os.urandom(5).hex()
        self.card_set = card_set
        self.white_cards: List[WhiteCard] = card_set.white
        self.black_cards: List[BlackCard] = card_set.black
        self._round: Optional[Round] = None
        self.__stopped: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._card_czar: discord.abc.User = ctx.author
        self._round_wait: asyncio.Event = asyncio.Event()
        self.path = cog_data_path(ctx.cog)
        self._wait_task: Optional[asyncio.Task] = None

    @property
    def round(self) -> Round:
        return self._round

    @property
    def card_czar(self) -> discord.abc.User:
        return self._card_czar

    @card_czar.setter
    def card_czar(self, other: Union[discord.Member, discord.User]):
        self._card_czar = other

    async def wait_loop(self, seconds: int):
        await asyncio.sleep(seconds)
        self._round_wait.set()

    async def played_cards_file(self) -> Optional[discord.File]:
        try:
            img = await self.make_played_cards()
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Error generating image")
            return None
        file = discord.File(img)

        return file

    async def make_played_cards(self) -> BytesIO:
        loop = asyncio.get_running_loop()
        img = await loop.run_in_executor(None, self._make_played_cards)
        temp = BytesIO()
        img.save(temp, format="webp")

        temp.name = "played_cards.webp"
        temp.seek(0)
        return temp

    def _make_played_cards(self):
        width = 425 * (self.round.black_card.pick or 1)
        height = 580 * len(self.round.played_cards)
        template = Image.new("RGBA", (width, height))
        for row, cards in enumerate(self.round.played_cards.values()):
            for column, card in enumerate(cards):
                img = card._image(self.path)
                template.paste(img, (column * 425, row * 580), img)

        return template

    async def start(self):
        if self.round is not None:
            raise GameAlreadyRunning("The game is already running.")
        for round_number in range(self.number_of_rounds):
            if self.__stopped.done():
                continue
            if not self.black_cards:
                self.black_cards.extend(self.discard_pile.black_cards)
                self.discard_pile.black_cards = []
            card = random.choice(self.black_cards)
            end_time = datetime.now() + timedelta(seconds=60)
            self._round = Round(self, card, end_time, round_number)
            await self.round.start(self.ctx)
            self._wait_task = asyncio.create_task(self.wait_loop(60))
            await self._round_wait.wait()
            self._round_wait.clear()
            if self.round.played_cards:
                winner = Winner(self, self.round.played_cards)
                choices = ""
                for i, cards in enumerate(self.round.played_cards.values()):
                    choices += f"{i+1}. {self.round.black_card.format(cards)}\n\n"
                msg = (
                    f"# {self.card_czar.mention} is the Card Czar!\n"
                    f"> ## {self.round.black_card}\n\n"
                    f"{choices}"
                )
                img = await self.played_cards_file()
                pages = list(pagify(msg))
                for page in pages[:-1]:
                    await self.ctx.send(page)
                await self.ctx.send(pages[-1], file=img, view=winner)
                await winner.wait()
            else:
                if not self.__stopped.done():
                    await self.ctx.send("No one played that round :cry:")

            self.discard_pile.add_black(card)
            self.black_cards.remove(card)
        await self.end_game()

    async def end_game(self):
        winning_players = []
        points = 0
        if self.players:
            for player in sorted(
                list(self.players.values()), key=lambda x: x.points, reverse=True
            ):
                if player.points >= points:
                    winning_players.append(player)
                    points = player.points
            players = [p.user.mention for p in winning_players]
            await self.ctx.send(
                f"{humanize_list(players)} won with {points} points!",
                allowed_mentions=discord.AllowedMentions(users=False),
            )
        else:
            await self.ctx.send("No one played.")

    def stop(self):
        if not self.__stopped.done():
            self.__stopped.set_result(False)
        self._round_wait.set()

    def draw_cards(self, player: Player, number: int):
        if len(self.white_cards) < number:
            self.white_cards.extend(self.discard_pile.white_cards)
            self.discard_pile.white_cards = []
        for i in range(number):
            card = random.choice(self.white_cards)
            self.white_cards.remove(card)
            player.hand.append(card)
