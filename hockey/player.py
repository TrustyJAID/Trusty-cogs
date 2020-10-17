import aiohttp
import json
import logging
import discord

from dataclasses import dataclass
from typing import Optional, Literal
from tabulate import tabulate
from datetime import datetime

from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from .constants import BASE_URL, HEADSHOT_URL, TEAMS

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.hockey")


# This is somewhat unnecessary but for consistency we have the expected
# object here to "get" the data from the disct the API provides
# this way we can expect a value for each dataclass and not have to worry about
# a lot of other issues that can arise when doing this type of inheritence
SKATER_STATS = {
    "time_on_ice": "timeOnIce",
    "assists": "assists",
    "goals": "goals",
    "pim": "pim",
    "shots": "shots",
    "games": "games",
    "hits": "hits",
    "powerplay_goals": "powerPlayGoals",
    "powerplay_points": "powerPlayPoints",
    "powerplay_time_on_ice": "powerPlayTimeOnIce",
    "event_time_on_ice": "evenTimeOnIce",
    "penalty_minutes": "penaltyMinutes",
    "face_off_percent": "faceOffPct",
    "shot_percent": "shotPct",
    "game_winning_goals": "gameWinningGoals",
    "over_time_goals": "overTimeGoals",
    "short_handed_goals": "shortHandedGoals",
    "short_handed_points": "shortHandedPoints",
    "short_handed_time_on_ice": "shortHandedTimeOnIce",
    "blocked": "blocked",
    "plusminus": "plusMinus",
    "points": "points",
    "shifts": "shifts",
    "time_on_ice_per_game": "timeOnIcePerGame",
    "even_time_on_ice_per_game": "evenTimeOnIcePerGame",
    "short_handed_time_on_ice_per_game": "shortHandedTimeOnIcePerGame",
    "powerplay_time_on_ice_per_game": "powerPlayTimeOnIcePerGame",
}

GOALIE_STATS = {
    "time_on_ice": "timeOnIce",
    "ot": "ot",
    "shutouts": "shutouts",
    "wins": "wins",
    "ties": "ties",
    "losses": "losses",
    "saves": "saves",
    "powerplay_saves": "powerPlaySaves",
    "shorthanded_saves": "shortHandedSaves",
    "even_saves": "evenSaves",
    "shorthanded_shots": "shortHandedShots",
    "even_shots": "evenShots",
    "powerplay_shots": "powerPlayShots",
    "save_percentage": "savePercentage",
    "goals_against_average": "goalAgainstAverage",
    "games": "games",
    "games_started": "gamesStarted",
    "shots_against": "shotsAgainst",
    "goals_against": "goalsAgainst",
    "time_on_ice_per_game": "timeOnIcePerGame",
    "powerplay_save_percentage": "powerPlaySavePercentage",
    "shorthanded_save_percentage": "shortHandedSavePercentage",
    "even_strength_save_percentage": "evenStrengthSavePercentage",
}


@dataclass
class Player:
    id: int
    accrued_seasons: Optional[int]
    add_names: Optional[str]
    age_signed_waiver: Optional[int]
    age_signel_fa: Optional[int]
    alert: Literal["Y", "N"]
    birth_city: Optional[str]
    birth_country: Optional[str]
    birth_date: Optional[str]
    birth_state_province: Optional[str]
    career_team_id: Optional[int]
    central_registry_position: Optional[str]
    club_elect_arb: Literal["Y", "N"]
    current_team_id: Optional[int]
    date_of_death: Optional[str]
    dda_id: Optional[int]
    deceased: bool
    ep_player_id: Optional[int]
    fa_group_after_season: Literal[None]
    first_name: str
    first_signed_by_team_id: Optional[int]
    free_agent_group: Optional[str]
    full_name: str
    group_5_election: Literal["Y", "N"]
    group_5_seasons_earned: Optional[int]
    group_6_proration: Literal[None]
    group_6_seasons_earned: Optional[int]
    groups_earned_thru_season: Optional[int]
    height: Optional[int]
    hof_induction_year: Optional[int]
    home_town: Optional[str]
    iihf_hof_induction_year: Optional[int]
    in_hockey_hof: bool
    in_iihf_hof: int
    in_top_100_all_time: int
    in_us_hockey_hof: bool
    is_defected: Literal["Y", "N"]
    is_deleted: Literal["Y", "N"]
    is_junior: Literal["Y", "N"]
    is_retired: Literal[None]
    is_rookie: Literal["Y", "N"]
    is_suspended: Literal["Y", "N"]
    last_ameteur_league_id: Optional[int]
    last_ameteur_team_id: Optional[int]
    last_nhl_team_id: Optional[int]
    last_name: str
    loan_cap_exception: Literal["Y", "N"]
    long_term_injury: Literal["Y", "N"]
    message: Optional[str]
    middle_name: Optional[str]
    nationality: Optional[str]
    nhl_experience: Optional[int]
    on_roster: Literal["Y", "N"]
    platform_year: Optional[int]
    position: Optional[Literal["L", "R", "C", "D", "G"]]
    pr_name: str
    pr_stat: int
    pro_year_reduction: Optional[int]
    reenty_waivers: Optional[Literal["Y", "N"]]
    roster_special_code: Optional[str]
    salary_arbitration_exp: Optional[int]
    shoots_catches: Optional[Literal["L", "R"]]
    sweater_number: Optional[int]
    update_timestamp: str
    us_hof_induction_year: Optional[int]
    vet_cap_exception: Literal["Y", "N"]
    waiver_amount: Optional[int]
    waiver_draft: Optional[str]
    waiver_status: Literal["Y", "N"]
    weight: Optional[int]
    years_pro: Optional[int]

    def __str__(self) -> str:
        return "{0.full_name}, born {0.birth_date}".format(self)

    def __repr__(self) -> str:
        return "<Player name={0.full_name} id={0.id} number={0.sweater_number}>".format(self)

    def description(self) -> str:
        desc = {
            "birth_date": _("Born on "),
            "position": _("Position "),
            "home_town": _("From "),
            "height": _("Height "),
            "weight": _("Weight "),
        }

        msg = ""
        for attr, name in desc.items():
            if getattr(self, attr):
                if attr == "height" and self.height:
                    msg += (
                        name
                        + f"{self.height//12}' {self.height%12}\" / {int(self.height * 2.54)} cm\n"
                    )
                elif attr == "birth_date":
                    years = int(
                        (datetime.now() - datetime.strptime(self.birth_date, "%Y-%m-%d")).days
                        / 365.25
                    )
                    msg += name + f"{getattr(self, attr)} ({years})\n"
                elif attr == "weight" and self.weight:
                    msg += name + f"{self.weight} lbs / {int(self.weight * 0.453592)} kg\n"
                elif attr == "home_town":
                    msg += (
                        name + f"{getattr(self, attr)} :flag_{self.birth_country.lower()[:2]}:\n"
                    )
                elif attr == "position":
                    shoots = f"({getattr(self, 'shoots_catches', '')})"
                    msg += name + f"{getattr(self, attr)} {shoots if shoots != '()' else ''}\n"
                else:
                    msg += name + f"{getattr(self, attr)}\n"
        msg += _("[Elite Prospects]({ep_url})").format(ep_url=self.ep_url())
        return msg

    def headshot(self) -> str:
        return HEADSHOT_URL.format(self.id)

    def get_embed(self) -> discord.Embed:
        try:
            team_name = [
                name for name, team in TEAMS.items() if team["id"] == self.current_team_id
            ][0]
            colour = int(TEAMS[team_name]["home"].replace("#", ""), 16)
            logo = TEAMS[team_name]["logo"]
        except IndexError:
            team_name = _("No Team")
            colour = 0xFFFFFF
            logo = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"

        em = discord.Embed(colour=colour)
        em.description = self.description()
        em.set_thumbnail(url=self.headshot())
        number = f"#{self.sweater_number}" if self.sweater_number else ""
        em.set_author(name=f"{self.full_name} {number}", icon_url=logo)
        em.description = self.description()
        return em

    async def get_full_stats(self, season: Optional[str]) -> str:
        if season:
            url_season = f"&season={season}"
        else:
            url_season = ""
        url = f"https://statsapi.web.nhl.com/api/v1/people/{self.id}/stats?stats=statsSingleSeason{url_season}"
        log.debug(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        if data["stats"][0]["splits"]:
            stats_season = data["stats"][0]["splits"][0]["season"]
            if self.position == "G":
                stats = [
                    data["stats"][0]["splits"][0]["stat"].get(v, "")
                    for k, v in GOALIE_STATS.items()
                ]
                player = Goalie(
                    *self.__dict__.values(),
                    stats_season,
                    *stats,
                )
                return await player.get_full_stats(season)
            else:
                stats = [
                    data["stats"][0]["splits"][0]["stat"].get(v, "") for v in SKATER_STATS.values()
                ]
                player = Skater(
                    *self.__dict__.values(),
                    stats_season,
                    *stats,
                )
                return await player.get_full_stats(season)
        return self

    def full_name_url(self) -> str:
        return self.full_name.replace(" ", "-").lower()

    def ep_url(self) -> str:
        return f"https://www.eliteprospects.com/player/{self.ep_player_id}/{self.full_name_url()}"

    @classmethod
    async def from_id(cls, player_id: int):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://records.nhl.com/site/api/player/{player_id}") as resp:
                data = await resp.json()
        return cls(*data["data"][0].values())


@dataclass
class Skater(Player):
    season: str
    time_on_ice: str
    assists: int
    goals: int
    pim: int
    shots: int
    games: int
    hits: int
    powerplay_goals: int
    powerplay_points: int
    powerplay_time_on_ice: str
    event_time_on_ice: str
    penalty_minutes: str
    face_off_percent: float
    shot_percent: float
    game_winning_goals: int
    over_time_goals: int
    short_handed_goals: int
    short_handed_points: int
    short_handed_time_on_ice: str
    blocked: int
    plusminus: int
    points: int
    shifts: int
    time_on_ice_per_game: str
    even_time_on_ice_per_game: str
    shorthanded_time_on_ice_per_game: str
    powerplay_time_on_ice_per_game: str

    def __str__(self) -> str:
        return "{0.full_name}, goals {0.goals}, games {0.games}".format(self)

    def __repr__(self) -> str:
        return "<Skater name={0.full_name} id={0.id} number={0.sweater_number}>".format(self)

    async def get_full_stats(self, season: Optional[str]) -> str:
        log.debug(season)
        if season:
            url_season = f"&season={season}"
        else:
            url_season = ""
        url = f"https://statsapi.web.nhl.com/api/v1/people/{self.id}/stats?stats=statsSingleSeasonPlayoffs{url_season}"
        log.debug(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        if data["stats"][0]["splits"]:
            stats_season = data["stats"][0]["splits"][0]["season"]
            stats = [
                data["stats"][0]["splits"][0]["stat"].get(v, "") for v in SKATER_STATS.values()
            ]

            player = SkaterPlayoffs(
                *self.__dict__.values(),
                *stats,
            )
            return player
        return self

    def get_embed(self) -> discord.Embed:
        try:
            team_name = [
                name for name, team in TEAMS.items() if team["id"] == self.current_team_id
            ][0]
            colour = int(TEAMS[team_name]["home"].replace("#", ""), 16)
            logo = TEAMS[team_name]["logo"]
        except IndexError:
            team_name = _("No Team")
            colour = 0xFFFFFF
            logo = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        em = discord.Embed(colour=colour)
        number = f"#{self.sweater_number}" if self.sweater_number else ""
        em.set_author(name=f"{self.full_name} {number}", icon_url=logo)
        em.set_thumbnail(url=self.headshot())
        em.description = self.description()
        post_data = [
            [_("Shots"), f"[ {self.shots} ]"],
            [_("Goals"), f"[ {self.goals} ]"],
            [_("Assists"), f"[ {self.assists} ]"],
            [_("Hits"), f"[ {self.hits} ]"],
            [_("Faceoff %"), f"[ {self.face_off_percent} ]"],
            ["+/-", f"[ {self.plusminus} ]"],
            [_("Blocked Shots"), f"[ {self.blocked} ]"],
            [_("PIM"), f"[ {self.pim} ]"],
            [_("GP"), f"[ {self.games} ]"],
        ]
        stats_md = tabulate(
            post_data, headers=[_("Stats"), f"{self.season[:4]}-{self.season[4:]}"]
        )
        em.set_thumbnail(url=self.headshot())
        em.add_field(name=_("Stats"), value=box(stats_md, lang="apache"))
        return em


@dataclass
class SkaterPlayoffs(Skater):
    p_time_on_ice: str
    p_assists: int
    p_goals: int
    p_pim: int
    p_shots: int
    p_games: int
    p_hits: int
    p_powerplay_goals: int
    p_powerplay_points: int
    p_powerplay_time_on_ice: str
    p_event_time_on_ice: str
    p_penalty_minutes: str
    p_face_off_percent: float
    p_shot_percent: float
    p_game_winning_goals: int
    p_over_time_goals: int
    p_short_handed_goals: int
    p_short_handed_points: int
    p_short_handed_time_on_ice: str
    p_blocked: int
    p_plusminus: int
    p_points: int
    p_shifts: int
    p_time_on_ice_per_game: str
    p_even_time_on_ice_per_game: str
    p_shorthanded_time_on_ice_per_game: str
    p_powerplay_time_on_ice_per_game: str

    def __str__(self) -> str:
        return "{0.full_name}, goals {0.goals}, games {0.games}".format(self)

    def __repr__(self) -> str:
        return "<Skater name={0.full_name} id={0.id} number={0.sweater_number}>".format(self)

    def get_embed(self) -> discord.Embed:
        try:
            team_name = [
                name for name, team in TEAMS.items() if team["id"] == self.current_team_id
            ][0]
            colour = int(TEAMS[team_name]["home"].replace("#", ""), 16)
            logo = TEAMS[team_name]["logo"]
        except IndexError:
            team_name = _("No Team")
            colour = 0xFFFFFF
            logo = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        em = discord.Embed(colour=colour)
        number = f"#{self.sweater_number}" if self.sweater_number else ""
        em.set_author(name=f"{self.full_name} {number}", icon_url=logo)
        em.set_thumbnail(url=self.headshot())
        em.description = self.description()
        post_data = [
            [_("GP"), f"[ {self.games} ]", f"[ {self.p_games} ]"],
            [_("Shots"), f"[ {self.shots} ]", f"[ {self.p_shots} ]"],
            [_("Goals"), f"[ {self.goals} ]", f"[ {self.p_goals} ]"],
            [_("Assists"), f"[ {self.assists} ]", f"[ {self.p_assists} ]"],
            [_("Hits"), f"[ {self.hits} ]", f"[ {self.p_hits} ]"],
            [_("Faceoff %"), f"[ {self.face_off_percent} ]", f"[ {self.p_face_off_percent} ]"],
            ["+/-", f"[ {self.plusminus} ]", f"[ {self.p_plusminus} ]"],
            [_("Blocked"), f"[ {self.blocked} ]", f"[ {self.p_blocked} ]"],
            [_("PIM"), f"[ {self.pim} ]", f"[ {self.p_pim} ]"],
        ]
        stats_md = tabulate(
            post_data, headers=[_("Stats"), f"{self.season[:4]}-{self.season[4:]}", _("Playoffs")]
        )
        em.set_thumbnail(url=self.headshot())
        em.add_field(name=_("Stats"), value=box(stats_md, lang="apache"))
        return em


@dataclass
class Goalie(Player):
    season: str
    time_on_ice: str
    ot: int
    shutouts: int
    ties: int
    wins: int
    losses: int
    saves: int
    powerplay_saves: int
    shorthanded_saves: int
    even_saves: int
    shorthanded_shots: int
    even_shots: int
    powerplay_shots: int
    save_percentage: float
    goals_against_average: float
    games: int
    games_started: int
    shots_against: int
    goals_against: int
    time_on_ice_per_game: str
    powerplay_save_percentage: float
    shorthanded_save_percentage: float
    even_strength_save_percentage: float

    def __str__(self) -> str:
        return "{0.full_name}, GAA {0.goals_against_average}, games {0.games}".format(self)

    def __repr__(self) -> str:
        return "<Goalie name={0.full_name} id={0.id} number={0.sweater_number}>".format(self)

    async def get_full_stats(self, season: Optional[str]) -> str:
        if season:
            url_season = f"&season={season}"
        else:
            url_season = ""
        url = f"https://statsapi.web.nhl.com/api/v1/people/{self.id}/stats?stats=statsSingleSeasonPlayoffs{url_season}"
        log.debug(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        if data["stats"][0]["splits"]:
            stats = [
                data["stats"][0]["splits"][0]["stat"].get(v, "") for k, v in GOALIE_STATS.items()
            ]
            player = GoaliePlayoffs(
                *self.__dict__.values(),
                *stats,
            )
            return player
        return self

    def get_embed(self) -> discord.Embed:
        try:
            team_name = [
                name for name, team in TEAMS.items() if team["id"] == self.current_team_id
            ][0]
            colour = int(TEAMS[team_name]["home"].replace("#", ""), 16)
            logo = TEAMS[team_name]["logo"]
        except IndexError:
            team_name = _("No Team")
            colour = 0xFFFFFF
            logo = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        em = discord.Embed(colour=colour)
        number = f"#{self.sweater_number}" if self.sweater_number else ""
        em.set_author(name=f"{self.full_name} {number}", icon_url=logo)
        em.set_thumbnail(url=self.headshot())
        em.description = self.description()
        post_data = [
            [_("Saves"), f"[ {self.saves} ]"],
            [_("Save %"), f"[ {self.save_percentage} ]"],
            [_("GAA"), f"[ {self.goals_against_average} ]"],
            [_("GP"), f"[ {self.games} ]"],
        ]
        stats_md = tabulate(
            post_data, headers=[_("Stats"), f"{self.season[:4]}-{self.season[4:]}"]
        )
        em.set_thumbnail(url=self.headshot())
        em.add_field(name=_("Stats"), value=box(stats_md, lang="apache"))
        return em


@dataclass
class GoaliePlayoffs(Goalie):
    p_time_on_ice: str
    p_ot: int
    p_shutouts: int
    p_ties: int
    p_wins: int
    p_losses: int
    p_saves: int
    p_powerplay_saves: int
    p_shorthanded_saves: int
    p_even_saves: int
    p_shorthanded_shots: int
    p_even_shots: int
    p_powerplay_shots: int
    p_save_percentage: float
    p_goals_against_average: float
    p_games: int
    p_games_started: int
    p_shots_against: int
    p_goals_against: int
    p_time_on_ice_per_game: str
    p_powerplay_save_percentage: float
    p_shorthanded_save_percentage: float
    p_even_strength_save_percentage: float

    def __str__(self) -> str:
        return "{0.full_name}, GAA {0.goals_against_average}, games {0.games}".format(self)

    def __repr__(self) -> str:
        return "<Goalie name={0.full_name} id={0.id} number={0.sweater_number}>".format(self)

    def get_embed(self) -> discord.Embed:
        try:
            team_name = [
                name for name, team in TEAMS.items() if team["id"] == self.current_team_id
            ][0]
            colour = int(TEAMS[team_name]["home"].replace("#", ""), 16)
            logo = TEAMS[team_name]["logo"]
        except IndexError:
            team_name = _("No Team")
            colour = 0xFFFFFF
            logo = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        em = discord.Embed(colour=colour)
        number = f"#{self.sweater_number}" if self.sweater_number else ""
        em.set_author(name=f"{self.full_name} {number}", icon_url=logo)
        em.set_thumbnail(url=self.headshot())
        em.description = self.description()
        post_data = [
            [_("GP"), f"[ {self.games} ]", f"[ {self.p_games} ]"],
            [_("Saves"), f"[ {self.saves} ]", f"[ {self.p_saves} ]"],
            [_("Save %"), f"[ {self.save_percentage} ]", f"[ {self.p_save_percentage} ]"],
            [_("GAA"), f"[ {self.goals_against_average} ]", f"[ {self.p_goals_against_average} ]"],
        ]

        stats_md = tabulate(
            post_data, headers=[_("Stats"), f"{self.season[:4]}-{self.season[4:]}", _("Playoffs")]
        )
        em.set_thumbnail(url=self.headshot())
        em.add_field(name=_("Stats"), value=box(stats_md, lang="apache"))
        return em
