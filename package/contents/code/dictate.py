#!/usr/bin/env python3
"""Dictate a reply for Talpy Den: your voice to text, on this computer
only, for the chat pane's reply box. It's written down by whisper.cpp's
whisper-cli if it's on the PATH, else by faster-whisper, which the widget
sets up in a Python environment of its own (no sudo, no compiler).

    python3 -I dictate.py --status
        whether it can: {"ok", "engine" ("whisper.cpp", "faster-whisper" or
        null), "tool", "model" (the one used), "modelName", "recorder",
        "missing" (what to install), "canSetup", "setUp", "setupMb",
        "chosen" (a model's name or "auto"), "models" [{"name", "mb",
        "note", "installed", "deletable", "used"}]}
    python3 -I dictate.py --setup [NAME]
        set dictation up: faster-whisper (from pypi.org) in
        ~/.local/share/talpy-den/whisper/venv, and the NAME (else base)
        model; minutes
    python3 -I dictate.py --start ID
        start recording (the microphone, until --stop or --cancel; at most
        five minutes) into the widget's private cache
    python3 -I dictate.py --stop ID [--language L]
        stop and write it down: {"ok", "text"}; the recording is deleted
    python3 -I dictate.py --cancel ID
        stop, nothing written, the recording deleted
    python3 -I dictate.py --get-model NAME
        download a speech model for the engine (from huggingface.co) into
        ~/.local/share/talpy-den/whisper, and use it
    python3 -I dictate.py --use-model NAME|auto
        the model to write with (auto: the best one downloaded); for every
        copy of the widget and the VS Code extension
    python3 -I dictate.py --delete-model NAME
        delete a downloaded model
    python3 -I dictate.py --remove-setup
        delete faster-whisper's environment and its models

Speech never leaves the computer: only setting up and downloading a model go
over the network. Standard library only (faster-whisper runs in its own
environment).
"""
import contextlib
import fcntl
import importlib.util
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TOOLS = ("whisper-cli", "whisper-cpp", "whisper.cpp")
# Models you can download: name -> (whisper.cpp's file, MB, what it's like);
# faster-whisper has the same ones by name
MODELS = {
    "tiny": ("ggml-tiny.bin", 75, "the fastest, often wrong"),
    "base": ("ggml-base.bin", 142, "fast, good for short replies"),
    "base.en": ("ggml-base.en.bin", 142, "English only, a little better at it"),
    "small": ("ggml-small.bin", 466, "better with names and mixed languages, about 3× slower"),
    "medium": ("ggml-medium.bin", 1460, "better still, slow without a graphics card"),
    "large-v3-turbo": ("ggml-large-v3-turbo.bin", 1550, "the best, slow without a graphics card"),
}
AUTO = ("small", "base", "base.en", "medium", "large-v3-turbo", "tiny")   # (auto: the first one downloaded)
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/%s/"
FW_PACKAGE = "faster-whisper>=1.1,<2"
# The exact versions faster-whisper's environment gets (pip -c), on each
# Python they were checked on; on another one pip takes what fits, as before.
FW_CONSTRAINTS = "".join('%s; python_version == "3.14"\n' % pin for pin in (
    "anyio==4.15.1", "av==19.0.2", "click==8.5.0", "ctranslate2==4.8.4", "faster-whisper==1.2.1", "filelock==4.2.4",
    "flatbuffers==25.12.19", "fsspec==2026.9.0", "h11==0.16.0", "hf-xet==1.7.0", "httpcore2==2.16.0", "httpx2==2.16.0",
    "huggingface_hub==2.3.0", "idna==3.20", "numpy==2.5.4", "onnxruntime==1.31.1", "packaging==26.3",
    "protobuf==7.36.2", "PyYAML==6.0.3", "tokenizers==0.23.3", "tqdm==4.70.1", "truststore==0.10.5",
    "typing_extensions==4.16.0"))
# Each speech model at a fixed revision of its repository, with the sha256 of
# its file (whisper.cpp's ggml-*.bin; faster-whisper's model.bin), checked
# before it's kept: {name: (revision, sha256)}. TO FILL IN from huggingface.co
# (ggerganov/whisper.cpp and Systran/faster-whisper-<name>: the commit, and
# the file's SHA256 its page shows); a model without them still comes from
# the repository's newest revision, unchecked but for its size.
GGML_PINS = {name: None for name in MODELS}
FW_PINS = {name: None for name in MODELS}
FW_MB = 470   # (faster-whisper's environment, about)
READY = ".ready"
# faster-whisper, run in its environment: writes down a 16 kHz mono WAV (read
# here, not with PyAV, whose newer versions faster-whisper can't open files
# with), a line for each stretch said
FW_WRITE = r"""
import sys, wave
import numpy as np
from faster_whisper import WhisperModel
folder, wav, language, threads = sys.argv[1:5]
with wave.open(wav) as w:
    if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
        sys.exit("the recording isn't 16 kHz mono")
    audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
model = WhisperModel(folder, device="cpu", compute_type="int8", cpu_threads=int(threads))
segments, _ = model.transcribe(audio, language=None if language == "auto" else language, vad_filter=True)
for segment in segments:
    print(segment.text.strip(), flush=True)
"""
FW_GET = r"""
import sys
from faster_whisper import download_model
download_model(sys.argv[1], output_dir=sys.argv[2], revision=sys.argv[3] or None)
"""
LONGEST_S = 300
LEFTOVER_S = 3600  # (a recording's files, kept no longer than that: see tidy)
VALID_ID = set("abcdefghijklmnopqrstuvwxyz0123456789-")


def data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "talpy-den" / "whisper"


def venv_dir():
    return data_dir() / "venv"


def fw_models():
    return data_dir() / "models"


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = Path(base) / "talpy-den" / "dictation"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)   # (what you said)
    return path


def find_tool():
    return next((shutil.which(t) for t in TOOLS if shutil.which(t)), None)


def fw_python():
    """faster-whisper's Python, once it's set up."""
    python = venv_dir() / "bin" / "python"
    return str(python) if (venv_dir() / READY).is_file() and python.exists() else None


def engine():
    """What writes it down: ("whisper.cpp", whisper-cli), ("faster-whisper",
    its Python) or (None, None)."""
    tool = find_tool()
    if tool:
        return "whisper.cpp", tool
    python = fw_python()
    return ("faster-whisper", python) if python else (None, None)


def model_path(eng, name):
    """Where the engine's model NAME is, or None."""
    if eng == "faster-whisper":
        folder = fw_models() / name
        return str(folder) if (folder / "model.bin").is_file() else None
    folders = [data_dir(), Path.home() / ".local/share/whisper.cpp/models", Path("/usr/share/whisper.cpp/models"),
               Path("/usr/local/share/whisper.cpp/models")]
    return next((str(f / MODELS[name][0]) for f in folders if (f / MODELS[name][0]).is_file()), None)


def chosen():
    try:
        name = json.loads((data_dir() / "settings.json").read_text()).get("model")
    except (OSError, ValueError, AttributeError):
        return None
    return name if name in MODELS else None


def choose(name):
    data_dir().mkdir(parents=True, exist_ok=True)
    if name is None:
        with contextlib.suppress(FileNotFoundError):  # (unlink(missing_ok=True) needs Python 3.8)
            (data_dir() / "settings.json").unlink()
    else:
        (data_dir() / "settings.json").write_text(json.dumps({"model": name}) + "\n")


def find_model(eng):
    """The model to write with: (name, path), or (None, None). $WHISPER_MODEL
    (whisper.cpp's), else the one chosen, else the best one downloaded."""
    env = os.environ.get("WHISPER_MODEL")
    if eng == "whisper.cpp" and env and os.path.isfile(env):
        return os.path.basename(env), env
    if eng is None:
        return None, None
    pick = chosen()
    for name in ([pick] if pick else []) + list(AUTO):
        path = model_path(eng, name)
        if path:
            return name, path
    return None, None


def widgets(path):
    """The model at path is one the widget downloaded (so it may delete it)."""
    return Path(path).parent in (data_dir(), fw_models())


def can_venv():
    """Python can make an environment (Debian and Ubuntu leave that out
    until python3-venv is installed)."""
    return importlib.util.find_spec("ensurepip") is not None and importlib.util.find_spec("venv") is not None


@contextlib.contextmanager
def busy():
    """One setup, download or deletion at a time: yields False while another
    runs."""
    data_dir().mkdir(parents=True, exist_ok=True)
    with open(data_dir() / ".busy", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def last_line(r):
    return (r.stderr.decode(errors="replace").strip().splitlines() or ["failed"])[-1]


def recorder(wav):
    """A command that records the microphone into wav (16 kHz mono, as
    whisper wants it), or None."""
    if shutil.which("pw-record"):
        return ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", str(wav)]
    if shutil.which("parecord"):
        return ["parecord", "--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav", str(wav)]
    if shutil.which("arecord"):
        return ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", str(wav)]
    return None


def status():
    eng, tool = engine()
    name, model = find_model(eng)
    rec = recorder("x.wav")
    setup = eng is None and can_venv()
    missing = []
    if eng is None and not setup:
        missing.append("Python's venv, to set up dictation (Debian, Ubuntu: sudo apt install python3-venv)")
    if rec is None:
        missing.append("a recorder (pw-record, from PipeWire)")
    models = []
    for n, (_, mb, note) in MODELS.items():
        path = model_path(eng, n) if eng else None
        models.append({"name": n, "mb": mb, "note": note, "installed": path is not None,
                       "deletable": path is not None and widgets(path), "used": n == name})
    return {"ok": tool is not None and model is not None and rec is not None, "engine": eng, "tool": tool,
            "model": model, "modelName": name, "recorder": rec[0] if rec else None, "missing": missing,
            "canSetup": setup, "setUp": fw_python() is not None, "setupMb": FW_MB + MODELS["base"][1],
            "chosen": chosen() or "auto", "models": models}


def setup(name="base"):
    if name not in MODELS:
        return {"ok": False, "message": "Not a model: " + str(name)}
    # (Python's venv only makes the environment: one made already brings the model)
    if not (venv_dir() / READY).is_file() and not can_venv():
        return {"ok": False, "message": "To set up dictation, install Python's venv (Debian, Ubuntu: sudo apt install python3-venv)"}
    with busy() as free:
        if not free:
            return {"ok": False, "message": "Dictation is being set up or a model downloaded already"}
        venv = venv_dir()
        if not (venv / READY).is_file():
            if not can_venv():  # (its environment was removed meanwhile)
                return {"ok": False, "message": "To set up dictation, install Python's venv (Debian, Ubuntu: sudo apt install python3-venv)"}
            shutil.rmtree(venv, ignore_errors=True)
            python = str(venv / "bin" / "python")
            pins = venv / "constraints.txt"
            for cmd, what in (([sys.executable, "-m", "venv", str(venv)], "make faster-whisper's environment"),
                              ([python, "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-q",
                                "-c", str(pins), FW_PACKAGE], "install faster-whisper"),
                              ([python, "-I", "-c", "import faster_whisper, numpy"], "start faster-whisper")):
                try:
                    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       timeout=1800)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    shutil.rmtree(venv, ignore_errors=True)
                    return {"ok": False, "message": f"Couldn't {what}: {exc}"}
                if r.returncode != 0:
                    shutil.rmtree(venv, ignore_errors=True)
                    return {"ok": False, "message": f"Couldn't {what}: {last_line(r)}"}
                if not pins.exists():  # (once the environment is there)
                    pins.write_text(FW_CONSTRAINTS)
            (venv / READY).write_text(FW_PACKAGE + "\n")
        if model_path("faster-whisper", name) is None:
            got = fetch_fw(name)
            if not got["ok"]:
                return got
    return {"ok": True, "message": f"Dictation is set up (faster-whisper, the {name} model): click the microphone and speak"}


def remove_setup():
    with busy() as free:
        if not free:
            return {"ok": False, "message": "Dictation is being set up or a model downloaded: try again after"}
        shutil.rmtree(venv_dir(), ignore_errors=True)
        shutil.rmtree(fw_models(), ignore_errors=True)
        if chosen() and model_path("whisper.cpp", chosen()) is None:
            choose(None)
    return {"ok": True, "message": "faster-whisper and its models are deleted"}


def paths(rid):
    if not rid or set(rid) - VALID_ID or len(rid) > 64:
        raise ValueError("Not a recording: " + str(rid))
    folder = cache_dir()
    return folder / (rid + ".wav"), folder / (rid + ".pid")


def tidy():
    """What a recording left behind (a pane closed or a widget gone while
    it recorded) goes once its recorder surely has: LONGEST_S, then up to
    10 minutes writing it down."""
    folder = cache_dir()
    for path in folder.iterdir():
        try:
            if time.time() - path.stat().st_mtime > LEFTOVER_S:
                path.unlink()
        except OSError:
            pass


def start(rid):
    wav, pid_file = paths(rid)
    cmd = recorder(wav)
    if cmd is None:
        return {"ok": False, "message": "To dictate, install PipeWire's pw-record (or arecord)"}
    tidy()
    # (its own session: the widget's command ends now, the recording goes on; at most LONGEST_S)
    proc = subprocess.Popen(["timeout", "--signal=INT", str(LONGEST_S)] + cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    pid_file.write_text(str(proc.pid))
    cancelled = wav.with_suffix(".cancel")
    if cancelled.exists():  # (cancelled while it started: see cancel)
        cancel(rid)
        return {"ok": False, "message": "Not written down"}
    time.sleep(0.3)
    if proc.poll() is not None:
        return {"ok": False, "message": "The microphone didn't start recording"}
    return {"ok": True, "message": "Recording"}


def stop_recording(pid_file):
    try:
        pid = int(pid_file.read_text())
    except (OSError, ValueError):
        return
    try:
        os.killpg(pid, signal.SIGINT)   # (the recorder closes its file properly)
    except OSError:
        pass
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            os.killpg(pid, 0)
        except OSError:
            break
        time.sleep(0.05)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        pid_file.unlink()
    except OSError:
        pass


def stop(rid, language="auto"):
    wav, pid_file = paths(rid)
    stop_recording(pid_file)
    try:
        eng, tool = engine()
        model = find_model(eng)[1]
        if tool is None or model is None:
            return {"ok": False, "message": "To write it down, set up dictation and a speech model"}
        if not wav.is_file() or wav.stat().st_size < 3200:   # (under a tenth of a second)
            return {"ok": False, "message": "Nothing was recorded"}
        threads = str(max(1, min(8, (os.cpu_count() or 2) - 1)))
        if eng == "whisper.cpp":
            cmd, env = [tool, "-m", model, "-f", str(wav), "-nt", "-np", "-l", language or "auto", "-t", threads], None
        else:   # (offline: the model is a folder here)
            cmd = [tool, "-I", "-c", FW_WRITE, model, str(wav), language or "auto", threads]
            env = dict(os.environ, HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=600, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "message": f"{eng} didn't finish: {exc}"}
        if r.returncode != 0:
            return {"ok": False, "message": f"{eng}: {last_line(r)}"}
        # (whisper.cpp's marks for silence and sounds: [BLANK_AUDIO], (wind) …)
        lines = [line.strip() for line in r.stdout.decode("utf-8", "replace").splitlines()]
        text = " ".join(line for line in lines if line and not re.fullmatch(r"[\[(][^\])]*[\])]", line))
        return {"ok": bool(text), "text": text, "message": "" if text else "Nothing was said"}
    finally:
        try:
            wav.unlink()
        except OSError:
            pass


def cancel(rid):
    """Stop a recording and drop it. One cancelled before its --start wrote
    its recorder down (the pane closed while it started) is marked first,
    and its --start stops it once it has."""
    wav, pid_file = paths(rid)
    marked = wav.with_suffix(".cancel")
    marked.touch()
    started = pid_file.exists()
    stop_recording(pid_file)
    for path in ([wav, marked] if started else [wav]):
        try:
            path.unlink()
        except OSError:
            pass
    return {"ok": True, "message": "Not written down"}


def get_model(name):
    if name not in MODELS:
        return {"ok": False, "message": "Not a model: " + str(name)}
    eng = engine()[0]
    if eng is None:
        return {"ok": False, "message": "Set up dictation first"}
    with busy() as free:
        if not free:
            return {"ok": False, "message": "Dictation is being set up or a model downloaded already"}
        got = fetch_fw(name) if eng == "faster-whisper" else fetch_ggml(name)
    if got["ok"]:
        choose(name)
    return got


def fetch_ggml(name):
    file, mb, _ = MODELS[name]
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target, part = folder / file, folder / (file + ".part")
    pin = GGML_PINS.get(name)
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(MODEL_URL % (pin[0] if pin else "main") + file, timeout=60) as r, \
                open(part, "wb") as out:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                digest.update(chunk)
                out.write(chunk)
        if part.stat().st_size < mb * 2 ** 20 * 0.9:
            raise OSError("the download was cut short")
        if pin and digest.hexdigest() != pin[1]:
            raise OSError("it isn't the file expected (another sha256)")
        os.replace(part, target)
    except (OSError, ValueError) as exc:
        try:
            part.unlink()
        except OSError:
            pass
        return {"ok": False, "message": f"Couldn't download the {name} model: {exc}"}
    return {"ok": True, "model": str(target), "message": f"The {name} speech model is here"}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_fw(name):
    target, part = fw_models() / name, fw_models() / (name + ".part")
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir(parents=True)
    env = dict(os.environ, HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_PROGRESS_BARS="1")
    pin = FW_PINS.get(name)
    try:
        r = subprocess.run([fw_python(), "-I", "-c", FW_GET, name, str(part), pin[0] if pin else ""],
                           stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3600, env=env)
        problem = None if r.returncode == 0 else last_line(r)
    except (OSError, TypeError, subprocess.TimeoutExpired) as exc:
        problem = str(exc)
    if problem is None and not (part / "model.bin").is_file():
        problem = "the download was cut short"
    elif problem is None and pin and file_sha256(part / "model.bin") != pin[1]:
        problem = "it isn't the file expected (another sha256)"
    if problem:
        shutil.rmtree(part, ignore_errors=True)
        return {"ok": False, "message": f"Couldn't download the {name} model: {problem}"}
    shutil.rmtree(part / ".cache", ignore_errors=True)
    shutil.rmtree(target, ignore_errors=True)
    os.replace(part, target)
    return {"ok": True, "model": str(target), "message": f"The {name} speech model is here"}


def use_model(name):
    if name == "auto":
        choose(None)
        return {"ok": True, "message": "Dictation uses the best model downloaded"}
    if name not in MODELS:
        return {"ok": False, "message": "Not a model: " + str(name)}
    eng = engine()[0]
    if eng is None or model_path(eng, name) is None:
        return {"ok": False, "message": f"The {name} model isn't downloaded"}
    choose(name)
    return {"ok": True, "message": f"Dictation uses the {name} model"}


def delete_model(name):
    if name not in MODELS:
        return {"ok": False, "message": "Not a model: " + str(name)}
    eng = engine()[0]
    path = model_path(eng, name) if eng else None
    if path is None:
        return {"ok": False, "message": f"The {name} model isn't downloaded"}
    if not widgets(path):
        return {"ok": False, "message": f"The {name} model isn't Talpy Den's to delete: it's in {Path(path).parent}"}
    with busy() as free:
        if not free:
            return {"ok": False, "message": "Dictation is being set up or a model downloaded: try again after"}
        if eng == "faster-whisper":
            shutil.rmtree(path, ignore_errors=True)
        else:
            with contextlib.suppress(FileNotFoundError):
                Path(path).unlink()
        if chosen() == name:
            choose(None)
    return {"ok": True, "message": f"The {name} model is deleted"}


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    language = "auto"
    if "--language" in args:
        i = args.index("--language")
        language = args[i + 1] if i + 1 < len(args) else "auto"
        del args[i:i + 2]
    try:
        if args == ["--status"]:
            tidy()
            result = status()
        elif args[:1] == ["--setup"] and len(args) <= 2:
            result = setup(*args[1:])
        elif len(args) == 2 and args[0] == "--start":
            result = start(args[1])
        elif len(args) == 2 and args[0] == "--stop":
            result = stop(args[1], language)
        elif len(args) == 2 and args[0] == "--cancel":
            result = cancel(args[1])
        elif len(args) == 2 and args[0] == "--get-model":
            result = get_model(args[1])
        elif len(args) == 2 and args[0] == "--use-model":
            result = use_model(args[1])
        elif len(args) == 2 and args[0] == "--delete-model":
            result = delete_model(args[1])
        elif args == ["--remove-setup"]:
            result = remove_setup()
        else:
            sys.exit(__doc__)
    except ValueError as exc:
        result = {"ok": False, "message": str(exc)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
