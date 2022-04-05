from __future__ import annotations

import asyncio
import logging
from copy import copy
from typing import Any, List, Optional, Tuple

import discord
import tekore
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list
from redbot.vendored.discord.ext import menus

from .helpers import (
    REPEAT_STATES,
    SPOTIFY_LOGO,
    InvalidEmoji,
    NotPlaying,
    _draw_play,
    make_details,
)

log = logging.getLogger("red.Trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


class EmojiHandler:
    def __init__(self):
        from .emojis import emojis

        # with open(Path(__file__).parent / "emojis.json", "r", encoding="utf8") as infile:
        self.emojis = emojis
        self.default = copy(self.emojis)

    def get_emoji(self, name: str, use_external: bool = True) -> discord.PartialEmoji:
        if use_external and name in self.emojis:
            return discord.PartialEmoji.from_str(self.emojis[name])
        return discord.PartialEmoji.from_str(self.default[name])
        # we shouldn't have anyone deleting emoji keys

    def reload_emojis(self):
        # we could just copy default but we can also just
        # reload the emojis from disk
        self.emojis = copy(self.default)

    def replace_emoji(self, name: str, to: str):
        if name not in self.emojis:
            raise InvalidEmoji
        self.emojis[name] = to


emoji_handler = EmojiHandler()  # initialize here so when it's changed other objects use this one


class SpotifyTrackPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullTrack], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None
        self.detailed = detailed
        self.select_options = []
        self.items = items
        for count, item in enumerate(items):
            artists = getattr(item, "artists", [])
            artist = humanize_list([a.name for a in artists])[:50]
            label = item.name[:19]
            description = artist
            self.select_options.append(
                discord.SelectOption(
                    label=f"{count+1}. {label}", value=count, description=description
                )
            )

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, track: tekore.model.FullTrack
    ) -> discord.Embed:
        self.current_track = track
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/track/{track.id}"
        artist_title = f"{track.name} by " + ", ".join(a.name for a in track.artists)
        album = getattr(track, "album", "")
        if album:
            album = f"[{album.name}](https://open.spotify.com/album/{album.id})"
        em.set_author(
            name=track.name[:256],
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        em.description = f"[{artist_title}]({url})\n\n{album}"
        if track.album.images:
            em.set_thumbnail(url=track.album.images[0].url)
        if self.detailed:
            sp = tekore.Spotify(sender=view.cog._sender)
            with sp.token_as(view.user_token):
                details = await sp.track_audio_features(track.id)

            msg = await make_details(track, details)
            em.add_field(name="Details", value=box(msg[:1000], lang="css"))
        try:
            em.set_footer(
                text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
            )
        except AttributeError:
            pass
        return em


class SpotifyArtistPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullArtist], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, artist: tekore.model.FullArtist
    ) -> discord.Embed:
        self.current_track = artist
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/artist/{artist.id}"
        artist_title = f"{artist.name}"
        em.set_author(
            name=artist_title,
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        sp = tekore.Spotify(sender=view.cog._sender)
        with sp.token_as(view.user_token):
            cur = await sp.artist_top_tracks(artist.id, "from_token")
        msg = _("Top Tracks\n")
        for track in cur:
            msg += f"[{track.name}](https://open.spotify.com/track/{track.id})\n"
        em.description = msg
        if artist.images:
            em.set_thumbnail(url=artist.images[0].url)
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyAlbumPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullAlbum], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None
        self.select_options = []
        self.items = items
        for count, item in enumerate(items):
            artists = getattr(item, "artists", [])
            artist = humanize_list([a.name for a in artists])[:50]
            label = item.name[:19]
            description = artist
            self.select_options.append(
                discord.SelectOption(
                    label=f"{count+1}. {label}", value=count, description=description
                )
            )

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, album: tekore.model.FullAlbum
    ) -> discord.Embed:
        self.current_track = album
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/album/{album.id}"
        title = f"{album.name} by {humanize_list([a.name for a in album.artists])}"
        if len(title) > 256:
            title = title[:253] + "..."
        em.set_author(
            name=title,
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        msg = "Tracks:\n"
        sp = tekore.Spotify(sender=view.cog._sender)
        with sp.token_as(view.user_token):
            cur = await sp.album(album.id)
        for track in cur.tracks.items:
            msg += f"[{track.name}](https://open.spotify.com/track/{track.id})\n"
        em.description = msg
        if album.images:
            em.set_thumbnail(url=album.images[0].url)
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyPlaylistPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.SimplePlaylist], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None
        self.select_options = []
        self.items = items
        for count, item in enumerate(items):
            description = item.name[:50]
            self.select_options.append(
                discord.SelectOption(
                    label=f"Page {count + 1}", value=count, description=description
                )
            )

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, playlist: tekore.model.SimplePlaylist
    ) -> discord.Embed:
        self.current_track = playlist
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/playlist/{playlist.id}"
        artists = getattr(playlist, "artists", [])
        artist = humanize_list([a.name for a in artists])[:256]
        em.set_author(
            name=artist or playlist.name,
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        user_spotify = tekore.Spotify(sender=view.cog._sender)
        description = ""
        with user_spotify.token_as(view.user_token):
            cur = await user_spotify.playlist_items(playlist.id)
            for track in cur.items[:10]:
                description += (
                    f"[{track.track.name}](https://open.spotify.com/track/{track.track.id})\n"
                )

        em.description = description
        if playlist.images:
            em.set_thumbnail(url=playlist.images[0].url)
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyNewPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.SimplePlaylist]):
        super().__init__(items, per_page=1)
        self.current_track = None
        self.select_options = []
        self.items = items
        for count, item in enumerate(items):
            artists = getattr(item, "artists", [])
            artist = humanize_list([a.name for a in artists])[:50]
            label = item.name[:19]
            description = artist
            self.select_options.append(
                discord.SelectOption(
                    label=f"{count+1}. {label}", value=count, description=description
                )
            )

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, playlist: tekore.model.SimplePlaylist
    ) -> discord.Embed:
        self.current_track = playlist
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/playlist/{playlist.id}"
        artists = getattr(playlist, "artists", [])
        artist = humanize_list([a.name for a in artists])[:256]
        em.set_author(
            name=artist or playlist.name,
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        user_spotify = tekore.Spotify(sender=view.cog._sender)
        description = ""
        with user_spotify.token_as(view.user_token):
            if playlist.type == "playlist":
                cur = await user_spotify.playlist_items(playlist.id)
                for track in cur.items[:10]:
                    description += f"[{track.track.name}](https://open.spotify.com/playlist/{track.track.id})\n"
            if playlist.type == "album":
                album = await user_spotify.album(playlist.id)
                cur = album.tracks
                for track in cur.items[:10]:
                    description += f"[{track.name}](https://open.spotify.com/album/{track.id})\n"

        em.description = description
        if playlist.images:
            em.set_thumbnail(url=playlist.images[0].url)
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyEpisodePages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullEpisode], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None
        self.detailed = detailed

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, episode: tekore.model.FullEpisode
    ) -> discord.Embed:
        self.current_track = episode
        show = episode.show
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/episode/{episode.id}"
        artist_title = f"{show.name} by {show.publisher}"
        em.set_author(
            name=artist_title[:256],
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        em.description = f"[{episode.description[:1900]}]({url})\n"
        if episode.images:
            em.set_thumbnail(url=episode.images[0].url)
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyShowPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullShow], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None
        self.detailed = detailed

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, show: tekore.model.FullShow
    ) -> discord.Embed:
        self.current_track = show
        em = discord.Embed(color=discord.Colour(0x1DB954))
        url = f"https://open.spotify.com/show/{show.id}"
        artist_title = f"{show.name} by {show.publisher}"
        em.set_author(
            name=artist_title[:256],
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        em.description = f"[{show.description[:1900]}]({url})\n"
        if show.images:
            em.set_thumbnail(url=show.images[0].url)
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyRecentSongPages(menus.ListPageSource):
    def __init__(self, tracks: List[tekore.model.PlayHistory], detailed: bool):
        super().__init__(tracks, per_page=1)
        self.current_track = None
        self.detailed = detailed
        self.select_options = []
        self.items = tracks
        for count, item in enumerate(tracks):
            artists = getattr(item.track, "artists", [])
            artist = humanize_list([a.name for a in artists])[:50]
            label = item.track.name[:19]
            description = artist
            self.select_options.append(
                discord.SelectOption(
                    label=f"{count+1}. {label}", value=count, description=description
                )
            )

    def is_paginating(self):
        return True

    async def format_page(
        self, view: discord.ui.View, history: tekore.model.PlayHistory
    ) -> discord.Embed:
        track = history.track
        self.current_track = track
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954), timestamp=history.played_at)
        url = f"https://open.spotify.com/track/{track.id}"
        artist_title = f"{track.name} by " + ", ".join(a.name for a in track.artists)
        em.set_author(
            name=track.name[:256],
            url=url,
            icon_url=SPOTIFY_LOGO,
        )
        em.description = f"[{artist_title}]({url})\n"
        if track.album.images:
            em.set_thumbnail(url=track.album.images[0].url)
        if self.detailed:
            sp = tekore.Spotify(sender=view.cog._sender)
            with sp.token_as(view.user_token):
                details = await sp.track_audio_features(history.track.id)

            msg = await make_details(track, details)
            em.add_field(name="Details", value=box(msg[:1000], lang="css"))
        em.set_footer(
            text=f"Page {view.current_page + 1}/{self.get_max_pages()} | Played at",
        )
        return em


class SpotifyPlaylistsPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.SimplePlaylist]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, view: discord.ui.View, playlists: List[tekore.model.SimplePlaylist]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=_("{user}'s Spotify Playlists").format(user=view.author.display_name),
            icon_url=view.author.avatar.url,
        )
        msg = ""
        for playlist in playlists:
            if playlist.public:
                msg += f"[{playlist.name}](https://open.spotify.com/playlist/{playlist.id})\n"
            else:
                msg += f"{playlist.name}\n"
        em.description = msg
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
            icon_url=SPOTIFY_LOGO,
        )
        return em


class SpotifyTopTracksPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.FullTrack]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, view: discord.ui.View, tracks: List[tekore.model.FullTrack]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=_("{user}'s Top Tracks").format(user=view.author.display_name),
            icon_url=view.author.avatar.url,
        )
        msg = ""
        for track in tracks:
            artist = humanize_list([a.name for a in track.artists])
            msg += f"[{track.name} by {artist}](https://open.spotify.com/track/{track.id})\n"
        em.description = msg
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
            icon_url=SPOTIFY_LOGO,
        )
        return em


class SpotifyTopArtistsPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.FullArtist]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, view: discord.ui.View, artists: List[tekore.model.FullArtist]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=_("{user}'s Top Artists").format(user=view.author.display_name),
            icon_url=view.author.avatar.url,
        )
        msg = ""
        for artist in artists:
            msg += f"[{artist.name}](https://open.spotify.com/artist/{artist.id})\n"
        em.description = msg
        em.set_footer(
            text=_("Page") + f" {view.current_page + 1}/{self.get_max_pages()}",
            icon_url=SPOTIFY_LOGO,
        )
        return em


class SpotifyPages(menus.PageSource):
    def __init__(self, user_token: tekore.Token, sender: tekore.AsyncSender, detailed: bool):
        super().__init__()
        self.user_token = user_token
        self.sender = sender
        self.detailed = detailed
        self.current_track = None
        self.is_liked = False
        self.is_playing = True
        self.is_shuffle = False
        self.repeat_state = "off"
        self.context = None
        self.select_options: List[SpotifyTrackOption] = []
        self.context_name = None

    async def format_page(
        self,
        view: discord.ui.View,
        cur_state: Tuple[tekore.model.CurrentlyPlayingContext, bool],
    ) -> discord.Embed:

        state = cur_state[0]
        is_liked = cur_state[1]
        self.context = state.context
        self.is_liked = is_liked
        self.is_playing = state.is_playing
        self.is_shuffle = state.shuffle_state
        self.repeat_state = state.repeat_state
        em = discord.Embed(color=discord.Colour(0x1DB954))
        self.current_track = state.item
        if getattr(state.item, "is_local", False):
            url = "https://open.spotify.com/"
            artist_title = f"{state.item.name} by " + humanize_list(
                [a.name for a in state.item.artists]
            )
            image = SPOTIFY_LOGO
        elif state.item.type == "episode":
            url = f"https://open.spotify.com/episode/{state.item.id}"
            artist_title = state.item.name
            image = state.item.images[0].url
        else:
            url = f"https://open.spotify.com/track/{state.item.id}"
            artist_title = f"{state.item.name} by " + humanize_list(
                [a.name for a in state.item.artists]
            )
            image = state.item.album.images[0].url
        album = getattr(state.item, "album", "")
        if album:
            album = f"[{album.name}](https://open.spotify.com/album/{album.id})"
        em.set_author(
            name=f"{view.author.display_name}" + _(" is currently listening to"),
            icon_url=view.author.avatar.url,
            url=url,
        )
        repeat = (
            f"Repeat: {REPEAT_STATES[state.repeat_state]} |" if state.repeat_state != "off" else ""
        )
        shuffle = "Shuffle: \N{TWISTED RIGHTWARDS ARROWS} |" if state.shuffle_state else ""
        liked = "Liked: \N{GREEN HEART}" if is_liked else ""
        footer = f"{repeat}{shuffle}{liked}"
        em.set_footer(text=footer, icon_url=SPOTIFY_LOGO)
        em.description = f"[{artist_title}]({url})\n\n{album}\n{_draw_play(state)}"
        try:
            if self.detailed and not getattr(state.item, "is_local", False):
                sp = tekore.Spotify(sender=self.sender)
                with sp.token_as(self.user_token):
                    details = await sp.track_audio_features(state.item.id)

                msg = await make_details(state.item, details)
                em.add_field(name="Details", value=box(msg[:1000], lang="css"))
        except tekore.NotFound:
            pass
        em.set_thumbnail(url=image)
        return em

    def is_paginating(self):
        """An abstract method that notifies the :class:`MenuPages` whether or not
        to start paginating. This signals whether to add reactions or not.
        Subclasses must implement this.
        Returns
        --------
        :class:`bool`
            Whether to trigger pagination.
        """
        return True

    def get_max_pages(self):
        """An optional abstract method that retrieves the maximum number of pages
        this page source has. Useful for UX purposes.
        The default implementation returns ``None``.
        Returns
        --------
        Optional[:class:`int`]
            The maximum number of pages required to properly
            paginate the elements, if given.
        """
        return None

    async def get_page(self, page_number):
        """|coro|
        An abstract method that retrieves an object representing the object to format.
        Subclasses must implement this.
        .. note::
            The page_number is zero-indexed between [0, :meth:`get_max_pages`),
            if there is a maximum number of pages.
        Parameters
        -----------
        page_number: :class:`int`
            The page number to access.
        Returns
        ---------
        Any
            The object represented by that page.
            This is passed into :meth:`format_page`.
        """
        try:
            user_spotify = tekore.Spotify(sender=self.sender)
            with user_spotify.token_as(self.user_token):
                cur_state = await user_spotify.playback()
                if not cur_state:
                    raise NotPlaying
                is_liked = False
                if not getattr(cur_state.item, "is_local", False):
                    song = cur_state.item.id
                    liked = await user_spotify.saved_tracks_contains([song])
                    is_liked = liked[0]
                    self.is_liked = liked[0]
                if cur_state.context is not None:
                    playlist_id = cur_state.context.uri.split(":")[-1]
                    cur_tracks = None
                    tracks = []
                    if cur_state.context.type == "playlist":
                        cur_tracks = await user_spotify.playlist(playlist_id)
                        tracks = [t.track for t in cur_tracks.tracks.items if t.track is not None]
                    if cur_state.context.type == "album":
                        cur_tracks = await user_spotify.album(playlist_id)
                        tracks = [t for t in cur_tracks.tracks.items if t is not None]
                    if cur_state.context.type == "artist":
                        cur_tracks = await user_spotify.artist(playlist_id)
                        top_tracks = await user_spotify.artist_top_tracks(
                            playlist_id, "from_token"
                        )
                        tracks = [t for t in top_tracks if t is not None]
                    if cur_state.context.type == "collection":
                        cur_tracks = await user_spotify.saved_tracks(limit=50)
                        cur_tracks.name = _("Saved Tracks")
                        tracks = [t.track for t in cur_tracks.items if t is not None]
                    if cur_tracks:
                        self.context_name = cur_tracks.name
                    for track in tracks:
                        if track.id is not None:
                            self.select_options.append(SpotifyTrackOption(track))
                if self.select_options and cur_state.context is None:
                    self.select_options = []
        except tekore.Unauthorised:
            raise
        return cur_state, is_liked


class SpotifyTrackOption(discord.SelectOption):
    def __init__(self, track: tekore.FullTrack):
        super().__init__(
            label=track.name[:100],
            description=humanize_list([i.name for i in track.artists])[:100],
            value=track.id,
        )
        self.track = track


class SpotifySelectTrack(discord.ui.Select):
    def __init__(
        self,
        options: List[discord.SelectOption],
        cog: commands.Cog,
        user_token: tekore.Token,
        placeholder: str,
    ):
        super().__init__(min_values=1, max_values=1, options=options, placeholder=placeholder)
        self.cog = cog
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        track_id = self.values[0]
        track = None
        for track_ in self.options:
            if track_id == track_.track.id:
                track = track_.track
        device_id = None
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.cog.config.user(interaction.user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        await self.cog.no_device(interaction)
                        return
                else:
                    device = cur.device
                await user_spotify.playback_start_context(
                    self.view.source.context.uri, offset=track_id, device_id=device_id
                )
                track_name = track.name
                artists = humanize_list([i.name for i in track.artists])
                await interaction.response.send_message(
                    _("Playing {track} by {artist} on {device}.").format(
                        track=track_name, artist=artists, device=device.name
                    ),
                    ephemeral=True,
                )
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class PlayPauseButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("playpause")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """go to the previous page"""
        try:
            device_id = None
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.cog.config.user(interaction.user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        await self.cog.no_device(interaction)
                        return
                else:
                    device = cur.device
                    device_id = device.id
                if cur.item.id == self.view.source.current_track.id:
                    if cur.is_playing:
                        await interaction.response.send_message(
                            _("Pausing Spotify on {device}.").format(device=device.name),
                            ephemeral=True,
                        )
                        await user_spotify.playback_pause(device_id=device_id)
                        self.emoji = emoji_handler.get_emoji("play")
                    else:
                        await interaction.response.send_message(
                            _("Resuming Spotify playback on {device}.").format(device=device.name),
                            ephemeral=True,
                        )
                        await user_spotify.playback_resume(device_id=device_id)
                        self.emoji = emoji_handler.get_emoji("pause")
                else:
                    if self.view.source.current_track.type == "track":
                        track_name = self.view.source.current_track.name
                        artists = humanize_list(
                            [i.name for i in self.view.source.current_track.artists]
                        )
                        await interaction.response.send_message(
                            _("Playing {track} by {artist} on {device}.").format(
                                track=track_name, artist=artists, device=device.name
                            ),
                            ephemeral=True,
                        )
                        await user_spotify.playback_start_tracks(
                            [self.view.source.current_track.id], device_id=device_id
                        )
                    else:
                        track_name = self.view.source.current_track.name
                        artists = humanize_list(
                            [i.name for i in self.view.source.current_track.artists]
                        )
                        await interaction.response.send_message(
                            _("Playing {track} by {artist} on {device}.").format(
                                track=track_name, artist=artists, device=device.name
                            ),
                            ephemeral=True,
                        )
                        await user_spotify.playback_start_context(
                            self.view.source.current_track.uri, device_id=device_id
                        )
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token,
                sender=self.cog._sender,
                detailed=self.view.source.detailed,
            )
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class PreviousTrackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("previous")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                await user_spotify.playback_previous()
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token,
                sender=self.cog._sender,
                detailed=self.view.source.detailed,
            )
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class NextTrackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("next")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                await user_spotify.playback_next()
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token,
                sender=self.cog._sender,
                detailed=self.view.source.detailed,
            )
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class ShuffleButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("shuffle")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """go to the next page"""
        try:
            device_id = None
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.cog.config.user(interaction.user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        await interaction.response.send_message(
                            _("I could not find an active device to play songs on."),
                            ephemeral=True,
                        )
                        return
                else:
                    device = cur.device
                    device_id = device.id
                state = not cur.shuffle_state
                if state:
                    self.style = discord.ButtonStyle.primary
                else:
                    self.style = discord.ButtonStyle.grey
                await user_spotify.playback_shuffle(state, device_id=device_id)
                await interaction.response.send_message(
                    _("Shuffling Spotify on {device}.").format(device=device.name), ephemeral=True
                )
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token,
                sender=self.cog._sender,
                detailed=self.view.source.detailed,
            )
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class RepeatButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("repeat")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """go to the next page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if cur.repeat_state == "off":
                    self.style = discord.ButtonStyle.primary
                    self.emoji = emoji_handler.get_emoji("repeat")
                    state = "context"
                if cur.repeat_state == "context":
                    self.style = discord.ButtonStyle.primary
                    self.emoji = emoji_handler.get_emoji("repeatone")
                    state = "track"
                if cur.repeat_state == "track":
                    self.style = discord.ButtonStyle.grey
                    self.emoji = emoji_handler.get_emoji("repeat")
                    state = "off"
                await user_spotify.playback_repeat(state)
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token,
                sender=self.cog._sender,
                detailed=self.view.source.detailed,
            )
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class LikeButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{GREEN HEART}"
        self.cog = cog
        self.source = source
        self.user_token = user_token
        self.disabled = False

    async def callback(self, interaction: discord.Interaction):
        """go to the next page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await self.cog.no_device(interaction)
                    return
                tracks = [self.view.source.current_track.id]
                if (await user_spotify.saved_tracks_contains(tracks))[0]:
                    await user_spotify.saved_tracks_delete(tracks)
                    await interaction.response.send_message(
                        _("Removed from your Liked Songs."), ephemeral=True
                    )

                else:
                    await user_spotify.saved_tracks_add(tracks)
                    await interaction.response.send_message(
                        _("Added to your Liked Songs."), ephemeral=True
                    )
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token,
                sender=self.cog._sender,
                detailed=self.view.source.detailed,
            )
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class PlayAllButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row, label=_("Play All"))
        self.style = style
        self.emoji = emoji_handler.get_emoji("playall")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """go to the previous page"""
        try:
            device_id = None
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.cog.config.user(interaction.user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        await self.cog.no_device(interaction)
                        return
                else:
                    device = cur.device
                if self.view.source.current_track.type == "track":
                    await user_spotify.playback_start_tracks(
                        [i.id for i in self.view.source.entries], device_id=device_id
                    )
                else:
                    await user_spotify.playback_start_context(
                        self.view.source.current_track.uri, device_id=device_id
                    )
                await interaction.response.send_message(
                    _("Now playing all songs on {device}.").format(device=device.name),
                    ephemeral=True,
                )
        except tekore.Unauthorised:
            await interaction.response.send_message.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()


class QueueTrackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row, label=_("Queue"))
        self.style = style
        self.emoji = emoji_handler.get_emoji("queue")
        self.cog = cog
        self.source = source
        self.user_token = user_token

    async def callback(self, interaction: discord.Interaction):
        """go to the previous page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            device_id = None
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.cog.config.user(interaction.user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if not device:
                        await self.cog.no_device(interaction)
                        return
                else:
                    device = cur.device
                if self.view.source.current_track.type == "track":
                    await user_spotify.playback_queue_add(
                        self.view.source.current_track.uri, device_id=device_id
                    )
                    await interaction.response.send_message(
                        _("{track} by {artist} has been added to your queue on {device}.").format(
                            track=self.view.source.current_track.name,
                            artist=humanize_list(
                                [i.name for i in self.view.source.current_track.artists]
                            ),
                            device=device.name,
                        ),
                        ephemeral=True,
                    )
                else:
                    await user_spotify.playback_start_context(
                        self.view.source.current_track.uri, device_id=device_id
                    )
        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        log.debug("deleting message")
        await interaction.message.delete()
        self.view.stop()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("play")

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page + 1, interaction)


class BackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("back_left")

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page - 1, interaction)


class LastItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("next")

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction)


class FirstItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = emoji_handler.get_emoji("previous")

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class SpotifyUserMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        clear_buttons_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.author = None
        self.message = message
        self._source = source
        self.user_token = user_token
        self.cog = cog
        self.ctx = kwargs.get("ctx", None)
        self.delete_message_after = delete_message_after
        self.clear_buttons_after = clear_buttons_after
        self._running = True
        self.previous_button = PreviousTrackButton(
            discord.ButtonStyle.grey, 0, cog, source, user_token
        )
        self.next_button = NextTrackButton(discord.ButtonStyle.grey, 0, cog, source, user_token)
        self.play_pause_button = PlayPauseButton(
            discord.ButtonStyle.primary, 0, cog, source, user_token
        )
        self.shuffle_button = ShuffleButton(discord.ButtonStyle.grey, 1, cog, source, user_token)
        self.repeat_button = RepeatButton(discord.ButtonStyle.grey, 1, cog, source, user_token)
        self.like_button = LikeButton(discord.ButtonStyle.grey, 1, cog, source, user_token)
        self.stop_button = StopButton(discord.ButtonStyle.red, 1)
        self.add_item(self.previous_button)
        self.add_item(self.play_pause_button)
        self.add_item(self.next_button)
        self.add_item(self.repeat_button)
        self.add_item(self.shuffle_button)
        self.add_item(self.like_button)
        self.add_item(self.stop_button)
        self.select_view: Optional[SpotifySelectTrack] = None

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        self._running = False
        # self.loop.cancel()
        if self.message is None:
            return
        if self.clear_buttons_after:
            await self.message.edit(view=None)
        elif self.delete_message_after:
            await self.message.delete()

    async def edit_menu_page_auto(self):
        """
        This is used to handled editing the menu when
        we detect that the song has changed from spotify
        It has no return so as not to edit the length
        of timeout on the menu itself so it returns nothing

        This is a minor quality of life feature so that
        if the track changes while you do the command it doesn't
        show an old song when you're already listening to a new song
        """
        # This cannot work with the current method of refreshing components
        # in d.py since this triggers a refresh of the timer
        # thus this is being removed for the time being
        while self._running:
            await asyncio.sleep(30)
            user_spotify = tekore.Spotify(sender=self.source.sender)
            with user_spotify.token_as(self.source.user_token):
                cur_state = await user_spotify.playback()
                if not cur_state or not cur_state.item:
                    continue
                await self.show_checked_page(0)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        is_slash = False

        if isinstance(ctx, discord.Interaction):
            is_slash = True
            self.author = ctx.user
        else:
            self.author = ctx.author
        if self.ctx is None:
            self.ctx = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if isinstance(self.source, SpotifyPages):
            if self.source.repeat_state == "track":
                self.repeat_button.emoji = REPEAT_STATES[self.source.repeat_state]
                self.repeat_button.style = discord.ButtonStyle.primary
            if self.source.repeat_state == "context":
                self.repeat_button.emoji = REPEAT_STATES[self.source.repeat_state]
                self.repeat_button.style = discord.ButtonStyle.primary

            if self.source.is_liked:
                self.like_button.emoji = emoji_handler.get_emoji("like")
            if not self.source.is_liked:
                self.like_button.emoji = "\N{BLACK HEART}"

            if self.source.is_playing:
                self.play_pause_button.emoji = emoji_handler.get_emoji("pause")
            if not self.source.is_playing:
                self.play_pause_button.emoji = emoji_handler.get_emoji("play")
            if self.source.is_shuffle:
                self.shuffle_button.style = discord.ButtonStyle.primary

            if self.source.select_options:
                for op in self.source.select_options:
                    if self.source.current_track and self.source.current_track.id == op.value:
                        op.emoji = discord.PartialEmoji.from_str(
                            "\N{SPEAKER WITH THREE SOUND WAVES}"
                        )
                    else:
                        op.emoji = None
                self.select_view = SpotifySelectTrack(
                    self.source.select_options[:25],
                    self.cog,
                    self.user_token,
                    self.source.context_name,
                )
                self.add_item(self.select_view)
        if is_slash:
            self.message = await ctx.followup.send(**kwargs, view=self, wait=True)
        else:
            self.message = await channel.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        if self._source.is_liked:
            self.like_button.emoji = emoji_handler.get_emoji("like")
        if not self._source.is_liked:
            self.like_button.emoji = "\N{BLACK HEART}"
        kwargs = await self._get_kwargs_from_page(page)
        if self.source.select_options:
            options = self.source.select_options[:25]
            for op in self.source.select_options:
                if self.source.current_track and self.source.current_track.id == op.value:
                    op.emoji = discord.PartialEmoji.from_str("\N{SPEAKER WITH THREE SOUND WAVES}")
                else:
                    op.emoji = None
            if len(self.source.select_options) > 25 and page_number > 12:
                self.remove_item(self.select_view)
                options = self.source.select_options[page_number - 12 : page_number + 13]
                self.select_view = SpotifySelectTrack(
                    options, self.cog, self.user_token, self.source.context_name
                )
                self.add_item(self.select_view)
        if self.select_view and not self.source.select_options:
            self.remove_item(self.select_view)
            self.select_view = None
        if not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs, view=self)
        else:
            await interaction.followup.edit(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def on_error(self, error, interaction: discord.Interaction, button: discord.ui.Button):
        log.debug(f"{error=} {button=} {interaction=}")

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        log.debug("Checking interaction")
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class SpotifySelectOption(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        await self.view.show_checked_page(index, interaction)


class SpotifyDeviceView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        if isinstance(ctx, discord.Interaction):
            self.author = ctx.user
        else:
            self.author = ctx.author
        self.device_id = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                _("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class SpotifySelectDevice(discord.ui.Select):
    def __init__(
        self,
        options: List[discord.SelectOption],
        user_token: str,
        sender: tekore.AsyncSender,
        send_callback=True,
    ):
        super().__init__(
            min_values=1, max_values=1, options=options, placeholder=_("Pick a device")
        )
        self._sender = sender
        self.user_token = user_token
        self.send_callback = send_callback
        self.device_id = None

    async def callback(self, interaction: discord.Interaction):
        self.view.device_id = self.values[0]
        if not self.send_callback:
            self.view.stop()
            return
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(self.user_token):
            now = await user_spotify.playback()
            await user_spotify.playback_transfer(self.values[0], now.is_playing)


class SpotifySearchMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        clear_buttons_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self._source = source
        self.author = None
        self.message = message
        self.user_token = user_token
        self.cog = cog
        self.ctx = None
        self.clear_buttons_after = clear_buttons_after
        self.delete_message_after = delete_message_after
        self.current_page = kwargs.get("page_start", 0)
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)

        self.play_pause_button = PlayPauseButton(
            discord.ButtonStyle.primary, 1, cog, source, user_token
        )
        self.play_all = PlayAllButton(discord.ButtonStyle.grey, 1, cog, source, user_token)
        self.queue_track = QueueTrackButton(discord.ButtonStyle.grey, 1, cog, source, user_token)
        self.stop_button = StopButton(discord.ButtonStyle.red, 1)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.play_pause_button)
        self.add_item(self.play_all)
        self.add_item(self.queue_track)

        self.add_item(self.stop_button)
        if hasattr(self.source, "select_options"):
            self.select_view = SpotifySelectOption(self.source.select_options[:25])
            self.add_item(self.select_view)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        if self.message is None:
            return
        if self.clear_buttons_after:
            await self.message.edit(view=None)
        elif self.delete_message_after:
            await self.message.delete()

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            self.author = ctx.user
        else:
            self.author = ctx.author

        self.ctx = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if is_slash:
            self.message = await ctx.followup.send(**kwargs, view=self, wait=True)
        else:
            self.message = await channel.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        if hasattr(self.source, "select_options") and page_number >= 12:
            self.remove_item(self.select_view)
            self.select_view = SpotifySelectOption(
                self.source.select_options[page_number - 12 : page_number + 13]
            )
            self.add_item(self.select_view)
            log.debug(f"changing select {len(self.select_view.options)}")
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        if not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs, view=self)
        else:
            await interaction.followup.edit(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""

        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class SpotifyBaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        clear_buttons_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.author = None
        self.user_token = user_token
        self.cog = cog
        self.message = message
        self.clear_buttons_after = clear_buttons_after
        self.delete_message_after = delete_message_after
        self._source = source
        self.ctx = None
        self.current_page = kwargs.get("page_start", 0)
        if hasattr(self.source, "select_options"):
            self.select_view = SpotifySelectOption(self.source.select_options[:25])
            self.add_item(self.select_view)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        if self.message is None:
            return
        if self.clear_buttons_after:
            await self.message.edit(view=None)
        elif self.delete_message_after:
            await self.message.delete()

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx: commands.Context, channel: discord.TextChannel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            self.author = ctx.user
        else:
            self.author = ctx.author

        self.ctx = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if is_slash:
            await ctx.followup.send(**kwargs, view=self)
            self.message = await ctx.original_message()
        else:
            self.message = await channel.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        if hasattr(self.source, "select_options") and page_number >= 12:
            self.remove_item(self.select_view)
            self.select_view = SpotifySelectOption(
                self.source.select_options[page_number - 12 : page_number + 12]
            )
            self.add_item(self.select_view)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        if not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs, view=self)
        else:
            await interaction.followup.edit(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        style=discord.ButtonStyle.red,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def stop_pages(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """stops the pagination session."""
        self.stop()
        await interaction.message.delete()

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """go to the first page"""
        await self.show_page(0, interaction)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1, interaction)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1, interaction)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1, interaction)
