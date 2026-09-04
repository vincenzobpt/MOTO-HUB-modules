# MOTO-HUB modules

Loadable modules for MOTO-HUB, and the list the app reads to find them.

MOTO-HUB ships knowing how to run a projection on a motorcycle's dashboard — the compositor, the
encoder, the transport — but not what to project. A module supplies that, and arrives with its own
screens and its own name: an app with nothing installed here has nothing to offer and says so.

## What is in this repository

- **`index.json`** — what the app fetches to know what exists. Adding a module to the offer is
  publishing a file here, not shipping an app update.
- **Releases** — one `.mhm` package per module version, attached as a release asset.

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
