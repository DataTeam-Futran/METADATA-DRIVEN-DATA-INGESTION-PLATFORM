# Customer and Department Incremental Append

This workflow incrementally appends rows from PostgreSQL connection 18
(database `source`) to isolated target tables through the active target
connection 11 (database `ingestion_metastore`). Physical source and target
objects are resolved from `catalog.dataset_binding` at runtime.

## Setup

From the innermost project directory, run:

```powershell
..\.venv\Scripts\python.exe -m scripts.incremental_load.prepare_customer_department_append
```

The preparation step validates the active profiles, supplies connection 18's
missing `username` parameter from connection 1 only when the host, port, and
credential reference match, adds `last_modified_at` to the source tables with
an insert default and update trigger, creates the isolated target tables, and
registers source/target datasets and bindings. It is safe to rerun.

The runtime derives tenant and environment IDs from the profiles. In the
current database, these IDs are positive; negative sentinel values are not
valid for catalog bindings or runtime resolution.

## Run

```powershell
..\.venv\Scripts\python.exe -m scripts.incremental_load.run_customer_department_append
```

The target's maximum `last_modified_at` is the checkpoint. The first run
loads all source rows. Later runs append only rows whose source watermark is
newer. Target writes are transactional and never truncate the existing
`warehouse.customer_target` table.

The load uses append semantics: an updated source row is appended as another
version rather than updating an existing target row. Run one copy of this
workflow at a time so concurrent executions do not reuse the same watermark.

## Multi-Table Demo Target

To load all base tables from the configured source connection's `public`
schema into same-named tables in `demo_target_db.public`, run:

```powershell
..\.venv\Scripts\python.exe -m scripts.incremental_load.incremental_loading_multiple_tables
```

The demo discovers every base table in source connection 18's `public` schema.
It uses target connection 11 for host and credentials, overrides the target
database to `demo_target_db`, and maps columns with identical names. A missing
target table is created from the supported PostgreSQL source column types.
Before each load, the script installs a trigger that refreshes
`last_modified_at` for source inserts and updates. The source connection needs
permission to alter source tables and create or replace the trigger function.

Each target table receives a generated version key. Existing primary keys are
replaced where needed so repeated business keys can be stored as history.
Existing target rows are preserved; changed source rows are appended as new
versions, not updated in place. The report shows mapping and row counts for
each table, aggregate counts, and the target table contents. Unsupported source
PostgreSQL types or other per-table failures are reported, and the run
continues with the remaining tables before returning a failure status.

## Select Specific Source Tables

To list the source tables without loading data:

```powershell
..\.venv\Scripts\python.exe -m incremental_loading.scripts.incremental_loading_selected_tables --list-tables
```

To select tables interactively, run the command without options. Enter one or
more displayed table numbers separated by commas:

```powershell
..\.venv\Scripts\python.exe -m incremental_loading.scripts.incremental_loading_selected_tables
```

You can also specify exact table names on the command line:

```powershell
..\.venv\Scripts\python.exe -m incremental_loading.scripts.incremental_loading_selected_tables --tables customer department
```

Only the selected source tables are passed to the incremental append workflow.
The same watermark, target-table setup, and append behavior as the multi-table
demo is used for each selected table.