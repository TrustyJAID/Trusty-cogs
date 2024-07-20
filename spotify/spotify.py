import asyncio
import re
import time
from abc import ABC
from contextlib import asynccontextmanager
from typing import Dict, Literal, Mapping, Optional, Tuple

import discord
import tekore
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .helpers import SPOTIFY_RE, InvalidEmoji, song_embed, spotify_emoji_handler
from .menus import SpotifyPages, SpotifySearchMenu, SpotifyTrackPages, SpotifyUserMenu
from .spotify_commands import SpotifyCommands

try:
    from .rpc import DashboardRPC_Spotify

    DASHBOARD = True
except ImportError:
    DASHBOARD = False

log = getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


@cog_i18n(_)
class Spotify(
    SpotifyCommands,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Display information from Spotify's API
    """

    __author__ = ["TrustyJAID", "NeuroAssassin"]
    __version__ = "1.7.3"

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.config.register_user(token={}, listen_for={}, show_private=False, default_device=None)
        self.config.register_guild(
            clear_reactions_after=True,
            delete_message_after=False,
            menu_timeout=120,
            enable_slash=False,
            enable_context=False,
        )
        self.config.register_global(
            emojis={},
            emojis_author="",
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
            enable_slash=False,
            enable_context=False,
        )

        self._app_token = None
        self._tokens: Tuple[str] = None
        self._spotify_client = None
        self._sender = None
        self._credentials = None
        self._ready = asyncio.Event()
        self.HAS_TOKENS = False
        self.current_menus = {}
        self.user_menus = {}
        self.GENRES = []

        # RPC
        self.dashboard_authed = []
        self.temp_cache = {}
        self.waiting_auth: Dict[int, asyncio.Event] = {}
        if DASHBOARD:
            self.rpc_extension = DashboardRPC_Spotify(self)
        self.slash_commands = {"guilds": {}}
        self._temp_user_devices = {}
        self.play_ctx = discord.app_commands.ContextMenu(
            name="Play on Spotify",
            callback=self.play_from_message,
        )
        self.queue_ctx = discord.app_commands.ContextMenu(
            name="Queue on Spotify",
            callback=self.play_from_message,
        )
        self._commit = ""
        self._repo = ""

    async def cog_load(self):
        if version_info > VersionInfo.from_str("3.5.9"):
            self.play_ctx.allowed_contexts = discord.app_commands.installs.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            )
            self.play_ctx.allowed_installs = discord.app_commands.installs.AppInstallationType(
                guild=True, user=True
            )
            self.queue_ctx.allowed_contexts = discord.app_commands.installs.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            )
            self.queue_ctx.allowed_installs = discord.app_commands.installs.AppInstallationType(
                guild=True, user=True
            )
            self.spotify_com.app_command.allowed_contexts = (
                discord.app_commands.installs.AppCommandContext(
                    guild=True, dm_channel=True, private_channel=True
                )
            )
            self.spotify_com.app_command.allowed_installs = (
                discord.app_commands.installs.AppInstallationType(guild=True, user=True)
            )

        self.bot.tree.add_command(self.play_ctx)
        self.bot.tree.add_command(self.queue_ctx)
        await self.set_tokens()

    async def set_tokens(self):
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
                spotify_emoji_handler.replace_emoji(name, emoji)
            except InvalidEmoji:
                pass
        self._ready.set()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\n- Cog Version: {self.__version__}\n"
        ret += f"- tekore Version: {tekore.__version__}\n"
        if self._repo:
            ret += f"- Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def cog_before_invoke(self, ctx: commands.Context) -> None:
        await self._get_commit()
        await self._ready.wait()

    async def _get_commit(self):
        if self._repo:
            return
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "citation":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    async def cog_unload(self):
        if DASHBOARD:
            self.rpc_extension.unload()
        if self._sender:
            await self._sender.client.aclose()
        self.bot.tree.remove_command(self.play_ctx.name, type=self.play_ctx.type)
        self.bot.tree.remove_command(self.queue_ctx.name, type=self.queue_ctx.type)

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

    @asynccontextmanager
    async def get_user_spotify(
        self, ctx: commands.Context, user: Optional[discord.User] = None
    ) -> Optional[tekore.Spotify]:
        user_token = await self.get_user_auth(ctx, user)
        if not user_token:
            yield None
        client = tekore.Spotify(sender=self._sender)
        cv_token = client._token_cv.set(user_token)
        yield client
        client._token_cv.reset(cv_token)

    @commands.Cog.listener()
    async def on_oauth_receive(self, user_id: int, payload: dict):
        if payload["provider"] != "spotify":
            return
        if "code" not in payload:
            log.error("Received Spotify OAuth without a code parameter %s - %s", user_id, payload)
            return
        if int(user_id) not in self.waiting_auth:
            return
        try:
            code = payload["code"]
            state = payload["state"]
            auth = self.temp_cache[int(user_id)]
            user_token = await auth.request_token(code=code, state=state)
            user = self.bot.get_user(int(user_id))
            if user is None:
                return
            await self.save_token(user, user_token)
            del self.temp_cache[user.id]
            self.dashboard_authed.append(user.id)
            msg = _("Detected authentication via dashboard.")
            await user.send(msg)
        except KeyError:
            log.error("Recieved Spotify Auth request but the user was not in the cache.")
            return
        except Exception:
            log.exception("Error setting user OAuth in Spotify")
        self.waiting_auth[int(user_id)].set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        author = message.author
        if author.id not in self.waiting_auth and author.id not in self.temp_cache:
            return
        if self._tokens[-1] not in message.clean_content:
            return
        redirected = message.clean_content.strip()
        auth = self.temp_cache[author.id]
        try:
            user_token = await auth.request_token(url=redirected)
            del self.temp_cache[author.id]
            msg = _("Detected authentication via message.")
            await author.send(msg)
        except AssertionError:
            msg = _(
                "You must follow the *latest* link I sent you for authorization. "
                "Older links are no longer valid."
            )
            await author.send(msg)
            return
        await self.save_token(author, user_token)
        self.waiting_auth[author.id].set()

    async def get_user_auth(
        self,
        ctx: commands.Context,
        user: Optional[discord.User] = None,
    ) -> Optional[tekore.Token]:
        """
        Handles getting and saving user authorization information
        """
        author = user
        if author is None:
            author = ctx.author

        if not self._credentials:
            msg = _(
                "The bot owner needs to set their Spotify credentials "
                "before this command can be used. "
                "See `{prefix}spotify set creds` for more details."
            ).format(prefix=ctx.clean_prefix)
            await ctx.send(msg, ephemeral=True)
            return None
        user_tokens = await self.config.user(author).token()
        if user_tokens:
            user_tokens["expires_in"] = user_tokens["expires_at"] - int(time.time())
            user_token = tekore.Token(user_tokens, user_tokens["uses_pkce"])
            if user_token.is_expiring:
                try:
                    user_token = await self._credentials.refresh(user_token)
                except tekore.BadRequest:
                    msg = _("Your refresh token has been revoked, clearing data.")
                    await ctx.send(msg, ephemeral=True)
                    await self.config.user(author).token.clear()
                    return None
                await self.save_token(author, user_token)
            return user_token
        if author.id in self.temp_cache:
            msg = _(
                "I've already sent you a link for authorization, "
                "please complete that first before trying a new command."
            )
            await ctx.send(msg)
            return None
        try:
            return await self.ask_for_auth(ctx, author)
        except discord.errors.Forbidden:
            msg = _(
                "You have blocked direct messages, please enable them to authorize spotify commands."
            )
            await ctx.send(msg, ephemeral=True)
        return None

    async def wait_for_auth(self, user_id: int):
        if user_id not in self.waiting_auth:
            raise RuntimeError("Tried to wait for a user's auth but they're not expecting it.")
        await self.waiting_auth[user_id].wait()

    async def ask_for_auth(
        self, ctx: commands.Context, author: discord.User
    ) -> Optional[tekore.Token]:
        scope_list = await self.config.scopes()
        scope = tekore.Scope(*scope_list)
        auth = tekore.UserAuth(self._credentials, scope=scope)
        self.temp_cache[author.id] = auth
        is_slash = False
        if ctx.interaction:
            is_slash = True
        msg = _(
            "Please accept the authorization [here]({auth}) and **DM "
            "me** with the final full url."
        ).format(auth=auth.url)

        if is_slash:
            await ctx.send(msg, ephemeral=True)
        else:
            await author.send(msg)
        self.waiting_auth[author.id] = asyncio.Event()
        try:
            await asyncio.wait_for(self.wait_for_auth(author.id), timeout=180)
        except asyncio.TimeoutError:
            # Let's check if they authenticated throug Dashboard
            try:
                del self.temp_cache[author.id]
                del self.waiting_auth[author.id]
            except KeyError:
                pass
            await author.send(_("Alright I won't interact with spotify for you."))
            return
        return await self.get_user_auth(ctx, author)

    async def save_token(self, author: discord.abc.User, user_token: tekore.Token):
        async with self.config.user(author).token() as token:
            token["access_token"] = user_token.access_token
            token["refresh_token"] = user_token.refresh_token
            token["expires_at"] = user_token.expires_at
            token["scope"] = str(user_token.scope)
            token["uses_pkce"] = user_token.uses_pkce
            token["token_type"] = user_token.token_type

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name == "spotify":
            await self.set_tokens()

    async def play_from_message(self, interaction: discord.Interaction, message: discord.Message):
        queue = interaction.command.name == "Queue on Spotify"
        user = interaction.user
        ctx = await self.bot.get_context(interaction)
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx, user)
        if not user_token:
            return

        content = message.content + " "
        if message.embeds:
            em_dict = message.embeds[0].to_dict()
            content += " ".join(
                str(v) for k, v in em_dict.items() if k in ["title", "description"]
            )
            if "title" in em_dict:
                if "url" in em_dict["title"]:
                    content += " " + em_dict["title"]["url"]
            if "fields" in em_dict:
                for field in em_dict["fields"]:
                    content += " " + field["name"] + " " + field["value"]
            log.verbose("Spotify content: %s", content)
        for component in message.components:
            if not isinstance(component, discord.ActionRow):
                if component.custom_id is not None:
                    continue
                if component.url is None:
                    continue
                content += f" {component.url}"
            else:
                for item in component.children:
                    if item.custom_id is not None:
                        continue
                    if item.url is None:
                        continue
                    content += f" {item.url}"

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
        if not any(tracks + albums + playlists):
            try:
                with user_spotify.token_as(user_token):
                    search = await user_spotify.search(
                        message.content, ("track",), "from_token", limit=50
                    )
                    items = search[0].items
            except Exception:
                await ctx.send(_("No tracks found from that search."))
                return
            if len(items) > 1:
                x = SpotifySearchMenu(
                    source=SpotifyTrackPages(items=items, detailed=False),
                    cog=self,
                    user_token=user_token,
                )
                await x.send_initial_message(ctx, ephemeral=True)
                return
            elif len(items) < 1:
                await ctx.send(_("No tracks found from that search."))
                return
            else:
                tracks.append(items[0].id)
        # play the song if it exists
        user_menu = SpotifyUserMenu(
            source=SpotifyPages(user_token=user_token, sender=self._sender, detailed=False),
            cog=self,
            user_token=user_token,
            ctx=ctx,
        )

        try:
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.config.user(user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if device is None:
                        await self.no_device(ctx)
                        return
                else:
                    device = cur.device

                if tracks:
                    all_tracks = await user_spotify.tracks(tracks)
                    track = all_tracks[0]
                    track_name = track.name
                    artists = getattr(track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    track_artist = humanize_list([a.name for a in artists])
                    em = await song_embed(track, False)
                    if queue:
                        await user_spotify.playback_queue_add(
                            all_tracks[0].uri, device_id=device.id
                        )
                        msg = _("Queueing {track} by {artist} on {device}.").format(
                            track=track_name, artist=artist, device=device.name
                        )
                    else:
                        await user_spotify.playback_start_tracks(tracks, device_id=device.id)
                        msg = _("Now playing {track} by {artist} on {device}.").format(
                            track=track_name, artist=artist, device=device.name
                        )
                    await asyncio.sleep(1)
                    await user_menu.send_initial_message(ctx, content=msg, ephemeral=True)
                    return
                elif new_uri:
                    log.debug("new uri is %s", new_uri)
                    if uri_type == "playlist":
                        if queue:
                            await interaction.response.send_message(
                                _("I cannot queue a playlist."),
                                ephemeral=True,
                            )
                            return
                        playlist_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.playlist(playlist_id)
                        track_name = cur_tracks.name
                        msg = _("Now playing {track} on {device}.").format(
                            track=track_name, device=device.name
                        )
                    if uri_type == "artist":
                        if queue:
                            await interaction.response.send_message(
                                _("I cannot queue an artist."),
                                ephemeral=True,
                            )
                            return
                        artist_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.artist(artist_id)
                        track_name = cur_tracks.name
                        msg = _("Now playing top tracks by {track} on {device}.").format(
                            track=track_name, device=device.name
                        )
                    if uri_type == "album":
                        if queue:
                            await interaction.response.send_message(
                                _("I cannot queue an album."),
                                ephemeral=True,
                            )
                            return
                        album_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.album(album_id)
                        track_name = cur_tracks.name
                        artists = getattr(cur_tracks, "artists", [])
                        artist = humanize_list([a.name for a in artists])
                        track_artist = humanize_list([a.name for a in artists])
                        msg = _("Now playing {track} by {artist} on {device}.").format(
                            track=track_name, artist=track_artist, device=device.name
                        )
                    await user_spotify.playback_start_context(new_uri, device_id=device.id)
                    await asyncio.sleep(1)
                    await user_menu.send_initial_message(ctx, content=msg, ephemeral=True)
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
                    log.verbose("play_from_message query: %s", query)
                    search = await user_spotify.search(query, ("track",), "from_token", limit=50)
                    # log.debug(search)
                    tracks = search[0].items
                    if tracks:
                        track_name = tracks[0].name
                        track_artist = humanize_list(tracks[0].artists)
                        em = await song_embed(tracks[0], False)
                        if queue:
                            await user_spotify.playback_queue_add(tracks[0].id)
                            msg = _("Queueing {track} by {artist} on {device}.").format(
                                track=track_name, artist=track_artist, device=device.name
                            )
                        else:
                            await user_spotify.playback_start_tracks(
                                [t.id for t in tracks], device_id=device.id
                            )
                            msg = _("Now playing {track} by {artist} on {device}.").format(
                                track=track_name, artist=track_artist, device=device.name
                            )
                        await user_menu.send_initial_message(ctx, content=msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(
                            _("No Spotify track could be found on that message."), ephemeral=True
                        )
                else:
                    await interaction.response.send_message(
                        _("No Spotify track could be found on that message."), ephemeral=True
                    )
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)
