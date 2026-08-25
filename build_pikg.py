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


def load_build_config() -> tuple[dict, dict, list[tuple[str, str, str]]]:
    app = json.loads((META_DIR / "app.json").read_text(encoding="utf-8"))
    pikg = json.loads((META_DIR / "pikg.json").read_text(encoding="utf-8"))
    platforms = {"x86_64": "linux/amd64", "aarch64": "linux/arm64"}
    docker_packages: dict[str, tuple[str, str, str]] = {}
    for package_name, package in pikg["sub_pkgs"].items():
        if package["source"]["type"] != "docker-image":
            continue

        selector = package.get("selector", {})
        arch = selector.get("arch")
        if selector.get("os") != "linux" or arch not in platforms:
            raise RuntimeError(f"unsupported Docker selector: {selector}")
        if arch in docker_packages:
            raise RuntimeError(f"duplicate Docker package for architecture: {arch}")
        docker_packages[arch] = (
            package_name,
            package["source"]["image"],
            platforms[arch],
        )

    missing_arches = set(platforms) - set(docker_packages)
    if missing_arches:
        missing = ", ".join(sorted(missing_arches))
        raise RuntimeError(f"dapp_meta/pikg.json is missing Docker architectures: {missing}")

    return app, pikg, [docker_packages[arch] for arch in platforms]


def git_commit() -> str:
    result = subprocess.run(
        ["git", "log", "-n", "1", "--format=%h"],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def verify_image_platform(image_name: str, expected_platform: str) -> None:
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Os}}/{{.Architecture}}",
            image_name,
        ],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=True,
    )
    actual_platform = result.stdout.strip()
    if actual_platform != expected_platform:
        raise RuntimeError(
            f"Docker image {image_name} has platform {actual_platform}, "
            f"expected {expected_platform}"
        )


def main() -> None:
    app, pikg, docker_packages = load_build_config()
    buckyos_tool = find_buckyos_tool()
    commit = git_commit()

    for package_name, image_name, docker_platform in docker_packages:
        print(f"Building {package_name} for {docker_platform}", flush=True)
        run(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                docker_platform,
                "--load",
                "--build-arg",
                f'APP_VERSION={app["version"]}',
                "--build-arg",
                f"GIT_COMMIT={commit}",
                "--tag",
                image_name,
                "--file",
                "image/Dockerfile",
                ".",
            ]
        )
        verify_image_platform(image_name, docker_platform)
    run([buckyos_tool, "--non-interactive", "pikg", "build", str(META_DIR)])
    run([buckyos_tool, "--non-interactive", "pikg", "pack", str(DIST_DIR)])

    pikg_path = DIST_DIR / pikg["pikg_file"]
    run([buckyos_tool, "--non-interactive", "pikg", "info", str(pikg_path)])
    print(f"PIKG created: {pikg_path}")


if __name__ == "__main__":
    main()
