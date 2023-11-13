from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, TypedDict

import aiohttp
from red_commons.logging import getLogger
from redbot.core.i18n import Translator

from .constants import TEAMS
from .game import Game, GameState, GameType
from .goal import Goal
from .standings import Standings

TEAM_IDS = {v["id"]: k for k, v in TEAMS.items()}

log = getLogger("red.trusty-cogs.Hockey")

_ = Translator("Hockey", __file__)


ORDINALS = {
    1: _("1st"),
    2: _("2nd"),
    3: _("3rd"),
    4: _("4th"),
    5: _("5th"),
}


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
    UNKNOWN = 0
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
        """
        if self.home_skaters == self.away_skaters == 5:
            return _("Even Strength")
        if self.home_skaters == self.away_skaters == 4:
            return _("4v4")
        if self.home_skaters == self.away_skaters == 3:
            return _("3v3")
        if home and self.home_skaters > self.away_skaters:
            return _("Power Play")
        if not home and self.home_skaters > self.away_skaters:
            return _("Shorthanded Goal")

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
    details: Optional[dict]

    @classmethod
    def from_json(cls, data: dict) -> Event:
        return cls(
            id=data.get("eventId", 0),
            period=data.get("period", 0),
            period_descriptor=data.get("periodDescriptor", {}),
            time_in_period=data.get("timeInPeriod", ""),
            time_remaining=data.get("timeRemaining", ""),
            situation_code=data.get("situationCode", "1551"),
            home_team_defending_side=data.get("homeTeamDefendingSide", "left"),
            type_code=GameEventTypeCode(data.get("typeCode", 0)),
            type_desc_key=data.get("typeDescKey", ""),
            sort_order=data.get("sortOrder", 0),
            details=data.get("details", {}),
        )

    @property
    def situation(self):
        return Situation(self.situation_code)

    def get_player(self, player_id: int, data: dict) -> dict:
        for player in data.get("rosterSpots", []):
            if player_id == player.get("playerId"):
                return player
        return {}

    def description(self, data: dict) -> str:
        description = ""
        shot_type = ""
        first_name = ""
        last_name = ""
        for key, value in self.details.items():
            if key == "shotType":
                shot_type = value
            if key == "scoringPlayerId":
                player = self.get_player(value, data)
                first_name = player.get("firstName", {}).get("default", "")
                last_name = player.get("lastName", {}).get("default", "")
                total = self.details.get("scoringPlayerTotal", 0)
                description += f"{first_name} {last_name} ({total}) {shot_type}, "

            if key == "assist1PlayerId":
                player = self.get_player(value, data)
                first_name = player.get("firstName", {}).get("default", "")
                last_name = player.get("lastName", {}).get("default", "")
                total = self.details.get("assist1PlayerTotal", 0)
                description += _("assists: {first_name} {last_name} ({total}), ").format(
                    first_name=first_name, last_name=last_name, total=total
                )
            if key == "assist2PlayerId":
                player = self.get_player(value, data)
                first_name = player.get("firstName", {}).get("default", "")
                last_name = player.get("lastName", {}).get("default", "")
                total = self.details.get("assist1PlayerTotal", 0)
                description += _("{first_name} {last_name} ({total})").format(
                    first_name=first_name, last_name=last_name, total=total
                )

        return description

    def to_goal(self, data: dict) -> Goal:
        scorer_id = self.details.get("scoringPlayerId", 0)
        jersey_no = self.get_player(scorer_id, data).get("sweaterNumber", 0)

        home_score = self.details.get("homeScore", 0)
        away_score = self.details.get("awayScore", 0)
        team_id = self.details.get("eventOwnerTeamId")
        team_name = TEAM_IDS.get(team_id)
        period_ord = ORDINALS.get(self.period)
        home = data["homeTeam"]["id"] == team_id
        return Goal(
            goal_id=self.id,
            team_name=team_name,
            scorer_id=scorer_id,
            jersey_no=jersey_no,
            description=self.description(data),
            period=self.period,
            period_ord=period_ord,
            time_remaining=self.time_remaining,
            time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            home_score=home_score,
            away_score=away_score,
            strength=self.situation.strength(home),
            strength_code=self.situation.code,
            empty_net=self.situation.empty_net(home),
            event="",
            link="",
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

    @classmethod
    def from_statsapi(cls, data: dict) -> ScheduledGame:
        raise NotImplementedError  # not working so no point building this yet

    @classmethod
    def from_nhle(cls, data: dict) -> ScheduledGame:
        game_id = data["id"]
        game_type = GameType.from_int(data["gameType"])
        venue = data["venue"].get("default", "Unknown")
        broadcasts = data["tvBroadcasts"]
        home_team_data = data["homeTeam"]
        home_team = TEAM_IDS[home_team_data["id"]]
        home_score = home_team_data.get("score", 0)
        away_team_data = data["awayTeam"]
        away_team = TEAM_IDS[away_team_data["id"]]
        away_score = away_team_data.get("score", 0)
        game_start = datetime.strptime(data["startTimeUTC"], "%Y-%m-%dT%H:%M:%SZ")
        game_start = game_start.replace(tzinfo=timezone.utc)
        schedule_state = data["gameScheduleState"]
        period = data.get("periodDescriptor", {}).get("number", -1)
        game_state = GameState.from_nhle(data["gameState"], period)
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
        )


class Schedule:
    def __init__(self, days: List[List[ScheduledGame]]):
        self.games: List[ScheduledGame] = [g for d in days for g in d]
        self.days: List[List[ScheduledGame]] = days

    @classmethod
    def from_statsapi(cls, data: dict) -> Schedule:
        raise NotImplementedError

    @classmethod
    def from_nhle(cls, data: dict) -> Schedule:
        days = []
        for day in data.get("gameWeek", []):
            games = []
            for game in day.get("games", []):
                games.append(ScheduledGame.from_nhle(game))
            days.append(games)
        return cls(days)


class HockeyAPI:
    def __init__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Red-DiscordBot Trusty-cogs Hockey"}
        )
        self.base_url = None

    async def close(self):
        await self.session.close()

    async def get_game_content(self, game_id: int):
        raise NotImplementedError()

    async def get_schedule(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        raise NotImplementedError

    async def get_games_list(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[dict]:
        raise NotImplementedError

    async def get_games(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[dict]:
        raise NotImplementedError

    async def get_game_from_id(self, game_id: int) -> dict:
        raise NotImplementedError

    async def get_game_from_url(self, game_url: str) -> dict:
        raise NotImplementedError


class StatsAPI(HockeyAPI):
    def __init__(self):
        super().__init__()
        self.base_url = "https://statsapi.web.nhl.com"

    async def get_game_content(self, game_id: int):
        async with self.session.get(f"{self.base_url}/{game_id}/content") as resp:
            data = await resp.json()
        return data

    async def get_schedule(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Schedule:
        start_date_str = start_date.strftime("%Y-%m-%d") if start_date is not None else None
        end_date_str = end_date.strftime("%Y-%m-%d") if end_date is not None else None
        params = {"expand": "schedule.teams,schedule.linescore,schedule.broadcasts"}
        url = self.base_url + "/api/v1/schedule"
        if start_date is None and end_date is not None:
            # if no start date is provided start with today
            params["startDate"] = datetime.now().strftime("%Y-%m-%d")
            params["endDate"] = end_date_str
            # url = f"{BASE_URL}/api/v1/schedule?startDate={start_date_str}&endDate={end_date_str}"
        elif start_date is not None and end_date is None:
            # if no end date is provided carry through to the following year
            params["endDate"] = str(start_date.year + 1) + start_date.strftime("-%m-%d")
            params["startDate"] = start_date_str
            # url = f"{BASE_URL}/api/v1/schedule?startDate={start_date_str}&endDate={end_date_str}"
        if start_date_str is not None:
            params["startDate"] = start_date_str
        if end_date_str is not None:
            params["endDate"] = end_date_str
        if team not in ["all", None]:
            # if a team is provided get just that TEAMS data
            # url += "&teamId={}".format(TEAMS[team]["id"])
            params["teamId"] = TEAMS[team]["id"]
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                data = None
                log.info("Error checking schedule. %s", resp.status)
        return Schedule.from_statsapi(data)

    async def get_games_list(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[dict]:
        """
        Get a specified days games, defaults to the current day
        requires a datetime object
        returns a list of game objects
        if a start date and an end date are not provided to the url
        it returns only todays games

        returns a list of games
        """
        data = await self.get_schedule(team, start_date, end_date)
        game_list = [game for date in data["dates"] for game in date["games"]]
        return game_list

    async def get_games(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[dict]:
        """
        Get a specified days games, defaults to the current day
        requires a datetime object
        returns a list of game objects
        if a start date and an end date are not provided to the url
        it returns only todays games

        returns a list of game objects
        """
        games_list = await self.get_games_list(team, start_date, end_date)
        return_games_list = []
        if games_list != []:
            for games in games_list:
                try:
                    async with self.session.get(self.base_url + games["link"]) as resp:
                        data = await resp.json()
                    log.verbose("get_games, url: %s%s", self.base_url, games["link"])
                    return_games_list.append(await self.to_game_obj_json(data))
                except Exception:
                    log.error("Error grabbing game data:", exc_info=True)
                    continue
        return return_games_list

    async def get_game_from_id(self, game_id: int) -> dict:
        url = f"{self.base_url}/api/v1/game/{game_id}/feed/live"
        async with self.session.get(url) as resp:
            data = await resp.json()
        return data

    async def get_game_from_url(self, game_url: str) -> dict:
        url = f"{self.base_url}/{game_url}"
        async with self.session.get(url) as resp:
            data = await resp.json()
        return data

    def get_image_and_highlight_url(
        self, event_id: int, media_content: dict
    ) -> Tuple[Optional[str], ...]:
        image, link = None, None
        try:
            if media_content["media"]["milestones"]:
                for highlight in media_content["media"]["milestones"]["items"]:
                    if highlight["statsEventId"] == str(event_id):
                        for playback in highlight["highlight"]["playbacks"]:
                            if playback["name"] == "FLASH_1800K_896x504":
                                link = playback["url"]
                        image = (
                            highlight["highlight"]
                            .get("image", {})
                            .get("cuts", {})
                            .get("1136x640", {})
                            .get("src", None)
                        )
            else:
                for highlight in media_content["highlights"]["gameCenter"]["items"]:
                    if "keywords" not in highlight:
                        continue
                    for keyword in highlight["keywords"]:
                        if keyword["type"] != "statsEventId":
                            continue
                        if keyword["value"] == str(event_id):
                            for playback in highlight["playbacks"]:
                                if playback["name"] == "FLASH_1800K_896x504":
                                    link = playback["url"]
                            image = (
                                highlight["image"]
                                .get("cuts", {})
                                .get("1136x640", {})
                                .get("src", None)
                            )
        except KeyError:
            pass
        return link, image

    async def to_goal(self, data: dict, players: dict, media_content: Optional[dict]) -> Goal:
        scorer_id = []
        if "players" in data:
            scorer_id = [
                p["player"]["id"]
                for p in data["players"]
                if p["playerType"] in ["Scorer", "Shooter"]
            ]

        if "strength" in data["result"]:
            str_dat = data["result"]["strength"]["name"]
            strength_code = data["result"]["strength"]["code"]
            strength = "Even Strength" if str_dat == "Even" else str_dat
            if data["about"]["ordinalNum"] == "SO":
                strength = "Shoot Out"
        else:
            strength = " "
            strength_code = " "
        empty_net = data["result"].get("emptyNet", False)
        player_id = f"ID{scorer_id[0]}" if scorer_id != [] else None
        if player_id in players:
            jersey_no = players[player_id]["jerseyNumber"]
        else:
            jersey_no = ""
        link = None
        image = None
        if media_content:
            event_id = data["about"]["eventId"]
            link, image = self.get_image_and_highlight_url(event_id, media_content)

        # scorer = scorer_id[0]
        return Goal(
            goal_id=data["result"]["eventCode"],
            team_name=data["team"]["name"],
            scorer_id=scorer_id[0] if scorer_id != [] else None,
            jersey_no=jersey_no,
            description=data["result"]["description"],
            period=data["about"]["period"],
            period_ord=data["about"]["ordinalNum"],
            time_remaining=data["about"]["periodTimeRemaining"],
            time=data["about"]["dateTime"],
            home_score=data["about"]["goals"]["home"],
            away_score=data["about"]["goals"]["away"],
            strength=strength,
            strength_code=strength_code,
            empty_net=empty_net,
            event=data["result"]["event"],
            link=link,
            image=image,
            home_shots=data.get("home_shots", 0),
            away_shots=data.get("away_shots", 0),
        )

    async def get_game_recap_from_content(self, content: dict) -> Optional[str]:
        recap_url = None
        for _item in (
            content.get("editorial", {"recap": {}}).get("recap", {"items": []}).get("items", [])
        ):
            if "playbacks" not in _item["media"]:
                continue
            for _playback in _item["media"]["playbacks"]:
                if _playback["name"] == "FLASH_1800K_896x504":
                    recap_url = _playback["url"]
        return recap_url

    async def to_game(self, data: dict, content: Optional[dict]) -> Game:
        event = data["liveData"]["plays"]["allPlays"]
        home_team = data["gameData"]["teams"]["home"]["name"]
        away_team = data["gameData"]["teams"]["away"]["name"]
        away_roster = data["liveData"]["boxscore"]["teams"]["away"]["players"]
        home_roster = data["liveData"]["boxscore"]["teams"]["home"]["players"]
        players = {}
        players.update(away_roster)
        players.update(home_roster)
        game_id = data["gameData"]["game"]["pk"]
        season = data["gameData"]["game"]["season"]
        period_starts = {}
        for play in data["liveData"]["plays"]["allPlays"]:
            if play["result"]["eventTypeId"] == "PERIOD_START":
                dt = datetime.strptime(play["about"]["dateTime"], "%Y-%m-%dT%H:%M:%SZ")
                dt = dt.replace(tzinfo=timezone.utc)
                period_starts[play["about"]["ordinalNum"]] = dt

        try:
            recap_url = await self.get_game_recap_from_content(content)
        except Exception:
            log.error("Cannot get game recap url.")
            recap_url = None
        goals = [
            await self.to_goal(goal, players, content)
            for goal in event
            if goal["result"]["eventTypeId"] == "GOAL"
            or (
                goal["result"]["eventTypeId"] in ["SHOT", "MISSED_SHOT"]
                and goal["about"]["ordinalNum"] == "SO"
            )
        ]
        link = f"{self.base_url}{data['link']}"
        if "currentPeriodOrdinal" in data["liveData"]["linescore"]:
            period_ord = data["liveData"]["linescore"]["currentPeriodOrdinal"]
            period_time_left = data["liveData"]["linescore"]["currentPeriodTimeRemaining"]
            events = data["liveData"]["plays"]["allPlays"]
        else:
            period_ord = "0"
            period_time_left = "0"
            events = ["."]
        decisions = data["liveData"]["decisions"]
        first_star = decisions.get("firstStar", {}).get("fullName")
        second_star = decisions.get("secondStar", {}).get("fullName")
        third_star = decisions.get("thirdStar", {}).get("fullName")
        game_type = data["gameData"]["game"]["type"]
        game_state = (
            data["gameData"]["status"]["abstractGameState"]
            if data["gameData"]["status"]["detailedState"] != "Postponed"
            else data["gameData"]["status"]["detailedState"]
        )
        return Game(
            game_id=game_id,
            game_state=game_state,
            home_team=home_team,
            away_team=away_team,
            period=data["liveData"]["linescore"]["currentPeriod"],
            home_shots=data["liveData"]["linescore"]["teams"]["home"]["shotsOnGoal"],
            away_shots=data["liveData"]["linescore"]["teams"]["away"]["shotsOnGoal"],
            home_score=data["liveData"]["linescore"]["teams"]["home"]["goals"],
            away_score=data["liveData"]["linescore"]["teams"]["away"]["goals"],
            game_start=data["gameData"]["datetime"]["dateTime"],
            goals=goals,
            home_abr=data["gameData"]["teams"]["home"]["abbreviation"],
            away_abr=data["gameData"]["teams"]["away"]["abbreviation"],
            period_ord=period_ord,
            period_time_left=period_time_left,
            period_starts=period_starts,
            plays=events,
            first_star=first_star,
            second_star=second_star,
            third_star=third_star,
            away_roster=away_roster,
            home_roster=home_roster,
            link=link,
            game_type=game_type,
            season=season,
            recap_url=recap_url,
            # data=data,
        )


class NewAPI(HockeyAPI):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api-web.nhle.com/v1"

    async def get_game_content(self, game_id: int):
        raise NotImplementedError()

    def team_to_abbrev(self, team: str) -> Optional[str]:
        if len(team) == 3:
            return team
        if team.isdigit():
            team_name = TEAM_IDS[int(team)]
        else:
            team_name = team
        return TEAMS.get(team_name, {}).get("tri_code", None)

    async def schedule_now(self) -> Schedule:
        async with self.session.get(f"{self.base_url}/schedule/now") as resp:
            if resp.status != 200:
                log.error("Error accessing the Schedule for now. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return Schedule.from_nhle(data)

    async def schedule(self, date: datetime) -> Schedule:
        date_str = date.strftime("%Y-%m-%d")
        async with self.session.get(f"{self.base_url}/schedule/{date_str}") as resp:
            if resp.status != 200:
                log.error("Error accessing the Schedule for now. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return Schedule.from_nhle(data)

    async def club_schedule_season(self, team: str) -> Schedule:
        team_abr = self.team_to_abbrev(team)
        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")
        async with self.session.get(
            f"{self.base_url}/club-schedule-season/{team_abr}/now"
        ) as resp:
            if resp.status != 200:
                log.error("Error accessing the Club Schedule for the season. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return Schedule.from_nhle(data)

    async def club_schedule_week(self, team: str, date: Optional[datetime] = None) -> Schedule:
        team_abr = self.team_to_abbrev(team)
        date_str = "now"
        if date is not None:
            date_str = date.strftime("%Y-%M-%d")
        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")
        async with self.session.get(
            f"{self.base_url}/club-schedule/{team_abr}/week/{date_str}"
        ) as resp:
            if resp.status != 200:
                log.error("Error accessing the Club Schedule for the week. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return Schedule.from_nhle(data)

    async def club_schedule_month(self, team: str, date: Optional[datetime] = None) -> Schedule:
        team_abr = self.team_to_abbrev(team)

        if team_abr is None:
            raise HockeyAPIError("An unknown team name was provided")

        date_str = "now"
        if date is not None:
            date_str = date.strftime("%Y-%M")
        async with self.session.get(
            f"{self.base_url}/club-schedule/{team_abr}/month/{date_str}"
        ) as resp:
            if resp.status != 200:
                log.error("Error accessing the Club Schedule for the month. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return Schedule.from_nhle(data)

    async def gamecenter_landing(self, game_id: int):
        async with self.session.get(f"{self.base_url}/gamecenter/{game_id}/landing") as resp:
            if resp.status != 200:
                log.error("Error accessing the games landing page. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return data

    async def gamecenter_pbp(self, game_id: int):
        async with self.session.get(f"{self.base_url}/gamecenter/{game_id}/play-by-play") as resp:
            if resp.status != 200:
                log.error("Error accessing the games play-by-play. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return data

    async def gamecenter_boxscore(self, game_id: int):
        async with self.session.get(f"{self.base_url}/gamecenter/{game_id}/boxscore") as resp:
            if resp.status != 200:
                log.error("Error accessing the games play-by-play. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return data

    async def standings_now(self):
        async with self.session.get(f"{self.base_url}/standings/now") as resp:
            if resp.status != 200:
                log.error("Error accessing the standings. %s", resp.status)
                raise HockeyAPIError("There was an error accessing the API.")

            data = await resp.json()
        return data

    async def get_schedule(
        self,
        team: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Schedule:
        if team:
            if start_date is not None:
                return await self.club_schedule_week(team, start_date)
            return await self.club_schedule_season(team)
        if start_date is not None:
            return await self.schedule(start_date)
        return await self.schedule_now()

    async def get_standings(self) -> Standings:
        data = await self.standings_now()
        return Standings.from_nhle(data)

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

    async def get_game_from_id(self, game_id: int) -> Game:
        data = await self.gamecenter_pbp(game_id)
        return await self.to_game(data)

    async def get_game_from_url(self, game_url: str) -> dict:
        raise NotImplementedError

    async def to_goal(self, data: dict, players: dict, media_content: Optional[dict]) -> Goal:
        # scorer = scorer_id[0]
        return Goal(
            goal_id=data["result"]["eventCode"],
            team_name=data["team"]["name"],
            scorer_id=scorer_id[0] if scorer_id != [] else None,
            jersey_no=jersey_no,
            description=data["result"]["description"],
            period=data["about"]["period"],
            period_ord=data["about"]["ordinalNum"],
            time_remaining=data["about"]["periodTimeRemaining"],
            time=data["about"]["dateTime"],
            home_score=data["about"]["goals"]["home"],
            away_score=data["about"]["goals"]["away"],
            strength=strength,
            strength_code=strength_code,
            empty_net=empty_net,
            event=data["result"]["event"],
            link=link,
            image=image,
            home_shots=data.get("home_shots", 0),
            away_shots=data.get("away_shots", 0),
        )

    async def to_game(self, data: dict, content: Optional[dict] = None) -> Game:
        game_id = data["id"]
        period = data.get("period", -1)
        game_state = GameState.from_nhle(data["gameState"], period)
        home_id = data.get("homeTeam", {}).get("id", -1)
        home_team = TEAM_IDS.get(home_id, "Unknown Team")
        away_id = data.get("awayTeam", {}).get("id", -1)
        away_team = TEAM_IDS.get(away_id, "Unknown Team")
        game_start = data["startTimeUTC"]

        period_ord = ORDINALS.get(period, "")
        events = [Event.from_json(i) for i in data["plays"]]
        goals = [e.to_goal(data) for e in events if e.type_code is GameEventTypeCode.GOAL]
        home_roster = [p for p in data["rosterSpots"] if p["teamId"] == home_id]
        away_roster = [p for p in data["rosterSpots"] if p["teamId"] == away_id]
        game_type = GameType.from_int(data["gameType"])
        first_star = None
        second_star = None
        third_star = None
        period_time_left = data.get("clock", {}).get("timeRemaining")
        return Game(
            game_id=game_id,
            game_state=game_state,
            home_team=home_team,
            away_team=away_team,
            period=period,
            home_shots=data["homeTeam"].get("sog", 0),
            away_shots=data["awayTeam"].get("sog", 0),
            home_score=data["homeTeam"].get("score", 0),
            away_score=data["awayTeam"].get("score", 0),
            game_start=game_start,
            goals=goals,
            home_abr=data["homeTeam"].get("abbrev", ""),
            away_abr=data["awayTeam"].get("abbrev", ""),
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
            recap_url=None,
            api=self,
            # data=data,
        )
