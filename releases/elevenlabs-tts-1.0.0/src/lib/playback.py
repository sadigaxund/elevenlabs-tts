#!/usr/bin/env python3
"""
Main application - Full integration with GStreamer playback and playlist management
"""

from lib import path_to_uri
from lib.gst import GStreamerPlayer
from lib.mpris import build_track, Playlist
from lib.DBUS import MprisSessionMessageBus, MprisPlayerInterface, MprisRootInterface, MprisEventLoop

from gi.repository import GLib
import threading
import os

def build_playlist(tracks_dir: str) -> Playlist:
    
    tracks = []
    for filename in os.listdir(tracks_dir):
        if filename.endswith(".mp3"):
            track_path = os.path.join(tracks_dir, filename)
            track = build_track(track_path)
            tracks.append(track)
    return Playlist(tracks)

# @lambda _:_()
def main():
    print("=" * 60)
    print("🎵 MPRIS Media Player with Playlist")
    print("=" * 60)
    
    # Build playlist from tracks directory
    print("📁 Loading playlist from ./tracks...")
    tracks = build_playlist('./tracks')
    playlist = Playlist(tracks)
    print(f"✅ Loaded {len(playlist)} tracks")
    
    if len(playlist) == 0:
        print("❌ No tracks found in ./tracks directory!")
        return
    
    # Display loaded tracks
    print("\n📋 Playlist:")
    for i, track in enumerate(playlist.get_sorted_tracks()):
        print(f"   {i+1}. {track.name} - {track.artists[0].name if track.artists else 'Unknown Artist'}")
    
    # Get first track and set as current
    first_track = playlist[0]
    playlist.current_track = first_track
    playlist._history.append(first_track)
    
    print(f"\n🎵 Starting with: {first_track.name}")
    
    # Initialize GStreamer player
    print("🎮 Initializing GStreamer player...")
    player = GStreamerPlayer()
    
    # Start GLib main loop in background thread (required for GStreamer)
    def run_glib_mainloop():
        """Run GLib's main loop in a background thread"""
        loop = GLib.MainLoop()
        loop.run()
    
    glib_thread = threading.Thread(target=run_glib_mainloop, daemon=True)
    glib_thread.start()
    print("✅ GLib main loop started in background")
    
    # MPRIS configuration
    player_name = "Track"
    bus_name = f"org.mpris.MediaPlayer2.{player_name}"
    object_path = "/org/mpris/MediaPlayer2"
    
    # Define playlist navigation callbacks
    def on_next_track():
        """Handle Next button - return next track from playlist"""
        next_track = playlist.next_track()
        if next_track:
            print(f"\n🔄 Switching to next track: {next_track.name}")
            # Load track into GStreamer
            player.set_uri(next_track.uri)
            return next_track
        else:
            print("\n⚠️  No next track available")
            return None
    
    def on_previous_track():
        """Handle Previous button - return previous track from playlist"""
        prev_track = playlist.previous_track()
        if prev_track:
            print(f"\n🔄 Switching to previous track: {prev_track.name}")
            # Load track into GStreamer
            player.set_uri(prev_track.uri)
            return prev_track
        else:
            print("\n⚠️  No previous track available")
            return None
    
    def on_exit_program():
        """Called when playlist finishes and should exit"""
        print(f"\n\n👋 Playlist complete - thanks for listening!")
        import sys
        player.stop()
        bus.disconnect()
        sys.exit(0)
    
    # Set up initial track in GStreamer
    player.set_uri(first_track.uri)
    
    # 1. Get the session bus
    print(f"\n📡 Connecting to D-Bus...")
    bus = MprisSessionMessageBus()

    # 2. Create MPRIS interfaces with GStreamer player and playlist callbacks
    print(f"🎵 Creating MPRIS interfaces...")
    root_obj = MprisRootInterface(player_name)
    interface = MprisPlayerInterface(
        initial_track=first_track,
        gst_player=player,
        on_next_track=on_next_track,
        on_previous_track=on_previous_track,
        on_exit_program=on_exit_program
    )
    
    # Wrap LoopStatus setter to sync with playlist
    _original_loop_status_setter = type(interface).LoopStatus.fset
    def synced_loop_status_setter(self, status):
        _original_loop_status_setter(self, status)
        # Sync with playlist repeat mode
        if status == "None":
            playlist.set_repeat('off')
        elif status == "Track":
            playlist.set_repeat('one')
        elif status == "Playlist":
            playlist.set_repeat('all')
        print(f"   🔄 Playlist repeat mode: {playlist.repeat_mode}")
    
    type(interface).LoopStatus = property(
        type(interface).LoopStatus.fget,
        synced_loop_status_setter
    )
   
    # 3. Publish objects on the bus
    print(f"📢 Publishing MPRIS objects...")
    bus.publish_object(object_path, root_obj)
    bus.publish_object(object_path, interface)

    # 4. Register service name
    print(f"🔖 Registering service: {bus_name}")
    bus.register_service(bus_name)
    
    # 5. Auto-start playback
    print(f"\n▶️  Auto-starting playback...")
    player.play()
    
    print("\n" + "=" * 60)
    print("✅ MPRIS service ready and playing!")
    print("=" * 60)
    print(f"\n🎧 Now playing: {first_track.name}")
    print(f"   Artist: {first_track.artists[0].name if first_track.artists else 'Unknown'}")
    print(f"   Album: {first_track.album.name if first_track.album else 'Unknown'}")
    print("\n🎮 Controls:")
    print("   • Use GNOME media controls to Play/Pause/Next/Previous")
    print("   • Adjust volume with media volume slider")
    print("   • Seek using the position slider")
    print("\n📊 Playlist features:")
    print(f"   • Shuffle: {playlist.shuffle_mode}")
    print(f"   • Repeat: {playlist.repeat_mode}")
    print(f"   • Total tracks: {len(playlist)}")
    print("\n⏹️  Press Ctrl+C to exit\n")

    # 6. Run the event loop
    loop = MprisEventLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        player.stop()
        bus.disconnect()
        print("✅ Goodbye!")