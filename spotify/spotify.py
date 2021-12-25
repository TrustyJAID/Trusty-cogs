import asyncio
import logging
import re
import time
from typing import Literal, Mapping, Optional, Tuple, Union

import discord
import tekore
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .command_structure import SLASH_COMMANDS
from .helpers import SPOTIFY_RE, InvalidEmoji
from .spotify_commands import SpotifyCommands

try:
    from .rpc import DashboardRPC_Spotify

    DASHBOARD = True
except ImportError:
    DASHBOARD = False

log = logging.getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


@cog_i18n(_)
class Spotify(SpotifyCommands, commands.Cog):
    """
    Display information from Spotify's API
    """

    __author__ = ["TrustyJAID", "NeuroAssassin"]
    __version__ = "1.7.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.config.register_user(token={}, listen_for={}, show_private=False)
        self.config.register_guild(
            clear_reactions_after=True, delete_message_after=False, menu_timeout=120, commands={}
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
            commands={},
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
        self.slash_commands = {"guilds": {}}
        self.SLASH_COMMANDS = SLASH_COMMANDS

    async def pre_check_slash(self, interaction):
        if not await self.bot.allowed_by_whitelist_blacklist(interaction.user):
            await interaction.response.send_message(
                _("You are not allowed to run this command here."), ephemeral=True
            )
            return False
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        if not await self.bot.ignored_channel_or_guild(fake_ctx):
            await interaction.response.send_message(
                _("Commands are not allowed in this channel or guild."), ephemeral=True
            )
            return False
        return True

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # log.debug(f"Interaction received {interaction.data['name']}")
        interaction_id = int(interaction.data.get("id", 0))
        if interaction.guild.id in self.slash_commands["guilds"]:
            if interaction_id in self.slash_commands["guilds"][interaction.guild.id]:
                if await self.pre_check_slash(interaction):
                    await self.slash_commands["guilds"][interaction.guild.id][interaction_id](
                        interaction
                    )
        if interaction_id in self.slash_commands:
            if await self.pre_check_slash(interaction):
                await self.slash_commands[interaction_id](interaction)

    async def play_from_message(self, interaction: discord.Interaction):
        log.debug(interaction.message)
        message_data = list(interaction.data["resolved"]["messages"].values())[0]
        message = discord.Message(
            state=interaction._state, channel=interaction.channel, data=message_data
        )
        log.debug(message)
        user = interaction.user
        ctx = await self.bot.get_context(message)
        user_token = await self.get_user_auth(ctx, user)
        if not user_token:
            return

        content = message.content + " "
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
        content = content.replace("🧑‍🎨", ":artist:")
        # because discord will replace this in URI's automatically 🙄
        song_data = SPOTIFY_RE.finditer(content)
        tracks = []
        albums = []
        playlists = []
        uri_type = ""
        if song_data:
            new_uri = ""
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                uri_type = match.group(2)
                if match.group(2) == "track":
                    tracks.append(match.group(3))
                if match.group(2) == "album":
                    albums.append(match.group(3))
                if match.group(2) == "playlist":
                    playlists.append(match.group(3))

        user_spotify = tekore.Spotify(sender=self._sender)
        # play the song if it exists
        try:
            with user_spotify.token_as(user_token):
                if tracks:

                    await user_spotify.playback_start_tracks(tracks)
                    all_tracks = await user_spotify.tracks(tracks)
                    track = all_tracks[0]
                    track_name = track.name
                    artists = getattr(track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    track_artist = humanize_list([a.name for a in artists])
                    await interaction.response.send_message(
                        _("Now playing {track} by {artist}").format(
                            track=track_name, artist=artist
                        ),
                        ephemeral=True,
                    )
                    return
                elif new_uri:
                    log.debug("new uri is %s", new_uri)
                    await user_spotify.playback_start_context(new_uri)
                    if uri_type == "playlist":
                        cur_tracks = await user_spotify.playlist(new_uri)
                        track_name = cur_tracks.name
                        await interaction.response.send_message(
                            _("Now playing {track}").format(track=track_name),
                            ephemeral=True,
                        )
                    if uri_type == "artist":
                        artist_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.artist(artist_id)
                        track_name = cur_tracks.name
                        await interaction.response.send_message(
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
                        await interaction.response.send_message(
                            _("Now playing {track} by {artist}.").format(
                                track=track_name, artist=track_artist
                            ),
                            ephemeral=True,
                        )
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
                    search = await user_spotify.search(query, ("track",), "from_token", limit=50)
                    # log.debug(search)
                    tracks = search[0].items
                    if tracks:
                        track_name = tracks[0].name
                        track_artist = humanize_list(tracks[0].artists)
                        await user_spotify.playback_start_tracks([t.id for t in tracks])
                        await interaction.response.send_message(
                            _("Now playing {track} by {artist}").format(
                                track=track_name, artist=track_artist
                            ),
                            ephemeral=True,
                        )
        except Exception:
            log.exception("Error on reaction add play")
            pass

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
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if data["commands"]:
                self.slash_commands["guilds"][guild_id] = {}
                for command, command_id in data["commands"].items():
                    if command == "play on spotify":
                        self.slash_commands["guilds"][guild_id][
                            command_id
                        ] = self.play_from_message
                    if command == "spotify":
                        self.slash_commands["guilds"][guild_id][command_id] = self.spotify_com
        commands = await self.config.commands()
        for command_name, command_id in commands.items():
            self.slash_commands[command_id] = self.spotify_com
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

    async def get_user_auth(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        user: Optional[discord.User] = None,
    ):
        """
        Handles getting and saving user authorization information
        """
        author = user
        is_slash = False
        if author is None:
            if isinstance(ctx, commands.Context):
                author = ctx.author
            else:
                is_slash = True
                author = ctx.user

        if not self._credentials:
            msg = _(
                "The bot owner needs to set their Spotify credentials "
                "before this command can be used. "
                "See `{prefix}spotify set creds` for more details."
            ).format(prefix=ctx.clean_prefix)
            if not is_slash:
                await ctx.send(msg)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        user_tokens = await self.config.user(author).token()
        if user_tokens:
            user_tokens["expires_in"] = user_tokens["expires_at"] - int(time.time())
            user_token = tekore.Token(user_tokens, user_tokens["uses_pkce"])
            if user_token.is_expiring:
                try:
                    user_token = await self._credentials.refresh(user_token)
                except tekore.BadRequest:
                    msg = _("Your refresh token has been revoked, clearing data.")
                    if not is_slash:
                        await ctx.send(msg)
                    else:
                        await ctx.response.send_message(msg, ephemeral=True)
                    await self.config.user(author).token.clear()
                    return
                await self.save_token(author, user_token)
            return user_token
        if author.id in self.temp_cache:
            msg = _(
                "I've already sent you a link for authorization, "
                "please complete that first before trying a new command."
            )
            if not is_slash:
                await ctx.send(msg)
            else:
                await ctx.response.send_message(msg)
            return
        try:
            return await self.ask_for_auth(ctx, author)
        except discord.errors.Forbidden:
            msg = _(
                "You have blocked direct messages, please enable them to authorize spotify commands."
            )
            if not is_slash:
                await ctx.send(msg)
            else:
                await ctx.response.send_message(msg, ephemeral=True)

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
                await author.send(_("Detected authentication via dashboard for."))
                return await self.get_user_auth(ctx, author)
            try:
                del self.temp_cache[author.id]
            except KeyError:
                pass
            await author.send(_("Alright I won't interact with spotify for you."))
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
        try:
            user_token = await auth.request_token(url=redirected)
        except AssertionError:
            await author.send(
                _(
                    "You must follow the *latest* link I sent you for authorization. "
                    "Older links are no longer valid."
                )
            )
            return
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
        if str(payload.emoji) not in listen_for:
            log.debug(f"{payload.emoji} not in listen_for")
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        channel = guild.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return
        user = guild.get_member(payload.user_id)
        if not user:
            return
        ctx = await self.bot.get_context(message)
        user_token = await self.get_user_auth(ctx, user)
        if not user_token:
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
        content = content.replace("🧑‍🎨", ":artist:")
        # because discord will replace this in URI's automatically 🙄
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
        if str(payload.emoji) not in listen_for:
            return
        user_token = await self.get_user_auth(ctx, user)
        if not user_token:
            return
          
        user_spotify = tekore.Spotify(sender=self._sender)
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
