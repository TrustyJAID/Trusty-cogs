import logging
from copy import copy
from typing import Optional, Union

import discord
import tekore
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .helpers import (
    SPOTIFY_RE,
    InvalidEmoji,
    NotPlaying,
    RecommendationsConverter,
    ScopeConverter,
    SearchTypes,
    SpotifyURIConverter,
    song_embed,
    time_convert,
)
from .menus import (
    SpotifyAlbumPages,
    SpotifyArtistPages,
    SpotifyBaseMenu,
    SpotifyDeviceView,
    SpotifyEpisodePages,
    SpotifyNewPages,
    SpotifyPages,
    SpotifyPlaylistPages,
    SpotifyPlaylistsPages,
    SpotifyRecentSongPages,
    SpotifySearchMenu,
    SpotifySelectDevice,
    SpotifyShowPages,
    SpotifyTopArtistsPages,
    SpotifyTopTracksPages,
    SpotifyTrackPages,
    SpotifyUserMenu,
    emoji_handler,
)

log = logging.getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)

ActionConverter = commands.get_dict_converter(*emoji_handler.emojis.keys(), delims=[" ", ",", ";"])


class SpotifyCommands:

    @commands.group(name="spotify", aliases=["sp"])
    async def spotify_com(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Spotify commands
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "now": self.spotify_now,
                "recommendations": self.parse_spotify_recommends,
                "forgetme": self.spotify_forgetme,
                "me": self.spotify_me,
                "search": self.spotify_search,
                "genres": self.spotify_genres,
                "recent": self.spotify_recently_played,
                "pause": self.spotify_pause,
                "resume": self.spotify_resume,
                "next": self.spotify_next,
                "previous": self.spotify_previous,
                "play": self.spotify_play,
                "queue": self.spotify_queue_add,
                "repeat": self.spotify_repeat,
                "seek": self.spotify_seek,
                "volume": self.spotify_volume,
                "device": self.spotify_device,
                "playlist": self.spotify_playlist,
                "set": self.spotify_set,
            }
            option = ctx.data["options"][0]["name"]
            func = command_mapping[option]
            if getattr(func, "requires", None):
                if not await self.check_requires(func, ctx):
                    return
            if option == "recommendations":
                await func(ctx)
                return

            try:
                kwargs = {}
                for option in ctx.data["options"][0].get("options", []):
                    kwargs[option["name"]] = self.convert_slash_args(ctx, option)
            except KeyError:
                kwargs = {}
                pass
            except AttributeError:
                log.exception("Error converting interaction arguments")
                await ctx.response.send_message(
                    _("One or more options you have provided are not available in DM's."), ephemeral=True
                )
                return
            await func(ctx, **kwargs)

    @spotify_com.group(name="set")
    async def spotify_set(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Setup Spotify cog
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {}
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            try:
                kwargs = {
                    i["name"]: i["value"]
                    for i in ctx.data["options"][0]["options"][0].get("options", [])
                }
            except KeyError:
                kwargs = {}
                pass
            await func(ctx, **kwargs)

    @spotify_com.group(name="playlist", aliases=["playlists"])
    async def spotify_playlist(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View Spotify Playlists
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "add": self.spotify_playlist_add,
                "create": self.spotify_playlist_create,
                "featured": self.spotify_playlist_featured,
                "follow": self.spotify_playlist_follow,
                "list": self.spotify_playlist_list,
                "remove": self.spotify_playlist_remove,
                "view": self.spotify_playlist_view,
            }
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            if getattr(func, "requires", None):
                if not await self.check_requires(func, ctx):
                    return
            try:
                kwargs = {
                    i["name"]: i["value"]
                    for i in ctx.data["options"][0]["options"][0].get("options", [])
                }
            except KeyError:
                kwargs = {}
                pass
            await func(ctx, **kwargs)

    @spotify_com.group(name="artist", aliases=["artists"])
    async def spotify_artist(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View Spotify Artist info
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "follow": self.spotify_artist_follow,
                "albums": self.spotify_artist_albums,
            }
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            if getattr(func, "requires", None):
                if not await self.check_requires(func, ctx):
                    return
            try:
                kwargs = {
                    i["name"]: i["value"]
                    for i in ctx.data["options"][0]["options"][0].get("options", [])
                }
            except KeyError:
                kwargs = {}
                pass
            await func(ctx, **kwargs)

    @spotify_com.group(name="device")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_device(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Spotify device commands
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "transfer": self.spotify_device_transfer,
                "default": self.spotify_device_default,
                "list": self.spotify_device_list,
            }
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            if getattr(func, "requires", None):
                if not await self.check_requires(func, ctx):
                    return
            command_options = ctx.data["options"][0]["options"][0].get("options", [])
            if ctx.type.value == 4:
                cur_value = command_options[0]["value"]
                if not await self.config.user(ctx.user).token():
                    # really don't want to force users to auth from autocomplete
                    log.debug("No tokens.")
                    return
                user_token = await self.get_user_auth(ctx)
                if not user_token:
                    log.debug("STILL No tokens.")
                    return
                if ctx.user.id not in self._temp_user_devices:
                    try:
                        user_devices = []
                        user_spotify = tekore.Spotify(sender=self._sender)
                        with user_spotify.token_as(user_token):
                            devices = await user_spotify.playback_devices()
                        for d in devices:
                            user_devices.append({"name": d.name, "value": d.id})
                        self._temp_user_devices[ctx.user.id] = user_devices
                    except Exception:
                        log.exception("uhhhhhh")
                        return

                choices = [i for i in self._temp_user_devices[ctx.user.id] if cur_value in i["name"].lower()]
                await ctx.response.auto_complete(choices[:25])
                return
            try:
                kwargs = {
                    i["name"]: i["value"]
                    for i in ctx.data["options"][0]["options"][0].get("options", [])
                }
            except KeyError:
                kwargs = {}
                pass
            await func(ctx, **kwargs)

    @spotify_set.group(name="slash")
    @commands.admin_or_permissions(manage_guild=True)
    async def spotify_slash(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Slash command toggling for Spotify
        """
        pass

    @spotify_slash.command(name="context")
    async def spotify_context(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Toggle right click play on spotify for messages
        """
        play = {
            "name": "Play on Spotify",
            "type": 3,
        }
        queue = {
            "name": "Queue on Spotify",
            "type": 3,
        }
        async with self.config.guild(ctx.guild).commands() as commands:
            if "play on spotify" in commands:
                command_id = commands["play on spotify"]
                try:
                    await ctx.bot.http.delete_guild_command(ctx.guild.me.id, ctx.guild.id, command_id)
                    del commands["play on spotify"]
                except Exception:
                    pass

            else:
                data = await ctx.bot.http.upsert_guild_command(ctx.guild.me.id, ctx.guild.id, payload=play)
                command_id = int(data.get("id"))
                commands["play on spotify"] = command_id
                if ctx.guild.id not in self.slash_commands["guilds"]:
                    self.slash_commands["guilds"][ctx.guild.id] = {}
                self.slash_commands["guilds"][ctx.guild.id][command_id] = self.play_from_message

            if "queue on spotify" in commands:
                command_id = commands["queue on spotify"]
                try:
                    await ctx.bot.http.delete_guild_command(ctx.guild.me.id, ctx.guild.id, command_id)
                    del commands["queue on spotify"]
                except Exception:
                    pass

            else:
                data = await ctx.bot.http.upsert_guild_command(ctx.guild.me.id, ctx.guild.id, payload=queue)
                command_id = int(data.get("id"))
                commands["queue on spotify"] = command_id
                if ctx.guild.id not in self.slash_commands["guilds"]:
                    self.slash_commands["guilds"][ctx.guild.id] = {}
                self.slash_commands["guilds"][ctx.guild.id][command_id] = self.queue_from_message

        await ctx.tick()

    @spotify_slash.command(name="globalcontext")
    @commands.is_owner()
    async def spotify_global_context(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Toggle right click play on spotify for messages
        """
        play = {
            "name": "Play on Spotify",
            "type": 3,
        }
        queue = {
            "name": "Queue on Spotify",
            "type": 3,
        }
        async with self.config.commands() as commands:
            if "play on spotify" in commands:
                command_id = commands["play on spotify"]
                try:
                    await ctx.bot.http.delete_global_command(ctx.me.id, command_id)
                    del commands["play on spotify"]
                    del self.slash_commands[command_id]
                except Exception:
                    pass
            else:
                data = await ctx.bot.http.upsert_global_command(ctx.guild.me.id, payload=play)
                command_id = int(data.get("id"))
                commands["play on spotify"] = command_id
                self.slash_commands[command_id] = self.play_from_message

            if "queue on spotify" in commands:
                command_id = commands["queue on spotify"]
                try:
                    await ctx.bot.http.delete_global_command(ctx.me.id, command_id)
                    del commands["queue on spotify"]
                    del self.slash_commands[command_id]
                except Exception:
                    pass
            else:
                data = await ctx.bot.http.upsert_global_command(ctx.guild.me.id, payload=queue)
                command_id = int(data.get("id"))
                commands["queue on spotify"] = command_id
                self.slash_commands[command_id] = self.queue_from_message

        await ctx.tick()

    @spotify_slash.command(name="global")
    @commands.is_owner()
    async def spotify_global_slash(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Enable Spotify commands as slash commands globally
        """
        data = await ctx.bot.http.upsert_global_command(ctx.guild.me.id, payload=self.SLASH_COMMANDS)
        command_id = int(data.get("id"))
        log.info(data)
        self.slash_commands[command_id] = self.spotify_com
        async with self.config.commands() as commands:
            commands["spotify"] = command_id
        await ctx.tick()

    @spotify_slash.command(name="globaldel")
    @commands.is_owner()
    async def spotify_global_slash_disable(
        self, ctx: Union[commands.Context, discord.Interaction]
    ):
        """
        Disable Spotify commands as slash commands globally
        """
        commands = await self.config.commands()
        command_id = commands.get("spotify", None)
        if not command_id:
            await ctx.send("There is no global slash command registered from this cog on this bot.")
            return
        await ctx.bot.http.delete_global_command(ctx.me.id, command_id)
        async with self.config.commands() as commands:
            del commands["spotify"]
        await ctx.tick()

    @spotify_slash.command(name="enable")
    @commands.guild_only()
    async def spotify_guild_slash(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Enable Spotify commands as slash commands in this server
        """
        global_commands = await self.config.commands()
        if "spotify" in global_commands:
            await ctx.send(_("This command is already registered globally."))
            return
        data = await ctx.bot.http.upsert_guild_command(ctx.guild.me.id, ctx.guild.id, payload=self.SLASH_COMMANDS)
        command_id = int(data.get("id"))
        if ctx.guild.id not in self.slash_commands["guilds"]:
            self.slash_commands["guilds"][ctx.guild.id] = {}
        self.slash_commands["guilds"][ctx.guild.id][command_id] = self.spotify_com
        async with self.config.guild(ctx.guild).commands() as commands:
            commands["spotify"] = command_id
        await ctx.tick()

    @spotify_slash.command(name="disable")
    @commands.guild_only()
    async def spotify_delete_slash(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Delete servers slash commands
        """

        commands = await self.config.guild(ctx.guild).commands()
        command_id = commands.get("spotify", None)
        if not command_id:
            await ctx.send(_("This command is not enabled in this guild."))
            return
        await ctx.bot.http.delete_guild_command(ctx.guild.me.id, ctx.guild.id, command_id)
        del self.slash_commands["guilds"][ctx.guild.id][command_id]
        async with self.config.guild(ctx.guild).commands() as commands:
            del commands["spotify"]
        global_commands = await self.config.commands()
        if "spotify" in global_commands:
            await ctx.send(_("This command is already registered globally so you may still see it."))
            return
        await ctx.tick()

    async def not_authorized(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("I am not authorized to perform this action for you.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    async def not_playing(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("It appears you're not currently listening to Spotify.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    async def no_user_token(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("You need to authorize me to interact with spotify.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    async def no_device(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("I could not find an active device to play songs on.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    async def forbidden_action(
        self, ctx: Union[commands.Context, discord.Interaction], error: str
    ) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        if "non-premium" in error:
            msg = _("This action is prohibited for non-premium users.")
        else:
            msg = _("I couldn't perform that action for you.")
        msg = _("You need to authorize me to interact with spotify.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    async def unknown_error(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("An exception has occured, please contact the bot owner for more assistance.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)

    @spotify_set.command(name="listen")
    async def set_reaction_listen(
        self, ctx: Union[commands.Context, discord.Interaction], *, listen_for: ActionConverter
    ):
        """
        Set the bot to listen for specific emoji reactions on messages

        If the message being reacted to has somthing valid to search
        for the bot will attempt to play the found search on spotify for you.

        `<listen_for>` Must be one of the following action names followed by an emoji:
        `pause` - Pauses your current Spotify player.
        `repeat` - Changes your current Spotify player to repeat current playlist.
        `repeatone` - Changes your current spotify player to repeat the track.
        `next` - Skips to the next track in queue.
        `previous` - Skips to the previous track in queue.
        `like` - Likes a song link or URI if it is inside the message reacted to.
        `volume_down` - Adjusts the volume of your Spotify player down 10%.
        `volume_up`- Adjusts the volume of your Spotify player up 10%.
        `volume_mute` - Mutes your Spotify player.
        `shuffle` - Shuffles your current Spotify player.
        `play` - Plays a song link or URI if it is inside the message reacted to.
        """
        added = {}
        async with self.config.user(ctx.author).listen_for() as current:
            for action, raw_emoji in listen_for.items():
                if action not in emoji_handler.emojis.keys():
                    continue
                emoji = discord.PartialEmoji.from_str(raw_emoji)
                if emoji.is_custom_emoji():
                    animated = "a" if emoji.animated else ""
                    emoji_str = f"<{animated}:{emoji.name}:{emoji.id}>"
                    current[emoji_str] = action
                    added[emoji_str] = action
                else:
                    try:
                        await ctx.message.add_reaction(str(emoji))
                        current[str(emoji)] = action
                        added[str(emoji)] = action
                    except discord.errors.HTTPException:
                        pass
        msg = _("I will now listen for the following emojis from you:\n")
        for emoji, action in added.items():
            msg += f"{emoji} -> {action}\n"
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="remlisten")
    async def set_reaction_remove_listen(
        self, ctx: Union[commands.Context, discord.Interaction], *emoji_or_name: str
    ):
        """
        Set the bot to listen for specific emoji reactions on messages

        If the message being reacted to has somthing valid to search
        for the bot will attempt to play the found search on spotify for you.

        `<listen_for>` Must be one of the following action names:
        `pause` - Pauses your current Spotify player.
        `repeat` - Changes your current Spotify player to repeat current playlist.
        `repeatone` - Changes your current spotify player to repeat the track.
        `next` - Skips to the next track in queue.
        `previous` - Skips to the previous track in queue.
        `like` - Likes a song link or URI if it is inside the message reacted to.
        `volume_down` - Adjusts the volume of your Spotify player down 10%.
        `volume_up`- Adjusts the volume of your Spotify player up 10%.
        `volume_mute` - Mutes your Spotify player.
        `shuffle` - Shuffles your current Spotify player.
        `play` - Plays a song link or URI if it is inside the message reacted to.
        """
        removed = []
        async with self.config.user(ctx.author).listen_for() as current:
            for name in emoji_or_name:
                if name in current:
                    action = current[name]
                    del current[name]
                    removed.append(f"{name} -> {action}")
                else:
                    to_rem = []
                    for emoji, action in current.items():
                        if name == action:
                            to_rem.append(emoji)
                            removed.append(f"{emoji} -> {action}")
                    if to_rem:
                        for emoji in to_rem:
                            del current[emoji]

        if not removed:
            return await ctx.send(_("None of the listed events were being listened for."))
        msg = _("I will no longer listen for emojis for the following events:\n{listen}").format(
            listen="\n".join(i for i in removed)
        )
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="showsettings", aliases=["settings"])
    @commands.mod_or_permissions(manage_messages=True)
    async def show_settings(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Show settings for menu timeouts
        """
        delete_after = await self.config.guild(ctx.guild).delete_message_after()
        clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
        timeout = await self.config.guild(ctx.guild).menu_timeout()
        msg = _(
            "Delete After: {delete_after}\nClear After: {clear_after}\nTimeout: {timeout}"
        ).format(delete_after=delete_after, clear_after=clear_after, timeout=timeout)
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="showprivate")
    async def show_private(
        self, ctx: Union[commands.Context, discord.Interaction], show_private: bool
    ):
        """
        Set whether or not to show private playlists

        This will also display your spotify username and a link
        to your profile if you use `[p]spotify me` command in public channels.
        """
        await self.config.user(ctx.author).show_private.set(show_private)
        if show_private:
            msg = _("I will show private playlists now.")
        else:
            msg = _("I will stop showing private playlists now.")
        await ctx.send(msg)

    @spotify_set.command(name="clearreactions")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_clear_reactions(
        self, ctx: Union[commands.Context, discord.Interaction], clear_after: bool
    ):
        """
        Set whether or not to clear reactions after sending the message

        Note: the bot requires manage messages for this to work
        """
        await self.config.guild(ctx.guild).clear_reactions_after.set(clear_after)
        if clear_after:
            msg = _("I will now clear reactions after the menu has timed out.\n")
        else:
            msg = _("I will stop clearing reactions after the menu has timed out.\n")
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            msg += _(
                "I don't have manage messages permissions so this might not work as expected."
            )
        await ctx.send(msg)

    @spotify_set.command(name="deletemessage")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_delete_message_after(
        self, ctx: Union[commands.Context, discord.Interaction], delete_after: bool
    ):
        """
        Set whether or not to delete the spotify message after timing out

        """
        await self.config.guild(ctx.guild).delete_message_after.set(delete_after)
        if delete_after:
            msg = _("I will now delete the menu message after timeout.\n")
        else:
            msg = _("I will stop deleting the menu message after timeout.\n")
        await ctx.send(msg)

    @spotify_set.command(name="menutimeout")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_menu_timeout(
        self, ctx: Union[commands.Context, discord.Interaction], timeout: int
    ):
        """
        Set the timeout time for spotify menus

        `<timeout>` The time until the menu will timeout. This does not affect
        interacting with the menu.
        Note: This has a maximum of 10 minutes and a minimum of 30 seconds.
        """
        timeout = max(min(600, timeout), 30)
        await self.config.guild(ctx.guild).menu_timeout.set(timeout)
        msg = _("I will timeout menus after {time} seconds.\n").format(time=timeout)
        await ctx.send(msg)

    @spotify_set.command(name="resetemojis", aliases=["resetemoji"])
    @commands.is_owner()
    async def spotify_reset_emoji(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Resets the bot to use the default emojis
        """
        await self.config.emojis.clear()
        emoji_handler.reload_emojis()
        await ctx.send(_("I will now use the default emojis."))

    @spotify_set.command(name="emojis")
    @commands.is_owner()
    async def spotify_emojis(
        self, ctx: Union[commands.Context, discord.Interaction], *, new_emojis: ActionConverter
    ):
        """
        Change the emojis used by the bot for various actions

        `<new_emojis>` Is a space or comma separated list of name followed by emoji
        for example `[p]spotify set emojis playpause 😃` will then replace ⏯
        usage with the 😃 emoji.

        Available name replacements:
           `playpause` -> ⏯
           `pause` -> ⏸
           `repeat` -> 🔁
           `repeatone` -> 🔂
           `next` -> ⏭
           `previous` -> ⏮
           `like` -> ♥
           `fastforward` -> ⏩
           `rewind` -> ⏪
           `volume_down` -> 🔉
           `volume_up` -> 🔊
           `volume_mute` -> 🔇
           `off` -> ❎
           `playall` -> ⏏
           `shuffle` -> 🔀
           `back_left` -> ◀
           `play` -> ▶
           `queue` -> 🇶
        """
        emojis_changed = {}
        async with self.config.emojis() as emojis:
            for name, raw_emoji in new_emojis.items():
                emoji = discord.PartialEmoji.from_str(raw_emoji)
                if emoji.is_unicode_emoji():
                    try:
                        await ctx.message.add_reaction(str(emoji))
                        emoji_handler.replace_emoji(name, str(emoji))
                        emojis[name] = str(emoji)
                        emojis_changed[name] = str(emoji)
                    except (InvalidEmoji, discord.errors.HTTPException):
                        pass
                else:
                    animated = "a" if emoji.animated else ""
                    emoji_str = f"<{animated}:{emoji.name}:{emoji.id}>"
                    emoji_handler.replace_emoji(name, emoji_str)
                    emojis[name] = emoji_str
                    emojis_changed[name] = str(emoji)

        if not emojis_changed:
            return await ctx.send(_("No emojis have been changed."))
        msg = _("The following emojis have been replaced:\n")
        for name, emoji in emojis_changed.items():
            original = emoji_handler.default[name]
            msg += f"{original} -> {emoji}\n"
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="scope", aliases=["scopes"])
    @commands.is_owner()
    async def spotify_api_scope(
        self, ctx: Union[commands.Context, discord.Interaction], *scopes: ScopeConverter
    ):
        """
        Set customized scope for what you want your bot to allow

        Available options are:
        user-read-private
        user-top-read
        user-read-recently-played
        user-follow-read
        user-library-read
        user-read-currently-playing
        user-read-playback-state
        user-read-playback-position
        playlist-read-collaborative
        playlist-read-private
        user-follow-modify
        user-library-modify
        user-modify-playback-state
        playlist-modify-public
        playlist-modify-private

        You can find more information here:
        https://developer.spotify.com/documentation/general/guides/scopes/
        """
        added = []
        removed = []
        async with self.config.scopes() as current_scope:
            for scope in scopes:
                if scope in current_scope:
                    current_scope.remove(scope)
                    removed.append(scope)
                else:
                    current_scope.append(scope)
                    added.append(scope)
        add = humanize_list(added)
        rem = humanize_list(removed)
        msg = ""
        if add:
            msg += _("The following scopes were added: {added}\n").format(added=add)
        if rem:
            _("The following scopes were removed: {removed}\n").format(removed=rem)
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="currentscope", aliases=["currentscopes"])
    @commands.is_owner()
    async def spotify_view_api_scope(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View the current scopes being requested
        """
        scope = humanize_list(await self.config.scopes())
        await ctx.maybe_send_embed(_("Current scopes:\n{scopes}").format(scopes=scope))

    @spotify_set.command(name="creds")
    @commands.is_owner()
    async def spotify_api_credential_set(self, ctx: Union[commands.Context, discord.Interaction]):
        """Instructions to set the Spotify API tokens."""
        message = _(
            "1. Go to Spotify developers and log in with your Spotify account.\n"
            "(https://developer.spotify.com/dashboard/applications)\n"
            '2. Click "Create An App".\n'
            "3. Fill out the form provided with your app name, etc.\n"
            '4. When asked if you\'re developing commercial integration select "No".\n'
            "5. Accept the terms and conditions.\n"
            "6. Copy your client ID and your client secret into:\n"
            "`{prefix}set api spotify client_id <your_client_id_here> "
            "client_secret <your_client_secret_here>`\n"
            "You may also provide `redirect_uri` in this command with "
            "a different redirect you would like to use but this is optional. "
            "the default redirect_uri is https://localhost/\n\n"
            "Note: The redirect URI Must be set in the Spotify Dashboard and must "
            "match either `https://localhost/` or the one you set with the `[p]set api` command"
        ).format(prefix=ctx.prefix)
        await ctx.maybe_send_embed(message)

    @spotify_set.command(name="forgetme")
    async def spotify_forgetme(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Forget all your spotify settings and credentials on the bot
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
            author = ctx.user
        else:
            author = ctx.author
        await self.config.user(author).clear()
        if author.id in self.dashboard_authed:
            self.dashboard_authed.remove(author.id)
        msg = _("All your spotify data deleted from my settings.")
        if is_slash:
            await ctx.followup.send(msg)
        else:
            await ctx.send(msg)

    @spotify_com.command(name="me")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_me(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Shows your current Spotify Settings
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer(ephemeral=True)
            author = ctx.user
        else:
            author = ctx.author
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(name=author.display_name + _(" Spotify Profile"), icon_url=author.avatar.url)
        msg = ""
        cog_settings = await self.config.user(author).all()
        listen_emojis = "\n".join(
            f"{emoji} -> {action}" for emoji, action in cog_settings["listen_for"].items()
        )
        if not listen_emojis:
            listen_emojis = "Nothing"
        show_private = cog_settings["show_private"]
        msg += _("Watching for Emojis:\n{listen_emojis}\n").format(listen_emojis=listen_emojis)
        msg += _("Show Private Playlists: {show_private}\n").format(show_private=show_private)
        if not cog_settings["token"]:
            em.description = msg
            await ctx.send(embed=em)
            return
        user_token = await self.get_user_auth(ctx)
        if user_token:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user()
                device_id = await self.config.user(author).default_device()
                devices = await user_spotify.playback_devices()
                device_name = "None"
                for d in devices:
                    if d.id == device_id:
                        device_name = d.name
                msg += _("Default Spotify Device: {device}").format(device=device_name)
        if show_private or isinstance(ctx.channel, discord.DMChannel):
            msg += _(
                "Spotify Name: [{display_name}](https://open.spotify.com/user/{user_id})\n"
                "Subscription: {product}\n"
            ).format(display_name=cur.display_name, product=cur.product, user_id=cur.id)
        if isinstance(ctx.channel, discord.DMChannel) or is_slash:
            private = _("Country: {country}\nSpotify ID: {id}\nEmail: {email}\n").format(
                country=cur.country, id=cur.id, email=cur.email
            )
            em.add_field(name=_("Private Data"), value=private)
        if cur.images:
            em.set_thumbnail(url=cur.images[0].url)
        em.description = msg
        if is_slash:
            await ctx.followup.send(embed=em)
        else:
            await ctx.send(embed=em)

    @spotify_com.command(name="now", aliases=["np"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_now(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        detailed: Optional[bool] = False,
        member: Optional[discord.Member] = None,
        public: bool = True,
    ):
        """
        Displays your currently played spotify song

        `[member]` Optional discord member to show their current spotify status
        if they're displaying it on Discord.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer(ephemeral=not public)
            author = ctx.user
        else:
            author = ctx.author
            await ctx.trigger_typing()

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        if member and isinstance(member, discord.Member):
            if not [c for c in member.activities if c.type == discord.ActivityType.listening]:
                msg = _("That user is not currently listening to Spotify on Discord.")
                if is_slash:
                    await ctx.followup.send(msg, ephemeral=True)
                else:
                    await ctx.send(msg)
                return
            else:
                activity = [
                    c for c in member.activities if c.type == discord.ActivityType.listening
                ][0]
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    track = await user_spotify.track(activity.track_id)
        else:
            member = None
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        try:
            if member is None:
                page_source = SpotifyPages(
                    user_token=user_token, sender=self._sender, detailed=detailed
                )
            else:
                page_source = SpotifyTrackPages(items=[track], detailed=detailed)
            x = SpotifyUserMenu(
                source=page_source,
                delete_message_after=delete_after,
                clear_reactions_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
                ctx=ctx,
            )
            await x.send_initial_message(ctx, ctx.channel)
        except NotPlaying:
            await self.not_playing(ctx)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)

    @spotify_com.command(name="share")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_share(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Tell the bot to play the users current song in their current voice channel
        """

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await ctx.send(_("It appears you're not currently listening to Spotify."))
                elif isinstance(cur.item, tekore.model.FullEpisode):
                    return await ctx.send(_("I cannot play podcasts from spotify."))
                elif cur.is_playing and not getattr(cur.item, "is_local", False):
                    msg = copy(ctx.message)
                    msg.content = ctx.prefix + f"play {cur.item.uri}"
                    self.bot.dispatch("message", msg)
                    await ctx.tick()
                else:
                    return await ctx.send(
                        _("You don't appear to be listening to something I can play in audio.")
                    )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="search")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_search(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        detailed: Optional[bool] = False,
        search_type: Optional[SearchTypes] = "track",
        *,
        query: str,
    ):
        """
        Search Spotify for things to play

        `[detailed=False]` Show detailed information for individual tracks.
        `[search_type=track]` The search type, available options are:
         - `track(s)`
         - `artist(s)`
         - `album(s)`
         - `playlist(s)`
         - `show(s)`
         - `episode(s)`
        `<query>` What you want to search for.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()
        search_types = {
            "track": SpotifyTrackPages,
            "artist": SpotifyArtistPages,
            "album": SpotifyAlbumPages,
            "episode": SpotifyEpisodePages,
            "playlist": SpotifyPlaylistPages,
            "show": SpotifyShowPages,
        }
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            search = await user_spotify.search(query, (search_type,), "from_token", limit=50)
            items = search[0].items
        if not search[0].items:
            msg = _("No {search_type} could be found matching that query.").format(
                search_type=search_type
            )
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=search_types[search_type](items=items, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_com.command(name="genres", aliases=["genre"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_genres(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Display all available genres for the recommendations
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer(ephemeral=True)
        else:
            await ctx.trigger_typing()
        try:
            self.GENRES = await self._spotify_client.recommendation_genre_seeds()
        except Exception:
            log.exception("Error grabbing genres.")
            msg = _(
                "The bot owner needs to set their Spotify credentials "
                "before this command can be used."
                " See `{prefix}spotify set creds` for more details."
            ).format(prefix=ctx.clean_prefix)
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
        msg = _(
            "The following are available genres for Spotify's recommendations:\n\n {genres}"
        ).format(genres=humanize_list(self.GENRES))
        if is_slash:
            await ctx.followup.send(msg, ephemeral=True)
        else:
            await ctx.maybe_send_embed(msg)

    @spotify_com.command(name="recommendations", aliases=["recommend", "recommendation"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_recommendations(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        detailed: Optional[bool] = False,
        *,
        recommendations: RecommendationsConverter,
    ):
        """
        Get Spotify Recommendations

        `<recommendations>` Requires at least 1 of the following matching objects:
         - `genre` Must be a valid genre type. Do `[p]spotify genres` to see what's available.
         - `tracks` Any spotify URL or URI leading to tracks will be added to the seed
         - `artists` Any spotify URL or URI leading to artists will be added to the seed

         The following parameters also exist and must include some additional parameter:
         - `acousticness` + a value from 0-100
         - `danceability` + a value from 0-100
         - `duration_ms` the duration target of the tracks
         - `energy` + a value from 0-100
         - `instrumentalness` + a value from 0-100
         - `key` A value from 0-11 representing Pitch Class notation
         - `liveness` + a value from 0-100
         - `loudness` + A value from -60 to 0 represending dB
         - `mode` + either major or minor
         - `popularity` + a value from 0-100
         - `speechiness` + a value from 0-100
         - `tempo` + the tempo in BPM
         - `time_signature` + the measure of bars e.g. `3` for `3/4` or `6/8`
         - `valence` + a value from 0-100
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        log.debug(recommendations)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            try:
                search = await user_spotify.recommendations(**recommendations)
            except Exception:
                log.exception("Error getting recommendations")
                msg = _("I could not find any recommendations with those parameters")
                if is_slash:
                    await ctx.followup.send(msg, ephemeral=True)
                else:
                    await ctx.reply(msg)
                return
            items = search.tracks
        if not items:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=SpotifyTrackPages(items=items, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_com.command(name="recent")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_recently_played(
        self, ctx: Union[commands.Context, discord.Interaction], detailed: Optional[bool] = False
    ):
        """
        Displays your most recently played songs on Spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.playback_recently_played(limit=50)
                tracks = search.items
        except tekore.Unauthorised:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=SpotifyRecentSongPages(tracks=tracks, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_com.command(name="toptracks")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def top_tracks(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your top tracks on spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user_top_tracks(limit=50)
        except tekore.Unauthorised:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
            tracks = cur.items
        x = SpotifyBaseMenu(
            source=SpotifyTopTracksPages(tracks),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_com.command(name="topartists")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def top_artists(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your top tracks on spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user_top_artists(limit=50)
        except tekore.Unauthorised:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        artists = cur.items
        x = SpotifyBaseMenu(
            source=SpotifyTopArtistsPages(artists),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_com.command(name="new")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_new(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List new releases on Spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            playlists = await user_spotify.new_releases(limit=50)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
            playlist_list = playlists.items
        x = SpotifySearchMenu(
            source=SpotifyNewPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_com.command(name="pause")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_pause(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Pauses spotify for you
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_pause()
            if is_slash:
                await ctx.followup.send(_("Pausing playback."), ephemeral=True)
            else:
                await ctx.react_quietly(
                    emoji_handler.get_emoji(
                        "pause", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="resume")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_resume(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Resumes spotify for you
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            device_id = None
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.config.user(author).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        return await self.no_device(ctx)
                else:
                    device = cur.device
                    device_id = device.id
                if not cur or not cur.is_playing:
                    await user_spotify.playback_resume(device_id=device_id)
                else:
                    msg = _("You are already playing music on Spotify.")
                    if is_slash:
                        await ctx.followup.send(msg)
                    else:
                        await ctx.reply(msg)
            if is_slash:
                await ctx.followup.send(_("Resuming playback."))
            else:
                await ctx.react_quietly(
                    emoji_handler.get_emoji(
                        "play", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="next", aliases=["skip"])
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_next(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Skips to the next track in queue on Spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_next()
            if is_slash:
                await ctx.followup.send(_("Skipping to next track."), ephemeral=True)
            else:
                await ctx.react_quietly(
                    emoji_handler.get_emoji(
                        "next", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="previous", aliases=["prev"])
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_previous(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Skips to the previous track in queue on Spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_previous()
            if is_slash:
                await ctx.followup.send(_("Skipping to previous track."), ephemeral=True)
            else:
                await ctx.react_quietly(
                    emoji_handler.get_emoji(
                        "previous", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="play")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_play(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        url_or_playlist_name: Optional[str] = "",
    ):
        """
        Play a track, playlist, or album on Spotify

        `<url_or_playlist_name>` can be multiple spotify track URL *or* URI or
        a single album or playlist link

        if something other than a spotify URL or URI is provided
        the bot will search through your playlists and start playing
        the playlist with the closest matching name
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            user = ctx.user
        else:
            user = ctx.author

        url_or_playlist_name = url_or_playlist_name.replace("🧑‍🎨", ":artist:")
        # because discord will replace this in URI's automatically 🙄
        song_data = SPOTIFY_RE.finditer(url_or_playlist_name)
        tracks = []
        new_uri = ""
        uri_type = ""
        if song_data:
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                uri_type = match.group(2)
                if match.group(2) == "track":
                    tracks.append(match.group(3))
            log.debug(new_uri)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.config.user(user).default_device()
                else:
                    device_id = None
                if tracks:
                    await user_spotify.playback_start_tracks(tracks, device_id=device_id)
                    if is_slash:
                        all_tracks = await user_spotify.tracks(tracks)
                        track = all_tracks[0]
                        track_name = track.name
                        artists = getattr(track, "artists", [])
                        artist = humanize_list([a.name for a in artists])
                        em = await song_embed(track, False)
                        await ctx.followup.send(
                            _("Now playing {track} by {artist}").format(
                                track=track_name, artist=artist
                            ),
                            embed=em,
                            ephemeral=True,
                        )
                    else:
                        await ctx.react_quietly(
                            emoji_handler.get_emoji(
                                "next",
                                ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                            )
                        )
                    return
                if new_uri:
                    await user_spotify.playback_start_context(new_uri, device_id=device_id)
                    if is_slash:
                        if uri_type == "playlist":
                            cur_tracks = await user_spotify.playlist(new_uri)
                            track_name = cur_tracks.name
                            await ctx.followup.send(
                                _("Now playing {track}").format(track=track_name),
                                ephemeral=True,
                            )
                        if uri_type == "artist":
                            artist_id = new_uri.split(":")[-1]
                            cur_tracks = await user_spotify.artist(artist_id)
                            track_name = cur_tracks.name
                            await ctx.followup.send(
                                _("Now playing top tracks by {track}").format(track=track_name),
                                ephemeral=True,
                            )
                        if uri_type == "album":
                            album_id = new_uri.split(":")[-1]
                            cur_tracks = await user_spotify.album(album_id)
                            track_name = cur_tracks.name
                            artists = getattr(cur_tracks, "artists", [])
                            artist = humanize_list([a.name for a in artists])
                            track_artist = humanize_list([a.name for a in artists])
                            await ctx.followup.send(
                                _("Now playing {track} by {artist}.").format(
                                    track=track_name, artist=track_artist
                                ),
                                ephemeral=True,
                            )
                    else:
                        await ctx.react_quietly(
                            emoji_handler.get_emoji(
                                "next",
                                ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                            )
                        )
                    return
                if url_or_playlist_name:
                    cur = await user_spotify.followed_playlists(limit=50)
                    playlists = cur.items
                    while len(playlists) < cur.total:
                        new = await user_spotify.followed_playlists(
                            limit=50, offset=len(playlists)
                        )
                        for p in new.items:
                            playlists.append(p)
                    for playlist in playlists:
                        if url_or_playlist_name.lower() in playlist.name.lower():
                            await user_spotify.playback_start_context(playlist.uri, device_id=device_id)
                            if is_slash:
                                await ctx.followup.send(
                                    _("Now playing {playlist}").format(playlist=playlist.name),
                                    ephemeral=True,
                                )
                            else:
                                await ctx.react_quietly(
                                    emoji_handler.get_emoji(
                                        "next",
                                        ctx.channel.permissions_for(
                                            ctx.guild.me
                                        ).use_external_emojis,
                                    )
                                )
                            return
                    saved_tracks = await user_spotify.saved_tracks(limit=50)
                    for track in saved_tracks.items:
                        if (
                            url_or_playlist_name.lower() in track.track.name.lower()
                            or url_or_playlist_name.lower()
                            in ", ".join(a.name for a in track.track.artists)
                        ):
                            await user_spotify.playback_start_tracks([track.track.id], device_id=device_id)
                            if is_slash:
                                track_name = track.track.name
                                artists = getattr(track.track, "artists", [])
                                artist = humanize_list([a.name for a in artists])
                                track_artist = humanize_list([a.name for a in artists])
                                em = await song_embed(track.track, False)
                                await ctx.followup.send(
                                    _("Now playing {track} by {artist}").format(
                                        track=track_name, artist=artist
                                    ),
                                    embed=em,
                                    ephemeral=True,
                                )
                            else:
                                await ctx.react_quietly(
                                    emoji_handler.get_emoji(
                                        "next",
                                        ctx.channel.permissions_for(
                                            ctx.guild.me
                                        ).use_external_emojis,
                                    )
                                )
                            return
                else:
                    cur = await user_spotify.saved_tracks(limit=50)
                    await user_spotify.playback_start_tracks([t.track.id for t in cur.items], device_id=device_id)
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "next", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                        )
                    )
                    return
                msg = _("I could not find any URL's or matching playlist names.")
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            log.debug("Error playing song", exc_info=True)
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="queue")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_queue_add(
        self, ctx: Union[commands.Context, discord.Interaction], *songs: SpotifyURIConverter
    ):
        """
        Queue a song to play next in Spotify

        `<songs>` is one or more spotify URL or URI leading to a single track that will
        be added to your current queue
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        tracks = []
        for song in songs:
            if song.group(2) == "track":
                tracks.append(f"spotify:{song.group(2)}:{song.group(3)}")
        if not tracks:
            msg = _("I can only add tracks to your spotify queue.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for uri in tracks:
                    await user_spotify.playback_queue_add(uri)
                all_tracks = await user_spotify.tracks(added_tracks)
            if is_slash:
                track = all_tracks[0]
                track_name = track.name
                artists = getattr(track, "artists", [])
                artist = humanize_list([a.name for a in artists])
                em = await song_embed(track, False)
                await ctx.followup.send(
                    _("Queueing {track} by {artist}").format(track=track_name, artist=artist),
                    embed=em,
                    ephemeral=True,
                )
            else:
                await ctx.react_quietly(
                    emoji_handler.get_emoji(
                        "next", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="repeat")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_repeat(
        self, ctx: Union[commands.Context, discord.Interaction], state: Optional[str]
    ):
        """
        Repeats your current song on spotify

        `<state>` must accept one of `off`, `track`, or `context`.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        if state and state.lower() not in ["off", "track", "context"]:
            msg = _("Repeat must accept either `off`, `track`, or `context`.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if state:
                    lookup = {
                        "off": "off",
                        "context": "repeat",
                        "track": "repeatone",
                    }
                    emoji = emoji_handler.get_emoji(
                        lookup[state.lower()],
                        ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                    )
                else:
                    cur = await user_spotify.playback()
                    if not cur:
                        device_id = await self.config.user(author).default_device()
                        devices = await user_spotify.playback_devices()
                        device = None
                        for d in devices:
                            if d.id == device_id:
                                device = d
                        if not device:
                            return await self.no_device(ctx)

                    else:
                        device = cur.device
                        device_id = device.id
                    if cur and cur.repeat_state == "off":
                        state = "context"
                        emoji = emoji_handler.get_emoji(
                            "repeat", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                        )
                    if cur and cur.repeat_state == "context":
                        state = "track"
                        emoji = emoji_handler.get_emoji(
                            "repeatone",
                            ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                        )
                    if cur and cur.repeat_state == "track":
                        state = "off"
                        emoji = emoji_handler.get_emoji(
                            "off", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                        )
                    if state is None:
                        state = "off"
                        emoji = emoji_handler.get_emoji(
                            "off", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                        )
                await user_spotify.playback_repeat(str(state).lower(), device_id=device_id)
            if is_slash:
                await ctx.followup.send(
                    _("Setting Spotify repeat to {state} on {device}.").format(
                        state=state.title(), device=device.name
                    ),
                    ephemeral=True,
                )
            else:
                await ctx.react_quietly(emoji)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="shuffle")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_shuffle(
        self, ctx: Union[commands.Context, discord.Interaction], state: Optional[bool] = None
    ):
        """
        Shuffles your current song list

        `<state>` either true or false. Not providing this will toggle the current setting.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if state is None:
                    cur = await user_spotify.playback()
                    if not cur:
                        device_id = await self.config.user(author).default_device()
                        devices = await user_spotify.playback_devices()
                        device = None
                        for d in devices:
                            if d.id == device_id:
                                device = d
                        if not device:
                            return await self.no_device(ctx)
                        state = False
                    else:
                        device = cur.device
                        device_id = device.id
                        state = not cur.shuffle_state
                await user_spotify.playback_shuffle(state, device_id=device_id)
            if is_slash:
                if state:
                    await ctx.followup.send(_("Shuffling songs on Spotify."), ephemeral=True)
                else:
                    await ctx.followup.send(_("Turning off shuffle on Spotify."), ephemeral=True)
            else:
                await ctx.react_quietly(
                    emoji_handler.get_emoji(
                        "shuffle", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="seek")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_seek(
        self, ctx: Union[commands.Context, discord.Interaction], seconds: Union[int, str]
    ):
        """
        Seek to a specific point in the current song

        `<seconds>` Accepts seconds or a value formatted like
        00:00:00 (`hh:mm:ss`) or 00:00 (`mm:ss`).
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        try:
            int(seconds)
            abs_position = False
        except ValueError:
            abs_position = True
            seconds = time_convert(seconds)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                now = cur.progress_ms
                total = cur.item.duration_ms
                emoji = emoji_handler.get_emoji(
                    "fastforward", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                )
                log.debug(seconds)
                if abs_position:
                    to_seek = seconds * 1000
                else:
                    to_seek = seconds * 1000 + now
                if to_seek < now:
                    emoji = emoji_handler.get_emoji(
                        "rewind", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                if to_seek > total:
                    emoji = emoji_handler.get_emoji(
                        "next", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    )
                await user_spotify.playback_seek(to_seek)
            if is_slash:
                await ctx.followup.send(
                    _("Seeking to {time}.").format(time=seconds), ephemeral=True
                )
            else:
                await ctx.react_quietly(emoji)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="volume", aliases=["vol"])
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_volume(
        self, ctx: Union[commands.Context, discord.Interaction], volume: Union[int, str]
    ):
        """
        Set your spotify volume percentage

        `<volume>` a number between 0 and 100 for volume percentage.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        volume = max(min(100, volume), 0)  # constrains volume to be within 100
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.config.user(author).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        return await self.no_device(ctx)
                else:
                    device = cur.device
                await user_spotify.playback_volume(volume)
                if volume == 0:
                    emoji = emoji_handler.get_emoji(
                        "volume_mute",
                        ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                    )
                elif cur and volume > cur.device.volume_percent:
                    emoji = emoji_handler.get_emoji(
                        "volume_up",
                        ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                    )
                else:
                    emoji = emoji_handler.get_emoji(
                        "volume_down",
                        ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                    )

            if is_slash:
                await ctx.followup.send(
                    _("Setting {device}'s volume to {volume}.").format(volume=volume, device=device.name),
                    ephemeral=True,
                )
            else:
                await ctx.react_quietly(emoji)

        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_device.command(name="transfer")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_device_transfer(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        device_name: Optional[str] = None,
    ):
        """
        Change the currently playing spotify device

        `<device_name>` The name of the device you want to switch to.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            new_device = None
            if device_name:
                for d in devices:
                    if device_name.lower() in d.name.lower() or device_name == d.id:
                        log.debug(f"Transferring playback to {d.name}")
                        new_device = d
            else:
                new_view = SpotifyDeviceView(ctx)
                options = []
                for device in devices[:25]:
                    options.append(discord.SelectOption(label=device.name[:25], value=device.id))
                select_view = SpotifySelectDevice(options, user_token, self._sender)
                new_view.add_item(select_view)
                msg = _("Pick the device you want to transfer playback to")
                if is_slash:
                    await ctx.followup.send(msg, view=new_view)
                else:
                    await ctx.send(msg, view=new_view)
                # new_device = await self.spotify_pick_device(ctx, devices)
                return
            if not new_device:
                msg = _("I will not transfer spotify playback for you.")
                if is_slash:
                    await ctx.followup.send(msg, ephemeral=True)
                else:
                    await ctx.send(msg)
                return
            with user_spotify.token_as(user_token):
                await user_spotify.playback_transfer(new_device.id, is_playing)
            if is_slash:
                await ctx.followup.send(
                    _("Transferring playback to {device}").format(device=new_device.name),
                    ephemeral=True,
                )
            else:
                await ctx.tick()
        except tekore.Unauthorised:
            log.debug("Error transferring playback", exc_info=True)
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_device.command(name="default")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_device_default(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        device_name: Optional[str] = None,
    ):
        """
        Set your default device to attempt to start playing new tracks on
        if you aren't currently listening to Spotify.

        `<device_name>` The name of the device you want to switch to.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            new_device = None
            if device_name:
                for d in devices:
                    if device_name.lower() in d.name.lower() or device_name == d.id:
                        log.debug(f"Transferring playback to {d.name}")
                        new_device = d
            else:
                new_view = SpotifyDeviceView(ctx)
                options = []
                for device in devices[:25]:
                    options.append(discord.SelectOption(label=device.name[:25], value=device.id))
                options.insert(0, discord.SelectOption(label="None", value="None"))
                select_view = SpotifySelectDevice(options, user_token, self._sender, send_callback=False)
                new_view.add_item(select_view)
                msg = _("Pick the device you want to set as your default player")
                if is_slash:
                    await ctx.followup.send(msg, view=new_view)
                else:
                    await ctx.send(msg, view=new_view)
                await new_view.wait()
                device_id = new_view.device_id if new_view.device_id != "None" else None

                if device_id:
                    for d in devices:
                        if device.id == new_view.device_id:
                            device_name = d.name
                    await self.config.user(author).default_device.set(device_id)
                else:
                    await self.config.user(author).default_device.clear()
                    device_name = "None"
                msg = _("Saving default device as {device}.").format(device=device_name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)
                # new_device = await self.spotify_pick_device(ctx, devices)
                return
            if not new_device:
                msg = _("I will not save your default device for you.")
                if is_slash:
                    await ctx.followup.send(msg, ephemeral=True)
                else:
                    await ctx.send(msg)
                await self.config.user(author).default_device.clear()
                return
            await self.config.user(author).default_device.set(new_device.id)
            if is_slash:
                await ctx.followup.send(
                    _("Saving default device as {device}.").format(device=new_device.name),
                    ephemeral=True,
                )
            else:
                await ctx.tick()
        except tekore.Unauthorised:
            log.debug("Error transferring playback", exc_info=True)
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_device.command(name="list")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_device_list(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List all available devices for Spotify
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
            author = ctx.user
        else:
            author = ctx.author

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            devices_msg = _("{author}'s Spotify Devices:\n").format(author=author.display_name)
            for c, d in enumerate(devices):
                devices_msg += f"{c+1}. `{d.name}` - {d.type} - {d.volume_percent}% "
                if d.is_active:
                    devices_msg += str(emoji_handler.get_emoji(
                        "playpause", ctx.channel.permissions_for(ctx.guild.me).use_external_emojis
                    ))
                devices_msg += "\n"
            if is_slash:
                if ctx.channel.permissions_for(ctx.guild.me).embed_links:
                    await ctx.followup.send(
                        embed=discord.Embed(description=devices_msg), ephemeral=True
                    )
                else:
                    await ctx.followup.send(devices_msg, ephemeral=True)
            else:
                await ctx.maybe_send_embed(devices_msg)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_playlist.command(name="featured")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_playlist_featured(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your Spotify featured Playlists
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
        else:
            await ctx.trigger_typing()

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                playlists = await user_spotify.featured_playlists(limit=50)
        except tekore.Unauthorised:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        playlist_list = playlists[1].items
        x = SpotifySearchMenu(
            source=SpotifyNewPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_playlist.command(name="list", aliases=["ls"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_playlist_list(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your Spotify Playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            is_slash = True
            author = ctx.user
        else:
            await ctx.trigger_typing()
            author = ctx.author
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
        except tekore.Unauthorised:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        show_private = await self.config.user(author).show_private() or isinstance(
            ctx.channel, discord.DMChannel
        )
        if show_private:
            playlist_list = playlists
        else:
            playlist_list = [p for p in playlists if p.public is not False]
        if len(playlist_list) == 0:
            msg = _("You don't have any saved playlists I can show here.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        x = SpotifyBaseMenu(
            source=SpotifyPlaylistsPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_playlist.command(name="view")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_playlist_view(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View details about your spotify playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            is_slash = True
            author = ctx.user
        else:
            await ctx.trigger_typing()
            author = ctx.author

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
        except tekore.Unauthorised:
            return await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        show_private = await self.config.user(author).show_private() or isinstance(
            ctx.channel, discord.DMChannel
        )
        show_private = await self.config.user(author).show_private() or isinstance(
            ctx.channel, discord.DMChannel
        )
        if show_private:
            playlist_list = playlists
        else:
            playlist_list = [p for p in playlists if p.public is not False]
        if len(playlist_list) == 0:
            msg = _("You don't have any saved playlists I can show here.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        x = SpotifySearchMenu(
            source=SpotifyPlaylistPages(playlist_list, False),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)

    @spotify_playlist.command(name="create")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_create(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        public: Optional[bool] = False,
        *,
        description: Optional[str] = "",
    ):
        """
        Create a Spotify Playlist

        `<name>` The name of the newly created playlist
        `[public]` Wheter or not the playlist should be public, defaults to False.
        `[description]` The description of the playlist you're making.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                user = await user_spotify.current_user()
                await user_spotify.playlist_create(user.id, name, public, description)
            if is_slash:
                msg = _("Created {public} playlist named: {name}").format(
                    public=_("Public") if public else _("Private"), name=name
                )
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.tick()
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_playlist.command(name="add")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_add(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        to_add: SpotifyURIConverter,
    ):
        """
        Add 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to add songs to
        `<to_remove>` The song links or URI's you want to add
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        tracks = []
        new_uri = ""
        for match in to_add:
            new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
            if match.group(2) == "track":
                tracks.append(new_uri)
        if not tracks:
            msg = _("You did not provide any tracks for me to add to the playlist.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
                for playlist in playlists:
                    if name.lower() == playlist.name.lower():
                        await user_spotify.playlist_add(playlist.id, tracks)
                        await ctx.tick()
                        return
            msg = _("I could not find a playlist matching {name}.").format(name=name)
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_playlist.command(name="remove")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_remove(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        to_remove: SpotifyURIConverter,
    ):
        """
        Remove 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to remove songs from
        `<to_remove>` The song links or URI's you want to have removed
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        tracks = []
        new_uri = ""
        for match in to_remove:
            new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
            if match.group(2) == "track":
                tracks.append(new_uri)
        if not tracks:
            msg = _("You did not provide any tracks for me to add to the playlist.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
                for playlist in playlists:
                    if name.lower() == playlist.name.lower():
                        await user_spotify.playlist_remove(playlist.id, tracks)
                        await ctx.tick()
                        return
            msg = _("I could not find a playlist matching {name}.").format(name=name)
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_playlist.command(name="follow")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_follow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        to_follow: SpotifyURIConverter,
        public: Optional[bool] = False,
    ):
        """
        Add a playlist to your spotify library

        `[public]` Whether or not the followed playlist should be public after
        `<to_follow>` The song links or URI's you want to have removed
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True

        tracks = []
        for match in to_follow:
            if match.group(2) == "playlist":
                tracks.append(match.group(3))
        if not tracks:
            msg = _("You did not provide any playlists for me to add to your library.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for playlist in tracks:
                    await user_spotify.playlist_follow(playlist, public)
                await ctx.tick()
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_artist.command(name="follow")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_artist_follow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        to_follow: SpotifyURIConverter,
    ):
        """
        Add an artist to your spotify library

        `<to_follow>` The song links or URI's you want to have removed
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            is_slash = True

        tracks = []
        for match in to_follow:
            if match.group(2) == "artist":
                tracks.append(match.group(3))
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for playlist in tracks:
                    await user_spotify.artist_follow(playlist)
                    msg = _("Now following {artist}").format(artist=playlist)
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_artist.command(name="albums", aliases=["album"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def spotify_artist_albums(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        to_follow: SpotifyURIConverter,
    ):
        """
        View an artists albums

        `<to_follow>` The artis links or URI's you want to view the albums of
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(ephemeral=True)
            is_slash = True
        else:
            await ctx.trigger_typing()
        tracks = []
        for match in to_follow:
            if match.group(2) == "artist":
                tracks.append(match.group(3))
        if not tracks:
            msg = _("You did not provide an artist link or URI.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send()
            return
        try:
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.artist_albums(tracks[0], limit=50)
                tracks = search.items
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=SpotifyAlbumPages(tracks, False),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(ctx, ctx.channel)
