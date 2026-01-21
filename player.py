import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame
from mutagen import File
import time
from enum import IntEnum

class PlaybackState(IntEnum):
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2

class MusicPlayer:
    __slots__ = ('current_song', 'state', 'start_time', 'pause_time', '_cached_info', '_cached_duration')
    
    def __init__(self):
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception:
            pygame.mixer.init()
        self.current_song = None
        self.state = PlaybackState.STOPPED
        self.start_time = 0
        self.pause_time = 0
        self._cached_info = None
        self._cached_duration = 0

    @property
    def playing(self):
        return self.state == PlaybackState.PLAYING

    def load_song(self, song_path):
        if not os.path.exists(song_path):
            self.current_song = None
            self._cached_info = None
            self._cached_duration = 0
            raise FileNotFoundError(f"Song not found: {song_path}")
        
        pygame.mixer.music.load(song_path)
        self.current_song = song_path
        self.state = PlaybackState.STOPPED
        self.start_time = 0
        self.pause_time = 0
        self._cached_info = None
        self._cached_duration = 0

    def play(self):
        if self.current_song:
            pygame.mixer.music.play()
            self.state = PlaybackState.PLAYING
            self.start_time = time.time() - self.pause_time

    def stop(self):
        pygame.mixer.music.stop()
        self.state = PlaybackState.STOPPED
        self.start_time = 0
        self.pause_time = 0

    def pause(self):
        if self.state == PlaybackState.PLAYING:
            pygame.mixer.music.pause()
            self.state = PlaybackState.PAUSED
            self.pause_time = time.time() - self.start_time

    def unpause(self):
        if self.state == PlaybackState.PAUSED and self.current_song:
            if pygame.mixer.music.get_busy() or self.pause_time > 0:
                pygame.mixer.music.unpause()
                self.state = PlaybackState.PLAYING
                self.start_time = time.time() - self.pause_time
            else:
                self.play()

    def fadeout(self, ms=2000):
        pygame.mixer.music.fadeout(ms)
        self.state = PlaybackState.STOPPED

    def set_volume(self, volume):
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))

    def get_volume(self):
        return pygame.mixer.music.get_volume()

    def queue_song(self, song_path):
        if os.path.exists(song_path):
            pygame.mixer.music.queue(song_path)

    def get_song_info(self):
        if not self.current_song:
            return {}
        
        if self._cached_info is not None:
            return self._cached_info
        
        try:
            audio = File(self.current_song)
            if not audio:
                self._cached_info = {"title": "", "artist": "", "duration": 0}
                return self._cached_info
            
            self._cached_duration = int(audio.info.length) if audio.info else 0
            title = ""
            artist = ""
            
            if audio.tags:
                title = str(audio.tags.get('TIT2', audio.tags.get('title', [""]))[0])
                artist = str(audio.tags.get('TPE1', audio.tags.get('artist', [""]))[0])
            
            self._cached_info = {
                "title": title,
                "artist": artist,
                "duration": self._cached_duration
            }
            return self._cached_info
        except Exception:
            self._cached_info = {"title": "", "artist": "", "duration": 0}
            return self._cached_info

    def get_pos(self):
        if self.state == PlaybackState.PLAYING and self.start_time > 0:
            return int(time.time() - self.start_time)
        elif self.pause_time > 0:
            return int(self.pause_time)
        return 0

    def seek(self, seconds):
        if not self.current_song:
            return
        
        if self._cached_duration == 0:
            try:
                audio = File(self.current_song)
                self._cached_duration = int(audio.info.length) if audio and audio.info else 0
            except Exception:
                return
        
        current_pos = self.get_pos()
        new_pos = max(0, min(current_pos + seconds, self._cached_duration))
        
        was_playing = self.state == PlaybackState.PLAYING
        
        try:
            pygame.mixer.music.load(self.current_song)
            pygame.mixer.music.play(start=new_pos)
            
            if was_playing:
                self.state = PlaybackState.PLAYING
                self.start_time = time.time() - new_pos
                self.pause_time = 0
            else:
                pygame.mixer.music.pause()
                self.state = PlaybackState.PAUSED
                self.pause_time = new_pos
        except Exception:
            pass

    def is_song_finished(self):
        return (self.current_song and 
                self.state == PlaybackState.PLAYING and 
                not pygame.mixer.music.get_busy())