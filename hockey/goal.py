from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import discord
from red_commons.logging import getLogger
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_list

from .helper import Team, check_to_post, get_channel_obj, get_team

if TYPE_CHECKING:
    from yarl import URL

    from .api import GameEventTypeCode, GoalData, Player
    from .game import Game
    from .hockey import Hockey


_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")


class Goal:
    def __init__(self, **kwargs):
        super().__init__()
        self.goal_id = kwargs.get("goal_id")
        self.team: Team = kwargs.get("team")
        self.scorer_id = kwargs.get("scorer_id")
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
        self.link: Optional[Union[str, URL]] = kwargs.get("link", None)
        self.image = kwargs.get("image", None)
        self.tasks: List[asyncio.Task] = []
        self.home_shots: int = kwargs.get("home_shots", 0)
        self.away_shots: int = kwargs.get("away_shots", 0)
        self.situation = kwargs.get("situation")
        self.scorer: Player = kwargs.get("scorer")
        self.assisters: List[Player] = kwargs.get("assisters")
        self.game_id: int = kwargs.get("game_id")
        self.type_code: GameEventTypeCode = kwargs.get("type_code")
        self.nhle_event = kwargs.get("nhle_event")

    def __repr__(self):
        return "<Hockey Goal team={0.team_name} id={0.goal_id} >".format(self)

    @property
    def team_name(self):
        return self.team.name

    @property
    def emoji(self) -> Union[discord.PartialEmoji, str]:
        return self.team.emoji

    def __eq__(self, other) -> bool:
        if not isinstance(other, Goal):
            return False
        if (
            self.description == other.description
            and str(self.link) == str(other.link)
            # if one of these is a URL then the standard == will be false causing
            # us to constantly try and edit goals we've already edited.
            # So instead, let's just cast to string.
            and self.goal_id == other.goal_id
        ):
            return True
        return False

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

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
            "link": str(self.link) if self.link is not None else None,
            "image": self.image,
            "home_shots": self.home_shots,
            "away_shots": self.away_shots,
            "game_id": self.game_id,
        }

    @classmethod
    def from_data(cls, data: GoalData):
        return cls(**data)

    @staticmethod
    def get_image_and_highlight_url(
        event_id: int, media_content: dict
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
        image = None
        if media_content:
            event_id = data["about"]["eventId"]
            link, image = cls.get_image_and_highlight_url(event_id, media_content)

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
            image=image,
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
        cog: Hockey = bot.get_cog("Hockey")
        event = cog.get_goal_save_event(game_data.game_id, str(self.goal_id), False)
        post_state = ["all", game_data.home_team, game_data.away_team]
        msg_list = []
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
                continue
            should_post = await check_to_post(
                bot, channel, data, post_state, game_data.game_state, True
            )
            if should_post:
                tasks.append(channel)
        async for channel in AsyncIter(tasks, delay=5, steps=5):
            post_data.append(await self.actually_post_goal(bot, channel, goal_embed, goal_text))
        # data = await bounded_gather(*tasks)
        for channel in post_data:
            if channel is None:
                continue
            else:
                msg_list.append(channel)
        config = cog.config
        async with config.teams() as teams:
            for team in teams:
                if team["team_name"] == self.team_name and team["game_id"] == game_data.game_id:
                    try:
                        team["goal_id"][str(self.goal_id)]["messages"] = msg_list
                    except KeyError:
                        log.error("Error saving message list for goal %r", self)
        event.set()
        return msg_list

    async def actually_post_goal(
        self, bot: Red, channel: discord.TextChannel, goal_embed: discord.Embed, goal_text: str
    ) -> Optional[Tuple[int, int, int]]:
        try:
            guild = channel.guild
            if not channel.permissions_for(guild.me).send_messages:
                log.debug("No permission to send messages in %r", channel)
                return None

            config = bot.get_cog("Hockey").config
            game_day_channels = await config.guild(guild).gdc()
            game_day_threads = await config.guild(guild).gdt()
            # Don't want to ping people in the game day channels
            can_embed = channel.permissions_for(guild.me).embed_links
            can_manage_webhooks = False  # channel.permissions_for(guild.me).manage_webhooks
            role = None

            guild_image_setting = await config.guild(guild).include_goal_image()
            channel_image_setting = await config.channel(channel).include_goal_image()
            include_goal_image = guild_image_setting or channel_image_setting
            send_em = goal_embed.copy()
            if include_goal_image and self.image:
                send_em.set_image(url=self.image)
            # publish_goals = "Goal" in await config.channel(channel).publish_states()

            montreal = ["Montréal Canadiens", "Montreal Canadiens"]
            roles = set()
            team_role = discord.utils.get(guild.roles, name=f"{self.team_name} GOAL")
            if team_role is None and self.team_name in montreal:
                # Special lookup for Canadiens without the accent
                for name in montreal:
                    team_role = discord.utils.get(guild.roles, name=f"{name} GOAL")
                    if team_role is not None:
                        break
            if team_role is not None:
                roles.add(team_role.mention)
            goal_roles = await config.channel(channel).game_goal_roles()
            mention_roles = set()

            for team, role_ids in goal_roles.items():
                if team not in ["all", self.team_name]:
                    continue
                for role_id in role_ids:
                    if role := guild.get_role(role_id):
                        mention_roles.add(role)
                        roles.add(role.mention)
            allowed_mentions = discord.AllowedMentions(roles=list(mention_roles))
            roles_text = humanize_list(list(roles))
            if game_day_channels is not None:
                # We don't want to ping people in the game day channels twice
                if channel.id in game_day_channels:
                    role = None

            if game_day_threads is not None:
                if channel.id in game_day_threads:
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
                logo = self.team.logo
                await webhook.send(username=self.team_name, avatar_url=logo, embed=goal_embed)
                return None

            if not can_embed and not can_manage_webhooks:
                # Create text only message if embed_links permission is not set
                if roles_text:
                    msg = await channel.send(
                        f"{roles_text}\n{goal_text}", allowed_mentions=allowed_mentions
                    )
                else:
                    msg = await channel.send(goal_text)
                # msg_list[str(channel.id)] = msg.id

            if not roles_text or "missed" in self.event.lower():
                msg = await channel.send(embed=send_em)
                # msg_list[str(channel.id)] = msg.id

            else:
                msg = await channel.send(
                    roles_text, embed=send_em, allowed_mentions=allowed_mentions
                )
                # msg_list[str(channel.id)] = msg.id
            return channel.guild.id, channel.id, msg.id
        except Exception:
            log.exception("Could not post goal in %s", repr(channel))
            return None

    @staticmethod
    async def remove_goal_post(bot: Red, goal_id: str, team: str, data: Game) -> None:
        """
        Attempt to delete a goal if it was pulled back
        """
        log.trace("Removing goal %s from game %s", goal_id, data)
        cog: Hockey = bot.get_cog("Hockey")
        config = cog.config
        event = cog.get_goal_save_event(data.game_id, str(goal_id), True)
        await event.wait()
        team_data = await get_team(bot, team, data.game_start_str, data.game_id)
        if str(goal_id) not in [str(goal.goal_id) for goal in data.goals]:
            try:
                old_msgs = team_data["goal_id"][goal_id]["messages"]
            except KeyError:
                return
            except Exception:
                log.exception("Error iterating saved goals")
                return
            msgs = []
            for guild_id, channel_id, message_id in old_msgs:
                guild = bot.get_guild(int(guild_id))
                if not guild:
                    continue
                channel = await get_channel_obj(bot, int(channel_id), {"guild_id": int(guild_id)})
                if not channel:
                    continue
                if not channel.permissions_for(channel.guild.me).read_message_history:
                    continue
                msgs.append(channel.get_partial_message(message_id))

            async for message in AsyncIter(msgs, delay=5, steps=5):
                try:
                    await message.delete()
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    pass
                except Exception:
                    log.exception(
                        "Error getting old goal for %s %s in guild=%s channel=%s",
                        team,
                        goal_id,
                        message.guild.id,
                        message.channel.id,
                    )

            async with config.teams() as team_entries:
                for team_entry in team_entries:
                    if team_entry["team_name"] == team and team_entry["game_id"] == data.game_id:
                        try:
                            del team_entry["goal_id"][goal_id]
                        except KeyError:
                            log.exception("Error removing teams goals")
                            continue
        return

    async def edit_team_goal(self, bot: Red, game_data: Game) -> None:
        """
        When a goal scorer has changed we want to edit the original post
        """
        # scorer = self.headshots.format(goal["players"][0]["player"]["id"])
        # post_state = ["all", game_data.home_team, game_data.away_team]
        cog: Hockey = bot.get_cog("Hockey")
        event = cog.get_goal_save_event(game_data.game_id, str(self.goal_id), True)
        await event.wait()
        # Wait until the initial posting has fully completed before continuing to edit
        og_msg = []
        old_data = await get_team(bot, self.team_name, game_data.game_start_str, self.game_id)
        og_msg = old_data["goal_id"].get(str(self.goal_id), {}).get("messages")
        updated_goal = cog.get_current_goal(game_data.game_id, self.goal_id)
        em = await updated_goal.goal_post_embed(game_data)
        text = await updated_goal.goal_post_text(game_data)
        if og_msg is None:
            return
        async for guild_id, channel_id, message_id in AsyncIter(og_msg, delay=5, steps=5):
            guild = bot.get_guild(int(guild_id))
            if not guild:
                continue
            channel = await get_channel_obj(bot, int(channel_id), {"guild_id": int(guild_id)})
            if channel is None:
                continue
            if datetime.now(timezone.utc) - discord.utils.snowflake_time(
                int(message_id)
            ) >= timedelta(hours=1):
                # Discord has a limit on how many messages older than 1 hour that can be edited.
                # So we will just ignore any since they are likely complete and pushed out
                # of view of chat anyway.
                continue
            if channel.is_news():
                asyncio.create_task(self.edit_goal(bot, channel, message_id, em, text))
                # This is to prevent endlessly waiting incase someone
                # decided to publish one of our messages we want to edit
                # if we did bounded_gather here the gather would wait until
                # rate limits are up for editing that one message
                # in this case we can send off the task to do it's thing
                # and forget about it. If one never finishes I don't care
            else:
                await self.edit_goal(bot, channel, message_id, em, text)
        return

    async def edit_goal(
        self,
        bot: Red,
        channel: Union[discord.TextChannel, discord.Thread],
        message_id: int,
        em: discord.Embed,
        text: str,
    ) -> None:
        try:
            if channel.guild.me.is_timed_out():
                return
            try:
                message = channel.get_partial_message(message_id)
            except (discord.errors.NotFound, discord.errors.Forbidden):
                return
            guild = channel.guild
            config = bot.get_cog("Hockey").config
            game_day_channels = await config.guild(guild).gdc()
            game_day_threads = await config.guild(guild).gdt()
            guild_image_setting = await config.guild(guild).include_goal_image()
            channel_image_setting = await config.channel(channel).include_goal_image()
            include_goal_image = guild_image_setting or channel_image_setting
            send_em = em.copy()
            montreal = ["Montréal Canadiens", "Montreal Canadiens"]
            roles = set()
            team_role = discord.utils.get(guild.roles, name=f"{self.team_name} GOAL")
            if team_role is None and self.team_name in montreal:
                # Special lookup for Canadiens without the accent
                for name in montreal:
                    team_role = discord.utils.get(guild.roles, name=f"{name} GOAL")
                    if team_role is not None:
                        break
            if team_role is not None:
                roles.add(team_role.mention)
            goal_roles = await config.channel(channel).game_goal_roles()
            mention_roles = set()

            for team, role_ids in goal_roles.items():
                if team not in ["all", self.team_name]:
                    continue
                for role_id in role_ids:
                    if role := guild.get_role(role_id):
                        mention_roles.add(role)
                        roles.add(role.mention)
            allowed_mentions = discord.AllowedMentions(roles=list(mention_roles))
            roles_text = humanize_list(list(roles))
            if include_goal_image and self.image:
                send_em.set_image(url=self.image)

            if game_day_channels is not None:
                # We don't want to ping people in the game day channels twice
                if channel.id in game_day_channels:
                    role = None
            if game_day_threads is not None:
                if channel.id in game_day_threads:
                    role = None
            if channel.permissions_for(channel.guild.me).embed_links:
                if not roles_text or self.type_code.value != 505:  # Goal type_code value
                    await message.edit(embed=send_em, allowed_mentions=allowed_mentions)
                else:
                    await message.edit(content=roles_text, embed=send_em)
            else:
                if not roles_text or self.type_code.value != 505:  # Goal type_code value
                    await message.edit(content=text)
                else:
                    await message.edit(content=f"{roles_text}\n{text}")
        except (discord.errors.NotFound, discord.errors.Forbidden):
            log.exception("Apparently could not edit a message")
            return
        except Exception:
            log.exception("Could not edit goal in %s", repr(channel))

    async def get_shootout_display(self, game: Game) -> Tuple[str, str]:
        """
        Gets a string for the shootout display
        """
        home_msg = ""
        away_msg = ""
        score = "\N{WHITE HEAVY CHECK MARK} {scorer}\n"
        miss = "\N{CROSS MARK} {scorer}\n"

        for goal in game.home_goals:
            scorer = ""
            scorer_num = ""
            if goal.period_ord != "SO":
                continue
            if goal.goal_id > self.goal_id:
                continue
            if goal.scorer_id in game.home_roster:
                scorer = game.home_roster[goal.scorer_id].name
                scorer_num = game.home_roster[goal.scorer_id].sweaterNumber
            if goal.type_code.value in [506, 507]:  # Shots on Goal and Missed Shots
                home_msg += miss.format(scorer=f"#{scorer_num} {scorer}")
            if goal.type_code.value in [505]:
                home_msg += score.format(scorer=f"#{scorer_num} {scorer}")

        for goal in game.away_goals:
            scorer = ""
            scorer_num = ""
            if goal.period_ord != "SO":
                continue
            if goal.goal_id > self.goal_id:
                # if the goal object building this shootout display
                # is in the shootout and we reach a goal that happened *after*
                # this goal object, we break for a cleaner looking shootout display.

                # addendum, the new API removed timestamps so for this to work
                # we have to assume that goal ID's increment
                continue
            if goal.scorer_id in game.away_roster:
                scorer = game.away_roster[goal.scorer_id].name
                scorer_num = game.away_roster[goal.scorer_id].sweaterNumber
            if goal.type_code.value in [506, 507]:  # Shots on Goal and Missed Shots
                away_msg += miss.format(scorer=f"#{scorer_num} {scorer}")
            if goal.type_code.value in [505]:
                away_msg += score.format(scorer=f"#{scorer_num} {scorer}")

        return home_msg, away_msg

    async def goal_post_embed(self, game: Game, *, include_image: bool = False) -> discord.Embed:
        """
        Gets the embed for goal posts
        """
        # h_emoji = game.home_emoji
        # a_emoji = game.away_emoji
        shootout = False
        if self.period_ord == "SO":
            shootout = True
        colour = self.team.colour
        title = f"🚨 {self.team_name} #{self.jersey_no} {self.strength} {self.event} 🚨"
        url = self.team.team_url
        logo = self.team.logo
        if not shootout:
            em = discord.Embed(description=f"{self.description}")
            if self.link:
                em.description = f"[{self.description}]({self.link})"
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
            # em.timestamp = self.time
            # if self.image is not None:
            # em.set_image(url=self.image)
        else:
            if self.type_code.value != 505:
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
                text=_("{time} left in the {ordinal} period").format(
                    time=str(game.period_time_left), ordinal=str(self.period_ord)
                ),
                icon_url=logo,
            )
            # em.timestamp = self.time
        return em

    async def goal_post_text(self, game: Game) -> str:
        """
        Gets the text to send for goal posts
        """
        if game.period_ord != "SO":
            text = f"🚨 {self.team_name} #{self.jersey_no} {self.strength} {self.event} 🚨\n"
            if self.link:
                text += f"[{self.description}]({self.link})\n"
            else:
                text += f"{self.description}\n"
            text += (
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
