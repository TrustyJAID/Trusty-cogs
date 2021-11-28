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
                }
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
                    ]
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
                    ]
                }
            ],
        },
        {
            "name": "play",
            "description": "Play a track, playlist, or album on Spotify",
            "type": 1,
            "options":[
                {
                    "name": "url_or_playlist_name",
                    "type": 3,
                    "description": "The Spotify URL or playlist name you want to play.",
                    "required": False
                }
            ]
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
                    "required": True
                }
            ]
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
                    "name": "recommendations",
                    "type": 3,
                    "description": "Must be a genre, track, or artist",
                    "required": True,
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
                        {"name": "name", "description": "The name of the playlist you want to add a track to.", "type": 3, "required": True},
                        {"name": "to_add", "description": "The link to the song you want to add to the playlist.", "type": 3, "required": True},
                    ]
                },
                {
                    "name": "create",
                    "description": "Create a Spotify Playlist.",
                    "type": 1,
                    "options": [
                        {"name": "name","description":"The name of the new playlist.", "type": 3, "required": True},
                        {"name": "public","description":"Whether or not the playlist should be public.", "type": 5, "required": False},
                        {"name": "description","description":"A short description of the new playlist", "type": 3, "required": False},
                    ]
                },
                {
                    "name": "follow",
                    "description": "List your available Spotify Devices.",
                    "type": 1,
                    "options": [

                        {"name": "to_follow","description":"The playlist link you want to follow", "type": 3, "required": True},
                        {"name": "public","description":"Whether or not the followed playlist should be public.", "type": 5, "required": False},
                    ]
                },
                {
                    "name": "remove",
                    "description": "List your available Spotify Devices.",
                    "type": 1,
                    "Options": [
                        {"name": "name", "description": "The name of the playlist you want to remove a track from.", "type": 3, "required": True},
                        {"name": "to_remove", "description": "The link to the song you want to remove from the playlist.", "type": 3, "required": True},
                    ]
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
                    ]
                },
                {
                    "name": "list",
                    "description": "List your available Spotify Devices.",
                    "type": 1,
                },
            ],
        },
        {
            "name": "set",
            "description": "Set Spotify Options",
            "type": 2,
            "options": [
                {
                    "name": "forgetme",
                    "type": 1,
                    "description": "Forget all your spotify settings and credentials on the bot.",
                }
            ],
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
            ]
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
            ]
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
            ]
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
            ]
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
