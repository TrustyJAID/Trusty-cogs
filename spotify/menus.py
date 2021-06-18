from __future__ import annotations

import asyncio
import json
import logging
from copy import copy
from pathlib import Path
from typing import Any, List, Tuple, Optional

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

    def get_emoji(self, name: str, use_external: bool = True) -> str:
        if use_external and name in self.emojis:
            return self.emojis[name]
        return self.default[name]
        # we shouldn't have anyone deleting emoji keys

    def reload_emojis(self):
        # we could just copy default but we can also just
        # reload the emojis from disk
        with open(Path(__file__).parent / "emojis.json", "r", encoding="utf8") as infile:
            self.emojis = json.loads(infile.read())

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

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: menus.MenuPages, track: tekore.model.FullTrack
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
            sp = tekore.Spotify(sender=menu.cog._sender)
            with sp.token_as(menu.user_token):
                details = await sp.track_audio_features(track.id)

            msg = await make_details(track, details)
            em.add_field(name="Details", value=box(msg[:1000], lang="css"))
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyArtistPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullArtist], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: menus.MenuPages, artist: tekore.model.FullArtist
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
        sp = tekore.Spotify(sender=menu.cog._sender)
        with sp.token_as(menu.user_token):
            cur = await sp.artist_top_tracks(artist.id, "from_token")
        msg = _("Top Tracks\n")
        for track in cur:
            msg += f"[{track.name}](https://open.spotify.com/track/{track.id})\n"
        em.description = msg
        if artist.images:
            em.set_thumbnail(url=artist.images[0].url)
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyAlbumPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.FullAlbum], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: menus.MenuPages, album: tekore.model.FullAlbum
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
        sp = tekore.Spotify(sender=menu.cog._sender)
        with sp.token_as(menu.user_token):
            cur = await sp.album(album.id)
        for track in cur.tracks.items:
            msg += f"[{track.name}](https://open.spotify.com/track/{track.id})\n"
        em.description = msg
        if album.images:
            em.set_thumbnail(url=album.images[0].url)
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyPlaylistPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.SimplePlaylist], detailed: bool):
        super().__init__(items, per_page=1)
        self.current_track = None

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: menus.MenuPages, playlist: tekore.model.SimplePlaylist
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
        user_spotify = tekore.Spotify(sender=menu.cog._sender)
        description = ""
        with user_spotify.token_as(menu.user_token):
            cur = await user_spotify.playlist_items(playlist.id)
            for track in cur.items[:10]:
                description += (
                    f"[{track.track.name}](https://open.spotify.com/track/{track.track.id})\n"
                )

        em.description = description
        if playlist.images:
            em.set_thumbnail(url=playlist.images[0].url)
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyNewPages(menus.ListPageSource):
    def __init__(self, items: List[tekore.model.SimplePlaylist]):
        super().__init__(items, per_page=1)
        self.current_track = None

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: menus.MenuPages, playlist: tekore.model.SimplePlaylist
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
        user_spotify = tekore.Spotify(sender=menu.cog._sender)
        description = ""
        with user_spotify.token_as(menu.user_token):
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
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
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
        self, menu: menus.MenuPages, episode: tekore.model.FullEpisode
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
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
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
        self, menu: menus.MenuPages, show: tekore.model.FullShow
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
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
        )
        return em


class SpotifyRecentSongPages(menus.ListPageSource):
    def __init__(self, tracks: List[tekore.model.PlayHistory], detailed: bool):
        super().__init__(tracks, per_page=1)
        self.current_track = None
        self.detailed = detailed

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: menus.MenuPages, history: tekore.model.PlayHistory
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
            sp = tekore.Spotify(sender=menu.cog._sender)
            with sp.token_as(menu.user_token):
                details = await sp.track_audio_features(history.track.id)

            msg = await make_details(track, details)
            em.add_field(name="Details", value=box(msg[:1000], lang="css"))
        em.set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages()} | Played at",
        )
        return em


class SpotifyPlaylistsPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.SimplePlaylist]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, menu: menus.MenuPages, playlists: List[tekore.model.SimplePlaylist]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=_("{user}'s Spotify Playlists").format(user=menu.ctx.author.display_name),
            icon_url=menu.ctx.author.avatar.url,
        )
        msg = ""
        for playlist in playlists:
            if playlist.public:
                msg += f"[{playlist.name}](https://open.spotify.com/playlist/{playlist.id})\n"
            else:
                msg += f"{playlist.name}\n"
        em.description = msg
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
            icon_url=SPOTIFY_LOGO,
        )
        return em


class SpotifyTopTracksPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.FullTrack]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, menu: menus.MenuPages, tracks: List[tekore.model.FullTrack]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=_("{user}'s Top Tracks").format(user=menu.ctx.author.display_name),
            icon_url=menu.ctx.author.avatar.url,
        )
        msg = ""
        for track in tracks:
            artist = humanize_list([a.name for a in track.artists])
            msg += f"[{track.name} by {artist}](https://open.spotify.com/track/{track.id})\n"
        em.description = msg
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
            icon_url=SPOTIFY_LOGO,
        )
        return em


class SpotifyTopArtistsPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.FullArtist]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, menu: menus.MenuPages, artists: List[tekore.model.FullArtist]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=_("{user}'s Top Artists").format(user=menu.ctx.author.display_name),
            icon_url=menu.ctx.author.avatar.url,
        )
        msg = ""
        for artist in artists:
            msg += f"[{artist.name}](https://open.spotify.com/artist/{artist.id})\n"
        em.description = msg
        em.set_footer(
            text=_("Page") + f" {menu.current_page + 1}/{self.get_max_pages()}",
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

    async def format_page(
        self,
        menu: menus.MenuPages,
        cur_state: Tuple[tekore.model.CurrentlyPlayingContext, bool],
    ) -> discord.Embed:

        state = cur_state[0]
        is_liked = cur_state[1]
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
            name=f"{menu.ctx.author.display_name}" + _(" is currently listening to"),
            icon_url=menu.ctx.author.avatar.url,
            url=url,
        )
        repeat = (
            f"Repeat: {REPEAT_STATES[state.repeat_state]} |" if state.repeat_state != "off" else ""
        )
        shuffle = "Shuffle: \N{TWISTED RIGHTWARDS ARROWS} |" if state.shuffle_state else ""
        liked = "Liked: \N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}" if is_liked else ""
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
        except tekore.Unauthorised:
            raise
        return cur_state, is_liked


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
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await interaction.response.send_message(
                        _("I could not find an active device to play songs on."), ephemeral=True
                    )
                    return
                if cur.item.id == self.source.current_track.id:
                    if cur.is_playing:
                        await user_spotify.playback_pause()
                        self.emoji = emoji_handler.get_emoji("play")
                    else:
                        await user_spotify.playback_resume()
                        self.emoji = emoji_handler.get_emoji("pause")
                else:
                    if self.source.current_track.type == "track":
                        await user_spotify.playback_start_tracks([self.source.current_track.id])
                    else:
                        await user_spotify.playback_start_context(self.source.current_track.uri)
        except tekore.Unauthorised:
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token, sender=self.cog._sender, detailed=self.source.detailed
            )
        await asyncio.sleep(1)
        await self.view.show_checked_page(0)


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
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token, sender=self.cog._sender, detailed=self.source.detailed
            )
        await asyncio.sleep(1)
        await self.view.show_checked_page(0)


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
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token, sender=self.cog._sender, detailed=self.source.detailed
            )
        await asyncio.sleep(1)
        await self.view.show_checked_page(0)


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
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await interaction.response.send_message(
                        _("I could not find an active device to play songs on."), ephemeral=True
                    )
                state = not cur.shuffle_state
                if state:
                    self.style = discord.ButtonStyle.primary
                else:
                    self.style = discord.ButtonStyle.grey
                await user_spotify.playback_shuffle(state)
        except tekore.Unauthorised:
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token, sender=self.cog._sender, detailed=self.source.detailed
            )
        await asyncio.sleep(1)
        await self.view.show_checked_page(0)


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
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token, sender=self.cog._sender, detailed=self.source.detailed
            )
        await asyncio.sleep(1)
        await self.view.show_checked_page(0)


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
        self.emoji = emoji_handler.get_emoji("like")
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
                    await interaction.response.send_message(
                        _("I could not find an active device to play songs on."), ephemeral=True
                    )
                await user_spotify.saved_tracks_add([self.source.current_track.id])
                self.disabled = True
        except tekore.Unauthorised:
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )
        if isinstance(self.source, SpotifyTrackPages):
            self.source = SpotifyPages(
                user_token=self.user_token, sender=self.cog._sender, detailed=self.source.detailed
            )
        await self.view.show_checked_page(0)


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
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    # await interaction.response.send_message(_("I could not find an active device to play songs on."), ephemeral=True)
                    await interaction.response.send_message(
                        _("I could not find an active device to play songs on."), ephemeral=True
                    )
                    return
                else:
                    if self.source.current_track.type == "track":
                        await user_spotify.playback_start_tracks(
                            [i.id for i in self.source.entries]
                        )
                    else:
                        await user_spotify.playback_start_context(self.source.current_track.uri)
                    await interaction.response.send_message(
                        _("Now playing all songs."), ephemeral=True
                    )
        except tekore.Unauthorised:
            await interaction.response.send_message.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )


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
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await interaction.response.send_message(
                        _("I could not find an active device to play songs on."), ephemeral=True
                    )
                    return
                else:
                    if self.source.current_track.type == "track":
                        await user_spotify.playback_queue_add(self.source.current_track.uri)
                        await interaction.response.send_message(
                            _("{track} by {artist} has been added to your queue.").format(
                                track=self.source.current_track.name,
                                artist=humanize_list(
                                    [i.name for i in self.source.current_track.artists]
                                ),
                            ),
                            ephemeral=True,
                        )
                    else:
                        await user_spotify.playback_start_context(self.source.current_track.uri)
        except tekore.Unauthorised:
            await interaction.response.send_message(
                _("I am not authorized to perform this action for you.")
            )
        except tekore.NotFound:
            await interaction.response.send_message(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.response.send_message(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.response.send_message(
                _("An exception has occured, please contact the bot owner for more assistance."),
                ephemeral=True,
            )


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
        self.view.stop()
        if self.view.message.id in self.view.cog.current_menus:
            del self.view.cog.current_menus[self.view.message.id]
        if self.view.ctx.author.id in self.view.cog.user_menus:
            del self.view.cog.user_menus[self.view.ctx.author.id]
        await self.view.message.delete()


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
        await self.view.show_checked_page(self.view.current_page + 1)


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
        await self.view.show_checked_page(self.view.current_page - 1)


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
        await self.view.show_page(self.view._source.get_max_pages() - 1)


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
        await self.view.show_page(0)


class SpotifyUserMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        use_external: bool,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.message = message
        self._source = source
        self.user_token = user_token
        self.cog = cog
        self.use_external = use_external
        self.ctx = kwargs.get("ctx", None)
        self._running = True
        self.loop = self.ctx.bot.loop.create_task(self.edit_menu_page_auto())
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

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        self._running = False
        self.loop.cancel()
        del self.cog.user_menus[self.ctx.author.id]

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
        while self._running:
            await asyncio.sleep(15)
            user_spotify = tekore.Spotify(sender=self.source.sender)
            with user_spotify.token_as(self.source.user_token):
                cur_state = await user_spotify.playback()
                if not cur_state and not cur_state.item:
                    continue
                if cur_state.item.id != self.source.current_track.id:
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
        if self.ctx is None:
            self.ctx = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if self.source.repeat_state == "track":
            self.repeat_button.emoji = REPEAT_STATES[self.source.repeat_state]
            self.repeat_button.style = discord.ButtonStyle.primary
        if self.source.repeat_state == "context":
            self.repeat_button.emoji = REPEAT_STATES[self.source.repeat_state]
            self.repeat_button.style = discord.ButtonStyle.primary
        log.debug(f"initial message before {self.like_button.disabled}")
        if self.source.is_liked:
            self.like_button.disabled = True
        if not self.source.is_liked:
            self.like_button.disabled = False
        log.debug(f"initial message after {self.like_button.disabled}")
        if self.source.is_playing:
            self.play_pause_button.emoji = emoji_handler.get_emoji("pause")
        if not self.source.is_playing:
            self.play_pause_button.emoji = emoji_handler.get_emoji("play")

        self.message = await channel.send(**kwargs, view=self)
        self.cog.current_menus[self.message.id] = ctx.author.id
        self.cog.user_menus[ctx.author.id] = self.message.jump_url
        return self.message

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        log.debug(f"edited message before {self.like_button.disabled}")
        if self._source.is_liked:
            self.like_button.disabled = True
        if not self._source.is_liked:
            self.like_button.disabled = False
        log.debug(f"edited message after {self.like_button.disabled}")
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs, view=self)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def on_error(self, error, button: discord.ui.Button, interaction: discord.Interaction):
        log.debug(f"{error=} {button=} {interaction=}")

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        log.debug("Checking interaction")
        if interaction.message.id != self.message.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class SpotifySearchMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        use_external: bool,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self._source = source
        self.message = message
        self.user_token = user_token
        self.use_external = use_external
        self.cog = cog
        self.ctx = None
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
        self.like_button = LikeButton(discord.ButtonStyle.grey, 1, cog, source, user_token)
        self.stop_button = StopButton(discord.ButtonStyle.red, 1)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.play_pause_button)
        self.add_item(self.play_all)
        self.add_item(self.queue_track)

        self.add_item(self.like_button)
        self.add_item(self.stop_button)

    @property
    def source(self):
        return self._source

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
        self.ctx = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await channel.send(**kwargs, view=self)
        self.cog.current_menus[self.message.id] = ctx.author.id
        return self.message

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.message.id != self.message.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id != self.ctx.author.id:
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
        use_external: bool,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.user_token = user_token
        self.cog = cog
        self.message = message
        self._source = source
        self.ctx = None
        self.current_page = kwargs.get("page_start", 0)

    @property
    def source(self):
        return self._source

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
        self.ctx = ctx
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await channel.send(**kwargs, view=self)
        self.cog.current_menus[self.message.id] = ctx.author.id
        return self.message

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.message.id != self.message.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id not in (*self.bot.owner_ids, self._author_id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_first_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the first page"""
        await self.show_page(0)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_previous_page(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_next_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the next page"""
        log.debug(f"Changing to page {self.current_page + 1}")
        await self.show_checked_page(self.current_page + 1)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_last_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @discord.ui.button(style=discord.ButtonStyle.red, emoji="\N{CROSS MARK}", row=1)
    async def stop_pages(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """stops the pagination session."""
        self.stop()
        del self.cog.current_menus[self.message.id]
        await self.message.delete()
