"""Optional isolated native PostgreSQL test harness; never opens an existing cluster."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg-bin', type=Path, required=True)
    parser.add_argument('--port', type=int, default=55435)
    parser.add_argument('--cluster-name', default='postgres')
    args = parser.parse_args()
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    connection = runtime / 'test-connection.json'
    if connection.exists():
        print('Existing isolated test connection preserved; no cluster reinitialization.')
        return
    if not args.cluster_name.replace('-', '').isalnum():
        raise SystemExit('Invalid cluster name')
    cluster = runtime / args.cluster_name
    if cluster.exists():
        raise SystemExit('Partial cluster already exists; inspect it rather than overwrite')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    password = secrets.token_urlsafe(36)
    password_file = runtime / 'postgres-password.tmp'
    password_file.write_text(password, encoding='utf-8')
    suffix = '.exe' if os.name == 'nt' else ''
    subprocess.run([str(args.pg_bin / ('initdb' + suffix)), '-D', str(cluster), '-U', 'healthmon_test', '--pwfile', str(password_file), '--auth=scram-sha-256', '--encoding=UTF8', '--no-locale'], check=True)
    password_file.unlink()
    connection.write_text(json.dumps({'admin_dsn': f'postgresql://healthmon_test:{password}@127.0.0.1:{args.port}/postgres', 'port': args.port, 'cluster': '.runtime/' + args.cluster_name}), encoding='utf-8')
    if os.name != 'nt':
        connection.chmod(0o600)
    subprocess.run([str(args.pg_bin / ('pg_ctl' + suffix)), '-D', str(cluster), '-l', str(runtime / 'postgres.log'), '-o', f'-h 127.0.0.1 -p {args.port}', '-w', 'start'], check=True)
    print('Started a new loopback-only isolated PostgreSQL test cluster; credentials remain local.')


if __name__ == '__main__':
    main()
