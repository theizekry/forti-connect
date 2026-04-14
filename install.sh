#!/usr/bin/env bash
# forti-connect installer
# Supports: macOS (Homebrew), Debian/Ubuntu
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/theizekry/forti-connect/main/install.sh | bash
#
# To audit before running:
#   curl -fsSL https://raw.githubusercontent.com/theizekry/forti-connect/main/install.sh | less

set -e

REPO="https://github.com/theizekry/forti-connect.git"
MIN_PYTHON_MINOR=9

# ── Colors ────────────────────────────────────────────────────
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

info()    { echo -e "${CYAN}[*]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}$*${NC}"; }

# ── Detect OS ─────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)
            if [ -f /etc/debian_version ]; then
                echo "debian"
            else
                echo "linux"
            fi
            ;;
        *) error "Unsupported OS: $(uname -s)" ;;
    esac
}

OS=$(detect_os)

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       forti-connect Installer               ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
info "Platform: $OS"

# ── Step 1: Python 3.9+ ───────────────────────────────────────
step "Step 1/5: Checking Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.minor}')" 2>/dev/null)
        major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        if [ "$major" -eq 3 ] && [ "$version" -ge "$MIN_PYTHON_MINOR" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    warn "Python 3.$MIN_PYTHON_MINOR+ not found. Installing..."
    if [ "$OS" = "macos" ]; then
        if ! command -v brew &>/dev/null; then
            error "Homebrew not found. Install it first: https://brew.sh"
        fi
        brew install python3
    elif [ "$OS" = "debian" ]; then
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-pip python3-venv
    else
        error "Install Python 3.$MIN_PYTHON_MINOR+ manually then re-run."
    fi
    PYTHON="python3"
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
success "Python $PY_VERSION found"

# ── Step 2: pipx ──────────────────────────────────────────────
step "Step 2/5: Checking pipx..."

if ! command -v pipx &>/dev/null; then
    info "Installing pipx..."
    if [ "$OS" = "macos" ]; then
        brew install pipx
    elif [ "$OS" = "debian" ]; then
        # Try apt first (pipx available in Ubuntu 23+/Debian 12+)
        if apt-cache show pipx &>/dev/null 2>&1; then
            sudo apt-get install -y pipx
        else
            "$PYTHON" -m pip install --user pipx
        fi
    else
        "$PYTHON" -m pip install --user pipx
    fi
    # Ensure pipx bin dir is in PATH for this session
    export PATH="$PATH:$HOME/.local/bin"
    pipx ensurepath --force &>/dev/null || true
fi

if ! command -v pipx &>/dev/null; then
    export PATH="$PATH:$HOME/.local/bin"
fi

success "pipx $(pipx --version) found"

# ── Step 3: Install forti-connect ────────────────────────────
step "Step 3/5: Installing forti-connect..."

if pipx list 2>/dev/null | grep -q "forti-connect"; then
    info "Already installed — upgrading..."
    pipx install forti-connect --force --pip-args="--force-reinstall git+$REPO"
else
    pipx install forti-connect --pip-args="git+$REPO"
fi

# Ensure ~/.local/bin in PATH
export PATH="$HOME/.local/bin:$PATH"

if ! command -v vpn &>/dev/null; then
    error "'vpn' command not found after install. Try opening a new terminal."
fi

success "forti-connect installed → $(command -v vpn)"

# ── Step 4: Playwright Firefox ────────────────────────────────
step "Step 4/5: Installing Playwright Firefox..."

# Run playwright install inside the pipx venv
PIPX_HOME="${PIPX_HOME:-$HOME/.local/pipx}"
VPN_VENV=$(find "$PIPX_HOME/venvs" -name "forti-connect" -maxdepth 2 2>/dev/null | head -1)

if [ -n "$VPN_VENV" ] && [ -f "$VPN_VENV/bin/python" ]; then
    "$VPN_VENV/bin/python" -m playwright install firefox
else
    # Fallback: try system playwright
    "$PYTHON" -m playwright install firefox 2>/dev/null || \
    warn "Playwright Firefox install failed. Run manually: playwright install firefox"
fi

success "Playwright Firefox ready"

# ── Step 5: sudo PATH fix ─────────────────────────────────────
step "Step 5/5: Configuring sudo PATH..."

VPN_BIN=$(command -v vpn)
VPN_BIN_DIR=$(dirname "$VPN_BIN")
SUDOERS_FILE="/etc/sudoers.d/af-vpn"

if [ -w /etc/sudoers.d ] || sudo test -d /etc/sudoers.d 2>/dev/null; then
    # Build a secure_path that includes the vpn bin dir
    if [ "$OS" = "macos" ]; then
        SECURE_PATH="$VPN_BIN_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    else
        SECURE_PATH="$VPN_BIN_DIR:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    fi

    echo "Defaults secure_path=\"$SECURE_PATH\"" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    success "sudo PATH configured → $SUDOERS_FILE"
else
    warn "Could not write sudoers. To fix 'sudo vpn up', run:"
    echo "      sudo visudo -f /etc/sudoers.d/af-vpn"
    echo "      # Add: Defaults secure_path=\"$VPN_BIN_DIR:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\""
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║          Installation Complete ✓              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo ""
echo -e "  ${BOLD}1. Configure (one time):${NC}"
echo -e "     vpn setup"
echo ""
echo -e "  ${BOLD}2. Connect:${NC}"
echo -e "     sudo vpn up"
echo ""
echo -e "  ${BOLD}3. Disconnect:${NC}"
echo -e "     sudo vpn down"
echo ""
echo -e "  ${BOLD}Upgrade later:${NC}"
echo -e "     pipx install forti-connect --force --pip-args=\"--force-reinstall git+$REPO\""
echo ""

# Remind to reload shell if PATH was modified
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "Restart your terminal or run: source ~/.bashrc (or ~/.zshrc)"
fi
