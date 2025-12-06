#!/usr/bin/env python3
"""
Migration script: Old chora.db -> New chora-new.db
Transmutes the geological layers into clean Tensegrity Physics.
"""
import sqlite3
import json
import os
import re
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from chora_store.repository import Repository
from chora_store.models import Entity

# Mappings (Cruft -> Eidos)
TYPE_MAP = {
    'feature': 'story',
    'pattern': 'principle',
    'task': 'focus',
    'inquiry': 'inquiry',
    'learning': 'learning',
    'tool': 'tool',
    'release': 'story',
    'relationship': 'relationship',
    'behavior': 'behavior',
    'story': 'story',
    'principle': 'principle',
    'focus': 'focus'
}

# Status mappings to v4 defaults
STATUS_MAP = {
    'nascent': 'emerging',
    'converging': 'emerging',
    'stable': 'active',
    'drifting': 'active',
    'proposed': 'proposed',
    'adopted': 'active',
    'deprecated': 'deprecated',
    'active': 'active',
    'completed': 'fulfilled',
    'done': 'fulfilled',
    'open': 'active',
    'resolved': 'fulfilled',
    'reified': 'fulfilled',
    'clear': 'active',
    'emerging': 'emerging',
    'fulfilled': 'fulfilled',
    'captured': 'captured',
    'validated': 'validated',
    'applied': 'applied',
    'experimental': 'experimental',
    'specified': 'specified',
    'verified': 'verified',
    'failing': 'failing',
    'forming': 'forming',
    'stressed': 'stressed',
    'broken': 'broken',
    'untested': 'untested',
    'finalized': 'finalized',
    'unlocked': 'unlocked'
}


def migrate():
    old_db = Path(os.path.expanduser("~/.chora/chora.db"))
    if not old_db.exists():
        print(f"No old database found at {old_db}. Skipping migration.")
        return

    print(f"Migrating from {old_db} to Tensegrity Universe...")

    # Init new repo
    repo = Repository("~/.chora/chora-new.db")

    conn = sqlite3.connect(old_db)
    conn.row_factory = sqlite3.Row

    count = 0
    skipped = 0

    try:
        # Check if entities table exists
        try:
            conn.execute("SELECT 1 FROM entities LIMIT 1")
        except sqlite3.OperationalError:
            print("Old database has no entities table. Skipping.")
            return

        rows = conn.execute("SELECT * FROM entities").fetchall()
        for row in rows:
            old_type = row['type']
            if old_type not in TYPE_MAP:
                skipped += 1
                continue

            new_type = TYPE_MAP[old_type]
            try:
                old_data = json.loads(row['data'])
            except:
                old_data = {}

            # Map ID
            old_id = row['id']
            slug = old_id.split('-', 1)[1] if '-' in old_id else old_id
            # Clean slug
            slug = re.sub(r'[^a-z0-9-]', '', slug.lower())
            slug = slug[:50]  # Max 50 chars
            new_id = f"{new_type}-{slug}"

            # Map Status
            old_status = row['status']
            new_status = STATUS_MAP.get(old_status, 'active')

            # Map Data Fields
            new_data = old_data.copy()
            new_data['original_id'] = old_id

            # Special handling for Relationships
            if new_type == 'relationship':
                if 'from_entity' in new_data:
                    fid = new_data.pop('from_entity')
                    ftype = fid.split('-')[0] if '-' in fid else 'unknown'
                    fslug = fid.split('-', 1)[1] if '-' in fid else fid
                    fslug = re.sub(r'[^a-z0-9-]', '', fslug.lower())[:50]
                    if ftype in TYPE_MAP:
                        new_data['from_id'] = f"{TYPE_MAP[ftype]}-{fslug}"
                    else:
                        new_data['from_id'] = fid

                if 'to_entity' in new_data:
                    tid = new_data.pop('to_entity')
                    if tid:
                        ttype = tid.split('-')[0] if '-' in tid else 'unknown'
                        tslug = tid.split('-', 1)[1] if '-' in tid else tid
                        tslug = re.sub(r'[^a-z0-9-]', '', tslug.lower())[:50]
                        if ttype in TYPE_MAP:
                            new_data['to_id'] = f"{TYPE_MAP[ttype]}-{tslug}"
                        else:
                            new_data['to_id'] = tid

                if 'relationship_type' not in new_data:
                    new_data['relationship_type'] = 'relates-to'

            # Construct Entity
            title = new_data.get('name', new_data.get('title', slug))
            if not title:
                title = slug

            try:
                entity = Entity(
                    id=new_id,
                    type=new_type,
                    status=new_status,
                    title=title,
                    data=new_data
                )
                repo.save(entity)
                count += 1
            except Exception as e:
                print(f"Failed to migrate {old_id}: {e}")
                skipped += 1

    finally:
        conn.close()

    print(f"Migration complete. {count} entities transmuted. {skipped} skipped.")


if __name__ == "__main__":
    migrate()
