"""Compatibility wrapper for the benchmark runner."""

from .evaluation import runner as _impl
from .evaluation.runner import *

main = _impl.main
select_documents = _impl.select_documents
_extract_one = _impl._extract_one

__all__ = ["main", "select_documents"]

if __name__ == "__main__":
    raise SystemExit(main())
