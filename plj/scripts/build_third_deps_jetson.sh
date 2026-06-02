#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THIRD_DIR="${ROOT_DIR}/third"
BUILD_DIR="${THIRD_DIR}/_build"
INSTALL_DIR="${THIRD_DIR}/_install"
JOBS="${JOBS:-4}"

mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

build_gtsam() {
  cmake -S "${THIRD_DIR}/gtsam" -B "${BUILD_DIR}/gtsam" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}" \
    -DGTSAM_BUILD_WITH_MARCH_NATIVE=OFF \
    -DGTSAM_USE_SYSTEM_EIGEN=ON \
    -DGTSAM_BUILD_TESTS=OFF \
    -DGTSAM_BUILD_EXAMPLES_ALWAYS=OFF \
    -DGTSAM_BUILD_UNSTABLE=OFF \
    -DGTSAM_BUILD_WRAP=OFF
  cmake --build "${BUILD_DIR}/gtsam" --parallel "${JOBS}"
  cmake --install "${BUILD_DIR}/gtsam"
}

build_teaser() {
  cmake -S "${THIRD_DIR}/TEASER-plusplus" -B "${BUILD_DIR}/TEASER-plusplus" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}" \
    -DENABLE_DIAGNOSTIC_PRINT=OFF \
    -DBUILD_DOC=OFF \
    -DBUILD_TESTING=OFF \
    -DBUILD_PYTHON_BINDINGS=OFF \
    -DBUILD_MATLAB_BINDINGS=OFF
  cmake --build "${BUILD_DIR}/TEASER-plusplus" --parallel "${JOBS}"
  cmake --install "${BUILD_DIR}/TEASER-plusplus"
}

build_livox_sdk2() {
  cmake -S "${THIRD_DIR}/Livox-SDK2" -B "${BUILD_DIR}/Livox-SDK2" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}"
  cmake --build "${BUILD_DIR}/Livox-SDK2" --parallel "${JOBS}"
  cmake --install "${BUILD_DIR}/Livox-SDK2"
}

build_gtsam
build_teaser
build_livox_sdk2

echo "Third-party CMake dependencies installed to ${INSTALL_DIR}"
