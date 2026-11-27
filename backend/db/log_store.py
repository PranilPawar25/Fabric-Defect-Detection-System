"""
Defect Log Storage - SQLite Database Module

This module handles persistent storage of detected defects in a SQLite database.
Logs include timestamp, defect type, position, confidence, and fabric length.
"""

import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import sys

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH


class DefectLogStore:
    """
    Async SQLite-based storage for defect detection logs.
    """
    
    def __init__(self, db_path: Path = DB_PATH):
        """
        Initialize the log store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
    
    async def initialize(self):
        """
        Create database tables if they don't exist, and migrate schema if needed.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Define expected schema
            expected_columns = {
                'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
                'timestamp': 'TEXT NOT NULL',
                'session_id': 'TEXT',
                'defect_type': 'TEXT NOT NULL',
                'x': 'INTEGER NOT NULL',
                'y': 'INTEGER NOT NULL',
                'w': 'INTEGER NOT NULL',
                'h': 'INTEGER NOT NULL',
                'confidence': 'REAL NOT NULL',
                'fabric_length_m': 'REAL',
                'elapsed_time_s': 'REAL',
                'frame_number': 'INTEGER',
                'timestamp_seconds': 'REAL',
                'timestamp_display': 'TEXT',
                'source_type': 'TEXT',
                'detection_mode': 'TEXT',
                'feed_speed': 'REAL',
                'metadata': 'TEXT'
            }
            
            # Check if table exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='defects'"
            )
            table_exists = await cursor.fetchone() is not None
            
            if table_exists:
                # Table exists - check for schema drift and migrate
                cursor = await db.execute("PRAGMA table_info(defects)")
                existing_columns = {row[1]: row[2] for row in await cursor.fetchall()}
                
                # Find missing columns
                missing_columns = set(expected_columns.keys()) - set(existing_columns.keys())
                
                if missing_columns:
                    print(f"🔄 Database migration: Adding {len(missing_columns)} missing column(s) to 'defects' table")
                    for col_name in sorted(missing_columns):
                        col_type = expected_columns[col_name]
                        # Remove constraints that aren't allowed in ALTER TABLE
                        col_type_clean = col_type.replace(' NOT NULL', '').replace(' PRIMARY KEY AUTOINCREMENT', '')
                        try:
                            await db.execute(f"ALTER TABLE defects ADD COLUMN {col_name} {col_type_clean}")
                            print(f"  ✅ Added column: {col_name} ({col_type_clean})")
                        except Exception as e:
                            print(f"  ⚠️  Could not add column {col_name}: {e}")
                    
                    await db.commit()
                    print("✅ Database migration complete")
                else:
                    print("✅ Database schema is up to date")
            else:
                # Table doesn't exist - create fresh with full schema
                print("📦 Creating 'defects' table with full schema")
                await db.execute("""
                    CREATE TABLE defects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        session_id TEXT,
                        defect_type TEXT NOT NULL,
                        x INTEGER NOT NULL,
                        y INTEGER NOT NULL,
                        w INTEGER NOT NULL,
                        h INTEGER NOT NULL,
                        confidence REAL NOT NULL,
                        fabric_length_m REAL,
                        elapsed_time_s REAL,
                        frame_number INTEGER,
                        timestamp_seconds REAL,
                        timestamp_display TEXT,
                        source_type TEXT,
                        detection_mode TEXT,
                        feed_speed REAL,
                        metadata TEXT
                    )
                """)
                print("✅ Table created successfully")
            
            # Create indexes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON defects(timestamp)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_session 
                ON defects(session_id)
            """)
            
            await db.commit()
    
    async def log_defect(self, defect: Dict, session_id: Optional[str] = None) -> int:
        """
        Log a single defect to the database.
        
        Args:
            defect: Defect dictionary with keys:
                - type: Defect type
                - x, y, w, h: Bounding box
                - confidence: Confidence score
                - fabric_length_m: Optional fabric length
                - elapsed_time_s: Optional elapsed time
                - frame_number: Optional frame number
                - mode: Detection mode
                - feed_speed: Optional feed speed
            session_id: Optional session identifier for grouping
            
        Returns:
            ID of inserted row
        """
        timestamp = datetime.utcnow().isoformat()
        
        # Extract defect type (handle both 'type' and 'defect_type' keys)
        defect_type = defect.get('defect_type') or defect.get('type', 'unknown')
        
        # Extract metadata (any extra fields)
        metadata_fields = {}
        for key, value in defect.items():
            if key not in ['type', 'defect_type', 'x', 'y', 'w', 'h', 'confidence', 
                          'fabric_length_m', 'elapsed_time_s', 'frame_number',
                          'timestamp_seconds', 'timestamp_display', 'source_type',
                          'mode', 'feed_speed', 'session_id']:
                metadata_fields[key] = value
        
        metadata_json = json.dumps(metadata_fields) if metadata_fields else None
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO defects (
                    timestamp, session_id, defect_type,
                    x, y, w, h, confidence,
                    fabric_length_m, elapsed_time_s, frame_number,
                    timestamp_seconds, timestamp_display, source_type,
                    detection_mode, feed_speed, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                session_id,
                defect_type,
                defect['x'],
                defect['y'],
                defect['w'],
                defect['h'],
                defect['confidence'],
                defect.get('fabric_length_m'),
                defect.get('elapsed_time_s'),
                defect.get('frame_number'),
                defect.get('timestamp_seconds'),
                defect.get('timestamp_display'),
                defect.get('source_type'),
                defect.get('mode'),
                defect.get('feed_speed'),
                metadata_json
            ))
            
            await db.commit()
            return cursor.lastrowid
    
    async def log_defects_batch(self, defects: List[Dict], 
                               session_id: Optional[str] = None) -> List[int]:
        """
        Log multiple defects in a batch.
        
        Args:
            defects: List of defect dictionaries
            session_id: Optional session identifier
            
        Returns:
            List of inserted row IDs
        """
        ids = []
        for defect in defects:
            row_id = await self.log_defect(defect, session_id)
            ids.append(row_id)
        return ids
    
    async def get_all_defects(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Retrieve all defects from the database.
        
        Args:
            limit: Optional limit on number of results
            
        Returns:
            List of defect dictionaries
        """
        query = "SELECT * FROM defects ORDER BY timestamp DESC"
        if limit:
            query += f" LIMIT {limit}"
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            
            defects = []
            for row in rows:
                defect = dict(row)
                
                # Parse metadata JSON if present
                if defect['metadata']:
                    try:
                        metadata = json.loads(defect['metadata'])
                        defect.update(metadata)
                    except json.JSONDecodeError:
                        pass
                
                del defect['metadata']
                defects.append(defect)
            
            return defects
    
    async def get_defects_by_session(self, session_id: str) -> List[Dict]:
        """
        Retrieve defects for a specific session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of defect dictionaries
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM defects WHERE session_id = ? ORDER BY timestamp DESC",
                (session_id,)
            )
            rows = await cursor.fetchall()
            
            defects = []
            for row in rows:
                defect = dict(row)
                if defect['metadata']:
                    try:
                        metadata = json.loads(defect['metadata'])
                        defect.update(metadata)
                    except json.JSONDecodeError:
                        pass
                del defect['metadata']
                defects.append(defect)
            
            return defects
    
    async def get_defects_by_type(self, defect_type: str) -> List[Dict]:
        """
        Retrieve defects of a specific type.
        
        Args:
            defect_type: Type of defect to filter by
            
        Returns:
            List of defect dictionaries
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM defects WHERE defect_type = ? ORDER BY timestamp DESC",
                (defect_type,)
            )
            rows = await cursor.fetchall()
            
            defects = []
            for row in rows:
                defect = dict(row)
                if defect['metadata']:
                    try:
                        metadata = json.loads(defect['metadata'])
                        defect.update(metadata)
                    except json.JSONDecodeError:
                        pass
                del defect['metadata']
                defects.append(defect)
            
            return defects
    
    async def get_statistics(self) -> Dict:
        """
        Get summary statistics about logged defects.
        
        Returns:
            Dictionary with statistics:
                - total_defects: Total count
                - by_type: Count by defect type
                - avg_confidence: Average confidence score
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Total count
            cursor = await db.execute("SELECT COUNT(*) as count FROM defects")
            row = await cursor.fetchone()
            total = row[0]
            
            # Count by type
            cursor = await db.execute("""
                SELECT defect_type, COUNT(*) as count 
                FROM defects 
                GROUP BY defect_type
            """)
            rows = await cursor.fetchall()
            by_type = {row[0]: row[1] for row in rows}
            
            # Average confidence
            cursor = await db.execute("SELECT AVG(confidence) FROM defects")
            row = await cursor.fetchone()
            avg_confidence = row[0] if row[0] is not None else 0.0
            
            return {
                'total_defects': total,
                'by_type': by_type,
                'avg_confidence': round(avg_confidence, 2)
            }
    
    async def clear_all(self):
        """
        Clear all defect logs (use with caution).
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM defects")
            await db.commit()
    
    async def export_to_csv(self, output_path: Path) -> int:
        """
        Export all defects to a CSV file.
        
        Args:
            output_path: Path to output CSV file
            
        Returns:
            Number of rows exported
        """
        import csv
        
        defects = await self.get_all_defects()
        
        if not defects:
            return 0
        
        # Get all unique keys across all defects
        all_keys = set()
        for defect in defects:
            all_keys.update(defect.keys())
        
        fieldnames = sorted(all_keys)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for defect in defects:
                writer.writerow(defect)
        
        return len(defects)


# Global log store instance
_log_store_instance = None


async def get_log_store() -> DefectLogStore:
    """
    Get or create the global log store instance (singleton pattern).
    
    Returns:
        DefectLogStore instance
    """
    global _log_store_instance
    if _log_store_instance is None:
        _log_store_instance = DefectLogStore()
        await _log_store_instance.initialize()
    return _log_store_instance


if __name__ == "__main__":
    import asyncio
    
    async def test():
        """Test the log store."""
        print("Testing DefectLogStore...")
        
        # Create temporary test database
        test_db_path = Path("test_defects.db")
        if test_db_path.exists():
            test_db_path.unlink()
        
        store = DefectLogStore(test_db_path)
        await store.initialize()
        
        print("Database initialized")
        
        # Test logging
        test_defects = [
            {
                'type': 'hole',
                'x': 100, 'y': 100, 'w': 64, 'h': 64,
                'confidence': 85.5,
                'fabric_length_m': 1.5,
                'mode': 'autoencoder'
            },
            {
                'type': 'stain',
                'x': 200, 'y': 200, 'w': 128, 'h': 128,
                'confidence': 92.3,
                'fabric_length_m': 3.2,
                'mode': 'autoencoder'
            }
        ]
        
        ids = await store.log_defects_batch(test_defects, session_id="test-session")
        print(f"Logged {len(ids)} defects with IDs: {ids}")
        
        # Test retrieval
        all_defects = await store.get_all_defects()
        print(f"Retrieved {len(all_defects)} defects")
        
        # Test statistics
        stats = await store.get_statistics()
        print(f"Statistics: {stats}")
        
        # Test export
        csv_path = Path("test_export.csv")
        count = await store.export_to_csv(csv_path)
        print(f"Exported {count} rows to {csv_path}")
        
        # Cleanup
        test_db_path.unlink()
        csv_path.unlink()
        
        print("Test complete!")
    
    asyncio.run(test())
