import os
import time
import curses
from player import PlaybackState
from helpers import help_text

UNICODE_SUPPORT = (
    os.name != "nt" or
    os.getenv("WT_SESSION") or
    os.getenv("TERM_PROGRAM") == "vscode"
)

SYMBOLS = {
    "play": "▶" if UNICODE_SUPPORT else ">",
    "pause": "❚❚" if UNICODE_SUPPORT else "||",
    "stop": "■" if UNICODE_SUPPORT else "[]",
    "music": "♪" if UNICODE_SUPPORT else "*",
    "progress_full": "█" if UNICODE_SUPPORT else "=",
    "progress_empty": "░" if UNICODE_SUPPORT else "-",
    "progress_partial": ["▏", "▎", "▍", "▌", "▋", "▊", "▉"] if UNICODE_SUPPORT else None,
    "separator": "│" if UNICODE_SUPPORT else "|",
    "pointer": "►" if UNICODE_SUPPORT else ">",
}

class UI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.max_y, self.max_x = stdscr.getmaxyx()
        self.last_render = 0
        self.colors_initialized = False
        self.message_display_time = 0.0
        self.message_duration = 3.0
        self._init_colors()
    
    def _init_colors(self):
        if not self.colors_initialized:
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_BLACK)
            curses.init_pair(8, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(9, curses.COLOR_CYAN, curses.COLOR_BLACK)
            self.colors_initialized = True
    
    def _truncate_text(self, text, width):
        if len(text) > width - 1:
            return text[:width - 2] + "…"
        return text
    
    def render(self, cli, quit_prompt, search_state, command_state):
        now = time.time()
        if now - self.last_render > 0.016:
            self.max_y, self.max_x = self.stdscr.getmaxyx()
            
            if cli.error_message and self.message_display_time > 0:
                if now - self.message_display_time > self.message_duration:
                    cli.error_message = ""
                    self.message_display_time = 0.0
            
            if quit_prompt:
                command_input = "Quit wmus? (y/n)"
                search_mode = False
            elif command_state.active:
                command_input = command_state.buffer
                search_mode = False
            elif search_state.active:
                command_input = f"/{search_state.query}"
                search_mode = True
            else:
                command_input = ""
                search_mode = False
            
            self._render_top_bar(cli)
            self._render_content(cli, search_state, search_mode)
            self._render_status_bar(cli, command_input, search_mode, search_state)
            
            try:
                self.stdscr.refresh()
            except curses.error:
                pass
            
            self.last_render = now
    
    def _render_top_bar(self, cli):
        now_playing = ""
        status_icon = SYMBOLS["stop"]
        
        if cli.current_song_path and cli.current_song_path in cli.song_cache:
            cache = cli.song_cache[cli.current_song_path]
            pos_seconds = cli.player.get_pos()
            pos_min, pos_sec = divmod(pos_seconds, 60)
            
            if cli.player.state == PlaybackState.PLAYING:
                status_icon = SYMBOLS["play"]
            elif cli.player.state == PlaybackState.PAUSED:
                status_icon = SYMBOLS["pause"]
            
            progress = ""
            if cache.duration > 0:
                progress_width = 20
                progress_ratio = pos_seconds / cache.duration
                
                if UNICODE_SUPPORT and SYMBOLS["progress_partial"]:
                    filled = progress_ratio * progress_width
                    full_blocks = int(filled)
                    partial = filled - full_blocks
                    
                    partial_char = ""
                    if partial > 0 and full_blocks < progress_width:
                        partial_index = int(partial * len(SYMBOLS["progress_partial"]))
                        partial_char = SYMBOLS["progress_partial"][min(partial_index, len(SYMBOLS["progress_partial"]) - 1)]
                    
                    empty_blocks = progress_width - full_blocks - (1 if partial_char else 0)
                    progress = f"[{SYMBOLS['progress_full'] * full_blocks}{partial_char}{SYMBOLS['progress_empty'] * empty_blocks}]"
                else:
                    progress_percent = int(progress_ratio * progress_width)
                    progress = f"[{SYMBOLS['progress_full'] * progress_percent}{SYMBOLS['progress_empty'] * (progress_width - progress_percent)}]"
                
                progress_pct = int(progress_ratio * 100)
                progress = f"{progress} {progress_pct}%"
            
            vol = int(cli.player.get_volume() * 100)
            display_name = self._truncate_text(cache.name, self.max_x // 3)
            now_playing = f"{status_icon} {display_name} {progress} {pos_min:02}:{pos_sec:02}/{cache.timestamp} Vol:{vol}%"
        else:
            now_playing = f"{status_icon} No track playing"
        
        self.stdscr.attron(curses.color_pair(1))
        try:
            self.stdscr.addstr(0, 0, (" " + now_playing)[:self.max_x].ljust(self.max_x))
        except curses.error:
            pass
        self.stdscr.attroff(curses.color_pair(1))
    
    def _render_content(self, cli, search_state, search_mode):
        max_songs = max(0, self.max_y - 4)
        
        if cli.view_mode == 2:
            self._render_album_view(cli, max_songs)
        else:
            self._render_list_view(cli, max_songs, search_state, search_mode)
    
    def _render_list_view(self, cli, max_songs, search_state, search_mode):
        display_list = cli._get_display_list()
        current_songs = cli._get_current_songs()
        
        if search_mode and search_state.filtered_indices:
            filtered = [display_list[i] for i in search_state.filtered_indices if i < len(display_list)]
            selected = search_state.selected
            
            if selected < cli.scroll_offset:
                cli.scroll_offset = selected
            elif selected >= cli.scroll_offset + max_songs:
                cli.scroll_offset = selected - max_songs + 1
            
            visible = filtered[cli.scroll_offset:cli.scroll_offset + max_songs]
            
            for i in range(max_songs):
                try:
                    self.stdscr.move(1 + i, 0)
                    self.stdscr.clrtoeol()
                except curses.error:
                    pass
            
            for i, name in enumerate(visible):
                idx = cli.scroll_offset + i
                try:
                    if idx == selected:
                        self.stdscr.attron(curses.color_pair(2))
                        display_name = self._truncate_text(name, self.max_x - 3)
                        self.stdscr.addstr(1 + i, 0, (f" {SYMBOLS['pointer']} {display_name}").ljust(self.max_x))
                        self.stdscr.attroff(curses.color_pair(2))
                    else:
                        self.stdscr.attron(curses.color_pair(5))
                        display_name = self._truncate_text(name, self.max_x - 4)
                        self.stdscr.addstr(1 + i, 0, (f"   {display_name}").ljust(self.max_x))
                        self.stdscr.attroff(curses.color_pair(5))
                except curses.error:
                    pass
        else:
            selected = cli.selected_index
            
            if selected < cli.scroll_offset:
                cli.scroll_offset = selected
            elif selected >= cli.scroll_offset + max_songs:
                cli.scroll_offset = selected - max_songs + 1
            
            visible = display_list[cli.scroll_offset:cli.scroll_offset + max_songs]
            
            for i in range(max_songs):
                try:
                    self.stdscr.move(1 + i, 0)
                    self.stdscr.clrtoeol()
                except curses.error:
                    pass
            
            for i, name in enumerate(visible):
                idx = cli.scroll_offset + i
                
                if idx < len(current_songs):
                    song = current_songs[idx]
                    timestamp = cli.song_cache[song].timestamp if song in cli.song_cache else "--:--"
                    
                    is_playing = (idx < len(current_songs) and current_songs[idx] == cli.current_song_path)
                    play_icon = SYMBOLS["music"] if is_playing else " "
                    
                    if cli.view_mode == 3:
                        num_width = len(str(len(current_songs)))
                        display_name = self._truncate_text(name, self.max_x - len(timestamp) - num_width - 8)
                        display_text = f" {play_icon} {idx + 1:>{num_width}}. {display_name}"
                    else:
                        display_name = self._truncate_text(name, self.max_x - len(timestamp) - 5)
                        display_text = f" {play_icon} {display_name}"
                    
                    padding = self.max_x - len(display_text) - len(timestamp) - 2
                    if padding > 0:
                        display_text = f"{display_text}{' ' * padding}{timestamp} "
                    else:
                        display_text = f"{display_text[:self.max_x - len(timestamp) - 2]} {timestamp} "
                else:
                    display_name = self._truncate_text(name, self.max_x - 4)
                    display_text = f"   {display_name}"
                
                try:
                    if idx == selected:
                        self.stdscr.attron(curses.color_pair(2))
                        self.stdscr.addstr(1 + i, 0, (f" {SYMBOLS['pointer']}" + display_text[2:]).ljust(self.max_x))
                        self.stdscr.attroff(curses.color_pair(2))
                    elif idx < len(current_songs) and current_songs[idx] == cli.current_song_path:
                        self.stdscr.attron(curses.color_pair(3))
                        self.stdscr.addstr(1 + i, 0, display_text[:self.max_x].ljust(self.max_x))
                        self.stdscr.attroff(curses.color_pair(3))
                    else:
                        self.stdscr.attron(curses.color_pair(5))
                        self.stdscr.addstr(1 + i, 0, display_text[:self.max_x].ljust(self.max_x))
                        self.stdscr.attroff(curses.color_pair(5))
                except curses.error:
                    pass
    
    def _render_album_view(self, cli, max_songs):
        left_width = max(15, self.max_x // 2 - 1)
        separator_x = left_width + 1
        right_width = self.max_x - separator_x - 1
        
        album_names = cli.album_names
        selected_album = album_names[cli.album_view_selected] if album_names else None
        album_songs = cli.albums.get(selected_album, []) if selected_album else []
        
        if cli.album_column == 0:
            if cli.album_view_selected < cli.scroll_offset:
                cli.scroll_offset = cli.album_view_selected
            elif cli.album_view_selected >= cli.scroll_offset + max_songs:
                cli.scroll_offset = cli.album_view_selected - max_songs + 1
        else:
            if cli.album_song_selected < cli.album_songs_scroll:
                cli.album_songs_scroll = cli.album_song_selected
            elif cli.album_song_selected >= cli.album_songs_scroll + max_songs:
                cli.album_songs_scroll = cli.album_song_selected - max_songs + 1
        
        for i in range(max_songs):
            try:
                self.stdscr.move(1 + i, 0)
                self.stdscr.clrtoeol()
            except curses.error:
                pass
            
            idx = cli.scroll_offset + i
            if idx < len(album_names):
                album = album_names[idx]
                track_count = len(cli.albums[album])
                album_text = f"{album} ({track_count})"
                album_display = self._truncate_text(album_text, left_width - 2)
                
                try:
                    if idx == cli.album_view_selected and cli.album_column == 0:
                        self.stdscr.attron(curses.color_pair(2))
                        self.stdscr.addstr(1 + i, 0, (f" {SYMBOLS['pointer']} {album_display}").ljust(left_width))
                        self.stdscr.attroff(curses.color_pair(2))
                    else:
                        self.stdscr.attron(curses.color_pair(5))
                        self.stdscr.addstr(1 + i, 0, (f"   {album_display}").ljust(left_width))
                        self.stdscr.attroff(curses.color_pair(5))
                except curses.error:
                    pass
            else:
                try:
                    self.stdscr.attron(curses.color_pair(5))
                    self.stdscr.addstr(1 + i, 0, " " * left_width)
                    self.stdscr.attroff(curses.color_pair(5))
                except curses.error:
                    pass
            
            try:
                self.stdscr.attron(curses.color_pair(9))
                self.stdscr.addstr(1 + i, separator_x, SYMBOLS["separator"])
                self.stdscr.attroff(curses.color_pair(9))
            except curses.error:
                pass
        
        for i in range(max_songs):
            song_idx = cli.album_songs_scroll + i
            if song_idx < len(album_songs):
                song = album_songs[song_idx]
                name = cli.song_cache[song].name if song in cli.song_cache else os.path.basename(song)
                timestamp = cli.song_cache[song].timestamp if song in cli.song_cache else "--:--"
                
                is_playing = song == cli.current_song_path
                play_icon = SYMBOLS["music"] if is_playing else " "
                
                song_display = self._truncate_text(name, right_width - len(timestamp) - 5)
                song_text = f" {play_icon} {song_display}"
                padding = right_width - len(song_text) - len(timestamp) - 2
                if padding > 0:
                    song_text = f"{song_text}{' ' * padding}{timestamp} "
                
                try:
                    if song_idx == cli.album_song_selected and cli.album_column == 1:
                        self.stdscr.attron(curses.color_pair(2))
                        self.stdscr.addstr(1 + i, separator_x + 1, (f" {SYMBOLS['pointer']}" + song_text[1:]).ljust(right_width))
                        self.stdscr.attroff(curses.color_pair(2))
                    elif is_playing:
                        self.stdscr.attron(curses.color_pair(3))
                        self.stdscr.addstr(1 + i, separator_x + 1, song_text[:right_width].ljust(right_width))
                        self.stdscr.attroff(curses.color_pair(3))
                    else:
                        self.stdscr.attron(curses.color_pair(5))
                        self.stdscr.addstr(1 + i, separator_x + 1, ("  " + song_text[2:])[:right_width].ljust(right_width))
                        self.stdscr.attroff(curses.color_pair(5))
                except curses.error:
                    pass
    
    def _render_status_bar(self, cli, command_input="", search_mode=False, search_state=None):
        view_names = {1: "Library", 2: "Albums", 3: "Queue"}
        view_name = view_names.get(cli.view_mode, "Library")
        
        shuffle_status = "Shuffle: ON" if cli.shuffle else "Shuffle: OFF"
        repeat_status = "Repeat: ON" if cli.repeat else "Repeat: OFF"
        
        search_info = ""
        if search_mode and search_state and search_state.filtered_indices:
            match_count = len(search_state.filtered_indices)
            total_count = len(cli._get_display_list())
            search_info = f" | {match_count}/{total_count} matches"
        
        left_status = f" {view_name} | {len(cli._get_current_songs())} tracks | {shuffle_status} | {repeat_status}{search_info}"
        
        try:
            self.stdscr.attron(curses.color_pair(6))
            self.stdscr.addstr(self.max_y - 3, 0, left_status[:self.max_x].ljust(self.max_x))
            self.stdscr.attroff(curses.color_pair(6))
        except curses.error:
            pass
        
        if command_input:
            try:
                if search_mode:
                    label = " Search: "
                else:
                    label = " Command: "
                self.stdscr.attron(curses.color_pair(1))
                self.stdscr.addstr(self.max_y - 2, 0, (label + command_input)[:self.max_x].ljust(self.max_x))
                self.stdscr.attroff(curses.color_pair(1))
            except curses.error:
                pass
        elif cli.error_message:
            is_success = (cli.error_message.startswith("Added") or 
                         cli.error_message.startswith("Loaded") or 
                         cli.error_message.startswith("Refreshed") or 
                         cli.error_message.startswith("Cleared") or 
                         "ON" in cli.error_message or 
                         "OFF" in cli.error_message or 
                         cli.error_message.startswith("Seeked") or 
                         cli.error_message.startswith("Volume:") or 
                         cli.error_message.startswith("Fading"))
            
            if is_success:
                self.stdscr.attron(curses.color_pair(8))
                icon = "✓" if UNICODE_SUPPORT else "+"
            else:
                self.stdscr.attron(curses.color_pair(4))
                icon = "✗" if UNICODE_SUPPORT else "!"
            
            try:
                message = self._truncate_text(cli.error_message, self.max_x - 4)
                self.stdscr.addstr(self.max_y - 2, 0, (f" {icon} {message}").ljust(self.max_x))
            except curses.error:
                pass
            
            self.stdscr.attroff(curses.color_pair(8))
            self.stdscr.attroff(curses.color_pair(4))
            
            if self.message_display_time == 0:
                self.message_display_time = time.time()
        else:
            try:
                self.stdscr.attron(curses.color_pair(7))
                self.stdscr.addstr(self.max_y - 2, 0, "".ljust(self.max_x))
                self.stdscr.attroff(curses.color_pair(7))
            except curses.error:
                pass
        
        help_line = " [c]Play/Pause [n]Next [p]Prev [/]Search [1]Library [2]Albums [3]Queue [:help]"
        try:
            self.stdscr.attron(curses.color_pair(7))
            self.stdscr.addstr(self.max_y - 1, 0, help_line[:self.max_x].ljust(self.max_x))
            self.stdscr.attroff(curses.color_pair(7))
        except curses.error:
            pass
    
    def show_help(self, keybindings):
        help_msg = help_text(keybindings)
        lines = help_msg.splitlines()
        scroll_pos = 0
        
        while True:
            self.stdscr.clear()
            max_lines = self.max_y - 1
            visible_lines = lines[scroll_pos:scroll_pos + max_lines]
            
            for i, line in enumerate(visible_lines):
                try:
                    self.stdscr.addstr(i, 0, line[:self.max_x])
                except curses.error:
                    pass
            
            try:
                status = f" Scroll: j/k or Up/Down | q to exit | Line {scroll_pos + 1}/{len(lines)}"
                self.stdscr.attron(curses.color_pair(1))
                self.stdscr.addstr(self.max_y - 1, 0, status[:self.max_x].ljust(self.max_x))
                self.stdscr.attroff(curses.color_pair(1))
            except curses.error:
                pass
            
            self.stdscr.refresh()
            
            key = self.stdscr.getch()
            
            if key in (ord('q'), ord('Q'), 27):
                break
            elif key in (curses.KEY_DOWN, ord('j')):
                if scroll_pos < max(0, len(lines) - max_lines):
                    scroll_pos += 1
            elif key in (curses.KEY_UP, ord('k')):
                if scroll_pos > 0:
                    scroll_pos -= 1
            elif key == curses.KEY_NPAGE:
                scroll_pos = min(scroll_pos + max_lines, max(0, len(lines) - max_lines))
            elif key == curses.KEY_PPAGE:
                scroll_pos = max(scroll_pos - max_lines, 0)
    
    def show_version(self):
        from main import APP_VERSION
        self.stdscr.attron(curses.color_pair(3))
        try:
            self.stdscr.addstr(self.max_y - 3, 0, 
                f"wmus v{APP_VERSION} - Press any key to continue".ljust(self.max_x))
        except curses.error:
            pass
        self.stdscr.attroff(curses.color_pair(3))
        self.stdscr.refresh()
        self.stdscr.nodelay(False)
        self.stdscr.getch()
        self.stdscr.nodelay(True)