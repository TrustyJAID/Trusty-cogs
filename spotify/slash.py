import logging
import re

import discord
import tekore
from discord.enums import InteractionType
from discord.slash import CommandOptionChoice
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .helpers import SPOTIFY_RE, VALID_RECOMMENDATIONS, song_embed

log = logging.getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)


class SpotifySlash:
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

    async def queue_from_message(self, interaction: discord.Interaction):
        log.debug(interaction.message)
        message_data = list(interaction.data["resolved"]["messages"].values())[0]
        message = discord.Message(
            state=interaction._state, channel=interaction.channel, data=message_data
        )
        log.debug(message)
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

    async def play_from_message(self, interaction: discord.Interaction):
        log.debug(interaction.message)
        message_data = list(interaction.data["resolved"]["messages"].values())[0]
        message = discord.Message(
            state=interaction._state, channel=interaction.channel, data=message_data
        )
        log.debug(message)
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

    @staticmethod
    def convert_slash_args(interaction: discord.Interaction, option: dict):
        convert_args = {
            3: lambda x: x,
            4: lambda x: int(x),
            5: lambda x: bool(x),
            6: lambda x: final_resolved[int(x)] or interaction.guild.get_member(int(x)),
            7: lambda x: final_resolved[int(x)] or interaction.guild.get_channel(int(x)),
            8: lambda x: final_resolved[int(x)] or interaction.guild.get_role(int(x)),
            9: lambda x: final_resolved[int(x)]
            or interaction.guild.get_role(int(x))
            or interaction.guild.get_member(int(x)),
            10: lambda x: float(x),
        }
        resolved = interaction.data.get("resolved", {})
        final_resolved = {}
        if resolved:
            resolved_users = resolved.get("users")
            if resolved_users:
                resolved_members = resolved.get("members")
                for _id, data in resolved_users.items():
                    if resolved_members:
                        member_data = resolved_members[_id]
                        member_data["user"] = data
                        member = discord.Member(
                            data=member_data, guild=interaction.guild, state=interaction._state
                        )
                        final_resolved[int(_id)] = member
                    else:
                        user = discord.User(data=data, state=interaction._state)
                        final_resolved[int(_id)] = user
            resolved_channels = data.get("channels")
            if resolved_channels:
                for _id, data in resolved_channels.items():
                    data["position"] = None
                    _cls, _ = discord.channel._guild_channel_factory(data["type"])
                    channel = _cls(state=interaction._state, guild=interaction.guild, data=data)
                    final_resolved[int(_id)] = channel
            resolved_messages = resolved.get("messages")
            if resolved_messages:
                for _id, data in resolved_messages.items():
                    msg = discord.Message(
                        state=interaction._state, channel=interaction.channel, data=data
                    )
                    final_resolved[int(_id)] = msg
            resolved_roles = resolved.get("roles")
            if resolved_roles:
                for _id, data in resolved_roles.items():
                    role = discord.Role(
                        guild=interaction.guild, state=interaction._state, data=data
                    )
                    final_resolved[int(_id)] = role
        return convert_args[option["type"]](option["value"])

    async def set_genres(self):
        try:
            self.GENRES = await self._spotify_client.recommendation_genre_seeds()
        except Exception:
            log.exception("Error grabbing genres.")

    async def get_genre_choices(self, cur_value: str):
        supplied_genres = ""
        new_genre = ""
        for sup in cur_value.split(" "):
            if sup in self.GENRES:
                supplied_genres += f"{sup} "
            else:
                new_genre = sup

        ret = [
            CommandOptionChoice(name=f"{supplied_genres} {g}", value=f"{supplied_genres} {g}")
            # {"name": f"{supplied_genres} {g}", "value": f"{supplied_genres} {g}"}
            for g in self.GENRES
            if new_genre in g
        ]
        if supplied_genres:
            # ret.insert(0, {"name": supplied_genres, "value": supplied_genres})
            ret.insert(0, CommandOptionChoice(name=supplied_genres, value=supplied_genres))
        return ret

    async def parse_spotify_recommends(self, interaction: discord.Interaction):
        command_options = interaction.data["options"][0]["options"]
        if interaction.type is InteractionType.autocomplete:
            cur_value = command_options[0]["value"]
            if not self.GENRES:
                await self.set_genres()

            genre_choices = await self.get_genre_choices(cur_value)
            await interaction.response.autocomplete(genre_choices[:25])
            return
        recommendations = {"limit": 100, "market": "from_token"}
        detailed = False
        for option in command_options:
            name = option["name"]
            if name == "detailed":
                detailed = True
                continue
            if name in VALID_RECOMMENDATIONS and name != "mode":
                recommendations[f"target_{name}"] = VALID_RECOMMENDATIONS[name](option["value"])
            elif name == "genres":
                recommendations[name] = option["value"].strip().split(" ")
            elif name in ["artists", "tracks"]:
                song_data = SPOTIFY_RE.finditer(option["value"])
                tracks = []
                artists = []
                if song_data:
                    for match in song_data:
                        if match.group(2) == "track":
                            tracks.append(match.group(3))
                        if match.group(2) == "artist":
                            artists.append(match.group(3))
                if tracks:
                    recommendations["track_ids"] = tracks
                if artists:
                    recommendations["artist_ids"] = artists
            else:
                recommendations[f"target_{name}"] = option["value"]
        await self.spotify_recommendations(interaction, detailed, recommendations=recommendations)

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
