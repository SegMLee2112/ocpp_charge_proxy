# Contributing & Release Process

## Project Structure

```
ocpp_charge_proxy/                    # HA add-on (Docker container)
  config.yaml                         # Add-on metadata — contains the version
  src/                                # Python OCPP client
  tests/                              # pytest tests
  CHANGELOG.md                        # User-facing changelog
  DOCS.md                             # Add-on documentation (shown in HA)

custom_components/ocpp_charge_proxy/  # HA integration (HACS)
  manifest.json                       # Integration metadata — contains the version

.github/workflows/
  builder.yaml                        # Builds and pushes Docker images on push to master
  lint.yaml                           # Runs HA add-on linter
  test.yaml                           # Runs pytest
```

## Version Numbers

The add-on and integration versions **must stay in sync**:

| File | Field | Example |
|------|-------|---------|
| `ocpp_charge_proxy/config.yaml` | `version` | `"0.1.0"` |
| `custom_components/ocpp_charge_proxy/manifest.json` | `version` | `"0.1.0"` |

Both use [semver](https://semver.org/):
- **Patch** (0.1.1) — bug fixes
- **Minor** (0.2.0) — new features, backward compatible
- **Major** (1.0.0) — breaking changes

## Release Checklist

1. **Make your changes** on master (or a feature branch merged to master)

2. **Update the changelog** — edit `ocpp_charge_proxy/CHANGELOG.md`:
   ```markdown
   ## 0.2.0

   - Description of changes
   ```

3. **Bump both versions** — they must match:
   - `ocpp_charge_proxy/config.yaml` → `version: "0.2.0"`
   - `custom_components/ocpp_charge_proxy/manifest.json` → `"version": "0.2.0"`

4. **Commit**:
   ```bash
   git add ocpp_charge_proxy/config.yaml ocpp_charge_proxy/CHANGELOG.md \
          custom_components/ocpp_charge_proxy/manifest.json
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
- **Integration:** HACS checks the `version` in `manifest.json`. Users update via HACS > Integrations.

Both update independently but should always be the same version to avoid confusion.

## Development Setup

```bash
cd ocpp_charge_proxy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-aiohttp

# Run tests
python -m pytest tests/ -v

# Run standalone (outside HA)
./run_standalone.sh ocpp.example.com CHARGEPOINT_ID PASSWORD
```

## Testing in HA

1. Push changes to GitHub
2. In HA: **Settings > Add-ons > OCPP Charge Proxy > Rebuild**
3. For the integration: **HACS > Integrations > OCPP Charge Proxy > Redownload**, then restart HA

## Security Score

Current score: **8/8**

| Factor | Score |
|--------|-------|
| Base | 5 |
| Custom AppArmor profile (`apparmor.txt`) | +1 |
| Ingress (`ingress: true`) | +2 |

Avoid: `host_network`, `privileged`, `full_access`, `docker_api` (all reduce score).
