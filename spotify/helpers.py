import re
import discord
import datetime
import tekore

from tabulate import tabulate
from typing import Literal

from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify, humanize_timedelta

from discord.ext.commands.converter import Converter, IDConverter, RoleConverter
from discord.ext.commands.errors import BadArgument


SPOTIFY_RE = re.compile(
    r"(https?:\/\/open\.spotify\.com\/|spotify:)(track|playlist|album|artist|episode)\/?:?([^?\(\)\s]+)"
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
        argument = argument.lower()
        if argument.endswith("s"):
            argument = argument[:-1]
        if argument not in valid_types:
            raise BadArgument(
                f"{argument} is not a valid search type. You must provide one of {humanize_list(valid_types)}."
            )
        return argument
