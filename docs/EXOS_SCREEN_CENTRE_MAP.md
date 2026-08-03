# EXOS Screen-to-Centre Map

Audit basis: 18 screen modules/embedded UI surfaces plus three application routes, for 21 audited surfaces. `screens/app_state.py` is a shared state helper rather than a screen.

| Current screen / route | File | Primary user | Approved Centre | Current purpose | Decision | Mobile | Dependencies | Known duplication |
|---|---|---|---|---|---|---|---|---|
| Admin workspace route | `MissionAI.py` | Admin/Designer/Facilitator | Dashboard | Nine-item sidebar and participant query route | Keep; regroup later | Poor: locked expanded sidebar | All active screens, app state | Duplicates separate Facilitator route |
| Facilitator route | `Facilitator.py` | Facilitator | Control Centre | Opens legacy Live Event Console directly | Merge into Control Centre | Tablet/desktop only | `live_event_console` | Control Centre, Show Control |
| Participant route | `Participant.py` | Participant | Identity Centre | Mobile participant application entry | Keep | Primary mobile route; lifecycle certification pending | Participant screen, branding | Also routed through `MissionAI.py?view=participant` |
| Events | `screens/events_home.py` | Admin/Designer | Event Centre | Event cards, active-event selection and navigation | Keep | Usable but desktop-oriented | Sheets, app state | Event Manager existing-events section |
| Create Event | `screens/create_event.py` | Admin/Designer | Event Centre | Guided event creation and programme choice | Keep; merge creation paths | Mixed | Sheets, app state | Event Manager Create Event |
| Event Manager | `screens/event_manager.py` | Admin | Event Centre | Legacy creation, duplication, team setup, road-hunt setup, runtime publish | Merge | Poor | Sheets, runtime, pandas | Create Event, Administration, Programme Builder packs |
| Programme Builder | `screens/programme_builder.py` | Designer | Event Centre | Programme/module/activity ordering, content linking, packs and installers | Keep; split authoring concerns | Poor: 1,900+ line desktop form | Sheets, hierarchy/other engines, client packs | Experience Studio assignment/editing; Event Manager installers |
| Experience Studio (internal Mission Studio) | `screens/mission_setup.py` | Designer | Experience Centre | Template/event experience authoring, media, bulk import and assignment | Keep; clarify template versus event copy | Poor: dense editors/tables | Sheets, media, uploads | Programme Builder experience library and event editors |
| Asset Library | `screens/asset_library.py` | Designer | Experience Centre | Reusable media catalogue | Keep; nest under Centre | Mixed | Sheets Assets, mission media | Media fields inside Experience Studio |
| Control Centre | `screens/control_centre.py` | Facilitator | Control Centre | Stage execution, timer, broadcast, review, wallet and identity recovery | Keep as canonical | Tablet/desktop; dense on phone | Sheets, runtime, live-console widgets, hierarchy | Live Event Console, Show Control, Mission Control |
| Live Event Console | `screens/live_event_console.py` | Facilitator | Control Centre | Legacy all-in-one launch, review, scoring, credits, GPS and leaderboard | Merge, then retire route | Desktop only | Sheets, runtime, Drive/media | Control Centre embeds several widgets |
| Show Control | `screens/show_control.py` | Facilitator | Control Centre | Legacy stage timeline/start/end | Merge/remove after parity | Desktop only | Sheets, stage timer | Control Centre stage/timer controls |
| Mission Control / Experience Control | `screens/mission_control.py` | Facilitator | Control Centre | Placeholder title and info only | Remove | Unknown | None | Name collides with canonical Control Centre |
| Projector | `screens/leaderboard_display.py` | Projector/Facilitator | Control Centre | Public display and display-controller views | Keep as output mode | Projector-first, not phone | Sheets, runtime, broadcast, timers | Live console leaderboard; broadcast helper |
| Broadcast controller/renderer | `screens/projector_broadcast.py` | Facilitator/Projector | Control Centre | Broadcast state controls and render fragments | Keep as shared component | Controller desktop; output responsive | Event metadata, media | Embedded in Control Centre and Projector |
| Reports | `screens/command_centre.py:show_results_reports` | Admin/Facilitator | Intelligence Centre | Results table and export | Keep; expand evidence provenance later | Mixed | Sheets, runtime | Live console leaderboard/scoring, projector rankings |
| Command Centre dashboard | `screens/command_centre.py:show_command_centre` | Admin/Facilitator | Dashboard | Readiness and shortcut dashboard; currently not routed | Keep outside centres; reconnect later | Mixed | Sheets, app state | Events home/readiness metrics |
| Administration | `screens/administration.py` | Admin | Settings | About, EVT-0004 assignment, reset, archive/data safety | Keep Settings; extract event-specific tools | Desktop only | Sheets/runtime | Event Manager reset/archive/setup |
| Experience Library prototype | `screens/experience_library.py` | Designer | Experience Centre | Recommendation-engine catalogue prototype; unrouted | Merge/remove | Basic | Recommendation engine | Experience Studio and Programme Builder libraries |
| Home prototype | `screens/home.py` | Admin/Facilitator | Dashboard | Unrouted legacy landing shortcuts | Remove after dashboard parity | Basic | Callback only | Command Centre dashboard |
| Remote | `screens/remote.py` | Facilitator | Control Centre | Empty legacy file | Remove | None | None | No implementation |

## Summary

- Keep/canonical: 11 surfaces.
- Merge into canonical surface: 6.
- Remove after parity: 4.
- Duplicate interface clusters: seven—event creation, event list/management, experience library, live control, stage control, reporting/leaderboard, and application routing.
- No rename/navigation change is executed by this audit.
