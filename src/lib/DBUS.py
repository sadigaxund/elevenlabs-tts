#!/usr/bin/env python3
import os
import sys
from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Str, Dict, Int64, Variant, ObjPath, List
from dasbus.loop import EventLoop
from dasbus.server.template import InterfaceTemplate
from gi.repository import GLib

from lib.mpris import Track
from lib.gst import GStreamerPlayer

MprisSessionMessageBus = SessionMessageBus
MprisEventLoop = EventLoop

# --------------------------------------------------------------------
# 1. Define the Root Interface (org.mpris.MediaPlayer2)
# --------------------------------------------------------------------
@dbus_interface("org.mpris.MediaPlayer2")
class MprisRootInterface:
    """
    The root interface for identity and basic capabilities.
    """

    def __init__(self, player_name: str):
        self._player_name = player_name

    @property
    def Identity(self) -> Str:
        """The name of the player."""
        return self._player_name

    @property
    def DesktopEntry(self) -> Str:
        """The desktop filename without the '.desktop' suffix."""
        return "my-media-player"  # e.g., 'vlc', 'rhythmbox'

    @property
    def SupportedUriSchemes(self) -> List[Str]:
        """URI schemes the player can handle."""
        return ["file"]

    @property
    def SupportedMimeTypes(self) -> List[Str]:
        """MIME types the player can handle."""
        return ["audio/mpeg", "audio/x-wav"]

    @property
    def CanRaise(self) -> bool:
        """Whether the player can show its GUI."""
        return False

    @property
    def CanQuit(self) -> bool:
        """Whether the player can be told to quit."""
        return False

    @property
    def HasTrackList(self) -> bool:
        """Whether the player manages a track list."""
        return False

    # Methods (Raise and Quit are typical no-ops for a background service)
    def Raise(self):
        pass

    def Quit(self):
        pass

# --------------------------------------------------------------------
# 2. Define the Player Interface (org.mpris.MediaPlayer2.Player)
# This is the core interface for playback control.
# --------------------------------------------------------------------
@dbus_interface("org.mpris.MediaPlayer2.Player")
class MprisPlayerInterface:
    """
    The authoritative MPRIS interface that directly controls a GStreamerPlayer.
    Handles all state management and D-Bus communication, converting between
    MPRIS units (microseconds) and GStreamer units (seconds).
    """
    
    # Define D-Bus signals
    PropertiesChanged = dbus_signal()
    
    @dbus_signal
    def Seeked(self, Position: Int64):
        """Emitted when position changes discontinuously (seeking)."""
        pass

    def __init__(self, initial_track: 'Track' = None, gst_player: GStreamerPlayer = None, 
                 on_next_track=None, on_previous_track=None, on_exit_program=None):
        """
        Args:
            initial_track: The first track to set as current metadata
            gst_player: GStreamerPlayer instance for actual audio playback (OPTIONAL)
            on_next_track: Callback function when Next is pressed - should return new Track or None
            on_previous_track: Callback function when Previous is pressed - should return new Track or None
            on_exit_program: Callback function to exit the program gracefully
        """
        self._gst_player: GStreamerPlayer = gst_player
        self._on_next_track = on_next_track
        self._on_previous_track = on_previous_track
        self._on_exit_program = on_exit_program
        
        # Initialize with a "Playing" state to grab focus
        self._playback_status = "Playing"
        self._loop_status = "None"
        self._shuffle = False
        self._volume = 1.0
        
        # Build metadata for the first track
        self._metadata = self._build_metadata_for_track(initial_track)
        self._position = Int64(0)
        
        # Get duration from track metadata (already in microseconds)
        if initial_track and hasattr(initial_track, 'length'):
            self._duration = Int64(initial_track.length)
        else:
            self._duration = Int64(0)
        
        # Timer for updating playback position when playing
        self._position_timer_id = None
        if self._playback_status == "Playing":
            self._start_position_timer()
        
        # Register track-end callback with GStreamer
        if self._gst_player:
            self._gst_player.set_on_track_end_callback(self._on_track_finished)
            
        print(f"✅ MprisPlayerInterface initialized")

    def _emit_properties_changed(self, changed_props: Dict[str, Variant], invalidated_props: List[str] = None):
        """Helper to emit PropertiesChanged signal."""
        try:
            # Emit the signal
            self.PropertiesChanged(
                "org.mpris.MediaPlayer2.Player",  # Interface name
                changed_props,                     # Changed properties
                invalidated_props or []           # Invalidated properties
            )
        except Exception as e:
            print(f"ERROR: Failed to emit PropertiesChanged: {e}")
            import traceback
            traceback.print_exc()

    def _build_metadata_for_track(self, track: 'Track' = None) -> Dict[Str, Variant]:
        """Build valid MPRIS metadata dictionary from a Track object."""
        if track and hasattr(track, 'uri') and track.uri:
            return {
                "mpris:trackid": Variant("o", ObjPath(track.track_id if hasattr(track, 'track_id') else "/org/mpris/MediaPlayer2/TrackList/NoTrack")),
                "mpris:artUrl": Variant("s", track.art_url or ""),
                "xesam:title": Variant("s", track.name),
                "xesam:url": Variant("s", track.uri),
                "xesam:artist": Variant("as", [track.artists[0].name] if track.artists else [""]),
                "xesam:album": Variant("s", track.album.name if track.album else ""),
                "mpris:length": Variant("x", Int64(track.length if hasattr(track, 'length') else 0))
            }
        else:
            return {
                "mpris:trackid": Variant("o", ObjPath("/org/mpris/MediaPlayer2/TrackList/NoTrack")),
                "xesam:title": Variant("s", "No Track"),
            }

    def _seconds_to_microseconds(self, seconds: float) -> Int64:
        """Convert seconds to microseconds for MPRIS."""
        return Int64(int(seconds * 1_000_000))

    def _microseconds_to_seconds(self, microseconds: Int64) -> float:
        """Convert microseconds to seconds for GStreamer."""
        return microseconds / 1_000_000.0

    def _start_position_timer(self):
        """Start a timer to update playback position from GStreamer when playing."""
        if self._position_timer_id:
            GLib.source_remove(self._position_timer_id)
        self._position_timer_id = GLib.timeout_add(100, self._update_position_from_gstreamer)
        print(f"DEBUG: Position timer started")

    def _stop_position_timer(self):
        """Stop the position update timer."""
        if self._position_timer_id:
            GLib.source_remove(self._position_timer_id)
            self._position_timer_id = None
            print(f"DEBUG: Position timer stopped")

    def _update_position_from_gstreamer(self) -> bool:
        """
        Update position from GStreamer and emit signal. Returns True to keep timer alive.
        """
        if self._playback_status == "Playing":
            if self._gst_player and hasattr(self._gst_player, 'get_position'):
                # Get actual position from GStreamer
                current_seconds = self._gst_player.get_position()
                new_position = self._seconds_to_microseconds(current_seconds)
            else:
                # Fallback: increment position by 100ms (timer interval)
                current_micros = int(self._position) + 100000
                new_position = Int64(min(current_micros, int(self._duration)))
            
            if new_position != self._position:
                old_position = self._position
                self._position = new_position
                
                # CRITICAL: Emit PropertiesChanged so GNOME slider follows position
                self._emit_properties_changed({
                    "Position": Variant("x", self._position)
                })
        
        return True  # Keep timer running

    def set_current_track(self, track: 'Track'):
        """Set the current track and update all related state."""
        old_track_id = self._metadata.get("mpris:trackid")
        self._metadata = self._build_metadata_for_track(track)
        
        # Update duration from track metadata
        if track and hasattr(track, 'length'):
            self._duration = Int64(track.length)
        
        self._position = Int64(0)  # Reset position for new track

        print(f"🎵 MPRIS: Track changed to: {track.name if track else 'None'}")

        # Remember if we were playing
        was_playing = self._playback_status == "Playing"

        # Load the track into GStreamer and restart playback if needed
        if self._gst_player and hasattr(self._gst_player, 'set_uri') and track and track.uri:
            # CRITICAL: Stop before changing URI, otherwise it won't actually switch tracks
            if was_playing:
                self._gst_player.stop()
                print(f"   ⏹️  Stopped current track")
            
            self._gst_player.set_uri(track.uri)
            print(f"   📀 Loaded into GStreamer: {track.uri}")
            
            # If we were playing, start the new track
            if was_playing:
                self._gst_player.play()
                print(f"   ▶️  Started playback of new track")

        # Emit change signals
        self._emit_properties_changed({
            "Metadata": Variant("a{sv}", self._metadata)
        })

        # If track ID changed, invalidate Position property  
        new_track_id = self._metadata.get("mpris:trackid")

        old_id_str = old_track_id.unpack()
        new_id_str = new_track_id.unpack()
        
        if old_id_str != new_id_str:
            self._emit_properties_changed({}, ["Position"])

    def _on_track_finished(self):
        """
        Called when track ends (EOS from GStreamer).
        Handles the logic based on LoopStatus:
        - 'Track': Restart current track
        - 'Playlist': Go to next track, loop if at end
        - 'None': Exit program immediately
        """
        print(f"\n🎵 MPRIS: Track finished (LoopStatus: {self._loop_status})")
        
        if self._loop_status == "Track":
            # Repeat single track
            print(f"   🔁 Repeating current track")
            if self._gst_player:
                self._gst_player.set_position(0)  # Restart from beginning
                self._gst_player.play()
                self._position = Int64(0)
                self._emit_properties_changed({
                    "Position": Variant("x", self._position)
                })
        
        elif self._loop_status == "Playlist":
            # Go to next track, loop back to start if at end
            print(f"   ➡️  Moving to next track (Playlist mode)")
            if self._on_next_track:
                next_track = self._on_next_track()
                if next_track:
                    self.set_current_track(next_track)
                    self.Play()
                else:
                    # Reached end of playlist, shouldn't happen in Playlist mode
                    # The callback should handle looping internally
                    print(f"   ⚠️  Playlist callback returned None in Playlist mode!")
                    if self._on_exit_program:
                        self._on_exit_program()
        
        else:  # LoopStatus == "None"
            # Exit program immediately when any track finishes
            print(f"   🏁 Track finished - exiting program")
            if self._on_exit_program:
                self._on_exit_program()
            else:
                print("   ⚠️  No exit callback set!")


    # --- MPRIS Properties with Signaling ---
    @property
    def PlaybackStatus(self) -> Str:
        print(f"DEBUG: PlaybackStatus getter called, returning: {self._playback_status}")
        return self._playback_status

    @property
    def LoopStatus(self) -> Str:
        return self._loop_status

    @LoopStatus.setter
    def LoopStatus(self, status: Str):
        if status in ("None", "Track", "Playlist") and self._loop_status != status:
            self._loop_status = status
            self._emit_properties_changed({
                "LoopStatus": Variant("s", status)
            })
            # TODO: Apply loop mode to GStreamer player if supported

    @property
    def Volume(self) -> float:
        """Get current volume level."""
        if self._gst_player and hasattr(self._gst_player, 'get_volume'):
            return self._gst_player.get_volume()
        return self._volume

    @Volume.setter
    def Volume(self, value: float):
        """Set volume level."""
        new_value = max(0.0, min(value, 1.0))
        if self._volume != new_value:
            self._volume = new_value
            print(f"🎵 MPRIS: Volume changed to {new_value:.0%}")
            print(f"🔊 VOLUME: {new_value:.0%}")
            
            # Set volume in GStreamer
            if self._gst_player and hasattr(self._gst_player, 'set_volume'):
                self._gst_player.set_volume(new_value)
            
            self._emit_properties_changed({
                "Volume": Variant("d", float(new_value))
            })

    @property
    def Metadata(self) -> Dict[Str, Variant]:
        return self._metadata

    @property
    def Position(self) -> Int64:
        """Get current playback position."""
        return self._position

    @property
    def CanGoNext(self) -> bool:
        # TODO: Implement logic based on your playlist
        return True

    @property
    def CanGoPrevious(self) -> bool:
        # TODO: Implement logic based on your playlist
        return True

    @property
    def CanPlay(self) -> bool:
        return True

    @property
    def CanPause(self) -> bool:
        return True

    @property
    def CanSeek(self) -> bool:
        return True

    @property
    def CanControl(self) -> bool:
        return True  # Must be True for the player to be controllable

    # --- Core MPRIS Methods ---
    def Play(self):
        """Start or resume playback."""
        print(f"🎵 MPRIS: Play() called (current status: {self._playback_status})")
        if self._playback_status != "Playing":
            self._playback_status = "Playing"
            self._start_position_timer()
            self._emit_properties_changed({
                "PlaybackStatus": Variant("s", "Playing")
            })
            
            # Call GStreamer's play() method
            if self._gst_player and hasattr(self._gst_player, 'play'):
                self._gst_player.play()
            
            print(f"▶️  NOW PLAYING")
        else:
            print(f"⚠️  Already playing")

    def Pause(self):
        """Pause playback."""
        print(f"🎵 MPRIS: Pause() called (current status: {self._playback_status})")
        if self._playback_status == "Playing":
            self._playback_status = "Paused"
            self._stop_position_timer()
            self._emit_properties_changed({
                "PlaybackStatus": Variant("s", "Paused")
            })
            
            # Call GStreamer's pause() method
            if self._gst_player and hasattr(self._gst_player, 'pause'):
                self._gst_player.pause()
            
            print(f"⏸️  PAUSED")
        else:
            print(f"⚠️  Not playing (status: {self._playback_status})")

    def PlayPause(self):
        """Toggle play/pause."""
        print(f"🎵 MPRIS: PlayPause() called")
        if self._playback_status == "Playing":
            self.Pause()
        else:
            self.Play()

    def Stop(self):
        """Stop playback."""
        print(f"🎵 MPRIS: Stop() called")
        if self._playback_status != "Stopped":
            self._playback_status = "Stopped"
            self._stop_position_timer()
            self._position = Int64(0)
            self._emit_properties_changed({
                "PlaybackStatus": Variant("s", "Stopped")
            })
            
            # Call GStreamer's stop() method
            if self._gst_player and hasattr(self._gst_player, 'stop'):
                self._gst_player.stop()
            
            print(f"⏹️  STOPPED")
        else:
            print(f"⚠️  Already stopped")

    def Next(self):
        """Skip to the next track."""
        print(f"🎵 MPRIS: Next()  called")
        print(f"⏭️  NEXT TRACK")
        
        # Call the playlist navigation callback if provided
        if self._on_next_track:
            next_track = self._on_next_track()
            if next_track:
                self.set_current_track(next_track)
                # Start playing the new track automatically
                if self._playback_status != "Stopped":
                    self.Play()
        
        # Invalidate position since track changed
        self._emit_properties_changed({}, ["Position"])

    def Previous(self):
        """Skip to the previous track."""
        print(f"🎵 MPRIS: Previous() called")
        print(f"⏮️  PREVIOUS TRACK")
        
        # Call the playlist navigation callback if provided
        if self._on_previous_track:
            prev_track = self._on_previous_track()
            if prev_track:
                self.set_current_track(prev_track)
                # Start playing the new track automatically
                if self._playback_status != "Stopped":
                    self.Play()
        
        # Invalidate position since track changed
        self._emit_properties_changed({}, ["Position"])

    def Seek(self, Offset: Int64):
        """Seek forward or backward by Offset microseconds."""
        offset_seconds = self._microseconds_to_seconds(Offset)
        print(f"🎵 MPRIS: Seek() called with offset {Offset}μs ({offset_seconds:.2f}s)")
        
        # Calculate new absolute position
        new_position = Int64(max(0, min(int(self._position) + int(Offset), int(self._duration))))
        new_position_seconds = self._microseconds_to_seconds(new_position)
        
        # Call GStreamer's set_position with absolute time (cleaner than seek with offset)
        if self._gst_player and hasattr(self._gst_player, 'set_position'):
            self._gst_player.set_position(new_position_seconds)
        
        # Update our position immediately
        self._position = new_position
        
        print(f"⏩ SEEK: {'+' if Offset > 0 else ''}{offset_seconds:.2f}s → Position: {self._microseconds_to_seconds(self._position):.2f}s")
        
        # Emit Seeked signal (required by MPRIS spec for position updates)
        self.Seeked(self._position)

    def SetPosition(self, TrackId: ObjPath, Position: Int64):
        """Set playback position to specific time for a specific track."""
        position_seconds = self._microseconds_to_seconds(Position)
        print(f"🎵 MPRIS: SetPosition() called - TrackId={TrackId}, Position={Position}μs ({position_seconds:.2f}s)")
        
        # Verify the track ID matches current track
        current_track_id_variant = self._metadata.get("mpris:trackid")
        if current_track_id_variant:
            current_track_id = current_track_id_variant.unpack()
        else:
            current_track_id = "/org/mpris/MediaPlayer2/TrackList/NoTrack"
            
        if current_track_id != str(TrackId):
            print(f"⚠️  Track ID mismatch! Current: {current_track_id}, Requested: {TrackId}")
            return

        # Update position immediately (don't wait for GStreamer as it's async)
        self._position = Position
        
        # Call GStreamer's set_position method
        if self._gst_player and hasattr(self._gst_player, 'set_position'):
            self._gst_player.set_position(position_seconds)
        
        print(f"🎯 SET POSITION: {position_seconds:.2f}s")
        
        # Emit Seeked signal (required by MPRIS spec for position updates)
        self.Seeked(self._position)


# --------------------------------------------------------------------
# 3. Service Manager class to publish the interfaces
# --------------------------------------------------------------------
class MprisServiceManager:
    def __init__(self, player_name: str = "MyMediaPlayer", gst_player: GStreamerPlayer = None, initial_track: Track = None):
        self.player_name = player_name
        self.gst_player = gst_player
        self.initial_track = initial_track
        
        # Create D-Bus connection
        self.bus = SessionMessageBus()
        
        # Create interfaces
        self.root_interface = MprisRootInterface(player_name)
        self.player_interface = MprisPlayerInterface(initial_track, gst_player)
        
        # Get object path
        self.object_path = "/org/mpris/MediaPlayer2"
        
        print(f"DEBUG: MprisServiceManager initialized for {player_name}")
        
    def publish(self):
        """Publish the MPRIS service on the session bus."""
        try:
            # Export the root object with both interfaces
            self.bus.publish_object(
                self.object_path,
                (self.root_interface, self.player_interface)
            )
            
            # Request the bus name
            self.bus.register_service(f"org.mpris.MediaPlayer2.{self.player_name}")
            
            print(f"DEBUG: MPRIS service published at {self.object_path}")
            print(f"DEBUG: Bus name: org.mpris.MediaPlayer2.{self.player_name}")
            
            # Start the event loop
            loop = EventLoop()
            print("DEBUG: MPRIS service running. Press Ctrl+C to exit.")
            loop.run()
            
        except Exception as e:
            print(f"ERROR: Failed to publish MPRIS service: {e}")
            import traceback
            traceback.print_exc()
            
    def update_track(self, track: Track):
        """Update the current track metadata."""
        self.player_interface.set_current_track(track)