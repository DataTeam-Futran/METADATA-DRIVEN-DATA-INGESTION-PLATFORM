"""
Runtime Physical Object Resolver

Purpose
-------
This module resolves the physical source and target objects required by the
runtime execution engine.

The runtime execution plan contains logical dataset IDs:

    Source Dataset ID -> 7
    Target Dataset ID -> 8

Those logical dataset IDs must be resolved to their physical locations using
catalog.dataset_binding.

For example:

    Source Dataset 7
        -> Connection 1
        -> demo_source_db.public.customer

    Target Dataset 8
        -> Connection 11
        -> ingestion_metastore.warehouse.customer_target

Important
---------
This module is READ ONLY.

It does not:
    - create tables
    - modify metadata
    - connect to source/target databases
    - move data

It only resolves metadata needed by the execution engine.
"""

from dataclasses import dataclass

from app.db.metastore import get_metastore_connection


@dataclass(frozen=True)
class RuntimeObject:
    """
    Represents a physical source or target object resolved from metadata.

    The object contains the connection reference and physical database/schema
    information required later by the execution engine.
    """

    # Logical dataset identifier from catalog.dataset.
    dataset_id: int

    # Physical binding identifier from catalog.dataset_binding.
    dataset_binding_id: int

    # Connection profile identifier used to resolve the actual connector.
    connection_id: int

    # Logical dataset code from catalog.dataset.
    dataset_code: str

    # Physical database/catalog name.
    catalog_name: str | None

    # Physical schema name.
    schema_name: str | None

    # Physical table/view/object name.
    object_name: str

    # Normalized physical object name used for metadata matching.
    object_name_normalized: str | None


class RuntimeObjectResolver:
    """
    Resolves source and target physical objects from metadata.

    The resolver deliberately works with dataset IDs instead of hardcoded
    database/table names. This is what allows the ingestion platform to remain
    metadata-driven.
    """

    def resolve(
        self,
        dataset_id: int,
        tenant_id: int,
        environment_id: int,
    ) -> RuntimeObject:
        """
        Resolve one logical dataset to its active physical binding.

        Parameters
        ----------
        dataset_id:
            Logical dataset identifier from catalog.dataset.

        tenant_id:
            Tenant that owns the dataset.

        environment_id:
            Runtime environment in which the dataset is being executed.

        Returns
        -------
        RuntimeObject
            Physical object information required by the execution engine.

        Raises
        ------
        ValueError
            If an invalid identifier is supplied.

        LookupError
            If no active binding is found.
        """

        # Validate the identifiers before querying metadata.
        if dataset_id <= 0:
            raise ValueError("dataset_id must be greater than zero.")

        if tenant_id <= 0:
            raise ValueError("tenant_id must be greater than zero.")

        if environment_id <= 0:
            raise ValueError("environment_id must be greater than zero.")

        # The dataset table contains logical metadata such as dataset_code.
        #
        # The dataset_binding table contains physical metadata such as:
        #   - connection_id
        #   - catalog_name
        #   - schema_name
        #   - object_name
        #
        # We therefore join the two tables using dataset_id.
        #
        # IMPORTANT:
        # We use the actual column names discovered from the metadata
        # inspection:
        #
        #   catalog_name
        #   object_name_normalized
        #
        # We do NOT assume database_name or normalized_object_name.
        query = """
            SELECT
                d.dataset_id,
                db.dataset_binding_id,
                db.connection_id,
                d.dataset_code,
                db.catalog_name,
                db.schema_name,
                db.object_name,
                db.object_name_normalized
            FROM catalog.dataset AS d
            INNER JOIN catalog.dataset_binding AS db
                ON db.dataset_id = d.dataset_id
            WHERE d.dataset_id = %s
              AND d.tenant_id = %s
              AND db.tenant_id = %s
              AND db.environment_id = %s
              AND d.status_code = 'ACTIVE'
              AND db.status_code = 'ACTIVE'
            ORDER BY db.dataset_binding_id DESC
            LIMIT 1;
        """

        # Open a metadata-store connection.
        #
        # This connection is only used to read metadata. No metadata
        # transaction is modified by this operation.
        with get_metastore_connection() as connection:

            # Create a cursor for executing the metadata query.
            with connection.cursor() as cursor:

                # Parameterized SQL prevents SQL injection and keeps values
                # separate from the SQL statement itself.
                cursor.execute(
                    query,
                    (
                        dataset_id,
                        tenant_id,
                        tenant_id,
                        environment_id,
                    ),
                )

                # Fetch the single active physical binding.
                row = cursor.fetchone()

        # If no row was found, the logical dataset cannot currently be
        # resolved to a physical object in this environment.
        if row is None:
            raise LookupError(
                "No active dataset binding found for "
                f"dataset_id={dataset_id}, "
                f"tenant_id={tenant_id}, "
                f"environment_id={environment_id}."
            )

        # Convert the database row into the strongly typed runtime object.
        return RuntimeObject(
            dataset_id=row[0],
            dataset_binding_id=row[1],
            connection_id=row[2],
            dataset_code=row[3],
            catalog_name=row[4],
            schema_name=row[5],
            object_name=row[6],
            object_name_normalized=row[7],
        )