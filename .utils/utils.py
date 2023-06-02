import glob
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional

import click
import tabulate
from babel.lists import format_list as babel_list

DEFAULT_INFO = {
    "author": [],
    "install_msg": "",
    "name": "",
    "disabled": False,
    "short": "",
    "description": "",
    "tags": [],
    "requirements": [],
    "hidden": False,
}

logging.basicConfig(filename="scripts.log", level=logging.INFO)
log = logging.getLogger(__file__)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "[{asctime}] [{levelname}] {name}: {message}",
    datefmt="%Y-%m-%d %H:%M:%S",
    style="{",
)
handler.setFormatter(formatter)
log.addHandler(handler)

ROOT = Path(__file__).parent.resolve().parents[0]

VER_REG = re.compile(r"\_\_version\_\_ = \"(\d+\.\d+\.\d+)", flags=re.I)

DEFAULT_AUTHOR = ["TrustyJAID"]


HEADER = (
    "# Trusty-cogs V3"
    "[![Red-DiscordBot](https://img.shields.io/badge/Red--DiscordBot-V3-red.svg)](https://github.com/Cog-Creators/Red-DiscordBot)"
    "[![Discord.py](https://img.shields.io/badge/Discord.py-rewrite-blue.svg)](https://github.com/Rapptz/discord.py/tree/rewrite)"
    "[![TrustyJAID](https://cdn.discordapp.com/attachments/371817142854746112/528059607705321482/Follow_me-TrustyJAID-yellow.svg)](https://trustyjaid.com/)"
    "[![Donate to help support more cog creation](https://img.shields.io/badge/Paypal-Donate-blue.svg)](https://paypal.me/TrustyJAID)"
    "[![Subscribe on Patreon](https://img.shields.io/badge/Patreon-Follow-orange.svg)](https://www.patreon.com/TrustyJAID)\n\n"
    "TrustyJAID's Cogs for  [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot/tree/V3/develop)."
    "To add the cogs to your instance please do: `[p]repo add Trusty-cogs https://github.com/TrustyJAID/Trusty-cogs/`\n"
    "## About Cogs\n"
    "{body}\n\n"
    "Any questions you can find [TrustyBot](https://discordapp.com/api/oauth2/authorize?client_id=268562382173765643&permissions=2146958583&scope=bot) and myself over on [my server](https://discord.gg/wVVrqej) or on the [Redbot Cog Support server](https://discord.gg/GET4DVk).\n"
    "## Credits\n"
    "Thank you to everyone who has pushed me to think about new ideas and implement them. Including but not limited to:\n{credits}\n"
)


@dataclass
class InfoJson:
    author: List[str]
    description: Optional[str] = ""
    install_msg: Optional[str] = "Thanks for installing"
    short: Optional[str] = ""
    name: Optional[str] = ""
    min_bot_version: Optional[str] = "3.3.0"
    max_bot_version: Optional[str] = "0.0.0"
    hidden: Optional[bool] = False
    disabled: Optional[bool] = False
    required_cogs: Mapping = field(default_factory=dict)
    requirements: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    type: Optional[str] = "COG"
    permissions: List[str] = field(default_factory=list)
    min_python_version: Optional[List[int]] = field(default_factory=lambda: [3, 8, 0])
    end_user_data_statement: str = (
        "This cog does not persistently store data or metadata about users."
    )

    @classmethod
    def from_json(cls, data: dict):
        author = []
        description = ""
        install_msg = "Thanks for installing"
        short = "Thanks for installing"
        min_bot_version = "3.1.8"
        max_bot_version = "0.0.0"
        name = ""
        required_cogs: Mapping = {}
        requirements = []
        tags = []
        hidden = False
        disabled = False
        type = "COG"
        permissions = []
        min_python_version = []
        end_user_data_statement = (
            "This cog does not persistently store data or metadata about users."
        )
        if "author" in data:
            author = data["author"]
        if "description" in data:
            description = data["description"]
        if "install_msg" in data:
            install_msg = data["install_msg"]
        if "short" in data:
            short = data["short"]
        if "bot_version" in data:
            min_bot_version = data["bot_version"]
            if isinstance(min_bot_version, list):
                min_bot_version = ".".join(str(i) for i in data["bot_version"])
        if "min_bot_version" in data:
            min_bot_version = data["min_bot_version"]
            # min_bot_version = "3.3.0"
        if "max_bot_version" in data:
            max_bot_version = data["max_bot_version"]
            # max_bot_version = "0.0.0"
        if "name" in data:
            name = data["name"]
        if "required_cogs" in data:
            if isinstance(data["required_cogs"], list):
                required_cogs = {}
            else:
                required_cogs = data["required_cogs"]
        if "requirements" in data:
            requirements = data["requirements"]
        if "tags" in data:
            tags = data["tags"]
        if "hidden" in data:
            hidden = data["hidden"]
        if "disabled" in data:
            disabled = data["disabled"]
        if "type" in data:
            type = data["type"]
        if "permissions" in data:
            permissions = data["permissions"]
        if "min_python_version" in data:
            min_python_version = data["min_python_version"]
            # min_python_version = [3, 8, 0]
        if "end_user_data_statement" in data:
            end_user_data_statement = data["end_user_data_statement"]

        return cls(
            author,
            description,
            install_msg,
            short,
            name,
            min_bot_version,
            max_bot_version,
            hidden,
            disabled,
            required_cogs,
            requirements,
            tags,
            type,
            permissions,
            min_python_version,
            end_user_data_statement,
        )


def save_json(folder, data):
    with open(folder, "w") as newfile:
        json.dump(data, newfile, indent=4, sort_keys=True, separators=(",", " : "))


@click.group()
def cli():
    """Utilities for Cog creation!"""
    pass


@cli.command()
def mass_fix():
    """Ensure all info.json files are up-to-date with current standards"""
    for folder in os.listdir(f"{ROOT}/"):
        if folder.startswith("."):
            continue
        try:
            with open(f"{ROOT}/{folder}/info.json", "r") as infile:
                info = InfoJson.from_json(json.load(infile))
            save_json(f"{ROOT}/{folder}/info.json", info.__dict__)
        except Exception:
            log.exception(f"Error reading info.json in {folder}")
            continue


@cli.command()
@click.option(
    "--key",
    prompt="Enter the json key you want to edit.",
    help="Name of the key being edited",
)
@click.option(
    "--value",
    prompt="Enter the value for the key you want changed.",
    help="The value you want the key edited to.",
)
def edit(key, value):
    for folder in os.listdir(f"{ROOT}/"):
        if folder.startswith("."):
            continue
        try:
            with open(f"{ROOT}/{folder}/info.json", "r") as infile:
                info = InfoJson.from_json(json.load(infile))
            setattr(info, key, value)
            save_json(f"{ROOT}/{folder}/info.json", info.__dict__)
        except Exception:
            log.exception(f"Error reading info.json in {folder}")
            continue


@cli.command()
@click.option("--author", default=DEFAULT_AUTHOR, help="Author of the cog", prompt=True)
@click.option("--name", prompt="Enter the name of the cog", help="Name of the cog being added")
@click.option(
    "--description",
    prompt="Enter a longer description for the cog.",
    help="Description about what the cog can do.",
)
@click.option(
    "--install-msg",
    prompt=True,
    default="Thanks for installing!",
    help="Enter the install message you would like. Default is `Thanks for installing!`",
)
@click.option(
    "--short",
    prompt="Enter a short description about the cog.",
    help="Enter a short description about the cog.",
)
@click.option(
    "--min-bot-version",
    default="3.3.0",
    help="This cogs minimum python version requirements.",
    prompt=True,
)
@click.option(
    "--max-bot-version",
    default="0.0.0",
    help="This cogs minimum python version requirements.",
    prompt=True,
)
@click.option(
    "--hidden",
    default=False,
    help="Whether or not the cog is hidden from downloader.",
    prompt=True,
    type=bool,
)
@click.option(
    "--disabled",
    default=False,
    help="Whether or not the cog is disabled in downloader.",
    prompt=True,
    type=bool,
)
@click.option("--required-cogs", default={}, help="Required cogs for this cog to function.")
@click.option("--requirements", prompt=True, default=[], help="Requirements for the cog.")
@click.option(
    "--tags",
    default=[],
    prompt=True,
    help="Any tags to help people find the cog better.",
)
@click.option("--permissions", prompt=True, default=[], help="Any permissions the cog requires.")
@click.option(
    "--min-python-version",
    default=[3, 8, 0],
    help="This cogs minimum python version requirements.",
)
@click.option(
    "--end-user-data-statement",
    prompt=True,
    default="This cog does not persistently store data or metadata about users.",
    help="The end user data statement for this cog.",
)
def make(
    author: list,
    name: str,
    description: str = "",
    install_msg: str = "",
    short: str = "",
    min_bot_version: str = "3.3.0",
    max_bot_version: str = "0.0.0",
    hidden: bool = False,
    disabled: bool = False,
    required_cogs: Mapping[str, str] = {},
    requirements: List[str] = [],
    tags: list = [],
    permissions: list = [],
    min_python_version: list = [3, 8, 0],
    end_user_data_statement: str = "This cog does not persistently store data or metadata about users.",
):
    """Generate a new info.json file for your new cog!"""
    if isinstance(author, str):
        author = [author]
        if ", " in author:
            author = author.split(", ")
    if isinstance(requirements, str):
        requirements = requirements.split(" ")
    if isinstance(permissions, str):
        permissions = permissions.split(" ")
    if isinstance(tags, str):
        tags = tags.split(" ")
    if isinstance(min_python_version, str):
        min_python_version = [int(i) for i in min_python_version.split(".")]
    type = "COG"
    data_obj = InfoJson(
        author,
        description,
        install_msg,
        short,
        name,
        min_bot_version,
        max_bot_version,
        hidden,
        disabled,
        required_cogs,
        requirements,
        tags,
        type,
        permissions,
        min_python_version,
        end_user_data_statement,
    )
    log.debug("make data_obj: %s", data_obj)
    save_json(f"{ROOT}/{name}/info.json", data_obj.__dict__)


@cli.command()
@click.option("--include-hidden", default=False)
@click.option("--include-disabled", default=False)
def countlines(include_hidden: bool = False, include_disabled: bool = False):
    """Count the number of lines of .py files in all folders"""
    total = 0
    totals = []
    log.debug("countlines root: %s", ROOT)
    for folder in os.listdir(ROOT):
        cog_path = ROOT / folder
        cog = 0
        if folder.startswith("."):
            continue
        if not cog_path.is_dir():
            log.debug("%s is not a directory", cog_path)
            continue
        try:
            with open(cog_path / "info.json", "r") as infile:
                info = InfoJson.from_json(json.load(infile))
        except Exception:
            info = InfoJson(DEFAULT_AUTHOR, hidden=True, disabled=True)
            log.debug("Error opening %s info.json", cog_path)
        if info.hidden and not include_hidden:
            continue
        if info.disabled and not include_disabled:
            continue
        try:
            for file in os.listdir(cog_path):
                file_path = cog_path / file
                if not file_path.is_file():
                    continue
                if not file.endswith(".py"):
                    continue
                try:
                    with open(file_path, "r") as infile:
                        lines = len(infile.readlines())
                        log.debug("%s has %s lines of code", file_path, lines)
                    cog += lines
                    total += lines
                except Exception:
                    log.exception(f"Error opening {file_path}")
            totals.append((folder, cog))
        except Exception:
            log.exception(f"Error reading {folder}")
    totals = sorted(totals, key=lambda x: x[1], reverse=True)
    totals.insert(0, ("Total", total))
    print(tabulate.tabulate(totals, headers=["Cog", "# of Lines"], tablefmt="pretty"))
    return totals


@cli.command()
@click.option("--include-hidden", default=False)
@click.option("--include-disabled", default=False)
def countchars(include_hidden: bool = False, include_disabled: bool = False):
    """Count the number of lines of .py files in all folders"""
    total = 0
    totals = []
    log.info("countchars %s", ROOT)
    for folder in os.listdir(f"{ROOT}/"):
        cog = 0
        if folder.startswith("."):
            continue
        try:
            with open(f"{ROOT}/{folder}/info.json", "r") as infile:
                info = InfoJson.from_json(json.load(infile))
        except Exception:
            continue
        if info.hidden and not include_hidden:
            continue
        if info.disabled and not include_disabled:
            continue
        try:
            for file in glob.glob(f"{ROOT}/{folder}/*.py"):
                try:
                    with open(file, "r") as infile:
                        lines = len(infile.read())
                    cog += lines
                    total += lines
                except Exception:
                    pass
            totals.append((folder, cog))
        except Exception:
            pass
    totals = sorted(totals, key=lambda x: x[1], reverse=True)
    totals.insert(0, ("Total", total))
    print(tabulate.tabulate(totals, headers=["Cog", "# ofchars"], tablefmt="pretty"))
    return totals


@cli.command()
def makereadme():
    """Generate README.md from info about all cogs"""
    table_data = []
    authors = set()
    for folder in os.listdir(ROOT):
        if folder.startswith(".") or folder.startswith("_"):
            continue
        _version = ""
        info = None
        for file in glob.glob(f"{ROOT}/{folder}/*"):
            if not file.endswith(".py") and not file.endswith("json"):
                continue
            if file.endswith("info.json"):
                try:
                    with open(file) as infile:
                        data = json.loads(infile.read())
                    info = InfoJson.from_json(data)
                except Exception:
                    log.exception(f"Error reading info.json {file}")
            if _version == "":
                with open(file, "r", encoding="utf-8") as infile:
                    data = infile.read()
                    maybe_version = VER_REG.search(data)
                    if maybe_version:
                        _version = maybe_version.group(1)
        if info and not (info.disabled or info.hidden):
            to_append = [info.name, _version]
            description = f"<details><summary>{info.short}</summary>{info.description}</details>"
            to_append.append(description)
            to_append.append(babel_list(info.author, style="standard", locale="en"))
            table_data.append(to_append)
        if info:
            for author in info.author:
                authors.add(author)

    body = tabulate.tabulate(
        table_data,
        headers=[
            "Name",
            "Status/Version",
            "Description (Click to see full status)",
            "Authors",
        ],
        tablefmt="github",
    )
    authors.remove("TrustyJAID")
    credits = "\n".join(f"- {i}" for i in sorted(authors))
    with open(f"{ROOT}/README.md", "w") as outfile:
        outfile.write(HEADER.format(body=body, credits=credits))


@cli.command()
def makerequirements():
    """Generate a requirements.txt for all cogs.
    Useful when setting up the bot in a new venv and requirements are missing.
    """
    requirements = set()
    with open(ROOT / "requirements.txt", "r") as infile:
        current_reqs = set()
        for _req in infile.readlines():
            current_reqs.add(_req.strip())
    for folder in os.listdir(ROOT):
        if folder.startswith(".") or folder.startswith("_"):
            continue
        info = None
        for file in glob.glob(f"{ROOT}/{folder}/*"):
            if not file.endswith(".py") and not file.endswith("json"):
                continue
            if file.endswith("info.json"):
                try:
                    with open(file) as infile:
                        data = json.loads(infile.read())
                    info = InfoJson.from_json(data)
                    if info.disabled:
                        continue
                    for req in info.requirements:
                        requirements.add(req)
                except Exception:
                    log.exception(f"Error reading info.json {file}")
    reqs = sorted(requirements)
    if current_reqs == requirements:
        log.info("Same requirements, ignoring")
        return
    requirements_txt = "{reqs}\n".format(reqs="\n".join(r for r in reqs))
    with open(ROOT / "requirements.txt", "w") as outfile:
        outfile.write(requirements_txt)


def run_cli():
    try:
        cli()
    except KeyboardInterrupt:
        log.debug("Exiting.")
    else:
        log.debug("Exiting.")


if __name__ == "__main__":
    run_cli()
