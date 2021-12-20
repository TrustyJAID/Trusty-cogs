SLASH_COMMANDS = {
    "name": "spotify",
    "description": "Spotify Interactions",
    "options": [
        {
            "name": "now",
            "description": "Your current Spotify Player",
            "type": 1,
            "options": [
                {
                    "name": "detailed",
                    "type": 5,
                    "description": "Show a detailed view of your current songs",
                    "required": False,
                },
                {
                    "name": "member",
                    "type": 6,
                    "description": "A discord user with a current spotify status.",
                    "required": False,
                },
            ],
        },
        {
            "name": "artist",
            "description": "View Spotify Artist info",
            "type": 2,
            "options": [
                {
                    "name": "follow",
                    "type": 1,
                    "description": "Add an artist to your Spotify library.",
                    "options": [
                        {
                            "name": "to_follow",
                            "description": "The artist link you want to follow.",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "albums",
                    "type": 1,
                    "description": "View an artists albums.",
                    "options": [
                        {
                            "name": "to_follow",
                            "description": "The artist link you want to view albums for.",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
            ],
        },
        {
            "name": "play",
            "description": "Play a track, playlist, or album on Spotify",
            "type": 1,
            "options": [
                {
                    "name": "url_or_playlist_name",
                    "type": 3,
                    "description": "The Spotify URL or playlist name you want to play.",
                    "required": False,
                }
            ],
        },
        {
            "name": "genres",
            "description": "Display all available genres for recommendations",
            "type": 1,
        },
        {
            "name": "next",
            "description": "Skips to the next track in queue on Spotify",
            "type": 1,
        },
        {
            "name": "previous",
            "description": "Skips to the previous track in queue on Spotify",
            "type": 1,
        },
        {
            "name": "queue",
            "description": "Queue a song on Spotify",
            "type": 1,
            "options": [
                {
                    "name": "songs",
                    "type": 3,
                    "description": "The song URL you want to queue to play after the current song.",
                    "required": True,
                }
            ],
        },
        {
            "name": "recent",
            "description": "Displays your most recently played songs on Spotify",
            "type": 1,
            "options": [
                {
                    "name": "detailed",
                    "type": 5,
                    "description": "Show a detailed view of your current songs",
                    "required": False,
                }
            ],
        },
        {
            "name": "recommendations",
            "description": "Get Spotify Recommendations",
            "type": 1,
            "options": [
                {
                    "name": "genres",
                    "type": 3,
                    "description": "Must be any combination of valid genres used as the seed.",
                    "required": True,
                    "autocomplete": True,
                },
                {
                    "name": "tracks",
                    "type": 3,
                    "description": "Any Spotify track URL used as the seed.",
                    "required": False,
                },
                {
                    "name": "artists",
                    "type": 3,
                    "description": "Any Spotify artist URL used as the seed.",
                    "required": False,
                },
                {
                    "name": "acousticness",
                    "type": 4,
                    "description": "A value from 0 to 100 the target acousticness of the tracks.",
                    "required": False,
                },
                {
                    "name": "danceability",
                    "type": 4,
                    "description": "A value from 0 to 100 describing how danceable the tracks are.",
                    "required": False,
                },
                {
                    "name": "energy",
                    "type": 4,
                    "description": "Energy is a measure from 0 to 100 and represents a perceptual measure of intensity and activity",
                    "required": False,
                },
                {
                    "name": "instrumentalness",
                    "type": 4,
                    "description": "A value from 0 to 100 representing whether or not a track contains vocals.",
                    "required": False,
                },
                {
                    "name": "key",
                    "type": 3,
                    "description": "The target key of the tracks.",
                    "required": False,
                    "choices": [
                        {"name": "C (also B♯, Ddouble flat)", "value": "0"},
                        {"name": "C♯, D♭ (also Bdouble sharp)", "value": "1"},
                        {"name": "D (also Cdouble sharp, Edouble flat)", "value": "2"},
                        {"name": "D♯, E♭ (also Fdouble flat)", "value": "3"},
                        {"name": "E (also Ddouble sharp, F♭)", "value": "4"},
                        {"name": "F (also E♯, Gdouble flat)", "value": "5"},
                        {"name": "F♯, G♭ (also Edouble sharp)", "value": "6"},
                        {"name": "G (also Fdouble sharp, Adouble flat)", "value": "7"},
                        {"name": "G♯, A♭", "value": "8"},
                        {"name": "A (also Gdouble sharp, Bdouble flat)", "value": "9"},
                        {"name": "A♯, B♭ (also Cdouble flat)", "value": "10"},
                        {"name": "B (also Adouble sharp, C♭)", "value": "11"},
                    ]
                },
                {
                    "name": "liveness",
                    "type": 4,
                    "description": "A value from 0-100 representing the presence of an audience in the recording.",
                    "required": False,
                },
                {
                    "name": "loudness",
                    "type": 4,
                    "description": "The overall loudness of a track in decibels (dB) between -60 and 0 db.",
                    "required": False,
                },
                {
                    "name": "mode",
                    "type": 3,
                    "description": "The target modality (major or minor) of the track.",
                    "required": False,
                    "choices": [
                        {"name": "major", "value": "1"},
                        {"name": "minor", "value": "0"},
                    ]
                },
                {
                    "name": "popularity",
                    "type": 4,
                    "description": "A value from 0-100 the target popularity of the tracks.",
                    "required": False,
                },
                {
                    "name": "speechiness",
                    "type": 4,
                    "description": "A value from 0-100 Speechiness is the presence of spoken words in a track.",
                    "required": False,
                },
                {
                    "name": "tempo",
                    "type": 4,
                    "description": "The overall estimated tempo of a track in beats per minute (BPM).",
                    "required": False,
                },
                {
                    "name": "time_signature",
                    "type": 4,
                    "description": "The time signature ranges from 3 to 7 indicating time signatures of '3/4', to '7/4'.",
                    "required": False,
                },
                {
                    "name": "valence",
                    "type": 4,
                    "description": "A measure from 0 to 100 describing the musical positiveness conveyed by a track",
                    "required": False,
                },
                {
                    "name": "detailed",
                    "type": 5,
                    "description": "Show a detailed view of the recommended songs",
                    "required": False,
                },
            ],
        },
        {"name": "pause", "description": "Pauses Spotify for you", "type": 1},
        {"name": "me", "description": "Shows your current Spotify Settings", "type": 1},
        {
            "name": "playlist",
            "description": "View Spotify Playlists",
            "type": 2,
            "options": [
                {
                    "name": "list",
                    "description": "List your Spotify Playlists.",
                    "type": 1,
                },
                {
                    "name": "featured",
                    "description": "List your Spotify featured Playlists.",
                    "type": 1,
                },
                {
                    "name": "add",
                    "description": "Add a track to a Spotify playlist.",
                    "type": 1,
                    "Options": [
                        {
                            "name": "name",
                            "description": "The name of the playlist you want to add a track to.",
                            "type": 3,
                            "required": True,
                        },
                        {
                            "name": "to_add",
                            "description": "The link to the song you want to add to the playlist.",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "create",
                    "description": "Create a Spotify Playlist.",
                    "type": 1,
                    "options": [
                        {
                            "name": "name",
                            "description": "The name of the new playlist.",
                            "type": 3,
                            "required": True,
                        },
                        {
                            "name": "public",
                            "description": "Whether or not the playlist should be public.",
                            "type": 5,
                            "required": False,
                        },
                        {
                            "name": "description",
                            "description": "A short description of the new playlist",
                            "type": 3,
                            "required": False,
                        },
                    ],
                },
                {
                    "name": "follow",
                    "description": "List your available Spotify Devices.",
                    "type": 1,
                    "options": [
                        {
                            "name": "to_follow",
                            "description": "The playlist link you want to follow",
                            "type": 3,
                            "required": True,
                        },
                        {
                            "name": "public",
                            "description": "Whether or not the followed playlist should be public.",
                            "type": 5,
                            "required": False,
                        },
                    ],
                },
                {
                    "name": "remove",
                    "description": "List your available Spotify Devices.",
                    "type": 1,
                    "Options": [
                        {
                            "name": "name",
                            "description": "The name of the playlist you want to remove a track from.",
                            "type": 3,
                            "required": True,
                        },
                        {
                            "name": "to_remove",
                            "description": "The link to the song you want to remove from the playlist.",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "view",
                    "description": "View details about your spotify playlists.",
                    "type": 1,
                },
            ],
        },
        {"name": "new", "description": "List new releases on Spotify", "type": 1},
        {
            "name": "device",
            "description": "Spotify Device commands",
            "type": 2,
            "options": [
                {
                    "name": "transfer",
                    "description": "Transfer Spotify playback to a designated device.",
                    "type": 1,
                    "options": [
                        {
                            "name": "device_name",
                            "description": "The name of the device you want to transfer Spotify playback to.",
                            "type": 3,
                            "required": False,
                        }
                    ],
                },
                {
                    "name": "list",
                    "description": "List your available Spotify Devices.",
                    "type": 1,
                },
            ],
        },
        {
            "name": "forgetme",
            "description": "Forget all your spotify settings and credentials on the bot.",
            "type": 1,
        },
        {
            "name": "repeat",
            "description": "Change your current repeat setting on Spotify.",
            "type": 1,
            "options": [
                {
                    "name": "state",
                    "type": 3,
                    "description": "Repeat state",
                    "choices": [
                        {"name": "Context", "value": "context"},
                        {"name": "Off", "value": "off"},
                        {"name": "Track", "value": "track"},
                    ],
                    "required": False,
                },
            ],
        },
        {
            "name": "shuffle",
            "description": "Change your current shuffle setting on Spotify.",
            "type": 1,
            "options": [
                {
                    "name": "state",
                    "type": 5,
                    "description": "Shuffle State",
                    "required": False,
                },
            ],
        },
        {
            "name": "seek",
            "description": "Seek to a specific point in the current song.",
            "type": 1,
            "options": [
                {
                    "name": "seconds",
                    "type": 3,
                    "description": "Seconds or a value formatted like 00:00:00 (hh:mm:ss)",
                    "required": True,
                },
            ],
        },
        {
            "name": "volume",
            "description": "Set your Spotify player volume.",
            "type": 1,
            "options": [
                {
                    "name": "volume",
                    "type": 4,
                    "description": "A number between 0 and 100 for volume percentage.",
                    "required": True,
                },
            ],
        },
        {
            "name": "search",
            "description": "Search Spotify for things to play",
            "type": 1,
            "options": [
                {
                    "name": "search_type",
                    "type": 3,
                    "description": "The search type",
                    "choices": [
                        {"name": "Track", "value": "track"},
                        {"name": "Artist", "value": "artist"},
                        {"name": "Album", "value": "album"},
                        {"name": "Playlist", "value": "playlist"},
                        {"name": "Show", "value": "show"},
                        {"name": "Episode", "value": "episode"},
                    ],
                    "required": True,
                },
                {
                    "name": "query",
                    "type": 3,
                    "description": "What you want to search for",
                    "required": True,
                },
                {
                    "name": "detailed",
                    "type": 5,
                    "description": "Show detailed view of your search",
                    "required": False,
                },
            ],
        },
    ],
}
