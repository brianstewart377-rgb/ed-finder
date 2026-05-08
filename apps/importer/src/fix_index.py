#!/usr/bin/env python3
import os
import psycopg2
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('fix_index')

# Database connection
_raw_url = os.getenv('DATABASE_URL', 'postgresql://edfinder:edfinder@postgres:5432/edfinder')

def fix_index():
    log.info("Starting automated index fix...")
    
    try:
        # Connect to the database
        conn = psycopg2.connect(_raw_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if index exists
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE tablename = 'systems' AND indexname = 'idx_sys_grid_null'
        """)
        if cur.fetchone()[0] > 0:
            log.info("Index 'idx_sys_grid_null' already exists. Nothing to do.")
            return True

        # Create the index
        log.info("Creating index 'idx_sys_grid_null' CONCURRENTLY...")
        log.info("This may take a few minutes depending on table size, but it won't block the database.")
        
        # Note: CONCURRENTLY cannot be run inside a transaction block in some drivers, 
        # but with autocommit=True it should work.
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sys_grid_null 
            ON systems(id64) 
            WHERE grid_cell_id IS NULL
        """)
        
        log.info("✓ Index created successfully!")
        return True
        
    except Exception as e:
        log.error(f"Failed to create index: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    if fix_index():
        sys.exit(0)
    else:
        sys.exit(1)
