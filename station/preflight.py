"""Quitting the other apps before a run, so the station has the memory.

The laptop has 8 GB. With a CAD program, an editor and a browser open beside
the station, most of what the trackers need gets pushed out to disk, and
frames wait on it coming back.

`quit_others` asks each open app to quit the way Cmd-Q does. One with nothing
to save goes; one with unsaved work puts up its own dialog and stays open.
Nothing is forced, so nothing is lost: whatever is still open afterwards is
named, and it waits while you deal with it.

`python3 -m station --quit-apps` does this before a run. The `quit-apps`
command does only this, from any terminal; `quit-apps --list` names the apps
and quits nothing.
"""

import argparse
import json
import os
import subprocess
import sys
import time

# Never asked to quit. Whatever the station was started from (Terminal, or
# VS Code) is kept too: see `_ancestors`.
KEEP = {"com.apple.finder"}
# Apps that live in the menu bar are left alone, except these: big, and no
# use to the station.
BACKGROUND = {"com.grammarly.ProjectLlama"}
# How long an app gets to quit before it's taken to be asking you something.
QUIT_S = 15.0

# Through AppKit rather than `tell application ... to quit`: macOS doesn't ask
# for permission to control each app, and the station's Chrome and your own
# are told apart by pid.
_APPS_JS = """
ObjC.import("AppKit");
function run(argv) {
  var apps = $.NSWorkspace.sharedWorkspace.runningApplications, out = [];
  for (var i = 0; i < apps.count; i++) {
    var a = apps.objectAtIndex(i), pid = Number(a.processIdentifier);
    if (argv.indexOf(String(pid)) >= 0) a.terminate;
    out.push({pid: pid, id: ObjC.unwrap(a.bundleIdentifier),
              name: ObjC.unwrap(a.localizedName),
              dock: Number(a.activationPolicy) === 0});
  }
  return JSON.stringify(out);
}
"""


def quit_others(wait_s=QUIT_S):
    """Quit every app the station doesn't need, and say what is left."""
    apps = others(running_apps(), _ancestors())
    if not apps:
        print("No other apps are open.")
        return
    print(f"Quitting {_names(apps)}")
    running_apps(quit=[a["pid"] for a in apps])
    left = _wait(apps, wait_s)
    if left and sys.stdin.isatty():
        print(f"Still open: {_names(left)}")
        try:
            input("Each is asking about unsaved work, or is slow to close. "
                  "Switch to it and answer, then press Enter here: ")
        except EOFError:
            print()
        left = [a for a in left if _alive(a["pid"])]
    if left:
        print(f"Left open: {_names(left)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="quit-apps",
                                description=__doc__.split("\n")[0])
    p.add_argument("--list", action="store_true",
                   help="name the apps that would be quit, and quit nothing")
    args = p.parse_args(argv)
    if args.list:
        apps = others(running_apps(), _ancestors())
        print(f"Would quit {_names(apps)}" if apps
              else "No other apps are open.")
    else:
        quit_others()


def running_apps(quit=()):
    """Every running app, as dicts of pid, id (its bundle id), name and dock
    (whether it shows in the Dock). Those with a pid in `quit` are asked to
    quit."""
    out = subprocess.run(["osascript", "-l", "JavaScript", "-e", _APPS_JS,
                          *map(str, quit)],
                         capture_output=True, text=True, check=True).stdout
    # macOS also lists apps it means to reopen and hasn't started.
    return [a for a in json.loads(out) if _alive(a["pid"])]


def others(apps, ancestors, keep=KEEP, background=BACKGROUND):
    """The apps to quit: everything in the Dock and the menu-bar apps named
    in `background`, less the ones kept and the ones this process runs in."""
    return [a for a in apps
            if (a["dock"] or a.get("id") in background)
            and a.get("id") not in keep and a["pid"] not in ancestors]


def _wait(apps, wait_s):
    """The apps still running once all have quit or `wait_s` has passed."""
    end = time.monotonic() + wait_s
    while True:
        apps = [a for a in apps if _alive(a["pid"])]
        if not apps or time.monotonic() >= end:
            return apps
        time.sleep(0.25)


def _ancestors():
    """This process and every one above it. The top of that chain is the app
    the station was started from."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid="],
                         capture_output=True, text=True).stdout
    parent = {}
    for line in out.splitlines():
        pid, ppid = line.split()
        parent[int(pid)] = int(ppid)
    pids, pid = set(), os.getpid()
    while pid and pid not in pids:
        pids.add(pid)
        pid = parent.get(pid, 0)
    return pids


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _names(apps):
    # WhatsApp's name starts with an invisible left-to-right mark.
    return ", ".join("".join(c for c in a["name"] if c.isprintable())
                     for a in apps)
