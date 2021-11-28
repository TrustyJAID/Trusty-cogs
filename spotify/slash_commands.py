import logging
from typing import Optional, Union

import discord
import tekore
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .helpers import (
    SPOTIFY_RE,
    NotPlaying,
    RecommendationsConverter,
    SearchTypes,
    SpotifyURIConverter,
    song_embed,
    time_convert,
)
from .menus import (
    SpotifyAlbumPages,
    SpotifyArtistPages,
    SpotifyBaseMenu,
    SpotifyDeviceView,
    SpotifyEpisodePages,
    SpotifyNewPages,
    SpotifyPages,
    SpotifyPlaylistPages,
    SpotifyPlaylistsPages,
    SpotifyRecentSongPages,
    SpotifySearchMenu,
    SpotifySelectDevice,
    SpotifyShowPages,
    SpotifyTopArtistsPages,
    SpotifyTopTracksPages,
    SpotifyTrackPages,
    SpotifyUserMenu,
    emoji_handler,
)

log = logging.getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


class SpotifySlash:
    async def slash_now(
        self,
        interaction: discord.Interaction,
        detailed: Optional[bool] = False,
    ):
        """
        Displays your currently played spotify song

        `[member]` Optional discord member to show their current spotify status
        if they're displaying it on Discord.
        """
        await interaction.response.defer()
        if interaction.user.id in self.user_menus:
            jump = self.user_menus[interaction.user.id]
            em = discord.Embed(
                description=_(
                    "[You already have a player running here.]({jump})\n"
                    "Please wait for that one to end or cancel it before trying again."
                ).format(jump=jump),
                colour=await self.bot.get_embed_colour(interaction),
            )
            await interaction.followup.send(embed=em, ephemeral=True)
            return
        user_token = await self.get_user_auth(interaction, interaction.user)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )

        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        try:
            page_source = SpotifyPages(
                user_token=user_token, sender=self._sender, detailed=detailed
            )
            x = SpotifyUserMenu(
                source=page_source,
                delete_message_after=delete_after,
                clear_reactions_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
                use_external=interaction.channel.permissions_for(
                    interaction.guild.me
                ).use_external_emojis,
                interaction=interaction,
            )
            await x.send_initial_message(interaction, interaction.channel)
        except NotPlaying:
            await interaction.followup.send(
                _("It appears you're not currently listening to Spotify."), ephemeral=True
            )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )

    async def slash_recommendations(
        self,
        interaction: discord.Interaction,
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
        log.debug(recommendations)
        await interaction.response.defer()
        recommendations = await RecommendationsConverter.convert_slash(self, recommendations)
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            try:
                search = await user_spotify.recommendations(**recommendations)
            except Exception:
                log.exception("Error getting recommendations")
                return await interaction.followup.send(
                    _("I could not find any recommendations with those parameters")
                )
            items = search.tracks
        if not items:
            return await interaction.followup.send(
                _("No recommendations could be found with that query.")
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=SpotifyTrackPages(items=items, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_set(self, interaction: discord.Interaction, **kwargs):
        command_mapping = {
            "forgetme": self.slash_forgetme,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        try:
            kwargs = {
                i["name"]: i["value"]
                for i in interaction.data["options"][0]["options"][0].get("options", [])
            }
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)

    async def slash_forgetme(self, interaction: discord.Interaction):
        """
        Forget all your spotify settings and credentials on the bot
        """
        await interaction.response.defer()
        await self.config.user(interaction.user).clear()
        if interaction.user.id in self.dashboard_authed:
            self.dashboard_authed.remove(interaction.user.id)
        await interaction.followup.send(_("All your spotify data deleted from my settings."))

    async def slash_me(self, interaction: discord.Interaction):
        """
        Shows your current Spotify Settings
        """
        await interaction.response.defer()
        em = discord.Embed(color=discord.Colour(0x1DB954))
        em.set_author(
            name=interaction.user.display_name + _(" Spotify Profile"),
            icon_url=interaction.user.avatar.url,
        )
        msg = ""
        cog_settings = await self.config.user(interaction.user).all()
        show_private = cog_settings["show_private"]
        msg += _("Show Private Playlists: {show_private}\n").format(show_private=show_private)
        if not cog_settings["token"]:
            em.description = msg
            await interaction.followup.send(embed=em)
            return
        user_token = await self.get_user_auth(interaction)
        if user_token:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user()
        if show_private or isinstance(interaction.channel, discord.DMChannel):
            msg += _(
                "Spotify Name: [{display_name}](https://open.spotify.com/user/{user_id})\n"
                "Subscription: {product}\n"
            ).format(display_name=cur.display_name, product=cur.product, user_id=cur.id)
        if isinstance(interaction.channel, discord.DMChannel):
            private = _("Country: {country}\nSpotify ID: {id}\nEmail: {email}\n").format(
                country=cur.country, id=cur.id, email=cur.email
            )
            em.add_field(name=_("Private Data"), value=private)
        if cur.images:
            em.set_thumbnail(url=cur.images[0].url)
        em.description = msg
        await interaction.followup.send(embed=em)

    async def slash_search(
        self,
        interaction: discord.Interaction,
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
        search_types = {
            "track": SpotifyTrackPages,
            "artist": SpotifyArtistPages,
            "album": SpotifyAlbumPages,
            "episode": SpotifyEpisodePages,
            "playlist": SpotifyPlaylistPages,
            "show": SpotifyShowPages,
        }
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify.")
            )
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            search = await user_spotify.search(query, (search_type,), "from_token", limit=50)
            items = search[0].items
        if not search[0].items:
            return await interaction.followup.send(
                _("No {search_type} could be found matching that query.").format(
                    search_type=search_type
                )
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=search_types[search_type](items=items, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_genres(self, interaction: discord.Interaction):
        """
        Display all available genres for the recommendations
        """
        await interaction.response.defer()
        try:
            self.GENRES = await self._spotify_client.recommendation_genre_seeds()
        except Exception:
            log.exception("Error grabbing genres.")
            return await interaction.followup.send(
                _(
                    "The bot owner needs to set their Spotify credentials "
                    "before this command can be used."
                    " See `{prefix}spotify set creds` for more details."
                ).format(prefix=interaction.clean_prefix)
            )
        await interaction.followup.send(
            _(
                "The following are available genres for Spotify's recommendations:\n\n {genres}"
            ).format(genres=humanize_list(self.GENRES)),
            ephemeral=True,
        )

    async def slash_recently_played(
        self, interaction: discord.Interaction, detailed: Optional[bool] = False
    ):
        """
        Displays your most recently played songs on Spotify
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.playback_recently_played(limit=50)
                tracks = search.items
        except tekore.Unauthorised:
            return await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=SpotifyRecentSongPages(tracks=tracks, detailed=detailed),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_top_tracks(self, interaction: discord.Interaction):
        """
        List your top tracks on spotify
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user_top_tracks(limit=50)
        except tekore.Unauthorised:
            return await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        tracks = cur.items
        x = SpotifyBaseMenu(
            source=SpotifyTopTracksPages(tracks),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def top_artists(self, interaction: discord.Interaction):
        """
        List your top tracks on spotify
        """

        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.current_user_top_artists(limit=50)
        except tekore.Unauthorised:
            return await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        artists = cur.items
        x = SpotifyBaseMenu(
            source=SpotifyTopArtistsPages(artists),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def spotify_new(self, interaction: discord.Interaction):
        """
        List new releases on Spotify
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        user_spotify = tekore.Spotify(sender=self._sender)
        with user_spotify.token_as(user_token):
            playlists = await user_spotify.new_releases(limit=50)
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        playlist_list = playlists.items
        x = SpotifySearchMenu(
            source=SpotifyNewPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_pause(self, interaction: discord.Interaction):
        """
        Pauses spotify for you
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_pause()
            await interaction.followup.send(_("Pausing playback."), ephemeral=True)
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_resume(self, interaction: discord.Interaction):
        """
        Resumes spotify for you
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                if not cur or not cur.is_playing:
                    await user_spotify.playback_resume()
                else:
                    return await interaction.followup.send(
                        _("You are already playing music on Spotify."), ephemeral=True
                    )
            await interaction.followup.send(_("Resuming playback."), ephemeral=True)
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_next(self, interaction: discord.Interaction):
        """
        Skips to the next track in queue on Spotify
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_next()
            await interaction.followup.send(_("Skipping to next track."), ephemeral=True)
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_previous(self, interaction: discord.Interaction):
        """
        Skips to the previous track in queue on Spotify
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_previous()
            await interaction.followup.send(_("Skipping to previous track."), ephemeral=True)
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_play(
        self, interaction: discord.Interaction, *, url_or_playlist_name: Optional[str] = ""
    ):
        """
        Play a track, playlist, or album on Spotify

        `<url_or_playlist_name>` can be multiple spotify track URL *or* URI or
        a single album or playlist link

        if something other than a spotify URL or URI is provided
        the bot will search through your playlists and start playing
        the playlist with the closest matching name
        """
        await interaction.response.defer()
        url_or_playlist_name = url_or_playlist_name.replace("🧑‍🎨", ":artist:")
        # because discord will replace this in URI's automatically 🙄
        song_data = SPOTIFY_RE.finditer(url_or_playlist_name)
        tracks = []
        new_uri = ""
        uri_type = ""
        if song_data:
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                uri_type = match.group(2)
                if match.group(2) == "track":
                    tracks.append(match.group(3))
            log.debug(new_uri)
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if tracks:
                    await user_spotify.playback_start_tracks(tracks)
                    all_tracks = await user_spotify.tracks(tracks)
                    track = all_tracks[0]
                    track_name = track.name
                    artists = getattr(track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    track_artist = humanize_list([a.name for a in artists])
                    em = await song_embed(track, False)
                    await interaction.followup.send(
                        _("Now playing {track} by {artist}").format(
                            track=track_name, artist=artist
                        ),
                        embed=em,
                        ephemeral=True,
                    )
                    return
                if new_uri:
                    await user_spotify.playback_start_context(new_uri)
                    if uri_type == "playlist":
                        cur_tracks = await user_spotify.playlist(new_uri)
                        track_name = cur_tracks.name
                        await interaction.followup.send(
                            _("Now playing {track}").format(track=track_name),
                            ephemeral=True,
                        )
                    if uri_type == "artist":
                        artist_id = new_uri.split(":")[-1]
                        cur_tracks = await user_spotify.artist(artist_id)
                        track_name = cur_tracks.name
                        await interaction.followup.send(
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
                        await interaction.followup.send(
                            _("Now playing {track} by {artist}.").format(
                                track=track_name, artist=track_artist
                            ),
                            ephemeral=True,
                        )
                    return
                if url_or_playlist_name:
                    cur = await user_spotify.followed_playlists(limit=50)
                    playlists = cur.items
                    while len(playlists) < cur.total:
                        new = await user_spotify.followed_playlists(
                            limit=50, offset=len(playlists)
                        )
                        for p in new.items:
                            playlists.append(p)
                    for playlist in playlists:
                        if url_or_playlist_name.lower() in playlist.name.lower():
                            await user_spotify.playback_start_context(playlist.uri)
                            await interaction.followup.send(
                                _("Now playing {playlist}").format(playlist=playlist.name),
                                ephemeral=True,
                            )
                            return
                    saved_tracks = await user_spotify.saved_tracks(limit=50)
                    for track in saved_tracks.items:
                        if (
                            url_or_playlist_name.lower() in track.track.name.lower()
                            or url_or_playlist_name.lower()
                            in ", ".join(a.name for a in track.track.artists)
                        ):
                            await user_spotify.playback_start_tracks([track.track.id])
                            track_name = track.track.name
                            artists = getattr(track.track, "artists", [])
                            artist = humanize_list([a.name for a in artists])
                            track_artist = humanize_list([a.name for a in artists])
                            em = await song_embed(track.track, False)
                            await interaction.followup.send(
                                _("Now playing {track} by {artist}").format(
                                    track=track_name, artist=artist
                                ),
                                embed=em,
                                ephemeral=True,
                            )
                            return
                else:
                    cur = await user_spotify.saved_tracks(limit=50)
                    await user_spotify.playback_start_tracks([t.track.id for t in cur.items])
                    await interaction.followup.send(_("Now playing saved tracks."), ephemeral=True)
                    return
                await interaction.followup.send(
                    _("I could not find any URL's or matching playlist names.")
                )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            log.debug("Error playing song", exc_info=True)
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_queue_add(self, interaction: discord.Interaction, songs: SpotifyURIConverter):
        """
        Queue a song to play next in Spotify

        `<songs>` is one or more spotify URL or URI leading to a single track that will
        be added to your current queue
        """
        await interaction.response.defer()
        tracks = []
        added_tracks = []
        song_data = SPOTIFY_RE.finditer(songs)
        for song in song_data:
            if song.group(2) == "track":
                tracks.append(f"spotify:{song.group(2)}:{song.group(3)}")
                added_tracks.append(song.group(3))
        if not tracks:
            return await interaction.followup.send(
                _("I can only add tracks to your spotify queue."), ephemeral=True
            )
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for uri in tracks:
                    await user_spotify.playback_queue_add(uri)
                all_tracks = await user_spotify.tracks(added_tracks)
            track = all_tracks[0]
            track_name = track.name
            artists = getattr(track, "artists", [])
            artist = humanize_list([a.name for a in artists])
            em = await song_embed(track, False)
            await interaction.followup.send(
                _("Queueing {track} by {artist}").format(track=track_name, artist=artist),
                embed=em,
                ephemeral=True,
            )
        except tekore.Unauthorised:
            log.exception("Cannot queue track")
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_repeat(self, interaction: discord.Interaction, state: Optional[str] = None):
        """
        Repeats your current song on spotify

        `<state>` must accept one of `off`, `track`, or `context`.
        """
        await interaction.response.defer()
        if state and state.lower() not in ["off", "track", "context"]:
            return await interaction.followup.send(
                _("Repeat must accept either `off`, `track`, or `context`.")
            )
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if state:
                    lookup = {
                        "off": "off",
                        "context": "repeat",
                        "track": "repeatone",
                    }
                else:
                    cur = await user_spotify.playback()
                    if not cur:
                        return await interaction.followup.send(
                            _("I could not find an active device to play songs on.")
                        )
                    if cur.repeat_state == "off":
                        state = "context"
                    if cur.repeat_state == "context":
                        state = "track"
                    if cur.repeat_state == "track":
                        state = "off"
                await user_spotify.playback_repeat(str(state).lower())
            await interaction.followup.send(
                _("Setting Spotify repeat to {state}.").format(state=state.title()), ephemeral=True
            )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_shuffle(self, interaction: discord.Interaction, state: Optional[bool] = None):
        """
        Shuffles your current song list

        `<state>` either true or false. Not providing this will toggle the current setting.
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if state is None:
                    cur = await user_spotify.playback()
                    if not cur:
                        await interaction.followup.send(
                            _("I could not find an active device to play songs on."),
                            ephemeral=True,
                        )
                    state = not cur.shuffle_state
                await user_spotify.playback_shuffle(state)
            if state:
                await interaction.followup.send(_("Shuffling songs on Spotify."), ephemeral=True)
            else:
                await interaction.followup.send(
                    _("Turning off shuffle on Spotify."), ephemeral=True
                )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_seek(self, interaction: discord.Interaction, seconds: Union[int, str]):
        """
        Seek to a specific point in the current song

        `<seconds>` Accepts seconds or a value formatted like
        00:00:00 (`hh:mm:ss`) or 00:00 (`mm:ss`).
        """
        await interaction.response.defer()
        try:
            int(seconds)
            abs_position = False
        except ValueError:
            abs_position = True
            seconds = time_convert(seconds)
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                now = cur.progress_ms
                total = cur.item.duration_ms
                log.debug(seconds)
                if abs_position:
                    to_seek = seconds * 1000
                else:
                    to_seek = seconds * 1000 + now
                await user_spotify.playback_seek(to_seek)
            await interaction.followup.send(
                _("Seeking to {time}.").format(time=seconds), ephemeral=True
            )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_volume(self, interaction: discord.Interaction, volume: Union[int, str]):
        """
        Set your spotify volume percentage

        `<volume>` a number between 0 and 100 for volume percentage.
        """
        await interaction.response.defer()
        volume = max(min(100, volume), 0)  # constrains volume to be within 100
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                await user_spotify.playback_volume(volume)
                await interaction.followup.send(
                    _("Setting Spotify's volume to {volume}.").format(volume=volume),
                    ephemeral=True,
                )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_device(self, interaction: discord.Interaction, **kwargs):
        command_mapping = {
            "transfer": self.slash_device_transfer,
            "list": self.slash_device_list,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        try:
            kwargs = {
                i["name"]: i["value"]
                for i in interaction.data["options"][0]["options"][0].get("options", [])
            }
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)

    async def slash_device_transfer(
        self, interaction: discord.Interaction, *, device_name: Optional[str] = None
    ):
        """
        Change the currently playing spotify device

        `<device_name>` The name of the device you want to switch to.
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            new_device = None
            if device_name:
                for d in devices:
                    if device_name.lower() in d.name.lower():
                        log.debug(f"Transferring playback to {d.name}")
                        new_device = d
            else:
                new_view = SpotifyDeviceView(interaction)
                options = []
                for device in devices[:25]:
                    options.append(discord.SelectOption(label=device.name[:25], value=device.id))
                select_view = SpotifySelectDevice(options, user_token, self._sender)
                new_view.add_item(select_view)
                await interaction.followup.send(
                    _("Pick the device you want to transfer playback to"), view=new_view
                )
                # new_device = await self.spotify_pick_device(interaction, devices)
                return
            if not new_device:
                return await interaction.followup.send(
                    _("I will not transfer spotify playback for you.")
                )
            with user_spotify.token_as(user_token):
                await user_spotify.playback_transfer(new_device.id, is_playing)
            await interaction.followup.send(
                _("Transferring playback to {device}").format(device=new_device.name),
                ephemeral=True,
            )
        except tekore.Unauthorised:
            log.debug("Error transferring playback", exc_info=True)
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_device_list(self, interaction: discord.Interaction):
        """
        List all available devices for Spotify
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            devices_msg = _("{author}'s Spotify Devices:\n").format(
                author=interaction.user.display_name
            )
            for c, d in enumerate(devices):
                devices_msg += f"{c+1}. `{d.name}` - {d.type} - {d.volume_percent}% "
                if d.is_active:
                    devices_msg += str(
                        emoji_handler.get_emoji(
                            "playpause",
                            interaction.channel.permissions_for(
                                interaction.guild.me
                            ).use_external_emojis,
                        )
                    )
                devices_msg += "\n"
            if interaction.channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.followup.send(
                    embed=discord.Embed(description=devices_msg), ephemeral=True
                )
            else:
                await interaction.followup.send(devices_msg, ephemeral=True)
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_playlists(self, interaction: discord.Interaction, **kwargs):
        command_mapping = {
            "add": self.slash_playlist_add,
            "create": self.slash_playlist_create,
            "featured": self.slash_playlist_featured,
            "follow": self.slash_playlist_follow,
            "list": self.slash_playlist_list,
            "remove": self.slash_playlist_remove,
            "view": self.slash_playlist_view,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        try:
            kwargs = {
                i["name"]: i["value"]
                for i in interaction.data["options"][0]["options"][0].get("options", [])
            }
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)

    async def slash_playlist_featured(self, interaction: discord.Interaction):
        """
        List your Spotify featured Playlists
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                playlists = await user_spotify.featured_playlists(limit=50)
        except tekore.Unauthorised:
            return await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        playlist_list = playlists[1].items
        x = SpotifySearchMenu(
            source=SpotifyNewPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_playlist_list(self, interaction: discord.Interaction):
        """
        List your Spotify Playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
        except tekore.Unauthorised:
            return await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        show_private = await self.config.user(interaction.user).show_private() or isinstance(
            interaction.channel, discord.DMChannel
        )
        if show_private:
            playlist_list = playlists
        else:
            playlist_list = [p for p in playlists if p.public is not False]
        if len(playlist_list) == 0:
            await interaction.followup.send(
                _("You don't have any saved playlists I can show here.")
            )
            return
        x = SpotifyBaseMenu(
            source=SpotifyPlaylistsPages(playlist_list),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_playlist_view(self, interaction: discord.Interaction):
        """
        View details about your spotify playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
        except tekore.Unauthorised:
            return await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        show_private = await self.config.user(interaction.author).show_private() or isinstance(
            interaction.channel, discord.DMChannel
        )
        show_private = await self.config.user(interaction.author).show_private() or isinstance(
            interaction.channel, discord.DMChannel
        )
        if show_private:
            playlist_list = playlists
        else:
            playlist_list = [p for p in playlists if p.public is not False]
        if len(playlist_list) == 0:
            await interaction.followup.send(
                _("You don't have any saved playlists I can show here.")
            )
            return
        x = SpotifySearchMenu(
            source=SpotifyPlaylistPages(playlist_list, False),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)

    async def slash_playlist_create(
        self,
        interaction: discord.Interaction,
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
        await interaction.response.defer()
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                user = await user_spotify.current_user()
                await user_spotify.playlist_create(user.id, name, public, description)
                await interaction.tick()
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_playlist_add(
        self,
        interaction: discord.Interaction,
        name: str,
        to_add: SpotifyURIConverter,
    ):
        """
        Add 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to add songs to
        `<to_remove>` The song links or URI's you want to add
        """
        await interaction.response.defer()
        tracks = []
        new_uri = ""
        for match in to_add:
            new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
            if match.group(2) == "track":
                tracks.append(new_uri)
        if not tracks:
            return await interaction.followup.send(
                _("You did not provide any tracks for me to add to the playlist.")
            )
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
                for playlist in playlists:
                    if name.lower() == playlist.name.lower():
                        await user_spotify.playlist_add(playlist.id, tracks)
                        return
            await interaction.followup.send(
                _("I could not find a playlist matching {name}.").format(name=name)
            )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_playlist_remove(
        self,
        interaction: discord.Interaction,
        name: str,
        to_remove: SpotifyURIConverter,
    ):
        """
        Remove 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to remove songs from
        `<to_remove>` The song links or URI's you want to have removed
        """
        await interaction.response.defer()
        tracks = []
        new_uri = ""
        for match in to_remove:
            new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
            if match.group(2) == "track":
                tracks.append(new_uri)
        if not tracks:
            return await interaction.followup.send(
                _("You did not provide any tracks for me to add to the playlist.")
            )
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.followed_playlists(limit=50)
                playlists = cur.items
                while len(playlists) < cur.total:
                    new = await user_spotify.followed_playlists(limit=50, offset=len(playlists))
                    for p in new.items:
                        playlists.append(p)
                for playlist in playlists:
                    if name.lower() == playlist.name.lower():
                        await user_spotify.playlist_remove(playlist.id, tracks)
                        return
            await interaction.followup.send(
                _("I could not find a playlist matching {name}.").format(name=name)
            )
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_playlist_follow(
        self,
        interaction: discord.Interaction,
        to_follow: SpotifyURIConverter,
        public: Optional[bool] = False,
    ):
        """
        Add a playlist to your spotify library

        `[public]` Whether or not the followed playlist should be public after
        `<to_follow>` The song links or URI's you want to have removed
        """
        await interaction.response.defer()
        tracks = []
        for match in to_follow:
            if match.group(2) == "playlist":
                tracks.append(match.group(3))
        if not tracks:
            return await interaction.followup.send(
                _("You did not provide any playlists for me to add to your library.")
            )
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for playlist in tracks:
                    await user_spotify.playlist_follow(playlist, public)
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_artists(self, interaction: discord.Interaction, **kwargs):
        command_mapping = {
            "follow": self.slash_artist_follow,
            "albums": self.slash_artist_albums,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        try:
            kwargs = {
                i["name"]: i["value"]
                for i in interaction.data["options"][0]["options"][0].get("options", [])
            }
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)

    async def slash_artist_follow(
        self,
        interaction: discord.Interaction,
        to_follow: SpotifyURIConverter,
    ):
        """
        Add an artist to your spotify library

        `<to_follow>` The song links or URI's you want to have removed
        """
        await interaction.response.defer()
        tracks = []
        for match in to_follow:
            if match.group(2) == "artist":
                tracks.append(match.group(3))
        user_token = await self.get_user_auth(interaction)
        if not user_token:
            return await interaction.followup.send(
                _("You need to authorize me to interact with spotify."), ephemeral=True
            )
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                for playlist in tracks:
                    await user_spotify.artist_follow(playlist)
                await interaction.tick()
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        except tekore.NotFound:
            await interaction.followup.send(
                _("I could not find an active device to play songs on."), ephemeral=True
            )
        except tekore.Forbidden as e:
            if "non-premium" in str(e):
                await interaction.followup.send(
                    _("This action is prohibited for non-premium users."), ephemeral=True
                )
            else:
                await interaction.followup.send(
                    _("I couldn't perform that action for you."), ephemeral=True
                )
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await interaction.followup.send(
                _("An exception has occured, please contact the bot owner for more assistance.")
            )

    async def slash_artist_albums(
        self,
        interaction: discord.Interaction,
        to_follow: SpotifyURIConverter,
    ):
        """
        View an artists albums

        `<to_follow>` The artis links or URI's you want to view the albums of
        """

        await interaction.response.defer()
        tracks = []
        for match in to_follow:
            if match.group(2) == "artist":
                tracks.append(match.group(3))
        if not tracks:
            return await interaction.followup.send(_("You did not provide an artist link or URI."))
        try:
            user_token = await self.get_user_auth(interaction)
            if not user_token:
                return await interaction.followup.send(
                    _("You need to authorize me to interact with spotify."), ephemeral=True
                )
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.artist_albums(tracks[0], limit=50)
                tracks = search.items
        except tekore.Unauthorised:
            await interaction.followup.send(
                _("I am not authorized to perform this action for you."), ephemeral=True
            )
        if interaction.guild:
            delete_after = await self.config.guild(interaction.guild).delete_message_after()
            clear_after = await self.config.guild(interaction.guild).clear_reactions_after()
            timeout = await self.config.guild(interaction.guild).menu_timeout()
        else:
            delete_after, clear_after, timeout = False, True, 120
        x = SpotifySearchMenu(
            source=SpotifyAlbumPages(tracks, False),
            delete_message_after=delete_after,
            clear_reactions_after=clear_after,
            timeout=timeout,
            cog=self,
            user_token=user_token,
        )
        await x.send_initial_message(interaction, interaction.channel)
