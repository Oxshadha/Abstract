# EDP-001: Local S3-compatible storage

| | |
|---|---|
| **Status** | Approved by owner (2026-11-11), option A → recorded as **D61** |
| **Raised during** | Spec 001 (foundation) |
| **Supersedes** | Local-storage part of D18 (MinIO) |

## Context / trigger
D18 chose MinIO as the local stand-in for S3. While building spec 001 we found that **MinIO stopped publishing Docker images in Oct 2025 and its repository was archived in Apr 2026**. There is no maintained official image.

## Options
| Option | Pros | Cons |
|---|---|---|
| **A. SeaweedFS 4.53** | Mature, Apache-2.0, single container, actively released | No MinIO-style web console |
| B. RustFS 1.0.5 | Closest MinIO look-alike, console included | Only just reached 1.0 |
| C. Old or third-party MinIO image | No decision change | Unmaintained, security exposure |

## Recommendation
A. Only local development is affected. Code talks to storage through the `Storage` port, so swapping again is a compose-only change (about 10 lines).

## Impact
`infra/docker-compose.yml` (s3 service), `infra/seaweedfs/s3.json` (dev credentials), spec 001 text. The API creates the dev bucket on startup (no init container). Production (AWS S3) is unchanged.

## Reversibility
Easy.
