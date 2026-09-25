# F06 rendered walkthrough — Core run log (development Core on 127.0.0.1:52131, fake model route)

UI profile used by the compositions during the walkthrough: uiprof-dcb7bb7a65f42af6ba2e (kit with Form); final published profile after copy fixes: uiprof-fe345cfb0d6818ad55a1.

## Runs created through the bridge (newest first)
- 21:36:59Z add_entry origin=ui state=succeeded reason=None run_ms=52 output={"id": "rec_0829809b9e0142a5a22a382c2e679a61", "revision": 1}
- 21:36:45Z add_entry origin=ui state=failed reason=operation_failed run_ms=51 output=null
- 21:36:23Z remove_entry origin=ui state=succeeded reason=None run_ms=40 output={}
- 21:36:10Z add_entry origin=ui state=succeeded reason=None run_ms=41 output={"id": "rec_05b0385813934776bcb4a5a638c6957a", "revision": 1}
- 21:35:21Z set_status origin=ui state=succeeded reason=None run_ms=48 output={"revision": 2}
- 21:34:29Z update_entry origin=ui state=succeeded reason=None run_ms=47 output={"id": "rec_5805c749167442d780a6f03dcc7a3f36", "revision": 2}
- 21:33:45Z update_entry origin=ui state=failed reason=operation_failed run_ms=44 output=null
- 21:33:35Z update_entry origin=ui state=failed reason=operation_failed run_ms=55 output=null
- 21:23:00Z seed_examples origin=user state=succeeded reason=None run_ms=31 output={"created": 18}

## Failure messages recorded for failed saves
- bd8163ce: invalid_input — entries.amount must be at most 1000
- d9103f23: invalid_input — entries.amount must be at most 1000
- 9d376814: invalid_input — entries.amount must be at most 1000

## Stored state after the walkthrough
- bricks: {"amount": 500, "kind": "note", "noted_on": "2026-09-25", "status": "new"} revision 1
- Example entry 13.1: {"amount": 12, "kind": "note", "noted_on": "2026-09-13", "status": "dismissed"} revision 2
- Example entry 1.1: {"amount": 0.0, "kind": "note", "noted_on": "2026-09-25", "reason": "useful", "status": "kept"} revision 2
