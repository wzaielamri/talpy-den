"""What Claude made, in Talpy Chat (made.py, pane.py --conversation's "made"
items and --made): pictures, plans and pages under the steps and replies that
made or named them, folded; unfolded, one file the transcript names, capped."""
import base64
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "package/contents/code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import made  # noqa: E402
import pane  # noqa: E402
import talpy_den as cs  # noqa: E402

from test_pane import SID, PaneFixture, text_reply, tool_result, tool_use  # noqa: E402
from test_talpy_den import iso, write  # noqa: E402
from test_tasks import prompt  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="teal"/></svg>'


def result(tid, ts, content, error=False, **kw):
    """A tool result entry whose content is blocks (an image, a document) or a text."""
    return {"type": "user", "timestamp": iso(ts), **kw,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "is_error": error,
                                                     "content": content}]}}


def image_block(data=PNG):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(data).decode()}}


class MadeFixture(PaneFixture):
    def setUp(self):
        super().setUp()
        self.t = self.now - 300
        self.cwd = str(self.folder)

    def items(self, *entries, start="make a logo"):
        for e in entries:
            e.setdefault("cwd", self.cwd)   # (as Claude Code writes every entry)
        self.chat(prompt(start, self.t, cwd=self.cwd), *entries)
        return pane.conversation(self.transcript, limit=500)[0]

    def made(self, items):
        return [(i["key"], i["of"], i["text"], i["made"]["type"], i["made"]["path"], i["made"]["size"], i["made"].get("gone", False))
                for i in items if i["kind"] == "made"]

    def at(self, n):
        return self.t + n


class MadeItemsTests(MadeFixture):
    def test_a_written_picture_page_and_plan_under_their_steps(self):
        svg, page = self.folder / "media/icon.svg", self.folder / "site/page.html"
        plan = self.home / ".claude-work/plans/brave-otter.md"
        write(svg, SVG)
        write(page, "<p>hi</p>")
        write(plan, "# Make the logo\n\n1. Draw it\n")
        items = self.items(
            tool_use("w1", "Write", {"file_path": str(svg), "content": SVG}, self.at(1), "m1"),
            tool_result("w1", self.at(2), text="File created"),
            tool_use("e1", "Edit", {"file_path": str(page), "old_string": "a", "new_string": "b"}, self.at(3), "m2"),
            tool_result("e1", self.at(4), text="updated"),
            tool_use("p1", "Write", {"file_path": str(plan), "content": "# Make the logo\n\n1. Draw it\n"}, self.at(5), "m3"),
            tool_result("p1", self.at(6)),
            tool_use("x1", "Edit", {"file_path": str(self.folder / "app.py"), "old_string": "a", "new_string": "b"}, self.at(7), "m4"),
            tool_result("x1", self.at(8)),
            tool_use("x2", "Write", {"file_path": str(self.folder / "README.md"), "content": "# Read me"}, self.at(9), "m5"),
            tool_result("x2", self.at(10)))
        self.assertEqual(self.made(items), [
            ("w1/made/0", "w1", "icon.svg", "picture", str(svg), len(SVG), False),
            ("e1/made/0", "e1", "page.html", "page", str(page), 9, False),
            ("p1/made/0", "p1", "Plan: Make the logo", "plan", str(plan), plan.stat().st_size, False)])
        keys = [i["key"] for i in items]
        self.assertEqual(keys.index("w1/made/0"), keys.index("w1") + 1)   # (right under its step)
        made = next(i for i in items if i["key"] == "w1/made/0")
        self.assertEqual((made["at"], made["made"]["name"]), (next(i for i in items if i["key"] == "w1")["at"], "icon.svg"))

    def test_a_step_that_failed_made_nothing_and_a_file_gone_since_says_so(self):
        svg = self.folder / "gone.svg"
        items = self.items(
            tool_use("w1", "Write", {"file_path": str(self.folder / "x.svg"), "content": SVG}, self.at(1), "m1"),
            tool_result("w1", self.at(2), error=True, text="<tool_use_error>No</tool_use_error>"),
            tool_use("w2", "Write", {"file_path": str(svg), "content": SVG}, self.at(3), "m2"),
            tool_result("w2", self.at(4)))
        self.assertEqual(self.made(items), [("w2/made/0", "w2", "gone.svg", "picture", str(svg), len(SVG), True)])

    def test_a_file_shows_once_a_turn_under_the_first_step(self):
        plan = self.home / ".claude-work/plans/brave-otter.md"
        write(plan, "# Ship it\n")
        steps = lambda n, t: (tool_use(f"e{n}", "Edit", {"file_path": str(plan), "old_string": "a", "new_string": "b"}, t, f"m{n}"),
                              tool_result(f"e{n}", t + 1))
        items = self.items(
            tool_use("w1", "Write", {"file_path": str(plan), "content": "# Ship it\n"}, self.at(1), "m0"), tool_result("w1", self.at(2)),
            *steps(1, self.at(3)), *steps(2, self.at(5)),
            text_reply("Done.", self.at(7), "r1", stop="end_turn"),
            prompt("again", self.at(20), cwd=self.cwd), *steps(3, self.at(21)))
        self.assertEqual([(k, text) for k, _, text, *_ in self.made(items)],
                         [("w1/made/0", "Plan: Ship it"), ("e3/made/0", "Plan: Ship it")])   # (its title from the Write)

    def test_a_plan_edited_without_its_write_is_named_after_its_file(self):
        plan = self.home / "repos/app/.claude/plans/tidy-plan.md"
        write(plan, "# Tidy\n")
        items = self.items(tool_use("e1", "Edit", {"file_path": str(plan), "old_string": "a", "new_string": "b"}, self.at(1), "m1"),
                           tool_result("e1", self.at(2)))
        self.assertEqual([text for _, _, text, *_ in self.made(items)], ["Plan: tidy-plan"])

    def test_read_results_that_carry_an_image(self):
        shot, doc = self.folder / "shot.png", self.folder / "paper.pdf"
        shot.write_bytes(PNG)
        items = self.items(
            tool_use("r1", "Read", {"file_path": str(shot)}, self.at(1), "m1"),
            result("r1", self.at(2), [image_block()], toolUseResult={"type": "image", "file": {"type": "image/png", "originalSize": 999}}),
            tool_use("r2", "Read", {"file_path": str(self.folder / "old.png")}, self.at(3), "m2"),
            result("r2", self.at(4), [image_block()], toolUseResult={"type": "image", "file": {"type": "image/png", "originalSize": 4321}}),
            tool_use("r3", "Read", {"file_path": str(self.folder / "app.py")}, self.at(5), "m3"),
            tool_result("r3", self.at(6), text="1→print(1)"),
            tool_use("r4", "Read", {"file_path": str(doc)}, self.at(7), "m4"),
            result("r4", self.at(8), [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "JVBERi0="}}],
                   toolUseResult={"type": "pdf", "file": {"filePath": str(doc), "originalSize": 2048}}),
            tool_use("r5", "Read", {"file_path": str(self.folder / "logo.svg")}, self.at(9), "m5"),
            tool_result("r5", self.at(10), text="1→<svg/>"))
        self.assertEqual(self.made(items), [
            # (what Claude saw: the transcript has it, gone or not; the file's size as the transcript says, nothing read)
            ("r1/made/0", "r1", "shot.png", "picture", str(shot), 999, False),
            ("r2/made/0", "r2", "old.png", "picture", str(self.folder / "old.png"), 4321, False),
            ("r4/made/0", "r4", "paper.pdf", "file", str(doc), 2048, True),
            ("r5/made/0", "r5", "logo.svg", "picture", str(self.folder / "logo.svg"), None, True)])
        self.assertEqual([i["made"].get("step") for i in items if i["kind"] == "made"], ["r1", "r2", None, None])

    def test_each_picture_claude_saw_in_a_turn(self):
        # (one screenshot path read again after it was made anew: each picture once; a reply that names it: shown)
        shot = self.folder / "shot.png"
        shot.write_bytes(PNG)
        reads = [(n, image_block(data)) for n, data in enumerate((PNG, PNG + b"2", PNG))]
        items = self.items(*[e for n, block in reads for e in (
            tool_use(f"r{n}", "Read", {"file_path": str(shot)}, self.at(2 * n + 1), f"m{n}"), result(f"r{n}", self.at(2 * n + 2), [block]))],
            text_reply(f"Look at {shot}", self.at(9), "r9"))
        self.assertEqual([(k, size) for k, _, _, _, _, size, _ in self.made(items)], [("r0/made/0", len(PNG)), ("r1/made/0", len(PNG) + 1)])

    def test_a_command_that_names_a_new_picture(self):
        new, old = self.folder / "out/render.png", self.folder / "base.png"
        new.parent.mkdir()
        new.write_bytes(PNG)
        old.write_bytes(PNG)
        os.utime(old, (self.t - 3600, self.t - 3600))   # (from before the turn)
        os.utime(new, (self.at(2), self.at(2)))
        items = self.items(
            tool_use("b0", "Bash", {"command": "python3 render.py --in base.png --out=out/render.png"}, self.at(1), "m0"),
            tool_result("b0", self.at(3), text=""),   # (its command isn't what it made: what it printed is)
            tool_use("b1", "Bash", {"command": "python3 render.py"}, self.at(1), "m1"),
            tool_result("b1", self.at(3), text=f"Saved {new}\nfrom {old}\nsee https://example.com/a.png and *.png, {self.folder}/none.png"),
            tool_use("b2", "Bash", {"command": "ls"}, self.at(4), "m2"),
            tool_result("b2", self.at(5), text="out/render.png  app.py"))   # (relative to the folder: the same file, shown already)
        self.assertEqual(self.made(items), [("b1/made/0", "b1", "render.png", "picture", str(new), len(PNG), False)])

    def test_pictures_a_reply_names_that_are_there(self):
        shot, rel = self.home / "shots/final.png", self.folder / "docs/look.webp"
        write(shot, "x")
        write(rel, "yy")
        svg = self.folder / "icon.svg"
        write(svg, SVG)
        items = self.items(
            tool_use("w1", "Write", {"file_path": str(svg), "content": SVG}, self.at(1), "m1"),
            tool_result("w1", self.at(2)),
            text_reply(f"Here it is: ![final]({shot}), and `docs/look.webp`; also {svg} and /nowhere/missing.png.",
                       self.at(3), "r1", stop="end_turn"))
        self.assertEqual(self.made(items), [
            ("w1/made/0", "w1", "icon.svg", "picture", str(svg), len(SVG), False),
            ("r1/made/0", "r1", "final.png", "picture", str(shot), 1, False),
            ("r1/made/1", "r1", "look.webp", "picture", str(rel), 2, False)])   # (icon.svg: under its step already)
        keys = [i["key"] for i in items]
        self.assertEqual(keys[keys.index("r1") + 1:], ["r1/made/0", "r1/made/1"])

    def test_parallel_steps_each_get_theirs(self):
        a, b = self.folder / "a.svg", self.folder / "b.svg"
        write(a, SVG)
        write(b, SVG)
        both = {"type": "assistant", "timestamp": iso(self.at(1)),
                "message": {"id": "m1", "role": "assistant", "content": [
                    {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": str(a), "content": SVG}},
                    {"type": "tool_use", "id": "t2", "name": "Write", "input": {"file_path": str(b), "content": SVG}}]}}
        items = self.items(both, tool_result("t1", self.at(2)), tool_result("t2", self.at(3)))
        self.assertEqual([i["key"] for i in items if i["kind"] != "you"], ["t1", "t1/made/0", "t2", "t2/made/0"])

    def test_the_cli_answer_has_them(self):
        svg = self.folder / "icon.svg"
        write(svg, SVG)
        self.chat(prompt("draw", self.t, cwd=self.cwd), tool_use("w1", "Write", {"file_path": str(svg), "content": SVG}, self.at(1)),
                  tool_result("w1", self.at(2)))
        got = self.cli("--conversation", SID, "--profile", ".claude-work")
        self.assertTrue(got["ok"], got)
        made_items = [i for i in got["items"] if i["kind"] == "made"]
        self.assertEqual(made_items, [{"kind": "made", "key": "w1/made/0", "of": "w1", "at": int(self.at(1) * 1000), "text": "icon.svg",
                                       "made": {"path": str(svg), "type": "picture", "name": "icon.svg", "size": len(SVG)}}])

    def test_a_long_chat_reads_as_quickly(self):
        # (nothing is read for a step or a reply that names no such file: one stat a file named)
        entries = []
        for n in range(300):
            entries += [tool_use(f"b{n}", "Bash", {"command": f"echo {n}"}, self.at(n), f"m{n}"),
                        tool_result(f"b{n}", self.at(n) + 0.5, text="ok " * 200),
                        text_reply("Done, see the parser and the cache. " * 20, self.at(n) + 0.7, f"r{n}")]
        self.chat(prompt("go", self.t, cwd=self.cwd), *entries)
        with mock.patch.object(made.Collector, "stat", side_effect=AssertionError("stat")):
            items, _ = pane.conversation(self.transcript, limit=2000)
        self.assertFalse([i for i in items if i["kind"] == "made"])


class ShowMadeTests(MadeFixture):
    """pane.py --made: one file the chat's transcript names, unfolded."""

    def setUp(self):
        super().setUp()
        self.svg = self.folder / "icon.svg"
        self.plan = self.home / ".claude-work/plans/brave-otter.md"
        self.page = self.folder / "page.html"
        self.png = self.folder / "shot.png"
        write(self.svg, SVG)
        write(self.plan, "# Plan\n\n" + "".join(f"- step {n}\n" for n in range(made.PLAN_LINES + 10)))
        write(self.page, "\n".join(f"<p>{n}</p>" for n in range(made.SOURCE_LINES + 5)))
        self.png.write_bytes(PNG)
        self.chat(prompt("make them", self.t, cwd=self.cwd),
                  *[e for n, p in enumerate((self.svg, self.plan, self.page))
                    for e in (tool_use(f"w{n}", "Write", {"file_path": str(p), "content": "x"}, self.at(n)), tool_result(f"w{n}", self.at(n) + 0.5))],
                  tool_use("r1", "Read", {"file_path": str(self.png)}, self.at(9)), result("r1", self.at(10), [image_block()]))

    def show(self, path, *more):
        return self.cli("--made", SID, "--path", str(path), "--profile", ".claude-work", *more)

    def test_a_picture_comes_as_its_bytes(self):
        got = self.show(self.png)
        self.assertEqual((got["ok"], got["type"], got["mime"], got["size"]), (True, "picture", "image/png", len(PNG)))
        self.assertEqual(base64.b64decode(got["data"]), PNG)
        svg = self.show(self.svg)
        self.assertEqual((svg["mime"], base64.b64decode(svg["data"]).decode()), ("image/svg+xml", SVG))

    def test_a_plan_and_a_pages_source_come_as_their_first_lines(self):
        plan = self.show(self.plan)
        self.assertEqual((plan["type"], plan["cut"]), ("plan", True))
        self.assertEqual(plan["text"].split("\n")[:3], ["# Plan", "", "- step 0"])
        self.assertEqual(len(plan["text"].split("\n")), made.PLAN_LINES)
        page = self.show(self.page)
        self.assertEqual((page["type"], page["cut"], len(page["text"].split("\n"))), ("page", True, made.SOURCE_LINES))

    def test_only_a_file_the_chat_made_of_those_types(self):
        other = self.folder / "other.png"
        other.write_bytes(PNG)   # (there, but this chat never named it)
        secret = self.folder / "secret.txt"
        write(secret, "x")
        for path in (other, secret, self.folder / "sub/../icon.svg", "icon.svg", self.home / ".claude-work/README.md"):
            got = self.show(path)
            self.assertFalse(got["ok"], path)
            self.assertNotIn("data", got)
        self.assertFalse(self.cli("--made", "not-a-chat", "--path", str(self.svg))["ok"])

    def test_gone_too_big_or_not_a_plain_file(self):
        self.png.unlink()
        self.assertEqual({k: v for k, v in self.show(self.png).items() if k != "message"}, {"ok": False, "gone": True})
        write(self.svg, "<svg>" + " " * made.SVG_SHOW_MAX + "</svg>")
        big = self.show(self.svg)
        self.assertEqual((big["ok"], big.get("big")), (False, True))
        self.assertIn("MB", big["message"])
        self.png.parent.mkdir(exist_ok=True)
        os.mkfifo(self.png)   # (a pipe named like a picture is never waited on)
        started = time.time()
        self.assertEqual(self.show(self.png)["message"], "It isn't a plain file")
        self.assertLess(time.time() - started, 5)

    def test_plasmas_picture_of_this_computer_is_its_path_once_its_a_plain_file(self):
        got = self.show(self.svg, "--as-file")
        self.assertEqual((got["ok"], got["file"], got["size"], "data" in got), (True, str(self.svg), len(SVG), False))
        write(self.svg, "<svg>" + " " * made.SVG_SHOW_MAX + "</svg>")
        self.assertEqual(self.show(self.svg, "--as-file").get("big"), True)
        self.png.unlink()
        os.mkfifo(self.png)   # (Qt's image reader would wait on a pipe for good)
        self.assertEqual(self.show(self.png, "--as-file"), {"ok": False, "message": "It isn't a plain file"})

    def test_what_claude_saw_comes_from_the_transcript(self):
        self.png.unlink()   # (gone since: the transcript has what Claude saw)
        got = self.show(self.png, "--step", "r1")
        self.assertEqual((got["ok"], got["seen"], got["mime"], got["size"]), (True, True, "image/png", len(PNG)))
        self.assertEqual(base64.b64decode(got["data"]), PNG)
        kept = self.show(self.png, "--step", "r1", "--as-file")   # (Plasma's: a copy here)
        self.assertEqual((Path(kept["file"]).read_bytes(), Path(kept["file"]).suffix, "data" in kept), (PNG, ".png", False))
        self.assertEqual(Path(kept["file"]).parent, cs.images_dir(self.home))
        for step in ("w0", "nope", "../x", "r1\"x"):   # (not a Read that got a picture)
            self.assertEqual(self.show(self.png, "--step", step)["ok"], False, step)

    def test_an_ssh_hosts_picture_kept_here_as_a_file(self):
        answer = {"ok": True, "type": "picture", "mime": "image/png", "data": base64.b64encode(PNG).decode(), "size": len(PNG)}
        with mock.patch("remote.host_answer", return_value=dict(answer)) as asked:
            got = self.cli("--made", SID, "--path", "/srv/app/shot.png", "--host", "devbox", "--as-file")
        self.assertEqual(asked.call_args[0][1], ["--made", SID, "--path", "/srv/app/shot.png", "--as-file"])
        self.assertIn("made.py", asked.call_args[1]["also"])
        self.assertNotIn("data", got)
        self.assertEqual(Path(got["file"]).parent, cs.images_dir(self.home))
        self.assertEqual(Path(got["file"]).read_bytes(), PNG)
        self.assertEqual(Path(got["file"]).stat().st_mode & 0o777, 0o600)
        with mock.patch("remote.host_answer", return_value=dict(answer)):   # (VS Code's: the bytes)
            self.assertEqual(self.cli("--made", SID, "--path", "/srv/app/shot.png", "--host", "devbox")["data"], answer["data"])


class PathsTests(unittest.TestCase):
    def test_named_paths(self):
        text = ("See /a/b.png, `rel/c.JPG` and ./d.gif or ../e.webp; ![x](f.svg) file:///g/h.png https://i.com/j.png "
                "*.png k/*.png --out=/l.png /m.png:12 /m.png again")
        self.assertEqual(made.named_paths(text, "/w"), ["/a/b.png", "/w/rel/c.JPG", "/w/d.gif", "/e.webp", "/w/f.svg", "/g/h.png",
                                                         "/l.png", "/m.png"])
        self.assertEqual(made.named_paths(text, None), ["/a/b.png", "/g/h.png", "/l.png", "/m.png"])
        self.assertEqual(made.named_paths("nothing here", "/w"), [])
        self.assertEqual(len(made.named_paths(" ".join(f"/p/{n}.png" for n in range(50)), "/w")), made.NAMED_MAX)

    def test_types(self):
        self.assertEqual([made.type_of(p) for p in ("/a/x.PNG", "/a/x.htm", "/h/.claude/plans/p.md", "/a/README.md", "/a/x.py")],
                         ["picture", "page", "plan", None, None])


if __name__ == "__main__":
    unittest.main()
