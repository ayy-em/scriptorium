"""One place that answers "can this actually run on this machine?".

Scriptorium leans on things Python cannot install for you: ffmpeg, pandoc, the
pango/cairo/glib stack behind PDF output, an OpenAI key, model weights that are
fetched on first use. Each of those used to fail in its own unrelated way — a
sidebar banner for ffmpeg, a raw ``CalledProcessError`` for pandoc, an
``OSError`` from deep inside cffi for pango, a silent 170MB download for rembg.
Four bespoke failure modes was the complaint in BACKLOG.md; there turned out to
be seven.

This module makes them one shape. A ``Capability`` says what is missing, who
needs it, and what to do about it, and everything else — the sidebar banner, a
script's own availability, the download notice on a form — is a presentation of
that same value.

Two things it deliberately does *not* do:

- **It does not fail a run.** A probe answering "absent" is how the UI warns
  before you press Run. Scripts still raise their own errors, because a
  capability can disappear between the check and the run.
- **It does not cache for the life of the process.** The old
  ``has_ffmpeg()`` was evaluated once, at import, into a Jinja global — so
  installing ffmpeg and reloading the page still showed the banner until the
  app was restarted. Results here expire, and ``invalidate()`` clears them
  outright.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import shutil
import sys
import time

# How long a probe result is trusted. Long enough that one page render does not
# re-import weasyprint several times, short enough that installing a dependency
# and reloading reflects it without a restart.
CACHE_SECONDS = 5.0

logger = logging.getLogger(__name__)

# What the user has to do about a missing capability. The distinction drives
# where it is surfaced, not just its wording: an install is a blocking banner,
# a download is a heads-up on the form that will resolve itself.
REMEDY_INSTALL = "install"
REMEDY_CONFIGURE = "configure"
REMEDY_DOWNLOAD = "download"


@dataclass(frozen=True)
class Capability:
    """Something a script needs that may not be there.

    Attributes:
        name: Stable identifier, e.g. ``"ffmpeg"``.
        label: Display name.
        present: Whether it was found.
        remedy: One of the ``REMEDY_*`` constants.
        required: False for a capability whose absence only costs an option —
            gifsicle, whose loss means a larger GIF rather than no GIF. Those
            are reported but never as a blocking warning.
        needed_for: Plain-language "what stops working without this".
        hint: What to do about it, already resolved for this platform.
        command: An install command the app can run on the user's behalf, as
            argv, already resolved for this platform. Empty when the fix is
            not a single unattended command — pango on Windows, anything
            needing sudo, a key to configure.
        env_var: For a configure remedy, the environment variable the value
            lives in, so the settings modal can offer a field for it.
        secret: Whether the value is a credential. A secret is entered masked
            and never shown again; a plain identifier such as a chat id is
            shown back, since the user has to be able to check it.
    """

    name: str
    label: str
    present: bool
    remedy: str
    required: bool
    needed_for: str
    hint: str = ""
    command: tuple[str, ...] = ()
    env_var: str = ""
    secret: bool = True


def _probe_binary(*names: str) -> Callable[[], bool]:
    """Build a probe that checks for executables on PATH.

    Args:
        *names: Executable names that must all be present.

    Returns:
        A probe callable.
    """
    return lambda: all(shutil.which(n) is not None for n in names)


def _probe_pango() -> bool:
    """Report whether the native stack behind PDF output can be loaded.

    Imports weasyprint for real rather than guessing at library filenames: the
    whole failure mode is that the libraries exist but cannot be resolved, and
    only an actual load settles it. The dlopen fallback has to be installed
    first, exactly as the PDF scripts do it.

    Returns:
        True if weasyprint imported successfully.
    """
    from core.native_libs import ensure_native_lib_resolution  # noqa: PLC0415

    ensure_native_lib_resolution()
    try:
        import weasyprint  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


def _probe_env(name: str) -> Callable[[], bool]:
    """Build a probe that checks an environment variable is set.

    Loads ``.env`` first. The webapp happens to do that at import, but a CLI
    caller does not, and a probe whose answer depends on who called it first is
    worse than no probe.

    Args:
        name: The variable that holds the value.

    Returns:
        A probe that is true when the variable is set to something non-blank.
    """

    def _probe() -> bool:
        from core.env import load_env  # noqa: PLC0415

        load_env()
        return bool(os.environ.get(name, "").strip())

    return _probe


@dataclass(frozen=True)
class _Spec:
    """Static description of a capability, minus whether it is present."""

    name: str
    label: str
    remedy: str
    required: bool
    needed_for: str
    probe: Callable[[], bool]
    hints: dict[str, str]
    commands: dict[str, tuple[str, ...]] = field(default_factory=dict)
    env_var: str = ""
    secret: bool = True


def _hint_for(hints: dict[str, str]) -> str:
    """Pick the install hint for the running platform.

    Args:
        hints: Mapping of ``sys.platform`` value to hint, with a ``""`` default.

    Returns:
        The most specific hint available, or an empty string.
    """
    return hints.get(sys.platform, hints.get("", ""))


def _command_for(commands: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Pick the runnable install command for the running platform.

    Unlike hints there is no ``""`` default: a command that is wrong for the
    platform is worse than no button.

    Args:
        commands: Mapping of ``sys.platform`` value to argv.

    Returns:
        The argv, or an empty tuple when nothing can be run unattended here.
    """
    return commands.get(sys.platform, ())


def _winget(package_id: str) -> tuple[str, ...]:
    """Build an unattended winget install for one package.

    Args:
        package_id: The exact winget package identifier.

    Returns:
        Argv that neither prompts for agreements nor guesses at the name.
    """
    return (
        "winget",
        "install",
        "--id",
        package_id,
        "--exact",
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    )


_SPECS: tuple[_Spec, ...] = (
    _Spec(
        name="ffmpeg",
        label="ffmpeg",
        remedy=REMEDY_INSTALL,
        required=True,
        needed_for="Audio and video scripts, GIF conversion, and audio/video format conversion",
        probe=_probe_binary("ffmpeg", "ffprobe"),
        hints={
            "darwin": "brew install ffmpeg",
            "win32": "winget install Gyan.FFmpeg — or download from gyan.dev/ffmpeg/builds and add it to PATH.",
            "": "Install ffmpeg with your package manager, e.g. apt install ffmpeg.",
        },
        commands={
            "darwin": ("brew", "install", "ffmpeg"),
            "win32": _winget("Gyan.FFmpeg"),
        },
    ),
    _Spec(
        name="pandoc",
        label="pandoc",
        remedy=REMEDY_INSTALL,
        required=True,
        needed_for="Converting documents between docx, rtf, md, html and pdf",
        probe=_probe_binary("pandoc"),
        hints={
            "darwin": "brew install pandoc",
            "win32": "winget install JohnMacFarlane.Pandoc",
            "": "apt install pandoc",
        },
        commands={
            "darwin": ("brew", "install", "pandoc"),
            "win32": _winget("JohnMacFarlane.Pandoc"),
        },
    ),
    _Spec(
        name="pango",
        label="pango / cairo / glib",
        remedy=REMEDY_INSTALL,
        required=True,
        needed_for="PDF output from Telegram chat analysis",
        # Probed through core.native_libs, so a Homebrew or MSYS2 install that
        # the default dlopen path cannot see still counts as present.
        probe=_probe_pango,
        hints={
            "darwin": "brew install pango",
            "win32": "Install MSYS2 and `pacman -S mingw-w64-ucrt-x86_64-pango`, or the GTK3 runtime.",
            "": "apt install libpango-1.0-0 libpangoft2-1.0-0",
        },
        commands={"darwin": ("brew", "install", "pango")},
    ),
    _Spec(
        name="weasyprint-cli",
        label="weasyprint",
        remedy=REMEDY_INSTALL,
        required=False,
        needed_for="Better-looking PDFs from document conversion; pandoc falls back to its own engine",
        probe=_probe_binary("weasyprint"),
        hints={"": "Comes with the weasyprint package: uv tool install weasyprint"},
    ),
    _Spec(
        name="gifsicle",
        label="gifsicle",
        remedy=REMEDY_INSTALL,
        required=False,
        needed_for="Extra GIF size optimisation; without it --optimize still runs, just less effectively",
        probe=_probe_binary("gifsicle"),
        hints={
            "darwin": "brew install gifsicle",
            "win32": "winget install gifsicle",
            "": "apt install gifsicle",
        },
        commands={"darwin": ("brew", "install", "gifsicle")},
    ),
    _Spec(
        name="openai-key",
        label="OpenAI API key",
        remedy=REMEDY_CONFIGURE,
        required=True,
        needed_for="Speech transcription",
        probe=_probe_env("OPENAI_API_KEY"),
        hints={"": "Paste the key under Settings → Keys, or put OPENAI_API_KEY=… in your .env file."},
        env_var="OPENAI_API_KEY",
    ),
    # Not required: notifications are opt-in, so an unset bot must not sit in
    # the sidebar banner of everyone who never asked for them.
    _Spec(
        name="telegram-bot-token",
        label="Telegram bot token",
        remedy=REMEDY_CONFIGURE,
        required=False,
        needed_for="Telegram notifications when a long run finishes, and util.notify",
        probe=_probe_env("TELEGRAM_BOT_TOKEN"),
        hints={"": "Create a bot with @BotFather and paste its token under Settings → Keys."},
        env_var="TELEGRAM_BOT_TOKEN",
    ),
    _Spec(
        name="telegram-chat-id",
        label="Telegram chat id",
        remedy=REMEDY_CONFIGURE,
        required=False,
        needed_for="Which chat the notifications go to — message your bot first, then read the id from @userinfobot",
        probe=_probe_env("TELEGRAM_CHAT_ID"),
        hints={"": "Paste the chat id under Settings → Keys."},
        env_var="TELEGRAM_CHAT_ID",
        secret=False,
    ),
)

_BY_NAME = {spec.name: spec for spec in _SPECS}

# Which capability a script needs, by dotted key first and theme second, so one
# script can depart from its theme's default.
#
# Not the same mapping as webapp/_badges.py's, despite the overlap. That one
# answers "what does this script drive" — including yt-dlp, which ships in the
# bundle and is therefore never missing. This one answers "what might be
# absent". Merging them would force an always-present tool into the registry.
#
# photo.remove_bg is absent on purpose: its dependency is a *per-model* weights
# file, so it is resolved through model_weights_present() rather than here.
_CAPABILITY_BY_KEY: dict[str, str] = {
    "formats.convert_audio": "ffmpeg",
    "formats.convert_video": "ffmpeg",
    "formats.convert_docs": "pandoc",
    "speech.transcribe": "openai-key",
    "util.notify": "telegram-bot-token",
    "telegram.chat_analysis": "pango",
    "telegram.group_analysis": "pango",
}

# gif.make_gif is deliberately not here: BACKLOG.md listed "gif.*" as needing
# ffmpeg, but it assembles frames with PIL and shells out to nothing.
_CAPABILITY_BY_THEME: dict[str, str] = {
    "av": "ffmpeg",
}

_cache: dict[str, tuple[float, bool]] = {}


def invalidate() -> None:
    """Drop every cached probe result.

    For tests, and for any point where the answer is known to have changed.
    """
    _cache.clear()


def _present(spec: _Spec) -> bool:
    """Run a spec's probe, or return a cached answer.

    Args:
        spec: The capability to check.

    Returns:
        Whether it is present. A probe that raises counts as absent — this is
        a warning mechanism, and it must not be the thing that breaks a page.
    """
    now = time.monotonic()
    cached = _cache.get(spec.name)
    if cached is not None and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    try:
        result = spec.probe()
    except Exception:
        result = False
    _cache[spec.name] = (now, result)
    return result


def _build(spec: _Spec) -> Capability:
    """Turn a spec plus a fresh probe into a Capability.

    Args:
        spec: The static description.

    Returns:
        The capability, with ``present`` filled in.
    """
    return Capability(
        name=spec.name,
        label=spec.label,
        present=_present(spec),
        remedy=spec.remedy,
        required=spec.required,
        needed_for=spec.needed_for,
        hint=_hint_for(spec.hints),
        command=_command_for(spec.commands),
        env_var=spec.env_var,
        secret=spec.secret,
    )


def probe(name: str) -> Capability | None:
    """Check one capability by name.

    Args:
        name: A capability name, e.g. ``"pandoc"``.

    Returns:
        The capability, or None if the name is unknown.
    """
    spec = _BY_NAME.get(name)
    return None if spec is None else _build(spec)


def probe_all() -> tuple[Capability, ...]:
    """Check every known capability.

    Returns:
        One Capability per registry entry, in declaration order.
    """
    return tuple(_build(spec) for spec in _SPECS)


def missing(*, required_only: bool = True) -> tuple[Capability, ...]:
    """Return the capabilities that are absent.

    Args:
        required_only: When True, omit capabilities whose absence only costs an
            option rather than a whole script.

    Returns:
        Absent capabilities, in declaration order.
    """
    return tuple(c for c in probe_all() if not c.present and (c.required or not required_only))


def _windows_registry_path() -> str:
    """Read the PATH a *new* process would get on Windows.

    Installers write to the registry and broadcast a change that only new
    processes pick up. A long-running app keeps the PATH it was born with, so
    something it just installed is invisible to ``shutil.which`` until a
    restart. This is the machine PATH followed by the user PATH, the same order
    Windows uses.

    Returns:
        The combined PATH string, with ``%VAR%`` references expanded.
    """
    import winreg  # noqa: PLC0415

    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    )
    parts: list[str] = []
    for root, subkey in keys:
        try:
            with winreg.OpenKey(root, subkey) as handle:
                value, _ = winreg.QueryValueEx(handle, "Path")
        except OSError:
            continue
        parts.append(os.path.expandvars(str(value)))
    return os.pathsep.join(part for part in parts if part)


def refresh_environment() -> None:
    """Make a just-installed binary findable without restarting the app.

    On Windows the process PATH is replaced with what the registry now says,
    keeping any entries the process already had so a launcher-injected path is
    not lost. Elsewhere installers put binaries in directories already on PATH,
    so there is nothing to do. Cached probe results are dropped either way.
    """
    if sys.platform == "win32":
        try:
            fresh = _windows_registry_path()
        except Exception:
            logger.warning("Could not re-read PATH from the registry", exc_info=True)
            fresh = ""
        if fresh:
            fresh_entries = [entry for entry in fresh.split(os.pathsep) if entry]
            kept = [
                entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry and entry not in fresh_entries
            ]
            os.environ["PATH"] = os.pathsep.join(fresh_entries + kept)
    invalidate()


def capability_name_for(key: str) -> str | None:
    """Return the capability a script depends on, if any.

    Args:
        key: Dotted script key such as ``"av.trim"``.

    Returns:
        A capability name, or None when the script needs nothing external.
        May name a capability that is not in the static registry — rembg's
        model weights are per-model, so they are resolved separately.
    """
    if key in _CAPABILITY_BY_KEY:
        return _CAPABILITY_BY_KEY[key]
    return _CAPABILITY_BY_THEME.get(key.split(".", 1)[0])


def for_script(key: str) -> Capability | None:
    """Return the registry capability a script needs, already probed.

    Args:
        key: Dotted script key.

    Returns:
        The capability, or None when the script needs nothing this module
        tracks statically.
    """
    name = capability_name_for(key)
    return None if name is None else probe(name)


def model_weights_dir() -> Path:
    """Return the directory rembg caches model weights in.

    Mirrors ``rembg.sessions.base.BaseSession.u2net_home`` rather than importing
    it: this is called to decide whether to warn *before* a run, and importing
    rembg costs a second and pulls in onnxruntime.

    Returns:
        The weights directory, which may not exist yet.
    """
    return Path(os.path.expanduser(os.getenv("U2NET_HOME", os.path.join(os.getenv("XDG_DATA_HOME", "~"), ".u2net"))))


def model_weights_present(model: str) -> bool:
    """Report whether a rembg model's weights are already on disk.

    Args:
        model: A rembg model name, e.g. ``"u2net"``.

    Returns:
        True if the weights file exists, meaning selecting this model will not
        trigger a download.
    """
    return (model_weights_dir() / f"{model}.onnx").is_file()
