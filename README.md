<p align="center">
  <img src="https://raw.githubusercontent.com/filebrowser/filebrowser/master/branding/banner.png" width="550"/>
</p>

[![Build](https://github.com/filebrowser/filebrowser/actions/workflows/ci.yaml/badge.svg)](https://github.com/filebrowser/filebrowser/actions/workflows/ci.yaml)
[![Go Report Card](https://goreportcard.com/badge/github.com/filebrowser/filebrowser/v2)](https://goreportcard.com/report/github.com/filebrowser/filebrowser/v2)
[![Version](https://img.shields.io/github/release/filebrowser/filebrowser.svg)](https://github.com/filebrowser/filebrowser/releases/latest)

File Browser provides a file managing interface within a specified directory and it can be used to upload, delete, preview and edit your files. It is a **create-your-own-cloud**-kind of software where you can just install it on your server, direct it to a path and access your files through a nice web interface.

## Documentation

Documentation on how to install, configure, and contribute to this project is hosted at [filebrowser.org](https://filebrowser.org).

## Project Status

This project is a finished product which fulfills its goal: be a single binary web File Browser which can be run by anyone anywhere. That means that File Browser is currently on **maintenance-only** mode. Therefore, please note the following:

- It can take a while until someone gets back to you. Please be patient.
- [Issues](https://github.com/filebrowser/filebrowser/issues) are meant to track bugs. Unrelated issues will be converted into [discussions](https://github.com/filebrowser/filebrowser/discussions).
- No new features will be implemented by maintainers. Pull requests for new features will be reviewed on a case by case basis.
- The priority is triaging issues, addressing security issues and reviewing pull requests meant to solve bugs.

## Contributing

Contributions are always welcome. To start contributing to this project, read our [guidelines](CONTRIBUTING.md) first.

## License

[Apache License 2.0](LICENSE) © File Browser Contributors


## BuckyOS named-object uploads

This BuckyOS build imports browser files and folders with the `buckyos` WebSDK. Sign in to File Browser and to the Zone; the SDK initializes the `filebrowser` App identity and obtains its own session. The same-origin `/api/ndm/*` proxy forwards that Bearer session to NDM and separately checks File Browser's `X-Auth`. It never substitutes a service/admin token or accepts an upstream URL from the browser.

Set `BUCKYOS_NDM_URL` on the Go service to its trusted NodeGateway/NDM origin (default `http://127.0.0.1:3180`). In a container this must identify the host/Zone gateway reachable from that container. Build the frontend with the corresponding SDK `main` source; the dependency is declared explicitly in `frontend/package.json`.

After SDK finalization reports the object ready, `/api/objects/<destination>` accepts `{ "obj_id": "cyfile:…" }` or a `cydir` identifier. The backend uses NamedStore `open_object` and `object/open` readers under the caller's root-object authorization, extracts into its own filesystem staging directory, and applies File Browser path/create/modify rules. Reads support ChunkList content without buffering entire files. The extraction limit is 64 GiB total, 100,000 entries and 256 levels; entry names and destination symlinks are checked. Staging prefixes `.ndm-import-*` are reserved and hidden from application reads.

Folder picker and recursive drops preserve a root DirObject, nested paths, and explicit empty directories from drag/drop. FileList cannot preserve empty folders; browsers without directory selection retain the file entry. Directory conflicts require rename/skip; file replacement requires the existing modify permission. Identical existing bytes/trees are reused on retry, including after a lost response, and are not overwritten. Cancelled/failed roots remain individually retryable while the page retains their File handles; the failed-item panel can retry a selected root under a different destination name without reuploading its ready object, or dismiss it. The batch shows separate success/failure/cancellation counts; earlier successful roots remain if another fails. A refresh requires reselecting files; SDK deduplication can reuse ready objects. No directory-batch atomicity is promised.

The old application TUS endpoints/client have been removed. `resources` POST creates empty files/directories; text editing still uses PUT. Browser content upload has a single SDK/NDM path.

Validation: `go test ./http`, `cd frontend && pnpm typecheck && pnpm build`. The HTTP tests cover streamed tree extraction, empty directories, content equality for retries, authorization forwarding, unsafe names, symlinks and extraction size limits. The object-commit handler tests use a signed local JWT, controlled NDM responses and real disk paths to verify file/dir readback, response-loss retry, replacement, renamed destinations, directory conflicts, staging cleanup and permissions revoked during extraction. Live Zone SSO, real container routing and browser interruption/restart still require deployment-level acceptance; these tests do not substitute for that run.
