from __future__ import annotations

import datetime
import re
from copy import copy
from enum import Enum
from typing import Final, List, Optional, Pattern, Union

import discord
import tekore
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta
from tabulate import tabulate

log = getLogger("red.trusty-cogs.spotify")

SPOTIFY_RE = re.compile(
    r"(https?:\/\/open\.spotify\.com\/|spotify:?)"
    r"(track|playlist|album|artist|episode|show)\/?:?([A-Za-z0-9]+)"
)

SPOTIFY_LOGO = "https://imgur.com/Ig4VuuJ.png"

_RE_TIME_CONVERTER: Final[Pattern] = re.compile(r"(?:(\d+):)?([0-5]?[0-9]):([0-5][0-9])")

_ = Translator("Spotify", __file__)


REPEAT_STATES = {
    "context": "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
    "track": "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}",
    "off": "",
}

PITCH = {
    0: "C ",
    1: "C♯, D♭",
    2: "D",
    3: "D♯, E♭",
    4: "E",
    5: "F",
    6: "F♯, G♭",
    7: "G",
    8: "G♯, A♭",
    9: "A",
    10: "A♯, B♭",
    11: "B",
    "t": "A♯, B♭",
    "A": "A♯, B♭",
    "e": "B",
    "B": "B",
}


class GenresConverter(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> List[str]:
        ret = []
        valid_genres = ctx.bot.get_cog("Spotify").GENRES
        for g in argument.split(" "):
            if g in valid_genres:
                ret.append(g)
        if not ret:
            raise commands.BadArgument
        return ret

    async def transform(self, interaction: discord.Interaction, argument: str) -> List[str]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        supplied_genres = ""
        new_genre = ""
        valid_genres = interaction.client.get_cog("Spotify").GENRES
        for sup in current.lower().split(" "):
            if sup in valid_genres:
                supplied_genres += f"{sup} "
            else:
                new_genre = sup.lower()

        ret = [
            discord.app_commands.Choice(
                name=f"{supplied_genres} {g}", value=f"{supplied_genres} {g}"
            )
            # {"name": f"{supplied_genres} {g}", "value": f"{supplied_genres} {g}"}
            for g in valid_genres
            if new_genre in g
        ]
        if supplied_genres:
            # ret.insert(0, {"name": supplied_genres, "value": supplied_genres})
            ret.insert(0, discord.app_commands.Choice(name=supplied_genres, value=supplied_genres))
        return ret[:25]


class TracksConverter:
    track_re = re.compile(r"(https?:\/\/open\.spotify\.com\/|spotify:?)track\/?:?([A-Za-z0-9]+)")

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> List[str]:
        find = cls.track_re.findall(argument)
        ret = []
        for find in cls.track_re.finditer(argument):
            ret.append(find.group(2))
        if not ret:
            raise commands.BadArgument(_("That is not a valid Spotify track URL."))
        return ret


class ArtistsConverter:
    track_re = re.compile(r"(https?:\/\/open\.spotify\.com\/|spotify:?)artist\/?:?([A-Za-z0-9]+)")

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> List[str]:
        find = cls.track_re.findall(argument)
        ret = []
        for find in cls.track_re.finditer(argument):
            ret.append(find.group(2))
        if not ret:
            raise commands.BadArgument(_("That is not a valid Spotify artist URL."))
        return ret


class Mode(Enum):
    minor = 0
    major = 1

    def __str__(self):
        return str(self.value)

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Mode:
        if argument.lower() == "major":
            return cls(1)
        if argument.lower() == "minor":
            return cls(0)
        else:
            raise BadArgument(_("`{argument}` is not a valid mode.").format(argument=argument))


class RecommendationsFlags(discord.ext.commands.FlagConverter, case_insensitive=True):
    genres: Optional[List[str]] = discord.ext.commands.flag(
        name="genres",
        aliases=["genre"],
        default=None,
        converter=GenresConverter,
        description="Must be any combination of valid genres",
    )
    tracks: Optional[List[str]] = discord.ext.commands.flag(
        name="tracks",
        aliases=["track"],
        default=None,
        converter=TracksConverter,
        description="Any Spotify track URL used as the seed.",
    )
    artists: Optional[List[str]] = discord.ext.commands.flag(
        name="artists",
        aliases=["artist"],
        default=None,
        converter=ArtistsConverter,
        description="Any Spotify artist URL used as the seed.",
    )
    acousticness: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="acousticness",
        aliases=["acoustic"],
        description="A value from 0 to 100 the target acousticness of the tracks.",
    )
    danceability: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="danceability",
        aliases=["dance"],
        description="A value from 0 to 100 describing how danceable the tracks are.",
    )
    duration_ms: Optional[int] = discord.ext.commands.flag(
        name="duration_ms", aliases=["duration"], description="The target duration of the tracks"
    )
    energy: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="energy",
        description="Energy is a measure from 0 to 100 and represents a perceptual measure of intensity and activity",
    )
    instrumentalness: Optional[
        discord.ext.commands.Range[int, 0, 100]
    ] = discord.ext.commands.flag(
        name="instrumentalness",
        aliases=["instrument"],
        description="A value from 0 to 100 representing whether or not a track contains vocals.",
    )
    key: Optional[int] = discord.ext.commands.flag(
        name="key", description="The target key of the tracks."
    )
    liveness: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="liveness",
        aliases=["live"],
        description="A value from 0-100 representing the presence of an audience in the recording.",
    )
    loudness: Optional[discord.ext.commands.Range[int, -60, 0]] = discord.ext.commands.flag(
        name="loudness",
        aliases=["loud"],
        description="The overall loudness of a track in decibels (dB) between -60 and 0 db.",
    )
    mode: Optional[Mode] = discord.ext.commands.flag(
        name="mode",
        description="The target modality (major or minor) of the track.",
    )
    popularity: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="popularity",
        description="A value from 0-100 the target popularity of the tracks.",
    )
    speechiness: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="speechiness",
        aliases=["speech"],
        description="A value from 0-100 Speechiness is the presence of spoken words in a track.",
    )
    tempo: Optional[discord.ext.commands.Range[int, 0, 500]] = discord.ext.commands.flag(
        name="tempo",
        description="The overall estimated tempo of a track in beats per minute (BPM).",
    )
    time_signature: Optional[int] = discord.ext.commands.flag(
        name="time_signature",
        aliases=["signature"],
        description="The time signature ranges from 3 to 7 indicating time signatures of '3/4', to '7/4'.",
    )
    valence: Optional[discord.ext.commands.Range[int, 0, 100]] = discord.ext.commands.flag(
        name="valence",
        aliases=["happiness"],
        description="A measure from 0 to 100 describing the musical positiveness conveyed by a track",
    )


class EmojiHandler:
    def __init__(self):
        # with open(Path(__file__).parent / "emojis.json", "r", encoding="utf8") as infile:
        self.emojis = {
            "playpause": "\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            "pause": "\N{DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            "repeat": "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
            "repeatone": "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}",
            "next": "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            "previous": "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            "like": "\N{GREEN HEART}",
            "fastforward": "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}\N{VARIATION SELECTOR-16}",
            "rewind": "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}\N{VARIATION SELECTOR-16}",
            "volume_down": "\N{SPEAKER WITH ONE SOUND WAVE}",
            "volume_up": "\N{SPEAKER WITH THREE SOUND WAVES}",
            "volume_mute": "\N{SPEAKER WITH CANCELLATION STROKE}",
            "off": "\N{NEGATIVE SQUARED CROSS MARK}",
            "playall": "\N{EJECT SYMBOL}\N{VARIATION SELECTOR-16}",
            "shuffle": "\N{TWISTED RIGHTWARDS ARROWS}",
            "back_left": "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            "forward_right": "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            "play": "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            "queue": "🇶",
        }

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


spotify_emoji_handler = (
    EmojiHandler()
)  # initialize here so when it's changed other objects use this one


class SpotifyError(Exception):
    pass


class NotPlaying(SpotifyError):
    pass


class InvalidEmoji(SpotifyError):
    pass


def time_convert(length: Union[int, str]) -> int:
    if isinstance(length, int):
        return length

    match = _RE_TIME_CONVERTER.match(length)
    if match is not None:
        hr = int(match.group(1)) if match.group(1) else 0
        mn = int(match.group(2)) if match.group(2) else 0
        sec = int(match.group(3)) if match.group(3) else 0
        pos = sec + (mn * 60) + (hr * 3600)
        return pos
    else:
        try:
            return int(length)
        except ValueError:
            return 0


async def song_embed(track: tekore.model.FullTrack, detailed: bool) -> discord.Embed:
    em = discord.Embed(color=discord.Colour(0x1DB954))
    url = f"https://open.spotify.com/track/{track.id}"
    artist_title = f"{track.name} by " + humanize_list([a.name for a in track.artists])
    album = getattr(track, "album", "")
    if album:
        album = f"[{album.name}](https://open.spotify.com/album/{album.id})"
    em.set_author(
        name=track.name[:256],
        url=url,
        icon_url=SPOTIFY_LOGO,
    )
    total_time = str(datetime.timedelta(seconds=track.duration_ms / 1000))
    em.description = f"[{artist_title}]({url}) - `{total_time:.7}`\n\n{album}"
    if track.album.images:
        em.set_thumbnail(url=track.album.images[0].url)
    return em


async def make_details(track: tekore.model.FullTrack, details: tekore.model.AudioFeatures) -> str:
    """
    {
      "duration_ms" : 255349,
      "key" : 5,
      "mode" : 0,
      "time_signature" : 4,
      "acousticness" : 0.514,
      "danceability" : 0.735,
      "energy" : 0.578,
      "instrumentalness" : 0.0902,
      "liveness" : 0.159,
      "loudness" : -11.840,
      "speechiness" : 0.0461,
      "valence" : 0.624,
      "tempo" : 98.002,
      "id" : "06AKEBrKUckW0KREUWRnvT",
      "uri" : "spotify:track:06AKEBrKUckW0KREUWRnvT",
      "track_href" : "https://api.spotify.com/v1/tracks/06AKEBrKUckW0KREUWRnvT",
      "analysis_url" : "https://api.spotify.com/v1/audio-analysis/06AKEBrKUckW0KREUWRnvT",
      "type" : "audio_features"
    }
    """
    attrs = [
        "duration_ms",
        "key",
        "mode",
        "time_signature",
        "acousticness",
        "danceability",
        "energy",
        "instrumentalness",
        "liveness",
        "speechiness",
        "valence",
        "loudness",
        "tempo",
    ]
    ls = []
    ls.append(("Explicit", track.explicit))
    ls.append(("Popularity", f"[ {track.popularity} ]"))
    track_num = getattr(track, "track_number", "None")
    ls.append(("Track", f"[ {track_num} ]"))
    for attr in attrs:
        friendly_name = attr.replace("_", " ").title()
        detail = getattr(details, attr)
        if attr == "duration_ms":
            detail = humanize_timedelta(seconds=int(detail) / 1000)
            ls.append(("Duration", detail))
            continue
        if attr == "key":
            detail = PITCH[detail]
        if attr == "mode":
            detail = Mode(detail).name
        if attr == "loudness":
            detail = f"[ {detail} dB ]"
        if attr == "tempo":
            detail = f"[ {detail} BPM ]"
        if attr == "time_signature":
            detail = f"[ {detail}/4 ]"
        if isinstance(detail, int):
            detail = f"[ {detail} ]"
        if isinstance(detail, float):
            detail = f"[ {round(detail * 100)}% ]"
        ls.append((friendly_name, detail))
    return tabulate(ls, headers=["Detail", "Info"], tablefmt="pretty")


def _draw_play(song: tekore.model.CurrentlyPlayingContext) -> str:
    """
    Courtesy of aikaterna from Audio in red and away cog
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/audio/core/utilities/formatting.py#L358-L376
    """
    total_time = datetime.timedelta(seconds=song.item.duration_ms / 1000)
    elapsed_time = datetime.timedelta(seconds=song.progress_ms / 1000)
    sections = 12
    loc_time = round((elapsed_time / total_time) * sections)  # 10 sections
    bar_char = "\N{BOX DRAWINGS HEAVY HORIZONTAL}"
    seek_char = "\N{RADIO BUTTON}"
    play_char = (
        "\N{BLACK RIGHT-POINTING TRIANGLE}"
        if song.is_playing
        else "\N{DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}"
    )
    msg = "\n" + play_char + " "

    for i in range(sections):
        if i == loc_time:
            msg += seek_char
        else:
            msg += bar_char
    msg += " `{:.7}`/`{:.7}`".format(str(elapsed_time), str(total_time))
    return msg


class SearchTypes(Converter):
    """
    This ensures that when using the search function we get a valid search type
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        valid_types = [
            "artist",
            "album",
            "episode",
            "playlist",
            "show",
            "track",
        ]
        find = argument.lower()
        if find not in valid_types:
            raise BadArgument(_("{argument} is not a valid genre.").format(argument=argument))
        return find


class ScopeConverter(Converter):
    """
    This ensures that when using the search function we get a valid search type
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        valid_types = [
            "user-read-private",
            "user-top-read",
            "user-read-recently-played",
            "user-follow-read",
            "user-library-read",
            "user-read-currently-playing",
            "user-read-playback-state",
            "user-read-playback-position",
            "playlist-read-collaborative",
            "playlist-read-private",
            "user-follow-modify",
            "user-library-modify",
            "user-modify-playback-state",
            "playlist-modify-public",
            "playlist-modify-private",
            "ugc-image-upload",
        ]
        find = argument.lower()
        if find not in valid_types:
            raise BadArgument(_("{argument} is not a valid scope.").format(argument=argument))
        return find


class SpotifyURIConverter(Converter):
    """
    Ensures that the argument is a valid spotify URL or URI
    """

    async def convert(self, ctx: commands.Context, argument: str) -> List[re.Match]:
        match = SPOTIFY_RE.finditer(argument)
        if not match:
            raise BadArgument(
                _("{argument} is not a valid Spotify URL or URI.").format(argument=argument)
            )
        return list(match)
