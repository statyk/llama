#!/usr/bin/env python3
"""Go-live probes for the station share: lock races and mtime-preserving rewrites.

Stdlib only and Python 3.11-compatible, so it also runs on hugo with python3.
It imports neither emcee nor llama.

  race  --dir D [--n 1000] [--workers 2]   exclusive-create / token-unlink race
  mtime --dir D --create | --replace NAME | --remove NAME
  cross --dir D --role a|b --n N --tag T    one side of a two-host race
"""
import argparse
import glob
import multiprocessing
import os
import secrets
import sys
import time

TARGET_MTIME = 1767225600  # 2026-01-01T00:00:00Z
HOLD_SECONDS = 0.005
_DROP_ENV = "STATION_PROBE_TEST_DROP_EXCL"


def _counts():
    return {"acquired": 0, "contended": 0, "vanished": 0, "double": 0, "overlap": 0}


def _race_loop(directory, name, n, worker, barrier=None):
    """Run n rounds of exclusive create against `name`; return the counts."""
    c = _counts()
    path = os.path.join(directory, name)
    marker = "%s.held-%s" % (path, worker)
    flags = os.O_CREAT | os.O_WRONLY
    if os.environ.get(_DROP_ENV) != "1":
        flags |= os.O_EXCL
    if barrier is not None:
        barrier.wait(timeout=60)
    for _ in range(n):
        token = secrets.token_hex(16)
        try:
            fd = os.open(path, flags, 0o644)
        except FileExistsError:
            c["contended"] += 1
            try:
                with open(path, "rb") as f:
                    f.read()
            except FileNotFoundError:
                c["vanished"] += 1
            except OSError:
                pass
            continue
        try:
            os.write(fd, token.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        c["acquired"] += 1
        open(marker, "w").close()
        others = [m for m in glob.glob(path + ".held-*") if m != marker]
        if others:
            c["overlap"] += 1
        time.sleep(HOLD_SECONDS)
        try:
            with open(path, "r") as f:
                held = f.read()
        except FileNotFoundError:
            held = None
        if held != token:
            c["double"] += 1
        try:
            os.unlink(marker)
        except FileNotFoundError:
            pass
        try:
            with open(path, "r") as f:
                mine = f.read() == token
            if mine:
                os.unlink(path)
        except FileNotFoundError:
            pass
    return c


def _worker_main(directory, name, n, worker, barrier, queue):
    try:
        queue.put(_race_loop(directory, name, n, worker, barrier))
    except BaseException as e:  # report rather than hang the parent
        queue.put({"error": repr(e)})


def _merge(results):
    total = _counts()
    for r in results:
        for k in total:
            total[k] += r[k]
    return total


def _print_counts(c):
    print("acquired %d contended %d vanished %d double %d marker-overlap %d (advisory)"
          % (c["acquired"], c["contended"], c["vanished"], c["double"], c["overlap"]))


def _cleanup(directory, name):
    for p in glob.glob(os.path.join(directory, name) + "*"):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


def cmd_race(args):
    name = ".lock-race-" + secrets.token_hex(4)
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(args.workers)
    queue = ctx.Queue()
    procs = [ctx.Process(target=_worker_main,
                         args=(args.dir, name, args.n, "w%d" % i, barrier, queue))
             for i in range(args.workers)]
    try:
        for p in procs:
            p.start()
        results = [queue.get(timeout=300) for _ in procs]
        for p in procs:
            p.join()
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
        _cleanup(args.dir, name)
    errors = [r["error"] for r in results if "error" in r]
    if errors:
        print("worker error: " + "; ".join(errors), file=sys.stderr)
        return 2
    c = _merge(results)
    _print_counts(c)
    return 0 if c["double"] == 0 else 1


def cmd_cross(args):
    name = ".lock-race-" + args.tag
    try:
        c = _race_loop(args.dir, name, args.n, args.role)
    finally:
        # The lock file is shared with the other host; only remove our own marker.
        try:
            os.unlink(os.path.join(args.dir, name) + ".held-" + args.role)
        except FileNotFoundError:
            pass
    _print_counts(c)
    return 0 if c["double"] == 0 else 1


def cmd_mtime(args):
    d = args.dir
    if args.create:
        name = ".mtime-probe-" + secrets.token_hex(4)
        with open(os.path.join(d, name), "w") as f:
            f.write("original\n")
            f.flush()
            os.fsync(f.fileno())
        print(name)
        return 0
    if args.remove:
        os.unlink(os.path.join(d, args.remove))
        return 0
    path = os.path.join(d, args.replace)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write("replaced\n")
            f.flush()
            os.fsync(f.fileno())
        os.utime(tmp, (TARGET_MTIME, TARGET_MTIME))
        os.rename(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    if int(os.stat(path).st_mtime) != TARGET_MTIME:
        os.utime(path, (TARGET_MTIME, TARGET_MTIME))
    print(TARGET_MTIME)
    return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("race")
    r.add_argument("--dir", required=True)
    r.add_argument("--n", type=int, default=1000)
    r.add_argument("--workers", type=int, default=2)
    r.set_defaults(func=cmd_race)
    m = sub.add_parser("mtime")
    m.add_argument("--dir", required=True)
    g = m.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true")
    g.add_argument("--replace", metavar="NAME")
    g.add_argument("--remove", metavar="NAME")
    m.set_defaults(func=cmd_mtime)
    x = sub.add_parser("cross")
    x.add_argument("--dir", required=True)
    x.add_argument("--role", choices=["a", "b"], required=True)
    x.add_argument("--n", type=int, required=True)
    x.add_argument("--tag", required=True)
    x.set_defaults(func=cmd_cross)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
