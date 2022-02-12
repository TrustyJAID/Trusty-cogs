SLASH_COMMANDS = {
    "name": "retrigger",
    "description": "Setup automatic triggers based on regular expressions",
    "options": [
        {
            "name": "remove",
            "description": "Remove a specified trigger",
            "type": 1,
            "options": [
                {
                    "name": "trigger",
                    "description": ".",
                    "type": 3,
                    "required": True,
                    "autocomplete": True,
                }
            ],
        },
        {
            "name": "modlog",
            "description": "Set which events to record in the modlog.",
            "type": 2,
            "options": [
                {
                    "name": "removeroles",
                    "description": "Toggle custom add role messages in the modlog",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "channel",
                    "description": "Set the modlog channel for filtered words",
                    "type": 1,
                    "options": [
                        {
                            "name": "channel",
                            "description": "The channel to send retrigger modlog entries to.",
                            "type": 7,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "kicks",
                    "description": "Toggle custom kick messages in the modlog",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "bans",
                    "description": "Toggle custom ban messages in the modlog",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "filter",
                    "description": "Toggle custom filter messages in the modlog",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "settings",
                    "description": "Show the current modlog settings for this server.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "addroles",
                    "description": "Toggle custom add role messages in the modlog",
                    "type": 1,
                    "options": [],
                },
            ],
        },
        {
            "name": "publish",
            "description": "Add a trigger to automatically publish content in news channels.",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "explain",
            "description": "Explain how to use retrigger",
            "type": 1,
            "options": [
                {
                    "name": "page_num",
                    "description": ".",
                    "type": 3,
                    "required": False,
                }
            ],
        },
        {
            "name": "filter",
            "description": "Add a trigger to delete a message",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "check_filenames",
                    "description": ".",
                    "type": 5,
                    "required": False,
                },
            ],
        },
        {
            "name": "mock",
            "description": "Add a trigger for command as if you used the command",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "command",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "text",
            "description": "Add a text response trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "text",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "delete_after",
                    "description": "seconds",
                    "type": 4,
                    "required": False,
                },
            ],
        },
        {
            "name": "allowlist",
            "description": "Set allowlist options for retrigger",
            "type": 2,
            "options": [
                {
                    "name": "remove",
                    "description": "Remove a channel, user, or role from triggers allowlist",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "channel_user_role",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "add",
                    "description": "Add a channel, user, or role to triggers allowlist",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "channel_user_role",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
            ],
        },
        {
            "name": "dm",
            "description": "Add a dm response trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "text",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "addrole",
            "description": "Add a trigger to add a role",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "roles",
                    "description": ".",
                    "type": 8,
                    "required": True,
                },
            ],
        },
        {
            "name": "ban",
            "description": "Add a trigger to ban users for saying specific things found with regex",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "dmme",
            "description": "Add trigger to DM yourself",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "text",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "edit",
            "description": "Edit various settings in a set trigger.",
            "type": 2,
            "options": [
                {
                    "name": "disable",
                    "description": "Disable a trigger",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "text",
                    "description": "Edit the text of a saved trigger.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "text",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "rolemention",
                    "description": "Set whether or not to send this trigger will allow role mentions",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "set_to",
                            "description": ".",
                            "type": 5,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "edited",
                    "description": "Toggle whether the bot will listen to edited messages as well as on_message for",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "cooldown",
                    "description": "Set cooldown options for retrigger",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "time",
                            "description": ".",
                            "type": 4,
                            "required": True,
                        },
                        {
                            "name": "style",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "choices": [
                                {"name": "Guild", "value": "guild"},
                                {"name": "Server", "value": "server"},
                                {"name": "Channel", "value": "channel"},
                                {"name": "User", "value": "user"},
                                {"name": "Member", "value": "member"},
                            ],
                        },
                    ],
                },
                {
                    "name": "deleteafter",
                    "description": "Edit the delete_after parameter of a saved text trigger.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "delete_after",
                            "description": ".",
                            "type": 4,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "chance",
                    "description": "Edit the chance a trigger will execute.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "chance",
                            "description": "1 in chance",
                            "type": 4,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "command",
                    "description": "Edit the text of a saved trigger.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "command",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "ignorecommands",
                    "description": "Toggle the trigger ignoring command messages entirely.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "react",
                    "description": "Edit the emoji reactions of a saved trigger.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "emojis",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "regex",
                    "description": "Edit the regex of a saved trigger.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "regex",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "role",
                    "description": "Edit the added or removed roles of a saved trigger.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "roles",
                            "description": ".",
                            "type": 8,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "everyonemention",
                    "description": "Set whether or not to send this trigger will allow everyone mentions",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "set_to",
                            "description": ".",
                            "type": 5,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "ocr",
                    "description": "Toggle whether to use Optical Character Recognition.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "readfilenames",
                    "description": "Toggle whether to search message attachment filenames.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "usermention",
                    "description": "Set whether or not to mention users in the reply",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "set_to",
                            "description": ".",
                            "type": 5,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "nsfw",
                    "description": "Toggle whether a trigger is considered NSFW.",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "reply",
                    "description": "Set whether or not to reply to the triggered message",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "set_to",
                            "description": ".",
                            "type": 5,
                            "required": False,
                        },
                    ],
                },
                {
                    "name": "enable",
                    "description": "Enable a trigger that has been disabled either by command or automatically",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        }
                    ],
                },
                {
                    "name": "tts",
                    "description": "Set whether or not to send the message with text-to-speech",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "set_to",
                            "description": ".",
                            "type": 5,
                            "required": True,
                        },
                    ],
                },
            ],
        },
        {
            "name": "removerole",
            "description": "Add a trigger to remove a role",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "roles",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "rename",
            "description": "Add trigger to rename users",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "text",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "multi",
            "description": "Add a multiple response trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "multi_response",
                    "description": "See `[p]help retrigger multi`",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "react",
            "description": "Add a reaction trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "emojis",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "blocklist",
            "description": "Set blocklist options for retrigger",
            "type": 2,
            "options": [
                {
                    "name": "remove",
                    "description": "Remove a channel, user, or role from triggers blocklist",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "channel_user_role",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "add",
                    "description": "Add a channel, user, or role to triggers blocklist",
                    "type": 1,
                    "options": [
                        {
                            "name": "trigger",
                            "description": ".",
                            "type": 3,
                            "required": True,
                            "autocomplete": True,
                        },
                        {
                            "name": "channel_user_role",
                            "description": ".",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
            ],
        },
        {
            "name": "image",
            "description": "Add an image/file response trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "image_url",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "list",
            "description": "List information about triggers.",
            "type": 1,
            "options": [
                {
                    "name": "trigger",
                    "description": ".",
                    "type": 3,
                    "required": False,
                    "autocomplete": True,
                },
                {
                    "name": "guild_id",
                    "description": "Bot owner only, the guild ID to lookup triggers.",
                    "type": 3,
                    "required": False,
                },
            ],
        },
        {
            "name": "resize",
            "description": "Add an image to resize in response to a trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "image_url",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "imagetext",
            "description": "Add an image/file response with text trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "text",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "image_url",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "command",
            "description": "Add a command trigger",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "command",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
        {
            "name": "kick",
            "description": "Add a trigger to kick users for saying specific things found with regex",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "regex",
                    "description": ".",
                    "type": 3,
                    "required": True,
                },
            ],
        },
    ],
}
