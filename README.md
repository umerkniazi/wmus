# wmus

A lightweight terminal music player for Windows, written in Python and inspired by [cmus](https://cmus.github.io/).

## Features

- Library, Albums, and Queue views
- Fuzzy search with intelligent filtering
- Shuffle and repeat modes
- Vim-style navigation (j/k/h/l)
- Smart metadata caching
- Configurable keybindings
- Volume control and seeking
- Supports MP3, FLAC, WAV, OGG, AAC, M4A, and more

## Installation

### Windows Installer (Recommended)

Download the latest installer from [Releases](https://github.com/umerkniazi/wmus/releases) and run it.

### Run from Source

```bash
pip install -r requirements.txt
python main.py
```

**Requirements:** Python 3.7+, `pygame`, `mutagen`, `windows-curses`

## Building from Source

### Build Executable

```bash
pip install pyinstaller
python build.py
```

This creates `dist/wmus.exe` and prepares files in `installer_files/`.

### Build Installer

1. Install [Inno Setup](https://jrsoftware.org/isdl.php)
2. Run `python build.py`
3. Compile `wmus-installer.iss` with Inno Setup
4. Find installer in `Output/` directory

## Quick Start

1. Launch: `wmus.exe` or `python main.py`
2. Add music: Type `:add` followed by the path to your music folder (e.g., `:add D:/Music`)
3. Navigate: `j`/`k` or arrow keys
4. Play: Press `c` or `Enter`

## Keybindings

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `c` | Play/pause | `n` / `p` | Next/previous |
| `j` / `k` | Down/up | `h` / `l` | Left/right |
| `+` / `-` | Volume | `<-` / `->` | Seek |
| `s` / `r` | Shuffle/repeat | `e` | Add to queue |
| `/` | Search | `1` / `2` / `3` | Switch views |
| `:help` | Show help | `:q` | Quit |

## Commands

- `:add <folder>` (`:a`) - Set music folder
- `:refresh` - Rescan library
- `:clear` (`:c`) - Clear queue
- `:remove <n>` (`:r`) - Remove track from queue
- `:help` (`:h`) - Show help

## Configuration

Edit `config.json` to customize keybindings, default volume, shuffle/repeat modes, and more.

## License

MIT