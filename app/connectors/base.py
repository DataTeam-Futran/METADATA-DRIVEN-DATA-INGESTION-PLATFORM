"""
Base Connector Contract
=======================

This module defines the common interface that every database
connector in the Metadata-Driven Data Ingestion Platform must
follow.

The platform will eventually support databases such as:

    PostgreSQL
    MySQL
    SQL Server
    Oracle
    Snowflake
    Databricks
    etc.

The ingestion engine should NOT contain database-specific logic.

Instead, every database implements this common connector
interface.

Architecture:

    Ingestion Engine
          |
          v
    BaseConnector
          |
    -------------------------
    |    |      |      |
    PG  MySQL  Oracle  SQLServer
"""

from abc import ABC, abstractmethod
from typing import Any, Iterator

from app.models.connection import ConnectionMetadata


class BaseConnector(ABC):
    """
    Abstract base class for all database connectors.

    Every concrete connector must inherit from this class.

    Example:

        class PostgreSQLConnector(BaseConnector):
            ...

    This gives the ingestion engine one standard interface
    regardless of the underlying database technology.
    """

    def __init__(
        self,
        metadata: ConnectionMetadata,
    ) -> None:
        """
        Initialize the connector with resolved connection
        metadata.

        Parameters
        ----------
        metadata:
            Connection information resolved from the metadata
            database.

        WHY:
        ----
        We pass metadata into the connector instead of hardcoding
        host, port, username, database, etc.

        This is what makes the platform metadata-driven.
        """

        self.metadata = metadata

    # =========================================================
    # CONNECTION
    # =========================================================

    @abstractmethod
    def connect(self) -> None:
        """
        Establish a connection to the database.

        Each database implementation provides its own logic.

        Example:

            PostgreSQL -> psycopg
            MySQL      -> mysql connector
            SQL Server -> pyodbc
            Oracle     -> oracledb
        """

        raise NotImplementedError

    # =========================================================
    # CONNECTION TEST
    # =========================================================

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test whether the database connection is valid.

        Returns
        -------
        bool
            True when the connection is successful.
        """

        raise NotImplementedError

    # =========================================================
    # CLOSE CONNECTION
    # =========================================================

    @abstractmethod
    def close(self) -> None:
        """
        Close the database connection.

        Every connector must release its resources properly.
        """

        raise NotImplementedError

    # =========================================================
    # SCHEMA DISCOVERY
    # =========================================================

    @abstractmethod
    def list_schemas(self) -> list[str]:
        """
        Return the list of schemas available in the database.

        WHY:
        ----
        Schema discovery is the first stage of metadata discovery.

        Example:

            database
                |
                +-- public
                +-- sales
                +-- finance
        """

        raise NotImplementedError

    # =========================================================
    # TABLE DISCOVERY
    # =========================================================

    @abstractmethod
    def list_tables(
        self,
        schema_name: str,
    ) -> list[str]:
        """
        Return all tables available inside a schema.

        Parameters
        ----------
        schema_name:
            Name of the schema to inspect.
        """

        raise NotImplementedError

    # =========================================================
    # BATCH DATA READING
    # =========================================================

    @abstractmethod
    def read_batches(
        self,
        query: str,
        batch_size: int,
    ) -> Iterator[list[tuple[Any, ...]]]:
        """
        Read source data in controlled batches.

        WHY:
        ----
        A production ingestion platform must not load an entire
        large table into application memory.

        Instead:

            Source
              |
              v
            Batch 1
            Batch 2
            Batch 3
            ...
              |
              v
            Target

        Parameters
        ----------
        query:
            SQL query used to extract data.

        batch_size:
            Maximum number of records returned per batch.

        Returns
        -------
        Iterator
            Batches of rows.
        """

    # =========================================================
    # BATCH DATA WRITING
    # =========================================================

    @abstractmethod
    def write_batch(
        self,
        target_schema: str,
        target_table: str,
        column_names: list[str],
        rows: list[tuple[Any, ...]],
    ) -> int:
        """
        Write one batch of records into the target table.

        Parameters
        ----------
        target_schema:
            Target database schema where the table exists.

        target_table:
            Target table that receives the records.

        column_names:
            Ordered target column names.

            WHY:
            ----
            The column order must be explicitly controlled so that
            source values are written to the correct target columns.

        rows:
            Batch of records to insert.

        Returns
        -------
        int
            Number of rows successfully written.

        WHY:
        ----
        The ingestion engine should use one common write contract
        regardless of the target database technology.

        Example:

            PostgreSQLConnector
                -> psycopg

            SQLServerConnector
                -> pyodbc

            OracleConnector
                -> oracledb

            SnowflakeConnector
                -> Snowflake connector

        The execution engine should not contain vendor-specific
        database code.
        """

        # =========================================================
    # TRANSACTION MANAGEMENT
    # =========================================================

    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begin a target database transaction.

        WHY:
        ----
        Full-load execution may contain many batches.

        A transaction allows the execution engine to commit the
        complete target load as one logical operation.
        """

        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        """
        Commit the current target database transaction.

        WHY:
        ----
        The execution engine calls commit only after all source
        batches have been successfully written.
        """

        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """
        Roll back the current target database transaction.

        WHY:
        ----
        If any batch fails, the execution engine can roll back
        the target changes made during the current load.
        """

        raise NotImplementedError

    # =========================================================
    # TARGET TABLE PREPARATION
    # =========================================================

    @abstractmethod
    def truncate_table(
        self,
        target_schema: str,
        target_table: str,
    ) -> None:
        """
        Remove all existing rows from a target table.

        Parameters
        ----------
        target_schema:
            Target database schema.

        target_table:
            Target table.

        WHY:
        ----
        The current FULL_LOAD configuration uses the
        TRUNCATE_INSERT strategy.

        Therefore existing target rows must be removed before
        inserting the new source dataset.
        """

        raise NotImplementedError