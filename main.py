import os
import sys
import glob
import time
import random
import json
import locale
from pathlib import Path
from player import MusicPlayer, PlaybackState
from mutagen import File
from config import load_config, save_config
from helpers import key_match, search, get_folder_hash, help_text
from ui import UI

APP_VERSION = "1.0.0"
CACHE_VERSION = "1.0"

CACHE_DIR = Path(os.getenv('LOCALAPPDATA')) / 'wmus' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
else:
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error:
        pass

UNICODE_SUPPORT = (
    sys.platform != "win32" or
    os.getenv("WT_SESSION") or
    os.getenv("TERM_PROGRAM") == "vscode"
)

if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--version"):
    print(APP_VERSION)
    sys.exit(0)

if sys.platform == "win32":
    os.system(f"title wmus v{APP_VERSION}")
else:
    print(f"\33]0;wmus v{APP_VERSION}\a", end="", flush=True)

try:
    import curses
except ImportError:
    if sys.platform.startswith("win"):
        print("Missing 'windows-curses'. Please run: pip install windows-curses")
        sys.exit(1)
    else:
        raise

class SongCache:
    __slots__ = ('name', 'duration', 'timestamp', 'album', 'artist')
    
    def __init__(self, name, duration, timestamp, album, artist=""):
        self.name = name
        self.duration = duration
        self.timestamp = timestamp
        self.album = album
        self.artist = artist

class SearchState:
    __slots__ = ('active', 'query', 'filtered_indices', 'selected')
    
    def __init__(self):
        self.active = False
        self.query = ""
        self.filtered_indices = None
        self.selected = 0
    
    def activate(self):
        self.active = True
        self.query = ""
        self.filtered_indices = None
        self.selected = 0
    
    def deactivate(self):
        self.active = False
        self.query = ""
        self.filtered_indices = None
        self.selected = 0

class CommandState:
    __slots__ = ('active', 'buffer')
    
    def __init__(self):
        self.active = False
        self.buffer = ""
    
    def activate(self):
        self.active = True
        self.buffer = ":"
    
    def deactivate(self):
        self.active = False
        self.buffer = ""

class CLI:
    __slots__ = (
        'player', 'config', 'keybindings', 'music_folder', 'seek_seconds',
        'playlist', 'song_cache', 'current_index', 'current_song_path', 
        'selected_index', 'scroll_offset', 'shuffle', 'repeat', 'volume', 
        'view_mode', 'queue_list', 'albums', 'album_names', 'album_view_selected',
        'queue_index', 'album_songs_scroll', 'album_song_selected', 'album_column',
        'error_message', 'ui'
    )
    
    def __init__(self, stdscr, config):
        self.player = MusicPlayer()
        self.ui = UI(stdscr)
        self.config = config
        self.keybindings = config.get("keybindings", {})
        self.music_folder = os.path.expanduser(config.get("music_folder", ""))
        self.seek_seconds = config.get("seek_seconds", 5)
        
        self.playlist = []
        self.song_cache = {}
        self.current_index = None
        self.current_song_path = None
        self.selected_index = 0
        self.scroll_offset = 0
        
        self.shuffle = config.get("shuffle", False)
        self.repeat = config.get("repeat", False)
        self.volume = config.get("volume", 1.0)
        self.player.set_volume(self.volume)
        
        self.view_mode = config.get("default_view", 1)
        self.queue_list = []
        self.queue_index = 0
        
        self.albums = {}
        self.album_names = []
        self.album_view_selected = 0
        self.album_songs_scroll = 0
        self.album_song_selected = 0
        self.album_column = 0
        
        self.error_message = ""
    
    def _get_song_info(self, filepath):
        if filepath in self.song_cache:
            cached = self.song_cache[filepath]
            return cached.name, cached.timestamp, cached.album, cached.artist
        
        try:
            audio = File(filepath)
            if not audio:
                name = os.path.splitext(os.path.basename(filepath))[0]
                cache = SongCache(name, 0, "--:--", None, "")
                self.song_cache[filepath] = cache
                return name, "--:--", None, ""
            
            duration = int(audio.info.length) if audio.info else 0
            minutes = duration // 60
            seconds = duration % 60
            timestamp = f"{minutes:02}:{seconds:02}"
            
            title = artist = album = ""
            if audio.tags:
                title = str(audio.tags.get('TIT2', audio.tags.get('title', [""]))[0])
                artist = str(audio.tags.get('TPE1', audio.tags.get('artist', [""]))[0])
                album = str(audio.tags.get('TALB', audio.tags.get('album', [""]))[0])
            
            if title and artist:
                name = f"{artist} - {title}"
            elif title:
                name = title
            elif artist:
                name = artist
            else:
                name = os.path.splitext(os.path.basename(filepath))[0]
            
            cache = SongCache(name, duration, timestamp, album, artist)
            self.song_cache[filepath] = cache
            return name, timestamp, album, artist
        except Exception:
            name = os.path.splitext(os.path.basename(filepath))[0]
            cache = SongCache(name, 0, "--:--", None, "")
            self.song_cache[filepath] = cache
            return name, "--:--", None, ""
    
    def load_playlist(self, path):
        path = os.path.expanduser(path)
        
        if not path.strip():
            self.playlist = []
            self.song_cache = {}
            self.albums = {}
            self.album_names = []
            self.error_message = "No music folder set. Use :add <folder> to add one"
            return
        
        cache_file = CACHE_DIR / f"playlist_cache_{get_folder_hash(path)}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                
                if cache.get("version") == CACHE_VERSION:
                    self.playlist = cache.get("playlist", [])
                    
                    for song, data in cache.get("song_cache", {}).items():
                        self.song_cache[song] = SongCache(
                            data["name"], data["duration"], 
                            data["timestamp"], data.get("album"), data.get("artist", "")
                        )
                    
                    self.albums = cache.get("albums", {})
                    self.album_names = sorted(self.albums.keys())
                    self.error_message = ""
                    return
            except (json.JSONDecodeError, IOError):
                pass
        
        if not os.path.exists(path):
            self.playlist = []
            self.song_cache = {}
            self.albums = {}
            self.album_names = []
            self.error_message = "Music folder not found"
            return
        
        extensions = (
            '*.mp3', '*.wav', '*.flac', '*.ogg', '*.aac', '*.m4a', '*.wma',
            '*.opus', '*.ape', '*.wv', '*.tta'
        )
        
        songs = []
        for ext in extensions:
            songs.extend(glob.glob(os.path.join(path, "**", ext), recursive=True))
        
        if not songs:
            self.playlist = []
            self.song_cache = {}
            self.albums = {}
            self.album_names = []
            self.error_message = "No music files found in folder"
            return
        
        self.playlist = sorted(songs)
        self.song_cache = {}
        self.albums = {}
        
        for song in self.playlist:
            name, timestamp, album, artist = self._get_song_info(song)
            if album:
                if album not in self.albums:
                    self.albums[album] = []
                self.albums[album].append(song)
        
        self.album_names = sorted(self.albums.keys())
        self.error_message = ""
        
        cache_data = {
            "version": CACHE_VERSION,
            "playlist": self.playlist,
            "song_cache": {
                song: {
                    "name": cache.name,
                    "duration": cache.duration,
                    "timestamp": cache.timestamp,
                    "album": cache.album,
                    "artist": cache.artist
                } for song, cache in self.song_cache.items()
            },
            "albums": self.albums
        }
        
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f)
        except IOError:
            pass
    
    def refresh_playlist(self):
        cache_file = CACHE_DIR / f"playlist_cache_{get_folder_hash(self.music_folder)}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except OSError:
                pass
        self.load_playlist(self.music_folder)
        self.selected_index = 0
        self.scroll_offset = 0
    
    def play_song(self, song_path):
        try:
            self.player.stop()
            self.player.load_song(song_path)
            self.player.play()
            self.current_song_path = song_path
            
            if song_path in self.playlist:
                self.current_index = self.playlist.index(song_path)
                self.selected_index = self.current_index
            
            self.error_message = ""
        except FileNotFoundError:
            self.error_message = f"File not found: {os.path.basename(song_path)}"
        except Exception as e:
            self.error_message = f"Failed to play: {os.path.basename(song_path)}"
    
    def toggle_play_pause(self):
        if self.player.state == PlaybackState.PLAYING:
            self.player.pause()
        elif self.player.state == PlaybackState.PAUSED:
            self.player.unpause()
        elif self.player.current_song:
            self.player.play()
        else:
            songs = self._get_current_songs()
            if songs and self.selected_index < len(songs):
                self.play_song(songs[self.selected_index])
    
    def next_song(self):
        if not self.playlist:
            return
        
        if self.shuffle:
            song = random.choice(self.playlist)
        else:
            if self.current_song_path and self.current_song_path in self.playlist:
                idx = self.playlist.index(self.current_song_path)
                idx = (idx + 1) % len(self.playlist)
            else:
                idx = 0
            song = self.playlist[idx]
        
        self.selected_index = self.playlist.index(song)
        self.play_song(song)
    
    def prev_song(self):
        if not self.playlist:
            return
        
        if self.shuffle:
            song = random.choice(self.playlist)
        else:
            if self.current_song_path and self.current_song_path in self.playlist:
                idx = self.playlist.index(self.current_song_path)
                idx = (idx - 1) % len(self.playlist)
            else:
                idx = 0
            song = self.playlist[idx]
        
        self.selected_index = self.playlist.index(song)
        self.play_song(song)
    
    def _handle_song_finished(self):
        if not (self.current_song_path and self.player.is_song_finished()):
            return
        
        if self.queue_list and self.queue_index < len(self.queue_list):
            next_song = self.queue_list[self.queue_index]
            self.play_song(next_song)
            self.queue_index += 1
            return
        
        if self.repeat and self.current_song_path:
            self.play_song(self.current_song_path)
            return
        
        if self.playlist:
            if self.shuffle:
                next_song = random.choice(self.playlist)
            else:
                if self.current_song_path in self.playlist:
                    idx = self.playlist.index(self.current_song_path)
                    idx = (idx + 1) % len(self.playlist)
                    next_song = self.playlist[idx]
                else:
                    next_song = self.playlist[0]
            self.play_song(next_song)
    
    def _switch_view(self, view_num):
        if view_num == 1:
            self.view_mode = 1
            self.selected_index = 0
            self.scroll_offset = 0
        elif view_num == 2:
            self.view_mode = 2
            self.album_view_selected = 0
            self.scroll_offset = 0
            self.album_songs_scroll = 0
            self.album_song_selected = 0
            self.album_column = 0
        elif view_num == 3:
            self.view_mode = 3
            self.selected_index = 0
            self.scroll_offset = 0
    
    def _get_display_list(self):
        if self.view_mode == 3:
            return [(self.song_cache[s].name if s in self.song_cache else os.path.basename(s)) 
                    for s in self.queue_list]
        elif self.view_mode == 2:
            if not self.album_names or self.album_view_selected >= len(self.album_names):
                return []
            album = self.album_names[self.album_view_selected]
            return [(self.song_cache[s].name if s in self.song_cache else os.path.basename(s)) 
                    for s in self.albums.get(album, [])]
        return [self.song_cache[s].name if s in self.song_cache else os.path.basename(s) 
                for s in self.playlist]
    
    def _get_current_songs(self):
        if self.view_mode == 3:
            return self.queue_list
        elif self.view_mode == 2:
            if not self.album_names or self.album_view_selected >= len(self.album_names):
                return []
            return self.albums.get(self.album_names[self.album_view_selected], [])
        return self.playlist
    
    def _handle_navigation(self, key):
        if self.view_mode == 2:
            self._handle_album_navigation(key)
        elif self.view_mode == 3:
            self._handle_queue_navigation(key)
        else:
            self._handle_library_navigation(key)
    
    def _handle_library_navigation(self, key):
        kb = self.keybindings
        
        if key_match(key, kb["down"]):
            if self.selected_index < len(self.playlist) - 1:
                self.selected_index += 1
        elif key_match(key, kb["up"]):
            if self.selected_index > 0:
                self.selected_index -= 1
        elif key_match(key, kb["enter"]):
            if self.playlist and self.selected_index < len(self.playlist):
                self.play_song(self.playlist[self.selected_index])
        elif key_match(key, kb.get("queue", [])):
            if self.playlist and self.selected_index < len(self.playlist):
                song = self.playlist[self.selected_index]
                if song not in self.queue_list:
                    self.queue_list.append(song)
                    self.error_message = f"Added to queue: {self.song_cache[song].name if song in self.song_cache else os.path.basename(song)}"
                else:
                    self.error_message = "Song already in queue"
                if self.selected_index < len(self.playlist) - 1:
                    self.selected_index += 1
    
    def _handle_queue_navigation(self, key):
        kb = self.keybindings
        
        if key_match(key, kb["down"]):
            if self.selected_index < len(self.queue_list) - 1:
                self.selected_index += 1
        elif key_match(key, kb["up"]):
            if self.selected_index > 0:
                self.selected_index -= 1
        elif key_match(key, kb["enter"]):
            if self.queue_list and self.selected_index < len(self.queue_list):
                self.play_song(self.queue_list[self.selected_index])
                self.queue_index = self.selected_index + 1
        elif key in (curses.KEY_DC, ord('d')):
            if self.queue_list and self.selected_index < len(self.queue_list):
                removed_song = self.queue_list[self.selected_index]
                del self.queue_list[self.selected_index]
                self.error_message = f"Removed: {self.song_cache[removed_song].name if removed_song in self.song_cache else os.path.basename(removed_song)}"
                if self.selected_index >= len(self.queue_list) and self.queue_list:
                    self.selected_index = len(self.queue_list) - 1
                if self.queue_index > self.selected_index:
                    self.queue_index -= 1
    
    def _handle_album_navigation(self, key):
        kb = self.keybindings
        album_names = self.album_names
        selected_album = album_names[self.album_view_selected] if album_names else None
        album_songs = self.albums.get(selected_album, []) if selected_album else []
        
        if key_match(key, kb["down"]):
            if self.album_column == 0:
                if self.album_view_selected < len(album_names) - 1:
                    self.album_view_selected += 1
                    self.album_songs_scroll = 0
                    self.album_song_selected = 0
            else:
                if album_songs and self.album_song_selected < len(album_songs) - 1:
                    self.album_song_selected += 1
        elif key_match(key, kb["up"]):
            if self.album_column == 0:
                if self.album_view_selected > 0:
                    self.album_view_selected -= 1
                    self.album_songs_scroll = 0
                    self.album_song_selected = 0
            else:
                if self.album_song_selected > 0:
                    self.album_song_selected -= 1
        elif key in (curses.KEY_RIGHT, ord('l'), ord('\t')):
            if self.album_column == 0 and album_songs:
                self.album_column = 1
        elif key in (curses.KEY_LEFT, ord('h')):
            if self.album_column == 1:
                self.album_column = 0
        elif key_match(key, kb["enter"]):
            if self.album_column == 1 and album_songs and self.album_song_selected < len(album_songs):
                self.play_song(album_songs[self.album_song_selected])
            elif self.album_column == 0 and album_songs:
                self.album_column = 1
        elif key_match(key, kb.get("queue", [])):
            if self.album_column == 1 and album_songs and self.album_song_selected < len(album_songs):
                song = album_songs[self.album_song_selected]
                if song not in self.queue_list:
                    self.queue_list.append(song)
                    self.error_message = f"Added to queue: {self.song_cache[song].name if song in self.song_cache else os.path.basename(song)}"
                else:
                    self.error_message = "Song already in queue"
            elif self.album_column == 0 and selected_album:
                added_count = 0
                for song in album_songs:
                    if song not in self.queue_list:
                        self.queue_list.append(song)
                        added_count += 1
                if added_count > 0:
                    self.error_message = f"Added {added_count} songs from '{selected_album}' to queue"
                else:
                    self.error_message = "All songs from album already in queue"
    
    def _handle_command(self, cmd):
        if cmd in (":help", ":h"):
            self.ui.show_help(self.keybindings)
        
        elif cmd.startswith(":add ") or cmd.startswith(":a "):
            folder = cmd.split(" ", 1)[1].strip() if " " in cmd else ""
            folder = os.path.expanduser(folder)
            
            if folder and os.path.exists(folder):
                self.music_folder = folder
                self.config["music_folder"] = folder
                save_config(self.config)
                self.load_playlist(self.music_folder)
                self.selected_index = 0
                self.scroll_offset = 0
                self.error_message = f"Loaded {len(self.playlist)} tracks from folder"
            else:
                self.error_message = "Folder not found"
        
        elif cmd == ":refresh":
            self.refresh_playlist()
            self.error_message = f"Refreshed library: {len(self.playlist)} tracks"
        
        elif cmd == ":q":
            return True
        
        elif cmd in (":v", ":version"):
            self.ui.show_version()
            self.error_message = ""
        
        elif cmd in (":clear", ":c"):
            count = len(self.queue_list)
            self.queue_list = []
            self.queue_index = 0
            self.error_message = f"Cleared {count} songs from queue"
        
        elif cmd.startswith(":remove ") or cmd.startswith(":r "):
            try:
                idx_str = cmd.split(" ", 1)[1].strip() if " " in cmd else ""
                idx = int(idx_str) - 1
                if 0 <= idx < len(self.queue_list):
                    removed = self.queue_list[idx]
                    del self.queue_list[idx]
                    if self.queue_index > idx:
                        self.queue_index -= 1
                    if self.selected_index >= len(self.queue_list) and self.queue_list:
                        self.selected_index = len(self.queue_list) - 1
                    self.error_message = f"Removed: {self.song_cache[removed].name if removed in self.song_cache else os.path.basename(removed)}"
                else:
                    self.error_message = "Invalid queue index"
            except (ValueError, IndexError):
                self.error_message = "Invalid queue index"
        
        elif cmd:
            self.error_message = f"Unknown command: {cmd}"
        
        return False
    
    def _handle_quit_prompt(self, key):
        if key in (ord('y'), ord('Y')):
            self.config["volume"] = self.volume
            self.config["shuffle"] = self.shuffle
            self.config["repeat"] = self.repeat
            save_config(self.config)
            return True
        return False
    
    def _handle_command_input(self, key, command_state):
        if key == 27:
            command_state.deactivate()
        elif key in (10, 13):
            if self._handle_command(command_state.buffer.strip()):
                self.config["volume"] = self.volume
                self.config["shuffle"] = self.shuffle
                self.config["repeat"] = self.repeat
                save_config(self.config)
                return True
            command_state.deactivate()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            command_state.buffer = command_state.buffer[:-1]
        elif 32 <= key <= 126:
            command_state.buffer += chr(key)
        return False
    
    def _handle_search_input(self, key, search_state):
        if self.view_mode == 2:
            search_state.deactivate()
            return
        
        display_list = self._get_display_list()
        search_state.filtered_indices = search(search_state.query, display_list)
        
        kb = self.keybindings
        
        if key_match(key, kb["down"]):
            if search_state.filtered_indices and search_state.selected < len(search_state.filtered_indices) - 1:
                search_state.selected += 1
        elif key_match(key, kb["up"]):
            if search_state.selected > 0:
                search_state.selected -= 1
        elif key in (27,) or key_match(key, kb["quit"]):
            search_state.deactivate()
        elif key_match(key, kb["enter"]):
            if search_state.filtered_indices and search_state.selected < len(search_state.filtered_indices):
                self.selected_index = search_state.filtered_indices[search_state.selected]
            search_state.deactivate()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if search_state.query:
                search_state.query = search_state.query[:-1]
                search_state.selected = 0
            else:
                search_state.deactivate()
        elif 32 <= key <= 126:
            search_state.query += chr(key)
            search_state.selected = 0
        
        if search_state.filtered_indices and search_state.selected >= len(search_state.filtered_indices):
            search_state.selected = max(0, len(search_state.filtered_indices) - 1)
    
    def _handle_regular_input(self, key, search_state, command_state):
        kb = self.keybindings
        
        if key == ord('q'):
            return True
        elif key == ord(':'):
            command_state.activate()
            self.error_message = ""
        elif key_match(key, kb.get("search", [])):
            if self.view_mode != 2:
                search_state.activate()
                self.error_message = ""
        elif key_match(key, kb.get("shuffle", [])):
            self.shuffle = not self.shuffle
            self.error_message = f"Shuffle: {'ON' if self.shuffle else 'OFF'}"
        elif key_match(key, kb.get("repeat", [])):
            self.repeat = not self.repeat
            self.error_message = f"Repeat: {'ON' if self.repeat else 'OFF'}"
        elif key_match(key, kb["next"]):
            self.next_song()
        elif key_match(key, kb["prev"]):
            self.prev_song()
        elif key_match(key, kb["play_pause"]):
            self.toggle_play_pause()
        elif key_match(key, kb.get("volume_up", [])):
            self.volume = min(1.0, self.volume + 0.05)
            self.player.set_volume(self.volume)
            self.error_message = f"Volume: {int(self.volume * 100)}%"
        elif key_match(key, kb.get("volume_down", [])):
            self.volume = max(0.0, self.volume - 0.05)
            self.player.set_volume(self.volume)
            self.error_message = f"Volume: {int(self.volume * 100)}%"
        elif key_match(key, kb.get("fadeout", [])):
            self.player.fadeout()
            self.error_message = "Fading out..."
        elif key_match(key, kb.get("seek_forward", [])) and self.view_mode != 2:
            self.player.seek(self.seek_seconds)
            self.error_message = f"Seeked forward {self.seek_seconds}s"
        elif key_match(key, kb.get("seek_backward", [])) and self.view_mode != 2:
            self.player.seek(-self.seek_seconds)
            self.error_message = f"Seeked backward {self.seek_seconds}s"
        elif key in (ord('1'), ord('2'), ord('3')):
            self._switch_view(int(chr(key)))
            self.error_message = ""
        else:
            self._handle_navigation(key)
        
        return False
    
    def process_input(self):
        self.ui.stdscr.nodelay(True)
        
        search_state = SearchState()
        command_state = CommandState()
        quit_prompt = False
        
        self.ui.render(self, quit_prompt, search_state, command_state)
        
        while True:
            self._handle_song_finished()
            self.ui.render(self, quit_prompt, search_state, command_state)
            
            key = self.ui.stdscr.getch()
            if key == -1:
                time.sleep(0.005)
                continue
            
            if quit_prompt:
                if self._handle_quit_prompt(key):
                    break
                quit_prompt = False
                continue
            
            if command_state.active:
                if self._handle_command_input(key, command_state):
                    break
                continue
            
            if search_state.active:
                self._handle_search_input(key, search_state)
                continue
            
            quit_prompt = self._handle_regular_input(key, search_state, command_state)

def main(stdscr):
    config = load_config()
    curses.curs_set(0)
    stdscr.keypad(True)
    cli = CLI(stdscr, config)
    cli.load_playlist(cli.music_folder)
    cli.process_input()

if __name__ == "__main__":
    curses.wrapper(main)