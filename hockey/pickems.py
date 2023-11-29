from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core.i18n import Translator

from .constants import TEAMS
from .errors import NotAValidTeamError, UserHasVotedError, VotingHasEndedError
from .game import Game, GameState, GameType

_ = Translator("Hockey", __file__)
log = getLogger("red.trusty-cogs.Hockey")


class PickemsButton(discord.ui.Button):
    def __init__(self, team: str, emoji: discord.PartialEmoji, disabled: bool, custom_id: str):
        self.team = team
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=f"{self.team}",
            emoji=emoji,
            disabled=disabled,
            custom_id=custom_id,
        )
        self.disabled = disabled
        self.view: Pickems

    async def respond(self, interaction: discord.Interaction, msg: str):
        locked = False
        guild = interaction.guild
        channel = interaction.channel
        if isinstance(channel, discord.PartialMessageable):
            channel = await guild.fetch_channel(channel.id)

        if isinstance(channel, discord.Thread):
            archived = channel.archived and not channel.locked
            locked = channel.locked
            if archived and channel.permissions_for(guild.me).manage_threads:
                await channel.edit(archived=False)
        if not locked and not self.view.should_edit:
            await interaction.response.send_message(msg, ephemeral=True)
        elif not locked and self.view.should_edit:
            await self.view.update_buttons()
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(msg, ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        time_now = datetime.now(tz=timezone.utc)
        log.verbose("PickemsButton time_now: %s", time_now)
        log.verbose("PickemsButton game_start: %s", self.view.game_start)
        if str(interaction.user.id) in self.view.votes:
            vote = self.view.votes[str(interaction.user.id)]
            emoji = discord.PartialEmoji.from_str(TEAMS[vote]["emoji"])
            if time_now > self.view.game_start:
                await self.respond(
                    interaction,
                    _("Voting has ended! You have voted for {emoji} {team}").format(
                        emoji=emoji, team=vote
                    ),
                )
                self.view.disable_buttons()
                await interaction.message.edit(view=self.view)
                return
            if self.view.votes[str(interaction.user.id)] != self.team:
                self.view.votes[str(interaction.user.id)] = self.team
                await self.respond(
                    interaction,
                    _("You have already voted! Changing vote to: {emoji} {team}").format(
                        emoji=self.emoji, team=self.team
                    ),
                )
                self.view._should_save = True
            else:
                await self.respond(
                    interaction,
                    _("You have already voted for {emoji} {team}!").format(
                        emoji=self.emoji, team=self.team
                    ),
                )
        else:
            if time_now > self.view.game_start:
                await self.respond(
                    interaction,
                    _("Voting has ended, You did not vote on this game!"),
                )
                return
            self.view.votes[str(interaction.user.id)] = self.team
            await self.respond(
                interaction,
                _("Setting your vote to: {emoji} {team}").format(emoji=self.emoji, team=self.team),
            )
            self.view._should_save = True


class Pickems(discord.ui.View):
    """
    Pickems object for handling votes on games for the day
    """

    def __init__(
        self,
        game_id: int,
        game_state: GameState,
        messages: List[str],
        guild: int,
        game_start: datetime,
        home_team: str,
        away_team: str,
        votes: Dict[str, str],
        name: str,
        winner: Optional[str],
        link: Optional[str],
        game_type: GameType,
        should_edit: bool,
    ):
        self.game_id = game_id
        self.game_state = game_state
        self.messages = messages
        self.guild = guild
        self.game_start: datetime = game_start
        self.home_team = home_team
        self.away_team = away_team
        self.votes = votes
        self._raw_home_emoji = TEAMS.get(self.home_team, {}).get("emoji", "\N{HOUSE BUILDING}")
        self.home_emoji = discord.PartialEmoji.from_str(self._raw_home_emoji)
        self._raw_away_emoji = TEAMS.get(self.away_team, {}).get("emoji", "\N{AIRPLANE}")
        self.away_emoji = discord.PartialEmoji.from_str(self._raw_away_emoji)
        self.winner = winner
        self.name = name
        self.link = link
        self._should_save: bool = True
        # Start true so we save instantiated pickems
        self.game_type: GameType = game_type
        super().__init__(timeout=None)
        disabled_buttons = datetime.now(tz=timezone.utc) > self.game_start
        self.home_button = PickemsButton(
            team=self.home_team,
            emoji=self.home_emoji,
            disabled=disabled_buttons,
            custom_id=f"home-{self.game_id}-{self.name}-{self.guild}",
        )
        self.away_button = PickemsButton(
            team=self.away_team,
            emoji=self.away_emoji,
            disabled=disabled_buttons,
            custom_id=f"away-{self.game_id}-{self.name}-{self.guild}",
        )
        self.add_item(self.home_button)
        self.add_item(self.away_button)
        self.should_edit: bool = should_edit

    def __repr__(self):
        return (
            "<Pickems game_id={0.game_id} game_state={0.game_state} "
            "game_type={0.game_type} name={0.name} guild={0.guild} winner={0.winner}>"
        ).format(self)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ):
        log.error("Pickems %s - %s", error, item)

    async def update_buttons(self):
        home_count = sum(1 for i in self.votes.values() if i == self.home_team)
        away_count = sum(1 for i in self.votes.values() if i == self.away_team)
        self.home_button.label = f"{self.home_team} ({home_count})"
        self.away_button.label = f"{self.away_team} ({away_count})"

    def disable_buttons(self) -> bool:
        if self.home_button.disabled and self.away_button.disabled:
            return False
        self.home_button.disabled = True
        self.away_button.disabled = True
        return True

    def enable_buttons(self) -> bool:
        if not self.home_button.disabled and not self.away_button.disabled:
            return False
        self.home_button.disabled = False
        self.away_button.disabled = False
        return True

    def compare_game(self, game: Game) -> bool:
        return (
            self.home_team == game.home_team
            and self.away_team == game.away_team
            and self.game_start == game.game_start
        )

    def add_vote(self, user_id: int, team: discord.Emoji) -> None:
        time_now = datetime.now(timezone.utc)

        team_choice = None
        if str(team.id) in str(self.home_emoji):
            team_choice = self.home_team
        if str(team.id) in str(self.away_emoji):
            team_choice = self.away_team
        if team_choice is None:
            raise NotAValidTeamError()
        if str(user_id) in self.votes:
            choice = self.votes[str(user_id)]
            if time_now > self.game_start:
                if choice == self.home_team:
                    emoji = self.home_emoji
                if choice == self.away_team:
                    emoji = self.away_emoji
                raise VotingHasEndedError(_("You have voted for ") + f"<:{emoji}>")
            else:
                if choice != team_choice:
                    self.votes[str(user_id)] = team_choice
                    self._should_save = True
                    raise UserHasVotedError("{} {}".format(team, team_choice))
        if time_now > self.game_start:
            raise VotingHasEndedError(_("You did not vote on this game!"))
        if str(user_id) not in self.votes:
            self.votes[str(user_id)] = team_choice
            self._should_save = True

    def to_json(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "game_state": self.game_state.value,
            "messages": self.messages,
            "guild": self.guild,
            "game_start": self.game_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home_team": self.home_team,
            "away_team": self.away_team,
            "votes": self.votes,
            "name": self.name,
            "winner": self.winner,
            "link": self.link,
            "game_type": self.game_type.value,
            "should_edit": self.should_edit,
        }

    @classmethod
    def from_json(cls, data: dict) -> Pickems:
        log.trace("Pickems from_json data: %s", data)
        game_start = datetime.strptime(data["game_start"], "%Y-%m-%dT%H:%M:%SZ")
        game_start = game_start.replace(tzinfo=timezone.utc)
        try:
            game_state = GameState(data["game_state"])
        except ValueError:
            game_state = GameState.from_statsapi(data["game_state"])
        return cls(
            game_id=data["game_id"],
            game_state=game_state,
            messages=data.get("messages", []),
            guild=data["guild"],
            game_start=game_start,
            home_team=data["home_team"],
            away_team=data["away_team"],
            votes=data["votes"],
            name=data.get("name", ""),
            winner=data.get("winner", None),
            link=data.get("link", None),
            game_type=GameType(data.get("game_type", "R")),
            should_edit=data.get("should_edit", True),
        )

    async def set_pickem_winner(self, game: Game) -> bool:
        """
        Sets the pickem object winner from game object

        Returns
        -------
        `True` if the winner has been set or the game is postponed
        `False` if the winner has not set and it's not time to clear it yet.
        """
        log.trace("Setting winner for %r", self)
        if not game:
            return False
        if game.game_state == "Postponed":
            if game.game_start != self.game_start:
                self.game_start = game.game_start
                self._should_save = True
            return False
        if game.home_score > game.away_score:
            self.winner = self.home_team
            self._should_save = True
            return True
        elif game.away_score > game.home_score:
            self.winner = self.away_team
            self._should_save = True
            return True
        return False

    async def get_game(self, api) -> Optional[Game]:
        return await api.get_game_from_id(self.game_id)

    async def check_winner(self, game: Optional[Game] = None) -> bool:
        """
        allow the pickems objects to check winner on their own

        wrapper around set_pickems_winner method to pull the game object
        and return true or false depending on the state of the game

        This realistically only gets called once all the games are done playing
        """
        after_game = datetime.now(tz=timezone.utc) >= (self.game_start + timedelta(hours=2))
        if self.winner:
            return True
        if game is not None:
            return await self.set_pickem_winner(game)
        # if self.link and after_game:
        # log.debug("Checking winner for %r", self)
        # game = await Game.from_url(self.link)
        # return await self.set_pickem_winner(game)
        return False
