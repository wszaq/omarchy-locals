# Controls

## Icon toolbar

| Icon | Action |
|------|--------|
| Containers | Show / hide Docker rows |
| Localhosts | Show / hide app-like localhost rows |
| Ports | Show / hide other listeners (off by default) |
| Default | Reset sort to default |
| Sort | Cycle Default → A–Z → Port |
| Options | Preferences (poll interval, open config, run autostart) |

## Actions menu

Each row has **Actions ▾**. Only legal actions appear:

- **Docker:** Start, Stop, Pause, Resume, Restart, Start on login, Docker TUI, Ignore
- **Localhost (user PID):** Pause, Stop, Restart (when cmdline known), Open, Start on login, Ignore
- **System / docker-proxy:** Open / Ignore only (never signaled)

## Resource KPIs

Under the green accent meter on Containers and Localhosts rows:

**CPU · MEM · PIDs**

Docker uses batched `docker stats`. Host listeners sample `/proc` (CPU needs a poll or two for a real %).
