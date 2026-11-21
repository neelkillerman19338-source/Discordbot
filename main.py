"""Discord bot entry point.

Features
--------
* Loads every cog in the ``cog/`` directory (``cog/<name>.py`` with a
  ``setup()`` coroutine) at startup.
* Accepts three command prefixes: an @mention of the bot, ``+`` and ``!``.
* Reads the bot token from a file named ``bot_token`` next to this script.

Target runtime: Python 3.13 (discord.py 2.7.0).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

# --------------------------------------------------------------------------- #
# Paths & logging
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "bot_token"
COG_DIR = BASE_DIR / "cog"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")


# --------------------------------------------------------------------------- #
# Token loading
# --------------------------------------------------------------------------- #
def read_token(path: Path = TOKEN_FILE) -> str:
    """Read the bot token from ``path``.

    The file may contain the token on its own line; surrounding whitespace,
    a UTF-8 BOM, blank lines, ``#`` comments, an optional ``BOT_TOKEN=`` /
    ``TOKEN=`` / ``DISCORD_TOKEN=`` prefix and surrounding quotes are all
    tolerated. The first usable line wins.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Token file not found: {path}\n"
            "Create a file named 'bot_token' next to main.py containing your "
            "Discord bot token."
        )

    raw = path.read_text(encoding="utf-8-sig")

    token = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            key, _, value = line.partition("=")
            if key.strip().upper() in {"BOT_TOKEN", "TOKEN", "DISCORD_TOKEN"}:
                candidate = value.strip()
            else:
                # Unknown key (e.g. "KEY=") — ignore this line, keep looking.
                continue
        else:
            candidate = line

        candidate = candidate.strip().strip('"').strip("'").strip()
        if candidate:
            token = candidate
            break

    if not token:
        raise ValueError(f"Token file contains no usable token: {path}")
    return token


# --------------------------------------------------------------------------- #
# Prefixes: @mention, "+", "!"
# --------------------------------------------------------------------------- #
def get_prefix(bot: commands.Bot, message: discord.Message):
    """Return the valid prefixes for ``message``.

    Supported forms:
      * an @mention of the bot — ``<@id>`` / ``<@!id>``, with or without a
        following space (so both ``@bot ping`` and ``@botping`` work);
      * ``+``
      * ``!``

    Longer prefixes are listed first because discord.py stops at the first
    match, so ``<@id> `` must be tried before ``<@id>``.
    """
    prefixes: list[str] = ["+", "!"]
    if bot.user is not None:
        uid = bot.user.id
        prefixes = [f"<@{uid}> ", f"<@!{uid}> ", f"<@{uid}>", f"<@!{uid}>", *prefixes]
    return prefixes


# --------------------------------------------------------------------------- #
# Cog loading
# --------------------------------------------------------------------------- #
async def load_cogs(bot: commands.Bot) -> None:
    """Load every ``cog/*.py`` module as an extension."""
    if not COG_DIR.is_dir():
        log.warning("Cog directory not found: %s (starting with no cogs)", COG_DIR)
        return

    # Extensions are imported as "cog.<name>". Python 3 treats a directory
    # without __init__.py as a namespace package, so no marker file is needed
    # (and none is created — the cog directory may be read-only). We only need
    # the bot's base directory on sys.path so the import can resolve.
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    loaded = 0
    for path in sorted(COG_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue  # skip __init__.py, __pycache__ helpers, etc.

        extension = f"cog.{path.stem}"
        try:
            await bot.load_extension(extension)
        except Exception:  # noqa: BLE001 - one bad cog must not kill the bot
            log.exception("Failed to load extension %s", extension)
        else:
            loaded += 1
            log.info("Loaded extension %s", extension)

    log.info("Cog loading complete: %d extension(s) loaded", loaded)


# --------------------------------------------------------------------------- #
# Bot
# --------------------------------------------------------------------------- #
class DiscordBot(commands.Bot):
    """Bot subclass that loads cogs during the async setup phase."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        # Required to read message content for prefix commands.
        intents.message_content = True

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            case_insensitive=True,
            strip_after_prefix=True,
        )

    async def setup_hook(self) -> None:
        await load_cogs(self)

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %s)", self.user, getattr(self.user, "id", "?"))
        log.info("Serving %d guild(s)", len(self.guilds))

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Minimal, non-crashing error surface for prefix commands."""
        # CommandInvokeError wraps the real exception raised inside the command.
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"Missing argument: `{error.param.name}`", mention_author=False)
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"On cooldown — try again in {error.retry_after:.1f}s",
                mention_author=False,
            )
            return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.reply("I do not have permission to do that.", mention_author=False)
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("You do not have permission to run that.", mention_author=False)
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.reply("You cannot run that command.", mention_author=False)
            return
        log.exception("Unhandled command error in %s", getattr(ctx.command, "name", "?"), exc_info=error)
        await ctx.reply("Something went wrong running that command.", mention_author=False)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    try:
        token = read_token()
    except (FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        raise SystemExit(1) from exc

    bot = DiscordBot()
    try:
        # log_handler=None: logging is already configured above.
        bot.run(token, log_handler=None)
    except discord.LoginFailure:
        log.error("Discord rejected the token in %s — check that it is valid.", TOKEN_FILE)
        raise SystemExit(1)
    except discord.PrivilegedIntentsRequired:
        log.error(
            "Message Content intent is not enabled. Enable it at "
            "https://discord.com/developers/applications -> Bot -> "
            "Privileged Gateway Intents."
        )
        raise SystemExit(1)
    except (OSError, aiohttp.ClientError) as exc:
        log.error("Could not connect to Discord: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
