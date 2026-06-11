import os
import sys
import glob
import time
import random
import json
import locale
import threading
from pathlib import Path
from player import MusicPlayer, PlaybackState
from mutagen import File
from config import load_config, save_config
from paths import CACHE_DIR
from helpers import key_match, search, get_folder_hash, help_text
from version import VERSION as APP_VERSION
from ui import UI

CACHE_VERSION = "1.0"

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
        'playlist', 'song_cache', 'song_index_map', 'current_index', 'current_song_path', 
        'selected_index', 'scroll_offset', 'shuffle', 'repeat', 'volume', 
        'view_mode', 'queue_list', 'albums', 'album_names', 'album_view_selected',
        'queue_index', 'album_songs_scroll', 'album_song_selected', 'album_column',
        'error_message', 'ui', 'last_seek_time', 'last_seek_delta',
        'library_scroll', 'library_selected', 'queue_scroll', 'queue_selected',
        'album_scroll', 'album_song_scroll', 'album_song_selected',
        '_loading', '_loaded_data', '_load_lock', '_display_list_cache', '_display_list_dirty'
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
        self.song_index_map = {}
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
        self.last_seek_time = 0
        self.last_seek_delta = 0
        
        self.library_scroll = 0
        self.library_selected = 0
        self.queue_scroll = 0
        self.queue_selected = 0
        self.album_scroll = 0
        self.album_song_scroll = 0
        self.album_song_selected = 0
        
        self._loading = False
        self._loaded_data = None
        self._load_lock = threading.Lock()
        
        self._display_list_cache = None
        self._display_list_dirty = True
    
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
    
    def _start_load_playlist(self, path):
        path = os.path.expanduser(path)
        with self._load_lock:
            self._loading = True
            self._loaded_data = None
        
        def worker():
            if not path.strip():
                data = ([], {}, {}, [])
            else:
                cache_file = CACHE_DIR / f"playlist_cache_{get_folder_hash(path)}.json"
                if cache_file.exists():
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cache = json.load(f)
                        if cache.get("version") == CACHE_VERSION:
                            playlist = cache.get("playlist", [])
                            sc = {}
                            for song, cdata in cache.get("song_cache", {}).items():
                                sc[song] = SongCache(
                                    cdata["name"], cdata["duration"],
                                    cdata["timestamp"], cdata.get("album"),
                                    cdata.get("artist", "")
                                )
                            albums = cache.get("albums", {})
                            data = (playlist, sc, albums, sorted(albums.keys()))
                            with self._load_lock:
                                self._loaded_data = data
                                self._loading = False
                            return
                    except (json.JSONDecodeError, IOError):
                        pass
                
                if not os.path.exists(path):
                    data = ([], {}, {}, [])
                else:
                    extensions = (
                        '*.mp3', '*.wav', '*.flac', '*.ogg', '*.aac', '*.m4a', '*.wma',
                        '*.opus', '*.ape', '*.wv', '*.tta'
                    )
                    songs = []
                    for ext in extensions:
                        songs.extend(glob.glob(os.path.join(path, "**", ext), recursive=True))
                    if not songs:
                        data = ([], {}, {}, [])
                    else:
                        songs = sorted(songs)
                        sc = {}
                        albums = {}
                        for song in songs:
                            name, timestamp, album, artist = self._get_song_info(song)
                            if album:
                                if album not in albums:
                                    albums[album] = []
                                albums[album].append(song)
                        album_names = sorted(albums.keys())
                        cache_data = {
                            "version": CACHE_VERSION,
                            "playlist": songs,
                            "song_cache": {
                                s: {
                                    "name": self.song_cache[s].name,
                                    "duration": self.song_cache[s].duration,
                                    "timestamp": self.song_cache[s].timestamp,
                                    "album": self.song_cache[s].album,
                                    "artist": self.song_cache[s].artist
                                } for s in songs
                            },
                            "albums": albums
                        }
                        try:
                            with open(cache_file, "w", encoding="utf-8") as f:
                                json.dump(cache_data, f)
                        except IOError:
                            pass
                        data = (songs, sc, albums, album_names)
            with self._load_lock:
                self._loaded_data = data
                self._loading = False
        
        threading.Thread(target=worker, daemon=True).start()
    
    def _apply_loaded_data(self, data):
        playlist, song_cache, albums, album_names = data
        self.playlist = playlist
        self.song_cache = song_cache
        self.albums = albums
        self.album_names = album_names
        self.song_index_map = {path: idx for idx, path in enumerate(playlist)}
        self.selected_index = 0
        self.scroll_offset = 0
        self.library_selected = 0
        self.library_scroll = 0
        self.queue_selected = 0
        self.queue_scroll = 0
        self.album_view_selected = 0
        self.album_scroll = 0
        self.album_song_selected = 0
        self.album_song_scroll = 0
        self.album_column = 0
        self._display_list_dirty = True
        
        if not playlist:
            self.error_message = "No music files found in folder"
        else:
            self.error_message = f"Loaded {len(playlist)} tracks"
    
    def load_playlist(self, path):
        pass
    
    def refresh_playlist(self):
        cache_file = CACHE_DIR / f"playlist_cache_{get_folder_hash(self.music_folder)}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except OSError:
                pass
        self._start_load_playlist(self.music_folder)
    
    def play_song(self, song_path):
        try:
            self.player.stop()
            self.player.load_song(song_path)
            self.player.play()
            self.current_song_path = song_path
            
            self.current_index = self.song_index_map.get(song_path)
            if self.current_index is not None:
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
            idx = self.current_index
            if idx is not None:
                idx = (idx + 1) % len(self.playlist)
            else:
                idx = 0
            song = self.playlist[idx]
        
        self.selected_index = self.song_index_map[song]
        self.play_song(song)
    
    def prev_song(self):
        if not self.playlist:
            return
        
        if self.shuffle:
            song = random.choice(self.playlist)
        else:
            idx = self.current_index
            if idx is not None:
                idx = (idx - 1) % len(self.playlist)
            else:
                idx = len(self.playlist) - 1
            song = self.playlist[idx]
        
        self.selected_index = self.song_index_map[song]
        self.play_song(song)
    
    def _handle_song_finished(self):
        if not (self.current_song_path and self.player.is_song_finished()):
            return
        
        if self.repeat and self.current_song_path:
            self.play_song(self.current_song_path)
            return
        
        if self.queue_list and self.queue_index < len(self.queue_list):
            next_song = self.queue_list[self.queue_index]
            self.play_song(next_song)
            self.queue_index += 1
            return
        
        if self.playlist:
            if self.shuffle:
                next_song = random.choice(self.playlist)
            else:
                idx = self.song_index_map.get(self.current_song_path)
                if idx is not None:
                    idx = (idx + 1) % len(self.playlist)
                    next_song = self.playlist[idx]
                else:
                    next_song = self.playlist[0]
            self.play_song(next_song)
    
    def _switch_view(self, view_num):
        if self.view_mode == 1:
            self.library_scroll = self.scroll_offset
            self.library_selected = self.selected_index
        elif self.view_mode == 2:
            self.album_scroll = self.scroll_offset
            self.album_song_scroll = self.album_songs_scroll
            self.album_song_selected = self.album_song_selected
        elif self.view_mode == 3:
            self.queue_scroll = self.scroll_offset
            self.queue_selected = self.selected_index
        
        if view_num == 1:
            self.view_mode = 1
            self.scroll_offset = self.library_scroll
            self.selected_index = self.library_selected
        elif view_num == 2:
            self.view_mode = 2
            self.scroll_offset = self.album_scroll
            self.album_songs_scroll = self.album_song_scroll
            self.album_song_selected = self.album_song_selected
            self.album_column = 0
        elif view_num == 3:
            self.view_mode = 3
            self.scroll_offset = self.queue_scroll
            self.selected_index = self.queue_selected
        
        self._display_list_dirty = True
    
    def _get_display_list(self):
        if not self._display_list_dirty and self._display_list_cache is not None:
            return self._display_list_cache
        
        if self.view_mode == 3:
            result = [(self.song_cache[s].name if s in self.song_cache else os.path.basename(s)) 
                      for s in self.queue_list]
        elif self.view_mode == 2:
            if not self.album_names or self.album_view_selected >= len(self.album_names):
                result = []
            else:
                album = self.album_names[self.album_view_selected]
                result = [(self.song_cache[s].name if s in self.song_cache else os.path.basename(s)) 
                          for s in self.albums.get(album, [])]
        else:
            result = [self.song_cache[s].name if s in self.song_cache else os.path.basename(s) 
                      for s in self.playlist]
        
        self._display_list_cache = result
        self._display_list_dirty = False
        return result
    
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
                self._display_list_dirty = True
        elif key_match(key, kb["up"]):
            if self.selected_index > 0:
                self.selected_index -= 1
                self._display_list_dirty = True
        elif key_match(key, kb["enter"]):
            if self.playlist and self.selected_index < len(self.playlist):
                self.play_song(self.playlist[self.selected_index])
        elif key_match(key, kb.get("queue", [])):
            if self.playlist and self.selected_index < len(self.playlist):
                song = self.playlist[self.selected_index]
                if song not in self.queue_list:
                    self.queue_list.append(song)
                    self._display_list_dirty = True
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
                self._display_list_dirty = True
        elif key_match(key, kb["up"]):
            if self.selected_index > 0:
                self.selected_index -= 1
                self._display_list_dirty = True
        elif key_match(key, kb["enter"]):
            if self.queue_list and self.selected_index < len(self.queue_list):
                self.play_song(self.queue_list[self.selected_index])
                self.queue_index = self.selected_index + 1
        elif key_match(key, kb.get("remove", [])):
            if self.queue_list and self.selected_index < len(self.queue_list):
                removed_song = self.queue_list[self.selected_index]
                del self.queue_list[self.selected_index]
                self._display_list_dirty = True
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
                    self._display_list_dirty = True
            else:
                if album_songs and self.album_song_selected < len(album_songs) - 1:
                    self.album_song_selected += 1
                    self._display_list_dirty = True
        elif key_match(key, kb["up"]):
            if self.album_column == 0:
                if self.album_view_selected > 0:
                    self.album_view_selected -= 1
                    self.album_songs_scroll = 0
                    self.album_song_selected = 0
                    self._display_list_dirty = True
            else:
                if self.album_song_selected > 0:
                    self.album_song_selected -= 1
                    self._display_list_dirty = True
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
                    self._display_list_dirty = True
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
                    self._display_list_dirty = True
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
                self._start_load_playlist(self.music_folder)
                self.error_message = "Loading..."
            else:
                self.error_message = "Folder not found"
        
        elif cmd == ":refresh":
            self.refresh_playlist()
            self.error_message = "Loading..."
        
        elif cmd == ":q":
            return True
        
        elif cmd in (":v", ":version"):
            self.ui.show_version()
            self.error_message = ""
        
        elif cmd in (":clear", ":c"):
            count = len(self.queue_list)
            self.queue_list = []
            self.queue_index = 0
            self._display_list_dirty = True
            self.error_message = f"Cleared {count} songs from queue"
        
        elif cmd.startswith(":remove ") or cmd.startswith(":r "):
            try:
                idx_str = cmd.split(" ", 1)[1].strip() if " " in cmd else ""
                idx = int(idx_str) - 1
                if 0 <= idx < len(self.queue_list):
                    removed = self.queue_list[idx]
                    del self.queue_list[idx]
                    self._display_list_dirty = True
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
        
        if key == curses.KEY_DOWN:
            if search_state.filtered_indices and search_state.selected < len(search_state.filtered_indices) - 1:
                search_state.selected += 1
        elif key == curses.KEY_UP:
            if search_state.selected > 0:
                search_state.selected -= 1
        elif key in (27,):
            search_state.deactivate()
        elif key in (10, 13):
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
    
    def _seek_with_throttle(self, delta):
        now = time.time()
        if self.last_seek_delta == delta and (now - self.last_seek_time) < 0.15:
            return
        self.last_seek_time = now
        self.last_seek_delta = delta
        self.player.seek(delta)
        direction = "forward" if delta > 0 else "backward"
        self.error_message = f"Seeked {direction} {abs(delta)}s"
    
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
            self._seek_with_throttle(self.seek_seconds)
        elif key_match(key, kb.get("seek_backward", [])) and self.view_mode != 2:
            self._seek_with_throttle(-self.seek_seconds)
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
            with self._load_lock:
                if not self._loading and self._loaded_data is not None:
                    data = self._loaded_data
                    self._loaded_data = None
                    self._apply_loaded_data(data)
            
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
    cli._start_load_playlist(cli.music_folder)
    cli.process_input()


if __name__ == "__main__":
    curses.wrapper(main)