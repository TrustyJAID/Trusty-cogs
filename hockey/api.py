from __future__ import annotations

import json
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, TypedDict, Union

import aiohttp
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta
from yarl import URL

from .constants import TEAMS
from .game import Game, GameState, GameType
from .goal import Goal
from .helper import Team
from .player import PlayerStats, Roster, SearchPlayer
from .standings import Playoffs, Standings

TEAM_IDS = {v["id"]: k for k, v in TEAMS.items()}

log = getLogger("red.trusty-cogs.Hockey")

_ = Translator("Hockey", __file__)

VIDEO_URL = URL("https://players.brightcove.net/6415718365001/EXtG1xJ7H_default/index.html")
ORDINALS = {
    1: _("1st"),
    2: _("2nd"),
    3: _("3rd"),
    4: _("4th"),
    5: _("5th"),
}


class CayenneExp(NamedTuple):
    key: str
    value: Union[int, str]

    def __str__(self):
        return f"{self.key}={self.value}"


class SortDir(Enum):
    ASC = "ASC"
    DESC = "DESC"

    def __str__(self):
        return self.value


@dataclass
class SortDict:
    property: str
    direction: SortDir

    def __str__(self):
        x = {"property": self.property, "direction": str(self.direction)}
        return json.dumps(x)


class HockeyAPIError(Exception):
    pass


class GoalData(TypedDict):
    """
    A TypedDict to contain all the needed information for Goal objects
    """

    goal_id: str
    team_name: str
    scorer_id: int
    jersey_no: str
    description: str
    period: int
    period_ord: str
    time_remaining: str
    time: datetime
    home_score: int
    away_score: int
    strength: str
    strength_code: str
    empty_net: bool
    event: str
    game_id: int
    link: Optional[str]


class GameData(TypedDict):
    """
    A TypedDict to contain all the needed information for Game objects
    """

    # might not need this anymore, was in theory to prevent circular imports but I think it's not an issue
    game_id: int
    game_state: str
    home_team: str
    away_team: str
    period: int
    home_shots: int
    away_shots: int
    home_score: int
    away_score: int
    game_start: datetime
    goals: List[GoalData]
    home_goals: list
    away_goals: list
    home_abr: str
    away_abr: str
    period_ord: str
    period_time_left: str
    period_starts: Dict[str, datetime]
    plays: List[dict]
    first_star: Optional[str]
    second_star: Optional[str]
    third_star: Optional[str]
    away_roster: Optional[dict]
    home_roster: Optional[dict]
    link: Optional[str]


class GameEventTypeCode(Enum):
    ALL = 0
    FACEOFF = 502
    HIT = 503
    GIVEAWAY = 504
    GOAL = 505
    SHOT_ON_GOAL = 506
    MISSED_SHOT = 507
    BLOCKED_SHOT = 508
    PENALTY = 509
    STOPPAGE = 516
    PERIOD_START = 520
    PERIOD_END = 521
    SHOOTOUT_COMPLETE = 523
    GAME_END = 524
    TAKEAWAY = 525
    DELAYED_PENALTY = 535
    FAILED_SHOT_ATTEMPT = 537

    def __str__(self):
        return self.name.title().replace("_", " ")

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> GameEventTypeCode:
        for event in GameEventTypeCode:
            if argument.lower() in event.name.lower():
                return event
        return GameEventTypeCode.ALL


class Situation:
    def __init__(self, code: str):
        if len(code) != 4:
            raise TypeError("Situation code must be length of 4.")
        self.away_goalie = int(code[0])
        self.away_skaters = int(code[1])
        self.home_skaters = int(code[2])
        self.home_goalie = int(code[3])
        self.code = code

    def strength(self, home: bool) -> str:
        """
        Get the equivalent strength from the situation code

        Parameters
        ----------
            home: bool
                Whether the situation represents the home team or not

        1551 - Even Strength
        0651 - Pulled away goalie
        1560 - Pulled home goalie
        1451 - Home power play
        1541 - Away power play
        1441 - 4v4
        1331 - 3v3
        1010 - Shootout Home shot
        0101 - Shootout Away shot
        """
        situations = []
        if self.home_skaters == 0 or self.away_skaters == 0:
            # Special case return for shootout situations
            return _("Shootout")
        if home and self.home_goalie == 0 or not home and self.away_goalie == 0:
            situations.append(_("Pulled Goalie"))
        elif home and self.away_goalie == 0 or not home and self.home_goalie == 0:
            situations.append(_("Empty Net"))

        if (self.away_skaters + self.away_goalie) != (self.home_skaters + self.home_goalie):
            if home:
                if self.home_skaters < self.away_skaters:
                    situations.append(_("Shorthanded"))
                else:
                    situations.append(_("Power Play"))
            else:
                if self.away_skaters < self.home_skaters:
                    situations.append(_("Shorthanded"))
                else:
                    situations.append(_("Power Play"))

        uneven = self.home_skaters < 5 or self.away_skaters < 5
        if not uneven and (self.home_goalie != 0 and self.away_goalie != 0):
            situations.append(_("Even Strength"))
        situations.append(f"({self.away_skaters}v{self.home_skaters})")

        return " ".join(s for s in situations)

    def empty_net(self, home: bool) -> str:
        """
        Determine whether the situation is an empty net from the situation code

        Parameters
        ----------
            home: bool
                Whether the situation represents the home team or not
        """
        if (home and self.away_goalie == 0) or (not home and self.home_goalie == 0):
            return _("Empty Net")
        return ""


@dataclass
class Player:
    teamId: int
    playerId: int
    firstName: dict
    lastName: dict
    sweaterNumber: int
    positionCode: str
    headshot: str

    def __str__(self):
        return f"#{self.sweaterNumber} {self.name}"

    @property
    def id(self):
        return self.playerId

    @property
    def first_name(self):
        return self.firstName.get("default", _("Unknown"))

    @property
    def last_name(self):
        return self.lastName.get("default", _("Unknown"))

    @property
    def url(self):
        return f"https://www.nhl.com/player/{self.first_name.lower()}-{self.last_name.lower()}-{self.id}"

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def as_link(self):
        return f"[{str(self)}]({self.url})"

    @classmethod
    def from_json(cls, data: dict) -> Player:
        return cls(
            teamId=data.get("teamId"),
            playerId=data.get("playerId"),
            firstName=data.get("firstName"),
            lastName=data.get("lastName"),
            sweaterNumber=data.get("sweaterNumber", 0),
            positionCode=data.get("positionCode"),
            headshot=data.get("headshot"),
        )


@dataclass
class Event:
    id: int
    period: int
    period_descriptor: dict
    time_in_period: str
    time_remaining: str
    situation_code: str
    home_team_defending_side: str
    type_code: GameEventTypeCode
    type_desc_key: str
    sort_order: int
    details: Dict[str, Any]
    team: Optional[Team]
    home: Team
    away: Team
    home_roster: Dict[int, Player]
    away_roster: Dict[int, Player]

    @classmethod
    def from_json(
        cls,
        data: dict,
        home_team: Team,
        away_team: Team,
        home_roster: Dict[int, Player],
        away_roster: Dict[int, Player],
    ) -> Event:
        team_id = data.get("details", {}).get("eventOwnerTeamId")
        team = None
        if team_id == home_team.id:
            team = home_team
        if team_id == away_team.id:
            team = away_team
        return cls(
            id=data.get("eventId", 0),
            period=data.get("periodDescriptor", {}).get("number"),
            period_descriptor=data.get("periodDescriptor", {}),
            time_in_period=data.get("timeInPeriod", ""),
            time_remaining=data.get("timeRemaining", ""),
            situation_code=data.get("situationCode", "1551"),
            home_team_defending_side=data.get("homeTeamDefendingSide", "left"),
            type_code=GameEventTypeCode(data.get("typeCode", 0)),
            type_desc_key=data.get("typeDescKey", ""),
            sort_order=data.get("sortOrder", 0),
            details=data.get("details", {}),
            team=team,
            home=home_team,
            away=away_team,
            home_roster=home_roster,
            away_roster=away_roster,
        )

    def is_goal_or_shot(self) -> bool:
        if self.type_code is GameEventTypeCode.GOAL:
            return True
        elif (
            self.type_code in [GameEventTypeCode.MISSED_SHOT, GameEventTypeCode.SHOT_ON_GOAL]
            and self.period_descriptor.get("periodType", None) == "SO"
        ):
            return True
        return False

    @property
    def situation(self):
        return Situation(self.situation_code)

    def get_player(self, player_id: int) -> Optional[Player]:
        if player_id in self.home_roster:
            return self.home_roster[player_id]
        if player_id in self.away_roster:
            return self.away_roster[player_id]
        return None

    def goal_description(self) -> str:
        description = ""
        shot_type = ""
        for key, value in self.details.items():
            if key == "shotType":
                shot_type = value
            if key in ["scoringPlayerId", "shootingPlayerId"]:
                player = self.get_player(value)
                player_name = player.name if player else _("Unknown")
                player_num = f"#{player.sweaterNumber} " if player else ""
                total = self.details.get("scoringPlayerTotal", 0)
                description += f"{player_num}{player_name} ({total}) {shot_type}"

            if key == "assist1PlayerId":
                player = self.get_player(value)
                player_name = player.name if player else _("Unknown")
                player_num = f"#{player.sweaterNumber} " if player else ""
                total = self.details.get("assist1PlayerTotal", 0)
                description += _(" assists: {player_num}{player_name} ({total})").format(
                    player_num=player_num, player_name=player_name, total=total
                )
            if key == "assist2PlayerId":
                player = self.get_player(value)
                player_name = player.name if player else _("Unknown")
                player_num = f"#{player.sweaterNumber} " if player else ""
                total = self.details.get("assist2PlayerTotal", 0)
                description += _(", {player_num}{player_name} ({total})").format(
                    player_num=player_num, player_name=player_name, total=total
                )
        return description

    def when(self) -> str:
        period_ord = self.period_descriptor.get("periodType", "REG")
        if period_ord == "REG":
            period_ord = ORDINALS.get(self.period)
        description = _("{time_left} left in the {ordinal} period").format(
            time_left=self.time_remaining,
            ordinal=period_ord,
        )
        return description

    def what(self) -> str:
        home = True if self.team and self.team.id == self.home.id else False
        return f"{self.situation.strength(home)} {self.type_code}"

    def description(self) -> str:
        return f"__{self.when()} {self.what()}__\n{self.who()}"

    def who(self) -> str:
        shot_type = ""
        description = ""
        if self.team:
            description = f"- {self.team.emoji} {self.team}\n"
        if self.details and self.is_goal_or_shot():
            for key, value in self.details.items():
                if key == "shotType":
                    shot_type = value
                if key in ["scoringPlayerId", "shootingPlayerId"]:
                    player = self.get_player(value)
                    total = self.details.get("scoringPlayerTotal", 0)
                    description += f"- {player.as_link() if player else ''} ({total}) {shot_type}"

                if key == "assist1PlayerId":
                    player = self.get_player(value)
                    total = self.details.get("assist1PlayerTotal", 0)
                    description += _(" assists: {player} ({total})").format(
                        player=player.as_link() if player else _("Unknown"), total=total
                    )
                if key == "assist2PlayerId":
                    player = self.get_player(value)
                    total = self.details.get("assist2PlayerTotal", 0)
                    description += _(", {player} ({total})").format(
                        player=player.as_link() if player else _("Unknown"), total=total
                    )
        else:
            if self.details:
                if "playerId" in self.details:
                    player = self.get_player(self.details["playerId"])
                    description += player.as_link() if player else ""
                if self.type_code is GameEventTypeCode.FACEOFF:
                    winner = self.get_player(self.details.get("winningPlayerId", 0))
                    loser = self.get_player(self.details.get("losingPlayerId", 0))
                    description += _("- {winner} won faceoff against {loser}").format(
                        winner=winner.as_link() if winner else winner,
                        loser=loser.as_link() if loser else loser,
                    )
                if self.type_code is GameEventTypeCode.HIT:
                    hitting = self.get_player(self.details.get("hittingPlayerId", 0))
                    hittee = self.get_player(self.details.get("hitteePlayerId", 0))
                    description += _("- {hitting} hit {hittee}").format(
                        hitting=hitting.as_link() if hitting else hitting,
                        hittee=hittee.as_link() if hittee else hittee,
                    )
                if self.type_code is GameEventTypeCode.BLOCKED_SHOT:
                    shooter = self.get_player(self.details.get("shootingPlayerId", 0))
                    blocker = self.get_player(self.details.get("blockingPlayerId", 0))
                    description += _("- {blocker} blocked shot from {shooter}").format(
                        blocker=blocker.as_link() if blocker else blocker,
                        shooter=shooter.as_link() if shooter else shooter,
                    )
                if self.type_code is GameEventTypeCode.SHOT_ON_GOAL:
                    shooter = self.get_player(self.details.get("shootingPlayerId", 0))
                    goalie = self.get_player(self.details.get("goalieInNetId", 0))
                    description += _("- {goalie} saved shot from {shooter}").format(
                        goalie=goalie.as_link() if goalie else goalie,
                        shooter=shooter.as_link() if shooter else shooter,
                    )
                if self.type_code is GameEventTypeCode.MISSED_SHOT:
                    shooter = self.get_player(self.details.get("shootingPlayerId", 0))
                    goalie = self.get_player(self.details.get("goalieInNetId", 0))
                    shot_type = self.details.get("shotType", _("Unknown"))
                    description += _("- {shooter} missed {shot_type} shot on {goalie}").format(
                        goalie=goalie.as_link() if goalie else goalie,
                        shooter=shooter.as_link() if shooter else shooter,
                        shot_type=shot_type,
                    )
                if self.type_code is GameEventTypeCode.PENALTY:
                    committed = self.get_player(self.details.get("committedByPlayerId", 0))
                    drawn = self.get_player(self.details.get("drawnByPlayerId", 0))
                    desc = self.details.get("descKey", _("Unknown")).title()
                    duration = timedelta(minutes=self.details.get("duration", 2))
                    duration_str = humanize_timedelta(timedelta=duration)
                    description += _("- {committed} {duration} for {desc}.").format(
                        desc=desc,
                        duration=duration_str,
                        committed=committed.as_link() if committed else committed,
                    )
                    if drawn:
                        description += _(" Drawn by {drawn}.").format(drawn=drawn.as_link())
                if self.type_code is GameEventTypeCode.STOPPAGE:
                    reason = self.details.get("reason")
                    if reason:
                        description += f"- {reason.title()}"
        return description

    def get_highlight(self, content: Optional[dict]) -> Optional[URL]:
        if content is None:
            return None
        clip_id = None
        scoring = content.get("summary", {}).get("scoring", [])
        for period in scoring:
            period_number = period.get("periodDescriptor", {}).get("number", -1)
            if period_number != self.period:
                continue
            for goal in period.get("goals", []):
                if goal.get("timeInPeriod", "") == self.time_in_period:
                    clip_id = goal.get("highlightClip", None)
        if clip_id is not None:
            return VIDEO_URL.with_query({"videoId": clip_id})
        return None

    def get_sog(self, data: dict) -> Tuple[int, int]:
        home_sog = 0
        away_sog = 0
        home_id = data.get("homeTeam", {}).get("id", 0)
        away_id = data.get("awayTeam", {}).get("id", 0)

        for e in data["plays"]:
            if e["typeCode"] not in [
                GameEventTypeCode.GOAL.value,
                GameEventTypeCode.SHOT_ON_GOAL.value,
            ]:
                continue
            if e["eventId"] == self.id:
                break
            if e.get("details", {}).get("eventOwnerTeamId", -1) == home_id:
                home_sog += 1
            if e.get("details", {}).get("eventOwnerTeamId", -1) == away_id:
                away_sog += 1
        return away_sog, home_sog

    def to_goal(self, data: dict, content: Optional[dict] = None) -> Goal:
        scorer_id = self.details.get("scoringPlayerId", 0)
        if scorer_id == 0:
            scorer_id = self.details.get("shootingPlayerId", 0)
        scorer = self.get_player(scorer_id)
        jersey_no = scorer.sweaterNumber if scorer else 0
        assisters = []
        if assist1 := self.get_player(self.details.get("assist1PlayerId", 0)):
            assisters.append(assist1)
        if assist2 := self.get_player(self.details.get("assist2PlayerId", 0)):
            assisters.append(assist2)
        home_score = self.details.get("homeScore", 0)
        away_score = self.details.get("awayScore", 0)
        team_id = self.details.get("eventOwnerTeamId")
        if team_id == self.home.id:
            team = self.home
        else:
            team = self.away

        period_ord = self.period_descriptor.get("periodType", "REG")
        if period_ord == "REG":
            period_ord = ORDINALS.get(self.period)
        home = data["homeTeam"]["id"] == team_id
        away_sog, home_sog = self.get_sog(data)
        game_id = data.get("id", -1)
        return Goal(
            goal_id=self.id,
            team=team,
            scorer_id=scorer_id,
            jersey_no=jersey_no,
            description=self.goal_description(),
            period=self.period,
            period_ord=period_ord,
            time_remaining=self.time_remaining,
            time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            home_score=home_score,
            away_score=away_score,
            strength=self.situation.strength(home),
            strength_code=self.situation.code,
            empty_net=self.situation.empty_net(home),
            event=str(self.type_code),
            link=self.get_highlight(content),
            situation=self.situation,
            scorer=scorer,
            assisters=assisters,
            home_shots=home_sog,
            away_shots=away_sog,
            game_id=game_id,
            type_code=self.type_code,
            nhle_event=self,
        )


@dataclass
class ScheduledGame:
    id: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    game_type: GameType
    game_start: datetime
    game_state: GameState
    broadcasts: List[dict]
    venue: str
    schedule_state: str
    home: Team
    away: Team
    base_url: URL

    @property
    def landing(self):
        return self.base_url.join(URL(f"/v1/gamecenter/{self.id}/landing"))

    @property
    def play_by_play(self):
        return self.base_url.join(URL(f"/v1/gamecenter/{self.id}/play-by-play"))

    @property
    def boxscore(self):
        return self.base_url.join(URL(f"/v1/gamecenter/{self.id}/boxscore"))

    @classmethod
    def from_statsapi(cls, data: dict) -> ScheduledGame:
        raise NotImplementedError  # not working so no point building this yet

    @classmethod
    def from_nhle(cls, data: dict, url: URL) -> ScheduledGame:
        game_id = data["id"]
        game_type = GameType.from_int(data["gameType"])
        venue = data["venue"].get("default", "Unknown")
        broadcasts = data["tvBroadcasts"]
        home_team_data = data["homeTeam"]
        home_team = TEAM_IDS.get(
            home_team_data["id"],
            home_team_data.get("placeName", {}).get("default", _("Unknown Team")),
        )
        home_score = home_team_data.get("score", 0)
        away_team_data = data["awayTeam"]
        away_team = TEAM_IDS.get(
            away_team_data["id"],
            away_team_data.get("placeName", {}).get("default", _("Unknown Team")),
        )
        away_score = away_team_data.get("score", 0)
        game_start = datetime.strptime(data["startTimeUTC"], "%Y-%m-%dT%H:%M:%SZ")
        game_start = game_start.replace(tzinfo=timezone.utc)
        schedule_state = data["gameScheduleState"]
        period = data.get("periodDescriptor", {}).get("number", -1)
        game_state = GameState.from_nhle(data["gameState"], period)
        home = Team.from_nhle(home_team_data, home=True)
        away = Team.from_nhle(away_team_data, home=False)
        return cls(
            id=game_id,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            game_type=game_type,
            game_start=game_start,
            game_state=game_state,
            broadcasts=broadcasts,
            venue=venue,
            schedule_state=schedule_state,
            home=home,
            away=away,
            base_url=url,
        )


class Schedule:
    def __init__(self, days: List[List[ScheduledGame]], url: URL):
        self.games: List[ScheduledGame] = [g for d in days for g in d]
        self.days: List[List[ScheduledGame]] = days
        self.url: URL = url

    @classmethod
    def from_statsapi(cls, data: dict) -> Schedule:
        raise NotImplementedError

    def remaining(self) -> List[ScheduledGame]:
        return [g for g in self.games if g.game_state.value < GameState.live.value]

    @classmethod
    def from_nhle(cls, data: dict, url: URL) -> Schedule:
        days = []
        if "games" in data:
            for g in data.get("games", []):
                days.append([ScheduledGame.from_nhle(g, url)])

        for day in data.get("gameWeek", []):
            games = []
            for game in day.get("games", []):
                games.append(ScheduledGame.from_nhle(game, url))
            days.append(games)
        return cls(days, url)


class HockeyAPI:
    def __init__(self, base_url: Union[URL, str], *, testing: bool = False):
        self.base_url = URL(base_url)
        self.session = aiohttp.ClientSession(
            self.base_url, headers={"User-Agent": "Red-DiscordBot Trusty-cogs Hockey"}
        )
        self.testing = testing

    async def close(self):
        await self.session.close()


class StatsType(Enum):
    skater = "skater"
    goalie = "goalie"
    team = "team"

    def __str__(self):
        return self.name.lower()

    @property
    def config_key(self):
        if self is StatsType.skater:
            return "playerReportData"
        return f"{self}ReportData"


class StatsAPI(HockeyAPI):
    """
    This Represents access to the new NHL Stats API
    """

    def __init__(self, testing: bool = False):
        super().__init__(URL("https://api.nhle.com"), testing=testing)
        self._config = None
        self._franchises = None

    @staticmethod
    def _cayenne_params(params: List[CayenneExp]) -> str:
        return r" and ".join(str(k) for k in params)

    async def franchises(self):
        if self._franchises is not None:
            return self._franchises
        url = URL("/stats/rest/en/franchise")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the standings at %s. %s", resp.url, resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            data = await resp.json()
        franchise_tuple = namedtuple("Franchise", [k for k in data["data"][0].keys()])
        self._franchises = [franchise_tuple(**i) for i in data["data"]]
        return self._franchises

    async def config(self):
        if self._config is not None:
            return self._config
        url = URL("/stats/rest/en/config")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the standings at %s. %s", resp.url, resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            data = await resp.json()

        self._config = data
        return self._config

    async def request(self, url: URL) -> dict:
        async with self.session.get(url) as resp:
            # log.debug("Stats API headers: %s", resp.headers)
            if resp.status != 200:
                log.error("Error accessing the standings at %s. %s", resp.url, resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            data = await resp.json()
        return data

    async def get(
        self,
        stat_type: StatsType,
        endpoint: str,
        *,
        filter: List[CayenneExp] = [],
        sort: List[SortDict] = [],
        is_aggregate: bool = False,
        is_game: bool = False,
        page: int = 0,
        limit: int = 100,
    ) -> List[NamedTuple]:
        config = await self.config()
        config_info = config.get(stat_type.config_key, {}).get(endpoint)
        if config_info is None:
            raise HockeyAPIError("Stat Type not available with that endpoint", stat_type, endpoint)

        url = URL(f"/stats/rest/en/{stat_type}/{endpoint}")
        query = {
            "start": page,
            "limit": limit,
            "isAggregate": str(is_aggregate).lower(),
            "isGame": str(is_game).lower(),
        }
        url = url.update_query(query)
        sort_keys = []
        if is_game:
            sort_keys = config_info["game"]["sortKeys"]
        else:
            sort_keys = config_info["season"]["sortKeys"]
        if not sort:
            for k in sort_keys:
                sort.append(SortDict(property=k, direction=SortDir.DESC))
        if sort:
            url = url.update_query({"sort": [str(s) for s in sort]})
        if filter:
            url = url.update_query({"cayenneExp": self._cayenne_params(filter)})
        data = await self.request(url)
        tp = namedtuple(
            f"{stat_type.name.title()}{endpoint.title()}", [k for k in data["data"][0].keys()]
        )
        log.debug(url)
        return [tp(**i) for i in data["data"]]


class SkaterStatsAPI(StatsAPI):
    def __init__(self, testing: bool = False):
        super().__init__(testing=testing)

    async def summary(
        self,
        *,
        game_type: GameType = GameType.regular_season,
        season_start: Optional[str] = None,
        season_end: Optional[str] = None,
        franchise: Optional[int] = None,
        page: int = 0,
        limit: int = 50,
    ) -> List[NamedTuple]:
        c_params = [CayenneExp(key="gameTypeId", value=int(game_type))]
        if season_start:
            c_params.append(CayenneExp(key="seasonId>", value=season_start))
        if season_end:
            c_params.append(CayenneExp(key="seasonId<", value=season_end))
        if franchise:
            c_params.append(CayenneExp(key="franchiseId", value=franchise))

        c_str = self._cayenne_params(c_params)
        url = URL("/stats/rest/en/skater/summary")
        url = url.update_query({"start": page, "limit": limit, "cayenneExp": c_str})
        data = await self.request(url)
        tp = namedtuple("SkaterSummary", [k for k in data["data"][0].keys()])
        return [tp(**i) for i in data["data"]]


class SearchAPI(HockeyAPI):
    def __init__(self, testing: bool = False):
        super().__init__(URL("https://search.d3.nhle.com"), testing=testing)

    async def player(
        self,
        search: str,
        *,
        culture: str = "en-us",
        active: Optional[bool] = None,
        limit: int = 20,
    ) -> List[SearchPlayer]:
        params = {"q": search, "culture": culture, "limit": limit}
        if active is not None:
            # omit active for wider range of search unless specified
            # the parameters expects a string not bool so convert
            params["active"] = str(active).lower()

        url = URL("/api/v1/search/player")
        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                log.error("Error accessing the Schedule for now. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            data = await resp.json()
        players = [SearchPlayer.from_json(i) for i in data]
        return sorted(players, key=lambda x: x.active, reverse=True)


class NewAPI(HockeyAPI):
    def __init__(self, testing: bool = False):
        super().__init__(URL("https://api-web.nhle.com"), testing=testing)
        self.search_api = SearchAPI(testing=testing)
        self.stats_api = StatsAPI(testing=testing)

    async def close(self):
        await self.search_api.close()
        await self.stats_api.close()
        await super().close()

    def team_to_abbrev(self, team: str) -> Optional[str]:
        if len(team) == 3:
            return team
        if team.isdigit():
            team_name = TEAM_IDS[int(team)]
        else:
            team_name = team
        return TEAMS.get(team_name, {}).get("tri_code", None)

    async def schedule_now(self) -> Schedule:
        url = URL("/v1/schedule/now")
        if self.testing:
            data = await self.load_testing_data("testschedule.json")
            return Schedule.from_nhle(data, url=self.base_url.join(url))

        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the Schedule for now. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey Schedule headers %s", resp.headers)
            data = await resp.json()
        return Schedule.from_nhle(data, url=self.base_url.join(url))

    async def search_player(
        self,
        search: str,
        *,
        culture: str = "en-us",
        active: Optional[bool] = None,
        limit: int = 20,
    ) -> List[SearchPlayer]:
        return await self.search_api.player(
            search=search, culture=culture, active=active, limit=limit
        )

    async def get_player(self, player_id: int) -> PlayerStats:
        url = URL(f"/v1/player/{player_id}/landing")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the Schedule for now. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            data = await resp.json()
        return PlayerStats.from_json(data)

    async def get_roster(self, team: str, *, season: Optional[str] = None):
        if season is None:
            season = "current"
        team_abr = self.team_to_abbrev(team)
        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")
        url = URL(f"/v1/roster/{team_abr}/{season}")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the Club Schedule for the season. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            data = await resp.json()
        return Roster.from_json(data)

    async def schedule(self, date: datetime) -> Schedule:
        date_str = date.strftime("%Y-%m-%d")
        url = URL(f"/v1/schedule/{date_str}")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the Schedule for now. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey Schedule headers %s", resp.headers)
            data = await resp.json()
        return Schedule.from_nhle(data, url=self.base_url.join(url))

    async def club_schedule_season(self, team: str) -> Schedule:
        team_abr = self.team_to_abbrev(team)
        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")
        url = URL(f"/v1/club-schedule-season/{team_abr}/now")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the Club Schedule for the season. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )

            data = await resp.json()
        return Schedule.from_nhle(data, url=self.base_url.join(url))

    async def club_schedule_week(self, team: str, date: Optional[datetime] = None) -> Schedule:
        team_abr = self.team_to_abbrev(team)
        date_str = "now"
        if date is not None:
            date_str = date.strftime("%Y-%m-%d")
        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")
        url = URL(f"/v1/club-schedule/{team_abr}/week/{date_str}")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error(
                    "Error accessing the Club Schedule for the week. %s: %s", resp.status, url
                )
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey Schedule headers %s", resp.headers)
            data = await resp.json()
        return Schedule.from_nhle(data, url=self.base_url.join(url))

    async def club_schedule_month(self, team: str, date: Optional[datetime] = None) -> Schedule:
        team_abr = self.team_to_abbrev(team)

        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")

        date_str = "now"
        if date is not None:
            date_str = date.strftime("%Y-%m")
        url = URL(f"/v1/club-schedule/{team_abr}/month/{date_str}")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the Club Schedule for the month. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey Schedule headers %s", resp.headers)
            data = await resp.json()
        return Schedule.from_nhle(data, url=self.base_url.join(url))

    async def gamecenter_landing(self, game_id: int):
        if self.testing:
            data = await self.load_testing_data("test-landing.json")
            return data
        url = URL(f"/v1/gamecenter/{game_id}/landing")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the games landing page. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey GC landing headers %s", resp.headers)
            data = await resp.json()
        return data

    async def gamecenter_pbp(self, game_id: int):
        url = URL(f"/v1/gamecenter/{game_id}/play-by-play")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the games play-by-play. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey GC pbp headers %s", resp.headers)
            data = await resp.json()
        return data

    async def gamecenter_boxscore(self, game_id: int):
        url = URL(f"/v1/gamecenter/{game_id}/boxscore")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the games play-by-play. %s", resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey GC boxscore headers %s", resp.headers)
            data = await resp.json()
        return data

    async def standings_now(self):
        url = URL("/v1/standings/now")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the standings at %s. %s", resp.url, resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey standings headers %s", resp.headers)
            data = await resp.json()
        return data

    async def get_schedule(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Schedule:
        if team is not None and team not in ["all"]:
            if start_date is not None:
                return await self.club_schedule_week(team, start_date)
            return await self.club_schedule_season(team)
        if start_date is not None:
            return await self.schedule(start_date)
        return await self.schedule_now()

    async def get_standings(self) -> Standings:
        data = await self.standings_now()
        return Standings.from_nhle(data)

    async def get_playoffs(self, date: Optional[Union[datetime, int]] = None):
        if date is None:
            year = datetime.now(timezone.utc).year
        elif isinstance(date, datetime):
            year = date.year
        else:
            year = date
        url = URL(f"/v1/playoff-bracket/{year}")
        async with self.session.get(url) as resp:
            if resp.status != 200:
                log.error("Error accessing the standings at %s. %s", resp.url, resp.status)
                raise HockeyAPIError(
                    "There was an error accessing the API.", resp.status, resp.url
                )
            log.trace("Hockey standings headers %s", resp.headers)
            data = await resp.json()
        return Playoffs.from_json(data, year)

    async def get_games_list(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Game]:
        return await self.get_games(team, start_date, end_date)

    async def get_games(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Game]:
        schedule = await self.get_schedule(team, start_date, end_date)
        if len(schedule.days) > 0:
            return [await self.get_game_from_id(g.id) for g in schedule.days[0]]
        return []

    async def load_testing_data(self, file_name: str) -> dict:
        path = Path(__file__).parent.resolve() / file_name
        with path.open("r") as infile:
            data = json.loads(infile.read())
        return data

    async def get_game_from_id(self, game_id: int) -> Game:
        if self.testing:
            data = await self.load_testing_data("testgame.json")
            landing = await self.gamecenter_landing(game_id)
            return await self.to_game(data, content=landing)
        data = await self.gamecenter_pbp(game_id)
        try:
            landing = await self.gamecenter_landing(game_id)
        except Exception:
            landing = None
        return await self.to_game(data, content=landing)

    async def get_game_recap(self, game_id: int) -> Optional[URL]:
        landing = await self.gamecenter_landing(game_id)
        recap = landing.get("summary", {}).get("gameVideo", {}).get("condensedGame")
        if recap is None:
            recap = landing.get("gameVideo", {}).get("condensedGame")
        if recap is not None:
            return VIDEO_URL.with_query({"videoId": recap})
        return None

    async def to_game(self, data: dict, content: Optional[dict] = None) -> Game:
        game_id = data["id"]
        period = data.get("periodDescriptor", {}).get("number", -1)
        period_time_left = data.get("clock", {}).get("timeRemaining")
        game_state = GameState.from_nhle(data["gameState"], period, period_time_left)
        home_data = data.get("homeTeam", {})
        home_id = home_data.get("id", -1)
        home_team = home_data.get("name", {}).get("default")
        home = Team.from_nhle(home_data, home=True)
        if home_id in TEAM_IDS:
            home_team = TEAM_IDS.get(home_id, "Unknown Team")
            home = Team.from_json(TEAMS.get(home_team, {}), home_team)

        away_data = data.get("awayTeam", {})
        away_id = away_data.get("id", -1)
        away_team = away_data.get("name", {}).get("default")
        away = Team.from_nhle(away_data, home=False)
        if away_id in TEAM_IDS:
            away_team = TEAM_IDS.get(away_id, "Unknown Team")
            away = Team.from_json(TEAMS.get(away_team, {}), away_team)
        game_start = data["startTimeUTC"]

        period_ord = ORDINALS.get(period, "")
        period_descriptor = data.get("periodDescriptor", {}).get("periodType", "REG")
        if period_descriptor != "REG":
            period_ord = period_descriptor

        home_roster = {
            p["playerId"]: Player.from_json(p)
            for p in data["rosterSpots"]
            if p["teamId"] == home_id
        }
        away_roster = {
            p["playerId"]: Player.from_json(p)
            for p in data["rosterSpots"]
            if p["teamId"] == away_id
        }
        events = [Event.from_json(i, home, away, home_roster, away_roster) for i in data["plays"]]
        goals = [e.to_goal(data, content=content) for e in events if e.is_goal_or_shot()]
        game_type = GameType.from_int(data["gameType"])
        first_star = None
        second_star = None
        third_star = None

        recap_url = None
        if content:
            recap = content.get("summary", {}).get("gameVideo", {}).get("condensedGame")
            if recap is None:
                recap = content.get("gameVideo", {}).get("condensedGame")
            if recap is not None:
                recap_url = VIDEO_URL.with_query({"videoId": recap})
            for star in content.get("summary", {}).get("threeStars", []):
                player_id = star.get("playerId", -1)
                player = home_roster.get(player_id, None) or away_roster.get(player_id, None)
                if star.get("star", 0) == 1:
                    first_star = player
                if star.get("star", 0) == 2:
                    second_star = player
                if star.get("star", 0) == 3:
                    third_star = player
        return Game(
            game_id=game_id,
            game_state=game_state,
            home=home,
            away=away,
            period=period,
            home_shots=data["homeTeam"].get("sog", 0),
            away_shots=data["awayTeam"].get("sog", 0),
            home_score=data["homeTeam"].get("score", 0),
            away_score=data["awayTeam"].get("score", 0),
            game_start=game_start,
            goals=goals,
            period_ord=period_ord,
            period_time_left=period_time_left,
            period_starts={},
            plays=events,
            first_star=first_star,
            second_star=second_star,
            third_star=third_star,
            away_roster=away_roster,
            home_roster=home_roster,
            link="",
            game_type=game_type,
            season=data.get("season", 0),
            recap_url=recap_url,
            api=self,
            url=URL(f"{self.base_url}/v1/gamecenter/{game_id}/play-by-play"),
            landing=content,
            # data=data,
        )
