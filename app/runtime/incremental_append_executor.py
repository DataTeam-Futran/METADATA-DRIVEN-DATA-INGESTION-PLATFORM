"""Append source rows newer than the target's stored watermark."""

from app.connectors.base import BaseConnector


class IncrementalAppendExecutor:
    """Append rows whose source watermark is newer than the target max."""

    def __init__(self) -> None:
        self.source_rows_read = 0
        self.target_rows_written = 0

    def execute(
        self,
        source_connector: BaseConnector,
        target_connector: BaseConnector,
        source_schema: str,
        source_table: str,
        target_schema: str,
        target_table: str,
        source_columns: list[str],
        target_columns: list[str],
        watermark_column: str = "last_modified_at",
        batch_size: int = 1000,
    ) -> int:
        if not source_columns or len(source_columns) != len(target_columns):
            raise ValueError(
                "Source and target columns must be non-empty and have equal lengths."
            )
        if watermark_column not in source_columns:
            raise ValueError(
                f"Watermark column {watermark_column!r} must be selected from source."
            )
        if watermark_column not in target_columns:
            raise ValueError(
                f"Watermark column {watermark_column!r} must be stored in target."
            )
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        quoted_source_columns = ", ".join(
            self._quote_identifier(column) for column in source_columns
        )
        quoted_target = (
            f"{self._quote_identifier(target_schema)}."
            f"{self._quote_identifier(target_table)}"
        )
        quoted_target_watermark = self._quote_identifier(watermark_column)
        quoted_source = (
            f"{self._quote_identifier(source_schema)}."
            f"{self._quote_identifier(source_table)}"
        )
        quoted_source_watermark = self._quote_identifier(watermark_column)

        transaction_started = False
        self.source_rows_read = 0
        self.target_rows_written = 0
        try:
            source_connector.connect()
            target_connector.connect()

            target_checkpoint_query = (
                f"SELECT MAX({quoted_target_watermark}) FROM {quoted_target}"
            )
            checkpoint_batches = target_connector.read_batches(
                target_checkpoint_query,
                batch_size=1,
            )
            try:
                first_batch = next(checkpoint_batches, [])
            finally:
                checkpoint_batches.close()

            watermark = first_batch[0][0] if first_batch else None
            source_query = (
                f"SELECT {quoted_source_columns} FROM {quoted_source}"
            )
            parameters = None
            if watermark is not None:
                source_query += (
                    f" WHERE {quoted_source_watermark} > %s"
                    f" ORDER BY {quoted_source_watermark}"
                )
                parameters = (watermark,)
            else:
                source_query += f" ORDER BY {quoted_source_watermark}"

            target_connector.begin_transaction()
            transaction_started = True

            for source_batch in source_connector.read_batches(
                source_query,
                batch_size=batch_size,
                parameters=parameters,
            ):
                self.source_rows_read += len(source_batch)
                self.target_rows_written += target_connector.write_batch(
                    target_schema=target_schema,
                    target_table=target_table,
                    column_names=target_columns,
                    rows=source_batch,
                )

            target_connector.commit()
            transaction_started = False
            return self.target_rows_written
        except Exception:
            if transaction_started:
                try:
                    target_connector.rollback()
                except Exception:
                    pass
            raise
        finally:
            for connector in (target_connector, source_connector):
                try:
                    connector.close()
                except Exception:
                    pass

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        if not identifier or not identifier.strip():
            raise ValueError("SQL identifiers must not be empty.")
        return '"' + identifier.strip().replace('"', '""') + '"'