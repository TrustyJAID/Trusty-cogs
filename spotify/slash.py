import logging
import re

from typing import Optional, Literal

import discord
import tekore
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .helpers import SPOTIFY_RE, song_embed

log = logging.getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


class SpotifySlash:

    spotify = app_commands.Group(
        name="spotify", description="Display information from Spotify's API"
    )
    artist = app_commands.Group(
        name="artist", description="View Spotify Artist info", parent=spotify
    )
    playlist = app_commands.Group(
        name="playlist", description="View Spotify Playlists", parent=spotify
    )
    device = app_commands.Group(
        name="device", description="Spotify Device commands", parent=spotify
    )
    spotify.add_command(artist)
    spotify.add_command(playlist)
    spotify.add_command(device)

    KEY_CHOICES = [
        app_commands.Choice(name="C (also B♯, Ddouble flat)", value=0),
        app_commands.Choice(name="C♯, D♭ (also Bdouble sharp)", value=1),
        app_commands.Choice(name="D (also Cdouble sharp, Edouble flat)", value=2),
        app_commands.Choice(name="D♯, E♭ (also Fdouble flat)", value=3),
        app_commands.Choice(name="E (also Ddouble sharp, F♭)", value=4),
        app_commands.Choice(name="F (also E♯, Gdouble flat)", value=5),
        app_commands.Choice(name="F♯, G♭ (also Edouble sharp)", value=6),
        app_commands.Choice(name="G (also Fdouble sharp, Adouble flat)", value=7),
        app_commands.Choice(name="G♯, A♭", value=8),
        app_commands.Choice(name="A (also Gdouble sharp, Bdouble flat)", value=9),
        app_commands.Choice(name="A♯, B♭ (also Cdouble flat)", value=10),
        app_commands.Choice(name="B (also Adouble sharp, C♭)", value=11),
    ]
    MODE_CHOICES = [
        app_commands.Choice(name="major", value=1),
        app_commands.Choice(name="minor", value=0),
    ]

    @spotify.command(name="now", description="Displays your currently played spotify song")
    async def spotify_now_slash(
        self,
        ctx: discord.Interaction,
        detailed: Optional[bool] = False,
        member: Optional[discord.Member] = None,
        public: bool = True,
    ):
        """Displays your currently played spotify song"""
        await self.spotify_now(ctx, detailed, member, public)

    @spotify.command(name="recommendations", description="Get Spotify Recommendations")
    @app_commands.choices(
        key=KEY_CHOICES,
        mode=MODE_CHOICES,
    )
    @app_commands.describe(
        genres="Must be any combination of valid genres",
        tracks="Any Spotify track URL used as the seed.",
        artists="Any Spotify artist URL used as the seed.",
        acousticness="A value from 0 to 100 the target acousticness of the tracks.",
        danceability="A value from 0 to 100 describing how danceable the tracks are.",
        energy="Energy is a measure from 0 to 100 and represents a perceptual measure of intensity and activity",
        instrumentalness="A value from 0 to 100 representing whether or not a track contains vocals.",
        key="The target key of the tracks.",
        liveness="A value from 0-100 representing the presence of an audience in the recording.",
        loudness="The overall loudness of a track in decibels (dB) between -60 and 0 db.",
        mode="The target modality (major or minor) of the track.",
        popularity="A value from 0-100 the target popularity of the tracks.",
        speechiness="A value from 0-100 Speechiness is the presence of spoken words in a track.",
        tempo="The overall estimated tempo of a track in beats per minute (BPM).",
        time_signature="The time signature ranges from 3 to 7 indicating time signatures of '3/4', to '7/4'.",
        valence="A measure from 0 to 100 describing the musical positiveness conveyed by a track",
    )
    async def spotify_recommendations_slash(
        self,
        interaction: discord.Interaction,
        genres: str,
        tracks: Optional[str],
        artists: Optional[str],
        acousticness: Optional[app_commands.Range[int, 0, 100]],
        danceability: Optional[app_commands.Range[int, 0, 100]],
        energy: Optional[app_commands.Range[int, 0, 100]],
        instrumentalness: Optional[app_commands.Range[int, 0, 100]],
        key: Optional[app_commands.Choice[int]],
        liveness: Optional[app_commands.Range[int, 0, 100]],
        loudness: Optional[app_commands.Range[int, 0, 100]],
        mode: Optional[app_commands.Choice[int]],
        popularity: Optional[app_commands.Range[int, 0, 100]],
        speechiness: Optional[app_commands.Range[int, 0, 100]],
        tempo: Optional[int],
        time_signature: Optional[int],
        valence: Optional[app_commands.Range[int, 0, 100]],
        detailed: Optional[bool],
    ):
        """Get Spotify Recommendations"""
        recs = {
            "genres": [g for g in genres.split(" ")],
            "track_ids": tracks,
            "artist_ids": artists,
            "limit": 100,
            "market": "from_token",
            "target_acousticness": acousticness,
            "target_danceability": danceability,
            "target_energy": energy,
            "target_instrumentalness": instrumentalness,
            "target_key": key.value if key else None,
            "target_liveness": liveness,
            "target_loudness": loudness,
            "target_mode": mode.value if mode else None,
            "target_popularity": popularity,
            "target_speechiness": speechiness,
            "target_tempo": tempo,
            "target_time_signature": time_signature,
            "target_valence": valence,
        }
        await self.spotify_recommendations(interaction, detailed, recommendations=recs)

    @spotify_recommendations_slash.autocomplete("genres")
    async def genres_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        namespace: app_commands.Namespace,
    ):
        supplied_genres = ""
        new_genre = ""
        for sup in current.split(" "):
            if sup in self.GENRES:
                supplied_genres += f"{sup} "
            else:
                new_genre = sup

        ret = [
            app_commands.Choice(name=f"{supplied_genres} {g}", value=f"{supplied_genres} {g}")
            # {"name": f"{supplied_genres} {g}", "value": f"{supplied_genres} {g}"}
            for g in self.GENRES
            if new_genre in g
        ]
        if supplied_genres:
            # ret.insert(0, {"name": supplied_genres, "value": supplied_genres})
            ret.insert(0, app_commands.Choice(name=supplied_genres, value=supplied_genres))
        return ret[:25]

    @device.command(name="transfer")
    async def spotify_device_transfer_slash(
        self, interaction: discord.Interaction, device_name: str
    ):
        """Change the currently playing spotify device"""
        await self.spotify_device_transfer(interaction, device_name=device_name)

    @device.command(name="default")
    async def spotify_device_default_slash(
        self, interaction: discord.Interaction, device_name: str
    ):
        """
        Set your default device to attempt to start playing new tracks on
        if you aren't currently listening to Spotify.
        """
        await self.spotify_device_default(interaction, device_name)

    @device.command(name="list")
    async def spotify_device_list_slash(self, interaction: discord.Interaction):
        """List all available devices for Spotify"""
        await self.spotify_device_list(interaction)

    @spotify_device_transfer_slash.autocomplete("device_name")
    @spotify_device_default_slash.autocomplete("device_name")
    async def device_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        namespace: app_commands.Namespace,
    ):
        if not await self.config.user(interaction.user).token():
            # really don't want to force users to auth from autocomplete
            log.debug("No tokens.")
            return
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            log.debug("STILL No tokens.")
            return
        if interaction.user.id not in self._temp_user_devices:
            try:
                user_devices = []
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    devices = await user_spotify.playback_devices()
                for d in devices:
                    # user_devices.append({"name": d.name, "value": d.id})
                    user_devices.append(app_commands.Choice(name=d.name, value=d.id))
                self._temp_user_devices[interaction.user.id] = user_devices
            except Exception:
                log.exception("uhhhhhh")
                return

        choices = [
            i for i in self._temp_user_devices[interaction.user.id] if current in i.name.lower()
        ]
        return choices[:25]

    @spotify.command(name="forgetme")
    async def spotify_forgetme_slash(self, interaction: discord.Interaction):
        """Forget all your spotify settings and credentials on the bot"""
        await self.spotify_forgetme(interaction)

    @spotify.command(name="me")
    async def spotify_me_slash(self, interaction: discord.Interaction):
        """Shows your current Spotify Settings"""
        await self.spotify_me(interaction)

    @spotify.command(name="genres")
    async def spotify_genres_slash(self, interaction: discord.Interaction):
        """Display all available genres for recommendations"""
        await self.spotify_genres(interaction)

    @spotify.command(name="recent")
    async def spotify_recently_played_slash(
        self, interaction: discord.Interaction, detailed: Optional[bool]
    ):
        """Display your most recently played songs on Spotify"""
        await self.spotify_recently_played(interaction, detailed)

    @spotify.command(name="toptracks")
    async def top_tracks_slash(self, interaction: discord.Interaction):
        """List your top tracks on Spotify"""
        await self.top_tracks(interaction)

    @spotify.command(name="topartists")
    async def top_artsist_slash(self, interaction: discord.Interaction):
        """List your top artists on Spotify"""
        await self.top_artists(interaction)

    @spotify.command(name="new")
    async def spotify_new_slash(self, interaction: discord.Interaction):
        """List new releases on Spotify"""
        await self.spotify_new(interaction)

    @spotify.command(name="pause")
    async def spotify_pause_slash(self, interaction: discord.Interaction):
        """Pauses Spotify for you"""
        await self.spotify_pause(interaction)

    @spotify.command(name="resume")
    async def spotify_resume_slash(self, interaction: discord.Interaction):
        """Resumes Spotify for you"""
        await self.spotify_resume(interaction)

    @spotify.command(name="next")
    async def spotify_next_slash(self, interaction: discord.Interaction):
        """Skips to the next track in queue on Spotify"""
        await self.spotify_next(interaction)

    @spotify.command(name="previous")
    async def spotify_previous_slash(self, interaction: discord.Interaction):
        """Skip to the previous track in queue on Spotify"""
        await self.spotify_previous(interaction)

    @spotify.command(name="play")
    async def spotify_play_slash(
        self, interaction: discord.Interaction, url_or_playlist_name: Optional[str]
    ):
        """Play a track, playlist, or album on Spotify"""
        await self.spotify_play(interaction, url_or_playlist_name)

    @spotify.command(name="queue")
    async def spotify_queue_add_slash(self, interaction: discord.Interaction, songs: str):
        """Queue a song to play next on Spotify"""
        await self.spotify_queue_add(interaction, songs=songs)

    @spotify.command(name="repeat")
    async def spotify_repeat_slash(
        self, interaction: discord.Interaction, state: Optional[Literal["off", "track", "context"]]
    ):
        """Set your Spotify players repeat state"""
        await self.spotify_repeat(interaction, state)

    @spotify.command(name="shuffle")
    async def spotify_shuffle_slash(self, interaction: discord.Interaction, state: Optional[bool]):
        """Set your Spotify players shuffle state"""
        await self.spotify_shuffle(interaction, state)

    @spotify.command(name="seek")
    @app_commands.describe(seconds="Seconds or a value formatted like 00:00:00 (hh:mm:ss)")
    async def spotify_seek_slash(self, interaction: discord.Interaction, seconds: str):
        """Seek to a specific point in the current song."""
        await self.spotify_seek(interaction, seconds)

    @spotify.command(name="volume")
    async def spotify_volume_slash(
        self, interaction: discord.Interaction, volume: app_commands.Range[int, 0, 100]
    ):
        """Set your Spotify players volume percentage"""
        await self.spotify_volume(interaction, volume)

    @playlist.command(name="featured")
    async def spotify_playlist_featured_slash(self, interaction: discord.Interaction):
        """List your Spotify featured Playlists"""
        await self.spotify_playlist_featured(interaction)

    @playlist.command(name="list")
    async def spotify_playlist_list_slash(self, interaction: discord.Interaction):
        """List your Spotify Playlists"""
        await self.spotify_playlist_list(interaction)

    @playlist.command(name="view")
    async def spotify_playlist_view_slash(self, interaction: discord.Interaction):
        """View details about your Spotify playlists"""
        await self.spotify_playlist_view(interaction)

    @playlist.command(name="create")
    async def spotify_playlist_create_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        public: Optional[bool] = False,
        description: Optional[str] = "",
    ):
        """Create a Spotify Playlist"""
        await self.spotify_playlist_create(interaction, name, public, description=description)

    @playlist.command(name="add")
    async def spotify_playlist_add_slash(
        self, interaction: discord.Interaction, name: str, to_add: str
    ):
        """Add a track to a Spotify Playlist"""
        await self.spotify_playlist_add(interaction, name, to_add=to_add)

    @playlist.command(name="remove")
    async def spotify_playlist_remove_slash(
        self, interaction: discord.Interaction, name: str, to_remove: str
    ):
        """Add a track to a Spotify Playlist"""
        await self.spotify_playlist_add(interaction, name, to_remove=to_remove)

    @playlist.command(name="follow")
    async def spotify_playlist_follow_slash(
        self, interaction: discord.Interaction, to_follow: str, public: Optional[bool] = False
    ):
        """Add a playlist to your Spotify library"""
        await self.spotify_playlist_follow(interaction, public, to_follow=to_follow)

    @artist.command(name="follow")
    async def spotify_artist_follow_slash(self, interaction: discord.Interaction, to_follow: str):
        """Add an artist to your Spotify Library"""
        await self.spotify_artist_follow(interaction, to_follow=to_follow)

    @artist.command(name="albums")
    async def spotify_artist_albums_slash(self, interaction: discord.Interaction, to_follow: str):
        """View an artists albums on Spotify"""
        await self.spotify_artist_albums(interaction, to_follow=to_follow)

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
        guild = interaction.guild
        if guild and guild.id in self.slash_commands["guilds"]:
            if interaction_id in self.slash_commands["guilds"][interaction.guild.id]:
                if await self.pre_check_slash(interaction):
                    await self.slash_commands["guilds"][interaction.guild.id][interaction_id](
                        interaction
                    )
        if interaction_id in self.slash_commands:
            if await self.pre_check_slash(interaction):
                await self.slash_commands[interaction_id](interaction)

    async def queue_from_message(self, interaction: discord.Interaction, message: discord.Message):
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
        if song_data:
            for match in song_data:
                if match.group(2) == "track":
                    tracks.append(match.group(3))

        user_spotify = tekore.Spotify(sender=self._sender)
        # play the song if it exists

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
                        await self.no_device(interaction)
                        return
                else:
                    device = cur.device
                if tracks:
                    all_tracks = await user_spotify.tracks(tracks)
                    await user_spotify.playback_queue_add(all_tracks[0].uri, device_id=device.id)
                    track = all_tracks[0]
                    track_name = track.name
                    artists = getattr(track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    track_artist = humanize_list([a.name for a in artists])
                    em = await song_embed(track, False)
                    await interaction.response.send_message(
                        _("Queueing {track} by {artist} on {device}.").format(
                            track=track_name, artist=artist, device=device.name
                        ),
                        embed=em,
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
                        await user_spotify.playback_queue_add(tracks[0].id)
                        em = await song_embed(tracks[0], False)
                        await interaction.response.send_message(
                            _("Queueing {track} by {artist} on {device}.").format(
                                track=track_name, artist=track_artist, device=device.name
                            ),
                            embed=em,
                            ephemeral=True,
                        )
                else:
                    await interaction.response.send_message(
                        _("No Spotify track could be found on that message."), ephemeral=True
                    )
        except tekore.Unauthorised:
            await self.not_authorized(interaction)
        except tekore.NotFound:
            await self.no_device(interaction)
        except tekore.Forbidden as e:
            await self.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(interaction)

    async def play_from_message(self, interaction: discord.Interaction, message: discord.Message):
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
                cur = await user_spotify.playback()
                if not cur:
                    device_id = await self.config.user(user).default_device()
                    devices = await user_spotify.playback_devices()
                    device = None
                    for d in devices:
                        if d.id == device_id:
                            device = d
                    if device is None:
                        await self.no_device(interaction)
                        return
                else:
                    device = cur.device

                if tracks:
                    await user_spotify.playback_start_tracks(tracks, device_id=device.id)
                    all_tracks = await user_spotify.tracks(tracks)
                    track = all_tracks[0]
                    track_name = track.name
                    artists = getattr(track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    track_artist = humanize_list([a.name for a in artists])
                    em = await song_embed(track, False)
                    await interaction.response.send_message(
                        _("Now playing {track} by {artist} on {device}.").format(
                            track=track_name, artist=artist, device=device.name
                        ),
                        embed=em,
                        ephemeral=True,
                    )
                    return
                elif new_uri:
                    log.debug("new uri is %s", new_uri)
                    await user_spotify.playback_start_context(new_uri, device_id=device.id)
                    if uri_type == "playlist":
                        playlist_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.playlist(playlist_id)
                        track_name = cur_tracks.name
                        await interaction.response.send_message(
                            _("Now playing {track} on {device}.").format(
                                track=track_name, device=device.name
                            ),
                            ephemeral=True,
                        )
                    if uri_type == "artist":
                        artist_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.artist(artist_id)
                        track_name = cur_tracks.name
                        await interaction.response.send_message(
                            _("Now playing top tracks by {track} on {device}.").format(
                                track=track_name, device=device.name
                            ),
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
                            _("Now playing {track} by {artist} on {device}.").format(
                                track=track_name, artist=track_artist, device=device.name
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
                    log.debug(query)
                    search = await user_spotify.search(query, ("track",), "from_token", limit=50)
                    # log.debug(search)
                    tracks = search[0].items
                    if tracks:
                        track_name = tracks[0].name
                        track_artist = humanize_list(tracks[0].artists)
                        await user_spotify.playback_start_tracks(
                            [t.id for t in tracks], device_id=device.id
                        )
                        em = await song_embed(tracks[0], False)
                        await interaction.response.send_message(
                            _("Now playing {track} by {artist} on {device}.").format(
                                track=track_name, artist=track_artist, device=device.name
                            ),
                            embed=em,
                            ephemeral=True,
                        )
                    else:
                        await interaction.response.send_message(
                            _("No Spotify track could be found on that message."), ephemeral=True
                        )
                else:
                    await interaction.response.send_message(
                        _("No Spotify track could be found on that message."), ephemeral=True
                    )
        except tekore.Unauthorised:
            await self.not_authorized(interaction)
        except tekore.NotFound:
            await self.no_device(interaction)
        except tekore.Forbidden as e:
            await self.forbidden_action(interaction, str(e))
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(interaction)

    async def set_genres(self):
        try:
            self.GENRES = await self._spotify_client.recommendation_genre_seeds()
        except Exception:
            log.exception("Error grabbing genres.")

    async def check_requires(self, func, interaction) -> bool:
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        fake_ctx.bot = self.bot
        fake_ctx.cog = self
        fake_ctx.command = func
        fake_ctx.permission_state = commands.requires.PermState.NORMAL

        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        msg = _("You are not authorized to use this command.")
        try:
            resp = await func.requires.verify(fake_ctx)
        except Exception:
            await interaction.response.send_message(msg, ephemeral=True)
            return False
        if not resp:
            await interaction.response.send_message(msg, ephemeral=True)
        return resp
