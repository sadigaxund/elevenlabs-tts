

from mutagen.mp3 import MP3
from mutagen.easyid3 import ID3, EasyID3

from typing import Optional, Iterable, Sequence, Union, Final, NamedTuple
from enum import auto, StrEnum, Enum
from urllib.parse import quote
from decimal import Decimal
from pathlib import Path
import uuid
import random
from typing import List, Optional, Iterator, Sequence
from enum import Enum
from . import create_track_id

# units and convenience aliases
type Microseconds = int
type Position = int
type Duration = int
type UnitInterval = Decimal
type Volume = Decimal
type Rate = Decimal
# type Playlist = Sequence[Track]
type DbusObj = str

class Ordering(StrEnum):
  Alphabetical = auto()
  User = auto()

DEFAULT_TRACK_ID: Final[str] = '/default/1'
DEFAULT_TRACK_NAME: Final[str] = "Default Track"
DEFAULT_TRACK_LENGTH: Final[int] = 0
DEFAULT_PLAYLIST_COUNT: Final[int] = 1
DEFAULT_ORDERINGS: Final[list[Ordering]] = [
  Ordering.Alphabetical,
  Ordering.User,
]
DEFAULT_ALBUM_NAME: Final[str] = "Default Album"
DEFAULT_ARTIST_NAME: Final[str] = "Default Artist"
NO_ARTISTS: Final[tuple[Artist, ...]] = tuple()
NO_ARTIST_NAME: Final[str] = ''

class Artist(NamedTuple):
  name: str = DEFAULT_ARTIST_NAME

class Album(NamedTuple):
  art_url: str | None = None
  artists: Sequence[Artist] = NO_ARTISTS
  name: str = DEFAULT_ALBUM_NAME

class Track(NamedTuple):
  album: Album | None = None
  art_url: str | None = None
  artists: Sequence[Artist] = NO_ARTISTS
  comments: list[str] | None = None
  disc_number: int | None = None
  length: Duration = DEFAULT_TRACK_LENGTH
  name: str = DEFAULT_TRACK_NAME
  track_id: DbusObj = DEFAULT_TRACK_ID
  order_id: int = -1
  track_number: int | None = None
  type: Enum | None = None
  uri: str | None = None


def build_artists(*artists: Iterable[str]) -> Sequence[Artist]:
    return [Artist(name=artist) for artist in artists]


def build_track(
    track_url: str,
    player_name: str = 'Track',
    name: Optional[str] = None,
    artists: Optional[list[str]] = None,
    album: Optional[str] = None,
    track_number: Optional[int] = None,
    length: Optional[int] = None
) -> Track:
    """
    Create Track from MP3. Parameters override file metadata.
    """
    filepath = Path(track_url)
    
    # Try to get file metadata (simple extraction)
    file_name = filepath.stem
    file_artists = NO_ARTISTS
    file_album = None
    file_track_num = None
    file_length = DEFAULT_TRACK_LENGTH
    file_order_id = -1
    
    try:
        audio = MP3(filepath)
        if audio.info.length:
            file_length = int(audio.info.length * 1_000_000)
        
        try:
            id3 = EasyID3(filepath)

            if 'title' in id3:
                file_name = id3['title'][0]
            if 'artist' in id3:
                artist_names = [a.strip() for a in id3['artist'][0].split('/') if a.strip()]
                file_artists = [Artist(name=n) for n in artist_names]
            if 'album' in id3:
                album_artists = NO_ARTISTS
                if 'albumartist' in id3:
                    album_artist_names = [a.strip() for a in id3['albumartist'][0].split('/') if a.strip()]
                    album_artists = [Artist(name=n) for n in album_artist_names]
                file_album = Album(name=id3['album'][0], artists=album_artists)
            if 'tracknumber' in id3:
                try:
                    track_text = id3['tracknumber'][0]
                    file_track_num = int(track_text.split('/')[0]) if '/' in track_text else int(track_text)
                except (ValueError, AttributeError):
                    pass
        except:
            pass
    except:
        pass
    
    # Apply overrides: parameter > file metadata > default

    file_order_id = int(str(ID3(filepath).get('TXXX:order_id', -1)))
    final_name = name or file_name
    final_artists = [Artist(name=a) for a in artists] if artists else file_artists
    final_album = Album(name=album, artists=final_artists) if album else file_album
    final_track_num = track_number if track_number is not None else file_track_num
    final_length = length if length is not None else file_length
    

    # print(f"{final_artists=}")
    return Track(
        order_id=file_order_id,
        album=final_album,
        artists=final_artists,
        length=final_length,
        name=final_name,
        track_id=create_track_id(player_name=player_name),
        track_number=final_track_num,
        uri=f"file://{quote(str(filepath.absolute()))}"
    )

class PlaylistIterator:
    """Internal iterator for the Playlist class."""
    
    def __init__(self, playlist: 'Playlist'):
        self.playlist = playlist
        self._setup_iterator()
        
    def _setup_iterator(self):
        """Setup the iterator based on current playback mode."""
        self.current_index = 0
        self.tracks_to_play = []
        
        if self.playlist.shuffle_mode:
            # Create a shuffled copy without replacement
            self.tracks_to_play = self.playlist.tracks.copy()
            random.shuffle(self.tracks_to_play)
        else:
            # Linear mode - use tracks in their sorted order
            self.tracks_to_play = self.playlist.tracks
            
        # If we're in repeat_one mode, we'll only play the current track
        if self.playlist.repeat_mode == 'one' and self.playlist.current_track:
            self.tracks_to_play = [self.playlist.current_track]
            self.current_index = 0
            
    def __iter__(self):
        return self
    
    def __next__(self) -> Track:
        if not self.tracks_to_play:
            raise StopIteration
            
        # If we've reached the end of the playlist
        if self.current_index >= len(self.tracks_to_play):
            if self.playlist.repeat_mode == 'all':
                # Loop back to beginning for repeat all
                self.current_index = 0
                # Reshuffle if in shuffle mode
                if self.playlist.shuffle_mode:
                    self._setup_iterator()
            else:
                # No repeat or repeat one - stop iteration
                raise StopIteration
        
        track = self.tracks_to_play[self.current_index]
        self.current_index += 1
        
        # Update the playlist's current track
        self.playlist.current_track = track
        
        return track

class Playlist:
    """A playlist class with Spotify-like playback features."""
    
    def __init__(self, tracks: List[Track]):
        """
        Initialize playlist with tracks.
        
        Args:
            tracks: List of Track objects. Will be sorted by order_id descending.
                   Tracks with order_id = -1 (default) will be placed at the end.
        """
        # Sort tracks by order_id descending (largest first)
        # Handle default order_id (-1) by placing them at the end
        self.tracks = sorted(
            tracks, 
            key=lambda x: (x.order_id == -1, -x.order_id)
        )
        self.current_track: Optional[Track] = None
        self.shuffle_mode: bool = False
        self.repeat_mode: str = 'off'  # 'off', 'all', 'one'
        self._played_tracks: set = set()  # For shuffle without replacement tracking
        self._history: List[Track] = []  # Track history for navigation
        
    def set_linear(self) -> None:
        """Set playlist to linear playback mode."""
        self.shuffle_mode = False
        self._played_tracks.clear()
        
    def set_repeat(self, mode: str = 'all') -> None:
        """
        Set repeat mode.
        
        Args:
            mode: 'off', 'all', or 'one'
        """
        if mode not in ['off', 'all', 'one']:
            raise ValueError("Repeat mode must be 'off', 'all', or 'one'")
        self.repeat_mode = mode
        
    def set_shuffle(self, enable: bool = True) -> None:
        """
        Enable or disable shuffle mode.
        
        Args:
            enable: True to enable shuffle, False to disable
        """
        self.shuffle_mode = enable
        self._played_tracks.clear()
        
    def toggle_shuffle(self) -> None:
        """Toggle shuffle mode on/off."""
        self.shuffle_mode = not self.shuffle_mode
        self._played_tracks.clear()
        
    def toggle_repeat(self) -> str:
        """
        Cycle through repeat modes: off -> all -> one -> off
        
        Returns:
            The new repeat mode
        """
        modes = ['off', 'all', 'one']
        current_index = modes.index(self.repeat_mode)
        new_index = (current_index + 1) % len(modes)
        self.repeat_mode = modes[new_index]
        return self.repeat_mode
    
    def add_track(self, track: Track) -> None:
        """Add a track to the playlist."""
        self.tracks.append(track)
        # Maintain sorting by order_id descending
        self.tracks.sort(key=lambda x: (x.order_id == -1, -x.order_id))
        
    def add_tracks(self, tracks: List[Track]) -> None:
        """Add multiple tracks to the playlist."""
        self.tracks.extend(tracks)
        self.tracks.sort(key=lambda x: (x.order_id == -1, -x.order_id))
        
    def remove_track(self, uri: str) -> bool:
        """
        Remove a track by its URI.
        
        Returns:
            True if track was removed, False if not found
        """
        for i, track in enumerate(self.tracks):
            if track.uri == uri:
                removed_track = self.tracks.pop(i)
                # If we're removing the current track, clear it
                if self.current_track and self.current_track.uri == uri:
                    self.current_track = None
                # Also remove from history
                self._history = [t for t in self._history if t.uri != uri]
                return True
        return False
    
    def get_track_by_uri(self, uri: str) -> Optional[Track]:
        """Get a track by its URI."""
        for track in self.tracks:
            if track.uri == uri:
                return track
        return None
    
    def get_tracks_by_artist(self, artist_name: str) -> List[Track]:
        """Get all tracks by a specific artist."""
        return [
            track for track in self.tracks 
            if any(artist.name == artist_name for artist in track.artists)
        ]
    
    def get_tracks_by_album(self, album_name: str) -> List[Track]:
        """Get all tracks from a specific album."""
        return [
            track for track in self.tracks 
            if track.album and track.album.name == album_name
        ]
    
    def play_track(self, uri: str) -> Optional[Track]:
        """
        Start playing a specific track by URI.
        
        Returns:
            The track if found, None otherwise
        """
        track = self.get_track_by_uri(uri)
        if track:
            self.current_track = track
            # Add to history if not already the last played
            if not self._history or self._history[-1].uri != track.uri:
                self._history.append(track)
        return track
    
    def next_track(self) -> Optional[Track]:
        """Get the next track based on current playback mode."""
        try:
            # Create a temporary iterator to get next track
            iterator = PlaylistIterator(self)
            
            # If we have a current track, find its position in the iterator's list
            if iterator.current_index == 0 and self.current_track:
                # Find where we are in the current track list
                for i, track in enumerate(iterator.tracks_to_play):
                    if track.uri == self.current_track.uri:
                        iterator.current_index = i + 1
                        break
            
            # Get the next track
            next_track = next(iterator)
            
            # Add to history
            if next_track and (not self._history or self._history[-1].uri != next_track.uri):
                self._history.append(next_track)
                
            return next_track
        except StopIteration:
            return None
            
    def previous_track(self) -> Optional[Track]:
        """Get the previous track from history."""
        if not self._history or len(self._history) < 2:
            return None
            
        # Remove current track from history
        self._history.pop()
        
        # Get the previous track (now the last in history)
        previous_track = self._history[-1] if self._history else None
        self.current_track = previous_track
        
        return previous_track
    
    def clear_history(self) -> None:
        """Clear playback history."""
        self._history.clear()
    
    def get_sorted_tracks(self) -> List[Track]:
        """
        Get tracks in their current sorted order.
        
        Returns:
            List of tracks sorted by order_id descending
        """
        return self.tracks.copy()
    
    def get_shuffled_tracks(self) -> List[Track]:
        """
        Get a shuffled version of tracks without modifying the original order.
        
        Returns:
            Shuffled list of tracks
        """
        shuffled = self.tracks.copy()
        random.shuffle(shuffled)
        return shuffled
    
    def get_playback_info(self) -> dict:
        """Get current playback information."""
        return {
            'total_tracks': len(self.tracks),
            'shuffle': self.shuffle_mode,
            'repeat': self.repeat_mode,
            'current_track': {
                'uri': self.current_track.uri if self.current_track else None,
                'name': self.current_track.name if self.current_track else None,
                'order_id': self.current_track.order_id if self.current_track else None,
                'artists': [artist.name for artist in self.current_track.artists] 
                          if self.current_track and self.current_track.artists else []
            } if self.current_track else None,
            'history_size': len(self._history)
        }
    
    def __iter__(self) -> Iterator[Track]:
        """Return an iterator for the playlist."""
        return PlaylistIterator(self)
    
    def __len__(self) -> int:
        return len(self.tracks)
    
    def __getitem__(self, index: int) -> Track:
        return self.tracks[index]
    
    def __contains__(self, track: Track) -> bool:
        return any(t.uri == track.uri for t in self.tracks)


# Example usage with your Track structure
if __name__ == "__main__":
    # Create sample albums and artists
    album1 = Album(name="Sample Album 1")
    album2 = Album(name="Sample Album 2")
    
    artist1 = Artist(name="Artist 1")
    artist2 = Artist(name="Artist 2")
    
    # Create tracks with your Track structure
    tracks = [
        Track(
            uri="spotify:track:1",
            name="Track 1",
            album=album1,
            artists=[artist1],
            order_id=3
        ),
        Track(
            uri="spotify:track:2",
            name="Track 2",
            album=album1,
            artists=[artist1, artist2],
            order_id=5  # Highest order_id, will come first
        ),
        Track(
            uri="spotify:track:3",
            name="Track 3",
            album=album2,
            artists=[artist2],
            order_id=2
        ),
        Track(
            uri="spotify:track:4",
            name="Track 4",
            album=album2,
            artists=[artist2],
            order_id=4
        ),
        Track(
            uri="spotify:track:5",
            name="Track 5",
            album=album1,
            artists=[artist1],
            order_id=-1  # Default, will come last
        ),
    ]
    
    # Create playlist
    playlist = Playlist(tracks)
    
    print("Initial playlist (sorted by order_id descending, -1 last):")
    for i, track in enumerate(playlist.get_sorted_tracks()):
        print(f"  {i+1}. {track.name} - order_id: {track.order_id}")
    
    print("\n--- Testing Linear Playback ---")
    playlist.set_linear()
    playlist.set_repeat('off')
    print("Playing first 3 tracks in linear mode:")
    for i, track in enumerate(playlist):
        if i >= 3:
            break
        print(f"  Playing: {track.name} (URI: {track.uri})")
    
    print("\n--- Testing Shuffle Playback ---")
    playlist.set_shuffle(True)
    print("Playing 3 tracks in shuffle mode (without replacement):")
    playlist.current_track = None  # Reset
    for i, track in enumerate(playlist):
        if i >= 3:
            break
        print(f"  Playing: {track.name}")
    
    print("\n--- Testing Track Navigation ---")
    playlist.set_linear()
    playlist.set_repeat('off')
    
    # Play specific track
    playlist.play_track("spotify:track:3")
    print(f"Current track: {playlist.current_track.name if playlist.current_track else 'None'}")
    
    # Play next
    next_track = playlist.next_track()
    print(f"Next track: {next_track.name if next_track else 'None'}")
    
    # Play previous
    prev_track = playlist.previous_track()
    print(f"Previous track: {prev_track.name if prev_track else 'None'}")
    
    print("\n--- Testing Playback Info ---")
    info = playlist.get_playback_info()
    print(f"Total tracks: {info['total_tracks']}")
    print(f"Shuffle: {info['shuffle']}")
    print(f"Repeat: {info['repeat']}")
    print(f"Current track: {info['current_track']['name'] if info['current_track'] else 'None'}")