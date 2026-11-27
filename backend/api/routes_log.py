"""
Defect Log API Routes

Handles retrieval and export of defect logs from the database.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import tempfile
from pathlib import Path
from typing import Optional

from db import get_log_store

router = APIRouter(prefix="/log", tags=["log"])


@router.get("/")
async def get_log(
    limit: Optional[int] = None,
    session_id: Optional[str] = None,
    defect_type: Optional[str] = None
):
    """
    Retrieve defect logs from the database.
    
    Parameters:
    - limit: Optional limit on number of results
    - session_id: Optional filter by session ID
    - defect_type: Optional filter by defect type
    
    Returns:
    JSON with list of defects
    """
    
    try:
        log_store = await get_log_store()
        
        if session_id:
            defects = await log_store.get_defects_by_session(session_id)
        elif defect_type:
            defects = await log_store.get_defects_by_type(defect_type)
        else:
            defects = await log_store.get_all_defects(limit=limit)
        
        return JSONResponse({
            "success": True,
            "count": len(defects),
            "defects": defects
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving log: {str(e)}")


@router.get("/statistics")
async def get_statistics():
    """
    Get summary statistics about logged defects.
    
    Returns:
    JSON with:
    - total_defects: Total count
    - by_type: Count by defect type
    - avg_confidence: Average confidence score
    """
    
    try:
        log_store = await get_log_store()
        stats = await log_store.get_statistics()
        
        return JSONResponse({
            "success": True,
            "statistics": stats
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving statistics: {str(e)}")


@router.get("/export")
async def export_log():
    """
    Export all defect logs to a CSV file.
    
    Returns:
    CSV file download
    """
    
    try:
        log_store = await get_log_store()
        
        # Create temporary file for export
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as tmp:
            tmp_path = Path(tmp.name)
        
        # Export to CSV
        count = await log_store.export_to_csv(tmp_path)
        
        if count == 0:
            tmp_path.unlink()
            raise HTTPException(status_code=404, detail="No defects to export")
        
        # Return file
        return FileResponse(
            path=str(tmp_path),
            media_type='text/csv',
            filename='defect_log.csv',
            background=None  # File will be deleted after response
        )
    
    except HTTPException:
        raise
    except Exception as e:
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink()
        raise HTTPException(status_code=500, detail=f"Error exporting log: {str(e)}")


@router.delete("/")
async def clear_log():
    """
    Clear all defect logs (use with caution).
    
    Returns:
    Success confirmation
    """
    
    try:
        log_store = await get_log_store()
        await log_store.clear_all()
        
        return JSONResponse({
            "success": True,
            "message": "All logs cleared"
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing log: {str(e)}")
