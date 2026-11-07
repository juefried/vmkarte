from datetime import datetime
from pathlib import Path

from libs.json_io_lib import write_json_atomic


def build_data_status(member_count, generated_at=None, run_started_at=None):
    """
    Builds the metadata written next to the map data.

    Args:
        member_count (int): Number of members written to vmforum_members.json.
        generated_at (datetime): Optional completion timestamp; defaults to local time.
        run_started_at (datetime): Optional start timestamp of the grabber run.

    Returns:
        dict: Metadata with ISO-8601 timestamps including UTC offset.
    """
    if generated_at is None:
        generated_at = datetime.now().astimezone()

    status = {
        'generatedAt': generated_at.isoformat(timespec='seconds'),
        'memberCount': member_count,
    }
    if run_started_at is not None:
        status = {
            'runStartedAt': run_started_at.isoformat(timespec='seconds'),
            **status,
        }
    return status


def write_data_status(path, member_count, generated_at=None, run_started_at=None):
    """
    Writes data-status.json atomically using a temporary file and os.replace.

    Args:
        path (Path): Destination file.
        member_count (int): Number of members written to vmforum_members.json.
        generated_at (datetime): Optional completion timestamp; defaults to local time.
        run_started_at (datetime): Optional start timestamp of the grabber run.
    """
    path = Path(path)
    status = build_data_status(member_count, generated_at, run_started_at)
    write_json_atomic(path, status)
