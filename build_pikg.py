#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
META_DIR = PROJECT_DIR / "dapp_meta"
DIST_DIR = PROJECT_DIR / "dapp_dist"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_DIR, check=True)


def find_buckyos_tool() -> str:
    configured = os.environ.get("BUCKYOS_TOOL_PATH")
    candidates = [configured] if configured else []
    candidates.extend(
        [
            shutil.which("buckyos"),
            str(PROJECT_DIR.parent / "buckyos" / "src" / "tools" / "buckyos-tool" / "buckyos"),
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().is_file():
            return str(Path(candidate).expanduser().resolve())
    raise RuntimeError(
        "buckyos-tool was not found; install the new buckyos command or set BUCKYOS_TOOL_PATH"
    )


def load_build_config() -> tuple[dict, dict, str, str]:
    app = json.loads((META_DIR / "app.json").read_text(encoding="utf-8"))
    pikg = json.loads((META_DIR / "pikg.json").read_text(encoding="utf-8"))
    docker_packages = [
        package
        for package in pikg["sub_pkgs"].values()
        if package["source"]["type"] == "docker-image"
    ]
    if len(docker_packages) != 1:
        raise RuntimeError("dapp_meta/pikg.json must contain exactly one Docker image")

    package = docker_packages[0]
    selector = package.get("selector", {})
    arch = selector.get("arch")
    platforms = {"x86_64": "linux/amd64", "aarch64": "linux/arm64"}
    if selector.get("os") != "linux" or arch not in platforms:
        raise RuntimeError(f"unsupported Docker selector: {selector}")

    return app, pikg, package["source"]["image"], platforms[arch]


def git_commit() -> str:
    result = subprocess.run(
        ["git", "log", "-n", "1", "--format=%h"],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> None:
    app, pikg, image_name, docker_platform = load_build_config()
    buckyos_tool = find_buckyos_tool()

    run(
        [
            "docker",
            "build",
            "--platform",
            docker_platform,
            "--build-arg",
            f'APP_VERSION={app["version"]}',
            "--build-arg",
            f"GIT_COMMIT={git_commit()}",
            "--tag",
            image_name,
            "--file",
            "image/Dockerfile",
            ".",
        ]
    )
    run([buckyos_tool, "--non-interactive", "pikg", "build", str(META_DIR)])
    run([buckyos_tool, "--non-interactive", "pikg", "pack", str(DIST_DIR)])

    pikg_path = DIST_DIR / pikg["pikg_file"]
    run([buckyos_tool, "--non-interactive", "pikg", "info", str(pikg_path)])
    print(f"PIKG created: {pikg_path}")


if __name__ == "__main__":
    main()
