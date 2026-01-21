import os
import json
from pathlib import Path

CONFIG_DIR = Path(os.getenv('LOCALAPPDATA')) / 'wmus' / 'config'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

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
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()
    
    for k in DEFAULT_CONFIG:
        if k not in config:
            config[k] = DEFAULT_CONFIG[k]
    
    if "keybindings" not in config:
        config["keybindings"] = DEFAULT_CONFIG["keybindings"].copy()
    else:
        for k in DEFAULT_CONFIG["keybindings"]:
            if k not in config["keybindings"]:
                config["keybindings"][k] = DEFAULT_CONFIG["keybindings"][k]
    
    if "music_folder" in config and config["music_folder"]:
        config["music_folder"] = str(Path(config["music_folder"]).expanduser())
    
    return config

def save_config(config, path=None):
    if path is None:
        path = CONFIG_DIR / "config.json"
    else:
        path = Path(path).expanduser()
    
    config_to_save = config.copy()
    
    if "music_folder" in config_to_save and config_to_save["music_folder"]:
        music_path = Path(config_to_save["music_folder"])
        home = Path.home()
        try:
            rel_path = music_path.relative_to(home)
            config_to_save["music_folder"] = str(Path("~") / rel_path).replace("\\", "/")
        except ValueError:
            config_to_save["music_folder"] = str(music_path).replace("\\", "/")
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config_to_save, f, indent=2)