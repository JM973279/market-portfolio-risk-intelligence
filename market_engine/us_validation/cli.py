"""Private research CLI. Has no export, publish, force or retrain command."""
import argparse
import json
import os
from pathlib import Path
import sys

from .engine import ORIGINAL, analyze, candidate
from .sources import collect
from .store import DEFAULT_ROOT, EvidenceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',type=Path,default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest='command',required=True)
    collection = commands.add_parser('collect')
    collection.add_argument('--start',default='2000-01-01')
    collection.add_argument('--end',required=True)
    collection.add_argument('--previous')
    collection.add_argument('--fred-vintage')
    for name in ('analyze','candidate'):
        command = commands.add_parser(name)
        command.add_argument('--snapshot' if name=='analyze' else '--analysis',required=True)
        command.add_argument('--original',type=Path,default=ORIGINAL)
        command.add_argument('--python',default=sys.executable)
        if name=='analyze':command.add_argument('--skip-historical-sensitivity',action='store_true')
    args = parser.parse_args()
    store = EvidenceStore(args.store)
    if args.command == 'collect':
        key = collect(store,args.start,args.end,fred_vintage=args.fred_vintage,
                      fred_key=os.getenv('FRED_API_KEY'),previous=args.previous)
        doc = store.load(key,'snapshots')
        result = {'snapshot':key,'collection_complete':doc['collection_complete'],'public_approved':False}
    elif args.command == 'analyze':
        key,doc,_ = analyze(store,args.snapshot,original=args.original,python=args.python,
                            sensitivity=not args.skip_historical_sensitivity)
        result = {'analysis':key,'stages':doc['stages'],'public_approved':False}
    else:
        key = candidate(store,args.analysis,original=args.original,python=args.python)
        result = {'candidate':key,'public_approved':False}
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
