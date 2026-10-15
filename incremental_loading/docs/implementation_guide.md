# Incremental Loading Guide

## Purpose

This guide explains how the project discovers source tables, maps source
columns to target columns, identifies inserted or updated rows, and appends
those rows without replacing earlier target records.

There are two related implementations in this repository:

1. **Multi-table demo:** discovers every base table in source `public`, maps
   same-named columns to a same-named target table, and uses the target's
   maximum watermark as its checkpoint.
2. **Metadata-driven engine:** reads registered datasets, table bindings,
   column mappings, load settings, and watermark state from the metastore.

They share connector and executor components, but they do not currently share
the same metadata registration or checkpoint workflow. Keep that distinction
in mind when selecting a command or extending the platform.

## Run the Multi-Table Demo

From the innermost project directory in PowerShell:

```powershell
..\.venv\Scripts\python.exe -m scripts.incremental_load.incremental_loading_multiple_tables
```

The runner uses source connection `18`, source schema `public`, target
connection `11`, and target database `demo_target_db`. It discovers all base
tables in the source schema. For each table, it creates or updates the
same-named target table, maps columns with identical names, performs the
incremental append, and prints the mapping, row counts, and target contents.

The target connection supplies the host and credentials. The runner overrides
its database name with `demo_target_db`; credentials are not stored in this
script.

## Example Tables and Column Mapping

The source database was inspected during development and contained these
`public` tables and columns:

| Source table | Source columns |
| --- | --- |
| `customer` | `customerid`, `firstname`, `lastname`, `email`, `phone`, `departmentid`, `last_modified_at` |
| `department` | `departmentid`, `departmentname`, `location`, `last_modified_at` |

For the demo, a source column maps to a target column when their names match.
For example:

| Source | Target |
| --- | --- |
| `public.customer.customerid` | `public.customer.customerid` |
| `public.customer.firstname` | `public.customer.firstname` |
| `public.customer.last_modified_at` | `public.customer.last_modified_at` |
| `public.department.departmentid` | `public.department.departmentid` |
| `public.department.departmentname` | `public.department.departmentname` |
| `public.department.last_modified_at` | `public.department.last_modified_at` |

The runner gets these names from PostgreSQL column discovery; they are not
hard-coded into a per-table mapping list. It excludes the target-only generated
version key (`_mdip_append_version_id`) from the source mapping. A source table
must have a `last_modified_at` column (the demo installs it if missing), and
the target needs a matching watermark column.

This automatic mapping supports **same-name fields**. If a source field named
`customer_name` must map to a target field named `full_name`, use the
metadata-driven mapping model described below or add an explicit mapping rule;
the demo will not infer that rename.

## How the Demo Finds and Loads Tables

The multi-table runner in
[`incremental_loading_multiple_tables.py`](../scripts/incremental_load/incremental_loading_multiple_tables.py)
uses these steps:

1. `RuntimeConnectionResolver.resolve()` resolves each connection ID through
   the metastore, connection service, connector factory, and connector
   registry.
2. `source_connector.list_tables("public")` discovers PostgreSQL base tables.
   Views are not included by this discovery method.
3. For each table, `list_columns()` reads its column names and data types.
4. `ensure_source_watermark_trigger()` creates the watermark column if needed
   and installs a trigger that sets `last_modified_at` on source INSERT and
   UPDATE operations.
5. `ensure_target_table()` creates a missing target table, adds missing source
   columns, and prepares a generated version key so repeated business keys
   can be retained as history.
6. `get_shared_column_mapping()` selects source/target columns with identical
   names and verifies that the watermark is mapped.
7. `IncrementalAppendExecutor.execute()` reads source rows newer than the
   target's current maximum watermark and writes each batch in a target
   transaction.
8. The runner prints per-table counts and the resulting target rows, then
   summarizes counts across tables.

The PostgreSQL type map in the runner defines which source column types can be
used when creating target tables. If discovery returns an unsupported type,
add a deliberate PostgreSQL type mapping before running the load.

## How Inserts and Updates Are Identified

The demo uses a timestamp watermark. The source trigger updates
`last_modified_at` when a source row is inserted or updated. The executor
checks the target checkpoint and builds a query equivalent to:

```sql
SELECT <mapped columns>
FROM public.<table>
WHERE last_modified_at > <target maximum watermark>
ORDER BY last_modified_at;
```

On the first run, an empty target has no checkpoint, so all source rows are
eligible. On later runs, rows whose watermark is newer than the target maximum
are eligible. Both a new row and an updated row are copied as a new target row;
the old target version is not updated or deleted.

This is **watermark-based change detection**, not a comparison of every source
row with its target copy. It depends on the source watermark being advanced
whenever relevant data changes. Deletes are not detected by this demo. The
demo's target-maximum checkpoint is also separate from the metastore's
`ingest.watermark_state` table.

## Metadata-Driven Mapping Model

The platform engine does not discover target mappings by matching names. It
resolves the metadata registered for a mapping version:

| Metadata object | What it identifies |
| --- | --- |
| `catalog.dataset` | Logical source or target dataset |
| `catalog.dataset_binding` | Physical connection, database/catalog, schema, and table for an environment |
| `catalog.dataset_schema_version` | A captured version of a dataset's schema |
| `catalog.dataset_field` | A column name, type, ordinal, and schema-version relationship |
| `map.mapping` | The named source-to-target mapping |
| `map.mapping_version` | The version, source dataset, target dataset, load type, and load strategy |
| `map.mapping_source` | A source dataset and alias used by a mapping version |
| `map.mapping_field` | A target field and its mapping behavior (for example, `DIRECT`) |
| `map.mapping_field_input` | The source field that supplies a mapped target field |
| `ingest.incremental_config` | The watermark field ID and incremental boundaries/policies |
| `ingest.load_config` | Incremental load type, batch size, and active status |
| `ingest.incremental_runtime_config` | Runtime schema and duplicate handling policies |
| `ingest.watermark_state` | The current checkpoint for a mapping version |
| `ingest.watermark_history` | Previously committed watermark transitions |

For a direct mapping, `map.mapping_field.target_field_id` identifies the target
column. `map.mapping_field_input.source_field_id` identifies the source column
that supplies its value. Both IDs refer to `catalog.dataset_field`; the
`ordinal_no` fields define a stable processing/display order. The
`RuntimeFieldMappingResolver` joins these tables and returns ordered runtime
field mappings.

The repository resolves active/published mapping versions by joining their
source and target dataset bindings with incremental and load configuration.
The table plan includes the resolved physical tables, watermark field, prior
watermark, batch size, schema policy, and duplicate policy. This is how the
metadata-driven engine identifies **which tables** to load and **which columns**
to map.

## Metadata-Driven Execution Flow

The API endpoint is `POST /ingestions/incremental/run`. It accepts tenant,
system, environment, source connection, load type, and load strategy. The
engine then:

1. Validates the request and source connection profile.
2. Resolves eligible mapping versions and their source/target table bindings.
3. Discovers source and target columns and validates types, nullability,
   watermark presence, and (depending on duplicate policy) primary keys.
4. Reads the prior watermark from `ingest.watermark_state`, or uses the
   configured initial watermark.
5. Captures an execution upper boundary and reads rows in the interval
   `previous watermark < row watermark <= execution watermark`.
6. Reads in batches and writes each batch using the configured duplicate
   strategy.
7. Commits target data, records execution metrics, then persists the new
   watermark in `ingest.watermark_state` and appends a transition to
   `ingest.watermark_history`.

The API response reports execution ID, status, tables processed, rows read,
rows inserted, rows skipped, execution watermark, and whether the watermark
was updated.

## Connecting Another Database Vendor

Connection selection is designed to be metadata-driven:

1. Register the connection profile with connector code, host, port, database,
   role, and credential reference in the metastore.
2. Implement a connector adapter that satisfies `BaseConnector`: connection
   lifecycle, schema/table discovery, batched reads, and batch writes.
3. Register the adapter in `create_connector_registry()` using the exact
   connector code stored in metadata.
4. Add and test that database's type discovery, quoting, parameter, transaction,
   and write behavior. Review target DDL/type mapping separately.
5. Create dataset bindings and mapping metadata for the source and target, then
   configure the watermark field, load settings, runtime settings, and initial
   watermark.

The resolver/factory avoids putting `if PostgreSQL`/`if MySQL` branches in the
incremental engine. **PostgreSQL is the connector currently registered by this
repository.** Supporting a server in the design is not the same as shipping a
working adapter for it. Also, the current incremental executor validates some
specific source-profile values; those checks must be made configurable before
it can run unchanged against arbitrary connection profiles.

## Important Project-Specific Notes

- The live metastore inspected for this guide has `ingest.watermark_state`,
  `ingest.watermark_history`, and `ingest.incremental_config`. There is no
  table named `ingest.watermark_id`.
- The demo's current datasets bind source connection 18 to `source.public.customer`
  and an existing target dataset to `ingestion_metastore.warehouse.customer_incremental_target`.
  They do **not** represent the demo target `demo_target_db.public.customer`.
  Do not reuse those dataset/mapping IDs for the separate demo target.
- The live metastore inspected did not have
  `ingest.incremental_runtime_config` or `ingest.incremental_field_metadata`,
  although the repository code and
  [`001_incremental_api_metadata.sql`](../scripts/incremental_load/sql/001_incremental_api_metadata.sql)
  expect these metadata structures. Apply and validate the appropriate
  migrations before using the metadata-driven engine in that database.
- The multi-table demo currently keeps its checkpoint in each target table's
  `MAX(last_modified_at)`; it does not create catalog mapping records or write
  `ingest.watermark_state` entries. Use the metadata-driven engine only after
  registering dedicated dataset bindings and an active incremental mapping
  for the intended physical source and target tables.
- Both paths require source and target tables to agree on the mapped columns
  and watermark data type. The demo supports same-name columns only; the
  metadata-driven engine supports explicit field-to-field mappings.

## Main Code Locations

- [Multi-table demo runner](../scripts/incremental_load/incremental_loading_multiple_tables.py)
- [Metadata-driven incremental executor](../app/incremental/executor.py)
- [Incremental table-plan and checkpoint repository](../app/incremental/repository.py)
- [Schema discovery, validation, and query builder](../app/incremental/schema.py)
- [Field mapping resolver](../app/runtime/field_mapping_resolver.py)
- [Connection resolver](../app/runtime/connection_resolver.py)
- [Connector registration](../app/connectors/register_connectors.py)
- [Incremental API](../app/api.py)