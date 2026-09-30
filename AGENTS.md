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
Eine `session:<ID>`- oder `parent:<ID>`-Tag darf **nie** entstehen — Session-Herkunft
ist Audit-Daten und liegt in `metadata.session_id` / `metadata.parent_session_id`.
`_METADATA_ATTRS` in `__init__.py` ist die verbindliche Liste.

### Zwei Tag-Quellen
1. **`agent:<name>` aus `retain_tags`** (Profil-`config.json`). Das Plugin merged
   `retain_tags` unbedingt in jedes Retain-Payload (`_build_retain_kwargs`). Verifiziert:
   raz → `tags: ["agent:raz"]`, nemo → `["agent:nemo"]`, devi → `["agent:devi"]`.
2. **Entity-Tags aus `entity_labels`** — serverseitig. `_inject_label_tags` projiziert
   **nur** Label-Gruppen mit `tag: true` in die `tags`-Spalte. **Frei-form Entities
   erzeugen KEINE Tags**; sie landen ausschließlich im Entity-Graph
   (`entities` / `unit_entities`). Ohne `entity_labels` gibt es serverseitig keine Tags.

Beleg (zwei Kontrollbänke, Retain ohne `tags` im Payload): mit
`entities_allow_free_form: true` entstanden `Alice`, `Acme Corp`, `Kubernetes`, `AWS`,
`Rust`, `QML` als **Entities** — die Tags blieben `agent:test` + `work:imp`. Frei-form
Entities und Tags sind also getrennte Kanäle.

### Agent-Tags sperren — `accept_agent_tags` (Halo-Fork)
Die obigen zwei Quellen sind **nicht** die einzige Tag-Herkunft. Das
`hindsight_retain`-Tool trägt einen `tags`-Parameter, den der Agent frei befüllt; das
Plugin merged ihn via `_build_retain_kwargs`. Daraus stammen die Badge-Trauben der
Halo-Profile (real beobachtet in `halo-dev`):

```
auto (sync_turn) → ["agent:devi"]
Tool-Call        → ["agent:devi","taurid","ops","worker","rust","tauri","ipc","kanban-protokoll"]
```

Steuerung über `accept_agent_tags` (Profil-`hindsight/config.json`, Default `true`):

* **`false`** → das Tool verwirft `args["tags"]` und **entfernt `tags` aus dem
  Schema** (ein angebotenes, aber ignoriertes Feld kostet Tokens und führt das Modell in
  die Irre). Damit bleibt pro Retain nur `retain_tags` + die Server-Label-Tags.
* Gesperrt wird **nur am Tool-Pfad**, nicht in `_build_retain_kwargs`: derselbe Builder
  bedient Auto-Retain, den Native-Store-Mirror und den Pre-Compress-Checkpoint, deren
  Tags **intern** sind. Zentrales Verwerfen würde den Reverse-Lookup des Mirrors
  (`_mirror_tag` → `native-mirror:<target>:<sha>`) zerstören.
* `entities_allow_free_form` berührt diesen Kanal **nicht** — es steuert die
  Entity-Extraktion, nicht die Tags.

`metadata.agent_identity` wird zusätzlich gestempelt, ersetzt aber nie den Tag — gefiltert
wird über `tags`.

### Tag-Konvention
| Profil | `retain_tags` | `recall_tags` | `agent:<name>`-Tag |
|---|---|---|---|
| cherub | *(leer)* | *(leer)* | **nein** — bewusst, damit bankweit sichtbar |
| raz, nemo | `agent:<name>` | `agent:<name>` | ja |
| devi, appsec, fronti, revi, taurid, tester | `agent:<name>` | `agent:<name>` | ja |

Alle Profile bekommen zusätzlich die Entity-Tags ihrer Bank/Strategie — auch cherub.

### Entity-Labels — die eigentliche Tag-Quelle
`entities_allow_free_form` steht bewusst auf **`false`** — bankweit **und** in jeder Strategie
(`halo`/`standard`, `halo`/`raz`, `halo`/`nemo`, `halo-dev`/`coding`): nur die Label-Werte
werden extrahiert, keine frei erfundenen Named Entities. Tags entstehen ohnehin **nur** aus
den Label-Gruppen (`tag: true`).
Die Gruppen liegen **zweistufig**: bankweit (Default `standard`) **und** je Strategie.
`apply_strategy` **ersetzt** `entity_labels`, es mergt nicht — eine Strategie ohne eigene
Labels fällt auf die Bank-Gruppen zurück, eine Strategie mit `entity_labels: []` löscht sie.

| Ebene | Gruppen |
|---|---|
| `halo` bankweit (`standard`) | 14: akki, cherb, speci, recht, ernae, sozia, kommu, priva, infra, mem, plugi, platf, konve, entsc |
| `halo` — Strategie `raz` | 10: text, urt, uebe, krit, kano, exeg, quel, geo, zeit, disk |
| `halo` — Strategie `nemo` | 11: klasse, dosis, form, wirk, ziel, einn, inter, zykl, evid, belast, quel |
| `halo-dev` bankweit (`coding`) | 12: work, code, stck, test, revi, secu, meth, depl, perf, conf, task, repo |

### Banken
| Bank | Profile | `retain_default_strategy` | Strategien |
|---|---|---|---|
| `halo` | cherub, raz, nemo | `standard` | `raz`, `nemo` |
| `halo-dev` | devi, appsec, fronti, revi, taurid, tester | `coding` | `coding` |

### `strategy` — verdrahtet (Retain-Strategie je Profil)
Das Plugin liest `strategy` aus der Profil-`config.json` und sendet es als **Item-Feld**
(`_build_retain_kwargs`), damit der Server die passende `retain_strategies`-Fassung
auflöst statt der Bank-Defaults.

* `""` bzw. `"standard"` → **kein** Key: die Bank-Config gilt direkt (`standard` ist der
  eingebaute „keine benannte Strategie"-Selektor, den der Server nicht kennt; er wird
  client-seitig zu `""` normalisiert).
* Ein Name, der weder in `{coding, raz, standard}` noch in den `retain_strategies`-Keys
  der Bank steht, **blockiert jeden Retain** (laut, kein stiller Fallback) — geprüft im
  zentralen `_retain_batch`.
* Die Bank weitet die eingebaute Liste per **Union** (`_bank_strategy_names`, gecacht,
  Fehler nie fatal): eine neu in der Bank angelegte Strategie funktioniert ohne
  Client-Änderung.

| Profil | `strategy` | wirksame Gruppen |
|---|---|---|
| cherub | `""` | `standard` → 14 Bank-Gruppen |
| nemo | `nemo` | 11 nemo-Gruppen |
| raz | `raz` | 10 raz-Gruppen |
| devi, appsec, fronti, revi, taurid, tester | `coding` | 12 coding-Gruppen |

> **Kein Netz-Lookup aus `__init__`.** `_apply_retain_policy({})` läuft aus `__init__`
> **vor** `_apply_connection_settings`; ein Bank-Lookup dort cached den Client gegen die
> Default-Cloud-URL und jede spätere Abfrage läuft ins 401. Der Bank-Lookup passiert
> ausschließlich auf dem Versandpfad.

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
