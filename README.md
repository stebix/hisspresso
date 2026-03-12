<p align="center">
  <img src="assets/hispresso-v0.1.png" alt="hisspresso banner" />
</p>

# hisspresso

[![Lint](https://github.com/stebix/hisspresso/actions/workflows/lint.yml/badge.svg)](https://github.com/stebix/hisspresso/actions/workflows/lint.yml)
[![Type Check](https://github.com/stebix/hisspresso/actions/workflows/typecheck.yml/badge.svg)](https://github.com/stebix/hisspresso/actions/workflows/typecheck.yml)
[![Tests](https://github.com/stebix/hisspresso/actions/workflows/test.yml/badge.svg)](https://github.com/stebix/hisspresso/actions/workflows/test.yml)

Your friendly Python-based caffeine intake tracker for the terminal. Log beverages, model pharmacokinetic decay, and visualize residual caffeine over time — all from the command line.

## Installation

Requires **Python 3.13+** and [**uv**](https://docs.astral.sh/uv/).

```bash
# Clone the repository
git clone https://github.com/stebix/hisspresso.git
cd hisspresso

# Install dependencies
uv sync

# Run hisspresso
uv run hisspresso
```

## Usage

### Log a beverage

```bash
hisspresso log espresso              # log an espresso (uses built-in caffeine value)
hisspresso log coffee --count 2      # log 2 cups of coffee
hisspresso log "energy drink" --caffeine 160   # specify caffeine manually
hisspresso log espresso --at "14:30"           # log at a specific time today
hisspresso log espresso --at "2026-03-10 08:00"  # log at a specific date and time
```

### Show caffeine graph

```bash
hisspresso show                      # auto-ranged residual caffeine graph
hisspresso show --hours 12           # last 12 hours
hisspresso show --from "08:00" --to "22:00"  # explicit time window
hisspresso show --theme light        # use a different graph theme
```

### Check when caffeine clears

```bash
hisspresso clear                     # when you'll drop below 10 mg (default)
hisspresso clear --threshold 20      # when you'll drop below 20 mg
```

### List logged doses

```bash
hisspresso list                      # show recent entries
hisspresso list -n 50                # show last 50 entries
hisspresso list --deleted            # include soft-deleted entries
```

### Undo and manage doses

```bash
hisspresso undo                      # undo the most recent dose
hisspresso delete <id-prefix>        # soft-delete a specific dose
hisspresso restore <id-prefix>       # restore a deleted dose
```

### Manage beverages

```bash
hisspresso beverages                 # list all known beverages
hisspresso beverages add matcha --caffeine 70 --aliases "green-tea"
hisspresso beverages remove matcha
```

### Configuration

```bash
hisspresso config                    # show current config
hisspresso config set --half-life 6  # set caffeine half-life (hours)
hisspresso config set --theme dark   # set default graph theme
```

### Sync across machines

```bash
hisspresso config set --sync-dir /path/to/shared/folder
hisspresso sync push                 # export local changes
hisspresso sync pull                 # import remote changes
hisspresso sync status               # show sync info
```

---

Jannik Stebani, 2026. Licensed under MIT. See [LICENSE](LICENSE).
