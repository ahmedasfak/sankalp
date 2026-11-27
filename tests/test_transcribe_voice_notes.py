from pathlib import Path

from transcribe_voice_notes import DEFAULT_FOLDER, HERE


def test_default_voice_notes_folder_is_in_data():
    assert DEFAULT_FOLDER == HERE.parent / "data" / "voice-notes"
    assert DEFAULT_FOLDER.is_dir()
