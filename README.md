# Sweepy for Home Assistant

A custom Home Assistant integration for [Sweepy](https://sweepy.com) — the home cleaning schedule app.

## Features

- **Room cleanliness sensors** — percentage for each room
- **Profile sensors** — daily points, streak, total points per household member
- **Today's task count** — how many tasks are scheduled today
- **Todo lists** — one per profile showing today's scheduled cleaning tasks
- **Mark tasks done** — check off a task in HA and it syncs to Sweepy

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations** → three-dot menu → **Custom repositories**
3. Add `https://github.com/Trkal/HACSSweepy` as an **Integration**
4. Search for "Sweepy" and install
5. Restart Home Assistant
6. Go to **Settings** → **Integrations** → **Add Integration** → search "Sweepy"
7. Enter your Sweepy email and password

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.{room}_cleanliness` | Sensor (%) | Room cleanliness percentage |
| `sensor.{name}_daily_points` | Sensor | Points earned today |
| `sensor.{name}_streak` | Sensor | Consecutive days streak |
| `sensor.{name}_total_points` | Sensor | All-time points |
| `sensor.today_s_tasks` | Sensor | Number of tasks scheduled today |
| `todo.{name}_tasks` | Todo | Today's tasks (checkable) |

## Notes

- Data refreshes every 5 minutes
- Marking a task as done in the todo list immediately calls the Sweepy API
- The integration uses Sweepy's OAuth2 API (reverse-engineered from the app)
