import json
import os
import tempfile
from datetime import datetime
from pathlib import Path


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

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f'{path.name}.',
        suffix='.tmp',
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as temp_file:
            json.dump(status, temp_file, ensure_ascii=False, indent=2)
            temp_file.write('\n')
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
