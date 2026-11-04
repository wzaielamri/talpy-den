"""Dictating a reply (dictate.py): recorded here, written down by whisper.cpp
here; run with stand-ins for the recorder and whisper.cpp."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
sys.path.insert(0, str(CODE))
import dictate  # noqa: E402

# Whether this Python can make an environment (Debian and Ubuntu leave venv
# out until python3-venv is installed): dictate.py run here offers the setup then
CAN_VENV = dictate.can_venv()
NO_VENV = "Python's venv, to set up dictation (Debian, Ubuntu: sudo apt install python3-venv)"

# Records until it's interrupted (SIGINT), as pw-record does: a WAV file
FAKE_RECORDER = """#!{python}
import signal, sys, time
out = sys.argv[-1]
def done(*_):
    open(out, "wb").write(b"RIFF" + b"\\0" * 8000)
    sys.exit(0)
signal.signal(signal.SIGINT, done)
open({log!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")
while True:
    time.sleep(0.05)
"""
FAKE_WHISPER = """#!{python}
import sys
open({log!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")
print(" Make the parser accept ISO weeks.")
print(" [BLANK_AUDIO]")
print(" Then run the tests.")
"""


class DictateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.log = self.home / "calls.log"
        self.model = self.home / "ggml-base.bin"
        self.model.write_bytes(b"model")

    def tool(self, name, source):
        path = self.bin / name
        path.write_text(source.format(python=sys.executable, log=str(self.log)))
        path.chmod(0o755)

    def run_it(self, *args, model=True):
        env = dict(os.environ, HOME=str(self.home), XDG_CACHE_HOME=str(self.home / "cache"),
                   XDG_DATA_HOME=str(self.home / "data"), PATH=f"{self.bin}:/usr/bin:/bin")
        if model:
            env["WHISPER_MODEL"] = str(self.model)
        else:
            env.pop("WHISPER_MODEL", None)
        out = subprocess.run([sys.executable, "-I", str(CODE / "dictate.py"), *args], stdout=subprocess.PIPE, env=env,
                             timeout=30)
        return json.loads(out.stdout)

    def test_recorded_then_written_down_and_the_recording_goes(self):
        self.tool("pw-record", FAKE_RECORDER)
        self.tool("whisper-cli", FAKE_WHISPER)
        self.assertTrue(self.run_it("--status")["ok"])
        self.assertEqual(self.run_it("--start", "r1")["message"], "Recording")
        time.sleep(0.3)
        got = self.run_it("--stop", "r1", "--language", "de")
        self.assertEqual(got, {"ok": True, "text": "Make the parser accept ISO weeks. Then run the tests.", "message": ""})
        calls = self.log.read_text()
        self.assertIn("--rate 16000 --channels 1 --format s16", calls)
        self.assertIn(f"-m {self.model}", calls)
        self.assertIn("-l de", calls)
        folder = self.home / "cache/talpy-den/dictation"
        self.assertEqual(list(folder.iterdir()), [])   # (what you said isn't kept)
        self.assertEqual(oct(folder.stat().st_mode & 0o777), "0o700")

    def test_cancelled_nothing_is_written_down(self):
        self.tool("pw-record", FAKE_RECORDER)
        self.tool("whisper-cli", FAKE_WHISPER)
        self.run_it("--start", "r2")
        time.sleep(0.2)
        self.assertEqual(self.run_it("--cancel", "r2"), {"ok": True, "message": "Not written down"})
        self.assertNotIn("-m ", self.log.read_text())
        self.assertEqual(list((self.home / "cache/talpy-den/dictation").iterdir()), [])

    def test_cancelled_before_it_started(self):
        # the pane closed while the recording started: the cancel can come
        # first, and the start then stops at once
        self.tool("pw-record", FAKE_RECORDER)
        self.assertEqual(self.run_it("--cancel", "r4"), {"ok": True, "message": "Not written down"})
        self.assertEqual(self.run_it("--start", "r4"), {"ok": False, "message": "Not written down"})
        self.assertEqual(list((self.home / "cache/talpy-den/dictation").iterdir()), [])

    def test_a_recording_left_behind_goes(self):
        # (a widget that stopped while it recorded): gone once the recorder
        # surely has, at the next look; a recent one stays
        folder = self.home / "cache/talpy-den/dictation"
        folder.mkdir(parents=True)
        for name in ("r5.wav", "r5.pid", "r6.cancel", "r7.wav"):
            (folder / name).write_text("2147483646" if name.endswith(".pid") else "x")
        for name in ("r5.wav", "r5.pid", "r6.cancel"):
            os.utime(folder / name, (time.time() - 2 * 3600,) * 2)
        self.tool("pw-record", FAKE_RECORDER)
        self.run_it("--status")
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["r7.wav"])

    def test_nothing_to_write_with_offers_the_setup(self):
        self.tool("pw-record", FAKE_RECORDER)
        got = self.run_it("--status", model=False)
        self.assertFalse(got["ok"])
        self.assertIsNone(got["engine"])
        self.assertIsNone(got["model"])
        self.assertEqual(got["canSetup"], CAN_VENV)
        self.assertEqual(got["missing"], [] if CAN_VENV else [NO_VENV])
        self.assertEqual([m["name"] for m in got["models"]], ["tiny", "base", "base.en", "small", "medium", "large-v3-turbo"])
        self.assertFalse(any(m["installed"] for m in got["models"]))
        self.assertEqual(self.run_it("--get-model", "base"), {"ok": False, "message": "Set up dictation first"})

    def test_whisper_cpp_models_found_chosen_and_deleted(self):
        self.tool("pw-record", FAKE_RECORDER)
        self.tool("whisper-cli", FAKE_WHISPER)
        # one downloaded by the widget, one whisper.cpp keeps (not the widget's to delete)
        folder = self.home / "data/talpy-den/whisper"
        folder.mkdir(parents=True)
        (folder / "ggml-base.bin").write_bytes(b"m")
        theirs = self.home / ".local/share/whisper.cpp/models"
        theirs.mkdir(parents=True)
        (theirs / "ggml-small.bin").write_bytes(b"m")
        got = self.run_it("--status", model=False)
        self.assertEqual((got["engine"], got["modelName"], got["chosen"]), ("whisper.cpp", "small", "auto"))
        installed = {m["name"]: m["deletable"] for m in got["models"] if m["installed"]}
        self.assertEqual(installed, {"base": True, "small": False})
        self.assertTrue(self.run_it("--use-model", "base", model=False)["ok"])
        self.assertEqual(self.run_it("--status", model=False)["model"], str(folder / "ggml-base.bin"))
        self.assertFalse(self.run_it("--delete-model", "small", model=False)["ok"])
        self.assertTrue(self.run_it("--delete-model", "base", model=False)["ok"])
        got = self.run_it("--status", model=False)
        self.assertEqual((got["modelName"], got["chosen"]), ("small", "auto"))

    def test_odd_ids_and_models_are_refused(self):
        self.assertEqual(self.run_it("--start", "../x"), {"ok": False, "message": "Not a recording: ../x"})
        self.assertEqual(self.run_it("--get-model", "huge"), {"ok": False, "message": "Not a model: huge"})
        self.assertEqual(self.run_it("--use-model", "huge"), {"ok": False, "message": "Not a model: huge"})


# faster-whisper's Python as dictate.py runs it (-I -c SCRIPT ARGS…): writes
# down, or "downloads" a model into the folder it's given
FAKE_FW_PYTHON = """#!{python}
import os, sys
script, args = sys.argv[3], sys.argv[4:]
open({log!r}, "a").write(" ".join(args) + " offline=" + os.environ.get("HF_HUB_OFFLINE", "") + "\\n")
if "download_model" in script:
    os.makedirs(os.path.join(args[1], ".cache"), exist_ok=True)
    open(os.path.join(args[1], "model.bin"), "w").write("m")
else:
    print("Make the parser accept ISO weeks.")
    print("Then run the tests.")
"""


class FasterWhisperTests(DictateTests):
    """Set up: its environment (a stand-in Python) in the widget's folder."""
    def setUp(self):
        super().setUp()
        self.whisper = self.home / "data/talpy-den/whisper"
        python = self.whisper / "venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text(FAKE_FW_PYTHON.format(python=sys.executable, log=str(self.log)))
        python.chmod(0o755)
        (self.whisper / "venv/.ready").write_text("faster-whisper")
        self.tool("pw-record", FAKE_RECORDER)

    def fw_model(self, name):
        (self.whisper / "models" / name).mkdir(parents=True)
        (self.whisper / "models" / name / "model.bin").write_bytes(b"m")

    def test_recorded_then_written_down_offline(self):
        self.fw_model("base")
        got = self.run_it("--status", model=False)
        self.assertTrue(got["ok"])
        self.assertEqual((got["engine"], got["modelName"], got["setUp"]), ("faster-whisper", "base", True))
        self.run_it("--start", "r1")
        time.sleep(0.3)
        got = self.run_it("--stop", "r1", "--language", "de", model=False)
        self.assertEqual(got, {"ok": True, "text": "Make the parser accept ISO weeks. Then run the tests.", "message": ""})
        line = self.log.read_text().splitlines()[-1]
        self.assertTrue(line.startswith(str(self.whisper / "models/base") + " "), line)
        self.assertIn(" de ", line)
        self.assertTrue(line.endswith("offline=1"))   # (nothing over the network)
        self.assertEqual(list((self.home / "cache/talpy-den/dictation").iterdir()), [])

    def test_models_downloaded_chosen_and_deleted(self):
        self.fw_model("base")
        got = self.run_it("--get-model", "small", model=False)
        self.assertTrue(got["ok"], got)
        self.assertEqual(sorted(p.name for p in (self.whisper / "models").iterdir()), ["base", "small"])
        self.assertFalse((self.whisper / "models/small/.cache").exists())
        got = self.run_it("--status", model=False)
        self.assertEqual((got["modelName"], got["chosen"]), ("small", "small"))   # (the one downloaded is used)
        self.assertTrue(all(m["deletable"] for m in got["models"] if m["installed"]))
        self.assertEqual(self.run_it("--use-model", "medium", model=False),
                         {"ok": False, "message": "The medium model isn't downloaded"})
        self.assertTrue(self.run_it("--use-model", "base", model=False)["ok"])
        self.assertEqual(self.run_it("--status", model=False)["modelName"], "base")
        self.assertTrue(self.run_it("--delete-model", "base", model=False)["ok"])
        got = self.run_it("--status", model=False)
        self.assertEqual((got["modelName"], got["chosen"]), ("small", "auto"))
        self.assertTrue(self.run_it("--remove-setup", model=False)["ok"])
        got = self.run_it("--status", model=False)
        self.assertEqual((got["engine"], got["setUp"], got["canSetup"]), (None, False, CAN_VENV))
        self.assertEqual(sorted(p.name for p in self.whisper.iterdir()), [".busy"])

    def test_setup_once_set_up_only_brings_the_model(self):
        # (its environment is made already: Python's venv isn't needed for it)
        got = self.run_it("--setup", model=False)
        self.assertTrue(got["ok"], got)
        self.assertTrue((self.whisper / "models/base/model.bin").is_file())
        self.assertEqual(self.log.read_text().count("base "), 1)

    def in_process(self):
        env = mock.patch.dict(os.environ, {"HOME": str(self.home), "XDG_DATA_HOME": str(self.home / "data")})
        env.start()
        self.addCleanup(env.stop)

    def test_set_up_without_pythons_venv(self):
        # set up once (an environment made then): a model comes without venv
        self.in_process()
        with mock.patch.object(dictate, "can_venv", return_value=False), \
                mock.patch.object(dictate, "fetch_fw", return_value={"ok": True}) as fetched:
            got = dictate.setup("small")
        self.assertTrue(got["ok"], got)
        fetched.assert_called_once_with("small")
        # not set up: venv is what it needs
        (self.whisper / "venv/.ready").unlink()
        with mock.patch.object(dictate, "can_venv", return_value=False), \
                mock.patch.object(dictate.subprocess, "run") as ran:
            got = dictate.setup("base")
        self.assertEqual(got, {"ok": False, "message": "To set up dictation, install Python's venv "
                                                       "(Debian, Ubuntu: sudo apt install python3-venv)"})
        ran.assert_not_called()
        self.assertTrue((self.whisper / "venv/bin/python").is_file())   # (nothing was removed)

    def test_a_setup_makes_the_environment(self):
        # The steps of a first setup, in order (the environment, pip's install
        # and the model stood in for: nothing is downloaded, no venv needed here)
        self.in_process()
        (self.whisper / "venv/.ready").unlink()
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[1:3] == ["-m", "venv"]:
                (Path(cmd[3]) / "bin").mkdir(parents=True)
                (Path(cmd[3]) / "bin/python").write_text("")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        with mock.patch.object(dictate, "can_venv", return_value=True), \
                mock.patch.object(dictate.subprocess, "run", side_effect=run), \
                mock.patch.object(dictate, "fetch_fw", return_value={"ok": True}):
            got = dictate.setup("base")
        self.assertTrue(got["ok"], got)
        self.assertEqual([c[1:3] for c in calls], [["-m", "venv"], ["-I", "-m"], ["-I", "-c"]])
        self.assertEqual(calls[1][0], str(self.whisper / "venv/bin/python"))
        self.assertEqual(calls[1][-3:], ["-c", str(self.whisper / "venv/constraints.txt"), dictate.FW_PACKAGE])
        self.assertIn('faster-whisper==1.2.1; python_version == "3.14"', (self.whisper / "venv/constraints.txt").read_text())
        self.assertTrue((self.whisper / "venv/.ready").is_file())

    def test_a_pinned_model_is_kept_only_with_its_sha256(self):
        self.in_process()
        asked = []

        def urlopen(url, timeout=None):
            asked.append(url)
            return io.BytesIO(b"not the model")
        with mock.patch.dict(dictate.MODELS, {"tiny": ("ggml-tiny.bin", 0, "")}), \
                mock.patch.dict(dictate.GGML_PINS, {"tiny": ("abc123", "0" * 64)}), \
                mock.patch.object(dictate.urllib.request, "urlopen", urlopen):
            got = dictate.fetch_ggml("tiny")
        self.assertEqual(got["message"], "Couldn't download the tiny model: it isn't the file expected (another sha256)")
        self.assertEqual(asked, ["https://huggingface.co/ggerganov/whisper.cpp/resolve/abc123/ggml-tiny.bin"])
        self.assertEqual(list(dictate.data_dir().glob("ggml-tiny.bin*")), [])

    def test_one_download_at_a_time(self):
        import fcntl
        self.whisper.mkdir(parents=True, exist_ok=True)
        with open(self.whisper / ".busy", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            got = self.run_it("--get-model", "tiny", model=False)
        self.assertEqual(got, {"ok": False, "message": "Dictation is being set up or a model downloaded already"})
        self.assertFalse((self.whisper / "models/tiny").exists())

    # (whisper.cpp's own tests, without whisper.cpp here)
    test_recorded_then_written_down_and_the_recording_goes = None
    test_cancelled_nothing_is_written_down = None
    test_nothing_to_write_with_offers_the_setup = None
    test_whisper_cpp_models_found_chosen_and_deleted = None


if __name__ == "__main__":
    unittest.main()
