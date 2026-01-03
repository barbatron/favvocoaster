#!/bin/bash
# Build Lambda deployment package
# Run from project root: ./deploy/build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/.build"
OUTPUT="$SCRIPT_DIR/lambda.zip"

echo "🔨 Building Lambda package..."
echo "   Project: $PROJECT_DIR"
echo "   Output:  $OUTPUT"

# Clean
rm -rf "$BUILD_DIR" "$OUTPUT"
mkdir -p "$BUILD_DIR"

# Install dependencies into build dir
echo "📦 Installing dependencies..."
pip install \
    --target "$BUILD_DIR" \
    --platform manylinux2014_x86_64 \
    --only-binary=:all: \
    --implementation cp \
    --python-version 3.12 \
    spotipy pydantic pydantic-settings python-dotenv

# Copy our code
echo "📂 Copying application code..."
cp -r "$PROJECT_DIR/favvocoaster" "$BUILD_DIR/"

# Remove unnecessary stuff to reduce size
echo "🧹 Cleaning up..."
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$BUILD_DIR/bin" 2>/dev/null || true

# Create zip
echo "📦 Creating zip..."
cd "$BUILD_DIR"
zip -r "$OUTPUT" . -x "*.pyc" -x "*__pycache__*" > /dev/null

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "✅ Built $OUTPUT ($SIZE)"
