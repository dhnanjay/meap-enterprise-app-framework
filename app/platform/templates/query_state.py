"""Query State — URL as the canonical representation of navigable view state.

Business state lives in the database.
Navigable view state lives in the URL.
Ephemeral interaction state lives in the browser.

This module provides typed structures and helpers so every module
handles search, filtering, sorting, and pagination consistently.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from urllib.parse import urlencode

from fastapi import Query
from pydantic import BaseModel
from starlette.datastructures import ImmutableMultiDict


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class PageQuery(BaseModel):
    """Base query model for list/search views.

    Every module extends this to add module-specific filters:
        class ExceptionQuery(PageQuery):
            status: ExceptionStatus | None = None
            min_amount: Decimal | None = None
    """

    q: str | None = None
    page: int = 1
    page_size: int = 25
    sort: str | None = None
    direction: SortDirection = SortDirection.ASC

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def is_desc(self) -> bool:
        return self.direction == SortDirection.DESC


def query_url(
    current: ImmutableMultiDict | dict[str, Any],
    *,
    set_: dict[str, Any] | None = None,
    reset: dict[str, Any] | None = None,
    remove: set[str] | list[str] | tuple[str, ...] | None = None,
) -> str:
    """Build a URL query string from current params with modifications.

    This is the platform helper for generating sort/filter/pagination links.

    Examples:
        # Flip sort direction on 'amount' column, reset to page 1
        query_url(request.query_params, set_={"sort": "amount", "direction": "desc"}, reset={"page": 1})

        # Change status filter, reset page
        query_url(request.query_params, set_={"status": "EXCEPTION"}, reset={"page": 1})

        # Pagination
        query_url(request.query_params, set_={"page": 3})
    """
    if hasattr(current, "multi_items"):
        params = dict(current.multi_items())
    else:
        params = dict(current)

    if set_:
        params.update({k: str(v) for k, v in set_.items()})

    if reset:
        for k, v in reset.items():
            params[k] = str(v)

    if remove:
        for key in remove:
            params.pop(key, None)

    if not params:
        return ""
    return "?" + urlencode(params, doseq=True)


def query_url_path(
    path: str,
    current: ImmutableMultiDict | dict[str, Any],
    *,
    set_: dict[str, Any] | None = None,
    reset: dict[str, Any] | None = None,
    remove: set[str] | list[str] | tuple[str, ...] | None = None,
) -> str:
    """Like query_url but prepends a path."""
    qs = query_url(current, set_=set_, reset=reset, remove=remove)
    return f"{path}{qs}"


# -- Sort column security (Section: URL Security) ------------------------


class SortMapper:
    """Maps allowed sort names to actual column expressions.

    Never interpolate raw request data into SQL. Always use a mapper:
        SORT_COLUMNS = {
            "amount": ExceptionRecord.amount,
            "date": ExceptionRecord.transaction_date,
        }
        mapper = SortMapper(SORT_COLUMNS)
        sort_column = mapper.resolve(query.sort)
    """

    def __init__(self, columns: dict[str, Any]) -> None:
        self._columns = columns

    def resolve(self, sort_name: str | None) -> Any | None:
        """Return the column for a sort name, or None if invalid/absent."""
        if sort_name is None:
            return None
        return self._columns.get(sort_name)

    @property
    def allowed(self) -> list[str]:
        return list(self._columns.keys())
