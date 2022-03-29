from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Literal, Mapping, Optional, Tuple, Union

import discord
import tekore
from redbot.core import Config, commands
from redbot.core.bot import Red

from .helpers import RecommendationsConverter, ScopeConverter, SpotifyURIConverter

if TYPE_CHECKING:
    from .spotify_commands import ActionConverter


class SpotifyMixin(ABC):

    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.
    """

    def __init__(self, *_args):
        super().__init__()
        self.bot: Red
        self.config: Config
        self._app_token: tekore.RefreshingToken
        self._tokens: Tuple[str]
        self._spotify_client: tekore.Spotify
        self._sender: tekore.AsyncSender
        self._credentials: tekore.Credentials
        self._ready: asyncio.Event
        self.HAS_TOKENS: bool
        self.current_menus: Dict[int, int]
        self.user_menus: Dict[int, int]
        self.GENRES: List[str]

    #######################################################################
    # spotify.py                                                          #
    #######################################################################

    @abstractmethod
    async def migrate_settings(self):
        raise NotImplementedError()

    @abstractmethod
    async def cog_load(self):
        raise NotImplementedError()

    @abstractmethod
    async def format_help_for_context(self, ctx: commands.Context) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def cog_before_invoke(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def cog_unload(self):
        raise NotImplementedError()

    @abstractmethod
    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def get_user_auth(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        user: Optional[discord.User] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def ask_for_auth(
        self, ctx: Union[commands.Context, discord.Interaction], author: discord.User
    ):
        raise NotImplementedError()

    @abstractmethod
    async def save_token(self, author: discord.User, user_token: tekore.Token):
        raise NotImplementedError()

    @abstractmethod
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        raise NotImplementedError()

    @abstractmethod
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # spotify_commands.py                                                 #
    #######################################################################

    @abstractmethod
    async def spotify_com(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_set(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View Spotify Playlists
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View Spotify Artist info
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Spotify device commands
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_slash(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Slash command toggling for Spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def set_guild_slash_toggle(self, ctx: commands.Context):
        """Toggle this cog to register slash commands in this server"""
        raise NotImplementedError()

    @abstractmethod
    async def spotify_guild_context(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Toggle right click play on spotify for messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def set_global_slash_toggle(self, ctx: commands.Context):
        """Toggle this cog to register slash commands"""
        raise NotImplementedError()

    @abstractmethod
    async def spotify_global_context(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Toggle right click play on spotify for messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def not_authorized(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def not_playing(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def no_user_token(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def no_device(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def forbidden_action(
        self, ctx: Union[commands.Context, discord.Interaction], error: str
    ) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        raise NotImplementedError()

    @abstractmethod
    async def unknown_error(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def show_settings(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Show settings for menu timeouts
        """
        raise NotImplementedError()

    @abstractmethod
    async def show_private(
        self, ctx: Union[commands.Context, discord.Interaction], show_private: bool
    ):
        """
        Set whether or not to show private playlists

        This will also display your spotify username and a link
        to your profile if you use `[p]spotify me` command in public channels.
        """
        raise NotImplementedError()

    @abstractmethod
    async def guild_clear_reactions(
        self, ctx: Union[commands.Context, discord.Interaction], clear_after: bool
    ):
        """
        Set whether or not to clear reactions after sending the message

        Note: the bot requires manage messages for this to work
        """
        raise NotImplementedError()

    @abstractmethod
    async def guild_delete_message_after(
        self, ctx: Union[commands.Context, discord.Interaction], delete_after: bool
    ):
        """
        Set whether or not to delete the spotify message after timing out

        """
        raise NotImplementedError()

    @abstractmethod
    async def guild_menu_timeout(
        self, ctx: Union[commands.Context, discord.Interaction], timeout: int
    ):
        """
        Set the timeout time for spotify menus

        `<timeout>` The time until the menu will timeout. This does not affect
        interacting with the menu.
        Note: This has a maximum of 10 minutes and a minimum of 30 seconds.
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_reset_emoji(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Resets the bot to use the default emojis
        """
        raise NotImplementedError()

    @abstractmethod
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
           `like` -> 💚
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
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_view_api_scope(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View the current scopes being requested
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_api_credential_set(self, ctx: Union[commands.Context, discord.Interaction]):
        """Instructions to set the Spotify API tokens."""
        raise NotImplementedError()

    @abstractmethod
    async def spotify_forgetme(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Forget all your spotify settings and credentials on the bot
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_me(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Shows your current Spotify Settings
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_share(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Tell the bot to play the users current song in their current voice channel
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_genres(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Display all available genres for the recommendations
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_recently_played(
        self, ctx: Union[commands.Context, discord.Interaction], detailed: Optional[bool] = False
    ):
        """
        Displays your most recently played songs on Spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def top_tracks(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your top tracks on spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def top_artists(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your top artists on spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_new(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List new releases on Spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_pause(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Pauses spotify for you
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_resume(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Resumes spotify for you
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_next(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Skips to the next track in queue on Spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_previous(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        Skips to the previous track in queue on Spotify
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_queue_add(
        self, ctx: Union[commands.Context, discord.Interaction], *, songs: SpotifyURIConverter
    ):
        """
        Queue a song to play next in Spotify

        `<songs>` is one or more spotify URL or URI leading to a single track that will
        be added to your current queue
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_repeat(
        self, ctx: Union[commands.Context, discord.Interaction], state: Optional[str]
    ):
        """
        Repeats your current song on spotify

        `<state>` must accept one of `off`, `track`, or `context`.
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_shuffle(
        self, ctx: Union[commands.Context, discord.Interaction], state: Optional[bool] = None
    ):
        """
        Shuffles your current song list

        `<state>` either true or false. Not providing this will toggle the current setting.
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_seek(
        self, ctx: Union[commands.Context, discord.Interaction], seconds: Union[int, str]
    ):
        """
        Seek to a specific point in the current song

        `<seconds>` Accepts seconds or a value formatted like
        00:00:00 (`hh:mm:ss`) or 00:00 (`mm:ss`).
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_volume(
        self, ctx: Union[commands.Context, discord.Interaction], volume: Union[int, str]
    ):
        """
        Set your spotify volume percentage

        `<volume>` a number between 0 and 100 for volume percentage.
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_list(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List all available devices for Spotify
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_featured(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your Spotify featured Playlists
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_list(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        List your Spotify Playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_view(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View details about your spotify playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        raise NotImplementedError()

    @abstractmethod
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_add(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        *,
        to_add: SpotifyURIConverter,
    ):
        """
        Add 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to add songs to
        `<to_add>` The song links or URI's you want to add
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_remove(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        *,
        to_remove: SpotifyURIConverter,
    ):
        """
        Remove 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to remove songs from
        `<to_remove>` The song links or URI's you want to have removed
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_follow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        public: Optional[bool] = False,
        *,
        to_follow: SpotifyURIConverter,
    ):
        """
        Add a playlist to your spotify library

        `[public]` Whether or not the followed playlist should be public after
        `<to_follow>` The song links or URI's you want to have removed
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist_follow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        to_follow: SpotifyURIConverter,
    ):
        """
        Add an artist to your spotify library

        `<to_follow>` The song links or URI's you want to have removed
        """
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist_albums(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        to_follow: SpotifyURIConverter,
    ):
        """
        View an artists albums

        `<to_follow>` The artis links or URI's you want to view the albums of
        """
        raise NotImplementedError()
