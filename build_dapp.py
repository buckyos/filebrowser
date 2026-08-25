#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
META_DIR = PROJECT_DIR / "dapp_meta"
DIST_DIR = PROJECT_DIR / "dapp_dist"


def run(command: list[str], *, cwd: Path = PROJECT_DIR, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


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


def load_build_config() -> tuple[dict, str, str, str]:
    app = json.loads((META_DIR / "app.json").read_text(encoding="utf-8"))
    pikg = json.loads((META_DIR / "pikg.json").read_text(encoding="utf-8"))
    docker_packages = [
        (name, package)
        for name, package in pikg["sub_pkgs"].items()
        if package["source"]["type"] == "docker-image"
    ]
    if len(docker_packages) != 1:
        raise RuntimeError("dapp_meta/pikg.json must contain exactly one Docker image")

    _, package = docker_packages[0]
    selector = package.get("selector", {})
    if selector.get("os") != "linux":
        raise RuntimeError("the File Browser Docker package must target Linux")

    arch = selector.get("arch")
    if arch == "x86_64":
        go_arch = "amd64"
        docker_platform = "linux/amd64"
    elif arch == "aarch64":
        go_arch = "arm64"
        docker_platform = "linux/arm64"
    else:
        raise RuntimeError(f"unsupported Docker architecture: {arch}")

    return app, package["source"]["image"], go_arch, docker_platform


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
    app, image_name, go_arch, docker_platform = load_build_config()
    buckyos_tool = find_buckyos_tool()

    run(["pnpm", "install", "--frozen-lockfile"], cwd=PROJECT_DIR / "frontend")
    run(["pnpm", "run", "build"], cwd=PROJECT_DIR / "frontend")

    build_env = os.environ.copy()
    build_env.update({"CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": go_arch})
    ldflags = (
        f'-s -w -X "github.com/filebrowser/filebrowser/v2/version.Version={app["version"]}" '
        f'-X "github.com/filebrowser/filebrowser/v2/version.CommitSHA={git_commit()}"'
    )
    run(["go", "build", "-ldflags", ldflags, "-o", "filebrowser", "."], env=build_env)
    run(
        [
            "docker",
            "build",
            "--platform",
            docker_platform,
            "--tag",
            image_name,
            "--file",
            "Dockerfile",
            ".",
        ]
    )

    run([buckyos_tool, "--non-interactive", "pikg", "build", str(META_DIR)])
    run([buckyos_tool, "--non-interactive", "pikg", "pack", str(DIST_DIR)])
    pikg_path = DIST_DIR / json.loads(
        (META_DIR / "pikg.json").read_text(encoding="utf-8")
    )["pikg_file"]
    run([buckyos_tool, "--non-interactive", "pikg", "info", str(pikg_path)])
    print(f"PIKG created: {pikg_path}")


if __name__ == "__main__":
    main()
