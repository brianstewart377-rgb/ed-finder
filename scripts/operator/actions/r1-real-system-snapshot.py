#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; API_SRC=ROOT/'apps'/'api'/'src'; sys.path.insert(0,str(API_SRC))
import psycopg2
import psycopg2.extras
from r1_real_snapshot import SnapshotSelector,build_report,load_snapshots,read_db_identity

def main():
    ap=argparse.ArgumentParser(description='Bounded read-only R1 canonical system snapshot')
    ap.add_argument('selectors',nargs='+',help='Exact system names or id64 values; prefix id64 with id: to force')
    args=ap.parse_args()
    if len(args.selectors)>20: raise SystemExit('STOP: maximum 20 selectors')
    selectors=[]
    for raw in args.selectors:
        if raw.startswith('id:'): selectors.append(SnapshotSelector('id64',raw[3:]))
        elif raw.isdigit(): selectors.append(SnapshotSelector('id64',raw))
        else: selectors.append(SnapshotSelector('name',raw))
    dsn=os.environ.get('R1_READONLY_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not dsn: raise SystemExit('STOP: R1_READONLY_DATABASE_URL or DATABASE_URL is required')
    conn=psycopg2.connect(dsn,cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conn.set_session(readonly=True,autocommit=True)
        ident=read_db_identity(conn); bundles=load_snapshots(conn,selectors)
        payload={'db_identity':ident,'transaction_read_only':'on','snapshots':[asdict(build_report(b)) for b in bundles],'safety':{'db_access_performed':True,'db_read_only_confirmed':True,'db_writes_performed':False,'migrations_performed':False}}
        print(json.dumps(payload,sort_keys=True,separators=(',',':')))
    finally: conn.close()
if __name__=='__main__': main()
