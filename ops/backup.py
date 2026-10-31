#!/usr/bin/env python3
"""The delivered cold-backup/restore workflow. Uses the deployed image, not live SQLite copies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def command(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def compose(project, *args, capture=False):
    cmd = ["docker", "compose"] + (["-p", project] if project else []) + list(args)
    result = command(cmd, capture_output=capture)
    return result.stdout.strip() if capture else ""


def inspect(project, service):
    container = compose(project, "ps", "-aq", service, capture=True)
    if not container or "\n" in container:
        raise RuntimeError(f"Create exactly one {service} container before this operation.")
    data = command(["docker", "inspect", "--format", "{{json .Mounts}}", container], capture_output=True)
    image = command(["docker", "inspect", "--format", "{{.Image}}", container], capture_output=True).stdout.strip()
    return {m["Destination"]: m["Name"] for m in json.loads(data.stdout) if m["Type"] == "volume"}, image


def volume_helper(image, volume, folder, code, capture=False, **environment):
    args = ["docker", "run", "--rm", "--network", "none", "--user", "0", "--entrypoint", "python",
            "-v", volume+":/volume", "-v", str(folder)+":/backup"]
    for key,value in environment.items():
        args.extend(["-e", f"{key}={value}"])
    return command(args+[image, "-c", code], capture_output=capture)


def create(project, folder):
    if folder.exists():
        raise RuntimeError("Choose a new backup directory; existing backups are never overwritten.")
    web, image = inspect(project, "web")
    caddy, _ = inspect(project, "caddy")
    volumes = {"app_data": web["/data"], "caddy_data": caddy["/data"], "caddy_config": caddy["/config"]}
    running = compose(project, "ps", "--services", "--status", "running", capture=True).splitlines()
    if "migrate" in running:
        raise RuntimeError("Wait for migrations to finish before taking a cold backup.")
    restart = [s for s in running if s in ["web", "worker", "caddy"]]
    restart_ids = [compose(project, "ps", "-aq", s, capture=True) for s in restart]
    folder.mkdir(parents=True, mode=0o700)
    try:
        compose(project, "stop", "-t", "15", "web", "worker", "caddy")
        manifest = {"format": 1, "procedure": "vocab-cold-backup-v1", "image": image,
                    "procedure_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "renderer": "cloze-v1/markdown-it-py-4.0.0",
                    "fsrs": "6.3.2", "excluded": ["audio_tmp", "deployer environment/secrets"], "sha256": {}}
        for role, volume in volumes.items():
            filename = role+".tar.gz"
            volume_helper(image, volume, folder, """
import os,tarfile
path='/backup/'+os.environ['FILENAME']
with tarfile.open(path,'w:gz') as archive: archive.add('/volume',arcname='.')
os.chmod(path,0o600)
os.chown(path,int(os.environ['OWNER_UID']),int(os.environ['OWNER_GID']))
""", FILENAME=filename, OWNER_UID=os.getuid(), OWNER_GID=os.getgid())
            manifest["sha256"][filename] = hashlib.sha256((folder/filename).read_bytes()).hexdigest()
        schema = volume_helper(image, volumes["app_data"], folder,
            "import json,sqlite3; db=sqlite3.connect('file:/volume/db.sqlite3?mode=ro',uri=True); print(json.dumps(db.execute('SELECT app,name FROM django_migrations ORDER BY app,name').fetchall()))", capture=True)
        manifest["schema"] = json.loads(schema.stdout)
        (folder/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        (folder/"manifest.json").chmod(0o600)
        print("Cold backup complete. Audio and deployer secrets are excluded.")
    finally:
        if restart_ids:
            # Restart existing containers without re-running migration dependencies or selecting a newer image.
            command(["docker", "start", *restart_ids])


def restore(project, folder):
    manifest = json.loads((folder/"manifest.json").read_text())
    names = {"app_data.tar.gz", "caddy_data.tar.gz", "caddy_config.tar.gz"}
    if manifest.get("format") != 1 or manifest.get("procedure") != "vocab-cold-backup-v1" or set(manifest.get("sha256", {})) != names:
        raise RuntimeError("Unsupported or incomplete backup manifest.")
    for filename,digest in manifest["sha256"].items():
        if hashlib.sha256((folder/filename).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Backup integrity check failed: "+filename)
    if compose(project, "ps", "--services", "--status", "running", capture=True):
        raise RuntimeError("Stop this target project first. Restore requires fresh empty volumes.")
    compose(project, "create", "migrate", "web", "worker", "caddy")
    web,image = inspect(project, "web")
    caddy,_ = inspect(project, "caddy")
    if image != manifest["image"]:
        raise RuntimeError("Use the exact backup application image first; migrate deliberately after restore.")
    volumes = {"app_data": web["/data"], "caddy_data": caddy["/data"], "caddy_config": caddy["/config"]}
    for volume in volumes.values():
        volume_helper(image, volume, folder, "from pathlib import Path; assert not any(p.is_file() or p.is_symlink() for p in Path('/volume').rglob('*')), 'Target volume contains data; nothing was overwritten.'")
    for role,volume in volumes.items():
        volume_helper(image, volume, folder, """
import os,tarfile
from pathlib import Path
with tarfile.open('/backup/'+os.environ['FILENAME'],'r:gz') as archive:
    archive.extractall('/volume',filter='data')
if os.environ['ROLE']=='app_data':
    for path in [Path('/volume'),*Path('/volume').rglob('*')]: os.chown(path,10001,10001)
""", FILENAME=role+".tar.gz", ROLE=role)
    volume_helper(image, volumes["app_data"], folder, "import sqlite3; db=sqlite3.connect('file:/volume/db.sqlite3?mode=ro',uri=True); assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'")
    print("Restore complete; processes remain stopped. Configure the original hostname/CA and run migrations before starting.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "restore"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--project", help="Compose project name; use a new name for a fresh-volume restore.")
    options = parser.parse_args()
    try:
        (create if options.operation == "create" else restore)(options.project, options.directory.resolve())
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, "Backup/restore failed: "+str(error)+"\n")


if __name__ == "__main__":
    main()
