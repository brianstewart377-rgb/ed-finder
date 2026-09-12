"""Execute the real pinned old builder only against a disposable local database."""
import json
import os
from pathlib import Path
import re
import sys


def main():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    request = json.load(sys.stdin)
    settings = conninfo_to_dict(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'])
    if (settings.get('host') not in {'127.0.0.1', 'localhost'} or
            settings.get('dbname') != 'ratings_v4_validation' or
            not re.fullmatch(r'v4_test_[0-9a-f]{32}', request['database'])):
        raise ValueError('legacy fixture requires a disposable local database')
    sys.path.insert(0, request['legacy_root'])
    from scripts.ratings_v4.run_generation import build_generation
    from scripts.ratings_v4.production_generation import code_identity

    if code_identity() != request['expected_identity']:
        raise ValueError('legacy fixture source identity differs from production')

    class Interrupted(Exception):
        pass

    def progress(item):
        if (request['stop_after'] and item['written'] and
                item['chunk_ordinal'] + 1 >= request['stop_after']):
            raise Interrupted

    with psycopg.connect(make_conninfo(**{**settings, 'dbname': request['database']}), autocommit=True) as connection:
        try:
            receipt = build_generation(connection, connection, Path(request['source']),
                                       request['key'], chunk_size=3, workers=2, progress=progress)
        except Interrupted:
            receipt = {'status': 'INTERRUPTED'}
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
