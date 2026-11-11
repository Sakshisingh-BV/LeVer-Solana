# LeVer – Solana development container (GitHub Codespaces)
#
# Everything below lives ONLY inside the cloud container image.
# Nothing is installed on the developer's local machine.
#
# Pinned toolchain (keep in sync with docs/CODESPACES_SETUP.md):
#   Rust 1.79.0 | Solana CLI 1.18.26 | Anchor 0.30.1
# Node 20 and Python 3.11 are added by Dev Container Features
# (see devcontainer.json), not here.
#
# Kani is intentionally NOT installed yet (planned for a later phase).

FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

ARG RUST_VERSION=1.79.0
ARG SOLANA_VERSION=1.18.26
ARG ANCHOR_VERSION=0.30.1

# Build dependencies required by Solana / Anchor / rust crates.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libssl-dev \
        libudev-dev \
        protobuf-compiler \
        llvm \
        clang \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

USER vscode
WORKDIR /home/vscode

# Toolchain locations are all under the container user's home.
ENV RUSTUP_HOME=/home/vscode/.rustup \
    CARGO_HOME=/home/vscode/.cargo
ENV PATH=/home/vscode/.cargo/bin:/home/vscode/.avm/bin:/home/vscode/.local/share/solana/install/active_release/bin:${PATH}

# 1) Rust (pinned, minimal profile)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain ${RUST_VERSION} --profile minimal \
    && rustc --version && cargo --version

# 2) Solana CLI (pinned release from Anza)
RUN sh -c "$(curl -sSfL https://release.anza.xyz/v${SOLANA_VERSION}/install)" \
    && solana --version

# 3) Anchor via AVM. AVM is pinned to the same tag so that it builds on Rust 1.79.
RUN cargo install --git https://github.com/coral-xyz/anchor --tag v${ANCHOR_VERSION} avm --locked --force \
    && avm install ${ANCHOR_VERSION} \
    && avm use ${ANCHOR_VERSION} \
    && anchor --version

ENV RUST_BACKTRACE=1
