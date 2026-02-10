#!/usr/bin/env python3
"""
wrap: Turn any subcommand-style CLI (e.g., git) into an interactive REPL.

Example:
    $ ./wrap.py git
    git> status
    git> commit -am "Message"
    git> !pwd               # run a shell escape
    git> :help              # built-in help
    git> :exit

Features
- Runs <base> <args> for each entered line
- Command history & persistent ~/.wrap_history
- Tab completion for subcommands (git-aware) & options (best-effort)
- Shell escapes with prefix '!'
- Variables: set with ':set key=value' and reference as ${key} in commands
- Multi-line input with trailing '\'
- Works on Linux/macOS; Windows with pyreadline3 may be needed for history
"""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

HISTFILE = Path.home() / ".wrap_history"
PROMPT_COLOR = "\033[1;36m"  # cyan bold
RESET = "\033[0m"

try:
    import readline  # type: ignore
    HAVE_READLINE = True
except Exception:
    HAVE_READLINE = False


def _print_err(*args):
    print(*args, file=sys.stderr)


def detect_git_subcommands(base_cmd: str):
    """Return a set of git subcommands if base_cmd == 'git', else empty set.
    Uses `git help -a` and parses lines like '  add, ...' or '  worktree'.
    """
    if os.path.basename(base_cmd) != "git":
        return set()
    try:
        out = subprocess.check_output([base_cmd, "help", "-a"], stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return set()
    cmds = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Sections contain commands separated by spaces, occasionally commas
        if re.match(r"^[a-z0-9][a-z0-9-]*([ ,][a-z0-9-]+)*$", line):
            for tok in re.split(r"[ ,]+", line):
                if tok:
                    cmds.add(tok)
    # Fallback: parse lines with leading two spaces then word
    for line in out.splitlines():
        m = re.match(r"\s{2,}([a-z0-9-]+)\b", line)
        if m:
            cmds.add(m.group(1))
    return cmds


def build_completer(base_cmd: str, subcommands):
    if not HAVE_READLINE:
        return

    def completer(text, state):
        """Tab completion: prioritize subcommands for the first token; otherwise file paths."""
        buffer = readline.get_line_buffer()
        begin = readline.get_begidx()
        # First token?
        tokens = shlex.split(buffer[:begin]) if buffer[:begin] else []
        # After a shell escape, defer to system (no completion)
        if buffer.strip().startswith("!"):
            return None
        candidates = []
        if len(tokens) == 0:
            # completing first token
            if subcommands:
                candidates = [c for c in sorted(subcommands) if c.startswith(text)]
        else:
            # best-effort: offer files/dirs
            try:
                dirname, partial = os.path.split(text)
                dirname = dirname or "."
                for name in os.listdir(dirname):
                    if name.startswith(partial):
                        path = os.path.join(dirname, name)
                        if os.path.isdir(path):
                            candidates.append(os.path.join(dirname, name) + "/")
                        else:
                            candidates.append(os.path.join(dirname, name))
            except Exception:
                pass
        return candidates[state] if state < len(candidates) else None

    readline.set_completer_delims(" \t\n\r")
    readline.set_completer(completer)
    # macOS uses libedit which needs different binding syntax
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
    try:
        readline.read_history_file(str(HISTFILE))
    except Exception:
        pass
    readline.set_history_length(1000)


def save_history():
    if HAVE_READLINE:
        try:
            readline.write_history_file(str(HISTFILE))
        except Exception:
            pass


def expand_vars(s: str, vars_map: dict):
    def repl(m):
        key = m.group(1)
        return vars_map.get(key, m.group(0))
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, s)


def handle_command(raw: str, base_cmd: str, base_args: list[str], vars_map: dict[str, str]) -> Optional[str]:
    """
    Handle a single command line. Returns:
    - "continue" to continue the loop
    - "break" to exit the loop
    - None to continue normally after processing
    """
    # Built-ins start with ':'
    if raw.startswith(":"):
        cmd = raw[1:].strip()
        if cmd in ("q", "quit", "exit"):
            return "break"
        if cmd == "help":
            print(":help                - this help")
            print(":set k=v            - set vars, used as ${k}")
            print(":vars               - list current variables")
            print(":pwd                - print working directory")
            print(":cd <path>          - change directory")
            print(":history            - show history (readline)")
            print(":exit | :quit | :q  - exit")
            return "continue"
        if cmd.startswith("set "):
            rest = cmd[4:].strip()
            if "=" in rest:
                k, v = rest.split("=", 1)
                vars_map[k.strip()] = v.strip()
            else:
                _print_err("Usage: :set key=value")
            return "continue"
        if cmd == "vars":
            for k, v in vars_map.items():
                print(f"{k}={v}")
            return "continue"
        if cmd == "pwd":
            print(os.getcwd())
            return "continue"
        if cmd.startswith("cd "):
            newdir = cmd[3:].strip()
            try:
                os.chdir(newdir)
            except Exception as e:
                _print_err(f"cd: {e}")
            return "continue"
        if cmd == "history" and HAVE_READLINE:
            for i in range(1, readline.get_current_history_length() + 1):
                print(readline.get_history_item(i))
            return "continue"
        _print_err("Unknown built-in. Use :help")
        return "continue"

    # Shell escape
    if raw.startswith("!"):
        shell_cmd = raw[1:].strip()
        if not shell_cmd:
            return "continue"
        rc = subprocess.call(shell_cmd, shell=True)
        if rc != 0:
            _print_err(f"[shell] exited with code {rc}")
        return "continue"

    # Variable expansion
    expanded = expand_vars(raw, vars_map)

    # Tokenize respecting quotes
    try:
        args = shlex.split(expanded)
    except ValueError as e:
        _print_err(f"parse error: {e}")
        return "continue"

    full = [base_cmd] + base_args + args
    try:
        proc = subprocess.Popen(full)
        rc = proc.wait()
        if rc != 0:
            _print_err(f"[{os.path.basename(base_cmd)}] exited with code {rc}")
    except FileNotFoundError:
        _print_err(f"Command not found: {base_cmd}")
        return "break"
    except Exception as e:
        _print_err(str(e))

    return None


def run_repl(base_cmd: str, base_args: list[str]):
    subcommands = detect_git_subcommands(base_cmd)
    build_completer(base_cmd, subcommands)

    vars_map: dict[str, str] = {}

    prompt = f"{PROMPT_COLOR}{os.path.basename(base_cmd)}>{RESET} "
    cont_prompt = "..> "

    try:
        while True:
            try:
                line_parts = []
                while True:
                    line = input(prompt if not line_parts else cont_prompt)
                    if line.endswith("\\"):
                        line_parts.append(line[:-1])
                        continue
                    else:
                        line_parts.append(line)
                        break
                raw = "".join(line_parts).strip()
            except EOFError:
                print()
                break

            if not raw:
                continue

            result = handle_command(raw, base_cmd, base_args, vars_map)
            if result == "break":
                break
            elif result == "continue":
                continue
    finally:
        save_history()


def main():
    if len(sys.argv) < 2:
        _print_err("Usage: wrap.py <base-command> [base-args...]")
        _print_err("Example: wrap.py git")
        sys.exit(2)
    base_cmd = sys.argv[1]
    base_args = sys.argv[2:]
    run_repl(base_cmd, base_args)


if __name__ == "__main__":
    main()

