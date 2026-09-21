# RHEL for Edge CI

This document describes the CI pipelines for RHEL for Edge and Fedora IoT tests
in this repository: automated compose triggers, manual test triggers, lint
checks, and supporting workflows.

## RHEL compose CI

RHEL compose triggers run once a day for each supported RHEL version. They
check the `COMPOSE_ID` of the latest compose. If the ID is not found in the
corresponding compose file (for example, `compose/compose.810`), a new pull
request is created with a corresponding `/test-rhel-*` comment. The compose
update policy validates eligible generated pull requests and enables rebase
auto-merge only after the required checks pass. That triggers all RHEL for Edge
tests for the corresponding RHEL version on Testing Farm.

## CentOS Stream compose CI

The CentOS Stream compose trigger runs once a day. It checks the `COMPOSE_ID`
of the latest compose. If the ID is not found in the compose file (for example,
`compose/compose.cs9`), a new pull request is created with a `/test-cs*`
comment. The compose update policy validates eligible generated pull requests
and enables rebase auto-merge only after the required checks pass. That
triggers all CentOS Stream Edge tests on Testing Farm.

## Fedora compose CI

The Fedora compose trigger runs once a day. It checks the `COMPOSE_ID` of the
latest compose. If the ID is not found in the compose file (for example,
`compose/compose.f43`), a new pull request is created with a `/test-f*`
comment. That triggers all Fedora Edge tests on Testing Farm.

The Fedora Rawhide compose trigger is currently disabled (commented out in
`trigger-fedora.yml`). Tests can still be triggered manually with
`/test-rawhide`.

## Fedora IoT compose CI

Fedora IoT compose triggers run daily for each supported version defined in
`trigger-iot.yml`. They can also be run manually, for example with
`/test-f44-iot`. The workflows check the `COMPOSE_ID` of the latest compose.
If the ID is not found in the corresponding compose file (for example,
`compose/compose.f44-iot`), a new pull request is created with a corresponding
`/test-f*-iot` comment. That triggers all Fedora IoT tests for the corresponding
version on Testing Farm.

## How to run compose test manually

Create a pull request and add a comment according to the following table:

| Comment | Triggered tests |
| --- | --- |
| `/test-rhel-8-10` | All RHEL 8.10 Edge tests |
| `/test-rhel-9-2` | All RHEL 9.2 Edge tests |
| `/test-rhel-9-4` | All RHEL 9.4 Edge tests |
| `/test-rhel-9-5` | All RHEL 9.5 Edge tests |
| `/test-rhel-9-6` | All RHEL 9.6 Edge tests |
| `/test-rhel-9-8` | All RHEL 9.8 Edge tests |
| `/test-cs9` | All CentOS Stream 9 Edge tests |
| `/test-f43` | All Fedora 43 Edge tests |
| `/test-f44-iot` | Fedora IoT 44 tests |
| `/test-f45-iot` | Fedora IoT 45 tests |
| `/test-f46-iot` | Fedora IoT 46 tests |

## `rhel-edge` repository CI

Any pull request triggers the **Lint** job automatically. Edge tests do not
run by default. To run an Edge test, add a comment from the table above.

Lint checks (defined in `.github/workflows/lint.yml`):

| Check | Local equivalent |
| --- | --- |
| Commit messages | CI only (`commitlint`) |
| Spelling | `codespell --check-filenames` |
| Shell scripts | Run `shellcheck` with the repository's exclusions |
| YAML | `yamllint .` |

## Other CI workflows

- **AWS AMI cleanup** (`cleanup-aws-ami.yaml`): removes stale AMI resources
- **vSphere cleanup** (`cleanup-vsphere.yaml`): removes stale vSphere resources
- **Compose file cleanup** (`clear-compose-file.yml`): clears compose files on schedule

## RHEL for Edge package CI

> **Note:** This workflow is currently inactive.

RHEL for Edge packages, such as `ostree`, `rpm-ostree`, `greenboot`,
`rust-coreos-installer`, and `fido-device-onboard`, will be monitored by brew
messages on UMB. The message will be cached when package building finishes and
the test will run against the new package.

## Customer case

> **Note:** This workflow is currently inactive.

Customer-case tests will run weekly for regression coverage.
