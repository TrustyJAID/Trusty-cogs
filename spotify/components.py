from __future__ import annotations

import asyncio
from typing import List, Optional

import discord
import tekore
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list
from redbot.vendored.discord.ext import menus

from .helpers import spotify_emoji_handler

log = getLogger("red.Trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


class SpotifySelectTrack(discord.ui.Select):
    def __init__(
        self,
        tracks: List[tekore.FullTrack],
        cog: commands.Cog,
        user_token: tekore.Token,
        placeholder: str,
        current_track: Optional[tekore.FullTrack],
    ):
        super().__init__(min_values=1, max_values=1, placeholder=placeholder)
        for track in tracks:
            emoji = None
            if current_track and track.id == current_track.id:
                emoji = spotify_emoji_handler.get_emoji("volume_up")
            self.add_option(
                label=track.name[:100],
                description=humanize_list([i.name for i in track.artists])[:100],
                value=track.id,
                emoji=emoji,
            )
        self.cog = cog
        self.user_token = user_token
        self.tracks = {t.id: t for t in tracks}

    async def callback(self, interaction: discord.Interaction):
        track_id = self.values[0]
        track = None
        track = self.tracks.get(track_id, None)
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
                if track is None:
                    track = await user_spotify.track(track_id, market="from_token")
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
        self.emoji = spotify_emoji_handler.get_emoji("playpause")
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
                if cur and cur.item.id == self.view.source.current_track.id:
                    if cur.is_playing:
                        await interaction.response.send_message(
                            _("Pausing Spotify on {device}.").format(device=device.name),
                            ephemeral=True,
                        )
                        await user_spotify.playback_pause(device_id=device_id)
                        self.emoji = spotify_emoji_handler.get_emoji("play")
                    else:
                        await interaction.response.send_message(
                            _("Resuming Spotify playback on {device}.").format(device=device.name),
                            ephemeral=True,
                        )
                        await user_spotify.playback_resume(device_id=device_id)
                        self.emoji = spotify_emoji_handler.get_emoji("pause")
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
        self.emoji = spotify_emoji_handler.get_emoji("previous")
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
        self.emoji = spotify_emoji_handler.get_emoji("next")
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
        self.emoji = spotify_emoji_handler.get_emoji("shuffle")
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
        self.emoji = spotify_emoji_handler.get_emoji("repeat")
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
                    self.emoji = spotify_emoji_handler.get_emoji("repeat")
                    state = "context"
                if cur.repeat_state == "context":
                    self.style = discord.ButtonStyle.primary
                    self.emoji = spotify_emoji_handler.get_emoji("repeatone")
                    state = "track"
                if cur.repeat_state == "track":
                    self.style = discord.ButtonStyle.grey
                    self.emoji = spotify_emoji_handler.get_emoji("repeat")
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
        await asyncio.sleep(1)
        page = getattr(self.view, "current_page", 0)
        await self.view.show_checked_page(page, interaction)


class VolumeModal(discord.ui.Modal):
    def __init__(
        self,
        cog: commands.Cog,
        button: discord.ui.Button,
        user_token: tekore.Token,
        cur_volume: Optional[int],
    ):
        super().__init__(title="Volume")
        self.text = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Volume",
            placeholder="0-100",
            default=str(cur_volume),
            min_length=1,
            max_length=3,
        )
        self.add_item(self.text)
        self.og_button = button
        self.user_token = user_token
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        volume = max(min(100, int(self.text.value)), 0)  # constrains volume to be within 100
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
                        return await self.cog.no_device(interaction)
                else:
                    device = cur.device
                await user_spotify.playback_volume(volume)
                if volume == 0:
                    emoji = spotify_emoji_handler.get_emoji("volume_mute", True)
                elif cur and volume in range(1, 50):
                    emoji = spotify_emoji_handler.get_emoji("volume_down", True)
                else:
                    emoji = spotify_emoji_handler.get_emoji(
                        "volume_up",
                        True,
                    )
            self.og_button.emoji = emoji

            await interaction.response.send_message(
                _("Setting {device}'s volume to {volume}.").format(
                    volume=volume, device=device.name
                ),
                ephemeral=True,
            )
            await self.og_button.view.show_checked_page(0, interaction)

        except tekore.Unauthorised:
            await self.cog.not_authorized(interaction)
        except tekore.NotFound:
            await self.cog.no_device(interaction)
        except tekore.Forbidden as e:
            await self.cog.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.cog.unknown_error(interaction)


class VolumeButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
        cog: commands.Cog,
        source: menus.PageSource,
        user_token: tekore.Token,
    ):
        super().__init__(style=style, row=row)
        self.source = source
        volume = getattr(self.source, "cur_volume", 1)
        if volume == 0:
            self.emoji = spotify_emoji_handler.get_emoji("volume_mute")
        elif volume in range(1, 50):
            self.emoji = spotify_emoji_handler.get_emoji("volume_down")
        else:
            self.emoji = spotify_emoji_handler.get_emoji("volume_up")
        self.cog = cog

        self.user_token = user_token
        self.disabled = False

    async def callback(self, interaction: discord.Interaction):
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
                    return await self.cog.no_device(interaction)
            else:
                device = cur.device
        cur_volume = None
        if cur:
            cur_volume = cur.device.volume_percent
        modal = VolumeModal(self.cog, self, self.user_token, cur_volume)
        await interaction.response.send_modal(modal)


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
        self.emoji = spotify_emoji_handler.get_emoji("playall")
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
        self.emoji = spotify_emoji_handler.get_emoji("queue")
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
        self.view.stop()
        log.verbose("StopButton flags: %s", interaction.message.flags)
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = spotify_emoji_handler.get_emoji("forward_right")

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
        self.emoji = spotify_emoji_handler.get_emoji("back_left")

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
        self.emoji = spotify_emoji_handler.get_emoji("next")

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
        self.emoji = spotify_emoji_handler.get_emoji("previous")

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class SpotifySelectOption(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        await self.view.show_checked_page(index, interaction)


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
        self.device_id = self.values[0]
        if not self.send_callback:
            await interaction.response.edit_message(view=None)
            self.view.stop()
            return
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(self.user_token):
            now = await user_spotify.playback()
            await user_spotify.playback_transfer(self.values[0], now.is_playing)
