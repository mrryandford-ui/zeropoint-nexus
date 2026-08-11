# ZeroPoint MCP Stack — Directory Layout

```
/
├── workspace/
│   └── zeropoint/                          # MCP workspace root
│       ├── config/
│       │   ├── mcp_server_config.yaml      # Master server config
│       │   ├── tool_registration.json      # Tool manifest
│       │   └── logging.yaml                # Logging config
│       │
│       ├── tools/                          # Tool implementations
│       │   ├── __init__.py
│       │   ├── filesystem.py               # FilesystemTool
│       │   ├── webtools.py                 # WebtoolsTool
│       │   ├── adb.py                      # AdbTool
│       │   └── android.py                  # AndroidTool + CamNet
│       │
│       ├── tasks/                          # Scheduled / queued tasks
│       │   ├── pending/
│       │   ├── running/
│       │   └── completed/
│       │
│       └── logs/                           # App-level logs
│           ├── server.log
│           └── tools/
│               ├── filesystem.log
│               ├── webtools.log
│               ├── adb.log
│               └── android.log
│
├── opt/
│   └── zeropoint/
│       └── venv/                           # Python virtualenv
│           ├── bin/
│           │   ├── python
│           │   ├── ray
│           │   └── activate
│           └── lib/
│               └── python3.11/
│                   └── site-packages/
│                       ├── ray/
│                       ├── mcp_server/
│                       ├── uiautomator2/
│                       └── appium/
│
├── data/
│   └── camnet/                             # CamNet media storage
│       ├── screenshots/                    # ADB screencaps
│       │   ├── cam-0/
│       │   ├── cam-1/
│       │   ├── cam-2/
│       │   └── cam-3/
│       ├── recordings/                     # Video captures
│       │   ├── cam-0/
│       │   ├── cam-1/
│       │   ├── cam-2/
│       │   └── cam-3/
│       └── sync/                           # Synced media staging area
│           └── YYYY-MM-DD/                 # Date-partitioned
│
├── etc/
│   ├── zeropoint/
│   │   └── env                             # Secrets / env vars (chmod 600)
│   ├── systemd/system/
│   │   ├── zeropoint-ray-head.service
│   │   ├── zeropoint-ray-worker.service
│   │   └── zeropoint-mcp.service
│   └── sysctl.d/
│       └── 99-zeropoint.conf
│
├── var/
│   ├── log/
│   │   └── zeropoint-ray/
│   │       ├── ray-head.log
│   │       ├── ray-head-err.log
│   │       ├── mcp-server.log
│   │       └── mcp-server-err.log
│   └── run/
│       ├── zeropoint-ray-head.pid
│       ├── zeropoint-ray-worker.pid
│       └── zeropoint-mcp.pid
│
└── tmp/
    └── mcp_scratch/                        # Ephemeral tool scratch space
```

## Source Repository Layout

```
zeropoint-mcp/                              # Repo root
├── README.md
├── pyproject.toml
├── setup.cfg
├── .env.example
│
├── mcp_server_config.yaml                  # ← generated config
├── tool_registration.json                  # ← generated manifest
├── ray_bootstrap.sh                        # ← cluster bootstrap
├── directory_layout.md                     # ← this file
│
├── zeropoint/                              # Python package
│   ├── __init__.py
│   ├── server.py                           # MCP server entrypoint
│   ├── registry.py                         # Tool loader & router
│   ├── auth.py                             # Bearer token middleware
│   ├── observability.py                    # Metrics + tracing
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                         # BaseTool ABC
│   │   ├── filesystem.py
│   │   ├── webtools.py
│   │   ├── adb.py
│   │   └── android/
│   │       ├── __init__.py
│   │       ├── tool.py                     # AndroidTool
│   │       ├── camnet.py                   # CamNet orchestrator
│   │       ├── ui.py                       # UiAutomator2 helpers
│   │       └── camera.py                   # Camera capture helpers
│   │
│   └── ray_actors/
│       ├── __init__.py
│       ├── webtools_actor.py
│       └── camnet_actor.py
│
├── android/                                # Android automation
│   ├── camnet_controller.py                # Multi-device controller
│   ├── device_registry.yaml               # Static device list
│   ├── appium_config.yaml
│   └── scripts/
│       ├── connect_all.sh                  # ADB connect all devices
│       ├── disconnect_all.sh
│       ├── bulk_screencap.sh
│       └── sync_media.sh
│
├── tests/
│   ├── unit/
│   │   ├── test_filesystem.py
│   │   ├── test_webtools.py
│   │   ├── test_adb.py
│   │   └── test_android.py
│   └── integration/
│       ├── test_mcp_server.py
│       ├── test_ray_cluster.py
│       └── test_camnet.py
│
├── scripts/
│   ├── ray_bootstrap.sh                    # ← generated bootstrap
│   ├── dev_start.sh                        # Local dev server
│   └── healthcheck.sh
│
└── docker/
    ├── Dockerfile.head
    ├── Dockerfile.worker
    └── docker-compose.yaml
```
