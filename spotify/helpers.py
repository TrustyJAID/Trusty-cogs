import discord
import datetime

class SpotifyError(Exception):
    pass

class NotPlaying(SpotifyError):
    pass


def _draw_play(song: discord.Spotify) -> str:
    """
    Courtesy of aikaterna from Audio in red and away cog
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/audio/core/utilities/formatting.py#L358-L376
    """
    song_start_time = song.start
    total_time = song.duration
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

def _tekore_to_discord(song) -> discord.Spotify:
        start = song.timestamp
        end = start + song.item.duration_ms
        if song.item.type == "track":
            art = "spotify:" + song.item.album.images[0].url.split("/")[-1]
            text = song.item.album.name
            artists = "; ".join(i.name for i in song.item.artists)
        elif song.item.type == "episode":
            art = "spotify:" + song.item.images[0].url.split("/")[-1]
            text = song.item.show.name
            artists = song.item.description
        fake_spot = discord.Spotify(
            state=artists,
            details=song.item.name,
            timestamps={"start": start, "end": end},
            assets={"large_text": text, "large_image": art},
            party={},
            sync_id=song.item.id,
            session_id=None,
            created_at=None,
        )
        return fake_spot