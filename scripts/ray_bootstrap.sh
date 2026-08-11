#!/usr/bin/env bash
################################################################################
# ZeroPoint Ray Cluster Bootstrap Script
# Two-node x86 cluster (head + worker)
# Generated: 2026-07-14
# Usage:
#   On HEAD node:   ./ray_bootstrap.sh head
#   On WORKER node: ./ray_bootstrap.sh worker <HEAD_IP>
################################################################################

set -euo pipefail

###############################################################################
# CONFIGURATION — edit these before running
###############################################################################
CLUSTER_NAME="zeropoint-cluster"
RAY_VERSION="2.34.0"
PYTHON_VERSION="3.11"

HEAD_IP="${HEAD_IP:-192.168.100.1}"
WORKER_IP="${WORKER_IP:-192.168.100.2}"
RAY_PORT=6379
DASHBOARD_PORT=8265
OBJECT_STORE_MEMORY_GB=8
HEAD_NUM_CPUS=8
HEAD_NUM_GPUS=0
WORKER_NUM_CPUS=8
WORKER_NUM_GPUS=0

MCP_WORKSPACE="/workspace/zeropoint"
MCP_VENV="/opt/zeropoint/venv"
LOG_DIR="/var/log/zeropoint-ray"
DATA_DIR="/data/camnet"

RAY_NAMESPACE="zeropoint"
REDIS_PASSWORD="${RAY_REDIS_PASSWORD:-zeropoint-ray-secret}"

###############################################################################
# COLORS & LOGGING
###############################################################################
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠ $*${NC}"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗ $*${NC}" >&2; exit 1; }
info() { echo -e "${BLUE}[$(date '+%H:%M:%S')] → $*${NC}"; }

###############################################################################
# HELPERS
###############################################################################
require_root() {
  [[ $EUID -eq 0 ]] || err "This script must be run as root (sudo ./ray_bootstrap.sh ...)"
}

detect_os() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_VERSION="$VERSION_ID"
  else
    err "Cannot detect OS — /etc/os-release not found."
  fi
  info "Detected OS: $OS_ID $OS_VERSION"
}

install_system_deps() {
  info "Installing system dependencies..."
  case "$OS_ID" in
    ubuntu|debian)
      apt-get update -qq
      apt-get install -y --no-install-recommends \
        python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python3-pip \
        curl wget git build-essential \
        libssl-dev libffi-dev \
        android-tools-adb \
        net-tools iproute2 \
        jq htop tmux
      ;;
    rhel|centos|fedora|rocky|almalinux)
      dnf install -y \
        python${PYTHON_VERSION} python3-pip \
        curl wget git gcc gcc-c++ \
        openssl-devel libffi-devel \
        android-tools \
        net-tools iproute \
        jq htop tmux
      ;;
    *)
      warn "Unknown OS '$OS_ID' — skipping system package install. Ensure dependencies are present."
      ;;
  esac
  log "System dependencies installed."
}

setup_venv() {
  info "Setting up Python virtual environment at $MCP_VENV..."
  mkdir -p "$(dirname "$MCP_VENV")"
  python${PYTHON_VERSION} -m venv "$MCP_VENV"
  # shellcheck disable=SC1090
  source "$MCP_VENV/bin/activate"

  pip install --upgrade pip wheel setuptools -q
  pip install \
    "ray[default]==${RAY_VERSION}" \
    "ray[serve]==${RAY_VERSION}" \
    "mcp-server>=0.4.0" \
    "aiohttp>=3.9" \
    "pyyaml>=6.0" \
    "click>=8.1" \
    "rich>=13.0" \
    "prometheus-client>=0.20" \
    "opentelemetry-sdk>=1.25" \
    "opentelemetry-exporter-otlp>=1.25" \
    "appium-python-client>=3.1" \
    "uiautomator2>=3.0" \
    "requests>=2.32" \
    "beautifulsoup4>=4.12" \
    "lxml>=5.0" \
    -q

  log "Python venv ready: $MCP_VENV"
}

create_directories() {
  info "Creating directory structure..."
  mkdir -p \
    "$MCP_WORKSPACE"/{config,tools,tasks,logs} \
    "$LOG_DIR" \
    "$DATA_DIR"/{screenshots,recordings,sync} \
    /tmp/mcp_scratch

  chmod 1777 /tmp/mcp_scratch
  log "Directories created."
}

configure_system() {
  info "Configuring system limits..."

  # Increase file descriptor limits for Ray
  cat > /etc/security/limits.d/99-zeropoint.conf <<EOF
* soft nofile 65536
* hard nofile 65536
* soft nproc 32768
* hard nproc 32768
EOF

  # Kernel tunables for Ray object store and networking
  cat > /etc/sysctl.d/99-zeropoint.conf <<EOF
# Shared memory for Ray object store
kernel.shmmax = $(python3 -c "print(${OBJECT_STORE_MEMORY_GB} * 1024**3)")
kernel.shmall = $(python3 -c "print(${OBJECT_STORE_MEMORY_GB} * 1024**3 // 4096)")

# Network performance
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.netdev_max_backlog = 5000
net.core.somaxconn = 1024
EOF
  sysctl -p /etc/sysctl.d/99-zeropoint.conf > /dev/null
  log "System limits configured."
}

###############################################################################
# HEAD NODE SETUP
###############################################################################
start_head_node() {
  info "Starting Ray HEAD node on $HEAD_IP..."

  source "$MCP_VENV/bin/activate"

  # Stop any existing Ray instance
  ray stop --force 2>/dev/null || true
  sleep 2

  ray start \
    --head \
    --node-ip-address="$HEAD_IP" \
    --port="$RAY_PORT" \
    --dashboard-host="0.0.0.0" \
    --dashboard-port="$DASHBOARD_PORT" \
    --num-cpus="$HEAD_NUM_CPUS" \
    --num-gpus="$HEAD_NUM_GPUS" \
    --object-store-memory="$(( OBJECT_STORE_MEMORY_GB * 1024 * 1024 * 1024 ))" \
    --redis-password="$REDIS_PASSWORD" \
    --log-color=true \
    --log-style=pretty \
    --block &

  RAY_PID=$!
  echo "$RAY_PID" > /var/run/zeropoint-ray-head.pid

  # Wait for Ray to be ready
  info "Waiting for Ray head to become ready..."
  for i in $(seq 1 30); do
    if ray status --address="${HEAD_IP}:${RAY_PORT}" &>/dev/null; then
      log "Ray head node ready (attempt $i/30)."
      break
    fi
    sleep 2
  done

  log "Ray HEAD node started. Dashboard: http://${HEAD_IP}:${DASHBOARD_PORT}"
}

start_mcp_server_head() {
  info "Starting ZeroPoint MCP server on head node..."

  source "$MCP_VENV/bin/activate"

  RAY_ADDRESS="${HEAD_IP}:${RAY_PORT}" \
  RAY_NAMESPACE="${RAY_NAMESPACE}" \
  MCP_CONFIG="${MCP_WORKSPACE}/config/mcp_server_config.yaml" \
    nohup python -m zeropoint.server \
      --config "${MCP_WORKSPACE}/config/mcp_server_config.yaml" \
      >> "$LOG_DIR/mcp-server.log" 2>&1 &

  echo $! > /var/run/zeropoint-mcp.pid
  log "MCP server started (PID: $(cat /var/run/zeropoint-mcp.pid))"
}

setup_head_firewall() {
  info "Configuring firewall rules for head node..."
  if command -v ufw &>/dev/null; then
    ufw allow from "${WORKER_IP}" to any port "${RAY_PORT}" proto tcp
    ufw allow from any to any port "${DASHBOARD_PORT}" proto tcp
    ufw allow from any to any port 8765 proto tcp   # MCP server
    ufw allow from any to any port 9090 proto tcp   # Prometheus
    log "UFW rules applied."
  elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="${RAY_PORT}/tcp"
    firewall-cmd --permanent --add-port="${DASHBOARD_PORT}/tcp"
    firewall-cmd --permanent --add-port="8765/tcp"
    firewall-cmd --permanent --add-port="9090/tcp"
    firewall-cmd --reload
    log "firewalld rules applied."
  else
    warn "No firewall manager detected — configure ports manually."
    warn "Required ports: ${RAY_PORT} (Ray), ${DASHBOARD_PORT} (Dashboard), 8765 (MCP), 9090 (Metrics)"
  fi
}

###############################################################################
# WORKER NODE SETUP
###############################################################################
start_worker_node() {
  local head_ip="${1:-$HEAD_IP}"
  info "Starting Ray WORKER node, connecting to head at ${head_ip}:${RAY_PORT}..."

  source "$MCP_VENV/bin/activate"

  ray stop --force 2>/dev/null || true
  sleep 2

  ray start \
    --address="${head_ip}:${RAY_PORT}" \
    --node-ip-address="$WORKER_IP" \
    --num-cpus="$WORKER_NUM_CPUS" \
    --num-gpus="$WORKER_NUM_GPUS" \
    --object-store-memory="$(( OBJECT_STORE_MEMORY_GB * 1024 * 1024 * 1024 ))" \
    --redis-password="$REDIS_PASSWORD" \
    --log-color=true \
    --block &

  RAY_WORKER_PID=$!
  echo "$RAY_WORKER_PID" > /var/run/zeropoint-ray-worker.pid

  log "Ray WORKER node started (PID: $RAY_WORKER_PID)"
}

###############################################################################
# HEALTH CHECK
###############################################################################
health_check() {
  info "Running cluster health check..."
  source "$MCP_VENV/bin/activate"

  echo ""
  echo "════════════════════════════════════════"
  echo "  ZeroPoint Ray Cluster Status"
  echo "════════════════════════════════════════"
  ray status --address="${HEAD_IP}:${RAY_PORT}" 2>/dev/null || warn "Cannot reach Ray head — is it running?"

  echo ""
  echo "  MCP Server Health:"
  curl -sf "http://${HEAD_IP}:8765/health" 2>/dev/null \
    && log "MCP server responding." \
    || warn "MCP server not responding on :8765"

  echo ""
  echo "  ADB Devices:"
  adb devices -l 2>/dev/null || warn "ADB not available."
  echo "════════════════════════════════════════"
}

###############################################################################
# TEARDOWN
###############################################################################
teardown() {
  warn "Stopping ZeroPoint Ray cluster..."
  source "$MCP_VENV/bin/activate" 2>/dev/null || true

  [[ -f /var/run/zeropoint-mcp.pid ]] && kill "$(cat /var/run/zeropoint-mcp.pid)" 2>/dev/null || true
  ray stop --force 2>/dev/null || true

  log "Cluster stopped."
}

###############################################################################
# SYSTEMD UNIT (optional install)
###############################################################################
install_systemd_services() {
  info "Installing systemd services..."

  cat > /etc/systemd/system/zeropoint-ray-head.service <<EOF
[Unit]
Description=ZeroPoint Ray Head Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile=/etc/zeropoint/env
ExecStartPre=${MCP_VENV}/bin/ray stop --force
ExecStart=${MCP_VENV}/bin/ray start --head \\
  --node-ip-address=${HEAD_IP} \\
  --port=${RAY_PORT} \\
  --dashboard-host=0.0.0.0 \\
  --dashboard-port=${DASHBOARD_PORT} \\
  --redis-password=\${RAY_REDIS_PASSWORD} \\
  --num-cpus=${HEAD_NUM_CPUS} \\
  --block
ExecStop=${MCP_VENV}/bin/ray stop --force
Restart=on-failure
RestartSec=10
StandardOutput=append:${LOG_DIR}/ray-head.log
StandardError=append:${LOG_DIR}/ray-head-err.log

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/zeropoint-mcp.service <<EOF
[Unit]
Description=ZeroPoint MCP Server
After=zeropoint-ray-head.service
Requires=zeropoint-ray-head.service

[Service]
Type=simple
User=root
WorkingDirectory=${MCP_WORKSPACE}
EnvironmentFile=/etc/zeropoint/env
Environment=RAY_ADDRESS=${HEAD_IP}:${RAY_PORT}
Environment=RAY_NAMESPACE=${RAY_NAMESPACE}
ExecStart=${MCP_VENV}/bin/python -m zeropoint.server \\
  --config ${MCP_WORKSPACE}/config/mcp_server_config.yaml
Restart=on-failure
RestartSec=5
StandardOutput=append:${LOG_DIR}/mcp-server.log
StandardError=append:${LOG_DIR}/mcp-server-err.log

[Install]
WantedBy=multi-user.target
EOF

  mkdir -p /etc/zeropoint
  cat > /etc/zeropoint/env <<EOF
RAY_REDIS_PASSWORD=${REDIS_PASSWORD}
MCP_AUTH_TOKEN=CHANGE_ME_BEFORE_PRODUCTION
EOF
  chmod 600 /etc/zeropoint/env

  systemctl daemon-reload
  systemctl enable zeropoint-ray-head zeropoint-mcp
  log "Systemd services installed and enabled."
}

###############################################################################
# MAIN
###############################################################################
main() {
  local mode="${1:-help}"
  shift || true

  require_root
  detect_os

  case "$mode" in
    head)
      info "=== Bootstrapping HEAD node ==="
      install_system_deps
      setup_venv
      create_directories
      configure_system
      setup_head_firewall
      start_head_node
      start_mcp_server_head
      health_check
      log "HEAD node bootstrap complete!"
      log "Dashboard: http://${HEAD_IP}:${DASHBOARD_PORT}"
      log "MCP Server: http://${HEAD_IP}:8765"
      ;;
    worker)
      HEAD_ADDR="${1:-$HEAD_IP}"
      info "=== Bootstrapping WORKER node (head: $HEAD_ADDR) ==="
      install_system_deps
      setup_venv
      create_directories
      configure_system
      start_worker_node "$HEAD_ADDR"
      log "WORKER node bootstrap complete!"
      ;;
    health)
      health_check
      ;;
    install-services)
      install_systemd_services
      ;;
    teardown)
      teardown
      ;;
    help|*)
      cat <<HELP
ZeroPoint Ray Cluster Bootstrap

Usage:
  sudo ./ray_bootstrap.sh head                   # Bootstrap head node
  sudo ./ray_bootstrap.sh worker [HEAD_IP]       # Bootstrap worker node
  sudo ./ray_bootstrap.sh health                 # Check cluster health
  sudo ./ray_bootstrap.sh install-services       # Install systemd units
  sudo ./ray_bootstrap.sh teardown               # Stop cluster

Environment variables:
  HEAD_IP              Head node IP         (default: 192.168.100.1)
  WORKER_IP            Worker node IP       (default: 192.168.100.2)
  RAY_REDIS_PASSWORD   Redis/GCS password   (default: zeropoint-ray-secret)
HELP
      ;;
  esac
}

main "$@"
