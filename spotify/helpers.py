import datetime
import logging
import re
from typing import Final, List, Pattern, Union

import tekore
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta
from tabulate import tabulate

log = logging.getLogger("red.trusty-cogs.spotify")

SPOTIFY_RE = re.compile(
    r"(https?:\/\/open\.spotify\.com\/|spotify:)(track|playlist|album|artist|episode|show)\/?:?([^?\(\)\s]+)"
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

MODE = {
    0: "minor",
    1: "Major",
}

VALID_RECOMMENDATIONS = {
    "acousticness": lambda x: max(min(1.0, x / 100), 0.0),
    "danceability": lambda x: max(min(1.0, x / 100), 0.0),
    "duration_ms": lambda x: int(x),
    "energy": lambda x: max(min(1.0, x / 100), 0.0),
    "instrumentalness": lambda x: max(min(1.0, x / 100), 0.0),
    "key": lambda x: max(min(11, x), 0),
    "liveness": lambda x: max(min(1.0, x / 100), 0.0),
    "loudness": lambda x: max(min(0.0, x), -60.0),
    "mode": lambda x: 1 if x.lower() == "major" else 0,
    "popularity": lambda x: max(min(100, x), 0),
    "speechiness": lambda x: max(min(1.0, x / 100), 0.0),
    "tempo": lambda x: float(x),
    "time_signature": lambda x: int(x),
    "valence": lambda x: max(min(1.0, x / 100), 0.0),
}


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
            detail = MODE[detail]
        if attr == "loudness":
            detail = f"[ {detail} dB ]"
        if attr == "tempo":
            detail = f"[ {detail} BPM ]"
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
    song_start_time = datetime.datetime.utcfromtimestamp(song.timestamp / 1000)
    end_time = datetime.datetime.utcfromtimestamp((song.timestamp + song.item.duration_ms) / 1000)
    total_time = end_time - song_start_time
    current_time = datetime.datetime.utcnow()
    elapsed_time = current_time - song_start_time
    sections = 12
    loc_time = round((elapsed_time / total_time) * sections)  # 10 sections

    bar_char = "\N{BOX DRAWINGS HEAVY HORIZONTAL}"
    seek_char = "\N{RADIO BUTTON}"
    play_char = "\N{BLACK RIGHT-POINTING TRIANGLE}"
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


class RecommendationsConverter(Converter):
    """
    This ensures that we are using valid genres
    """

    async def convert(self, ctx: commands.Context, argument: str) -> dict:
        query = {}
        rec_str = r"|".join(i for i in VALID_RECOMMENDATIONS.keys())
        find_rec = re.compile(fr"({rec_str})\W(.+)", flags=re.I)
        if not ctx.cog.GENRES:
            try:
                ctx.cog.GENRES = await ctx.cog._spotify_client.recommendation_genre_seeds()
            except Exception:
                raise BadArgument(
                    _(
                        "The bot owner needs to set their Spotify credentials "
                        "before this command can be used."
                        " See `{prefix}spotify set creds` for more details."
                    ).format(prefix=ctx.clean_prefix)
                )
        genre_str = r"|".join(i for i in ctx.cog.GENRES)
        find_genre = re.compile(fr"\b({genre_str})\b", flags=re.I)
        find_extra = find_rec.finditer(argument)
        genres = list(find_genre.findall(argument))
        song_data = SPOTIFY_RE.finditer(argument)
        tracks: List[str] = []
        artists: List[str] = []
        if song_data:
            for match in song_data:
                if match.group(2) == "track":
                    tracks.append(match.group(3))
                if match.group(2) == "artist":
                    tracks.append(match.group(3))
        query = {
            "artist_ids": artists if artists else None,
            "genres": genres if genres else None,
            "track_ids": tracks if tracks else None,
            "limit": 100,
            "market": "from_token",
        }
        for match in find_extra:
            try:
                num_or_str = match.group(2).isdigit()
                if num_or_str:
                    result = VALID_RECOMMENDATIONS[match.group(1)](int(match.group(2)))
                else:
                    result = VALID_RECOMMENDATIONS[match.group(1)](match.group(2))
                query[f"target_{match.group(1)}"] = result
            except Exception:
                log.exception("cannot match")
                continue
        if not any([query[k] for k in ["artist_ids", "genres", "track_ids"]]):
            raise BadArgument(
                _("You must provide either an artist or track seed or a genre for this to work")
            )
        return query


class SpotifyURIConverter(Converter):
    """
    Ensures that the argument is a valid spotify URL or URI
    """

    async def convert(self, ctx: commands.Context, argument: str) -> re.Match:
        match = SPOTIFY_RE.match(argument)
        if not match:
            raise BadArgument(
                _("{argument} is not a valid Spotify URL or URI.").format(argument=argument)
            )
        return match
