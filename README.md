# Personal packaging

Run `make` to list packages. Run `make live-serve help` for package commands.

## live-serve

Build Debian packages from the pinned upstream Linux binaries inside the target containers:

```sh
make live-serve test
```

This needs Docker and network access. It installs, serves a 3.2 MB HTML file, checks the WebSocket reload event, and removes the package in Debian bookworm, trixie and sid and Ubuntu noble for amd64 and arm64. Results are written to `live-serve/dist`. Containers share the host kernel.

`make live-serve build SUITE=bookworm ARCH=amd64` builds one package on a Linux host with curl, Python 3 and dpkg-deb. Other suites are `trixie`, `sid`, and `noble`. Other architecture is `arm64`. Review upstream release assets, license and hashes before updating pins.

`make live-serve release` checks the clean default branch against origin, runs the matrix, creates an annotated `live-serve/v<version>-<revision>` tag, and pushes it. The tag starts CI, which publishes a GitHub Release after all eight jobs pass. If CI fails, rerun the workflow on the same tag. Consume a specific tag's release URL, not the repository-wide latest release.

Set `PACKAGECLOUD_TOKEN` and `PACKAGECLOUD_REPOSITORY=cosgroveb/<repository>`, install the `package_cloud` CLI, then run `make live-serve publish` to upload the validated packages. The command checks Packagecloud's distribution list before uploading. It stops on the first failure and reports prior successes. Uploads are not atomic. Resolve duplicates and ambiguous failures manually before retrying. The publication path has not been tested against an authenticated Packagecloud account.
