import aiohttp
from datetime import datetime
from redbot.core import Config
from .pickems import Pickems
from .constants import BASE_URL, TEAMS
from .goal import Goal
from .helper import utc_to_local, check_to_post, get_team, get_team_role
from .standings import Standings
import discord
import logging
from redbot.core.i18n import Translator
import asyncio


_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


class Game:
    """
        This is the object that handles game information
        game state updates and goal posts
    """

    def __init__(
        self,
        game_state: str,
        home_team: str,
        away_team: str,
        period: int,
        home_shots: int,
        away_shots: int,
        home_score: int,
        away_score: int,
        game_start: str,
        goals: list,
        home_goals: list,
        away_goals: list,
        home_abr: str,
        away_abr: str,
        period_ord: str,
        period_time_left: str,
        plays: list,
        first_star: str,
        second_star: str,
        third_star: str,
        players: dict = None,
    ):
        super().__init__()
        self.game_state = game_state
        self.home_team = home_team
        self.away_team = away_team
        self.home_shots = home_shots
        self.away_shots = away_shots
        self.home_score = home_score
        self.away_score = away_score
        self.goals = goals
        self.home_goals = home_goals
        self.away_goals = away_goals
        self.home_abr = home_abr
        self.away_abr = away_abr
        self.period = period
        self.period_ord = period_ord
        self.period_time_left = period_time_left
        self.plays = plays
        self.game_start = datetime.strptime(game_start, "%Y-%m-%dT%H:%M:%SZ")
        self.home_logo = (
            TEAMS[home_team]["logo"]
            if home_team in TEAMS
            else "https://www-league.nhlstatic.com/images/logos/league-light/133.svg"
        )
        self.away_logo = (
            TEAMS[away_team]["logo"]
            if away_team in TEAMS
            else "https://www-league.nhlstatic.com/images/logos/league-light/133.svg"
        )
        self.home_emoji = (
            "<:{}>".format(TEAMS[home_team]["emoji"])
            if home_team in TEAMS
            else "<:nhl:496510372828807178>"
        )
        self.away_emoji = (
            "<:{}>".format(TEAMS[away_team]["emoji"])
            if away_team in TEAMS
            else "<:nhl:496510372828807178>"
        )
        self.first_star = first_star
        self.second_star = second_star
        self.third_star = third_star
        self.players = players

    def to_json(self) -> dict:
        return {
            "game_state": self.game_state,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_shots": self.home_shots,
            "away_shots": self.away_shots,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "goals": [goal.to_json() for goal in self.goals],
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_abr": self.home_abr,
            "away_abr": self.away_abr,
            "period": self.period,
            "period_ord": self.period_ord,
            "period_time_left": self.period_time_left,
            "plays": self.plays,
            "game_start": self.game_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home_logo": self.home_logo,
            "away_logo": self.away_logo,
            "home_emoji": self.home_emoji,
            "away_emoji": self.away_emoji,
            "first_star": self.first_star,
            "second_star": self.second_star,
            "third_star": self.third_star,
        }

    @staticmethod
    async def get_games(team=None, start_date: datetime = None, end_date: datetime = None):
        """
            Get a specified days games, defaults to the current day
            requires a datetime object
            returns a list of game objects
            if a start date and an end date are not provided to the url
            it returns only todays games

            returns a list of game objects
        """
        games_list = await Game.get_games_list(team, start_date, end_date)
        return_games_list = []
        if games_list != []:
            for games in games_list:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(BASE_URL + games["link"]) as resp:
                            data = await resp.json()
                    # log.debug(BASE_URL + games["link"])
                    return_games_list.append(await Game.from_json(data))
                except Exception:
                    log.error("Error grabbing game data:", exc_info=True)
                    continue
        return return_games_list

    @staticmethod
    async def get_games_list(team=None, start_date: datetime = None, end_date: datetime = None):
        """
            Get a specified days games, defaults to the current day
            requires a datetime object
            returns a list of game objects
            if a start date and an end date are not provided to the url
            it returns only todays games

            returns a list of games
        """
        start_date_str = start_date.strftime("%Y-%m-%d") if start_date is not None else None
        end_date_str = end_date.strftime("%Y-%m-%d") if end_date is not None else None
        if start_date is None and end_date is None:
            # if no dates are provided get todays current schedule
            url = BASE_URL + "/api/v1/schedule"
        elif start_date is None and end_date is not None:
            # if no start date is provided start with today
            start_date_str = datetime.now().strftime("%Y-%m-%d")
            url = f"{BASE_URL}/api/v1/schedule?startDate={start_date_str}&endDate={end_date_str}"
        elif start_date is not None and end_date is None:
            # if no end date is provided carry through to the following year
            end_date_str = str(start_date.year + 1) + start_date.strftime("-%m-%d")
            url = f"{BASE_URL}/api/v1/schedule?startDate={start_date_str}&endDate={end_date_str}"
        else:
            url = f"{BASE_URL}/api/v1/schedule?startDate={start_date_str}&endDate={end_date_str}"
        if team not in ["all", None]:
            # if a team is provided get just that TEAMS data
            url += "&teamId={}".format(TEAMS[team]["id"])
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        game_list = [game for date in data["dates"] for game in date["games"]]
        return game_list

    @staticmethod
    async def get_game_embed(post_list, page):
        """
            Makes the game object from provided URL
        """
        game = post_list[page]

        if type(game) is dict:
            async with aiohttp.ClientSession() as session:
                async with session.get(BASE_URL + game["link"]) as resp:
                    game_json = await resp.json()
            data = await Game.from_json(game_json)
            log.debug(BASE_URL + game["link"])
        else:
            data = game

        return await data.make_game_embed()

    async def make_game_embed(self):
        """
            Builds the game embed when the command is called
            provides as much data as possible
        """
        team_url = (
            TEAMS[self.home_team]["team_url"] if self.home_team in TEAMS else "https://nhl.com"
        )
        # timestamp = datetime.strptime(self.game_start, "%Y-%m-%dT%H:%M:%SZ")
        title = "{away} @ {home} {state}".format(
            away=self.away_team, home=self.home_team, state=self.game_state
        )
        colour = (
            int(TEAMS[self.home_team]["home"].replace("#", ""), 16)
            if self.home_team in TEAMS
            else None
        )

        em = discord.Embed(timestamp=self.game_start)
        if colour is not None:
            em.colour = colour
        em.set_author(name=title, url=team_url, icon_url=self.home_logo)
        em.set_thumbnail(url=self.home_logo)
        em.set_footer(text=_("Game start "), icon_url=self.away_logo)
        if self.game_state == "Preview":
            home_str, away_str = await self.get_stats_msg()
            em.add_field(
                name=f"{self.home_emoji} {self.home_team} {self.home_emoji}", value=home_str
            )
            em.add_field(
                name=f"{self.away_emoji} {self.away_team} {self.away_emoji}", value=away_str
            )
        if self.game_state != "Preview":
            home_msg = (
                _("Goals: **")
                + str(self.home_score)
                + _("** \nShots: **")
                + str(self.home_shots)
                + "**"
            )
            away_msg = (
                _("Goals: **")
                + str(self.away_score)
                + _("** \nShots: **")
                + str(self.away_shots)
                + "**"
            )
            em.add_field(
                name=f"{self.home_emoji} {self.home_team} {self.home_emoji}", value=home_msg
            )
            em.add_field(
                name=f"{self.away_emoji} {self.away_team} {self.away_emoji}", value=away_msg
            )
            if self.goals != []:
                goal_msg = ""
                first_goals = [goal for goal in self.goals if goal.period_ord == "1st"]
                second_goals = [goal for goal in self.goals if goal.period_ord == "2nd"]
                third_goals = [goal for goal in self.goals if goal.period_ord == "3rd"]
                ot_goals = [goal for goal in self.goals if goal.period_ord == "OT"]
                so_goals = [goal for goal in self.goals if goal.period_ord == "SO"]
                list_goals = {
                    "1st": first_goals,
                    "2nd": second_goals,
                    "3rd": third_goals,
                    "OT": ot_goals,
                }
                for goals in list_goals:
                    ordinal = goals
                    goal_msg = ""
                    count = 0
                    for goal in list_goals[ordinal]:
                        if count == 5:
                            em.add_field(
                                name=str(ordinal) + _(" Period Goals"), value=goal_msg[:1024]
                            )
                            count = 0
                            goal_msg = ""
                        emoji = TEAMS[goal.team_name]["emoji"]
                        goal_msg += f"<:{emoji}> {goal.team_name} Goal By {goal.description}\n\n"
                        count += 1
                    if len(list_goals[ordinal]) > 5 and goal_msg != "":
                        em.add_field(
                            name=str(ordinal) + _(" Period Goals (Continued)"),
                            value=goal_msg[:1024],
                        )
                    if len(list_goals[ordinal]) <= 5 and goal_msg != "":
                        em.add_field(name=str(ordinal) + _(" Period Goals"), value=goal_msg[:1024])
                if len(so_goals) != 0:
                    home_msg, away_msg = await self.goals[0].get_shootout_display(self)
                    em.add_field(name=f"{self.home_team}" + _(" Shootout"), value=home_msg)
                    em.add_field(name=f"{self.away_team}" + _(" Shootout"), value=away_msg)
            if self.first_star is not None:
                stars = f"⭐ {self.first_star}\n⭐⭐ {self.second_star}\n⭐⭐⭐ {self.third_star}"
                em.add_field(name=_("Stars of the game"), value=stars)
            if self.game_state == "Live":
                period = self.period_ord
                if self.period_time_left[0].isdigit():
                    msg = (
                        str(self.period_time_left)
                        + _(" Left in the ")
                        + str(period)
                        + _(" period")
                    )
                else:
                    msg = (
                        str(self.period_time_left)
                        + _(" Left in the ")
                        + str(period)
                        + _(" period")
                    )
                em.add_field(name="Period", value=msg)
        return em

    async def game_state_embed(self):
        """
            Makes the game state embed based on the game self provided
        """
        # post_state = ["all", self.home_team, self.away_team]
        # timestamp = datetime.strptime(self.game_start, "%Y-%m-%dT%H:%M:%SZ")
        title = f"{self.away_team} @ {self.home_team} {self.game_state}"
        em = discord.Embed(timestamp=self.game_start)
        home_field = "{0} {1} {0}".format(self.home_emoji, self.home_team)
        away_field = "{0} {1} {0}".format(self.away_emoji, self.away_team)
        if self.game_state != "Preview":
            home_str = (
                _("Goals: **")
                + str(self.home_score)
                + _("** \nShots: **")
                + str(self.home_shots)
                + "**"
            )
            away_str = (
                _("Goals: **")
                + str(self.away_score)
                + _("** \nShots: **")
                + str(self.away_shots)
                + "**"
            )
        else:
            home_str, away_str = await self.get_stats_msg()
        em.add_field(name=home_field, value=home_str, inline=True)
        em.add_field(name=away_field, value=away_str, inline=True)
        colour = (
            int(TEAMS[self.home_team]["home"].replace("#", ""), 16)
            if self.home_team in TEAMS
            else None
        )
        if colour is not None:
            em.colour = colour
        home_url = (
            TEAMS[self.home_team]["team_url"] if self.home_team in TEAMS else "https://nhl.com"
        )
        if self.first_star is not None:
            stars = f"⭐ {self.first_star}\n⭐⭐ {self.second_star}\n⭐⭐⭐ {self.third_star}"
            em.add_field(name=_("Stars of the game"), value=stars)
        em.set_author(name=title, url=home_url, icon_url=self.home_logo)
        em.set_thumbnail(url=self.home_logo)
        em.set_footer(text=_("Game start "), icon_url=self.away_logo)
        return em

    async def game_state_text(self):
        # post_state = ["all", self.home_team, self.away_team]
        # timestamp =  datetime.strptime(self.game_start, "%Y-%m-%dT%H:%M:%SZ")
        time_string = utc_to_local(self.game_start).strftime("%I:%M %p %Z")
        em = (
            f"{self.away_emoji}{self.away_team} @ {self.home_emoji}{self.home_team} "
            f"{self.game_state}\n({time_string})"
        )
        if self.game_state != "Preview":
            em = (
                _("**__Current Score__**\n")
                + f"{self.home_emoji} {self.home_team}: {self.home_score}\n"
                + f"{self.away_emoji} {self.away_team}: {self.away_score}"
            )
        return em

    async def get_stats_msg(self):
        """
            returns team stats on the season from standings object
        """
        msg = "GP:**{gp}** W:**{wins}** L:**{losses}\n**OT:**{ot}** PTS:**{pts}** S:**{streak}**\n"
        streak_types = {"wins": "W", "losses": "L", "ot": "OT"}
        home_str = "GP:**0** W:**0** L:**0\n**OT:**0** PTS:**0** S:**0**\n"
        away_str = "GP:**0** W:**0** L:**0\n**OT:**0** PTS:**0** S:**0**\n"
        try:
            stats, home_i = await Standings.get_team_standings(self.home_team)
            for team in stats:
                if team.name == self.away_team:
                    streak = "{} {}".format(team.streak, streak_types[team.streak_type])
                    away_str = msg.format(
                        wins=team.wins,
                        losses=team.losses,
                        ot=team.ot,
                        pts=team.pts,
                        gp=team.gp,
                        streak=streak,
                    )
                if team.name == self.home_team:
                    streak = "{} {}".format(team.streak, streak_types[team.streak_type])
                    home_str = msg.format(
                        wins=team.wins,
                        losses=team.losses,
                        ot=team.ot,
                        pts=team.pts,
                        gp=team.gp,
                        streak=streak,
                    )
        except Exception:
            pass
        return home_str, away_str

    async def check_game_state(self, bot):
        # post_state = ["all", self.home_team, self.away_team]
        home = await get_team(bot, self.home_team)
        # away = await get_team(self.away_team)
        # team_list = await self.config.teams()
        # Home team checking
        if self.game_state == "Preview":
            """Checks if the the game state has changes from Final to Preview
               Could be unnecessary since after Game Final it will check for next game
            """
            time_now = datetime.utcnow()
            # game_time = datetime.strptime(data.game_start, "%Y-%m-%dT%H:%M:%SZ")
            game_start = (self.game_start - time_now).total_seconds() / 60
            if "Preview" not in home["game_state"]:
                await self.post_game_state(bot)
                await self.save_game_state(bot)
            if game_start < 60 and game_start > 30 and home["game_state"] != "Preview60":
                # Post 60 minutes until game start
                await self.post_time_to_game_start(bot, "60")
                await self.save_game_state(bot, "60")
            if game_start < 30 and game_start > 10 and home["game_state"] != "Preview30":
                # Post 30 minutes until game start
                await self.post_time_to_game_start(bot, "30")
                await self.save_game_state(bot, "30")
            if game_start < 10 and game_start > 0 and home["game_state"] != "Preview10":
                # Post 10 minutes until game start
                await self.post_time_to_game_start(bot, "10")
                await self.save_game_state(bot, "10")

                # Create channel and look for game day thread

        if self.game_state == "Live":
            # Checks what the period is and posts the game is starting in the appropriate channel
            if home["period"] != self.period:
                msg = "**{} Period starting {} at {}**"
                log.debug(msg.format(self.period_ord, self.away_team, self.home_team))
                await self.post_game_state(bot)
                await self.save_game_state(bot)

            if (self.home_score + self.away_score) != 0:
                # Check if there's goals only if there are goals
                await self.check_team_goals(bot)

        if self.game_state == "Final":
            """Final game state checks"""
            if (self.home_score + self.away_score) != 0:
                """ Check for goal before posting game final, happens with OT games"""
                await self.check_team_goals(bot)
            if home["game_state"] != self.game_state and home["game_state"] != "Null":
                # Post game final data and check for next game
                msg = "Game Final {} @ {}"
                log.debug(msg.format(self.home_team, self.away_team))
                await self.post_game_state(bot)
                await self.save_game_state(bot)

    async def post_game_state(self, bot):
        """
            When a game state has changed this is called to create the embed
            and post in all channels
        """
        post_state = ["all", self.home_team, self.away_team]
        state_embed = await self.game_state_embed()
        state_text = await self.game_state_text()
        tasks = []
        for channels in await bot.get_cog("Hockey").config.all_channels():
            channel = bot.get_channel(id=channels)
            if channel is None:
                await bot.get_cog("Hockey").config._clear_scope(Config.CHANNEL, str(channels))
                log.info("{} channel was removed because it no longer exists".format(channels))
                continue
            should_post = await check_to_post(bot, channel, post_state, self.game_state)
            if should_post:
                tasks.append(self.actually_post_state(bot, channel, state_embed, state_text))
        previews = await asyncio.gather(*tasks)
        for preview in previews:
            if preview is None:
                continue
            else:
                await Pickems.create_pickem_object(bot, preview[0].guild, preview[1], preview[0], self)

    async def actually_post_state(self, bot, channel, state_embed, state_text):
        guild = channel.guild
        if not channel.permissions_for(guild.me).send_messages:
            log.debug(_("No permission to send messages in {channel} ({id})").format(
                        channel=channel, id=channel.id
                    ))
            return
        config = bot.get_cog("Hockey").config
        game_day_channels = await config.guild(guild).gdc()
        can_embed = channel.permissions_for(guild.me).embed_links
        # can_manage_webhooks = False  # channel.permissions_for(guild.me).manage_webhooks

        if self.game_state == "Live":

            state_notifications = await config.guild(guild).game_state_notifications()
            if state_notifications:
                home_role, away_role = await get_team_role(guild, self.home_team, self.away_team)
                if state_notifications == "auto" and guild.me.guild_permissions.manage_roles:
                    if home_role != self.home_team:
                        home_role_obj = guild.get_role(int(home_role[3:-1]))
                        if home_role_obj and home_role_obj < guild.me.top_role:
                            await home_role_obj.edit(mentionable=True)
                    if away_role != self.away_team:
                        away_role_obj = guild.get_role(int(away_role[3:-1]))
                        if away_role_obj and away_role_obj < guild.me.top_role:
                            await away_role_obj.edit(mentionable=True)
            if not state_notifications:
                home_role = self.home_team
                away_role = self.away_team

            if game_day_channels is not None:
                # We don't want to ping people in the game day channels twice
                if channel.id in game_day_channels:
                    home_role, away_role = self.home_team, self.away_team
            msg = (
                "**"
                + str(self.period_ord)
                + _(" Period starting ")
                + away_role
                + _(" at ")
                + home_role
                + "**"
            )
            try:
                if not can_embed:
                    await channel.send(msg + "\n{}".format(state_text))
                else:
                    await channel.send(msg, embed=state_embed)
            except Exception:
                log.error(
                    _("Could not post goal in {channel} ({id})").format(
                        channel=channel, id=channel.id
                    ),
                    exc_info=True,
                )
            if state_notifications == "auto" and guild.me.guild_permissions.manage_roles:
                if home_role != self.home_team:
                    home_role_obj = guild.get_role(int(home_role[3:-1]))
                    if home_role_obj and home_role_obj < guild.me.top_role:
                        await home_role_obj.edit(mentionable=False)
                if away_role != self.away_team:
                    away_role_obj = guild.get_role(int(away_role[3:-1]))
                    if away_role_obj and away_role_obj < guild.me.top_role:
                        await away_role_obj.edit(mentionable=False)

        else:
            if self.game_state == "Preview":
                if game_day_channels is not None:
                    # Don't post the preview message twice in the channel
                    if channel.id in game_day_channels:
                        return
            try:
                if not can_embed:
                    preview_msg = await channel.send(state_text)
                else:
                    preview_msg = await channel.send(embed=state_embed)

                # Create new pickems object for the game
                if self.game_state == "Preview":
                    if channel.permissions_for(guild.me).add_reactions:
                        try:
                            await preview_msg.add_reaction(self.away_emoji[2:-1])
                            await preview_msg.add_reaction(self.home_emoji[2:-1])
                        except Exception:
                            log.debug("Could not add reactions")
                        return channel, preview_msg
            except Exception:
                log.error(
                    _("Could not post goal in {channel} ({id})").format(
                        channel=channel, id=channel.id
                    ),
                    exc_info=True,
                )

    async def check_team_goals(self, bot):
        """
            Checks to see if a goal needs to be posted
        """
        home_team_data = await get_team(bot, self.home_team)
        away_team_data = await get_team(bot, self.away_team)
        # all_data = await get_team("all")
        team_list = await bot.get_cog("Hockey").config.teams()
        # post_state = ["all", self.home_team, self.away_team]

        # home_goal_ids = [goal.goal_id for goal in self.home_goals]
        # away_goal_ids = [goal.goal_id for goal in self.away_goals]

        home_goal_list = list(home_team_data["goal_id"])
        away_goal_list = list(away_team_data["goal_id"])

        for goal in self.goals:
            # goal_id = str(goal["result"]["eventCode"])
            # team = goal["team"]["name"]
            team_data = await get_team(bot, goal.team_name)
            if goal.goal_id not in team_data["goal_id"]:
                # attempts to post the goal if there is a new goal
                msg_list = await goal.post_team_goal(bot, self)
                team_list.remove(team_data)
                team_data["goal_id"][goal.goal_id] = {"goal": goal.to_json(), "messages": msg_list}
                team_list.append(team_data)
                await bot.get_cog("Hockey").config.teams.set(team_list)
                continue
            if goal.goal_id in team_data["goal_id"]:
                # attempts to edit the goal if the scorers have changed
                old_goal = Goal(**team_data["goal_id"][goal.goal_id]["goal"])
                if goal.description != old_goal.description:
                    old_msgs = team_data["goal_id"][goal.goal_id]["messages"]
                    team_list.remove(team_data)
                    team_data["goal_id"][goal.goal_id]["goal"] = goal.to_json()
                    team_list.append(team_data)
                    await bot.get_cog("Hockey").config.teams.set(team_list)
                    await goal.edit_team_goal(bot, self, old_msgs)
        # attempts to delete the goal if it was called back
        for goal_str in home_goal_list:
            await Goal.remove_goal_post(bot, goal_str, self.home_team, self)
        for goal_str in away_goal_list:
            await Goal.remove_goal_post(bot, goal_str, self.away_team, self)

    async def save_game_state(self, bot, time_to_game_start: str = "0"):
        """
            Saves the data do the config to compare against new data
        """
        home = await get_team(bot, self.home_team)
        away = await get_team(bot, self.away_team)
        team_list = await bot.get_cog("Hockey").config.teams()
        team_list.remove(home)
        team_list.remove(away)
        if self.game_state != "Final":
            if self.game_state == "Preview" and time_to_game_start != "0":
                home["game_state"] = self.game_state + time_to_game_start
                away["game_state"] = self.game_state + time_to_game_start
            else:
                home["game_state"] = self.game_state
                away["game_state"] = self.game_state
            home["period"] = self.period
            away["period"] = self.period
            home["game_start"] = self.game_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            away["game_start"] = self.game_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            home["game_state"] = "Null"
            away["game_state"] = "Null"
            home["period"] = 0
            away["period"] = 0
            home["goal_id"] = {}
            away["goal_id"] = {}
            home["game_start"] = ""
            away["game_start"] = ""
        team_list.append(home)
        team_list.append(away)
        await bot.get_cog("Hockey").config.teams.set(team_list)

    async def post_time_to_game_start(self, bot, time_left):
        """
            Post when there is 60, 30, and 10 minutes until the game starts in all channels
        """
        post_state = ["all", self.home_team, self.away_team]
        msg = _(
                "{time} minutes until {away_emoji} {away} @ {home_emoji} {home} starts!"
            ).format(
                time=time_left,
                away_emoji=self.away_emoji,
                away=self.away_team,
                home_emoji=self.home_emoji,
                home=self.home_team,
            )
        tasks = []
        for channels in await bot.get_cog("Hockey").config.all_channels():
            channel = bot.get_channel(id=channels)
            if channel is None:
                await bot.get_cog("Hockey").config._clear_scope(Config.CHANNEL, str(channels))
                log.info("{} channel was removed because it no longer exists".format(channels))
                continue

            should_post = await check_to_post(bot, channel, post_state, self.game_state)
            team_to_post = await bot.get_cog("Hockey").config.channel(channel).team()
            if should_post and "all" not in team_to_post:
                tasks.append(self.post_game_start(channel, msg))
        await asyncio.gather(*tasks)

    async def post_game_start(self, channel, msg):
        if not channel.permissions_for(channel.guild.me).send_messages:
            log.debug(_("No permission to send messages in {channel} ({id})").format(
                        channel=channel, id=channel.id
                    ))
            return
        try:
            await channel.send(msg)
        except Exception:
            log.error(
                _("Could not post goal in {channel} ({id})").format(
                    channel=channel, id=channel.id
                ),
                exc_info=True,
            )

    @staticmethod
    async def from_url(url: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(BASE_URL + url) as resp:
                    data = await resp.json()
            return await Game.from_json(data)
        except Exception:
            log.error(_("Error grabbing game data: "), exc_info=True)
            return

    @classmethod
    async def from_json(cls, data: dict):
        event = data["liveData"]["plays"]["allPlays"]
        home_team = data["gameData"]["teams"]["home"]["name"]
        away_team = data["gameData"]["teams"]["away"]["name"]
        players = data["liveData"]["boxscore"]["teams"]["away"]["players"]
        players.update(data["liveData"]["boxscore"]["teams"]["home"]["players"])
        goals = [
            await Goal.from_json(goal, players)
            for goal in event
            if goal["result"]["eventTypeId"] == "GOAL"
            or (
                goal["result"]["eventTypeId"] in ["SHOT", "MISSED_SHOT"]
                and goal["about"]["ordinalNum"] == "SO"
            )
        ]

        if "currentPeriodOrdinal" in data["liveData"]["linescore"]:
            period_ord = data["liveData"]["linescore"]["currentPeriodOrdinal"]
            period_time_left = data["liveData"]["linescore"]["currentPeriodTimeRemaining"]
            events = data["liveData"]["plays"]["allPlays"]
        else:
            period_ord = "0"
            period_time_left = "0"
            events = ["."]
        decisions = data["liveData"]["decisions"]
        first_star = decisions["firstStar"]["fullName"] if "firstStar" in decisions else None
        second_star = decisions["secondStar"]["fullName"] if "secondStar" in decisions else None
        third_star = decisions["thirdStar"]["fullName"] if "thirdStar" in decisions else None

        return cls(
            data["gameData"]["status"]["abstractGameState"],
            data["gameData"]["teams"]["home"]["name"],
            data["gameData"]["teams"]["away"]["name"],
            data["liveData"]["linescore"]["currentPeriod"],
            data["liveData"]["linescore"]["teams"]["home"]["shotsOnGoal"],
            data["liveData"]["linescore"]["teams"]["away"]["shotsOnGoal"],
            data["liveData"]["linescore"]["teams"]["home"]["goals"],
            data["liveData"]["linescore"]["teams"]["away"]["goals"],
            data["gameData"]["datetime"]["dateTime"],
            goals,
            [goal for goal in goals if home_team in goal.team_name],
            [goal for goal in goals if away_team in goal.team_name],
            data["gameData"]["teams"]["home"]["abbreviation"],
            data["gameData"]["teams"]["away"]["abbreviation"],
            period_ord,
            period_time_left,
            events,
            first_star,
            second_star,
            third_star,
            players
        )
