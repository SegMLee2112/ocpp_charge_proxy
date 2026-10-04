# Contributing & Release Process

## Project Structure

```
ocpp_charge_proxy/                    # HA add-on (Docker container)
  config.yaml                         # Add-on metadata — contains the version
  src/                                # Python OCPP client
  tests/                              # pytest tests
  CHANGELOG.md                        # User-facing changelog
  DOCS.md                             # Add-on documentation (shown in HA)

.github/workflows/
  builder.yaml                        # Builds and pushes Docker images on push to master
  lint.yaml                           # Runs HA add-on linter
  test.yaml                           # Runs pytest
```

## Version Numbers

The version is in `ocpp_charge_proxy/config.yaml` (`version`). It uses [semver](https://semver.org/):
- **Patch** (0.1.1) — bug fixes
- **Minor** (0.2.0) — new features, backward compatible
- **Major** (1.0.0) — breaking changes

## Release Checklist

1. **Make your changes** on master (or a feature branch merged to master)

2. **Update the changelog** — edit `ocpp_charge_proxy/CHANGELOG.md`. Each
   version gets a short title, and each line a tag saying what kind of
   change it is:
   ```markdown
   ## 2.13.0 — Supplier slots on the schedule

   - **Feature:** something new you can do
   - **Improvement:** something that works better or reads more clearly
   - **Fix:** something that was wrong and now isn't
   - **Change:** existing behaviour that now works differently
   - **Docs:** documentation only
   ```
   Newest version first, right under `# Changelog`.

3. **Bump the version** in `ocpp_charge_proxy/config.yaml` → `version: "0.2.0"`

4. **Commit**:
   ```bash
   git add ocpp_charge_proxy/config.yaml ocpp_charge_proxy/CHANGELOG.md
   git commit -m "release: v0.2.0"
   ```

5. **Push to master**:
   ```bash
   git push origin master
   ```

6. **Verify CI** — check GitHub Actions:
   - `Tests` workflow passes (pytest)
   - `Lint` workflow passes (add-on linter)
   - `Builder` workflow builds and pushes Docker images to GHCR

7. **Create a GitHub Release** (optional but recommended):
   ```bash
   gh release create v0.2.0 --title "v0.2.0" --notes "See CHANGELOG.md"
   ```

## What Happens on Push

| Workflow | Trigger | Action |
|----------|---------|--------|
| `test.yaml` | Push/PR to master | Runs `pytest` |
| `lint.yaml` | Push/PR to master | Runs HA add-on linter |
| `builder.yaml` | Push to master | Builds Docker images, pushes to GHCR |
| `builder.yaml` | PR to master | Test build only (no push) |

## How Users Get Updates

- **Add-on:** HA Supervisor checks the `version` in `config.yaml` against the installed version. When it changes, the user sees an update notification.

There's no separate integration (since 2.0.0): the add-on creates its own
Home Assistant entities.

## Development Setup

```bash
cd ocpp_charge_proxy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v
```

The add-on only runs under Home Assistant (it needs the Supervisor for its
sensors, history and settings); test changes by rebuilding it in HA.

## Testing in HA

1. Push changes to GitHub
2. In HA: **Settings > Add-ons > OCPP Charge Proxy > Rebuild**

## Security Score

Current score: **8/8**

| Factor | Score |
|--------|-------|
| Base | 5 |
| Custom AppArmor profile (`apparmor.txt`) | +1 |
| Ingress (`ingress: true`) | +2 |

Avoid: `host_network`, `privileged`, `full_access`, `docker_api` (all reduce score).
