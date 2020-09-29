import re
import discord
import datetime
import tekore
import logging

from tabulate import tabulate
from typing import Literal

from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify, humanize_timedelta
from redbot.core.i18n import Translator, cog_i18n

from discord.ext.commands.converter import Converter, IDConverter, RoleConverter
from discord.ext.commands.errors import BadArgument

log = logging.getLogger("red.trusty-cogs.spotify")

SPOTIFY_RE = re.compile(
    r"(https?:\/\/open\.spotify\.com\/|spotify:)(track|playlist|album|artist|episode|show)\/?:?([^?\(\)\s]+)"
)

ACTION_EMOJIS = {
    "play": "\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    "repeat": "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
    "repeatone": "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}",
    "next": "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    "previous": "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    "like": "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}",
}
LOOKUP = {v: k for k, v in ACTION_EMOJIS.items()}

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

VALID_GENRES = [
    "acoustic",
    "afrobeat",
    "alt-rock",
    "alternative",
    "ambient",
    "anime",
    "black-metal",
    "bluegrass",
    "blues",
    "bossanova",
    "brazil",
    "breakbeat",
    "british",
    "cantopop",
    "chicago-house",
    "children",
    "chill",
    "classical",
    "club",
    "comedy",
    "country",
    "dance",
    "dancehall",
    "death-metal",
    "deep-house",
    "detroit-techno",
    "disco",
    "disney",
    "drum-and-bass",
    "dub",
    "dubstep",
    "edm",
    "electro",
    "electronic",
    "emo",
    "folk",
    "forro",
    "french",
    "funk",
    "garage",
    "german",
    "gospel",
    "goth",
    "grindcore",
    "groove",
    "grunge",
    "guitar",
    "happy",
    "hard-rock",
    "hardcore",
    "hardstyle",
    "heavy-metal",
    "hip-hop",
    "holidays",
    "honky-tonk",
    "house",
    "idm",
    "indian",
    "indie",
    "indie-pop",
    "industrial",
    "iranian",
    "j-dance",
    "j-idol",
    "j-pop",
    "j-rock",
    "jazz",
    "k-pop",
    "kids",
    "latin",
    "latino",
    "malay",
    "mandopop",
    "metal",
    "metal-misc",
    "metalcore",
    "minimal-techno",
    "movies",
    "mpb",
    "new-age",
    "new-release",
    "opera",
    "pagode",
    "party",
    "philippines-opm",
    "piano",
    "pop",
    "pop-film",
    "post-dubstep",
    "power-pop",
    "progressive-house",
    "psych-rock",
    "punk",
    "punk-rock",
    "r-n-b",
    "rainy-day",
    "reggae",
    "reggaeton",
    "road-trip",
    "rock",
    "rock-n-roll",
    "rockabilly",
    "romance",
    "sad",
    "salsa",
    "samba",
    "sertanejo",
    "show-tunes",
    "singer-songwriter",
    "ska",
    "sleep",
    "songwriter",
    "soul",
    "soundtracks",
    "spanish",
    "study",
    "summer",
    "swedish",
    "synth-pop",
    "tango",
    "techno",
    "trance",
    "trip-hop",
    "turkish",
    "work-out",
    "world-music",
]

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

SCOPE = tekore.Scope(
    tekore.scope.user_read_private,
    tekore.scope.user_top_read,
    tekore.scope.user_read_recently_played,
    tekore.scope.user_follow_read,
    tekore.scope.user_library_read,
    tekore.scope.user_read_currently_playing,
    tekore.scope.user_read_playback_state,
    tekore.scope.user_read_playback_position,
    tekore.scope.playlist_read_collaborative,
    tekore.scope.playlist_read_private,
    tekore.scope.user_follow_modify,
    tekore.scope.user_library_modify,
    tekore.scope.user_modify_playback_state,
    tekore.scope.playlist_modify_public,
    tekore.scope.playlist_modify_private,
    tekore.scope.ugc_image_upload,
)


class SpotifyError(Exception):
    pass


class NotPlaying(SpotifyError):
    pass


async def make_details(track: tekore.model.FullTrack, details: tekore.model.AudioFeatures):
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

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Literal["artist", "album", "episode", "playlist", "show", "track"]:
        result = []
        valid_types = [
            "artist",
            "album",
            "episode",
            "playlist",
            "show",
            "track",
        ]
        find = argument.lower()
        if find not in VALID_GENRES:
            raise BadArgument(_("{argument} is not a valid genre.").format(argument=argument))
        return find


class RecommendationsConverter(Converter):
    """
    This ensures that we are using valid genres
    """

    async def convert(self, ctx: commands.Context, argument: str) -> dict:
        query = {}
        rec_str = r"|".join(i for i in VALID_RECOMMENDATIONS.keys())
        find_rec = re.compile(
            fr"({rec_str})\W(\d+\w+)", flags=re.I
        )
        genre_str = r"|".join(i for i in VALID_GENRES)
        find_genre = re.compile(fr"\b({genre_str})\b", flags=re.I)
        find_lim = re.compile(r"limit\W(\d+)", flags=re.I)
        find_extra = find_rec.finditer(argument)
        genres = list(find_genre.findall(argument))
        song_data = SPOTIFY_RE.finditer(argument)
        tracks = []
        artists = []
        new_uri = ""
        if song_data:
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                if match.group(2) == "track":
                    tracks.append(match.group(3))
                if match.group(2) == "artist":
                    tracks.append(match.group(3))
        query = {
            "artist_ids": artists if artists else None,
            "genres": genres if genres else None,
            "track_ids": tracks if tracks else None,
            "limit": 100,
        }
        if find_extra:
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

        if False:
            raise BadArgument(
                _(
                    "{argument} is not a valid search type. You must provide one of {valid}."
                ).format(argument=argument, valid=humanize_list(valid_types))
            )
        return query


class GenreConverter(Converter):
    """
    Convert into valid recommendation attributes

    acousticness = 'acousticness'
    danceability = 'danceability'
    duration_ms = 'duration_ms'
    energy = 'energy'
    instrumentalness = 'instrumentalness'
    key = 'key'
    liveness = 'liveness'
    loudness = 'loudness'
    mode = 'mode'
    popularity = 'popularity'
    speechiness = 'speechiness'
    tempo = 'tempo'
    time_signature = 'time_signature'
    valence = 'valence'
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Literal[VALID_GENRES]:
        result = []
        find = argument.lower()
        if find.endswith("s"):
            find = find[:-1]
        if find not in valid_types:
            raise BadArgument(
                _(
                    "{argument} is not a valid search type. You must provide one of {valid}."
                ).format(argument=argument, valid=humanize_list(valid_types))
            )
        return find


class SpotifyURIConverter(Converter):
    """
    Ensures that the argument is a valid spotify URL or URI
    """

    async def convert(self, ctx: commands.Context, argument: str) -> re.Match:
        match = SPOTIFY_RE.match(argument)
        if not match:
            raise BadArgument(_("{argument} is not a valid Spotify URL or URI."))
        return match
