import subprocess

def get_selected_text():
    try:
        r = subprocess.run(["xclip", "-o", "-selection", "primary"],
                           capture_output=True, text=True, timeout=1)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


