
def path_to_uri(file_path: str) -> str:
    """
    Convert a local file path to a properly encoded file:// URI.
    
    Args:
        file_path: Local path (can be relative like './tracks/song.mp3')
    
    Returns:
        A properly encoded file:// URI
    """

    from pathlib import Path
    from urllib.parse import quote
    # Convert to absolute path and resolve any symlinks/.././
    absolute_path = Path(file_path).resolve()
    
    # Convert to string and URL-encode special characters
    encoded_path = quote(str(absolute_path))
    
    # Add the file:// protocol prefix
    return f"file://{encoded_path}"

def create_track_id(uuid_str: str = None, player_name = 'Track') -> str:
    import uuid
    """Create a valid D-Bus object path from a UUID."""
    if uuid_str is None:
        uuid_str = str(uuid.uuid4())
    
    # Replace hyphens with underscores
    safe_uuid = uuid_str.replace('-', '_')
    
    # Optionally, validate the path
    # GLib.Variant.new_object_path would validate, but let's be safe
    return f"/org/mpris/MediaPlayer2/{player_name}/{safe_uuid}"
