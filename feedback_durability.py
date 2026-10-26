"""AI Stock Hunter feedback durability: additive SQLite restore and merge.

No Streamlit dependency; merge does not delete existing records. Designed for
partial legacy backups and concurrent application restarts.
"""
from __future__ import annotations
import os
import sqlite3
import tempfile
from pathlib import Path


def _tables(con):
    return {r[0]:r[1] for r in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if r[1]}


def _columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def _insert_rows(dest, table, columns, rows, ignore=True):
    if not columns or not rows:return 0
    names=','.join('"'+c+'"' for c in columns)
    marks=','.join('?' for _ in columns)
    command='INSERT OR IGNORE' if ignore else 'INSERT'
    sql=f'{command} INTO "{table}" ({names}) VALUES ({marks})'
    count=0
    for row in rows:
        cur=dest.execute(sql,tuple(row))
        count+=max(0,cur.rowcount)
    return count


def db_stats(path):
    con=sqlite3.connect(str(path),timeout=10)
    try:
        tables=_tables(con)
        def n(t):return int(con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]) if t in tables else 0
        return {'snapshots':n('snapshots'),'outcomes':n('outcomes'),
                'reliability_signals':n('reliability_signals'),
                'reliability_outcomes':n('reliability_outcomes'),
                'scanner_history':n('scanner_history')}
    finally:con.close()


def merge_database_bytes(destination, backup_bytes):
    """Idempotent union of supported database tables, preserving parent IDs.

    Existing destination rows always win. All import mutations are atomic.
    Unknown tables are carried over where schemas allow it. No table is erased.
    """
    if not backup_bytes or len(backup_bytes)<100:return False,'Backup is empty.',{}
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.feedback-merge-',suffix='.sqlite3',dir=str(destination.parent))
    try:
        with os.fdopen(fd,'wb') as f:f.write(bytes(backup_bytes));f.flush();os.fsync(f.fileno())
        source=sqlite3.connect(f'file:{tmp}?mode=ro',uri=True,timeout=20)
        try:
            if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                return False,'Invalid SQLite backup: integrity check failed.',{}
            source_tables=_tables(source)
            if 'snapshots' not in source_tables or 'outcomes' not in source_tables:
                return False,'This file is not a compatible Feedback database.',{}
            target=sqlite3.connect(str(destination),timeout=60)
            try:
                target.execute('PRAGMA busy_timeout=60000')
                target.execute('BEGIN IMMEDIATE')
                # The empty DB case: build the schema from the backup before merging.
                target_tables=_tables(target)
                for name,ddl in source_tables.items():
                    if name not in target_tables and name not in ('sqlite_sequence',):
                        target.execute(ddl)
                target_tables=_tables(target)
                changes={}
                snap_map={}
                newly_added_snap_ids=set()
                if 'snapshots' in source_tables:
                    s_cols=_columns(source,'snapshots');d_cols=_columns(target,'snapshots')
                    if not {'id','scan_id','ticker'}.issubset(s_cols) or not {'id','scan_id','ticker'}.issubset(d_cols):
                        raise ValueError('Snapshot identity columns missing')
                    select_cols=[c for c in s_cols if c in d_cols and c!='id']
                    if select_cols:
                        source_rows=source.execute('SELECT '+','.join('"'+c+'"' for c in ['id']+select_cols)+' FROM snapshots')
                        count=0
                        for row in source_rows:
                            old_id=int(row[0]); values=tuple(row[1:]); record=dict(zip(select_cols,values))
                            cur=target.execute('INSERT OR IGNORE INTO snapshots('+','.join('"'+c+'"' for c in select_cols)+') VALUES ('+','.join('?' for _ in select_cols)+')',values)
                            count+=max(0,cur.rowcount)
                            if cur.rowcount>0:newly_added_snap_ids.add(int(cur.lastrowid))
                            match=target.execute('SELECT id FROM snapshots WHERE scan_id=? AND ticker=?',(record['scan_id'],record['ticker'])).fetchone()
                            if not match:raise ValueError('Could not map imported snapshot')
                            snap_map[old_id]=int(match[0])
                        changes['snapshots']=count
                # Relink source origins if old IDs changed after union.
                if 'event_origin_snapshot_id' in _columns(target,'snapshots') and 'event_origin_snapshot_id' in _columns(source,'snapshots'):
                    for old_id,old_origin in source.execute('SELECT id,event_origin_snapshot_id FROM snapshots WHERE event_origin_snapshot_id IS NOT NULL'):
                        new_id=snap_map.get(int(old_id));new_origin=snap_map.get(int(old_origin))
                        if new_id and new_id in newly_added_snap_ids and not new_origin:
                            target.execute("UPDATE snapshots SET event_origin_snapshot_id=NULL WHERE id=?",(new_id,))
                        if new_id and new_origin and new_id in newly_added_snap_ids:
                            target.execute('UPDATE snapshots SET event_origin_snapshot_id=? WHERE id=? AND (event_origin_snapshot_id IS NULL OR event_origin_snapshot_id=?)',(new_origin,new_id,old_origin))
                if 'outcomes' in source_tables:
                    cols=[c for c in _columns(source,'outcomes') if c in _columns(target,'outcomes')]
                    if 'snapshot_id' in cols:
                        count=0
                        for old_row in source.execute('SELECT '+','.join('"'+c+'"' for c in cols)+' FROM outcomes'):
                            d=dict(zip(cols,old_row));new_id=snap_map.get(int(d['snapshot_id']))
                            if new_id is None:continue
                            d['snapshot_id']=new_id
                            count+=_insert_rows(target,'outcomes',cols,[tuple(d[c] for c in cols)])
                        changes['outcomes']=count
                signal_map={}
                if 'reliability_signals' in source_tables and 'reliability_signals' in target_tables:
                    cols=[c for c in _columns(source,'reliability_signals') if c in _columns(target,'reliability_signals') and c!='id']
                    if {'event_id','policy_version','snapshot_id'}.issubset(cols):
                        count=0
                        for old_row in source.execute('SELECT "id",'+','.join('"'+c+'"' for c in cols)+' FROM reliability_signals'):
                            d=dict(zip(cols,old_row[1:]));new_id=snap_map.get(int(d['snapshot_id']))
                            if new_id is None:continue
                            d['snapshot_id']=new_id
                            count+=_insert_rows(target,'reliability_signals',cols,[tuple(d[c] for c in cols)])
                            new_signal=target.execute('SELECT id FROM reliability_signals WHERE event_id=? AND policy_version=?',(d['event_id'],d['policy_version'])).fetchone()
                            if new_signal:signal_map[int(old_row[0])]=int(new_signal[0])
                        changes['reliability_signals']=count
                if 'reliability_outcomes' in source_tables and 'reliability_outcomes' in target_tables:
                    cols=[c for c in _columns(source,'reliability_outcomes') if c in _columns(target,'reliability_outcomes')]
                    if 'signal_id' in cols:
                        count=0
                        for old_row in source.execute('SELECT '+','.join('"'+c+'"' for c in cols)+' FROM reliability_outcomes'):
                            d=dict(zip(cols,old_row));new_id=signal_map.get(int(d['signal_id']))
                            if new_id is None:continue
                            d['signal_id']=new_id
                            count+=_insert_rows(target,'reliability_outcomes',cols,[tuple(d[c] for c in cols)])
                        changes['reliability_outcomes']=count
                skip={'snapshots','outcomes','reliability_signals','reliability_outcomes'}
                for name in source_tables:
                    if name in skip or name not in target_tables:continue
                    cols=[c for c in _columns(source,name) if c in _columns(target,name)]
                    # An autoincrement surrogate ID in replay_events is local only.
                    if name=='replay_events' and 'id' in cols:cols.remove('id')
                    if cols:
                        rows=source.execute('SELECT '+','.join('"'+c+'"' for c in cols)+f' FROM "{name}"')
                        count=0
                        for row in rows:count+=_insert_rows(target,name,cols,[row])
                        changes[name]=count
                target.commit()
                return True,'Backup merged successfully without deleting existing records.',changes
            except Exception:
                target.rollback();raise
            finally:target.close()
        finally:source.close()
    except Exception as e:
        return False,f'Backup merge failed; existing data unchanged: {type(e).__name__}: {e}',{}
    finally:
        try:os.unlink(tmp)
        except OSError:pass
