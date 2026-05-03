import json
import copy
from pathlib import Path
from paths import CONFIG_DIR


DEFAULT_CONFIG = {
    "keybindings": {
        "quit": [":q"],
        "search": ["/"],
        "next": ["n"],
        "prev": ["p"],
        "play_pause": ["c"],
        "down": ["KEY_DOWN", "j"],
        "up": ["KEY_UP", "k"],
        "enter": ["KEY_ENTER", 10, 13],
        "shuffle": ["s"],
        "repeat": ["r"],
        "volume_up": ["+", "="],
        "volume_down": ["-"],
        "fadeout": ["f"],
        "queue": ["e"],
        "seek_forward": ["KEY_RIGHT"],
        "seek_backward": ["KEY_LEFT"]
    },
    "music_folder": "",
    "seek_seconds": 5,
    "shuffle": False,
    "repeat": False,
    "volume": 1.0,
    "default_view": 1
}


def load_config(path=None):
    if path is None:
        path = CONFIG_DIR / "config.json"
    else:
        path = Path(path).expanduser()

    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        return copy.deepcopy(DEFAULT_CONFIG)

    # Merge missing top-level keys
    for k in DEFAULT_CONFIG:
        if k not in config:
            config[k] = copy.deepcopy(DEFAULT_CONFIG[k])

    # Merge keybindings safely
    if "keybindings" not in config:
        config["keybindings"] = copy.deepcopy(DEFAULT_CONFIG["keybindings"])
    else:
        for k in DEFAULT_CONFIG["keybindings"]:
            if k not in config["keybindings"]:
                config["keybindings"][k] = copy.deepcopy(DEFAULT_CONFIG["keybindings"][k])

    # Normalize music folder path
    if config.get("music_folder"):
        config["music_folder"] = str(Path(config["music_folder"]).expanduser())

    return config


def save_config(config, path=None):
    if path is None:
        path = CONFIG_DIR / "config.json"
    else:
        path = Path(path).expanduser()

    config_to_save = copy.deepcopy(config)

    # Store music path relative to home if possible
    if config_to_save.get("music_folder"):
        music_path = Path(config_to_save["music_folder"])
        home = Path.home()
        try:
            rel_path = music_path.relative_to(home)
            config_to_save["music_folder"] = str(Path("~") / rel_path).replace("\\", "/")
        except ValueError:
            config_to_save["music_folder"] = str(music_path).replace("\\", "/")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config_to_save, f, indent=2)