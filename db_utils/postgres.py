import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Union

import psycopg
from psycopg import conninfo, sql
from psycopg.errors import DatabaseError, OperationalError

logger = logging.getLogger(__name__)

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres@127.0.0.1:5432/postgres")
_DEFAULT_KEY = "__default__"


class PostgresDB:
    connections: Dict[str, psycopg.Connection] = {}

    @classmethod
    def _make_dsn(cls, db_name: Optional[str] = None) -> str:
        if db_name is None:
            return POSTGRES_DSN
        return conninfo.make_conninfo(POSTGRES_DSN, dbname=db_name)

    @classmethod
    def connect(cls, db_name: Optional[str] = None) -> bool:
        """Establish a PostgreSQL connection if one is not already open."""
        key = db_name or _DEFAULT_KEY
        connection = cls.connections.get(key)
        if connection is not None and not connection.closed:
            return True

        logger.info(
            "Attempting to connect to PostgreSQL using DSN: %s",
            cls._make_dsn(db_name),
        )
        try:
            connection = psycopg.connect(cls._make_dsn(db_name), autocommit=True)
            connection.execute(sql.SQL("SELECT 1"))
            cls.connections[key] = connection
            logger.info(
                "Connected to PostgreSQL%s",
                f" database '{db_name}'" if db_name else "",
            )
            return True
        except (OperationalError, DatabaseError) as exc:
            logger.error("Failed to connect to PostgreSQL: %s", exc)
            cls.connections.pop(key, None)
            return False

    @classmethod
    def close(cls, db_name: Optional[str] = None) -> None:
        """Close the PostgreSQL connection(s)."""
        if db_name is None:
            for connection in cls.connections.values():
                if connection and not connection.closed:
                    connection.close()
            cls.connections.clear()
            logger.info("Closed all PostgreSQL connections")
            return

        key = db_name or _DEFAULT_KEY
        connection = cls.connections.pop(key, None)
        if connection and not connection.closed:
            connection.close()
            logger.info("Closed PostgreSQL connection for database '%s'", db_name)

    @classmethod
    def get_connection(cls, db_name: Optional[str] = None) -> Optional[psycopg.Connection]:
        """Return the active PostgreSQL connection, creating it when required."""
        if not cls.connect(db_name):
            return None
        key = db_name or _DEFAULT_KEY
        return cls.connections.get(key)

    @classmethod
    def is_connected(cls, db_name: Optional[str] = None) -> bool:
        """Return whether PostgreSQL is connected and responding."""
        connection = cls.get_connection(db_name)
        if connection is None:
            return False
        try:
            connection.execute(sql.SQL("SELECT 1"))
            return True
        except (OperationalError, DatabaseError) as exc:
            logger.warning("PostgreSQL ping failed: %s", exc)
            return False

    @classmethod
    def status(cls, db_name: Optional[str] = None) -> dict:
        """Return diagnostic information for the PostgreSQL connection."""
        connection = cls.get_connection(db_name)
        if connection is None:
            return {"status": "disconnected"}
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                db_name_value, db_user = cur.fetchone()
            return {
                "status": "connected",
                "database": db_name_value,
                "user": db_user,
            }
        except (OperationalError, DatabaseError) as exc:
            logger.warning("Failed to query PostgreSQL status: %s", exc)
            return {"status": "error", "error": str(exc)}

def fetch_records(
    table: str,
    columns: Optional[Sequence[str]] = None,
    conditions: Optional[Dict[str, Any]] = None,
    order_by: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    db_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch rows from a table with optional filtering, ordering, and limits."""
    connection = PostgresDB.get_connection(db_name)
    if connection is None:
        logger.error("PostgreSQL connection is not available")
        return []
    selected_columns = (
        sql.SQL(", ").join(sql.Identifier(col) for col in columns)
        if columns
        else sql.SQL("*")
    )
    query = sql.SQL("SELECT {columns} FROM {table}").format(
        columns=selected_columns,
        table=sql.Identifier(table),
    )
    params: Dict[str, Any] = {}
    if conditions:
        where_clause = sql.SQL(" AND ").join(
            sql.SQL("{column} = {placeholder}").format(
                column=sql.Identifier(column),
                placeholder=sql.Placeholder(column),
            )
            for column in conditions.keys()
        )
        query += sql.SQL(" WHERE {where_clause}").format(where_clause=where_clause)
        params.update(conditions)
    if order_by:
        order_clause = sql.SQL(", ").join(sql.Identifier(col) for col in order_by)
        query += sql.SQL(" ORDER BY {order_clause}").format(order_clause=order_clause)
    if limit is not None:
        query += sql.SQL(" LIMIT {limit}").format(limit=sql.Literal(limit))
    try:
        with connection.cursor() as cur:
            cur.execute(query, params or None)
            rows = cur.fetchall()
            column_names = [desc.name for desc in cur.description]
    except (OperationalError, DatabaseError) as exc:
        logger.error("Failed to fetch records from %s: %s", table, exc)
        return []
    return [dict(zip(column_names, row)) for row in rows]

def insert_record(
    table: str,
    values: Dict[str, Any],
    returning: Optional[Sequence[str]] = None,
    db_name: Optional[str] = None,
) -> Optional[Union[Any, Sequence[Any]]]:
    """Insert a row into a table, optionally returning specific columns."""
    connection = PostgresDB.get_connection(db_name)
    if connection is None:
        logger.error("PostgreSQL connection is not available")
        return None

    if not values:
        logger.error("No values provided for insert into table '%s'", table)
        return None

    columns = sql.SQL(", ").join(sql.Identifier(col) for col in values.keys())
    placeholders = sql.SQL(", ").join(sql.Placeholder(col) for col in values.keys())

    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({values})").format(
        table=sql.Identifier(table),
        columns=columns,
        values=placeholders,
    )

    if returning:
        returning_clause = sql.SQL(", ").join(sql.Identifier(col) for col in returning)
        query += sql.SQL(" RETURNING {returning}").format(returning=returning_clause)

    try:
        with connection.cursor() as cur:
            cur.execute(query, values)
            if returning:
                row = cur.fetchone()
                if row is None:
                    return None
                if len(row) == 1:
                    return row[0]
                return row
            return cur.rowcount
    except (OperationalError, DatabaseError) as exc:
        logger.error("Failed to insert record into %s: %s", table, exc)
        return None


def insert_records(
    table: str,
    rows: List[Dict[str, Any]],
    returning: Optional[Sequence[str]] = None,
    db_name: Optional[str] = None,
) -> Optional[List[Union[Any, Sequence[Any]]]]:
    """Insert multiple rows into a table in a single batch."""
    if not rows:
        return []

    connection = PostgresDB.get_connection(db_name)
    if connection is None:
        logger.error("PostgreSQL connection is not available")
        return None

    columns = list(rows[0].keys())
    if not all(list(row.keys()) == columns for row in rows[1:]):
        logger.error("All rows must provide the same columns when inserting into '%s'", table)
        return None

    column_identifiers = sql.SQL(", ").join(sql.Identifier(col) for col in columns)
    placeholders = sql.SQL(", ").join(sql.Placeholder(col) for col in columns)
    payload = [{col: row[col] for col in columns} for row in rows]

    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({values})").format(
        table=sql.Identifier(table),
        columns=column_identifiers,
        values=placeholders,
    )

    if returning:
        returning_clause = sql.SQL(", ").join(sql.Identifier(col) for col in returning)
        query += sql.SQL(" RETURNING {returning}").format(returning=returning_clause)

    try:
        with connection.cursor() as cur:
            cur.executemany(query, payload)
            if returning:
                result_rows = cur.fetchall()
                if not result_rows:
                    return []
                if len(returning) == 1:
                    return [row[0] for row in result_rows]
                return [tuple(row) for row in result_rows]
            return cur.rowcount
    except (OperationalError, DatabaseError) as exc:
        logger.error("Failed to insert multiple records into %s: %s", table, exc)
        return None


def update_records(
    table: str,
    values: Dict[str, Any],
    conditions: Dict[str, Any],
    returning: Optional[Sequence[str]] = None,
    db_name: Optional[str] = None,
) -> Optional[Union[int, Sequence[Any]]]:
    """Update rows matching the conditions and optionally return columns."""
    connection = PostgresDB.get_connection(db_name)
    if connection is None:
        logger.error("PostgreSQL connection is not available")
        return None

    if not values:
        logger.error("No values provided for update in table '%s'", table)
        return None
    if not conditions:
        logger.error("Update in table '%s' requires at least one condition", table)
        return None

    set_clause = sql.SQL(", ").join(
        sql.SQL("{column} = {placeholder}").format(
            column=sql.Identifier(column),
            placeholder=sql.Placeholder(f"set_{column}"),
        )
        for column in values.keys()
    )
    where_clause = sql.SQL(" AND ").join(
        sql.SQL("{column} = {placeholder}").format(
            column=sql.Identifier(column),
            placeholder=sql.Placeholder(f"where_{column}"),
        )
        for column in conditions.keys()
    )

    params = {f"set_{column}": value for column, value in values.items()}
    params.update({f"where_{column}": value for column, value in conditions.items()})

    query = sql.SQL("UPDATE {table} SET {set_clause} WHERE {where_clause}").format(
        table=sql.Identifier(table),
        set_clause=set_clause,
        where_clause=where_clause,
    )

    if returning:
        returning_clause = sql.SQL(", ").join(sql.Identifier(col) for col in returning)
        query += sql.SQL(" RETURNING {returning}").format(returning=returning_clause)

    try:
        with connection.cursor() as cur:
            cur.execute(query, params)
            if returning:
                rows = cur.fetchall()
                if not rows:
                    return None
                if len(returning) == 1:
                    return [row[0] for row in rows]
                return rows
            return cur.rowcount
    except (OperationalError, DatabaseError) as exc:
        logger.error("Failed to update records in %s: %s", table, exc)
        return None


def update_many_records(
    table: str,
    rows: List[Dict[str, Any]],
    condition_keys: Sequence[str],
    returning: Optional[Sequence[str]] = None,
    db_name: Optional[str] = None,
) -> Optional[List[Union[int, Sequence[Any]]]]:
    """Update multiple rows by matching columns listed in condition_keys."""
    if not rows:
        return []

    connection = PostgresDB.get_connection(db_name)
    if connection is None:
        logger.error("PostgreSQL connection is not available")
        return None

    missing = [row for row in rows if not all(key in row for key in condition_keys)]
    if missing:
        logger.error("All rows must include condition keys %s for bulk update of '%s'", condition_keys, table)
        return None

    results: List[Union[int, Sequence[Any]]] = []

    for row in rows:
        values = {k: v for k, v in row.items() if k not in condition_keys}
        conditions = {k: row[k] for k in condition_keys}
        result = update_records(table, values, conditions, returning, db_name)
        results.append(result if result is not None else 0)

    return results

