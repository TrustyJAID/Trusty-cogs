import asyncio
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
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.utils.menus import start_adding_reactions


from .abc import MixinMeta
from .errors import NotAValidTeamError, UserHasVotedError, VotingHasEndedError
from .game import Game
from .pickems import Pickems

_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.Hockey")

hockeyset_commands = MixinMeta.hockeyset_commands
# defined in abc.py allowing this to be inherited by multiple files


class HockeyPickems(MixinMeta):
    """
    Hockey Pickems Logic
    """

    def __init__(self, *args):
        self.pickems_lock = asyncio.lock()

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
            if f"{channel.id}-{payload.message_id}" in pickem.messages:
                reply_message = ""
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
                    except discord.HTTPException:
                        log.error(f"Error trying to DM {repr(user)}")
                    except Exception:
                        log.exception(f"Error trying to send message to {repr(user)}")
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
                await self.all_pickems[str(guild_id)][pickem_name].check_winner(game)

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
        old_pickem = self.all_pickems[str(guild.id)].get(new_name, None)

        if old_pickem is None:
            pickems[new_name] = Pickems.from_json(
                {
                    "messages": [f"{channel.id}-{message.id}"],
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
            log.debug(f"creating new pickems {pickems[new_name]}")
            return True
        else:
            old_pickem.messages.append(f"{channel.id}-{message.id}")
            if not old_pickem.link:
                old_pickem.link = game.link
            pickems[old_pickem.name] = old_pickem
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

    async def create_pickems_channels_and_message(
        self, guilds: List[discord.Guild], day: datetime
    ):
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
                    msg_tasks.append(self.create_pickems_game_msg(channel, game))
        await bounded_gather(*msg_tasks)
        return save_data

    async def create_weekly_pickems_pages(self, guilds: List[discord.Guild]):
        save_data = {}
        today = datetime.now()
        tasks = []
        for days in range(7):
            tasks.append(
                self.create_pickems_channels_and_message(guilds, today + timedelta(days=days))
            )
            if today.weekday() == 6:
                # just incase we end up in an infinite loop somehow
                # can never be too careful with async coding
                break

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
                log.debug(f"Tallying results for {repr(pickems)}")
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
                log.debug(f"Removing pickem {name}")
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

    @hockeyset_commands.group(name="pickems")
    @commands.admin_or_permissions(manage_channels=True)
    async def pickems_commands(self, ctx: commands.Context):
        """
        Commands for managing pickems
        """
        pass

    @pickems_commands.command(name="settings")
    async def pickems_settings(self, ctx: commands.Context):
        """
        Show the servers current pickems settings
        """
        data = await self.pickems_config.guild(ctx.guild).all()
        category_channel = ctx.guild.get_channel(data.get("pickems_category"))
        category = category_channel.mention if category_channel else None
        msg = _("Pickems Settings for {guild}\nCategory: {category}\nChannels: {channels}").format(
            guild=ctx.guild.name,
            category=category,
            channels=humanize_list([f"<#{chan}>" for chan in data.get("pickems_channels")]),
        )
        await ctx.maybe_send_embed(msg)

    @pickems_commands.command(name="setup", aliases=["auto", "set"])
    @commands.admin_or_permissions(manage_channels=True)
    async def setup_auto_pickems(
        self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None
    ):
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
    async def delete_auto_pickems(self, ctx: commands.Context):
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
    async def toggle_auto_pickems(self, ctx: commands.Context):
        """
        Turn off automatic pickems page creation
        """
        await self.pickems_config.guild(ctx.guild).pickems_category.clear()
        await ctx.send(_("I will not automatically generate pickems in this server."))

    @pickems_commands.command(name="page")
    @commands.admin_or_permissions(manage_channels=True)
    async def pickems_page(self, ctx, date: Optional[str] = None):
        """
        Generates a pickems page for voting on a specified day must be "YYYY-MM-DD"
        """
        if date is None:
            new_date = datetime.now()
        else:
            try:
                new_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return await ctx.send(_("`date` must be in the format `YYYY-MM-DD`."))
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
        games_list = await Game.get_games(None, new_date, new_date, session=self.session)
        await ctx.send(msg)
        for game in games_list:
            new_msg = await ctx.send(
                "__**{} {}**__ @ __**{} {}**__".format(
                    game.away_emoji, game.away_team, game.home_emoji, game.home_team
                )
            )
            # Create new pickems object for the game

            await self.create_pickem_object(ctx.guild, new_msg, ctx.channel, game)
            if ctx.channel.permissions_for(ctx.guild.me).add_reactions:
                try:
                    await new_msg.add_reaction(game.away_emoji[2:-1])
                    await new_msg.add_reaction(game.home_emoji[2:-1])
                except Exception:
                    log.debug("Error adding reactions")

    @pickems_commands.command(name="remove")
    async def rempickem(self, ctx: commands.Context, true_or_false: bool):
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
    async def pickems_leaderboard_commands(self, ctx: commands.Context):
        """
        Settings for clearing/resetting pickems leaderboards
        """
        pass

    @pickems_leaderboard_commands.command(name="clear")
    async def clear_server_leaderboard(self, ctx: commands.Context, true_or_false: bool):
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
    async def tally_server_leaderboard(self, ctx: commands.Context, true_or_false: bool):
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
    async def clear_weekly_leaderboard(self, ctx: commands.Context, true_or_false: bool):
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
    async def clear_seasonal_leaderboard(self, ctx: commands.Context, true_or_false: bool):
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
