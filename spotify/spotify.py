import asyncio
import logging
import re
import time
from copy import copy
from typing import Literal, Mapping, Optional, Tuple, Union

import discord
import tekore
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .helpers import (
    SPOTIFY_RE,
    InvalidEmoji,
    NotPlaying,
    RecommendationsConverter,
    ScopeConverter,
    SearchTypes,
    SpotifyURIConverter,
    time_convert,
)
from .menus import (
    SpotifyAlbumPages,
    SpotifyArtistPages,
    SpotifyBaseMenu,
    SpotifyEpisodePages,
    SpotifyNewPages,
    SpotifyPages,
    SpotifyPlaylistPages,
    SpotifyPlaylistsPages,
    SpotifyRecentSongPages,
    SpotifySearchMenu,
    SpotifyShowPages,
    SpotifyTopArtistsPages,
    SpotifyTopTracksPages,
    SpotifyTrackPages,
    SpotifyUserMenu,
    emoji_handler,
)

try:
    from .rpc import DashboardRPC_Spotify

    DASHBOARD = True
except ImportError:
    DASHBOARD = False

log = logging.getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)

ActionConverter = commands.get_dict_converter(*emoji_handler.emojis.keys(), delims=[" ", ",", ";"])


@cog_i18n(_)
class Spotify(commands.Cog):
    """
    Display information from Spotify's API
    """

    __author__ = ["TrustyJAID", "NeuroAssassin"]
    __version__ = "1.5.2"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.config.register_user(token={}, listen_for={}, show_private=False)
        self.config.register_guild(
            clear_reactions_after=True, delete_message_after=False, menu_timeout=120
        )
        self.config.register_global(
            emojis={},
            scopes=[
                "user-read-private",
                "user-top-read",
                "user-read-recently-played",
                "user-follow-read",
                "user-library-read",
                "user-read-currently-playing",
                "user-read-playback-state",
                "user-read-playback-position",
                "playlist-read-collaborative",
                "playlist-read-private",
                "user-follow-modify",
                "user-library-modify",
                "user-modify-playback-state",
                "playlist-modify-public",
                "playlist-modify-private",
                "ugc-image-upload",
            ],
            version="0.0.0",
        )

        self._app_token = None
        self._tokens: Tuple[str] = None
        self._spotify_client = None
        self._sender = None
        self._credentials = None
        self._ready = asyncio.Event()
        self.bot.loop.create_task(self.initialize())
        self.HAS_TOKENS = False
        self.current_menus = {}
        self.user_menus = {}
        self.GENRES = []

        # RPC
        self.dashboard_authed = []
        self.temp_cache = {}
        if DASHBOARD:
            self.rpc_extension = DashboardRPC_Spotify(self)

    async def migrate_settings(self):
        if await self.config.version() < "1.4.9":
            all_users = await self.config.all_users()
            for user_id, data in all_users.items():
                if not data["listen_for"]:
                    continue
                if isinstance(data["listen_for"], list):
                    new_data = {}
                else:
                    new_data = {v: k for k, v in data["listen_for"].items()}
                await self.config.user_from_id(user_id).listen_for.set(new_data)
            await self.config.version.set(self.__version__)

    async def initialize(self):
        await self.migrate_settings()

        tokens = await self.bot.get_shared_api_tokens("spotify")
        if not tokens:
            self._ready.set()
            return
        try:
            self._sender = tekore.AsyncSender()
            self._tokens = (
                tokens.get("client_id"),
                tokens.get("client_secret"),
                tokens.get("redirect_uri", "https://localhost/"),
            )
            self._credentials = tekore.Credentials(*self._tokens, sender=self._sender)
            self._app_token = tekore.request_client_token(*self._tokens[:2])
            self._spotify_client = tekore.Spotify(self._app_token, sender=self._sender)
            self.GENRES = await self._spotify_client.recommendation_genre_seeds()
        except Exception:
            log.exception("error starting the cog")
        emojis = await self.config.emojis()
        for name, emoji in emojis.items():
            try:
                emoji_handler.replace_emoji(name, emoji)
            except InvalidEmoji:
                pass
        self._ready.set()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_before_invoke(self, ctx: commands.Context) -> None:
        await self._ready.wait()

    def cog_unload(self):
        if DASHBOARD:
            self.rpc_extension.unload()
        if self._sender:
            self.bot.loop.create_task(self._sender.client.aclose())

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        await self.config.user_from_id(user_id).clear()

    async def get_user_auth(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """
        Handles getting and saving user authorization information
        """
        author = user or ctx.author
        if not self._credentials:
            await ctx.send(
                _(
                    "The bot owner needs to set their Spotify credentials "
                    "before this command can be used. "
                    "See `{prefix}spotify set creds` for more details."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        user_tokens = await self.config.user(author).token()
        if user_tokens:
            user_tokens["expires_in"] = user_tokens["expires_at"] - int(time.time())
            user_token = tekore.Token(user_tokens, user_tokens["uses_pkce"])
            if user_token.is_expiring:
                try:
                    user_token = await self._credentials.refresh(user_token)
                except tekore.BadRequest:
                    await ctx.send("Your refresh token has been revoked, clearing data.")
                    await self.config.user(author).token.clear()
                    return
                await self.save_token(author, user_token)
            return user_token
        if author.id in self.temp_cache:
            await ctx.send(
                _(
                    "I've already sent you a link for authorization, "
                    "please complete that first before trying a new command."
                )
            )
            return
        try:
            return await self.ask_for_auth(ctx, author)
        except discord.errors.Forbidden:
            await ctx.send(
                _(
                    "You have blocked direct messages, please enable them to authorize spotify commands."
                )
            )

    async def ask_for_auth(self, ctx: commands.Context, author: discord.User):
        scope_list = await self.config.scopes()
        scope = tekore.Scope(*scope_list)
        auth = tekore.UserAuth(self._credentials, scope=scope)
        self.temp_cache[author.id] = auth

        msg = _(
            "Please accept the authorization in the following link and reply "
            "to me with the full url\n\n {auth}"
        ).format(auth=auth.url)

        def check(message):
            return (author.id in self.dashboard_authed) or (
                message.author.id == author.id and self._tokens[-1] in message.content
            )

        await author.send(msg)
        try:
            check_msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            # Let's check if they authenticated throug Dashboard
            if author.id in self.dashboard_authed:
                await author.send(
                    _("Detected authentication via dashboard for {user}.").format(user=author.name)
                )
                return await self.get_user_auth(ctx, author)
            try:
                del self.temp_cache[author.id]
            except KeyError:
                pass
            await author.send(
                _("Alright I won't interact with spotify for you {author}.").format(
                    author=author.mention
                )
            )
            return

        if author.id in self.dashboard_authed:
            await author.send(
                _("Detected authentication via dashboard for {user}.").format(user=author.name)
            )
            return await self.get_user_auth(ctx, author)

        redirected = check_msg.clean_content.strip()
        if self._tokens[-1] not in redirected:
            del self.temp_cache[author.id]
            return await ctx.send(_("Credentials not valid"))
        reply_msg = _("Your authorization has been set!")
        await author.send(reply_msg)

        user_token = await auth.request_token(url=redirected)
        await self.save_token(author, user_token)

        del self.temp_cache[author.id]
        return user_token

    async def save_token(self, author: discord.User, user_token: tekore.Token):
        async with self.config.user(author).token() as token:
            token["access_token"] = user_token.access_token
            token["refresh_token"] = user_token.refresh_token
            token["expires_at"] = user_token.expires_at
            token["scope"] = str(user_token.scope)
            token["uses_pkce"] = user_token.uses_pkce
            token["token_type"] = user_token.token_type

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Handles listening for reactions and parsing
        """
        if payload.message_id in self.current_menus:
            if self.current_menus[payload.message_id] == payload.user_id:
                log.debug("Menu reaction from the same user ignoring")
                return
        listen_for = await self.config.user_from_id(payload.user_id).listen_for()
        if not listen_for:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        content = message.content
        if message.embeds:
            em_dict = message.embeds[0].to_dict()
            content += " ".join(v for k, v in em_dict.items() if k in ["title", "description"])
            if "title" in em_dict:
                if "url" in em_dict["title"]:
                    content += " " + em_dict["title"]["url"]
            if "fields" in em_dict:
                for field in em_dict["fields"]:
                    content += " " + field["name"] + " " + field["value"]
            log.debug(content)
        song_data = SPOTIFY_RE.finditer(content)
        tracks = []
        albums = []
        playlists = []
        if song_data:
            new_uri = ""
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                if match.group(2) == "track":
                    tracks.append(match.group(3))
                if match.group(2) == "album":
                    albums.append(match.group(3))
                if match.group(2) == "playlist":
                    playlists.append(match.group(3))
        ctx = await self.bot.get_context(message)
        user = self.bot.get_user(payload.user_id)
        if not user:
            return
        user_token = await self.get_user_auth(ctx, user)
        if not user_token:
            return
        user_spotify = tekore.Spotify(sender=self._sender)
        if str(payload.emoji) not in listen_for:
            return
        action = listen_for[str(payload.emoji)]
        if action == "play" or action == "playpause":
            # play the song if it exists
            try:
                with user_spotify.token_as(user_token):
                    if tracks:
                        await user_spotify.playback_start_tracks(tracks)
                        await ctx.react_quietly(payload.emoji)
                        return
                    elif new_uri:
                        await user_spotify.playback_start_context(new_uri)
                        await ctx.react_quietly(payload.emoji)
                        return
                    elif message.embeds:
                        em = message.embeds[0]
                        query = None
                        if em.description:
                            look = f"{em.title if em.title else ''}-{em.description}"
                            find = re.search(r"\[(.+)\]", look)
                            if find:
                                query = find.group(1)
                        else:
                            query = em.title if em.title else ""
                        if not query or query == "-":
                            return
                        search = await user_spotify.search(
                            query, ("track",), "from_token", limit=50
                        )
                        # log.debug(search)
                        tracks = search[0].items
                        if tracks:
                            await user_spotify.playback_start_tracks([t.id for t in tracks])
                            await ctx.react_quietly(payload.emoji)
            except Exception:
                log.exception("Error on reaction add play")
                pass
        if action == "queue":
            # append a track to the queue
            try:
                with user_spotify.token_as(user_token):
                    if tracks:
                        for track in tracks:
                            await user_spotify.playback_queue_add(f"spotify:track:{track}")
                        await ctx.react_quietly(payload.emoji)
                        return
                    elif message.embeds:
                        em = message.embeds[0]
                        query = None
                        if em.description:
                            look = f"{em.title if em.title else ''}-{em.description}"
                            find = re.search(r"\[(.+)\]", look)
                            if find:
                                query = find.group(1)
                        else:
                            query = em.title if em.title else ""
                        if not query or query == "-":
                            return
                        search = await user_spotify.search(
                            query, ("track",), "from_token", limit=50
                        )
                        # log.debug(search)
                        tracks = search[0].items
                        if tracks:
                            await user_spotify.playback_start_tracks([t.id for t in tracks])
                            await ctx.react_quietly(payload.emoji)
            except Exception:
                log.exception("Error on reaction add play")
                pass
        if action == "like":
            try:
                with user_spotify.token_as(user_token):
                    if tracks:
                        await user_spotify.saved_tracks_add(tracks)
                    if albums:
                        await user_spotify.saved_albums_add(albums)
                    if playlists:
                        for playlist in playlists:
                            await user_spotify.playlists_add(playlist)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "pause":
            try:
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    if cur.is_playing:
                        await user_spotify.playback_pause()
                    await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "repeat":
            try:
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    if cur.repeat_state == "off":
                        state = "context"
                    if cur.repeat_state == "context":
                        state = "off"
                    await user_spotify.playback_repeat(state)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "repeatone":
            try:
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    if cur.repeat_state == "off":
                        state = "track"
                    if cur.repeat_state == "track":
                        state = "off"
                    await user_spotify.playback_repeat(state)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "shuffle":
            try:
                with user_spotify.token_as(self.user_token):
                    cur = await user_spotify.playback()
                    if not cur:
                        return
                    await user_spotify.playback_shuffle(not cur.shuffle_state)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "next":
            try:
                with user_spotify.token_as(user_token):
                    await user_spotify.playback_next()
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "previous":
            try:
                with user_spotify.token_as(user_token):
                    await user_spotify.playback_previous()
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "volume_down":
            try:
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    volume = cur.device.volume_percent - 10
                    await user_spotify.playback_volume(volume)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "volume_up":
            try:
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    volume = cur.device.volume_percent + 10
                    await user_spotify.playback_volume(volume)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass
        if action == "volume_mute":
            try:
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    await user_spotify.playback_volume(0)
                await ctx.react_quietly(payload.emoji)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name == "spotify":
            await self.initialize()

    @commands.group(name="spotify", aliases=["sp"])
    async def spotify_com(self, ctx: commands.Context):
        """
        Spotify commands
        """
        pass

    @spotify_com.group(name="set")
    async def spotify_set(self, ctx: commands.Context):
        """
        Setup Spotify cog
        """
        pass

    @spotify_com.group(name="playlist", aliases=["playlists"])
    async def spotify_playlist(self, ctx: commands.Context):
        """
        View Spotify Playlists
        """
        pass

    @spotify_com.group(name="artist", aliases=["artists"])
    async def spotify_artist(self, ctx: commands.Context):
        """
        View Spotify Artist info
        """
        pass

    @spotify_set.command(name="listen")
    async def set_reaction_listen(self, ctx: commands.Context, *, listen_for: ActionConverter):
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
            for action, emoji in listen_for.items():
                if action not in emoji_handler.emojis.keys():
                    continue
                custom_emoji = None
                try:
                    custom_emoji = await commands.PartialEmojiConverter().convert(ctx, emoji)
                except commands.BadArgument:
                    pass
                if custom_emoji:
                    current[str(custom_emoji)] = action
                    added[str(custom_emoji)] = action
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
    async def set_reaction_remove_listen(self, ctx: commands.Context, *emoji_or_name: str):
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
    async def show_settings(self, ctx: commands.Context):
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
    async def show_private(self, ctx: commands.Context, show_private: bool):
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
    async def guild_clear_reactions(self, ctx: commands.Context, clear_after: bool):
        """
        Set whether or not to clear reactions after sending the message

        Note: the bot requires manage messages for this to work
        """
        await self.config.guild(ctx.guild).clear_reactions_after.set(clear_after)
        if clear_after:
            msg = _("I will now clear reactions after the menu has timed out.\n")
        else:
            msg = _("I will stop clearing reactions after the menu has timed out.\n")
        if not ctx.channel.permissions_for(ctx.me).manage_messages:
            msg += _(
                "I don't have manage messages permissions so this might not work as expected."
            )
        await ctx.send(msg)

    @spotify_set.command(name="deletemessage")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_delete_message_after(self, ctx: commands.Context, delete_after: bool):
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
    async def guild_menu_timeout(self, ctx: commands.Context, timeout: int):
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
    async def spotify_reset_emoji(self, ctx: commands.Context):
        """
        Resets the bot to use the default emojis
        """
        await self.config.emojis.clear()
        emoji_handler.reload_emojis()
        await ctx.send(_("I will now use the default emojis."))

    @spotify_set.command(name="emojis")
    @commands.is_owner()
    async def spotify_emojis(self, ctx: commands.Context, *, new_emojis: ActionConverter):
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
            for name, emoji in new_emojis.items():
                try:
                    await ctx.message.add_reaction(str(emoji))
                    emoji_handler.replace_emoji(name, str(emoji))
                    emojis[name] = str(emoji)
                    emojis_changed[name] = str(emoji)
                except (InvalidEmoji, discord.errors.HTTPException):
                    pass
        if not emojis_changed:
            return await ctx.send(_("No emojis have been changed."))
        msg = _("The following emojis have been replaced:\n")
        for name, emoji in emojis_changed.items():
            original = emoji_handler.default[name]
            msg += f"{original} -> {emoji}\n"
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="scope", aliases=["scopes"])
    @commands.is_owner()
    async def spotify_api_scope(self, ctx: commands.Context, *scopes: ScopeConverter):
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
    async def spotify_view_api_scope(self, ctx: commands.Context):
        """
        View the current scopes being requested
        """
        scope = humanize_list(await self.config.scopes())
        await ctx.maybe_send_embed(_("Current scopes:\n{scopes}").format(scopes=scope))

    @spotify_set.command(name="creds")
    @commands.is_owner()
    async def spotify_api_credential_set(self, ctx: commands.Context):
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
    async def spotify_forgetme(self, ctx: commands.Context):
        """
        Forget all your spotify settings and credentials on the bot
        """
        await self.config.user(ctx.author).clear()
        if ctx.author.id in self.dashboard_authed:
            self.dashboard_authed.remove(ctx.author.id)
        await ctx.send(_("All your spotify data deleted from my settings."))

    @spotify_com.command(name="me")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_me(self, ctx: commands.Context):
        """
        Shows your current Spotify Settings
        """
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=ctx.author.display_name + _(" Spotify Profile"), icon_url=ctx.author.avatar_url
        )
        msg = ""
        cog_settings = await self.config.user(ctx.author).all()
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
        if show_private or isinstance(ctx.channel, discord.DMChannel):
            msg += _(
                "Spotify Name: [{display_name}](https://open.spotify.com/user/{user_id})\n"
                "Subscription: {product}\n"
            ).format(display_name=cur.display_name, product=cur.product, user_id=cur.id)
        if isinstance(ctx.channel, discord.DMChannel):
            private = _("Country: {country}\nSpotify ID: {id}\nEmail: {email}\n").format(
                country=cur.country, id=cur.id, email=cur.email
            )
            em.add_field(name=_("Private Data"), value=private)
        if cur.images:
            em.set_thumbnail(url=cur.images[0].url)
        em.description = msg
        await ctx.send(embed=em)

    @spotify_com.command(name="now", aliases=["np"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_now(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        member: Optional[discord.Member] = None,
    ):
        """
        Displays your currently played spotify song

        `[member]` Optional discord member to show their current spotify status
        if they're displaying it on Discord.
        """
        if ctx.author.id in self.user_menus:
            jump = self.user_menus[ctx.author.id]
            em = discord.Embed(
                description=_(
                    "[You already have a player running here.]({jump})\n"
                    "Please wait for that one to end or cancel it before trying again."
                ).format(jump=jump),
                colour=await self.bot.get_embed_colour(ctx),
            )
            await ctx.send(embed=em, delete_after=10)
            return
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        if member:
            if not [c for c in member.activities if c.type == discord.ActivityType.listening]:
                return await ctx.send(
                    _("That user is not currently listening to Spotify on Discord.")
                )
            else:
                activity = [
                    c for c in member.activities if c.type == discord.ActivityType.listening
                ][0]
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    track = await user_spotify.track(activity.track_id)
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
            await SpotifyUserMenu(
                source=page_source,
                delete_message_after=delete_after,
                clear_reactions_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
                use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
            ).start(ctx=ctx)
        except NotPlaying:
            await ctx.send(_("It appears you're not currently listening to Spotify."))
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))

    @spotify_com.command(name="share")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_share(self, ctx: commands.Context):
        """
        Tell the bot to play the users current song in their current voice channel
        """

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await ctx.send(_("It appears you're not currently listening to Spotify."))
                if cur.is_playing and not cur.item.is_local:
                    msg = copy(ctx.message)
                    msg.content = ctx.prefix + f"play {cur.item.uri}"
                    self.bot.dispatch("message", msg)
                    await ctx.tick()
                else:
                    return await ctx.send(
                        _("You don't appear to be listening to something I can play in audio.")
                    )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="search")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_search(
        self,
        ctx: commands.Context,
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
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            search = await user_spotify.search(query, (search_type,), "from_token", limit=50)
            items = search[0].items
        if not search[0].items:
            return await ctx.send(
                _("No {search_type} could be found matching that query.").format(
                    search_type=search_type
                )
            )
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        await SpotifySearchMenu(
            source=search_types[search_type](items=items, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_com.command(name="genres", aliases=["genre"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_genres(self, ctx: commands.Context):
        """
        Display all available genres for the recommendations
        """
        try:
            self.GENRES = await self._spotify_client.recommendation_genre_seeds()
        except Exception:
            log.exception("Error grabbing genres.")
            return await ctx.send(
                _(
                    "The bot owner needs to set their Spotify credentials "
                    "before this command can be used."
                    " See `{prefix}spotify set creds` for more details."
                ).format(prefix=ctx.clean_prefix)
            )
        await ctx.maybe_send_embed(
            _(
                "The following are available genres for Spotify's recommendations:\n\n {genres}"
            ).format(genres=humanize_list(self.GENRES))
        )

    @spotify_com.command(name="recommendations", aliases=["recommend", "recommendation"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_recommendations(
        self,
        ctx: commands.Context,
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
         - `time_signature` + the measure of bars
         - `valence` + a value from 0-100
        """

        log.debug(recommendations)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            try:
                search = await user_spotify.recommendations(**recommendations)
            except Exception:
                log.exception("Error getting recommendations")
                return await ctx.send(
                    _("I could not find any recommendations with those parameters")
                )
            items = search.tracks
        if not items:
            return await ctx.send(_("No recommendations could be found that query."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        await SpotifySearchMenu(
            source=SpotifyTrackPages(items=items, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_com.command(name="recent")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_recently_played(
        self, ctx: commands.Context, detailed: Optional[bool] = False
    ):
        """
        Displays your most recently played songs on Spotify
        """

        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.playback_recently_played(limit=50)
                tracks = search.items
        except tekore.Unauthorised:
            return await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        await SpotifySearchMenu(
            source=SpotifyRecentSongPages(tracks=tracks, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_com.command(name="toptracks")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def top_tracks(self, ctx: commands.Context):
        """
        List your top tracks on spotify
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user_top_tracks(limit=50)
        except tekore.Unauthorised:
            return await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        tracks = cur.items
        await SpotifyBaseMenu(
            source=SpotifyTopTracksPages(tracks),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_com.command(name="topartists")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def top_artists(self, ctx: commands.Context):
        """
        List your top tracks on spotify
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user_top_artists(limit=50)
        except tekore.Unauthorised:
            return await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        artists = cur.items
        await SpotifyBaseMenu(
            source=SpotifyTopArtistsPages(artists),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_com.command(name="new")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_new(self, ctx: commands.Context):
        """
        List new releases on Spotify
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
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
        await SpotifySearchMenu(
            source=SpotifyNewPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_com.command(name="pause")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_pause(self, ctx: commands.Context):
        """
        Pauses spotify for you
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_pause()
            await ctx.react_quietly(
                emoji_handler.get_emoji(
                    "pause", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
            )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="resume")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_resume(self, ctx: commands.Context):
        """
        Resumes spotify for you
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur or not cur.is_playing:
                    await user_spotify.playback_resume()
                else:
                    return await ctx.send(_("You are already playing music on Spotify."))
            await ctx.react_quietly(
                emoji_handler.get_emoji(
                    "play", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
            )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="next", aliases=["skip"])
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_next(self, ctx: commands.Context):
        """
        Skips to the next track in queue on Spotify
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_next()
            await ctx.react_quietly(
                emoji_handler.get_emoji(
                    "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
            )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="previous", aliases=["prev"])
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_previous(self, ctx: commands.Context):
        """
        Skips to the previous track in queue on Spotify
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_previous()
            await ctx.react_quietly(
                emoji_handler.get_emoji(
                    "previous", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
            )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="play")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_play(
        self, ctx: commands.Context, *, url_or_playlist_name: Optional[str] = ""
    ):
        """
        Play a track, playlist, or album on Spotify

        `<url_or_playlist_name>` can be multiple spotify track URL *or* URI or
        a single album or playlist link

        if something other than a spotify URL or URI is provided
        the bot will search through your playlists and start playing
        the playlist with the closest matching name
        """
        song_data = SPOTIFY_RE.finditer(url_or_playlist_name)
        tracks = []
        new_uri = ""
        if song_data:
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                if match.group(2) == "track":
                    tracks.append(match.group(3))
            log.debug(new_uri)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if tracks:
                    await user_spotify.playback_start_tracks(tracks)
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    )
                    return
                if new_uri:
                    await user_spotify.playback_start_context(new_uri)
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
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
                            await user_spotify.playback_start_context(playlist.uri)
                            await ctx.react_quietly(
                                emoji_handler.get_emoji(
                                    "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
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
                            await user_spotify.playback_start_tracks([track.track.id])
                            await ctx.react_quietly(
                                emoji_handler.get_emoji(
                                    "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
                                )
                            )
                            return
                else:
                    cur = await user_spotify.saved_tracks(limit=50)
                    await user_spotify.playback_start_tracks([t.track.id for t in cur.items])
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    )
                    return
                await ctx.send(_("I could not find any URL's or matching playlist names."))
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="queue")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_queue_add(self, ctx: commands.Context, *songs: SpotifyURIConverter):
        """
        Queue a song to play next in Spotify

        `<songs>` is one or more spotify URL or URI leading to a single track that will
        be added to your current queue
        """
        tracks = []
        for song in songs:
            if song.group(2) == "track":
                tracks.append(f"spotify:{song.group(2)}:{song.group(3)}")
        if not tracks:
            return await ctx.send(_("I can only add tracks to your spotify queue."))
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for uri in tracks:
                    await user_spotify.playback_queue_add(uri)
            await ctx.react_quietly(
                emoji_handler.get_emoji(
                    "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
            )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="repeat")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_repeat(self, ctx: commands.Context, state: Optional[str]):
        """
        Repeats your current song on spotify

        `<state>` must accept one of `off`, `track`, or `context`.
        """
        if state and state.lower() not in ["off", "track", "context"]:
            return await ctx.send(_("Repeat must accept either `off`, `track`, or `context`."))
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
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
                        ctx.channel.permissions_for(ctx.me).use_external_emojis,
                    )
                else:
                    cur = await user_spotify.playback()
                    if not cur:
                        return await ctx.send(
                            _("I could not find an active device to send requests for.")
                        )
                    if cur.repeat_state == "off":
                        state = "context"
                        emoji = emoji_handler.get_emoji(
                            "repeat", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    if cur.repeat_state == "context":
                        state = "track"
                        emoji = emoji_handler.get_emoji(
                            "repeatone", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    if cur.repeat_state == "track":
                        state = "off"
                        emoji = emoji_handler.get_emoji(
                            "off", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                await user_spotify.playback_repeat(str(state).lower())
            await ctx.react_quietly(emoji)
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="shuffle")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_shuffle(self, ctx: commands.Context, state: Optional[bool] = None):
        """
        Shuffles your current song list

        `<state>` either true or false. Not providing this will toggle the current setting.
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if state is None:
                    cur = await user_spotify.playback()
                    if not cur:
                        await ctx.send(
                            _("I could not find an active device to send requests for.")
                        )
                    state = not cur.shuffle_state
                await user_spotify.playback_shuffle(state)
            await ctx.react_quietly(
                emoji_handler.get_emoji(
                    "shuffle", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
            )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="seek")
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_seek(self, ctx: commands.Context, seconds: Union[int, str]):
        """
        Seek to a specific point in the current song

        `<seconds>` Accepts seconds or a value formatted like
        00:00:00 (`hh:mm:ss`) or 00:00 (`mm:ss`).
        """
        try:
            int(seconds)
            abs_position = False
        except ValueError:
            abs_position = True
            seconds = time_convert(seconds)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                now = cur.progress_ms
                total = cur.item.duration_ms
                emoji = emoji_handler.get_emoji(
                    "fastforward", ctx.channel.permissions_for(ctx.me).use_external_emojis
                )
                log.debug(seconds)
                if abs_position:
                    to_seek = seconds * 1000
                else:
                    to_seek = seconds * 1000 + now
                if to_seek < now:
                    emoji = emoji_handler.get_emoji(
                        "rewind", ctx.channel.permissions_for(ctx.me).use_external_emojis
                    )
                if to_seek > total:
                    emoji = emoji_handler.get_emoji(
                        "next", ctx.channel.permissions_for(ctx.me).use_external_emojis
                    )
                await user_spotify.playback_seek(to_seek)
            await ctx.react_quietly(emoji)
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="volume", aliases=["vol"])
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_volume(self, ctx: commands.Context, volume: Union[int, str]):
        """
        Set your spotify volume percentage

        `<volume>` a number between 0 and 100 for volume percentage.
        """
        volume = max(min(100, volume), 0)  # constrains volume to be within 100
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                await user_spotify.playback_volume(volume)
                if volume == 0:
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "volume_mute", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    )
                elif cur and volume > cur.device.volume_percent:
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "volume_up", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    )
                else:
                    await ctx.react_quietly(
                        emoji_handler.get_emoji(
                            "volume_down", ctx.channel.permissions_for(ctx.me).use_external_emojis
                        )
                    )
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_com.command(name="device", hidden=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def spotify_device(self, ctx: commands.Context, *, device_name: str):
        """
        Change the currently playing spotify device

        `<device_name>` The name of the device you want to switch to.
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            for d in devices:
                if device_name.lower() in d.name.lower():
                    log.debug(f"Transferring playback to {d.name}")
                    await user_spotify.playback_transfer(d.id, is_playing)
                    await ctx.tick()
                    break
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_playlist.command(name="featured")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_featured(self, ctx: commands.Context):
        """
        List your Spotify featured Playlists
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                playlists = await user_spotify.featured_playlists(limit=50)
        except tekore.Unauthorised:
            return await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        playlist_list = playlists[1].items
        await SpotifySearchMenu(
            source=SpotifyNewPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_playlist.command(name="list", aliases=["ls"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def playlist_playlist_list(self, ctx: commands.Context):
        """
        List your Spotify Playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
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
            return await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        show_private = await self.config.user(ctx.author).show_private() or isinstance(
            ctx.channel, discord.DMChannel
        )
        if show_private:
            playlist_list = playlists
        else:
            playlist_list = [p for p in playlists if p.public is not False]
        await SpotifyBaseMenu(
            source=SpotifyPlaylistsPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_playlist.command(name="view")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_view(self, ctx: commands.Context):
        """
        View details about your spotify playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
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
            return await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        show_private = await self.config.user(ctx.author).show_private() or isinstance(
            ctx.channel, discord.DMChannel
        )
        show_private = await self.config.user(ctx.author).show_private() or isinstance(
            ctx.channel, discord.DMChannel
        )
        if show_private:
            playlist_list = playlists
        else:
            playlist_list = [p for p in playlists if p.public is not False]
        await SpotifySearchMenu(
            source=SpotifyPlaylistPages(playlist_list, False),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)

    @spotify_playlist.command(name="create")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_create(
        self,
        ctx: commands.Context,
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
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                user = await user_spotify.current_user()
                await user_spotify.playlist_create(user.id, name, public, description)
                await ctx.tick()
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_playlist.command(name="add")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_add(
        self,
        ctx: commands.Context,
        name: str,
        *to_add: SpotifyURIConverter,
    ):
        """
        Add 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to add songs to
        `<to_remove>` The song links or URI's you want to add
        """
        tracks = []
        new_uri = ""
        for match in to_add:
            new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
            if match.group(2) == "track":
                tracks.append(new_uri)
        if not tracks:
            return await ctx.send(
                _("You did not provide any tracks for me to add to the playlist.")
            )
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
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
            await ctx.send(_("I could not find a playlist matching {name}.").format(name=name))
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_playlist.command(name="remove")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_remove(
        self,
        ctx: commands.Context,
        name: str,
        *to_remove: SpotifyURIConverter,
    ):
        """
        Remove 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to remove songs from
        `<to_remove>` The song links or URI's you want to have removed
        """
        tracks = []
        new_uri = ""
        for match in to_remove:
            new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
            if match.group(2) == "track":
                tracks.append(new_uri)
        if not tracks:
            return await ctx.send(
                _("You did not provide any tracks for me to add to the playlist.")
            )
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
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
            await ctx.send(_("I could not find a playlist matching {name}.").format(name=name))
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_playlist.command(name="follow")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_playlist_follow(
        self,
        ctx: commands.Context,
        public: Optional[bool] = False,
        *to_follow: SpotifyURIConverter,
    ):
        """
        Add a playlist to your spotify library

        `[public]` Whether or not the followed playlist should be public after
        `<to_follow>` The song links or URI's you want to have removed
        """
        tracks = []
        for match in to_follow:
            if match.group(2) == "playlist":
                tracks.append(match.group(3))
        if not tracks:
            return await ctx.send(
                _("You did not provide any playlists for me to add to your library.")
            )
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for playlist in tracks:
                    await user_spotify.playlist_follow(playlist, public)
                await ctx.tick()
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_artist.command(name="follow")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_artist_follow(
        self,
        ctx: commands.Context,
        *to_follow: SpotifyURIConverter,
    ):
        """
        Add an artist to your spotify library

        `<to_follow>` The song links or URI's you want to have removed
        """
        tracks = []
        for match in to_follow:
            if match.group(2) == "artist":
                tracks.append(match.group(3))
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await ctx.send(_("You need to authorize me to interact with spotify."))
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for playlist in tracks:
                    await user_spotify.artist_follow(playlist)
                await ctx.tick()
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        except tekore.NotFound:
            await ctx.send(_("I could not find an active device to send requests for."))
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await ctx.send(_("This action is prohibited for non-premium users."))
            else:
                await ctx.send(_("I couldn't perform that action for you."))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await ctx.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    @spotify_artist.command(name="albums", aliases=["album"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def spotify_artist_albums(
        self,
        ctx: commands.Context,
        *to_follow: SpotifyURIConverter,
    ):
        """
        View an artists albums

        `<to_follow>` The artis links or URI's you want to view the albums of
        """
        tracks = []
        for match in to_follow:
            if match.group(2) == "artist":
                tracks.append(match.group(3))
        if not tracks:
            return await ctx.send(_("You did not provide an artist link or URI."))
        try:
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await ctx.send(_("You need to authorize me to interact with spotify."))
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.artist_albums(tracks[0], limit=50)
                tracks = search.items
        except tekore.Unauthorised:
            await ctx.send(_("I am not authorized to perform this action for you."))
        if ctx.guild:
            delete_after = await self.config.guild(ctx.guild).delete_message_after()
            clear_after = await self.config.guild(ctx.guild).clear_reactions_after()
            timeout = await self.config.guild(ctx.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        await SpotifySearchMenu(
            source=SpotifyAlbumPages(tracks, False),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
            use_external=ctx.channel.permissions_for(ctx.me).use_external_emojis,
        ).start(ctx=ctx)
