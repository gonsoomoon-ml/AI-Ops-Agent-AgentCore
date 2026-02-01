#!/bin/bash

# =============================================================================
# Ops AI Agent 환경 설정 스크립트 (필수)
# =============================================================================
# 사용법:
#   ./setup/create_env.sh
#
# 이 스크립트는 프로젝트 실행 전 반드시 실행해야 합니다.
# Strands Agent SDK 및 관련 패키지를 모두 설치합니다.
#
# 설정 파일:
#   - setup/pyproject.toml: 프로젝트 의존성 정의 (소스)
#   - pyproject.toml: setup/pyproject.toml에서 복사됨
# =============================================================================

set -e

echo ""
echo "========================================"
echo " Ops AI Agent - Environment Setup"
echo "========================================"
echo ""

# 프로젝트 루트로 이동
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)
SETUP_DIR="$PROJECT_ROOT/setup"
echo "Project root: $PROJECT_ROOT"
echo ""

# Step 1: uv 설치 확인
echo "[1/4] Checking uv installation..."
if ! command -v uv &> /dev/null; then
    echo "      Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
fi
echo "      ✓ uv is available"

# Step 2: pyproject.toml 심볼릭 링크 확인/생성
echo "[2/4] Setting up pyproject.toml..."
if [ -f "$SETUP_DIR/pyproject.toml" ]; then
    # 기존 pyproject.toml 처리
    if [ -L "$PROJECT_ROOT/pyproject.toml" ]; then
        echo "      ✓ pyproject.toml symlink already exists"
    elif [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        # 일반 파일이면 백업 후 심볼릭 링크 생성
        mv "$PROJECT_ROOT/pyproject.toml" "$PROJECT_ROOT/pyproject.toml.bak"
        ln -s "setup/pyproject.toml" "$PROJECT_ROOT/pyproject.toml"
        echo "      ✓ pyproject.toml symlink created (backup: pyproject.toml.bak)"
    else
        # 없으면 심볼릭 링크 생성
        ln -s "setup/pyproject.toml" "$PROJECT_ROOT/pyproject.toml"
        echo "      ✓ pyproject.toml symlink created"
    fi
else
    echo "      ✗ setup/pyproject.toml not found!"
    exit 1
fi

# Step 3: 의존성 설치
echo "[3/4] Installing dependencies..."
uv sync --quiet
echo "      ✓ All packages installed"

# Step 4: 설치 확인
echo "[4/4] Verifying installation..."
STRANDS_VER=$(uv run --no-sync python -c "import strands; print('installed')" 2>/dev/null || echo "NOT FOUND")
BOTO3_VER=$(uv run --no-sync python -c "import boto3; print(boto3.__version__)" 2>/dev/null || echo "NOT FOUND")
echo "      strands-agents: $STRANDS_VER"
echo "      boto3: $BOTO3_VER"

echo ""
echo "========================================"
echo " ✓ Setup Complete!"
echo "========================================"
echo ""
echo "다음 단계:"
echo ""
echo "  1. AWS 인증 설정:"
echo "     aws configure"
echo ""
echo "  2. 환경 변수 설정:"
echo "     cp .env.example .env"
echo "     # .env 파일을 편집하여 필요한 값 설정"
echo ""
echo "  3. Agent 실행 (Mock 모드):"
echo "     uv run ops-agent"
echo ""
echo "  4. 테스트 실행:"
echo "     uv run pytest"
echo ""
