SLASH_COMMANDS = {
    "name": "event",
    "description": "All event related commands.",
    "options": [
        {
            "name": "join",
            "description": "Join an event being hosted",
            "type": 1,
            "options": [
                {
                    "name": "hoster",
                    "description": "The person whose event you want to join.",
                    "type": 6,
                    "required": True,
                }
            ],
        },
        {
            "name": "make",
            "description": "Create an event",
            "type": 1,
            "options": [
                {
                    "name": "description",
                    "description": "What do you want to advertise the event as?",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "members",
                    "description": "Do you already have members ready to go?",
                    "type": 6,
                    "required": False,
                },
                {
                    "name": "max_slots",
                    "description": "What is the maximum slots for you event?",
                    "type": 4,
                    "required": False,
                },
            ],
        },
        {
            "name": "show",
            "description": "Show current event being run by a member",
            "type": 1,
            "options": [
                {
                    "name": "member",
                    "description": "Whose event do you want to see?",
                    "type": 6,
                    "required": True,
                }
            ],
        },
        {
            "name": "ping",
            "description": "Ping all the registered users for your event including optional message",
            "type": 1,
            "options": [
                {
                    "name": "include_maybe",
                    "description": "Include the members registered as maybe?",
                    "type": 5,
                    "required": False,
                },
                {
                    "name": "message",
                    "description": "What message do you want to send with the ping?",
                    "type": 3,
                    "required": False,
                },
            ],
        },
        {
            "name": "edit",
            "description": "Edit various things in events",
            "type": 2,
            "options": [
                {
                    "name": "memberadd",
                    "description": "Add members to your event (hopefully not against their will)",
                    "type": 1,
                    "options": [
                        {
                            "name": "new_members",
                            "description": "The member you want to add to the event.",
                            "type": 6,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "memberremove",
                    "description": "Remove members from your event (hopefully not against their will)",
                    "type": 1,
                    "options": [
                        {
                            "name": "members",
                            "description": "The member you want to remove from the event.",
                            "type": 6,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "title",
                    "description": "Edit the title of your event",
                    "type": 1,
                    "options": [
                        {
                            "name": "new_description",
                            "description": "The new event title you want to use.",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "slots",
                    "description": "Edit the number of slots available for your event",
                    "type": 1,
                    "options": [
                        {
                            "name": "new_slots",
                            "description": "The new event slots you want to use.",
                            "type": 4,
                            "required": False,
                        }
                    ],
                },
                {
                    "name": "remaining",
                    "description": "Show how long until your event will be automatically ended if available.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "maybeadd",
                    "description": "Add members to your events maybe list",
                    "type": 1,
                    "options": [
                        {
                            "name": "new_members",
                            "description": "The members you want to add to your events maybe list.",
                            "type": 6,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "mayberemove",
                    "description": "Remove members from your events maybe list",
                    "type": 1,
                    "options": [
                        {
                            "name": "members",
                            "description": "The members you want to remove from your maybe list.",
                            "type": 6,
                            "required": True,
                        }
                    ],
                },
            ],
        },
        {
            "name": "set",
            "description": "Manage server specific settings for events",
            "type": 2,
            "options": [
                {
                    "name": "channel",
                    "description": "Set the Announcement channel for events",
                    "type": 1,
                    "options": [
                        {
                            "name": "channel",
                            "description": "The channel you want set for announcements.",
                            "type": 7,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "bypass",
                    "description": "Set whether or not admin approval is required for events to be posted.",
                    "type": 1,
                    "options": [
                        {
                            "name": "true_or_false",
                            "description": "Whether you want to bypass confirmation of events by admins.",
                            "type": 5,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "class",
                    "description": "Set's the users default player class. If nothing is provided this will be rest.",
                    "type": 1,
                    "options": [
                        {
                            "name": "player_class",
                            "description": "What do you want your playerclass to be set to as default?",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "roles",
                    "description": "Set the roles that are allowed to create events",
                    "type": 1,
                    "options": [
                        {
                            "name": "roles",
                            "description": "What role should be allowed to create events?",
                            "type": 8,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "defaultmax",
                    "description": "Set's the servers default maximum slots",
                    "type": 1,
                    "options": [
                        {
                            "name": "max_slots",
                            "description": "What should be the default maximum slots for all events?",
                            "type": 4,
                            "required": False,
                        }
                    ],
                },
                {
                    "name": "thread",
                    "description": "Set whether or not to turn the announcement message into a thread",
                    "type": 1,
                    "options": [
                        {
                            "name": "true_or_false",
                            "description": "Should a thread be created for each new event?",
                            "type": 5,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "links",
                    "description": "Set the custom thumbnail for events",
                    "type": 1,
                    "options": [
                        {
                            "name": "keyword",
                            "description": "The keyword looked for when events are created.",
                            "type": 3,
                            "required": True,
                        },
                        {
                            "name": "link",
                            "description": "The image URL used when a keyword is found in an event title.",
                            "type": 3,
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "ping",
                    "description": "Set the ping to use when an event is announced",
                    "type": 1,
                    "options": [
                        {
                            "name": "roles",
                            "description": "What do you want pinged on all events?",
                            "type": 9,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "maxevents",
                    "description": "Set the maximum number of events the server can host.",
                    "type": 1,
                    "options": [
                        {
                            "name": "number_of_events",
                            "description": "Maximum number of allowed events in the server.",
                            "type": 4,
                            "required": False,
                        }
                    ],
                },
                {
                    "name": "approvalchannel",
                    "description": "Set the admin approval channel",
                    "type": 1,
                    "options": [
                        {
                            "name": "channel",
                            "description": "The approval channel that ideally only mods and admins can see.",
                            "type": 7,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "viewlinks",
                    "description": "Show custom thumbnails available for events in this server",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "settings",
                    "description": "Show the current event settings.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "cleanup",
                    "description": "Set the events cleanup interval.",
                    "type": 1,
                    "options": [
                        {"name": "time", "description": "test", "type": 3, "required": False}
                    ],
                },
                {
                    "name": "remove",
                    "description": "Remove and end a current event.",
                    "type": 1,
                    "options": [
                        {
                            "name": "hoster_or_message",
                            "description": "The host of the event or the announcement message of the event.",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "removeplayerclass",
                    "description": "Add a playerclass choice for users to pick from for this server.",
                    "type": 1,
                    "options": [
                        {
                            "name": "player_class",
                            "description": "The name of the player class you want to remove from the list.",
                            "type": 3,
                            "required": True,
                        }
                    ],
                },
                {
                    "name": "playerclasslist",
                    "description": "List the playerclass choices in this server.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "addplayerclass",
                    "description": "Add a playerclass choice for users to pick from for this server.",
                    "type": 1,
                    "options": [
                        {
                            "name": "player_class",
                            "description": "The name of the playerclass that is listed.",
                            "type": 3,
                            "required": True,
                        },
                        {"name": "emoji", "description": "test", "type": 3, "required": False},
                    ],
                },
            ],
        },
        {
            "name": "leave",
            "description": "Leave an event being hosted",
            "type": 1,
            "options": [
                {
                    "name": "hoster",
                    "description": "The user who is hosting the event you want to leave.",
                    "type": 6,
                    "required": True,
                }
            ],
        },
        {
            "name": "clear",
            "description": "Delete a stored event so you can create more",
            "type": 1,
            "options": [
                {
                    "name": "clear",
                    "description": "Clear your existing event and mark it as complete.",
                    "type": 3,
                    "required": True,
                }
            ],
        },
    ],
}
