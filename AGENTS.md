# AGENTS.md — Hindsight Memory Provider (Halo-Fork)

Dieses Verzeichnis ist der **Halo-Fork** des Hindsight-Memory-Providers für Hermes Agent.
Es ist die **Live-Quelle**: Der Plugin-Code läuft von hier, der Hindsight-Server wird
aus `hindsight-api-slim/` gebaut.

- **Fork:** `github.com/Ismanix-dev/hindsight`, Branch `halo`
- **Upstream:** `github.com/vectorize-io/hindsight` (Remote `upstream`, nur Lesen)
- **Lift-Basis:** Commit `176f8c2d` („lift plugin to repository root"), darauf die Halo-Stufen

## Struktur (das ist alles, was hier liegt)

| Pfad | Inhalt |
|---|---|
| `__init__.py` | Der Memory-Provider: `HindsightMemoryProvider`, Tools, Recall/Retain-Logik |
| `settings.py` | Settings-Normalisierung (Tags, Observation-Scopes, Bank-Segmente) |
| `config_schema.py` | Deklarierte Config-Oberfläche für das Desktop-Panel |
| `embedded.py` | `local_embedded`-Daemon-Verwaltung |
| `templates.py` | Starter-Memory-Templates für den Setup-Wizard |
| `setup.py` | Wizard-Hook (`post_setup`) |
| `tests/` | Provider-Tests (25) — `tests/conftest.py` stubbt die Hermes-Core-Interfaces |
| `hindsight-api-slim/` | Der Server-Quellcode (aus diesem Pfad wird `~/.hindsight/venv` installiert) |
| `hindsight-clients/` | Client-SDKs (Python/TS/Rust/Go) |
| `plugin.yaml` | Plugin-Manifest (`name`, `version`, `hooks`) |
| `README.md` | Nutzer-Doku: Installation, Config-Keys, Tools, Umgebungsvariablen |

**Nicht vorhanden** (Upstream-Monorepo, hier bewusst nicht): `scripts/`, `hindsight-control-plane/`,
`hindsight-cli/`, `hindsight-ui/`, `hindsight-embed/`, `hindsight-docs/`, `hindsight-system-evals/`.
Anweisungen, die dorthin zeigen, gelten hier nicht.

## Betriebsregeln des Forks

### Session-ID gehört NUR in die Metadata
Tags sind reserviert für `retain_tags` aus der Config und extrahierte Entity-Tags.
Eine `session:<ID>`- oder `parent:<ID>`-Tag darf **nie** entstehen — Session-Herkunft
ist Audit-Daten und liegt in `metadata.session_id` / `metadata.parent_session_id`.

### Tag-Konvention
- Tags: nur `agent:<name>` (aus `retain_tags`) plus freie Entity-Tags.
- **cherub trägt keinen Tag** — bewusste Ausnahme, damit seine Memories bankweit sichtbar bleiben.
- Alle anderen Profile: `retain_tags = agent:<name>`, `recall_tags = agent:<name>`.

### Banken
| Bank | Profile | `retain_strategies` | `retain_default_strategy` |
|---|---|---|---|
| `halo` | cherub, raz, nemo | `nemo`, `raz` | `standard` (built-in) |
| `halo-dev` | devi, appsec, fronti, revi, taurid, tester | `coding` | `coding` |

`agent` und `strategy` in der Profil-`config.json` sind **inerte Felder** — das Plugin liest sie
nicht und sendet keine Strategie an den Server; die Bank entscheidet.

### Modus
Alle Profile laufen `local_external` gegen `http://localhost:9177`.

## Tests

```bash
python -m pytest tests/ -q
```

Erwartung: **25 passed**. `tests/conftest.py` lädt dieses Verzeichnis als Paket und stubbt
`MemoryProvider`, den Secret-Scope und `cfg_get` — Hermes Agent ist nicht auf PyPI.

**Kein `uv run`** in diesem Verzeichnis: `uv` legt dabei ein `.venv/` an, das hier bewusst
nicht existiert. Stattdessen einen vorhandenen Interpreter mit `pytest` verwenden.

## Änderungen

- `pyproject.toml` ist die einzige Abhängigkeits-Autorität (`hindsight-client>=0.10.1,<1`).
- `config_schema.py` importiert absichtlich aus `plugins.memory.config_schema` — nicht vendorn.
- Vor jedem Commit: `python -m pytest tests/ -q`.
- Nach Server-Änderungen: Hindsight-Service neu starten und `/version` prüfen
  (`curl -s http://127.0.0.1:9177/version`).
