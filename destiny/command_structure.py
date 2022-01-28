SLASH_COMMANDS = {
    "name": "destiny",
    "description": "Get information from the Destiny 2 API",
    "options": [
        {
            "name": "pvp",
            "description": "Display a menu of each character's pvp stats",
            "type": 1,
            "options": [],
        },
        {
            "name": "banshee",
            "description": "Display Banshee-44's wares",
            "type": 1,
            "options": [],
        },
        {
            "name": "gambit",
            "description": "Display a menu of each characters gambit stats",
            "type": 1,
            "options": [],
        },
        {
            "name": "reset",
            "description": "Show approximately when Weekly and Daily reset is",
            "type": 1,
            "options": [],
        },
        {
            "name": "search",
            "description": "Search for a destiny item, vendor, record, etc.",
            "type": 2,
            "options": [
                {
                    "name": "items",
                    "description": "Search for a specific item in Destiny 2",
                    "type": 1,
                    "options": [
                        {
                            "name": "search",
                            "description": "The item to lookup.",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "details_or_lore",
                            "description": "Whether to display details or lore of the item.",
                            "type": 3,
                            "required": False,
                            "choices": [
                                {"name": "lore", "value": "lore"},
                                {"name": "details", "value": "True"},
                            ],
                        },
                    ],
                },
                {
                    "name": "lore",
                    "description": "Find Destiny Lore",
                    "type": 1,
                    "options": [
                        {
                            "name": "entry",
                            "description": "The Lore entry you want to read.",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
            ],
        },
        {
            "name": "raid",
            "description": "Display a menu for each character's RAID stats",
            "type": 1,
            "options": [],
        },
        {
            "name": "history",
            "description": "Display a menu of each character's last 5 activities",
            "type": 1,
            "options": [
                {
                    "name": "activity",
                    "description": "The activity type you want to see history of.",
                    "type": 3,
                    "required": True,
                    "autocomplete": True,
                }
            ],
        },
        {
            "name": "loadout",
            "description": "Display a menu of each character's equipped weapons and their info",
            "type": 1,
            "options": [
                {
                    "name": "user",
                    "description": "The user whose loadout you want to see.",
                    "type": 6,
                    "required": False,
                },
                {
                    "name": "full",
                    "description": "Whether or not to display the full information.",
                    "type": 5,
                    "required": False,
                },
            ],
        },
        {
            "name": "forgetme",
            "description": "Remove your authorization to the destiny API on the bot",
            "type": 1,
            "options": [],
        },
        {
            "name": "ada-1",
            "description": "Display Ada-1's wares",
            "type": 1,
            "options": [
                {
                    "name": "character",
                    "description": "The character class you want to view the inventory for.",
                    "type": 3,
                    "required": False,
                    "choices": [
                        {"name": "Hunter", "value": "hunter"},
                        {"name": "Titan", "value": "titan"},
                        {"name": "Warlock", "value": "warlock"},
                    ],
                }
            ],
        },
        {"name": "spider", "description": "Display Spiders wares", "type": 1, "options": []},
        {
            "name": "stats",
            "description": "Display each character's stats for a specific activity",
            "type": 1,
            "options": [
                {
                    "name": "stat_type",
                    "description": "The type of stats you want to see.",
                    "type": 3,
                    "required": True,
                    "choices": [
                        {"name": "All PVP", "value": "allPvP"},
                        {"name": "Patrol", "value": "patrol"},
                        {"name": "Raids", "value": "raid"},
                        {"name": "Story", "value": "story"},
                        {"name": "Strikes", "value": "allStrikes"},
                        {"name": "PVE", "value": "allPvE"},
                        {"name": "Gambit", "value": "allPvECompetitive"},
                    ],
                },
            ],
        },
        {
            "name": "clan",
            "description": "Clan settings",
            "type": 2,
            "options": [
                {
                    "name": "pending",
                    "description": "Display pending clan members.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "info",
                    "description": "Display basic information about the clan set in this server",
                    "type": 1,
                    "options": [
                        {
                            "name": "clan_id",
                            "description": "Your clan ID or URL to your clan page.",
                            "type": 3,
                            "required": False,
                        }
                    ],
                },
                {
                    "name": "set",
                    "description": "Set the clan ID for this server",
                    "type": 1,
                    "options": [
                        {
                            "name": "clan_id",
                            "description": "Your clan ID or URL to your clan page.",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "roster",
                    "description": "Get the full clan roster",
                    "type": 1,
                    "options": [
                        {
                            "name": "output_format",
                            "description": "The output format if required either csv or md.",
                            "type": 3,
                            "required": False,
                            "choices": [
                                {"name": "CSV", "value": "csv"},
                                {"name": "Markdown", "value": "md"},
                            ],
                        }
                    ],
                },
            ],
        },
        {
            "name": "quickplay",
            "description": "Display a menu of past quickplay matches",
            "type": 1,
            "options": [],
        },
        {
            "name": "xur",
            "description": "Display a menu of X\u00fbr's current wares",
            "type": 1,
            "options": [
                {
                    "name": "full",
                    "description": "Whether to display full information from xur.",
                    "type": 5,
                    "required": False,
                }
            ],
        },
        {
            "name": "whereisxur",
            "description": "Show X\u00fbr's current location.",
            "type": 1,
        },
        {
            "name": "user",
            "description": "Display a menu of your basic character's info",
            "type": 1,
            "options": [
                {
                    "name": "user",
                    "description": "Someone other than yourself you would like to lookup if they've registered.",
                    "type": 6,
                    "required": False,
                }
            ],
        },
        {
            "name": "eververse",
            "description": "Display items currently available on the Eververse in a menu",
            "type": 1,
            "options": [
                {
                    "name": "item_types",
                    "description": "The item type from eververse to display.",
                    "type": 4,
                    "required": False,
                    "choices": [
                        {"name": "Consumable", "value": 9},
                        {"name": "Ship", "value": 21},
                        {"name": "Vehicle", "value": 22},
                        {"name": "Ghost", "value": 24},
                        {"name": "Finisher", "value": 29},
                    ],
                }
            ],
        },
        {
            "name": "joinme",
            "description": "Get your Steam ID to give people to join your in-game fireteam",
            "type": 1,
            "options": [],
        },
        {"name": "rahool", "description": "Display Rahools wares", "type": 1, "options": []},
    ],
}
