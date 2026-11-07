import json
import os
import tempfile
from pathlib import Path


def write_json_atomic(path, data, indent=2):
    """
    Writes JSON data atomically using a temporary file in the target directory.

    Readers see either the previous or the new complete file, never a partially
    written one. The temporary file is renamed via os.replace, which is atomic
    on the same filesystem.

    Args:
        path (Path): Destination file.
        data: JSON-serializable data.
        indent (int): JSON indentation.
    """
    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f'{path.name}.',
        suffix='.tmp',
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as temp_file:
            json.dump(data, temp_file, ensure_ascii=False, indent=indent)
            temp_file.write('\n')
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
