# CLAUDE.md — Hindsight Memory Provider, Halo-Fork

Anleitung für Agenten und Entwickler, die **in diesem Verzeichnis** arbeiten.

Dies ist der **Halo-Fork** (`github.com/Ismanix-dev/hindsight`, Branch `halo`) des
Hindsight-Memory-Providers für Hermes Agent. Upstream ist `vectorize-io/hindsight`
(Remote `upstream`, nur Lesen). Der Fork liegt auf dem Lift-Commit `176f8c2d` und trägt
darüber die Halo-Stufen 3a–3d.

- **Projekt-, Struktur- und Betriebsdoku:** [AGENTS.md](./AGENTS.md) — Struktur, Fork-Regeln
  (Session-ID nur in Metadata, Tag-Konvention, Banken), Testkommando, Änderungsregeln.
- **Nutzerdoku** (Installation, Config-Keys, Tools, Env-Variablen): [README.md](./README.md).

## Wichtig: Dies ist NICHT das Upstream-Monorepo

Die ursprüngliche `CLAUDE.md` beschrieb das vollständige Upstream-Monorepo. Hiervon existieren
hier **nur** `hindsight-api-slim/` und `hindsight-clients/`.

**Nicht vorhanden** — Anweisungen, die dorthin zeigen, gelten hier nicht:
`scripts/` (Dev-Skripte, Benchmarks, `generate-openapi.sh`, `generate-clients.sh`,
`hooks/lint.sh`, `hooks/check-unused.sh`, `release-integration.sh`),
`hindsight-control-plane/`, `hindsight-cli/`, `hindsight-ui/`, `hindsight-embed/`,
`hindsight-docs/`, `hindsight-integrations/`, `hindsight-system-tests/`,
`hindsight-system-evals/`, `hindsight-integration-tests/`, `hindsight-extensions/`,
`hindsight-tools/`, `hindsight-dev/`, `hindsight-all*/`, `hindsight-api/`.
Auch `.claude/skills/code-review/SKILL.md` existiert hier nicht.

## Wo der Code liegt

| Bereich | Pfad |
|---|---|
| Provider (Hermes-Seite) | `__init__.py`, `settings.py`, `config_schema.py`, `embedded.py`, `templates.py`, `setup.py` |
| Server-Engine | `hindsight-api-slim/hindsight_api/engine/` |
| Server-API | `hindsight-api-slim/hindsight_api/api/` (`http.py`, `mcp.py`) |
| Migrationen | `hindsight-api-slim/hindsight_api/alembic/` |
| Client-SDKs | `hindsight-clients/` |
| Tests (Provider) | `tests/` |

Der Server wird aus diesem Pfad installiert: `direct_url` in `~/.hindsight/venv` zeigt auf
`file:///home/akki/.hermes/plugins/hindsight/hindsight-api-slim`. Änderungen hier erreichen den
laufenden Service erst nach Neuinstallation des venv und Neustart von `hindsight-api.service`.

## Kernoperationen des Servers

- **Retain**: Memories speichern; extrahiert Fakten, Entities, Beziehungen; Dokument-Chunking.
- **Recall**: Abruf über 4 parallele Strategien (semantisch, BM25, Graph, temporal) + Reranking.
- **Reflect**: Dispositionsbewusste Synthese über Memories und Mental Models.
- **Knowledge Base**: Baum aus automatisch aktualisierten synthetischen Dokumenten (Mental Models).
- **Directives & Mental Models**: Verhaltensrichtlinien und konsolidierte Fakten pro Bank.

**Datenbank:** PostgreSQL mit pgvector, Schema über Alembic-Migrationen (laufen beim API-Start
automatisch). Kerntabellen: `banks`, `documents`, `chunks`, `entities`, `memory_units`,
`memory_links`, `directives`, `mental_models`, `knowledge_pages`.

**Bank-Config statt Alt-Endpunkte:** Dispositions (skepticism, literalism, empathy 1–5) und
`reflect_mission` werden über `PATCH /v1/default/banks/{bank_id}/config` gesetzt. Bank-Isolation
ist strikt — kein Cross-Bank-Leak. Dispositions wirken nur auf reflect, nicht auf recall.

## Tests

```bash
python -m pytest tests/ -q      # Erwartung: 25 passed
```

**Kein `uv run`** hier — `uv` legt dabei ein `.venv/` an, das es in diesem Verzeichnis bewusst
nicht gibt. `tests/conftest.py` lädt das Verzeichnis als Paket und stubbt die Hermes-Core-
Interfaces (`MemoryProvider`, Secret-Scope, `cfg_get`); Hermes Agent ist nicht auf PyPI.

Für Server-Tests gilt die Upstream-Anleitung sinngemäß: `cd hindsight-api-slim && uv run pytest
tests/`. Diese Suite ist groß und langsam; sie läuft hier nicht routinemäßig.

## Konventionen des Forks

- **Session-IDs nie in Tags.** Session-Herkunft gehört in `metadata.session_id` /
  `metadata.parent_session_id`. `_METADATA_ATTRS` ist die verbindliche Liste.
- **Zwei Tag-Quellen, nicht drei.**
  1. `agent:<name>` aus `retain_tags` — das Plugin merged es unbedingt in jedes Payload.
  2. Entity-Tags aus `entity_labels` mit `tag: true` — **nur serverseitig**.
  Frei-form Entities werden **nie** zu Tags; sie landen im Entity-Graph. „Freie Entity-Tags"
  gibt es nicht. `metadata.agent_identity` ergänzt, ersetzt aber nicht den Tag.
- **`entities_allow_free_form: false`** in beiden Banken — bankweit und in jeder Strategie.
  Nur die Label-Werte werden extrahiert; frei erfundene Named Entities entfallen. Tags
  kommen weiterhin ausschließlich aus den Label-Gruppen (`tag: true`).
- **Entity-Labels zweistufig.** `apply_strategy` **ersetzt** `entity_labels` (kein Merge):
  bankweit für `standard`, zusätzlich je Strategie (`raz` 10, `nemo` 11, `coding` 12).
- **`strategy` ist verdrahtet.** Das Plugin liest `strategy` aus der Profil-`config.json`
  und sendet es als Item-Feld; der Server löst dann die passende `retain_strategies`-Fassung
  auf. `""`/`"standard"` → kein Key (Bank-Default). Unbekannte Namen blockieren alle Retains
  (Union aus eingebauter Liste und Bank-Keys, siehe AGENTS.md).
- **`agent` ist inert.** Wird nicht gelesen; `agent_identity` kommt vom Core (initialize),
  der `agent:<name>`-Tag aus `retain_tags`.
- **Keine 0.10.0-Halo-Patches zurückholen.** `allow_retain_tags` und
  `title_first_turn_immediate` sind tote Felder (definiert, nie gelesen); der
  Strategie-Merge-Patch in `config_resolver.py` verhinderte das Löschen von Strategien.
  Der Fork läuft bewusst ohne sie.
- **Achtung `retain_strategies` wird ersetzt, nicht gemergt** (kein Merge-Patch im
  installierten Server). Beim Setzen von Strategien die **vollständige** Map senden,
  sonst gehen Missionen und andere Strategien verloren.
- **Keine Auto-Titel.** Automatische Session-Namen und Document-Titel sind im Fork abgeschafft.
- `config_schema.py` importiert absichtlich aus `plugins.memory.config_schema` — nicht vendorn.
- `pyproject.toml` ist die einzige Abhängigkeits-Autorität (`hindsight-client>=0.10.1,<1`).
- Vor jedem Commit: `python -m pytest tests/ -q`.
- Nach Server-Änderungen: venv neu installieren, `hindsight-api.service` neu starten,
  Migrationen abwarten (der Port bindet erst danach), dann `/version` prüfen
  (`curl -s http://127.0.0.1:9177/version`).
