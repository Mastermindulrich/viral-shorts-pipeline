"""One local scheduled tick. Publishing requires --publish and approved exports."""
import argparse
import sys
import pipeline as p
parser = argparse.ArgumentParser()
parser.add_argument('--publish', action='store_true')
args = parser.parse_args()
failures = []
with p.lock():
    try:
        p.discover()
    except Exception as exc:
        failures.append(str(exc))
    for path in sorted((p.DATA/'jobs').glob('*.json')):
        try:
            job = p.read(path)
            p.validate(job)
            dest = p.output(job)
            if not (dest/'job.json').exists():
                p.render(job)
            if args.publish and (dest/'approval.json').exists() and not (dest/'upload.json').exists():
                p.upload(job)
        except Exception as exc:
            failures.append(f'{path.name}: {exc}')
for failure in failures:
    print(failure, file=sys.stderr)
sys.exit(bool(failures))
