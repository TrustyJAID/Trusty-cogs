from __future__ import annotations

import asyncio
import discord
import logging
import tekore
from tabulate import tabulate

from typing import Any, List, Tuple

from redbot.vendored.discord.ext import menus
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta, box, pagify

from .helpers import _draw_play, NotPlaying, make_details, REPEAT_STATES

log = logging.getLogger("red.Trusty-cogs.spotify")


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
        em.set_author(
            name=track.name[:256],
            url=url,
        )
        em.description = f"[{artist_title}]({url})\n"
        if track.album.images:
            em.set_thumbnail(url=track.album.images[0].url)
        if self.detailed:
            sp = tekore.Spotify(sender=menu.cog._sender)
            with sp.token_as(menu.user_token):
                details = await sp.track_audio_features(track.id)

            msg = await make_details(track, details)
            em.add_field(name="Details", value=box(msg[:1000], lang="css"))
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        )
        sp = tekore.Spotify(sender=menu.cog._sender)
        with sp.token_as(menu.user_token):
            cur = await sp.artist_top_tracks(artist.id, "from_token")
        msg = "Top Tracks\n"
        for track in cur:
            msg += f"[{track.name}](https://open.spotify.com/{track.id})\n"
        em.description = msg
        if artist.images:
            em.set_thumbnail(url=artist.images[0].url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        )
        msg = "Tracks:\n"
        sp = tekore.Spotify(sender=menu.cog._sender)
        with sp.token_as(menu.user_token):
            cur = await sp.album(album.id)
        for track in cur.tracks.items:
            msg += f"[{track.name}](https://open.spotify.com/{track.id})\n"
        em.description = msg
        if album.images:
            em.set_thumbnail(url=album.images[0].url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        )
        user_spotify = tekore.Spotify(sender=menu.cog._sender)
        description = ""
        with user_spotify.token_as(menu.user_token):
            cur = await user_spotify.playlist_items(playlist.id)
            for track in cur.items[:10]:
                description += (
                    f"[{track.track.name}](https://open.spotify.com/playlist/{track.track.id})\n"
                )

        em.description = description
        if playlist.images:
            em.set_thumbnail(url=playlist.images[0].url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        )
        em.description = f"[{episode.description[:1900]}]({url})\n"
        if episode.images:
            em.set_thumbnail(url=episode.images[0].url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        )
        em.description = f"[{show.description[:1900]}]({url})\n"
        if show.images:
            em.set_thumbnail(url=show.images[0].url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
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
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()} | Played at")
        return em


class SpotifyPlaylistsPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.SimplePlaylist]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, menu: menus.MenuPages, playlists: List[tekore.model.SimplePlaylist]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(name=f"{menu.ctx.author.display_name}'s Spotify Playlists")
        msg = ""
        for playlist in playlists:
            if playlist.public:
                msg += f"[{playlist.name}](https://open.spotify.com/playlist/{playlist.id})\n"
            else:
                msg += f"{playlist.name}\n"
        em.description = msg
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class SpotifyTopTracksPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.FullTrack]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, menu: menus.MenuPages, tracks: List[tekore.model.FullTrack]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(name=f"{menu.ctx.author.display_name}'s Top Tracks")
        msg = ""
        for track in tracks:
            artist = humanize_list([a.name for a in track.artists])
            msg += f"[{track.name} by {artist}](https://open.spotify.com/artist{track.id})\n"
        em.description = msg
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class SpotifyTopArtistsPages(menus.ListPageSource):
    def __init__(self, playlists: List[tekore.model.FullArtist]):
        super().__init__(playlists, per_page=10)

    async def format_page(
        self, menu: menus.MenuPages, artists: List[tekore.model.FullArtist]
    ) -> discord.Embed:
        em = None
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(name=f"{menu.ctx.author.display_name}'s Top Artists")
        msg = ""
        for artist in artists:
            msg += f"[{artist.name}](https://open.spotify.com/artist/{artist.id})\n"
        em.description = msg
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class SpotifyPages(menus.PageSource):
    def __init__(
        self, user_token: tekore.Token, sender: tekore.AsyncSender, detailed: bool
    ) -> discord.Embed:
        super().__init__()
        self.user_token = user_token
        self.sender = sender
        self.detailed = detailed

    async def format_page(
        self,
        menu: menus.MenuPages,
        cur_state: Tuple[tekore.model.CurrentlyPlayingContext, bool],
    ) -> discord.Embed:

        state = cur_state[0]
        is_liked = cur_state[1]
        em = discord.Embed(color=discord.Colour(0x1DB954))

        if state.item.type == "episode":
            url = f"https://open.spotify.com/episode/{state.item.id}"
            artist_title = state.item.name
            image = state.item.images[0].url
        else:
            url = f"https://open.spotify.com/track/{state.item.id}"
            artist_title = f"{state.item.name} by " + ", ".join(a.name for a in state.item.artists)
            image = state.item.album.images[0].url
        album = getattr(state.item, "album", "")
        if album:
            album = f"[{album.name}](https://open.spotify.com/track/{album.id})"
        em.set_author(
            name=f"{menu.ctx.author.display_name} is currently listening to",
            icon_url=menu.ctx.author.avatar_url,
            url=url,
        )
        repeat = (
            f"Repeat: {REPEAT_STATES[state.repeat_state]} |" if state.repeat_state != "off" else ""
        )
        shuffle = "Shuffle: \N{TWISTED RIGHTWARDS ARROWS} |" if state.shuffle_state else ""
        liked = "Liked: \N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}" if is_liked else ""
        footer = f"{repeat}{shuffle}{liked}"
        if footer:
            em.set_footer(text=footer)
        em.description = f"[{artist_title}]({url})\n\n{album}\n{_draw_play(state)}"
        try:
            if self.detailed:
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
        user_spotify = tekore.Spotify(sender=self.sender)
        with user_spotify.token_as(self.user_token):
            cur_state = await user_spotify.playback()
            if not cur_state:
                raise NotPlaying
            song = cur_state.item.id
            liked = await user_spotify.saved_tracks_contains([song])
            is_liked = liked[0]
        return cur_state, is_liked


class SpotifyUserMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.user_token = user_token
        self.cog = cog

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        msg = await channel.send(**kwargs)
        self.cog.current_menus[msg.id] = ctx.author.id
        return msg

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

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id != self._author_id:
            return False
        return payload.emoji in self.buttons

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

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
    )
    async def play_pause(self, payload):
        """go to the previous page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if cur.is_playing:
                    await user_spotify.playback_pause()
                else:
                    await user_spotify.playback_resume()
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await asyncio.sleep(1)
        await self.show_checked_page(0)

    @menus.button(
        "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
    )
    async def repeat(self, payload):
        """go to the next page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if cur.repeat_state == "off":
                    state = "track"
                if cur.repeat_state == "track":
                    state = "context"
                if cur.repeat_state == "context":
                    state = "off"
                await user_spotify.playback_repeat(state)
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await asyncio.sleep(1)
        await self.show_checked_page(0)

        # @menus.button(
        # "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}",
        # )
        # async def repeat_one(self, payload):
        """go to the next page"""
        # await self.show_checked_page(0)

    @menus.button(
        "\N{TWISTED RIGHTWARDS ARROWS}",
    )
    async def shuffle(self, payload):
        """go to the next page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                state = not cur.shuffle_state
                await user_spotify.playback_shuffle(state)
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await asyncio.sleep(1)
        await self.show_checked_page(0)

    @menus.button(
        "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}",
    )
    async def like_song(self, payload):
        """go to the next page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                await user_spotify.saved_tracks_add([self.source.current_track.id])
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await self.show_checked_page(0)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                await user_spotify.playback_previous()
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await asyncio.sleep(1)
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(2),
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                await user_spotify.playback_next()
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await asyncio.sleep(1)
        await self.show_page(0)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        del self.cog.current_menus[self.message.ids]
        await self.message.delete()


class SpotifySearchMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.user_token = user_token
        self.cog = cog

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        msg = await channel.send(**kwargs)
        self.cog.current_menus[msg.id] = ctx.author.id
        return msg

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

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id != self._author_id:
            return False
        return payload.emoji in self.buttons

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

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
    )
    async def play_pause(self, payload):
        """go to the previous page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                cur = await user_spotify.playback()
                if not cur:
                    await ctx.send("I could not find an active device to send requests for.")
                    return
                if cur.item.id == self.source.current_track.id:
                    if cur.is_playing:
                        await user_spotify.playback_pause()
                    else:
                        await user_spotify.playback_resume()
                else:
                    if self.source.current_track.type == "track":
                        await user_spotify.playback_start_tracks([self.source.current_track.id])
                    else:
                        await user_spotify.playback_start_context(self.source.current_track.uri)
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )

    @menus.button(
        "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}",
    )
    async def like_song(self, payload):
        """go to the next page"""
        try:
            user_spotify = tekore.Spotify(sender=self.cog._sender)
            with user_spotify.token_as(self.user_token):
                await user_spotify.saved_tracks_add([self.source.current_track.id])
        except tekore.NotFound:
            await self.ctx.send("I could not find an active device to send requests for.")
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await self.ctx.send("This action is prohibited for non-premium users.")
            else:
                await self.ctx.send("I couldn't perform that action for you.")
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.ctx.send(
                "An exception has occured, please contact the bot owner for more assistance."
            )
        await self.show_checked_page(0)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        del self.cog.current_menus[self.message.id]
        await self.message.delete()


class SpotifyBaseMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        user_token: tekore.Token,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.user_token = user_token
        self.cog = cog

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        msg = await channel.send(**kwargs)
        self.cog.current_menus[msg.id] = ctx.author.id
        return msg

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

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self._author_id):
            return False
        return payload.emoji in self.buttons

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

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        del self.cog.current_menus[self.message.id]
        await self.message.delete()
