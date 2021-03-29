import logging
from copy import copy
from datetime import datetime, timedelta
from typing import List, Optional

import discord
from discord.ext import tasks
from redbot import VersionInfo, version_info
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.utils.menus import start_adding_reactions

from .abc import MixinMeta
from .errors import NotAValidTeamError, UserHasVotedError, VotingHasEndedError
from .game import Game
from .pickems import Pickems

_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.Hockey")


class HockeyPickems(MixinMeta):
    """
    Hockey Pickems Logic
    """

    @commands.Cog.listener()
    async def on_hockey_preview_message(self, channel, message, game):
        """
        Handles adding preview messages to the pickems object.
        """
        # a little hack to avoid circular imports
        await self.create_pickem_object(channel.guild, message, channel, game)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        if str(guild.id) not in self.all_pickems:
            return
        user = guild.get_member(payload.user_id)
        # log.debug(payload.user_id)
        if not user or user.bot:
            return

        for name, pickem in self.all_pickems[str(guild.id)].items():
            if payload.message_id in pickem.message:
                if (channel.id, payload.message_id) not in pickem.messages:
                    pickem.messages.append((channel.id, payload.message_id))
                reply_message = ""
                remove_emoji = None
                try:
                    # log.debug(payload.emoji)
                    pickem.add_vote(user.id, payload.emoji)
                except UserHasVotedError as team:
                    remove_emoji = (
                            pickem.home_emoji
                            if str(payload.emoji.id) in pickem.away_emoji
                            else pickem.away_emoji
                        )
                    reply_message = _("You have already voted! Changing vote to: {team}").format(
                        team=team
                    )
                except VotingHasEndedError as error_msg:
                    remove_emoji = payload.emoji
                    reply_message = _("Voting has ended! {voted_for}").format(
                        voted_for=str(error_msg)
                    )
                except NotAValidTeamError:
                    remove_emoji = payload.emoji
                    reply_message = _("Don't clutter the voting message with emojis!")
                if remove_emoji and channel.permissions_for(guild.me).manage_messages:
                    try:
                        if version_info >= VersionInfo.from_str("3.4.6"):
                            msg = channel.get_partial_message(payload.message_id)
                        else:
                            msg = await channel.fetch_message(id=payload.message_id)
                        await msg.remove_reaction(remove_emoji, user)
                    except (discord.errors.NotFound, discord.errors.Forbidden):
                        pass
                if reply_message != "":
                    try:
                        await user.send(reply_message)
                    except Exception:
                        pass

    @tasks.loop(seconds=120)
    async def pickems_loop(self):
        await self.save_pickems_data()
        log.debug("Saved pickems data.")

    async def save_pickems_data(self):
        try:

            log.debug("Saving pickems data")
            all_pickems = copy(self.all_pickems)
            for guild_id, pickems in all_pickems.items():
                data = {}
                for name, pickem in pickems.items():
                    data[name] = pickem.to_json()
                await self.pickems_config.guild_from_id(guild_id).pickems.set(data)
        except Exception:
            log.exception("Error saving pickems Data")
            # catch all errors cause we don't want this loop to fail for something dumb

    @pickems_loop.after_loop
    async def after_pickems_loop(self):
        if self.pickems_loop.is_being_cancelled():
            await self.save_pickems_data()

    @pickems_loop.before_loop
    async def before_pickems_loop(self):
        await self.bot.wait_until_ready()
        await self._ready.wait()
        # wait until migration if necessary
        all_data = await self.pickems_config.all_guilds()
        for guild_id, data in all_data.items():
            pickems_list = data.get("pickems", {})
            if pickems_list is None:
                log.info(f"Resetting pickems in {guild_id} for incompatible type")
                await self.pickems_config.guild_from_id(guild_id).pickems.clear()
                continue
            if type(pickems_list) is list:
                log.info(f"Resetting pickems in {guild_id} for incompatible type")
                await self.pickems_config.guild_from_id(guild_id).pickems.clear()
                continue
            # pickems = [Pickems.from_json(p) for p in pickems_list]
            pickems = {name: Pickems.from_json(p) for name, p in pickems_list.items()}
            self.all_pickems[str(guild_id)] = pickems

    def pickems_name(self, game: Game) -> str:
        return f"{game.away_abr}@{game.home_abr}-{game.game_start.month}-{game.game_start.day}"

    async def find_pickems_object(self, game: Game) -> List[Pickems]:
        """
        Returns a list of all pickems on the bot for that game
        """
        return_pickems = []
        new_name = f"{game.away_abr}@{game.home_abr}-{game.game_start.month}-{game.game_start.day}"
        for guild_id, pickems in self.all_pickems.items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            if pickems is None:
                pickems = []
            if new_name in pickems:
                return_pickems.append(pickems[new_name])

        return return_pickems

    async def set_guild_pickem_winner(self, game: Game):
        for guild_id, pickems in self.all_pickems.items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            if pickems is None:
                pickems = {}
            pickem_name = self.pickems_name(game)
            if pickem_name in pickems:
                old_pickem = self.all_pickems[str(guild_id)][pickem_name]
                new_pickem = await old_pickem.set_pickem_winner(game)
                self.all_pickems[str(guild_id)][pickem_name] = new_pickem

    async def create_pickem_object(
        self,
        guild: discord.Guild,
        message: discord.Message,
        channel: discord.TextChannel,
        game: Game,
    ) -> bool:
        """
        Checks to see if a pickem object is already created for the game
        if not it creates one or adds the message, channel to the current ones
        """
        pickems = self.all_pickems.get(str(guild.id), None)
        new_name = self.pickems_name(game)
        if type(pickems) is list:
            pickems = {}
        if pickems is None:
            self.all_pickems[str((guild.id))] = {}
            pickems = {}
        old_pickem = None
        old_name = None
        for name, p in pickems.items():
            if p.compare_game(game):
                log.debug("Pickem already exists, adding channel")
                old_pickem = p
                old_name = name

        if old_pickem is None:
            pickems[new_name] = Pickems.from_json(
                {
                    "message": [message.id],
                    "messages": [(channel.id, message.id)],
                    "game_start": game.game_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "home_team": game.home_team,
                    "away_team": game.away_team,
                    "votes": {},
                    "name": new_name,
                    "winner": None,
                    "link": game.link,
                }
            )

            self.all_pickems[str(guild.id)] = pickems
            log.debug("creating new pickems")
            log.debug(pickems)
            return True
        else:
            # del pickems[old_name]
            # old_pickem["message"].append(message.id)
            # old_pickem["channel"].append(channel.id)
            old_pickem.message.append(message.id)
            # The message attribute should eventually be removed
            # This has been running fine but I'd feel safer actually
            # saving channel ID's for compatibility
            old_pickem.messages.append((channel.id, message.id))
            if not old_pickem.link:
                old_pickem.link = game.link
            pickems[old_name] = old_pickem
            # self.all_pickems[str(guild.id)] = pickems
            log.debug("using old pickems")
            return False

    async def reset_weekly(self):
        # Reset the weekly leaderboard for all servers
        pickems_channels_to_delete = []
        async for guild_id, data in AsyncIter(
            (await self.pickems_config.all_guilds()).items(), steps=100
        ):
            guild = self.bot.get_guild(id=guild_id)
            if guild is None:
                continue
            leaderboard = await self.pickems_config.guild(guild).leaderboard()
            try:
                current_guild_pickem_channels = await self.pickems_config.guild(
                    guild
                ).pickems_channels()
                if current_guild_pickem_channels:
                    pickems_channels_to_delete += current_guild_pickem_channels
            except Exception:
                log.error("Error adding channels to delete", exc_info=True)
            if leaderboard is None:
                leaderboard = {}
            for user in leaderboard:
                leaderboard[str(user)]["weekly"] = 0
            await self.pickems_config.guild(guild).leaderboard.set(leaderboard)
        try:
            await self.delete_pickems_channels(pickems_channels_to_delete)
        except Exception:
            log.error("Error deleting pickems Channels", exc_info=True)

    async def create_pickems_channel(
        self, name: str, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        msg = _(
            "**Welcome to our daily Pick'ems challenge!  Below you will see today's games!"
            "  Vote for who you think will win!  You get one point for each correct prediction."
            "  We will be tracking points over the course "
            "of the season and will be rewarding weekly,"
            " worst and full-season winners!**\n\n"
            "- Click the reaction for the team you think will win the day's match-up.\n"
            "- Anyone who votes for both teams will have their "
            "vote removed and will receive no points!\n\n\n\n"
        )
        category = guild.get_channel(await self.pickems_config.guild(guild).pickems_category())
        if not category:
            return None
        try:
            new_chn = await guild.create_text_channel(name, category=category)
            await new_chn.send(msg)
        except discord.errors.Forbidden:
            await self.pickems_config.guild(guild).pickems_category.clear()
            return None
        return new_chn

    async def create_pickems_game_msg(self, channel: discord.TextChannel, game: Game):
        try:
            new_msg = await channel.send(
                "__**{} {}**__ @ __**{} {}**__".format(
                    game.away_emoji, game.away_team, game.home_emoji, game.home_team
                )
            )
        except Exception:
            log.error("Error sending messages in pickems channel.")
            return
        # Create new pickems object for the game
        try:
            await self.create_pickem_object(channel.guild, new_msg, channel, game)
        except Exception as e:
            log.error("Error creating pickems Object.", exc_info=e)
        if channel.permissions_for(channel.guild.me).add_reactions:
            start_adding_reactions(new_msg, [game.away_emoji[2:-1], game.home_emoji[2:-1]])

    async def create_weekly_pickems_pages(self, guilds: List[discord.Guild], game_obj: Game):
        save_data = {}
        today = datetime.now()
        new_day = timedelta(days=1)
        count = 0

        while True:
            chn_name = _("pickems-{month}-{day}").format(month=today.month, day=today.day)
            data = []
            channel_tasks = []
            for guild in guilds:
                channel_tasks.append(self.create_pickems_channel(chn_name, guild))
            data = await bounded_gather(*channel_tasks)

            for new_channel in data:
                if new_channel is None:
                    continue
                if new_channel.guild.id not in save_data:
                    save_data[new_channel.guild.id] = [new_channel.id]
                else:
                    save_data[new_channel.guild.id].append(new_channel.id)

            games_list = await game_obj.get_games(None, today, today, self.session)

            msg_tasks = []
            for game in games_list:
                for channel in data:
                    if channel:
                        msg_tasks.append(self.create_pickems_game_msg(channel, game))
            await bounded_gather(*msg_tasks)

            today = today + new_day
            count += 1
            if today.weekday() == 6 or count == 7:
                # just incase we end up in an infinite loop somehow
                # can never be too careful with async coding
                break
        for guild_id, channels in save_data.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            await self.pickems_config.guild(guild).pickems_channels.set(channels)

    async def delete_pickems_channels(self, channels: List[int]):
        log.debug("Deleting pickems channels")
        for channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue
            try:
                await channel.delete()
            except discord.errors.Forbidden:
                pass
            except Exception:
                log.error("Error deleting old pickems channels", exc_info=True)

    async def tally_guild_leaderboard(self, guild: discord.Guild):
        """
        Allows individual guilds to tally pickems leaderboard
        """
        pickems_list = copy(self.all_pickems.get(str(guild.id)))
        to_remove = []
        async for name, pickems in AsyncIter(pickems_list.items(), steps=50):
            # check for definitive winner here just incase
            if await pickems.check_winner():
                to_remove.append(name)
                async with self.pickems_config.guild(guild).leaderboard() as leaderboard:
                    for user, choice in pickems.votes.items():
                        if str(user) not in leaderboard:
                            leaderboard[str(user)] = {"season": 0, "weekly": 0, "total": 0}
                        if choice == pickems.winner:
                            if str(user) not in leaderboard:
                                leaderboard[str(user)] = {"season": 1, "weekly": 1, "total": 0}
                            else:
                                leaderboard[str(user)]["season"] += 1
                                leaderboard[str(user)]["weekly"] += 1
                        if "total" not in leaderboard[str(user)]:
                            leaderboard[str(user)]["total"] = 0
                        leaderboard[str(user)]["total"] += 1
        for name in to_remove:
            try:
                del self.all_pickems[str(guild.id)][name]
            except Exception:
                log.error("Error removing pickems from memory", exc_info=True)

    async def tally_leaderboard(self):
        """
        This should be where the pickems is removed and tallies are added
        to the leaderboard
        """
        async for guild_id in AsyncIter(self.all_pickems.keys(), steps=100):
            guild = self.bot.get_guild(id=int(guild_id))
            if guild is None:
                continue
            try:
                await self.tally_guild_leaderboard(guild)
            except Exception:
                log.exception(f"Error tallying leaderboard in {guild.name}")
