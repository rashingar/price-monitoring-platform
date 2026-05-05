"""Safe local CSV file editor support."""

from ecommerce.file_editor.csv_editor import (
    CsvReadResult,
    CsvWriteResult,
    InvalidCsvDelimiterError,
    read_csv_file,
    write_csv_copy,
    write_csv_file,
)
from ecommerce.file_editor.safe_paths import (
    DEFAULT_FILE_ROOTS,
    FILE_ROOTS_ENV_VAR,
    UnsafePathError,
    get_allowed_roots,
    get_file_root_entries,
    is_path_allowed,
    resolve_safe_path,
)

__all__ = [
    "CsvReadResult",
    "CsvWriteResult",
    "InvalidCsvDelimiterError",
    "read_csv_file",
    "write_csv_copy",
    "write_csv_file",
    "DEFAULT_FILE_ROOTS",
    "FILE_ROOTS_ENV_VAR",
    "UnsafePathError",
    "get_allowed_roots",
    "get_file_root_entries",
    "is_path_allowed",
    "resolve_safe_path",
]
