import logging
from datetime import datetime

import aiohttp
import discord

from .constants import BASE_URL, TEAMS

log = logging.getLogger("red.trusty-cogs.Hockey")


class Standings:
    def __init__(
        self,
        name: str,
        division: str,
        conference: str,
        division_rank: int,
        conference_rank: int,
        league_rank: int,
        wins: int,
        losses: int,
        ot: int,
        gp: int,
        pts: int,
        streak: int,
        streak_type: str,
        goals: int,
        gaa: int,
        wc: str,
        last_updated: str,
    ):
        super().__init__()
        self.name = name
        self.division = division
        self.conference = conference
        self.division_rank = division_rank
        self.conference_rank = conference_rank
        self.league_rank = league_rank
        self.wins = wins
        self.losses = losses
        self.ot = ot
        self.gp = gp
        self.pts = pts
        self.streak = streak
        self.streak_type = streak_type
        self.goals = goals
        self.gaa = gaa
        self.wc = wc
        self.last_updated = datetime.strptime(last_updated, "%Y-%m-%dT%H:%M:%SZ")

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "division": self.division_rank,
            "conference": self.conference_rank,
            "division_rank": self.division_rank,
            "conference_rank": self.conference_rank,
            "league_rank": self.league_rank,
            "wins": self.wins,
            "losses": self.losses,
            "ot": self.ot,
            "gp": self.gp,
            "pts": self.pts,
            "streak": self.streak,
            "streak_type": self.streak_type,
            "goals": self.goals,
            "gaa": self.gaa,
            "wc": self.wc,
            "last_updated": self.last_updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @staticmethod
    async def get_team_standings(style):
        """
        Creates a list of standings when given a particular style
        accepts Division names, Conference names, and Team names
        returns a list of standings objects and the location of the given
        style in the list
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL + "/api/v1/standings") as resp:
                data = await resp.json()
        conference = []  # ["eastern", "western", "conference"]
        # The NHL removed conferences from the standings
        division = [
            "central",
            "discover",
            "division",
            "scotia",
            "north",
            "massmutual",
            "east",
            "honda",
            "west"
        ]
        if style.lower() in conference:
            # Leaving this incase it comes back
            e = [
                await Standings.from_json(
                    team, record["division"]["name"], record["conference"]["name"]
                )
                for record in data["records"]
                for team in record["teamRecords"]
                if record["conference"]["name"] == "Eastern"
            ]
            w = [
                await Standings.from_json(
                    team, record["division"]["name"], record["conference"]["name"]
                )
                for record in data["records"]
                for team in record["teamRecords"]
                if record["conference"]["name"] == "Western"
            ]

            index = 0
            for div in [e, w]:
                if div[0].conference.lower() == style and style != "conference":
                    index = [e, w].index(div)
            return [e, w], index
        if style.lower() in division:
            new_list = []
            for record in data["records"]:
                new_list.append(
                    [
                        await Standings.from_json(
                            team, record["division"]["name"], None  # record["conference"]["name"]
                        )
                        for team in record["teamRecords"]
                    ]
                )
            index = 0
            for div in new_list:
                if style in div[0].division.lower() and style != "division":
                    index = new_list.index(div)
            return new_list, index
        else:
            all_teams = [
                await Standings.from_json(
                    team, record["division"]["name"], None  # record["conference"]["name"]
                )
                for record in data["records"]
                for team in record["teamRecords"]
            ]
            index = 0
            for team in all_teams:
                if team.name.lower() == style:
                    index = all_teams.index(team)
            return all_teams, index

    @staticmethod
    async def post_automatic_standings(bot):
        """
        Automatically update a standings embed with the latest stats
        run when new games for the day is updated
        """
        log.debug("Updating Standings.")
        config = bot.get_cog("Hockey").config
        all_guilds = await config.all_guilds()
        for guilds in all_guilds:
            guild = bot.get_guild(guilds)
            if guild is None:
                continue
            log.debug(guild.name)
            if await config.guild(guild).post_standings():

                search = await config.guild(guild).standings_type()
                if search is None:
                    continue
                standings_channel = await config.guild(guild).standings_channel()
                if standings_channel is None:
                    continue
                channel = bot.get_channel(standings_channel)
                if channel is None:
                    continue
                standings_msg = await config.guild(guild).standings_msg()
                if standings_msg is None:
                    continue
                try:
                    message = await channel.fetch_message(standings_msg)
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    await config.guild(guild).post_standings.set(False)
                    continue

                standings, page = await Standings.get_team_standings(search)
                team_stats = standings[page]

                if len(standings) >= 2 and len(standings) < 4:
                    em = await Standings.make_division_standings_embed(team_stats)

                elif len(standings) >= 4 and len(standings) < 31:
                    em = await Standings.make_conference_standings_embed(team_stats)
                else:
                    em = await Standings.all_standing_embed(standings)
                if message is not None:
                    await message.edit(embed=em)

    @classmethod
    async def from_json(cls, data: dict, division: str, conference: str):
        if "streak" in data:
            streak_number = data["streak"]["streakNumber"]
            streak_type = data["streak"]["streakType"]
        else:
            streak_number = 0
            streak_type = 0
        return cls(
            data["team"]["name"],
            division,
            conference,
            data["divisionRank"],
            data["conferenceRank"],
            data["leagueRank"],
            data["leagueRecord"]["wins"],
            data["leagueRecord"]["losses"],
            data["leagueRecord"]["ot"],
            data["gamesPlayed"],
            data["points"],
            streak_number,
            streak_type,
            data["goalsScored"],
            data["goalsAgainst"],
            data["wildCardRank"],
            data["lastUpdated"],
        )

    @staticmethod
    async def all_standing_embed(post_standings):
        """
        Builds the standing embed when all TEAMS are selected
        """
        em = discord.Embed()
        new_dict = {}
        nhl_icon = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        latest_timestamp = post_standings[0].last_updated
        for team in post_standings:
            if team.division not in new_dict:
                new_dict[team.division] = ""
            emoji = TEAMS[team.name]["emoji"]
            wildcard = f"(WC{team.wc})" if team.wc in ["1", "2"] else ""
            new_dict[team.division] += (
                f"{team.division_rank}. <:{emoji}> GP: **{team.gp}** "
                f"W: **{team.wins}** L: **{team.losses}** OT: "
                f"**{team.ot}** PTS: **{team.pts}** {wildcard}\n"
            )
            if team == post_standings[-1]:
                new_dict[team.division] += "\nFrom: https://www.nhl.com/standings"
        for div in new_dict:
            em.add_field(name=f"{div} Division", value=new_dict[div], inline=False)
        em.set_author(
            name="NHL Standings",
            url="https://www.nhl.com/standings",
            icon_url="https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png",
        )
        em.set_thumbnail(url=nhl_icon)
        em.timestamp = latest_timestamp
        em.set_footer(text="Stats Last Updated", icon_url=nhl_icon)
        return em

    @staticmethod
    async def make_division_standings_embed(team_stats):
        em = discord.Embed()
        msg = ""
        # timestamp = datetime.strptime(team_stats[0].last_updated, "%Y-%m-%dT%H:%M:%SZ")
        em.timestamp = team_stats[0].last_updated

        for team in team_stats:
            emoji = TEAMS[team.name]["emoji"]
            msg += (
                f"{team.division_rank}. <:{emoji}> GP: **{team.gp}** "
                f"W: **{team.wins}** L: **{team.losses}** OT: "
                f"**{team.ot}** PTS: **{team.pts}**\n"
            )
        em.description = msg
        division = team_stats[0].division
        division_logo = TEAMS["Team {}".format(division)]["logo"]
        em.colour = int(TEAMS["Team {}".format(division)]["home"].replace("#", ""), 16)
        em.set_author(
            name=division + " Division",
            url="https://www.nhl.com/standings",
            icon_url=division_logo,
        )
        em.set_footer(text="Stats last Updated", icon_url=division_logo)
        em.set_thumbnail(url=division_logo)
        return em

    @staticmethod
    async def make_conference_standings_embed(team_stats):
        em = discord.Embed()
        msg = ""
        newteam_stats = sorted(team_stats, key=lambda k: int(k.conference_rank))
        for team in newteam_stats:
            emoji = TEAMS[team.name]["emoji"]
            msg += (
                f"{team.conference_rank}. <:{emoji}> GP: **{team.gp}** "
                f"W: **{team.wins}** L: **{team.losses}** OT: "
                f"**{team.ot}** PTS: **{team.pts}**\n"
            )
        em.description = msg
        conference = team_stats[0].conference
        em.colour = int("c41230", 16) if conference == "Eastern" else int("003e7e", 16)
        logo = {
            "Eastern": (
                "https://upload.wikimedia.org/wikipedia/en/thumb/1/"
                "16/NHL_Eastern_Conference.svg/1280px-NHL_Eastern_Conference.svg.png"
            ),
            "Western": (
                "https://upload.wikimedia.org/wikipedia/en/thumb/6/"
                "65/NHL_Western_Conference.svg/1280px-NHL_Western_Conference.svg.png"
            ),
        }
        em.set_author(
            name=conference + " Conference",
            url="https://www.nhl.com/standings",
            icon_url=logo[conference],
        )
        em.set_thumbnail(url=logo[conference])
        em.set_footer(text="Stats last Updated", icon_url=logo[conference])
        return em

    @staticmethod
    async def make_team_standings_embed(team_stats):
        em = discord.Embed()
        em.set_author(
            name="# {} {}".format(team_stats.league_rank, team_stats.name),
            url="https://www.nhl.com/standings",
            icon_url=TEAMS[team_stats.name]["logo"],
        )
        em.colour = int(TEAMS[team_stats.name]["home"].replace("#", ""), 16)
        em.set_thumbnail(url=TEAMS[team_stats.name]["logo"])
        em.add_field(name="Division", value="# " + team_stats.division_rank)
        em.add_field(name="Conference", value="# " + team_stats.conference_rank)
        em.add_field(name="Wins", value=team_stats.wins)
        em.add_field(name="Losses", value=team_stats.losses)
        em.add_field(name="OT", value=team_stats.ot)
        em.add_field(name="Points", value=team_stats.pts)
        em.add_field(name="Games Played", value=team_stats.gp)
        em.add_field(name="Goals Scored", value=team_stats.goals)
        em.add_field(name="Goals Against", value=team_stats.gaa)
        em.add_field(
            name="Current Streak",
            value="{} {}".format(team_stats.streak, team_stats.streak_type),
        )
        # timestamp = datetime.strptime(team_stats.last_updated, "%Y-%m-%dT%H:%M:%SZ")
        em.timestamp = team_stats.last_updated
        em.set_footer(text="Stats last Updated", icon_url=TEAMS[team_stats.name]["logo"])
        return em

    @staticmethod
    async def build_standing_embed(post_list, page=0):
        """
        Builds the standings type based on number of items in the list
        """
        team_stats = post_list[page]

        if not isinstance(team_stats, list):
            return await Standings.make_team_standings_embed(team_stats)

        elif len(team_stats) >= 7 and len(team_stats) < 16:
            return await Standings.make_division_standings_embed(team_stats)

        elif len(team_stats) >= 16 and len(team_stats) < 31:
            return await Standings.make_conference_standings_embed(team_stats)
        else:
            return await Standings.all_standing_embed(team_stats)
