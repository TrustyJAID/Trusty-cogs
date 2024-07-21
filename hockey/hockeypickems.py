import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

import discord
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import bank, commands
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import pagify

from hockey.helper import slow_send_task, utc_to_local

from .abc import HockeyMixin
from .game import Game, GameState, GameType
from .pickems import Pickems

_ = Translator("Hockey", __file__)
log = getLogger("red.trusty-cogs.Hockey")

hockey_commands = HockeyMixin.hockey_commands
# defined in abc.py allowing this to be inherited by multiple files

PICKEMS_MESSAGE = _(
    "**Welcome to our daily Pick'ems challenge!  Below you will see today's games!"
    "  Vote for who you think will win!  You get one point for each correct prediction. "
    "Votes are weighted based on total number of votes you have made. So the more "
    "you play and guess correctly the higher you will be on the leaderboard.**\n\n"
    "- Click the button for the team you think will win the day's match-up.\n"
    "{guild_message}"
)


class HockeyPickems(HockeyMixin):
    """
    Hockey Pickems Logic
    """

    def __init__(self, *args):
        super().__init__()
        self.pickems_games: Dict[str, Game] = {}
        # This is a temporary class attr used for
        # storing only 1 copy of the game object so
        # we're not spamming the API with the same game over and over
        # this gets cleared and is only used with leaderboard tallying
        self.antispam = {}

    @tasks.loop(seconds=300)
    async def pickems_loop(self) -> None:
        try:
            await self.save_pickems_data()
        except Exception:
            log.exception("Error saving pickems data")
        log.verbose("Saved pickems data.")

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        if before.archived == after.archived:
            return
        if after.locked:
            # explicitly allow moderators to lock the channel still
            return
        guild = before.guild
        if not before.permissions_for(guild.me).manage_threads:
            return
        if str(before.id) in await self.pickems_config.guild(guild).pickems_channels():
            await after.edit(archived=False)
            log.debug("Unarchiving thread %r", after)
        if before.id in await self.config.guild(guild).gdt():
            await after.edit(archived=False)
            log.debug("Unarchiving thread %r", after)
        if (
            before.parent
            and before.parent.id == await self.pickems_config.guild(guild).pickems_channel()
        ):
            if not before.created_at:
                return
            if (datetime.now(timezone.utc) - before.created_at) < timedelta(days=9):
                await after.edit(archived=False)
                log.debug("Unarchiving thread %r", after)

    async def save_pickems_data(self) -> None:
        to_del: Dict[str, List[str]] = {}
        log.trace("Saving pickems data")
        # all_pickems = self.all_pickems.copy()
        async for guild_id, pickems in AsyncIter(self.all_pickems.items(), steps=10):
            async with self.pickems_config.guild_from_id(int(guild_id)).pickems() as data:
                for name, pickem in pickems.items():
                    if pickem._should_save:
                        log.trace("Saving pickem %r", pickem)
                        data[name] = pickem.to_json()
                    self.all_pickems[guild_id][name]._should_save = False
                    days_old = datetime.now(timezone.utc) - pickem.game_start
                    if pickem.game_type in [
                        GameType.pre_season,
                        GameType.playoffs,
                    ] and days_old >= timedelta(days=7):
                        del data[name]
                        if guild_id not in to_del:
                            to_del[guild_id] = [name]
                        else:
                            to_del[guild_id].append(name)
                    elif days_old >= timedelta(days=30):
                        del data[name]
                        if guild_id not in to_del:
                            to_del[guild_id] = [name]
                        else:
                            to_del[guild_id].append(name)

        for guild_id, names in to_del.items():
            for name in names:
                try:
                    del self.all_pickems[guild_id][name]
                except KeyError:
                    pass

    async def after_pickems_loop(self) -> None:
        log.verbose("Saving pickems data and stopping views")
        await self.save_pickems_data()
        for guild_id, pickems in self.all_pickems.items():
            for game, pickem in pickems.items():
                # Don't forget to remove persistent views when the cog is unloaded.
                log.trace("Stopping %s", pickem.name)
                pickem.stop()

    @pickems_loop.before_loop
    async def before_pickems_loop(self) -> None:
        log.trace("Waiting for Red to be ready")
        await self.bot.wait_until_red_ready()
        log.trace("Waiting for the cog to finish migrating")
        await self._ready.wait()
        # wait until migration if necessary
        all_data = await self.pickems_config.all_guilds()
        for guild_id, data in all_data.items():
            pickems_list = data.get("pickems", {})
            if pickems_list is None:
                log.info("Resetting pickems in %s for incompatible type", guild_id)
                await self.pickems_config.guild_from_id(int(guild_id)).pickems.clear()
                continue
            if type(pickems_list) is list:
                log.info("Resetting pickems in %S for incompatible type", guild_id)
                await self.pickems_config.guild_from_id(int(guild_id)).pickems.clear()
                continue
            # pickems = [Pickems.from_json(p) for p in pickems_list]
            pickems = {name: Pickems.from_json(p) for name, p in pickems_list.items()}
            if not pickems:
                continue
            self.all_pickems[str(guild_id)] = pickems
            for name, pickem in pickems.items():
                try:
                    self.bot.add_view(pickem)
                except Exception:
                    log.exception("Error adding pickems to the bot %r", pickem)

    def pickems_name(self, game: Game) -> str:
        return f"{game.away.tri_code}@{game.home.tri_code}-{game.game_start.month}-{game.game_start.day}"

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

    async def disable_pickems_buttons(self, game: Game) -> None:
        all_pickems = self.all_pickems.copy()
        # log.debug("Disabling pickems Buttons for game %r", game)
        for guild_id, pickems in all_pickems.items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                log.trace("Guild ID %s Not available", guild_id)
                continue
            if str(game.game_id) not in pickems:
                log.trace("Game %r not in pickems", game)
                continue
            pickem = self.all_pickems[str(guild_id)][str(game.game_id)]
            should_edit = pickem.disable_buttons()
            if not should_edit:
                continue
            for message in pickem.messages:
                try:
                    channel_id, message_id = message.split("-")
                except ValueError:
                    log.verbose("Game %r missing message %s", game, message)
                    continue
                channel = guild.get_channel_or_thread(int(channel_id))
                if not channel:
                    # log.debug("Game %r missing channel", game)
                    continue
                asyncio.create_task(
                    self.edit_pickems_message(channel, int(message_id), game, pickem)
                )

    async def set_guild_pickem_winner(self, game: Game, edit_message: bool = False) -> None:
        all_pickems = self.all_pickems.copy()
        # log.debug("Setting winner for game %r", game)
        tasks = []
        for guild_id, pickems in all_pickems.items():
            if str(game.game_id) not in pickems:
                # log.debug("Game %r not in pickems list.", game)
                continue
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                # log.debug("Guild %s not available", guild_id)
                continue
            pickem = self.all_pickems[str(guild_id)][str(game.game_id)]
            if not await pickem.check_winner(game):
                # log.debug("Game %r does not have a winner yet.", game)
                continue
            if game.game_state is pickem.game_state:
                # log.debug("Game state %s not equal to pickem game state %s", game.game_state, pickem.game_state)
                continue
            pickem.game_state = game.game_state
            pickem._should_save = True
            if not edit_message:
                continue
            if pickem.winner == pickem.home_team:
                pickem.home_button.style = discord.ButtonStyle.green
                pickem.away_button.style = discord.ButtonStyle.red
            if pickem.winner == pickem.away_team:
                pickem.home_button.style = discord.ButtonStyle.red
                pickem.away_button.style = discord.ButtonStyle.green

            for message in pickem.messages:
                try:
                    channel_id, message_id = message.split("-")
                except ValueError:
                    # log.debug("Game %r missing message %s", game, message)
                    continue
                channel = guild.get_channel_or_thread(int(channel_id))
                if not channel:
                    # log.debug("Game %r missing channel", game)
                    continue
                tasks.append(self.edit_pickems_message(channel, int(message_id), game, pickem))
        if tasks:
            asyncio.create_task(slow_send_task(tasks))

    async def edit_pickems_message(
        self, channel: discord.Thread, message_id: int, game: Game, pickem: Pickems
    ) -> None:
        log.debug("Editing Pickems")

        try:
            if channel.archived and channel.permissions_for(channel.guild.me).manage_threads:
                await channel.edit(archived=False)
            content = await self.make_pickems_msg(channel.guild, game)
            message = channel.get_partial_message(message_id)
            await message.edit(content=content, view=pickem)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            log.error("Error editing pickems message in %s", repr(channel))
            return
        except Exception:
            log.exception("Error editing pickems message in %s", repr(channel))

    async def get_pickem_object(
        self,
        guild: discord.Guild,
        game: Game,
    ) -> Pickems:
        """
        Checks to see if a pickem object is already created for the game
        if not it creates one or adds the message, channel to the current ones
        """
        new_name = self.pickems_name(game)
        if str(guild.id) not in self.all_pickems:
            self.all_pickems[str((guild.id))] = {}
        old_pickem = self.all_pickems[str(guild.id)].get(str(game.game_id))

        if old_pickem is None:
            pickem = Pickems(
                game_id=game.game_id,
                game_state=game.game_state,
                messages=[],
                guild=guild.id,
                game_start=game.game_start,
                home_team=game.home_team,
                away_team=game.away_team,
                votes={},
                name=new_name,
                winner=None,
                link=game.link,
                game_type=game.game_type,
                should_edit=await self.pickems_config.guild(guild).show_count(),
            )

            self.all_pickems[str(guild.id)][str(game.game_id)] = pickem
            log.debug("creating new pickems %s", new_name)
            return pickem
        else:
            if old_pickem.game_start != game.game_start:
                self.all_pickems[str(guild.id)][str(game.game_id)].game_start = game.game_start
                self.all_pickems[str(guild.id)][str(game.game_id)].enable_buttons()
                self.all_pickems[str(guild.id)][str(game.game_id)]._should_save = True
            return self.all_pickems[str(guild.id)][str(game.game_id)]

    async def fix_pickem_game_start(self, game: Game):
        tasks = []
        async for guild_id, data in AsyncIter(self.all_pickems.items(), steps=50):
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            if str(game.game_id) in data:
                pickem = data[str(game.game_id)]
                if game.game_start != pickem.game_start:
                    # only attempt to edit if the game ID is the same
                    # and the game start is different on the pickems from
                    # the actual game playing today.
                    pickem.game_start = game.game_start
                    pickem.enable_buttons()
                    pickem._should_save = True
                    for message in pickem.messages:
                        try:
                            channel_id, message_id = message.split("-")
                        except ValueError:
                            log.debug("Game %r missing message %s", game, message)
                            continue
                        channel = guild.get_channel_or_thread(int(channel_id))
                        if channel is None:
                            # log.debug("Game %r missing channel", game)
                            continue
                        tasks.append(
                            self.edit_pickems_message(channel, int(message_id), game, pickem)
                        )
            else:
                channel_id = await self.pickems_config.guild(guild).pickems_channel()
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                threads = await self.pickems_config.guild(guild).pickems_channels()
                thread = None
                game_start = utc_to_local(game.game_start)
                for thread_id, date in threads.items():
                    dt = datetime.utcfromtimestamp(date).replace(tzinfo=timezone.utc)
                    thread_date = dt
                    if (game_start.year, game_start.month, game_start.day) == (
                        thread_date.year,
                        thread_date.month,
                        thread_date.day,
                    ):
                        thread = guild.get_thread(int(thread_id))
                if thread is not None:
                    tasks.append(self.create_pickems_game_message(thread, game))
        if tasks:
            asyncio.create_task(slow_send_task(tasks))

    async def reset_weekly(self) -> None:
        # Reset the weekly leaderboard for all servers
        async for guild_id, data in AsyncIter(
            (await self.pickems_config.all_guilds()).items(), steps=10
        ):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            # current_guild_pickem_channels = await self.pickems_config.guild(
            # guild
            # ).pickems_channels()
            # self.asyncio.create_task(
            # self.delete_pickems_channels(guild, current_guild_pickem_channels)
            # )
            top_members: List[int] = []
            global_bank = await bank.is_global()
            if global_bank:
                top_amount = await self.pickems_config.top_amount()
            else:
                top_amount = await self.pickems_config.guild(guild).top_amount()
            async with self.pickems_config.guild(guild).leaderboard() as leaderboard:
                try:
                    top_members = sorted(
                        leaderboard.items(), key=lambda i: i[1]["weekly"], reverse=True
                    )[:top_amount]
                    top_members = [int(user_id) for user_id, data in top_members]
                except Exception:
                    log.exception("Error getting top users for pickems weekly.")
                await self.pickems_config.guild(guild).last_week_leaderboard.set(leaderboard)

                for user, data in leaderboard.items():
                    data["weekly"] = 0
                    data["playoffs_weekly"] = 0
                    data["pre-season_weekly"] = 0
            asyncio.create_task(self.add_weekly_pickems_credits(guild, top_members))

    async def add_weekly_pickems_credits(
        self, guild: discord.Guild, top_members: List[int]
    ) -> None:
        global_bank = await bank.is_global()
        if global_bank:
            top_credits = await self.pickems_config.top_credits()
        else:
            top_credits = await self.pickems_config.guild(guild).top_credits()
        for user_id in top_members:
            if member := guild.get_member(user_id):
                try:
                    await bank.deposit_credits(member, top_credits)
                except Exception:
                    log.error("Could not add credits to %s", repr(member))

    async def create_pickems_thread(
        self, day: datetime, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        guild_message = await self.pickems_config.guild(guild).pickems_message()
        global_bank = await bank.is_global()
        currency_name = await bank.get_currency_name(guild)
        if guild.me.is_timed_out():
            return None
        if global_bank:
            base_credits = await self.pickems_config.base_credits()
            top_credits = await self.pickems_config.top_credits()
            top_members = await self.pickems_config.top_amount()
        else:
            base_credits = await self.pickems_config.guild(guild).base_credits()
            top_credits = await self.pickems_config.guild(guild).top_credits()
            top_members = await self.pickems_config.guild(guild).top_amount()

        msg = _(PICKEMS_MESSAGE).replace("{guild_message}", guild_message)
        msg = (
            msg.replace("{currency}", str(currency_name))
            .replace("{base_credits}", str(base_credits))
            .replace("{top_credits}", str(top_credits))
            .replace("{top_members}", str(top_members))
        )
        channel = guild.get_channel(await self.pickems_config.guild(guild).pickems_channel())
        if channel is None:
            await self.pickems_config.guild(guild).pickems_channel.clear()
            return None
        if not channel.permissions_for(guild.me).create_public_threads:
            return None
        timestamp = int(day.replace(tzinfo=None, hour=12).timestamp())
        # replace hour to 12 because on UTC machines this doesn't work as expected
        # 12 should cover most of the US and most times are in relation to the US
        # In practice we don't care since the exact dates are under the game themselves
        # but this is used to display a mostly accurate day.
        start_msg = _("Pickems <t:{date}:D>").format(date=timestamp)
        name = _("Pickems-{month}-{day}").format(month=day.month, day=day.day)
        auto_archive_duration = 10080
        new_chn = None
        if isinstance(channel, discord.TextChannel):
            message = await channel.send(start_msg)
            try:
                new_chn = await channel.create_thread(
                    name=name, message=message, auto_archive_duration=auto_archive_duration
                )
                for page in pagify(msg):
                    await new_chn.send(page)
            except (discord.Forbidden, discord.HTTPException):
                return None
        elif isinstance(channel, discord.ForumChannel):
            start_pages = [p for p in pagify(f"{start_msg}\n{msg}")]
            content = start_pages.pop(0)
            try:
                channel_with_msg = await channel.create_thread(
                    name=name, content=content, auto_archive_duration=auto_archive_duration
                )
                new_chn = channel_with_msg[0]
                for page in start_pages:
                    await new_chn.send(page)
            except (discord.Forbidden, discord.HTTPException):
                return None
        return new_chn

    async def create_pickems_channel(
        self, day: datetime, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        name = _("pickems-{month}-{day}").format(month=day.month, day=day.day)
        guild_message = await self.pickems_config.guild(guild).pickems_message()
        global_bank = await bank.is_global()
        currency_name = await bank.get_currency_name(guild)
        if global_bank:
            base_credits = await self.pickems_config.base_credits()
            top_credits = await self.pickems_config.top_credits()
            top_members = await self.pickems_config.top_amount()
        else:
            base_credits = await self.pickems_config.guild(guild).base_credits()
            top_credits = await self.pickems_config.guild(guild).top_credits()
            top_members = await self.pickems_config.guild(guild).top_amount()

        msg = _(PICKEMS_MESSAGE).replace("{guild_message}", guild_message)
        msg = (
            msg.replace("{currency}", str(currency_name))
            .replace("{base_credits}", str(base_credits))
            .replace("{top_credits}", str(top_credits))
            .replace("{top_members}", str(top_members))
        )
        category = guild.get_channel(await self.pickems_config.guild(guild).pickems_category())
        if category is None or not isinstance(category, discord.CategoryChannel):
            await self.pickems_config.guild(guild).pickems_category.clear()
            return None
        if not category.permissions_for(guild.me).manage_channels:
            return None
        if len(category.channels) >= 50 or len(guild.channels) > 500:
            return None
        try:
            new_chn = await guild.create_text_channel(name, category=category)
            for page in pagify(msg):
                await new_chn.send(page)
        except discord.Forbidden:
            await self.pickems_config.guild(guild).pickems_category.clear()
            return None
        except discord.HTTPException:
            return None
        return new_chn

    async def make_pickems_msg(self, guild: discord.Guild, game: Game) -> str:
        winner = ""
        if game.game_state.value > GameState.over.value:
            team = game.home_team if game.home_score > game.away_score else game.away_team
            team_emoji = game.home_emoji if game.home_score > game.away_score else game.away_emoji
            winner = _("**WINNER:** {team_emoji} {team}").format(team_emoji=team_emoji, team=team)

        time_str = f"<t:{game.timestamp}:F>"
        if game.game_state == "Postponed":
            time_str = _("Postponed")

        msg = (
            "__**{away_emoji} {away_name}**__ @ "
            "__**{home_emoji} {home_name}**__ "
            "{start_time}\n{winner}"
        ).format(
            away_emoji=game.away_emoji,
            away_name=game.away_team,
            home_emoji=game.home_emoji,
            home_name=game.home_team,
            start_time=time_str,
            winner=winner,
        )
        return msg

    async def create_pickems_game_message(
        self, channel: Union[discord.TextChannel, discord.Thread], game: Game
    ) -> None:
        msg = await self.make_pickems_msg(channel.guild, game)
        pickem = await self.get_pickem_object(channel.guild, game)
        try:
            new_msg = await channel.send(msg, view=pickem)
        except discord.Forbidden:
            log.error("Could not send pickems message in %s", repr(channel))
            return
        pickem.messages.append(f"{channel.id}-{new_msg.id}")
        pickem._should_save = True
        # Create new pickems object for the game

    async def create_pickems_channels_and_message(
        self, guilds: List[discord.Guild], day: datetime
    ) -> Dict[int, List[int]]:
        data = []
        # channel_tasks = []
        save_data = {}
        for guild in guilds:
            data.append(await self.create_pickems_thread(day, guild))
        # data = await bounded_gather(*channel_tasks)

        for new_channel in data:
            if new_channel is None:
                continue
            if new_channel.guild.id not in save_data:
                save_data[new_channel.guild.id] = [new_channel.id]
            else:
                save_data[new_channel.guild.id].append(new_channel.id)

        games_list = await self.api.get_games(None, day, day)

        # msg_tasks = []
        for game in games_list:
            for channel in data:
                if channel:
                    await self.create_pickems_game_message(channel, game)
        # await bounded_gather(*msg_tasks)
        return save_data

    async def create_next_pickems_day(self, guilds: List[discord.Guild]) -> None:
        """
        This will attempt to find the last day of which pickems channels were created
        for in each guild and create the following days channel on a daily basis.

        This also handles the conversion from the old method to the new method incase
        This is updated in between.
        """
        for guild in guilds:
            cur_channels = await self.pickems_config.guild(guild).pickems_channels()

            latest_date, latest_chan = None, None
            earliest_date, earliest_chan = None, None
            to_rem_chans = []
            # This is only here if for whatever reason
            # we have additional channels we don't care about
            # and never were removed from config
            now = datetime.now(tz=timezone.utc) - timedelta(days=1)
            # compare it to 1 day prior just so we don't accidentally
            # delete todays games channel

            for channel_id, date in cur_channels.items():
                dt = datetime.utcfromtimestamp(date).replace(tzinfo=timezone.utc)
                if dt < now:
                    to_rem_chans.append(channel_id)
                if earliest_date is None:
                    earliest_date, earliest_chan = dt, channel_id

                if latest_date is None:
                    latest_date, latest_chan = dt, channel_id

                if dt < earliest_date:
                    earliest_date, earliest_chan = dt, channel_id

                if dt > latest_date:
                    latest_date, latest_chan = dt, channel_id
                log.debug(
                    "earliest_date %s earliest_chan %s latest_date %s latest_chan %s",
                    earliest_date,
                    earliest_chan,
                    latest_date,
                    latest_chan,
                )
            if earliest_chan is not None:
                old_chan = guild.get_thread(int(earliest_chan))
                if old_chan is not None:
                    try:
                        await old_chan.edit(archived=True)
                    except Exception:
                        log.exception("Error deleting channel %s", repr(old_chan))
                        pass
                async with self.pickems_config.guild(guild).pickems_channels() as chans:
                    try:
                        del chans[str(earliest_chan)]
                    except KeyError:
                        pass
            if to_rem_chans:
                for channel_id in to_rem_chans:
                    c = guild.get_channel(int(channel_id))
                    if c is not None:
                        try:
                            await c.delete()
                        except Exception:
                            log.exception("Error deleting channel %s", repr(old_chan))
                            pass
                async with self.pickems_config.guild(guild).pickems_channels() as chans:
                    try:
                        del chans[str(channel_id)]
                    except KeyError:
                        pass
            if latest_date:
                channel_data = await self.create_pickems_channels_and_message(
                    [guild], latest_date + timedelta(days=1)
                )
                for guild_id, channels in channel_data.items():
                    async with self.pickems_config.guild_from_id(
                        guild_id
                    ).pickems_channels() as save_channels:
                        for channel_id in channels:
                            save_channels[str(channel_id)] = (
                                latest_date + timedelta(days=1)
                            ).timestamp()

    async def create_weekly_pickems_pages(self, guilds: List[discord.Guild]) -> None:
        save_data = {}
        now = datetime.now(timezone.utc)
        today = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
        tasks = []
        guild_data = []
        for days in range(7):
            guild_data.append(
                await self.create_pickems_channels_and_message(
                    guilds, today + timedelta(days=days)
                )
            )

        # guild_data = await bounded_gather(*tasks)
        for channel_data in guild_data:
            for guild_id, channels in channel_data.items():
                if guild_id not in save_data:
                    save_data[guild_id] = channels
                    continue
                for channel in channels:
                    save_data[guild_id].append(channel)

        for guild_id, channels in save_data.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            async with self.pickems_config.guild(guild).pickems_channels() as save_channels:
                for channel_id in channels:
                    chan = guild.get_thread(channel_id)
                    if chan is None:
                        continue
                    _pickems, month, day = chan.name.split("-")
                    save_channels[str(chan.id)] = int(
                        datetime(datetime.now().year, int(month), int(day))
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                    )
            # await self.pickems_config.guild(guild).pickems_channels.set(channels)

    async def delete_pickems_channels(self, guild: discord.Guild, channels: List[int]) -> None:
        """
        This was used to delete all pickems channels during the weekly
        This is no longer necessary with the daily page creation/deletion
        """
        log.debug("Deleting pickems channels")
        for channel_id in channels:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            try:
                await channel.delete()
                if guild.id in self.antispam:
                    if channel_id in self.antispam[guild.id]:
                        del self.antispam[guild.id][channel_id]
                        # this is just so we don't constantly
                        # keep adding more of these to memory
                        # requiring us to reload over time
            except discord.errors.Forbidden:
                log.error("Missing permissions to delete old pickems channel in %r", guild)
                pass
            except Exception:
                log.exception(f"Error deleting old pickems channels in {repr(guild)}")

    async def tally_guild_leaderboard(self, guild: discord.Guild) -> None:
        """
        Allows individual guilds to tally pickems leaderboard
        """
        global_bank = await bank.is_global()
        if global_bank:
            base_credits = await self.pickems_config.base_credits()
        else:
            base_credits = await self.pickems_config.guild(guild).base_credits()
        pickems_list = self.all_pickems.get(str(guild.id)).copy()
        to_remove = []
        async for name, pickems in AsyncIter(pickems_list.items(), steps=10):
            # check for definitive winner here just incase
            if name not in self.pickems_games:
                try:
                    game = await pickems.get_game(self.api)
                except Exception:
                    log.exception(
                        "Error getting game info for %s - %s", pickems.name, pickems.game_id
                    )
                    continue
                self.pickems_games[name] = game
                await self.set_guild_pickem_winner(self.pickems_games[name])
                # Go through all the current pickems for every server
                # and handle editing postponed games, etc here
                # This will ensure any games that never make it to
                # the main loop still get checked
            if not await pickems.check_winner(self.pickems_games[name]):
                continue
            log.debug("Tallying results for %r", pickems)
            to_remove.append(name)
            DEFAULT_LEADERBOARD = {
                "season": 0,
                "weekly": 0,
                "total": 0,
                "playoffs": 0,
                "playoffs_weekly": 0,
                "playoffs_total": 0,
                "pre-season": 0,
                "pre-season_weekly": 0,
                "pre-season_total": 0,
            }
            async with self.pickems_config.guild(guild).leaderboard() as leaderboard:
                for user, choice in pickems.votes.items():
                    if str(user) not in leaderboard:
                        leaderboard[str(user)] = DEFAULT_LEADERBOARD.copy()
                    for key, value in DEFAULT_LEADERBOARD.items():
                        # verify all defaults are in the setting
                        if key not in leaderboard[str(user)]:
                            leaderboard[str(user)][key] = value

                    if choice == pickems.winner:
                        if member := guild.get_member(int(user)):
                            try:
                                await bank.deposit_credits(member, int(base_credits))
                            except Exception:
                                log.debug("Could not deposit pickems credits for %r", member)
                        if pickems.game_type is GameType.playoffs:
                            leaderboard[str(user)]["playoffs"] += 1
                            leaderboard[str(user)]["playoffs_weekly"] += 1
                            leaderboard[str(user)]["playoffs_total"] += 1
                        elif pickems.game_type is GameType.pre_season:
                            leaderboard[str(user)]["pre-season"] += 1
                            leaderboard[str(user)]["pre-season_weekly"] += 1
                            leaderboard[str(user)]["pre-season_total"] += 1
                        else:
                            leaderboard[str(user)]["season"] += 1
                            leaderboard[str(user)]["total"] += 1
                            # The above needs to be adjusted when this current season
                            # playoffs is finished
                            leaderboard[str(user)]["weekly"] += 1
                    else:
                        if pickems.game_type is GameType.playoffs:
                            leaderboard[str(user)]["playoffs_total"] += 1
                        elif pickems.game_type is GameType.pre_season:
                            leaderboard[str(user)]["pre-season_total"] += 1
                        else:
                            leaderboard[str(user)]["total"] += 1
                        # Weekly reset weekly but we want to track this
                        # regardless of playoffs and pre-season
                        # If this causes confusion I can change it later
                        # leaving this comment so I remember
        for name in to_remove:
            try:
                log.verbose("Removing pickem %s", name)
                del self.all_pickems[str(guild.id)][name]
                async with self.pickems_config.guild(guild).pickems() as data:
                    if name in data:
                        del data[name]
            except Exception:
                log.error("Error removing pickems from memory", exc_info=True)

    async def tally_leaderboard(self) -> None:
        """
        This should be where the pickems is removed and tallies are added
        to the leaderboard
        """
        async for guild_id in AsyncIter(self.all_pickems.keys(), steps=10):
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            try:
                await self.tally_guild_leaderboard(guild)
            except Exception:
                log.exception(f"Error tallying leaderboard in {guild.name}")
        self.pickems_games = {}
        # Clear the data since we no longer need it after this
        # anything new will be a new day and that's when we care

    #######################################################################
    # All pickems related commands for setup, etc.                        #
    #######################################################################

    @hockey_commands.group(name="pickems")
    @commands.admin_or_permissions(manage_channels=True)
    async def pickems_commands(self, ctx: commands.Context) -> None:
        """
        Commands for managing pickems
        """
        pass

    @pickems_commands.command(name="settings")
    async def pickems_settings(self, ctx: commands.Context) -> None:
        """
        Show the servers current pickems settings
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        data = await self.pickems_config.guild(ctx.guild).all()
        category_channel = ctx.guild.get_channel(data.get("pickems_category"))
        category = category_channel.mention if category_channel else None
        channel = ctx.guild.get_channel(data.get("pickems_channel"))
        channel = channel.mention if channel else None
        global_bank = await bank.is_global()
        currency_name = await bank.get_currency_name(ctx.guild)
        if global_bank:
            base_credits = await self.pickems_config.base_credits()
            top_credits = await self.pickems_config.top_credits()
            top_members = await self.pickems_config.top_amount()
        else:
            base_credits = await self.pickems_config.guild(ctx.guild).base_credits()
            top_credits = await self.pickems_config.guild(ctx.guild).top_credits()
            top_members = await self.pickems_config.guild(ctx.guild).top_amount()
        msg = _(
            "**Pickems Settings for {guild}**\n"
            "__Channel:__ **{channel}**\n"
            "__Base {currency}:__ {base_credits}\n"
            "__Weekly {currency}:__ Top {top_members} members will earn {top_credits} {currency}\n"
            "__Threads:__\n {channels}\n"
        ).format(
            guild=ctx.guild.name,
            channel=channel,
            channels="\n".join([f"<#{chan}>" for chan in data.get("pickems_channels", [])]),
            currency=currency_name,
            top_members=top_members,
            top_credits=top_credits,
            base_credits=base_credits,
        )
        await ctx.maybe_send_embed(msg)

    @commands.group(name="pickemscredits")
    async def pickems_credits(self, ctx: commands.Context) -> None:
        """
        Settings for awarding credits on correct pickems votes
        """
        pass

    @pickems_credits.command(name="base")
    async def pickems_credits_base(
        self, ctx: commands.Context, amount: Optional[int] = None
    ) -> None:
        """
        Set the base awarded credits for correct pickems votes.

        `<amount>` The number of credits that will be awarded to everyone
        who voted correctly on the game.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if amount and amount <= 0:
            amount = None
        global_bank = await bank.is_global()
        set_credits = False
        if global_bank and not await self.bot.is_owner(ctx.author):
            msg = _("This command is restricted to bot owner while the bank is global.")
            await ctx.send(msg, ephemeral=True)
        elif global_bank and await self.bot.is_owner(ctx.author):
            if amount is not None:
                set_credits = True
                await self.pickems_config.base_credits.set(int(amount))
            else:
                await self.pickems_config.base_credits.clear()
        elif not global_bank:
            if amount is not None:
                set_credits = True
                await self.pickems_config.guild(ctx.guild).base_credits.set(int(amount))
            else:
                await self.pickems_config.guild(ctx.guild).base_credits.clear()
        if set_credits:
            msg = _("Correct pickems voters will receive {credits} {credits_name}.").format(
                credits=amount,
                credits_name=await bank.get_currency_name(ctx.guild),
            )
            await ctx.send(msg)
        else:
            msg = _("Base credits for correct pickems votes have been removed.")
            await ctx.send(msg)

    @pickems_credits.command(name="top")
    async def pickems_credits_top(
        self, ctx: commands.Context, amount: Optional[int] = None
    ) -> None:
        """
        Set the amount of credits awarded for the top x winners of pickems.

        `<amount>` The number of credits that will be awarded to the winners
        every week.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if amount and amount <= 0:
            amount = None
        global_bank = await bank.is_global()
        author = ctx.author

        if global_bank and not await self.bot.is_owner(author):
            msg = _("This command is restricted to bot owner while the bank is global.")
            await ctx.send(msg)

        elif global_bank and await self.bot.is_owner(ctx.author):
            if amount is not None:
                await self.pickems_config.top_credits.set(int(amount))
            else:
                await self.pickems_config.top_credits.clear()
        elif not global_bank:
            if amount is not None:
                await self.pickems_config.guild(ctx.guild).top_credits.set(int(amount))
            else:
                await self.pickems_config.guild(ctx.guild).top_credits.clear()
        if global_bank:
            amount = await self.pickems_config.top_amount()
        else:
            amount = await self.pickems_config.guild(ctx.guild).top_amount()
        msg = _(
            "The top {amount} users every week will receive {pickems_credits} {currency_name}."
        ).format(
            amount=amount,
            pickems_credits=amount,
            currency_name=await bank.get_currency_name(ctx.guild),
        )
        await ctx.send(msg)

    @pickems_credits.command(name="amount")
    async def pickems_credits_amount(
        self, ctx: commands.Context, amount: Optional[int] = None
    ) -> None:
        """
        Set the number of top winners to receive the top weekly award credits.

        `<amount>` The number of top members to receive the weekly awarded amount.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if amount and amount <= 0:
            amount = None
        global_bank = await bank.is_global()

        if global_bank and not await self.bot.is_owner(ctx.author):
            msg = _("This command is restricted to bot owner while the bank is global.")
            await ctx.send(msg)

        elif global_bank and await self.bot.is_owner(ctx.author):
            if amount is not None:
                await self.pickems_config.top_amount.set(int(amount))
            else:
                await self.pickems_config.top_amount.clear()
        elif not global_bank:
            if amount is not None:
                await self.pickems_config.guild(ctx.guild).top_amount.set(int(amount))
            else:
                await self.pickems_config.guild(ctx.guild).top_amount.clear()
        if global_bank:
            pickems_credits = await self.pickems_config.top_credits()
        else:
            pickems_credits = await self.pickems_config.guild(ctx.guild).top_credits()
        msg = _(
            "The top {amount} users every week will receive {pickems_credits} {currency_name}."
        ).format(
            amount=amount,
            pickems_credits=pickems_credits,
            currency_name=await bank.get_currency_name(ctx.guild),
        )
        await ctx.send(msg)

    @pickems_commands.command(name="message")
    @commands.admin_or_permissions(manage_channels=True)
    async def set_pickems_message(
        self, ctx: commands.Context, *, message: Optional[str] = ""
    ) -> None:
        """
        Customize the pickems message for this server

        `[message]` Optional additional messaged added at the
        end of pickems message setup. If not provided the default
        message will only be sent at the start of the pickems page.

        `{currency}` will be replaced the bots currency name.
        `{base_credits}` will be replaced with the credits earned
        by each member who votes correctly.
        `{top_credits}` will be replaced with the credits earned
        by the top users weekly.
        `{top_members}` will be replaced with the top number of
        users per week to earn the weekly reward.

        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        global_bank = await bank.is_global()
        currency_name = await bank.get_currency_name(ctx.guild)
        if global_bank:
            base_credits = await self.pickems_config.base_credits()
            top_credits = await self.pickems_config.top_credits()
            top_members = await self.pickems_config.top_amount()
        else:
            base_credits = await self.pickems_config.guild(ctx.guild).base_credits()
            top_credits = await self.pickems_config.guild(ctx.guild).top_credits()
            top_members = await self.pickems_config.guild(ctx.guild).top_amount()

        msg = _(PICKEMS_MESSAGE).replace("{guild_message}", message)
        msg = (
            msg.replace("{currency}", str(currency_name))
            .replace("{base_credits}", str(base_credits))
            .replace("{top_credits}", str(top_credits))
            .replace("{top_members}", str(top_members))
        )
        await self.pickems_config.guild(ctx.guild).pickems_message.set(message)
        start_msg = _("Pickems pages will now start with:")
        await ctx.send(start_msg)
        for page in pagify(msg):
            await ctx.channel.send(page)

    async def check_pickems_req(self, ctx: commands.Context) -> bool:
        msg = await self.pickems_config.unavailable_msg()
        if msg is None:
            msg = _(
                "Pickems is not available at this time. Speak to the bot owner about enabling it."
            )

        if await self.pickems_config.only_allowed():
            if ctx.guild.id not in await self.pickems_config.allowed_guilds():
                await ctx.send(msg)
                return False
        return True

    @pickems_commands.command(name="setup", aliases=["auto", "set"])
    @commands.admin_or_permissions(manage_channels=True)
    async def setup_auto_pickems(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.ForumChannel] = commands.CurrentChannel,
    ) -> None:
        """
        Sets up automatically created pickems threads every week.

        `[channel]` the channel where pickems threads will be created.
        If not provided this will use the current channel.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.defer()
        if not await self.check_pickems_req(ctx):
            return
        if isinstance(channel, discord.Thread):
            msg = _("You cannot create threads within threads.")
            await ctx.send(msg)
            return

        if not channel.permissions_for(ctx.guild.me).create_public_threads:
            msg = _("I don't have permission to create public threads!")
            await ctx.send(msg)
            return
        if not channel.permissions_for(ctx.guild.me).manage_threads:
            msg = _("I do not have permission to manage threads in {channel}.").format(
                channel=channel.mention
            )
            await ctx.send(msg)
            return
        if not channel.permissions_for(ctx.guild.me).send_messages_in_threads:
            msg = _("I do not have permission to send messages in threads in {channel}.").format(
                channel=channel.mention
            )
            await ctx.send(msg)
            return

        await self.pickems_config.guild(ctx.guild).pickems_channel.set(channel.id)
        existing_channels = await self.pickems_config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            await self.pickems_config.guild(ctx.guild).pickems_channels.clear()
        await self.create_weekly_pickems_pages([ctx.guild])
        msg = _("I will now automatically create pickems pages every day.")
        await ctx.send(msg)

    @pickems_commands.command(name="showcount")
    @commands.is_owner()
    async def set_pickems_edits(self, ctx: commands.Context, enabled: bool) -> None:
        """
        Enable pickems buttons to be edited showing the number of votes for each team
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await self.pickems_config.guild(ctx.guild).show_count.set(enabled)
        if enabled:
            msg = _("Pickems will attempt to edit the buttons showing the number of votes.")
        else:
            msg = _("Pickems will not edit the buttons.")
        await ctx.send(msg)

    @pickems_commands.command(name="clear")
    @commands.admin_or_permissions(manage_channels=True)
    async def delete_auto_pickems(self, ctx: commands.Context) -> None:
        """
        Stop posting new pickems threads and clear existing list of pickems threads.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        existing_channels = await self.pickems_config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            await self.pickems_config.guild(ctx.guild).pickems_channels.clear()
        await self.pickems_config.guild(ctx.guild).pickems_channel.clear()
        await ctx.send(_("I have cleared existing pickems threads."))

    @pickems_commands.command(name="page")
    @commands.admin_or_permissions(manage_channels=True)
    async def pickems_page(self, ctx, date: Optional[str] = None) -> None:
        """
        Generates a pickems page for voting on

        `[date]` is a specified day in the format "YYYY-MM-DD"
        if `date` is not provided the current day is used instead.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.defer()
        if not await self.check_pickems_req(ctx):
            return
        if date is None:
            new_date = datetime.now(timezone.utc)
        else:
            try:
                new_date = datetime.strptime(date, "%Y-%m-%d")
                new_date.replace(tzinfo=timezone.utc)
            except ValueError:
                msg = _("`date` must be in the format `YYYY-MM-DD`.")
                await ctx.send(msg)
                return
        guild_message = await self.pickems_config.guild(ctx.guild).pickems_message()
        msg = _(PICKEMS_MESSAGE).format(guild_message=guild_message)
        games_list = await self.api.get_games(None, new_date, new_date)
        for page in pagify(msg):
            await ctx.channel.send(page)
        for game in games_list:
            await self.create_pickems_game_message(ctx.channel, game)

    @pickems_commands.command(name="remove")
    @commands.admin_or_permissions(manage_channels=True)
    async def rempickem(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Clears the servers current pickems object list

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            await self.pickems_config.guild(ctx.guild).pickems.clear()
            try:
                del self.all_pickems[str(ctx.guild.id)]
            except KeyError:
                pass
            await ctx.send(_("All pickems removed on this server."))
        else:
            await ctx.send(_("I will not remove the current pickems on this server."))

    @commands.group(name="pickemsleaderboard")
    @commands.admin_or_permissions(administrator=True)
    async def pickems_leaderboard_commands(self, ctx: commands.Context) -> None:
        """
        Settings for clearing/resetting pickems leaderboards
        """
        pass

    @pickems_leaderboard_commands.command(name="clear")
    async def clear_server_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Clears the entire pickems leaderboard in the server.

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            await self.pickems_config.guild(ctx.guild).leaderboard.clear()
            await ctx.send(_("Server leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="tally")
    async def tally_server_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Manually tallies this servers pickems leaderboard incase votes
        aren't working properly.

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            await self.tally_guild_leaderboard(ctx.guild)
            await ctx.send(_("Server leaderboard has been saved."))
        else:
            await ctx.send(_("I will not tally this servers pickems leaderboard."))

    @pickems_leaderboard_commands.command(name="clearweekly")
    async def clear_weekly_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["weekly"] = 0
            await ctx.send(_("Servers weekly leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems weekly leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="clearseason")
    async def clear_seasonal_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["season"] = 0
                    leaderboard[str(user)]["total"] = 0
            await ctx.send(_("Servers seasonal leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems seasonal leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="clearweeklyplayoffs")
    async def clear_weekly_playoffs_leaderboard(
        self, ctx: commands.Context, true_or_false: bool
    ) -> None:
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["playoffs_weekly"] = 0
            await ctx.send(_("Servers weekly playoffs leaderboard reset."))
        else:
            await ctx.send(
                _("I will not reset the pickems weekly playoffs leaderboard in this server.")
            )

    @pickems_leaderboard_commands.command(name="clearplayoffs")
    async def clear_playoffs_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["playoffs"] = 0
                    leaderboard[str(user)]["playoffs_total"] = 0
            await ctx.send(_("Servers playoffs leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems playoffs leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="clearweeklypreseason")
    async def clear_weekly_preseason_leaderboard(
        self, ctx: commands.Context, true_or_false: bool
    ) -> None:
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["pre-season_weekly"] = 0
            await ctx.send(_("Servers weekly pre-season leaderboard reset."))
        else:
            await ctx.send(
                _("I will not reset the pickems weekly pre-season leaderboard in this server.")
            )

    @pickems_leaderboard_commands.command(name="clearpresesason")
    async def clear_preseason_leaderboard(
        self, ctx: commands.Context, true_or_false: bool
    ) -> None:
        """
        Clears the pre-season tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["pre-season"] = 0
                    leaderboard[str(user)]["pre-season_total"] = 0
            await ctx.send(_("Servers pre-season leaderboard reset."))
        else:
            await ctx.send(
                _("I will not reset the pickems pre-season leaderboard in this server.")
            )

    @pickems_leaderboard_commands.command(name="setuser")
    async def leaderboardset(
        self,
        ctx: commands.Context,
        user: discord.Member,
        season: int,
        weekly: int = 0,
        total: int = 0,
    ) -> None:
        """
        Allows moderators to set a users points on the leaderboard
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        leaderboard = await self.pickems_config.guild(ctx.guild).leaderboard()
        if leaderboard == {} or leaderboard is None:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return
        if str(user.id) not in leaderboard:
            leaderboard[str(user.id)] = {
                "season": season,
                "weekly": weekly,
                "total": total,
                "playoffs": 0,
                "playoffs_weekly": 0,
                "playoffs_total": 0,
                "pre-season": 0,
                "pre-season_weekly": 0,
                "pre-season_total": 0,
            }
        else:
            del leaderboard[str(user.id)]
            leaderboard[str(user.id)] = {
                "season": season,
                "weekly": weekly,
                "total": total,
                "playoffs": 0,
                "playoffs_weekly": 0,
                "playoffs_total": 0,
                "pre-season": 0,
                "pre-season_weekly": 0,
                "pre-season_total": 0,
            }
        await self.pickems_config.guild(ctx.guild).leaderboard.set(leaderboard)
        msg = _(
            "{user} now has {season} points on the season, "
            "{weekly} points for the week, and {total} votes overall."
        ).format(user=user.display_name, season=season, weekly=weekly, total=total)
        await ctx.send(msg)
