from datetime import datetime
from redbot.core import Config
from .game import Game
from .constants import CONFIG_ID, TEAMS
from .pickems import Pickems
from .helper import utc_to_local
import logging

log = logging.getLogger("red.trusty-cogs.Hockey")


class GameDayChannels:
    """
        This is where the functions to handle creation and deletion
        of game day channels is stored
    """

    def __init__(self):
        pass

    @staticmethod
    async def get_chn_name(game):
        """
            Creates game day channel name
        """
        timestamp = utc_to_local(game.game_start)
        chn_name = "{}-vs-{}-{}-{}-{}".format(
            game.home_abr, game.away_abr, timestamp.year, timestamp.month, timestamp.day
        )
        return chn_name.lower()

    @staticmethod
    async def check_new_gdc(bot):
        config = Config.get_conf(None, CONFIG_ID, cog_name="Hockey")
        game_list = await Game.get_games()  # Do this once so we don't spam the api
        for guilds in await config.all_guilds():
            guild = bot.get_guild(guilds)
            if guild is None:
                continue
            if not await config.guild(guild).create_channels():
                continue
            team = await config.guild(guild).gdc_team()
            if team != "all":
                next_games = await Game.get_games_list(team, datetime.now())
                next_game = None
                if next_games != []:
                    next_game = await Game.from_url(next_games[0]["link"])
                if next_game is None:
                    continue
                chn_name = await GameDayChannels.get_chn_name(next_game)
                try:
                    cur_channels = await config.guild(guild).gdc()
                    cur_channel = bot.get_channel(cur_channels[0])
                except Exception:
                    log.error("Error checking new GDC", exc_info=True)
                    cur_channel = None
                if cur_channel is None:
                    await GameDayChannels.create_gdc(bot, guild)
                elif cur_channel.name != chn_name.lower():
                    await GameDayChannels.delete_gdc(bot, guild)
                    await GameDayChannels.create_gdc(bot, guild)

            else:
                await GameDayChannels.delete_gdc(bot, guild)
                for game in game_list:
                    await GameDayChannels.create_gdc(bot, guild, game)

    @staticmethod
    async def create_gdc(bot, guild, game_data=None):
        """
            Creates a game day channel for the given game object
            if no game object is passed it looks for the set team for the guild
            returns None if not setup
        """
        config = Config.get_conf(None, CONFIG_ID, cog_name="Hockey")
        guild_data = await config.guild(guild).all()
        if "category" not in guild_data:
            return
        category = bot.get_channel(guild_data["category"])
        if category is None:
            # Return none if there's no category to create the channel
            return
        if game_data is None:
            team = guild_data["gdc_team"]

            next_games = await Game.get_games_list(team, datetime.now())
            if next_games != []:
                next_game = await Game.from_url(next_games[0]["link"])
                if next_game is None:
                    return
            else:
                # Return if no more games are playing for this team
                return
        else:
            team = game_data.home_team
            next_game = game_data

        chn_name = await GameDayChannels.get_chn_name(next_game)
        try:
            new_chn = await guild.create_text_channel(chn_name, category=category)
        except Exception:
            log.error("Error creating channels in {}".format(guild.name), exc_info=True)
            return
        # cur_channels = await config.guild(guild).gdc()
        if "gdc" not in guild_data:
            guild_data["gdc"] = []
        if guild_data["gdc"] is None:
            guild_data["gdc"] = []
        guild_data["gdc"].append(new_chn.id)
        await config.guild(guild).gdc.set(guild_data["gdc"])
        # await config.guild(guild).create_channels.set(True)
        await config.channel(new_chn).team.set([team])
        # delete_gdc = await config.guild(guild).delete_gdc()
        await config.channel(new_chn).to_delete.set(guild_data["delete_gdc"])

        # Gets the timezone to use for game day channel topic
        # timestamp = datetime.strptime(next_game.game_start, "%Y-%m-%dT%H:%M:%SZ")
        # guild_team = await config.guild(guild).gdc_team()
        channel_team = team if team != "all" else next_game.home_team
        timezone = (
            TEAMS[channel_team]["timezone"]
            if channel_team in TEAMS
            else TEAMS[next_game.away_team]["timezone"]
        )
        time_string = utc_to_local(next_game.game_start, timezone).strftime(
            "%A %B %d, %Y at %I:%M %p %Z"
        )

        game_msg = (
            f"{next_game.away_team} {next_game.away_emoji} @ "
            f"{next_game.home_team} {next_game.home_emoji} {time_string}"
        )

        await new_chn.edit(topic=game_msg)
        if new_chn.permissions_for(guild.me).embed_links:
            em = await next_game.game_state_embed()
            preview_msg = await new_chn.send(embed=em)
        else:
            preview_msg = await new_chn.send(await next_game.game_state_text())

        # Create new pickems object for the game
        await Pickems.create_pickem_object(guild, preview_msg, new_chn, next_game)

        if new_chn.permissions_for(guild.me).manage_messages:
            await preview_msg.pin()
        if new_chn.permissions_for(guild.me).add_reactions:
            try:
                await preview_msg.add_reaction(next_game.away_emoji[2:-1])
                await preview_msg.add_reaction(next_game.home_emoji[2:-1])
            except Exception:
                log.debug("cannot add reactions")

    @staticmethod
    async def delete_gdc(bot, guild):
        """
            Deletes all game day channels in a given guild
        """
        config = Config.get_conf(None, CONFIG_ID, cog_name="Hockey")
        channels = await config.guild(guild).gdc()

        for channel in channels:
            chn = bot.get_channel(channel)
            if chn is None:
                try:
                    await config._clear_scope(Config.CHANNEL, str(chn))
                except Exception:
                    pass
                continue
            if not await config.channel(chn).to_delete():
                continue
            try:
                await config.channel(chn).clear()
                await chn.delete()
            except Exception:
                log.error("Cannot delete GDC channels")
        await config.guild(guild).gdc.set([])
