from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.incremental.executor import IncrementalExecutor
from app.incremental.schema import SchemaValidationError


app = FastAPI(title="Metadata-Driven Ingestion API")


class IncrementalRunRequest(BaseModel):
    tenant_id: int = Field(gt=0)
    system_id: int = Field(gt=0)
    environment_id: int = Field(gt=0)
    connection_id: int = Field(gt=0)
    load_type: str = "INCREMENTAL"
    load_strategy: str = "APPEND"


@app.post("/ingestions/incremental/run")
def run_incremental_load(request: IncrementalRunRequest) -> dict[str, object]:
    try:
        result = IncrementalExecutor().execute(
            tenant_id=request.tenant_id,
            system_id=request.system_id,
            environment_id=request.environment_id,
            source_connection_id=request.connection_id,
            load_type=request.load_type,
            load_strategy=request.load_strategy,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, SchemaValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return {
        "execution_id": result.execution_id,
        "status": result.status,
        "tables_processed": result.tables_processed,
        "rows_read": result.rows_read,
        "rows_inserted": result.rows_inserted,
        "rows_skipped": result.rows_skipped,
        "execution_watermark": result.execution_watermark.isoformat(),
        "watermark_updated": result.watermark_updated,
    }