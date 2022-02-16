from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import discord
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter

from .constants import HEADSHOT_URL, TEAMS
from .helper import check_to_post, get_channel_obj, get_team

if TYPE_CHECKING:
    from .game import Game

try:
    from .oilers import Oilers
except ImportError:
    pass


_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


class Goal:

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

    def __init__(self, **kwargs):
        super().__init__()
        self.goal_id = kwargs.get("goal_id")
        self.team_name = kwargs.get("team_name")
        self.scorer_id = kwargs.get("scorer_id")
        self.headshot = HEADSHOT_URL.format(kwargs.get("scorer_id", ""))
        self.jersey_no = kwargs.get("jersey_no")
        self.description = kwargs.get("description")
        self.period = kwargs.get("period")
        self.period_ord = kwargs.get("period_ord")
        self.time_remaining = kwargs.get("time_remaining")
        time = kwargs.get("time", "")
        time = datetime.strptime(time, "%Y-%m-%dT%H:%M:%SZ")
        self.time = time.replace(tzinfo=timezone.utc)
        self.home_score = kwargs.get("home_score")
        self.away_score = kwargs.get("away_score")
        self.strength = kwargs.get("strength")
        self.strength_code = kwargs.get("strength_code")
        self.empty_net = kwargs.get("empty_net")
        self.event = kwargs.get("event")
        self.link = kwargs.get("link", None)
        self.tasks: List[asyncio.Task] = []
        self.home_shots: int = kwargs.get("home_shots", 0)
        self.away_shots: int = kwargs.get("away_shots", 0)

    def __repr__(self):
        return "<Hockey Goal team={0.team_name} id={0.goal_id} >".format(self)

    def to_json(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "team_name": self.team_name,
            "scorer_id": self.scorer_id,
            "jersey_no": self.jersey_no,
            "description": self.description,
            "period": self.period,
            "period_ord": self.period_ord,
            "time_remaining": self.time_remaining,
            "time": self.time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home_score": self.home_score,
            "away_score": self.away_score,
            "strength": self.strength,
            "empty_net": self.empty_net,
            "event": self.event,
            "link": self.link,
            "home_shots": self.home_shots,
            "away_shots": self.away_shots,
        }

    @classmethod
    async def from_json(
        cls, data: dict, players: dict, media_content: Optional[dict] = None
    ) -> Goal:
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
        if media_content:
            event_id = data["about"]["eventId"]
            try:
                for highlight in media_content["media"]["milestones"]["items"]:
                    if highlight["statsEventId"] == str(event_id):
                        for playback in highlight["highlight"]["playbacks"]:
                            if playback["name"] == "FLASH_1800K_896x504":
                                link = playback["url"]
            except KeyError:
                pass

        # scorer = scorer_id[0]
        return cls(
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
            home_shots=data.get("home_shots", 0),
            away_shots=data.get("away_shots", 0),
        )

    @property
    def timestamp(self) -> int:
        """
        This is just a helper property to return
        the timestamp in which this goal was scored for simply
        using inside discords new timestamps.
        """
        return int(self.time.timestamp())

    async def post_team_goal(self, bot: Red, game_data: Game) -> List[Tuple[int, int, int]]:
        """
        Creates embed and sends message if a team has scored a goal
        """
        # scorer = self.headshots.format(goal["players"][0]["player"]["id"])
        post_state = ["all", game_data.home_team, game_data.away_team]
        msg_list = []
        if "Edmonton Oilers" in self.team_name and "missed" not in self.event.lower():
            try:
                hue = Oilers(bot)
                self.tasks.append(hue.goal_lights())
            except Exception:
                pass
        goal_embed = await self.goal_post_embed(game_data)
        goal_text = await self.goal_post_text(game_data)
        tasks = []
        all_channels = await bot.get_cog("Hockey").config.all_channels()
        post_data = []
        async for channel_id, data in AsyncIter(all_channels.items(), steps=100):
            channel = await get_channel_obj(bot, channel_id, data)
            if not channel:
                continue
            if channel.guild.me.is_timed_out():
                return
            should_post = await check_to_post(bot, channel, data, post_state, "Goal")
            if should_post:
                post_data.append(
                    await self.actually_post_goal(bot, channel, goal_embed, goal_text)
                )
        # data = await bounded_gather(*tasks)
        for channel in post_data:
            if channel is None:
                continue
            else:
                msg_list.append(channel)
        return msg_list

    async def actually_post_goal(
        self, bot: Red, channel: discord.TextChannel, goal_embed: discord.Embed, goal_text: str
    ) -> Optional[Tuple[int, int, int]]:
        try:
            guild = channel.guild
            if not channel.permissions_for(guild.me).send_messages:
                log.debug("No permission to send messages in %s", repr(channel))
                return None

            config = bot.get_cog("Hockey").config
            game_day_channels = await config.guild(guild).gdc()
            # Don't want to ping people in the game day channels
            can_embed = channel.permissions_for(guild.me).embed_links
            can_manage_webhooks = False  # channel.permissions_for(guild.me).manage_webhooks
            role = None
            guild_notifications = await config.guild(guild).goal_notifications()
            channel_notifications = await config.channel(channel).goal_notifications()
            goal_notifications = guild_notifications or channel_notifications
            # publish_goals = "Goal" in await config.channel(channel).publish_states()
            allowed_mentions = {}
            montreal = ["Montréal Canadiens", "Montreal Canadiens"]

            role = discord.utils.get(guild.roles, name=f"{self.team_name} GOAL")
            try:
                if self.team_name in montreal:
                    if not role:
                        montreal.remove(self.team_name)
                        role = discord.utils.get(guild.roles, name=f"{montreal[0]} GOAL")
            except Exception:
                log.error("Error trying to find montreal goal role")
            if goal_notifications:
                log.debug(goal_notifications)
                allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=True)}
            else:
                allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}

            if game_day_channels is not None:
                # We don't want to ping people in the game day channels twice
                if channel.id in game_day_channels:
                    role = None

            if not can_embed and can_manage_webhooks:
                # try to create a webhook with the teams info to bypass embed permissions
                # Waiting for d.py to return messages from webhook responses
                # After testing it doesn't look as nice as I would like
                # Will leave it off until at some point I can make it look better
                webhook = None
                for hook in await channel.webhooks():
                    if hook.name == guild.me.name:
                        webhook = hook
                if webhook is None:
                    webhook = await channel.create_webhook(name=guild.me.name)
                url = TEAMS[self.team_name]["logo"]
                await webhook.send(username=self.team_name, avatar_url=url, embed=goal_embed)
                return None

            if not can_embed and not can_manage_webhooks:
                # Create text only message if embed_links permission is not set
                if role is not None:
                    msg = await channel.send(f"{role}\n{goal_text}", **allowed_mentions)
                else:
                    msg = await channel.send(goal_text)
                # msg_list[str(channel.id)] = msg.id

            if role is None or "missed" in self.event.lower():
                msg = await channel.send(embed=goal_embed)
                # msg_list[str(channel.id)] = msg.id

            else:
                msg = await channel.send(role.mention, embed=goal_embed, **allowed_mentions)
                # msg_list[str(channel.id)] = msg.id
            return channel.guild.id, channel.id, msg.id
        except Exception:
            log.exception("Could not post goal in %s", repr(channel))
            return None

    @staticmethod
    async def remove_goal_post(bot: Red, goal: str, team: str, data: Game) -> None:
        """
        Attempt to delete a goal if it was pulled back
        """
        config = bot.get_cog("Hockey").config
        team_list = await config.teams()
        team_data = await get_team(bot, team)
        if goal not in [goal.goal_id for goal in data.goals]:
            try:
                old_msgs = team_data["goal_id"][goal]["messages"]
            except KeyError:
                return
            except Exception:
                log.exception("Error iterating saved goals")
                return
            for guild_id, channel_id, message_id in old_msgs:
                guild = bot.get_guild(int(guild_id))
                if not guild:
                    continue
                channel = await get_channel_obj(bot, int(channel_id), {"guild_id": int(guild_id)})
                if channel and channel.permissions_for(channel.guild.me).read_message_history:
                    try:
                        message = channel.get_partial_message(message_id)
                    except (discord.errors.NotFound, discord.errors.Forbidden):
                        continue
                    except Exception:
                        log.exception(
                            f"Error getting old goal for {str(team)} {str(goal)} in "
                            f"{guild_id=} {channel_id=}"
                        )
                        pass
                    if message is not None:
                        try:
                            await message.delete()
                        except (discord.errors.NotFound, discord.errors.Forbidden):
                            pass
                        except Exception:
                            log.exception(
                                f"Error getting old goal for {str(team)} {str(goal)} in "
                                f"{guild_id=} {channel_id=}"
                            )
                else:
                    log.debug("Channel does not have permission to read history")
            try:
                team_list.remove(team_data)
                del team_data["goal_id"][goal]
                team_list.append(team_data)
                await config.teams.set(team_list)
            except Exception:
                log.exception("Error removing teams goals")
                return
        return

    async def edit_team_goal(
        self, bot: Red, game_data: Game, og_msg: Tuple[int, int, int]
    ) -> None:
        """
        When a goal scorer has changed we want to edit the original post
        """
        # scorer = self.headshots.format(goal["players"][0]["player"]["id"])
        # post_state = ["all", game_data.home_team, game_data.away_team]
        em = await self.goal_post_embed(game_data)
        async for guild_id, channel_id, message_id in AsyncIter(og_msg, steps=100):
            guild = bot.get_guild(guild_id)
            if not guild:
                continue
            channel = await get_channel_obj(bot, int(channel_id), {"guild_id": int(guild_id)})
            if channel is None:
                continue
            bot.loop.create_task(self.edit_goal(bot, channel, message_id, em))
            # This is to prevent endlessly waiting incase someone
            # decided to publish one of our messages we want to edit
            # if we did bounded_gather here the gather would wait until
            # rate limits are up for editing that one message
            # in this case we can send off the task to do it's thing
            # and forget about it. If one never finishes I don't care

        return

    async def edit_goal(
        self,
        bot: Red,
        channel: Union[discord.TextChannel, discord.Thread],
        message_id: int,
        em: discord.Embed,
    ) -> None:
        try:
            if not channel.permissions_for(channel.guild.me).embed_links:
                return
            if channel.guild.me.is_timed_out():
                return
            try:
                message = channel.get_partial_message(message_id)
            except (discord.errors.NotFound, discord.errors.Forbidden):
                return
            guild = channel.guild
            game_day_channels = await bot.get_cog("Hockey").config.guild(guild).gdc()
            role = discord.utils.get(guild.roles, name=self.team_name + " GOAL")
            if game_day_channels is not None:
                # We don't want to ping people in the game day channels twice
                if channel.id in game_day_channels:
                    role = None
            if role is None or "missed" in self.event.lower():
                await message.edit(embed=em)
            else:
                await message.edit(content=role.mention, embed=em)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            return
        except Exception:
            log.exception("Could not edit goal in %s", repr(channel))

    async def get_shootout_display(self, game: Game) -> Tuple[str, str]:
        """
        Gets a string for the shootout display
        """
        home_msg = ""
        away_msg = ""
        score = "☑ {scorer}\n"
        miss = "❌ {scorer}\n"
        players = game.home_roster
        players.update(game.away_roster)
        for goal in game.home_goals:
            scorer = ""
            scorer_num = ""
            if goal.time > self.time:
                break
            if f"ID{goal.scorer_id}" in players:
                scorer = players[f"ID{goal.scorer_id}"]["person"]["fullName"]
            if goal.event in ["Shot", "Missed Shot"] and goal.period_ord == "SO":
                home_msg += miss.format(scorer=scorer)
            if goal.event in ["Goal"] and goal.period_ord == "SO":
                home_msg += score.format(scorer=scorer)

        for goal in game.away_goals:
            scorer = ""
            if goal.time > self.time:
                # if the goal object building this shootout display
                # is in the shootout and we reach a goal that happened *after*
                # this goal object, we break for a cleaner looking shootout display.
                break
            if f"ID{goal.scorer_id}" in players:
                scorer = players[f"ID{goal.scorer_id}"]["person"]["fullName"]
            if goal.event in ["Shot", "Missed Shot"] and goal.period_ord == "SO":
                away_msg += miss.format(scorer=scorer)
            if goal.event in ["Goal"] and goal.period_ord == "SO":
                away_msg += score.format(scorer=scorer)

        return home_msg, away_msg

    async def goal_post_embed(self, game: Game) -> discord.Embed:
        """
        Gets the embed for goal posts
        """
        # h_emoji = game.home_emoji
        # a_emoji = game.away_emoji
        shootout = False
        if game.period_ord == "SO":
            shootout = True
        colour = (
            int(TEAMS[self.team_name]["home"].replace("#", ""), 16)
            if self.team_name in TEAMS
            else 0
        )
        empty_net = _("Empty Net ") if self.empty_net else ""
        title = f"🚨 {self.team_name} #{self.jersey_no} {empty_net}{self.strength} {self.event} 🚨"
        url = TEAMS[self.team_name]["team_url"] if self.team_name in TEAMS else "https://nhl.com"
        logo = TEAMS[self.team_name]["logo"] if self.team_name in TEAMS else "https://nhl.com"
        if not shootout:

            em = discord.Embed(description=f"{self.description}\n<t:{self.timestamp}:T>")
            if self.link:
                em.description = f"[{self.description}\n<t:{self.timestamp}:T>]({self.link})"
            if colour is not None:
                em.colour = colour
            em.set_author(name=title, url=url, icon_url=logo)
            home_str = _("Goals: **{home_score}**\nShots: **{home_shots}**").format(
                home_score=self.home_score, home_shots=self.home_shots
            )
            away_str = _("Goals: **{away_score}**\nShots: **{away_shots}**").format(
                away_score=self.away_score, away_shots=self.away_shots
            )
            home_field = f"{game.home_emoji} {game.home_team} {game.home_emoji}"
            away_field = f"{game.away_emoji} {game.away_team} {game.away_emoji}"
            em.add_field(name=home_field, value=home_str, inline=True)
            em.add_field(name=away_field, value=away_str, inline=True)
            em.set_footer(
                text=_("{time_remaining} left in the {period_ord} period").format(
                    time_remaining=self.time_remaining, period_ord=self.period_ord
                ),
                icon_url=logo,
            )
            em.timestamp = self.time
        else:
            if "missed" in self.event.lower():
                em = discord.Embed(description=self.description, colour=colour)
                em.set_author(name=title.replace("🚨", ""), url=url, icon_url=logo)
            else:
                em = discord.Embed(description=self.description, colour=colour)
                em.set_author(name=title, url=url, icon_url=logo)
            home_msg, away_msg = await self.get_shootout_display(game)
            if home_msg:
                em.add_field(name=game.home_team, value=home_msg)
            if away_msg:
                em.add_field(name=game.away_team, value=away_msg)
            em.set_footer(
                text=str(game.period_time_left)
                + _(" left in the ")
                + str(game.period_ord)
                + _(" period"),
                icon_url=logo,
            )
            em.timestamp = self.time
        return em

    async def goal_post_text(self, game: Game) -> str:
        """
        Gets the text to send for goal posts
        """
        if game.period_ord != "SO":
            text = (
                f"{game.home_emoji} {game.home_team}: {game.home_score}\n"
                f"{game.away_emoji} {game.away_team}: {game.away_score}\n "
            )
            text += _("{time_remaining} left in the {period_ord} period").format(
                time_remaining=self.time_remaining, period_ord=self.period_ord
            )
        else:
            home_msg, away_msg = await self.get_shootout_display(game)
            text = (
                f"{game.home_emoji} {game.home_team}: {home_msg}\n"
                f"{game.away_emoji} {game.away_team}: {away_msg}\n "
            )
            text += _("{time_remaining} left in the {period_ord} period").format(
                time_remaining=self.time_remaining, period_ord=self.period_ord
            )
        return text
