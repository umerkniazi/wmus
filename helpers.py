import curses
import difflib
import hashlib

def key_match(key, options, buffer=None):
    for opt in options:
        if isinstance(opt, int):
            if key == opt:
                return True
        elif isinstance(opt, str):
            if opt.startswith("KEY_"):
                if hasattr(curses, opt) and key == getattr(curses, opt):
                    return True
            elif len(opt) == 1:
                if key == ord(opt):
                    return True
            elif buffer is not None and buffer == opt:
                return True
    return False

def search(query, names):
    if not query or not query.strip():
        return list(range(len(names)))
    
    q = query.lower()
    exact = []
    starts = []
    word = []
    substring = []
    
    for i, n in enumerate(names):
        nl = n.lower()
        if nl == q:
            exact.append(i)
        elif nl.startswith(q):
            starts.append(i)
        elif any(w.startswith(q) for w in nl.split()):
            word.append(i)
        elif q in nl:
            substring.append(i)
    
    taken = set(exact + starts + word + substring)
    if len(taken) == len(names):
        return exact + starts + word + substring
    
    candidates = [i for i in range(len(names)) if i not in taken]
    cand_names = [names[i] for i in candidates]
    matches = difflib.get_close_matches(q, cand_names, n=len(cand_names), cutoff=0.5)
    
    fuzzy = []
    if matches:
        matches_set = set(matches)
        for i, nm in zip(candidates, cand_names):
            if nm in matches_set:
                fuzzy.append(i)
    
    return exact + starts + word + substring + fuzzy

def get_folder_hash(path):
    return hashlib.md5(path.encode("utf-8")).hexdigest()

_HELP_MAPPING = {
    "up": "Navigate up in list",
    "down": "Navigate down in list",
    "enter": "Play selected track",
    "play_pause": "Toggle play/pause",
    "next": "Skip to next track",
    "prev": "Go to previous track",
    "shuffle": "Toggle shuffle mode",
    "repeat": "Toggle repeat mode",
    "search": "Search library (type to filter)",
    "quit": "Quit application",
    "volume_up": "Increase volume by 5%",
    "volume_down": "Decrease volume by 5%",
    "fadeout": "Fade out current track",
    "queue": "Add selected track to queue",
    "seek_forward": "Seek forward 5 seconds",
    "seek_backward": "Seek backward 5 seconds"
}

_HELP_SECTIONS = {
    "Navigation": ["up", "down", "enter"],
    "Playback": ["play_pause", "next", "prev", "seek_forward", "seek_backward"],
    "Audio": ["volume_up", "volume_down", "fadeout"],
    "Library": ["search", "shuffle", "repeat", "queue"],
    "System": ["quit"]
}

_HELP_COMMANDS = (
    "",
    "=" * 60,
    "COMMANDS:",
    "=" * 60,
    ":add <folder>     Set or change music library folder",
    ":a <folder>       (alias for :add)",
    ":refresh          Rescan library and rebuild cache",
    ":clear            Clear the playback queue",
    ":c                (alias for :clear)",
    ":remove <n>       Remove track #n from queue",
    ":r <n>            (alias for :remove)",
    ":q                Quit wmus",
    ":v, :version      Display version information",
    ":help             Show this help screen",
    ":h                (alias for :help)",
    "",
    "=" * 60,
    "VIEW MODES:",
    "=" * 60,
    "Press 1           Library view (all tracks)",
    "Press 2           Album view (organized by album)",
    "Press 3           Queue view (upcoming tracks)",
    "",
    "=" * 60,
    "ALBUM VIEW:",
    "=" * 60,
    "* Use Left/Right, h/l, or Tab to switch columns",
    "* Press Enter on album to view songs",
    "* Press 'e' on album to queue entire album",
    "* Press 'e' on song to queue individual track",
    "",
    "=" * 60,
    "QUEUE MANAGEMENT:",
    "=" * 60,
    "* Press 'e' to add tracks to queue",
    "* Press 'd' or Delete to remove from queue (in Queue view)",
    "* Use :clear or :c to clear entire queue",
    "* Use :remove N or :r N to remove track #N",
    "",
    "=" * 60,
    "TIPS:",
    "=" * 60,
    "* Search filters as you type (press Esc to cancel)",
    "* Queue tracks play after current song finishes",
    "* Press 'q' for quit prompt, ':q' for immediate quit",
    "* Volume, shuffle, and repeat states are saved on exit",
    ""
)

def help_text(keybindings):
    lines = [
        "=" * 60,
        "           WMUS - TERMINAL MUSIC PLAYER HELP              ",
        "=" * 60,
        ""
    ]
    
    for section, keys in _HELP_SECTIONS.items():
        lines.append("-" * 60)
        lines.append(f" {section.upper()}")
        lines.append("-" * 60)
        
        for k in keys:
            if k not in keybindings:
                continue
            
            key_list = []
            for key in keybindings[k]:
                if isinstance(key, str):
                    if key.startswith("KEY_"):
                        formatted = key[4:].replace("_", "")
                        if formatted.upper() == "ENTER":
                            key_list.append("Enter")
                        elif formatted.upper() == "UP":
                            key_list.append("Up")
                        elif formatted.upper() == "DOWN":
                            key_list.append("Down")
                        elif formatted.upper() == "LEFT":
                            key_list.append("Left")
                        elif formatted.upper() == "RIGHT":
                            key_list.append("Right")
                        else:
                            key_list.append(formatted.title())
                    elif key == " ":
                        key_list.append("Space")
                    elif key.startswith(":"):
                        key_list.append(key)
                    else:
                        key_list.append(key.upper())
                else:
                    key_list.append(str(key))
            
            desc = _HELP_MAPPING.get(k, k.replace("_", " ").title())
            
            key_display = "/".join(key_list[:3])
            lines.append(f"  {key_display:<15} {desc}")
        
        lines.append("")
    
    lines.extend(_HELP_COMMANDS)
    
    return "\n".join(lines)

def format_time(seconds):
    if seconds < 0:
        return "--:--"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def truncate_string(text, max_length, suffix="..."):
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def center_text(text, width):
    if len(text) >= width:
        return text[:width]
    padding = (width - len(text)) // 2
    return " " * padding + text + " " * (width - len(text) - padding)