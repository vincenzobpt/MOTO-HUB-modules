# MOTO-HUB modules

Loadable modules for MOTO-HUB, the community dashboards, and the lists the app reads to find them.

MOTO-HUB ships knowing how to run a projection on a motorcycle's dashboard — the compositor, the
encoder, the transport — but not what to project. A module supplies that, and arrives with its own
screens and its own name: an app with nothing installed here has nothing to offer and says so.

## What is in this repository

- **`index.json`** — what the app fetches to know what exists. Adding a module to the offer is
  publishing a file here, not shipping an app update.
- **Releases** — one `.mhm` package per module version, attached as a release asset.
- **`dashboards/`** — the community dashboards: the `.mhd` files, and the index the app's
  Community page reads. See [Community dashboards](#community-dashboards).

Nothing else. The modules' source lives in their own repositories, under their own licences.

## The `.mhm` package

One file: a zip holding the module's dex and the Ed25519 signature that covers it. One file
rather than two because two that only make sense together are two chances to pair the wrong ones.

The app verifies that signature when the module is installed **and again every time it is
loaded** — a file that passed on the way in can still be replaced afterwards, and nothing else
checks it. The platform vets the signer of an APK; a file the app loads itself has no such gate.
So a package downloaded from here and one picked out of Downloads meet exactly the same checks:
where a file came from changes nothing about how far it is trusted.

Assets are named `<module-id>-<version>.mhm`. The version must start with a digit, which is what
stops `android-auto` from claiming `android-auto-extras-1.0.0.mhm` once modules multiply.

## Adding a module to the list

Append an object to `index.json`:

```json
{
  "id": "android-auto",
  "displayName": "Android Auto",
  "summary": "Runs Android Auto on the motorcycle's screen.",
  "owner": "vincenzobpt",
  "repository": "MOTO-HUB-modules"
}
```

`owner`/`repository` say where the releases are; a module hosted elsewhere points there instead.

The index only advertises. Nothing in it is trusted: the app still verifies whatever it downloads
against its own key, and refuses a package whose manifest says something different from what the
index promised.

## Modules

| Module | Licence | Source |
| --- | --- | --- |
| `android-auto` | AGPL-3.0-only | published with its release |

## Community dashboards

The dashboards riders share, shown in the app under **Ride → Dashboard map → Community**.

```
dashboards/
  files/<id>.mhd        the dashboards, one file each, named after the id inside
  listing.json          the only hand-written part: kind, tags, featured
  index.json            generated - never edit
  previews/<id>.png     generated - extracted from each file
```

### Adding a dashboard

1. Make it in the MOTO-HUB Dashboard Editor and save it as `.mhd`, with a preview image.
   Give it an id of your own (`yourname.alpine-split`): ids starting with `motohub.` belong to
   the dashboards the app ships.
2. Put the file in `dashboards/files/`, named `<id>.mhd`.
3. Optionally describe it in `dashboards/listing.json`:

   ```json
   {
     "yourname.alpine-split": { "kind": "touring", "tags": ["curves", "mountain"], "featured": false }
   }
   ```

   `kind` is one of `ride`, `touring`, `engine`, `track`, `minimal` (default `ride`).
4. Open a pull request. The workflow checks every file; once merged it rebuilds
   `dashboards/index.json` and the previews.

To check locally: `python3 tools/build_dashboard_index.py --check`.

### What the index says, and where it comes from

Everything the app filters on is read from the file itself, never typed by hand: canvas size and
orientations, the map engine (the first map element decides; no map means the OBD session),
whether an OBD adapter or a module is needed, the minimum app version, and the elements used.
Published and updated dates are the file's first and last commit. Each entry carries the
SHA-256 of the file and of its preview.

### Why it can be trusted as far as it needs to be

A dashboard carries no code: the worst a bad file can do is draw badly. The app fetches the index
and the files from this repository's raw host (no GitHub API, no token), checks each download
against the SHA-256 in the index, and then imports it through the same validator as a file picked
from the phone's storage - where a dashboard came from changes nothing about what it may do.
