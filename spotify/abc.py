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
        self.play_ctx: discord.app_commands.ContextMenu
        self.queue_ctx: discord.app_commands.ContextMenu

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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_slash(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def set_guild_slash_toggle(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_guild_context(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def set_global_slash_toggle(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_global_context(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def not_authorized(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def not_playing(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def no_user_token(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def no_device(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def forbidden_action(
        self, ctx: Union[commands.Context, discord.Interaction], error: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def unknown_error(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def show_settings(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def show_private(
        self, ctx: Union[commands.Context, discord.Interaction], show_private: bool
    ):
        raise NotImplementedError()

    @abstractmethod
    async def guild_clear_reactions(
        self, ctx: Union[commands.Context, discord.Interaction], clear_after: bool
    ):
        raise NotImplementedError()

    @abstractmethod
    async def guild_delete_message_after(
        self, ctx: Union[commands.Context, discord.Interaction], delete_after: bool
    ):
        raise NotImplementedError()

    @abstractmethod
    async def guild_menu_timeout(
        self, ctx: Union[commands.Context, discord.Interaction], timeout: int
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_reset_emoji(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_emojis(
        self, ctx: Union[commands.Context, discord.Interaction], *, new_emojis: ActionConverter
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_api_scope(
        self, ctx: Union[commands.Context, discord.Interaction], *scopes: ScopeConverter
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_view_api_scope(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_api_credential_set(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_forgetme(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_me(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_now(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        detailed: Optional[bool] = False,
        member: Optional[discord.Member] = None,
        public: bool = True,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_share(self, ctx: Union[commands.Context, discord.Interaction]):
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_genres(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_recommendations(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        detailed: Optional[bool] = False,
        *,
        recommendations: RecommendationsConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_recently_played(
        self, ctx: Union[commands.Context, discord.Interaction], detailed: Optional[bool] = False
    ):
        raise NotImplementedError()

    @abstractmethod
    async def top_tracks(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def top_artists(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_new(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_pause(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_resume(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_next(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_previous(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_play(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        url_or_playlist_name: Optional[str] = "",
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_queue_add(
        self, ctx: Union[commands.Context, discord.Interaction], *, songs: SpotifyURIConverter
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_repeat(
        self, ctx: Union[commands.Context, discord.Interaction], state: Optional[str]
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_shuffle(
        self, ctx: Union[commands.Context, discord.Interaction], state: Optional[bool] = None
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_seek(
        self, ctx: Union[commands.Context, discord.Interaction], seconds: Union[int, str]
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_volume(
        self, ctx: Union[commands.Context, discord.Interaction], volume: Union[int, str]
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_transfer(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        device_name: Optional[str] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_default(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        device_name: Optional[str] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_device_list(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_featured(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_list(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_view(self, ctx: Union[commands.Context, discord.Interaction]):
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
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_add(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        *,
        to_add: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_remove(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        name: str,
        *,
        to_remove: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_playlist_follow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        public: Optional[bool] = False,
        *,
        to_follow: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist_follow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        to_follow: SpotifyURIConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def spotify_artist_albums(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        to_follow: SpotifyURIConverter,
    ):
        raise NotImplementedError()
