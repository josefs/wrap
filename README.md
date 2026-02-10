# wrap

Turn any subcommand-style CLI (e.g., git, docker) into an interactive REPL.

## Usage

```bash
./wrap.py <base-command> [base-args...]
```

### Example

```bash
$ ./wrap.py git
git> status
git> commit -am "Message"
git> log --oneline -5
git> :exit
```

## Features

- **Interactive REPL** - Runs `<base> <args>` for each entered line
- **Command history** - Persistent history saved to `~/.wrap_history`
- **Tab completion** - Subcommand completion (git-aware) and file path completion
- **Shell escapes** - Run shell commands with `!` prefix (e.g., `!pwd`)
- **Variables** - Set with `:set key=value`, use as `${key}` in commands
- **Multi-line input** - Continue lines with trailing `\`
- **Plugin system** - Extensible support for command-specific features

## Built-in Commands

| Command | Description |
|---------|-------------|
| `:help` | Show help |
| `:set k=v` | Set variable, use as `${k}` |
| `:vars` | List current variables |
| `:pwd` | Print working directory |
| `:cd <path>` | Change directory |
| `:history` | Show command history |
| `:exit` / `:quit` / `:q` | Exit the REPL |

## Adding Plugin Support for New Commands

To add support for a new command, subclass `CommandPlugin` in `wrap.py`:

```python
class DockerPlugin(CommandPlugin):
    command_name = "docker"
    
    def get_subcommands(self, base_cmd: str) -> set:
        return {"run", "build", "ps", "images", "pull", "push", ...}

# Add to PLUGINS list
PLUGINS: list[CommandPlugin] = [
    GitPlugin(),
    DockerPlugin(),
]
```

## Requirements

- Python 3.9+
- Works on Linux/macOS; Windows may require `pyreadline3` for history support

## License

MIT
