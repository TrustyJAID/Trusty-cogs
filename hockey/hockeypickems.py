import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Union

import discord
from discord.ext import tasks
from redbot import VersionInfo, version_info
from redbot.core import commands, bank
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.utils.antispam import AntiSpam
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions


from .abc import MixinMeta
from .constants import TEAMS
from .errors import NotAValidTeamError, UserHasVotedError, VotingHasEndedError
from .game import Game
from .helper import utc_to_local, TimezoneFinder
from .pickems import Pickems

_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.Hockey")

hockeyset_commands = MixinMeta.hockeyset_commands
# defined in abc.py allowing this to be inherited by multiple files

PICKEMS_MESSAGE = (
    "**Welcome to our daily Pick'ems challenge!  Below you will see today's games!"
    "  Vote for who you think will win!  You get one point for each correct prediction. "
    "Votes are weighted based on total number of votes you have made. So the more "
    "you play and guess correctly the higher you will be on the leaderboard.**\n\n"
    "- Click the reaction for the team you think will win the day's match-up.\n"
    "{guild_message}"
)


class HockeyPickems(MixinMeta):
    """
    Hockey Pickems Logic
    """

    default_intervals = [
        (timedelta(seconds=5), 3),  # 3 per 5 seconds
        (timedelta(minutes=1), 5),  # 5 per 60 seconds
        (timedelta(hours=1), 16),   # at most we'll see 16 games in one day
        (timedelta(days=1), 64),    # 24 per 24 hours
    ]
    # This default interval should be good for pickems
    # This is only to prevent trying to dm spammers
    # an obscen number of times where it's not required
    # and is set per channel
    # At most we'll have 16 games in one day so this lets
    # the user receive the message indicating so for up
    # to an hour.
    # Since this only affects the display and not the actual
    # results this should be fine although I should communicate
    # in some way the changes but there's no good way
    # to do this outside what has already been done.
    # I need to guard my api responses with this
    # to prevent users having access to rate limit the bot.

    def __init__(self, *args):
        self.pickems_games: Dict[str, Game] = {}
        # This is a temporary class attr used for
        # storing only 1 copy of the game object so
        # we're not spamming the API with the same game over and over
        # this gets cleared and is only used with leaderboard tallying
        self.antispam = {}

    @commands.Cog.listener()
    async def on_hockey_preview_message(
        self, channel: discord.TextChannel, message: discord.Message, game: Game
    ) -> None:
        """
        Handles adding preview messages to the pickems object.
        """
        # a little hack to avoid circular imports
        await self.create_pickem_object(channel.guild, message, channel, game)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
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
            if f"{channel.id}-{payload.message_id}" in pickem.messages:
                reply_message = None
                remove_emoji = None
                try:
                    # log.debug(payload.emoji)
                    log.debug("Adding vote")
                    pickem.add_vote(user.id, payload.emoji)
                except UserHasVotedError as team:
                    log.debug("User has voted already")
                    remove_emoji = (
                        pickem.home_emoji
                        if str(payload.emoji.id) in pickem.away_emoji
                        else pickem.away_emoji
                    )
                    reply_message = _("You have already voted! Changing vote to: {team}").format(
                        team=team
                    )
                except VotingHasEndedError as error_msg:
                    log.debug("Voting has ended")
                    remove_emoji = payload.emoji
                    reply_message = _("Voting has ended! {voted_for}").format(
                        voted_for=str(error_msg)
                    )
                except NotAValidTeamError:
                    log.debug("Invalid emoji")
                    remove_emoji = payload.emoji
                    reply_message = _("Don't clutter the voting message with emojis!")
                except Exception:
                    log.exception(f"Error adding vote to {repr(pickem)}")
                await self.handle_pickems_response(
                    user, channel, remove_emoji, payload.message_id, reply_message
                )

    async def handle_pickems_response(
        self,
        user: discord.Member,
        channel: discord.TextChannel,
        emoji: Optional[Union[discord.Emoji, str]],
        message_id: int,
        reply_message: Optional[str],
    ):
        guild = channel.guild
        if channel.guild.id not in self.antispam:
            self.antispam[guild.id] = {}
        if channel.id not in self.antispam[guild.id]:
            self.antispam[guild.id][channel.id] = {}
        if user.id not in self.antispam[guild.id][channel.id]:
            self.antispam[guild.id][channel.id][user.id] = AntiSpam(
                self.default_intervals
            )
        if self.antispam[guild.id][channel.id][user.id].spammy:
            return

        if emoji is not None and channel.permissions_for(guild.me).manage_messages:
            try:
                if version_info >= VersionInfo.from_str("3.4.6"):
                    msg = channel.get_partial_message(message_id)
                else:
                    msg = await channel.fetch_message(id=message_id)
                await msg.remove_reaction(emoji, user)
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        try:
            await user.send(reply_message)
        except discord.HTTPException:
            log.error(f"Could not send message to {repr(user)}.")
        except Exception:
            log.exception(f"Error trying to send message to {repr(user)}")
            pass
        self.antispam[guild.id][channel.id][user.id].stamp()

    @tasks.loop(seconds=300)
    async def pickems_loop(self) -> None:
        await self.save_pickems_data()
        # log.debug("Saved pickems data.")

    async def save_pickems_data(self):
        try:

            # log.debug("Saving pickems data")
            all_pickems = self.all_pickems.copy()
            async for guild_id, pickems in AsyncIter(all_pickems.items(), steps=10):
                data = {}
                async with self.pickems_config.guild_from_id(guild_id).pickems() as data:
                    for name, pickem in pickems.items():
                        if pickem._should_save:
                            log.debug(f"Saving pickem {repr(pickem)}")
                            data[name] = pickem.to_json()
                        self.all_pickems[guild_id][name]._should_save = False
        except Exception:
            log.exception("Error saving pickems Data")
            # catch all errors cause we don't want this loop to fail for something dumb

    @pickems_loop.after_loop
    async def after_pickems_loop(self) -> None:
        if self.pickems_loop.is_being_cancelled():
            await self.save_pickems_data()

    @pickems_loop.before_loop
    async def before_pickems_loop(self) -> None:
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

    async def set_guild_pickem_winner(self, game: Game) -> None:
        all_pickems = self.all_pickems.copy()
        for guild_id, pickems in all_pickems.items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            pickems_channels = await self.pickems_config.guild(guild).pickems_channels()
            if str(game.game_id) not in pickems:
                continue
            pickem = self.all_pickems[str(guild_id)][str(game.game_id)]
            if pickem.winner is not None:
                log.debug(f"Pickems winner is not None {repr(pickem)}")
                continue
            await self.all_pickems[str(guild_id)][str(game.game_id)].check_winner(game)
            if game.game_state == pickem.game_state:
                continue
            self.all_pickems[str(guild_id)][str(game.game_id)].game_state = game.game_state
            self.all_pickems[str(guild_id)][str(game.game_id)]._should_save = True
            for message in pickem.messages:
                try:
                    channel_id, message_id = message.split("-")
                except ValueError:
                    continue
                if int(channel_id) not in pickems_channels:
                    continue
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue
                self.bot.loop.create_task(
                    self.edit_pickems_message(channel, int(message_id), game)
                )

    async def edit_pickems_message(
        self, channel: discord.TextChannel, message_id: int, game: Game
    ) -> None:
        log.debug("Editing Pickems")

        try:
            content = await self.make_pickems_msg(channel.guild, game)
            if version_info >= VersionInfo.from_str("3.4.6"):
                message = channel.get_partial_message(message_id)
            else:
                message = await channel.fetch_message(message_id)
            await message.edit(content=content)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            log.error(f"Error editing pickems message in {repr(channel)}")
            return
        except Exception:
            log.exception(f"Error editing pickems message in {repr(channel)}")

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
        pickems = self.all_pickems.get(str(guild.id), {})
        new_name = self.pickems_name(game)
        if str(guild.id) not in self.all_pickems:
            self.all_pickems[str((guild.id))] = {}
        old_pickem = self.all_pickems[str(guild.id)].get(str(game.game_id))

        if old_pickem is None:
            pickem = Pickems(
                game_id=game.game_id,
                game_state=game.game_state,
                messages=[f"{channel.id}-{message.id}"],
                guild=guild.id,
                game_start=game.game_start,
                home_team=game.home_team,
                away_team=game.away_team,
                votes={},
                name=new_name,
                winner=None,
                link=game.link,
            )

            self.all_pickems[str(guild.id)][str(game.game_id)] = pickem
            log.debug(f"creating new pickems {pickems[str(game.game_id)]}")
            return True
        else:
            self.all_pickems[str(guild.id)][str(game.game_id)].messages.append(
                f"{channel.id}-{message.id}"
            )
            if old_pickem.name != new_name:
                self.all_pickems[str(guild.id)][str(game.game_id)].name = new_name
            if old_pickem.game_start != game.game_start:
                self.all_pickems[str(guild.id)][str(game.game_id)].game_start = game.game_start
            if old_pickem.game_state != game.game_state:
                self.all_pickems[str(guild.id)][str(game.game_id)].game_state = game.game_state
            self.all_pickems[str(guild.id)][str(game.game_id)]._should_save = True
            log.debug("using old pickems")
            return False

    async def reset_weekly(self) -> None:
        # Reset the weekly leaderboard for all servers
        async for guild_id, data in AsyncIter(
            (await self.pickems_config.all_guilds()).items(), steps=10
        ):
            guild = self.bot.get_guild(id=guild_id)
            if guild is None:
                continue
            current_guild_pickem_channels = await self.pickems_config.guild(
                guild
            ).pickems_channels()
            self.bot.loop.create_task(
                self.delete_pickems_channels(guild, current_guild_pickem_channels)
            )
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

                for user, data in leaderboard.items():
                    data["weekly"] = 0
            self.bot.loop.create_task(self.add_weekly_pickems_credits(guild, top_members))

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
                    log.error(f"Could not add credits to {repr(member)}")

    async def create_pickems_channel(
        self, name: str, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
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
        if game.game_state == "Final":
            team = game.home_team if game.home_score > game.away_score else game.away_team
            team_emoji = game.home_emoji if game.home_score > game.away_score else game.away_emoji
            winner = _("**WINNER:** {team_emoji} {team}").format(team_emoji=team_emoji, team=team)
        timezone = await self.pickems_config.guild(guild).pickems_timezone()
        if timezone is None:
            game_start = utc_to_local(game.game_start, TEAMS[game.home_team]["timezone"])
        else:
            game_start = utc_to_local(game.game_start, timezone)
        time_str = game_start.strftime("%B %d, %Y at %I:%M %p %Z")
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

    async def create_pickems_game_message(self, channel: discord.TextChannel, game: Game) -> None:
        msg = await self.make_pickems_msg(channel.guild, game)
        try:
            new_msg = await channel.send(msg)
        except discord.Forbidden:
            log.error(f"Could not send pickems message in {repr(channel)}")
            return
        except Exception:
            log.exception("Error sending messages in pickems channel.")
            return
        # Create new pickems object for the game
        try:
            await self.create_pickem_object(channel.guild, new_msg, channel, game)
        except Exception:
            log.exception("Error creating pickems Object.")
        if channel.permissions_for(channel.guild.me).add_reactions:
            start_adding_reactions(new_msg, [game.away_emoji[2:-1], game.home_emoji[2:-1]])

    async def create_pickems_channels_and_message(
        self, guilds: List[discord.Guild], day: datetime
    ) -> Dict[int, List[int]]:
        chn_name = _("pickems-{month}-{day}").format(month=day.month, day=day.day)
        data = []
        channel_tasks = []
        save_data = {}
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

        games_list = await Game.get_games(None, day, day, self.session)

        msg_tasks = []
        for game in games_list:
            for channel in data:
                if channel:
                    msg_tasks.append(self.create_pickems_game_message(channel, game))
        await bounded_gather(*msg_tasks)
        return save_data

    async def create_weekly_pickems_pages(self, guilds: List[discord.Guild]) -> None:
        save_data = {}
        today = datetime.now()
        tasks = []
        for days in range(7):
            if (today + timedelta(days=days)).weekday() == 6 and days != 0:
                # This was originally to prevent an infinite loop
                # now this is required to only make pages until the following
                # Sunday so that we're not creating more channels than necessary
                # unless it's sunday
                break
            tasks.append(
                self.create_pickems_channels_and_message(guilds, today + timedelta(days=days))
            )

        guild_data = await bounded_gather(*tasks)
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
            await self.pickems_config.guild(guild).pickems_channels.set(channels)

    async def delete_pickems_channels(self, guild: discord.Guild, channels: List[int]) -> None:
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
                log.error(f"Missing permissions to delete old pickems channel in {repr(guild)}")
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
                game = await pickems.get_game()
                self.pickems_games[name] = game
                await self.set_guild_pickem_winner(self.pickems_games[name])
                # Go through all the current pickems for every server
                # and handle editing postponed games, etc here
                # This will ensure any games that never make it to
                # the main loop still get checked
            if not await pickems.check_winner(self.pickems_games[name]):
                continue
            log.debug(f"Tallying results for {repr(pickems)}")
            to_remove.append(name)
            async with self.pickems_config.guild(guild).leaderboard() as leaderboard:
                for user, choice in pickems.votes.items():
                    if str(user) not in leaderboard:
                        leaderboard[str(user)] = {"season": 0, "weekly": 0, "total": 0}
                    if choice == pickems.winner:
                        if member := guild.get_member(int(user)):
                            try:
                                await bank.deposit_credits(member, int(base_credits))
                            except Exception:
                                log.debug(f"Could not deposit pickems credits for {repr(member)}")
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
                log.debug(f"Removing pickem {name}")
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
            guild = self.bot.get_guild(id=int(guild_id))
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

    @hockeyset_commands.group(name="pickems")
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
        data = await self.pickems_config.guild(ctx.guild).all()
        category_channel = ctx.guild.get_channel(data.get("pickems_category"))
        category = category_channel.mention if category_channel else None
        timezone = data["pickems_timezone"] or _("Home Teams Timezone")
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
        if timezone is None:
            timezone = _("Home Teams Timezone")
        msg = _(
            "**Pickems Settings for {guild}**\n"
            "__Category:__ **{category}**\n"
            "__Timezone:__ **{timezone}**\n"
            "__Base {currency}:__ {base_credits}\n"
            "__Weekly {currency}:__ Top {top_members} members will earn {top_credits} {currency}\n"
            "__Channels:__\n {channels}\n"
        ).format(
            guild=ctx.guild.name,
            category=category,
            channels="\n".join([f"<#{chan}>" for chan in data.get("pickems_channels")]),
            timezone=timezone,
            currency=currency_name,
            top_members=top_members,
            top_credits=top_credits,
            base_credits=base_credits,
        )
        await ctx.maybe_send_embed(msg)

    @pickems_commands.group(name="credits")
    async def pickems_credits(self, ctx: commands.Context) -> None:
        """
        Settings for awarding credits on correct pickems votes
        """
        pass

    @pickems_credits.command(name="base")
    async def pickems_credits_base(
        self, ctx: commands.Context, _credits: Optional[int] = None
    ) -> None:
        """
        Set the base awarded credits for correct pickems votes.

        `<_credits>` The number of credits that will be awarded to everyone
        who voted correctly on the game.
        """
        if _credits and _credits <= 0:
            _credits = None
        global_bank = await bank.is_global()
        set_credits = False
        if global_bank and not await self.bot.is_owner(ctx.author):
            return await ctx.send(
                _("This command is restricted to bot owner while the bank is global.")
            )
        elif global_bank and await self.bot.is_owner(ctx.author):
            if _credits is not None:
                set_credits = True
                await self.pickems_config.base_credits.set(int(_credits))
            else:
                await self.pickems_config.base_credits.clear()
        elif not global_bank:
            if _credits is not None:
                set_credits = True
                await self.pickems_config.guild(ctx.guild).base_credits.set(int(_credits))
            else:
                await self.pickems_config.guild(ctx.guild).base_credits.clear()
        if set_credits:
            await ctx.send(
                _("Correct pickems voters will receive {credits} {credits_name}.").format(
                    credits=_credits,
                    credits_name=await bank.get_currency_name(ctx.guild),
                )
            )
        else:
            await ctx.send(_("Base credits for correct pickems votes have been removed."))

    @pickems_credits.command(name="top")
    async def pickems_credits_top(
        self, ctx: commands.Context, _credits: Optional[int] = None
    ) -> None:
        """
        Set the amount of credits awarded for the top x winners of pickems.

        `<credits>` The number of credits that will be awarded to the winners
        every week.
        """
        if _credits and _credits <= 0:
            _credits = None
        global_bank = await bank.is_global()
        if global_bank and not await self.bot.is_owner(ctx.author):
            return await ctx.send(
                _("This command is restricted to bot owner while the bank is global.")
            )
        elif global_bank and await self.bot.is_owner(ctx.author):
            if _credits is not None:
                await self.pickems_config.top_credits.set(int(_credits))
            else:
                await self.pickems_config.top_credits.clear()
        elif not global_bank:
            if _credits is not None:
                await self.pickems_config.guild(ctx.guild).top_credits.set(int(_credits))
            else:
                await self.pickems_config.guild(ctx.guild).top_credits.clear()
        if global_bank:
            amount = await self.pickems_config.top_amount()
        else:
            amount = await self.pickems_config.guild(ctx.guild).top_amount()
        await ctx.send(
            _(
                "The top {amount} users every week will receive {pickems_credits} {currency_name}."
            ).format(
                amount=amount,
                pickems_credits=_credits,
                currency_name=await bank.get_currency_name(ctx.guild),
            )
        )

    @pickems_credits.command(name="amount")
    async def pickems_credits_amount(
        self, ctx: commands.Context, amount: Optional[int] = None
    ) -> None:
        """
        Set the number of top winners to receive the top weekly award credits.

        `<amount>` The number of top members to receive the weekly awarded amount.
        """
        if amount and amount <= 0:
            amount = None
        global_bank = await bank.is_global()
        if global_bank and not await self.bot.is_owner(ctx.author):
            return await ctx.send(
                _("This command is restricted to bot owner while the bank is global.")
            )
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
        await ctx.send(
            _(
                "The top {amount} users every week will receive {pickems_credits} {currency_name}."
            ).format(
                amount=amount,
                pickems_credits=pickems_credits,
                currency_name=await bank.get_currency_name(ctx.guild),
            )
        )

    @pickems_commands.command(name="message")
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
        msg = _("Pickems pages will now start with:\n{message}").format(message=msg)
        for page in pagify(msg):
            await ctx.send(page)

    @pickems_commands.command(name="timezone", aliases=["timezones", "tz"])
    async def set_pickems_timezone(
        self, ctx: commands.Context, timezone: Optional[TimezoneFinder] = None
    ) -> None:
        """
        Customize the timezone pickems utilize in this server

        `[timezone]` The full name of the timezone you want to set. For a list of
        available timezone names use `[p]hockeyset pickems timezone list`
        defaults to US/Pacific if not provided.
        """
        if timezone is not None:
            await self.pickems_config.guild(ctx.guild).pickems_timezone.set(timezone)
        else:
            await self.pickems_config.guild(ctx.guild).pickems_timezone.clear()
            timezone = "US/Pacific"
        msg = _("Pickems Timezone set to {timezone}").format(timezone=timezone)
        await ctx.send(msg)

    @pickems_commands.command(name="setup", aliases=["auto", "set"])
    @commands.admin_or_permissions(manage_channels=True)
    async def setup_auto_pickems(
        self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None
    ) -> None:
        """
        Sets up automatically created pickems channels every week.

        `[category]` the channel category where pickems channels will be created.
        This must be the category ID. If not provided this will use the current
        channels category if it exists.
        """

        if category is None and not ctx.channel.category:
            return await ctx.send(_("A channel category is required."))
        elif category is None and ctx.channel.category is not None:
            category = ctx.channel.category

        if not category.permissions_for(ctx.me).manage_channels:
            await ctx.send(_("I don't have manage channels permission!"))
            return

        await self.pickems_config.guild(ctx.guild).pickems_category.set(category.id)
        existing_channels = await self.pickems_config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            cant_delete = []
            for chan_id in existing_channels:
                channel = ctx.guild.get_channel(chan_id)
                if channel:
                    try:
                        await channel.delete()
                    except discord.errors.Forbidden:
                        cant_delete.append(chan_id)
                await self.pickems_config.guild(ctx.guild).pickems_channels.clear()
                if cant_delete:
                    chans = humanize_list([f"<#{_id}>" for _id in cant_delete])
                    await ctx.send(
                        _(
                            "I tried to delete the following channels without success:\n{chans}"
                        ).format(chans=chans)
                    )
        await self.create_weekly_pickems_pages([ctx.guild])
        await ctx.send(_("I will now automatically create pickems pages every Sunday."))

    @pickems_commands.command(name="clear")
    @commands.admin_or_permissions(manage_channels=True)
    async def delete_auto_pickems(self, ctx: commands.Context) -> None:
        """
        Automatically delete all the saved pickems channels.
        """
        existing_channels = await self.pickems_config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            cant_delete = []
            for chan_id in existing_channels:
                channel = ctx.guild.get_channel(chan_id)
                if channel:
                    try:
                        await channel.delete()
                    except discord.errors.Forbidden:
                        cant_delete.append(chan_id)
                await self.pickems_config.guild(ctx.guild).pickems_channels.clear()
                if cant_delete:
                    chans = humanize_list([f"<#{_id}>" for _id in cant_delete])
                    await ctx.send(
                        _(
                            "I tried to delete the following channels without success:\n{chans}"
                        ).format(chans=chans)
                    )
        await ctx.send(_("I have deleted existing pickems channels."))

    @pickems_commands.command(name="toggle")
    @commands.admin_or_permissions(manage_channels=True)
    async def toggle_auto_pickems(self, ctx: commands.Context) -> None:
        """
        Turn off automatic pickems page creation
        """
        await self.pickems_config.guild(ctx.guild).pickems_category.clear()
        await ctx.send(_("I will not automatically generate pickems in this server."))

    @pickems_commands.command(name="page")
    @commands.admin_or_permissions(manage_channels=True)
    async def pickems_page(self, ctx, date: Optional[str] = None) -> None:
        """
        Generates a pickems page for voting on

        `[date]` is a specified day in the format "YYYY-MM-DD"
        if `date` is not provided the current day is used instead.
        """
        if date is None:
            new_date = datetime.now()
        else:
            try:
                new_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return await ctx.send(_("`date` must be in the format `YYYY-MM-DD`."))
        guild_message = await self.pickems_config.guild(ctx.guild).pickems_message()
        msg = _(PICKEMS_MESSAGE).format(guild_message=guild_message)
        games_list = await Game.get_games(None, new_date, new_date, session=self.session)
        for page in pagify(msg):
            await ctx.send(page)
        for game in games_list:
            await self.create_pickems_game_message(ctx.channel, game)

    @pickems_commands.command(name="remove")
    async def rempickem(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Clears the servers current pickems object list

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if true_or_false:
            await self.pickems_config.guild(ctx.guild).pickems.clear()
            try:
                del self.all_pickems[str(ctx.guild.id)]
            except KeyError:
                pass
            await ctx.send(_("All pickems removed on this server."))
        else:
            await ctx.send(_("I will not remove the current pickems on this server."))

    @pickems_commands.group(name="leaderboard")
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
        if true_or_false:
            async with self.pickems_config.guild(ctx.guild).leaderboard() as leaderboard:
                if leaderboard is None:
                    leaderboard = {}
                for user in leaderboard:
                    leaderboard[str(user)]["season"] = 0
            await ctx.send(_("Servers weekly leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems seasonal leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="setuser")
    async def leaderboardset(
        self,
        ctx: commands.Context,
        user: discord.Member,
        season: int,
        weekly: int = None,
        total: int = None,
    ) -> None:
        """
        Allows moderators to set a users points on the leaderboard
        """
        if weekly is None:
            weekly = season
        if total is None:
            total = season
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if leaderboard == {} or leaderboard is None:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return
        if str(user.id) not in leaderboard:
            leaderboard[str(user.id)] = {"season": season, "weekly": weekly, "total": total}
        else:
            del leaderboard[str(user.id)]
            leaderboard[str(user.id)] = {"season": season, "weekly": weekly, "total": total}
        await self.config.guild(ctx.guild).leaderboard.set(leaderboard)
        msg = _(
            "{user} now has {season} points on the season, "
            "{weekly} points for the week, and {total} votes overall."
        ).format(user=user.display_name, season=season, weekly=weekly, total=total)
        await ctx.send(msg)
