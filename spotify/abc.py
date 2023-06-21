from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Literal, Mapping, Optional, Tuple, Union

import discord
import tekore
from redbot.core import Config, commands
from redbot.core.bot import Red

from .helpers import RecommendationsFlags, ScopeConverter, SpotifyURIConverter

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
        self.play_ctx: discord.app_commands.ContextMenu
        self.queue_ctx: discord.app_commands.ContextMenu

    #######################################################################
    # spotify.py                                                          #
    #######################################################################

    @abstractmethod
    async def cog_load(self):
        raise NotImplementedError()

    @abstractmethod
    async def get_user_spotify(
        self, ctx: commands.Context, user: Optional[discord.User] = None
    ) -> Optional[tekore.Spotify]:
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
        ctx: commands.Context,
        user: Optional[discord.User] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def ask_for_auth(self, ctx: commands.Context, author: discord.User):
        raise NotImplementedError()

    @abstractmethod
    async def save_token(self, author: discord.User, user_token: tekore.Token):
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
    async def spotify_com(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_set(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def not_authorized(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def not_playing(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def no_user_token(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def no_device(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def forbidden_action(self, ctx: commands.Context, error: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def unknown_error(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def show_settings(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def show_private(self, ctx: commands.Context, show_private: bool):
        raise NotImplementedError()

    @abstractmethod
    async def guild_clear_reactions(self, ctx: commands.Context, clear_after: bool):
        raise NotImplementedError()

    @abstractmethod
    async def guild_delete_message_after(self, ctx: commands.Context, delete_after: bool):
        raise NotImplementedError()

    @abstractmethod
    async def guild_menu_timeout(self, ctx: commands.Context, timeout: int):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_reset_emoji(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_emojis(self, ctx: commands.Context, *, new_emojis: ActionConverter):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_api_scope(self, ctx: commands.Context, *scopes: ScopeConverter):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_view_api_scope(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_api_credential_set(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_forgetme(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_me(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_now(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        member: Optional[discord.Member] = None,
        public: bool = True,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_share(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_search(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        search_type: Optional[SearchTypes] = "track",
        *,
        query: str,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_genres(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_recommendations(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        *,
        recommendations: RecommendationsFlags,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_recently_played(
        self, ctx: commands.Context, detailed: Optional[bool] = False
    ):
        raise NotImplementedError()

    @abstractmethod
    async def top_tracks(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def top_artists(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_new(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_pause(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_resume(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_next(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_previous(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_play(
        self,
        ctx: commands.Context,
        *,
        url_or_playlist_name: Optional[str] = "",
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_queue_add(self, ctx: commands.Context, *, songs: SpotifyURIConverter):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_repeat(self, ctx: commands.Context, state: Optional[str]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_shuffle(self, ctx: commands.Context, state: Optional[bool] = None):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_seek(self, ctx: commands.Context, seconds: Union[int, str]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_volume(self, ctx: commands.Context, volume: Union[int, str]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_transfer(
        self,
        ctx: commands.Context,
        *,
        device_name: Optional[str] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_default(
        self,
        ctx: commands.Context,
        *,
        device_name: Optional[str] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_list(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_featured(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_list(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_view(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_create(
        self,
        ctx: commands.Context,
        name: str,
        public: Optional[bool] = False,
        *,
        description: Optional[str] = "",
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_add(
        self,
        ctx: commands.Context,
        name: str,
        *,
        to_add: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_remove(
        self,
        ctx: commands.Context,
        name: str,
        *,
        to_remove: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_follow(
        self,
        ctx: commands.Context,
        public: Optional[bool] = False,
        *,
        to_follow: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist_follow(
        self,
        ctx: commands.Context,
        *,
        to_follow: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist_albums(
        self,
        ctx: commands.Context,
        *,
        to_follow: SpotifyURIConverter,
    ):
        raise NotImplementedError()
