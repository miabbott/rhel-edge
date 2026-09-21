# RHEL for Edge and Fedora IoT Tests

This repository contains downstream integration tests for OSTree-based edge
images. It tests:

- RHEL for Edge, CentOS Stream, and Fedora images built with
  [`osbuild-composer`](https://github.com/osbuild/osbuild-composer)
- Fedora IoT images downloaded from pre-built compose artifacts

Testing Farm provisions the test VMs. GitHub Actions starts the workflows and
posts the test result to the pull request. The test plans and scripts support
x86_64 and aarch64, although the enabled CI matrix varies by stream.

## Contents

- [`setup.sh`](setup.sh) and [`iot-setup.sh`](iot-setup.sh): provision the
  composer or IoT test environment inside a disposable VM
- `*.sh`: image-specific integration tests
- [`tmt/plans/`](tmt/plans): TMT plans and hardware requirements
- [`tmt/tests/test.sh`](tmt/tests/test.sh): dispatches `TEST_CASE` to a test
  script
- [`files/`](files): osbuild-composer repository configuration
- [`compose/`](compose): compose IDs already selected for testing
- [`check-ostree.yaml`](check-ostree.yaml) and
  [`check-ostree-iot.yaml`](check-ostree-iot.yaml): post-installation checks
- [`.github/workflows/`](.github/workflows): compose triggers, test triggers,
  linting, cleanup, and security scanning

The files in `compose/` are managed by the scheduled workflows. Do not edit
them manually.

## Test Matrix

### Edge test cases

| `TEST_CASE` | Script | Coverage |
| --- | --- | --- |
| `edge-commit` | [`ostree.sh`](ostree.sh) | OSTree commit deployed with kickstart |
| `edge-installer` | [`ostree-ng.sh`](ostree-ng.sh) | Bootable installer ISO |
| `edge-raw-image` | [`ostree-raw-image.sh`](ostree-raw-image.sh) | Raw disk image imported into a VM |
| `edge-ami-image` | [`ostree-ami-image.sh`](ostree-ami-image.sh) | AWS AMI deployment |
| `edge-simplified-installer` | [`ostree-simplified-installer.sh`](ostree-simplified-installer.sh) | Simplified installer ISO, including FDO where supported |
| `edge-vsphere` | [`ostree-vsphere.sh`](ostree-vsphere.sh) | VMDK deployment to vSphere |
| `edge-ignition` | [`ostree-ignition.sh`](ostree-ignition.sh) | Ignition with simplified installer and raw image |
| `edge-8to9` | [`ostree-8-to-9.sh`](ostree-8-to-9.sh) | RHEL 8 or CentOS Stream 8 to version 9 |
| `edge-9to9` | [`ostree-9-to-9.sh`](ostree-9-to-9.sh) | Upgrade within RHEL 9 |

### Fedora IoT test cases

| `TEST_CASE` | Script | Coverage |
| --- | --- | --- |
| `iot-installer` | [`iot-installer.sh`](iot-installer.sh) | Installer ISO deployed with kickstart |
| `iot-simplified-installer` | [`iot-simplified-installer.sh`](iot-simplified-installer.sh) | Simplified installer with FDO and Ignition |
| `iot-raw-image` | [`iot-raw-image.sh`](iot-raw-image.sh) | Raw image imported into a VM |
| `iot-bootc` | [`iot-bootc-image.sh`](iot-bootc-image.sh) | `bootc` OCI image converted with `bootc-image-builder` |

The dispatcher in [`tmt/tests/test.sh`](tmt/tests/test.sh) is the authoritative
mapping between TMT test cases and scripts.

### Supported compose streams

The scheduled compose workflows currently track:

- RHEL 8.10
- RHEL 9.2, 9.4, 9.5, 9.6, and 9.8
- CentOS Stream 9
- Fedora 43
- Fedora IoT 44, 45, and 46

The exact architecture coverage is defined by each stream's workflow. RHEL 9
and CentOS Stream 9 workflows include x86_64 and, where enabled, aarch64
Testing Farm jobs. Fedora IoT aarch64 jobs are currently disabled in the
workflows.

## CI Workflows

### Compose tracking

Scheduled `trigger-*.yml` workflows fetch the latest compose ID for each
stream. If it has not already been tested, the workflow appends it to the
corresponding `compose/compose.*` file and opens a pull request. The pull
request also receives the command that starts the stream-specific Testing Farm
workflow.

Generated compose pull requests are eligible for the compose policy only when
they:

- Come from `cloudkitebot` and have the existing `automated-pr` or `auto-merge`
  label
- Change exactly one `compose/compose.*` file
- Append exactly one compose ID without changing existing lines
- Match the current compose ID from the external compose source
- Have passing lint and stream-specific Testing Farm checks
- Are not drafts, held by a review label, or superseded by a newer compose

The policy is implemented by
[`.github/workflows/compose-update-policy.yml`](.github/workflows/compose-update-policy.yml)
and [`.github/scripts/compose-update-policy.py`](.github/scripts/compose-update-policy.py).
When every condition passes, it approves the pull request and enables rebase
auto-merge. Other automated changes, test failures, infrastructure failures,
and changes outside the compose tracking files remain manual-review work.

Compose retention cleanup is handled separately by
[`clear-compose-file.yml`](.github/workflows/clear-compose-file.yml).

### Test triggers

Test workflows respond to authorized pull-request comments. The available
commands are:

| Comment | Tests |
| --- | --- |
| `/test-rhel-8-10` | RHEL 8.10 Edge |
| `/test-rhel-9-2` | RHEL 9.2 Edge |
| `/test-rhel-9-4` | RHEL 9.4 Edge |
| `/test-rhel-9-5` | RHEL 9.5 Edge |
| `/test-rhel-9-6` | RHEL 9.6 Edge |
| `/test-rhel-9-8` | RHEL 9.8 Edge |
| `/test-cs9` | CentOS Stream 9 Edge |
| `/test-f43` | Fedora 43 Edge |
| `/test-f44-iot` | Fedora IoT 44 |
| `/test-f45-iot` | Fedora IoT 45 |
| `/test-f46-iot` | Fedora IoT 46 |
| `/test-rawhide` | Fedora Rawhide Edge, when the workflow is enabled |

The comment sender must have the repository permission required by the
workflow. See [`CI.md`](CI.md) for workflow details and the Testing Farm
integration.

### Repository checks

The [`Lint`](.github/workflows/lint.yml) workflow runs on every pull request:

- Commit message validation with `commitlint`
- Spelling validation with `codespell`
- Shell validation with `shellcheck`
- YAML validation with `yamllint`

The [`CodeQL`](.github/workflows/codeql.yml) workflow provides code scanning.
Cleanup workflows remove stale AWS AMI and vSphere resources.

## Running Tests Locally

These are integration tests intended for disposable VMs. There is no local
build step for the repository itself. The scripts provision their environment,
build or download an image, deploy it, run validation, and clean up.

### Requirements

For x86_64, use a machine or VM with KVM available:

```shell
ls -l /dev/kvm
```

aarch64 tests require an ARM host with the required cloud or virtualization
access. Testing Farm is the supported execution environment for CI.

### Examples

RHEL Edge tests require `DOWNLOAD_NODE` to identify the RHEL compose server:

```shell
DOWNLOAD_NODE=download.example.com ./ostree.sh
```

Tests that push images also require the relevant registry credentials:

```shell
DOWNLOAD_NODE=download.example.com \
QUAY_USERNAME=example \
QUAY_PASSWORD='token' \
./ostree-ng.sh
```

Fedora IoT tests download their compose artifacts directly and do not normally
need a compose-server variable:

```shell
./iot-installer.sh
```

Do not put credentials in scripts, compose files, pull requests, or commits.
CI receives secrets through GitHub Actions and Testing Farm configuration.

### Configuration variables

| Variable | Purpose |
| --- | --- |
| `DOWNLOAD_NODE` | RHEL compose download server |
| `QUAY_USERNAME` | Quay username for OCI image tests |
| `QUAY_PASSWORD` | Quay password or token for OCI image tests |
| `DOCKERHUB_USERNAME` | Docker Hub username for image tests |
| `DOCKERHUB_PASSWORD` | Docker Hub password or token for image tests |
| `AWS_ACCESS_KEY_ID` | AWS credentials for AMI and EC2 tests |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials for AMI and EC2 tests |
| `AWS_DEFAULT_REGION` | AWS region for AMI and EC2 tests |
| `GOVC_URL`, `GOVC_USERNAME`, `GOVC_PASSWORD` | vSphere tests |

The workflows may pass additional credentials to Testing Farm for specific
scenarios. See the individual workflow and test script before running a cloud
or registry-backed test.

## Post-installation Checks

The Ansible playbooks validate the deployed systems, including:

- BIOS/UEFI, secure boot, TPM, partitions, LVM, and mount points
- SELinux, `systemd`, `ostree`, and `rpm-ostree` state
- OSTree deployments, refs, upgrades, rebases, and rollback behavior
- `greenboot`, boot completion, and persistent journal state
- Podman root and non-root containers
- Ignition and FDO provisioning where supported
- Installed packages, custom files and services, and kernel error logs

Edge checks are in [`check-ostree.yaml`](check-ostree.yaml). Fedora IoT checks
are in [`check-ostree-iot.yaml`](check-ostree-iot.yaml).

## Contributing

Create a branch from `main`, make the smallest focused change, and run the
repository lint commands described in [`CI.md`](CI.md). Use Conventional
Commits and sign commits off for DCO compliance. Open a pull request against
`main`; use an authorized `/test-*` comment when integration testing is needed.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for repository conventions and
[`AGENTS.md`](AGENTS.md) for the repository structure and workflow rules.

## Contact

Open a [GitHub issue](https://github.com/virt-s1/rhel-edge/issues) or start a
[GitHub discussion](https://github.com/virt-s1/rhel-edge/discussions).
